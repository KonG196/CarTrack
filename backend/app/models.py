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
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    # How the user is signed under a shared car's entries. NULL means the
    # label falls back to the part of the email before the «@».
    display_name: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    # Unique per app logic: linking re-assigns a chat id instead of duplicating it.
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Whether the Sunday digest is wanted, toggled by «/digest on|off» in the
    # bot. On by default: a weekly summary of a week you actually used the
    # tracker is the point of keeping one, and the empty-week rule (see
    # bot/service.build_weekly_digest) already keeps it from being noise.
    digest_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    # Password reset via Telegram: bcrypt hash of the 6-digit code + its expiry.
    # Pre-0014 accounts are verified by the migration: they existed before the
    # gate, so locking them out would be a regression, not a security win.
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    verify_code_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    verify_code_expires_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    reset_code_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reset_code_expires_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    cars: Mapped[list[Car]] = relationship(back_populates="user", cascade="all, delete-orphan")
    memberships: Mapped[list[CarMember]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def label(self) -> str:
        """How this user is signed to other people on a shared car.

        Their display name if they set one, else the part of their email
        before the «@» — never the whole address: a members list is shown to
        everyone on the car, and an email is not theirs to hand out.
        """
        display_name = (self.display_name or "").strip()
        return display_name or self.email.split("@")[0]


class CarMember(Base):
    """One person's access to one car they do not own.

    The owner is NOT defined by this table — ``cars.user_id`` stays the
    authoritative owner, and app.access derives the 'owner' role from it.
    An owner row is nevertheless kept here (backfilled by migration 0008,
    written on create) so the members list is one plain query; access works
    with or without it.
    """

    __tablename__ = "car_members"
    __table_args__ = (UniqueConstraint("car_id", "user_id", name="uq_car_members_car_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    car_id: Mapped[int] = mapped_column(
        ForeignKey("cars.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # One of app.access.ROLE_RANK. An unrecognized value ranks below every
    # real role rather than raising — see app.access.role_rank.
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    car: Mapped[Car] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


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
    # 17 chars of the VIN alphabet, upper-cased; the check digit is not
    # verified (European VINs put a filler there). See services/vin.py.
    vin: Mapped[Optional[str]] = mapped_column(String(17), nullable=True)
    # Kept exactly as the owner typed it, only trimmed and upper-cased:
    # Ukrainian, European and transit plates have no one format.
    plate: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    avg_daily_km_override: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Usable tank volume in liters. Feeds the full-tank range estimate only
    # (services/fuel.py:compute_range_km) — the app never knows how much fuel
    # is actually in the tank right now. NULL hides the estimate entirely.
    tank_liters: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # The owner's self-set spending limit for a calendar month, in ₴.
    # NULL = no budget, which is not the same as a budget of zero.
    monthly_budget: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    # Nullable for pre-0003 rows; future offline sync keys on this stamp.
    updated_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime, nullable=True, default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="cars")
    logs: Mapped[list[LogEntry]] = relationship(
        back_populates="car", cascade="all, delete-orphan"
    )
    intervals: Mapped[list[ServiceInterval]] = relationship(
        back_populates="car", cascade="all, delete-orphan"
    )
    specs: Mapped[list[CarSpec]] = relationship(
        back_populates="car", cascade="all, delete-orphan"
    )
    documents: Mapped[list[CarDocument]] = relationship(
        back_populates="car", cascade="all, delete-orphan"
    )
    members: Mapped[list[CarMember]] = relationship(
        back_populates="car", cascade="all, delete-orphan"
    )
    invites: Mapped[list[CarInvite]] = relationship(
        back_populates="car", cascade="all, delete-orphan"
    )
    tire_sets: Mapped[list[TireSet]] = relationship(
        back_populates="car", cascade="all, delete-orphan"
    )


class CarInvite(Base):
    """A share link for one car: a hashed token that may be spent once.

    The token itself is never stored — only its bcrypt hash, exactly as the
    password reset codes are handled, so a leaked database hands out no
    working links. It is returned to the owner once, at creation, and cannot
    be recovered afterwards; a lost link is re-issued, not looked up.

    Spent invites are kept rather than deleted: ``used_by``/``used_at`` are
    the record of how someone came to have access to the car.
    """

    __tablename__ = "car_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    car_id: Mapped[int] = mapped_column(
        ForeignKey("cars.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # The role this link grants — 'editor' or 'viewer' (see
    # app.access.ASSIGNABLE_ROLES). An invite can never hand out 'owner'.
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    # Both NULL until the link is spent, then both set together.
    used_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    used_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    car: Mapped[Car] = relationship(back_populates="invites")


class LogEntry(Base):
    __tablename__ = "log_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    car_id: Mapped[int] = mapped_column(
        ForeignKey("cars.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Who wrote this entry. NULL for everything created before sharing
    # existed: the author of those is genuinely unknown and is never guessed.
    # SET NULL rather than CASCADE — a member leaving must not delete the
    # history they wrote on someone else's car.
    author_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    odometer: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    # Nullable for pre-0003 rows; future offline sync keys on this stamp.
    updated_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime, nullable=True, default=utcnow, onupdate=utcnow
    )

    car: Mapped[Car] = relationship(back_populates="logs")
    # Deliberately one-directional: a User has no «logs I wrote» collection.
    # A reverse side would put authored entries in the cascade path of
    # deleting a user, and a member's history belongs to the car, not to them.
    author: Mapped[Optional[User]] = relationship(foreign_keys=[author_id])
    refuel: Mapped[Optional[RefuelDetails]] = relationship(
        back_populates="log_entry", cascade="all, delete-orphan", uselist=False
    )
    maintenance: Mapped[Optional[MaintenanceDetails]] = relationship(
        back_populates="log_entry", cascade="all, delete-orphan", uselist=False
    )
    repair: Mapped[Optional[RepairDetails]] = relationship(
        back_populates="log_entry", cascade="all, delete-orphan", uselist=False
    )
    # Absent on pre-0004 expense rows: those keep no category at all.
    expense: Mapped[Optional[ExpenseDetails]] = relationship(
        back_populates="log_entry", cascade="all, delete-orphan", uselist=False
    )
    photos: Mapped[list[LogPhoto]] = relationship(
        back_populates="log_entry", cascade="all, delete-orphan"
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
    fuel_kind: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

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


class ExpenseDetails(Base):
    __tablename__ = "expense_details"

    log_entry_id: Mapped[int] = mapped_column(
        ForeignKey("log_entries.id", ondelete="CASCADE"), primary_key=True
    )
    # One of the canonical categories in schemas.EXPENSE_CATEGORIES.
    category: Mapped[str] = mapped_column(String(50), nullable=False)

    log_entry: Mapped[LogEntry] = relationship(back_populates="expense")


class LogPhoto(Base):
    __tablename__ = "log_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    log_entry_id: Mapped[int] = mapped_column(
        ForeignKey("log_entries.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # The generated on-disk name (<uuid4>.<ext>) inside <UPLOADS_DIR>/<user_id>/.
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    log_entry: Mapped[LogEntry] = relationship(back_populates="photos")


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
    snoozed_until: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    # Nullable for pre-0003 rows; future offline sync keys on this stamp.
    updated_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime, nullable=True, default=utcnow, onupdate=utcnow
    )

    car: Mapped[Car] = relationship(back_populates="intervals")


class ObdSession(Base):
    """One Car Scanner CSV log imported for a car.

    The raw CSV is deliberately not stored: a 40-minute log is megabytes of
    text whose only use is the series already extracted into ObdMetric.
    """

    __tablename__ = "obd_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    car_id: Mapped[int] = mapped_column(
        ForeignKey("cars.id", ondelete="CASCADE"), index=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # NULL when the log was timed in seconds from start rather than in
    # absolute timestamps — Car Scanner writes both, depending on profile.
    recorded_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    duration_s: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    metrics: Mapped[list[ObdMetric]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class ObdMetric(Base):

    __tablename__ = "obd_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("obd_sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # A canonical key from services/obd.py, never the raw column header.
    key: Mapped[str] = mapped_column(String(50), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    min: Mapped[float] = mapped_column(Float, nullable=False)
    max: Mapped[float] = mapped_column(Float, nullable=False)
    avg: Mapped[float] = mapped_column(Float, nullable=False)
    last: Mapped[float] = mapped_column(Float, nullable=False)
    # [[seconds, value], ...] downsampled to <= 200 points (extremes kept).
    series: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    session: Mapped[ObdSession] = relationship(back_populates="metrics")


class CarSpec(Base):
    """One line of a car's cheat sheet: «Колісні болти» = «120 Нм».

    Free-form on purpose. Presets (services/spec_presets.py) only seed the
    first values; there is no global specification database behind this.
    """

    __tablename__ = "car_specs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    car_id: Mapped[int] = mapped_column(
        ForeignKey("cars.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # One of schemas.SPEC_CATEGORIES.
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    car: Mapped[Car] = relationship(back_populates="specs")


class TireSet(Base):
    """One set of tires a car wears, on the car or on the shelf.

    At most one set per car is installed at a time; that invariant belongs to
    the install endpoint (routers/tires.py), which mounts one set and takes
    the previous one off in the same transaction. Nothing else writes
    ``is_installed``.

    ``odometer_at_install`` is stamped from the car's odometer at that moment
    and is the only thing the mileage of a set is derived from. Deliberately
    kept when the set comes off: it is the record of when it was last put on,
    and the owner may correct it (tires already on the car when the garage was
    entered have km of their own).
    """

    __tablename__ = "tire_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    car_id: Mapped[int] = mapped_column(
        ForeignKey("cars.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    # One of schemas.TIRE_SEASONS.
    season: Mapped[str] = mapped_column(String(10), nullable=False)
    size: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    dot_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    purchased_at: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    odometer_at_install: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_installed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    car: Mapped[Car] = relationship(back_populates="tire_sets")

    @property
    def km_on_set(self) -> Optional[int]:
        """Kilometres run since this set was put on, or None when unknown.

        Only the mounted set can answer: taking a set off records no odometer,
        so «current - stamp» for a set on the shelf would go on counting the
        kilometres the car drove on the other one. A set with no stamp (a row
        predating the install endpoint) says nothing rather than guessing 0.

        Never negative: an odometer corrected downwards is a typo being fixed,
        not a car driven backwards, and «-3 000 км on this set» is no answer.
        """
        if not self.is_installed or self.odometer_at_install is None:
            return None
        return max(0, self.car.current_odometer - self.odometer_at_install)


class CarDocument(Base):
    """A scan or PDF filed under a car: policy, tech passport, invoice.

    Files live next to log photos, under <UPLOADS_DIR>/<user_id>/ (see
    services/photos.py). An expiring document (insurance/inspection with
    expires_at) also books a ServiceInterval so the deadline is reminded
    about; that interval is deliberately not owned by this row — the policy
    still lapses if the owner deletes the scan.
    """

    __tablename__ = "car_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    car_id: Mapped[int] = mapped_column(
        ForeignKey("cars.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # One of schemas.DOCUMENT_KINDS.
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    # The generated on-disk name (<uuid4>.<ext>) inside <UPLOADS_DIR>/<user_id>/.
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    car: Mapped[Car] = relationship(back_populates="documents")
