"""Pydantic v2 request/response schemas for the Kapot Tracker API."""

from __future__ import annotations

import datetime as dt
import json
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.currency import normalize_currency
from app.units import normalize_unit_system
from app.i18n import normalize_lang
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
    # The UI language the account is created in; drives emails/bot/errors too.
    # Optional so older clients still work — the register endpoint defaults it.
    language: Optional[str] = None
    currency: Optional[str] = None
    unit_system: Optional[str] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        local, _, domain = value.partition("@")
        if not local or not domain or "." not in domain:
            raise ValueError("invalid email address")
        return value

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else normalize_lang(value)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else normalize_currency(value)

    @field_validator("unit_system")
    @classmethod
    def validate_unit_system(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else normalize_unit_system(value)


class PasswordChangeIn(BaseModel):
    # The current password is not ceremony: a session left open on a borrowed
    # laptop must not be enough to take the account.
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


class EmailChangeIn(BaseModel):
    new_email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class AccountDeleteIn(BaseModel):
    # Deletion is irreversible and wipes every car's service history, so a live
    # session is not enough — the current password must prove the owner.
    password: str = Field(min_length=1, max_length=128)


class EmailChangeOut(BaseModel):
    # Where the code went, so the UI can say it plainly instead of «check your
    # email» when there are now two of them in play.
    pending_email: str


class EmailChangeConfirmIn(BaseModel):
    code: str = Field(min_length=1, max_length=16)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    # Whether the address is confirmed. Drives the «verify your email» banner and
    # the scan / plate-lookup gates on the web (login no longer depends on it).
    email_verified: bool = False
    # «password» or «google». The web hides the change-password UI for google
    # accounts — they have no password to change.
    auth_provider: str = "password"
    # Owner-only: unlocks the /admin panel in the web. Never set through signup.
    is_superadmin: bool = False
    # Onboarding tours already shown. Stored as a JSON string on the model; the
    # validator turns it into a list for the client (and tolerates bad data).
    tours_seen: list[str] = Field(default_factory=list)
    # How the user is signed on a shared car; None means «use the email
    # handle» (models.User.label decides that, not the client).
    display_name: Optional[str] = None

    @field_validator("tours_seen", mode="before")
    @classmethod
    def parse_tours_seen(cls, value: object) -> list[str]:
        if isinstance(value, list):
            return value
        try:
            parsed = json.loads(value) if value else []
            return [str(x) for x in parsed] if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []
    # An address awaiting its code. Shown so the user knows a change is in
    # flight and where to look for it.
    pending_email: Optional[str] = None
    # Notification switches, surfaced so the web can toggle them too — the bot
    # was the only place before. reminders_enabled is the ТО reminders; the rest
    # are the per-type smart pushes.
    digest_enabled: bool = True
    reminders_enabled: bool = True
    notify_fuel: bool = True
    notify_seasonal: bool = True
    notify_rotation: bool = True
    # UI language ('en' | 'uk'); also the language of emails/bot/error details.
    language: str = "en"
    # Display currency code (symbol only; amounts are never converted).
    currency: str = "USD"
    # Display unit system ('metric' | 'imperial'); values are stored metric.
    unit_system: str = "metric"
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
    digest_enabled: Optional[bool] = None
    reminders_enabled: Optional[bool] = None
    notify_fuel: Optional[bool] = None
    notify_seasonal: Optional[bool] = None
    notify_rotation: Optional[bool] = None
    language: Optional[str] = None
    currency: Optional[str] = None
    unit_system: Optional[str] = None

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: Optional[str]) -> Optional[str]:
        return _clean_display_name(value)

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else normalize_lang(value)

    @field_validator("unit_system")
    @classmethod
    def validate_unit_system(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else normalize_unit_system(value)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else normalize_currency(value)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    # Long-lived; the client trades it for a fresh access token at /auth/refresh
    # when the access token expires, so a live session is not interrupted.
    refresh_token: str | None = None


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=1)


class GoogleLoginIn(BaseModel):
    # The Google ID token (a JWT) from Google Identity Services on the client.
    id_token: str = Field(min_length=1)
    # Only used when this login creates a brand-new account, to seed its UI
    # language and currency from what the browser was already using.
    language: Optional[str] = None
    currency: Optional[str] = None
    unit_system: Optional[str] = None

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else normalize_currency(value)

    @field_validator("unit_system")
    @classmethod
    def validate_unit_system(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else normalize_unit_system(value)


class RegisterOut(BaseModel):
    id: int
    email: str
    created_at: dt.datetime
    email_verified: bool
    verification_sent: bool


class PlateLookupIn(BaseModel):
    query: str = Field(min_length=3, max_length=32)
    by_vin: bool = False


class PlateLookupOut(BaseModel):
    plate: Optional[str] = None
    vin: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    fuel_type: Optional[str] = None
    fuel_label: Optional[str] = None
    engine: Optional[str] = None
    color: Optional[str] = None
    photo_url: Optional[str] = None
    is_stolen: Optional[bool] = None
    stolen_details: Optional[str] = None
    registrations: int = 0
    last_registered_at: Optional[str] = None


class VerifyRequestIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class VerifyConfirmIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    # Not pinned to six digits: a pasted token must reach the uniform 400,
    # not a 422 that echoes it back.
    code: str = Field(min_length=1, max_length=512)


class ResetRequestIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    # Which channel the user asked for. Honoured when that channel can reach
    # the account, otherwise the other one is used — the response never says
    # which, because that would leak whether the account has a bot linked.
    channel: Optional[Literal["telegram", "email"]] = None


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
    scratchpad: Optional[str] = Field(default=None, max_length=2000)
    contact_phone: Optional[str] = Field(default=None, max_length=30)
    insurance_number: Optional[str] = Field(default=None, max_length=50)
    insurance_until: Optional[dt.date] = None
    tire_pressure: Optional[str] = Field(default=None, max_length=50)
    fuel_approval: Optional[str] = Field(default=None, max_length=120)


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
    scratchpad: Optional[str] = Field(default=None, max_length=2000)
    contact_phone: Optional[str] = Field(default=None, max_length=30)
    insurance_number: Optional[str] = Field(default=None, max_length=50)
    insurance_until: Optional[dt.date] = None
    tire_pressure: Optional[str] = Field(default=None, max_length=50)
    fuel_approval: Optional[str] = Field(default=None, max_length=120)


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
    # The driver's free-text cheat sheet (gate codes, service phones). NULL/empty
    # until written; editable from the web and via the bot's /note.
    scratchpad: Optional[str] = None
    # QR-passport fields. public_token is present once a passport link is minted
    # (NULL after revoke); the rest are the owner-entered facts the passport shows.
    public_token: Optional[str] = None
    contact_phone: Optional[str] = None
    insurance_number: Optional[str] = None
    insurance_until: Optional[dt.date] = None
    tire_pressure: Optional[str] = None
    fuel_approval: Optional[str] = None
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


class CarImageOut(BaseModel):
    """Imagery for a car: a real photo URL (Wikimedia CC0) when one exists, and a
    marque-logo URL as a fallback. Either may be null; the client shows the photo
    if present, else the logo, else nothing."""

    url: Optional[str] = None
    logo: Optional[str] = None


class PassportTokenOut(BaseModel):
    """The minted passport link and a ready-to-print QR of it."""

    token: str
    url: str
    # An inline SVG of the QR — the web renders it directly, no image request
    # and no client-side QR library.
    qr_svg: str


class PublicCarPassport(BaseModel):
    """The tokenless public view of a car — only what a service or a stranger
    who finds it parked needs. No owner identity, no journal, no analytics."""

    brand: str
    model: str
    generation: Optional[str] = None
    engine: Optional[str] = None
    year: int
    plate: Optional[str] = None
    vin: Optional[str] = None
    fuel_type: FuelType
    contact_phone: Optional[str] = None
    insurance_number: Optional[str] = None
    insurance_until: Optional[dt.date] = None
    tire_pressure: Optional[str] = None
    fuel_approval: Optional[str] = None


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
    # What the next one will likely cost, so «Виконано» opens on a number
    # instead of a zero. Same contract as the forecast: source says whose
    # number it is.
    estimated_cost: Optional[float] = None
    estimated_cost_source: Optional[str] = None


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
    # Kilometres since the last axle rotation (or install) — drives the «rotate»
    # nudge and the button's subtitle. None for a shelf set.
    km_since_rotation: Optional[int] = None


class TireSeasonStatus(BaseModel):
    """Whether the car's region is in a seasonal tyre/washer changeover window.

    Drives the in-app «time to change over» banner. ``changeover_season`` is the
    season the region should move to now ("winter" in autumn, "summer" in
    spring) or None outside both fortnights.
    """

    changeover_season: Optional[Literal["winter", "summer"]] = None
    washer_changeover_due: bool = False


class NotificationOut(BaseModel):
    """One in-app nudge. ``id`` is a stable key for client-side dismiss."""

    id: str
    kind: str  # interval | spike | tire_age | rotation | seasonal | insurance
    severity: str  # crit | warn | info
    car_id: int
    car_label: str
    title: str
    body: str
    action: Optional[str] = None  # a web route to open, e.g. "/intervals"


class NotificationList(BaseModel):
    items: list[NotificationOut]
    count: int
    # How many stored notifications the user hasn't opened the centre for — the
    # header bell's badge.
    unread: int = 0


class NotificationHistoryItem(BaseModel):
    """A stored notification (active or past) for the history page."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    notif_key: str
    kind: str
    severity: str
    car_id: Optional[int] = None
    car_label: Optional[str] = None
    title: str
    body: str
    action: Optional[str] = None
    first_seen_at: dt.datetime
    read_at: Optional[dt.datetime] = None
    resolved_at: Optional[dt.datetime] = None


class NotificationHistory(BaseModel):
    items: list[NotificationHistoryItem]
    unread: int = 0


class UnreadCount(BaseModel):
    unread: int = 0


class YearReviewStation(BaseModel):
    name: str
    avg_price_per_liter: float


class YearReviewBiggest(BaseModel):
    type: str
    title: str
    amount: float
    date: dt.date


class YearReviewOut(BaseModel):
    """«Ваш рік з Kapot» recap. Numeric fields are null for a year with no logs."""

    year: int
    has_data: bool
    available_years: list[int] = Field(default_factory=list)
    total_spent: Optional[float] = None
    by_type: Optional[dict[str, float]] = None
    entries_count: Optional[int] = None
    refuels_count: Optional[int] = None
    liters: Optional[float] = None
    km_driven: Optional[int] = None
    cost_per_km: Optional[float] = None
    avg_consumption_l_100km: Optional[float] = None
    cheapest_station: Optional[YearReviewStation] = None
    biggest_expense: Optional[YearReviewBiggest] = None
    busiest_month: Optional[int] = None


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


class ConsumptionSpikeOut(BaseModel):
    """The latest full-to-full segment running over the car's own recent norm."""

    fuel_kind: str
    consumption_l_100km: float
    baseline_l_100km: float
    pct_over: int
    date: dt.date


class FuelStatsOut(BaseModel):
    avg_consumption_l_100km: Optional[float]
    last_consumption_l_100km: Optional[float]
    avg_cost_per_km: Optional[float]
    history: list[FuelHistoryItem]
    # Per effective fuel kind; empty without refuels, one key for a
    # single-fuel car, two for ГБО. More than one key is what tells the UI to
    # draw a line per fuel instead of one.
    by_kind: dict[str, FuelKindStats] = Field(default_factory=dict)
    # The most recent consumption spike over the car's own baseline, or None —
    # the same watchdog the Telegram bot fires on, surfaced for the web tab.
    spike: Optional[ConsumptionSpikeOut] = None


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
    # "history" | "baseline" — where the number came from. The client must say
    # which: a market ballpark shown as if it were the user's own record is a
    # number nobody has a reason to double-check.
    estimated_cost_source: Optional[str] = None


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


class Tco(BaseModel):
    """Honest cost of ownership: all logged spend over the car's real usage.

    ``cost_per_km`` divides every hryvnia (fuel, service, repairs, expenses) by
    the odometer span; ``cost_per_day`` divides it by the days between the first
    and last log. Each is None until two logs span a distance / a day.
    """

    distance_km: Optional[int] = None
    days: Optional[int] = None
    cost_per_km: Optional[float] = None
    cost_per_day: Optional[float] = None


class LpgSavings(BaseModel):
    """Money the gas tank saved over petrol, from the car's own measured rates.

    Present only on a dual-fuel car with measured segments of both fuels where
    gas actually came out cheaper.
    """

    gas_distance_km: int
    saved_per_km: float
    saved_total: float


class AnalyticsOut(BaseModel):
    totals: Totals
    tco: Tco = Field(default_factory=Tco)
    monthly: list[MonthlyBucket]
    # All-time expense spend per category; only categories with entries appear
    # (pre-0004 expenses count under DEFAULT_EXPENSE_CATEGORY).
    expense_by_category: dict[str, float] = Field(default_factory=dict)
    # Per-station refuel breakdown, most expensive station first.
    stations: list[StationStat] = Field(default_factory=list)
    # What the gas tank saved over petrol; None unless a dual-fuel car with
    # measured segments of both fuels where gas was the cheaper.
    lpg_savings: Optional[LpgSavings] = None
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


class OcrWorkOrderResult(BaseModel):
    items: list[str]
    parts_cost: Optional[float]
    labor_cost: Optional[float]
    total_cost: Optional[float]
    date: Optional[dt.date]
    # False when the read is too thin to prefill a card. The client still gets
    # every field, and decides between offering them and asking the user to type.
    confident: bool
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


# ── Superadmin panel (routers/admin.py) ──────────────────────────────────────


class AdminUserRow(BaseModel):
    """One user as shown in the admin list — identity, status, and cheap counts."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: Optional[str] = None
    language: str
    currency: str
    unit_system: str
    auth_provider: str
    email_verified: bool
    is_superadmin: bool
    blocked: bool
    blocked_reason: Optional[str] = None
    created_at: dt.datetime
    car_count: int = 0
    log_count: int = 0


class AdminUserList(BaseModel):
    users: list[AdminUserRow]
    total: int


class AdminCarRow(BaseModel):
    """A user's car, read-only, in the detail view."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    brand: str
    model: str
    year: int
    fuel_type: str
    current_odometer: int
    plate: Optional[str] = None
    vin: Optional[str] = None
    created_at: dt.datetime
    # Cached car photo URL (Wikimedia) + marque-logo fallback, for the thumbnail.
    image_url: Optional[str] = None
    image_logo: Optional[str] = None


class AdminAuditRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: Optional[int] = None
    action: str
    target_user_id: Optional[int] = None
    target_email: Optional[str] = None
    detail: Optional[str] = None
    created_at: dt.datetime


class AdminUserDetail(BaseModel):
    user: AdminUserRow
    cars: list[AdminCarRow]
    audit: list[AdminAuditRow]


class AdminUserUpdate(BaseModel):
    """Fields a superadmin may edit directly. Password is never here — reset
    links are the only way in, since passwords are hashed."""

    email: Optional[str] = Field(default=None, min_length=3, max_length=255)
    display_name: Optional[str] = None
    language: Optional[str] = None
    currency: Optional[str] = None
    unit_system: Optional[str] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip().lower()
        local, _, domain = value.partition("@")
        if not local or not domain or "." not in domain:
            raise ValueError("invalid email address")
        return value

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: Optional[str]) -> Optional[str]:
        return _clean_display_name(value)

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else normalize_lang(value)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else normalize_currency(value)

    @field_validator("unit_system")
    @classmethod
    def validate_unit_system(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else normalize_unit_system(value)


class AdminStatusUpdate(BaseModel):
    """Status toggles. Each is optional; only the ones sent are applied. When
    `blocked` is true, `blocked_reason` is required (enforced in the router)."""

    email_verified: Optional[bool] = None
    is_superadmin: Optional[bool] = None
    blocked: Optional[bool] = None
    blocked_reason: Optional[str] = Field(default=None, max_length=500)


class AdminLinkOut(BaseModel):
    """A generated verify/reset link and whether it was also mailed."""

    link: str
    emailed: bool = False
