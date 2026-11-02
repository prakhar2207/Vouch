# SriLekh — Changelog
**Record of Incremental Remediation Changes**  
*Document Ref:* `docs/trust-flexibility/CHANGELOG.md`  
*Branch:* `feature/trust-flexibility-remediation`  

---

## [Unreleased / Production-Candidate] — 2026-11-02

### Added
- **Audited Statement Exclusion Endpoints:**
  - `POST /api/v1/accounting/banking/statements/<uuid:pk>/exclude/` — Non-destructive statement exclusion with business audit reason and automatic canonical voucher reversal.
  - `POST /api/v1/accounting/banking/statements/<uuid:pk>/restore/` — Safe statement restoration endpoint.
  - Associated service methods in `apps/accounting/services/bank_reconciliation_service.py` (`exclude_statement_import`).
- **Comprehensive Production Integration Test Suite:**
  - Added test coverage in `apps/accounting/tests_banking_production.py` verifying statement exclusion, transaction exclusion, and restoration workflows.
- **Client Error Boundary Telemetry:**
  - Enhanced `frontend/src/app/error.tsx` and `frontend/src/app/global-error.tsx` with error diagnostics, stack traces, and a "Clear Cache & Reload" recovery button.

### Changed
- **Client Statement Parser (2D Spatial & Semantic Engine):**
  - Upgraded `frontend/src/lib/banking/clientStatementParser.ts` from 1D regex line slicing to 2D dynamic coordinate column detection (`xDep`, `xWdl`, `xBal`).
  - Implemented boundary delimiter grouping by `Chq:` tokens, preserving multi-line payee names (e.g. `SATYAM AND CO`), removing boilerplate page headers, and accurately categorizing debits vs credits.
- **Optimistic Concurrency Control (OCC) Voucher Updates:**
  - Added `version` field serialization to `VoucherDetailAPIView.get`, `serialize_voucher_detail`, and universal voucher list serializers.
  - Added HTTP `ETag: "v-<id>-v<version>"` response headers.
  - Updated `EditPaymentReceiptModal.tsx`, `EditPurchaseInvoiceModal.tsx`, and `EditSalesInvoiceModal.tsx` to maintain version state and include `version` in PATCH payload bodies.
- **CORS Configuration:**
  - Added `if-match`, `if-none-match`, `x-voucher-version` to `CORS_ALLOW_HEADERS` in `config/settings.py`.
  - Exposed `ETag` and `If-Match` in `CORS_EXPOSE_HEADERS`.
- **PWA Manifest Standards:**
  - Sanitized `frontend/src/app/manifest.ts` and `frontend/public/manifest.json`, eliminating cache query strings from icon URLs to ensure 100% compliance with Android PWABuilder and Bubblewrap APK packaging.
  - Guarded `OnboardingTour.tsx` to desktop-only viewports ($\ge 768\text{px}$) and safeguarded all `localStorage` calls with try/catch.

### Fixed
- **DEF-01:** Fixed bank statement parser line bleeding that lost merchant names and scrambled amounts across page headers.
- **DEF-02:** Fixed HTTP 404 error when excluding bank statements from books.
- **DEF-03:** Fixed HTTP 428 Precondition Required error during voucher edits.
- **DEF-04:** Fixed CORS preflight rejection when sending conditional headers from browser.
- **DEF-05:** Fixed mobile PWA build failures and mobile touch screen crash loops.

---
*Maintained by SriLekh Core Platform Team.*
