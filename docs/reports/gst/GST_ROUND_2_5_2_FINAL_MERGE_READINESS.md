# SriLekh GST — Round 2.5.2 Final Merge Readiness Certification

**Release Candidate Branch:** `feat/round2-5-2-merge-readiness`  
**Base Commit (origin/main):** `6b0858be2df17989fbd8ebadf90bb6a2deb58a28`  
**Target Branch:** `main`  
**Evaluation Date:** 2026-11-20  
**Verification Environment:** Neon Staging (`neondb_staging`, fingerprint `6f4741bdaaf4`)  
**Certification Status:** **PASS (READY FOR CONTROLLED MERGE)**

---

## Executive Summary

Round 2.5.2 finalizes the audit certification and merge readiness of the SriLekh GST Reporting Allocation Engine. All remaining architectural concerns raised across Round 2.5 and Round 2.5.1 have been resolved:

1. **Git Lineage Clarified:** Verified that commit `3ce8887` is the direct parent of `6b0858b` on `main`. Feature branch ancestry is unbroken and fully aligned with `origin/main`.
2. **Fail-Closed Receipt Evidence:** Inward supplies default to unconfirmed receipt (`is_receipt_confirmed=False`), blocking ITC until affirmative documentation (GRN, Delivery Challan, E-Way Bill) is confirmed. Partial consignments claim proportionate credit.
3. **Multi-Layer Deletion Protection:** Implemented custom QuerySets overriding `.delete()`, model-level `.delete()` overrides, and Django `pre_delete` signals across all accounting and GST transactional models. Bulk and cascade hard deletions are permanently prevented.
4. **Statutory Time Bars & Overrides:**
   - Section 16(5) non-obstante power guarantees that FY 2017-18 to 2020-21 ITC claims remain eligible up to 30 November 2021 regardless of early GSTR-9 filings.
   - Section 16(6) extends the claim window by 30 days from the revocation order date for cancelled registrations subsequently restored under Section 30.
5. **Credit Note Disambiguation:** Section 34 tax credit notes are distinguished from Section 15(3)(b) commercial credit notes. Commercial credit notes without tax adjustment are excluded from GSTR-1 Table 9B.
6. **Rule 37 & Rule 37A Lifecycle:** Automated calculations for 180-day non-payment reversals and supplier GSTR-3B defaults, alongside reclaim mechanisms exempt from Section 16(4) time bars.

---

## 1. Git Lineage & Branch Reconciliation

- **Reference Inspection:**
  - `origin/main` HEAD: `6b0858be2df17989fbd8ebadf90bb6a2deb58a28`
  - Immediate Parent on `main`: `3ce8887e1615fa9bd45277d7eebd1b5b8859fd90` (Post-Merge Main Deployment Verification)
  - Round 2.5 Feature Base: `6b0858b`
  - Merge-Base between feature and target: exact match (`6b0858b`)
- **Conclusion:** There are no divergent branches or lost commits. The branch `feat/round2-5-2-merge-readiness` builds directly upon `origin/main`.

---

## 2. Technical Implementation Summary

### A. Fail-Closed Receipt Architecture (`apps/gst/models.py`, `allocation_service.py`)
- Inward purchase vouchers require affirmative documentary confirmation to be eligible for ITC.
- Without affirmative evidence, allocations are marked `status='EXCLUDED'` and `allocation_reason='GOODS_SERVICES_NOT_RECEIVED'`.
- Supported receipt documents: `GRN`, `DELIVERY_CHALLAN`, `EWAY_BILL`, `SERVICE_COMPLETION`, `INVOICE_PHYSICAL_COPY`.
- Proportionate delivery (`partial_received_fraction`) scales taxable and tax amounts proportionally under `PARTIAL_RECEIPT_PROPORTIONATE`.

### B. Multi-Layer Deletion Prevention (`apps/accounting/models.py`, `apps/gst/models.py`)
- Three distinct layers prevent hard deletion:
  1. `QuerySet.delete()` overrides on `ProtectedVoucherQuerySet`, `ProtectedVoucherItemQuerySet`, `ProtectedLedgerEntryQuerySet`, `ProtectedGSTAllocationQuerySet`, `ProtectedGSTWorkspaceQuerySet`, `ProtectedGSTSnapshotQuerySet`, `ProtectedGSTFilingRecordQuerySet`.
  2. Model-level `delete()` overrides checking lifecycle status.
  3. Django `pre_delete` signal receivers that intercept all deletion attempts, including administrative bulk deletions and foreign key cascades.

### C. Statutory Overrides & Rule 37/37A Mechanics (`apps/gst/services/allocation_service.py`)
- `get_statutory_cutoff_date`:
  - Retrospective Section 16(5) rule overrides Section 16(4) early GSTR-9 cutoff dates for FY 2017-18 through 2020-21.
  - Section 16(6) revocation order extension adds 30 days beyond the revocation date.
- `calculate_rule37_reversal`, `create_rule37_reversal_allocation`, `create_rule37_reclaim_allocation`:
  - Enforces proportionate reversal of unpaid invoices after 180 days in GSTR-3B Table 4(B)(2).
  - Permits reclaiming reversed ITC in Table 4(A)(5) and Table 4(D)(1) upon subsequent payment without time-limit restrictions.
- `create_rule37a_reversal_allocation`, `create_rule37a_reclaim_allocation`:
  - Reverses ITC when suppliers default on GSTR-3B filing and permits reclaim once the supplier files.

---

## 3. Automated Test Verification Results

| Test Module | Coverage Area | Tests Run | Result | Duration |
| :--- | :--- | :---: | :---: | :---: |
| `apps.gst.tests_round2_5_allocation` | Allocation, Statutory Overrides, Receipt Evidence, Delete Guards | 30 | **PASS (OK)** | 22.5s |
| `apps.gst.tests_production_safety_controls` | Protected Tenant Isolation & Security Guards | 12 | **PASS (OK)** | 3.0s |
| `apps.gst.tests_sandbox_integration` | End-to-end Return Preparation & Sandbox API | 14 | **PASS (OK)** | 7.1s |
| `apps.gst.tests_round2_2_export` | Return Workspaces & Export Snapshots | 27 | **PASS (OK)** | 27.3s |
| `apps.accounting.tests_stage4_13_stabilization` | Core Accounting, Vouchers & Ledgers | 4 | **PASS (OK)** | 1.2s |
| **Total** | **Comprehensive Regression Suite** | **87** | **PASS (100%)** | **61.1s** |

---

## 4. Final Merge Readiness Verdict

**Verdict:** **PASS — CERTIFIED FOR MERGE**

The feature branch `feat/round2-5-2-merge-readiness` satisfies all statutory compliance, accounting invariance, security isolation, and data protection criteria.
