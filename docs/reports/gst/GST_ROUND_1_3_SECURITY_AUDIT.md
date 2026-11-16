# SriLekh GST Integration — Round 1.3 Security & Threat Modeling Audit
## Threat Vector Analysis, Defense-in-Depth Implementation & Cryptographic Review

- **Target System:** SriLekh GST Integration & Provider Gateway
- **Auditor Role:** Principal Security Architect & Lead Security Engineer
- **Environment:** Dedicated Staging (`fix/stage4-12-day6-remediation`)
- **Audit Date:** November 16, 2026
- **Status:** APPROVED — STRICT CONTROLS IN EFFECT

---

## 1. Executive Summary

A comprehensive application security audit and threat modeling assessment was performed on the SriLekh GST Integration following the Round 1.3 remediation. The objective was to ensure that multi-tenant boundaries, cryptographic credentials, API outbound calls, and user authorization mechanisms withstand attack vectors common to multi-tenant FinTech applications.

---

## 2. Threat Vector Remediation Matrix

### Threat Vector 1: Server-Side Request Forgery (SSRF)
- **Vulnerability:** In Round 1.2, `CompanyGSTConfig.sandbox_base_url` could be configured with arbitrary URLs, potentially allowing attackers to pivot outbound HTTP requests to internal cloud metadata endpoints (`169.254.169.254`) or internal services.
- **Remediation Implemented:**
  - Implemented `ALLOWED_SANDBOX_HOSTS = {'api.sandbox.co.in', 'test-api.sandbox.co.in'}` in `apps/gst/services/sandbox_client.py`.
  - The client extracts the hostname via `urllib.parse.urlparse` and strictly validates against the allowlist.
  - Any URL outside the allowlist raises `GSTValidationError("Target sandbox host '...' is not authorized")`.
- **Status:** **MITIGATED & VERIFIED**

### Threat Vector 2: Weak Encryption & Plaintext Credential Exposure
- **Vulnerability:** Previous versions fell back to plaintext storage or `SECRET_KEY` derivation if dedicated keys were absent, risking exposure in staging or live environments.
- **Remediation Implemented:**
  - Enforced authenticated Fernet envelope (`AES-128-CBC` + `HMAC-SHA256` with 256-bit derived key) with `enc:v1:` prefix.
  - Removed plaintext pass-through in live/staging environments.
  - Implemented fail-closed behavior: corrupted ciphertext or mismatched keys raise `CredentialDecryptionError`.
  - Added Django startup check `check_gst_encryption_configuration` (`Tags.security`) to prevent server boot if `GST_ENCRYPTION_KEY` is missing or invalid.
- **Status:** **MITIGATED & VERIFIED**

### Threat Vector 3: Credential Echoing & Log Leakage
- **Vulnerability:** Sensitive API keys, client secrets, and bearer tokens could be logged in unhandled exception tracebacks or outbound HTTP error dumps.
- **Remediation Implemented:**
  - Sanitized error message extraction in `SandboxGSTClient.execute_request`.
  - Masked API key strings in logger messages and API responses (`key[:4] + "****"`).
  - Explicit masking of GSTINs in application debug logs (`[MASKED_GSTIN]`).
- **Status:** **MITIGATED & VERIFIED**

### Threat Vector 4: Broken Object Level Authorization & Privilege Escalation
- **Vulnerability:** Non-admin tenant members (e.g., Viewers, Employees) could theoretically invoke registration mutations or deactivations.
- **Remediation Implemented:**
  - Added `CanManageGSTRegistration` permission class checking `user_has_company_roles(request.user, company, ['OWNER', 'ADMIN'])`.
  - Enforced `get_authorized_company` tenant scoping on all views.
  - Restricted `PartyEnrichmentApplyAPIView` to `OWNER`, `ADMIN`, and `ACCOUNTANT`.
  - Verified that cross-tenant access returns HTTP 403 Forbidden or HTTP 404 Not Found.
- **Status:** **MITIGATED & VERIFIED**

### Threat Vector 5: Client-Side Data Tampering (Party Auto-Fill)
- **Vulnerability:** An attacker could submit arbitrary legal names or addresses to `PartyEnrichmentApplyAPIView`, overwriting verified ledger records with fraudulent data.
- **Remediation Implemented:**
  - Enforced that party enrichment data must match verified records in `GSTTaxpayerCache`.
  - Any attempt to submit arbitrary unverified data is rejected.
  - Updates only legitimate party fields (`name`, `state_code`, `address`, `gstin`) and logs an audit trail.
- **Status:** **MITIGATED & VERIFIED**

### Threat Vector 6: Race Conditions in Primary GSTIN Management
- **Vulnerability:** Concurrent HTTP requests to create or set primary registrations could cause multiple active primary GSTINs for a single company.
- **Remediation Implemented:**
  - Added PostgreSQL partial unique constraint:
    ```sql
    CREATE UNIQUE INDEX unique_primary_gstin_per_company 
    ON gst_gstregistration (company_id) 
    WHERE is_primary = TRUE;
    ```
  - Added `select_for_update()` row-level locks on `Company` and existing registrations during primary toggle operations.
- **Status:** **MITIGATED & VERIFIED**

---

## 3. Cryptographic Invariants Summary

1. **Cipher Algorithm:** AES-128 in Cipher Block Chaining (CBC) mode with PKCS7 padding.
2. **Authentication:** HMAC with SHA-256 for authenticated ciphertext verification.
3. **Key Length:** 256 bits (128-bit AES key + 128-bit HMAC key).
4. **Key Derivation:** URL-safe Base64-encoded 32-byte key.
5. **Multi-Key Support:** `MultiFernet` with primary key (`GST_ENCRYPTION_KEY`) and fallback key (`GST_ENCRYPTION_KEY_OLD`).
6. **Integrity Assurance:** Ciphertext tampering triggers `InvalidToken` / `CredentialDecryptionError` immediately upon model field access.

---

## 4. Audit Sign-Off

The GST integration codebase meets commercial SaaS security standards for MSME accounting. Outbound calls are locked down, credentials are cryptographically protected at rest, tenant isolation is strictly enforced at the database and application levels, and privilege escalation vulnerabilities have been remediated.
