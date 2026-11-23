# SRI LEKH GST — ROUND 2.5.17
# Deliverable 1: Authentication Integrity & Token Schema Certification Report

**Repository**: https://github.com/prakhar2207/Vouch  
**Production Application**: https://srilekh.com  
**Audit Date**: November 23, 2026  
**Auditor**: Independent Principal Software & Security Architect  
**Dedicated Test Tenant**: `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`)  
**Protected Production Tenant**: `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) — STRICTLY UNTOUCHED

---

## 1. Executive Summary & Problem Resolution

In previous revisions, the GST Portal integration exhibited an architectural defect during OTP verification:
```python
# DEFECTIVE CODE (PERMANENTLY ELIMINATED):
auth_token = sb_data.get('auth_token') or sb_data.get('access_token') or sb_res.get('correlation_id')
```
This fallback allowed request tracking IDs (`correlation_id`) to be erroneously stored as authenticated taxpayer session tokens when Sandbox.co.in returned a correlation ID without a session token.

Under Round 2.5.17 Phase A, this vulnerability has been permanently eradicated with a strict schema validation pipeline.

---

## 2. Authentication Pipeline Architecture & Security Controls

The hardened verification pipeline in `apps/gst/services/gst_sandbox_service.py` enforces the following invariants:

1. **Zero Tracking ID Fallback**:
   - Only `auth_token` or `access_token` from provider data payload is accepted.
   - Any token matching `correlation_id`, request `txn_id`, or prefixing `CORR-`, `CHAL-`, `TXN-`, or `GST-` is rejected with error code `INVALID_SESSION_TOKEN`.
   - Token length is strictly enforced (`len(token) >= 10`).

2. **Provider Response & Status Validation**:
   - Rejects responses where `status_cd == "0"` or where the data object contains an `error` dictionary.
   - Requires HTTP 200 with valid data dictionary payload.

3. **Multi-Format Future Expiry Enforcement**:
   - Parses epoch milliseconds, epoch seconds, relative offsets, and ISO 8601 strings.
   - Enforces timezone-aware comparison against `timezone.now()`.
   - Rejects past timestamps, missing expiry, or malformed formats with `INVALID_EXPIRY`.

4. **Taxpayer GSTIN Mismatch Protection**:
   - Matches the GSTIN returned in the authenticated taxpayer session against the requested company registration GSTIN.
   - Mismatches immediately trigger `GSTIN_MISMATCH` rejection and audit logging.

5. **Sanitized Cryptographic Audit Logging**:
   - Every rejected authentication event logs to `GSTAuditService` with correlation ID, endpoint, and HTTP status.
   - Passwords, OTPs, API secrets, and tokens are automatically masked via `sanitize_audit_payload`.

---

## 3. Verification Test Evidence (Phase A)

All test cases implemented in `apps/gst/tests_round2_5_17_integrity.py` executed successfully against the dedicated sandbox:

| Test Case | Description | Result |
| :--- | :--- | :--- |
| `test_auth_rejects_missing_access_token` | Provider response without session token rejected with `INVALID_SESSION_TOKEN`. | **PASSED** |
| `test_auth_rejects_correlation_id_as_token` | Correlation ID in place of token rejected with `INVALID_SESSION_TOKEN`. | **PASSED** |
| `test_auth_rejects_status_cd_zero` | HTTP 200 with `status_cd: "0"` rejected; no session established. | **PASSED** |
| `test_auth_rejects_missing_expiry` | Response without expiry timestamp rejected with `INVALID_EXPIRY`. | **PASSED** |
| `test_auth_rejects_malformed_expiry` | Unparseable timestamp rejected with `INVALID_EXPIRY`. | **PASSED** |
| `test_auth_rejects_past_expiry` | Expired timestamp rejected with `INVALID_EXPIRY`. | **PASSED** |
| `test_auth_rejects_gstin_mismatch` | Session for mismatched GSTIN rejected with `GSTIN_MISMATCH`. | **PASSED** |
| `test_auth_rejects_short_token` | Token length < 10 characters rejected with `INVALID_SESSION_TOKEN`. | **PASSED** |
| `test_auth_success_stores_valid_session` | Genuine token and future expiry sets `is_connected=True`. | **PASSED** |

---

## 4. Phase A Certification

**STATUS: CERTIFIED & COMPLIANT**  
The authentication flow strictly respects the Sandbox.co.in API contract and will never establish a session on unauthenticated tracking IDs or invalid credentials.
