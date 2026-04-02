"""SQLAlchemy ORM models for EcoNet water heater data storage.

Uses Optional[X] instead of X | None for Python 3.9 compatibility —
SQLAlchemy evaluates Mapped annotations at runtime so __future__ annotations
does not help here.
"""
from datetime import date as Date_, datetime, time as Time_
from typing import Optional

from sqlalchemy import (
    Boolean, Date, DateTime, Float, Integer, String, Time,
    UniqueConstraint, func
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class HeaterReading(Base):
    """Raw state snapshot polled every 5 minutes."""
    __tablename__ = "heater_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True,
                                                 server_default=func.now())
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="")
    setpoint: Mapped[float] = mapped_column(Float, nullable=False)
    current_temp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hot_water_avail: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0-100 %
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    running: Mapped[bool] = mapped_column(Boolean, nullable=False)
    running_state: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    wifi_signal: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class EnergyUsage(Base):
    """Hourly energy consumption from EcoNet API."""
    __tablename__ = "energy_usage"
    __table_args__ = (UniqueConstraint("date", "hour", name="uq_energy_date_hour"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[Date_] = mapped_column(Date, nullable=False, index=True)
    hour: Mapped[int] = mapped_column(Integer, nullable=False)   # 0-23
    kwh: Mapped[float] = mapped_column(Float, nullable=False)
    cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tou_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # $/kWh applied
    tou_tier: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # peak/mid_peak/off_peak


class DailyEnergySummary(Base):
    """Aggregated daily totals with TOU breakdown."""
    __tablename__ = "daily_energy_summary"
    __table_args__ = (UniqueConstraint("date", name="uq_summary_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[Date_] = mapped_column(Date, nullable=False, index=True)
    total_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    total_cost: Mapped[float] = mapped_column(Float, nullable=False)
    peak_kwh: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mid_peak_kwh: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    off_peak_kwh: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    peak_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mid_peak_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    off_peak_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class WaterUsage(Base):
    """Hourly water consumption from EcoNet API."""
    __tablename__ = "water_usage"
    __table_args__ = (UniqueConstraint("date", "hour", name="uq_water_date_hour"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[Date_] = mapped_column(Date, nullable=False, index=True)
    hour: Mapped[int] = mapped_column(Integer, nullable=False)
    gallons: Mapped[float] = mapped_column(Float, nullable=False)


class ScheduleEntry(Base):
    """User-defined or optimizer-generated schedule entries, per day-of-week."""
    __tablename__ = "schedule_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0=Mon..6=Sun, 7=all
    time_of_day: Mapped[Time_] = mapped_column(Time, nullable=False)
    setpoint: Mapped[float] = mapped_column(Float, nullable=False)
    mode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")  # manual|optimizer
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class TOURateEntry(Base):
    """Time-of-use electricity rate tiers."""
    __tablename__ = "tou_rate_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False)       # peak, mid_peak, off_peak
    start_hour: Mapped[int] = mapped_column(Integer, nullable=False)    # 0-23
    end_hour: Mapped[int] = mapped_column(Integer, nullable=False)      # 1-24
    rate_per_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    days_of_week: Mapped[str] = mapped_column(String(16), nullable=False)  # comma-separated 0-6 (Mon=0)
    holiday_exception: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ComfortPreferences(Base):
    """Singleton row of user comfort settings."""
    __tablename__ = "comfort_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    min_acceptable_temp: Mapped[float] = mapped_column(Float, nullable=False, default=110.0)
    max_recovery_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    preferred_setpoint: Mapped[float] = mapped_column(Float, nullable=False, default=120.0)
    away_setpoint: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


    # UsagePattern model removed — energy data not available via REST on Gen5 firmware.
    # Usage patterns will be derived from HeaterReading state snapshots when needed.


class Device(Base):
    """Registered device (water heater, EV charger, etc.) for multi-device support."""
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID as string
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # econet, smartthings, manual
    device_type: Mapped[str] = mapped_column(String(32), nullable=False, default="water_heater")
    external_device_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
