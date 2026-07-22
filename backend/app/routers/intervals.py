"""Service interval endpoints with computed status/prediction fields."""

from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.access import ROLE_EDITOR, ROLE_OWNER, ROLE_VIEWER, get_accessible_car
from app.auth import get_current_user
from app.database import get_db
from app.models import Car, LogEntry, ServiceInterval, User
from app.routers.cars import car_avg_daily_km, get_owned_car
from app.schemas import (
    IntervalCompleteIn,
    IntervalCompleteOut,
    IntervalPresetOut,
    IntervalPresetsOut,
    IntervalStatusOut,
    LogEntryOut,
    ServiceIntervalCreate,
    ServiceIntervalUpdate,
)
from app.services.forecast import estimate_interval_cost
from app.services.intervals import compute_interval_status
from app.services.intervals_complete import complete_interval
from app.services.presets import compliance_presets, maintenance_presets

router = APIRouter(tags=["intervals"])


def get_owned_interval(
    db: Session, user: User, interval_id: int, min_role: str = ROLE_OWNER
) -> ServiceInterval:
    """Fetch an interval the user may act on at ``min_role``, or raise 404/403.

    ``min_role`` defaults to 'owner': the service rules of a car are the
    owner's to set. Logging that a rule was carried out is a different act —
    see the complete endpoint, which asks for 'editor'.
    """
    interval = db.execute(
        select(ServiceInterval).where(ServiceInterval.id == interval_id)
    ).scalar_one_or_none()
    if interval is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Service interval not found"
        )
    get_accessible_car(
        db,
        user,
        interval.car_id,
        min_role=min_role,
        not_found_detail="Service interval not found",
    )
    return interval


def _car_logs(db: Session, car: Car) -> list[LogEntry]:
    return list(
        db.execute(
            select(LogEntry)
            .where(LogEntry.car_id == car.id)
            .options(
                selectinload(LogEntry.maintenance),
                selectinload(LogEntry.repair),
            )
        )
        .scalars()
        .all()
    )


def serialize_interval(
    db: Session,
    interval: ServiceInterval,
    car: Car,
    logs: Sequence[LogEntry] | None = None,
) -> IntervalStatusOut:
    """One interval with its status and what the next one will likely cost.

    ``logs`` is passed in by the list route, which reads them once for the whole
    garage; a single-interval caller lets this fetch its own.
    """
    computed = compute_interval_status(
        interval=interval,
        current_odometer=car.current_odometer,
        avg_daily_km=car_avg_daily_km(db, car),
    )
    if logs is None:
        logs = _car_logs(db, car)
    estimate = estimate_interval_cost(interval.title, logs, car)
    return IntervalStatusOut(
        id=interval.id,
        car_id=interval.car_id,
        title=interval.title,
        interval_km=interval.interval_km,
        interval_days=interval.interval_days,
        last_odometer=interval.last_odometer,
        last_date=interval.last_date,
        updated_at=interval.updated_at,
        estimated_cost=estimate.amount if estimate else None,
        estimated_cost_source=estimate.source if estimate else None,
        **computed,
    )


@router.get("/interval-presets", response_model=IntervalPresetsOut)
def list_interval_presets(
    current_user: User = Depends(get_current_user),
) -> IntervalPresetsOut:
    lang = current_user.language
    return IntervalPresetsOut(
        maintenance=[IntervalPresetOut(**preset._asdict()) for preset in maintenance_presets(lang)],
        compliance=[IntervalPresetOut(**preset._asdict()) for preset in compliance_presets(lang)],
    )


@router.get("/cars/{car_id}/intervals", response_model=list[IntervalStatusOut])
def list_intervals(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[IntervalStatusOut]:
    car = get_accessible_car(db, current_user, car_id, min_role=ROLE_VIEWER)
    intervals = (
        db.execute(
            select(ServiceInterval)
            .where(ServiceInterval.car_id == car.id)
            .order_by(ServiceInterval.id)
        )
        .scalars()
        .all()
    )
    # Read once for the whole list: the estimate needs the car's history, and
    # fetching it per interval is the same query N times.
    logs = _car_logs(db, car)
    return [serialize_interval(db, interval, car, logs) for interval in intervals]


@router.post(
    "/cars/{car_id}/intervals",
    response_model=IntervalStatusOut,
    status_code=status.HTTP_201_CREATED,
)
def create_interval(
    car_id: int,
    payload: ServiceIntervalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IntervalStatusOut:
    """Create a service interval (owner only — service rules are the owner's)."""
    car = get_owned_car(db, current_user, car_id)
    interval = ServiceInterval(car_id=car.id, **payload.model_dump())
    db.add(interval)
    db.commit()
    db.refresh(interval)
    return serialize_interval(db, interval, car)


@router.patch("/intervals/{interval_id}", response_model=IntervalStatusOut)
def update_interval(
    interval_id: int,
    payload: ServiceIntervalUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IntervalStatusOut:
    """Partially update a service interval (owner only)."""
    interval = get_owned_interval(db, current_user, interval_id, min_role=ROLE_OWNER)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(interval, field, value)

    if interval.interval_km is None and interval.interval_days is None:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="at least one of interval_km or interval_days is required",
        )

    db.commit()
    db.refresh(interval)
    car = get_owned_car(db, current_user, interval.car_id)
    return serialize_interval(db, interval, car)


@router.post(
    "/intervals/{interval_id}/complete",
    response_model=IntervalCompleteOut,
    status_code=status.HTTP_201_CREATED,
)
def complete_interval_endpoint(
    interval_id: int,
    payload: IntervalCompleteIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IntervalCompleteOut:
    """Log the work and advance the interval in one transaction (editor+)."""
    interval = get_owned_interval(db, current_user, interval_id, min_role=ROLE_EDITOR)
    completion = complete_interval(
        db,
        interval,
        odometer=payload.odometer,
        date=payload.date,
        total_cost=payload.total_cost,
        parts_cost=payload.parts_cost,
        labor_cost=payload.labor_cost,
        items=payload.items,
        notes=payload.notes,
        author_id=current_user.id,
    )
    return IntervalCompleteOut(
        log=LogEntryOut.model_validate(completion.log),
        interval=serialize_interval(db, completion.interval, completion.car),
    )


@router.delete("/intervals/{interval_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_interval(
    interval_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a service interval (owner only)."""
    interval = get_owned_interval(db, current_user, interval_id, min_role=ROLE_OWNER)
    db.delete(interval)
    db.commit()
    return None
