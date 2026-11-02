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
*Captured live on Neon PostgreSQL 18.6 and Next.js 16.3.8.*
