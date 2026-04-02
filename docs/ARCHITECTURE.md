# WattWise Architecture

## Overview

WattWise is a whole-home energy savings platform built as a local-first web application with optional cloud sync. It follows a layered architecture with clear separation between the backend API, frontend templates, and external service integrations.

## Data Hierarchy

```
User (Supabase Auth)
  |
  +-- Location (home, office, rental)
  |     |
  |     +-- Device (water heater, HVAC, EV charger)
  |           |
  |           +-- HeaterReading (5-min state snapshots)
  |           +-- EnergyUsage (hourly kWh + TOU tier)
  |           +-- DailyEnergySummary (aggregated daily totals)
  |           +-- WaterUsage (hourly gallons)
  |
  +-- ScheduleEntry (per day-of-week setpoint/mode)
  +-- TOURateEntry (local rate tiers)
  +-- ComfortPreferences (optimizer inputs)
```

## System Architecture

```
+------------------+       +------------------+       +------------------+
|   macOS App      |       |   Web Browser    |       |   Mobile App     |
|   (pywebview)    |       |                  |       |   (React Native) |
+--------+---------+       +--------+---------+       +--------+---------+
         |                          |                          |
         +----------+---+-----------+-----future---------------+
                    |
              HTTP (localhost:8000)
                    |
         +----------+-----------+
         |    FastAPI Backend    |
         |                      |
         |  routes_api.py       |  Core API (status, energy, control, schedule)
         |  routes_devices.py   |  Multi-device CRUD
         |  routes_locations.py |  Location management
         |  routes_tou.py       |  TOU rate lookup (Supabase proxy)
         |  routes_auth.py      |  Auth pages (login, signup, callback)
         |  routes_pages.py     |  HTML page rendering (Jinja2)
         |                      |
         |  econet_client.py    |  ClearBlade REST + MQTT client
         |  poller.py           |  Background state polling (5-min interval)
         |  optimizer.py        |  TOU schedule optimization engine
         |  auth.py             |  JWT verification (Supabase tokens)
         |  supabase_sync.py    |  Cloud data sync
         +----+-----+-----+----+
              |     |     |
     +--------+  +--+--+  +--------+
     |           |     |           |
  SQLite      Supabase   ClearBlade IoT
  (local)     (cloud)    (Rheem MQTT)
```

## Local Database (SQLite)

The local SQLite database (`config/econet_data.db`) stores all operational data. Tables:

| Table | Purpose |
|-------|---------|
| `heater_readings` | Raw device state snapshots (temp, mode, running) |
| `energy_usage` | Hourly energy consumption with TOU cost |
| `daily_energy_summary` | Aggregated daily totals with peak/mid/off-peak breakdown |
| `water_usage` | Hourly water consumption |
| `schedule_entries` | User and optimizer schedule rules |
| `tou_rate_entries` | Local TOU rate tiers (seeded from config) |
| `comfort_preferences` | User preferences for the optimizer |
| `devices` | Registered devices with provider and location_id |
| `locations` | User-defined physical locations |

## Supabase Schema (Cloud)

Supabase serves three purposes:

### 1. Authentication
- Email/password signup and login
- Magic link (OTP) sign-in
- JWT tokens verified server-side via `auth.py`
- Token refresh handled client-side in `auth.js`

### 2. TOU Rate Database
Queried via PostgREST through `routes_tou.py`:

| Table | Purpose |
|-------|---------|
| `tou_countries` | Countries with TOU data |
| `tou_regions` | States/provinces per country |
| `tou_utilities` | Utility companies per region |
| `tou_rate_plans` | Rate plan definitions per utility |
| `tou_rate_blocks` | Individual rate blocks (tier, hours, price, days) |
| `tou_zip_lookup` | ZIP code to utility mapping |

### 3. Cloud Sync
- `profiles` -- user profile data
- `daily_energy_summary` -- synced daily totals
- `energy_usage` -- synced hourly data
- `heater_readings` -- synced state snapshots

All tables have Row Level Security (RLS) policies so users can only access their own data.

## API Design

The API is organized into router modules, each with a clear prefix:

| Router | Prefix | Responsibility |
|--------|--------|----------------|
| `routes_api` | `/api` | Core device control, energy, schedule, config |
| `routes_devices` | `/api/devices` | Multi-device CRUD and live status |
| `routes_locations` | `/api/locations` | Location CRUD and primary selection |
| `routes_tou` | `/api/tou` | TOU rate lookup (Supabase proxy) |
| `routes_auth` | (various) | Auth pages and `/api/auth/me` |
| `routes_pages` | (various) | HTML template rendering |

### Auth Flow
1. User visits `/login` -- rendered by `routes_auth`
2. Client-side JS (`auth.js`) calls Supabase Auth REST API directly
3. On success, token stored in localStorage + cookie
4. `auth.js` overrides `fetch()` to inject `Authorization: Bearer <token>` on `/api/` calls
5. Server-side `auth.py` verifies JWT on protected endpoints

### Device Data Flow
1. `econet_client.py` authenticates with ClearBlade (Rheem's IoT platform)
2. MQTT connection established for real-time updates
3. `poller.py` runs background polling every 5 minutes as fallback
4. State snapshots saved to `heater_readings` table
5. Energy data aggregated into `energy_usage` and `daily_energy_summary`

## Frontend Architecture

Single-page sections rendered as Jinja2 templates with inline JavaScript:

- `base.html` -- layout shell with sidebar, command palette (Cmd+K), connection status, auth state, theme toggle
- Each page extends `base.html` and adds its own `{% block content %}` and `{% block scripts %}`
- No build step -- vanilla JS, no bundler
- Chart.js for data visualization
- SVG icons inline (no icon font dependency)
- CSS custom properties for light/dark theming

## Native macOS App

`macos/wattwise_app.py` wraps the web app in a native window:

1. Starts the FastAPI/uvicorn server as a subprocess
2. Creates a pywebview window (WKWebView on macOS)
3. Exposes a `WattWiseBridge` JS API (`window.pybridge`) for native functionality
4. Architecture mirrors iOS WKScriptMessageHandler for future portability

## Security Model

- Credentials stored in `config/.env` with `chmod 0600`
- Supabase JWT verification on protected API endpoints
- CORS restricted to localhost only
- Trusted hosts middleware (localhost/127.0.0.1 only)
- Security headers on all responses (X-Content-Type-Options, X-Frame-Options, etc.)
- Input validation via Pydantic schemas at API boundaries
