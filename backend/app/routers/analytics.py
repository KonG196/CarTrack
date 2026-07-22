"""Per-car spending and fuel analytics endpoint."""

import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.access import ROLE_VIEWER, get_accessible_car
from app.auth import get_current_user
from app.database import get_db
from app.models import Car, LogEntry, User
from app.schemas import AnalyticsOut, BudgetStatus, YearReviewOut
from app.services.forecast import build_forecast
from app.services.fuel import compute_range_km
from app.services.stats import compute_analytics
from app.services.year_review import available_years, build_year_review


def _car_logs(db: Session, car: Car) -> list[LogEntry]:
    return list(
        db.execute(
            select(LogEntry)
            .where(LogEntry.car_id == car.id)
            .order_by(LogEntry.date, LogEntry.odometer)
            .options(
                selectinload(LogEntry.refuel),
                selectinload(LogEntry.maintenance),
                selectinload(LogEntry.repair),
                selectinload(LogEntry.expense),
            )
        )
        .scalars()
        .all()
    )

router = APIRouter(tags=["analytics"])

#: Percentages of the limit at which the budget changes colour. Spend is
#: 'warn' from WARN_PCT through the limit itself and 'over' only past it —
#: hitting the budget exactly is not yet breaking it.
BUDGET_WARN_PCT = 80.0
BUDGET_OVER_PCT = 100.0


def budget_status(pct_used: float) -> BudgetStatus:
    if pct_used < BUDGET_WARN_PCT:
        return "ok"
    if pct_used <= BUDGET_OVER_PCT:
        return "warn"
    return "over"


def build_budget(
    car: Car, spent_this_month: float, projected_month_total: float | None
) -> dict | None:
    """The budget block for a car, or None when the owner set no limit.

    Both inputs are handed in rather than recomputed: the spend is the same
    total the analytics payload already reports, and the projection is the
    forecast's own number — two independently derived «this month» figures in
    one response would eventually disagree.
    """
    if car.monthly_budget is None:
        return None
    limit = float(car.monthly_budget)
    if limit <= 0:
        # The API rejects a non-positive limit, but a row could predate it;
        # dividing by it would 500 the whole analytics screen.
        return None

    pct_used = spent_this_month / limit * 100.0
    return {
        "limit": round(limit, 2),
        "spent_this_month": spent_this_month,
        "projected_month_total": projected_month_total,
        "pct_used": round(pct_used, 1),
        # Off the exact ratio, not the rounded display value: 100.04% is over
        # the budget even where the card reads «100%».
        "status": budget_status(pct_used),
    }


@router.get("/cars/{car_id}/analytics", response_model=AnalyticsOut)
def get_analytics(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnalyticsOut:
    car = get_accessible_car(db, current_user, car_id, min_role=ROLE_VIEWER)
    logs = (
        db.execute(
            select(LogEntry)
            .where(LogEntry.car_id == car.id)
            .order_by(LogEntry.date, LogEntry.odometer)
            .options(
                selectinload(LogEntry.refuel),
                selectinload(LogEntry.maintenance),
                selectinload(LogEntry.repair),
                selectinload(LogEntry.expense),
            )
        )
        .scalars()
        .all()
    )
    analytics = compute_analytics(logs, car)
    forecast = build_forecast(db, car, logs=logs)
    return AnalyticsOut(
        **analytics,
        forecast=forecast,
        range_km=compute_range_km(
            car.tank_liters, analytics["fuel"]["avg_consumption_l_100km"]
        ),
        budget=build_budget(
            car,
            spent_this_month=analytics["totals"]["this_month"],
            projected_month_total=forecast["projected_month_total"],
        ),
    )


@router.get("/cars/{car_id}/year-review", response_model=YearReviewOut)
def get_year_review(
    car_id: int,
    year: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> YearReviewOut:
    """«Ваш рік з Kapot» — a one-year recap. Defaults to the newest year with data."""
    car = get_accessible_car(db, current_user, car_id, min_role=ROLE_VIEWER)
    logs = _car_logs(db, car)
    years = available_years(logs)
    chosen = year if year is not None else (years[0] if years else dt.date.today().year)
    return YearReviewOut(**build_year_review(car, logs, chosen, current_user.language))
