"""Pydantic v2 request/response schemas for the Kapot Tracker API."""

from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FuelType = Literal["diesel", "petrol", "lpg", "electric", "hybrid"]
LogType = Literal["refuel", "maintenance", "repair", "expense"]
IntervalHealth = Literal["ok", "due_soon", "overdue"]


# ---------------------------------------------------------------------------
# Auth / users
# ---------------------------------------------------------------------------


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
    created_at: dt.datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# Cars
# ---------------------------------------------------------------------------


class CarCreate(BaseModel):
    brand: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    generation: Optional[str] = Field(default=None, max_length=100)
    engine: Optional[str] = Field(default=None, max_length=100)
    year: int = Field(ge=1950, le=2100)
    fuel_type: FuelType
    current_odometer: int = Field(ge=0)


class CarUpdate(BaseModel):
    brand: Optional[str] = Field(default=None, min_length=1, max_length=100)
    model: Optional[str] = Field(default=None, min_length=1, max_length=100)
    generation: Optional[str] = Field(default=None, max_length=100)
    engine: Optional[str] = Field(default=None, max_length=100)
    year: Optional[int] = Field(default=None, ge=1950, le=2100)
    fuel_type: Optional[FuelType] = None
    current_odometer: Optional[int] = Field(default=None, ge=0)


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
    avg_daily_km: float
    created_at: dt.datetime


# ---------------------------------------------------------------------------
# Log entry details
# ---------------------------------------------------------------------------


class RefuelDetailsIn(BaseModel):
    liters: float = Field(gt=0)
    price_per_liter: float = Field(ge=0)
    is_full_tank: bool
    gas_station: Optional[str] = Field(default=None, max_length=200)


class RefuelDetailsUpdate(BaseModel):
    liters: Optional[float] = Field(default=None, gt=0)
    price_per_liter: Optional[float] = Field(default=None, ge=0)
    is_full_tank: Optional[bool] = None
    gas_station: Optional[str] = Field(default=None, max_length=200)


class RefuelDetailsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    liters: float
    price_per_liter: float
    is_full_tank: bool
    gas_station: Optional[str]


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


# ---------------------------------------------------------------------------
# Log entries
# ---------------------------------------------------------------------------


class LogEntryCreate(BaseModel):
    type: LogType
    odometer: int = Field(ge=0)
    date: dt.date
    total_cost: float = Field(ge=0)
    notes: Optional[str] = None
    refuel: Optional[RefuelDetailsIn] = None
    maintenance: Optional[MaintenanceDetailsIn] = None
    repair: Optional[RepairDetailsIn] = None

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
    created_at: dt.datetime


class LogListOut(BaseModel):
    items: list[LogEntryOut]
    total: int


# ---------------------------------------------------------------------------
# Service intervals
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


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


class FuelStatsOut(BaseModel):
    avg_consumption_l_100km: Optional[float]
    last_consumption_l_100km: Optional[float]
    avg_cost_per_km: Optional[float]
    history: list[FuelHistoryItem]


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


class AnalyticsOut(BaseModel):
    totals: Totals
    monthly: list[MonthlyBucket]
    fuel: FuelStatsOut
    forecast: Forecast


# ---------------------------------------------------------------------------
# Receipt OCR
# ---------------------------------------------------------------------------


class OcrScanResult(BaseModel):
    liters: Optional[float]
    price_per_liter: Optional[float]
    total_cost: Optional[float]
    date: Optional[dt.date]
    gas_station: Optional[str]
    raw_text: str


# ---------------------------------------------------------------------------
# Telegram linking
# ---------------------------------------------------------------------------


class TelegramLinkCodeResponse(BaseModel):
    code: str
    deep_link: Optional[str]
    expires_in_minutes: int


class TelegramStatus(BaseModel):
    linked: bool
