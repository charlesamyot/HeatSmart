"""Supabase client for database operations and credential encryption."""
from __future__ import annotations

import logging
import os
from typing import Optional

from cryptography.fernet import Fernet

from .config import get_settings

logger = logging.getLogger(__name__)

_fernet = None


def get_fernet() -> Fernet:
    """Get or create the Fernet encryption instance for credential storage."""
    global _fernet
    if _fernet is None:
        key = get_settings().encryption_key
        if not key:
            # Generate a key on first use and warn
            key = Fernet.generate_key().decode()
            logger.warning("No ENCRYPTION_KEY set — generated ephemeral key. "
                           "Set ENCRYPTION_KEY env var for persistence.")
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt_credential(plaintext: str) -> bytes:
    """Encrypt a credential (email or password) for database storage."""
    return get_fernet().encrypt(plaintext.encode())


def decrypt_credential(ciphertext: bytes) -> str:
    """Decrypt a credential from database storage."""
    return get_fernet().decrypt(ciphertext).decode()
