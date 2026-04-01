"""Tests for EcoNet API client (mocked HTTP)."""
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.backend.econet_client import EcoNetClient, _safe_float, _safe_int


AUTH_RESPONSE = {"user_token": "tok_abc123", "user_id": "user_42"}
EQUIPMENT_RESPONSE = {
    "locations": [{
        "equiptments": [{
            "serial_number": "SN001",
            "@NAME": {"value": "My Water Heater"},
            "@SETPOINT": {"value": 120, "constraints": {"lowerLimit": 110, "upperLimit": 140}},
            "@MODE": {"value": 1, "status": "Energy Saver  ",
                      "constraints": {"enumText": ["Off", "Energy Saver", "Heat Pump",
                                                   "High Demand", "Electric/Gas", "Vacation"]}},
            "@RUNNING": "",
            "@HOTWATER": "ic_tank_75_percent_v2.png",
            "@CONNECTED": True,
            "@ACTIVE": True,
            "@ENABLED": {"value": 1},
            "@TYPE": "heatpumpWaterHeaterGen5",
            "device_name": "11980437215467865",
        }]
    }]
}


@pytest.fixture
def mock_http():
    """Patch httpx.AsyncClient.post to return mock responses."""
    async def mock_post(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "user/auth" in url:
            resp.json.return_value = AUTH_RESPONSE
        elif "getUserDataForApp" in url:
            resp.json.return_value = EQUIPMENT_RESPONSE
        elif "dynamicAction" in url:
            resp.json.return_value = {"data": {"2026-04-01T07": 0.45, "2026-04-01T08": 0.6}}
        else:
            resp.json.return_value = {}
        return resp
    return mock_post


class TestEcoNetClient:
    @pytest.mark.asyncio
    async def test_login_success(self, mock_http):
        client = EcoNetClient("test@example.com", "password")
        with patch.object(client._http, "post", side_effect=mock_http):
            result = await client.login()
        assert result is True
        assert client.state.authenticated is True
        assert client.state.user_token == "tok_abc123"
        assert client.state.account_id == "user_42"
        await client.close()

    @pytest.mark.asyncio
    async def test_login_failure_returns_false(self):
        client = EcoNetClient("bad@example.com", "wrong")
        async def fail_post(url, **kwargs):
            import httpx
            raise httpx.HTTPStatusError("401", request=MagicMock(), response=MagicMock())
        with patch.object(client._http, "post", side_effect=fail_post):
            result = await client.login()
        assert result is False
        assert client.state.authenticated is False
        await client.close()

    @pytest.mark.asyncio
    async def test_get_equipment_returns_devices(self, mock_http):
        client = EcoNetClient("test@example.com", "password")
        with patch.object(client._http, "post", side_effect=mock_http):
            await client.login()
            equipment = await client.get_equipment()
        assert len(equipment) == 1
        device = equipment[0]
        assert device.device_id == "SN001"
        assert device.setpoint == 120
        assert device.mode == "ENERGY_SAVING"
        assert device.hot_water_avail == 75.0  # parsed from ic_tank_75_percent_v2.png
        assert device.running is False
        await client.close()

    @pytest.mark.asyncio
    async def test_set_setpoint_enforces_bounds(self, mock_http):
        """set_setpoint must clamp to 110-140°F regardless of input."""
        client = EcoNetClient("test@example.com", "password")
        with patch.object(client._http, "post", side_effect=mock_http):
            await client.login()
            client._state.equipment = (await client.get_equipment())

        # Patch _publish_desired to capture what temperature is sent
        sent_temps = []
        async def capture_desired(device_id, payload):
            sent_temps.append(payload.get("@SETPOINT"))
            return True
        with patch.object(client, "_publish_desired", side_effect=capture_desired):
            await client.set_setpoint("SN001", 200.0)   # above max
            await client.set_setpoint("SN001", 50.0)    # below min
            await client.set_setpoint("SN001", 125.0)   # valid
        assert sent_temps[0] == 140.0
        assert sent_temps[1] == 110.0
        assert sent_temps[2] == 125.0
        await client.close()

    # get_energy_usage removed — dynamicAction API doesn't work on Gen5 firmware


class TestHelpers:
    def test_safe_float_valid(self):
        assert _safe_float(3.14) == 3.14
        assert _safe_float("2.5") == 2.5
        assert _safe_float(None) is None
        assert _safe_float("bad") is None

    def test_safe_int_valid(self):
        assert _safe_int(5) == 5
        assert _safe_int("3") == 3
        assert _safe_int(None) is None
        assert _safe_int("x") is None
