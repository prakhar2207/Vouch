# SRI LEKH — GST AUTHENTICATION LIFECYCLE REPORT
**Date**: November 23, 2026  
**System**: SriLekh GST Taxpayer Authentication Engine  
**Module**: `apps/gst/services/gst_sandbox_service.py` & `apps/gst/services/sandbox_client.py`  

---

## 1. Authentication Lifecycle State Diagram

```
                ┌──────────────────────────────────────┐
                │          [ DISCONNECTED ]            │
                └──────────────────┬───────────────────┘
                                   │
                    request_portal_otp(gstin, username)
                                   │
                                   ▼
                ┌──────────────────────────────────────┐
                │          [ OTP CHALLENGE ]           │
                │        (30s cooldown active)         │
                └──────────────────┬───────────────────┘
                                   │
                    verify_portal_otp(otp, txn_id)
                                   │
                                   ▼
                ┌──────────────────────────────────────┐
                │          [ LIVE CONNECTED ]          │
                │         (6-hour session token)       │
                └───────┬──────────────────────┬───────┘
                        │                      │
           refresh_portal_session()  disconnect_portal_session()
                        │                      │
                        ▼                      ▼
                ┌───────────────┐      ┌───────────────┐
                │ [ EXTENDED ]  │      │ [ REVOKED ]   │
                └───────────────┘      └───────────────┘
```

---

## 2. Security Controls & Rate Limiting

### 2.1 Cooldown & Hourly Request Limiting
To prevent abuse of GSTN's SMS gateway and adhere to compliance thresholds:
1. **Per-Request Cooldown**:
   - Enforced via Redis cache: `gst_otp_cooldown_{company.id}`.
   - 30-second minimum gap between successive OTP requests.
   - Returns code `COOLDOWN_ACTIVE` with `cooldown_remaining` seconds.
2. **Hourly Request Cap**:
   - Enforced via Redis cache: `gst_otp_hourly_count_{company.id}` (3600-second TTL).
   - Maximum 5 OTP requests per hour per company.
   - Prevents brute-forcing or SMS spamming of authorized signatory mobile numbers.
3. **Verification Brute-Force Shield**:
   - Enforced via Redis cache: `gst_otp_verify_attempts_{company.id}` (600-second TTL).
   - Maximum 5 failed verification attempts per challenge.
   - Locks challenge upon 5 failed attempts with code `MAX_ATTEMPTS_EXCEEDED`.

---

## 3. Token Storage & Multi-Tenant Isolation

### 3.1 Token Storage
- Session tokens are stored in the `CompanyGSTConfig` model associated with each `Company`:
  - `auth_token`: Encrypted session token returned by GSTN.
  - `token_expires_at`: UTC timestamp (defaulting to 6 hours from issue time).
  - `eway_username`: Associated registered taxpayer username.
- Sensitive credentials (`api_secret`, `auth_token`) are strictly deferred from list queries and never exposed via public API endpoints.

### 3.2 Tenant Isolation Policy
- All queries and updates to `CompanyGSTConfig` filter by `company=company`.
- Cross-company boundary checks ensure:
  - An active session on Company A (`Apex Belting`) has **zero effect** on Company B (`Apex Tooling`).
  - Company switching in the frontend triggers isolated preflight checks (`/api/v1/gst/portal/preflight/<company_id>/`).
  - Attempting to access another company's return or session token yields HTTP 403 / 404 forbidden.

---

## 4. Session Refresh and Remote Logout Protocol

### 4.1 Session Extension (Refresh)
- Endpoint: `POST https://api.sandbox.co.in/gst/compliance/tax-payer/session/refresh`
- Headers:
  - `x-source: primary`
  - `x-api-version: 1.0.0`
  - `authorization: Bearer <current_auth_token>`
  - `x-api-key: <sandbox_key>`
- Response: Returns updated `access_token` and `session_expiry` timestamp.
- Local Persistence: Updates `CompanyGSTConfig.auth_token` and `token_expires_at` in an atomic database transaction.

### 4.2 Disconnect (Remote Logout)
- Endpoint: `POST https://api.sandbox.co.in/gst/compliance/tax-payer/logout`
- Invalidation: Immediately revokes the session on GSTN/Sandbox servers.
- Database State: Clears `auth_token = ''` and `token_expires_at = None`.
- UI State: Transitions instantly to `Not Connected` state.
