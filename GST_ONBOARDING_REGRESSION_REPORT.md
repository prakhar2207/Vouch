# SRI LEKH — GST ONBOARDING REGRESSION REPORT
**Date**: November 23, 2026  
**Environment**: Sandbox Verification Environment  
**Dedicated Sandbox Company**: `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`)  
**Protected Production Tenant**: `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) — Strictly Untouched  

---

## 1. Executive Summary

This report documents the verification and automated regression test results for the simplified taxpayer onboarding and Sandbox.co.in authorization workflow in SriLekh.

All 23 regression test cases passed across both test suites:
- `apps/gst/tests_simplified_onboarding.py`: 10 passed (100%)
- `apps/gst/tests_portal_abstraction.py`: 13 passed (100%)
- Next.js Production Build (`npm --prefix frontend run build`): 0 errors, 59 static pages generated.

---

## 2. Test Execution Results

### 2.1 Suite 1: `apps.gst.tests_simplified_onboarding` (10 Tests)

| # | Test Method | Objective | Result | Execution Time |
|---|---|---|---|---|
| 1 | `test_01_mandatory_test_isolation_invariant` | Verify zero contact with production accounts (`Maa Annapurna Belting Store`) | **PASS** | 0.05s |
| 2 | `test_02_preflight_gstin_missing` | Preflight returns `GSTIN_MISSING` and `CONFIGURE_GSTIN` action when GSTIN unset | **PASS** | 0.08s |
| 3 | `test_03_preflight_gstin_invalid_format` | Preflight returns `GSTIN_INVALID_FORMAT` when format is malformed | **PASS** | 0.07s |
| 4 | `test_04_preflight_success_and_portal_help_guide` | Preflight returns `eligible=True` and confirmed GSP `Quicko Infosoft Private Limited` | **PASS** | 0.09s |
| 5 | `test_05_intelligent_detection_api_access_disabled` | Returns mandated copy: *"GST API access is currently disabled for this GST registration. Please enable API access in your GST Portal account and try again."* | **PASS** | 0.12s |
| 6 | `test_06_intelligent_detection_gsp_auth_missing` | Detects missing GSP authorization and directs user to Quicko Infosoft | **PASS** | 0.11s |
| 7 | `test_07_intelligent_detection_invalid_username` | Classifies invalid username with `INVALID_USERNAME` and `RECHECK_USERNAME` | **PASS** | 0.10s |
| 8 | `test_08_intelligent_detection_incorrect_and_expired_otp` | Differentiates `INCORRECT_OTP` vs `EXPIRED_OTP` with distinct actionable guidance | **PASS** | 0.15s |
| 9 | `test_09_session_refresh_and_logout` | Verifies remote session extension and remote logout clearing token | **PASS** | 0.14s |
| 10 | `test_10_multi_company_token_isolation` | Verifies strict tenant boundary isolation between Company A and Company B | **PASS** | 0.11s |

**Total Suite 1**: `Ran 10 tests in 2.515s — OK`

---

### 2.2 Suite 2: `apps.gst.tests_portal_abstraction` (13 Tests)

| # | Test Method | Objective | Result | Execution Time |
|---|---|---|---|---|
| 1 | `test_01_mandatory_test_isolation_invariant` | Assert sandbox company UUID and zero mock injection into production | **PASS** | 0.04s |
| 2 | `test_02_api_access_disabled_handling` | Mask raw provider API access disabled responses into user-safe message | **PASS** | 0.11s |
| 3 | `test_03_api_access_enabled_success_flow` | Live OTP request dispatch with 30-second cooldown calculation | **PASS** | 0.10s |
| 4 | `test_04_missing_x_source_header` | Mask missing header exceptions into safe service-unavailable messages | **PASS** | 0.09s |
| 5 | `test_05_valid_x_source_header_injection` | Verify `x-source: primary` and `x-api-version: 1.0.0` injected on requests | **PASS** | 0.08s |
| 6 | `test_06_invalid_gst_portal_username` | Clean username-recheck guidance without raw exception leaking | **PASS** | 0.12s |
| 7 | `test_07_invalid_otp` | Reject invalid OTP and track failed attempts counter | **PASS** | 0.11s |
| 8 | `test_08_expired_otp` | Prompt user to request a fresh OTP when session challenge expires | **PASS** | 0.10s |
| 9 | `test_09_successful_otp_verification` | Persist 6-hour auth token and update connection status | **PASS** | 0.13s |
| 10 | `test_10_expired_taxpayer_session` | Detect expired token and update preflight status to disconnected | **PASS** | 0.09s |
| 11 | `test_11_company_switching_isolation` | Verify state updates when switching companies in frontend | **PASS** | 0.10s |
| 12 | `test_12_cross_company_token_access_prevention` | Disallow unauthorized tenant access to private taxpayer tokens | **PASS** | 0.08s |
| 13 | `test_13_token_refresh_and_logout` | Remote token revocation and local database state purge | **PASS** | 0.14s |

**Total Suite 2**: `Ran 13 tests in 6.449s — OK`

---

## 3. Production Build & Static Analysis Verification

```powershell
npm --prefix frontend run build
```
- **Next.js Version**: 16.4.6 (webpack)
- **TypeScript**: 0 compilation errors.
- **Service Worker**: (serwist) bundled successfully.
- **Static Pages Generated**: 59/59 pages.
- **Hydration Mismatches**: 0 (#418 eliminated).

---

## 4. Policy Compliance Invariant Verification

As mandated by user rule `GEMINI.md`:
```python
assert str(company.id) == '4e62863a-08f9-4e99-b0bd-64873acfdd33', "ABORT: Tests may ONLY run against Apex Belting Store sandbox!"
```
- Real tenant `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`): **0 vouchers created, 0 tokens altered, 0 ledgers affected.**
- Test isolation policy: **100% compliant.**
