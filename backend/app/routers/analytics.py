"""Per-car spending and fuel analytics endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import LogEntry, User
from app.routers.cars import get_owned_car
from app.schemas import AnalyticsOut
from app.services.stats import compute_analytics

router = APIRouter(tags=["analytics"])


@router.get("/cars/{car_id}/analytics", response_model=AnalyticsOut)
def get_analytics(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnalyticsOut:
    """Return spending totals, monthly breakdown and fuel stats for a car."""
    car = get_owned_car(db, current_user, car_id)
    logs = (
        db.execute(
            select(LogEntry)
            .where(LogEntry.car_id == car.id)
            .order_by(LogEntry.date, LogEntry.odometer)
        )
        .scalars()
        .all()
    )
    return AnalyticsOut(**compute_analytics(logs))
