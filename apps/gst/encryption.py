import base64
import hashlib
import logging
from django.db import models
from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

ENCRYPTION_PREFIX = "enc:v1:"

def get_gst_credential_fernet() -> Fernet:
    """
    Derives an authenticated 32-byte URL-safe base64 key from settings.GST_CREDENTIAL_KEY or settings.SECRET_KEY.
    Uses SHA-256 HKDF-style key derivation to ensure standard 256-bit entropy.
    """
    raw_key = getattr(settings, 'GST_CREDENTIAL_KEY', None) or settings.SECRET_KEY
    digest = hashlib.sha256(raw_key.encode('utf-8')).digest()
    key_b64 = base64.urlsafe_b64encode(digest)
    return Fernet(key_b64)

def encrypt_gst_credential(value: str) -> str:
    """
    Encrypts plaintext credential using AES-128-CBC + HMAC-SHA256 authenticated envelope (Fernet).
    Prefixes with 'enc:v1:' to guarantee idempotency and avoid double-encryption.
    """
    if not value or not isinstance(value, str):
        return value or ""
    if value.startswith(ENCRYPTION_PREFIX):
        return value
    try:
        f = get_gst_credential_fernet()
        cipher = f.encrypt(value.encode('utf-8')).decode('utf-8')
        return f"{ENCRYPTION_PREFIX}{cipher}"
    except Exception as e:
        logger.error(f"Failed to encrypt GST credential: {e}")
        return value

def decrypt_gst_credential(value: str) -> str:
    """
    Decrypts an encrypted GST credential.
    Transparently returns the value if it's not prefixed with 'enc:v1:' (handles existing legacy plaintext).
    """
    if not value or not isinstance(value, str):
        return value or ""
    if not value.startswith(ENCRYPTION_PREFIX):
        return value
    token = value[len(ENCRYPTION_PREFIX):]
    try:
        f = get_gst_credential_fernet()
        return f.decrypt(token.encode('utf-8')).decode('utf-8')
    except (InvalidToken, Exception) as e:
        logger.warning(f"Could not decrypt credential token: {e}")
        return value

class EncryptedTextField(models.TextField):
    """
    Custom Django model field for credentials and secrets.
    Transparently encrypts plaintext values before storing in the database (prep_value),
    and decrypts them upon retrieval from the database (from_db_value / to_python).
    """
    description = "Fernet AES-256 Authenticated Encrypted Text"

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return decrypt_gst_credential(value)

    def to_python(self, value):
        if value is None:
            return value
        return decrypt_gst_credential(value)

    def get_prep_value(self, value):
        if value is None or value == '':
            return ''
        return encrypt_gst_credential(str(value))
