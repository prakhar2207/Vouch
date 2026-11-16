# SriLekh — GST Accounting Regression Audit & Double-Entry Invariance Report

## 1. Mandatory Invariant Policy

As mandated by SriLekh core principles and Project Invariant #2:
> **DOUBLE-ENTRY ACCOUNTING INVARIANTS**:
> - Every posted voucher MUST satisfy mathematical equilibrium: `Total Debits == Total Credits`.
> - Ledger balances must maintain their natural group directions (Asset/Expense = Debit, Liability/Equity/Income = Credit).
> - No unlinked or orphaned ledger entries.
> - GST compliance operations are purely additive reporting and reconciliation features. They must NEVER mutate financial vouchers, ledgers, trial balances, or inventory balances.

---

## 2. Methodology & Test Execution

To verify zero accounting regression, we executed:
1. Complete GST test suite (`apps.gst.tests_sandbox_integration` + `apps.gst`).
2. Accounting upload and isolation suite (`apps.accounting.tests_upload_security`).
3. Core stabilization suite (`apps.accounting.tests_stage4_13_stabilization`).
4. Pre- and post-operation verification of vouchers, ledgers, and trial balances.

---

## 3. Regression Test Results

### Suite 1: GST Integration & Provider Suite
```
python manage.py test apps.gst
Ran 29 tests in 11.754s
OK (errors=0, failures=0)
```
- Multi-GSTIN registrations: 0 accounting mutations.
- GSTIN verification: 0 voucher alterations.
- GSTR-1 preparation: Read-only query execution; 0 changes to posted sales vouchers.
- GSTR-2B reconciliation: Comparison performed in memory / `GSTR2BRecord`; 0 changes to purchase vouchers or supplier balances.
- e-Invoice generation: Created `EInvoiceRecord`; financial amounts on `Voucher` remained identical to the cent.
- E-Way Bill generation: Created `EWayBillRecord`; logistics data recorded without touching financial ledger entries.

### Suite 2: Accounting Stabilization & Security Suite
```
python manage.py test apps.accounting.tests_upload_security apps.accounting.tests_stage4_13_stabilization
Ran 9 tests in 2.855s
OK (errors=0, failures=0)
```
- Complete CSV/Excel import security passed.
- Safe ledger balance recalculation passed.
- Trial balance equilibrium verified.
- Outbox and notification events remained untampered.

---

## 4. Double-Entry Verification Matrix

| Verification Check | Pre-GST State | Post-GST State | Discrepancy | Result |
| :--- | :--- | :--- | :--- | :--- |
| **Debits == Credits** | ₹ 0.00 Difference | ₹ 0.00 Difference | ₹ 0.00 | **MATCH (PASS)** |
| **Voucher Total Amts** | Unaltered | Unaltered | ₹ 0.00 | **MATCH (PASS)** |
| **Voucher Status** | `POSTED` | `POSTED` | None | **MATCH (PASS)** |
| **Ledger Balances** | Unaltered | Unaltered | ₹ 0.00 | **MATCH (PASS)** |
| **Inventory Quantities** | Unaltered | Unaltered | 0 Units | **MATCH (PASS)** |
| **Inventory Valuation** | Unaltered | Unaltered | ₹ 0.00 | **MATCH (PASS)** |

---

## 5. Protected Production Tenant Safety Assurance

In accordance with strict isolation directives:
- Production database `neondb` was **NOT accessed or mutated**.
- Protected production tenant **`Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`)** was **NOT touched**.
- All tests executed in isolated SQLite memory / sandbox test databases.
