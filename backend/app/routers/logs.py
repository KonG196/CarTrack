"""Log entry endpoints: list/create under a car, patch/delete by log id."""

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import (
    Car,
    LogEntry,
    MaintenanceDetails,
    RefuelDetails,
    RepairDetails,
    User,
)
from app.routers.cars import get_owned_car
from app.schemas import (
    LogEntryCreate,
    LogEntryOut,
    LogEntryUpdate,
    LogListOut,
    MaintenanceDetailsIn,
    RefuelDetailsIn,
    RepairDetailsIn,
)

router = APIRouter(tags=["logs"])

VALID_LOG_TYPES = {"refuel", "maintenance", "repair", "expense"}


def get_owned_log(db: Session, user: User, log_id: int) -> LogEntry:
    """Fetch a log entry whose car belongs to the user, or raise 404."""
    log = db.execute(
        select(LogEntry)
        .join(Car, LogEntry.car_id == Car.id)
        .where(LogEntry.id == log_id, Car.user_id == user.id)
    ).scalar_one_or_none()
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Log entry not found")
    return log


def _to_decimal(value: float) -> Decimal:
    """Convert a float to Decimal without binary-float artifacts."""
    return Decimal(str(value))


@router.get("/cars/{car_id}/logs", response_model=LogListOut)
def list_logs(
    car_id: int,
    type: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LogListOut:
    """List a car's log entries, newest first, with optional type filter."""
    car = get_owned_car(db, current_user, car_id)

    filters = [LogEntry.car_id == car.id]
    if type:
        if type not in VALID_LOG_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid log type '{type}'",
            )
        filters.append(LogEntry.type == type)

    total = db.execute(select(func.count(LogEntry.id)).where(*filters)).scalar_one()
    items = (
        db.execute(
            select(LogEntry)
            .where(*filters)
            .order_by(LogEntry.date.desc(), LogEntry.odometer.desc())
            .offset(offset)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return LogListOut(
        items=[LogEntryOut.model_validate(item) for item in items],
        total=total,
    )


@router.post(
    "/cars/{car_id}/logs", response_model=LogEntryOut, status_code=status.HTTP_201_CREATED
)
def create_log(
    car_id: int,
    payload: LogEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LogEntry:
    """Create a log entry; bumps the car's odometer when the log is ahead."""
    car = get_owned_car(db, current_user, car_id)

    log = LogEntry(
        car_id=car.id,
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

    # Side effect: a log ahead of the car's odometer moves the car forward.
    if payload.odometer > car.current_odometer:
        car.current_odometer = payload.odometer

    db.commit()
    db.refresh(log)
    return log


def _build_detail_or_422(update_payload: BaseModel, create_schema: type[BaseModel]) -> BaseModel:
    """Promote a partial detail payload to a full create payload or raise 422."""
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
) -> LogEntry:
    """Partially update a log entry's shared fields and/or its detail object."""
    log = get_owned_log(db, current_user, log_id)
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

    db.commit()
    db.refresh(log)
    return log


@router.delete("/logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_log(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a log entry owned (via its car) by the current user."""
    log = get_owned_log(db, current_user, log_id)
    db.delete(log)
    db.commit()
    return None
