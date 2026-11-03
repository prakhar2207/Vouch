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

**Unit & Workflow Test Output (11/11 PASS):**
```text
Using existing test database for alias 'default'...
2026-11-03 12:02:07,290 [INFO] [vouch.access] HTTP PATCH /api/vouchers/3c97ff4f-c9ed-4463-8e6e-b163303c8ead/ 403 in 1057.42ms
..2026-11-03 12:02:21,528 [INFO] [vouch.access] HTTP GET /api/vouchers/8fd125f2-cecd-4bc0-875b-9c83ebca30d4/ 200 in 903.58ms
2026-11-03 12:02:22,404 [INFO] [vouch.access] HTTP GET /api/vouchers/8fd125f2-cecd-4bc0-875b-9c83ebca30d4/ 200 in 874.69ms
2026-11-03 12:02:25,623 [INFO] [vouch.access] HTTP PATCH /api/vouchers/8fd125f2-cecd-4bc0-875b-9c83ebca30d4/ 200 in 3218.42ms
2026-11-03 12:02:26,361 [INFO] [vouch.access] HTTP PATCH /api/vouchers/8fd125f2-cecd-4bc0-875b-9c83ebca30d4/ 409 in 736.73ms
2026-11-03 12:02:27,374 [INFO] [vouch.access] HTTP GET /api/vouchers/8fd125f2-cecd-4bc0-875b-9c83ebca30d4/ 200 in 1011.28ms
2026-11-03 12:02:30,441 [INFO] [vouch.access] HTTP PATCH /api/vouchers/8fd125f2-cecd-4bc0-875b-9c83ebca30d4/ 200 in 3065.56ms
.2026-11-03 12:02:41,504 [INFO] [vouch.access] HTTP PATCH /api/vouchers/cbe7bf17-df0b-4ad6-8dc9-5fb4212a4478/ 200 in 3899.48ms
.2026-11-03 12:02:51,872 [INFO] [vouch.access] HTTP PATCH /api/vouchers/de34d780-5e31-464e-8744-c8c26b75ba6e/ 200 in 3386.27ms
.2026-11-03 12:02:58,811 [INFO] [vouch.access] HTTP PATCH /api/vouchers/1d06bb52-ec5e-4de7-9d94-b2250058bfe2/ 400 in 164.34ms
2026-11-03 12:02:58,977 [INFO] [vouch.access] HTTP PATCH /api/vouchers/1d06bb52-ec5e-4de7-9d94-b2250058bfe2/ 400 in 165.15ms
.2026-11-03 12:03:05,430 [INFO] [vouch.access] HTTP PATCH /api/vouchers/c191bb1c-9a7f-4c71-b75a-eab26415710c/ 428 in 175.33ms
.2026-11-03 12:03:12,989 [INFO] [vouch.access] HTTP PATCH /api/vouchers/9a582a55-0402-4831-b840-5c3566842523/ 409 in 716.53ms
.2026-11-03 12:03:19,751 [INFO] [vouch.access] HTTP PATCH /api/vouchers/920eed54-1a0c-4f52-8eb1-54c99dd37e04/ 428 in 173.62ms
.2026-11-03 12:03:27,366 [INFO] [vouch.access] HTTP PATCH /api/vouchers/0244a1bc-07c5-48ae-bf15-fe7a597b1954/ 428 in 166.42ms
2026-11-03 12:03:28,495 [INFO] [vouch.access] HTTP PATCH /api/vouchers/0244a1bc-07c5-48ae-bf15-fe7a597b1954/ 409 in 681.48ms
.2026-11-03 12:03:38,960 [INFO] [vouch.access] HTTP PATCH /api/vouchers/e893d90a-3dc6-4ff1-a4d6-046f97d82b9e/ 200 in 3566.64ms
.
----------------------------------------------------------------------
Ran 11 tests in 100.504s

OK
Preserving test database for alias 'default'...
Found 11 test(s).
```

**Multi-Threaded Concurrency Test Output (2/2 PASS, Barrier Synchronized with Independent GET Reads):**
```text
Using existing test database for alias 'default'...
2026-11-03 12:04:11,911 [INFO] [vouch.access] HTTP GET /api/vouchers/20f627ec-6a65-4983-aa82-e2775c22cf97/ 200 in 1591.48ms
2026-11-03 12:04:12,600 [INFO] [vouch.access] HTTP GET /api/vouchers/6554d55b-52d1-46ad-a453-088ed1f106bf/ 200 in 2290.92ms
2026-11-03 12:04:15,818 [INFO] [vouch.access] HTTP PATCH /api/vouchers/20f627ec-6a65-4983-aa82-e2775c22cf97/ 200 in 3214.05ms
2026-11-03 12:04:18,820 [INFO] [vouch.access] HTTP PATCH /api/vouchers/6554d55b-52d1-46ad-a453-088ed1f106bf/ 200 in 6218.55ms
.2026-11-03 12:04:49,206 [INFO] [vouch.access] HTTP GET /api/vouchers/f7ad63bc-7c0e-4b54-a7f2-d3eaa899d2fb/ 200 in 2323.09ms
2026-11-03 12:04:50,296 [INFO] [vouch.access] HTTP GET /api/vouchers/f7ad63bc-7c0e-4b54-a7f2-d3eaa899d2fb/ 200 in 3367.42ms
2026-11-03 12:04:53,850 [INFO] [vouch.access] HTTP PATCH /api/vouchers/f7ad63bc-7c0e-4b54-a7f2-d3eaa899d2fb/ 200 in 3549.34ms
2026-11-03 12:04:54,589 [INFO] [vouch.access] HTTP PATCH /api/vouchers/f7ad63bc-7c0e-4b54-a7f2-d3eaa899d2fb/ 409 in 4291.44ms
.
----------------------------------------------------------------------
Ran 2 tests in 66.805s

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
9. `test_real_browser_preflight_and_patch_flow`: Browser OPTIONS preflight returns 200 with `Access-Control-Allow-Headers: if-match, x-voucher-version` and `Access-Control-Expose-Headers: ETag, X-Voucher-Version`; followed by PATCH with `If-Match: "1"` returning 200 OK and `X-Voucher-Version: 2`.
10. `test_precondition_required_and_conflict_zero_side_effects`: 428 and 409 produce zero financial mutations on voucher lines, ledger entries, product stock, and audit logs.
11. `test_two_concurrent_updates_same_version_one_succeeds_one_conflicts`: Both threads independently execute GET to read initial version 1, synchronize on `threading.Barrier(2)`, and fire concurrent PATCH; PostgreSQL `select_for_update()` serializes execution: exactly one succeeds (200), one returns 409, final version is 2.
12. `test_two_concurrent_updates_different_vouchers_both_succeed`: Concurrent updates to different vouchers both return 200.

---
*Captured live on Neon PostgreSQL 18.6 and Next.js 16.3.8.*
