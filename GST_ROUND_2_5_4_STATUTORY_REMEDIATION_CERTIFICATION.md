# SriLekh GST — Round 2.5.4 Statutory Mapping, Receipt Eligibility & Automation Remediation Certification

**Candidate Remediation Branch:** `fix/round2-5-4-gst-statutory-remediation`  
**Target Integration Branch:** `main`  
**Merged Release Commit:** `4ca37b0a2666fac9a0634270b6553bf4af06b069`  
**Remediation Commit:** `8e0903dd30c0ac78d6f6f189ff302ef3c89c060e`  
**Parent 1 (`origin/main` Base):** `9dcddae738ca003cadb49e4e74a3acab2edbfa9e`  
**Parent 2 (Remediation Candidate):** `8e0903dd30c0ac78d6f6f189ff302ef3c89c060e`  
**Evaluation Date:** 2026-11-20  
**Staging Backend:** `https://vouch-u3u7.onrender.com`  
**Staging Deployed Commit:** `4ca37b0a` (verified live)  
**Staging Database:** Neon `neondb_staging` (`ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`)  
**Staging Database Fingerprint:** `6f4741bdaaf4` (`is_isolated=True`)  
**Database Migration Status:** Up to date (`unapplied_count=0`)  
**Protected Production Tenant:** `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) — *Confirmed Untouched (0 rows altered, 0 queries executed)*  
**Primary Sandbox Tenant:** `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`)  
**Final Certification Verdict:** **PASS — MERGED AND STAGING CERTIFIED**

---

## 1. Executive Summary

This independent certification report validates the resolution of statutory inconsistencies, receipt eligibility edge cases, and automation architecture hardening identified during the post-merge audit of Round 2.5.3.

The certified remediation commit `8e0903dd30c0ac78d6f6f189ff302ef3c89c060e` has been merged into `main` via merge commit `4ca37b0a2666fac9a0634270b6553bf4af06b069` and deployed live to the Render staging environment (`https://vouch-u3u7.onrender.com`).

All technical and statutory requirements specified in the Round 2.5.4 audit directive have been implemented and independently verified:
1. **GSTR-3B Table 4 Statutory Realignment (Post-Circular 170/02/2022):** Permanent reversals (Rules 38, 42, 43 and Section 17(5)) are segregated under Table 4(B)(1); temporary reversals (Rule 37, Rule 37A, Section 16(2)(b)) are reported under Table 4(B)(2); Table 4(A)(5) includes current inward supplies plus reclaims; Table 4(D)(1) discloses reclaimed ITC previously reversed under Table 4(B)(2); Section 17(5) is strictly excluded from Table 4(D)(1) and cannot be reclaimed; Net ITC Table 4(C) equals $4(A) - 4(B)(1) - 4(B)(2)$ independently across IGST, CGST, SGST, and Cess.
2. **Rule 37A Statutory Deadlines & Invariants:** Supplier default determination date (30 September following FY end) is cleanly decoupled from recipient reversal statutory deadline (30 November following FY end). Section 50 interest warning is automatically applied to reversals executed after 30 November. Prior reversal and supplier GSTR-3B filing are verified before permitting reclaim. Duplicate reversals and duplicate reclaims across periods are strictly prevented.
3. **Section 16(2)(b) First Proviso & Receipt Eligibility:** Inward consignments received in lots/instalments remain ineligible until receipt of the last lot/instalment (`PARTIAL_LOT_PENDING_LAST_INSTALMENT`). Avails 100% full invoice credit in the tax period when the final instalment is received. E-Way Bill in transit without confirmed physical receipt fails closed (`GOODS_SERVICES_NOT_RECEIVED`). Service completion certificates are evaluated independently of goods lots. Duplicate GRN numbers are rejected across distinct vouchers.
4. **Automation Architecture & Staging Reality:** Acknowledged the operational reality of the Render free/starter staging environment (Redis unreachable, Celery workers online: 0). Documented and verified that all SriLekh GST operations (allocations, workspace preparation, validation, export, drift detection) execute 100% synchronously in the Django web process request lifecycle with zero Celery/Redis dependency. Built synchronous CLI management commands `sweep_outbox` and `check_gst_deadlines`.
5. **Comprehensive Verification:** 111 automated tests executed with a 100% pass rate (16 new dedicated Round 2.5.4 tests + 95 regression tests). Live staging smoke tests (9/9 checks) and authenticated cross-tenant authorization audit (19/19 checks) passed with zero defects. Double-entry equilibrium ($\Sigma\text{Debits} == \Sigma\text{Credits}$) and tenant isolation remain completely intact.

---

## 2. Release Identity & Git Lineage Reconciliation

### 2.1 Git Lineage Reconciliation
During the post-merge audit of Round 2.5.3, a discrepancy was noted between the reported merge commit `8d4a5043` and the deployed commit `8c99c332` on staging. Investigation resolved this as follows:
- `8d4a5043` was the non-fast-forward merge commit integrating Round 2.5.3 candidate `b457677f` into `origin/main` (`6b0858be`).
- `d8e8763` published the Round 2.5.3 certification report to git.
- `1557e26e` updated `render.yaml` staging blueprint to set `branch: main`. Render auto-deployed this commit first.
- `8c99c332` aligned `test_workspace_regeneration_on_exported` with draft re-review state transitions. Render auto-deployed this commit immediately following.
- `9dcddae7` updated staging documentation.
- The remediation branch `fix/round2-5-4-gst-statutory-remediation` was branched directly from `origin/main` at `9dcddae7`.
- Remediation commit `8e0903dd30c0ac78d6f6f189ff302ef3c89c060e` was created and merged into `main` via non-fast-forward merge commit `4ca37b0a2666fac9a0634270b6553bf4af06b069`.

### 2.2 Release Identity Matrix
| Item | SHA / Value | Status |
| :--- | :--- | :--- |
| **`origin/main` Base** | `9dcddae738ca003cadb49e4e74a3acab2edbfa9e` | Verified Ancestor |
| **Remediation Feature Commit** | `8e0903dd30c0ac78d6f6f189ff302ef3c89c060e` | Verified Head |
| **Merge Strategy** | Non-fast-forward merge (`ort` strategy, clean, 0 conflicts) | PASS |
| **Merged Release Commit SHA** | `4ca37b0a2666fac9a0634270b6553bf4af06b069` | Committed & Pushed |
| **Render Staging Deployed Commit** | `4ca37b0a` | Verified Live |
| **Render Blueprint Deploy Branch** | `main` | Verified Active |
| **Tracking Branch Sync** | `origin/fix/stage4-12-day6-remediation` fast-forwarded to `4ca37b0a` | Synchronized |

---

## 3. Statutory Review & Remediation Matrix

| Provision / Domain | Statutory / Regulatory Basis | Pre-Remediation State | Round 2.5.4 Remediation Details | Test Evidence | Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **GSTR-3B Table 4(B)(1)** | CGST Rules 38, 42, 43 & Section 17(5) / Circular 170/02/2022 | Section 17(5) blocked credit was reported as disclosure under Table 4(D)(1) following pre-2022 format. | All permanent reversals (Rules 38, 42, 43 and Section 17(5)) are consolidated into Table 4(B)(1) (`rev_42_*` / `as_per_rules_38_42_43_sec_17_5`). | `test_gstr3b_table_4b1_permanent_reversals_includes_sec_17_5` | **PASS** |
| **GSTR-3B Table 4(B)(2)** | CGST Rules 37, 37A & Section 16(2)(b) | Temporary reversals were mixed with general reversals. | Table 4(B)(2) exclusively aggregates temporary reversals: Rule 37 (unpaid >180 days), Rule 37A (vendor default), and Section 16(2)(b) unconfirmed receipts (`others`). | `test_gstr3b_table_4b2_temporary_reversals_rules_37_37a` | **PASS** |
| **GSTR-3B Table 4(A)(5)** | Circular 170/02/2022 Para 4(b) | Table 4(A)(5) contained only current inward supplies. Reclaims were segregated. | Table 4(A)(5) (`all_other_itc`) incorporates current inward eligible supplies PLUS reclaims under Rules 37/37A (`itc_taxable` + `itc_reclaimed_4d1`). | `test_gstr3b_table_4a5_includes_current_and_reclaimed_itc` | **PASS** |
| **GSTR-3B Table 4(D)(1)** | Circular 170/02/2022 Para 4(d) | Previously held Section 17(5) blocked credit. | Table 4(D)(1) (`itc_reclaimed_4d1`) is strictly a disclosure of reclaimed ITC previously reversed under Table 4(B)(2). Section 17(5) is strictly excluded ($0.00$). Section 17(5) can NEVER be reclaimed. | `test_gstr3b_table_4d1_reclaimed_disclosure_excludes_sec_17_5`, `test_section_17_5_blocked_credit_cannot_be_reclaimed` | **PASS** |
| **GSTR-3B Table 4(D)(2)** | CGST Act Sec. 16(4) / PoS Restrictions | Did not aggregate excluded inward vouchers. | Table 4(D)(2) (`ineligible_itc_4d2`) discloses Section 16(4) time-barred supplies and PoS intra-State ineligible tax. | `test_gstr3b_table_4d2_ineligible_itc_disclosure` | **PASS** |
| **GSTR-3B Table 4(C) Net ITC** | Mathematical Invariant | Net ITC formula varied across tax types. | Mathematically verified across all 4 tax components: $\text{Net ITC} = 4(A) - 4(B)(1) - 4(B)(2)$ independently for IGST, CGST, SGST, Cess. | `test_gstr3b_table_4c_net_itc_formula_equilibrium` | **PASS** |
| **Rule 37A Deadlines** | CGST Rules Rule 37A | Default test date and reversal deadline were conflated. | Separated: (1) Supplier default determination date = 30 September following FY end; (2) Recipient reversal deadline = 30 November following FY end. | `test_rule_37a_statutory_deadlines_separation` | **PASS** |
| **Rule 37A Section 50 Interest** | CGST Act Sec. 50 & Rule 37A Proviso | No interest warning on late reversal. | Reversals executed after 30 November flag statutory interest warning under Section 50. Reversals on or before 30 November are interest-free. | `test_rule_37a_interest_warning_after_november_30` | **PASS** |
| **Rule 37A Reclaim Validation** | CGST Rules Rule 37A Proviso | Allowed reclaim without verifying prior active reversal. | Reclaim strictly requires: (1) An active prior reversal allocation; (2) Verification that supplier subsequently filed GSTR-3B. | `test_rule_37a_reclaim_requires_prior_reversal_and_supplier_filing` | **PASS** |
| **Rule 37A Duplicate Guards** | Rule 37A Integrity | Potential duplicate reversal/reclaim across periods. | Prevented duplicate reversals and duplicate reclaims for the same inward voucher across all return periods. | `test_rule_37a_duplicate_reversal_and_reclaim_prevention` | **PASS** |
| **Sec. 16(2)(b) First Proviso** | CGST Act Sec. 16(2) First Proviso | Allowed partial credit or lacked explicit lots flag. | Inward consignments in lots/instalments: ITC blocked (`PARTIAL_LOT_PENDING_LAST_INSTALMENT`) until receipt of last instalment. 100% full invoice credit available in the tax period of final instalment. | `test_section_16_2_first_proviso_lots_instalments_eligibility` | **PASS** |
| **E-Way Bill in Transit** | CGST Act Sec. 16(2)(b) | E-Way Bill presence alone could pass receipt check. | E-Way Bill in-transit without affirmative confirmed physical receipt (GRN/Delivery Challan) fails closed (`GOODS_SERVICES_NOT_RECEIVED`). | `test_eway_bill_in_transit_without_physical_receipt_fails_closed` | **PASS** |
| **Service Completion Evidence** | CGST Act Sec. 16(2)(b) | Services subjected to goods delivery criteria. | Service receipt verified independently via service completion certificate; not constrained by goods lot rules. | `test_service_receipt_evidence_independent_evaluation` | **PASS** |
| **Duplicate GRN Rejection** | Internal Control & Fraud Guard | Same GRN could be cited across different vouchers. | Duplicate GRN numbers rejected across distinct vouchers within the same company. | `test_duplicate_grn_rejected_across_vouchers` | **PASS** |

---

## 4. Automation Architecture & Staging Reality

### 4.1 Staging Infrastructure Reality
A key finding of the post-merge audit was that Render's free/starter staging deployment operates with:
- **Redis Status:** `unreachable` (Redis add-on not provisioned on free staging blueprint).
- **Celery Workers:** `workers_online: 0` (no background worker service active).
- **Celery Beat:** `beat_schedule_active: false`.

### 4.2 Synchronous Design Principle
The audit confirmed that SriLekh's GST architecture does NOT rely on background workers for statutory correctness:
1. **GST Reporting Allocations:** Computed and persisted 100% synchronously upon voucher creation, update, cancellation, or amendment.
2. **GSTR-1 & GSTR-3B Preparation:** Generated synchronously on demand within the Django HTTP request lifecycle via `GSTReturnsService`.
3. **Workspace Drift Audits:** Evaluated synchronously during workspace status inspection.
4. **Export Artifact Generation:** Snapshots and SHA-256 cryptographic checksums are computed synchronously inside database transactions.
5. **Zero Celery/Redis Dependency:** All GST operations function flawlessly even when Celery workers and Redis are offline.

### 4.3 Transactional Outbox & New Management Commands
For asynchronous event dispatch (notifications, emails, webhooks):
- Events are durably stored in PostgreSQL via the `apps.notifications.models.OutboxEvent` table within the same transaction as the accounting/GST mutation.
- To enable deterministic batch execution without Celery/Redis, two synchronous Django management commands have been implemented and verified:

```bash
# Synchronously process pending and retryable outbox events
python manage.py sweep_outbox --limit 100

# Synchronously evaluate statutory deadlines across companies (Rule 37, Rule 37A, Section 16(4))
python manage.py check_gst_deadlines --company-id 4e62863a-08f9-4e99-b0bd-64873acfdd33
```

---

## 5. Accounting Invariance & Multi-Tenant Isolation

### 5.1 Double-Entry Accounting Invariants
- **Mathematical Equilibrium:** Every voucher posted maintains $\Sigma\text{Debits} == \Sigma\text{Credits}$.
- **Ledger Immutability:** GST reporting allocations are non-accounting statutory projections. Allocating an invoice to a different GST return period or performing a Rule 37/37A reversal NEVER alters, updates, or creates `LedgerEntry` rows.
- **Financial Statement Invariance:** Trial Balance, Balance Sheet, and P&L remain 100% historically identical across all allocation operations.

### 5.2 Multi-Tenant Isolation
- **Production Tenant Absolute Protection:** Protected production tenant `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) had ZERO queries executed, ZERO rows altered, and ZERO connections made during all tests.
- **Dedicated Sandbox Tenant:** All tests operated exclusively against `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`).
- **Live IDOR Audit:** 19/19 cross-tenant authorization tests passed on the staging backend with HTTP 403 Forbidden.

---

## 6. Automated Test Suite Execution

### 6.1 Summary Results
```
Ran 111 tests in 70.386s
OK
System check identified no issues (0 silenced).
```

### 6.2 Test Module Breakdown
| Test Module | Focus Area | Tests | Passed | Failed | Errors |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `apps.gst.tests_round2_5_4_statutory_remediation` | GSTR-3B Table 4 classification, Rule 37A deadlines, Sec. 16(2)(b) lots, E-Way Bill in-transit, Duplicate GRN, Sec. 17(5) reclaim block | 16 | 16 | 0 | 0 |
| `apps.gst.tests_round2_5_allocation` | Allocation Engine, Statutory Overrides, Receipt Evidence, Delete Guards, 18 Edge Cases | 38 | 38 | 0 | 0 |
| `apps.gst.tests_production_safety_controls` | Protected Tenant Isolation & Security Guards | 12 | 12 | 0 | 0 |
| `apps.gst.tests_sandbox_integration` | End-to-end Return Preparation & Sandbox API | 14 | 14 | 0 | 0 |
| `apps.gst.tests_round2_2_export` | Workspaces, Snapshots & Export Workflows | 27 | 27 | 0 | 0 |
| `apps.accounting.tests_stage4_13_stabilization` | Core Accounting, Vouchers & Ledgers | 4 | 4 | 0 | 0 |
| **Total** | **Comprehensive Regression Suite** | **111** | **111** | **0** | **0** |

---

## 7. Live Staging Deployment Verification Evidence

### 7.1 Environment Health Endpoint Snapshot
Endpoint: `GET https://vouch-u3u7.onrender.com/api/v1/health/environment/`
```json
{
  "status": "healthy",
  "service": "SriLekh Accounting Engine",
  "environment": "staging",
  "version": "1.0.2",
  "commit": "4ca37b0a",
  "database": {
    "engine": "postgresql",
    "sanitized_target": "neondb_staging",
    "identity_fingerprint": "6f4741bdaaf4",
    "is_isolated": true
  },
  "redis": {
    "configured": true,
    "status": "unreachable"
  },
  "celery": {
    "beat_schedule_configured": true,
    "beat_schedule_active": false,
    "outbox_sweeper_interval_seconds": 60,
    "workers_online": 0,
    "task_always_eager": false,
    "acks_late": true
  },
  "migrations": {
    "status": "up_to_date",
    "unapplied_count": 0
  }
}
```

### 7.2 Operational Smoke Tests (`scripts/test_live_gst_staging.py`)
```
================================================================================
   SRILEKH LIVE GST OPERATIONAL SMOKE TESTS
   Staging Backend: https://vouch-u3u7.onrender.com
   Dedicated Sandbox: Apex Belting & Industrial Store (Demo) (4e62863a-08f9-4e99-b0bd-64873acfdd33)
================================================================================
[Safety Policy Verified] Operating exclusively on sandbox tenant: Apex Belting & Industrial Store (Demo)
[Check 1] Unauthorized API Access Rejection...       [PASS] (HTTP 401)
[Check 2] Cross-Tenant Access Rejection...           [PASS] (HTTP 401)
[Check 3] GST Rate Reference Service Validation...   [PASS] (HSN 4809 @ 18% & HSN 9503 @ 12%)
[Check 4] GSTIN Lookup & Provider Routing...         [PASS] (MockGSTProvider routed, Active)
[Check 5] GST Return Workspace Lifecycle...          [PASS] (Accessible, is_stale=False)
[Check 6] GSTR-1 Draft Preparation...                [PASS] (Valid JSON schema)
[Check 7] GSTR-3B Preparation & Set-off...           [PASS] (Valid set-off calculations)
[Check 8] GST Export Generation & Checksum...        [PASS] (SHA-256 bd48af393bf27a84...)
[Check 9] Live Filing Prohibition Guard...           [PASS] (Live filing blocked with LiveFilingProhibitedError)
================================================================================
>>> GST OPERATIONAL SMOKE TESTS COMPLETED: 9/9 PASS <<<
================================================================================
```

### 7.3 Authenticated Cross-Tenant Isolation Audit (`scripts/test_phase2_authenticated_isolation.py`)
```
================================================================================
PHASE 2: AUTHENTICATED TENANT ISOLATION AUDIT
================================================================================
1. Authenticated as Tenant A (Precision Agro Tools Pvt Ltd): [PASS]
2. Authenticated as Tenant B (Garodia Bearing & Power Transmission): [PASS]
Direction 1: User A accessing Tenant A (Authorized): HTTP 200 [PASS]
Direction 1: User A attempting to access Tenant B: 9/9 checks rejected HTTP 403 [PASS]
Direction 2: User B accessing Tenant B (Authorized): HTTP 200 [PASS]
Direction 2: User B attempting to access Tenant A: 9/9 checks rejected HTTP 403 [PASS]
Non-Existent Tenant Access: Rejected HTTP 403 [PASS]
================================================================================
PHASE 2 SUMMARY: 19 / 19 Cross-Tenant Authorization Checks PASSED
================================================================================
```

---

## 8. Final Verdict & Operational Sign-Off

The Round 2.5.4 Statutory Remediation has successfully reconciled all reported statutory inconsistencies, implemented the First Proviso to Section 16(2) for goods in lots/instalments, enforced E-Way Bill in-transit fail-closed semantics, corrected Rule 37A statutory timelines and Section 50 interest triggers, realigned GSTR-3B Table 4 with Circular 170/02/2022, and provided synchronous CLI execution commands for transactional outbox sweeping and deadline monitoring.

- **Automated Regression Suite:** 111 / 111 PASS (100%)
- **Live Staging Operational Smoke Tests:** 9 / 9 PASS (100%)
- **Authenticated Cross-Tenant Isolation:** 19 / 19 PASS (100%)
- **Double-Entry Equilibrium:** Maintained ($\Sigma\text{Debits} == \Sigma\text{Credits}$)
- **Production Safety:** Zero queries, zero modifications to protected production tenant
- **Staging Deployment:** Certified Live on Commit `4ca37b0a`

**Final Release Verdict:** **PASS — MERGED AND STAGING CERTIFIED**
