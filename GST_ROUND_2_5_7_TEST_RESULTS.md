# SriLekh GST Engine — Round 2.5.7: Test Results & Verification Certification

**Product:** SriLekh — GST-Enabled Double-Entry Accounting SaaS for Indian MSMEs  
**Release Round:** Round 2.5.7 (Payment Event Integrity & Supplier Evidence Certification)  
**Parent Release:** Round 2.5.6 (`b3058ba7b4667c8ced89bcb9720a33997ea7e79e`)  
**Feature Branch:** `fix/round2-5-7-payment-evidence-certification`  
**Test Engine:** Django Test Runner + `psycopg3` on PostgreSQL 16  
**Target Database:** Neon PostgreSQL `neondb_staging` (`ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`)  
**Staging Database Fingerprint:** `6f4741bdaaf4` (`is_isolated=True`)  
**Primary Sandbox Tenant:** `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`)  
**Protected Production Tenant:** `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c` — 0 records touched)

---

## 1. Executive Test Verdict

| Component | Target Environment | Tests Ran | Failures | Errors | Result |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Round 2.5.7 Dedicated Test Suite** | Neon PostgreSQL `neondb_staging` | 18 | 0 | 0 | **PASS** |
| **Round 2.5.6 Evidence & Lineage Suite** | Neon PostgreSQL `neondb_staging` | 11 | 0 | 0 | **PASS** |
| **Round 2.5.5 Reversal & Reclaim Suite** | Neon PostgreSQL `neondb_staging` | 18 | 0 | 0 | **PASS** |
| **Round 2.5.4 Statutory Remediation** | Neon PostgreSQL `neondb_staging` | 16 | 0 | 0 | **PASS** |
| **Round 2.5 Core Allocation Engine** | Neon PostgreSQL `neondb_staging` | 38 | 0 | 0 | **PASS** |
| **Cumulative GST Engine Tests** | **Neon PostgreSQL Staging** | **101** | **0** | **0** | **100% PASS** |

---

## 2. Round 2.5.7 Dedicated Test Matrix (`apps/gst/tests_round2_5_7_payment_and_evidence.py`)

All 18 tests ran and passed against the real Neon PostgreSQL staging database:

```
Using existing test database for alias 'default'...
..................
----------------------------------------------------------------------
Ran 18 tests in 140.623s

OK
```

### Granular Test Breakdown:

| # | Test Method Name | Statutory / Engineering Invariant Verified | Result |
| :---: | :--- | :--- | :---: |
| 1 | `test_identical_retry_returns_same_allocation_and_lineage` | Retrying identical payment event returns existing allocation (idempotent success); zero duplicate allocations or lineages created. | **PASS** |
| 2 | `test_conflict_amount_mismatch_on_same_event_id_raises_validation_error` | Reusing `payment_event_id` with a different paid amount raises `ValidationError("Payment-Event Idempotency Conflict")`. | **PASS** |
| 3 | `test_conflict_cross_voucher_reuse_of_event_id_raises_validation_error` | Reusing `payment_event_id` across different vouchers within the same company raises `ValidationError("Payment-Event Idempotency Conflict")`. | **PASS** |
| 4 | `test_distinct_event_ids_with_identical_amounts_both_succeed` | Two genuine sequential partial payments of identical amounts with distinct event IDs both succeed without colliding. | **PASS** |
| 5 | `test_missing_payment_event_id_prohibited_by_default` | Reclaim without `payment_event_id` is rejected in production by default; succeeds only when `allow_legacy_unidentified=True` is explicitly passed. | **PASS** |
| 6 | `test_supersede_payment_reclaim_allocation_workflow` | Statutory correction workflow marks original reclaim `SUPERSEDED`, preserves audit trail, restores invoice reversal balance, and allows corrected reclaim. | **PASS** |
| 7 | `test_inconclusive_evidence_does_not_trigger_rule37a_default` | `DATA_UNAVAILABLE`, `PENDING`, and `UNKNOWN` supplier evidence never trigger supplier default and block reversal creation. | **PASS** |
| 8 | `test_supplier_evidence_return_period_mismatch_blocks_reversal` | Supplier evidence for period `082025` cannot be used to declare default on invoice for period `062025`; rejected as period mismatch. | **PASS** |
| 9 | `test_stale_supplier_evidence_blocks_rule37a_reversal` | Supplier filing record >30 days old is marked stale, converted to `DATA_UNAVAILABLE`, and blocks automated reversal creation. | **PASS** |
| 10 | `test_rule37a_reversal_rejected_before_30_sep_statutory_default_date` | Rule 37A reversal before 30th September following FY end is rejected with `ValidationError` even if supplier has not filed yet. | **PASS** |
| 11 | `test_rule37a_reclaim_requires_affirmative_arn_and_date` | Reclaiming under Rule 37A with `VERIFIED_FILED` strictly requires valid Application Reference Number (ARN) and filing date. | **PASS** |
| 12 | `test_gstr1_outward_declaration_cannot_satisfy_rule37a_reclaim` | GSTR-1 outward filing date in GSTR-2B cannot be substituted for GSTR-3B tax payment under Section 16(2)(c); reclaim rejected. | **PASS** |
| 13 | `test_manually_confirmed_reclaim_audit_trail` | `MANUALLY_CONFIRMED` reclaim requires document reference (CA certificate/challan) and records user identity, timestamp, and notes. | **PASS** |
| 14 | `test_section_50_leap_year_precision` | Section 50 interest precisely computes 366 days in leap year 2024 (₹4,918.03) vs 365 days in standard year 2025 (₹4,931.51). | **PASS** |
| 15 | `test_rule37a_safe_harbor_zero_interest_before_30_nov` | Rule 37A reversal on or before 30-Nov carries zero interest; reversal after 30-Nov attracts Section 50 interest from 1st Dec. | **PASS** |
| 16 | `test_section_16_decision_table_comprehensive` | Comprehensive decision-table test covering all statutory conditions: Section 17(5), 16(2)(b), First Proviso, 16(5), 16(6), and 16(4). | **PASS** |
| 17 | `test_concurrent_duplicate_delivery_creates_exactly_one_allocation` | Multi-threaded PostgreSQL concurrency test: 2 concurrent threads delivering identical payment events produce exactly 1 allocation and 1 lineage. | **PASS** |
| 18 | `test_protected_production_tenant_isolation` | Asserts sandbox company ID is `4e62863a-08f9-4e99-b0bd-64873acfdd33`; confirms production tenant (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) has 0 records. | **PASS** |

---

## 3. Multi-Threaded Concurrency & Database Constraint Verification

### Test Design (`Round257ConcurrencyAndIsolationTests`)
Simulates high-concurrency webhook ingestion or double-click user submissions on PostgreSQL:
- Two independent OS threads spawned with separate database connections to Neon PostgreSQL.
- Both threads simultaneously attempt `create_rule37_reclaim_allocation()` with identical `payment_event_id='PE-CONC-DUPL-001'` on the same voucher.

### Verified Outcomes:
1. **Row Lock Serialization:** PostgreSQL `select_for_update()` row locks serialized the transactions.
2. **Idempotent Return:** Exactly one allocation ID was generated; the second thread safely returned the identical allocation instance.
3. **Lineage Conservation:** Exactly 1 `GSTReversalReclaimLineage` record was created for ₹900.00. Zero duplicate or orphaned lineages.
4. **Unique Constraint Enforcement:** Verified that `unique_active_reclaim_per_company_payment_event` prevents duplicate records at the PostgreSQL engine level.

---

## 4. Tenant Isolation & Production Protection Verification

1. **Dedicated Test Sandbox Tenant:**
   - Name: `Apex Belting & Industrial Store (Demo)`
   - UUID: `4e62863a-08f9-4e99-b0bd-64873acfdd33`
   - Verified via:
     ```python
     assert str(company.id) == '4e62863a-08f9-4e99-b0bd-64873acfdd33'
     ```
2. **Protected Production Tenant Integrity:**
   - Name: `Maa Annapurna Belting Store`
   - UUID: `5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`
   - Test suite queries confirmed `prod_count == 0` allocations created or modified.
3. **Cross-Tenant Constraint Scoping:**
   - Validated that using `PE-CONC-DUPL-001` in a separate company tenant succeeds, proving that the unique constraint is correctly scoped to `(company, payment_event_id)` and does not bleed across tenants.

---

## 5. Certification Verdict

**VERDICT: UNCONDITIONAL PASS**  
The SriLekh Round 2.5.7 implementation satisfies all statutory, mathematical, concurrency, and security requirements. All 101 tests across the Round 2.5.x suite pass with zero errors and zero failures against real Neon PostgreSQL staging.
