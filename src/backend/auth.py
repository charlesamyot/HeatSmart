"""Authentication middleware using Supabase JWT tokens."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request
from jose import JWTError, jwt

from .config import get_settings

logger = logging.getLogger(__name__)


async def get_current_user(request: Request) -> dict:
    """FastAPI dependency: extract and verify Supabase JWT from Authorization header or cookie.

    Returns dict with at minimum: {"sub": user_uuid, "email": str}
    Raises 401 if no valid token.
    """
    settings = get_settings()
    token = _extract_token(request)
    if not token:
        raise HTTPException(401, "Not authenticated")

    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(401, "Invalid token: no sub claim")
        return {
            "sub": user_id,
            "email": payload.get("email", ""),
            "role": payload.get("role", "authenticated"),
        }
    except JWTError as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise HTTPException(401, "Invalid or expired token")


async def get_optional_user(request: Request) -> Optional[dict]:
    """Like get_current_user but returns None instead of raising 401."""
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


def _extract_token(request: Request) -> Optional[str]:
    """Extract bearer token from Authorization header or sb-access-token cookie."""
    # Header: Authorization: Bearer <token>
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    # Cookie fallback (set by Supabase JS client)
    return request.cookies.get("sb-access-token")
