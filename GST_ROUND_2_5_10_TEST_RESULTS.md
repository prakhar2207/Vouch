# SriLekh GST — Round 2.5.10 Test Results
## Rule 37A UNKNOWN-State Fail-Closed & Evidence Integrity Test Certification

---

## 1. Test Execution Summary

- **Execution Environment:** Neon PostgreSQL Staging (`neondb_staging`, Fingerprint: `6f4741bdaaf4`)
- **Isolation Sandbox Company:** `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`)
- **Protected Production Tenant:** `Maa Annapurna Belting Store` (`5d2e5dea-fe86-4871-b2af-fe1c5a05c03c`) — **ZERO ACCESS / 100% UNTOUCHED**
- **Cumulative Active Tests Executed in Round 2.5.10:** **79 / 79 PASSED (100% SUCCESS)**
  - Dedicated Round 2.5.10 Test Suite: **16 / 16 PASSED** (90.4s)
  - Round 2.5.9 Regression Test Suite: **26 / 26 PASSED** (172.8s)
  - Round 2.5.8 Regression Test Suite: **37 / 37 PASSED** (247.4s)
  - Historical Passed Tests (Rounds 2.5.4–2.5.7): **101 tests preserved without redundant re-execution** per directive.

---

## 2. Dedicated Round 2.5.10 Test Suite Results (16/16 Passed)

**Module:** `apps.gst.tests_round2_5_10_rule37a_unknown_state.py`  
**Class:** `Rule37AUnknownStateTestCase`

| Test ID | Test Method | Statutory / Technical Invariant Verified | Outcome |
|:---:|:---|:---|:---:|
| **R25910-01** | `test_r25910_01_resolver_unknown_false_evaluator_remains_unknown` | When resolver returns `status='UNKNOWN'` and `supplier_gstr3b_filed=False`, evaluator must retain `clean_status='UNKNOWN'`, `is_supplier_default=False`. | **PASS** |
| **R25910-02** | `test_r25910_02_no_evidence_past_statutory_default_date_no_default` | An invoice with zero evidence evaluated on 15-Oct (post 30-Sep) must NOT be marked in default. | **PASS** |
| **R25910-03** | `test_r25910_03_no_evidence_reversal_not_permitted` | Creating a Rule 37A reversal allocation with `supplier_status='UNKNOWN'` is strictly rejected with `ValidationError`. | **PASS** |
| **R25910-04** | `test_r25910_04_explicit_unknown_with_boolean_false_no_conversion` | Explicit status `'UNKNOWN'` paired with `supplier_gstr3b_filed=False` does not convert to `VERIFIED_NOT_FILED`. | **PASS** |
| **R25910-05** | `test_r25910_05_explicit_data_unavailable_with_boolean_false_no_default` | Status `'DATA_UNAVAILABLE'` with `supplier_gstr3b_filed=False` past default date results in `is_supplier_default=False`. | **PASS** |
| **R25910-06** | `test_r25910_06_explicit_pending_with_boolean_false_no_default` | Status `'PENDING'` with `supplier_gstr3b_filed=False` results in `is_supplier_default=False`. | **PASS** |
| **R25910-07** | `test_r25910_07_null_boolean_and_unknown_status_no_default` | `supplier_status='UNKNOWN'` with `supplier_gstr3b_filed=None` results in `is_supplier_default=False`. | **PASS** |
| **R25910-08** | `test_r25910_08_explicit_verified_not_filed_with_valid_fresh_evidence_functional` | Explicit `VERIFIED_NOT_FILED` with matching GSTIN, matching period, fresh timestamp, past 30-Sep correctly establishes default and permits reversal. | **PASS** |
| **R25910-09** | `test_r25910_09_explicit_verified_filed_with_valid_evidence_functional` | Explicit `VERIFIED_FILED` with matching GSTIN, matching period, and fresh evidence marks `is_supplier_default=False` and enables reclaim eligibility. | **PASS** |
| **R25910-10** | `test_r25910_10_wrong_supplier_gstin_evidence_rejected` | Evidence with mismatched supplier GSTIN converts to `DATA_UNAVAILABLE` and prevents default evaluation. | **PASS** |
| **R25910-11** | `test_r25910_11_wrong_return_period_evidence_rejected` | Evidence with mismatched return period converts to `DATA_UNAVAILABLE` and prevents default evaluation. | **PASS** |
| **R25910-12** | `test_r25910_12_stale_or_missing_verification_timestamp_evidence_rejected` | Evidence verified >30 days ago or with missing timestamp converts to `DATA_UNAVAILABLE` and prevents default evaluation. | **PASS** |
| **R25910-13** | `test_r25910_13_deadline_checker_no_evidence_no_reversal_or_default` | Management command `check_gst_deadlines` executes post 30-Sep on vouchers with no evidence; creates 0 reversals and issues 0 warnings. | **PASS** |
| **R25910-14** | `test_r25910_14_api_service_integration_passes_resolver_output_directly` | Direct integration test verifying output of `resolve_voucher_evidence` passes directly into `evaluate_rule37a_status` without tampering. | **PASS** |
| **R25910-15** | `test_r25910_15_boolean_true_with_unknown_status_never_establishes_filing` | Evaluator with `supplier_status='UNKNOWN'` and raw `supplier_gstr3b_filed=True` does NOT allow statutory reclaim. | **PASS** |
| **R25910-16** | `test_r25910_16_trace_service_with_unknown_status_clean_lineage` | `ITCTraceService.trace_invoice_itc_lifecycle()` on voucher with `UNKNOWN` evidence cleanly reports inward ITC available without false reversal flags. | **PASS** |

---

## 3. Regression Test Suites Execution Results (63/63 Passed)

### 3.1 Round 2.5.9 Regression Suite (26/26 Passed)
**Module:** `apps.gst.tests_round2_5_9_rule37a_evidence_resolution.py`  
- Enforces strict 6-digit GSTR-3B return period validation (`MMYYYY`).
- Prohibits inferring GSTR-3B periods from GSTR-2B import batch statement periods.
- Preserves raw portal verification timestamps and detects stale evidence (>30 days).
- Resolves cross-source contradictions (portal vs GSTR-2B) into fail-closed `DATA_UNAVAILABLE`.
- Prevents reversals before 30th September post FY end.
- Enforces reclaim balance exhaustion and Section 17(5) blocking.
- **Result:** **26 passed, 0 failures, 0 errors** (172.8s).

### 3.2 Round 2.5.8 Regression Suite (37/37 Passed)
**Module:** `apps.gst.tests_round2_5_8_rule37a_evidence_integrity.py`  
- Comprehensive validation of all 12 statutory negative test cases.
- Mandatory keyword arguments on `create_rule37a_reversal_allocation`.
- Database schema and composite indexing on `GSTReportingAllocation`.
- Multi-threaded voucher reversal concurrency protection.
- **Result:** **37 passed, 0 failures, 0 errors** (247.4s).

---

## 4. Total Verification Metric Summary

```
======================================================================
ROUND 2.5.10 TEST SUMMARY:
----------------------------------------------------------------------
New Fail-Closed Guard Tests:         16 passed (100%)
Round 2.5.9 Evidence Resolution:     26 passed (100%)
Round 2.5.8 Evidence Integrity:      37 passed (100%)
----------------------------------------------------------------------
Cumulative Round Tests Executed:     79 passed, 0 failed, 0 errors
Historical Unbroken Tests Preserved: 101 passed (R2.5.4 - R2.5.7)
Total Comprehensive Portfolio:      180 tests in verified state
======================================================================
```
