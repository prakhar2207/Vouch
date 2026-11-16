# SRI LEKH — GST ROUND 1.2.1 AUDIT REPORT: PROVIDER CLIENT & RESILIENCE
**Audited Target:** `apps/gst/services/sandbox_client.py` & `apps/gst/services/audit_service.py`  
**Git Commit:** `8860b99ac3f13db1c554b7d9b0a559a79c5a927e`  
**Branch:** `fix/stage4-12-day6-remediation`  
**Auditor:** Principal SaaS Architect & GST Integration Specialist  
**Date:** 2026-11-16  

---

## 1. Executive Summary

This independent forensic audit evaluates `SandboxGSTClient` (`apps/gst/services/sandbox_client.py`), the central provider integration client connecting SriLekh to the **Sandbox by Quicko** GST API (`https://api.sandbox.co.in`). 

The client coordinates:
1. Environment-aware credential and base URL resolution.
2. Two-legged JWT token exchange via `POST /authenticate`.
3. Bearer and header injection (`authorization`, `x-api-key`, `x-api-version`, `x-transaction-id`).
4. Safe retry mechanics for idempotent versus non-idempotent endpoints.
5. Structured audit logging via `GSTAuditService`.

This audit uncovers **one P1 architectural flaw concerning token caching and race conditions when `CompanyGSTConfig` is absent**, **one P2 flaw in token expiry lease parsing**, and **one P2 flaw regarding audit logging on non-company invocations**.

---

## 2. Detailed Findings

### FINDING CLI-01 (Severity: P1 — High)
**Token Stampede & Redundant `/authenticate` Roundtrips When `CompanyGSTConfig` Is Not Persisted**

- **File & Function:** `apps/gst/services/sandbox_client.py`: `get_access_token()` (lines 111–116 & 142–146).
- **Exact Problem:**
  `SandboxGSTClient.get_access_token()` checks whether a cached JWT token exists using:
  ```python
  now = timezone.now()
  if not force_refresh and self.config and self.config.sandbox_access_token:
      if self.config.sandbox_token_expires_at and self.config.sandbox_token_expires_at > (now + timedelta(minutes=5)):
          return self.config.sandbox_access_token
  ```
  And when a new token is fetched from `POST /authenticate`:
  ```python
  if self.config:
      self.config.sandbox_access_token = token
      self.config.sandbox_token_expires_at = now + timedelta(seconds=expires_in)
      self.config.save(update_fields=['sandbox_access_token', 'sandbox_token_expires_at'])
  ```
  However, in multi-tenant SaaS environments, credentials can be configured at the platform environment level via `SANDBOX_API_KEY` and `SANDBOX_API_SECRET` in `settings.py` / `.env` for companies that have not yet saved a custom `CompanyGSTConfig` row.
  
  When `self.config` is `None` (or when `company` is `None`, e.g. for global lookup tasks):
  1. `self.config` is `None`, so line 113 evaluates to `False`.
  2. The client **completely skips the cache check**.
  3. The client dispatches a new `POST /authenticate` network request on **every single outbound API call**, including every GSTIN verification and autocomplete request.
  4. Under concurrent user requests, this results in a **token stampede**, rapidly exhausting Quicko's rate limit on `/authenticate` (HTTP 429).
  5. Furthermore, there is **no mutex or distributed lock** around `get_access_token()`. Even with `self.config` present, 5 concurrent requests from the same company will all see the token as expired simultaneously and all 5 will fire `POST /authenticate`.

- **Reproduction Scenario:**
  1. Set platform-wide `SANDBOX_API_KEY` and `SANDBOX_API_SECRET` in staging.
  2. Create a new company without creating a `CompanyGSTConfig` record.
  3. Call `client.search_taxpayer(...)` 10 times consecutively.
  4. Observe network logs: `POST https://api.sandbox.co.in/authenticate` is executed 10 times instead of 1 time.

- **Business / Security Impact:**
  High latency overhead (adding 300–800ms per request), wasted provider quota, and immediate risk of HTTP 429 lockout during high-traffic billing periods.

- **Recommended Correction:**
  Implement a fallback distributed or memory cache using Django's standard cache framework (`django.core.cache.cache`):
  ```python
  cache_key = f"gst_sandbox_jwt_{self.company.id if self.company else 'global'}"
  cached_token = cache.get(cache_key)
  if cached_token and not force_refresh:
      return cached_token
  ```
  Wrap the token generation with a 10-second cache lock (`cache.lock(...)`) to prevent stampedes under concurrency.

- **Detected by Existing Tests?**
  **NO.** Tests mock `requests.request` with pre-created `self.config_a`, hiding the missing config execution path.

---

### FINDING CLI-02 (Severity: P2 — Medium)
**Incomplete Expiry Parsing for Nested Response Schemas**

- **File & Function:** `apps/gst/services/sandbox_client.py`: lines 135–136.
- **Exact Problem:**
  In `get_access_token()`, the response parsing handles nested keys for `token`, but fails to do so for `expires_in`:
  ```python
  token = data.get('access_token') or (data.get('data', {}).get('access_token') if isinstance(data.get('data'), dict) else '')
  expires_in = data.get('expires_in', 86400)
  ```
  If Sandbox by Quicko returns the token response wrapped in a standard `data` envelope:
  ```json
  {
    "status_code": 200,
    "data": {
      "access_token": "jwt...",
      "expires_in": 3600
    }
  }
  ```
  The code parses `token` correctly from `data['data']['access_token']`, but `data.get('expires_in', 86400)` returns `86400` (24 hours) because `expires_in` is nested inside `data['data']`.
  
  As a consequence, the application assumes a 24-hour token validity when the actual lease granted by Sandbox is only 1 hour (3600s). The client will not refresh the token until 23 hours later, resulting in repeated 401 Unauthorized errors on all subsequent API calls.

- **Reproduction Scenario:**
  1. Mock Quicko `/authenticate` returning `{"data": {"access_token": "valid_token", "expires_in": 3600}}`.
  2. Inspect `self.config.sandbox_token_expires_at`.
  3. The expiry timestamp is set to `now + 86400 seconds` (24h) instead of `now + 3600 seconds` (1h).

- **Business / Security Impact:**
  Medium. Once the 1-hour token expires on Quicko's servers, the application relies on the in-flight 401 retry handler rather than proactively refreshing the token before expiry.

- **Recommended Correction:**
  Update lines 135–136 to inspect both top-level and nested `expires_in`:
  ```python
  payload_data = data.get('data') if isinstance(data.get('data'), dict) else {}
  token = data.get('access_token') or payload_data.get('access_token') or ''
  expires_in = data.get('expires_in') or payload_data.get('expires_in') or 86400
  ```

- **Detected by Existing Tests?**
  **NO.** Test `test_client_authentication_success_and_caching` passes flat JSON: `{"access_token": "...", "expires_in": 86400}`.

---

### FINDING CLI-03 (Severity: P2 — Medium)
**Unlogged Outbound Calls When `self.company` Is Omitted**

- **File & Function:** `apps/gst/services/sandbox_client.py`: lines 256, 304.
- **Exact Problem:**
  `execute_request()` guards the audit logging call with:
  ```python
  if self.company:
      GSTAuditService.log_action(...)
  ```
  If `SandboxGSTClient` is instantiated without a `company` (e.g. for a global public verification or background system task), **no audit log is generated at all**. All outbound requests, HTTP statuses, and correlation IDs are silently lost.

- **Business / Security Impact:**
  Breaks statutory audit trail completeness for non-tenant-specific outbound requests.

- **Recommended Correction:**
  Allow `GSTAuditLog.company` to accept a system fallback or ensure `company` is mandatory for all client instances.

- **Detected by Existing Tests?**
  **NO.**

---

## 3. Resilience, Retry & Error Handling Matrix

| HTTP Scenario | Implementation | Forensic Assessment |
|---|---|---|
| **HTTP 401 (Token Expired)** | In `execute_request`: refreshes token once (`get_access_token(force_refresh=True)`) and retries the request with new bearer header. | **EXCELLENT.** Automatic recovery prevents user-facing errors on token expiry. |
| **HTTP 429 (Rate Limit)** | If `allow_retries=True`: sleeps `1.5 * attempt` seconds and retries (up to 3 times). If `allow_retries=False`: raises `GSTRateLimitExceededError` immediately. | **EXCELLENT.** Distinguishes idempotent reads from non-idempotent writes. |
| **Timeout (504)** | Retries up to 3 times on idempotent reads (`search_taxpayer`), aborts immediately on non-idempotent writes (`generate_einvoice`). | **EXCELLENT.** Strictly avoids duplicate invoice/IRN generation. |
| **Sensitive Redaction** | `GSTAuditService` recursively replaces keys in `SENSITIVE_KEYS` (`api_key`, `secret`, `password`, `token`, `otp`) with `"REDACTED"`. | **EXCELLENT.** Zero secret leakage in `GSTAuditLog`. |

---

## 4. Verdict & Release Readiness

**Dimension Verdict:** **CONDITIONAL PASS**  
The client architecture is exceptionally robust regarding timeouts, retry discrimination, and credential redaction. However, the token caching stampede (Finding CLI-01) and nested `expires_in` parsing (Finding CLI-02) must be resolved before high-concurrency production activation.
