# SRI LEKH GST — ROUND 2.5.18
## Audit Log Security & Sensitive Data Redaction Report

**Repository:** `https://github.com/prakhar2207/Vouch`  
**Production Application:** `https://srilekh.com`  
**Baseline Commit:** `7856cca6e510b5a435a93c83a2eaf285dedbd8b5`  
**Target Branch:** `main`  
**Auditor Roles:** Application Security Engineer, Financial Systems Auditor  
**Date:** 2026-11-23  

---

### 1. Executive Summary

Statutory audit logs (`GSTAuditLog`) and filing error messages (`GSTFilingRecord.error_message`) must comply with data protection regulations, Section 155 of the CGST Act, and security best practices:
1. Under no circumstances may plaintext API keys, secrets, passwords, taxpayer OTPs, or bearer tokens be stored in logs.
2. Network timeouts and socket error strings must not leak internal IP addresses, ports, or raw HTTP headers into error fields or user-facing responses.

In Round 2.5.18:
1. `GSTAuditService` applies recursive key-based redaction and regex scrubbing across all logged payloads.
2. Direct filing network timeout handlers now scrub raw socket strings into clean, sanitized diagnostic messages.

---

### 2. Redaction Architecture

#### Sensitive Key Dictionary:
```python
SENSITIVE_KEYS = {
    'api_key', 'api_secret', 'secret', 'password', 'eway_password',
    'einvoice_password', 'auth_token', 'token', 'access_token',
    'otp', 'sandbox_api_key', 'sandbox_api_secret', 'authorization',
    'x-api-key', 'x-api-secret', 'client_secret', 'clientid', 'client_id',
    'bearer', 'refresh_token', 'jwt'
}
```

#### Exception String Sanitization:
In `upload_gstr1_direct()`:
```python
except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
    logger.exception(f"GSTR-1 submission network failure/timeout: {exc}")
    filing_rec.status = 'RECONCILIATION_REQUIRED'
    filing_rec.error_message = "Network timeout during submission. Outcome pending reconciliation."
    filing_rec.save(update_fields=['status', 'error_message', 'updated_at'])
```
Raw strings like `HTTPSConnectionPool(host='api.sandbox.co.in', port=443): Max retries exceeded` are strictly excluded from `filing_rec.error_message`.

---

### 3. Empirical Test Evidence

| Test Case | Scenario Description | Redaction Assertion | Result |
| :--- | :--- | :--- | :--- |
| `test_no_bearer_tokens_or_passwords_in_audit_logs` | Payload with `auth_token`, `password`, `x-api-key` | All replaced with `"REDACTED"` | **PASS** |
| `test_no_raw_network_exception_leaked_in_filing_error` | Network ConnectTimeout with raw pool details | Stored error message sanitized; pool details excluded | **PASS** |

---

### 4. Conclusion
Audit logging and error persistence satisfy stringent financial privacy and application security standards.
