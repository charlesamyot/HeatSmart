"""
Background data collection using APScheduler.

Tasks:
- State poll every 5 minutes → HeaterReading rows
- Daily rollup at midnight → DailyEnergySummary rows
- MQTT real-time updates as primary; REST poll as fallback

NOTE: Energy/water usage APIs (dynamicAction) are not available on Gen5 firmware.
Energy tracking is derived from heater state snapshots (running state × time = kWh estimate).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .config import get_settings, load_tou_rates
from .econet_client import EcoNetClient, WaterHeaterState
from .models import DailyEnergySummary, EnergyUsage, HeaterReading, WaterUsage

logger = logging.getLogger(__name__)


class Poller:
    def __init__(self, client: EcoNetClient, session_factory: async_sessionmaker) -> None:
        self._client = client
        self._session_factory = session_factory
        self._scheduler = AsyncIOScheduler()
        self._settings = get_settings()
        self._tou_rates = load_tou_rates()
        # Backfill progress tracking
        self.backfill_status = {"running": False, "total": 0, "done": 0, "current_date": "", "errors": 0}

    def start(self) -> None:
        interval_sec = self._settings.state_poll_interval

        energy_sec = self._settings.energy_poll_interval

        self._scheduler.add_job(self._poll_state, "interval", seconds=interval_sec, id="state_poll")
        self._scheduler.add_job(self._poll_energy, "interval", seconds=energy_sec, id="energy_poll")
        self._scheduler.add_job(self._daily_rollup, "cron", hour=0, minute=1, id="daily_rollup")
        self._scheduler.start()

        # Register MQTT callback for real-time state updates
        self._client.subscribe_state(self._on_mqtt_state)
        self._client.start_mqtt()

        # Backfill historical energy data on startup
        import asyncio
        asyncio.ensure_future(self._backfill_energy())

        logger.info("Poller started (state poll every %ds, energy every %ds)", interval_sec, energy_sec)

    def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        self._client.stop_mqtt()
        logger.info("Poller stopped")

    # ------------------------------------------------------------------
    # MQTT real-time callback
    # ------------------------------------------------------------------

    def _on_mqtt_state(self, device: WaterHeaterState) -> None:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(self._record_state(device))
            )
        except Exception as exc:
            logger.warning("MQTT→async bridge error: %s", exc)

    # ------------------------------------------------------------------
    # Scheduled jobs
    # ------------------------------------------------------------------

    async def _backfill_energy(self) -> None:
        """Fetch historical energy data in monthly chunks (newest first).

        Phase 1: Fetch today's hourly data immediately.
        Phase 2: Fetch monthly chunks going backward for daily summaries.
        Phase 3: Fetch hourly detail for recent 7 days.
        """
        from datetime import timedelta
        import calendar
        equipment = self._client.state.equipment
        if not equipment:
            logger.info("Backfill skipped — no equipment yet")
            return

        device = equipment[0]
        total_months = 12
        self.backfill_status = {"running": True, "total": total_months + 30,
                                "done": 0, "current_date": "", "errors": 0}

        # Phase 1: Today's hourly data (immediate)
        logger.info("Backfill phase 1: fetching today's hourly data...")
        self.backfill_status["current_date"] = "today (hourly)"
        today = date.today()
        await self._fetch_and_store_hourly(device, today)
        yesterday = today - timedelta(days=1)
        await self._fetch_and_store_hourly(device, yesterday)
        self.backfill_status["done"] = 1

        # Phase 2: Monthly chunks going backward
        logger.info("Backfill phase 2: fetching monthly summaries...")
        for months_ago in range(0, total_months):
            # Calculate month start/end
            target_month = today.month - months_ago
            target_year = today.year
            while target_month <= 0:
                target_month += 12
                target_year -= 1
            last_day = calendar.monthrange(target_year, target_month)[1]
            month_start = date(target_year, target_month, 1)
            month_end = date(target_year, target_month, last_day)
            if month_end > today:
                month_end = today

            self.backfill_status["done"] = months_ago + 1
            self.backfill_status["current_date"] = f"{target_year}-{target_month:02d}"

            try:
                # Multi-day range returns daily totals (name = day of month)
                usage = await self._client.get_energy_usage(
                    device.device_name, device.device_id,
                    month_start.isoformat(), month_end.isoformat())
                if not usage:
                    continue

                async with self._session_factory() as session:
                    for day_str, kwh in usage.items():
                        day_num = int(day_str)
                        if day_num < 1 or day_num > last_day:
                            continue
                        target_date = date(target_year, target_month, day_num)
                        # Store as daily summary (hour=99 sentinel for daily total)
                        # We'll use the daily summary table directly
                        avg_rate = 0.12  # rough average for daily totals
                        stmt = (
                            sqlite_insert(DailyEnergySummary)
                            .values(date=target_date, total_kwh=kwh,
                                    total_cost=round(kwh * avg_rate, 4),
                                    peak_kwh=0, mid_peak_kwh=0, off_peak_kwh=kwh,
                                    peak_cost=0, mid_peak_cost=0, off_peak_cost=round(kwh * avg_rate, 4))
                            .on_conflict_do_update(
                                index_elements=["date"],
                                set_={"total_kwh": kwh, "total_cost": round(kwh * avg_rate, 4),
                                       "off_peak_kwh": kwh, "off_peak_cost": round(kwh * avg_rate, 4)},
                            )
                        )
                        await session.execute(stmt)
                    await session.commit()
                logger.info("Backfill month %s: %d days", f"{target_year}-{target_month:02d}", len(usage))
            except Exception as exc:
                self.backfill_status["errors"] += 1
                logger.warning("Backfill month %s failed: %s", f"{target_year}-{target_month:02d}", exc)

        # Phase 3: Hourly detail for recent 30 days (for TOU breakdown)
        logger.info("Backfill phase 3: fetching hourly detail for recent 30 days...")
        self.backfill_status["current_date"] = "hourly detail"
        for days_ago in range(2, 31):  # Days 2-30 (0-1 done in phase 1)
            target = today - timedelta(days=days_ago)
            self.backfill_status["done"] = total_months + days_ago
            self.backfill_status["current_date"] = f"hourly {target.isoformat()}"
            await self._fetch_and_store_hourly(device, target)
        self.backfill_status["done"] = total_months + 30

        self.backfill_status["running"] = False
        logger.info("Energy backfill complete")

    async def _fetch_and_store_hourly(self, device, target_date: date) -> None:
        """Fetch and store hourly energy data for a single day."""
        try:
            usage = await self._client.get_energy_usage(
                device.device_name, device.device_id,
                target_date.isoformat(), target_date.isoformat())
            if not usage:
                return
            async with self._session_factory() as session:
                for hour_str, kwh in usage.items():
                    hour = int(hour_str)
                    if hour < 0 or hour > 23:
                        continue
                    tier, rate = _get_tou_tier(target_date, hour, self._tou_rates)
                    cost = round(kwh * rate, 6)
                    stmt = (
                        sqlite_insert(EnergyUsage)
                        .values(date=target_date, hour=hour, kwh=kwh,
                                cost=cost, tou_rate=rate, tou_tier=tier)
                        .on_conflict_do_update(
                            index_elements=["date", "hour"],
                            set_={"kwh": kwh, "cost": cost, "tou_rate": rate, "tou_tier": tier},
                        )
                    )
                    await session.execute(stmt)
                await self._build_summary(session, target_date)
                await session.commit()
        except Exception as exc:
            logger.warning("Hourly fetch failed for %s: %s", target_date, exc)

    async def _poll_state(self) -> None:
        equipment = await self._client.get_equipment()
        for device in equipment:
            await self._record_state(device)

    async def _poll_energy(self) -> None:
        """Fetch energy usage for today and yesterday, converting from device TZ to local TZ."""
        from datetime import timedelta
        equipment = self._client.state.equipment
        today = date.today()
        yesterday = today - timedelta(days=1)

        async with self._session_factory() as session:
            for device in equipment:
                for target_date in [yesterday, today]:
                    target_str = target_date.isoformat()
                    usage = await self._client.get_energy_usage(
                        device.device_name, device.device_id, target_str, target_str)
                    for hour_str, kwh in usage.items():
                        local_hour = int(hour_str)
                        local_date = target_date
                        tier, rate = _get_tou_tier(local_date, local_hour, self._tou_rates)
                        cost = round(kwh * rate, 6)
                        stmt = (
                            sqlite_insert(EnergyUsage)
                            .values(date=local_date, hour=local_hour, kwh=kwh,
                                    cost=cost, tou_rate=rate, tou_tier=tier)
                            .on_conflict_do_update(
                                index_elements=["date", "hour"],
                                set_={"kwh": kwh, "cost": cost, "tou_rate": rate, "tou_tier": tier},
                            )
                        )
                        await session.execute(stmt)

                # Water usage for today
                water_total = await self._client.get_water_usage(
                    device.device_name, device.device_id, today.isoformat(), today.isoformat())
                if water_total > 0:
                    stmt = (
                        sqlite_insert(WaterUsage)
                        .values(date=today, hour=0, gallons=water_total)
                        .on_conflict_do_update(
                            index_elements=["date", "hour"],
                            set_={"gallons": water_total},
                        )
                    )
                    await session.execute(stmt)

            # Build summaries for both days
            await self._build_summary(session, yesterday)
            await self._build_summary(session, today)
            await session.commit()
            if equipment:
                logger.info("Energy poll complete for %s and %s", yesterday, today)

    async def _daily_rollup(self) -> None:
        from datetime import timedelta
        yesterday = date.today() - timedelta(days=1)
        async with self._session_factory() as session:
            await self._build_summary(session, yesterday)
            await session.commit()
        logger.info("Daily rollup complete for %s", yesterday)

    # ------------------------------------------------------------------
    # Core recording
    # ------------------------------------------------------------------

    async def _record_state(self, device: WaterHeaterState) -> None:
        async with self._session_factory() as session:
            reading = HeaterReading(
                timestamp=datetime.now(timezone.utc),
                device_id=device.device_id,
                setpoint=device.setpoint,
                current_temp=device.current_temp,
                hot_water_avail=device.hot_water_avail,
                mode=device.mode,
                running=device.running,
                running_state=device.running_state,
                wifi_signal=device.wifi_signal,
            )
            session.add(reading)
            await session.commit()

    async def _build_summary(self, session: AsyncSession, target_date: date) -> None:
        result = await session.execute(
            select(EnergyUsage).where(EnergyUsage.date == target_date)
        )
        rows = result.scalars().all()
        if not rows:
            return
        totals = {"peak": 0.0, "mid_peak": 0.0, "off_peak": 0.0}
        costs = {"peak": 0.0, "mid_peak": 0.0, "off_peak": 0.0}
        for row in rows:
            tier = row.tou_tier or "off_peak"
            totals[tier] = totals.get(tier, 0.0) + row.kwh
            costs[tier] = costs.get(tier, 0.0) + (row.cost or 0.0)

        summary_data = dict(
            date=target_date, total_kwh=sum(totals.values()), total_cost=sum(costs.values()),
            peak_kwh=totals["peak"], mid_peak_kwh=totals["mid_peak"], off_peak_kwh=totals["off_peak"],
            peak_cost=costs["peak"], mid_peak_cost=costs["mid_peak"], off_peak_cost=costs["off_peak"],
        )
        stmt = sqlite_insert(DailyEnergySummary).values(**summary_data).on_conflict_do_update(
            index_elements=["date"], set_=summary_data
        )
        await session.execute(stmt)


# ---------------------------------------------------------------------------
# TOU tier lookup (also used by optimizer)
# ---------------------------------------------------------------------------

def _convert_tz_hour(api_date: date, api_hour: int, settings) -> tuple:
    """Convert an hour from the device timezone (ET) to local timezone (PT).

    ClearBlade registers the device as America/New_York but the device is in
    America/Los_Angeles. ET is 3 hours ahead of PT.

    Returns (local_date, local_hour).
    """
    from datetime import timedelta

    # Calculate offset: ET is UTC-4 (EDT) or UTC-5 (EST), PT is UTC-7 (PDT) or UTC-8 (PST)
    # Simplified: ET is always 3 hours ahead of PT (both shift for DST together)
    tz_map = {
        ("America/New_York", "America/Los_Angeles"): -3,
        ("America/New_York", "America/Chicago"): -1,
        ("America/New_York", "America/Denver"): -2,
    }
    device_tz = getattr(settings, 'device_timezone', 'America/New_York')
    local_tz = getattr(settings, 'local_timezone', 'America/Los_Angeles')

    offset_hours = tz_map.get((device_tz, local_tz), 0)
    if offset_hours == 0 and device_tz == local_tz:
        return api_date, api_hour

    local_hour = api_hour + offset_hours
    local_date = api_date

    if local_hour < 0:
        local_hour += 24
        local_date = api_date - timedelta(days=1)
    elif local_hour >= 24:
        local_hour -= 24
        local_date = api_date + timedelta(days=1)

    return local_date, local_hour


def _is_holiday(d: date, tou_config: dict) -> bool:
    import calendar
    fixed = {(h["month"], h["day"]) for h in tou_config.get("holidays", [])}
    if (d.month, d.day) in fixed:
        return True

    def nth_weekday(year, month, weekday, n):
        first = date(year, month, 1)
        offset = (weekday - first.weekday()) % 7
        return date(year, month, 1 + offset + (n - 1) * 7)

    def last_weekday(year, month, weekday):
        last_day = calendar.monthrange(year, month)[1]
        last = date(year, month, last_day)
        offset = (last.weekday() - weekday) % 7
        return date(year, month, last_day - offset)

    floating = [
        nth_weekday(d.year, 1, 0, 3), nth_weekday(d.year, 2, 0, 3),
        last_weekday(d.year, 5, 0), nth_weekday(d.year, 9, 0, 1),
        nth_weekday(d.year, 10, 0, 2), nth_weekday(d.year, 11, 3, 4),
    ]
    return d in floating


def _get_tou_tier(d: date, hour: int, tou_config: dict):
    dow = d.weekday()
    holiday = _is_holiday(d, tou_config)
    rates_by_name = {e["name"]: e["rate_per_kwh"] for e in tou_config.get("rates", [])}
    peak_rate = rates_by_name.get("peak", 0.1674)
    mid_rate = rates_by_name.get("mid_peak", 0.1465)
    off_rate = rates_by_name.get("off_peak", 0.0837)

    if 0 <= hour < 6:
        return ("off_peak", off_rate)
    if 17 <= hour < 21 and dow in range(6) and not holiday:
        return ("peak", peak_rate)
    return ("mid_peak", mid_rate)
