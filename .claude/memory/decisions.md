# Key Decisions Made

## License: BSL 1.1
- Free for personal/internal/academic use
- Competing SaaS requires commercial license
- Converts to Apache 2.0 on April 1, 2030
- pyeconet MIT attribution in NOTICES file

## Tech Stack
- Backend: Python 3.9 / FastAPI / SQLite (migrating to Supabase PostgreSQL)
- Frontend: Vanilla HTML/JS + Chart.js (no framework — keeps bundle small)
- Auth: Supabase (email + magic link + Google)
- Payments: Stripe (soft donation prompt + $9.99 premium unlock)
- Hosting: Render.com free tier
- macOS: py2app + rumps menu bar app

## TOU Rates: Seattle City Light
- Peak: 5-9 PM Mon-Sat $0.1674/kWh
- Mid-Peak: 6 AM-5 PM & 9 PM-midnight Mon-Sat, all day Sun/holidays $0.1465/kWh
- Off-Peak: midnight-6 AM every day $0.0837/kWh
- Base charge: $0.4103/day

## Monetization
- Free tier: full monitoring, basic optimizer, 7-day history
- Premium ($9.99 one-time): CSV export, advanced optimizer, full history
- Soft donation prompt after optimizer runs (10% of estimated savings)

## Branch Strategy
- main: production releases
- dev: integration
- release/*: release candidates
- feature/*: individual features
- hotfix/*: urgent fixes
