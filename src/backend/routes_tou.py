"""Time-of-Use rate lookup routes — queries Supabase PostgREST API."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query

from .config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tou", tags=["tou"])


def _supabase_headers() -> Dict[str, str]:
    """Build headers for Supabase PostgREST requests."""
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_key:
        raise HTTPException(503, "Supabase is not configured.")
    return {
        "apikey": settings.supabase_key,
        "Authorization": f"Bearer {settings.supabase_key}",
        "Content-Type": "application/json",
    }


def _supabase_url(table: str) -> str:
    """Build the PostgREST URL for a table."""
    settings = get_settings()
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}"


async def _supabase_get(
    table: str,
    params: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Execute a GET against Supabase PostgREST and return rows."""
    url = _supabase_url(table)
    headers = _supabase_headers()

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers, params=params or {})

    if resp.status_code != 200:
        logger.error("Supabase query failed: %s %s -> %s", table, params, resp.text)
        raise HTTPException(502, f"Supabase query failed: {resp.status_code}")

    return resp.json()


@router.get("/countries")
async def list_countries():
    """List available countries with TOU rate data."""
    rows = await _supabase_get(
        "tou_countries",
        {"select": "id,name,code", "order": "name.asc"},
    )
    return rows


@router.get("/regions")
async def list_regions(country: str = Query(..., description="Country code (e.g. US)")):
    """List regions/states for a given country."""
    rows = await _supabase_get(
        "tou_regions",
        {
            "select": "id,name,country_code",
            "country_code": f"eq.{country}",
            "order": "name.asc",
        },
    )
    return rows


@router.get("/utilities")
async def list_utilities(region_id: int = Query(..., description="Region ID")):
    """List utilities for a given region."""
    rows = await _supabase_get(
        "tou_utilities",
        {
            "select": "id,name,region_id",
            "region_id": f"eq.{region_id}",
            "order": "name.asc",
        },
    )
    return rows


@router.get("/rates")
async def get_rates(utility_id: int = Query(..., description="Utility ID")):
    """Get rate plans and blocks for a utility."""
    # Fetch rate plans
    plans = await _supabase_get(
        "tou_rate_plans",
        {
            "select": "id,name,utility_id,description,effective_date",
            "utility_id": f"eq.{utility_id}",
            "order": "effective_date.desc",
        },
    )
    if not plans:
        return {"plans": [], "blocks": []}

    # Fetch rate blocks for all plans from this utility
    plan_ids = [str(p["id"]) for p in plans]
    plan_filter = f"in.({','.join(plan_ids)})"
    blocks = await _supabase_get(
        "tou_rate_blocks",
        {
            "select": "id,rate_plan_id,name,start_hour,end_hour,rate_per_kwh,days_of_week",
            "rate_plan_id": plan_filter,
            "order": "start_hour.asc",
        },
    )
    return {"plans": plans, "blocks": blocks}


@router.get("/lookup")
async def lookup_by_zip(zip: str = Query(..., min_length=5, max_length=10, description="ZIP code")):
    """Look up utility by ZIP code."""
    rows = await _supabase_get(
        "tou_zip_lookup",
        {
            "select": "zip_code,utility_id,tou_utilities(id,name,region_id)",
            "zip_code": f"eq.{zip}",
        },
    )
    if not rows:
        raise HTTPException(404, f"No utility found for ZIP code {zip}.")
    return rows
