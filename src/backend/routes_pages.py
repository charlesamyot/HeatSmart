"""HTML page routes — serves Jinja2 templates."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import select_autoescape

router = APIRouter()

_templates = Jinja2Templates(
    directory="src/frontend/templates",
    # Explicitly enable auto-escaping for HTML/XML templates
    autoescape=select_autoescape(
        enabled_extensions=("html", "xml"),
        default_for_string=True,
        default=True,
    ),
)


@router.get("/", response_class=RedirectResponse)
async def root():
    return RedirectResponse("/dashboard")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return _templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/schedule", response_class=HTMLResponse)
async def schedule(request: Request):
    return _templates.TemplateResponse("schedule.html", {"request": request})


@router.get("/settings", response_class=HTMLResponse)
async def settings(request: Request):
    return _templates.TemplateResponse("settings.html", {"request": request})


@router.get("/history", response_class=HTMLResponse)
async def history(request: Request):
    return _templates.TemplateResponse("history.html", {"request": request})


@router.get("/help", response_class=HTMLResponse)
async def help_page(request: Request):
    return _templates.TemplateResponse("help.html", {"request": request})
