"""PDF service-history report endpoint."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.access import ROLE_VIEWER, get_accessible_car
from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services.report import build_car_report

router = APIRouter(tags=["reports"])


@router.get("/cars/{car_id}/report")
def get_report(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    car = get_accessible_car(db, current_user, car_id, min_role=ROLE_VIEWER)
    pdf_bytes = build_car_report(db, car, current_user.language, current_user.currency)
    filename = f"kapot-tracker-report-{car.id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
