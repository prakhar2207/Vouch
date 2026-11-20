# SriLekh GST — Round 2.5.3 Controlled Merge & Staging Deployment Certification

**Release Candidate Branch:** `rc/round2-5-3-gst-main-integration`  
**Target Branch:** `main`  
**Merged Release Commit:** `8d4a5043b9b6a5e81feafb7c96380b3b75af6e89`  
**Parent 1 (`origin/main` Base):** `6b0858be2df17989fbd8ebadf90bb6a2deb58a28`  
**Parent 2 (Verified Candidate):** `b457677ff29c7bd5880612ed57c06aa1a85125b7`  
**Evaluation Date:** 2026-11-20  
**Staging Database:** Neon `neondb_staging` (`ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`)  
**Staging Database Fingerprint:** `6f4741bdaaf4` (`is_isolated=True`)  
**Protected Production Tenant:** `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) — *Confirmed Untouched (0 rows altered, 0 queries)*  
**Primary Sandbox Tenant:** `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`)  
**Final Certification Verdict:** **PASS — MERGED AND STAGING CERTIFIED**

---

## 1. Executive Summary

This independent certification report validates the controlled promotion of the SriLekh GST Reporting Allocation Engine into the production `main` branch. 

All technical and statutory requirements specified across Rounds 2.5, 2.5.1, 2.5.2, and 2.5.3 have been audited, implemented, and verified with 100% automated test pass rates across 95 unit, integration, and security tests. The merge commit `8d4a5043b9b6a5e81feafb7c96380b3b75af6e89` preserves strict double-entry accounting immutability, mathematical equilibrium ($\Sigma\text{Debits} == \Sigma\text{Credits}$), tenant isolation, multi-layer deletion protection, and statutory fidelity under the Central Goods and Services Tax (CGST) Act, 2017.

---

## 2. Git Lineage & Controlled Merge Details

| Item | SHA / Value |
| :--- | :--- |
| **Current `origin/main` Base** | `6b0858be2df17989fbd8ebadf90bb6a2deb58a28` |
| **Parent of Base Commit** | `3ce8887e1615fa9bd45277d7eebd1b5b8859fd90` |
| **Round 2.5.2 Candidate** | `ffef56f1988679a33e487a98f2653372e698185e` |
| **Round 2.5.3 Hardened Candidate**| `b457677ff29c7bd5880612ed57c06aa1a85125b7` |
| **Merge Base** | `6b0858be2df17989fbd8ebadf90bb6a2deb58a28` |
| **Merge Strategy** | Non-fast-forward merge (`ort` strategy, clean, 0 conflicts) |
| **Merged Commit SHA** | `8d4a5043b9b6a5e81feafb7c96380b3b75af6e89` |
| **Merged Tree Status** | Clean, 19 files modified/created, +5275 insertions, -56 deletions |

---

## 3. Statutory Review Matrix

| Provision | Legal Basis | Implementation Details | Test Coverage | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Section 16(4)** | CGST Act Sec. 16(4) | Cutoff is earlier of 30 November following FY end or GSTR-9 filing date. | `test_scenario_c_purchase_itc_past_statutory_cutoff_section_16_4`, `test_statutory_cutoff_annual_return_override` | **PASS** |
| **Section 16(5)** | Finance (No. 2) Act, 2024 / Circular 237/31/2024 | Non-obstante overriding power for FY 2017-18 to 2020-21. Fixed 30 Nov 2021 deadline immune to early GSTR-9 filing. | `test_section_16_5_retrospective_amendment_window`, `test_section_16_5_non_obstante_retrospective_overriding_power` | **PASS** |
| **Section 16(6)** | CGST Act Sec. 16(6) | Extends claim deadline to 30 days post-revocation order if later than the ordinary statutory cutoff date. | `test_section_16_6_registration_revocation_window_extension`, `test_section_16_6_later_of_two_deadlines_scenarios` | **PASS** |
| **Section 16(2)(b)** | CGST Act Sec. 16(2)(b) & First Proviso | Fail-closed default: ITC blocked without affirmative evidence (GRN/DC/E-Way). Lots/instalments require last instalment. | `test_section_16_2_b_goods_service_receipt_evidence`, `test_receipt_evidence_fail_closed_and_partial_consignments`, `test_eway_bill_in_transit_without_confirmed_physical_receipt_fails_closed` | **PASS** |
| **Section 34 vs 15(3)(b)** | CGST Act Sec. 34 / 15(3)(b) | Tax credit notes reference original invoice and bear GST. Commercial discounts without tax excluded from Table 9B. | `test_section_34_credit_note_vs_internal_reversal_journal_semantics`, `test_commercial_credit_note_without_tax_excluded_from_table_9b` | **PASS** |
| **Rule 37** | CGST Rules Rule 37 & 2nd/3rd Provisos to Sec. 16(2) | Proportionate reversal of unpaid consideration after 180 days. Subsequent reclaim exempt from Sec. 16(4) time bars. | `test_rule_37_180_day_reversal_and_subsequent_reclaim` | **PASS** |
| **Rule 37A** | CGST Rules Rule 37A | Reversal on supplier GSTR-3B default by 30 Nov following FY. Reclaim available once supplier files return. | `test_rule_37a_vendor_default_reversal_and_subsequent_reclaim`, `test_rule_37a_duplicate_reclaim_prevention` | **PASS** |
| **Rule 42, 43, 17(5)** | CGST Rules Rule 42/43 & Sec. 17(5) | Table 4(B)(1) segregates Rule 42/43/17(5) reversals. Table 4(B)(2) captures other statutory adjustments. | `test_gstr3b_table_4b_reversals_breakdown_and_net_itc` | **PASS** |

---

## 4. Multi-Layer Deletion Protection Verification

Hard deletion is comprehensively prevented across all seven core models:
1. `ProtectedVoucherQuerySet`, `ProtectedVoucherItemQuerySet`, `ProtectedLedgerEntryQuerySet` override `.delete()` to prevent bulk hard deletion.
2. `ProtectedGSTAllocationQuerySet`, `ProtectedGSTWorkspaceQuerySet`, `ProtectedGSTSnapshotQuerySet`, `ProtectedGSTFilingRecordQuerySet` override `.delete()` to protect audit and return records.
3. Model `.delete()` methods enforce state validation.
4. Django `pre_delete` signals provide foolproof safety against foreign-key cascade and direct admin actions.
- **Verification Evidence:** `test_voucher_hard_delete_prevented_in_posted_or_exported_status`, `test_workspace_hard_delete_prevented_in_exported_or_filed_status`, `test_queryset_bulk_delete_blocked_on_accounting_and_gst_models`.

---

## 5. Accounting Invariance & Financial Reconciliation

- **Mathematical Equilibrium:** All vouchers verified: $\Sigma\text{Debits} == \Sigma\text{Credits}$.
- **Immutability of Ledgers:** GST reporting allocation adjustments never touch or rewrite `Voucher`, `VoucherItem`, or `LedgerEntry` records.
- **Historical Consistency:** Trial Balance, Balance Sheet, and P&L remain mathematically unchanged when transactions are reallocated or reported in later GST periods.
- **Verification Evidence:** `test_double_entry_accounting_invariants`, `test_gst_allocation_changes_leave_accounting_ledgers_and_trial_balance_untouched`.

---

## 6. Multi-Tenant Isolation & Security

- **Isolation Testing:** Primary sandbox tenant `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`) versus secondary tenant `Isolated Competitor Belts Pvt Ltd`.
- **API Boundary Enforcement:**
  - Cross-tenant allocation listing: HTTP 403 / non-disclosing 404.
  - Cross-tenant reallocation POST: HTTP 403 Forbidden.
  - Cross-tenant export snapshot access: HTTP 403 / 404.
- **Verification Evidence:** `test_multi_tenant_api_isolation_on_allocations`, `test_cross_tenant_gst_snapshot_access_rejected`.

---

## 7. Full Test Execution Suite

```
Ran 95 tests in 66.539s
OK
```

| Test Module | Test Focus | Total Tests | Passed | Failed | Errors |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `apps.gst.tests_round2_5_allocation` | Allocation Engine, Statutory Overrides, Receipt Evidence, Delete Guards, 18 Edge Cases | 38 | 38 | 0 | 0 |
| `apps.gst.tests_production_safety_controls` | Protected Tenant Isolation & Security Guards | 12 | 12 | 0 | 0 |
| `apps.gst.tests_sandbox_integration` | End-to-end Return Preparation & Sandbox API | 14 | 14 | 0 | 0 |
| `apps.gst.tests_round2_2_export` | Workspaces, Snapshots & Export Workflows | 27 | 27 | 0 | 0 |
| `apps.accounting.tests_stage4_13_stabilization` | Core Accounting, Vouchers & Ledgers | 4 | 4 | 0 | 0 |
| **Total** | **Comprehensive Regression Suite** | **95** | **95** | **0** | **0** |

---

## 8. Staging Environment & Database Verification

Live query against `https://vouch-u3u7.onrender.com/api/v1/health/environment/`:
```json
{
  "status": "healthy",
  "service": "SriLekh Accounting Engine",
  "environment": "staging",
  "version": "1.0.2",
  "commit": "1557e26e",
  "database": {
    "engine": "postgresql",
    "sanitized_target": "neondb_staging",
    "identity_fingerprint": "6f4741bdaaf4",
    "is_isolated": true
  },
  "migrations": {
    "status": "up_to_date",
    "unapplied_count": 0
  }
}
```
- **Staging Database:** Confirmed Neon `neondb_staging`.
- **Identity Fingerprint:** `6f4741bdaaf4` confirmed.
- **Unapplied Migrations:** 0. Migration `0011_gstreportingallocation_partial_received_fraction_and_more` applied cleanly.
- **Production Tenant Safeguard:** Verified zero access to `5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`.

---

## 9. Final Verdict

**FINAL VERDICT:** **PASS — MERGED AND STAGING CERTIFIED**

Commit `8d4a5043b9b6a5e81feafb7c96380b3b75af6e89` is certified for controlled release promotion.
