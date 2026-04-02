# WattWise

**Smart energy, real savings.**

WattWise is a whole-home energy savings platform that monitors and optimizes your connected appliances using time-of-use (TOU) electricity rates. Connect your Rheem EcoNet water heater and other devices, organize them by location, look up your utility's rate plan, and let the savings optimizer shift usage to cheaper off-peak hours.

## Features

- **Multi-device support** -- water heaters, HVAC, EV chargers, dishwashers, washers, dryers, and more
- **Location management** -- organize devices across multiple homes or properties with utility auto-detection
- **TOU rate service** -- look up your utility rate plan by ZIP code or browse Country > Region > Utility > Rate Plan
- **Real-time monitoring** -- temperature, hot water availability, mode, running status via MQTT
- **MQTT live control** -- change mode and setpoint directly from the app
- **Energy dashboard** -- hourly/daily/weekly/monthly usage with TOU cost breakdown
- **Savings optimizer** -- AI-generated schedules that shift usage to off-peak hours with monthly/yearly savings estimates
- **Data export** -- CSV download at hourly or daily granularity, up to 2 years
- **Supabase authentication** -- email/password, magic link, password reset, auto-refresh tokens
- **Cloud sync** -- Supabase-backed data sync for cross-device access
- **Command palette** -- Cmd+K spotlight search across pages, actions, and settings
- **Native macOS app** -- sidebar nav, WebKit rendering via pywebview
- **Dark mode** -- full light/dark theme with system-native styling

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/charlesamyot/WattWise.git
cd WattWise
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp config/.env.example config/.env
```

Edit `config/.env` with your credentials:

| Variable | Required | Source |
|----------|----------|--------|
| `ECONET_EMAIL` | For EcoNet devices | Your Rheem EcoNet account |
| `ECONET_PASSWORD` | For EcoNet devices | Your Rheem EcoNet account |
| `SUPABASE_URL` | For auth/sync/TOU | Supabase Dashboard > Settings > API |
| `SUPABASE_KEY` | For auth/sync/TOU | Supabase Dashboard > Settings > API (anon key) |
| `SUPABASE_JWT_SECRET` | For auth | Supabase Dashboard > Settings > API > JWT Secret |

### 3. Configure Supabase (for user accounts and TOU lookup)

In your Supabase Dashboard > Authentication > URL Configuration:

- **Site URL:** `http://localhost:8000`
- **Redirect URLs:** `http://localhost:8000/auth/callback`

Database tables are created via migration. TOU rate data (countries, regions, utilities, rate plans, rate blocks) is stored in Supabase and queried via PostgREST. All user tables have Row Level Security.

### 4. Run

**Web server (development):**
```bash
python -m uvicorn src.backend.main:app --host 127.0.0.1 --port 8000 --reload
# Open http://localhost:8000
```

**Native macOS app:**
```bash
python macos/wattwise_app.py
```

**Build macOS .app bundle:**
```bash
cd macos
python setup.py py2app
# Output: macos/dist/WattWise.app
```

Or double-click `start.command` from Finder.

## Architecture

```
User > Location > Device > Data

macOS App (pywebview/WKWebView)
       |
  FastAPI (Python)  <->  ClearBlade IoT (rheem.clearblade.com)
       |                        | MQTT (port 1884, TLS)
  SQLite (local)           Connected Devices
       |
  Supabase (auth + TOU rates + cloud sync)
```

- **Backend:** Python 3.9+ / FastAPI / SQLite (local) + PostgreSQL (Supabase cloud)
- **Frontend:** Vanilla HTML/JS / Chart.js / Jinja2 / inline SVG icons
- **Native app:** pywebview (WKWebView on macOS)
- **Auth:** Supabase Auth (email/password, magic link, JWT verification)
- **TOU Service:** Supabase PostgREST (country/region/utility/rate plan lookup)
- **Cloud sync:** PostgREST API with RLS policies

## Project Structure

```
src/
  backend/
    main.py              # FastAPI app entrypoint, router registration, lifespan
    auth.py              # JWT verification middleware (Supabase tokens)
    config.py            # Settings (pydantic-settings + .env)
    routes_api.py        # Core REST API (status, energy, control, schedule, config)
    routes_auth.py       # Login, signup, logout, auth callback pages
    routes_devices.py    # Multi-device CRUD + live status
    routes_locations.py  # Location management CRUD + utility lookup
    routes_pages.py      # HTML page routes (Jinja2 templates)
    routes_tou.py        # TOU rate lookup (Supabase PostgREST proxy)
    models.py            # SQLAlchemy ORM models
    schemas.py           # Pydantic request/response schemas
    optimizer.py         # TOU schedule optimizer
    poller.py            # Background data polling
    econet_client.py     # ClearBlade/EcoNet API + MQTT client
    database.py          # SQLAlchemy async engine + session
    supabase_sync.py     # Cloud data sync
  frontend/
    templates/
      base.html          # Layout: sidebar, command palette, auth, connection status
      dashboard.html     # Main monitoring dashboard
      devices.html       # Multi-device management with location assignment
      device_detail.html # Per-device info, credentials, preferences
      schedule.html      # Schedule editor + optimizer
      history.html       # Energy history charts + export
      settings.html      # Locations, account, TOU rates, debug tools
      help.html          # Documentation and legal
      login.html         # Sign in (email, magic link)
      signup.html        # Create account
      auth_callback.html # OAuth/magic link redirect handler
    static/
      css/style.css      # Full stylesheet (light/dark themes, sidebar, components)
      js/auth.js         # Supabase auth client + token management + fetch interceptor
      js/dashboard.js    # Dashboard-specific logic
macos/
  wattwise_app.py        # Native macOS windowed app (pywebview + JS bridge)
  setup.py               # py2app build config
config/
  .env.example           # Environment variable template
  default_rates.yaml     # Seattle City Light TOU rates (seed data)
docs/
  MOBILE_APP_PLAN.md     # React Native mobile app strategy
  TOU_RATE_RESEARCH.md   # TOU rate data research
```

## API Endpoints

### Core API (`/api`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | Current device status |
| GET | `/api/device` | Full device info (firmware, location, health) |
| POST | `/api/refresh` | Force re-poll from EcoNet |
| GET | `/api/energy?range=day\|week\|month` | Energy data with TOU breakdown |
| POST | `/api/setpoint` | Set target temperature |
| POST | `/api/mode` | Change operating mode |
| GET | `/api/schedule` | Get active schedule entries |
| PUT | `/api/schedule` | Update schedule for a day |
| POST | `/api/schedule/copy` | Copy schedule between days |
| POST | `/api/schedule/optimize` | Generate optimized schedule |
| POST | `/api/schedule/apply` | Apply optimizer suggestions |
| GET | `/api/config/tou-rates` | Get local TOU rate tiers |
| PUT | `/api/config/tou-rates` | Update local TOU rate tiers |
| GET | `/api/config/preferences` | Get comfort preferences |
| PUT | `/api/config/preferences` | Update comfort preferences |
| POST | `/api/config/credentials` | Update EcoNet credentials |
| GET | `/api/config/status` | Connection and MQTT status |
| GET | `/api/export?granularity=hourly\|daily&start=...&end=...` | CSV export |
| GET | `/api/backfill-status` | Background data loading progress |

### Devices (`/api/devices`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/devices` | List all devices |
| POST | `/api/devices` | Add a device (econet, smartthings, manual) |
| GET | `/api/devices/{id}` | Get device by ID |
| PUT | `/api/devices/{id}` | Update device (name, location, active) |
| DELETE | `/api/devices/{id}` | Remove a device |
| GET | `/api/devices/{id}/status` | Live provider status |

### Locations (`/api/locations`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/locations` | List all locations |
| POST | `/api/locations` | Create a location (auto utility lookup) |
| PUT | `/api/locations/{id}` | Update a location |
| DELETE | `/api/locations/{id}` | Delete a location |
| POST | `/api/locations/{id}/set-primary` | Set as primary location |

### TOU Rate Lookup (`/api/tou`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/tou/countries` | List countries with TOU data |
| GET | `/api/tou/regions?country=US` | List regions for a country |
| GET | `/api/tou/utilities?region_id=1` | List utilities for a region |
| GET | `/api/tou/rates?utility_id=1` | Get rate plans and blocks |
| GET | `/api/tou/lookup?zip=98101` | Look up utility by ZIP code |

### Auth (`/api/auth`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/auth/me` | Current user info or 401 |
| GET | `/login` | Login page |
| GET | `/signup` | Signup page |
| GET | `/auth/callback` | OAuth/magic link callback |
| GET | `/logout` | Clear session and redirect |

## Supported Devices

| Device | Firmware | Status |
|--------|----------|--------|
| Rheem Heat Pump Water Heater Gen5 | RH-WIFI-0500-15 | Fully supported |
| Other Rheem EcoNet devices | Various | Basic support |
| Manual entry devices | N/A | Usage tracking only |
| Samsung SmartThings | Various | Planned |

## Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Production-ready releases |
| `dev-v1.1` | Integration branch for v1.1 features |
| `release/*` | Release candidates |
| `features/*` | Individual features |
| `fix/*` | Bug fixes |

## License

Licensed under the [Business Source License 1.1](LICENSE).

- **Free for:** Personal use, internal business use, academic/research use
- **Not free for:** Running a competing energy monitoring SaaS
- **Converts to** Apache 2.0 on April 1, 2030

## Legal

WattWise is an independent product. Not affiliated with, endorsed by, or sponsored by Rheem Manufacturing Company, EcoNet, or ClearBlade, Inc. All trademarks are property of their respective owners.

This software includes code derived from [pyeconet](https://github.com/w1ll1am23/pyeconet) (MIT License). See [NOTICES](NOTICES) for full attributions.

## Author

Built by [Charles Amyot](mailto:charles@wattwise.app) in Seattle, WA.
