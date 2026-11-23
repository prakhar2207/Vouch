# SriLekh GST — Round 2.5.9 Test Execution Results
## Rule 37A Evidence Resolution Hardening & Independent Re-Certification

---

## 1. Test Environment Certification

- **Target Database:** `neondb_staging` (PostgreSQL 16+ on Neon Serverless)
- **Host / Database SHA-256 Fingerprint:** `6f4741bdaaf4` (Verified)
- **Dedicated Sandbox Company:** `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`)
- **Protected Production Tenant:** `Maa Annapurna Belting Store` (`5d2e5dea-fe86-4871-b2af-fe1c5a05c03c`) — **ZERO ACCESS (VERIFIED)**
- **Test Settings Module:** `config.settings_test_pg` (`USE_POSTGRES_TEST=1`)

---

## 2. Test Count Manifest Reconciliation (Section 8)

### 2.1 Resolution of Round 2.5.8 Count Discrepancy
- The Round 2.5.8 implementation report claimed 37 tests.
- The test results document claimed 37 tests.
- The Round 2.5.8 commit message stated "100 cumulative tests".
- **Reconciliation Finding:** The historical test suite spanning Rounds 2.5 through 2.5.7 contains exactly 101 tests (38 in `tests_round2_5_allocation` + 16 in `tests_round2_5_4_statutory_remediation` + 18 in `tests_round2_5_5_reversal_reclaim_integrity` + 11 in `tests_round2_5_6_itc_evidence_and_lineage` + 18 in `tests_round2_5_7_payment_and_evidence`). The Round 2.5.8 commit message cited "100 cumulative tests" referring to the pre-existing baseline (approx. 100), rather than combining it with the 37 newly added Round 2.5.8 tests.
- The true cumulative test count in Round 2.5.8 was **138 tests** (101 historical + 37 new).
- In Round 2.5.9, 26 new statutory tests were introduced, bringing the true cumulative total to **164 tests**.

### 2.2 Comprehensive Test Manifest Table

| Suite / File | Discovered | Executed | Skipped | Passed | Status | Role |
|---|---|---|---|---|---|---|
| `apps.gst.tests_round2_5_9_rule37a_evidence_resolution` | 26 | 26 | 0 | 26 | **100% OK** | Round 2.5.9 Dedicated Suite |
| `apps.gst.tests_round2_5_8_rule37a_evidence_integrity` | 37 | 37 | 0 | 37 | **100% OK** | Round 2.5.8 Regression Suite |
| `apps.gst.tests_round2_5_7_payment_and_evidence` | 18 | 18 | 0 | 18 | **100% OK** | Round 2.5.7 Payment Evidence Suite |
| `apps.gst.tests_round2_5_6_itc_evidence_and_lineage` | 11 | 11 | 0 | 11 | **100% OK** | Round 2.5.6 Lineage Suite |
| `apps.gst.tests_round2_5_5_reversal_reclaim_integrity` | 18 | 18 | 0 | 18 | **100% OK** | Round 2.5.5 Reversal Reclaim Suite |
| `apps.gst.tests_round2_5_4_statutory_remediation` | 16 | 16 | 0 | 16 | **100% OK** | Round 2.5.4 Remediation Suite |
| `apps.gst.tests_round2_5_allocation` | 38 | 38 | 0 | 38 | **100% OK** | Round 2.5 Core Allocation Suite |
| **TOTAL CUMULATIVE GST TESTS** | **164** | **164** | **0** | **164** | **100% OK** | **Full Platform Verification** |

---

## 3. Dedicated Round 2.5.9 Test Suite (26 Scenarios)

Command:
```bash
python manage.py test apps.gst.tests_round2_5_9_rule37a_evidence_resolution --settings=config.settings_test_pg --keepdb
```
Output:
```
Using existing test database for alias 'default'...
..........................
----------------------------------------------------------------------
Ran 26 tests in 215.170s

OK
Preserving test database for alias 'default'...
Found 26 test(s).
System check identified no issues (0 silenced).
```

### Scenario Verification Matrix

| # | Test Method Name | Invariant Verified | Result |
|---|---|---|---|
| 1 | `test_01_missing_supplier_gstin_rejected` | Missing supplier GSTIN fails closed with ValidationError | **PASS** |
| 2 | `test_02_missing_supplier_status_rejected` | Missing supplier status fails closed with ValidationError | **PASS** |
| 3 | `test_03_missing_evidence_source_rejected` | Missing evidence source fails closed with ValidationError | **PASS** |
| 4 | `test_04_missing_verification_timestamp_rejected` | Missing verification timestamp fails closed with ValidationError | **PASS** |
| 5 | `test_05_blank_gstr2b_gstr3b_period_rejected` | Blank GSTR-3B return period on GSTR-2B fallback returns DATA_UNAVAILABLE | **PASS** |
| 6 | `test_06_malformed_gstr2b_gstr3b_period_rejected` | Malformed GSTR-3B return period returns DATA_UNAVAILABLE | **PASS** |
| 7 | `test_07_wrong_gstr3b_period_rejected` | Mismatched return period (052024 vs 042024) returns DATA_UNAVAILABLE | **PASS** |
| 8 | `test_08_wrong_supplier_gstin_rejected` | Different supplier GSTIN on GSTR-2B returns UNKNOWN | **PASS** |
| 9 | `test_09_stale_negative_evidence_returns_data_unavailable` | Negative evidence >30 days old returns DATA_UNAVAILABLE | **PASS** |
| 10 | `test_10_missing_timestamp_on_negative_evidence_returns_data_unavailable` | Negative evidence without timestamp returns DATA_UNAVAILABLE | **PASS** |
| 11 | `test_11_valid_exact_period_non_filing_evidence_succeeds` | Fresh, exact-period non-filing evidence with timestamp resolves as VERIFIED_NOT_FILED | **PASS** |
| 12 | `test_12_valid_historical_filing_evidence_with_arn_and_date` | Positive filing fact with ARN & filing date remains immutable | **PASS** |
| 13 | `test_13_conflicting_positive_and_negative_sources_returns_data_unavailable` | Direct contradiction between sources returns DATA_UNAVAILABLE | **PASS** |
| 14 | `test_14_duplicate_matching_records` | Duplicate matching GSTR-2B records deterministically resolve to latest verified | **PASS** |
| 15 | `test_15_cross_company_evidence_isolation` | Evidence belonging to Company B is completely invisible to Company A | **PASS** |
| 16 | `test_16_gstr1_date_cannot_establish_gstr3b_proof` | GSTR-1 outward filing date without GSTR-3B payment proof returns DATA_UNAVAILABLE | **PASS** |
| 17 | `test_17_manufactured_status_without_supporting_evidence_rejected` | Passing VERIFIED_NOT_FILED without supporting record or reason fails closed | **PASS** |
| 18 | `test_18_reversal_before_statutory_date_rejected` | Reversal before 30th Sept of following FY rejected with ValidationError | **PASS** |
| 19 | `test_19_duplicate_reversal_attempt_rejected` | Second reversal attempt on same voucher rejected | **PASS** |
| 20 | `test_20_reclaim_without_prior_reversal_rejected` | Reclaim without active prior Rule 37A reversal rejected | **PASS** |
| 21 | `test_21_reclaim_with_incomplete_filing_evidence_rejected` | Reclaim with missing ARN or missing filing date rejected | **PASS** |
| 22 | `test_22_duplicate_reclaim_rejected` | Second reclaim attempt after reversal balance exhaustion rejected | **PASS** |
| 23 | `test_23_excessive_reclaim_rejected` | Reclaim amount exceeding eligible active reversal balance rejected | **PASS** |
| 24 | `test_24_section_17_5_blocked_credit_reclaim_rejected` | Reclaim on permanently blocked Section 17(5) credit rejected upfront | **PASS** |
| 25 | `test_25_concurrent_rule37a_reversal_attempts_serialized` | Concurrent reversals across 2 threads: exactly 1 succeeds, 1 rejected | **PASS** |
| 26 | `test_26_concurrent_rule37a_reclaim_attempts_serialized` | Concurrent reclaims across 2 threads: exactly 1 succeeds, 1 rejected | **PASS** |

---

## 4. Multi-Threaded PostgreSQL Concurrency Results

- **Environment:** PostgreSQL staging database with separate client database connections per thread.
- **Scenario 25 (Reversal):**
  - Thread 1 and Thread 2 concurrently invoked `create_rule37a_reversal_allocation()`.
  - Transaction isolation and row lock (`select_for_update()`) serialized execution.
  - Results: 1 success, 1 `ValidationError` ("Rule 37A reversal already exists").
  - Database verification: exactly 1 active reversal allocation persisted.
- **Scenario 26 (Reclaim):**
  - Thread 1 and Thread 2 concurrently invoked `create_rule37a_reclaim_allocation()`.
  - Transaction isolation and reversal balance check serialized execution.
  - Results: 1 success, 1 `ValidationError` ("reversal balance exhausted / already fully reclaimed").
  - Database verification: exactly 1 active reclaim allocation persisted; balance consumed to ₹0.00.
