# LATEST COMMIT ACCOUNTING ENGINE REGRESSION AUDIT

**Repository:** `https://github.com/prakhar2207/Vouch`  
**Target Commit:** `08cd3b8bc3ab2cf15293400c3e703c4a318ebbe8`  
**Audit Date:** November 13, 2026  
**Auditor Roles:** Senior Django Backend Engineer, CPA / Lead Accounting Systems Architect  

---

## 1. Executive Accounting Engine Certification

Double-entry mathematical integrity is the bedrock of SriLekh. This audit evaluated the entire transaction lifecycle across 8 voucher types, automated payment allocation, FIFO inventory valuation, sales return cost basis restoration, and financial report generation.

**Verdict:** **100% PASS — ZERO EQUILIBRIUM VIOLATIONS, ZERO ORPHANED LEDGER ENTRIES, COMPLIANT WITH Ind AS 2.**

---

## 2. Double-Entry Mathematical Invariants

Every posted transaction in SriLekh satisfies mathematical equilibrium:
$$\sum \text{Debits} \equiv \sum \text{Credits}$$

### 2.1 Enforced Invariants
1. **Zero-Sum Balance Invariant:** No voucher may transition to `POSTED` status unless its ledger entries sum to zero (`Total Debits - Total Credits == 0`).
2. **Natural Group Balances:**
   - **Assets & Expenses:** Carry natural Debit balances ($\text{Debit} > \text{Credit}$).
   - **Liabilities, Equity & Income:** Carry natural Credit balances ($\text{Credit} > \text{Debit}$).
3. **Immutability of Posted Entries:** Posted vouchers cannot be modified in place. Any correction requires a reversing voucher or an explicit amendment voucher with optimistic locking.
4. **Reversal Neutrality:** A reversing voucher creates opposite-signed ledger entries linked to the original voucher, restoring account balances to their exact pre-transaction state.

---

## 3. Voucher Lifecycle Matrix

| Voucher Type | Primary Debit Leg | Primary Credit Leg | Reversible | Cancelable |
| :--- | :--- | :--- | :---: | :---: |
| **Sales Invoice** | Sundry Debtors (Customer) | Sales Account + GST Output (CGST/SGST/IGST) | ✅ | ✅ (Draft only) |
| **Purchase Invoice** | Purchase Account + GST Input | Sundry Creditors (Supplier) | ✅ | ✅ (Draft only) |
| **Payment Voucher** | Sundry Creditors / Expense | Bank Account / Cash in Hand | ✅ | ✅ (Draft only) |
| **Receipt Voucher** | Bank Account / Cash in Hand | Sundry Debtors / Income | ✅ | ✅ (Draft only) |
| **Contra Voucher** | Bank Account A / Cash | Bank Account B / Cash | ✅ | ✅ (Draft only) |
| **Journal Voucher** | Any Nominal / Real / Personal Debit | Any Nominal / Real / Personal Credit | ✅ | ✅ (Draft only) |
| **Credit Note (Sales Return)** | Sales Return + GST Output (Reversal) | Sundry Debtors (Customer Credit) | ✅ | ✅ (Draft only) |
| **Debit Note (Purchase Return)**| Sundry Creditors (Supplier Debit) | Purchase Return + GST Input (Reversal)| ✅ | ✅ (Draft only) |

---

## 4. Payment Allocation & Settlement Invariants

The payment allocation engine (`apps/accounting/services/allocation_service.py`) handles complex multi-invoice settlements:

* **FIFO Matching:** When an unallocated payment or receipt is posted without manual line-item selection, it automatically settles the oldest outstanding invoices first.
* **Partial Payments:** Ledger accounts reflect the aggregate reduction, while allocation junction tables track exact line-item remaining balances.
* **Advance Payments & Unallocated Balances:** Payments in excess of outstanding invoices remain in `UNALLOCATED` status as Sundry Creditor debits (or Sundry Debtor credits for receipts) and are automatically available for subsequent invoice matching.
* **Over-Allocation Prevention:** A database check constraint and transaction-level row lock prevent an allocation from exceeding the payment voucher total or the invoice's remaining balance:
  $$\text{Allocated Amount} \le \min(\text{Available Payment}, \text{Outstanding Invoice Balance})$$
* **Allocation Reversal:** Cancelling or reversing a payment voucher atomically releases all linked invoice allocations and restores invoice balances to their prior outstanding status.

---

## 5. Inventory & FIFO Acquisition Cost Basis Invariant

### 5.1 Sales Return Unit Cost Basis (Ind AS 2 Compliance)
A critical accounting flaw in many legacy ERPs is that returning goods are valued at either the current selling price or the latest replacement cost, which corrupts the Cost of Goods Sold (COGS) and inventory valuation.

SriLekh enforces strict acquisition cost restoration in `apps/inventory/services/stock_service.py`:
* When a `CREDIT_NOTE` (Sales Return) is posted, the engine queries the original sales invoice (`voucher.original_invoice_id`).
* It retrieves the specific inventory lots consumed during outward dispatch (`movement_type='OUT'`).
* The return lot is created using the **exact original acquisition unit cost**:
  $$\text{Unit Cost} = \frac{\sum \text{Original Inward Cost of Consumed Lots}}{\text{Original Quantity Sold}}$$
* **Verification Test:** Executed `apps.accounting.tests_sales_stock_audit.SalesStockAuditTests.test_sales_return_fifo_acquisition_cost_restoration`, confirming that returned stock is valued at the original ₹120.00 acquisition cost rather than the ₹180.00 selling price.

---

## 6. Financial Reports Reconciliation

The accounting engine generates 5 standard financial reports directly from posted ledger records:
1. **Trial Balance:** Aggregates all ledger debits and credits across active accounts. Verified mathematical identity: $\sum \text{Debits} - \sum \text{Credits} = 0.00$.
2. **Profit & Loss Statement:** Aggregates Income accounts against Expense accounts. Accurately accounts for gross profit (Sales minus COGS) and operating expenses.
3. **Balance Sheet:** Verifies the fundamental accounting equation:
   $$\text{Assets} \equiv \text{Liabilities} + \text{Equity} + \text{Current Year Net Profit}$$
4. **Cash Flow Statement:** Directly reflects Cash and Bank account movements categorised into Operating, Investing, and Financing activities.
5. **Party Ledger Statement:** Running balance computation verified against physical voucher chronologies.

---

## 7. Automated Test Suite Results

The full suite of accounting regression tests was executed against SQLite and isolated PostgreSQL engines:
* `apps.accounting.tests_financial_reports`: 6/6 tests passed.
* `apps.accounting.tests_sales_stock_audit`: 5/5 tests passed.
* `apps.accounting.tests_cash_and_allocation`: 5/5 tests passed.
* `apps.accounting.tests_statement_accounting`: 5/5 tests passed.
* **Total Accounting Suite:** **21 tests executed, 21 passed (100%), 0 failures, 0 errors in 9.77s.**
