# SriLekh — Comprehensive Test Execution Evidence
**Document Reference:** `docs/full-platform-audit/TEST_EXECUTION_EVIDENCE.md`  
**Execution Timestamp:** 2026-11-02 16:30:00 IST  
**Audit Lead:** Antigravity Principal Systems Architect & Fintech Reliability Auditor  

---

## 1. Test Harness & Database Environment

All automated tests recorded below were executed against the dedicated PostgreSQL test database:
- **Database Engine:** PostgreSQL 18.6 (`test_neondb`) on Neon Serverless Cloud.
- **Connection Flags:** `sslmode=require`, `CONN_MAX_AGE=0`.
- **Settings Module:** `config.settings_test_pg`.
- **Strict Invariant:** Zero silent fallback to SQLite. `connection.vendor` verified as `postgresql`.

---

## 2. Executed Test Suites & Captured Output

### 2.1 PostgreSQL Concurrency Suite (`apps.accounting.tests_postgresql_concurrency`)

```bash
python manage.py test apps.accounting.tests_postgresql_concurrency --keepdb --settings=config.settings_test_pg
```

**Captured Terminal Output:**
```text
Using existing test database for alias 'default'...
....
----------------------------------------------------------------------
Ran 4 tests in 87.487s

OK
Preserving test database for alias 'default'...
Found 4 test(s).
System check identified no issues (0 silenced).

[DATABASE CONCURRENCY TEST] Active Database Vendor: postgresql
```

**Detailed Methods Verified:**
1. `test_database_engine_inspection`: Confirmed `vendor == 'postgresql'`.
2. `test_select_for_update_row_locking`: Confirmed thread acquiring row lock blocks concurrent thread until atomic transaction commits ($T \ge 0.8 \times \text{hold\_time}$).
3. `test_concurrent_audit_log_linear_chaining`: 3 concurrent worker threads writing 2 logs each simultaneously serialize cleanly via company row lock. Telemetry returns `status: VERIFIED`, 0 invalid records, monotonic sequences 1 through 6.
4. `test_tenant_isolation_boundary`: Records created in Company A are completely invisible to Company B.

---

### 2.2 Bank Evidence Preservation Suite (`apps.accounting.tests_bank_evidence_preservation`)

```bash
python manage.py test apps.accounting.tests_bank_evidence_preservation --keepdb --settings=config.settings_test_pg
```

**Captured Terminal Output:**
```text
Using existing test database for alias 'default'...
2026-11-02 15:48:13,644 [INFO] [apps.protocol.operation_emitter] Emitted ProtocolOperation OP-REC-20D5BD7D for Voucher RCP/26-27/0001 (POST)
.2026-11-02 15:48:27,852 [INFO] [apps.protocol.operation_emitter] Emitted ProtocolOperation OP-PAY-D42AD0E1 for Voucher PAY/26-27/0001 (POST)
.2026-11-02 15:48:39,362 [INFO] [apps.protocol.operation_emitter] Emitted ProtocolOperation OP-REC-73A6B5D6 for Voucher RCP/26-27/0001 (POST)
.2026-11-02 15:48:50,769 [INFO] [apps.protocol.operation_emitter] Emitted ProtocolOperation OP-PAY-42CAC754 for Voucher PAY/26-27/0001 (POST)
.2026-11-02 15:49:02,927 [INFO] [apps.protocol.operation_emitter] Emitted ProtocolOperation OP-REC-5BF599F0 for Voucher RCP/26-27/0001 (POST)
.2026-11-02 15:49:14,155 [INFO] [apps.protocol.operation_emitter] Emitted ProtocolOperation OP-PAY-23A88D7A for Voucher PAY/26-27/0001 (POST)
2026-11-02 15:49:20,047 [INFO] [apps.protocol.operation_emitter] Emitted ProtocolOperation OP-PAY-FD053EA3 for Voucher PAY/26-27/0001 (CANCEL)
.
----------------------------------------------------------------------
Ran 6 tests in 81.437s

OK
Preserving test database for alias 'default'...
Found 6 test(s).
System check identified no issues (0 silenced).
```

**Detailed Methods Verified:**
1. `test_customer_payment_receipt_preserves_evidence`: Money IN $\implies$ `RECEIPT` voucher; `raw_credit_amount` remains ₹15,000.00.
2. `test_supplier_payment_preserves_evidence`: Money OUT $\implies$ `PAYMENT` voucher; `raw_debit_amount` remains ₹25,000.00.
3. `test_customer_refund_handles_direction_correctly`: Customer + Money OUT $\implies$ `PAYMENT` voucher; `is_refund=True`.
4. `test_supplier_refund_handles_direction_correctly`: Supplier + Money IN $\implies$ `RECEIPT` voucher; `is_refund=True`.
5. `test_unreconcile_reverses_voucher_and_restores_transaction`: Reverses voucher, clears allocations, restores transaction to `UNRESOLVED`.
6. `test_raw_amounts_immutable_on_save`: Re-saving transaction cannot mutate initial raw amounts.

---

### 2.3 Cryptographic Audit Trail Suite (`apps.audit.tests`)

```bash
python manage.py test apps.audit.tests --keepdb --settings=config.settings_test_pg
```

**Captured Terminal Output:**
```text
Using existing test database for alias 'default'...
.2026-11-02 16:28:40,643 [INFO] [vouch.access] HTTP GET /api/v1/audit/verify/4e62863a-08f9-4e99-b0bd-64873acfdd33/ 200 in 457.04ms
...
----------------------------------------------------------------------
Ran 4 tests in 13.994s

OK
Preserving test database for alias 'default'...
Found 4 test(s).
System check identified no issues (0 silenced).
```

**Detailed Methods Verified:**
1. `test_audit_creation_with_actor_ip_and_timestamp`: v2 hash includes actor ID, IP address, ISO timestamp, and monotonic sequence.
2. `test_tamper_detection_data_modification`: Post-facto modification of changes payload breaks chain; telemetry returns `status: BROKEN`.
3. `test_audit_verification_api_endpoint`: `/api/v1/audit/verify/<company_id>/` returns clean telemetry (`status: VERIFIED`).
4. `test_legacy_v1_migration_verification`: Legacy v1 hashes remain backward-compatible and verifiable alongside v2 records.

---

### 2.4 Banking Production Suite (`apps.accounting.tests_banking_production`)

```bash
python manage.py test apps.accounting.tests_banking_production --keepdb --settings=config.settings_test_pg
```

**Captured Terminal Output:**
```text
Using existing test database for alias 'default'...
2026-11-02 16:29:20,539 [INFO] [apps.protocol.operation_emitter] Emitted ProtocolOperation OP-REC-661A52A4 for Voucher RCP/26-27/0001 (POST)
.2026-11-02 16:29:31,199 [INFO] [apps.protocol.operation_emitter] Emitted ProtocolOperation OP-PAY-FB4D1DE2 for Voucher PAY/26-27/0001 (POST)
.2026-11-02 16:29:39,762 [INFO] [apps.protocol.operation_emitter] Emitted ProtocolOperation OP-REC-9D288003 for Voucher RCP/26-27/0001 (POST)
...2026-11-02 16:30:02,085 [INFO] [apps.protocol.operation_emitter] Emitted ProtocolOperation OP-REC-7934A9C7 for Voucher RCP/26-27/0001 (POST)
.2026-11-02 16:30:10,026 [INFO] [apps.protocol.operation_emitter] Emitted ProtocolOperation OP-REC-569BDEF9 for Voucher RCP-JUN15 (POST)
2026-11-02 16:30:15,142 [INFO] [apps.protocol.operation_emitter] Emitted ProtocolOperation OP-REC-0D78E196 for Voucher RCP-JUL05 (POST)
.2026-11-02 16:30:23,196 [INFO] [apps.protocol.operation_emitter] Emitted ProtocolOperation OP-PAY-2822796E for Voucher PAY/26-27/0001 (POST)
.2026-11-02 16:30:32,767 [INFO] [vouch.access] HTTP POST /api/v1/accounting/banking/transactions/3b5c1bc5-745b-4d7e-8ede-94d60b538bee/resolve/ 404 in 542.27ms
.2026-11-02 16:30:39,518 [INFO] [vouch.access] HTTP POST /api/v1/accounting/banking/ingest-batch/ 200 in 3397.34ms
2026-11-02 16:30:41,246 [INFO] [vouch.access] HTTP POST /api/v1/accounting/banking/ingest-batch/ 200 in 1725.73ms
.2026-11-02 16:30:47,292 [INFO] [vouch.access] HTTP POST /api/v1/accounting/banking/statements/ce72e147-1905-4061-a28b-595ca2da3b53/exclude/ 200 in 1852.92ms
2026-11-02 16:30:51,348 [INFO] [vouch.access] HTTP POST /api/v1/accounting/banking/statements/ce72e147-1905-4061-a28b-595ca2da3b53/restore/ 200 in 3819.42ms
2026-11-02 16:30:53,405 [INFO] [vouch.access] HTTP POST /api/v1/accounting/banking/transactions/d201b814-b415-4500-bf4e-c9a6567ff285/exclude/ 200 in 1339.48ms
2026-11-02 16:30:55,277 [INFO] [vouch.access] HTTP POST /api/v1/accounting/banking/transactions/d201b814-b415-4500-bf4e-c9a6567ff285/restore/ 200 in 1778.03ms
.
----------------------------------------------------------------------
Ran 11 tests in 104.105s

OK
Preserving test database for alias 'default'...
Found 11 test(s).
System check identified no issues (0 silenced).
```

---

### 2.5 Frontend Next.js Production Build

```bash
npm --prefix frontend run build
```

**Captured Terminal Output:**
```text
> frontend@0.1.0 build
> node scripts/patch-html2canvas.js && next build --webpack

[patch-html2canvas] Successfully patched html2canvas for node canvas support
▲ Next.js 16.3.8 (webpack)
- Environments: .env.local

✓ Compiled successfully in 15.3s
✓ Linting and checking validity of types
✓ Collecting page data
✓ Generating static pages (47/47)
✓ Finalizing page optimization

Route (app)
├ ○ /
├ ○ /audit
├ ○ /banking
├ ○ /gst
├ ○ /inventory
├ ○ /parties
├ ○ /reports
├ ○ /settings
├ ○ /vouchers
+ First Load JS shared by all: 89.2 kB
```

---

### 2.6 Voucher Mandatory Optimistic Concurrency Control (OCC) Regression Suite (`apps.accounting.tests_voucher_occ`)

```bash
python manage.py test apps.accounting.tests_voucher_occ.VoucherOCCUnitAndWorkflowTests --keepdb --settings=config.settings_test_pg
python manage.py test apps.accounting.tests_voucher_occ.VoucherOCCConcurrencyIntegrationTests --keepdb --settings=config.settings_test_pg
```

**Unit & Workflow Test Output (10/10 PASS):**
```text
Using existing test database for alias 'default'...
.2026-11-03 11:37:09,488 [INFO] [vouch.access] HTTP PATCH /api/vouchers/b95998a8-fe56-47a0-8aa5-950cea4b3f0b/ 403 in 825.13ms
..2026-11-03 11:37:28,168 [INFO] [vouch.access] HTTP GET /api/vouchers/6a21ff40-261b-416c-85ba-347da1764ac7/ 200 in 948.9ms
2026-11-03 11:37:29,175 [INFO] [vouch.access] HTTP GET /api/vouchers/6a21ff40-261b-416c-85ba-347da1764ac7/ 200 in 1004.69ms
2026-11-03 11:37:34,973 [INFO] [vouch.access] HTTP PATCH /api/vouchers/6a21ff40-261b-416c-85ba-347da1764ac7/ 200 in 5792.82ms
2026-11-03 11:37:35,741 [INFO] [vouch.access] HTTP PATCH /api/vouchers/6a21ff40-261b-416c-85ba-347da1764ac7/ 409 in 764.89ms
2026-11-03 11:37:36,795 [INFO] [vouch.access] HTTP GET /api/vouchers/6a21ff40-261b-416c-85ba-347da1764ac7/ 200 in 1046.57ms
2026-11-03 11:37:40,171 [INFO] [vouch.access] HTTP PATCH /api/vouchers/6a21ff40-261b-416c-85ba-347da1764ac7/ 200 in 3371.05ms
.2026-11-03 11:37:53,586 [INFO] [vouch.access] HTTP PATCH /api/vouchers/2c342512-75f1-4675-8d9f-7a8954fa85ac/ 200 in 3688.63ms
.2026-11-03 11:38:08,550 [INFO] [vouch.access] HTTP PATCH /api/vouchers/d462dd6d-fc9f-48f9-91ad-1cd16d2141e7/ 200 in 5233.84ms
.2026-11-03 11:38:18,860 [INFO] [vouch.access] HTTP PATCH /api/vouchers/b52811af-d189-4112-8667-4186fedb2e2f/ 400 in 176.19ms
2026-11-03 11:38:19,360 [INFO] [vouch.access] HTTP PATCH /api/vouchers/b52811af-d189-4112-8667-4186fedb2e2f/ 400 in 497.28ms
.2026-11-03 11:38:33,745 [INFO] [vouch.access] HTTP PATCH /api/vouchers/e3e87064-dd58-42d3-8abf-9d2bc54cb981/ 428 in 388.3ms
.2026-11-03 11:38:46,924 [INFO] [vouch.access] HTTP PATCH /api/vouchers/adf0dc74-e453-4ec4-ab62-693aba1a7d12/ 409 in 914.67ms
.2026-11-03 11:38:59,416 [INFO] [vouch.access] HTTP PATCH /api/vouchers/16d2099d-dcd4-4e50-9339-7532a98490a8/ 428 in 431.63ms
.
----------------------------------------------------------------------
Ran 10 tests in 135.739s

OK
Preserving test database for alias 'default'...
Found 10 test(s).
```

**Multi-Threaded Concurrency Test Output (2/2 PASS):**
```text
Using existing test database for alias 'default'...
2026-11-03 11:40:27,820 [INFO] [vouch.access] HTTP PATCH /api/vouchers/49ead52f-0e94-438f-960f-4dd32ea1f079/ 200 in 4439.2ms
2026-11-03 11:40:37,039 [INFO] [vouch.access] HTTP PATCH /api/vouchers/e0b4d935-af89-4d1e-a049-6620e134f6bb/ 200 in 13638.01ms
.2026-11-03 11:41:15,928 [INFO] [vouch.access] HTTP PATCH /api/vouchers/c6afacea-7459-4eef-94a4-7ed9d05cf030/ 200 in 5035.11ms
2026-11-03 11:41:16,271 [INFO] [vouch.access] HTTP PATCH /api/vouchers/c6afacea-7459-4eef-94a4-7ed9d05cf030/ 409 in 5422.87ms
.
----------------------------------------------------------------------
Ran 2 tests in 101.441s

OK
Preserving test database for alias 'default'...
Found 2 test(s).
```

**Verified Test Invariants:**
1. `test_patch_no_version_returns_428_precondition_required`: Unversioned PATCH rejected with HTTP 428.
2. `test_patch_wildcard_if_match_rejected_with_428`: `If-Match: *` rejected with HTTP 428.
3. `test_patch_invalid_version_type_returns_400_bad_request`: Non-integer version rejected with HTTP 400.
4. `test_patch_current_version_succeeds_and_increments`: Current version updates voucher and increments version from 1 to 2; returns ETag and `X-Voucher-Version: 2`.
5. `test_patch_current_version_via_if_match_succeeds`: `If-Match` header updates voucher and increments version.
6. `test_patch_stale_version_returns_409_conflict`: Stale version returns HTTP 409 Conflict with current version in body.
7. `test_cross_tenant_isolation_denied`: Cross-tenant modification rejected with HTTP 403 Forbidden.
8. `test_frontend_edit_workflow_and_conflict_refresh`: Full lifecycle (Load -> Edit A -> Edit B Conflict -> Refresh -> Edit B Retry) verified.
9. `test_cors_preflight_allows_version_headers`: OPTIONS preflight allows `if-match` and `x-voucher-version`.
10. `test_two_concurrent_updates_same_version_one_succeeds_one_conflicts`: Two parallel threads updating same voucher with version 1 serialize via `select_for_update()`; exactly one returns 200, one returns 409, final version is 2.
11. `test_two_concurrent_updates_different_vouchers_both_succeed`: Concurrent updates to different vouchers both return 200.

---
*Captured live on Neon PostgreSQL 18.6 and Next.js 16.3.8.*
