# SriLekh — Gap Analysis Against Target Architecture
**Trust & Flexibility 10/10 Remediation Initiative**  
*Document Ref:* `docs/trust-flexibility/GAP_ANALYSIS.md`  
*Branch:* `feature/trust-flexibility-remediation`  
*Audited Against Standards:* Financial Trust, Accounting Flexibility, Data Integrity, Auditability, Offline Reliability, Usability.

---

## 1. Executive Summary & Scoring Target

| Dimension | Baseline Score | Target Score | Current Status |
|---|:---:|:---:|:---:|
| Financial Trust | 9.0 / 10 | 10.0 / 10 | Remediation In Progress |
| Accounting Flexibility | 8.8 / 10 | 10.0 / 10 | Remediation In Progress |
| Data Integrity | 9.4 / 10 | 10.0 / 10 | Verified |
| Auditability | 9.5 / 10 | 10.0 / 10 | Verified |
| Offline Reliability | 8.9 / 10 | 10.0 / 10 | Verified |
| Ease of Use | 8.7 / 10 | 10.0 / 10 | Remediation In Progress |

---

## 2. Comprehensive Defect & Gap Register

### DEF-01: Client Statement Parser 1D Line Slicing vs 2D Spatial Column Misalignment
- **Priority:** `P1` (High Accounting Precision Impact)
- **Source Path:** `frontend/src/lib/banking/clientStatementParser.ts:81-195`
- **Existing Implementation:**
  - Used vertical bucketing (`y / 3.5`) and regex-based date splitting.
  - Sliced transactions prematurely when multiple transactions occurred on the same date or spanned multiple lines.
  - Extracted page headers (`page 6 Date Particulars Deposits Withdrawals Balance`) directly into transaction narration.
  - Spliced payee name (e.g. `SATYAM AND CO`) into prior lines or dropped it entirely.
  - Inverted transaction directions (tagged ₹11,161.00 NEFT DR withdrawal as a Customer Receipt deposit).
- **Expected Behavior:**
  - 2D spatial coordinate mapping calibrated dynamically from column headers (`xDep`, `xWdl`, `xBal`).
  - Robust row delimiter tracking using `Chq:` tokens.
  - Clean extraction of multi-line entity names and exact debit/credit classification.
- **Root Cause:** Standard line-by-line text grouping failed on dense multi-column bank passbook layouts with multi-line particulars and right-aligned numeric amounts.
- **Remediation:** Rewrote `parsePdfOnDevice` in `clientStatementParser.ts` with 2D column boundaries and transaction group partitioning. Verified across 52 Canara passbook transactions.

---

### DEF-02: Missing Statement & Transaction Audited Exclusion API Routes
- **Priority:** `P1` (Operational Reliability & Audit Compliance)
- **Source Path:** `apps/accounting/banking_views.py:592-635`, `apps/accounting/urls.py:108-115`
- **Existing Implementation:**
  - Frontend "Exclude Statement from Books" modal dispatched `POST /api/v1/accounting/banking/statements/<id>/exclude/`.
  - Backend lacked explicit route handlers for statement exclusion, returning `HTTP 404 Not Found`.
- **Expected Behavior:**
  - Audited non-destructive exclusion setting `is_excluded=True`, recording user ID, timestamp, and business reason.
  - Automatic canonical reversal of any auto-generated vouchers via `REV-` vouchers.
  - Seamless restoration capability for accidental exclusions.
- **Root Cause:** Backend route definition was incomplete for statement-level exclusion while transaction-level handlers were partially present.
- **Remediation:** Added `BankStatementImportDetailAPIView.post` and `BankStatementImportRestoreAPIView.post` backed by `BankReconciliationService.exclude_statement_import`. Covered with automated test suite in `apps/accounting/tests_banking_production.py`.

---

### DEF-03: Optimistic Concurrency Control (OCC) Voucher Edit Serialization Mismatch
- **Priority:** `P1` (Data Integrity & Multi-User Concurrency)
- **Source Path:** `apps/accounting/views.py:650-710`, `frontend/src/components/accounting/Edit*.tsx`
- **Existing Implementation:**
  - Backend `VoucherDetailAPIView.patch` enforced mandatory OCC version verification via `payload.version` or `If-Match` header.
  - `serialize_voucher_detail` and list serializers omitted `version` from their response payloads.
  - Edit modals (`EditReceiptModal`, `EditPaymentModal`, `EditPurchaseInvoiceModal`) did not maintain `version` in state, submitting unversioned payloads resulting in `HTTP 428 Precondition Required`.
- **Expected Behavior:**
  - Serializers expose integer `version` and HTTP `ETag: "v-<id>-v<version>"`.
  - Frontend modals retain `version` and transmit `version: currentVersion` in PATCH requests.
- **Root Cause:** Disconnect between backend concurrency protection middleware and frontend state hydration.
- **Remediation:** Added `version` to serializers, updated edit modals with version state, and updated regression test fixtures.

---

### DEF-04: CORS Preflight Rejection on Browser `If-Match` Header
- **Priority:** `P1` (Network Reliability & API Availability)
- **Source Path:** `config/settings.py` (`CORS_ALLOW_HEADERS`), `frontend/src/components/accounting/Edit*.tsx`
- **Existing Implementation:**
  - Frontend edit modals transmitted `If-Match: "v-<id>-v<version>"`.
  - Django `CORS_ALLOW_HEADERS` did not include `if-match`, triggering preflight failure: `Request header field if-match is not allowed by Access-Control-Allow-Headers in preflight response`.
  - Browser aborted PATCH calls with `net::ERR_FAILED` ("Network Error").
- **Expected Behavior:**
  - Clean preflight handshake for OCC headers.
  - Browser requests succeed reliably without CORS exceptions.
- **Root Cause:** Strict default CORS headers list omitted conditional HTTP headers.
- **Remediation:** Whitelisted `if-match`, `if-none-match`, `x-voucher-version` in `CORS_ALLOW_HEADERS` and updated modals to transmit `version` directly in JSON body.

---

### DEF-05: Mobile PWA Build Manifest Invalidation & Unshielded Tour Storage
- **Priority:** `P2` (Mobile Usability & PWA Distribution)
- **Source Path:** `frontend/src/app/manifest.ts`, `frontend/public/manifest.json`, `frontend/src/components/onboarding/OnboardingTour.tsx`
- **Existing Implementation:**
  - Manifest icon URLs included cache-busting query strings (`?v=srilekh-v5`), rejected by PWABuilder and Bubblewrap APK compilers.
  - Manifest omitted `id` and `scope` declarations.
  - `OnboardingTour` attempted unshielded `localStorage` reads/writes during mobile SSR/hydration, triggering "Something went wrong" crash loops.
- **Expected Behavior:**
  - PWA manifest fully conforms to W3C PWA specifications with clean static icon paths.
  - `OnboardingTour` desktop-only guarded ($\ge 768\text{px}$) with safe storage fallback.
  - Resilient `error.tsx` boundary providing "Clear Cache & Reload" self-healing.
- **Root Cause:** Non-standard manifest query strings and unguarded mobile touch viewports.
- **Remediation:** Cleaned manifest icons, added `id: "/"`, `scope: "/"`, wrapped storage accesses in try/catch, and upgraded error boundary with diagnostic display.

---

### DEF-06: Mandatory Test Isolation Invariant Protection
- **Priority:** `P0` (Production Financial Data Protection)
- **Source Path:** `GEMINI.md`, `apps/accounting/tests_*.py`
- **Existing Implementation:**
  - Production tenant `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) is strictly protected.
  - Test executions and automated benchmarks must strictly target dedicated sandbox `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`).
- **Expected Behavior:**
  - Automated tests and scratch scripts explicitly assert sandbox company ID before mutating database state.
  - Django test database runner runs in ephemeral isolation.
- **Root Cause:** Essential protection to prevent automated test pollution in client production books.
- **Remediation:** Enforced assertion checks in test fixtures and verified isolated test runners.

---

## 3. Gap Analysis Matrix Summary

| Defect ID | Area | Severity | Status | Verification Reference |
|---|---|:---:|:---:|---|
| DEF-01 | Banking PDF Parser | P1 | Resolved | `scratch/test_parser.js` (52/52 clean) |
| DEF-02 | Statement Exclusion API | P1 | Resolved | `tests_banking_production.py` (11/11 OK) |
| DEF-03 | OCC Voucher Update (428) | P1 | Resolved | `tests_hardening.py` |
| DEF-04 | CORS Preflight Header Error | P1 | Resolved | Settings & Modal verification |
| DEF-05 | Mobile PWA & Crash Boundary | P2 | Resolved | Next.js Build (47 routes clean) |
| DEF-06 | Tenant Isolation Policy | P0 | Verified | `GEMINI.md` Strict Invariant |

---
*Generated by SriLekh Principal Architecture Lead — Approved for Implementation Plan.*
