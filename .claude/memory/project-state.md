# HeatSmart — Project State (as of April 1, 2026)

## What This Is
A water heater monitoring & TOU cost optimization web app for Rheem EcoNet heat pump water heaters. Built as a local Python/FastAPI server with vanilla HTML/JS frontend. Being transformed into a multi-tenant SaaS with Supabase auth, Stripe payments, and Render.com deployment.

## Owner
Charles Amyot, Seattle WA 98107. Device: Rheem Gen5 HPWH, firmware RH-WIFI-0500-15.

## Repo
https://github.com/charlesamyot/HeatSmart — BSL 1.1 license

---

## What's Working (v1.0)

### Backend
- **MQTT connected** to rheem.clearblade.com:1884 (stays connected, no more rc=7 disconnects)
- **Mode + setpoint control** via MQTT publish — confirmed working, reflects in EcoNet app
- **Energy data** via REST `dynamicAction` with pyeconet's exact format (uppercase `ACTION`, `device_name`, timezone-aware dates)
- **Energy backfill** on startup: phase 1 (today hourly), phase 2 (12 monthly chunks), phase 3 (30 days hourly detail)
- **State polling** every 5 min (REST fallback), energy polling every 30 min
- **Heating cycle detection** from running state transitions
- **TOU tier classification** with Seattle City Light rates + US federal holiday detection
- **Hot water parsing** from image filenames (4 levels: 0/33/66/100% per pyeconet mapping)

### Frontend
- **Dashboard**: Status cards, mode popover (button+descriptions), setpoint +/-, running indicator, energy chart (today/yesterday), refresh button
- **Schedule Simulator**: Drag blocks on 24h timeline, real-time cost comparison (Day/Week/Month/Year tabs), TOU overlay, auto-optimizer with OFF periods, per-tier savings breakdown table
- **History**: Unified toolbar (Hourly/6-Hour/Daily/Weekly/Monthly × Today/Yesterday/7d/30d/90d/1y), stats bar (total/avg/peak/low/off-peak%), collapsible sections, CSV export
- **Settings**: Device info card (name/location/firmware/MQTT/serial/MAC), credentials with show/hide, comfort preferences, TOU heatmap editor, debug tools drawer
- **Help**: Collapsible FAQ sections, legal disclaimers, feedback buttons, about page
- **Dark mode**, toast notifications, fetchWithTimeout, connection icon with hover popover

### macOS App
- `HeatSmart.app` — menu bar app (🔥 icon), runs server in background, auto-opens browser
- Settings dialog to change port (default 7777)
- Built with py2app + rumps

---

## Critical API Details (DO NOT CHANGE WITHOUT TESTING)

### Authentication
```
POST https://rheem.clearblade.com/api/v/1/user/auth
```
- Response has TWO IDs: `user_id` (ClearBlade) and `options.account_id` (Rheem)
- **MQTT topics use `options.account_id`** — using `user_id` causes immediate disconnect (rc=7)

### MQTT
- Host: rheem.clearblade.com, Port: **1884**
- Auth: `username_pw_set(user_token, password=SYSTEM_KEY)` — NOT token as both args
- Paho 2.x: MUST use `CallbackAPIVersion.VERSION1`
- Client ID must be unique (not match phone app format)
- Subscribe: `user/{rheem_account_id}/device/reported` and `desired`
- Publish control: `{"transactionId":"ANDROID_...", "device_name":"...", "serial_number":"...", "@MODE": 1}`

### Energy Usage API (WORKING)
```
POST /api/v/1/code/{key}/dynamicAction
{
  "ACTION": "waterheaterUsageReportView",   ← UPPERCASE
  "device_name": "11980437215467865",       ← numeric ClearBlade ID
  "serial_number": "07-0e-17-0c-2c-32-c0-c8-01",
  "start_date": "2026-04-01T00:00:00.999",
  "end_date": "2026-04-01T23:59:59.999",
  "usage_type": "energyUsage"               ← or "waterUsage"
}
```
- Single-day returns hourly: `{name: hour, value: kwh}`
- Multi-day returns daily: `{name: day_of_month, value: kwh}`

### What Does NOT Work
- All lowercase `action` dynamicAction calls → "Bad Request"
- All `code/` endpoints → 500 "code_meta not found"
- REST messaging publish → "does not have permissions"
- Schedule retrieval from device → no working endpoint found
- MQTT doesn't receive unsolicited pushes (mqtt_message_count stays 0)

### Device Data Format
- `@`-prefixed keys at top level (NOT nested under `properties`)
- `@MODE.value`: 0=Off, 1=Energy Saver, 2=Heat Pump, 3=High Demand, 4=Electric, 5=Vacation
- `@HOTWATER`: image filename → `ten_percent`=33%, `fourty_percent`=66%, `hundread_percent`=100%
- `@RUNNING`: empty=""idle, "Compressor Running"=active
- `device_name` (numeric "11980437215467865") vs `serial_number` (dash-separated)

### Timezone
- ClearBlade registers device as `America/New_York` but device is in Seattle (PT)
- Currently storing energy hours as-is from API (no conversion) — works for display
- Config has `device_timezone` and `local_timezone` fields for future use

---

## What's Scaffolded (Not Yet Wired)

### Supabase Auth
- `src/backend/auth.py` — JWT verification middleware (reads from Authorization header or cookie)
- `src/backend/supabase_client.py` — Fernet credential encryption
- `src/backend/routes_auth.py` — Login/logout page routes
- `src/frontend/static/js/auth.js` — Supabase REST auth (no SDK), auto-injects Bearer token on /api/ calls
- `src/frontend/templates/login.html` — Email/password + magic link sign in

### Stripe Payments
- `src/backend/routes_payments.py` — Checkout session creation + webhook handler
- Premium unlock ($9.99) + donation flow scaffolded

### PWA
- `src/frontend/static/manifest.json` — App name, icons, standalone display
- `src/frontend/static/sw.js` — Service worker (cache-first static, network-first API)
- Missing: actual icon files in `static/icons/`

### Render Deployment
- `render.yaml` — Blueprint with env vars
- `Procfile` — uvicorn start command

---

## Remaining Work (Priority Order)

1. **Supabase integration** — Wire auth middleware to all routes, create PostgreSQL tables, migrate from SQLite
2. **Multi-tenant data** — Add user_id to all DB queries, per-user MQTT connections
3. **Device abstraction** — DeviceProvider base class, add/remove/rename devices in settings
4. **PWA mobile CSS** — Bottom nav, safe areas, touch targets, 480px breakpoint
5. **Stripe wiring** — Connect checkout to Supabase profile (is_premium flag)
6. **Deploy to Render** — Push, configure env vars, test
7. **iPhone testing** — Add to Home Screen, verify all pages at 393px

---

## File Inventory (43 files)

### Backend (src/backend/)
| File | Lines | Purpose |
|------|-------|---------|
| main.py | ~120 | FastAPI app, lifespan, CORS, security headers |
| config.py | ~80 | Pydantic settings (EcoNet, Supabase, Stripe, TZ) |
| econet_client.py | ~700 | ClearBlade REST+MQTT client, device parsing |
| poller.py | ~300 | APScheduler: state/energy polling, backfill, cycles |
| optimizer.py | ~400 | TOU schedule optimizer (5 candidates, OFF periods) |
| routes_api.py | ~400 | All REST endpoints (status, energy, control, schedule, config, export, debug) |
| routes_pages.py | ~50 | Jinja2 HTML page routes |
| routes_auth.py | ~25 | Login/logout (scaffolded) |
| routes_payments.py | ~80 | Stripe checkout/webhook (scaffolded) |
| auth.py | ~55 | JWT verification middleware (scaffolded) |
| supabase_client.py | ~40 | Fernet encryption for credentials |
| models.py | ~130 | SQLAlchemy models (8 tables) |
| database.py | ~40 | Async SQLite engine |
| schemas.py | ~170 | Pydantic request/response schemas |

### Frontend (src/frontend/)
| File | Purpose |
|------|---------|
| templates/base.html | Nav, theme, connection popover, toast, backfill bar |
| templates/dashboard.html | Status cards, mode popover, energy chart |
| templates/schedule.html | Simulator with cost impact tabs |
| templates/history.html | Unified toolbar, stats, charts, export |
| templates/settings.html | Device card, credentials, TOU heatmap, debug |
| templates/help.html | FAQ, disclaimers, feedback, about |
| templates/login.html | Auth page (scaffolded) |
| static/css/style.css | Light/dark theme, all components |
| static/js/dashboard.js | Status, mode popover, charts |
| static/js/schedule.js | Timeline/list/week views (old, replaced by simulator) |
| static/js/auth.js | Supabase REST auth (scaffolded) |

### Config & Legal
| File | Purpose |
|------|---------|
| LICENSE | BSL 1.1 (converts to Apache 2.0 on 2030-04-01) |
| PRIVACY.md | Full privacy policy |
| NOTICES | Third-party attributions (pyeconet MIT, Chart.js) |
| config/.env.example | All env vars documented |
| config/default_rates.yaml | Seattle City Light TOU rates + holidays |
| render.yaml | Render.com deployment blueprint |
| Procfile | uvicorn start command |

### Tests (34 passing)
- test_econet_client.py — Auth, equipment parsing, setpoint bounds
- test_optimizer.py — Schedule optimization, TOU tiers, cost estimates
- test_poller_tou.py — TOU tier logic, holiday detection (including floating holidays)

---

## UX Preferences (Charles)

- Button+popover for mode selection (not dropdown)
- Unified toolbar for history (not scattered controls)
- Toast notifications (not browser alerts)
- Debug tools in collapsible drawer on Settings (not hidden)
- Connection status as icon with hover popover (not text badge)
- Help as ? button in nav (not full menu item)
- Dark mode preferred
- Collapsible sections with arrows in History
- Table footers with total/average rows
- Year labels on dates from previous years
