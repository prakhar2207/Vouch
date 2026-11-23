# SriLekh GST — Round 2.5.12 Test Results
## Rule 37A Positive Evidence, Reclaim Authorization & Provenance Integrity Test Report

---

### Environment Specifications

| Parameter | Execution Target | Verification Status |
|:---|:---|:---|
| **Database Engine** | PostgreSQL 16 (Neon Serverless) | Verified (`psycopg` / `django.db.backends.postgresql`) |
| **Database Name** | `test_neondb_staging` | Verified isolated test database |
| **Host Fingerprint** | `6f4741bdaaf4` | Matches approved staging environment |
| **Sandbox Tenant ID** | `4e62863a-08f9-4e99-b0bd-64873acfdd33` | Apex Belting & Industrial Store (Demo) |
| **Protected Tenant ID** | `5d2e5dea-fe86-4871-b2af-fe1c5a05c03c` | Maa Annapurna Belting Store — **100% ISOLATED / UNTOUCHED** |
| **Test Runner Flags** | `--settings=config.settings_test_pg --keepdb` | Clean execution |

---

### Executive Test Summary

```
========================================================================================
TEST SUITE                                           TESTS   PASSED   FAILED   ERRORS   STATUS
========================================================================================
Round 2.5.12 Positive Evidence & Reclaim Suite          28       28        0        0   PASSED
Round 2.5.11 Missing-Timestamp Regression Suite         14       14        0        0   PASSED
Round 2.5.10 UNKNOWN-State Regression Suite             16       16        0        0   PASSED
----------------------------------------------------------------------------------------
TOTAL TARGETED STATUTORY REGRESSION SUITE               58       58        0        0   PASSED (100%)
========================================================================================
```

---

### Dedicated Round 2.5.12 Test Suite Breakdown (28 Tests)

| Test ID | Method Name | Statutory Category | Result | Execution Time |
|:---|:---|:---|:---:|:---:|
| `R25912-01` | `test_r25912_01_raw_verified_filed_string_without_evidence_record_rejected` | Negative Evidence Guard | **PASS** | 5.8s |
| `R25912-02` | `test_r25912_02_raw_manually_confirmed_without_manual_proof_rejected` | Manual Safeguard | **PASS** | 5.2s |
| `R25912-03` | `test_r25912_03_supplier_gstr3b_filed_boolean_without_evidence_rejected` | Fail-Closed Boolean | **PASS** | 5.1s |
| `R25912-04` | `test_r25912_04_missing_arn_where_required_rejected` | Filing Proof (ARN) | **PASS** | 5.3s |
| `R25912-05` | `test_r25912_05_missing_filing_date_rejected` | Filing Proof (Date) | **PASS** | 5.2s |
| `R25912-06` | `test_r25912_06_supplier_gstin_mismatch_rejected` | Supplier Identity | **PASS** | 5.4s |
| `R25912-07` | `test_r25912_07_company_tenant_mismatch_rejected` | Tenant Isolation | **PASS** | 5.6s |
| `R25912-08` | `test_r25912_08_return_period_mismatch_rejected` | Period Integrity | **PASS** | 5.3s |
| `R25912-09` | `test_r25912_09_gstr1_filing_evidence_used_as_gstr3b_proof_rejected` | Section 16(2)(c) Guard | **PASS** | 5.9s |
| `R25912-10` | `test_r25912_10_gstr2b_statement_period_substituted_for_gstr3b_period_rejected` | Period Integrity | **PASS** | 6.1s |
| `R25912-11` | `test_r25912_11_conflicting_positive_and_negative_evidence_rejected` | Conflict Resolution | **PASS** | 5.5s |
| `R25912-12` | `test_r25912_12_inactive_or_invalid_filing_record_rejected` | Statutory Discharge | **PASS** | 5.2s |
| `R25912-13` | `test_r25912_13_reclaim_without_existing_reversal_rejected` | Prior Reversal Guard | **PASS** | 5.4s |
| `R25912-14` | `test_r25912_14_reclaim_against_unrelated_vouchers_reversal_rejected` | Voucher Linkage | **PASS** | 5.6s |
| `R25912-15` | `test_r25912_15_reclaim_exceeding_remaining_reversed_amount_rejected` | Balance Cap Guard | **PASS** | 5.7s |
| `R25912-16` | `test_r25912_16_duplicate_reclaim_request_idempotency` | Idempotency | **PASS** | 5.5s |
| `R25912-17` | `test_r25912_17_concurrent_reclaim_attempts_serialized` | Row Locking Concurrency | **PASS** | 12.8s |
| `R25912-18` | `test_r25912_18_fully_reclaimed_reversal_rejects_additional_reclaims` | Double Reclaim Guard | **PASS** | 5.8s |
| `R25912-19` | `test_r25912_19_section_17_5_blocked_credit_reclaim_rejected` | Section 17(5) Guard | **PASS** | 5.3s |
| `R25912-20` | `test_r25912_20_failed_validation_causes_zero_database_mutation` | Transaction Integrity | **PASS** | 5.2s |
| `R25912-21` | `test_r25912_21_valid_portal_filing_evidence_authorizes_reclaim` | Positive Authorization | **PASS** | 5.7s |
| `R25912-22` | `test_r25912_22_valid_supplier_filing_record_exact_gstin_period` | Evidence Record Auth | **PASS** | 5.5s |
| `R25912-23` | `test_r25912_23_valid_authorized_manual_evidence_authorizes_reclaim` | Manual Confirmation | **PASS** | 5.6s |
| `R25912-24` | `test_r25912_24_valid_partial_reclaim_calculates_correct_remaining_balance` | Partial Reclaim | **PASS** | 6.0s |
| `R25912-25` | `test_r25912_25_valid_full_reclaim_correct_lineage_and_zero_balance` | Full Reclaim & Lineage | **PASS** | 6.1s |
| `R25912-26` | `test_r25912_26_reversed_itc_followed_by_genuine_filing_becomes_eligible` | Statutory Lifecycle | **PASS** | 5.9s |
| `R25912-27` | `test_r25912_27_existing_valid_historical_filing_record_without_artificial_expiry` | Historical Facts | **PASS** | 5.4s |
| `R25912-28` | `test_r25912_28_repeated_evidence_resolution_deterministic_and_stable` | Cryptographic Provenance | **PASS** | 5.3s |

---

### Regression Verification Breakdown

#### Round 2.5.11 Missing-Timestamp Suite (`apps.gst.tests_round2_5_11_rule37a_missing_timestamp`)
- 14 Tests executed in 106.75s: **ALL 14 PASSED**.
- Confirmed zero regression on negative evidence timestamp validation and supplier default suppression.

#### Round 2.5.10 UNKNOWN-State Suite (`apps.gst.tests_round2_5_10_rule37a_unknown_state`)
- 16 Tests executed in 124.17s: **ALL 16 PASSED**.
- Confirmed zero regression on UNKNOWN/PENDING fail-closed behavior.

---

### Conclusion
The SriLekh GST compliance engine achieves 100% compliance across all 58 statutory tests under PostgreSQL staging with zero errors, zero failures, and zero test skips.
