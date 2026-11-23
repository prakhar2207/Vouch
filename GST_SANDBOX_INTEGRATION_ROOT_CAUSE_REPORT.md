# SRI LEKH — GST Sandbox.co.in Integration Root Cause Report

**Domain**: Third-Party GST Compliance API Integration  
**Provider**: [Sandbox by Quicko](https://console.sandbox.co.in/) (`api.sandbox.co.in`)  
**Official API Docs**: [GST Taxpayer Authentication API](https://sandbox-docs.readme.io/reference/gst-taxpayer-authentication)  
**Date**: November 2026  
**Status**: INVESTIGATED & RESOLVED  

---

## 1. Executive Summary & Clarification

SriLekh integrates with **Sandbox.co.in** as its authorized Application Service Provider (ASP/GSP) bridge. SriLekh does **not** communicate directly with the Government of India GST sandbox portal (`sandbox.gst.gov.in`); rather, **`api.sandbox.co.in`** serves as the API gateway whose backend infrastructure routes compliant calls to the GST Common Portal (GSTN).

This report analyzes the root causes of the prior integration failures:
1. The perimeter parameter exception: `Missing required request parameters: [x-source]`.
2. Confusion between API gateway authentication and taxpayer session generation.
3. Decoupling of the company GSTIN and custom GST Portal usernames.
4. Handling of the statutory condition where API access is disabled on the taxpayer's GST Portal profile.
5. Incomplete session lifecycle management (refresh and remote logout).

---

## 2. Root Cause Analysis

### 2.1 Perimeter Rejection: `Missing required request parameters: [x-source]`

#### The Defect
When users clicked *"Request Portal OTP"* in SriLekh, Sandbox.co.in immediately rejected the request with HTTP 400:
```json
{
  "code": 400,
  "error": "Missing required request parameters: [x-source]",
  "timestamp": 1795421420000
}
```

#### Technical Mechanism
According to Sandbox's official compliance contract:
- **Endpoint**: `POST https://api.sandbox.co.in/gst/compliance/tax-payer/otp`
- **Required Perimeter Headers**:
  - `authorization: <jwt_access_token>`
  - `x-api-key: <api_key>`
  - `x-api-version: 1.0.0`
  - `x-source: primary` *(or `secondary`)*
  - `Content-Type: application/json`
  - `Accept: application/json`

In the original backend client (`apps/gst/services/sandbox_client.py`), `_get_authorized_headers()` injected `authorization`, `x-api-key`, and `x-api-version`, but omitted `x-source`. Sandbox's API gateway rejects any request lacking `x-source` before querying GSTN.

#### Resolution
`SandboxGSTClient._get_authorized_headers()` was updated to inject `"x-source": "primary"` (configurable to `"secondary"` for secondary portal usernames) on all compliance calls.

---

### 2.2 False Positive: Gateway Authentication vs Taxpayer Session

#### The Defect
The previous interface displayed a prominent banner:
`"Successfully authenticated with Sandbox by Quicko"` / `"LIVE API READY"`
even when no taxpayer OTP had been entered and no valid GSTN session existed.

#### Technical Mechanism
Sandbox.co.in requires a 2-stage authentication hierarchy:
1. **Developer Gateway Token**: Obtained via `POST /authenticate` using `x-api-key` and `x-api-secret`. This token identifies SriLekh to Sandbox.co.in (valid 24h).
2. **Taxpayer Session Token**: Obtained only after calling `POST /gst/compliance/tax-payer/otp` and successfully verifying the 6-digit OTP via `POST /gst/compliance/tax-payer/otp/verify`. This token identifies the specific taxpayer to GSTN (valid ~6 hours).

The previous UI conflated Step 1 with Step 2, erroneously indicating that the business was "connected" before the taxpayer had completed OTP verification.

#### Resolution
SriLekh now evaluates `is_portal_connected` strictly on the presence of a valid, non-expired taxpayer session token:
```python
is_connected = bool(config.auth_token and (not config.token_expires_at or config.token_expires_at > timezone.now()))
```
Gateway credentials alone never mark a taxpayer as connected.

---

### 2.3 Independent Submission of GSTIN vs GST Portal Username

#### The Requirement
In India, a company's **GSTIN** is a 15-character statutory identifier (e.g. `09CIFPS1329P2ZL`). However, a taxpayer's **GST Portal Username** (created on `services.gst.gov.in`) may be:
- The GSTIN itself (default), OR
- A custom username created by the business (e.g. `annapurna_tax_2026`, `satyam_belting`).

#### The Defect
Previous implementations conflated the two fields or fell back to overwriting custom usernames with the GSTIN.

#### Resolution
1. The frontend explicitly accepts `portalUsername` independently from `gstin`.
2. The backend view `GSTRDirectPortalOTPRequestAPIView` separates `gstin` (`request.data.get('gstin') or company.gstin`) from `username` (`request.data.get('username') or gstin`).
3. The request body submitted to Sandbox adheres to the documented schema:
```json
{
  "username": "custom_taxpayer_username",
  "gstin": "09CIFPS1329P2ZL"
}
```

---

### 2.4 GST Portal API Access Disabled Condition

#### The Statutory Rule
GSTN requires taxpayers to explicitly opt-in to third-party software access:
1. Log into `services.gst.gov.in`.
2. Navigate to **My Profile > Manage API Access**.
3. Toggle **Enable API Request** to **Yes** and select duration (up to 30 days).

When disabled, GSTN rejects OTP requests. Sandbox returns an error payload indicating disabled API access.

#### The Defect
When this occurred, the UI displayed raw technical strings or generic network error boxes, leaving the accountant without guidance on how to fix the problem.

#### Resolution
`apps/gst/services/gst_error_normalizer.py` intercepts any response matching `"api access"`, `"enable api"`, `"manage api access"`, or `"api_access_disabled"` and returns the mandated customer message:
> *"GST API access is currently disabled for this GST registration. Please enable API access in your GST Portal account and try again."*

---

### 2.5 Session Token Expiry, Refresh, and Remote Logout

#### The Defect
1. Taxpayer session tokens expire after 6 hours. When expired, the UI failed to provide a clean 1-click refresh action.
2. Disconnecting previously cleared the database record locally, but left the active session dangling on Sandbox's upstream gateway.

#### Resolution
1. Implemented `POST /gst/compliance/tax-payer/session/refresh` via `SandboxGSTClient.refresh_portal_session()` and `GSTPortalService.refresh_portal_session()`.
2. Implemented `POST /gst/compliance/tax-payer/logout` via `SandboxGSTClient.logout_portal_session()` and `GSTPortalService.disconnect_portal_session()`.
