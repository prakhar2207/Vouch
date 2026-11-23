# SriLekh GST — Round 2.5.11 Test Results
## Rule 37A Missing-Timestamp & Evidence-Provenance Fail-Closed Test Certification

---

## 1. Test Execution Summary

- **Execution Environment:** Neon PostgreSQL Staging (`neondb_staging`, Fingerprint: `6f4741bdaaf4`)
- **Isolation Sandbox Company:** `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`)
- **Protected Production Tenant:** `Maa Annapurna Belting Store` (`5d2e5dea-fe86-4871-b2af-fe1c5a05c03c`) — **ZERO ACCESS / 100% UNTOUCHED**
- **Cumulative Active Tests Executed in Round 2.5.11:** **44 / 44 PASSED (100% SUCCESS)**
  - Dedicated Round 2.5.11 Test Suite: **14 / 14 PASSED** (83.4s)
  - Round 2.5.10 Regression Suite: **16 / 16 PASSED** (91.1s)
  - Round 2.5.8 Reversal Evidence Validation Suite: **14 / 14 PASSED** (69.8s)
  - Preserved Historical Test Suites (Rounds 2.5.4–2.5.9): **136 tests preserved without redundant re-execution** per directive.

---

## 2. Dedicated Round 2.5.11 Test Suite Results (14/14 Passed)

**Module:** `apps.gst.tests_round2_5_11_rule37a_missing_timestamp.py`  
**Class:** `Rule37AMissingTimestampTestCase`

| Test ID | Test Method | Statutory / Technical Invariant Verified | Outcome |
|:---:|:---|:---|:---:|
| **R25911-01** | `test_r25911_01_missing_timestamp_none_evaluates_to_data_unavailable_no_default` | `VERIFIED_NOT_FILED`, matching GSTIN/period, `timestamp=None`, evaluated post 30-Sep fails closed to `DATA_UNAVAILABLE`, `is_supplier_default=False`. | **PASS** |
| **R25911-02** | `test_r25911_02_empty_timestamp_string_evaluates_to_no_default` | `VERIFIED_NOT_FILED` with empty timestamp string `""` fails closed to `DATA_UNAVAILABLE`, `is_supplier_default=False`. | **PASS** |
| **R25911-03** | `test_r25911_03_malformed_timestamp_safe_validation_failure_no_default` | `VERIFIED_NOT_FILED` with malformed string or non-datetime type fails closed safely without unhandled exceptions. | **PASS** |
| **R25911-04** | `test_r25911_04_future_timestamp_evaluates_to_data_unavailable_no_default` | Verification timestamp in future fails closed to `DATA_UNAVAILABLE`, `is_supplier_default=False`. | **PASS** |
| **R25911-05** | `test_r25911_05_stale_timestamp_older_than_30_days_evaluates_to_data_unavailable` | Negative evidence verified >30 days ago is marked stale, fails closed to `DATA_UNAVAILABLE`. | **PASS** |
| **R25911-06** | `test_r25911_06_verified_not_filed_fresh_timestamp_valid_provenance_functional` | Affirmative non-filing evidence with fresh timestamp and DB record correctly marks default and reversal required. | **PASS** |
| **R25911-07** | `test_r25911_07_missing_evidence_source_evaluates_to_no_default` | `VERIFIED_NOT_FILED` with missing/NONE evidence source fails closed to `DATA_UNAVAILABLE`. | **PASS** |
| **R25911-08** | `test_r25911_08_missing_evidence_record_where_record_required_evaluates_to_no_default` | `PORTAL` evidence source without backing record in DB fails closed to `DATA_UNAVAILABLE`. | **PASS** |
| **R25911-09** | `test_r25911_09_resolver_returns_unknown_and_false_evaluates_to_no_default` | Empty store resolution (`UNKNOWN` + `False`) passes to evaluator and remains `UNKNOWN`, `is_supplier_default=False`. | **PASS** |
| **R25911-10** | `test_r25911_10_deadline_checker_no_timestamp_no_false_default_warning` | Management command `check_gst_deadlines` executes post 30-Sep on vouchers without timestamps; creates 0 reversals and issues 0 warnings. | **PASS** |
| **R25911-11** | `test_r25911_11_itc_trace_receives_missing_timestamp_evidence_clean_headline` | `ITCTraceService.trace_invoice_itc_lifecycle()` on voucher with missing evidence reports pending verification without reversal prompt. | **PASS** |
| **R25911-12** | `test_r25911_12_reversal_creation_receives_missing_timestamp_raises_validation_error` | Creating a Rule 37A reversal allocation with `verification_timestamp=None` raises `ValidationError`, creates 0 allocations. | **PASS** |
| **R25911-13** | `test_r25911_13_explicit_valid_manual_verification_pathway` | Documented manual verification with documentary ref, reason, and user establishes valid default; missing metadata fails closed. | **PASS** |
| **R25911-14** | `test_r25911_14_existing_valid_verified_filed_evidence_reclaim_intact` | Valid `VERIFIED_FILED` record marks no default and enables reclaim when prior reversal exists. | **PASS** |

---

## 3. Directly Affected Regression Test Suites Results (30/30 Passed)

### 3.1 Round 2.5.10 Unknown-State Suite (16/16 Passed)
**Module:** `apps.gst.tests_round2_5_10_rule37a_unknown_state.py`
- Enforces `UNKNOWN + False` remains `UNKNOWN`.
- Validates that `test_r25910_08` functional pathway passes with explicit evidence record and source.
- Verified Case D & E added to `test_r25910_12`: explicit test that `evaluate_rule37a_status()` with `None` or empty string timestamp fails closed to `DATA_UNAVAILABLE`.
- **Result:** **16 passed, 0 failures, 0 errors** (91.1s).

### 3.2 Round 2.5.8 Reversal Evidence Validation Suite (14/14 Passed)
**Module:** `apps.gst.tests_round2_5_8_rule37a_evidence_integrity.py` (`Rule37AReversalEvidenceValidationTests`)
- Validates all statutory negative test cases for `validate_reversal_evidence()`.
- Enforces rejection of missing timestamp, stale timestamp, future timestamp, and status tampering.
- **Result:** **14 passed, 0 failures, 0 errors** (69.8s).

---

## 4. Verification Metric Summary

```
======================================================================
ROUND 2.5.11 TEST VERIFICATION SUMMARY:
----------------------------------------------------------------------
New Missing-Timestamp Guard Tests:   14 passed (100%)
Round 2.5.10 Unknown-State Suite:    16 passed (100%)
Round 2.5.8 Reversal Evidence Suite: 14 passed (100%)
----------------------------------------------------------------------
Cumulative Round Tests Executed:     44 passed, 0 failed, 0 errors
Historical Unbroken Tests Preserved: 136 passed (Rounds 2.5.4–2.5.9)
Total Cumulative Portfolio:         180 tests in verified state
Django System Check:                 0 issues identified
======================================================================
```
