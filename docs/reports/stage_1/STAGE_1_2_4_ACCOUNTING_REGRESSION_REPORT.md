# SRI LEKH — STAGE 1.2.4 ACCOUNTING & INVENTORY REGRESSION REPORT

**Assessment Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness`  
**Overall Gate Status (Gate F):** **PASS** *(Zero Accounting Regressions; Full PostgreSQL Concurrency, OCC & Double-Entry Suites Green)*

---

## 1. Accounting Logic Non-Modification Confirmation

Stage 1.2.4 made **zero changes** to double-entry posting rules, tax engines, rounding, ledger balance math, or voucher OCC logic. Code edits were restricted strictly to frontend/backend spreadsheet/XML upload parsing & input validation ([`upload_security.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/upload_security.py), [`spreadsheet-parser.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/import/spreadsheet-parser.ts)), [`PriceListImportModal.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/components/modals/PriceListImportModal.tsx), [`mobile-shell/index.html`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/mobile-shell/index.html), and test expansions.

---

## 2. Stage 1.2.4 Regression Execution Matrix

| Test Run / Command | Target Database | Result | Key Invariants Proven |
| :--- | :--- | :--- | :--- |
| **`apps.accounting.tests_postgresql_concurrency` + `tests_voucher_occ` + `tests_stage4_12_remediation` + `tests_stage4_13_stabilization` + `tests_stage4_14_certification` + `tests_financial_reports` + `apps.inventory.tests_stage4_15_inventory` + `tests_price_list_integrity` + `apps.ledgers.tests_opening_balance`** | **Neon PostgreSQL 18.6 (`test_neondb_staging --keepdb`)** | **62 / 62 PASSED (`OK`, 1356.600s, `0` failures, `0` errors)** | Real PostgreSQL MVCC concurrent voucher `PATCH` `200+409` & `428` OCC checks; `select_for_update()` stock lock (`Stage415ConcurrentInventoryTests`); FIFO lot depletion & voucher reversal stock restoration; Balance Sheet parity (`is_balanced`), P&L, Trial Balance, opening balance, duplicate payment/sales protection, outbox worker locking, and DR audit-hash chain restoration |
| **`apps.accounts.tests_play_launch_account_deletion` + `apps.accounting.tests_upload_security`** | **Neon PostgreSQL 18.6 (`test_neondb_staging --keepdb`)** | **15 / 15 PASSED (`OK`, 111.556s, `0` skipped)** | True multi-threaded `TransactionTestCase` parallel account deletion returning `200` + `409`, rate throttle (`429`), intact `AuditLog` hash chain, XXE/ZIP-bomb upload hardening + valid GSTR-2B Excel ingestion |
| **Batch A: `tests_stage1_2_auth_cookies` + `tests_auth_otp` + `tests_staging_isolation` + `tests_upload_security` + `apps.audit.tests` + `tests_stage4_15_auth` + `apps.gst.tests_itc_reconciliation`** | Isolated SQLite | **56 / 56 PASSED (`OK`, 83.213s)** | HttpOnly cookies, CSRF, OTP lifecycle, staging DB isolation guard, upload security, `AuditLog` tamper detection (`VERIFIED` vs tampered), notification RBAC/IDOR (`403`/`404`), GSTR-2B reconciliation & GST hold API |
| **`apps.common.tests_disaster_recovery` + `apps.common.tests_code_review_findings`** | Isolated SQLite | **13 / 13 PASSED (`OK`, 6.868s)** | Encrypted backup/restore, `MultiFernet` rotation, Trial Balance self-healing, GST missing-state fail-closed (`V-02`), statement upload error masking, single-use SSE tickets |
| **`apps.accounts.tests_play_launch_account_deletion` (local SQLite check)** | Isolated SQLite | **9 / 9 PASSED, 1 skipped (`OK`)** | Skips only the PG MVCC multi-thread lock test cleanly (`executed & passed on test_neondb_staging` above) |
| **Frontend Suite (`cd frontend && npm test`)** | Node + `fake-indexeddb` + WebCrypto | **45 / 45 PASSED across 6 suites** | Offline sales voucher queueing, crash recovery (`IN_FLIGHT`), `X-Idempotency-Key` reconciliation, OCC `version` preservation, AES-GCM-256 tamper/AAD/multi-tenant checks, hardened spreadsheet parser |

---

## 3. Staging Isolation Confirmation

- `python scripts/verify_staging_identity.py`: `neondb_staging` (`PostgreSQL 18.6`, `76` public tables, `146` migrations, `6` staging companies, **`0`** records for protected production tenant `Maa Annapurna Belting Store`).
- Production branch `main` and production database `neondb` were never modified or queried by test suites.
