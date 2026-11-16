# SRI LEKH — ACCOUNTING ENGINE REGRESSION REPORT

**Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness`  
**Accounting / Inventory Scope:** Double-entry vouchers (`Total Debits == Total Credits`), Optimistic Concurrency Control (`If-Match` / `version`), FIFO/stock locking (`select_for_update`), Balance Sheet / P&L / Ledger Statements, SHA-256 hash-chained `AuditLog`, and offline-first sync parity.

---

## 1. Executed Test Suites & Observed Results (Stage 1.2.3)

| Suite / Module | Database Target | Result | Coverage Summary |
| :--- | :--- | :--- | :--- |
| **`apps.accounting.tests_voucher_occ` + `apps.accounts.tests_play_launch_account_deletion` + `apps.accounts.tests_stage1_2_auth_cookies`** | Neon PostgreSQL 18.6 (`test_neondb_staging --keepdb`) | **26 / 26 PASSED (`OK`, 279.131s)** | Concurrent `VoucherDetailAPIView` PATCH OCC races (`200` + `409`/`428`), CSRF/cookie auth, hardened row-locked account deletion |
| **`apps.inventory.tests_stage4_15_inventory`** | Neon PostgreSQL 18.6 (`test_neondb_staging --keepdb`) | **3 / 3 PASSED (`OK`, 196.292s)** | Negative-stock policy enforcement, FIFO lot exhaustion, Credit/Debit Notes, Voucher reversal stock restoration, Balance Sheet parity (`is_balanced`), and multi-threaded concurrent stock lock (`select_for_update`, zero lost updates) |
| **`apps.accounting.tests_stage4_12_remediation.Stage412DEF02ConcurrentRaceTests`** | Neon PostgreSQL 18.6 (`test_neondb_staging --keepdb`) | **1 / 1 PASSED (`OK`, 64.567s)** | Concurrent metadata PATCH OCC race returning `[200, 409]` cleanly |
| **`apps.accounting.tests_financial_reports` + `apps.accounting.tests_statement_accounting` + `apps.audit.tests`** | Isolated SQLite | **18 / 18 PASSED (`OK`, 9.508s)** | P&L, Balance Sheet equilibrium, Bank Statement bulk resolution, Ledger Statement, and SHA-256 `AuditLog` chain verification |
| **`apps.accounting.tests_stage4_12_remediation` (full module)** | Isolated SQLite *(baseline note)* | `25 / 26` total in batch (`7/8` module) | All non-concurrent DEF-01/DEF-03 duplicate override, RBAC, and allocation checks passed; only PostgreSQL-only multi-threaded `Stage412DEF02ConcurrentRaceTests` hit SQLite table-lock and was verified `OK` on Neon PostgreSQL above |
| **Offline Sync & Client Operation Manager (`offline-sync.test.ts` + `stage1_2_offline_auth_privacy.test.ts`)** | Node + `fake-indexeddb` + WebCrypto `AES-GCM-256` | **39 / 39 Frontend Tests PASSED** | Offline voucher queuing, outbox crash recovery, `X-Idempotency-Key` reconciliation, OCC `version` preservation, tenant/user isolation, encrypted rest format |

---

## 2. Invariant & Policy Compliance Verification

- **No Accounting Logic Mutations Introduced in Stage 1.2.3:** Zero changes were made to voucher posting, ledger balance calculation, tax computation, or double-entry invariants.
- **Staging Database Identity Check (`scripts/verify_staging_identity.py`):** Confirmed `neondb_staging` (`PostgreSQL 18.6`, `76` public tables, `146` migrations, **`0`** rows for protected tenant `Maa Annapurna Belting Store`).
- **Pending Migrations Check (`python manage.py makemigrations --check --dry-run`):** **`No changes detected`** (`exit 0`).
