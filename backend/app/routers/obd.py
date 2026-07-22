"""OBD log endpoints: import a Car Scanner CSV, list/read/delete sessions."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import ROLE_EDITOR, ROLE_OWNER, ROLE_VIEWER, get_accessible_car
from app.auth import get_current_user
from app.database import get_db
from app.models import ObdMetric, ObdSession, User
from app.schemas import ObdMetricOut, ObdSessionDetail, ObdSessionOut, ObdVerdictOut
from app.services.obd import ObdParseError, parse_obd_csv, session_verdicts, summarize
from app.i18n import t

router = APIRouter(tags=["obd"])

# A one-hour log at 1 Hz over ~40 PIDs is roughly 8 MB of CSV; 20 leaves room
# for the chattier profiles without letting a stray file through.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

# Browsers and file managers disagree about what a .csv is: Safari sends
# text/csv, Windows sends application/vnd.ms-excel, some send octet-stream.
# The extension is the tie-breaker.
CSV_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "text/csv",
        "application/csv",
        "text/plain",
        "text/comma-separated-values",
        "application/vnd.ms-excel",
        "application/octet-stream",
    }
)


def get_owned_session(
    db: Session, user: User, session_id: int, min_role: str = ROLE_OWNER
) -> ObdSession:
    """Fetch an OBD session the user may act on at ``min_role``, or raise 404/403.

    ``min_role`` defaults to 'owner' so a caller that forgets to widen it
    fails closed.
    """
    obd_session = db.execute(
        select(ObdSession).where(ObdSession.id == session_id)
    ).scalar_one_or_none()
    if obd_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    get_accessible_car(
        db, user, obd_session.car_id, min_role=min_role, not_found_detail="Session not found"
    )
    return obd_session


def _decode_csv(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _detail(db: Session, obd_session: ObdSession, unmapped: list[str]) -> ObdSessionDetail:
    metrics = list(
        db.execute(
            select(ObdMetric).where(ObdMetric.session_id == obd_session.id).order_by(ObdMetric.id)
        )
        .scalars()
        .all()
    )
    summaries = [
        {"key": m.key, "min": m.min, "max": m.max, "avg": m.avg, "last": m.last}
        for m in metrics
    ]
    return ObdSessionDetail(
        session=ObdSessionOut.model_validate(obd_session),
        metrics=[ObdMetricOut.model_validate(m) for m in metrics],
        verdicts=[ObdVerdictOut(**verdict) for verdict in session_verdicts(summaries)],
        unmapped_columns=unmapped,
    )


@router.post(
    "/cars/{car_id}/obd",
    response_model=ObdSessionDetail,
    status_code=status.HTTP_201_CREATED,
)
async def import_obd_csv(
    car_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ObdSessionDetail:
    """Import a Car Scanner CSV log (max 20 MB) for a car the user can edit.

    The file itself is never stored: it is parsed into canonical metrics whose
    series are capped at 200 points each.
    """
    car = get_accessible_car(db, current_user, car_id, min_role=ROLE_EDITOR)

    filename = file.filename or "obd.csv"
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in CSV_CONTENT_TYPES and not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=t("err.onlyCarScannerCsv", current_user.language),
        )

    too_large = HTTPException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        detail=t("err.fileTooLarge20", current_user.language),
    )
    # Same cap strategy as the photo endpoint: check the spooled size first,
    # then read at most one byte over the limit.
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise too_large
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise too_large

    try:
        parsed = parse_obd_csv(_decode_csv(raw))
    except ObdParseError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error

    obd_session = ObdSession(
        car_id=car.id,
        filename=filename[:255],
        recorded_at=parsed["recorded_at"],
        duration_s=parsed["duration_s"],
        sample_count=parsed["sample_count"],
    )
    db.add(obd_session)
    db.flush()

    for metric in parsed["metrics"]:
        summary = summarize(metric["key"], metric["unit"], metric["samples"])
        db.add(
            ObdMetric(
                session_id=obd_session.id,
                key=summary["key"],
                unit=summary["unit"],
                min=summary["min"],
                max=summary["max"],
                avg=summary["avg"],
                last=summary["last"],
                series=[[t, value] for t, value in summary["series"]],
            )
        )
    db.commit()
    db.refresh(obd_session)
    return _detail(db, obd_session, parsed["unmapped_columns"])


@router.get("/cars/{car_id}/obd", response_model=list[ObdSessionOut])
def list_obd_sessions(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ObdSession]:
    car = get_accessible_car(db, current_user, car_id, min_role=ROLE_VIEWER)
    return list(
        db.execute(
            select(ObdSession)
            .where(ObdSession.car_id == car.id)
            .order_by(ObdSession.created_at.desc(), ObdSession.id.desc())
        )
        .scalars()
        .all()
    )


@router.get("/obd/{session_id}", response_model=ObdSessionDetail)
def get_obd_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ObdSessionDetail:
    obd_session = get_owned_session(db, current_user, session_id, min_role=ROLE_VIEWER)
    return _detail(db, obd_session, [])


@router.delete("/obd/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_obd_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    obd_session = get_owned_session(db, current_user, session_id, min_role=ROLE_EDITOR)
    db.delete(obd_session)
    db.commit()
    return None
