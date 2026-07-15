"""Who may do what to a car — the one place that decides it.

Every ownership check in the application funnels through
``get_accessible_car``. Two sources answer «what is this user to this car»:

1. ``cars.user_id`` — the authoritative owner, unchanged by the sharing
   epic, so no existing query had to move;
2. ``car_members`` — everyone invited since.

The owner is derived from (1), never from (2): a car whose membership row is
missing is still the owner's car, and a membership row claiming 'owner' can
never quietly promote anyone.

**404 vs 403.** A car that is not yours in any way answers 404 — the same as
one that never existed, so the API cannot be used to discover that a car with
some id is out there. A car you *do* have access to, at a rank below what the
action needs, answers 403: hiding it there would only puzzle someone who can
plainly see the car in their garage.
"""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Car, CarMember, User

ROLE_OWNER = "owner"
ROLE_EDITOR = "editor"
ROLE_VIEWER = "viewer"

#: Roles, weakest to strongest. Access needs rank >= the route's min_role.
ROLE_RANK: dict[str, int] = {ROLE_VIEWER: 1, ROLE_EDITOR: 2, ROLE_OWNER: 3}

#: The roles an invite may hand out — 'owner' is not one of them.
ASSIGNABLE_ROLES: tuple[str, ...] = (ROLE_EDITOR, ROLE_VIEWER)


def role_rank(role: Optional[str]) -> int:
    """Rank a role, treating anything unrecognized as no access at all.

    A role the app does not know (a typo, a role retired later, a row written
    by a future version) must fail closed rather than raise a 500 or, worse,
    pass a comparison it should not.
    """
    if role is None:
        return 0
    return ROLE_RANK.get(role, 0)


def user_role_for_car(db: Session, user: User, car: Car) -> Optional[str]:
    """The user's role on this car, or None when they have no access.

    The owner is always 'owner', membership row or not.
    """
    if car.user_id == user.id:
        return ROLE_OWNER
    membership = db.execute(
        select(CarMember).where(CarMember.car_id == car.id, CarMember.user_id == user.id)
    ).scalar_one_or_none()
    return membership.role if membership is not None else None


def get_accessible_car(
    db: Session,
    user: User,
    car_id: int,
    min_role: str = ROLE_VIEWER,
    not_found_detail: str = "Car not found",
) -> Car:
    """Fetch a car the user may act on at ``min_role``, or raise.

    Raises 404 when the car does not exist or the user has no access to it,
    and 403 when they have access but not enough of it.

    ``not_found_detail`` lets the sub-resource helpers (a log, a photo, a
    spec) keep saying «<thing> not found» for both 404 paths: their caller
    asked about the thing, not about its car, and two different messages
    would tell an outsider which of the two ids was the real one.
    """
    # Strict, unlike role_rank: a stored role is data and fails closed, but a
    # min_role is written here in the source. A typo must not silently rank 0
    # and wave everyone through — it must break loudly, in the tests.
    if min_role not in ROLE_RANK:
        raise ValueError(f"Unknown min_role {min_role!r}")

    car = db.execute(select(Car).where(Car.id == car_id)).scalar_one_or_none()
    if car is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_detail)

    role = user_role_for_car(db, user, car)
    if role is None:
        # Deliberately the same answer as a car that does not exist.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_detail)
    if role_rank(role) < ROLE_RANK[min_role]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for this car",
        )
    return car


def list_accessible_cars(db: Session, user: User) -> list[Car]:
    """The user's garage: cars they own plus cars shared with them, by id.

    One query over ``cars`` with an IN subquery rather than a join to
    ``car_members``: a join would return the owner's car twice once the
    backfilled owner membership row exists.
    """
    return list(
        db.execute(
            select(Car)
            .where(
                or_(
                    Car.user_id == user.id,
                    Car.id.in_(
                        select(CarMember.car_id).where(CarMember.user_id == user.id)
                    ),
                )
            )
            .order_by(Car.id)
        )
        .scalars()
        .all()
    )


def ensure_owner_membership(db: Session, car: Car) -> None:
    """Give a car its owner membership row if it has none.

    Staged on the session, not committed: the caller owns the transaction.
    Access never depends on this row (``cars.user_id`` decides ownership) —
    it exists so that listing a car's members is one plain query.
    """
    existing = db.execute(
        select(CarMember.id).where(
            CarMember.car_id == car.id, CarMember.user_id == car.user_id
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(CarMember(car_id=car.id, user_id=car.user_id, role=ROLE_OWNER))


def member_label(user: User) -> str:
    return user.label
