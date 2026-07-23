"""Car CRUD endpoints (per-user access enforced everywhere via app.access)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import (
    ROLE_OWNER,
    ensure_owner_membership,
    get_accessible_car,
    list_accessible_cars,
    user_role_for_car,
)
from app.auth import get_current_user
from app.database import get_db
from app.models import Car, LogEntry, RefuelDetails, User
from app.schemas import CarCreate, CarOut, CarUpdate, PassportTokenOut
from app.services import passport
from app.services.admin_notify import notify_first_car
from app.services.fuel import resolve_fuel_kind
from app.services.intervals import compute_avg_daily_km, effective_avg_daily_km

router = APIRouter(prefix="/cars", tags=["cars"])


def get_owned_car(db: Session, user: User, car_id: int) -> Car:
    """Fetch a car the user owns, or raise 404/403.

    A thin wrapper over get_accessible_car kept for the callers that really
    do mean «owner»; routes that need less ask get_accessible_car directly.
    """
    return get_accessible_car(db, user, car_id, min_role=ROLE_OWNER)


def car_logs(db: Session, car: Car) -> list[LogEntry]:
    return list(
        db.execute(select(LogEntry).where(LogEntry.car_id == car.id)).scalars().all()
    )


def car_avg_daily_km(db: Session, car: Car) -> float:
    """A car's effective daily pace: the owner's override, else computed."""
    return effective_avg_daily_km(car, car_logs(db, car))


def car_fuel_kinds_used(db: Session, car: Car) -> list[str]:
    stored = (
        db.execute(
            select(RefuelDetails.fuel_kind)
            .join(LogEntry, LogEntry.id == RefuelDetails.log_entry_id)
            .where(LogEntry.car_id == car.id)
            .distinct()
        )
        .scalars()
        .all()
    )
    return sorted({resolve_fuel_kind(kind, car) for kind in stored})


def serialize_car(db: Session, car: Car, user: User) -> CarOut:
    computed = compute_avg_daily_km(car_logs(db, car))
    override = car.avg_daily_km_override
    return CarOut(
        id=car.id,
        brand=car.brand,
        model=car.model,
        generation=car.generation,
        engine=car.engine,
        year=car.year,
        fuel_type=car.fuel_type,
        current_odometer=car.current_odometer,
        vin=car.vin,
        plate=car.plate,
        avg_daily_km=round(override if override is not None else computed, 1),
        avg_daily_km_computed=round(computed, 1),
        avg_daily_km_override=override,
        tank_liters=car.tank_liters,
        # Numeric(10, 2) reads back as Decimal; the API speaks in floats like
        # every other money field.
        monthly_budget=(
            float(car.monthly_budget) if car.monthly_budget is not None else None
        ),
        scratchpad=car.scratchpad,
        public_token=car.public_token,
        contact_phone=car.contact_phone,
        insurance_number=car.insurance_number,
        insurance_until=car.insurance_until,
        tire_pressure=car.tire_pressure,
        fuel_approval=car.fuel_approval,
        fuel_kinds_used=car_fuel_kinds_used(db, car),
        your_role=user_role_for_car(db, user, car) or ROLE_OWNER,
        created_at=car.created_at,
        updated_at=car.updated_at,
    )


@router.get("", response_model=list[CarOut])
def list_cars(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CarOut]:
    return [
        serialize_car(db, car, current_user)
        for car in list_accessible_cars(db, current_user)
    ]


@router.post("", response_model=CarOut, status_code=status.HTTP_201_CREATED)
def create_car(
    payload: CarCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CarOut:
    car = Car(user_id=current_user.id, **payload.model_dump())
    db.add(car)
    db.flush()  # allocate the car id the membership row points at
    ensure_owner_membership(db, car)
    db.commit()
    db.refresh(car)
    notify_first_car(db, current_user, car)
    return serialize_car(db, car, current_user)


@router.get("/{car_id}", response_model=CarOut)
def get_car(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CarOut:
    car = get_accessible_car(db, current_user, car_id)
    return serialize_car(db, car, current_user)


@router.patch("/{car_id}", response_model=CarOut)
def update_car(
    car_id: int,
    payload: CarUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CarOut:
    """Partially update a car (owner only — the car itself is not shared work)."""
    car = get_owned_car(db, current_user, car_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(car, field, value)
    db.commit()
    db.refresh(car)
    return serialize_car(db, car, current_user)


@router.post("/{car_id}/passport-token", response_model=PassportTokenOut)
def mint_passport_token(
    car_id: int,
    regenerate: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PassportTokenOut:
    """Ensure a public passport link and return it with a printable QR.

    Idempotent by default — pressing «generate» again shows the same link, so a
    QR already in the glovebox keeps working. ``regenerate=true`` mints a fresh
    token, revoking the old link.
    """
    car = get_owned_car(db, current_user, car_id)
    if car.public_token is None or regenerate:
        car.public_token = passport.new_token()
        db.commit()
    url = passport.passport_url(car.public_token)
    return PassportTokenOut(token=car.public_token, url=url, qr_svg=passport.qr_svg(url))


@router.delete("/{car_id}/passport-token", status_code=status.HTTP_204_NO_CONTENT)
def revoke_passport_token(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Revoke the public passport link — the old URL 404s from then on."""
    car = get_owned_car(db, current_user, car_id)
    car.public_token = None
    db.commit()
    return None


@router.delete("/{car_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_car(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a car (and all its logs/intervals/members) — owner only."""
    car = get_owned_car(db, current_user, car_id)
    db.delete(car)
    db.commit()
    return None
