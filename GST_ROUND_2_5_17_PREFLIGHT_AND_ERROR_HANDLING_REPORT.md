# SRI LEKH GST — ROUND 2.5.17
# Deliverable 4: Preflight Configuration & Safe Error Normalization Report

**Repository**: https://github.com/prakhar2207/Vouch  
**Production Application**: https://srilekh.com  
**Audit Date**: November 23, 2026  
**Auditor**: Senior Frontend Engineer & Application Security Architect  
**Dedicated Test Tenant**: `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`)  

---

## 1. Production Abstraction & Error Redaction

Ordinary business owners (traders, distributors, retailers) must never see:
1. Provider names or API endpoints (`api.sandbox.co.in`).
2. Internal header requirements (e.g. `Missing required request parameters: [x-source]`).
3. Render environment variable diagnostics (`Render Platform Environment Credentials Active LIVE API READY`).
4. Raw tracebacks, Python exceptions, or database errors.

---

## 2. Technical Implementation

1. **Strict Separation of Preflight Flags**:
   - `eligible`: Validates whether the company has a valid 15-character GSTIN.
   - `gateway_configured`: Verifies that API key, secret, and HTTPS base URL are present.
   - `has_active_session` / `is_connected`: Validates non-expired session token for that specific registration.
   - Gateway readiness never implies connection status.

2. **Recursive Secret Masking in Audit Logs (`sanitize_audit_payload`)**:
   - Automatically redacts `password`, `otp`, `auth_token`, `access_token`, `api_secret`, `client_secret` with `***REDACTED***`.
   - Prevents sensitive credentials from appearing in `GSTAuditLog` or application logs.

3. **User-Friendly Error Translation (`normalize_gst_error`)**:
   - `Missing required request parameters: [x-source]` -> Translated to customer-friendly GST Portal communication notice.
   - `API access is disabled for this GSTIN` -> Translated to clear 4-step action guide for `services.gst.gov.in`.
   - Strips URLs, headers, and vendor details.

4. **Internal Developer Diagnostic Guard**:
   - `CompanyGSTConfigTestConnectionAPIView` is strictly restricted: only staff/superusers can invoke it. Ordinary users receive HTTP 403 Forbidden with clear error message.

---

## 3. Verification Test Evidence (Phase D & E)

| Test Case | Description | Result |
| :--- | :--- | :--- |
| `test_preflight_gateway_configured_false_when_missing_keys` | Gateway configured is False when keys are absent. | **PASSED** |
| `test_preflight_gateway_configured_false_when_invalid_url` | Non-HTTPS scheme (`ftp://...`) rejected with warning; gateway unconfigured. | **PASSED** |
| `test_preflight_separates_gateway_ready_from_session_active` | Gateway configured does NOT set `is_connected=True`. | **PASSED** |
| `test_audit_log_redacts_credentials` | Sanitizer recursively replaces all secrets with `***REDACTED***`. | **PASSED** |
| `test_error_messages_contain_no_internal_urls_or_headers` | Error messages contain zero internal URLs or headers. | **PASSED** |
| `test_test_connection_restricted_from_ordinary_users` | Ordinary users cannot call `test-connection` (HTTP 403 Forbidden). | **PASSED** |
| `test_test_connection_accessible_to_staff_admins` | Staff/Superusers can run internal diagnostic tooling. | **PASSED** |

---

## 4. Phase D & E Certification

**STATUS: CERTIFIED & COMPLIANT**  
Production interface completely abstracts backend infrastructure and sanitizes all operational errors.
