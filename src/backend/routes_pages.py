"""HTML page routes — serves Jinja2 templates."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import select_autoescape

from .config import get_settings

router = APIRouter()

_templates = Jinja2Templates(
    directory="src/frontend/templates",
    autoescape=select_autoescape(
        enabled_extensions=("html", "xml"),
        default_for_string=True,
        default=True,
    ),
)


def _ctx(request: Request, **extra) -> dict:
    """Build template context with Supabase config and request."""
    s = get_settings()
    return {
        "request": request,
        "supabase_url": s.supabase_url,
        "supabase_key": s.supabase_key,
        **extra,
    }


@router.get("/", response_class=RedirectResponse)
async def root():
    return RedirectResponse("/dashboard")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return _templates.TemplateResponse("dashboard.html", _ctx(request))


@router.get("/schedule", response_class=HTMLResponse)
async def schedule(request: Request):
    return _templates.TemplateResponse("schedule.html", _ctx(request))


@router.get("/devices", response_class=HTMLResponse)
async def devices(request: Request):
    return _templates.TemplateResponse("devices.html", _ctx(request))


@router.get("/devices/{device_id}", response_class=HTMLResponse)
async def device_detail(request: Request, device_id: str):
    return _templates.TemplateResponse("device_detail.html", _ctx(request, device_id=device_id))


@router.get("/settings", response_class=HTMLResponse)
async def settings(request: Request):
    return _templates.TemplateResponse("settings.html", _ctx(request))


@router.get("/history", response_class=HTMLResponse)
async def history(request: Request):
    return _templates.TemplateResponse("history.html", _ctx(request))


@router.get("/help", response_class=HTMLResponse)
async def help_page(request: Request):
    return _templates.TemplateResponse("help.html", _ctx(request))
