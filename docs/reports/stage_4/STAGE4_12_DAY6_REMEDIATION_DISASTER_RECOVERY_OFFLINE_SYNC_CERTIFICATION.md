# SRI LEKH — STAGE 4.12 (DAY 6): REMEDIATION, DISASTER RECOVERY & OFFLINE SYNC CERTIFICATION

**Audit Date:** 2026-11-12  
**Repository:** `prakhar2207/Vouch`  
**Audit / Remediation Branch:** `fix/stage4-12-day6-remediation`  
**Remediation Commits:**  
- Backend & DR (`09459edcba9dc6a18f367579f1b506860e512b11`) — `fix(accounting,common,ledgers): resolve DEF-01..03, DR snapshot/migration isolation, and report N+1 queries`  
- Frontend Offline & Sync (`1c7e3941c644a822cf7892304ae1470881e89a36`) — `fix(offline,sync,auth): harden IndexedDB tenant/user isolation, outbox lifecycle, and OCC version preservation`  
**Untouched Baseline Release Branch:** `release/stage4-final-rc-integration` (`4888e451c7155220527b47e6ba5c3f09f14ec61d`)  
**Untouched Production Branch:** `main` (`f09087fa7d41d1d66b04c5e9c02c173fc3a7b0ac`)  
**Staging Database:** `neondb_staging` on `ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech` (fingerprint `6f4741bdaaf4`)  

---

## Certification Decision

**VERDICT: `CONDITIONAL PASS — Code Remediations, DR Drill, Outbox Stress & Offline-First Tests Verified Against Isolated Neon Staging; Live Render Redeploy & Public Probe Pending Before Day 7 / Production Promotion`**

All functional defects carried forward from Stage 4.11 (`DEF-01`, `DEF-02`, `DEF-03`), critical offline-first IndexedDB / multi-tenant isolation gaps, PostgreSQL report N+1 bottlenecks, and two newly discovered infrastructure bugs (an un-scoped multi-database `RunPython` migration and unstable chunked `ProtocolOperation` snapshot pagination) were resolved and verified on `fix/stage4-12-day6-remediation`.

**Blocking Conditions Preventing Full Live-Staging Sign-Off:**
1. **Live Render Staging Unreachable & Un-deployed:** Public HTTPS health probes to `https://vouch-u3u7.onrender.com` timed out with `0` bytes received, and `pg_stat_activity` showed `0` active connections from Render against `neondb_staging`. Consequently, the Stage 4.12 commits on `fix/stage4-12-day6-remediation` have **not** been exercised over public Render infrastructure — only via local Django WSGI, PostgreSQL `test_neondb_staging`, direct isolated `neondb_staging` harnesses, and Node 24 + `fake-indexeddb`.
2. **Staging Hygiene Carryovers:** `neondb_staging` retains `170` historical pre-existing `PENDING` outbox rows and `2` historical ledgers on `Staging MSME Alpha Belts Pvt Ltd` with cached `current_balance` drift relative to dynamic GL (Trial Balance remains ₹0.00 balanced).
3. **Production Deployment Prohibition Remains in Effect:** Merge into `main` and deployment to `srilekh.com` remain **prohibited** pending Render redeploy of `fix/stage4-12-day6-remediation` (or re-integrated RC), public HTTPS verification, and Day 7 soak completion.

---

## 1. Environment & Safety Isolation Verification

Every database check verified strict staging isolation before and after execution using [`get_environment_identity_metadata`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/config/environment_guard.py#L100-L172):

| Check | Verified Value | Status |
|---|---|---|
| PostgreSQL Host | `ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech` | PASS |
| Active Database | `neondb_staging` | PASS |
| Database Fingerprint | `6f4741bdaaf4` | PASS |
| `is_isolated` | `true` | PASS |
| Migrations Status | `up_to_date` (`unapplied_count: 0`, `makemigrations --check --dry-run` exit `0`) | PASS |
| Protected Production Tenant (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) | `0` rows in `neondb_staging` | PASS |
| Baseline RC Branch `release/stage4-final-rc-integration` | Untouched at `4888e451c7155220527b47e6ba5c3f09f14ec61d` | PASS |
| Public Render URL (`https://vouch-u3u7.onrender.com`) | HTTPS timeout (`0` bytes received; `0` Render DB connections) | BLOCKED |

---

## 2. Phase A — Stage 4.11 Functional Defect Remediations

### 2.1 DEF-01: Payment/Receipt Duplicate Override Governance & Idempotency
- **Fixed in:** [`authorize_and_resolve_duplicate_override`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/deduplication_engine.py#L43), [`parse_bool_flag`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/deduplication_engine.py#L32), [`log_duplicate_override`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/deduplication_engine.py#L67), and [`CreatePaymentReceiptAPIView`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/views.py#L2372).
- **Changes:**
  - Enforced strict RBAC for duplicate overrides (`OWNER`, `ADMIN`, `CA` permitted; `EMPLOYEE` / lower roles rejected with HTTP `403`).
  - Decoupled `allow_statutory_override` and `allow_negative_cash` flags from duplicate override resolution.
  - Replaced truthy string handling via `parse_bool_flag` so string `"false"` never triggers an accidental override.
  - Forwarded `force_duplicate` cleanly to `post_voucher`, recorded immutable `AuditLog` (`DUPLICATE_OVERRIDE`) entries, and persisted `IdempotencyService` replay records.

### 2.2 DEF-02: Posted Voucher PATCH Constraints, Payment Ledger Preservation & OCC
- **Fixed in:** [`VoucherDetailAPIView`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/views.py#L1085).
- **Changes:**
  - Blocked PATCH mutations on terminal statuses (`SUPERSEDED`, `REVERSED`, `CANCELLED`).
  - Rejected raw financial, `status`, `entries`, and `items` mutations on `POSTED` vouchers via partial PATCH while supporting safe metadata-only updates (including `due_date`) across `SALES`, `PURCHASE`, `RECEIPT`, `PAYMENT`, `JOURNAL`, and `CREDIT_NOTE`.
  - Fixed broken `4888e451` re-post indentation and `elif is_payment_receipt` control flow, and preserved `payment_ledger` before clearing entries during valid re-posts.
  - Preserved strict optimistic concurrency control (`version` validation & increment; `428` missing, `409` stale / concurrent conflict).

### 2.3 DEF-03: Sales, Purchase & Universal Voucher Deduplication Consistency
- **Fixed in:** [`_DuplicateConflictException`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/views.py#L8), [`_post_and_audit_voucher`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/views.py#L2727), [`CreateSalesInvoiceAPIView`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/views.py#L37), [`CreatePurchaseInvoiceAPIView`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/views.py#L314), [`UniversalVoucherAPIView`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/views.py#L2720), [`normalize_commercial_reference`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/deduplication_engine.py#L98), [`compute_items_canonical_hash`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/deduplication_engine.py#L117), [`check_duplicate_candidate`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/deduplication_engine.py#L162), [sales_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/sales_service.py), and [voucher_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/voucher_service.py).
- **Changes:**
  - Unified Case 1 / Case 2 duplicate conflict handling into `_post_and_audit_voucher` raising `_DuplicateConflictException` (`HTTP 409`) inside an atomic boundary with clean rollback, RBAC `403` enforcement, and `DUPLICATE_OVERRIDE` audit logging.
  - Updated `check_duplicate_candidate` to evaluate explicit `reference_number` / `external_invoice_number` (ignoring auto-mirrored `voucher_number` values) and canonical line-item hashes (`compute_items_canonical_hash`) so genuinely distinct bills on the same day are allowed while exact duplicates are blocked.
  - Forwarded `voucher_number` through `sales_service.create_sales_invoice` (`reference_number` persisted) and `voucher_service.post_voucher`, and included OCC `version` in responses.

### 2.4 Backend PostgreSQL Verification Results
All PostgreSQL test suites executed cleanly against `test_neondb_staging` **after** final edits:
- **Stage 4.12 Remediation Suite ([tests_stage4_12_remediation.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/tests_stage4_12_remediation.py)):** **8 / 8 passed (`OK`, `624.652s`)**:
  - `Stage412DEF01PaymentDuplicateTests` (2 tests): default duplicate blocking, authorized override, `EMPLOYEE` `403`, `"false"` string guard, distinct ref allowance, idempotency replay.
  - `Stage412DEF02PostedPatchTests` (2 tests): metadata PATCH across 6 posted voucher types without unintended re-posting; prohibited fields, terminal statuses, and cross-tenant IDOR blocking.
  - `Stage412DEF02ConcurrentRaceTests` (1 test): 2-thread barrier PATCH race returning `200` and `409`.
  - `Stage412DEF03SalesPurchaseDupTests` (2 tests): sales distinct items/refs, exact duplicate `409`, RBAC override + `DUPLICATE_OVERRIDE` audit, plus purchase & universal voucher paths.
  - `Stage412PhaseFQueryOptimizationTests` (1 test): batched P&L/BS balance calculation parity vs per-ledger baseline with strict query ceiling.
- **Core Regression Suite (`task-49474`, executed post-all edits):** **31 / 31 passed (`OK`, `298.325s`)** covering `apps.common.tests_disaster_recovery`, `apps.accounting.tests_voucher_occ`, `apps.accounting.tests_deduplication`, and `apps.accounting.tests_financial_reports`.

---

## 3. Phase B — Offline-First IndexedDB & Sync Engine Hardening

### 3.1 Implemented Hardening
- **[offlineDb.ts](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/db/offlineDb.ts):** Upgraded Dexie schema to `version(9)` indexing `companyId` and `userId` on `operationLog` and `outboxQueue`; exported [`hasPendingOfflineTransactions`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/db/offlineDb.ts#L395); hardened [`safePurgeTenantData`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/db/offlineDb.ts#L427) to wipe read caches (`syncedVouchers`, `syncedLedgers`, `syncedProducts`, `syncedBankTransactions`, `syncedPaymentAllocations`, `analyticsDaily`, `analyticsParty`, `syncMeta`, `masters`, `ocrCache`, `inboxQueue`, `syncCursors`, synced `vouchers`, `COMPLETED` outbox rows) while preserving unacknowledged `outboxQueue` (`QUEUED`, `IN_FLIGHT`, `FAILED`), linked `operationLog`, and unsynced local vouchers.
- **[auth.ts](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/auth.ts#L68), [CompanyContext.tsx](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/context/CompanyContext.tsx#L215), [DashboardLayout.tsx](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/components/DashboardLayout.tsx):** Cleared active company localStorage/Capacitor keys (`vouch_active_company_id`, `activeCompanyId`, `vouch_active_company`, `vouch_active_company_name`, `vouch_cached_companies_list`) on logout in `removeTokens()`, and added async `switchCompany` (plus `setActiveCompany` cleanup) awaiting `safePurgeTenantData(prevId)` before reloading.
- **[clientOperationManager.ts](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/crdt/clientOperationManager.ts#L19), [sync-worker.ts](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/sync/sync-worker.ts#L220), [sync-repository.ts](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/data/sync-repository.ts#L55):**
  - Tagged operations/outbox entries with `companyId` and `userId`; enforced both `[Tenant Guard]` and `[User Guard]` so Session B/Company B can never push queued mutations belonging to Session A/Company A.
  - Added per-process `activeSyncPromise` mutex, automatic crash recovery for orphaned `IN_FLIGHT` items, `X-Idempotency-Key` headers on protocol sync, and terminal handling (no infinite retry loop) on `403`/`409`/`422` responses in `pushPendingSalesInvoices`.
  - Preserved server OCC `version` across `RawVoucherDto`, `VoucherIngestInput`, `pushPendingSalesInvoices`, `pullIncrementalChanges`, and `ingestVoucherLocally`; updated `getSyncStatus(companyId)` to reflect company-scoped `outboxQueue` (`QUEUED`, `IN_FLIGHT`, `FAILED`).

### 3.2 Frontend Offline Verification Results (`task-49481`)
Executed via custom Node 24 TypeScript hook loader ([test-loader.mjs](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/test-loader.mjs)) + `fake-indexeddb/auto` + real WebCrypto Ed25519 keys ([offline-sync.test.ts](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/sync/offline-sync.test.ts)):
- **`npm test` (`frontend`):** **12 / 12 tests passed across 3 suites (`pass 12`, `fail 0`, `skipped 0`, `2258.6826ms`)**, including all 5 Stage 4.12 Phase B scenarios:
  1. Queues offline `SALES` voucher locally, exposes pending status, and reconciles cleanly upon reconnect with `X-Idempotency-Key` & server `version`.
  2. Recovers orphaned `IN_FLIGHT` outbox rows after crash/reload and retries `FAILED` transient `503` errors once backoff expires without duplicate IDs.
  3. Tenant Switch Safety: purges previous tenant UI caches while preserving its pending `outboxQueue` and refusing cross-tenant push (`comp-A` under `comp-B`).
  4. Cross-User Logout Safety: clears read caches & localStorage company state while preserving User A outbox and blocking User B from pushing it.
  5. Pull Incremental Changes & Local Ingest preserve server OCC `version`.
- **`npx tsc --noEmit`:** **Exit `0`** (zero TypeScript errors).
- **Note on ESLint:** `npx eslint src/lib/sync/offline-sync.test.ts` exited `0`; pre-existing `@typescript-eslint/no-explicit-any` technical debt remains in older untouched sections of `sync-worker.ts`, `clientOperationManager.ts`, and `DashboardLayout.tsx`.

---

## 4. Phase C — Backup, Disaster Recovery & Incident Remediations

### 4.1 Multi-Database `RunPython` Migration Bug Discovered & Remediated
- **Root Cause & Incident:** During initial DR provisioning (`migrate` against `dr_restore`) from a Django process whose `'default'` DB pointed to `neondb_staging`, [`consolidate_party_ledgers`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/ledgers/migrations/0003_consolidate_party_ledgers.py#L7) queried models without `.using(schema_editor.connection.alias)`. That caused `v.items.all().delete()` and `v.ledger_entries.all().delete()` to execute in autocommit on `neondb_staging` for voucher `4cd6c7f9-dc38-4093-9b91-216961273224` (`SUPP-INV-3356d0`, `9440.00`, `Supplier Apex Staging`) before FK protection on `PaymentAllocation` aborted `v.delete()`.
- **Repair & Fix:** Reconstructed the exact `1` `VoucherItem` and `4` `LedgerEntry` rows from cryptographic `ProtocolOperation OP-PUR-FC80D2A8` and `InventoryEntry`, recalculated ledger balances, verified `(0 zero-entry, 0 unbalanced)` across all posted vouchers, isolated DR `migrate`/`restore` steps into separate subprocesses bound to `DR_URL`, and updated [0003_consolidate_party_ledgers.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/ledgers/migrations/0003_consolidate_party_ledgers.py#L7) to enforce `.using(schema_editor.connection.alias)` on all ORM operations. Verified `makemigrations --check --dry-run` exits `0` (`No changes detected`).

### 4.2 Disaster Recovery Drill & Post-Fix Snapshot Parity
1. **Full Disposable DR Restore Drill (`task-49369`, executed pre-PK-sort fix in `backup_service.py`):**
   - **Encrypted Backup (`perform_backup(upload_s3=False, encrypt=True)`):** `23.135s`, `1.297 MB` (`1,360,184` bytes), SHA-256 `82896dfb9ec2a69614483d5a4a06464c3dc0a9d0db8a0fdffcf483d6cb7cfd36`, WAL LSN `0/99FA000`.
   - **Disposable Target (`neondb_staging_dr_restore`):** DB create `0.822s` + `migrate` (145 migrations) `158.281s` + bulk-optimized [`restore_backup`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/common/services/backup_service.py#L392) (`12,089` records, `error_count: 0`) `123.523s` = **Total RTO `282.626s` (~4m 43s)**.
   - **Accounting & Relational Parity Across All 5 Pilot Companies:** `orphan_entries: 0`, `orphan_items: 0`, `unbalanced_posted: 0`, **`financial_diffs: {}`** (₹0.00 variance on Trial Balance, Balance Sheet, and P&L).
   - **Pre-Fix Discrepancies Observed:**
     - `AuditLog` (`1200 -> 0`): intentionally skipped by Django JSON fallback when `pg_dump` is unavailable on host ([`_dump_postgresql`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/common/services/backup_service.py#L240-L260)).
     - `ProtocolOperation` (`1127 -> 1086`, `-41` rows): caused by `[i:i+500]` slicing over tied `logical_timestamp` values without deterministic primary-key ordering.
2. **Post-Fix Snapshot Parity Verification (`task-49553`, after adding `.order_by(model._meta.pk.name)` at `backup_service.py:273`):**
   - Executed `DatabaseBackupService.perform_backup(upload_s3=False, encrypt=True)` and decrypted/unpacked in memory (`26.12s`, `1.474 MB`, SHA-256 `a7463d0bf39b879c263bdf2c02eef9d3fa8b5d87bbfaf776ebeae1d5024398c5`, `12,226` objects):
     - `ProtocolOperation`: `1,131` in DB == `1,131` in snapshot (`100%` parity)
     - `Voucher`: `1,246` in DB == `1,246` in snapshot (`100%` parity)
     - `LedgerEntry`: `4,508` in DB == `4,508` in snapshot (`100%` parity)
     - `AuditLog`: `1,208` in DB (`0` in JSON snapshot; documented exclusion in fallback serializer when `pg_dump` binary is absent)
   - Verified disposable DR database `neondb_staging_dr_restore` was dropped (`pg_database` contains only `neondb`, `neondb_staging`, `postgres`, `test_neondb_staging`).

---

## 5. Phase D — Sustained Outbox Reliability (`task-49417`)

- **Workload Executed:** `98` synthetic outbox events (`80` healthy + `8` expired-lease `PROCESSING` + `6` transient-fail + `4` dead-letter + `10` concurrent duplicate probes across `6` threads).
- **Measured Outcome:**
  - `8 / 8` expired leases recovered automatically.
  - `94` events `PROCESSED`, `4` terminal `DEAD_LETTER`, `0` remaining test backlog.
  - `0` duplicate email dispatches across concurrent duplicate workers.
  - Max delivery age: `38.63s`; total elapsed runtime: `39.847s`; effective throughput: `2.46 events/sec`.
  - Cleanup verified post-run (`task-49553`): **`temp_phase_d_remaining: 0`**. (Pre-existing staging DB baseline retains `603 PROCESSED`, `227 SKIPPED`, `170 PENDING`, `9 DEAD_LETTER` rows.)

---

## 6. Phase E — Concurrent Financial Report Consistency (`task-49445`)

- **Workload Executed:** Queried Trial Balance & Balance Sheet snapshots concurrently across `Staging Beta Engineering Supplies Ltd` during `4` concurrent receipt creations + `1` immediate reversal (+ `3` cleanup reversals restoring net financial effect to ₹0.00).
- **Measured Outcome:**
  - `18` concurrent snapshots collected
  - `torn_trial_balance_snapshots: 0`
  - `torn_balance_sheet_snapshots: 0`
  - `errors: []`
  - `post_write_tb_variance: "0.00"`, `post_write_bs_balanced: true`

---

## 7. Phase F — Report Performance Profiling, N+1 Remediation & WSGI Load (`task-49445`)

- **ORM Optimization:**
  - Added [`calculate_all_ledger_period_balances`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/period_service.py#L109) using batched `GROUP BY` aggregations and wired [`generate_profit_and_loss`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/financial_statements_service.py#L118) and [`generate_balance_sheet`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/financial_statements_service.py#L273) to eliminate per-ledger loops.
  - Updated [`allocation_service.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/allocation_service.py#L495) to use `select_related('party_ledger', 'party_ledger__group')` fixing Receivables Aging N+1 queries.
- **Query Count & Single-Tenant Latency (`Staging MSME Alpha Belts Pvt Ltd`, `543` vouchers, `16` active ledgers):**
  - Pre-fix per-ledger loop (simulated read-only): `48` SQL queries (`4141.55ms`)
  - Post-fix batched ORM:
    - Profit & Loss: `8` SQL queries (`713.09ms`)
    - Balance Sheet: `12` SQL queries (`1367.08ms`)
    - Trial Balance: `4` SQL queries (`520.37ms`)
    - Receivables Aging (Customer): `2` SQL queries (`4867.01ms` — zero N+1; compute + remote WAN RTT)
    - Payables Aging (Supplier): `2` SQL queries (`164.25ms`)
- **Local WSGI Concurrency Benchmarks (`0` errors, 100% HTTP `200 OK` across all tiers):**

| Concurrency Mode | VUs | Requests | Total Time | Throughput | p50 | p95 | Max |
|---|---|---|---|---|---|---|---|
| 4-Slot Procfile Cap | 5 | 10 | `15.266s` | `0.66 rps` | `2536.68ms` | `10922.21ms` | — |
| 4-Slot Procfile Cap | 10 | 20 | `20.894s` | `0.96 rps` | `2094.27ms` | `12628.46ms` | — |
| 4-Slot Procfile Cap | 20 | 40 | `45.538s` | `0.88 rps` | `2735.24ms` | `11083.38ms` | — |
| Unthrottled Threads | 5 | 10 | `16.8s` | `0.60 rps` | `3017.96ms` | `13187.21ms` | — |
| Unthrottled Threads | 10 | 20 | `15.123s` | `1.32 rps` | `3209.95ms` | `11610.01ms` | — |
| Unthrottled Threads | 20 | 40 | `15.648s` | `2.56 rps` | `2693.30ms` | `13135.17ms` | — |
| Unthrottled Threads | 50 | 100 | `19.561s` | `5.11 rps` | `4020.10ms` | `13127.45ms` | `14646.56ms` |

---

## 8. Phase G — 5-Tenant Pilot Cohort Census & Security Regression (`task-49445`, `task-49553`)

### 8.1 Cohort Accounting Integrity (`neondb_staging`)

| Tenant Company | Total Vouchers | Breakdown | Trial Balance | BS Variance |
|---|---|---|---|---|
| `Garodia Bearing & Power Transmission` (`cd788d07-ae29-4af9-89d2-c5a4f32378cf`) | `63` | `62 POSTED`, `1 DRAFT` | `678241.20` | `0.00` |
| `Precision Agro Tools Pvt Ltd` (`c2771ca4-31bd-47d2-b98c-c1be119f40a1`) | `534` | `523 POSTED`, `11 DRAFT` | `1694738.70` | `0.00` |
| `Shree Radhe Industrial Hardware` (`ce9c6000-c17c-446d-92d3-7ba4b09198c3`) | `60` | `60 POSTED` | `505813.79` | `0.00` |
| `Staging Beta Engineering Supplies Ltd` (`434af258-8d98-4505-9d1b-65eb03c97cc7`) | `46` | `42 POSTED`, `4 REVERSED` | `287835.00` | `0.00` |
| `Staging MSME Alpha Belts Pvt Ltd` (`75a4b5e7-d8af-4cca-905e-31817ba829ca`) | `543` | `444 POSTED`, `92 DRAFT`, `7 REVERSED` | `823068.66` | `0.00` |
| **Cohort Totals** | **`1,246`** | **`1,131 POSTED`**, `104 DRAFT`, `11 REVERSED` | — | **`0.00`** |

- **Double-Entry Invariant Check (`1,131 POSTED` vouchers):** `zero_entry_posted: 0`, `unbalanced_posted: 0`, `orphan_entries: 0`.
- **Security Regression:** Cross-tenant IDOR (Trial Balance, Vouchers, Aging) -> `403`; `VIEWER` receipt creation -> `403`.
- **Carryover Warning (`Staging MSME Alpha Belts Pvt Ltd`):** `2` historical ledgers (`Customer Saksham Staging` diff `8260.00`, `Domestic Sales` diff `7000.00`) carry cached `current_balance` drift vs dynamic GL while Trial Balance stays balanced (`0.00`).

---

## 9. Required Next Actions Before Day 7 / Production Release Gate

1. **Deploy `fix/stage4-12-day6-remediation` (`1c7e3941`) to Staging Render (`https://vouch-u3u7.onrender.com`):** Restore service responsiveness and re-run live public HTTPS probes (`test_live_render_staging.py` plus DEF-01/02/03 write & IDOR checks) against live Render.
2. **Install Native `pg_dump` or Verify Neon PITR in Staging/Prod Backup Docs:** Because host environments lacking `postgresql-client` fall back to JSON serialization (excluding `AuditLog`), either add `pg_dump` to the backend/worker runtime image or configure Neon branch/PITR snapshots alongside S3 encrypted backups.
3. **Staging Maintenance Cleanup:** Recalculate cached ledger balances on `Staging MSME Alpha Belts Pvt Ltd` and drain/archive the `170` historical `PENDING` outbox rows on `neondb_staging`.
4. **Prohibited Until Gate Clears:** Do **not** merge into `main` or promote to `srilekh.com` until Render live staging passes all end-to-end checks and Stage 4.13 / Day 7 soak finishes cleanly.
