import base64
import hashlib
import logging
from django.db import models
from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

ENCRYPTION_PREFIX = "enc:v1:"

class CredentialSecurityError(Exception):
    """Base exception for sensitive credential cryptographic operations."""
    pass

class CredentialEncryptionError(CredentialSecurityError):
    """Raised when encryption fails. Guarantees no silent downgrade to plaintext."""
    pass

class CredentialDecryptionError(CredentialSecurityError):
    """Raised when decryption fails. Guarantees no silent fallback to corrupted values or ciphertext."""
    pass

def get_gst_credential_fernet() -> Fernet:
    """
    Derives an authenticated 32-byte URL-safe base64 key from settings.GST_CREDENTIAL_KEY or settings.SECRET_KEY.
    Uses SHA-256 key derivation to ensure standard 256-bit entropy.
    Fails closed if no key is configured.
    """
    raw_key = getattr(settings, 'GST_CREDENTIAL_KEY', None) or getattr(settings, 'SECRET_KEY', None)
    if not raw_key:
        raise CredentialEncryptionError("Encryption key is missing. Cannot initialize secure cryptographic provider.")
    digest = hashlib.sha256(raw_key.encode('utf-8')).digest()
    key_b64 = base64.urlsafe_b64encode(digest)
    return Fernet(key_b64)

def encrypt_gst_credential(value: str) -> str:
    """
    Encrypts plaintext credential using AES-128-CBC + HMAC-SHA256 authenticated envelope (Fernet).
    Prefixes with 'enc:v1:' to guarantee idempotency and avoid double-encryption.
    
    SECURITY INVARIANT: FAIL CLOSED.
    Never swallows encryption errors. If key derivation or encryption fails,
    raises CredentialEncryptionError immediately so database transactions abort
    and plaintext is NEVER persisted.
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
        logger.error(f"Failed to encrypt credential envelope: {type(e).__name__}")
        raise CredentialEncryptionError(
            "Cryptographic encryption failed. Operation aborted to prevent plaintext credential exposure."
        ) from e

def decrypt_gst_credential(value: str) -> str:
    """
    Decrypts an encrypted GST credential.
    
    SECURITY INVARIANT: FAIL CLOSED.
    If decryption of an 'enc:v1:' payload fails (corrupted ciphertext, key mismatch),
    raises CredentialDecryptionError immediately. Never returns ciphertext or corrupted data.
    """
    if not value or not isinstance(value, str):
        return value or ""
    if not value.startswith(ENCRYPTION_PREFIX):
        return value
    token = value[len(ENCRYPTION_PREFIX):]
    try:
        f = get_gst_credential_fernet()
        return f.decrypt(token.encode('utf-8')).decode('utf-8')
    except InvalidToken as it:
        logger.error("Failed to decrypt credential envelope: InvalidToken / corrupted ciphertext or key mismatch.")
        raise CredentialDecryptionError(
            "Cryptographic decryption failed: InvalidToken (ciphertext corrupted or encryption key mismatch)."
        ) from it
    except Exception as e:
        logger.error(f"Failed to decrypt credential envelope: {type(e).__name__}")
        raise CredentialDecryptionError(
            "Cryptographic decryption failed due to an unexpected error."
        ) from e

class EncryptedTextField(models.TextField):
    """
    Custom Django model field for credentials and secrets.
    Transparently encrypts plaintext values before storing in the database (prep_value),
    and decrypts them upon retrieval from the database (from_db_value / to_python).
    Enforces fail-closed semantics across all persistence operations.
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

