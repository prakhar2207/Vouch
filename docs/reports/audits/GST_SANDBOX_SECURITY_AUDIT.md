# SriLekh — GST Integration Security, Isolation & Cryptographic Audit

## 1. Executive Summary

This security audit inspects the implementation of the Sandbox by Quicko integration in SriLekh against standards for SaaS multi-tenancy, cryptographic key management, sensitive data handling, and role-based access control.

---

## 2. Multi-Tenant Isolation & Authorization

### Tenant Boundary Enforcement
- **Tenant Context**: All GST REST endpoints strictly authenticate the user via JWT session and resolve the active company tenant.
- **Permission Class (`HasGSTPermission`)**:
  - Enforces that the authenticated user belongs to the target company.
  - Checks role authorization: Only `OWNER`, `ADMIN`, or `ACCOUNTANT` roles may generate e-Invoices, file returns, or update taxpayer credentials.
  - Verifies multi-GSTIN access: If `registration.authorized_users` is specified, users outside the list are denied access with HTTP 403.
- **Cross-Tenant Attack Prevention**:
  - Direct object references (`uuid`) to registrations, filings, or e-invoice records are always filtered with `company=request.company`.
  - A malicious user belonging to Tenant A cannot view or mutate registrations, filings, or e-invoices of Tenant B.
  - Verified by automated IDOR test cases.

---

## 3. Cryptographic Storage & In-Transit Protection

### Encryption at Rest (Fernet / AES-256)
- **Sensitive Fields**:
  - `CompanyGSTConfig.sandbox_api_secret`
  - `CompanyGSTConfig.sandbox_access_token`
  - `GSTRegistration.auth_token`
  - `GSTRegistration.einvoice_password`
  - `GSTRegistration.eway_password`
- **Implementation**: Managed by `apps.gst.encryption.encrypt_credential()` and `decrypt_credential()` using symmetric Fernet encryption with cryptographic HMAC authentication.
- **Failure Mode**: Corrupted ciphertext or key mismatch raises an explicit decryption error and triggers re-authentication rather than leaking ciphertext or crashing silently.

### In-Transit Protection
- All outbound connections to Quicko Sandbox are enforced over **TLS 1.3** (`https://api.sandbox.co.in` or `https://test-api.sandbox.co.in`).
- Certificate verification is strictly active (`verify=True` in `requests.Session`).

---

## 4. Sensitive Data Redaction in Logging & Exceptions

To prevent accidental credential leaks into log aggregators (e.g., Render logs, Sentry, Datadog), `GSTAuditService` applies automatic recursive regex redaction:

### Redacted Keys
Any dictionary or query parameter matching:
`api_key`, `api_secret`, `password`, `token`, `otp`, `authorization`, `secret`, `x-api-key`, `x-api-secret`

Is transformed to:
`"********"` (Masked).

### Audit Trail Verification (`GSTAuditLog`)
- Every GST API interaction is persisted to `GSTAuditLog`.
- `request_payload` and `response_payload` pass through `GSTAuditService.redact_sensitive_payload()` prior to database insertion.
- Tested and verified: API secrets, passwords, OTPs, and JWTs are never recorded in plaintext.

---

## 5. Replay Attack & Idempotency Guards

1. **e-Invoice IRN Idempotency**:
   - `EInvoiceService.generate_irn()` checks for existing active records matching `voucher`.
   - Replay requests return the cached IRN immediately with zero additional outbound network calls.
2. **Return Submission SHA-256 Hashing**:
   - Returns compute a canonical SHA-256 hash of the return payload.
   - Resubmission of an identical return period checks for matching hash to prevent duplicate portal submission.

---

## 6. Security Audit Verdict

| Security Vector | Status | Evidence |
| :--- | :--- | :--- |
| **Credential Encryption at Rest** | **PASS** | Fernet AES-256 active on all secrets |
| **Transport Security (TLS 1.3)** | **PASS** | Strict HTTPS enforcement; SSL cert verification enabled |
| **Sensitive Data Redaction** | **PASS** | Recursive sanitization verified in `test_audit_logging_and_payload_redaction` |
| **Tenant Isolation (IDOR)** | **PASS** | Filter enforcement verified on all viewsets |
| **Role-Based Access Control** | **PASS** | `HasGSTPermission` blocks unauthorized roles |
| **Idempotency & Replay Protection** | **PASS** | Verified in `test_einvoice_generation_and_idempotency` |
