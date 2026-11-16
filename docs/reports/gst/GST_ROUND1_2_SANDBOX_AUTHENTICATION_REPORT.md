# SriLekh — GST Round 1.2 Sandbox Authentication Report

## 1. Executive Summary

This report assesses the authentication pipeline between SriLekh and **Sandbox by Quicko** (`https://sandbox.co.in` / `https://api.sandbox.co.in`).

- **Authentication Architecture & Client**: **PASS** (Unit & Integration tested).
- **Live Provider Token Exchange**: **BLOCKED (Awaiting Owner Provisioning)** pending credential entry by the business owner in the Render Staging dashboard.

---

## 2. Official Provider Specification (`POST /authenticate`)

Verified against official Sandbox by Quicko developer documentation (`https://developer.sandbox.co.in`):

### Request Format
- **URL**: `POST https://api.sandbox.co.in/authenticate`
- **Headers**:
  ```http
  x-api-key: <SANDBOX_API_KEY>
  x-api-secret: <SANDBOX_API_SECRET>
  x-api-version: 1.0
  x-transaction-id: AUTH-<CORRELATION_ID>
  Content-Type: application/json
  ```
- **Body**: Empty JSON `{}`

### Expected Success Response (`HTTP 200 OK`)
```json
{
  "code": 200,
  "status": "success",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "expires_in": 86400
  }
}
```

---

## 3. Client Implementation Architecture (`SandboxGSTClient`)

1. **Token Caching & Lifecycle**:
   - Extracted JWT `access_token` is persisted in `CompanyGSTConfig.sandbox_access_token`.
   - Expiration timestamp is set to `now + timedelta(seconds=expires_in)`.
   - Pre-emptive refresh: If token is within 5 minutes of expiration, client automatically refreshes the token before dispatching API requests.
2. **Reactive 401 Re-Authentication**:
   - If a request receives `HTTP 401 Unauthorized` due to premature token revocation, the client executes an immediate forced refresh (`force_refresh=True`) and retries the request once.
3. **Log Scrubbing**:
   - Headers `x-api-key`, `x-api-secret`, and `authorization` are filtered through `redact_sensitive_payload()` prior to writing to `GSTAuditLog`.

---

## 4. Credential Availability Status in Staging

| Variable | Staging Status | Action Required |
| :--- | :---: | :--- |
| `SANDBOX_API_KEY` | `NOT_SET` | Owner must enter in Render Staging Environment |
| `SANDBOX_API_SECRET` | `NOT_SET` | Owner must enter in Render Staging Environment |
| `SANDBOX_BASE_URL` | `https://api.sandbox.co.in` | Verified active default |
| `GST_ENCRYPTION_KEY` | `NOT_SET` | Owner must generate and enter in Render Staging |

---

## 5. Verification Verdict

**VERDICT: BLOCKED (LIVE) / PASS (CLIENT ARCHITECTURE)** — The authentication pipeline is built, hardened, and test-verified. Live connection remains gated on owner credential provisioning.
