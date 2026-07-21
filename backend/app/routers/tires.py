"""Seasonal tire endpoints: set CRUD plus the install swap.

Tire sets are car configuration, not journal content: what the car wears is
the owner's decision, the same as its intervals and its cheat sheet. So every
write here is owner-only, while reading stays viewer+ — a member who logs the
refuels can see which set is on and how far it has run.

No seasonal reminders live here on purpose: «time to change over» is a date,
not a mileage, and the plan leaves it to an ordinary date interval.
"""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import ROLE_OWNER, ROLE_VIEWER, get_accessible_car
from app.auth import get_current_user
from app.database import get_db
from app.models import Car, TireSet, User
from app.routers.cars import get_owned_car
from app.schemas import TireSeasonStatus, TireSetCreate, TireSetOut, TireSetUpdate
from app.services import climate

router = APIRouter(tags=["tires"])


def get_owned_tire_set(
    db: Session, user: User, tire_set_id: int, min_role: str = ROLE_OWNER
) -> TireSet:
    """Fetch a tire set the user may act on at ``min_role``, or raise 404/403.

    ``min_role`` defaults to 'owner': every route that reaches a set by its own
    id changes it.
    """
    tire_set = db.execute(
        select(TireSet).where(TireSet.id == tire_set_id)
    ).scalar_one_or_none()
    if tire_set is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tire set not found"
        )
    get_accessible_car(
        db, user, tire_set.car_id, min_role=min_role, not_found_detail="Tire set not found"
    )
    return tire_set


def car_tire_sets(db: Session, car: Car) -> list[TireSet]:
    """A car's sets in display order: the one on the car first, then by id.

    The mounted set leads because it is the one the answer «скільки на них
    пройдено» is about; the rest keep a stable order behind it.
    """
    return list(
        db.execute(
            select(TireSet)
            .where(TireSet.car_id == car.id)
            .order_by(TireSet.is_installed.desc(), TireSet.id)
        )
        .scalars()
        .all()
    )


@router.get("/cars/{car_id}/tires", response_model=list[TireSetOut])
def list_tire_sets(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TireSet]:
    car = get_accessible_car(db, current_user, car_id, min_role=ROLE_VIEWER)
    return car_tire_sets(db, car)


@router.get("/cars/{car_id}/tires/season-status", response_model=TireSeasonStatus)
def tire_season_status(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TireSeasonStatus:
    """Whether the car's region is in a tyre/washer changeover window right now.

    A read-only signal for the in-app banner — the seasonal date logic lives in
    climate.py and is keyed off the car's plate region (central-Ukraine
    fallback). Viewer+, like the rest of the reads here.
    """
    car = get_accessible_car(db, current_user, car_id, min_role=ROLE_VIEWER)
    today = dt.date.today()
    return TireSeasonStatus(
        changeover_season=climate.tire_changeover_season(car.plate, today),
        washer_changeover_due=climate.washer_changeover_due(car.plate, today),
    )


@router.post(
    "/cars/{car_id}/tires", response_model=TireSetOut, status_code=status.HTTP_201_CREATED
)
def create_tire_set(
    car_id: int,
    payload: TireSetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TireSet:
    """Add one tire set to a car owned by the current user.

    The set lands on the shelf: mounting it is a separate, deliberate act, so
    that «at most one set is installed» is decided in exactly one place.
    """
    car = get_owned_car(db, current_user, car_id)
    tire_set = TireSet(car_id=car.id, **payload.model_dump())
    db.add(tire_set)
    db.commit()
    db.refresh(tire_set)
    return tire_set


@router.patch("/tires/{tire_set_id}", response_model=TireSetOut)
def update_tire_set(
    tire_set_id: int,
    payload: TireSetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TireSet:
    tire_set = get_owned_tire_set(db, current_user, tire_set_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tire_set, field, value)
    db.commit()
    db.refresh(tire_set)
    return tire_set


@router.delete("/tires/{tire_set_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tire_set(
    tire_set_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    tire_set = get_owned_tire_set(db, current_user, tire_set_id)
    db.delete(tire_set)
    db.commit()
    return None


@router.post("/tires/{tire_set_id}/install", response_model=TireSetOut)
def install_tire_set(
    tire_set_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TireSet:
    """Put this set on the car and take the previous one off, in one commit.

    One transaction because the two halves are one physical act: a car cannot
    wear two sets, and a failure between «зняли» and «поставили» would leave
    it wearing none or both.

    Re-installing the set already on the car returns it untouched. Re-stamping
    would reset its mileage to zero — the exact number the stamp is kept for.
    """
    tire_set = get_owned_tire_set(db, current_user, tire_set_id)
    if tire_set.is_installed:
        return tire_set

    car = db.execute(select(Car).where(Car.id == tire_set.car_id)).scalar_one()
    previous = (
        db.execute(
            select(TireSet).where(
                TireSet.car_id == car.id,
                TireSet.is_installed.is_(True),
                TireSet.id != tire_set.id,
            )
        )
        .scalars()
        .all()
    )
    # A list, not one row: the invariant is «at most one», and if a stray
    # second set ever exists, mounting must leave the car with exactly one.
    for other in previous:
        other.is_installed = False

    tire_set.is_installed = True
    tire_set.odometer_at_install = car.current_odometer
    # A freshly mounted set starts its rotation clock now.
    tire_set.odometer_at_rotation = car.current_odometer
    tire_set.rotation_reminded_km = None
    db.commit()
    db.refresh(tire_set)
    return tire_set


@router.post("/tires/{tire_set_id}/rotate", response_model=TireSetOut)
def rotate_tire_set(
    tire_set_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TireSet:
    """Record an axle rotation: reset this set's rotation clock to now.

    Only the set on the car can be rotated — a shelf set is not turning any
    wheels. The next nudge is then 10 000 km of driving away.
    """
    tire_set = get_owned_tire_set(db, current_user, tire_set_id)
    if not tire_set.is_installed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rotate the set that is on the car",
        )
    car = db.execute(select(Car).where(Car.id == tire_set.car_id)).scalar_one()
    tire_set.odometer_at_rotation = car.current_odometer
    tire_set.rotation_reminded_km = None
    db.commit()
    db.refresh(tire_set)
    return tire_set
