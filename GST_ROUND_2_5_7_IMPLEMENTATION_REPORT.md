# SriLekh GST Engine — Round 2.5.7: Implementation & Release Certification Report

**Product:** SriLekh — GST-Enabled Double-Entry Accounting SaaS for Indian MSMEs  
**Repository:** https://github.com/prakhar2207/Vouch  
**Release Round:** Round 2.5.7 (Payment Event Integrity & Supplier Evidence Certification)  
**Base Feature Commit:** `b3058ba7b4667c8ced89bcb9720a33997ea7e79e`  
**Parent Branch:** `fix/round2-5-6-itc-evidence-and-event-linkage`  
**New Release Branch:** `fix/round2-5-7-payment-evidence-certification`  
**Staging Backend:** `https://vouch-u3u7.onrender.com`  
**Staging Database:** Neon PostgreSQL `neondb_staging` (`ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`)  
**Staging Database Fingerprint:** `6f4741bdaaf4` (`is_isolated=True`, confirmed)  
**Dedicated Sandbox Tenant:** `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`)  
**Protected Production Tenant:** `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c` — strictly untouched)

---

## 1. Release Objective & Executive Summary

SriLekh Round 2.5.7 remediates the remaining architectural and statutory concerns identified during independent source code review of Round 2.5.6. While Round 2.5.6 established the core event linkage model, critical edge cases remained regarding payment idempotency validation, payload modification detection, supplier evidence specificity, and Section 16 classification.

Round 2.5.7 hardens the SriLekh engine across five major technical pillars:
1. **P0 Payment-Event Idempotency & Conflict Prevention:** Requires stable source event tracking (`payment_event_id`), computes canonical SHA-256 event fingerprints, rejects conflicting retries (amount, date, voucher), scopes database unique constraints to the company tenant, and provides a statutory superseding workflow (`supersede_payment_reclaim_allocation`).
2. **P0 Supplier GSTR-3B Evidence Lifecycle:** Strictly distinguishes between `VERIFIED_NOT_FILED`, `PENDING`, `UNKNOWN`, and `DATA_UNAVAILABLE`. Resolves the critical `.order_by('-return_period').first()` bug by enforcing exact invoice return period lookups (`return_period=inv_period`). Enforces a 30-day evidence freshness window (`is_stale(threshold_days=30)`). Rejects GSTR-1 outward date substitution for GSTR-3B tax payment.
3. **P1 Section 50 Statutory Interest Validation:** Implements leap-year mathematical precision (366 days in 2024 vs 365 days in 2025) across calendar boundaries. Validates the Rule 37A safe harbor (zero interest if reversed on or before 30-Nov).
4. **P1 Section 16 Decision-Table Matrix:** Evaluates inward purchase transactions into explicit statutory categories (`NOT_YET_ELIGIBLE`, `PERMANENTLY_BLOCKED`, `TIME_BARRED`, `SPECIAL_STATUTORY_EXCEPTION`, `ELIGIBLE`, `REVERSED_CONDITIONAL`, `ELIGIBLE_CLAIMED`).
5. **P1 PostgreSQL Concurrency & Tenant Isolation:** Verified under genuine multi-threaded execution against Neon PostgreSQL `neondb_staging` (`6f4741bdaaf4`). 100% of cumulative tests pass (101/101).

---

## 2. Technical Modifications & Architectural Manifest

```
Directory: apps/gst/
├── models.py                     [MODIFIED] Added payment_fingerprint, company unique constraint, is_stale()
├── migrations/
│   └── 0015_...py                [ADDED] Migration for payment_fingerprint & tenant unique constraint
├── services/
│   ├── allocation_service.py     [MODIFIED] Canonical fingerprinting, conflict rejection, superseding workflow, Section 16 matrix
│   └── itc_trace_service.py      [MODIFIED] Exact period match, stale evidence handling, uncertainty explanation
├── management/commands/
│   └── check_gst_deadlines.py    [MODIFIED] Exact period match, PENDING separation, stale evidence handling
└── tests_round2_5_7_...py        [ADDED] Dedicated 18-test comprehensive test suite
```

### 2.1 Schema & Model Upgrades (`apps/gst/models.py`)
1. **`GSTReportingAllocation.payment_fingerprint`:**
   - Added `CharField(max_length=64, blank=True, default='', db_index=True)`.
   - Stores the 64-character SHA-256 hexadecimal canonical hash of the payment event payload.
   - Added composite index `models.Index(fields=['company', 'payment_fingerprint'])`.
2. **Tenant-Scoped Unique Constraint:**
   - Replaced `unique_active_reclaim_per_payment_event` on `(company, voucher, payment_event_id)` with `unique_active_reclaim_per_company_payment_event` on `(company, payment_event_id)` where `is_active=True` and `payment_event_id > ''`.
   - Prevents identical event IDs from being credited against different vouchers in the same company.
3. **`SupplierGSTR3BFilingRecord` Upgrades:**
   - Added `STATUS_CHOICES` updates (`PENDING`, `UNKNOWN`, `DATA_UNAVAILABLE`, `MANUALLY_CONFIRMED`).
   - Implemented `is_stale(threshold_days: int = 30) -> bool`: returns `True` if non-filed evidence is older than 30 days.

### 2.2 Database Migration 0015
- Generated migration `apps/gst/migrations/0015_remove_gstreportingallocation_unique_active_reclaim_per_payment_event_and_more.py`.
- Applied and verified against Neon PostgreSQL `neondb_staging` (`[X] 0015_...`). Zero unapplied migrations.

### 2.3 Service Implementation (`apps/gst/services/allocation_service.py`)
1. **`compute_payment_event_fingerprint()`:**
   - Computes deterministic SHA-256 hash across `(company_id, voucher_id, payment_event_id, paid_amount, currency, payment_date, payment_allocation_id, payment_reference)`.
2. **`create_rule37_reclaim_allocation()`:**
   - Requires `payment_event_id` in production by default (`allow_legacy_unidentified=False`).
   - Tenant-scoped existing allocation lookup.
   - If allocation exists:
     - Cross-voucher reuse -> raises `ValidationError("Payment-Event Idempotency Conflict: ... already registered against voucher ...")`.
     - Fingerprint mismatch -> raises `ValidationError("Payment-Event Idempotency Conflict: ... payload produces different fingerprint ...")`.
     - Identical retry -> returns existing allocation (idempotent success).
   - Filters reversal lineages by `reclaim_allocation__is_active=True`, ensuring superseded reclaims do not consume the available reversal balance.
3. **`supersede_payment_reclaim_allocation()`:**
   - Implements atomic correction pathway under Section 155.
   - Marks allocation `is_active=False`, `status='SUPERSEDED'`, sets `superseded_at`.
   - Appends audit reason to `statutory_notes`.
   - Preserves historical `GSTReversalReclaimLineage` rows for audit while freeing the reversal balance for subsequent corrected payments.
4. **`evaluate_rule37a_status()` & `create_rule37a_reversal_allocation()`:**
   - Rejects `DATA_UNAVAILABLE`, `PENDING`, `UNKNOWN` from triggering supplier default.
   - Enforces exact invoice return period match (`return_period=inv_period`).
   - Enforces evidence freshness (`is_stale_evidence=False`).
   - Rejects reversals before the statutory default date (30-Sep following FY end).
5. **`create_rule37a_reclaim_allocation()`:**
   - Strictly enforces `VERIFIED_FILED` carries valid GSTR-3B ARN and filing date.
   - Blocks GSTR-1 outward date substitution for GSTR-3B tax payment.
   - Blocks duplicate active reclaims across periods.
   - Enforces `MANUALLY_CONFIRMED` carries documentary reference.
6. **`evaluate_section_16_status()`:**
   - Adds explicit `category` field mapping all 10 statutory conditions.

---

## 3. Dedicated Test Suite Results (`apps/gst/tests_round2_5_7_payment_and_evidence.py`)

18 dedicated tests ran against Neon PostgreSQL `neondb_staging` (`ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`):

```
Using existing test database for alias 'default'...
..................
----------------------------------------------------------------------
Ran 18 tests in 140.623s

OK
Preserving test database for alias 'default'...
Found 18 test(s).
System check identified no issues (0 silenced).
```

### Granular Summary:
- **Part 1 (Idempotency & Conflicts):** 6 tests (Identical retry, amount mismatch, cross-voucher reuse, sequential payments, missing event ID rejection, supersede workflow). All passed.
- **Part 2 (Supplier Evidence):** 7 tests (Inconclusive evidence, period mismatch, stale evidence, 30-Sep default date, ARN/date requirement, GSTR-1 outward rejection, manual confirmation). All passed.
- **Part 3 (Section 50 Interest):** 2 tests (Leap year 2024 vs standard year 2025 precision, Rule 37A safe harbor before 30-Nov). All passed.
- **Part 4 (Section 16 Decision Matrix):** 1 comprehensive decision-table test covering all conditions. Passed.
- **Part 5 (Concurrency & Isolation):** 2 tests (Multi-threaded concurrent duplicate delivery, protected production tenant isolation). All passed.

---

## 4. Cumulative Regression Test Status

All 5 GST test suites were executed and verified:
1. `apps.gst.tests_round2_5_7_payment_and_evidence`: 18 tests — **PASS**
2. `apps.gst.tests_round2_5_6_itc_evidence_and_lineage`: 11 tests — **PASS**
3. `apps.gst.tests_round2_5_5_reversal_reclaim_integrity`: 18 tests — **PASS**
4. `apps.gst.tests_round2_5_4_statutory_remediation`: 16 tests — **PASS**
5. `apps.gst.tests_round2_5_allocation`: 38 tests — **PASS**

**Total Test Count: 101 tests — 100% Passed.** Zero regressions across all historical release milestones.

---

## 5. Security & Isolation Verification

- **Neon Staging Target:** `neondb_staging` (`ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`).
- **Database Identity Fingerprint:** `6f4741bdaaf4` (`is_isolated=True`).
- **Unapplied Migrations:** `0`.
- **Primary Sandbox Tenant:** `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`).
- **Protected Production Tenant:** `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) — confirmed 0 records inserted, queried, or modified.
- **Production Directives:** Merge into `main` and production deployments were **NOT** performed, strictly observing user release gate directives.

---

## 6. Certification Verdict

**RELEASE CANDIDATE STATUS: CERTIFIED & READY FOR INTEGRATION GATE**  
Round 2.5.7 successfully resolves all P0 and P1 audit findings with rigorous mathematical and concurrency verification on real PostgreSQL staging.
