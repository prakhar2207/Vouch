# PROJECT INVARIANTS & SYSTEM POLICIES

## 1. MANDATORY TEST ISOLATION POLICY (CRITICAL - HIGHEST PRIORITY)

> **STRICT USER DIRECTIVE - NEVER OVERRIDE OR BYPASS UNTIL EXPLICITLY DIRECTED BY USER**

1. **PROHIBITION ON USER ACCOUNTS**:
   - Under **NO circumstances** may any test, mock data generator, load test, concurrency test, or automated verification script insert, modify, or delete vouchers, ledgers, bank transactions, or inventory in **ANY real user account or client tenant**.
   - Specifically, **`Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`)** and all real client accounts are strictly protected production tenants.

2. **DEDICATED TEST SANDBOX**:
   - ALL automated tests, API test scripts, load benchmarks, and scratch test runs MUST STRICTLY use the dedicated sandbox company:
     - **Company Name**: `Apex Belting & Industrial Store (Demo)` (Apex Belting Store)
     - **Company ID**: `4e62863a-08f9-4e99-b0bd-64873acfdd33`
   - Before executing any script that generates vouchers, ledger entries, bank statement imports, or journal adjustments, the script MUST verify:
     ```python
     assert str(company.id) == '4e62863a-08f9-4e99-b0bd-64873acfdd33', "ABORT: Tests may ONLY run against Apex Belting Store sandbox!"
     ```

3. **PRODUCTION ACCOUNT INTEGRITY**:
   - Real tenant books (`Maa Annapurna Belting Store`, etc.) contain real-world accounting records (invoices, GST filings, bank feeds, audit logs).
   - Only user-initiated actions via the authenticated frontend or explicitly approved administrative maintenance (e.g. balance rebuilds without data corruption) are permitted.

---

## 2. DOUBLE-ENTRY ACCOUNTING INVARIANTS
- Every posted voucher MUST satisfy mathematical equilibrium: `Total Debits == Total Credits`.
- Ledger balances must maintain their natural group directions (Asset/Expense = Debit, Liability/Equity/Income = Credit).
- No unlinked or orphaned ledger entries.
- Audit trails must remain tamper-evident with cryptographic SHA-256 hash chaining.
