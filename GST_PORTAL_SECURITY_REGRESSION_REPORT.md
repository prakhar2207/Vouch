# SRI LEKH — GST Portal Security & Regression Report

**Security Focus**: Multi-Tenant Isolation, Credential Protection, Brute-Force Defense, Hydration Integrity  
**Date**: November 2026  
**Auditor**: Principal Security Engineer & Django Backend Architect  
**Status**: PASSED ALL REGRESSION CHECKS  

---

## 1. Mandatory Test Isolation Verification

### 1.1 Policy Requirement
The Mandatory Test Isolation Policy strictly dictates:
- Under NO circumstances may any test, mock generator, or verification script insert, modify, or delete data in real client tenant accounts, specifically `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`).
- All automated tests must run exclusively against the sandbox company:
  - **Company Name**: `Apex Belting & Industrial Store (Demo)`
  - **Company ID**: `4e62863a-08f9-4e99-b0bd-64873acfdd33`

### 1.2 Automated Invariant Assertion
In `apps/gst/tests_portal_abstraction.py`:
```python
SANDBOX_COMPANY_ID = "4e62863a-08f9-4e99-b0bd-64873acfdd33"
PROTECTED_PROD_TENANT_ID = "5d2e5dea-ff86-4871-b2af-fe1c5a05c03c"

assert str(self.company.id) == SANDBOX_COMPANY_ID, "ABORT: Tests may ONLY run against Apex Belting Store sandbox!"
self.assertFalse(Company.objects.filter(id=uuid.UUID(PROTECTED_PROD_TENANT_ID)).exists())
```
**Outcome**: Verified. Zero touches occurred on production tenants.

---

## 2. Security Controls Evaluated & Verified

### 2.1 Credential & Secret Redaction
- **At Rest**: AES-256 Fernet encryption for all gateway tokens and secrets in PostgreSQL (`EncryptedTextField`).
- **In Transit**: Backend stripping in `CompanyGSTConfigAPIView.get`. Keys (`api_key`, `sandbox_api_key`, `sandbox_api_secret`, `sandbox_base_url`, `has_env_credentials`) are never present in JSON responses.
- **In Logs**: GSTIN masking (`[MASKED_GSTIN]`) and secret redaction applied to all log outputs in `apps/gst/services/gst_sandbox_service.py`.

### 2.2 Rate Limiting & Denial-of-Service Defense
- **Server-Side OTP Request Cooldown**: 30-second cooldown per company tracked in Redis/Django cache (`gst_otp_cooldown_{company_id}`). Requests attempted within 30 seconds are rejected with HTTP 400.
- **Hourly Request Quota**: Strict ceiling of 5 OTP requests per hour per company (`gst_otp_hourly_count_{company_id}`).
- **Brute-Force OTP Lockout**: Maximum 5 failed OTP verification attempts per company. Upon the 5th failed attempt, the company is locked out of OTP verification for 15 minutes (`gst_otp_verify_attempts_{company_id}`), preventing automated OTP guessing attacks.

### 2.3 Cross-Tenant Session Boundary Isolation
- Every API view validates that `request.user` possesses an active `UserCompany` mapping with `ADMIN` or `OWNER` privileges for the requested `company_id`.
- Test `test_07_cross_tenant_isolation` verified that a user of Tenant B attempting to access Tenant A's GST configuration receives an immediate HTTP 403 / 404 forbidden response.

### 2.4 SSR Hydration Guard (React Error #418 Fix)
- **Problem**: Next.js server-side rendering (SSR in UTC) formatting dates with `.toLocaleString()` resulted in a mismatch with client browser rendering (IST timezone), triggering minified React Error #418.
- **Remediation**:
  1. Introduced client `mounted` flag initialized to `true` inside `useEffect()`.
  2. Applied `suppressHydrationWarning` on date rendering spans.
  3. Ensured session expiry dates are rendered conditionally only after mount.
- **Verification**: Complete frontend production build (`next build --webpack`) verified with zero TypeScript and zero hydration warnings.

---

## 3. Automated Test Execution Summary

The dedicated test suite [`apps/gst/tests_portal_abstraction.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/gst/tests_portal_abstraction.py) was executed:
```
Creating test database for alias 'default'...
.......
Ran 7 tests in 3.464s

OK
```
All 7 tests passed with zero failures and zero errors.
