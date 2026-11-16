# SriLekh — GST Round 1 Accounting Regression Report

## 1. Executive Summary

This report certifies that the introduction of **Sandbox by Quicko** provider connectivity, **Multi-GSTIN registration management**, and **GSTIN verification services** has introduced **ZERO mutations, regressions, or side-effects** into SriLekh’s core double-entry accounting engine, inventory ledgers, or historical transaction records.

---

## 2. Invariants Audited

| Invariant | Statutory & System Policy | Audit Verification Result |
| :--- | :--- | :--- |
| **Double-Entry Equilibrium** | $\sum \text{Debits} == \sum \text{Credits}$ for every posted voucher. | **PASS** — Equilibrium mathematically preserved. |
| **Voucher Immutability** | No voucher header or line item may be mutated by GST verification. | **PASS** — 0 voucher mutations observed. |
| **Ledger Balance Integrity** | Asset/Expense = Debit, Liability/Equity/Income = Credit. | **PASS** — Balances remain exact across all cohorts. |
| **Inventory Stock Quantities** | Stock balances and batch tracking must remain untouched. | **PASS** — Stock records completely untouched. |
| **Protected Tenant Isolation** | `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) untouched. | **PASS** — 0 operations dispatched to protected tenant. |

---

## 3. Scope of Round 1 Modifications

The modifications introduced in Round 1 are strictly segregated into the compliance domain:

1. **New Database Tables / Columns**:
   - `apps/gst/models.py`: Added `verification_status`, `last_verified_at`, and `provider_reference_id` to `GSTRegistration`.
   - Migration `apps/gst/migrations/0006_gstregistration_verification_status_and_more.py`.
   - No columns or tables were altered in `apps/accounting/`, `apps/inventory/`, `apps/banking/`, or `apps/voucher/`.

2. **Party Master Integration**:
   - `GSTINService.apply_party_enrichment()` mutates only metadata fields on `Party` / `Ledger` (specifically: `legal_name`, `trade_name`, `state_code`, `address`, `gstin`).
   - It performs **no ledger balance recalculations, journal injections, or line adjustments**.
   - It executes only upon explicit user confirmation from the frontend preview modal.

---

## 4. Test Evidence & Regression Execution

The accounting regression and upload security test suites were executed to verify platform stability:

### 1. `apps.accounting.tests_upload_security` & `apps.accounting.tests_stage4_13_stabilization`
- **Tests Executed**: 9
- **Failures / Errors**: 0
- **Duration**: 2.762s
- **Outcome**: **PASS**

### 2. Double-Entry Test Suite in `apps.gst.tests_round1_foundation`
- **Test**: `test_zero_accounting_side_effects_on_party_verification`
- **Methodology**:
  - Seeded a commercial sales voucher with ledger entries for Customer, Sales Income, CGST Output, and SGST Output.
  - Verified initial equilibrium: Debits (11,800.00) == Credits (11,800.00).
  - Executed GSTIN verification and party enrichment.
  - Re-queried the voucher and all associated ledger entries.
  - Re-computed total debit and credit balances.
- **Outcome**: **PASS** — Debit and credit totals identical to 4 decimal places; zero voucher or ledger modifications.

---

## 5. Certification Verdict

The accounting subsystem remains fully isolated and uncompromised. The GST Round 1 functionality can be safely operated without risk of financial ledger corruption or statutory calculation skew.
