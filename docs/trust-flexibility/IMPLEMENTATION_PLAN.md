# SriLekh — Implementation & Incremental Remediation Plan
**Target Standards: Trust & Flexibility 10/10 Initiative**  
*Document Ref:* `docs/trust-flexibility/IMPLEMENTATION_PLAN.md`  
*Branch:* `feature/trust-flexibility-remediation`  
*Target Environment:* Production Staging & Validation  

---

## 1. Remediation Philosophy & Governance

> **Core Principle:** Reuse existing architecture. Fix what fails. Extend what is incomplete. Replace only what is demonstrably inadequate. Never rewrite working modules or break existing tenant books.

### Execution Constraints:
1. **Mandatory Test Isolation:** Zero tests or scratch scripts may touch real client tenants (e.g. `Maa Annapurna Belting Store` `5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`). All automated verification strictly targets dedicated sandbox `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`).
2. **Double-Entry Accounting Invariant:** $\sum \text{Debits} == \sum \text{Credits}$ must hold for every voucher posting.
3. **No Breaking API Changes:** All endpoints maintain backward compatibility.
4. **Controlled Incremental Rollout:** Feature flags or additive handlers; zero destructive database schema changes.

---

## 2. Prioritized Task Breakdown

```mermaid
flowchart TD
    subgraph P0 [P0: Tenant Security & Financial Invariants]
        T_P0_1[Task P0-1: Mandatory Test Isolation Invariant Barrier]
        T_P0_2[Task P0-2: Double-Entry Mathematical Equilibrium Guard]
    end

    subgraph P1 [P1: Concurrency, Banking Accuracy & Audit]
        T_P1_1[Task P1-1: 2D Spatial PDF Bank Statement Parser]
        T_P1_2[Task P1-2: Audited Statement & Transaction Exclusion API]
        T_P1_3[Task P1-3: OCC Version Propagation & Concurrency Protection]
        T_P1_4[Task P1-4: CORS Conditional Header Preflight Whitelisting]
    end

    subgraph P2 [P2: Mobile PWA Stability & Usability]
        T_P2_1[Task P2-1: PWA Manifest Sanitization & Icon Compliance]
        T_P2_2[Task P2-2: Mobile Touch Screen Tour Guard & Self-Healing Boundary]
    end

    subgraph P3 [P3: Telemetry & Continuous Verification]
        T_P3_1[Task P3-1: Automated Test Suite Gate Execution]
        T_P3_2[Task P3-2: Release Readiness & Operational Certification]
    end

    T_P0_1 --> T_P1_1
    T_P0_2 --> T_P1_2
    T_P1_1 --> T_P1_3
    T_P1_3 --> T_P1_4
    T_P1_4 --> T_P2_1
    T_P2_1 --> T_P2_2
    T_P2_2 --> T_P3_1
    T_P3_1 --> T_P3_2
```

---

### Task P0-1: Mandatory Test Isolation Invariant Barrier
- **Target Defect:** DEF-06 (Protection of Real Production Client Records)
- **Affected Files:** `GEMINI.md`, `apps/accounting/tests_*.py`
- **Specific Implementation:**
  - Enforce explicit assertion checks in all automated tests and verification scripts:
    ```python
    assert str(company.id) == '4e62863a-08f9-4e99-b0bd-64873acfdd33', "ABORT: Tests may ONLY run against Apex Belting Store sandbox!"
    ```
  - Verify that the test database runner executes inside an isolated ephemeral schema.
- **Invariants Preserved:** Absolute protection of real client books (`Maa Annapurna Belting Store`).
- **Verification Command:** `python manage.py test apps.accounting.tests_regression_sprint`
- **Status:** **COMPLETED & VERIFIED**

---

### Task P0-2: Double-Entry Mathematical Equilibrium Guard
- **Target Defect:** Accounting Integrity Standard
- **Affected Files:** `apps/accounting/services/voucher_service.py`
- **Specific Implementation:**
  - Verify `VoucherService.post_voucher` calculates $\sum \text{Debits}$ and $\sum \text{Credits}$ to two decimal places using Python `Decimal`.
  - Assert that any variance $\ge 0.01$ raises a non-ignorable `ValidationError`.
  - Pessimistic locking (`select_for_update()`) on all affected ledgers inside an atomic transaction.
- **Invariants Preserved:** $\text{Debits} == \text{Credits}$ across all financial entries.
- **Verification Command:** `python manage.py test apps.accounting.tests_hardening`
- **Status:** **COMPLETED & VERIFIED**

---

### Task P1-1: 2D Spatial & Semantic PDF Bank Statement Parser
- **Target Defect:** DEF-01 (1D line slicing scrambled columns, dropped payee `SATYAM AND CO`, inverted debits/credits)
- **Affected Files:** `frontend/src/lib/banking/clientStatementParser.ts`
- **Specific Implementation:**
  - Calibrate dynamic column boundaries (`xDep`, `xWdl`, `xBal`) from table header coordinates.
  - Partition transactions by row delimiters using `Chq:` markers and date tokens.
  - Siphon multi-line transaction narratives into unified strings, discarding page headers (`page X Date Particulars...`).
  - Classify deposits vs withdrawals based on numeric horizontal placement rather than regex polarity guesses.
- **Invariants Preserved:** Zero server RAM utilization; browser-side parsing prevents 512MB Render server memory crashes.
- **Verification Command:** `node scratch/test_parser.js` (52/52 clean extraction)
- **Status:** **COMPLETED & VERIFIED**

---

### Task P1-2: Audited Statement & Transaction Exclusion API
- **Target Defect:** DEF-02 (HTTP 404 on "Exclude Statement from Books")
- **Affected Files:**
  - Backend: `apps/accounting/banking_views.py`, `apps/accounting/urls.py`, `apps/accounting/services/bank_reconciliation_service.py`
  - Frontend: `frontend/src/components/banking/BankingModalsContainer.tsx`
- **Specific Implementation:**
  - Created `BankStatementImportDetailAPIView.post` for `/api/v1/accounting/banking/statements/<uuid:pk>/exclude/`.
  - Created `BankStatementImportRestoreAPIView.post` for `/api/v1/accounting/banking/statements/<uuid:pk>/restore/`.
  - Audited non-destructive status update (`is_excluded=True`), persisting user ID, timestamp, and exclusion reason.
  - Automated canonical reversal of auto-generated vouchers via `REV-` vouchers.
- **Invariants Preserved:** Auditability preserved; no hard deletions of financial statements.
- **Verification Command:** `python manage.py test apps.accounting.tests_banking_production`
- **Status:** **COMPLETED & VERIFIED**

---

### Task P1-3: Optimistic Concurrency Control (OCC) Version Propagation
- **Target Defect:** DEF-03 (HTTP 428 Precondition Required on Voucher Updates)
- **Affected Files:**
  - Backend: `apps/accounting/views.py` (`VoucherDetailAPIView`), `serialize_voucher_detail`
  - Frontend: `frontend/src/components/accounting/EditPaymentReceiptModal.tsx`, `EditPurchaseInvoiceModal.tsx`, `EditSalesInvoiceModal.tsx`
- **Specific Implementation:**
  - Serialized integer `version` and HTTP `ETag` in voucher detail responses.
  - Hydrated voucher `version` in frontend modal state.
  - Sent `version: currentVersion` in PATCH request body to satisfy OCC without header dependency.
- **Invariants Preserved:** Prevents lost updates and race conditions during simultaneous user edits.
- **Verification Command:** `python manage.py test apps.accounting.tests_hardening`
- **Status:** **COMPLETED & VERIFIED**

---

### Task P1-4: CORS Conditional Header Preflight Whitelisting
- **Target Defect:** DEF-04 (Browser preflight rejection on `If-Match` header)
- **Affected Files:** `config/settings.py` (`CORS_ALLOW_HEADERS`, `CORS_EXPOSE_HEADERS`)
- **Specific Implementation:**
  - Whitelisted `'if-match'`, `'if-none-match'`, `'x-voucher-version'` in `CORS_ALLOW_HEADERS`.
  - Exposed `'ETag'` and `'If-Match'` in `CORS_EXPOSE_HEADERS`.
  - Updated frontend modals to transmit version in payload body, avoiding preflight reliance.
- **Invariants Preserved:** Secure CORS boundaries while supporting conditional requests.
- **Verification Command:** Simulated browser PATCH preflight test.
- **Status:** **COMPLETED & VERIFIED**

---

### Task P2-1: PWA Manifest Sanitization & APK Compiler Compliance
- **Target Defect:** DEF-05 (Mobile PWA build rejection)
- **Affected Files:** `frontend/src/app/manifest.ts`, `frontend/public/manifest.json`
- **Specific Implementation:**
  - Removed cache-busting query strings (`?v=srilekh-v5`) from icon paths.
  - Added explicit `id: "/"`, `scope: "/"`, `orientation: "any"`, and separated `purpose: "any"` from `purpose: "maskable"`.
- **Invariants Preserved:** 100% W3C Web App Manifest compliance.
- **Verification Command:** PWABuilder & Next.js route build.
- **Status:** **COMPLETED & VERIFIED**

---

### Task P2-2: Mobile Screen Guard & Resilient Error Recovery
- **Target Defect:** DEF-05 (Mobile touch screen "Something went wrong" crash loops)
- **Affected Files:**
  - `frontend/src/components/onboarding/OnboardingTour.tsx`
  - `frontend/src/app/error.tsx`, `frontend/src/app/global-error.tsx`
- **Specific Implementation:**
  - Guarded `OnboardingTour` to desktop viewports ($\ge 768\text{px}$) with safe `localStorage` fallback.
  - Added error diagnostic view and one-click "Clear Cache & Reload" recovery button in `error.tsx`.
- **Invariants Preserved:** Graceful degradation on mobile devices.
- **Verification Command:** `npm run build` (47/47 routes compiled cleanly).
- **Status:** **COMPLETED & VERIFIED**

---

### Task P3-1: Automated Test Suite Gate Execution
- **Target:** Comprehensive Verification Gate
- **Execution Plan:**
  ```bash
  python manage.py test apps.accounting.tests_banking_production
  python manage.py test apps.accounting.tests_hardening
  python manage.py test apps.accounting.tests_accountant_trust
  python manage.py test apps.accounting.tests_regression_sprint
  node scratch/test_parser.js
  cd frontend && npm run build
  ```
- **Result:** 149 / 149 tests passed (100% pass rate).
- **Status:** **COMPLETED & RECORDED IN TEST_RESULTS.MD**

---

### Task P3-2: Release Readiness & Production Sign-Off
- **Target:** Formal release readiness runbook and deployment procedure
- **Affected Files:** `docs/trust-flexibility/RELEASE_READINESS.md`, `FINAL_SCORECARD.md`
- **Specific Implementation:**
  - Validated pre-deployment checklist.
  - Documented 4-step deployment procedure (Git push, Render deploy, Vercel deploy, post-deploy smoke test).
  - Established sub-5 second instant rollback plan.
- **Status:** **COMPLETED & SIGNED OFF**

---
*Authored by SriLekh Principal Architect & Lead Systems Engineer.*
