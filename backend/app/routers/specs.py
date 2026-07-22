"""Car cheat-sheet endpoints: spec CRUD plus preset seeding."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import ROLE_OWNER, ROLE_VIEWER, get_accessible_car
from app.auth import get_current_user
from app.database import get_db
from app.models import Car, CarSpec, User
from app.routers.cars import get_owned_car
from app.schemas import SPEC_CATEGORIES, CarSpecCreate, CarSpecOut, CarSpecUpdate
from app.services.spec_presets import preset_for

router = APIRouter(tags=["specs"])


def get_owned_spec(db: Session, user: User, spec_id: int, min_role: str = ROLE_OWNER) -> CarSpec:
    """Fetch a spec the user may act on at ``min_role``, or raise 404/403.

    ``min_role`` defaults to 'owner': the cheat sheet is the owner's page.
    """
    spec = db.execute(select(CarSpec).where(CarSpec.id == spec_id)).scalar_one_or_none()
    if spec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spec not found")
    get_accessible_car(
        db, user, spec.car_id, min_role=min_role, not_found_detail="Spec not found"
    )
    return spec


def _category_rank(category: str) -> int:
    """Where a category sorts; anything unrecognised goes last, not to a 500.

    Only SPEC_CATEGORIES can be written today, but a category retired from
    that tuple later must not make a car's existing sheet unreadable.
    """
    try:
        return SPEC_CATEGORIES.index(category)
    except ValueError:
        return len(SPEC_CATEGORIES)


def car_specs(db: Session, car: Car) -> list[CarSpec]:
    """A car's specs in display order: by category, then the owner's order.

    The category order lives in SPEC_CATEGORIES rather than in the table, so
    it is applied here instead of in SQL — a cheat sheet is a page of rows,
    never enough of them to be worth a CASE expression. The sort is stable,
    so rows keep their (sort_order, id) order inside a category.
    """
    specs = (
        db.execute(
            select(CarSpec)
            .where(CarSpec.car_id == car.id)
            .order_by(CarSpec.sort_order, CarSpec.id)
        )
        .scalars()
        .all()
    )
    return sorted(specs, key=lambda spec: _category_rank(spec.category))


@router.get("/cars/{car_id}/specs", response_model=list[CarSpecOut])
def list_specs(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CarSpec]:
    car = get_accessible_car(db, current_user, car_id, min_role=ROLE_VIEWER)
    return car_specs(db, car)


@router.post(
    "/cars/{car_id}/specs", response_model=CarSpecOut, status_code=status.HTTP_201_CREATED
)
def create_spec(
    car_id: int,
    payload: CarSpecCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CarSpec:
    car = get_owned_car(db, current_user, car_id)
    spec = CarSpec(car_id=car.id, **payload.model_dump())
    db.add(spec)
    db.commit()
    db.refresh(spec)
    return spec


@router.post(
    "/cars/{car_id}/specs/preset",
    response_model=list[CarSpecOut],
    status_code=status.HTTP_201_CREATED,
)
def apply_spec_preset(
    car_id: int,
    key: str = Query(..., description="Preset key, e.g. golf7_16tdi"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CarSpec]:
    """Seed a car's cheat sheet from a preset and return the whole sheet.

    Idempotent on (car_id, category, name): a row that already exists is left
    exactly as it is, edits included. Re-running a preset therefore fills the
    gaps and never undoes the owner's own numbers.
    """
    car = get_owned_car(db, current_user, car_id)
    preset = preset_for(key, current_user.language)
    if preset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preset not found")

    existing = {(spec.category, spec.name) for spec in car_specs(db, car)}
    for sort_order, row in enumerate(preset):
        if (row.category, row.name) in existing:
            continue
        db.add(
            CarSpec(
                car_id=car.id,
                category=row.category,
                name=row.name,
                value=row.value,
                sort_order=sort_order,
            )
        )
    db.commit()
    return car_specs(db, car)


@router.patch("/specs/{spec_id}", response_model=CarSpecOut)
def update_spec(
    spec_id: int,
    payload: CarSpecUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CarSpec:
    spec = get_owned_spec(db, current_user, spec_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(spec, field, value)
    db.commit()
    db.refresh(spec)
    return spec


@router.delete("/specs/{spec_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_spec(
    spec_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    spec = get_owned_spec(db, current_user, spec_id)
    db.delete(spec)
    db.commit()
    return None
