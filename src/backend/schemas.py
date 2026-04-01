"""Pydantic request/response schemas for API endpoints."""
from datetime import date, datetime, time
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Status / Readings
# ---------------------------------------------------------------------------

class HeaterStatus(BaseModel):
    setpoint: float
    current_temp: Optional[float]
    hot_water_avail: Optional[float]  # 0-100 %
    mode: str
    running: bool
    running_state: Optional[str]
    wifi_signal: Optional[int]
    last_updated: Optional[datetime]
    connected: bool


class HeaterReadingOut(BaseModel):
    timestamp: datetime
    setpoint: float
    current_temp: Optional[float]
    hot_water_avail: Optional[float]
    mode: str
    running: bool


# ---------------------------------------------------------------------------
# Energy & Cost
# ---------------------------------------------------------------------------

class HourlyEnergy(BaseModel):
    hour: int
    kwh: float
    cost: Optional[float]
    tou_tier: Optional[str]


class DailyEnergyOut(BaseModel):
    date: date
    total_kwh: float
    total_cost: float
    peak_kwh: float
    mid_peak_kwh: float
    off_peak_kwh: float
    peak_cost: float
    mid_peak_cost: float
    off_peak_cost: float


class EnergyResponse(BaseModel):
    range: str
    hourly: List[HourlyEnergy] = []
    daily: List[DailyEnergyOut] = []
    total_kwh: float
    total_cost: float


# ---------------------------------------------------------------------------
# Heating Cycles
# ---------------------------------------------------------------------------

class HeatingCycleOut(BaseModel):
    id: int
    start_time: datetime
    end_time: Optional[datetime]
    duration_seconds: Optional[int]
    mode: str
    setpoint_at_start: float


# ---------------------------------------------------------------------------
# Control
# ---------------------------------------------------------------------------

class SetpointRequest(BaseModel):
    temperature: float = Field(..., ge=110.0, le=140.0, description="Target temperature in F")

    @field_validator("temperature")
    @classmethod
    def round_to_half(cls, v: float) -> float:
        return round(v * 2) / 2  # EcoNet typically accepts 0.5 F increments


class ModeRequest(BaseModel):
    mode: Literal[
        "ENERGY_SAVING", "HEAT_PUMP_ONLY", "ELECTRIC_MODE",
        "HIGH_DEMAND", "OFF", "VACATION", "PERFORMANCE"
    ]


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

class ScheduleEntryIn(BaseModel):
    day_of_week: int = Field(default=7, ge=0, le=7, description="0=Mon..6=Sun, 7=all days")
    time_of_day: time
    setpoint: float = Field(..., ge=110.0, le=140.0)
    mode: Optional[str] = None


class ScheduleEntryOut(BaseModel):
    id: int
    day_of_week: int
    time_of_day: time
    setpoint: float
    mode: Optional[str]
    is_active: bool
    source: str
    created_at: datetime


class ScheduleUpdate(BaseModel):
    day_of_week: int = Field(default=7, ge=0, le=7, description="Which day to update. 7=all.")
    entries: List[ScheduleEntryIn] = Field(..., max_length=4,
                                           description="Up to 4 schedule entries per day")


class CopyScheduleRequest(BaseModel):
    from_day: int = Field(..., ge=0, le=6)
    to_days: List[int] = Field(..., description="List of day_of_week values to copy to")


class OptimizedSchedule(BaseModel):
    suggested_entries: List[ScheduleEntryIn]
    estimated_daily_cost: float
    current_daily_cost: Optional[float]
    savings_pct: Optional[float]
    savings_monthly_low: Optional[float]
    savings_monthly_high: Optional[float]
    savings_yearly_low: Optional[float]
    savings_yearly_high: Optional[float]
    explanation: str


# ---------------------------------------------------------------------------
# TOU Rates
# ---------------------------------------------------------------------------

class TOURateIn(BaseModel):
    name: str
    start_hour: int = Field(..., ge=0, le=23)
    end_hour: int = Field(..., ge=1, le=24)
    rate_per_kwh: float = Field(..., gt=0)
    days_of_week: str  # e.g. "0,1,2,3,4,5"
    holiday_exception: bool = False


class TOURateOut(TOURateIn):
    id: int


# ---------------------------------------------------------------------------
# Comfort Preferences
# ---------------------------------------------------------------------------

class ComfortPreferencesIn(BaseModel):
    min_acceptable_temp: float = Field(..., ge=90.0, le=130.0)
    max_recovery_minutes: int = Field(..., ge=10, le=240)
    preferred_setpoint: float = Field(..., ge=110.0, le=140.0)
    away_setpoint: Optional[float] = Field(default=None, ge=90.0, le=130.0)


class ComfortPreferencesOut(ComfortPreferencesIn):
    pass


# ---------------------------------------------------------------------------
# Credentials & Config Status
# ---------------------------------------------------------------------------

class CredentialsIn(BaseModel):
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class ConfigStatus(BaseModel):
    connected: bool
    last_poll: Optional[datetime]
    last_error: Optional[str]
    mqtt_connected: bool
    db_path: str
