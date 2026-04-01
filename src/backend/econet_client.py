"""
EcoNet ClearBlade API client.

Communicates with Rheem's EcoNet backend (ClearBlade IoT platform) using the
same REST + MQTT endpoints as the official EcoNet mobile app.

Protocol details reverse-engineered from the pyeconet open-source project
(github.com/w1ll1am23/pyeconet).  This implementation uses only httpx + paho-mqtt
without pulling in the full pyeconet dependency tree.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import ssl
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ClearBlade platform constants
# These are public values embedded in the official Rheem EcoNet mobile app
# APK/IPA — they are not private secrets. However, they are loaded via env
# so they never appear in git history of forks/clones with custom values.
# ---------------------------------------------------------------------------
_CB_BASE_URL = "https://rheem.clearblade.com"
_CB_SYSTEM_KEY = os.environ.get("CLEARBLADE_SYSTEM_KEY", "e2e699cb0bb0bbb88fc8858cb5a401")
_CB_SYSTEM_SECRET = os.environ.get("CLEARBLADE_SYSTEM_SECRET", "E2E699CB0BE6C6FADDB1B0BC9A20")
_MQTT_HOST = "rheem.clearblade.com"
_MQTT_PORT = 1884
_TOKEN_REFRESH_INTERVAL = 1500  # 25 minutes (conservative before potential expiry)


@dataclass
class DeviceLocation:
    city: str = ""
    state: str = ""
    street: str = ""
    zipcode: str = ""
    country: str = ""


@dataclass
class WaterHeaterState:
    device_id: str          # serial_number (e.g. "07-0e-17-...")
    device_name: str        # ClearBlade device ID (e.g. "11980437215467865")
    name: str
    setpoint: float
    set_point_min: float
    set_point_max: float
    current_temp: Optional[float]
    hot_water_avail: Optional[float]   # 0-100 %
    mode: str
    modes: List[str]
    running: bool
    running_state: Optional[str]
    wifi_signal: Optional[int]
    connected: bool
    active: bool
    todays_energy_kwh: Optional[float]
    energy_type: Optional[str]         # KWH or KBTU
    device_type: str = ""              # e.g. "WH"
    equipment_type: str = ""           # e.g. "heatpumpWaterHeaterGen5"
    mac_address: str = ""
    compressor_health: Optional[float] = None  # 0-100
    tank_health: Optional[float] = None        # 0-100
    compressor_status: str = ""
    tank_status: str = ""
    location: Optional[DeviceLocation] = None


@dataclass
class EcoNetClientState:
    user_token: str = ""
    account_id: str = ""      # Rheem account_id (from options) — used in MQTT topics
    cb_user_id: str = ""      # ClearBlade user_id — for REST auth
    authenticated: bool = False
    mqtt_message_count: int = 0
    last_auth_time: float = 0.0
    last_error: Optional[str] = None
    last_poll: Optional[float] = None
    mqtt_connected: bool = False
    equipment: List[WaterHeaterState] = field(default_factory=list)


class EcoNetClient:
    """
    Async-friendly EcoNet client wrapping ClearBlade REST + MQTT.

    Usage:
        client = EcoNetClient(email, password)
        await client.login()
        equipment = await client.get_equipment()
        await client.set_setpoint(device_id, 120.0)
    """

    # Circular buffer of recent raw MQTT messages for debugging
    MAX_MSG_BUFFER = 50

    def __init__(self, email: str, password: str) -> None:
        self._email = email
        self._password = password
        self._state = EcoNetClientState()
        self._http = httpx.AsyncClient(timeout=15.0)
        self._mqtt_client: Optional[mqtt.Client] = None
        self._state_callbacks: list[Callable[[WaterHeaterState], None]] = []
        self._mqtt_loop_task: Optional[asyncio.Task] = None
        self._state_lock = threading.Lock()
        self._recent_messages: list = []  # circular buffer of recent MQTT messages

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def login(self) -> bool:
        """Authenticate with ClearBlade. Returns True on success."""
        try:
            resp = await self._http.post(
                f"{_CB_BASE_URL}/api/v/1/user/auth",
                headers=self._cb_headers(),
                json={"email": self._email, "password": self._password},
            )
            resp.raise_for_status()
            data = resp.json()
            self._state.user_token = data["user_token"]
            # ClearBlade returns user_id at top level AND account_id inside options
            # The MQTT topic uses the Rheem account_id from options, not the ClearBlade user_id
            options = data.get("options", {})
            self._state.account_id = options.get("account_id", data.get("user_id", ""))
            self._state.cb_user_id = data.get("user_id", "")
            logger.info("Auth IDs — cb_user_id: %s, rheem_account_id: %s",
                        self._state.cb_user_id, self._state.account_id)
            self._state.authenticated = True
            self._state.last_auth_time = time.monotonic()
            self._state.last_error = None
            logger.info("EcoNet login successful for %s", self._email)
            return True
        except Exception as exc:
            self._state.authenticated = False
            self._state.last_error = str(exc)
            logger.error("EcoNet login failed: %s", exc)
            return False

    async def get_equipment(self) -> list[WaterHeaterState]:
        """Discover water heater equipment on the account."""
        await self._ensure_authenticated()
        try:
            resp = await self._http.post(
                f"{_CB_BASE_URL}/api/v/1/code/{_CB_SYSTEM_KEY}/getUserDataForApp",
                headers=self._cb_headers(authed=True),
                json={"resource": "friedrich"},
            )
            resp.raise_for_status()
            data = resp.json()

            # Debug: log the top-level response keys and structure
            if isinstance(data, dict):
                logger.info("getUserDataForApp response keys: %s", list(data.keys()))
                # Try to find equipment in various known response formats
                results = data.get("results", data)
                if isinstance(results, str):
                    # ClearBlade sometimes wraps response in a JSON string
                    import json as _json
                    try:
                        results = _json.loads(results)
                        logger.info("Parsed stringified results, keys: %s", list(results.keys()) if isinstance(results, dict) else type(results))
                    except (ValueError, TypeError):
                        pass
            else:
                results = data
                logger.info("getUserDataForApp response type: %s", type(data))

            if isinstance(results, dict):
                raw_data = results
            else:
                raw_data = data

            equipment = []
            # Try multiple known response structures
            locations = raw_data.get("locations", [])
            if not locations:
                # Some firmware returns equipment at top level
                logger.info("No 'locations' key found. Available keys: %s",
                            list(raw_data.keys()) if isinstance(raw_data, dict) else "N/A")
                # Log a sample of the data for debugging (truncated for safety)
                import json as _json
                sample = _json.dumps(raw_data, default=str)[:2000]
                logger.info("Raw response sample: %s", sample)

            for location in locations:
                # Parse location info
                loc_addr = location.get("@LOCATION_ADDRESS", {})
                loc_info = DeviceLocation(
                    city=loc_addr.get("city", ""),
                    state=loc_addr.get("state", ""),
                    street=loc_addr.get("street", ""),
                    zipcode=loc_addr.get("zipcode", ""),
                    country=loc_addr.get("country", ""),
                )

                devices = location.get("equiptments", location.get("equipments", []))
                for device in devices:
                    state = self._parse_device(device)
                    if state:
                        state.location = loc_info
                        equipment.append(state)

            self._state.equipment = equipment
            self._state.last_poll = time.monotonic()
            if equipment:
                logger.info("Found %d device(s): %s", len(equipment),
                            [e.device_id for e in equipment])
            else:
                logger.warning("No equipment found in API response")
            return equipment
        except Exception as exc:
            self._state.last_error = str(exc)
            logger.error("get_equipment failed: %s", exc)
            return []

    async def set_setpoint(self, device_id: str, temperature: float) -> bool:
        """Change the water heater setpoint. Temperature in °F."""
        # Server-side safety bounds — never trust caller to enforce
        temperature = max(110.0, min(140.0, temperature))
        return await self._publish_desired(device_id, {"@SETPOINT": temperature})

    async def set_mode(self, device_id: str, mode: str) -> bool:
        """Change the operating mode. Converts string mode name to numeric value."""
        mode_num = MODE_TO_NUM.get(mode)
        if mode_num is None:
            logger.error("Unknown mode '%s', valid: %s", mode, list(MODE_TO_NUM.keys()))
            return False
        return await self._publish_desired(device_id, {"@MODE": mode_num})

    async def get_energy_usage(self, device_name: str, serial_number: str,
                               start: str, end: str) -> dict:
        """Fetch energy usage via dynamicAction with the correct pyeconet payload format.

        Dates should be YYYY-MM-DD. Returns dict like {hour_int: kwh_float}.
        The API returns hours that match the EcoNet app's display (user's local time).
        """
        await self._ensure_authenticated()
        payload = {
            "ACTION": "waterheaterUsageReportView",
            "device_name": device_name,
            "serial_number": serial_number,
            "start_date": f"{start}T00:00:00.999",
            "end_date": f"{end}T23:59:59.999",
            "usage_type": "energyUsage",
        }
        try:
            resp = await self._http.post(
                f"{_CB_BASE_URL}/api/v/1/code/{_CB_SYSTEM_KEY}/dynamicAction",
                headers=self._cb_headers(authed=True),
                json=payload,
            )
            data = resp.json()
            logger.info("Energy usage response: status=%d success=%s",
                        resp.status_code, data.get("success"))
            if data.get("success") and "results" in data:
                results = data["results"]
                if isinstance(results, str):
                    results = json.loads(results)
                energy = results.get("energy_usage", {})
                # Log the structure for debugging multi-day responses
                logger.info("Energy response keys: %s, data entries: %d, message: %s",
                            list(energy.keys()) if isinstance(energy, dict) else "?",
                            len(energy.get("data", [])),
                            str(energy.get("message", ""))[:100])
                if energy.get("data") and len(energy["data"]) > 0:
                    sample = energy["data"][0]
                    logger.info("Energy data sample item: %s", sample)
                usage = {}
                for item in energy.get("data", []):
                    usage[int(item["name"])] = float(item["value"])
                logger.info("Energy usage: %d entries parsed", len(usage))
                return usage
            logger.warning("Energy usage call returned success=false: %s", str(data)[:300])
            return {}
        except Exception as exc:
            logger.error("get_energy_usage failed: %s", exc)
            return {}

    async def get_water_usage(self, device_name: str, serial_number: str,
                               start: str, end: str) -> float:
        """Fetch water usage. Returns total gallons or 0."""
        await self._ensure_authenticated()
        payload = {
            "ACTION": "waterheaterUsageReportView",
            "device_name": device_name,
            "serial_number": serial_number,
            "start_date": f"{start}T00:00:00.999",
            "end_date": f"{end}T23:59:59.999",
            "usage_type": "waterUsage",
        }
        try:
            resp = await self._http.post(
                f"{_CB_BASE_URL}/api/v/1/code/{_CB_SYSTEM_KEY}/dynamicAction",
                headers=self._cb_headers(authed=True),
                json=payload,
            )
            data = resp.json()
            if data.get("success") and "results" in data:
                results = data["results"]
                if isinstance(results, str):
                    results = json.loads(results)
                water = results.get("water_usage", {})
                total = sum(item["value"] for item in water.get("data", []))
                return total
            return 0.0
        except Exception as exc:
            logger.error("get_water_usage failed: %s", exc)
            return 0.0

    def subscribe_state(self, callback: Callable[[WaterHeaterState], None]) -> None:
        """Register a callback to receive real-time state updates from MQTT."""
        self._state_callbacks.append(callback)

    def start_mqtt(self) -> None:
        """Start the MQTT client matching pyeconet's exact ClearBlade setup."""
        if not self._state.authenticated:
            logger.warning("Cannot start MQTT — not authenticated")
            return

        # Client ID must be unique — if same as the phone app, ClearBlade boots one
        # Use a different suffix to coexist with the EcoNet mobile app
        import hashlib
        unique = hashlib.md5(f"{self._email}_webapp".encode()).hexdigest()[:12]
        client_id = f"{unique}_{int(time.time())}_web"

        # Paho 2.x requires CallbackAPIVersion to use v1-style callbacks
        try:
            from paho.mqtt.client import CallbackAPIVersion
            client = mqtt.Client(
                callback_api_version=CallbackAPIVersion.VERSION1,
                client_id=client_id,
                protocol=mqtt.MQTTv311,
                clean_session=True,
            )
        except ImportError:
            # Paho 1.x fallback
            client = mqtt.Client(
                client_id=client_id,
                protocol=mqtt.MQTTv311,
                clean_session=True,
            )

        # Auth: user_token as username, SYSTEM KEY as password
        client.username_pw_set(self._state.user_token, password=_CB_SYSTEM_KEY)
        client.on_connect = self._on_mqtt_connect
        client.on_disconnect = self._on_mqtt_disconnect
        client.on_message = self._on_mqtt_message
        client.on_log = self._on_mqtt_log
        client.on_subscribe = self._on_mqtt_subscribe

        # TLS: use default SSL context (same as pyeconet)
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS)
        ssl_ctx.load_default_certs()
        client.tls_set_context(ssl_ctx)
        client.tls_insecure_set(False)

        try:
            client.connect_async(_MQTT_HOST, _MQTT_PORT)  # Port 1884
            client.loop_start()
            self._mqtt_client = client
            logger.info("MQTT client started, connecting to %s:%d (client_id=%s)",
                        _MQTT_HOST, _MQTT_PORT, client_id[:40] + "...")
        except Exception as exc:
            logger.error("MQTT connect failed: %s — will rely on REST polling", exc)
            self._state.last_error = str(exc)

    def stop_mqtt(self) -> None:
        if self._mqtt_client:
            self._mqtt_client.loop_stop()
            self._mqtt_client.disconnect()
            self._mqtt_client = None
        self._state.mqtt_connected = False

    @property
    def state(self) -> EcoNetClientState:
        return self._state

    async def close(self) -> None:
        self.stop_mqtt()
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cb_headers(self, authed: bool = False) -> Dict[str, str]:
        headers = {
            "ClearBlade-SystemKey": _CB_SYSTEM_KEY,
            "ClearBlade-SystemSecret": _CB_SYSTEM_SECRET,
            "Content-Type": "application/json",
        }
        if authed and self._state.user_token:
            headers["ClearBlade-UserToken"] = self._state.user_token
        return headers

    async def _ensure_authenticated(self) -> None:
        elapsed = time.monotonic() - self._state.last_auth_time
        if not self._state.authenticated or elapsed > _TOKEN_REFRESH_INTERVAL:
            logger.info("Token refresh needed, re-authenticating")
            await self.login()

    async def _publish_desired(self, device_id: str, payload: Dict[str, Any]) -> bool:
        """Publish a desired state change via MQTT (the only method that works for Gen5 firmware)."""
        await self._ensure_authenticated()

        # Find the device_name (ClearBlade ID) for this serial number
        device_name = ""
        for eq in self._state.equipment:
            if eq.device_id == device_id:
                device_name = eq.device_name
                break

        topic = f"user/{self._state.account_id}/device/desired"
        # Message format must match pyeconet exactly
        from datetime import datetime as _dt, timezone as _tz
        transaction_id = f"ANDROID_{_dt.now(_tz.utc).isoformat()}"
        msg = {
            "transactionId": transaction_id,
            "device_name": device_name or device_id,
            "serial_number": device_id,
            **payload,
        }
        msg_json = json.dumps(msg)

        # Method 1: Direct MQTT publish (primary — this is what works)
        if self._mqtt_client and self._state.mqtt_connected:
            result = self._mqtt_client.publish(topic, msg_json)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info("MQTT publish OK: topic=%s payload=%s", topic, msg_json[:200])
                return True
            logger.warning("MQTT publish failed rc=%d", result.rc)

        # Method 2: ClearBlade REST messaging API (publishes to MQTT topic via HTTP)
        try:
            resp = await self._http.post(
                f"{_CB_BASE_URL}/api/v/1/message/{_CB_SYSTEM_KEY}",
                headers=self._cb_headers(authed=True),
                json={"topic": topic, "body": msg_json},
            )
            logger.info("REST messaging: status=%d body=%s", resp.status_code, resp.text[:300])
            if resp.status_code == 200:
                return True
        except Exception as exc:
            logger.warning("REST messaging failed: %s", exc)

        self._state.last_error = "Command failed. MQTT not connected and REST messaging rejected."
        logger.error("All control methods failed for device %s", device_id)
        return False

    def _parse_device(self, device: Dict[str, Any]) -> Optional[WaterHeaterState]:
        """Parse a device dict from the ClearBlade API.

        Rheem's API uses @-prefixed keys at the top level (not nested under
        'properties'). Values are either plain scalars or dicts with a 'value'
        key and optional 'constraints'/'status' metadata.
        """
        try:
            serial = (device.get("serial_number", "")
                      or device.get("serialNumber", ""))
            if not serial:
                return None

            # Helper: extract .value from @-prefixed dict-style properties
            def _val(key: str, default=None):
                raw = device.get(key, default)
                if isinstance(raw, dict):
                    return raw.get("value", default)
                return raw

            def _constraint(key: str, field: str, default=None):
                raw = device.get(key, {})
                if isinstance(raw, dict):
                    constraints = raw.get("constraints", {})
                    return constraints.get(field, default)
                return default

            # --- Name ---
            name = _val("@NAME", serial)
            if isinstance(name, str):
                name = name.strip()

            # --- Setpoint ---
            setpoint = _safe_float(_val("@SETPOINT", 120)) or 120.0
            sp_min = _safe_float(_constraint("@SETPOINT", "lowerLimit", 110)) or 110.0
            sp_max = _safe_float(_constraint("@SETPOINT", "upperLimit", 140)) or 140.0

            # --- Mode ---
            # @MODE.value is numeric (0-5), @MODE.status is the human label
            # Mapping: 0=Off, 1=Energy Saver, 2=Heat Pump, 3=High Demand,
            #          4=Electric/Gas, 5=Vacation
            mode_num = _safe_int(_val("@MODE", 0)) or 0
            mode_map = {
                0: "OFF",
                1: "ENERGY_SAVING",
                2: "HEAT_PUMP_ONLY",
                3: "HIGH_DEMAND",
                4: "ELECTRIC_MODE",
                5: "VACATION",
            }
            mode = mode_map.get(mode_num, "UNKNOWN")
            modes = list(mode_map.values())

            # --- Running ---
            running_raw = device.get("@RUNNING", "")
            # @RUNNING is a string — non-empty means active
            running = bool(running_raw and str(running_raw).strip())
            running_state = str(running_raw).strip() if running_raw else None

            # --- Hot water availability ---
            # @HOTWATER is an image filename like "ic_tank_zero_percent_v2.png"
            hot_water_img = device.get("@HOTWATER", "")
            hot_water_avail = _parse_hot_water_image(hot_water_img)

            # --- Connected / Active ---
            connected = bool(device.get("@CONNECTED", False))
            active = bool(device.get("@ACTIVE", True))
            enabled_val = _val("@ENABLED", 1)
            if enabled_val == 0:
                active = False

            # --- Health ---
            # No current_temp, wifi_signal, or todaysEnergyUsage in this API format

            # ClearBlade device ID (different from serial_number)
            cb_device_name = device.get("device_name", "")

            # Health sensors
            combustion = device.get("@COMBUSTION", {})
            compressor_health = _safe_float(combustion.get("value")) if isinstance(combustion, dict) else None
            compressor_status = combustion.get("status", "") if isinstance(combustion, dict) else ""
            tank_data = device.get("@TANK", {})
            tank_health = _safe_float(tank_data.get("value")) if isinstance(tank_data, dict) else None
            tank_status = tank_data.get("status", "") if isinstance(tank_data, dict) else ""

            return WaterHeaterState(
                device_id=serial,
                device_name=cb_device_name,
                name=name or serial,
                setpoint=setpoint,
                set_point_min=sp_min,
                set_point_max=sp_max,
                current_temp=None,   # not available in this API format
                hot_water_avail=hot_water_avail,
                mode=mode,
                modes=modes,
                running=running,
                running_state=running_state,
                wifi_signal=None,    # not available in this API format
                connected=connected,
                active=active,
                todays_energy_kwh=None,
                energy_type="KWH",
                device_type=device.get("device_type", ""),
                equipment_type=device.get("@TYPE", ""),
                mac_address=device.get("mac_address", ""),
                compressor_health=compressor_health,
                tank_health=tank_health,
                compressor_status=compressor_status,
                tank_status=tank_status,
            )
        except Exception as exc:
            logger.warning("Failed to parse device: %s", exc)
            return None

    # ------------------------------------------------------------------
    # MQTT callbacks (called from paho's background thread)
    # ------------------------------------------------------------------

    def _on_mqtt_connect(self, client: mqtt.Client, userdata: Any, flags: dict, rc: int) -> None:
        with self._state_lock:
            if rc == 0:
                self._state.mqtt_connected = True
                logger.info("MQTT connected! flags=%s", flags)
                # Subscribe using the Rheem account_id (not ClearBlade user_id)
                topic_reported = f"user/{self._state.account_id}/device/reported"
                topic_desired = f"user/{self._state.account_id}/device/desired"
                client.subscribe(topic_reported, qos=0)
                client.subscribe(topic_desired, qos=0)
                logger.info("MQTT subscribed to %s", topic_reported)
            else:
                self._state.mqtt_connected = False
                rc_reasons = {1: "bad protocol", 2: "client ID rejected", 3: "server unavailable",
                              4: "bad credentials", 5: "not authorized"}
                logger.error("MQTT connection refused, rc=%d (%s)", rc,
                             rc_reasons.get(rc, "unknown"))

    def _on_mqtt_log(self, client: mqtt.Client, userdata: Any, level: int, buf: str) -> None:
        if level <= mqtt.MQTT_LOG_WARNING:
            logger.info("MQTT-paho [%d]: %s", level, buf)

    def _on_mqtt_subscribe(self, client: mqtt.Client, userdata: Any, mid: int, granted_qos: Any) -> None:
        logger.info("MQTT subscribed mid=%d qos=%s", mid, granted_qos)

    def _on_mqtt_disconnect(self, client: mqtt.Client, userdata: Any, rc: int) -> None:
        with self._state_lock:
            self._state.mqtt_connected = False
        if rc != 0:
            logger.warning("MQTT unexpected disconnect rc=%d — paho will reconnect", rc)

    def _on_mqtt_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        try:
            raw = msg.payload.decode()
            payload = json.loads(raw)
            self._state.mqtt_message_count += 1

            # Store in debug buffer (truncated)
            from datetime import datetime as _dt
            self._recent_messages.append({
                "time": _dt.now().isoformat(),
                "topic": msg.topic,
                "keys": list(payload.keys()) if isinstance(payload, dict) else str(type(payload)),
                "size": len(raw),
                "sample": raw[:500],
            })
            if len(self._recent_messages) > self.MAX_MSG_BUFFER:
                self._recent_messages.pop(0)

            topic_type = "reported" if "/reported" in msg.topic else "desired" if "/desired" in msg.topic else "other"
            logger.info("MQTT %s msg: %d keys, %d bytes, keys=%s",
                        topic_type, len(payload) if isinstance(payload, dict) else 0,
                        len(raw), list(payload.keys())[:10] if isinstance(payload, dict) else "?")

            if not isinstance(payload, dict):
                return

            # Match to a device — try both serial_number and device_name
            serial = payload.get("serial_number", payload.get("serialNumber", ""))
            dev_name = payload.get("device_name", "")
            callbacks_to_fire: List[Tuple[Callable, WaterHeaterState]] = []

            with self._state_lock:
                for idx, device in enumerate(self._state.equipment):
                    if (serial and device.device_id == serial) or \
                       (dev_name and device.device_name == dev_name):
                        updated = self._apply_mqtt_update(device, payload)
                        self._state.equipment = (
                            self._state.equipment[:idx] + [updated] + self._state.equipment[idx + 1:]
                        )
                        callbacks_to_fire = [(cb, updated) for cb in self._state_callbacks]
                        break

            for cb, updated in callbacks_to_fire:
                try:
                    cb(updated)
                except Exception as cb_exc:
                    logger.warning("State callback error: %s", cb_exc)
        except Exception as exc:
            logger.warning("MQTT message parse error: %s", exc)

    def get_recent_messages(self) -> list:
        """Return the recent MQTT message buffer for debugging."""
        return list(self._recent_messages)

    def _apply_mqtt_update(self, device: WaterHeaterState, payload: dict) -> WaterHeaterState:
        """Apply a partial MQTT state update. Handles both @-prefixed and plain key formats."""

        def _val(key: str, at_key: str, default=None):
            """Try @-prefixed key first, then plain key."""
            raw = payload.get(at_key)
            if raw is not None:
                return raw.get("value", raw) if isinstance(raw, dict) else raw
            return payload.get(key, default)

        # Mode: handle numeric @MODE or string mode
        mode_raw = _val("mode", "@MODE")
        if mode_raw is not None:
            mode_map = {0: "OFF", 1: "ENERGY_SAVING", 2: "HEAT_PUMP_ONLY",
                        3: "HIGH_DEMAND", 4: "ELECTRIC_MODE", 5: "VACATION"}
            if isinstance(mode_raw, (int, float)):
                mode = mode_map.get(int(mode_raw), device.mode)
            elif isinstance(mode_raw, dict) and "value" in mode_raw:
                mode = mode_map.get(int(mode_raw["value"]), device.mode)
            else:
                mode = str(mode_raw) if mode_raw else device.mode
        else:
            mode = device.mode

        # Setpoint
        sp_raw = _val("setPoint", "@SETPOINT")
        setpoint = _safe_float(sp_raw) if sp_raw is not None else device.setpoint

        # Running
        running_raw = _val("running", "@RUNNING")
        if isinstance(running_raw, str):
            running = bool(running_raw.strip())
            running_state = running_raw.strip() if running_raw.strip() else device.running_state
        elif isinstance(running_raw, bool):
            running = running_raw
            running_state = device.running_state
        else:
            running = device.running
            running_state = device.running_state

        # Hot water
        hw_raw = payload.get("@HOTWATER", payload.get("hotWaterStatus"))
        if isinstance(hw_raw, str) and "percent" in hw_raw.lower():
            hot_water = _parse_hot_water_image(hw_raw)
        elif hw_raw is not None:
            hot_water = _safe_float(hw_raw) if not isinstance(hw_raw, str) else device.hot_water_avail
        else:
            hot_water = device.hot_water_avail

        connected = payload.get("@CONNECTED", payload.get("connected", device.connected))

        return WaterHeaterState(
            device_id=device.device_id,
            device_name=device.device_name,
            name=device.name,
            setpoint=setpoint or device.setpoint,
            set_point_min=device.set_point_min,
            set_point_max=device.set_point_max,
            current_temp=_safe_float(_val("inletTemperature", "@INLET_TEMP")) or device.current_temp,
            hot_water_avail=hot_water,
            mode=mode,
            modes=device.modes,
            running=running,
            running_state=running_state,
            wifi_signal=device.wifi_signal,
            connected=bool(connected),
            active=device.active,
            todays_energy_kwh=_safe_float(payload.get("todaysEnergyUsage")) or device.todays_energy_kwh,
            energy_type=device.energy_type,
            device_type=device.device_type,
            equipment_type=device.equipment_type,
            mac_address=device.mac_address,
            compressor_health=device.compressor_health,
            tank_health=device.tank_health,
            compressor_status=device.compressor_status,
            tank_status=device.tank_status,
            location=device.location,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val: Any) -> Optional[float]:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _safe_int(val: Any) -> Optional[int]:
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _parse_hot_water_image(img: Any) -> Optional[float]:
    """Parse hot water availability from the @HOTWATER image filename.

    Per pyeconet source (water_heater.py lines 116-134), the image names DON'T
    map to literal percentages. Rheem uses only 4 levels:
      ic_tank_hundread_percent  → 100% (they misspell "hundred")
      ic_tank_fourty_percent    → 66%  (2/3 full — "fourty" is also misspelled)
      ic_tank_ten_percent       → 33%  (1/3 full)
      ic_tank_empty / ic_tank_zero_percent → 0%
    """
    if not isinstance(img, str):
        return None
    img_lower = img.lower()

    if "hundread_percent" in img_lower or "hundred_percent" in img_lower:
        return 100.0
    if "fourty_percent" in img_lower or "forty_percent" in img_lower:
        return 66.0   # 2/3 full per pyeconet
    if "ten_percent" in img_lower:
        return 33.0   # 1/3 full per pyeconet
    if "empty" in img_lower or "zero_percent" in img_lower:
        return 0.0

    # Fallback: try to extract a number
    import re
    match = re.search(r"(\d+)[_\s]*percent", img_lower)
    if match:
        return float(match.group(1))
    return None


# Mode name → numeric value mapping for sending control commands
MODE_TO_NUM = {
    "OFF": 0,
    "ENERGY_SAVING": 1,
    "HEAT_PUMP_ONLY": 2,
    "HIGH_DEMAND": 3,
    "ELECTRIC_MODE": 4,
    "VACATION": 5,
}
