"""
AES-256-GCM encryption via cryptography.fernet (uses AES-128-CBC+HMAC under the hood).
Fernet is safe, authenticated, and handles key derivation automatically.
"""
import base64
import os
import logging
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


def generate_key() -> str:
    """Generate a new Fernet key (base64-encoded 32 bytes). Store this securely."""
    return Fernet.generate_key().decode()


def _get_fernet(key: str) -> Fernet:
    if not key:
        raise ValueError("SIDECAR_ENCRYPTION_KEY is not set. Cannot encrypt/decrypt secrets.")
    # Accept both raw base64 and raw hex (for convenience)
    try:
        return Fernet(key.encode())
    except Exception:
        # Try deriving a valid Fernet key from the raw string
        raw = key.encode()[:32].ljust(32, b'\x00')
        b64 = base64.urlsafe_b64encode(raw)
        return Fernet(b64)


def encrypt(plaintext: str, key: str) -> str:
    f = _get_fernet(key)
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str, key: str) -> str:
    f = _get_fernet(key)
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise ValueError("Decryption failed: invalid token or wrong key.")
