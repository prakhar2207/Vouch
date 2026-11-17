import os
import sys
import base64
import hashlib
import logging
from typing import Union, Tuple
from django.db import models
from django.conf import settings
from cryptography.fernet import Fernet, MultiFernet, InvalidToken

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


def _derive_fernet_from_raw_key(raw_key: str) -> list[Fernet]:
    """
    Derives Fernet instances from a raw key string.
    Supports both direct 44-character urlsafe base64 keys and SHA-256 derived passphrases.
    """
    keys = []
    clean_key = str(raw_key).strip()
    is_direct = False

    if len(clean_key) == 44:
        try:
            decoded = base64.urlsafe_b64decode(clean_key.encode('utf-8'))
            if len(decoded) == 32:
                keys.append(Fernet(clean_key.encode('utf-8')))
                is_direct = True
        except Exception:
            pass

    # SHA-256 derived key (guarantees standard 256-bit entropy & backward compatibility)
    digest = hashlib.sha256(clean_key.encode('utf-8')).digest()
    sha_fernet = Fernet(base64.urlsafe_b64encode(digest))
    if is_direct:
        keys.append(sha_fernet)
    else:
        keys.insert(0, sha_fernet)

    return keys


def get_primary_fernet() -> Fernet:
    """
    Returns the authoritative primary Fernet provider used for all new encryption operations.
    """
    raw_key = (
        getattr(settings, 'GST_ENCRYPTION_KEY', None)
        or os.environ.get('GST_ENCRYPTION_KEY')
        or getattr(settings, 'GST_CREDENTIAL_KEY', None)
        or os.environ.get('GST_CREDENTIAL_KEY')
    )
    if raw_key:
        raw_key = str(raw_key).strip()

    env_name = str(getattr(settings, 'ENVIRONMENT', '') or os.environ.get('ENVIRONMENT', '')).strip().lower()
    is_testing = ('test' in sys.argv) or getattr(settings, 'TESTING', False)

    if not raw_key:
        if env_name in ('staging', 'stage', 'production', 'prod') and not is_testing:
            raise CredentialEncryptionError(
                f"FATAL SECURITY CONFIGURATION: Dedicated GST encryption key (GST_ENCRYPTION_KEY) "
                f"must be explicitly configured in environment '{env_name}'. "
                f"Fallback to Django SECRET_KEY is disabled to prevent cross-subsystem credential loss."
            )
        django_secret = getattr(settings, 'SECRET_KEY', None) or os.environ.get('SECRET_KEY')
        if not django_secret:
            raise CredentialEncryptionError("Encryption key is missing. Cannot initialize secure cryptographic provider.")
        raw_key = str(django_secret).strip()

    keys = _derive_fernet_from_raw_key(raw_key)
    return keys[0]


def get_gst_credential_fernet() -> Union[Fernet, MultiFernet]:
    """
    Constructs an authenticated MultiFernet cryptographic provider.
    Safeguards:
    1. Requires a dedicated GST_ENCRYPTION_KEY in staging and production;
       disallows silent fallback to Django SECRET_KEY in live environments.
    2. Accepts both direct 44-char urlsafe base64 keys (Fernet.generate_key())
       and SHA-256 derived passphrases for backward compatibility.
    3. Supports key rotation via GST_ENCRYPTION_KEY_OLD.
    4. Fails closed if keys are missing or invalid.
    """
    raw_key = (
        getattr(settings, 'GST_ENCRYPTION_KEY', None)
        or os.environ.get('GST_ENCRYPTION_KEY')
        or getattr(settings, 'GST_CREDENTIAL_KEY', None)
        or os.environ.get('GST_CREDENTIAL_KEY')
    )
    if raw_key:
        raw_key = str(raw_key).strip()

    env_name = str(getattr(settings, 'ENVIRONMENT', '') or os.environ.get('ENVIRONMENT', '')).strip().lower()
    is_testing = ('test' in sys.argv) or getattr(settings, 'TESTING', False)

    if not raw_key:
        if env_name in ('staging', 'stage', 'production', 'prod') and not is_testing:
            raise CredentialEncryptionError(
                f"FATAL SECURITY CONFIGURATION: Dedicated GST encryption key (GST_ENCRYPTION_KEY) "
                f"must be explicitly configured in environment '{env_name}'. "
                f"Fallback to Django SECRET_KEY is disabled to prevent cross-subsystem credential loss."
            )
        django_secret = getattr(settings, 'SECRET_KEY', None) or os.environ.get('SECRET_KEY')
        if not django_secret:
            raise CredentialEncryptionError("Encryption key is missing. Cannot initialize secure cryptographic provider.")
        raw_key = str(django_secret).strip()

    primary_keys = _derive_fernet_from_raw_key(raw_key)
    all_keys = list(primary_keys)

    # 3. Key rotation support: GST_ENCRYPTION_KEY_OLD
    old_key = getattr(settings, 'GST_ENCRYPTION_KEY_OLD', None) or os.environ.get('GST_ENCRYPTION_KEY_OLD')
    if old_key:
        old_str = str(old_key).strip()
        old_keys = _derive_fernet_from_raw_key(old_str)
        all_keys.extend(old_keys)

    # 4. In non-production or test contexts, also append Django SECRET_KEY derivation as fallback
    if is_testing or env_name in ('development', 'dev', 'local', 'test'):
        django_secret = getattr(settings, 'SECRET_KEY', None) or os.environ.get('SECRET_KEY')
        if django_secret and str(django_secret).strip() != raw_key:
            digest_sec = hashlib.sha256(str(django_secret).strip().encode('utf-8')).digest()
            all_keys.append(Fernet(base64.urlsafe_b64encode(digest_sec)))

    return MultiFernet(all_keys) if len(all_keys) > 1 else all_keys[0]


def encrypt_gst_credential(value: str) -> str:
    """
    Encrypts plaintext credential using Fernet authenticated envelope
    (AES-128 in CBC mode with PKCS7 padding and HMAC-SHA256 with 256-bit derived key).
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
        primary_f = get_primary_fernet()
        cipher = primary_f.encrypt(value.encode('utf-8')).decode('utf-8')
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
        env_name = str(getattr(settings, 'ENVIRONMENT', '') or os.environ.get('ENVIRONMENT', '')).strip().lower()
        is_testing = ('test' in sys.argv) or getattr(settings, 'TESTING', False)
        if env_name in ('staging', 'stage', 'production', 'prod') and not is_testing:
            logger.warning("POTENTIAL INTEGRITY RISK: Unencrypted credential value encountered in live environment.")
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


def is_encrypted_with_primary_key(value: str) -> bool:
    """
    Checks if an encrypted value can be decrypted using the current primary encryption key alone.
    Returns True if already on primary key, False if encrypted with an old/fallback key or not encrypted.
    """
    if not value or not isinstance(value, str) or not value.startswith(ENCRYPTION_PREFIX):
        return False
    token = value[len(ENCRYPTION_PREFIX):]
    try:
        primary_f = get_primary_fernet()
        primary_f.decrypt(token.encode('utf-8'))
        return True
    except InvalidToken:
        return False
    except Exception:
        return False


def rotate_credential_value(value: str) -> Tuple[str, bool]:
    """
    Re-encrypts a credential value using the current primary key.
    Returns (new_value, was_rotated).
    Idempotent: if already encrypted with primary key, returns (value, False).
    """
    if not value or not isinstance(value, str):
        return value, False

    # Plaintext value: encrypt with primary key
    if not value.startswith(ENCRYPTION_PREFIX):
        encrypted = encrypt_gst_credential(value)
        return encrypted, True

    # Already on primary key: skip
    if is_encrypted_with_primary_key(value):
        return value, False

    # Decrypt via MultiFernet fallback (supporting GST_ENCRYPTION_KEY_OLD)
    decrypted_plain = decrypt_gst_credential(value)
    # Re-encrypt with primary key
    new_encrypted = encrypt_gst_credential(decrypted_plain)
    return new_encrypted, True


class EncryptedTextField(models.TextField):
    """
    Custom Django model field for credentials and secrets.
    Transparently encrypts plaintext values before storing in the database (prep_value),
    and decrypts them upon retrieval from the database (from_db_value / to_python).
    Uses Fernet authenticated envelope (AES-128-CBC + HMAC-SHA256 with 256-bit derived key).
    Enforces fail-closed semantics across all persistence operations.
    """
    description = "Fernet Authenticated Encrypted Text (AES-128-CBC + HMAC-SHA256 with 256-bit derived key)"

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
