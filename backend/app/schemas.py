"""Pydantic v2 request/response schemas for the Kapot Tracker API."""

from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.vin import normalize_vin

FuelType = Literal["diesel", "petrol", "lpg", "electric", "hybrid"]
# What one refuel may be. Narrower than FuelType on purpose: 'hybrid' is a
# property of a car, never of the stuff going into a tank. NULL is not an
# absent answer but a real one — «the same as the car» (services.fuel).
RefuelFuelKind = Literal["petrol", "diesel", "lpg", "electric"]
LogType = Literal["refuel", "maintenance", "repair", "expense"]
IntervalHealth = Literal["ok", "due_soon", "overdue"]
ExpenseCategory = Literal[
    "Мийка",
    "Паркування",
    "Штраф",
    "Страхування",
    "Податок",
    "Шини",
    "Аксесуари",
    "Інше",
]

EXPENSE_CATEGORIES: tuple[str, ...] = (
    "Мийка",
    "Паркування",
    "Штраф",
    "Страхування",
    "Податок",
    "Шини",
    "Аксесуари",
    "Інше",
)

# Cheat-sheet sections, in the order a car's specs are listed.
SpecCategory = Literal[
    "Моменти затяжки",
    "Рідини та обʼєми",
    "Допуски",
    "Інше",
]

SPEC_CATEGORIES: tuple[str, ...] = (
    "Моменти затяжки",
    "Рідини та обʼєми",
    "Допуски",
    "Інше",
)

DocumentKind = Literal["tech_passport", "insurance", "inspection", "invoice", "other"]

DOCUMENT_KINDS: tuple[str, ...] = (
    "tech_passport",
    "insurance",
    "inspection",
    "invoice",
    "other",
)

# The kinds that lapse on a date rather than just sitting in the glovebox: an
# upload with an expiry books a reminder only for these.
EXPIRING_DOCUMENT_KINDS: frozenset[str] = frozenset({"insurance", "inspection"})

# How this month's spend stands against the car's budget. Not IntervalHealth:
# an interval is 'overdue' the moment it passes, a budget is 'over' only above
# the limit — and 'warn' here is the last fifth of the money, not a date.
BudgetStatus = Literal["ok", "warn", "over"]

TireSeason = Literal["summer", "winter", "all_season"]

TIRE_SEASONS: tuple[str, ...] = ("summer", "winter", "all_season")

# What an expense without an explicit category is filed under (and where
# pre-0004 rows are counted in the analytics breakdown).
DEFAULT_EXPENSE_CATEGORY = "Інше"


# Auth / users


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        local, _, domain = value.partition("@")
        if not local or not domain or "." not in domain:
            raise ValueError("invalid email address")
        return value


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    # How the user is signed on a shared car; None means «use the email
    # handle» (models.User.label decides that, not the client).
    display_name: Optional[str] = None
    created_at: dt.datetime


def _clean_display_name(value: Optional[str]) -> Optional[str]:
    """Trim a display name, or refuse it.

    None clears the name (the label falls back to the email handle); a value
    that is only whitespace is a mistake, not a way to clear it.
    """
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("імʼя не може бути порожнім")
    if len(trimmed) > 80:
        raise ValueError("імʼя не може бути довшим за 80 символів")
    return trimmed


class UserUpdate(BaseModel):
    display_name: Optional[str] = None

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: Optional[str]) -> Optional[str]:
        return _clean_display_name(value)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterOut(BaseModel):
    id: int
    email: str
    created_at: dt.datetime
    email_verified: bool
    verification_sent: bool


class VerifyRequestIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class VerifyConfirmIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    # Not pinned to six digits: a pasted token must reach the uniform 400,
    # not a 422 that echoes it back.
    code: str = Field(min_length=1, max_length=512)


class ResetRequestIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class ResetConfirmIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    # Deliberately loose length bound: a wrong-shaped code (e.g. a pasted JWT)
    # must fall through to the uniform 400, not a 422 echoing the input back.
    code: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=8, max_length=128)


# Cars


def _clean_vin(value: Optional[str]) -> Optional[str]:
    if value is None or not value.strip():
        return None
    normalized = normalize_vin(value)
    if normalized is None:
        raise ValueError(
            "VIN має складатися з 17 символів A-Z (крім I, O, Q) та цифр"
        )
    return normalized


def _clean_plate(value: Optional[str]) -> Optional[str]:
    """Trim and upper-case a plate, keeping whatever format it is in.

    Ukrainian, European and transit plates share no format worth validating,
    so the only rule is that blank means "not set".
    """
    if value is None or not value.strip():
        return None
    return value.strip().upper()


class CarBase(BaseModel):

    @field_validator("vin", check_fields=False)
    @classmethod
    def validate_vin(cls, value: Optional[str]) -> Optional[str]:
        return _clean_vin(value)

    @field_validator("plate", check_fields=False)
    @classmethod
    def validate_plate(cls, value: Optional[str]) -> Optional[str]:
        return _clean_plate(value)


class CarCreate(CarBase):
    brand: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    generation: Optional[str] = Field(default=None, max_length=100)
    engine: Optional[str] = Field(default=None, max_length=100)
    year: int = Field(ge=1950, le=2100)
    fuel_type: FuelType
    current_odometer: int = Field(ge=0)
    vin: Optional[str] = Field(default=None, max_length=32)
    plate: Optional[str] = Field(default=None, max_length=16)
    avg_daily_km_override: Optional[float] = Field(default=None, gt=0)
    tank_liters: Optional[float] = Field(default=None, gt=0)
    monthly_budget: Optional[float] = Field(default=None, gt=0)


class CarUpdate(CarBase):
    brand: Optional[str] = Field(default=None, min_length=1, max_length=100)
    model: Optional[str] = Field(default=None, min_length=1, max_length=100)
    generation: Optional[str] = Field(default=None, max_length=100)
    engine: Optional[str] = Field(default=None, max_length=100)
    year: Optional[int] = Field(default=None, ge=1950, le=2100)
    fuel_type: Optional[FuelType] = None
    current_odometer: Optional[int] = Field(default=None, ge=0)
    vin: Optional[str] = Field(default=None, max_length=32)
    plate: Optional[str] = Field(default=None, max_length=16)
    avg_daily_km_override: Optional[float] = Field(default=None, gt=0)
    tank_liters: Optional[float] = Field(default=None, gt=0)
    monthly_budget: Optional[float] = Field(default=None, gt=0)


class CarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    brand: str
    model: str
    generation: Optional[str]
    engine: Optional[str]
    year: int
    fuel_type: FuelType
    current_odometer: int
    vin: Optional[str]
    plate: Optional[str]
    # The pace forecasts actually use: the override when set, else the
    # computed one. Both are reported so the form can show what auto mode
    # would say while an override is in force.
    avg_daily_km: float
    avg_daily_km_computed: float
    avg_daily_km_override: Optional[float]
    # Usable tank volume, liters. Only the full-tank range estimate reads it.
    tank_liters: Optional[float]
    # The owner's monthly spending limit, ₴. NULL = no budget at all.
    monthly_budget: Optional[float]
    # The effective fuel kinds this car's refuels actually used, resolved, so
    # legacy NULL rows read as the car's own type. Empty without refuels, one
    # entry for a single-fuel car. The refuel form shows its fuel selector
    # when this has more than one entry (or the car is 'lpg') and stays out of
    # the way otherwise — the 95% never chose a fuel and never should.
    fuel_kinds_used: list[str] = Field(default_factory=list)
    # The current user's role on this car ('owner' | 'editor' | 'viewer').
    # The UI hides controls by it rather than letting a viewer press a button
    # that would only come back 403.
    your_role: str
    created_at: dt.datetime
    updated_at: Optional[dt.datetime]


# Sharing: members and invites


class MemberOut(BaseModel):

    # The membership row's id — what DELETE/PATCH /api/members/{id} take.
    id: int
    user_id: int
    # models.User.label: their display name, else their email handle. The
    # email itself is never reported: the list is shown to every member.
    label: str
    role: str
    is_you: bool
    created_at: dt.datetime


class MemberUpdate(BaseModel):
    # A plain str, not a Literal of the assignable roles: 'owner' is a real
    # role that is simply not grantable this way, which is a rule (400), not
    # a malformed request (422). The routes hold every value to the same rule.
    role: str = Field(min_length=1, max_length=20)


class InviteCreate(BaseModel):
    role: str = Field(min_length=1, max_length=20)


class InviteCreatedOut(BaseModel):
    """The one and only time a token is readable."""

    token: str
    # Where to send whoever gets the link: services.invites.INVITE_PATH_PREFIX
    # + token, so the frontend route lives in one place on the backend too.
    invite_path: str
    expires_at: dt.datetime


class InviteCarOut(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    brand: str
    model: str
    year: int


class InvitePreviewOut(BaseModel):
    car: InviteCarOut
    role: str
    inviter_label: str


class InviteAcceptOut(BaseModel):
    car_id: int
    # The role actually held after accepting — an existing member keeps the
    # one they had, which is not necessarily the one the link offered.
    role: str
    already_member: bool


# Log entry details


class RefuelDetailsIn(BaseModel):
    liters: float = Field(gt=0)
    price_per_liter: float = Field(ge=0)
    is_full_tank: bool
    gas_station: Optional[str] = Field(default=None, max_length=200)
    # Omitted by every single-fuel client, which is the 95% case: NULL then
    # resolves to the car's own fuel_type and nothing about the maths moves.
    fuel_kind: Optional[RefuelFuelKind] = None


class RefuelDetailsUpdate(BaseModel):
    liters: Optional[float] = Field(default=None, gt=0)
    price_per_liter: Optional[float] = Field(default=None, ge=0)
    is_full_tank: Optional[bool] = None
    gas_station: Optional[str] = Field(default=None, max_length=200)
    # An explicit null clears it back to «as the car» — the same erase-by-null
    # semantics the other optional detail fields have.
    fuel_kind: Optional[RefuelFuelKind] = None


class RefuelDetailsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    liters: float
    price_per_liter: float
    is_full_tank: bool
    gas_station: Optional[str]
    # Kept raw rather than resolved: the form must be able to tell «as the
    # car» from a kind the user pinned deliberately, which matters the day the
    # car's own fuel_type changes.
    fuel_kind: Optional[RefuelFuelKind] = None
    # The full-to-full segment ENDING at this refuel. Filled in by the log
    # read endpoints from a per-car segment map; null for partial tanks,
    # segment anchors and unmeasurable segments.
    consumption_l_100km: Optional[float] = None


class MaintenanceDetailsIn(BaseModel):
    parts_cost: float = Field(ge=0)
    labor_cost: float = Field(ge=0)
    items: list[str] = Field(default_factory=list)


class MaintenanceDetailsUpdate(BaseModel):
    parts_cost: Optional[float] = Field(default=None, ge=0)
    labor_cost: Optional[float] = Field(default=None, ge=0)
    items: Optional[list[str]] = None


class MaintenanceDetailsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    parts_cost: float
    labor_cost: float
    items: list[str]


class RepairDetailsIn(BaseModel):
    category: str = Field(min_length=1, max_length=100)
    part_name: Optional[str] = Field(default=None, max_length=200)
    warranty_months: Optional[int] = Field(default=None, ge=0)
    warranty_km: Optional[int] = Field(default=None, ge=0)


class RepairDetailsUpdate(BaseModel):
    category: Optional[str] = Field(default=None, min_length=1, max_length=100)
    part_name: Optional[str] = Field(default=None, max_length=200)
    warranty_months: Optional[int] = Field(default=None, ge=0)
    warranty_km: Optional[int] = Field(default=None, ge=0)


class RepairDetailsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category: str
    part_name: Optional[str]
    warranty_months: Optional[int]
    warranty_km: Optional[int]


class ExpenseDetailsIn(BaseModel):
    category: ExpenseCategory


class ExpenseDetailsUpdate(BaseModel):
    category: Optional[ExpenseCategory] = None


class ExpenseDetailsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category: ExpenseCategory


# Log photos


class PhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    content_type: str
    size: int
    created_at: dt.datetime


# Authorship


class AuthorOut(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str


# Log entries


class LogEntryCreate(BaseModel):
    type: LogType
    odometer: int = Field(ge=0)
    date: dt.date
    total_cost: float = Field(ge=0)
    notes: Optional[str] = None
    refuel: Optional[RefuelDetailsIn] = None
    maintenance: Optional[MaintenanceDetailsIn] = None
    repair: Optional[RepairDetailsIn] = None
    # Optional on purpose: an expense without one is filed under
    # DEFAULT_EXPENSE_CATEGORY, and legacy entries carry no category at all.
    expense: Optional[ExpenseDetailsIn] = None

    @model_validator(mode="after")
    def check_required_details(self) -> "LogEntryCreate":
        if self.type == "refuel" and self.refuel is None:
            raise ValueError("refuel details are required when type is 'refuel'")
        if self.type == "maintenance" and self.maintenance is None:
            raise ValueError("maintenance details are required when type is 'maintenance'")
        return self


class LogEntryUpdate(BaseModel):
    type: Optional[LogType] = None
    odometer: Optional[int] = Field(default=None, ge=0)
    date: Optional[dt.date] = None
    total_cost: Optional[float] = Field(default=None, ge=0)
    notes: Optional[str] = None
    refuel: Optional[RefuelDetailsUpdate] = None
    maintenance: Optional[MaintenanceDetailsUpdate] = None
    repair: Optional[RepairDetailsUpdate] = None
    expense: Optional[ExpenseDetailsUpdate] = None


class LogEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    car_id: int
    type: LogType
    odometer: int
    date: dt.date
    total_cost: float
    notes: Optional[str]
    refuel: Optional[RefuelDetailsOut]
    maintenance: Optional[MaintenanceDetailsOut]
    repair: Optional[RepairDetailsOut]
    expense: Optional[ExpenseDetailsOut]
    photos: list[PhotoOut] = Field(default_factory=list)
    # None for every entry written before sharing existed: the author of
    # those is genuinely unknown and is never guessed. Clients must render
    # the row without it — an author is a signature, not part of the record.
    author: Optional[AuthorOut] = None
    created_at: dt.datetime
    updated_at: Optional[dt.datetime]

    @model_validator(mode="after")
    def default_legacy_expense_category(self) -> "LogEntryOut":
        """Report a pre-0004 expense under the default category.

        Those rows carry no expense_details row at all, but the missing row
        is storage history, not a distinct state the client should handle:
        the analytics breakdown already counts them under
        DEFAULT_EXPENSE_CATEGORY, so the log endpoints report the same
        bucket. Read-only — nothing is written back to the database.
        """
        if self.type == "expense" and self.expense is None:
            self.expense = ExpenseDetailsOut(category=DEFAULT_EXPENSE_CATEGORY)
        return self


class LogListOut(BaseModel):
    items: list[LogEntryOut]
    total: int


# Service intervals


class ServiceIntervalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    interval_km: Optional[int] = Field(default=None, gt=0)
    interval_days: Optional[int] = Field(default=None, gt=0)
    last_odometer: Optional[int] = Field(default=None, ge=0)
    last_date: Optional[dt.date] = None

    @model_validator(mode="after")
    def check_at_least_one_interval(self) -> "ServiceIntervalCreate":
        if self.interval_km is None and self.interval_days is None:
            raise ValueError("at least one of interval_km or interval_days is required")
        return self


class ServiceIntervalUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    interval_km: Optional[int] = Field(default=None, gt=0)
    interval_days: Optional[int] = Field(default=None, gt=0)
    last_odometer: Optional[int] = Field(default=None, ge=0)
    last_date: Optional[dt.date] = None


class IntervalStatusOut(BaseModel):
    id: int
    car_id: int
    title: str
    interval_km: Optional[int]
    interval_days: Optional[int]
    last_odometer: Optional[int]
    last_date: Optional[dt.date]
    due_odometer: Optional[int]
    due_date: Optional[dt.date]
    km_left: Optional[int]
    days_left: Optional[int]
    predicted_due_date: Optional[dt.date]
    health_pct: float
    status: IntervalHealth
    updated_at: Optional[dt.datetime]


class IntervalCompleteIn(BaseModel):
    odometer: int = Field(ge=0)
    date: dt.date
    total_cost: float = Field(default=0, ge=0)
    parts_cost: float = Field(default=0, ge=0)
    labor_cost: float = Field(default=0, ge=0)
    # Empty means "just the interval title" — filled in by the service.
    items: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class IntervalCompleteOut(BaseModel):
    log: LogEntryOut
    interval: IntervalStatusOut


class IntervalPresetOut(BaseModel):
    title: str
    interval_km: Optional[int]
    interval_days: Optional[int]


class IntervalPresetsOut(BaseModel):
    maintenance: list[IntervalPresetOut]
    compliance: list[IntervalPresetOut]


# Car specs (cheat sheet)


class CarSpecCreate(BaseModel):
    category: SpecCategory
    name: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=200)
    sort_order: int = Field(default=0, ge=0)


class CarSpecUpdate(BaseModel):
    category: Optional[SpecCategory] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    value: Optional[str] = Field(default=None, min_length=1, max_length=200)
    sort_order: Optional[int] = Field(default=None, ge=0)


class CarSpecOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    car_id: int
    # A plain str, unlike the Literal on the way in: writes are held to
    # SPEC_CATEGORIES, but a row already in the table is reported as stored.
    # Retiring a category must never turn a car's saved sheet into a 500 —
    # the data outlives the tuple. The clients sort unknown ones last.
    category: str
    name: str
    value: str
    sort_order: int


# Car documents


class CarDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    car_id: int
    kind: DocumentKind
    title: str
    filename: str
    content_type: str
    size: int
    expires_at: Optional[dt.date]
    created_at: dt.datetime
    # The reminder booked for an expiring document, reported by the upload
    # that created it. Not a stored column: the interval is independent of
    # the document from the moment it exists, so a listing has nothing to
    # report here.
    linked_interval_id: Optional[int] = None


# Tire sets


class TireSetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    season: TireSeason
    size: Optional[str] = Field(default=None, max_length=30)
    dot_year: Optional[int] = Field(default=None, ge=1980, le=2100)
    purchased_at: Optional[dt.date] = None


class TireSetUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    season: Optional[TireSeason] = None
    size: Optional[str] = Field(default=None, max_length=30)
    dot_year: Optional[int] = Field(default=None, ge=1980, le=2100)
    purchased_at: Optional[dt.date] = None
    # Correctable because installing can only stamp «now»: a set already on
    # the car when the garage was entered has km of its own. `is_installed`
    # is deliberately absent — the swap has one door, POST /tires/{id}/install.
    odometer_at_install: Optional[int] = Field(default=None, ge=0)


class TireSetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    car_id: int
    name: str
    # A plain str, unlike the Literal on the way in: writes are held to
    # TIRE_SEASONS, but a row already in the table is reported as stored.
    season: str
    size: Optional[str]
    dot_year: Optional[int]
    purchased_at: Optional[dt.date]
    odometer_at_install: Optional[int]
    is_installed: bool
    created_at: dt.datetime
    # Computed, not stored: models.TireSet.km_on_set reads it off the car's
    # current odometer, so it is right without anything writing it.
    km_on_set: Optional[int] = None


# Analytics


class TotalsByType(BaseModel):
    refuel: float
    maintenance: float
    repair: float
    expense: float


class Totals(BaseModel):
    all_time: float
    this_month: float
    by_type: TotalsByType


class MonthlyBucket(BaseModel):
    month: str
    refuel: float
    maintenance: float
    repair: float
    expense: float
    total: float


class FuelHistoryItem(BaseModel):
    date: dt.date
    odometer: int
    distance_km: int
    liters: float
    consumption_l_100km: float


class FuelKindStats(BaseModel):

    avg_consumption_l_100km: Optional[float]
    last_consumption_l_100km: Optional[float]
    avg_cost_per_km: Optional[float]
    # Everything bought of this fuel, including fills too early or too late to
    # be measured — unlike the averages above, which are measured-only.
    total_liters: float
    total_cost: float
    # This fuel's own measured segments — what the chart draws as its line.
    # For a single-fuel car this is the same list as FuelStatsOut.history.
    history: list[FuelHistoryItem] = Field(default_factory=list)


class FuelStatsOut(BaseModel):
    avg_consumption_l_100km: Optional[float]
    last_consumption_l_100km: Optional[float]
    avg_cost_per_km: Optional[float]
    history: list[FuelHistoryItem]
    # Per effective fuel kind; empty without refuels, one key for a
    # single-fuel car, two for ГБО. More than one key is what tells the UI to
    # draw a line per fuel instead of one.
    by_kind: dict[str, FuelKindStats] = Field(default_factory=dict)


class PriceHistoryItem(BaseModel):

    date: dt.date
    price_per_liter: float
    # Resolved, not raw: a line on a chart cannot be labelled «NULL».
    fuel_kind: str
    gas_station: Optional[str]


class ForecastUpcomingItem(BaseModel):
    interval_id: int
    title: str
    predicted_due_date: Optional[dt.date]
    km_left: Optional[int]
    days_left: Optional[int]
    estimated_cost: Optional[float]


class Forecast(BaseModel):
    monthly_km_rate: Optional[float]
    avg_monthly_spend: Optional[float]
    projected_month_total: Optional[float]
    upcoming: list[ForecastUpcomingItem]


class StationStat(BaseModel):

    name: str
    refuels: int
    total_liters: float
    total_cost: float
    # Blended price actually paid (total cost / total liters), not a mean of
    # per-refuel prices. None only if the station somehow logged zero liters.
    avg_price_per_liter: Optional[float]
    # Averages the full-to-full segments STARTING here; None when this station
    # never anchored a measurable segment.
    avg_consumption_l_100km: Optional[float]


class BudgetOut(BaseModel):
    """This calendar month against the owner's limit. Absent without a limit."""

    limit: float
    spent_this_month: float
    # The same number the forecast reports — read from it, never recomputed.
    # None when the car has no spending data to project from.
    projected_month_total: Optional[float]
    # Spend as a percentage of the limit; may exceed 100.
    pct_used: float
    #: 'ok' under 80%, 'warn' from 80% through 100%, 'over' above it.
    status: BudgetStatus


class AnalyticsOut(BaseModel):
    totals: Totals
    monthly: list[MonthlyBucket]
    # All-time expense spend per category; only categories with entries appear
    # (pre-0004 expenses count under DEFAULT_EXPENSE_CATEGORY).
    expense_by_category: dict[str, float] = Field(default_factory=dict)
    # Per-station refuel breakdown, most expensive station first.
    stations: list[StationStat] = Field(default_factory=list)
    fuel: FuelStatsOut
    # Every refuel's price per litre, oldest first, capped at the most recent
    # PRICE_HISTORY_LIMIT. Kept flat and kind-tagged rather than pre-split
    # into series: the chart decides how many lines to draw.
    price_history: list[PriceHistoryItem] = Field(default_factory=list)
    forecast: Forecast
    # Kilometres a FULL tank goes at the car's average consumption — not the
    # distance left in the current tank, which nothing here knows. None
    # without a tank volume or without a measured consumption.
    range_km: Optional[int] = None
    # None when the car has no monthly_budget: there is nothing to show.
    budget: Optional[BudgetOut] = None


# Refuel form context


class RefuelContextOut(BaseModel):
    recent_stations: list[str] = Field(default_factory=list)
    last_price_per_liter: Optional[float]
    last_refuel_odometer: Optional[int]
    # Across ALL log types, not just refuels: the odometer the form prefills.
    last_entry_odometer: Optional[int]
    last_entry_date: Optional[dt.date]


# Receipt OCR


class OcrScanResult(BaseModel):
    liters: Optional[float]
    price_per_liter: Optional[float]
    total_cost: Optional[float]
    date: Optional[dt.date]
    gas_station: Optional[str]
    raw_text: str


# VIN decoding


class VinDecodeIn(BaseModel):
    # Deliberately unvalidated: the form decodes as the user types, and a
    # half-typed VIN must come back as valid=False, not as a 422.
    vin: str = Field(min_length=1, max_length=64)


class VinDecodeOut(BaseModel):
    wmi: Optional[str]
    manufacturer: Optional[str]
    country: Optional[str]
    model_year: Optional[int]
    valid: bool


# Telegram linking


class TelegramLinkCodeResponse(BaseModel):
    code: str
    deep_link: Optional[str]
    expires_in_minutes: int


class TelegramStatus(BaseModel):
    linked: bool


# OBD import (Car Scanner)

VerdictLevel = Literal["ok", "warn", "crit"]


class ObdSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    car_id: int
    filename: str
    # None when the log carried seconds from start instead of wall-clock time.
    recorded_at: Optional[dt.datetime]
    duration_s: float
    sample_count: int
    created_at: dt.datetime


class ObdMetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    unit: str
    min: float
    max: float
    avg: float
    last: float
    # [[seconds_from_start, value], ...], at most 200 points.
    series: list[tuple[float, float]]


class ObdVerdictOut(BaseModel):
    key: str
    level: VerdictLevel
    text: str


class ObdSessionDetail(BaseModel):
    session: ObdSessionOut
    metrics: list[ObdMetricOut]
    verdicts: list[ObdVerdictOut]
    # Only ever populated by the import response: the columns a session did
    # not recognize are not stored, so a later GET reports an empty list.
    unmapped_columns: list[str] = []
