"""Location management API routes."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_session
from .models import Location
from .schemas import LocationIn, LocationOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/locations")


def _location_to_out(loc: Location) -> LocationOut:
    return LocationOut(
        id=loc.id,
        name=loc.name,
        address=loc.address,
        city=loc.city,
        state=loc.state,
        zip_code=loc.zip_code,
        country=loc.country,
        utility_name=loc.utility_name,
        is_primary=loc.is_primary,
        created_at=loc.created_at,
    )


async def _lookup_utility_by_zip(
    zip_code: str | None, session: AsyncSession
) -> str | None:
    """Try to find a utility name from tou_zip_utility_map if the table exists."""
    if not zip_code:
        return None
    try:
        from sqlalchemy import text
        result = await session.execute(
            text("SELECT utility_name FROM tou_zip_utility_map WHERE zip_code = :z LIMIT 1"),
            {"z": zip_code},
        )
        row = result.first()
        return row[0] if row else None
    except Exception:
        # Table may not exist yet — silently skip
        return None


@router.get("", response_model=list[LocationOut])
async def list_locations(session: AsyncSession = Depends(get_session)):
    """List all user locations, primary first."""
    result = await session.execute(
        select(Location).order_by(Location.is_primary.desc(), Location.name)
    )
    return [_location_to_out(loc) for loc in result.scalars().all()]


@router.post("", response_model=LocationOut, status_code=201)
async def create_location(
    body: LocationIn, session: AsyncSession = Depends(get_session)
):
    """Add a new location. Auto-looks up utility by zip code."""
    utility = await _lookup_utility_by_zip(body.zip_code, session)

    # If this is the first location, make it primary
    count_result = await session.execute(select(Location))
    is_first = len(count_result.scalars().all()) == 0

    loc = Location(
        name=body.name,
        address=body.address,
        city=body.city,
        state=body.state,
        zip_code=body.zip_code,
        country=body.country,
        utility_name=utility,
        is_primary=is_first,
    )
    session.add(loc)
    await session.commit()
    await session.refresh(loc)
    logger.info("Created location: %s (id=%d)", loc.name, loc.id)
    return _location_to_out(loc)


@router.put("/{location_id}", response_model=LocationOut)
async def update_location(
    location_id: int, body: LocationIn,
    session: AsyncSession = Depends(get_session),
):
    """Update an existing location."""
    result = await session.execute(
        select(Location).where(Location.id == location_id)
    )
    loc = result.scalar_one_or_none()
    if not loc:
        raise HTTPException(404, "Location not found")

    loc.name = body.name
    loc.address = body.address
    loc.city = body.city
    loc.state = body.state
    loc.zip_code = body.zip_code
    loc.country = body.country

    # Re-lookup utility if zip changed
    utility = await _lookup_utility_by_zip(body.zip_code, session)
    if utility:
        loc.utility_name = utility

    await session.commit()
    await session.refresh(loc)
    logger.info("Updated location: %s (id=%d)", loc.name, loc.id)
    return _location_to_out(loc)


@router.delete("/{location_id}")
async def delete_location(
    location_id: int, session: AsyncSession = Depends(get_session),
):
    """Delete a location."""
    result = await session.execute(
        select(Location).where(Location.id == location_id)
    )
    loc = result.scalar_one_or_none()
    if not loc:
        raise HTTPException(404, "Location not found")

    was_primary = loc.is_primary
    await session.delete(loc)
    await session.commit()

    # If deleted location was primary, promote the next one
    if was_primary:
        result = await session.execute(select(Location).limit(1))
        next_loc = result.scalar_one_or_none()
        if next_loc:
            next_loc.is_primary = True
            await session.commit()

    logger.info("Deleted location id=%d", location_id)
    return {"status": "ok"}


@router.post("/{location_id}/set-primary")
async def set_primary_location(
    location_id: int, session: AsyncSession = Depends(get_session),
):
    """Set a location as the primary location."""
    result = await session.execute(
        select(Location).where(Location.id == location_id)
    )
    loc = result.scalar_one_or_none()
    if not loc:
        raise HTTPException(404, "Location not found")

    # Clear all primary flags
    all_result = await session.execute(select(Location))
    for other in all_result.scalars().all():
        other.is_primary = (other.id == location_id)

    await session.commit()
    logger.info("Set primary location: %s (id=%d)", loc.name, loc.id)
    return {"status": "ok", "primary_id": location_id}
