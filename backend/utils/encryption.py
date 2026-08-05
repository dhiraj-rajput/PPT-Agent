import base64
import hashlib
import logging
from cryptography.fernet import Fernet
from config.settings import settings

logger = logging.getLogger(__name__)

def _get_fernet_key() -> bytes:
    jwt_secret = getattr(settings, "JWT_SECRET", "") or ""
    if not jwt_secret:
        raise ValueError(
            "[Encryption] JWT_SECRET is not set in environment variables. "
            "Cannot derive encryption key — refusing to use a hardcoded fallback. "
            "Set JWT_SECRET in your .env file before starting the application."
        )
    key_hash = hashlib.sha256(jwt_secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(key_hash)

def encrypt_data(plain_text: str) -> str:
    """Encrypt a string and return a base64 encoded cipher text."""
    if not plain_text:
        return ""
    try:
        key = _get_fernet_key()
        f = Fernet(key)
        return f.encrypt(plain_text.encode("utf-8")).decode("utf-8")
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        raise RuntimeError("Failed to encrypt data") from e

def decrypt_data(cipher_text: str) -> str:
    """Decrypt base64 cipher text and return the original string."""
    if not cipher_text:
        return ""
    try:
        key = _get_fernet_key()
        f = Fernet(key)
        return f.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        raise RuntimeError("Failed to decrypt data") from e
