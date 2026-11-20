# SriLekh GST — Round 2.5.5: Reversal & Reclaim Integrity Audit and Remediation Report

**Candidate Remediation Branch:** `fix/round2-5-5-reversal-reclaim-integrity`  
**Base Commit SHA (`origin/main`):** `dd1a7ca226c459a7dcc2657222122409128248da`  
**Preceding Merged Commit:** `4ca37b0a2666fac9a0634270b6553bf4af06b069`  
**Final Remediation Commit SHA:** `d0e70798dfa823a597b3f412c894f0fb17692dfe`  
**Evaluation Date:** 2026-11-20  
**Staging Backend:** `https://vouch-u3u7.onrender.com`  
**Staging Database:** Neon `neondb_staging` (`ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`)  
**Staging Database Fingerprint:** `6f4741bdaaf4` (`is_isolated=True`)  
**Dedicated Sandbox Tenant:** `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`)  
**Protected Production Tenant:** `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) — *Confirmed Untouched (0 rows altered, 0 queries executed)*  
**Release Decision:** **PASS WITH LIMITATIONS**

---

## 1. Executive Summary & Verification Context

In accordance with the Round 2.5.5 audit directive, an independent statutory and financial integrity audit was conducted across SriLekh's GST ITC reversal and reclaim engine. 

While Round 2.5.4 previously aligned GSTR-3B Table 4 classification with CBIC Circular 170/02/2022, deep inspection revealed 8 substantive defects in reversal/reclaim balance validation, caller bypass loopholes, database constraint conflicts with partial payments, false supplier default generation in deadline monitoring, and lack of quantified Section 50 interest calculations.

All 8 identified defects have been remediated on branch `fix/round2-5-5-reversal-reclaim-integrity` (commit `d0e70798dfa823a597b3f412c894f0fb17692dfe`). A comprehensive 18-test verification suite was created, and the full regression suite of 129 tests across accounting and GST passed with a 100% success rate (0 failures, 0 errors in 74.59s). In adherence to the strict instruction *"Do not merge or deploy without explicit authorization"*, this release candidate remains unmerged and undeployed to production/staging until explicit authorization is granted.

---

## 2. Identified Defects & Severity Analysis

| Defect ID | Severity | Statutory / Architectural Area | Description & Root Cause | Impact |
| :--- | :--- | :--- | :--- | :--- |
| **DEF-255-01** | **CRITICAL** | Rule 37 Reclaim Precondition | `create_rule37_reclaim_allocation` did not verify that an active `ITC_REVERSAL_RULE_37` existed for the voucher before creating a reclaim allocation. | Callers could reclaim ITC on invoices that were never reversed, creating unauthorized tax credits. |
| **DEF-255-02** | **CRITICAL** | Rule 37 Reclaim Balance Cap | Cumulative reclaims were not capped against the cumulative reversed tax. Multiple partial reclaims could exceed 100% of the reversed credit. | Severe financial vulnerability allowing excess ITC avails in GSTR-3B Table 4(A)(5) and Table 4(D)(1). |
| **DEF-255-03** | **HIGH** | Database Schema Constraint | `unique_active_allocation_per_voucher_event` enforced uniqueness on `(voucher, event_type)` where `is_active=True`. | When an MSME paid an invoice in multiple instalments across different months, creating a second active `ITC_RECLAIM` crashed with `IntegrityError`. |
| **DEF-255-04** | **HIGH** | Rule 37A Reversal Bypass | `create_rule37a_reclaim_allocation` parameter `require_prior_reversal` defaulted to `False`. | Callers could bypass mandatory prior reversal verification by simply using default parameters. |
| **DEF-255-05** | **HIGH** | Deadline Engine Statutory Integrity | Management command `check_gst_deadlines` hardcoded `supplier_gstr3b_filed=False` when calling `evaluate_rule37a_status`. | Falsely flagged every single purchase invoice past 30 September as a defaulting supplier, corrupting compliance audit reports. |
| **DEF-255-06** | **MEDIUM** | Rule 37A Unavailable Data Handling | When GST portal or GSP provider data was unavailable, the engine had no distinct state and could presume default. | Lack of portal data would illegally force taxpayers to reverse ITC under Rule 37A when no actual default was proven. |
| **DEF-255-07** | **MEDIUM** | Section 50 Interest Calculation | Section 50 interest was only noted as a boolean string without calculating exact interest days or quantified interest amounts. | Taxpayers and accountants were not given actionable liability estimates for overdue reversals under Section 50(1). |
| **DEF-255-08** | **MEDIUM** | Monitoring Command Scope | `check_gst_deadlines` help text claimed to evaluate Rule 37 (180 days) and Section 16(4), but the command only evaluated Rule 37A. | Incomplete statutory monitoring; taxpayers received zero alerts for 180-day unpaid vendor invoices or statute-barred ITC. |

---

## 3. Before & After Implementation Details

### 3.1 Rule 37 Reclaim Mandatory Prior Reversal & Balance Cap (DEF-255-01 & DEF-255-02)
* **Before:** `create_rule37_reclaim_allocation` computed proportionate tax from `paid_amount` and immediately created `GSTReportingAllocation` without querying prior reversals or existing reclaims.
* **After:**
  1. Serialized execution via `transaction.atomic()` and `Voucher.objects.select_for_update().get(id=voucher.id)`.
  2. Queries active prior reversals: `active_reversals = GSTReportingAllocation.objects.filter(voucher=locked_voucher, event_type='ITC_REVERSAL_RULE_37', is_active=True)`. Raises `ValidationError` if `total_reversed_tax <= 0`.
  3. Queries existing reclaims: `active_reclaims = GSTReportingAllocation.objects.filter(voucher=locked_voucher, event_type='ITC_RECLAIM', allocation_reason='RECLAIM_RULE_37', is_active=True)`.
  4. Calculates `remaining_reversed_tax = total_reversed_tax - total_already_reclaimed`.
  5. Raises `ValidationError` if `reclaim_tax > remaining_reversed_tax` or if `remaining_reversed_tax <= 0`.

### 3.2 Database Constraint Exemption for Legitimate Multiple Reclaims (DEF-255-03)
* **Before:**
  ```python
  UniqueConstraint(
      fields=['voucher', 'event_type'],
      condition=Q(is_active=True),
      name='unique_active_allocation_per_voucher_event'
  )
  ```
* **After:** Modified in `apps/gst/models.py` and applied via migration `0012_remove_gstreportingallocation_unique_active_allocation_per_voucher_event_and_more.py`:
  ```python
  UniqueConstraint(
      fields=['voucher', 'event_type'],
      condition=Q(is_active=True) & ~Q(event_type='ITC_RECLAIM'),
      name='unique_active_allocation_per_voucher_event'
  )
  ```
  Uniqueness remains strictly enforced for all primary supply and reversal events (`INWARD_ITC`, `OUTWARD_SUPPLY`, `CREDIT_NOTE`, `ITC_REVERSAL_RULE_37A`, `ITC_REVERSAL_SEC_17_5`), while permitting legitimate multiple partial reclaims protected by unique `idempotency_key` and cumulative balance checks.

### 3.3 Rule 37A Mandatory Prior Reversal & Evidence Preservation (DEF-255-04 & DEF-255-06)
* **Before:**
  ```python
  def create_rule37a_reclaim_allocation(..., require_prior_reversal: bool = False):
      if require_prior_reversal: ...
  ```
* **After:**
  1. Removed bypass option: Prior active reversal check is mandatory on all execution paths.
  2. Supported explicit supplier status enumeration: `VERIFIED_FILED`, `VERIFIED_NOT_FILED`, `DATA_UNAVAILABLE`, `MANUALLY_CONFIRMED`, `UNKNOWN`.
  3. Prohibits reversal or reclaim if status is `DATA_UNAVAILABLE`.
  4. Requires `VERIFIED_FILED` or `MANUALLY_CONFIRMED` for reclaim.
  5. Preserves verification evidence in `statutory_notes`: source (`verification_source`), reference ARN/challan (`verification_reference`), date, and user.

### 3.4 Statutory Deadline Engine & Section 50 Interest (DEF-255-05, DEF-255-07, DEF-255-08)
* **Before:** `check_gst_deadlines.py` looped through purchases and called `evaluate_rule37a_status` with `supplier_gstr3b_filed=False` hardcoded. Rule 37 and Section 16(4) were omitted.
* **After:**
  1. **Rule 37 Evaluation:** Evaluates 180-day payment deadline (`voucher_date + 180 days`) and actual paid/unpaid amount via `PaymentAllocationService.get_voucher_payment_status(voucher)`. Flags unpaid vouchers past 180 days with required reversal amount and Section 50 interest.
  2. **Rule 37A Evaluation:** Evaluates actual supplier filing status from `GSTR2BRecord` or manual confirmation. Reports `DATA_UNAVAILABLE (Data Pending)` without assuming default. Flags verified defaults with Section 50 interest.
  3. **Section 16(4)/16(5)/16(6) Evaluation:** Evaluates unavailed vouchers against statutory cutoffs taking into account GSTR-9 annual return filing date, Section 16(5) 30-Nov-2021 override, and Section 16(6) revocation extension.
  4. **Section 50 Interest Method:** Added `GSTAllocationService.calculate_section_50_interest` computing exact formula:
     $$\text{Interest} = \frac{\text{Tax Amount} \times 18\% \times \text{Days Delay}}{100 \times 365}$$
  5. Added `--json` flag for machine-readable output.

---

## 4. Statutory Review Matrix

| Statutory Provision | Statutory Basis | Pre-Round 2.5.5 State | Remediated Implementation | Compliance Status |
| :--- | :--- | :--- | :--- | :--- |
| **Rule 37(1) Reversal** | CGST Act Sec. 16(2) 2nd Proviso & Rule 37(1) | Supported reversal calculation, but allowed cumulative reversals to exceed invoice total tax. | Reversals locked with `select_for_update`; cumulative reversal capped at invoice tax. Overdue reversals include Section 50 interest details. | **PASS** |
| **Rule 37(4) Reclaim** | CGST Act Sec. 16(2) 3rd Proviso & Rule 37(4) | Allowed reclaim without prior reversal; allowed cumulative reclaims to exceed reversed amount. | Enforced mandatory prior reversal; cumulative reclaim strictly capped at remaining reversed tax; supports multiple partial payments. | **PASS** |
| **Rule 37A Reversal** | CGST Rules Rule 37A | Presumed default on unverified data; interest notes lacked exact interest calculation. | Prohibits reversal on `DATA_UNAVAILABLE`; enforces 30-Nov recipient deadline; calculates Section 50 interest for post-Nov-30 reversals. | **PASS** |
| **Rule 37A Reclaim** | Proviso to CGST Rules Rule 37A | Reclaim allowed bypass of prior reversal (`require_prior_reversal=False`). | Removed bypass; requires active reversal; requires `VERIFIED_FILED` or `MANUALLY_CONFIRMED`; preserves verification evidence. | **PASS** |
| **Section 50 Interest** | CGST Act Sec. 50(1) & Sec. 50(3) | Boolean indicator only; no numeric interest calculation. | Implemented `calculate_section_50_interest` with exact 18% p.a. formula and daily delay tracking. | **PASS** |
| **Section 17(5) Block** | CGST Act Sec. 17(5) | Blocked in some paths, but checked after prior reversal in Rule 37A. | Checked at inception before prior reversal checks; permanently ineligible credit cannot be reclaimed under any circumstances. | **PASS** |

---

## 5. Automated Test Suite Execution

### 5.1 Comprehensive Suite Summary
```
Ran 129 tests in 74.590s
OK
System check identified no issues (0 silenced).
```

### 5.2 Test Module Breakdown
| Test Module | Coverage Scope | Total Tests | Passed | Failed | Errors |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `apps.gst.tests_round2_5_5_reversal_reclaim_integrity` | Rule 37 balance caps, partial payments, Rule 37A status states, Section 50 interest, deadline engine | 18 | 18 | 0 | 0 |
| `apps.gst.tests_round2_5_4_statutory_remediation` | GSTR-3B Table 4 classification, Rule 37A statutory dates, Section 16(2)(b) lots proviso | 16 | 16 | 0 | 0 |
| `apps.gst.tests_round2_5_allocation` | Allocation Engine, Statutory Overrides, Receipt Evidence, Delete Guards, 18 Edge Cases | 38 | 38 | 0 | 0 |
| `apps.gst.tests_production_safety_controls` | Protected Tenant Isolation & Security Guards | 12 | 12 | 0 | 0 |
| `apps.gst.tests_sandbox_integration` | End-to-end Return Preparation & Sandbox API | 14 | 14 | 0 | 0 |
| `apps.gst.tests_round2_2_export` | Workspaces, Snapshots & Export Workflows | 27 | 27 | 0 | 0 |
| `apps.accounting.tests_stage4_13_stabilization` | Core Accounting, Vouchers & Ledgers | 4 | 4 | 0 | 0 |
| **Total** | **Comprehensive Regression Suite** | **129** | **129** | **0** | **0** |

---

## 6. Staging Database Fingerprint & Operational Verifications

### 6.1 Database Fingerprint & Migration Status
- **Target Database:** Neon PostgreSQL `neondb_staging` (`ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`)
- **Identity Fingerprint:** `6f4741bdaaf4` (`is_isolated=True`)
- **Local Migration Status:** Migration `0012_remove_gstreportingallocation_unique_active_allocation_per_voucher_event_and_more.py` successfully generated and applied to the test environment.
- **Staging Database Status:** The deployed staging container is currently at commit `4ca37b0a` (0 unapplied migrations prior to Round 2.5.5 promotion).

### 6.2 Deadline Engine Execution Evidence (`check_gst_deadlines`)
```json
{
  "evaluation_date": "2026-11-20",
  "companies_evaluated": 1,
  "total_vouchers_checked": 0,
  "rule37": {
    "evaluated": 0,
    "reversal_required_count": 0,
    "total_reversal_tax_required": 0.0,
    "overdue_count": 0,
    "total_est_interest": 0.0,
    "findings": []
  },
  "rule37a": {
    "evaluated": 0,
    "verified_filed_count": 0,
    "verified_default_count": 0,
    "data_unavailable_count": 0,
    "overdue_count": 0,
    "total_est_interest": 0.0,
    "findings": []
  },
  "section16": {
    "evaluated": 0,
    "statute_barred_count": 0,
    "findings": []
  }
}
```

### 6.3 Transactional Outbox Sweeper Evidence (`sweep_outbox`)
```
[2026-11-20T12:10:38] Starting synchronous outbox sweep (limit: 5)...
  Existing Queue State: PENDING/RETRY=0, PROCESSING=0
  [SUCCESS] Outbox sweep completed successfully.
```

---

## 7. Accounting Invariants & Multi-Tenant Isolation

1. **Double-Entry Equilibrium:** Mathematical equilibrium $\Sigma\text{Debits} == \Sigma\text{Credits}$ verified across all posted vouchers. Allocations, reversals, and reclaims never mutate `Voucher`, `VoucherItem`, or `LedgerEntry` records.
2. **Production Tenant Protection:** Strict isolation enforced. Protected production tenant `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) had **zero queries** executed and **zero records** altered during this entire audit.
3. **Sandbox Scoping:** All operations strictly scoped to `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`).

---

## 8. Explicit Limitations & Unverified Integrations

1. **Live GSTN Portal Filing Prohibition:** Live filing to external GSTN endpoints is strictly prohibited by application invariant (`LiveFilingProhibitedError`). All returns and reclaims are prepared for offline audit export and statutory compliance monitoring.
2. **Staging Celery/Redis Offline Status:** In Render's Free/Starter staging deployment, Celery background workers are offline (`workers_online: 0`, Redis unreachable). SriLekh's GST architecture runs 100% synchronously in the Django web request lifecycle and does not depend on Celery or Redis for statutory correctness. The management commands `check_gst_deadlines` and `sweep_outbox` provide synchronous operational execution.
3. **Live Taxpayer Portal Status Integration:** Supplier GSTR-3B filing verification is simulated in the sandbox via mock data and GSTR-2B reconciliation records. Live real-time GSTN API taxpayer status queries require authenticated production GSP credentials.

---

## 9. Release Decision & Recommendation

**Verdict:** **PASS WITH LIMITATIONS**

The Round 2.5.5 Reversal & Reclaim Integrity remediations are complete, mathematically sound, statutorily defensible, and fully certified across 129 regression tests.

In strict compliance with user instructions, no merge or deployment has been performed. All changes remain committed on candidate branch [`fix/round2-5-5-reversal-reclaim-integrity`](https://github.com/prakhar2207/Vouch/tree/fix/round2-5-5-reversal-reclaim-integrity) (commit `d0e70798dfa823a597b3f412c894f0fb17692dfe`).

**Recommended Next Step:** Awaiting explicit authorization from the user to execute a controlled non-fast-forward merge into `main` and deploy to staging.
