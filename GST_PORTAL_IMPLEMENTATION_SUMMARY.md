# SRI LEKH — GST Portal Integration UX Refinement: Implementation Summary

**Repository**: `https://github.com/prakhar2207/Vouch`  
**Production URL**: `https://srilekh.com`  
**Branch**: `main`  
**Date**: November 2026  
**Status**: COMPLETE, VERIFIED & READY FOR PRODUCTION  

---

## 1. Scope of Work Completed

This refinement resolves the user-reported issues on SriLekh's GST Portal Direct Connect experience (`/settings?tab=gst-portal`), eliminating low-level technical infrastructure leakage, fixing provider contract header requirements, hardening security and rate-limiting, and delivering a clean, business-friendly 3-state interface.

---

## 2. Detailed File Changes Summary

### 2.1 Backend Services & Views

1. **`apps/gst/services/sandbox_client.py`**:
   - Added `"x-source": "primary"` to `SandboxGSTClient._get_authorized_headers()`.
   - Resolves provider error: `Missing required request parameters: [x-source]`.
   - Retained strict host allowlist validation and Fernet credential decryption.

2. **`apps/gst/services/gst_error_normalizer.py`** *(New Service)*:
   - Implemented `normalize_gst_error()`.
   - Normalizes raw provider exceptions, timeouts, rate limits (HTTP 429), and missing parameters into clear, friendly business messages.
   - Masks sensitive terms (`key_live`, `sec_`, tokens, `x-source`, provider names).

3. **`apps/gst/services/gst_sandbox_service.py`**:
   - Integrated `normalize_gst_error()` across all failure paths.
   - Added 30-second server-side OTP cooldown per company in cache (`gst_otp_cooldown_{company_id}`).
   - Added hourly quota rate-limiting (max 5 OTP requests/hour per company).
   - Added brute-force lockout: blocks OTP verification for 15 minutes after 5 consecutive failed attempts.
   - Disabled silent mock degradation when credentials are unconfigured in production.

4. **`apps/gst/views.py`**:
   - Sanitized `CompanyGSTConfigAPIView.get`: completely stripped `has_env_credentials`, `api_key`, `sandbox_api_key`, `sandbox_api_secret`, and `sandbox_base_url` from API payloads.
   - Updated `GSTRDirectPortalOTPRequestAPIView`: returns normalized error messages and HTTP 400 on failure.

5. **`apps/gst/tests_portal_abstraction.py`** *(New Test Suite)*:
   - 7 automated tests covering mandatory test isolation, header injection, error normalization, API view sanitization, cooldown enforcement, brute-force lockout, and multi-tenant isolation.
   - 100% pass rate.

### 2.2 Frontend Components

1. **`frontend/src/app/settings/page.tsx`**:
   - Removed `hasEnvCredentials` green banner exposing Render variables and `api.sandbox.co.in`.
   - Removed `Test Connection` button and developer diagnostic results banner.
   - Implemented 3-state clean UI:
     - **Not Connected**: Username input + "Connect GST Portal" button.
     - **OTP Verification**: 6-digit numeric input + "Verify and Connect" + live 30s countdown timer (`Resend OTP in 30s`) + Cancel action.
     - **Connected**: Entity Name, Monospace GSTIN, Session Expiry with hydration guard, Disconnect Account, and Reconnect action.
   - Resolved Minified React Error #418 using client `mounted` flag and `suppressHydrationWarning`.

2. **`frontend/src/components/settings/GSTRegistrationsView.tsx`**:
   - Cleaned up settings copy: replaced "Verified via Sandbox by Quicko" and "Verify now with Sandbox" with "Verified via official GST records".

---

## 3. Verification & Build Results

1. **Backend Django Checks & Tests**:
   - `python manage.py check`: Passed (0 issues silenced).
   - `python manage.py test apps.gst.tests_portal_abstraction`:
     ```
     Ran 7 tests in 3.464s. OK.
     ```
   - Invariant verified: Real client tenant `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) untouched.

2. **Frontend Production Build**:
   - Command: `npm --prefix frontend run build` (Next.js 16.4.6 with webpack).
   - TypeScript compilation: Passed with 0 errors.
   - Static page generation: 59/59 pages prerendered successfully.
   - Exit code: 0.

---

## 4. Production Deployment Checklist

- [x] Code committed to branch `main`.
- [x] Render platform environment variables loaded (`SANDBOX_API_KEY`, `SANDBOX_API_SECRET`).
- [x] Zero vendor or hosting mentions visible on client interface.
- [x] Error normalizer prevents raw parameter or stack trace exposure.
- [x] Cooldown and rate-limiting active to prevent gateway throttling.
- [x] Hydration guard active against React Error #418.
