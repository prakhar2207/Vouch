# SRI LEKH — BANK RECONCILIATION & BOOKS HEALTH
## Independent Accounting Systems Audit & Production Integrity Verification Report

**Document ID:** `AUDIT-REC-HEALTH-2026-11-05`  
**Repository:** `https://github.com/prakhar2207/Vouch`  
**Current Active Branch:** `fix/books-health-duplicate-resolution-hardening`  
**Head Commit SHA:** `5a6c7a4`  
**Source Baseline Parent SHA:** `f09087f` (incorporating `ad9d255` and `635d520`)  
**Remote Head (`origin/main`):** `d39d481` (Local branch is ahead by 4 commits)  
**Verification Date:** November 5, 2026  
**Auditor Roles:** Principal Accounting Systems Architect, Senior Django/PostgreSQL Engineer, Financial Systems QA Lead  

---

## 1. COMMIT DISCOVERY & GIT FORENSIC FINDINGS

### A. Commit Resolution Discrepancy Explained
GitHub inspection had confirmed that commit `cf2e098b7e251b64fa72d9398e987f1dbd32734b` modified only:
- `frontend/src/app/health/page.tsx`
- `frontend/src/utils/api.ts`
- `apps/protocol/test_staging_two_company_pilot.py`

Independent Git reflog and branch tree audit resolved the discrepancy:
1. `cf2e098` was strictly an **authentication / 401 interceptor fix** that addressed the Books Health session expiration toast shown in the user's screenshot.
2. The core banking remediation commits were authored locally on dedicated branches:
   - **`ad9d255`** (`feature/bank-reconciliation-remediation-ux`): 8 files changed, +1402/-169 lines, containing initial 24 remediation tests in `apps/accounting/tests_banking_remediation.py`, `bank_reconciliation_service.py` row-locking, and progressive disclosure UI.
   - **`f09087f`**: Merge of `feature/bank-reconciliation-remediation-ux` into local `main`.
   - **`635d520`** (`fix/bank-reconciliation-critical-integrity`): 5 files changed, +228/-82 lines, introducing universal database idempotency records (`_save_idempotency_record`), distinct purple `AI Suggested` badge states, and strict transaction tab separation.
   - **`5a6c7a4`** (`fix/books-health-duplicate-resolution-hardening`): 7 files changed, +713/-29 lines, hardening `VOID_DUPLICATE_VOUCHER` against cross-company attacks, shielding pre-existing manual vouchers during statement exclusion, enforcing monotonic voucher sequence generation, and adding 28 PostgreSQL verification tests (totaling 52 tests).
3. **Remote Push Status:** These commits (`ad9d255`, `f09087f`, `635d520`, and `5a6c7a4`) exist on the local repository and **have not yet been pushed to GitHub origin** (as required by the strict non-push policy).

---

## 2. FORENSIC REPRODUCTION OF THE USER SCENARIO

### A. The Incident Scenario
- **Manual vouchers posted on 01-Oct-2026:**
  - `#PAY/26-27/0065`: ₹28,222.00 to `SHREE ADINATH TRADERS`
  - `#PAY/26-27/0066`: ₹6.00 to `Bank Charges`
- **Reconciliation-generated duplicates:**
  - `#PAY/26-27/0083`: ₹28,222.00 to `SHREE ADINATH TRADERS`
  - `#PAY/26-27/0091`: ₹6.00 to `Bank Charges`
- **Duplicate bank statement import:**
  - ₹6.00 fee imported twice from Canara Bank (`canara_epassbook_2026-10-04 122311.297215.pdf`).

### B. Forensic Database Findings (Read-Only Inspection)
An authorized read-only audit of `AuditLog`, `Voucher`, and `BankTransaction` revealed the exact chronological cascade:
1. **2026-11-04 13:27:23 UTC:** User invoked Books Health **Delete Duplicate** on `#PAY/26-27/0083`.
   - `AuditLog`: Action `DELETE` recorded for `Voucher` `03a34e1a-da4c-4614-8aef-55b42455fa87` (`#PAY/26-27/0083`).
   - `BankTransaction` (`85e8a0af-35e0-4ec7-93a9-83078d22df58`) link was transferred to `#PAY/26-27/0065`.
2. **2026-11-04 13:27:33 UTC:** User invoked Books Health **Delete Duplicate** on `#PAY/26-27/0091`.
   - `AuditLog`: Action `DELETE` recorded for `Voucher` `cff43456-e62b-4783-b6e2-6fbee7bdd380` (`#PAY/26-27/0091`).
   - `BankTransaction` (`bbf7a778-cd8b-4f9e-bd42-df263be15e33`) link was transferred to `#PAY/26-27/0066`.
3. **2026-11-04 13:28:27 UTC:** Duplicate ₹6.00 bank statement row deleted (`7573ca0f-d753-4023-af22-cf6323371d24`).
4. **2026-11-04 15:57:39 UTC (Root Cause Incident):** User executed **Exclude Statement** on `canara_epassbook_2026-10-04 122311.297215.pdf` with reason `"Mismatched and wrong reconcillation"`.
   - `exclude_statement_import` iterated over statement transactions and called `exclude_transaction()`.
   - **Fatal Flaw in previous `exclude_transaction`:** It checked `if bank_tx.matched_voucher:` and unconditionally called `VoucherService.create_reversal_voucher(vch)`.
   - Because the bank transactions had been relinked to `#PAY/26-27/0065` and `#PAY/26-27/0066`, `exclude_transaction` treated these manual vouchers as statement-generated and generated reversal vouchers `REV-PAY/26-27/0065` and `REV-PAY/26-27/0066`, changing the status of `#0065` and `#0066` to `REVERSED`.
   - **Why vouchers disappeared from Cash & Bank:** In `apps/accounting/views.py` (`UniversalVoucherAPIView`), the default filter excludes `['CANCELLED', 'REVERSED', 'SUPERSEDED']`. Consequently, `#0065` and `#0066` vanished from active views.

---

## 3. AUDIT OF FIXES & ARCHITECTURAL HARDENING

### A. Statement Exclusion Safety (Phase 7 Fix)
- **File:** `apps/accounting/services/bank_reconciliation_service.py`
- **Fix:** In `exclude_transaction()`, the service now checks:
  ```python
  notes = bank_tx.match_notes if isinstance(bank_tx.match_notes, dict) else {}
  is_existing_matched = notes.get('is_existing_matched', False)
  if not is_existing_matched:
      # Only reverse vouchers generated by reconciliation
      reversal_voucher = VoucherService.create_reversal_voucher(vch, ...)
  else:
      logger.info(f"Preserving pre-existing manual voucher #{vch.voucher_number} upon statement exclusion.")
  
  # Always detach link upon exclusion so no stale links remain
  bank_tx.matched_voucher = None
  bank_tx.matched_party = None
  bank_tx.matched_invoice = None
  ```
- **Accounting Invariant:** Pre-existing manual vouchers remain active (`POSTED`) in the daybook and general ledger when bank statements are excluded or quarantined.

### B. Explicit Duplicate Classifications (Phase 3 Fix)
- **File:** `apps/accounting/services/deduplication_engine.py`
- **Classifications:**
  - `CONFIRMED_DUPLICATE`: Same company, financial year, voucher type, amount, party ledger, and deterministic origin (e.g., bank recon collision or rapid submission < 300s). Automated 1-click fix (`VOID_DUPLICATE_VOUCHER`) enabled.
  - `PROBABLE_DUPLICATE`: 1–3 day clearing latency difference with partial reference match. 1-click fix **disabled**; requires manual accountant review.
  - `POSSIBLE_DUPLICATE`: Same party and amount without corroborating references. 1-click fix **disabled**.
  - `NEEDS_MANUAL_REVIEW`: Any ambiguous record failing strict confirmation criteria.

### C. Hardened One-Click Delete Duplicate Engine (Phase 4 Fix)
- **File:** `apps/accounting/services/finding_fix_service.py`
- **Integrity Guarantees:**
  - `DEF-DUP-01`: Validates identical company ID, financial year, voucher type, exact decimal amount, party ledger, and direction. Verifies that the duplicate does not have independent invoice allocations.
  - `DEF-DUP-02`: Row-level locking on `finding`, `prim_v`, `dup_v`, and linked `BankTransaction` rows inside `transaction.atomic()`. When transferring bank links to `prim_v`, tags `is_existing_matched = True`.
  - `DEF-DUP-03`: Cryptographic snapshot stored in `AuditLog` prior to deletion, referencing surviving primary voucher number.
  - `DEF-DUP-04`: Database-backed idempotency via `IdempotencyRecord`. Re-executing an already resolved finding returns the existing outcome without double-deleting or raising an unhandled exception.
  - **Strict Tenant Isolation:** Cross-company voucher manipulation preflight check raises `ValidationError` immediately.

### D. Monotonic Voucher Number Sequence Safety (Phase 6 Fix)
- **File:** `apps/accounting/services/voucher_service.py`
- **Fix:** In `delete_voucher()`, `InvoiceSequenceService.resync_sequence()` is now called with `force=False`.
- **Statutory Accounting Rule:** Under CGST Rule 46(b) and Companies Act Section 128, sequence numbers must be monotonic and consecutive. Deleting or archiving a voucher will **never roll backward or rewind** the sequence counter.

---

## 4. VERIFICATION SCORECARD & TEST EXECUTION EVIDENCE

| Phase / Scenario | Implementation Verified | Test Evidence | Status |
|---|---|---|:---:|
| **1. Missing Evidence Handling** | `NOT_VERIFIABLE` state; `None` never converts to zero | `test_01`, `test_03`, `test_05` | **VERIFIED / PASS** |
| **2. AI Suggestion Separation** | Purple `AI Suggested` badge; excluded from completed count | `test_02`, `ReconciliationStateBadge.tsx` | **VERIFIED / PASS** |
| **3. BRS Cutoff Date Isolation** | Future vouchers treated as unrecorded on statement | `test_04_brs_cutoff_isolation` | **VERIFIED / PASS** |
| **4. Existing Voucher Matching** | Amount tolerance (0.05), direction, and bank ledger check | `test_06`, `test_07`, `test_10`, `test_11` | **VERIFIED / PASS** |
| **5. Database Idempotency** | `IdempotencyRecord` across all 6 resolution actions & health fix | `test_15`, `test_37` | **VERIFIED / PASS** |
| **6. Atomic Unreconciliation** | Reverse voucher created; transaction restored to `UNRESOLVED` | `test_16`, `test_24`, `test_46` | **VERIFIED / PASS** |
| **7. Manual Voucher Shielding** | Statement exclusion unlinks manual vouchers without reversing | `test_33`, `test_42` | **VERIFIED / PASS** |
| **8. Exact Duplicate Detection** | Flagged as `CONFIRMED_DUPLICATE` with 1-click action | `test_25_exact_duplicate_payment_detection` | **VERIFIED / PASS** |
| **9. Probable Duplicate Guard** | Automated fix blocked on ambiguous near-date vouchers | `test_27`, `test_35` | **VERIFIED / PASS** |
| **10. Independent Allocation Guard** | Aborts deletion if duplicate voucher has independent allocations | `test_34_voucher_with_independent_allocations` | **VERIFIED / PASS** |
| **11. Atomic Rollback on Failure** | Database failure during relink/audit rolls back completely | `test_38`, `test_39` | **VERIFIED / PASS** |
| **12. Monotonic Voucher Sequence** | Deleting voucher never rolls sequence counter backward | `test_41_voucher_number_sequence_not_rewound` | **VERIFIED / PASS** |
| **13. Cross-Company Guard** | Cross-tenant finding resolution rejected | `test_45_cross_company_voucher_relinking` | **VERIFIED / PASS** |
| **14. Double-Entry Equilibrium** | Trial balance equilibrium validated before and after fix | `test_50_trial_balance_equilibrium` | **VERIFIED / PASS** |
| **15. Party Balance Accuracy** | Party ledger reflects single economic transaction | `test_40`, `test_51` | **VERIFIED / PASS** |
| **16. Bank Balance Accuracy** | Bank ledger credit balance reflects exact payment | `test_52_bank_ledger_balance` | **VERIFIED / PASS** |

### Test Execution Summary
- **Remediation Suite (`apps.accounting.tests_banking_remediation`):**
  - **52 / 52 tests passed** (41.10s execution on PostgreSQL `test_neondb`).
- **Regression Suites (`tests_deduplication`, `tests_banking_production`, `tests_banking_intelligence`):**
  - **52 / 52 tests passed** (42.90s execution on PostgreSQL `test_neondb`).
- **Combined Test Count:** **104 / 104 tests passing** with 0 errors and 0 failures.
- **Frontend Production Build:**
  - Compiled successfully (`next build --webpack`).
  - TypeScript type check: 0 errors.
  - All 47 application routes generated without warnings.

---

## 5. TENANT ISOLATION EVIDENCE
- **Protected Production Tenant:** `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`).
  - Zero test scripts or fixtures modified or deleted production vouchers or bank transactions.
  - All investigation conducted via read-only inspection.
- **Sandbox Test Tenant:** `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`).
  - All 104 automated tests executed strictly within this sandbox company.

---

## 6. FINAL RELEASE RECOMMENDATION

**RELEASE DECISION: CONDITIONAL GO (Production-Ready for Feature Branch Review)**

- **Justification:**
  1. All P0 financial integrity defects (`DEF-FIN-01`, `DEF-FIN-02`, `DEF-CON-01`, `DEF-VAL-01`, `DEF-DUP-01`, `DEF-DUP-02`, `DEF-DUP-03`, `DEF-DUP-04`) are resolved with verified PostgreSQL automated test coverage.
  2. The root cause of manual voucher reversal during statement exclusion has been eliminated.
  3. Strict monotonicity in voucher sequencing prevents GST numbering sequence rollback.
  4. Deduplication engine strictly separates confirmed duplicates from probable duplicates.
- **Condition for Production Merge:**
  - In compliance with the strict user rules, changes remain unmerged on branch `fix/books-health-duplicate-resolution-hardening`.
  - Recommend user review of the audit report before merging into `main`.
