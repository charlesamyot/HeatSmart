"""Authentication routes — login page and session management."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .auth import get_optional_user
from .config import get_settings

router = APIRouter()
_templates = Jinja2Templates(directory="src/frontend/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = await get_optional_user(request)
    if user:
        return RedirectResponse("/dashboard")
    s = get_settings()
    return _templates.TemplateResponse("login.html", {
        "request": request,
        "supabase_url": s.supabase_url,
        "supabase_key": s.supabase_key,
    })


@router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    user = await get_optional_user(request)
    if user:
        return RedirectResponse("/dashboard")
    s = get_settings()
    return _templates.TemplateResponse("signup.html", {
        "request": request,
        "supabase_url": s.supabase_url,
        "supabase_key": s.supabase_key,
    })


@router.get("/auth/callback", response_class=HTMLResponse)
async def auth_callback(request: Request):
    """Handle Supabase auth redirects (magic link, OAuth).

    The actual token extraction happens client-side from the URL hash.
    This page just loads the auth.js script which processes the fragment.
    """
    s = get_settings()
    return _templates.TemplateResponse("auth_callback.html", {
        "request": request,
        "supabase_url": s.supabase_url,
        "supabase_key": s.supabase_key,
    })


@router.get("/api/auth/me")
async def auth_me(request: Request):
    """Return current user info or 401."""
    user = await get_optional_user(request)
    if not user:
        return JSONResponse({"authenticated": False}, status_code=401)
    return {"authenticated": True, "user_id": user["sub"], "email": user["email"], "role": user["role"]}


@router.get("/logout")
async def logout():
    response = RedirectResponse("/login")
    response.delete_cookie("sb-access-token", path="/")
    return response
