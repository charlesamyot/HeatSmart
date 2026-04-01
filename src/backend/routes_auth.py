"""Authentication routes — login page and session management."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .auth import get_optional_user

router = APIRouter()
_templates = Jinja2Templates(directory="src/frontend/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = await get_optional_user(request)
    if user:
        return RedirectResponse("/dashboard")
    return _templates.TemplateResponse("login.html", {"request": request})


@router.get("/logout")
async def logout():
    response = RedirectResponse("/login")
    response.delete_cookie("sb-access-token")
    return response
