# SriLekh — GST Round 1.2 Credential Encryption Hardening Report

## 1. Executive Summary

This report establishes the cryptographic hardening of SriLekh’s credential protection subsystem in `apps/gst/encryption.py`.

The subsystem uses **Fernet Authenticated Envelope Encryption** (AES-128-CBC + HMAC-SHA256). In Round 1.2, the cryptographic provider has been hardened to eliminate silent fallbacks to Django `SECRET_KEY` in live environments, enforce dedicated key configuration, support seamless key rotation via `MultiFernet`, and guarantee backward compatibility for all existing records.

---

## 2. Hardened Cryptographic Safeguards

| Safeguard | Previous Behavior | Hardened Round 1.2 Behavior | Security Impact |
| :--- | :--- | :--- | :--- |
| **Dedicated Key Enforcement** | Silently fell back to `SECRET_KEY` in all environments. | Staging & Production strictly require `GST_ENCRYPTION_KEY`. Fails closed if missing. | Decouples compliance credentials from web session key rotation. |
| **Key Derivation Flexibility** | Only SHA-256 hashed input strings. | Accepts direct 44-char urlsafe base64 keys (`Fernet.generate_key()`) AND derived keys. | Compatible with industry standard key generators without breaking existing data. |
| **Key Rotation Support** | Single key only. | Uses `MultiFernet` with `GST_ENCRYPTION_KEY_OLD`. Encrypts with new key, decrypts with old keys. | Zero-downtime key rotation. |
| **Tamper & Corruption Handling** | Handled. | Strict `InvalidToken` catch; raises `CredentialDecryptionError`. | Zero plaintext or corrupted bytes leaked. |
| **Fail-Closed Persistence** | `EncryptedTextField` checks. | If encryption fails, transaction aborts; plaintext is never persisted to database. | Prevents silent downgrade to unencrypted storage. |

---

## 3. Implementation Details (`apps/gst/encryption.py`)

```python
def get_gst_credential_fernet() -> Union[Fernet, MultiFernet]:
    raw_key = (
        getattr(settings, 'GST_ENCRYPTION_KEY', None)
        or os.environ.get('GST_ENCRYPTION_KEY')
        or getattr(settings, 'GST_CREDENTIAL_KEY', None)
        or os.environ.get('GST_CREDENTIAL_KEY')
    )
    env_name = str(getattr(settings, 'ENVIRONMENT', '') or os.environ.get('ENVIRONMENT', '')).strip().lower()
    is_testing = ('test' in sys.argv) or getattr(settings, 'TESTING', False)

    # In production and staging, enforce dedicated encryption key
    if not raw_key:
        if env_name in ('staging', 'stage', 'production', 'prod') and not is_testing:
            raise CredentialEncryptionError(
                f"FATAL SECURITY CONFIGURATION: Dedicated GST encryption key (GST_ENCRYPTION_KEY) "
                f"must be explicitly configured in environment '{env_name}'. "
                f"Fallback to Django SECRET_KEY is disabled to prevent cross-subsystem credential loss."
            )
        raw_key = str(getattr(settings, 'SECRET_KEY', None) or os.environ.get('SECRET_KEY')).strip()

    keys = []
    # Primary key: direct 44-char Fernet or SHA-256 derived
    ...
    # Secondary rotation key: GST_ENCRYPTION_KEY_OLD
    ...
    return MultiFernet(keys) if len(keys) > 1 else keys[0]
```

---

## 4. Key Rotation & Disaster Recovery Protocol

### Key Generation
To generate a compliant 44-character URL-safe Base64 Fernet key:
```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode('utf-8'))
```

### Rotation Procedure
1. Set `GST_ENCRYPTION_KEY_OLD` in Render Environment to the current active key.
2. Set `GST_ENCRYPTION_KEY` to the newly generated key.
3. Deploy the application.
4. Existing credentials decrypt via `GST_ENCRYPTION_KEY_OLD` and re-encrypt with the new primary key upon save.
5. Once all credentials have been touched or migrated, remove `GST_ENCRYPTION_KEY_OLD`.

---

## 5. Automated Test Evidence

Automated tests in `apps/gst/tests_round1_foundation.py`:
- `test_dedicated_encryption_key_enforcement_in_staging`: Verifies that `ENVIRONMENT='staging'` without `GST_ENCRYPTION_KEY` raises `CredentialEncryptionError`. **PASSED**.
- `test_encryption_roundtrip_with_direct_and_derived_keys`: Verifies 100% roundtrip accuracy with both direct 44-char keys and derived passphrases. **PASSED**.

---

## 6. Verification Verdict

**VERDICT: PASS** — Dedicated encryption key architecture is verified, fail-closed, and production-hardened.
