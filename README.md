# HeatSmart

**Smart heating, smart savings.**

Monitor and optimize your Rheem EcoNet heat pump water heater with time-of-use (TOU) electricity rate awareness. Save money by shifting energy usage to off-peak hours.

## Features

- **Real-time monitoring** — Temperature, hot water availability, mode, running status
- **MQTT control** — Change mode and setpoint directly from the app
- **Energy dashboard** — Hourly/daily/weekly/monthly usage with TOU cost breakdown
- **Schedule simulator** — Drag blocks to see real-time cost impact with Day/Week/Month/Year projections
- **TOU optimizer** — Auto-generates cost-saving schedules with OFF periods during peak hours
- **Data export** — CSV download at hourly or daily granularity, up to 2 years
- **Dark mode** — Full light/dark theme support
- **PWA** — Install on iPhone/Android as a native-feeling app

## Quick Start

```bash
git clone https://github.com/charlesamyot/HeatSmart.git
cd HeatSmart
pip install -r requirements.txt
cp config/.env.example config/.env
# Edit config/.env with your EcoNet credentials
python -m uvicorn src.backend.main:app --reload
# Open http://localhost:8000
```

## Architecture

```
Browser/PWA  <->  FastAPI (Python)  <->  ClearBlade IoT (rheem.clearblade.com)
                       |                        | MQTT (port 1884, TLS)
                  Supabase DB              Rheem Water Heater
```

- **Backend:** Python 3.9+ / FastAPI / PostgreSQL (Supabase) / paho-mqtt
- **Frontend:** Vanilla HTML/JS / Chart.js / Jinja2
- **Deployment:** Render.com (free tier)
- **Auth:** Supabase (email + magic link)
- **Payments:** Stripe (donation + premium unlock)

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

HeatSmart is an independent product. Not affiliated with, endorsed by, or sponsored by Rheem Manufacturing Company, EcoNet, or ClearBlade, Inc. All trademarks are property of their respective owners.

This software includes code derived from [pyeconet](https://github.com/w1ll1am23/pyeconet) (MIT License). See [NOTICES](NOTICES) for full attributions.

## Author

Built by [Charles Amyot](mailto:charles@heatsmart.app) in Seattle, WA.
