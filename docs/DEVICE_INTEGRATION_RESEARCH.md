# Device Integration Research: TP-Link Kasa & LG ThinQ

**Date:** 2026-04-01
**Status:** Research complete
**App context:** WattWise (FastAPI backend, SQLAlchemy/SQLite, APScheduler poller, existing EcoNet integration)

---

## 1. TP-Link Kasa Smart Plugs (EP25)

### 1.1 Library: python-kasa

**Package:** `python-kasa` (PyPI)
**Repository:** https://github.com/python-kasa/python-kasa
**License:** GPL-3.0
**Maturity:** Very mature, actively maintained, large community (Home Assistant core dependency)

#### Key facts

- **Local-only by default.** All communication happens over the local network via TP-Link's proprietary protocol (port 9999 for older devices, KLAP/AES for newer firmware). No cloud account or internet connection required.
- **Async-native.** Built on asyncio, which fits our FastAPI/async architecture perfectly.
- **Supports EP25.** The EP25 (Kasa Smart Plug Mini with Energy Monitoring) is a "slim" plug with full energy monitoring. python-kasa identifies it as a `KP125M` or `EP25` depending on hardware revision. It uses the newer KLAP or AES transport (not the legacy XOR protocol).
- **MATTER/Thread models:** Some newer EP25 variants support Matter. python-kasa handles these through its device discovery, though Matter-only devices may need different handling.

#### Authentication / transport

- **No cloud auth needed for local control.** python-kasa communicates directly with the device on the LAN.
- **Newer firmware (KLAP/AES):** Devices with firmware 1.1.0+ use KLAP (Key-Level Authentication Protocol) or AES encryption. python-kasa handles this transparently but requires the device's **TP-Link cloud credentials** (email/password used in the Kasa app) for initial handshake on KLAP devices. After the first successful auth, the session is cached.
- **Credential requirement for EP25:** Because EP25 uses newer firmware, you WILL need to pass TP-Link cloud credentials to python-kasa for the KLAP handshake, even though all communication stays local. This is a one-time auth per device.

```python
from kasa import Discover, Credentials

# Credentials needed for newer devices (EP25 uses KLAP)
creds = Credentials(username="user@example.com", password="kasa_password")

# Discover all devices on local network
devices = await Discover.discover(credentials=creds)
```

#### Cloud API alternative

- **TP-Link cloud (tplinkcloud):** TP-Link does have a cloud API but it is undocumented, rate-limited, and unreliable. The `tplink-cloud-api` npm package exists but there is no well-maintained Python equivalent.
- **Recommendation:** Use python-kasa (local) exclusively. It is faster, more reliable, and does not depend on TP-Link's cloud infrastructure.

### 1.2 EP25 Energy Monitoring Capabilities

The EP25 has a built-in energy monitoring chip. python-kasa exposes this through the `emeter` (Energy Meter) module.

| Data point | Available | Access method | Notes |
|---|---|---|---|
| Real-time wattage (W) | Yes | `device.emeter_realtime.power` | Updated every ~2 seconds internally |
| Real-time voltage (V) | Yes | `device.emeter_realtime.voltage` | Typically 120V +/- |
| Real-time current (A) | Yes | `device.emeter_realtime.current` | Milliamp precision |
| Total kWh (cumulative) | Yes | `device.emeter_realtime.total` | Since last reset |
| Monthly kWh history | Yes | `await device.get_emeter_monthly()` | Dict of {month: kwh} |
| Daily kWh history | Yes | `await device.get_emeter_daily(year, month)` | Dict of {day: kwh} for given month |
| On/off state | Yes | `device.is_on` | Boolean |
| On/off control | Yes | `await device.turn_on()` / `await device.turn_off()` | Immediate |
| Device alias/name | Yes | `device.alias` | User-assigned name from Kasa app |
| Signal strength | No | N/A | Not exposed via local protocol |

**Historical data:** The device stores daily and monthly kWh totals internally (rolling ~30 days of daily, 12 months of monthly). There is NO hourly breakdown stored on the device -- only daily totals and real-time instantaneous readings. To get hourly data, you must poll and aggregate yourself.

### 1.3 Example Code

```python
"""TP-Link Kasa EP25 integration example for WattWise."""
import asyncio
from kasa import Discover, SmartPlug, Credentials

async def discover_kasa_devices(
    tp_email: str, tp_password: str
) -> list[dict]:
    """Discover all Kasa devices on the local network."""
    creds = Credentials(username=tp_email, password=tp_password)
    devices = await Discover.discover(credentials=creds)

    result = []
    for ip, dev in devices.items():
        await dev.update()  # Fetch current state
        result.append({
            "ip": ip,
            "alias": dev.alias,
            "model": dev.model,
            "device_id": dev.device_id,
            "has_emeter": dev.has_emeter,
            "is_on": dev.is_on,
        })
    return result


async def read_energy(host: str, tp_email: str, tp_password: str) -> dict:
    """Read real-time energy data from a specific EP25 plug."""
    creds = Credentials(username=tp_email, password=tp_password)
    dev = await Discover.discover_single(host, credentials=creds)
    await dev.update()

    if not dev.has_emeter:
        raise ValueError(f"Device {dev.alias} does not support energy monitoring")

    realtime = dev.emeter_realtime
    return {
        "power_w": realtime.power,       # Current wattage
        "voltage_v": realtime.voltage,    # Current voltage
        "current_a": realtime.current,    # Current amperage
        "total_kwh": realtime.total,      # Cumulative kWh since reset
        "is_on": dev.is_on,
    }


async def read_historical_energy(
    host: str, tp_email: str, tp_password: str, year: int, month: int
) -> dict:
    """Read daily kWh totals for a given month."""
    creds = Credentials(username=tp_email, password=tp_password)
    dev = await Discover.discover_single(host, credentials=creds)
    await dev.update()

    daily = await dev.get_emeter_daily(year=year, month=month)
    monthly = await dev.get_emeter_monthly(year=year)
    return {
        "daily_kwh": daily,    # {1: 0.5, 2: 1.2, ...}
        "monthly_kwh": monthly # {1: 15.0, 2: 12.3, ...}
    }


async def control_plug(host: str, tp_email: str, tp_password: str, turn_on: bool):
    """Turn a plug on or off."""
    creds = Credentials(username=tp_email, password=tp_password)
    dev = await Discover.discover_single(host, credentials=creds)
    await dev.update()

    if turn_on:
        await dev.turn_on()
    else:
        await dev.turn_off()
```

### 1.4 Polling Strategy & Rate Limits

- **No official rate limit.** Communication is local, so there is no cloud rate limit. However, the device itself can become unresponsive if polled too aggressively.
- **Recommended polling interval:** 30-60 seconds for energy data. The device's internal measurement updates roughly every 2 seconds, but polling more than once per 10 seconds risks socket timeouts.
- **Connection lifecycle:** Each `update()` call opens a new TCP connection. For frequent polling, reuse the device object but call `await dev.update()` each time to refresh state. Do NOT hold persistent connections -- the device has limited sockets.
- **Discovery vs direct connect:** Discovery broadcasts UDP on the LAN (takes 3-5 seconds). For polling, always connect directly by IP address using `Discover.discover_single(host)`. Store the IP after initial discovery.
- **IP changes:** Devices may get new IPs after router restart. Consider re-running discovery periodically (e.g., daily) or using DHCP reservations.

### 1.5 Integration Architecture for WattWise

#### Device model changes

Add `"kasa"` as a new provider value:

```python
# In schemas.py - DeviceCreate
provider: Literal["econet", "smartthings", "kasa", "lg_thinq", "manual"]

# In models.py - Device table
# provider = "kasa"
# device_type = "smart_plug"
# external_device_id = device's IP address or device_id from python-kasa
```

#### Provider config

Store in `config/kasa.json` or in environment variables:

```json
{
  "tp_email": "user@example.com",
  "tp_password": "...",
  "poll_interval_seconds": 60,
  "devices": [
    {
      "host": "192.168.1.50",
      "alias": "Dryer Plug",
      "device_id": "80067B24..."
    }
  ]
}
```

Credentials should go in `.env`:
```
KASA_EMAIL=user@example.com
KASA_PASSWORD=your_kasa_password
```

#### New database table: PlugReading

```python
class PlugReading(Base):
    """Energy snapshot from a Kasa smart plug."""
    __tablename__ = "plug_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True,
                                                 server_default=func.now())
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    power_w: Mapped[float] = mapped_column(Float, nullable=False)       # instantaneous watts
    voltage_v: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_a: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_kwh: Mapped[float] = mapped_column(Float, nullable=False)     # cumulative
    is_on: Mapped[bool] = mapped_column(Boolean, nullable=False)
```

#### Poller integration

Add a `KasaPoller` class alongside the existing `Poller`:

```python
class KasaPoller:
    """Polls Kasa smart plugs for energy data."""

    def __init__(self, config: dict, session_factory):
        self._config = config
        self._session_factory = session_factory
        self._devices: dict[str, SmartPlug] = {}

    async def poll_all(self):
        """Poll all configured Kasa devices."""
        creds = Credentials(
            username=self._config["tp_email"],
            password=self._config["tp_password"],
        )
        for dev_cfg in self._config["devices"]:
            try:
                if dev_cfg["host"] not in self._devices:
                    dev = await Discover.discover_single(
                        dev_cfg["host"], credentials=creds
                    )
                    self._devices[dev_cfg["host"]] = dev
                else:
                    dev = self._devices[dev_cfg["host"]]

                await dev.update()
                if dev.has_emeter:
                    rt = dev.emeter_realtime
                    async with self._session_factory() as session:
                        session.add(PlugReading(
                            device_id=dev.device_id,
                            power_w=rt.power,
                            voltage_v=rt.voltage,
                            current_a=rt.current,
                            total_kwh=rt.total,
                            is_on=dev.is_on,
                        ))
                        await session.commit()
            except Exception as e:
                logger.warning("Kasa poll failed for %s: %s", dev_cfg["host"], e)
```

Register with APScheduler at 60-second intervals.

#### Energy aggregation

The existing `EnergyUsage` and `DailyEnergySummary` tables can be reused. Compute hourly kWh deltas from consecutive `PlugReading.total_kwh` values and insert into `EnergyUsage` with TOU tier tagging (same logic as EcoNet).

### 1.6 Gotchas & Limitations

1. **KLAP credentials required.** EP25 requires TP-Link cloud credentials even for local access. Users must provide their Kasa app email/password.
2. **No push/events.** Kasa devices do not support MQTT, webhooks, or push notifications. You MUST poll. There is no way to get notified when the plug turns on/off without polling.
3. **Device firmware updates.** TP-Link occasionally changes the local protocol. python-kasa keeps up but there can be gaps. Pin the package version in production.
4. **IP address instability.** Devices use DHCP. Recommend static DHCP leases or periodic re-discovery.
5. **Multi-plug awareness.** EP25 is a single-outlet plug. The KP303 power strip has multiple outlets with independent metering -- the code would need slight changes for multi-outlet devices.
6. **Thread/Matter variants.** Some EP25P models are Matter-enabled. These may not work with python-kasa's traditional discovery. Check the specific hardware version.
7. **Concurrent access.** If the Kasa mobile app and WattWise poll simultaneously, there can be occasional socket conflicts. Keep polling intervals reasonable (>= 30s).

### 1.7 Effort Estimate: EASY

- python-kasa is well-documented and async-native
- Energy monitoring data is rich and straightforward
- Local-only means no OAuth flows, no token management
- Main work: new poller class, one new DB table, add "kasa" provider to routes
- Estimated: 1-2 days of development

---

## 2. LG ThinQ (Washer/Dryer)

### 2.1 Libraries Overview

There are three Python libraries for LG ThinQ, each targeting a different API version:

| Library | ThinQ API version | Status | Notes |
|---|---|---|---|
| **wideq** | v1 | Abandoned (2019) | Original reverse-engineered client. No longer works for most devices. |
| **thinq2-python** | v2 | Community maintained | Works but requires manual OAuth flow. Mostly used via Home Assistant's `ha-smartthinq-sensors`. |
| **thinqconnect** | ThinQ Connect (v3) | Official LG SDK | Released 2024. Uses LG's official developer portal. Requires developer account approval. |

#### Recommendation: thinq2-python (via ha-smartthinq-sensors patterns)

**Why not thinqconnect (official SDK)?**
- Requires registration on LG's ThinQ Connect developer portal
- Requires device/app approval process (can take weeks)
- Designed for commercial integrations, not personal use
- Limited documentation for washer/dryer specifics

**Why not wideq?**
- Dead project, v1 API is deprecated by LG
- Most recent devices (2021+) are not supported

**Why thinq2-python / ha-smartthinq-sensors?**
- The Home Assistant integration `ha-smartthinq-sensors` (https://github.com/ollo69/ha-smartthinq-sensors) contains the most complete and actively maintained ThinQ v2 client
- The core library can be extracted/adapted for standalone use
- Handles OAuth, device discovery, and state monitoring for washers/dryers
- Covers LG models from 2019 onwards

**Alternative package:** `thinqlg` is occasionally mentioned but is not a real maintained package. The community standard is to adapt from `ha-smartthinq-sensors`.

### 2.2 Authentication Flow

LG ThinQ uses a multi-step OAuth2 flow through LG's servers. This is significantly more complex than Kasa's local approach.

```
1. User opens LG login URL in browser
2. User logs into their LG account (email + password)
3. LG redirects back with an authorization code
4. App exchanges code for access_token + refresh_token
5. App uses access_token to call ThinQ API
6. When access_token expires (~1 hour), use refresh_token to get new one
7. refresh_token is long-lived (~90 days) but can expire
```

#### OAuth details

- **Auth URL:** `https://us.lgeapi.com/oauth/1.0/authorize` (varies by region: `us`, `eu`, `kr`, etc.)
- **Token URL:** `https://us.lgeapi.com/oauth/1.0/token`
- **Redirect-based:** The user must log in via a web browser. There is NO way to authenticate with just email/password programmatically (LG blocks direct credential submission).
- **Region-specific:** The API endpoints differ by region. Users must select their region (US, EU, KR, etc.).
- **Client credentials:** The ThinQ v2 API uses hardcoded client IDs and secrets extracted from the LG ThinQ mobile app. These are embedded in `ha-smartthinq-sensors` and other clients.

#### Token storage

```python
# Tokens to persist (in DB or encrypted file, NOT in .env)
{
    "access_token": "eyJ...",
    "refresh_token": "abc123...",
    "user_number": "KR1234567890",
    "country": "US",
    "language": "en-US",
    "expires_at": 1712000000
}
```

### 2.3 Washer/Dryer Data Availability

| Data point | Available | Notes |
|---|---|---|
| Current cycle state | Yes | Idle, Running, Paused, End (cycle complete), Error |
| Remaining time | Yes | Minutes remaining in current cycle |
| Cycle type | Yes | Normal, Heavy Duty, Delicates, etc. (model-dependent) |
| Spin speed | Yes | RPM setting |
| Water temperature | Yes | Cold, Warm, Hot setting (not actual temp) |
| Door lock status | Yes | Locked/Unlocked |
| Error codes | Yes | E1, UE, OE, etc. with descriptions |
| **Energy per cycle** | **No** | LG does not report per-cycle energy consumption |
| **Real-time wattage** | **No** | ThinQ has no energy monitoring capability |
| **Cumulative kWh** | **No** | Not available through any ThinQ API |
| Smart Diagnosis | Yes | Remote diagnostic data (error history) |
| Notification events | Partial | Cycle complete notifications via polling |

**Critical finding: LG ThinQ does NOT provide energy consumption data for washers/dryers.** The integration value is limited to operational status monitoring (cycle tracking, notifications). To monitor washer/dryer energy, you would need to put the appliance on a Kasa EP25 smart plug and measure at the outlet.

### 2.4 Example Code

```python
"""LG ThinQ v2 washer/dryer integration sketch for WattWise.

NOTE: This is a simplified sketch. A production implementation should
adapt the client code from ha-smartthinq-sensors which handles all
the edge cases, regional differences, and protocol quirks.
"""
import httpx
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

# LG ThinQ v2 API constants (from ThinQ mobile app)
GATEWAY_URL = "https://route.lgthinq.com:46030/v1/service/application/gateway-uri"
API_ROOT = "https://aic-service.lgthinq.com:46030/v1"  # US region
CLIENT_ID = "LGAO221A02"  # From LG ThinQ Android app
OAUTH_SECRET_KEY = "c053c2a6ddeb7c1e"  # From LG ThinQ Android app
APP_KEY = "6V1V8H2BN5-QTFGCDMQ"
SVC_CODE = "SVC202"


@dataclass
class WasherState:
    device_id: str
    device_name: str
    state: str              # "IDLE", "RUNNING", "END", "PAUSE", "ERROR"
    remaining_time_min: int
    cycle_type: str         # "NORMAL", "HEAVY_DUTY", etc.
    spin_speed: str
    water_temp: str         # "COLD", "WARM", "HOT"
    door_locked: bool
    error_code: Optional[str]


def get_login_url(callback_url: str, country: str = "US", language: str = "en-US") -> str:
    """Generate the LG OAuth login URL. User must open this in a browser."""
    params = {
        "country": country,
        "language": language,
        "svc_list": SVC_CODE,
        "client_id": CLIENT_ID,
        "division": "ha",
        "redirect_uri": callback_url,
        "state": "wattwise_auth",
        "show_thirdparty_login": "GGL,AMZ,FBK,APPL",
    }
    return f"https://us.m.lgaccount.com/login/signIn?{urlencode(params)}"


async def exchange_code_for_token(auth_code: str, callback_url: str) -> dict:
    """Exchange OAuth authorization code for access/refresh tokens."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://us.lgeapi.com/oauth/1.0/token",
            data={
                "code": auth_code,
                "grant_type": "authorization_code",
                "redirect_uri": callback_url,
            },
            headers={
                "x-lge-appkey": APP_KEY,
                "x-lge-oauth-date": _oauth_timestamp(),
            },
        )
        return resp.json()
        # Returns: {"access_token": "...", "refresh_token": "...", "expires_in": 3600}


async def list_devices(access_token: str) -> list[dict]:
    """List all ThinQ devices on the account."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_ROOT}/service/application/dashboard",
            headers=_auth_headers(access_token),
        )
        data = resp.json()
        devices = []
        for item in data.get("result", {}).get("item", []):
            devices.append({
                "device_id": item["deviceId"],
                "name": item.get("alias", item.get("deviceType", "")),
                "type": item.get("deviceType", ""),  # 201=washer, 202=dryer
                "model": item.get("modelName", ""),
                "online": item.get("online", False),
            })
        return devices


async def get_washer_status(access_token: str, device_id: str) -> WasherState:
    """Get current washer/dryer status."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_ROOT}/service/devices/{device_id}/poll",
            headers=_auth_headers(access_token),
        )
        data = resp.json().get("result", {})

        # State mapping (numeric codes vary by model)
        state_map = {
            "0": "IDLE", "1": "IDLE", "2": "RUNNING",
            "3": "PAUSE", "4": "END", "5": "ERROR",
        }

        return WasherState(
            device_id=device_id,
            device_name="",
            state=state_map.get(str(data.get("State", "0")), "UNKNOWN"),
            remaining_time_min=int(data.get("Remain_Time_H", 0)) * 60
                               + int(data.get("Remain_Time_M", 0)),
            cycle_type=data.get("Course", "UNKNOWN"),
            spin_speed=data.get("SpinSpeed", ""),
            water_temp=data.get("WaterTemp", ""),
            door_locked=data.get("DoorLock", "0") == "1",
            error_code=data.get("Error", None),
        )


def _auth_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "x-thinq-application-key": APP_KEY,
        "x-thinq-security-key": OAUTH_SECRET_KEY,
        "Accept": "application/json",
    }


def _oauth_timestamp() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
```

### 2.5 Polling Strategy & Push Notifications

- **Polling:** ThinQ v2 supports polling via the `/poll` endpoint. LG's servers have an informal rate limit of roughly 1 request per 30 seconds per device. Exceeding this may result in temporary blocks or token invalidation.
- **Recommended polling interval:** 60 seconds when a cycle is running, 300 seconds (5 min) when idle.
- **MQTT / push notifications:** ThinQ v2 does support a push notification channel via AWS IoT (MQTT), but it requires complex setup:
  - Subscribe to LG's AWS IoT MQTT broker with device-specific certificates
  - The certificates are obtained through the ThinQ API after device registration
  - This is implemented in `ha-smartthinq-sensors` but is complex to extract standalone
  - Push events include: cycle start, cycle end, error, door open/close
- **Recommendation for v1:** Use polling only. Add MQTT push in a later iteration.

### 2.6 Integration Architecture for WattWise

#### OAuth flow for WattWise

Since ThinQ requires browser-based OAuth, the flow would be:

1. User clicks "Connect LG ThinQ" in WattWise settings
2. WattWise redirects to LG's login page (via `get_login_url()`)
3. User logs in with their LG account
4. LG redirects back to WattWise callback URL with auth code
5. WattWise exchanges code for tokens and stores them in DB
6. WattWise polls device status on a schedule

This requires:
- A new route: `GET /api/lg-thinq/auth` (redirects to LG)
- A callback route: `GET /api/lg-thinq/callback` (handles code exchange)
- Token storage in DB (new table or extend Device with a credentials column)

#### New database table: ApplianceCycle

Since ThinQ does not provide energy data, track operational cycles instead:

```python
class ApplianceCycle(Base):
    """Washer/dryer cycle tracking from LG ThinQ."""
    __tablename__ = "appliance_cycles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cycle_type: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)  # RUNNING, END, ERROR
    estimated_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Energy estimate based on appliance specs + cycle type + duration
```

#### Energy estimation (workaround)

Since ThinQ provides no energy data, two approaches:

1. **Appliance-spec estimation:** Use published energy consumption specs for the specific LG model. A Normal cycle on a typical LG washer uses ~0.15-0.3 kWh. Map cycle types to estimated consumption.
2. **Kasa plug measurement:** Place the washer/dryer on an EP25 smart plug. Correlate ThinQ cycle events with Kasa power readings for accurate per-cycle energy data.

### 2.7 Provider Config

```json
{
  "provider": "lg_thinq",
  "country": "US",
  "language": "en-US",
  "poll_interval_running": 60,
  "poll_interval_idle": 300,
  "energy_estimates": {
    "NORMAL": 0.2,
    "HEAVY_DUTY": 0.4,
    "DELICATES": 0.1,
    "QUICK_WASH": 0.08,
    "SANITIZE": 0.5
  }
}
```

### 2.8 Gotchas & Limitations

1. **No energy data.** This is the biggest limitation. ThinQ simply does not report energy consumption for washers/dryers. The integration is status-only.
2. **OAuth complexity.** Browser-based OAuth is significantly more complex than Kasa's credential pass-through. Requires callback URL, token management, and refresh logic.
3. **Regional API differences.** API endpoints, device type codes, and state values differ by region (US, EU, KR). Must handle per-region configuration.
4. **Token expiration.** Access tokens expire after ~1 hour. Refresh tokens last ~90 days but can be revoked if the user changes their LG password or if LG invalidates them server-side.
5. **No official Python SDK for personal use.** The `thinqconnect` official SDK requires developer portal approval. The community approach (adapting from `ha-smartthinq-sensors`) works but is technically reverse-engineered and could break if LG changes their API.
6. **Rate limits.** LG enforces undocumented rate limits. Aggressive polling will get your tokens invalidated.
7. **Device compatibility.** Not all LG washers/dryers support ThinQ. The appliance must have Wi-Fi and be registered in the ThinQ app.
8. **Dryer specifics.** Dryers use the same API but report different state fields (e.g., drying temperature instead of water temperature). Need separate parsing logic for device type 201 (washer) vs 202 (dryer).
9. **240V appliances and smart plugs.** Many dryers run on 240V. The EP25 is a 120V/15A plug. You CANNOT use an EP25 to monitor a 240V dryer's power. Only 120V washers and gas dryers (which use 120V) can be monitored with an EP25.

### 2.9 Effort Estimate: HARD

- Complex OAuth flow with browser redirect
- No official SDK for personal use -- must adapt from Home Assistant code
- Regional differences add complexity
- No energy data -- requires workarounds (estimation or Kasa plug pairing)
- Token lifecycle management (refresh, expiration, re-auth)
- Estimated: 5-8 days of development

---

## 3. Summary Comparison

| Aspect | TP-Link Kasa (EP25) | LG ThinQ (Washer/Dryer) |
|---|---|---|
| **Library** | `python-kasa` | Adapted from `ha-smartthinq-sensors` |
| **pip install** | `python-kasa` | No standalone package; vendor code |
| **Auth method** | TP-Link credentials (local KLAP) | OAuth2 browser redirect flow |
| **Communication** | Local network only | Cloud API (LG servers) |
| **Real-time energy** | Yes (watts, volts, amps) | No |
| **Historical energy** | Daily/monthly kWh on device | No |
| **Device control** | On/off | No (read-only for washers) |
| **Push notifications** | No (must poll) | Possible via AWS IoT MQTT (complex) |
| **Effort** | Easy (1-2 days) | Hard (5-8 days) |
| **Reliability** | Very high (local, no cloud dependency) | Moderate (cloud API, token issues) |
| **Provider value** | `"kasa"` | `"lg_thinq"` |
| **Device type value** | `"smart_plug"` | `"washer"` or `"dryer"` |

## 4. Requirements.txt Additions

```
# TP-Link Kasa smart plug control (local network)
python-kasa>=0.7.0

# LG ThinQ (no standalone package -- vendor from ha-smartthinq-sensors)
# Dependencies needed if vendoring ThinQ client code:
# httpx already in requirements.txt
# pycryptodome>=3.20.0  # For ThinQ message signing (only if needed)
```

For Kasa, add one line to `requirements.txt`:
```
python-kasa>=0.7.0
```

For LG ThinQ, there is no clean pip package. Options:
1. Vendor the ThinQ client code from `ha-smartthinq-sensors` into `src/backend/thinq_client.py` (recommended)
2. Use `pip install ha-smartthinq-sensors` but this pulls in Home Assistant dependencies (not recommended)
3. Wait for LG's `thinqconnect` SDK to become more accessible

## 5. Recommended Implementation Order

1. **Phase 1: Kasa EP25** (Easy, high value)
   - Add `python-kasa` to requirements
   - Create `src/backend/kasa_client.py` with discovery + energy reading
   - Add `PlugReading` model
   - Add `KasaPoller` to APScheduler
   - Add `"kasa"` provider to device routes
   - Add Kasa device settings UI

2. **Phase 2: LG ThinQ** (Hard, moderate value without energy data)
   - Vendor ThinQ v2 client code
   - Implement OAuth flow with callback routes
   - Add `ApplianceCycle` model
   - Add ThinQ poller for cycle tracking
   - Add `"lg_thinq"` provider to device routes
   - Add ThinQ auth flow to settings UI

3. **Phase 3: Cross-device energy correlation** (Medium, high value)
   - Pair Kasa plugs with ThinQ appliances
   - Correlate ThinQ cycle events with Kasa power readings
   - Calculate per-cycle energy cost using TOU rates
   - "Your Heavy Duty wash cycle used 0.35 kWh and cost $0.04"

## 6. Schemas Updates Needed

```python
# Add to DeviceCreate.provider Literal:
provider: Literal["econet", "smartthings", "kasa", "lg_thinq", "manual"]

# Add to DeviceCreate.device_type Literal:
device_type: Literal[
    "water_heater", "dishwasher", "washer", "dryer",
    "ev_charger", "hvac", "smart_plug", "other"
]

# New schema for Kasa discovery response:
class KasaDeviceDiscovered(BaseModel):
    ip: str
    alias: str
    model: str
    device_id: str
    has_emeter: bool
    is_on: bool

# New schema for Kasa energy reading:
class KasaEnergyReading(BaseModel):
    power_w: float
    voltage_v: Optional[float]
    current_a: Optional[float]
    total_kwh: float
    is_on: bool
    timestamp: datetime

# New schema for ThinQ washer status:
class ThinQWasherStatus(BaseModel):
    state: str  # IDLE, RUNNING, END, PAUSE, ERROR
    remaining_time_min: int
    cycle_type: str
    door_locked: bool
    error_code: Optional[str]
```
