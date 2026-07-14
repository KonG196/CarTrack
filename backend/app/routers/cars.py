"""Car CRUD endpoints (per-user ownership enforced everywhere)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Car, LogEntry, User
from app.schemas import CarCreate, CarOut, CarUpdate
from app.services.intervals import compute_avg_daily_km

router = APIRouter(prefix="/cars", tags=["cars"])


def get_owned_car(db: Session, user: User, car_id: int) -> Car:
    """Fetch a car owned by the user or raise 404."""
    car = db.execute(
        select(Car).where(Car.id == car_id, Car.user_id == user.id)
    ).scalar_one_or_none()
    if car is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Car not found")
    return car


def car_avg_daily_km(db: Session, car: Car) -> float:
    """Compute a car's average daily km from its log history."""
    logs = db.execute(select(LogEntry).where(LogEntry.car_id == car.id)).scalars().all()
    return compute_avg_daily_km(logs)


def serialize_car(db: Session, car: Car) -> CarOut:
    """Build the API representation of a car, including avg_daily_km."""
    return CarOut(
        id=car.id,
        brand=car.brand,
        model=car.model,
        generation=car.generation,
        engine=car.engine,
        year=car.year,
        fuel_type=car.fuel_type,
        current_odometer=car.current_odometer,
        avg_daily_km=round(car_avg_daily_km(db, car), 1),
        created_at=car.created_at,
    )


@router.get("", response_model=list[CarOut])
def list_cars(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CarOut]:
    """List the current user's cars."""
    cars = (
        db.execute(select(Car).where(Car.user_id == current_user.id).order_by(Car.id))
        .scalars()
        .all()
    )
    return [serialize_car(db, car) for car in cars]


@router.post("", response_model=CarOut, status_code=status.HTTP_201_CREATED)
def create_car(
    payload: CarCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CarOut:
    """Create a new car for the current user."""
    car = Car(user_id=current_user.id, **payload.model_dump())
    db.add(car)
    db.commit()
    db.refresh(car)
    return serialize_car(db, car)


@router.get("/{car_id}", response_model=CarOut)
def get_car(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CarOut:
    """Fetch a single car owned by the current user."""
    car = get_owned_car(db, current_user, car_id)
    return serialize_car(db, car)


@router.patch("/{car_id}", response_model=CarOut)
def update_car(
    car_id: int,
    payload: CarUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CarOut:
    """Partially update a car owned by the current user."""
    car = get_owned_car(db, current_user, car_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(car, field, value)
    db.commit()
    db.refresh(car)
    return serialize_car(db, car)


@router.delete("/{car_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_car(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a car (and all its logs/intervals) owned by the current user."""
    car = get_owned_car(db, current_user, car_id)
    db.delete(car)
    db.commit()
    return None
