"""Car document endpoints: upload under a car, stream/delete by document id.

Files are stored by the log-photo service, in the same
``<UPLOADS_DIR>/<car owner's id>/`` directory: a policy scan is a photo with
paperwork attached, and one storage path is one thing to back up and secure.
The directory is keyed on the car's owner rather than on the uploader — see
the storage note in routers/photos.py.
"""

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import ROLE_EDITOR, ROLE_OWNER, ROLE_VIEWER, get_accessible_car
from app.auth import get_current_user
from app.database import get_db
from app.models import Car, CarDocument, ServiceInterval, User
from app.schemas import EXPIRING_DOCUMENT_KINDS, CarDocumentOut, DocumentKind
from app.services.photos import new_photo_filename, photo_path, write_photo_file

router = APIRouter(tags=["documents"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# A document is a scan or a PDF; nothing else is a document.
ALLOWED_CONTENT_TYPES: tuple[str, ...] = ("application/pdf",)

# The reminder booked for an expiring document renews yearly, which is what
# both an ОСЦПВ policy and a Ukrainian техогляд do.
DOCUMENT_INTERVAL_DAYS = 365


def get_owned_document(
    db: Session, user: User, document_id: int, min_role: str = ROLE_OWNER
) -> tuple[CarDocument, Car]:
    """Fetch a document the user may act on at ``min_role``, plus its car.

    The car comes back with it because every caller needs it anyway: it
    carries the owner id the file is stored under. ``min_role`` defaults to
    'owner' so a caller that forgets to widen it fails closed.
    """
    document = db.execute(
        select(CarDocument).where(CarDocument.id == document_id)
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    car = get_accessible_car(
        db, user, document.car_id, min_role=min_role, not_found_detail="Document not found"
    )
    return document, car


def _check_content_type(content_type: Optional[str]) -> None:
    value = content_type or ""
    if value.startswith("image/") or value in ALLOWED_CONTENT_TYPES:
        return
    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Only image or PDF uploads are supported",
    )


async def _read_capped(file: UploadFile) -> bytes:
    too_large = HTTPException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        detail="Document is too large (max 10 MB)",
    )
    # Same cap strategy as the photo endpoint: check the spooled size first,
    # then read at most one byte over the limit.
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise too_large
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise too_large
    return content


def _expiry_interval(
    car: Car, kind: str, title: str, expires_at: Optional[dt.date]
) -> Optional[ServiceInterval]:
    """The reminder an expiring document books, or None if it books none.

    Date-only by nature: a policy lapses on a date, not at an odometer
    reading. ``last_date`` is backdated a full period so the interval comes
    due exactly on ``expires_at`` and the ordinary 14-day warning fires two
    weeks before the car is uninsured.
    """
    if expires_at is None or kind not in EXPIRING_DOCUMENT_KINDS:
        return None
    return ServiceInterval(
        car_id=car.id,
        title=f"{title} (документ)",
        interval_days=DOCUMENT_INTERVAL_DAYS,
        last_date=expires_at - dt.timedelta(days=DOCUMENT_INTERVAL_DAYS),
    )


@router.post(
    "/cars/{car_id}/documents",
    response_model=CarDocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    car_id: int,
    file: UploadFile = File(...),
    kind: DocumentKind = Form(...),
    title: str = Form(..., min_length=1, max_length=150),
    expires_at: Optional[dt.date] = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CarDocumentOut:
    """File a document (image or PDF, max 10 MB) under a car.

    An insurance or inspection document with an expiry also books the
    reminder for that expiry, in this same transaction: the document and its
    deadline are one action, so they land together or not at all.
    """
    car = get_accessible_car(db, current_user, car_id, min_role=ROLE_EDITOR)
    _check_content_type(file.content_type)
    content = await _read_capped(file)

    # Named now, written after the commit: a file on disk with no row behind
    # it is litter, and this way a failed commit cannot leave one.
    filename = new_photo_filename(file.filename, file.content_type)
    document = CarDocument(
        car_id=car.id,
        kind=kind,
        title=title,
        filename=filename,
        content_type=file.content_type or "application/octet-stream",
        size=len(content),
        expires_at=expires_at,
    )
    db.add(document)
    interval = _expiry_interval(car, kind, title, expires_at)
    if interval is not None:
        db.add(interval)
    db.commit()
    db.refresh(document)
    linked_interval_id = interval.id if interval is not None else None

    write_photo_file(car.user_id, filename, content)
    return CarDocumentOut.model_validate(document).model_copy(
        update={"linked_interval_id": linked_interval_id}
    )


@router.get("/cars/{car_id}/documents", response_model=list[CarDocumentOut])
def list_documents(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CarDocument]:
    car = get_accessible_car(db, current_user, car_id, min_role=ROLE_VIEWER)
    return list(
        db.execute(
            select(CarDocument)
            .where(CarDocument.car_id == car.id)
            .order_by(CarDocument.created_at.desc(), CarDocument.id.desc())
        )
        .scalars()
        .all()
    )


@router.get("/documents/{document_id}")
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    document, car = get_owned_document(db, current_user, document_id, min_role=ROLE_VIEWER)
    path = photo_path(car.user_id, document.filename)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return FileResponse(path, media_type=document.content_type)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    document, car = get_owned_document(db, current_user, document_id, min_role=ROLE_EDITOR)
    path = photo_path(car.user_id, document.filename)
    db.delete(document)
    db.commit()
    path.unlink(missing_ok=True)
    return None
