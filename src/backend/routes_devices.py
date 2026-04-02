"""Multi-device management API routes."""
from __future__ import annotations

import logging
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_session
from .models import Device
from .schemas import DeviceCreate, DeviceOut, DeviceUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/devices", tags=["devices"])


def _device_to_out(device: Device) -> DeviceOut:
    return DeviceOut(
        id=device.id,
        name=device.name,
        provider=device.provider,
        device_type=device.device_type,
        external_device_id=device.external_device_id,
        is_active=device.is_active,
        created_at=device.created_at,
    )


@router.get("", response_model=List[DeviceOut])
async def list_devices(session: AsyncSession = Depends(get_session)):
    """List all registered devices."""
    result = await session.execute(
        select(Device).order_by(Device.created_at.desc())
    )
    return [_device_to_out(d) for d in result.scalars().all()]


@router.post("", response_model=DeviceOut, status_code=201)
async def add_device(
    body: DeviceCreate,
    session: AsyncSession = Depends(get_session),
):
    """Register a new device. For econet provider, validates credentials first."""
    external_device_id = None

    if body.provider == "econet":
        if not body.credentials:
            raise HTTPException(
                400, "Credentials (email + password) are required for EcoNet devices."
            )
        # Test the EcoNet login before saving
        from .econet_client import EcoNetClient

        test_client = EcoNetClient(body.credentials.email, body.credentials.password)
        try:
            logged_in = await test_client.login()
            if not logged_in:
                raise HTTPException(
                    401,
                    "EcoNet authentication failed. Check your credentials.",
                )
            # Get the first equipment device id as the external reference
            equipment = await test_client.get_equipment()
            if equipment:
                external_device_id = equipment[0].device_id
        finally:
            await test_client.close()

    device = Device(
        id=str(uuid.uuid4()),
        name=body.name,
        provider=body.provider,
        device_type=body.device_type,
        external_device_id=external_device_id,
        is_active=True,
    )
    session.add(device)
    await session.commit()
    await session.refresh(device)

    logger.info("Device added: %s (%s / %s)", device.name, device.provider, device.id)
    return _device_to_out(device)


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(
    device_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get a single device by ID."""
    device = await session.get(Device, device_id)
    if not device:
        raise HTTPException(404, "Device not found.")
    return _device_to_out(device)


@router.put("/{device_id}", response_model=DeviceOut)
async def update_device(
    device_id: str,
    body: DeviceUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update device name or active status."""
    device = await session.get(Device, device_id)
    if not device:
        raise HTTPException(404, "Device not found.")

    if body.name is not None:
        device.name = body.name
    if body.is_active is not None:
        device.is_active = body.is_active

    await session.commit()
    await session.refresh(device)

    logger.info("Device updated: %s (%s)", device.name, device.id)
    return _device_to_out(device)


@router.delete("/{device_id}")
async def delete_device(
    device_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Remove a device."""
    device = await session.get(Device, device_id)
    if not device:
        raise HTTPException(404, "Device not found.")

    await session.delete(device)
    await session.commit()

    logger.info("Device deleted: %s (%s)", device_id, device.name)
    return {"status": "ok", "deleted": device_id}


@router.get("/{device_id}/status")
async def get_device_status(
    device_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get live status from the device's provider."""
    device = await session.get(Device, device_id)
    if not device:
        raise HTTPException(404, "Device not found.")

    if not device.is_active:
        raise HTTPException(400, "Device is inactive.")

    if device.provider == "econet":
        # Use the existing global EcoNet client for status
        from .routes_api import _get_client

        try:
            client = _get_client()
        except HTTPException:
            raise HTTPException(503, "EcoNet client not available.")

        eq = client.state.equipment
        # Match by external_device_id if available
        matched = None
        for e in eq:
            if device.external_device_id and e.device_id == device.external_device_id:
                matched = e
                break
        if not matched and eq:
            matched = eq[0]

        if not matched:
            raise HTTPException(404, "No EcoNet equipment found.")

        return {
            "device_id": device.id,
            "provider": "econet",
            "online": matched.connected,
            "setpoint": matched.setpoint,
            "current_temp": matched.current_temp,
            "hot_water_avail": matched.hot_water_avail,
            "mode": matched.mode,
            "running": matched.running,
            "running_state": matched.running_state,
        }

    if device.provider == "smartthings":
        return {
            "device_id": device.id,
            "provider": "smartthings",
            "online": False,
            "message": "SmartThings integration not yet implemented.",
        }

    # manual provider
    return {
        "device_id": device.id,
        "provider": "manual",
        "online": None,
        "message": "Manual devices do not report live status.",
    }
