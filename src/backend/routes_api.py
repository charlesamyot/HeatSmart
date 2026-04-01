"""JSON REST API routes."""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import stat
import time
from datetime import date, datetime, time as dt_time, timedelta, timezone
from time import monotonic
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .database import get_session
from .models import (
    ComfortPreferences, DailyEnergySummary, EnergyUsage, HeaterReading,
    HeatingCycle, ScheduleEntry, TOURateEntry, WaterUsage,
)
from .schemas import (
    ComfortPreferencesIn, ComfortPreferencesOut, ConfigStatus, CopyScheduleRequest,
    CredentialsIn, DailyEnergyOut, EnergyResponse, HeaterStatus, HeatingCycleOut,
    HourlyEnergy, ModeRequest, OptimizedSchedule, ScheduleEntryIn, ScheduleEntryOut,
    ScheduleUpdate, SetpointRequest, TOURateIn, TOURateOut,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

_client = None
_poller = None


def set_client(client, poller) -> None:
    global _client, _poller
    _client, _poller = client, poller


def _get_client():
    if _client is None:
        raise HTTPException(503, "EcoNet client not initialized")
    return _client


def _first_device():
    client = _get_client()
    eq = client.state.equipment
    if not eq:
        raise HTTPException(404, "No water heater found. Check credentials in settings.")
    return eq[0]


# ---------------------------------------------------------------------------
# Status & Device
# ---------------------------------------------------------------------------

@router.get("/status", response_model=HeaterStatus)
async def get_status():
    device = _first_device()
    return HeaterStatus(
        setpoint=device.setpoint,
        current_temp=device.current_temp,
        hot_water_avail=device.hot_water_avail,
        mode=device.mode,
        running=device.running,
        running_state=device.running_state,
        wifi_signal=device.wifi_signal,
        last_updated=datetime.now(timezone.utc),
        connected=device.connected,
    )


@router.get("/device")
async def get_device_info():
    client = _get_client()
    d = _first_device()
    loc = d.location
    settings = get_settings()
    return {
        "device_id": d.device_id, "device_name": d.device_name, "name": d.name,
        "mac_address": d.mac_address, "device_type": d.device_type,
        "equipment_type": d.equipment_type,
        "setpoint": d.setpoint, "setpoint_range": [d.set_point_min, d.set_point_max],
        "mode": d.mode, "modes": d.modes,
        "running": d.running, "running_state": d.running_state,
        "hot_water_avail": d.hot_water_avail, "connected": d.connected,
        "compressor_health": d.compressor_health, "compressor_status": d.compressor_status,
        "tank_health": d.tank_health, "tank_status": d.tank_status,
        "location": {"city": loc.city, "state": loc.state, "street": loc.street,
                      "zipcode": loc.zipcode} if loc else None,
        "firmware": "RH-WIFI-0500-15", "wifi_signal": d.wifi_signal,
        "mqtt_connected": client.state.mqtt_connected,
        "econet_email": settings.econet_email,
        "poll_interval_sec": settings.state_poll_interval,
    }


@router.get("/backfill-status")
async def get_backfill_status():
    if _poller:
        return _poller.backfill_status
    return {"running": False}


@router.post("/refresh")
async def force_refresh():
    client = _get_client()
    equipment = await client.get_equipment()
    if not equipment:
        return {"status": "ok", "equipment": 0}
    d = equipment[0]
    # Trigger energy poll to DB
    energy_hours = 0
    if _poller:
        try:
            await _poller._poll_energy()
            energy_hours = 24
        except Exception as exc:
            logger.warning("Energy poll during refresh failed: %s", exc)
    return {"status": "ok", "setpoint": d.setpoint, "mode": d.mode,
            "running": d.running, "connected": d.connected,
            "energy_hours": energy_hours}


# ---------------------------------------------------------------------------
# Energy & Cycles
# ---------------------------------------------------------------------------

@router.get("/energy", response_model=EnergyResponse)
async def get_energy(
    range: Annotated[Literal["day", "yesterday", "week", "month", "quarter", "year"], Query()] = "day",
    session: AsyncSession = Depends(get_session),
):
    start, end = _date_range(range)
    result = await session.execute(
        select(EnergyUsage)
        .where(EnergyUsage.date >= start, EnergyUsage.date <= end)
        .order_by(EnergyUsage.date, EnergyUsage.hour)
    )
    rows = result.scalars().all()
    hourly = [HourlyEnergy(hour=r.hour, kwh=r.kwh, cost=r.cost, tou_tier=r.tou_tier) for r in rows]

    daily_result = await session.execute(
        select(DailyEnergySummary)
        .where(DailyEnergySummary.date >= start, DailyEnergySummary.date <= end)
        .order_by(DailyEnergySummary.date)
    )
    daily = [DailyEnergyOut(
        date=r.date, total_kwh=r.total_kwh, total_cost=r.total_cost,
        peak_kwh=r.peak_kwh, mid_peak_kwh=r.mid_peak_kwh, off_peak_kwh=r.off_peak_kwh,
        peak_cost=r.peak_cost, mid_peak_cost=r.mid_peak_cost, off_peak_cost=r.off_peak_cost,
    ) for r in daily_result.scalars().all()]

    return EnergyResponse(range=range, hourly=hourly, daily=daily,
                          total_kwh=sum(r.kwh for r in rows),
                          total_cost=sum(r.cost or 0.0 for r in rows))


@router.get("/cycles", response_model=list[HeatingCycleOut])
async def get_cycles(
    range: Annotated[Literal["day", "yesterday", "week", "month", "quarter", "year"], Query()] = "day",
    session: AsyncSession = Depends(get_session),
):
    start, _ = _date_range(range)
    result = await session.execute(
        select(HeatingCycle)
        .where(HeatingCycle.start_time >= datetime.combine(start, datetime.min.time()))
        .order_by(HeatingCycle.start_time.desc()).limit(200)
    )
    return [HeatingCycleOut(id=r.id, start_time=r.start_time, end_time=r.end_time,
                            duration_seconds=r.duration_seconds, mode=r.mode,
                            setpoint_at_start=r.setpoint_at_start)
            for r in result.scalars().all()]


# ---------------------------------------------------------------------------
# Control
# ---------------------------------------------------------------------------

@router.post("/setpoint")
async def set_setpoint(req: SetpointRequest):
    settings = get_settings()
    temp = max(settings.min_setpoint, min(settings.max_setpoint, req.temperature))
    device = _first_device()
    logger.info("Setpoint change: %.1f°F (device: %s)", temp, device.device_id)
    success = await _get_client().set_setpoint(device.device_id, temp)
    if not success:
        raise HTTPException(500, "Failed to update setpoint.")
    logger.info("Setpoint set to %.1f°F", temp)
    return {"status": "ok", "setpoint": temp}


@router.post("/mode")
async def set_mode(req: ModeRequest):
    device = _first_device()
    logger.info("Mode change: %s (device: %s)", req.mode, device.device_id)
    success = await _get_client().set_mode(device.device_id, req.mode)
    if not success:
        raise HTTPException(500, "Failed to update mode.")
    logger.info("Mode set to %s", req.mode)
    return {"status": "ok", "mode": req.mode}


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

@router.get("/schedule", response_model=list[ScheduleEntryOut])
async def get_schedule(
    day: int = Query(default=None, ge=0, le=7),
    session: AsyncSession = Depends(get_session),
):
    query = select(ScheduleEntry).where(
        ScheduleEntry.is_active == True  # noqa: E712
    ).order_by(ScheduleEntry.day_of_week, ScheduleEntry.time_of_day)
    if day is not None:
        query = query.where(ScheduleEntry.day_of_week == day)
    result = await session.execute(query)
    return [ScheduleEntryOut(
        id=r.id, day_of_week=r.day_of_week, time_of_day=r.time_of_day,
        setpoint=r.setpoint, mode=r.mode, is_active=r.is_active,
        source=r.source, created_at=r.created_at,
    ) for r in result.scalars().all()]


@router.put("/schedule")
async def update_schedule(body: ScheduleUpdate, session: AsyncSession = Depends(get_session)):
    dow = body.day_of_week
    result = await session.execute(
        select(ScheduleEntry).where(ScheduleEntry.is_active == True, ScheduleEntry.day_of_week == dow)
    )
    for row in result.scalars().all():
        row.is_active = False
    for entry in body.entries:
        session.add(ScheduleEntry(
            day_of_week=dow, time_of_day=entry.time_of_day,
            setpoint=max(110.0, min(140.0, entry.setpoint)),
            mode=entry.mode, is_active=True, source="manual",
        ))
    await session.commit()
    return {"status": "ok", "day": dow}


@router.post("/schedule/copy")
async def copy_schedule(body: CopyScheduleRequest, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(ScheduleEntry).where(
            ScheduleEntry.is_active == True, ScheduleEntry.day_of_week == body.from_day
        ).order_by(ScheduleEntry.time_of_day)
    )
    source = result.scalars().all()
    if not source:
        raise HTTPException(404, "No schedule entries for source day.")
    for target in body.to_days:
        if target == body.from_day:
            continue
        existing = await session.execute(
            select(ScheduleEntry).where(ScheduleEntry.is_active == True, ScheduleEntry.day_of_week == target)
        )
        for row in existing.scalars().all():
            row.is_active = False
        for src in source:
            session.add(ScheduleEntry(
                day_of_week=target, time_of_day=src.time_of_day,
                setpoint=src.setpoint, mode=src.mode, is_active=True, source=src.source,
            ))
    await session.commit()
    return {"status": "ok", "copied_to": body.to_days}


@router.post("/schedule/optimize", response_model=OptimizedSchedule)
async def optimize_schedule(session: AsyncSession = Depends(get_session)):
    from .optimizer import ScheduleOptimizer

    prefs_result = await session.execute(select(ComfortPreferences).limit(1))
    prefs = prefs_result.scalar_one_or_none()

    thirty_days_ago = date.today() - timedelta(days=30)
    wu_result = await session.execute(select(WaterUsage).where(WaterUsage.date >= thirty_days_ago))
    usage_by_hour = {}
    for row in wu_result.scalars().all():
        usage_by_hour.setdefault(row.hour, []).append(row.gallons)
    avg_usage = {h: sum(v) / len(v) for h, v in usage_by_hour.items()}

    optimizer = ScheduleOptimizer(
        preferred_setpoint=prefs.preferred_setpoint if prefs else 120.0,
        min_acceptable_temp=prefs.min_acceptable_temp if prefs else 110.0,
        max_recovery_minutes=prefs.max_recovery_minutes if prefs else 60,
    )
    result = optimizer.optimize(avg_usage, date.today())
    return OptimizedSchedule(
        suggested_entries=[
            ScheduleEntryIn(time_of_day=dt_time(hour=s.hour, minute=s.minute), setpoint=s.setpoint, mode=s.mode)
            for s in result.schedule
        ],
        estimated_daily_cost=result.estimated_daily_cost,
        current_daily_cost=result.current_daily_cost,
        savings_pct=result.savings_pct,
        savings_monthly_low=result.savings_monthly_low,
        savings_monthly_high=result.savings_monthly_high,
        savings_yearly_low=result.savings_yearly_low,
        savings_yearly_high=result.savings_yearly_high,
        explanation=result.explanation,
    )


@router.post("/schedule/apply")
async def apply_optimized_schedule(body: ScheduleUpdate, session: AsyncSession = Depends(get_session)):
    dow = body.day_of_week
    result = await session.execute(
        select(ScheduleEntry).where(ScheduleEntry.is_active == True, ScheduleEntry.day_of_week == dow)
    )
    for row in result.scalars().all():
        row.is_active = False
    for entry in body.entries:
        session.add(ScheduleEntry(
            day_of_week=dow, time_of_day=entry.time_of_day,
            setpoint=max(110.0, min(140.0, entry.setpoint)),
            mode=entry.mode, is_active=True, source="optimizer",
        ))
    await session.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@router.get("/config/tou-rates", response_model=list[TOURateOut])
async def get_tou_rates(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(TOURateEntry))
    return [TOURateOut(id=r.id, name=r.name, start_hour=r.start_hour, end_hour=r.end_hour,
                       rate_per_kwh=r.rate_per_kwh, days_of_week=r.days_of_week,
                       holiday_exception=r.holiday_exception)
            for r in result.scalars().all()]


@router.put("/config/tou-rates", response_model=list[TOURateOut])
async def update_tou_rates(rates: list[TOURateIn], session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(TOURateEntry))
    for row in result.scalars().all():
        await session.delete(row)
    new_rows = []
    for rate in rates:
        row = TOURateEntry(name=rate.name, start_hour=rate.start_hour, end_hour=rate.end_hour,
                           rate_per_kwh=rate.rate_per_kwh, days_of_week=rate.days_of_week,
                           holiday_exception=rate.holiday_exception)
        session.add(row)
        new_rows.append(row)
    await session.commit()
    for row in new_rows:
        await session.refresh(row)
    return [TOURateOut(id=r.id, name=r.name, start_hour=r.start_hour, end_hour=r.end_hour,
                       rate_per_kwh=r.rate_per_kwh, days_of_week=r.days_of_week,
                       holiday_exception=r.holiday_exception)
            for r in new_rows]


@router.get("/config/preferences", response_model=ComfortPreferencesOut)
async def get_preferences(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(ComfortPreferences).limit(1))
    prefs = result.scalar_one_or_none()
    return ComfortPreferencesOut(
        min_acceptable_temp=prefs.min_acceptable_temp if prefs else 110.0,
        max_recovery_minutes=prefs.max_recovery_minutes if prefs else 60,
        preferred_setpoint=prefs.preferred_setpoint if prefs else 120.0,
        away_setpoint=prefs.away_setpoint if prefs else None,
    )


@router.put("/config/preferences", response_model=ComfortPreferencesOut)
async def update_preferences(body: ComfortPreferencesIn, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(ComfortPreferences).limit(1))
    prefs = result.scalar_one_or_none()
    if not prefs:
        prefs = ComfortPreferences(id=1)
        session.add(prefs)
    prefs.min_acceptable_temp = body.min_acceptable_temp
    prefs.max_recovery_minutes = body.max_recovery_minutes
    prefs.preferred_setpoint = body.preferred_setpoint
    prefs.away_setpoint = body.away_setpoint
    await session.commit()
    return ComfortPreferencesOut(
        min_acceptable_temp=prefs.min_acceptable_temp,
        max_recovery_minutes=prefs.max_recovery_minutes,
        preferred_setpoint=prefs.preferred_setpoint,
        away_setpoint=prefs.away_setpoint,
    )


@router.post("/config/credentials")
async def update_credentials(body: CredentialsIn):
    client = _get_client()
    client._email = body.email
    client._password = body.password
    success = await client.login()
    if not success:
        logger.error("EcoNet credential update failed: %s", client.state.last_error)
        raise HTTPException(401, "Authentication failed. Please check your credentials.")
    env_path = "config/.env"
    try:
        lines = []
        if os.path.exists(env_path):
            with open(env_path) as f:
                lines = [l for l in f.readlines()
                         if not l.startswith("ECONET_EMAIL=") and not l.startswith("ECONET_PASSWORD=")]
        lines.append(f"ECONET_EMAIL={body.email}\n")
        lines.append(f"ECONET_PASSWORD={body.password}\n")
        with open(env_path, "w") as f:
            f.writelines(lines)
        os.chmod(env_path, stat.S_IRUSR | stat.S_IWUSR)
    except Exception as exc:
        logger.warning("Could not persist credentials to .env: %s", exc)
    await client.get_equipment()
    return {"status": "ok", "connected": True}


@router.get("/config/status", response_model=ConfigStatus)
async def get_config_status():
    client = _get_client()
    last_poll = None
    if client.state.last_poll:
        elapsed = monotonic() - client.state.last_poll
        last_poll = datetime.now(timezone.utc) - timedelta(seconds=elapsed)
    return ConfigStatus(
        connected=client.state.authenticated,
        last_poll=last_poll,
        last_error=client.state.last_error,
        mqtt_connected=client.state.mqtt_connected,
        db_path="configured",
    )


# ---------------------------------------------------------------------------
# Data Export
# ---------------------------------------------------------------------------

@router.get("/export")
async def export_data(
    granularity: Annotated[Literal["hourly", "daily"], Query()] = "daily",
    start: str = Query(...), end: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    try:
        start_date, end_date = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD.")
    if (end_date - start_date).days > 730:
        raise HTTPException(400, "Max 2 years.")
    output = io.StringIO()
    writer = csv.writer(output)
    if granularity == "hourly":
        writer.writerow(["date", "hour", "kwh", "cost", "tou_tier", "tou_rate"])
        for row in (await session.execute(
            select(EnergyUsage).where(EnergyUsage.date >= start_date, EnergyUsage.date <= end_date)
            .order_by(EnergyUsage.date, EnergyUsage.hour)
        )).scalars().all():
            writer.writerow([row.date.isoformat(), row.hour, round(row.kwh, 6),
                             round(row.cost, 6) if row.cost else "", row.tou_tier or "",
                             round(row.tou_rate, 4) if row.tou_rate else ""])
    else:
        writer.writerow(["date", "total_kwh", "total_cost", "peak_kwh", "mid_peak_kwh",
                          "off_peak_kwh", "peak_cost", "mid_peak_cost", "off_peak_cost"])
        for row in (await session.execute(
            select(DailyEnergySummary).where(DailyEnergySummary.date >= start_date, DailyEnergySummary.date <= end_date)
            .order_by(DailyEnergySummary.date)
        )).scalars().all():
            writer.writerow([row.date.isoformat(), round(row.total_kwh, 6), round(row.total_cost, 4),
                             round(row.peak_kwh, 6), round(row.mid_peak_kwh, 6), round(row.off_peak_kwh, 6),
                             round(row.peak_cost, 4), round(row.mid_peak_cost, 4), round(row.off_peak_cost, 4)])
    output.seek(0)
    return StreamingResponse(output, media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=econet_{granularity}_{start}_to_{end}.csv"})


# ---------------------------------------------------------------------------
# Debug (consolidated — single endpoint)
# ---------------------------------------------------------------------------

@router.get("/debug/{action}")
async def debug_action(action: str):
    """Consolidated debug endpoint. Actions: mqtt-status, mqtt-messages, equipment, raw."""
    client = _get_client()
    if action == "mqtt-status":
        mc = client._mqtt_client
        return {
            "authenticated": client.state.authenticated,
            "account_id": client.state.account_id,
            "cb_user_id": client.state.cb_user_id,
            "mqtt_connected": client.state.mqtt_connected,
            "mqtt_client_exists": mc is not None,
            "mqtt_is_connected": mc.is_connected() if mc else False,
            "mqtt_message_count": client.state.mqtt_message_count,
            "equipment_count": len(client.state.equipment),
        }
    elif action == "mqtt-messages":
        msgs = client.get_recent_messages()
        return {"total": client.state.mqtt_message_count, "buffered": len(msgs), "messages": msgs}
    elif action == "equipment":
        equipment = await client.get_equipment()
        return {"count": len(equipment), "devices": [
            {"id": e.device_id, "name": e.name, "device_name": e.device_name,
             "mode": e.mode, "setpoint": e.setpoint, "running": e.running,
             "connected": e.connected, "hot_water": e.hot_water_avail}
            for e in equipment
        ]}
    elif action == "energy-test":
        eq = client.state.equipment
        if not eq:
            return {"error": "No equipment"}
        d = eq[0]
        today = date.today().isoformat()
        usage = await client.get_energy_usage(d.device_name, d.device_id, today, today)
        return {"device_name": d.device_name, "date": today, "hours": len(usage), "usage": usage}
    elif action == "energy-range":
        # Test multi-day range to see response format
        eq = client.state.equipment
        if not eq:
            return {"error": "No equipment"}
        d = eq[0]
        end = date.today().isoformat()
        start = (date.today() - timedelta(days=6)).isoformat()
        usage = await client.get_energy_usage(d.device_name, d.device_id, start, end)
        return {"start": start, "end": end, "entries": len(usage), "usage": usage}
    elif action == "raw":
        import httpx
        await client._ensure_authenticated()
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.post(
                "https://rheem.clearblade.com/api/v/1/code/e2e699cb0bb0bbb88fc8858cb5a401/getUserDataForApp",
                headers=client._cb_headers(authed=True), json={"resource": "friedrich"},
            )
            return resp.json()
    else:
        return {"error": f"Unknown debug action: {action}. Use: mqtt-status, mqtt-messages, equipment, raw"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _date_range(range_str: str):
    today = date.today()
    if range_str == "yesterday":
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday
    if range_str == "week":
        return today - timedelta(days=6), today
    if range_str == "month":
        return today - timedelta(days=29), today
    if range_str == "quarter":
        return today - timedelta(days=89), today
    if range_str == "year":
        return today - timedelta(days=364), today
    return today, today
