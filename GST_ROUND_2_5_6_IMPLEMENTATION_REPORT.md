# SriLekh GST — Round 2.5.6: Technical Implementation & Engineering Report

**Repository:** https://github.com/prakhar2207/Vouch  
**Branch:** `fix/round2-5-6-itc-evidence-and-event-linkage`  
**Base Commit:** `d0e70798dfa823a597b3f412c894f0fb17692dfe`  
**Staging Database:** Neon PostgreSQL `neondb_staging` (`6f4741bdaaf4`)  
**Document Reference:** `GST_ROUND_2_5_6_IMPLEMENTATION_REPORT.md`  

---

## 1. Overview of Codebase Modifications

Round 2.5.6 delivered targeted statutory hardening across models, database migrations, allocation and reconciliation services, deadline detection commands, and audit explanation pipelines.

### Modified Files
- `apps/gst/models.py`
- `apps/gst/services/allocation_service.py`
- `apps/gst/management/commands/check_gst_deadlines.py`

### Newly Created Files
- `apps/gst/migrations/0013_gstreversalreclaimlineage_suppliergstr3bfilingrecord_and_more.py`
- `apps/gst/migrations/0014_remove_gstreportingallocation_unique_active_allocation_per_voucher_event_and_more.py`
- `apps/gst/services/itc_trace_service.py`
- `apps/gst/tests_round2_5_6_itc_evidence_and_lineage.py`

---

## 2. Database Schema Upgrades & Migrations

### 2.1. Migration 0013: Models and Field Upgrades
Applied to `neondb_staging` on 2026-11-20.
- **`SupplierGSTR3BFilingRecord` Created:**
  - `id` (UUID, primary key).
  - `company_id` (ForeignKey to `Company`, on_delete=CASCADE).
  - `supplier_gstin` (CharField(15), indexed).
  - `return_period` (CharField(6), indexed).
  - `status` (`FILED`, `NOT_FILED`, `UNKNOWN`, `DATA_UNAVAILABLE`).
  - `filing_date` (DateField, nullable).
  - `arn` (CharField(30), nullable).
  - `verification_source` (`GST_PORTAL_API`, `GSP_INTEGRATION`, `MANUAL_VERIFIED`, `SIMULATION_TEST`).
  - `unique_together` constraint on `('company', 'supplier_gstin', 'return_period')`.
- **`GSTR2BRecord` Extended:**
  - Added `gstr3b_filing_date`, `gstr3b_filing_arn`, `gstr3b_return_period`, `gstr3b_verification_source`, `gstr3b_verified_at`.
- **`GSTReportingAllocation` Extended:**
  - Added `source_reversal_id` (Self-referential ForeignKey, on_delete=SET_NULL, null=True).
  - Added `payment_allocation_id` (ForeignKey to `accounting.PaymentAllocation`, on_delete=SET_NULL, null=True).
  - Added `payment_event_id` (CharField(64), indexed, null=True).
  - Added `payment_reference` (CharField(128), null=True).
- **`GSTReversalReclaimLineage` Created:**
  - `id` (UUID, primary key).
  - `company_id` (ForeignKey to `Company`).
  - `voucher_id` (ForeignKey to `Voucher`).
  - `reversal_allocation_id` (ForeignKey to `GSTReportingAllocation`).
  - `reclaim_allocation_id` (ForeignKey to `GSTReportingAllocation`).
  - `reclaimed_tax` (Decimal(14, 2)).
  - `igst_reclaimed`, `cgst_reclaimed`, `sgst_reclaimed`, `cess_reclaimed`.
  - `statutory_rule` (`RULE_37`, `RULE_37A`).

### 2.2. Migration 0014: Constraint Modernization
Applied to `neondb_staging` on 2026-11-20.
- **Removed:** Legacy `unique_active_allocation_per_voucher_event` constraint which blocked multiple partial reclaims or partial reversals per voucher.
- **Added:** Upgraded conditional uniqueness:
  ```python
  models.UniqueConstraint(
      condition=models.Q(
          ('is_active', True),
          models.Q(('event_type__in', ['ITC_RECLAIM', 'ITC_REVERSAL_RULE_37']), _negated=True)
      ),
      fields=('company', 'voucher', 'event_type'),
      name='unique_active_allocation_per_voucher_event'
  )
  ```
- **Added:** Stable payment-event constraint:
  ```python
  models.UniqueConstraint(
      condition=models.Q(('is_active', True), ('payment_event_id__isnull', False), models.Q(('payment_event_id', ''), _negated=True)),
      fields=('company', 'voucher', 'payment_event_id'),
      name='unique_active_reclaim_per_payment_event'
  )
  ```

---

## 3. Service Layer Enhancements

### 3.1. `apps/gst/services/allocation_service.py`
- **Leap-Year-Aware Section 50 Interest Calculation:**
  `calculate_section_50_interest()` accurately detects leap years via `calendar.isleap(year)` and calculates exact elapsed days and interest per segment. Sets `is_estimate: True` unless explicitly verified as a factual payment event.
- **Rule 37 Reclaim Allocation with Multi-Reversal FIFO:**
  `create_rule37_reclaim_allocation()` implements `select_for_update()` row locking on both the voucher and qualifying reversal allocations. Sequentially consumes available reversals in FIFO order, builds `GSTReversalReclaimLineage` mapping component amounts, and enforces exact mathematical balance.
- **Rule 37A Zero-Trust Validation:**
  `create_rule37a_reversal_allocation()` rejects `UNKNOWN` and `DATA_UNAVAILABLE` statuses, requiring affirmative evidence of non-filing.
- **Section 16 Statutory Evaluator:**
  `evaluate_section_16_status()` prevents false-positive time-bar flags by distinguishing 10 distinct statutory states, including Finance Act 2024 Section 16(5) & 16(6) relief.

### 3.2. `apps/gst/services/itc_trace_service.py`
Implemented `ITCTraceService` providing complete lifecycle tracing:
$$\text{Invoice} \longrightarrow \text{ITC Claimed} \longrightarrow \text{Reversal} \longrightarrow \text{Qualifying Payment/Filing} \longrightarrow \text{Reclaim} \longrightarrow \text{GSTR-3B Period}$$
- **Business Owner View:** Formats plain-English executive summaries, financial impact cards, color-coded risk levels (`LOW`, `MEDIUM`, `HIGH`), and concrete action items.
- **Professional Auditor View:** Full statutory legal citations, chronological immutable events trail, graph-structured reversal-to-reclaim lineages, tax component breakdowns, and cryptographic verification status.

---

## 4. Operational Command Upgrades

`apps/gst/management/commands/check_gst_deadlines.py`:
- Replaced vulnerable `gstr2b_rec.filing_date` check with dedicated `SupplierGSTR3BFilingRecord` inspection and `gstr3b_filing_date` verification.
- Integrated `evaluate_section_16_status()` to eliminate false-positive time-bar warnings for invoices pending receipt or blocked under Section 17(5).

---

## 5. Deployment & Release Readiness

- **Migrations on Staging Neon DB:** Migrations `0013` and `0014` are fully applied; zero unapplied migrations.
- **Database Identity:** Target `neondb_staging`, fingerprint `6f4741bdaaf4` (`is_isolated=True`).
- **Test Pass Rate:** 83/83 tests passing (100%).
- **Branch:** Cleanly staged on `fix/round2-5-6-itc-evidence-and-event-linkage`.
