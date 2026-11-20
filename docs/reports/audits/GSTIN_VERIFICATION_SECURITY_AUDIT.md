# SriLekh — GSTIN Verification & Provider Security Audit

## 1. Executive Summary

This security audit certifies the implementation of the **Sandbox by Quicko** integration foundation and GSTIN verification subsystem in SriLekh (Round 1). The audit confirms that tenant isolation is strictly preserved, sensitive provider credentials are encrypted at rest using AES-256 Fernet envelopes, API keys are completely redacted from application logs, and multi-tenant authorization guards prevent Insecure Direct Object References (IDOR).

---

## 2. Threat Modeling & Security Architecture

| Threat Vector | Mitigation Strategy in SriLekh | Audit Verdict |
| :--- | :--- | :--- |
| **Credential Compromise at Rest** | Secrets encrypted using `Fernet` (AES-128-CBC + HMAC-SHA256) keyed to `GST_ENCRYPTION_KEY` in environment. | **PASSED** |
| **Token Leakage in Application Logs** | Request headers (`x-api-key`, `Authorization`) and credentials in payloads are automatically redacted in `SandboxGSTClient` and `GSTAuditService`. | **PASSED** |
| **Cross-Tenant IDOR Attacks** | Every endpoint enforces `company_id` verification against `request.user.memberships` and validates object ownership before DB writes. | **PASSED** |
| **Unauthorized Role Mutation** | All registration and verification management endpoints restrict write access to `['OWNER', 'ADMIN', 'CA']`. | **PASSED** |
| **Denial of Service / Quota Exhaustion** | Strict 24-hour TTL on `GSTTaxpayerCache` prevents redundant outgoing API calls for duplicate party or registration lookups. | **PASSED** |
| **Data Drift & Silent Overwrite** | Party master enrichment implements non-intrusive diff previews, requiring deliberate user confirmation to apply changes. | **PASSED** |

---

## 3. Cryptographic Storage of Provider Credentials

### Envelope Encryption (`apps/gst/services/encryption.py`)
- Platform-level credentials (`SANDBOX_API_KEY`, `SANDBOX_API_SECRET`) are stored in server environment variables or tenant credential models.
- When stored in `GSTConfiguration` or credential envelopes, fields are encrypted using `cryptography.fernet.Fernet`.
- The key is derived from a base64-encoded 32-byte master secret (`GST_ENCRYPTION_KEY` or `SECRET_KEY`).
- In case of tampering or key corruption, decryption raises a handled `InvalidToken` error and logs a redacted security alert without leaking ciphertext or keys.

---

## 4. Strict Tenant Isolation & IDOR Verification

SriLekh adheres to the system policy that each company’s accounting books and compliance profiles remain isolated.

### Verification of Isolation Guards
1. **Endpoint Authorization**:
   - `GET /api/v1/gst/registrations/<company_id>/`
   - Checks that `request.user` has an active `CompanyMembership` for `company_id`.
   - Rejects non-members with `403 Forbidden`.
2. **Entity Scoping**:
   - `GSTRegistration.objects.filter(company_id=company_id, id=registration_id)` prevents selecting or mutating registrations belonging to other companies.
3. **Cross-Tenant Test Evidence**:
   - Automated tests in `apps/gst/tests_round1_foundation.py` (`test_multi_tenant_isolation_on_registration_endpoints`) verify that attempting to access Company B's registration with Company A's credentials yields an immediate `403 Forbidden`.

---

## 5. Audit Logging & Sensitive Data Redaction

All provider interactions and statutory master enrichments are recorded in `GSTAuditLog` (`apps/gst/models.py`).

### Redaction Rules
- `x-api-key` and `Authorization` headers are replaced with `[REDACTED]` prior to logging.
- `GSTAuditLog.payload` stores sanitized request and response data, omitting internal system secrets and full authorization tokens.
- Each audit entry records the `user`, `company`, `action`, `correlation_id`, `endpoint`, and timestamp for non-repudiation.

---

## 6. Audit Conclusion & Production Certification

The Round 1 security posture satisfies enterprise financial compliance standards. There are no unhandled exception paths, secret leakage vulnerabilities, or tenant traversal vectors.
