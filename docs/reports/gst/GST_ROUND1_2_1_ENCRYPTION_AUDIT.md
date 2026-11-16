# SRI LEKH — GST ROUND 1.2.1 AUDIT REPORT: ENCRYPTION & KEY MANAGEMENT
**Audited Target:** `apps/gst/encryption.py` & `apps/gst/models.py`  
**Git Commit:** `8860b99ac3f13db1c554b7d9b0a559a79c5a927e`  
**Branch:** `fix/stage4-12-day6-remediation`  
**Auditor:** Principal Software Architect & Senior Django Security Engineer  
**Date:** 2026-11-16  

---

## 1. Executive Summary

This independent forensic audit evaluates the cryptographic implementation protecting sensitive Indian Goods and Services Tax (GST) credentials in SriLekh, including Sandbox API keys, API secrets, JWT bearer tokens, and taxpayer credentials. 

The encryption subsystem at commit `8860b99` implements an envelope using Fernet symmetric encryption (`cryptography.fernet.Fernet` and `MultiFernet`) based on AES-128 in CBC mode with PKCS7 padding and HMAC-SHA256 for authenticated ciphertext integrity.

While significant hardening occurred in Round 1.2 (notably preventing silent fallback to Django's `SECRET_KEY` in staging/production, and adding key rotation via `MultiFernet`), this audit identifies **one P1 architectural flaw regarding key rotation persistence**, **one P2 plaintext bypass risk**, and **one P3 test detection fragility**.

---

## 2. Detailed Findings

### FINDING ENC-01 (Severity: P1 — High)
**False Architectural Claim: Key Rotation Does Not Re-Encrypt Database Records at Rest**

- **File & Function:** `apps/gst/encryption.py`: `get_gst_credential_fernet()` (lines 85–98) & `EncryptedTextField` (lines 159–182).
- **Exact Problem:**
  Previous documentation claimed that introducing `GST_ENCRYPTION_KEY_OLD` alongside a new `GST_ENCRYPTION_KEY` enables seamless key rotation with automatic re-encryption of database records. 
  
  In cryptography, `MultiFernet` behaves as follows:
  1. `MultiFernet.encrypt()` always uses the first key in the list (`keys[0]`, the new primary key).
  2. `MultiFernet.decrypt()` iterates through keys in sequence until one successfully decrypts the ciphertext.
  
  However, `MultiFernet.decrypt()` is invoked inside `from_db_value()` / `to_python()` when reading records from PostgreSQL. This **only decrypts the ciphertext in memory**. The stored database row in PostgreSQL (`CompanyGSTConfig.sandbox_api_key`, `GSTRegistration.auth_token`, etc.) **remains encrypted under the old key forever** unless that row is subsequently saved via `instance.save()` where the encrypted field is included in `update_fields`.
  
  If the DevOps team assumes automatic database re-encryption has completed and subsequently retires/removes `GST_ENCRYPTION_KEY_OLD` from the environment, all untouched database records become permanently undecryptable (`InvalidToken` / `CredentialDecryptionError`), causing immediate system-wide outage for those tenants.

- **Reproduction Scenario:**
  1. Store credentials under `Key_A` in staging database `neondb_staging`.
  2. Rotate environment: set `GST_ENCRYPTION_KEY = Key_B` and `GST_ENCRYPTION_KEY_OLD = Key_A`.
  3. Query `CompanyGSTConfig.objects.get(company=apex)`: in memory, `config.sandbox_api_key` decrypts successfully via `MultiFernet` fallback.
  4. Inspect raw database column via SQL: `SELECT sandbox_api_key FROM gst_companygstconfig WHERE ...`. The column text is unchanged and still encrypted with `Key_A`.
  5. After 30 days, decommission `GST_ENCRYPTION_KEY_OLD`.
  6. Query `CompanyGSTConfig`: raises `CredentialDecryptionError("InvalidToken")`. All operations halt.

- **Business / Security Impact:**
  High risk of catastrophic data loss during operational key rotation cycles. False confidence in documentation creates operational fragility.

- **Recommended Correction:**
  1. Implement a dedicated Django management command:
     `python manage.py rotate_gst_credentials`
     which explicitly loads every `CompanyGSTConfig` and `GSTRegistration` row within a transaction, decrypts the fields, and calls `save(update_fields=[...])` using the new primary key, logging re-encrypted row counts.
  2. Clarify documentation that `MultiFernet` provides *transitional read compatibility*, not *automatic rest re-encryption*.

- **Detected by Existing Tests?**
  **NO.** Existing tests in `tests_round1_foundation.py` verify in-memory roundtrip with mock keys, but do not simulate database-level rotation lifecycle, key retirement, or data migration.

---

### FINDING ENC-02 (Severity: P2 — Medium)
**Plaintext Pass-Through Fallback in `decrypt_gst_credential()`**

- **File & Function:** `apps/gst/encryption.py`: `decrypt_gst_credential()` (lines 140–144).
- **Exact Problem:**
  Lines 142–143 state:
  ```python
  if not value.startswith(ENCRYPTION_PREFIX):
      return value
  ```
  If a value stored in PostgreSQL does not start with `enc:v1:`, the method returns `value` as raw plaintext without raising an error or logging a warning. While this was introduced for backward compatibility with unencrypted legacy records, it creates a silent failure mode: if an attacker, rogue migration, or developer script inserts raw plaintext credentials into `EncryptedTextField`, the application reads and uses them silently without flagging the integrity violation.

- **Reproduction Scenario:**
  1. Manually update a `CompanyGSTConfig` record via SQL or Django shell:
     `CompanyGSTConfig.objects.filter(id=...).update(sandbox_api_key='plain_secret_key')`.
  2. Call `config.refresh_from_db()` and inspect `config.sandbox_api_key`.
  3. The getter returns `'plain_secret_key'` without raising `CredentialDecryptionError` and without any audit warning.

- **Business / Security Impact:**
  Circumvents the fail-closed security guarantee. Plaintext data could reside in the database indefinitely without triggering operational alerts.

- **Recommended Correction:**
  In staging and production (`env_name in ('staging', 'production')`), disallow plaintext pass-through unless an explicit legacy migration flag is active. At minimum, emit a structured security warning:
  ```python
  if not value.startswith(ENCRYPTION_PREFIX):
      if env_name in ('staging', 'production') and not is_testing:
          logger.critical("SECURITY INVARIANT VIOLATION: Plaintext credential detected in EncryptedTextField.")
      return value
  ```

- **Detected by Existing Tests?**
  **NO.** No test asserts that unencrypted strings raise an error or trigger an alert in production.

---

### FINDING ENC-03 (Severity: P3 — Low)
**Fragile Testing Detection via `('test' in sys.argv)`**

- **File & Function:** `apps/gst/encryption.py`: line 48.
- **Exact Problem:**
  Line 48 detects test execution via:
  ```python
  is_testing = ('test' in sys.argv) or getattr(settings, 'TESTING', False)
  ```
  While functional when running `python manage.py test`, this check fails when running tests via Pytest (`pytest`), custom runners, Celery test workers, or management commands invoked with different argument naming conventions where `'test'` is absent from `sys.argv` and `settings.TESTING` is unset. In staging integration test scripts, this could cause unintended configuration errors or unexpected fallback behavior.

- **Recommended Correction:**
  Standardize on `getattr(settings, 'IS_TESTING', False)` or `hasattr(sys, '_called_from_test')`, and ensure `TESTING = True` is declared in test settings.

- **Detected by Existing Tests?**
  **NO.** Tests pass because `manage.py test` satisfies `'test' in sys.argv`.

---

## 3. Cryptographic Correctness Analysis

| Component | Implementation | Forensic Evaluation |
|---|---|---|
| **Cipher Suite** | Fernet (AES-128-CBC + HMAC-SHA256) | Standard authenticated symmetric envelope. Guarantees 128-bit security margin and ciphertext integrity. |
| **Key Derivation** | SHA-256 over raw key string | Generates 32-byte key digest, urlsafe base64 encoded. Handles both direct 44-char keys and passphrase strings. |
| **MultiFernet Ordering** | `keys[0]` is primary, `keys[1:]` are fallback | Correct: new writes always use the active key; previous keys can still read. |
| **Prefix Tagging** | `enc:v1:` prepended to all ciphertext | Prevents double encryption; provides format versioning. |
| **Environment Guard** | Refuses fallback to `SECRET_KEY` in staging/prod | **VERIFIED.** Fails closed with `CredentialEncryptionError` if `GST_ENCRYPTION_KEY` is omitted in staging or prod. |
| **Fail-Closed on Write** | `CredentialEncryptionError` on failure | **VERIFIED.** Unhandled encryption errors abort transaction; no plaintext is saved. |

---

## 4. Verdict & Release Readiness

**Dimension Verdict:** **CONDITIONAL PASS**  
The encryption implementation is robust and cryptographically sound for single-key operations and backward compatibility. However, before executing key rotation in production, a dedicated migration/management command must be implemented to re-encrypt records at rest (remediating Finding ENC-01).
