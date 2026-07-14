"""Service interval endpoints with computed status/prediction fields."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Car, ServiceInterval, User
from app.routers.cars import car_avg_daily_km, get_owned_car
from app.schemas import IntervalStatusOut, ServiceIntervalCreate, ServiceIntervalUpdate
from app.services.intervals import compute_interval_status

router = APIRouter(tags=["intervals"])


def get_owned_interval(db: Session, user: User, interval_id: int) -> ServiceInterval:
    """Fetch an interval whose car belongs to the user, or raise 404."""
    interval = db.execute(
        select(ServiceInterval)
        .join(Car, ServiceInterval.car_id == Car.id)
        .where(ServiceInterval.id == interval_id, Car.user_id == user.id)
    ).scalar_one_or_none()
    if interval is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Service interval not found"
        )
    return interval


def serialize_interval(db: Session, interval: ServiceInterval, car: Car) -> IntervalStatusOut:
    """Build the API representation of an interval with computed status."""
    computed = compute_interval_status(
        interval=interval,
        current_odometer=car.current_odometer,
        avg_daily_km=car_avg_daily_km(db, car),
    )
    return IntervalStatusOut(
        id=interval.id,
        car_id=interval.car_id,
        title=interval.title,
        interval_km=interval.interval_km,
        interval_days=interval.interval_days,
        last_odometer=interval.last_odometer,
        last_date=interval.last_date,
        **computed,
    )


@router.get("/cars/{car_id}/intervals", response_model=list[IntervalStatusOut])
def list_intervals(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[IntervalStatusOut]:
    """List a car's service intervals with computed status."""
    car = get_owned_car(db, current_user, car_id)
    intervals = (
        db.execute(
            select(ServiceInterval)
            .where(ServiceInterval.car_id == car.id)
            .order_by(ServiceInterval.id)
        )
        .scalars()
        .all()
    )
    return [serialize_interval(db, interval, car) for interval in intervals]


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
    """Create a service interval for a car owned by the current user."""
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
    """Partially update a service interval owned by the current user."""
    interval = get_owned_interval(db, current_user, interval_id)
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


@router.delete("/intervals/{interval_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_interval(
    interval_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a service interval owned by the current user."""
    interval = get_owned_interval(db, current_user, interval_id)
    db.delete(interval)
    db.commit()
    return None
