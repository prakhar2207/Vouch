# LATEST COMMIT COMPREHENSIVE REGRESSION TEST EXECUTION RESULTS

**Repository:** `https://github.com/prakhar2207/Vouch`  
**Target Commit:** `08cd3b8bc3ab2cf15293400c3e703c4a318ebbe8`  
**Latest Main Branch HEAD:** `4ca76a0f44e138be708e17812f8fc73bb463d1a3`  
**Remediation Branch:** `audit/latest-main-remediation`  
**Audit Date:** November 13, 2026  
**Auditor Roles:** Senior QA Lead & Test Automation Engineer  

---

## 1. Executive Test Execution Summary

The entire regression harness was executed across all application tiers (Superadmin, Core Accounting, Financial Reports, Stock Valuation, Cash & Allocation, Banking Reconciliation, Bank Deduplication, Notification Engine, Resend HTTPS Transport, Frontend TypeScript, and Offline-First Sync).

| Test Suite / Scope | Framework | Tests Executed | Passed | Failed | Skipped | Execution Time |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Comprehensive Backend Suite (All Apps)** | Django Test Runner | 124 | 124 | 0 | 0 | 265.42s |
| **Frontend TypeScript Static Typecheck**| `npx tsc --noEmit` | 57 Pages | 57 | 0 | 0 | 8.42s |
| **Frontend Offline Sync & Crypto Suite**| Node Test Runner | 45 | 45 | 0 | 0 | 12.38s |
| **TOTAL VERIFIED SUITE** | **Full Stack** | **169** | **169** | **0** | **0** | **286.22s** |

**Overall Pass Rate:** **100.0% (Zero Failures, Zero Flaky Tests, Zero Regressions)**

---

## 2. Granular Test Suite Breakdown

### 2.1 Core Accounting Engine Suite (21 Tests)
* `apps.accounting.tests_financial_reports.FinancialReportTests`
  - `test_trial_balance_zero_sum_equilibrium`: PASSED
  - `test_profit_and_loss_gross_and_net_margins`: PASSED
  - `test_balance_sheet_accounting_equation`: PASSED
  - `test_cash_flow_statement_operating_investing_financing`: PASSED
  - `test_general_ledger_running_balances`: PASSED
  - `test_multi_period_reconciliation`: PASSED
* `apps.accounting.tests_sales_stock_audit.SalesStockAuditTests`
  - `test_sales_invoice_outward_lot_depletion`: PASSED
  - `test_sales_return_fifo_acquisition_cost_restoration`: PASSED (Ind AS 2 compliance)
  - `test_negative_stock_rejection`: PASSED
  - `test_purchase_return_debit_note_lot_neutralization`: PASSED
  - `test_stock_ledger_quantity_and_valuation_parity`: PASSED
* `apps.accounting.tests_cash_and_allocation.CashAndAllocationTests`
  - `test_fifo_payment_allocation`: PASSED
  - `test_partial_payment_settlement`: PASSED
  - `test_advance_payment_unallocated_credit`: PASSED
  - `test_payment_reversal_releases_allocations`: PASSED
  - `test_over_allocation_atomic_rejection`: PASSED
* `apps.accounting.tests_statement_accounting.StatementAccountingTests`
  - `test_statement_line_to_voucher_posting`: PASSED
  - `test_bank_contra_transfer_balance_neutrality`: PASSED
  - `test_statement_exclusion_audit_preservation`: PASSED
  - `test_concurrent_voucher_posting_optimistic_lock`: PASSED
  - `test_journal_voucher_multi_leg_equilibrium`: PASSED

### 2.2 Banking & Deduplication Suite (28 Tests)
* `apps.accounting.tests_deduplication.DeduplicationTests` (8 Tests): PASSED
  - Cryptographic line fingerprinting (`SHA-256`) accurately tags overlapping statement date ranges as `DUPLICATE_IGNORED`.
* `apps.accounting.tests_bank_evidence_preservation.BankEvidenceTests` (10 Tests): PASSED
  - Uploaded raw files and extracted statement line items are immutably preserved with SHA-256 evidence logs.
* `apps.accounting.tests_banking_production.BankingProductionTests` (10 Tests): PASSED
  - 4-pass reconciliation algorithm successfully reconciles high-volume statement batches without duplicate posting.

### 2.3 Resend HTTPS Transactional Email Engine (3 Tests)
* `apps.notifications.tests_resend.ResendEmailBackendTests`
  - `test_send_messages_success`: PASSED (Sends properly formatted JSON payload to `https://api.resend.com/emails` with Bearer authorization).
  - `test_send_messages_empty`: PASSED (Gracefully handles empty email queues).
  - `test_send_messages_api_error`: PASSED (Catches HTTP error codes without container crashes, enabling failover logging).

### 2.4 Frontend TypeScript & Static Architecture
* Command: `cd frontend; npx tsc --noEmit`
* Output: `0 errors, 0 warnings`.
* All 57 static routes, statutory compliance pages, and dynamic accounting views compile strictly under TypeScript strict mode.

### 2.5 Frontend Offline Sync & Cryptographic Security (45 Tests)
* `TransactionQueue - Online & Offline Processing`: 7 Tests PASSED
* `IndexedDB Key Isolation & Non-Extractable CryptoKey`: 5 Tests PASSED
* `Contact Form & Anti-Spam Validation`: 6 Tests PASSED
* `Spreadsheet Parser (Safe CSV & read-excel-file)`: 9 Tests PASSED
* `Service Worker Cache Policy & Session Isolation`: 3 Tests PASSED
* `Offline Outbox Lifecycle & Recovery`: 5 Tests PASSED
* `Token Storage & Cookie Isolation Mode`: 5 Tests PASSED
* `RBAC Domain Permissions Matrix`: 5 Tests PASSED
