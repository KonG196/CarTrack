"""SQLAlchemy ORM models for Kapot Tracker."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> dt.datetime:
    """Timezone-aware UTC timestamp used for created_at defaults."""
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    # Unique per app logic: linking re-assigns a chat id instead of duplicating it.
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    cars: Mapped[list[Car]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Car(Base):
    __tablename__ = "cars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    brand: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    generation: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    engine: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    fuel_type: Mapped[str] = mapped_column(String(20), nullable=False)
    current_odometer: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="cars")
    logs: Mapped[list[LogEntry]] = relationship(
        back_populates="car", cascade="all, delete-orphan"
    )
    intervals: Mapped[list[ServiceInterval]] = relationship(
        back_populates="car", cascade="all, delete-orphan"
    )


class LogEntry(Base):
    __tablename__ = "log_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    car_id: Mapped[int] = mapped_column(
        ForeignKey("cars.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    odometer: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    car: Mapped[Car] = relationship(back_populates="logs")
    refuel: Mapped[Optional[RefuelDetails]] = relationship(
        back_populates="log_entry", cascade="all, delete-orphan", uselist=False
    )
    maintenance: Mapped[Optional[MaintenanceDetails]] = relationship(
        back_populates="log_entry", cascade="all, delete-orphan", uselist=False
    )
    repair: Mapped[Optional[RepairDetails]] = relationship(
        back_populates="log_entry", cascade="all, delete-orphan", uselist=False
    )


class RefuelDetails(Base):
    __tablename__ = "refuel_details"

    log_entry_id: Mapped[int] = mapped_column(
        ForeignKey("log_entries.id", ondelete="CASCADE"), primary_key=True
    )
    liters: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    price_per_liter: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    is_full_tank: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    gas_station: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    log_entry: Mapped[LogEntry] = relationship(back_populates="refuel")


class MaintenanceDetails(Base):
    __tablename__ = "maintenance_details"

    log_entry_id: Mapped[int] = mapped_column(
        ForeignKey("log_entries.id", ondelete="CASCADE"), primary_key=True
    )
    parts_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    labor_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    items: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    log_entry: Mapped[LogEntry] = relationship(back_populates="maintenance")


class RepairDetails(Base):
    __tablename__ = "repair_details"

    log_entry_id: Mapped[int] = mapped_column(
        ForeignKey("log_entries.id", ondelete="CASCADE"), primary_key=True
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    part_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    warranty_months: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    warranty_km: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    log_entry: Mapped[LogEntry] = relationship(back_populates="repair")


class ServiceInterval(Base):
    __tablename__ = "service_intervals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    car_id: Mapped[int] = mapped_column(
        ForeignKey("cars.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    interval_km: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    interval_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_odometer: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_date: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    last_notified_at: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)

    car: Mapped[Car] = relationship(back_populates="intervals")
