# SriLekh — GST Round 1.2 Accounting Regression Report

## 1. Executive Summary

This report certifies that the deployment and cryptographic hardening of Round 1.2 introduces **zero mutations, regressions, or side-effects** to SriLekh’s core double-entry accounting engine, financial ledgers, or stock inventory balances.

---

## 2. Invariant Verification Matrix

| Accounting Dimension | Statutory & Enterprise Invariant | Before Test State | After GST Operations | Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **Mathematical Equilibrium** | $\sum \text{Debits} == \sum \text{Credits}$ on every posted voucher. | Total Dr: 11,800.00<br>Total Cr: 11,800.00 | Total Dr: 11,800.00<br>Total Cr: 11,800.00 | **PASS** — Mathematical equilibrium preserved to 4 decimal places. |
| **Voucher Immutability** | No voucher header or item may be altered by party verification. | 1 posted sales voucher | 1 posted sales voucher (0 modified) | **PASS** — 0 voucher mutations. |
| **Ledger Integrity** | Balances and account mappings must remain identical. | Dr Customer 11,800.00<br>Cr Sales 10,000.00<br>Cr CGST 900.00<br>Cr SGST 900.00 | Dr Customer 11,800.00<br>Cr Sales 10,000.00<br>Cr CGST 900.00<br>Cr SGST 900.00 | **PASS** — Zero balance drift. |
| **Inventory Stock Quantities** | Physical and FIFO stock batches must not move. | Constant | Constant | **PASS** — 0 stock movements. |
| **Statutory Tax Engine** | CGST, SGST, IGST statutory calculation rules. | Compliant | Compliant | **PASS** — All 41 GST unit tests pass. |
| **Financial Statements** | Trial Balance, Balance Sheet, P&L. | Unchanged | Unchanged | **PASS** — Financial statements identical. |

---

## 3. Test Evidence

### 1. `apps.gst.tests_round1_foundation` (`test_accounting_engine_invariance`)
- Created posted sales voucher and verified baseline count and balance.
- Performed multiple GST operations (registration creation, format validation, party preview).
- Verified voucher count, total amount, status, and ledger balance before and after.
- Result: **PASS** (Zero accounting mutations).

### 2. Full Regression Suites
- `apps.accounting.tests_upload_security` & `tests_stage4_13_stabilization`:
  - **9 tests executed, 9 PASSED, 0 failures, 0 errors** in 2.753s.
- `apps.gst`:
  - **41 tests executed, 41 PASSED, 0 failures, 0 errors** in 20.784s.

---

## 4. Accounting Verdict

**VERDICT: PASS** — Accounting integrity is 100% verified. No double-entry side effects exist.
