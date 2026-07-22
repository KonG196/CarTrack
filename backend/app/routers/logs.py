"""Log entry endpoints: list/create under a car, patch/delete by log id."""

from collections.abc import Mapping
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session, contains_eager, selectinload

from app.access import ROLE_EDITOR, ROLE_OWNER, ROLE_VIEWER, get_accessible_car
from app.auth import get_current_user
from app.database import get_db
from app.models import (
    Car,
    ExpenseDetails,
    LogEntry,
    MaintenanceDetails,
    RefuelDetails,
    RepairDetails,
    User,
    utcnow,
)
from app.schemas import (
    DEFAULT_EXPENSE_CATEGORY,
    ExpenseDetailsIn,
    LogEntryCreate,
    LogEntryOut,
    LogEntryUpdate,
    LogListOut,
    MaintenanceDetailsIn,
    RefuelContextOut,
    RefuelDetailsIn,
    RepairDetailsIn,
)
from app.services.intervals import sync_intervals_from_log
from app.services.stats import consumption_by_log_id

router = APIRouter(tags=["logs"])

VALID_LOG_TYPES = {"refuel", "maintenance", "repair", "expense"}

# How many distinct recently used stations the refuel form offers.
RECENT_STATIONS_LIMIT = 5


def get_owned_log(db: Session, user: User, log_id: int, min_role: str = ROLE_OWNER) -> LogEntry:
    """Fetch a log entry the user may act on at ``min_role``, or raise 404/403.

    The log is looked up first and its car is then run through the one access
    check, so «someone else's log» and «no such log» stay indistinguishable.
    ``min_role`` defaults to 'owner' so a caller that forgets to widen it
    fails closed.
    """
    log = db.execute(
        select(LogEntry)
        .where(LogEntry.id == log_id)
        .options(selectinload(LogEntry.author))
    ).scalar_one_or_none()
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Log entry not found")
    get_accessible_car(
        db, user, log.car_id, min_role=min_role, not_found_detail="Log entry not found"
    )
    return log


def _to_decimal(value: float) -> Decimal:
    return Decimal(str(value))


def _car_consumption_map(db: Session, car: Car) -> dict[int, float]:
    """Full-to-full consumption per refuel log id for a whole car.

    One query for the car's entire refuel history: consumption is a property
    of the segment between two full tanks, so it can only be derived from all
    of them at once — never per listed row. The car itself comes along because
    a refuel's fuel kind is only meaningful against it.
    """
    refuels = (
        db.execute(
            select(LogEntry)
            .join(RefuelDetails, RefuelDetails.log_entry_id == LogEntry.id)
            .where(LogEntry.car_id == car.id, LogEntry.type == "refuel")
            .options(contains_eager(LogEntry.refuel))
            .order_by(LogEntry.odometer, LogEntry.date)
        )
        .scalars()
        .all()
    )
    return consumption_by_log_id(refuels, car)


def _serialize_log(log: LogEntry, consumption: Mapping[int, float]) -> LogEntryOut:
    out = LogEntryOut.model_validate(log)
    if out.refuel is not None:
        out.refuel.consumption_l_100km = consumption.get(log.id)
    return out


@router.get("/cars/{car_id}/logs", response_model=LogListOut)
def list_logs(
    car_id: int,
    type: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LogListOut:
    car = get_accessible_car(db, current_user, car_id, min_role=ROLE_VIEWER)

    filters = [LogEntry.car_id == car.id]
    if type:
        if type not in VALID_LOG_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid log type '{type}'",
            )
        filters.append(LogEntry.type == type)

    base = select(LogEntry).where(*filters)
    if q:
        # NOTE: SQLite folds case only for ASCII in LIKE, so Cyrillic search
        # is case-sensitive in dev; on PostgreSQL (prod) ilike is complete.
        pattern = f"%{q}%"
        base = (
            base.outerjoin(
                RefuelDetails, RefuelDetails.log_entry_id == LogEntry.id
            )
            .outerjoin(
                MaintenanceDetails, MaintenanceDetails.log_entry_id == LogEntry.id
            )
            .outerjoin(RepairDetails, RepairDetails.log_entry_id == LogEntry.id)
            .where(
                or_(
                    LogEntry.notes.ilike(pattern),
                    cast(MaintenanceDetails.items, String).ilike(pattern),
                    RepairDetails.category.ilike(pattern),
                    RepairDetails.part_name.ilike(pattern),
                    RefuelDetails.gas_station.ilike(pattern),
                )
            )
            .distinct()
        )

    total = db.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one()
    items = (
        db.execute(
            base
            # Eager-load everything LogEntryOut serializes: one query per
            # relationship instead of five lazy loads per row.
            .options(
                selectinload(LogEntry.refuel),
                selectinload(LogEntry.maintenance),
                selectinload(LogEntry.repair),
                selectinload(LogEntry.expense),
                selectinload(LogEntry.photos),
                # One query for every author on the page, however many people
                # share the car — not one per row.
                selectinload(LogEntry.author),
            )
            .order_by(LogEntry.date.desc(), LogEntry.odometer.desc())
            .offset(offset)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    # Built once for the whole car (segments span rows a filtered page may
    # not even contain), then mapped onto the returned rows.
    consumption = _car_consumption_map(db, car)
    return LogListOut(
        items=[_serialize_log(item, consumption) for item in items],
        total=total,
    )


@router.get("/cars/{car_id}/refuel-context", response_model=RefuelContextOut)
def get_refuel_context(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RefuelContextOut:
    car = get_accessible_car(db, current_user, car_id, min_role=ROLE_VIEWER)

    # One read of the car's rows, newest first; every field below is derived
    # from it in Python rather than by a query of its own.
    rows = db.execute(
        select(
            LogEntry.type,
            LogEntry.odometer,
            LogEntry.date,
            RefuelDetails.gas_station,
            RefuelDetails.price_per_liter,
        )
        .outerjoin(RefuelDetails, RefuelDetails.log_entry_id == LogEntry.id)
        .where(LogEntry.car_id == car.id)
        .order_by(LogEntry.date.desc(), LogEntry.odometer.desc(), LogEntry.id.desc())
    ).all()

    if not rows:
        return RefuelContextOut(
            recent_stations=[],
            last_price_per_liter=None,
            last_refuel_odometer=None,
            last_entry_odometer=None,
            last_entry_date=None,
        )

    refuels = [row for row in rows if row.type == "refuel"]
    stations: list[str] = []
    for row in refuels:
        station = (row.gas_station or "").strip()
        if station and station not in stations:
            stations.append(station)
        if len(stations) == RECENT_STATIONS_LIMIT:
            break

    last_refuel = refuels[0] if refuels else None
    return RefuelContextOut(
        recent_stations=stations,
        last_price_per_liter=(
            float(last_refuel.price_per_liter)
            if last_refuel is not None and last_refuel.price_per_liter is not None
            else None
        ),
        last_refuel_odometer=last_refuel.odometer if last_refuel is not None else None,
        # The odometer never goes backwards, so a backdated correction must
        # not lower the value the form prefills.
        last_entry_odometer=max(row.odometer for row in rows),
        last_entry_date=rows[0].date,
    )


@router.post(
    "/cars/{car_id}/logs", response_model=LogEntryOut, status_code=status.HTTP_201_CREATED
)
def create_log(
    car_id: int,
    payload: LogEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LogEntryOut:
    car = get_accessible_car(db, current_user, car_id, min_role=ROLE_EDITOR)

    log = LogEntry(
        car_id=car.id,
        # Whoever is writing it, which on a shared car is not always the
        # owner. Taken from the token, never from the payload.
        author_id=current_user.id,
        type=payload.type,
        odometer=payload.odometer,
        date=payload.date,
        total_cost=_to_decimal(payload.total_cost),
        notes=payload.notes,
    )
    db.add(log)
    db.flush()

    # Only the detail object matching the log type is persisted.
    if payload.type == "refuel" and payload.refuel is not None:
        db.add(
            RefuelDetails(
                log_entry_id=log.id,
                liters=_to_decimal(payload.refuel.liters),
                price_per_liter=_to_decimal(payload.refuel.price_per_liter),
                is_full_tank=payload.refuel.is_full_tank,
                gas_station=payload.refuel.gas_station,
                # Left NULL when the client did not send one — «as the car».
                # Only ГБО clients ever send it (see CarOut.fuel_kinds_used).
                fuel_kind=payload.refuel.fuel_kind,
            )
        )
    elif payload.type == "maintenance" and payload.maintenance is not None:
        db.add(
            MaintenanceDetails(
                log_entry_id=log.id,
                parts_cost=_to_decimal(payload.maintenance.parts_cost),
                labor_cost=_to_decimal(payload.maintenance.labor_cost),
                items=payload.maintenance.items,
            )
        )
    elif payload.type == "repair" and payload.repair is not None:
        db.add(
            RepairDetails(
                log_entry_id=log.id,
                category=payload.repair.category,
                part_name=payload.repair.part_name,
                warranty_months=payload.repair.warranty_months,
                warranty_km=payload.repair.warranty_km,
            )
        )
    elif payload.type == "expense":
        # Unlike the other details, this one is never absent: an expense
        # without a stated category is filed under the default.
        db.add(
            ExpenseDetails(
                log_entry_id=log.id,
                category=(
                    payload.expense.category
                    if payload.expense is not None
                    else DEFAULT_EXPENSE_CATEGORY
                ),
            )
        )

    # Side effect: a log ahead of the car's odometer moves the car forward.
    if payload.odometer > car.current_odometer:
        car.current_odometer = payload.odometer

    # A logged service advances the interval it fulfils, so the journal and the
    # intervals agree without a second "Done" tap. Needs the detail row flushed
    # so its items are visible to the matcher.
    db.flush()
    sync_intervals_from_log(db, log)

    db.commit()
    db.refresh(log)
    # A new full tank can close a segment, so the created row carries the same
    # consumption the list would report for it.
    return _serialize_log(log, _car_consumption_map(db, car))


@router.get("/logs/{log_id}", response_model=LogEntryOut)
def get_log(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LogEntryOut:
    log = get_owned_log(db, current_user, log_id, min_role=ROLE_VIEWER)
    return _serialize_log(log, _car_consumption_map(db, log.car))


def _build_detail_or_422(update_payload: BaseModel, create_schema: type[BaseModel]) -> BaseModel:
    data = update_payload.model_dump(exclude_unset=True)
    try:
        return create_schema(**data)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Incomplete detail object: {exc.errors()[0]['msg']}",
        )


@router.patch("/logs/{log_id}", response_model=LogEntryOut)
def update_log(
    log_id: int,
    payload: LogEntryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LogEntryOut:
    """Partially update a log entry's shared fields and/or its detail object.

    The author is not among them and never is: an entry is signed by whoever
    wrote it, and correcting someone's typo does not make their fill-up
    yours. LogEntryUpdate has no author field, so a payload claiming one is
    ignored rather than refused.
    """
    log = get_owned_log(db, current_user, log_id, min_role=ROLE_EDITOR)
    updates = payload.model_dump(exclude_unset=True)

    if "type" in updates:
        log.type = updates["type"]
    if "odometer" in updates:
        log.odometer = updates["odometer"]
    if "date" in updates:
        log.date = updates["date"]
    if "total_cost" in updates:
        log.total_cost = _to_decimal(updates["total_cost"])
    if "notes" in updates:
        log.notes = updates["notes"]

    if payload.refuel is not None:
        if log.refuel is None:
            full = _build_detail_or_422(payload.refuel, RefuelDetailsIn)
            log.refuel = RefuelDetails(
                liters=_to_decimal(full.liters),
                price_per_liter=_to_decimal(full.price_per_liter),
                is_full_tank=full.is_full_tank,
                gas_station=full.gas_station,
                fuel_kind=full.fuel_kind,
            )
        else:
            detail_updates = payload.refuel.model_dump(exclude_unset=True)
            if "liters" in detail_updates:
                log.refuel.liters = _to_decimal(detail_updates["liters"])
            if "price_per_liter" in detail_updates:
                log.refuel.price_per_liter = _to_decimal(detail_updates["price_per_liter"])
            if "is_full_tank" in detail_updates:
                log.refuel.is_full_tank = detail_updates["is_full_tank"]
            if "gas_station" in detail_updates:
                log.refuel.gas_station = detail_updates["gas_station"]
            # An explicit null is «back to as-the-car», not «leave it alone» —
            # exclude_unset is what tells the two apart.
            if "fuel_kind" in detail_updates:
                log.refuel.fuel_kind = detail_updates["fuel_kind"]

    if payload.maintenance is not None:
        if log.maintenance is None:
            full = _build_detail_or_422(payload.maintenance, MaintenanceDetailsIn)
            log.maintenance = MaintenanceDetails(
                parts_cost=_to_decimal(full.parts_cost),
                labor_cost=_to_decimal(full.labor_cost),
                items=full.items,
            )
        else:
            detail_updates = payload.maintenance.model_dump(exclude_unset=True)
            if "parts_cost" in detail_updates:
                log.maintenance.parts_cost = _to_decimal(detail_updates["parts_cost"])
            if "labor_cost" in detail_updates:
                log.maintenance.labor_cost = _to_decimal(detail_updates["labor_cost"])
            if "items" in detail_updates:
                log.maintenance.items = detail_updates["items"]

    if payload.expense is not None:
        if log.expense is None:
            full = _build_detail_or_422(payload.expense, ExpenseDetailsIn)
            log.expense = ExpenseDetails(category=full.category)
        else:
            detail_updates = payload.expense.model_dump(exclude_unset=True)
            if "category" in detail_updates:
                log.expense.category = detail_updates["category"]

    if payload.repair is not None:
        if log.repair is None:
            full = _build_detail_or_422(payload.repair, RepairDetailsIn)
            log.repair = RepairDetails(
                category=full.category,
                part_name=full.part_name,
                warranty_months=full.warranty_months,
                warranty_km=full.warranty_km,
            )
        else:
            detail_updates = payload.repair.model_dump(exclude_unset=True)
            for field, value in detail_updates.items():
                setattr(log.repair, field, value)

    # A type change drops detail rows that no longer match the log type.
    if log.type != "refuel" and log.refuel is not None:
        log.refuel = None
    if log.type != "maintenance" and log.maintenance is not None:
        log.maintenance = None
    if log.type != "repair" and log.repair is not None:
        log.repair = None
    if log.type != "expense" and log.expense is not None:
        log.expense = None

    # Enforce the same detail invariants as creation.
    if log.type == "refuel" and log.refuel is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="refuel details are required when type is 'refuel'",
        )
    if log.type == "maintenance" and log.maintenance is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="maintenance details are required when type is 'maintenance'",
        )

    # Same side effect as creation: a log ahead of the car's odometer moves
    # the car forward (never backwards).
    if log.odometer > log.car.current_odometer:
        log.car.current_odometer = log.odometer

    # Explicit stamp: column-level onupdate fires only when the log row itself
    # changes, missing detail-only edits — offline sync keys on this stamp.
    log.updated_at = utcnow()

    # A corrected odometer or item list can now match (or better fit) an
    # interval, so re-run the same advance the create path does.
    db.flush()
    sync_intervals_from_log(db, log)

    db.commit()
    db.refresh(log)
    # Editing liters or a tank flag re-opens the segment, so the response
    # carries the recomputed value rather than a stale null.
    return _serialize_log(log, _car_consumption_map(db, log.car))


@router.delete("/logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_log(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    log = get_owned_log(db, current_user, log_id, min_role=ROLE_EDITOR)
    db.delete(log)
    db.commit()
    return None
