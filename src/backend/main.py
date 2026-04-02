"""FastAPI application entrypoint."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .database import close_db, init_db
from .econet_client import EcoNetClient
from .poller import Poller
from .routes_api import router as api_router, set_client
from .routes_pages import router as pages_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_poller: Poller | None = None
_client: EcoNetClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _poller, _client
    settings = get_settings()

    # Database
    await init_db()
    logger.info("Database initialized at %s", settings.database_path)

    # Seed TOU rates if table is empty
    await _seed_tou_rates()

    # EcoNet client
    _client = EcoNetClient(settings.econet_email, settings.econet_password)
    if settings.has_credentials:
        logged_in = await _client.login()
        if logged_in:
            await _client.get_equipment()
        else:
            logger.warning("EcoNet login failed — update credentials in settings")
    else:
        logger.warning("EcoNet credentials not configured — visit /settings to add them")

    # Background poller
    from .database import _session_factory
    if _session_factory is not None:
        _poller = Poller(_client, _session_factory)
        _poller.start()

    set_client(_client, _poller)

    yield

    # Shutdown
    if _poller:
        _poller.stop()
    if _client:
        await _client.close()
    await close_db()
    logger.info("Shutdown complete")


app = FastAPI(
    title="WattWise",
    description="Smart energy, real savings. Monitor and optimize your home appliances with TOU rate awareness.",
    version="1.1.0",
    lifespan=lifespan,
)

# Trusted hosts — localhost only
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])

# CORS — localhost only (never open to *)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    """Add security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response

# Static files
static_path = Path("src/frontend/static")
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

app.include_router(api_router)
app.include_router(pages_router)


async def _seed_tou_rates() -> None:
    """Insert default Seattle City Light TOU rates if table is empty."""
    from sqlalchemy import select, func
    from .database import _session_factory
    from .models import TOURateEntry

    if _session_factory is None:
        return

    async with _session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(TOURateEntry))
        if count and count > 0:
            return

        # Seattle City Light — confirmed TOU schedule
        defaults = [
            # Off-peak: midnight–6 AM every day
            TOURateEntry(name="off_peak", start_hour=0, end_hour=6,
                         rate_per_kwh=0.0837, days_of_week="0,1,2,3,4,5,6",
                         holiday_exception=False),
            # Peak: 5 PM–9 PM Mon–Sat (except holidays)
            TOURateEntry(name="peak", start_hour=17, end_hour=21,
                         rate_per_kwh=0.1674, days_of_week="0,1,2,3,4,5",
                         holiday_exception=True),
            # Mid-peak: 6 AM–5 PM Mon–Sat
            TOURateEntry(name="mid_peak", start_hour=6, end_hour=17,
                         rate_per_kwh=0.1465, days_of_week="0,1,2,3,4,5",
                         holiday_exception=False),
            # Mid-peak: 9 PM–midnight Mon–Sat
            TOURateEntry(name="mid_peak", start_hour=21, end_hour=24,
                         rate_per_kwh=0.1465, days_of_week="0,1,2,3,4,5",
                         holiday_exception=False),
            # Mid-peak: 6 AM–midnight Sundays and holidays
            TOURateEntry(name="mid_peak", start_hour=6, end_hour=24,
                         rate_per_kwh=0.1465, days_of_week="6",
                         holiday_exception=False),
        ]
        session.add_all(defaults)
        await session.commit()
        logger.info("Seeded default Seattle City Light TOU rates")
