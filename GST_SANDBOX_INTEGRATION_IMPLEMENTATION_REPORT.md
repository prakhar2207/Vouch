# SRI LEKH — GST Sandbox.co.in Integration Implementation Report

**Domain**: Third-Party GST Compliance API Integration  
**Provider**: [Sandbox by Quicko](https://console.sandbox.co.in/) (`api.sandbox.co.in`)  
**Official API Docs**: [GST Taxpayer Authentication API](https://sandbox-docs.readme.io/reference/gst-taxpayer-authentication)  
**Date**: November 2026  
**Status**: IMPLEMENTED, TESTED, VERIFIED  

---

## 1. Summary of Changes

| Component | File | Description of Fix |
|---|---|---|
| **Header Contract** | `apps/gst/services/sandbox_client.py` | Added `"x-source": "primary"` and `"Accept": "application/json"` to all compliance headers. Added support for `source` and `omit_source`. |
| **Request Payloads** | `apps/gst/services/sandbox_client.py` | Updated `request_portal_otp` and `verify_portal_otp` to pass `{"username": ..., "gstin": ...}` strictly per Sandbox documentation. |
| **Session Lifecycle** | `apps/gst/services/sandbox_client.py` | Added `refresh_portal_session` (`POST /gst/compliance/tax-payer/session/refresh`) and `logout_portal_session` (`POST /gst/compliance/tax-payer/logout`). |
| **Error Normalization** | `apps/gst/services/gst_error_normalizer.py` | Added exact mapping for API access disabled: *"GST API access is currently disabled for this GST registration. Please enable API access in your GST Portal account and try again."* Cleaned OTP and technical exception masks. |
| **Portal Service** | `apps/gst/services/gst_sandbox_service.py` | Independent parameter handling for GSTIN and username. Integrated `refresh_portal_session` and `disconnect_portal_session` with remote logout and local database cleanup. |
| **API Endpoints** | `apps/gst/views.py` & `apps/gst/urls.py` | Registered `POST /api/v1/gst/portal/refresh/` (`GSTRDirectPortalRefreshSessionAPIView`). Updated disconnect view to call service disconnect. |
| **Frontend UI** | `frontend/src/app/settings/page.tsx` | Clean 3-state flow. Reset transient OTP/error state on company switch. Added "Extend Session" action. |
| **Multi-GSTIN View** | `frontend/src/components/settings/GSTRegistrationsView.tsx` | Cleaned up vendor terminology from registration cards. |

---

## 2. API Contract Specification & Verification

### 2.1 Authenticate with Sandbox Gateway
- **Endpoint**: `POST https://api.sandbox.co.in/authenticate`
- **Headers**:
  ```http
  x-api-key: <SANDBOX_API_KEY>
  x-api-secret: <SANDBOX_API_SECRET>
  x-api-version: 1.0.0
  Content-Type: application/json
  Accept: application/json
  x-transaction-id: AUTH-...
  ```
- **Response**: JWT access token (valid 24 hours), cached in Redis and database.

### 2.2 Generate Taxpayer OTP
- **Endpoint**: `POST https://api.sandbox.co.in/gst/compliance/tax-payer/otp`
- **Headers**:
  ```http
  authorization: <JWT_ACCESS_TOKEN>
  x-api-key: <SANDBOX_API_KEY>
  x-api-version: 1.0.0
  x-source: primary
  Content-Type: application/json
  Accept: application/json
  x-transaction-id: GST-...
  ```
- **Request Body**:
  ```json
  {
    "username": "custom_or_gstin_username",
    "gstin": "27AAACA1234A1Z5"
  }
  ```
- **Response Handling**:
  - If API access is disabled on the GST Portal: normalized to *"GST API access is currently disabled for this GST registration. Please enable API access in your GST Portal account and try again."*
  - If successful: returns `cooldown_seconds: 30` and transition to OTP screen.

### 2.3 Verify Taxpayer OTP
- **Endpoint**: `POST https://api.sandbox.co.in/gst/compliance/tax-payer/otp/verify?otp=<6_DIGIT_OTP>`
- **Headers**: Same headers including `x-source: primary`.
- **Request Body**:
  ```json
  {
    "username": "custom_or_gstin_username",
    "gstin": "27AAACA1234A1Z5"
  }
  ```
- **Response Handling**:
  - On valid OTP: saves `auth_token` and `token_expires_at` (converted from `session_expiry` millisecond timestamp) to `CompanyGSTConfig`.
  - On invalid/expired OTP: normalized to *"The OTP entered is incorrect or has expired. Please check and try again."*

### 2.4 Extend / Refresh Taxpayer Session
- **Endpoint**: `POST https://api.sandbox.co.in/gst/compliance/tax-payer/session/refresh`
- **Headers**: `authorization: <taxpayer_auth_token>`, `x-api-key`, `x-api-version: 1.0.0`, `x-source: primary`.
- **Response**: Extends active session by ~6 hours, updating database without requiring a new OTP prompt.

### 2.5 Invalidate Session (Logout)
- **Endpoint**: `POST https://api.sandbox.co.in/gst/compliance/tax-payer/logout`
- **Headers**: `authorization: <taxpayer_auth_token>`, `x-api-key`, `x-api-version: 1.0.0`.
- **Response**: Upstream session terminated and local database fields (`auth_token`, `token_expires_at`) set to null.

---

## 3. Test Suite Evidence & Results

Automated test execution from `apps.gst.tests_portal_abstraction`:
```
python manage.py test apps.gst.tests_portal_abstraction
```

### Execution Log
```
Creating test database for alias 'default'...
.............
----------------------------------------------------------------------
Ran 13 tests in 17.130s

OK
Destroying test database for alias 'default'...
Found 13 test(s).

System check identified no issues (0 silenced).
```

### Detailed Test Matrix

| # | Test Method | Covered Scenario | Result |
|---|---|---|---|
| **1** | `test_01_mandatory_test_isolation_invariant` | Verifies test suite operates on `Apex Belting (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`) and protects real tenant `Maa Annapurna Belting Store`. | **PASSED** |
| **2** | `test_02_api_access_disabled` | Verifies exact customer copy when API access is disabled on GST Portal. | **PASSED** |
| **3** | `test_03_api_access_enabled` | Verifies successful OTP request dispatch when API access is active. | **PASSED** |
| **4** | `test_04_missing_x_source_header` | Omits `x-source`, verifies provider perimeter rejection and mask of `[x-source]`. | **PASSED** |
| **5** | `test_05_valid_x_source_header` | Confirms injection of `x-source: primary`, `x-api-version: 1.0.0`, and headers. | **PASSED** |
| **6** | `test_06_invalid_gst_portal_username` | Verifies normalized guidance when taxpayer username does not exist. | **PASSED** |
| **7** | `test_07_invalid_otp` | Verifies normalized copy on incorrect OTP input. | **PASSED** |
| **8** | `test_08_expired_otp` | Verifies normalized copy on expired OTP input. | **PASSED** |
| **9** | `test_09_successful_otp_verification` | Verifies 6-hour token storage, DB persistence, and `is_portal_connected: True`. | **PASSED** |
| **10** | `test_10_expired_taxpayer_session` | Verifies past `token_expires_at` is evaluated as `is_portal_connected: False`. | **PASSED** |
| **11** | `test_11_company_switching` | Verifies company switching isolates credentials, username, and connected states. | **PASSED** |
| **12** | `test_12_cross_company_token_access` | Verifies RBAC barrier (User B cannot access or modify Company A's session). | **PASSED** |
| **13** | `test_13_token_refresh_and_logout` | Verifies session refresh and remote logout flow. | **PASSED** |

---

## 4. Frontend Compilation & System Health

1. **Django System Check**:
   ```
   python manage.py check
   System check identified no issues (0 silenced).
   ```
2. **Next.js Production Build**:
   ```
   npm --prefix frontend run build
   ✓ Compiled successfully in 30.9s
   ✓ TypeScript check completed with 0 errors
   ✓ 59/59 pages prerendered successfully
   Exit code: 0
   ```
