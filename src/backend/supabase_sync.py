"""Supabase sync — pushes local history data to Supabase for cloud backup and cross-device access.

Syncs: energy_usage, daily_energy_summary, heater_readings (recent).
Uses Supabase PostgREST API directly (no SDK dependency).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .models import DailyEnergySummary, EnergyUsage, HeaterReading

logger = logging.getLogger(__name__)


class SupabaseSync:
    """Pushes local SQLite data to Supabase PostgREST tables."""

    def __init__(self, user_id: str):
        self.settings = get_settings()
        self.user_id = user_id
        self.base_url = self.settings.supabase_url
        self.api_key = self.settings.supabase_key

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.api_key and self.user_id)

    def _headers(self, token: Optional[str] = None) -> dict:
        h = {
            "apikey": self.api_key,
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        }
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    async def sync_daily_summaries(self, session: AsyncSession, token: str,
                                   days_back: int = 90) -> dict:
        """Sync daily energy summaries to Supabase."""
        if not self.enabled:
            return {"synced": 0, "error": "Supabase not configured"}

        cutoff = datetime.utcnow().date() - timedelta(days=days_back)
        stmt = select(DailyEnergySummary).where(DailyEnergySummary.date >= cutoff)
        result = await session.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            return {"synced": 0}

        records = [
            {
                "user_id": self.user_id,
                "date": str(r.date),
                "total_kwh": r.total_kwh,
                "total_cost": r.total_cost,
                "peak_kwh": r.peak_kwh,
                "mid_peak_kwh": r.mid_peak_kwh,
                "off_peak_kwh": r.off_peak_kwh,
                "peak_cost": r.peak_cost,
                "mid_peak_cost": r.mid_peak_cost,
                "off_peak_cost": r.off_peak_cost,
            }
            for r in rows
        ]

        return await self._upsert("daily_energy_summary", records, token)

    async def sync_energy_usage(self, session: AsyncSession, token: str,
                                days_back: int = 30) -> dict:
        """Sync hourly energy usage to Supabase."""
        if not self.enabled:
            return {"synced": 0, "error": "Supabase not configured"}

        cutoff = datetime.utcnow().date() - timedelta(days=days_back)
        stmt = select(EnergyUsage).where(EnergyUsage.date >= cutoff)
        result = await session.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            return {"synced": 0}

        records = [
            {
                "user_id": self.user_id,
                "date": str(r.date),
                "hour": r.hour,
                "kwh": r.kwh,
                "cost": r.cost,
                "tou_rate": r.tou_rate,
                "tou_tier": r.tou_tier,
            }
            for r in rows
        ]

        return await self._upsert("energy_usage", records, token)

    async def sync_readings(self, session: AsyncSession, token: str,
                            days_back: int = 7) -> dict:
        """Sync recent heater readings to Supabase."""
        if not self.enabled:
            return {"synced": 0, "error": "Supabase not configured"}

        cutoff = datetime.utcnow() - timedelta(days=days_back)
        stmt = select(HeaterReading).where(HeaterReading.timestamp >= cutoff)
        result = await session.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            return {"synced": 0}

        records = [
            {
                "user_id": self.user_id,
                "timestamp": r.timestamp.isoformat(),
                "device_id": r.device_id,
                "setpoint": r.setpoint,
                "current_temp": r.current_temp,
                "hot_water_avail": r.hot_water_avail,
                "mode": r.mode,
                "running": r.running,
                "running_state": r.running_state,
            }
            for r in rows
        ]

        return await self._upsert("heater_readings", records, token)

    async def _upsert(self, table: str, records: list[dict], token: str) -> dict:
        """POST records to Supabase PostgREST with upsert."""
        url = f"{self.base_url}/rest/v1/{table}"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    url,
                    json=records,
                    headers=self._headers(token),
                )
                if resp.status_code in (200, 201):
                    return {"synced": len(records)}
                else:
                    logger.warning("Supabase upsert %s failed: %s %s",
                                   table, resp.status_code, resp.text[:200])
                    return {"synced": 0, "error": f"HTTP {resp.status_code}"}
        except httpx.HTTPError as e:
            logger.error("Supabase sync error for %s: %s", table, e)
            return {"synced": 0, "error": str(e)}

    async def sync_all(self, session: AsyncSession, token: str) -> dict:
        """Run all sync operations and return combined results."""
        results = {}
        results["daily_summaries"] = await self.sync_daily_summaries(session, token)
        results["energy_usage"] = await self.sync_energy_usage(session, token)
        results["readings"] = await self.sync_readings(session, token)

        total = sum(r.get("synced", 0) for r in results.values())
        errors = [f"{k}: {r['error']}" for k, r in results.items() if "error" in r]

        return {
            "total_synced": total,
            "details": results,
            "errors": errors if errors else None,
        }
