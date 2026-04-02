# WattWise

**Smart energy, real savings.**

Monitor and optimize your Rheem EcoNet heat pump water heater with time-of-use (TOU) electricity rate awareness. Save money by shifting energy usage to off-peak hours.

## Features

- **Real-time monitoring** — Temperature, hot water availability, mode, running status
- **MQTT live control** — Change mode and setpoint directly from the app
- **Energy dashboard** — Hourly/daily/weekly/monthly usage with TOU cost breakdown
- **Savings optimizer** — AI-generated schedules that shift usage to off-peak hours
- **Data export** — CSV download at hourly or daily granularity, up to 2 years
- **Cloud sync** — Supabase-backed data sync for cross-device access
- **User accounts** — Email/password, magic link, and token refresh via Supabase Auth
- **Command palette** — Cmd+K spotlight search across pages, actions, and settings
- **Native macOS app** — Sidebar nav, WebKit rendering via pywebview
- **Dark mode** — Full light/dark theme with system-native styling

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
| `ECONET_EMAIL` | Yes | Your Rheem EcoNet account |
| `ECONET_PASSWORD` | Yes | Your Rheem EcoNet account |
| `SUPABASE_URL` | For auth/sync | Supabase Dashboard → Settings → API |
| `SUPABASE_KEY` | For auth/sync | Supabase Dashboard → Settings → API (anon key) |
| `SUPABASE_JWT_SECRET` | For auth/sync | Supabase Dashboard → Settings → API → JWT Secret |

### 3. Configure Supabase (for user accounts)

In your Supabase Dashboard → Authentication → URL Configuration:

- **Site URL:** `http://localhost:8000`
- **Redirect URLs:** `http://localhost:8000/auth/callback`

The database tables (`profiles`, `daily_energy_summary`, `energy_usage`, `heater_readings`) are created automatically via migration. All tables have Row Level Security — users can only access their own data.

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
macOS App (pywebview/WebKit)
       |
  FastAPI (Python)  <->  ClearBlade IoT (rheem.clearblade.com)
       |                        | MQTT (port 1884, TLS)
  SQLite (local)           Rheem Water Heater
       |
  Supabase (cloud sync + auth)
```

- **Backend:** Python 3.9+ / FastAPI / SQLite (local) + PostgreSQL (Supabase cloud)
- **Frontend:** Vanilla HTML/JS / Chart.js / Jinja2 / inline SVG icons
- **Native app:** pywebview (WKWebView on macOS)
- **Auth:** Supabase Auth (email/password, magic link, JWT verification)
- **Cloud sync:** PostgREST API with RLS policies

## Project Structure

```
src/
  backend/
    main.py          # FastAPI app entrypoint
    auth.py          # JWT verification middleware
    config.py        # Settings (pydantic-settings + .env)
    routes_api.py    # REST API endpoints
    routes_auth.py   # Login, logout, auth callback
    routes_pages.py  # HTML page routes
    supabase_sync.py # Cloud data sync
    models.py        # SQLAlchemy models
    schemas.py       # Pydantic request/response schemas
    optimizer.py     # TOU schedule optimizer
    poller.py        # Background data polling
    econet_client.py # ClearBlade/EcoNet API client
  frontend/
    templates/       # Jinja2 HTML templates
    static/
      css/style.css  # Full stylesheet (light/dark themes)
      js/auth.js     # Supabase auth client + token management
macos/
  wattwise_app.py    # Native macOS windowed app (pywebview)
  setup.py           # py2app build config
config/
  .env.example       # Environment variable template
  default_rates.yaml # Seattle City Light TOU rates
```

## Supported Devices

| Device | Firmware | Status |
|--------|----------|--------|
| Rheem Heat Pump Water Heater Gen5 | RH-WIFI-0500-15 | Fully supported |
| Other Rheem EcoNet devices | Various | Planned |

## Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Production-ready releases |
| `dev` | Integration branch for features |
| `release/*` | Release candidates |
| `feature/*` | Individual features |
| `hotfix/*` | Urgent production fixes |

## License

Licensed under the [Business Source License 1.1](LICENSE).

- **Free for:** Personal use, internal business use, academic/research use
- **Not free for:** Running a competing water heater monitoring SaaS
- **Converts to** Apache 2.0 on April 1, 2030

## Legal

WattWise is an independent product. Not affiliated with, endorsed by, or sponsored by Rheem Manufacturing Company, EcoNet, or ClearBlade, Inc. All trademarks are property of their respective owners.

This software includes code derived from [pyeconet](https://github.com/w1ll1am23/pyeconet) (MIT License). See [NOTICES](NOTICES) for full attributions.

## Author

Built by [Charles Amyot](mailto:charles@wattwise.app) in Seattle, WA.
