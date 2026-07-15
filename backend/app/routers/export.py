"""Data portability endpoints: JSON export, per-car CSV export, JSON import."""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.access import ROLE_VIEWER, get_accessible_car
from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services.export import (
    ImportValidationError,
    build_export,
    build_logs_csv,
    import_data,
)

router = APIRouter(tags=["export"])


@router.get("/export")
def export_all(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONResponse:
    data = build_export(db, current_user)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    filename = f"kapot-tracker-export-{stamp}.json"
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/cars/{car_id}/export.csv")
def export_car_csv(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    car = get_accessible_car(db, current_user, car_id, min_role=ROLE_VIEWER)
    csv_text = build_logs_csv(db, car)
    filename = f"kapot-tracker-logs-{car.id}.csv"
    return Response(
        content=csv_text.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
def import_all(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    try:
        return import_data(db, current_user, payload)
    except ImportValidationError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
