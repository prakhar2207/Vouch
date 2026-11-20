# SriLekh GST Integration — Round 1.3 Cryptographic Specification & Key Rotation Runbook
## Envelope Encryption, MultiFernet Fallback & Zero-Downtime Migration Procedures

- **Target Module:** `apps/gst/encryption.py` & `apps/gst/management/commands/rotate_gst_credentials.py`
- **Specification Version:** 1.3.0
- **Auditor Role:** Principal Cryptographic & Security Engineer
- **Date:** November 16, 2026

---

## 1. Cryptographic Envelope Specification

### Standard Envelope
SriLekh enforces Fernet symmetric authenticated encryption for all sensitive GST credentials at rest.

```
Format: enc:v1:<Base64-Fernet-Token>
```

### Cryptographic Primitives
1. **Encryption Algorithm:** AES-128-CBC (Advanced Encryption Standard in Cipher Block Chaining mode).
2. **Authentication / Integrity:** HMAC-SHA256 (Hash-based Message Authentication Code).
3. **Key Composition:** 256-bit total key (128 bits for AES-128 encryption, 128 bits for HMAC-SHA256 authentication).
4. **IV / Nonce:** 128-bit random IV generated uniquely per encryption operation from `os.urandom()`.
5. **Timestamp:** 64-bit integer tracking creation time.
6. **Key Encoding:** 32-byte raw key encoded via URL-safe Base64 (44 ASCII characters).

### Protected Database Fields
- **`apps.gst.models.CompanyGSTConfig`**:
  - `api_key`
  - `api_secret`
  - `sandbox_api_key`
  - `sandbox_api_secret`
  - `sandbox_access_token`
  - `eway_password`
  - `einvoice_password`
  - `auth_token`
- **`apps.gst.models.GSTRegistration`**:
  - `auth_token`
  - `einvoice_password`
  - `eway_password`

---

## 2. Multi-Key Fallback & Zero-Downtime Rotation

### Environment Variables
- **`GST_ENCRYPTION_KEY`**: The active primary key used for all new encryption operations and re-encryptions.
- **`GST_ENCRYPTION_KEY_OLD`**: (Optional) The prior key used to decrypt historical records that have not yet been migrated.

### Rotation Mechanics
1. **Read Path:** `decrypt_gst_credential` uses `cryptography.fernet.MultiFernet([primary_fernet, old_fernet])`. If a token was encrypted with the old key, `MultiFernet` seamlessly decrypts it using the fallback key.
2. **Write Path:** `encrypt_gst_credential` strictly uses the primary key (`get_primary_fernet()`).
3. **Fail-Closed Semantics:** If neither key can decrypt the token, or if ciphertext is corrupted, `CredentialDecryptionError` is raised immediately.

---

## 3. Key Rotation Management Command Runbook

SriLekh provides a dedicated management command to re-encrypt stored credentials from the old key to the new key without downtime:

```bash
python manage.py rotate_gst_credentials [OPTIONS]
```

### Command Flags
- `--dry-run`: Inspects all encrypted records, attempts decryption and re-encryption in memory, and displays the exact count of fields that would be rotated without writing to the database.
- `--batch-size <N>`: Configures chunk size for database query iterators (default: `100`).
- `--company-id <UUID>`: Scopes rotation to a specific company/tenant for targeted migrations.

### Standard Production Rotation Procedure

#### Phase 1: Key Generation
Generate a fresh 32-byte Fernet key:
```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode('utf-8'))
```

#### Phase 2: Staging Environment Variable Configuration
1. Set `GST_ENCRYPTION_KEY_OLD` to the current `GST_ENCRYPTION_KEY`.
2. Set `GST_ENCRYPTION_KEY` to the newly generated key.
3. Deploy/restart the application service.

#### Phase 3: Dry-Run Verification
Execute dry-run to verify backward-compatible readability:
```bash
python manage.py rotate_gst_credentials --dry-run
```
*Expected Output:*
```
Starting GST Credential Key Rotation [Dry Run: True]
==================================================
CompanyGSTConfig records processed:       X
GSTRegistration records processed:        Y
Total Fields Rotated:                     Z
Total Fields Skipped (Already Primary):   W
Total Fields Failed:                      0
==================================================
Key rotation completed successfully.
```

#### Phase 4: Live Execution
Execute live database re-encryption:
```bash
python manage.py rotate_gst_credentials
```
*Expected Output:*
```
Total Fields Failed: 0
Total Fields Rotated: Z
```

#### Phase 5: Verification & Decommissioning
1. Run a subsequent rotation command to confirm idempotency (`Total Fields Rotated: 0`).
2. Verify application GSTIN lookups and provider API calls function normally.
3. Once all records are rotated, remove `GST_ENCRYPTION_KEY_OLD` from environment variables.

---

## 4. Startup Health Check (`check_gst_encryption_configuration`)

SriLekh includes a Django system check registered under `Tags.security`:
- Verifies that `GST_ENCRYPTION_KEY` is present.
- Verifies that `GST_ENCRYPTION_KEY` is a valid 32-byte URL-safe base64 string.
- Verifies that `GST_ENCRYPTION_KEY_OLD` (if configured) is valid.
- If checks fail in production, deployment boot is halted immediately (SystemCheckError).
