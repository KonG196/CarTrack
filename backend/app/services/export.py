"""Data portability: full-account JSON export/import and per-car CSV of logs.

The JSON tree is deliberately free of internal ids (and photo files — only
their metadata travels), so a dump can be re-imported into any account or
instance. Import is append-only v1: everything is created as new rows for
the current user inside a single transaction.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.access import ensure_owner_membership
from app.models import (
    Car,
    LogEntry,
    MaintenanceDetails,
    RefuelDetails,
    RepairDetails,
    ServiceInterval,
    User,
)
from app.schemas import CarCreate, LogEntryCreate, ServiceIntervalCreate

SCHEMA_VERSION = 1

CSV_COLUMNS = (
    "date",
    "type",
    "odometer",
    "total_cost",
    "liters",
    "price_per_liter",
    "is_full_tank",
    "gas_station",
    "items",
    "parts_cost",
    "labor_cost",
    "category",
    "part_name",
    "warranty_months",
    "warranty_km",
    "notes",
)


class ImportValidationError(Exception):
    """Raised when an import payload element fails validation; str() is the 422 detail."""


def _to_decimal(value: float) -> Decimal:
    return Decimal(str(value))


# Export


def _user_cars(db: Session, user: User) -> list[Car]:
    return (
        db.execute(
            select(Car)
            .where(Car.user_id == user.id)
            .options(
                selectinload(Car.intervals),
                selectinload(Car.logs).selectinload(LogEntry.refuel),
                selectinload(Car.logs).selectinload(LogEntry.maintenance),
                selectinload(Car.logs).selectinload(LogEntry.repair),
                selectinload(Car.logs).selectinload(LogEntry.expense),
                selectinload(Car.logs).selectinload(LogEntry.photos),
            )
            .order_by(Car.id)
        )
        .scalars()
        .all()
    )


def _serialize_log(log: LogEntry) -> dict:
    """Portable log dict: detail objects only when present, photos as metadata."""
    data: dict = {
        "type": log.type,
        "odometer": log.odometer,
        "date": log.date.isoformat(),
        "total_cost": float(log.total_cost),
        "notes": log.notes,
        "photos": [
            {
                "filename": photo.filename,
                "content_type": photo.content_type,
                "size": photo.size,
            }
            for photo in log.photos
        ],
    }
    if log.refuel is not None:
        data["refuel"] = {
            "liters": float(log.refuel.liters),
            "price_per_liter": float(log.refuel.price_per_liter),
            "is_full_tank": log.refuel.is_full_tank,
            "gas_station": log.refuel.gas_station,
        }
    if log.maintenance is not None:
        data["maintenance"] = {
            "parts_cost": float(log.maintenance.parts_cost),
            "labor_cost": float(log.maintenance.labor_cost),
            "items": log.maintenance.items,
        }
    if log.repair is not None:
        data["repair"] = {
            "category": log.repair.category,
            "part_name": log.repair.part_name,
            "warranty_months": log.repair.warranty_months,
            "warranty_km": log.repair.warranty_km,
        }
    return data


def _serialize_car(car: Car) -> dict:
    return {
        "brand": car.brand,
        "model": car.model,
        "generation": car.generation,
        "engine": car.engine,
        "year": car.year,
        "fuel_type": car.fuel_type,
        "current_odometer": car.current_odometer,
        "intervals": [
            {
                "title": interval.title,
                "interval_km": interval.interval_km,
                "interval_days": interval.interval_days,
                "last_odometer": interval.last_odometer,
                "last_date": interval.last_date.isoformat() if interval.last_date else None,
            }
            for interval in sorted(car.intervals, key=lambda i: i.id)
        ],
        "logs": [
            _serialize_log(log)
            for log in sorted(car.logs, key=lambda l: (l.date, l.odometer, l.id))
        ],
    }


def build_export(db: Session, user: User) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "cars": [_serialize_car(car) for car in _user_cars(db, user)],
    }


def build_logs_csv(db: Session, car: Car) -> str:
    logs = (
        db.execute(
            select(LogEntry)
            .where(LogEntry.car_id == car.id)
            .options(
                selectinload(LogEntry.refuel),
                selectinload(LogEntry.maintenance),
                selectinload(LogEntry.repair),
                selectinload(LogEntry.expense),
            )
            .order_by(LogEntry.date, LogEntry.odometer, LogEntry.id)
        )
        .scalars()
        .all()
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for log in logs:
        refuel, maintenance, repair = log.refuel, log.maintenance, log.repair
        writer.writerow(
            [
                log.date.isoformat(),
                log.type,
                log.odometer,
                float(log.total_cost),
                float(refuel.liters) if refuel else "",
                float(refuel.price_per_liter) if refuel else "",
                ("true" if refuel.is_full_tank else "false") if refuel else "",
                (refuel.gas_station or "") if refuel else "",
                "; ".join(maintenance.items) if maintenance else "",
                float(maintenance.parts_cost) if maintenance else "",
                float(maintenance.labor_cost) if maintenance else "",
                repair.category if repair else "",
                (repair.part_name or "") if repair else "",
                repair.warranty_months if repair and repair.warranty_months is not None else "",
                repair.warranty_km if repair and repair.warranty_km is not None else "",
                log.notes or "",
            ]
        )
    return buffer.getvalue()


# Import


def _validate(schema: type, raw: object, path: str):
    try:
        return schema.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        raise ImportValidationError(f"{path}: {first['msg']}") from exc


def _list_field(raw: dict, key: str, path: str) -> list:
    value = raw.get(key, [])
    if not isinstance(value, list):
        raise ImportValidationError(f"{path}.{key}: must be a list")
    return value


def _build_log(car_id: int, payload: LogEntryCreate) -> LogEntry:
    log = LogEntry(
        car_id=car_id,
        type=payload.type,
        odometer=payload.odometer,
        date=payload.date,
        total_cost=_to_decimal(payload.total_cost),
        notes=payload.notes,
    )
    if payload.type == "refuel" and payload.refuel is not None:
        log.refuel = RefuelDetails(
            liters=_to_decimal(payload.refuel.liters),
            price_per_liter=_to_decimal(payload.refuel.price_per_liter),
            is_full_tank=payload.refuel.is_full_tank,
            gas_station=payload.refuel.gas_station,
        )
    elif payload.type == "maintenance" and payload.maintenance is not None:
        log.maintenance = MaintenanceDetails(
            parts_cost=_to_decimal(payload.maintenance.parts_cost),
            labor_cost=_to_decimal(payload.maintenance.labor_cost),
            items=payload.maintenance.items,
        )
    elif payload.type == "repair" and payload.repair is not None:
        log.repair = RepairDetails(
            category=payload.repair.category,
            part_name=payload.repair.part_name,
            warranty_months=payload.repair.warranty_months,
            warranty_km=payload.repair.warranty_km,
        )
    return log


def import_data(db: Session, user: User, payload: dict) -> dict:
    """Append everything in an export payload to the user's account.

    All-or-nothing: the whole tree is validated element by element (reusing
    the create schemas) and staged on the session; the single commit happens
    only after the last element. Raises ImportValidationError with the path
    of the first invalid element — the caller must roll back.
    """
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ImportValidationError(
            f"schema_version: only version {SCHEMA_VERSION} is supported"
        )
    if not isinstance(payload.get("cars"), list):
        raise ImportValidationError("cars: must be a list")

    cars_created = logs_created = intervals_created = 0
    for car_index, car_raw in enumerate(payload["cars"]):
        car_path = f"cars[{car_index}]"
        car_payload: CarCreate = _validate(CarCreate, car_raw, car_path)
        car = Car(user_id=user.id, **car_payload.model_dump())
        db.add(car)
        db.flush()  # allocate the new car id for children
        ensure_owner_membership(db, car)
        cars_created += 1

        for index, interval_raw in enumerate(_list_field(car_raw, "intervals", car_path)):
            interval_payload: ServiceIntervalCreate = _validate(
                ServiceIntervalCreate, interval_raw, f"{car_path}.intervals[{index}]"
            )
            db.add(ServiceInterval(car_id=car.id, **interval_payload.model_dump()))
            intervals_created += 1

        for index, log_raw in enumerate(_list_field(car_raw, "logs", car_path)):
            log_payload: LogEntryCreate = _validate(
                LogEntryCreate, log_raw, f"{car_path}.logs[{index}]"
            )
            db.add(_build_log(car.id, log_payload))
            logs_created += 1

    db.commit()
    return {
        "cars_created": cars_created,
        "logs_created": logs_created,
        "intervals_created": intervals_created,
    }
