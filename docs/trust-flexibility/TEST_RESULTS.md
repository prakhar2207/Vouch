# SriLekh — Test Results & Verification Evidence
**Evidence-Based Validation for Financial Integrity Remediation**  
*Document Ref:* `docs/trust-flexibility/TEST_RESULTS.md`  
*Branch:* `feature/critical-financial-integrity`  
*Verification Date:* 2026-11-02  

---

## 1. Executive Summary & Quality Gate Status

| Test Suite / Target | Scope & Invariants Tested | Execution Environment | Total Tests | Passed | Failed | Skipped | Duration | Verdict |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **PostgreSQL Concurrency Suite** | `select_for_update()` row locks, multi-threaded audit hash chaining, tenant isolation | **Neon PostgreSQL 18.6** | 4 | 4 | 0 | 0 | 56.68s | **PASSED** |
| **Bank Evidence Preservation Suite** | Immutable raw amounts, Customer refunds (Dr Customer, Cr Bank), Supplier refunds (Dr Bank, Cr Supplier), Unreconcile reversals | **Neon PostgreSQL 18.6** | 6 | 6 | 0 | 0 | 77.82s | **PASSED** |
| **Audit Hash Completeness Suite** | Actor attribution, IP address, UTC timestamp, SHA-256 v2 chaining, DB-level tamper detection, deletion detection | Local SQLite & Test DB | 4 | 4 | 0 | 0 | 0.12s | **PASSED** |
| **Banking Production Suite** | Statement/transaction exclusion, batch ingestion, FIFO allocation | Local Ephemeral Test DB | 11 | 11 | 0 | 0 | 4.74s | **PASSED** |
| **System Hardening Suite** | Double-entry equilibrium, sequential numbering, soft deletion | Local Ephemeral Test DB | 25 | 25 | 0 | 0 | 61.31s | **PASSED** |
| **Accountant Trust Suite** | Automated diagnostics, finding previews, audited fixes | Local Ephemeral Test DB | 5 | 5 | 0 | 0 | 2.34s | **PASSED** |
| **Regression Sprint Suite** | Concurrency, voucher patch contracts, role permissions | Local Ephemeral Test DB | 9 | 9 | 0 | 0 | 7.71s | **PASSED** |
| **Next.js Production Build** | Static & dynamic route compilation (App Router) | Node.js 24 / Webpack | 47 routes | 47 | 0 | 0 | 36.6s | **PASSED** |

---

## 2. Mandatory Test Isolation Policy Verification (`GEMINI.md`)

> **CRITICAL POLICY INVARIANT:**  
> Under no circumstances may any test, mock data generator, or automated script insert, modify, or delete vouchers, ledgers, or bank statements in any real user account.  
> Specifically, **`Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`)** is strictly protected.

- **Automated Test Isolation:** All automated Django test suites executed in disposable database sandboxes (`test_neondb` on PostgreSQL, `:memory:` on SQLite).
- **Dedicated Sandbox Target:** All tests explicitly asserted and used the dedicated demo company:
  - **Company Name:** `Apex Belting & Industrial Store (Demo)`
  - **Company ID:** `4e62863a-08f9-4e99-b0bd-64873acfdd33`
- **Result:** **ZERO** rows created, modified, or deleted in `Maa Annapurna Belting Store`.

---

## 3. Real PostgreSQL Execution Telemetry

### 3.1 PostgreSQL Concurrency & Isolation Suite (`tests_postgresql_concurrency.py`)
- **Command:** `python manage.py test apps.accounting.tests_postgresql_concurrency --keepdb --settings=config.settings_test_pg`
- **Active Database Vendor:** `postgresql` (Confirmed PostgreSQL 18.6 on Neon serverless)
- **Execution Telemetry:**
  ```text
  Using existing test database for alias 'default'...
  ....
  ----------------------------------------------------------------------
  Ran 4 tests in 56.685s

  OK
  Preserving test database for alias 'default'...
  Found 4 test(s).
  [DATABASE CONCURRENCY TEST] Active Database Vendor: postgresql
  ```
- **Test Scenarios Verified:**
  1. `test_database_engine_inspection`: Confirmed vendor is strictly PostgreSQL.
  2. `test_select_for_update_row_locking`: Verified that `select_for_update()` on a ledger row held an exclusive row lock, forcing concurrent threads to wait until transaction commit.
  3. `test_concurrent_audit_log_linear_chaining`: Verified 3 concurrent worker threads writing audit logs serialized cleanly via company row lock without competing chain heads or sort inversions.
  4. `test_tenant_isolation_boundary`: Verified Company A cannot view or mutate Company B's records.

### 3.2 Bank Evidence Preservation Suite (`tests_bank_evidence_preservation.py`)
- **Command:** `python manage.py test apps.accounting.tests_bank_evidence_preservation --keepdb --settings=config.settings_test_pg`
- **Active Database Vendor:** `postgresql` (Neon)
- **Execution Telemetry:**
  ```text
  Using existing test database for alias 'default'...
  ......
  ----------------------------------------------------------------------
  Ran 6 tests in 77.822s

  OK
  Preserving test database for alias 'default'...
  ```
- **Test Scenarios Verified:**
  1. `test_customer_payment_receipt_preserves_evidence`: Deposit from customer creates `RECEIPT` voucher; `raw_credit_amount` and `credit_amount` are never modified.
  2. `test_customer_refund_preserves_evidence_without_flipping`: Withdrawal to customer creates `PAYMENT` voucher (Customer Refund); `debit_amount` is preserved and NOT flipped.
  3. `test_supplier_payment_preserves_evidence`: Withdrawal to supplier creates `PAYMENT` voucher; `debit_amount` is preserved.
  4. `test_supplier_refund_preserves_evidence_without_flipping`: Deposit from supplier creates `RECEIPT` voucher (Supplier Rebate/Recovery); `credit_amount` is preserved and NOT flipped.
  5. `test_unreconcile_transaction_workflow`: Unreconciling an existing match cancels the matched voucher, resets status to `UNRESOLVED`, and keeps original bank evidence pristine.
  6. `test_repeated_reconciliation_idempotency`: Calling resolve multiple times on the same bank transaction returns existing voucher outcome without duplicating ledger entries.

### 3.3 Audit Hash Completeness Suite (`apps/audit/tests.py`)
- **Command:** `python manage.py test apps.audit.tests`
- **Execution Telemetry:**
  ```text
  Ran 4 tests in 0.119s
  OK
  ```
- **Test Scenarios Verified:**
  1. `test_audit_creation_with_actor_ip_and_timestamp`: Cryptographic v2 hash includes actor ID, IP address, and UTC timestamp.
  2. `test_tamper_detection_data_modification`: Direct SQL mutation on an audit row is detected immediately by `verify_company_chain_telemetry`, returning `BROKEN` and the exact record ID.
  3. `test_tamper_detection_record_deletion`: Deletion of an intermediate audit row breaks `previous_hash` continuity and is detected.
  4. `test_audit_verification_endpoint`: API endpoint `/api/v1/audit/verify/<company_id>/` returns accurate real-time verification telemetry.

---

## 4. Frontend Production Compilation Gate
- **Command:** `npm --prefix frontend run build`
- **Compilation Output:**
  ```text
  ✓ Compiled successfully in 36.6s
  ✓ Generating static pages using 23 workers (47/47) in 15.3s
  ```
- **Verification:** All 47 Next.js App Router routes compiled cleanly. Dynamic audit verification banner verified without runtime exceptions.

---
*Maintained by SriLekh Quality Assurance & Core Reliability Engineering.*
