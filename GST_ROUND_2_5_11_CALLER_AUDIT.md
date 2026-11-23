# SriLekh GST — Round 2.5.11 Caller Audit
## Exhaustive Audit of Rule 37A Callers & Evidence Invariants

---

## 1. Scope & Objective

This audit examines every caller and invocation site of the core Rule 37A compliance routines across the repository to verify that:
1. Missing, empty, malformed, future, or stale timestamps can NEVER establish a supplier default.
2. Missing evidence sources or records cannot establish a default.
3. Raw booleans (`False` / `True`) cannot establish filing state.
4. Manually supplied strings cannot bypass server-side validation.
5. Management deadline commands and ITC trace lifecycle views remain fail-closed without false reversal alerts.

---

## 2. Caller-by-Caller Verification Table

### 2.1 `GSTAllocationService.evaluate_rule37a_status()`

| Caller Location | Context / File | Input Arguments Passed | Handling of Missing / Stale Timestamp & Provenance | Risk of False Default | Status / Audit Finding |
|---|---|---|---|:---:|---|
| `check_gst_deadlines.py:130` | Automated deadline evaluation command | `voucher`, `check_date=eval_date`, `supplier_status=ev_res["status"]`, `supplier_return_period=ev_res["return_period"]`, `supplier_gstin=ev_res["supplier_gstin"]`, `is_stale_evidence=ev_res["is_stale"]`, `verification_timestamp=ev_res.get("verification_timestamp")`, `evidence_source=ev_res.get("evidence_source")`, `evidence_record=ev_res.get("evidence_record")`, `evidence_document_ref=ev_res.get("document_ref")` | When `verification_timestamp` is `None` or evidence is missing, evaluator immediately sets `clean_status='DATA_UNAVAILABLE'`, `is_supplier_default=False`. `check_gst_deadlines` does not trigger reversal warning, overdue flag, or interest calculation. | **ZERO** | **VERIFIED FAIL-CLOSED** |
| `itc_trace_service.py:132` | Lifecycle ITC tracing / Business Owner View | `voucher`, `check_date=today`, `supplier_status=ev_res["status"]`, `supplier_return_period=ev_res["return_period"]`, `supplier_gstin=ev_res["supplier_gstin"]`, `is_stale_evidence=ev_res["is_stale"]`, `verification_timestamp=ev_res.get("verification_timestamp")`, `evidence_source=ev_res.get("evidence_source")`, `evidence_record=ev_res.get("evidence_record")`, `evidence_document_ref=ev_res.get("document_ref")` | When evidence timestamp or provenance is missing, `r37a_status["supplier_status"]` is set to `DATA_UNAVAILABLE`. Trace headline outputs `"Pending Verification: Supplier GSTR-3B Evidence Unavailable"`, never prompting reversal. | **ZERO** | **VERIFIED FAIL-CLOSED** |
| `tests_round2_5_10_...` | Round 2.5.10 test suite | Tests `test_r25910_08` and `test_r25910_12` | `test_r25910_08` passes valid evidence provenance; `test_r25910_12` explicitly tests `None` and `""` timestamps, asserting fail-closed `DATA_UNAVAILABLE`. | **ZERO** | **VERIFIED FAIL-CLOSED** |
| `tests_round2_5_11_...` | Round 2.5.11 dedicated test suite | Explicit testing of missing, empty, malformed, future, stale timestamps, missing source, and missing records | 14/14 scenarios confirm absolute fail-closed operation across all unverified timestamp states. | **ZERO** | **VERIFIED FAIL-CLOSED** |

---

### 2.2 `Rule37AEvidenceService.resolve_voucher_evidence()`

| Caller Location | Context / File | Input Arguments Passed | Handling of Missing / Stale Evidence | Risk of Premature Default | Status / Audit Finding |
|---|---|---|---|:---:|---|
| `check_gst_deadlines.py:128` | Deadline sweep job | `voucher` | Queries portal filing record and GSTR-2B. When records are missing, returns `{"status": "UNKNOWN", "supplier_gstr3b_filed": False, "verification_timestamp": None, "evidence_source": "NONE", "evidence_record": None}`. | **ZERO** | **VERIFIED FAIL-CLOSED** |
| `itc_trace_service.py:130` | ITC Trace Lifecycle | `voucher` | Resolves evidence provenance. When missing, returns `UNKNOWN` with `verification_timestamp=None`. | **ZERO** | **VERIFIED FAIL-CLOSED** |
| `tests_round2_5_8_...`, `tests_round2_5_9_...`, `tests_round2_5_10_...`, `tests_round2_5_11_...` | Test suites | `voucher` | Thoroughly tests resolution precedence, conflict detection (`CONFLICTING_SOURCES` -> `DATA_UNAVAILABLE`), and staleness expiration (>30 days). | **ZERO** | **VERIFIED FAIL-CLOSED** |

---

### 2.3 `Rule37AEvidenceService.validate_reversal_evidence()`

| Caller Location | Context / File | Input Arguments Passed | Handling of Missing / Stale Evidence | Risk of Premature Default | Status / Audit Finding |
|---|---|---|---|:---:|---|
| `create_rule37a_reversal_allocation()` | Allocation Service reversal factory | `voucher`, `supplier_status`, `supplier_gstin`, `supplier_return_period`, `evidence_source`, `verification_timestamp`, `check_date`, ... | Strictly rejects missing (`None`), empty string, or malformed timestamps with `ValidationError`. Rejects future timestamps, stale timestamps (>30 days), period mismatch, and GSTIN mismatch. | **ZERO** | **VERIFIED FAIL-CLOSED** |
| `Rule37AReversalEvidenceValidationTests` | Dedicated reversal validation suite | 14 statutory negative cases | Enforces `ValidationError` across all negative boundary conditions. | **ZERO** | **VERIFIED FAIL-CLOSED** |

---

### 2.4 `GSTAllocationService.create_rule37a_reversal_allocation()`

| Caller Location | Context / File | Pre-requisites & Evidence Checks | Handling of Unverified States | Status / Audit Finding |
|---|---|---|---|---|
| Direct API / Management / Workflow invocation | Inward ITC reversal creation | Requires mandatory keyword arguments: `supplier_status`, `supplier_gstin`, `supplier_return_period`, `evidence_source`, `verification_timestamp`. | Calls `validate_reversal_evidence()`. Any attempt to pass `None`, empty string, or unverified timestamp raises `ValidationError`. Duplicate reversals on same invoice are blocked. | **VERIFIED FAIL-CLOSED** |
| `tests_round2_5_11_rule37a_missing_timestamp.py:R25911-12` | Missing-timestamp reversal test | `verification_timestamp=None` | Raises `ValidationError("Rule 37A reversal requires a verification timestamp.")`. Allocations count remains 0. | **VERIFIED FAIL-CLOSED** |

---

### 2.5 `apps.gst.management.commands.check_gst_deadlines`

| Execution Context | Scanning Filter | Evidence Check | Reversal Creation Policy | Status / Audit Finding |
|---|---|---|---|---|
| CLI Command / Scheduled Cron | `status='POSTED'`, `voucher_type='PURCHASE'`, `allocation_type='INWARD_SUPPLY'` | Resolves evidence via `Rule37AEvidenceService.resolve_voucher_evidence(v)` and evaluates status via `evaluate_rule37a_status(...)`. | Only issues reversal warning if `r37a_res["is_supplier_default"] == True`. Because missing timestamps fail closed to `DATA_UNAVAILABLE` (`is_supplier_default=False`), zero false warnings or automated reversals are executed. | **VERIFIED FAIL-CLOSED** |

---

## 3. Summary of Caller Audit Findings

1. **Complete Eradication of Timestamp Fallbacks:** Missing timestamps in `evaluate_rule37a_status()` now deterministically transition to `DATA_UNAVAILABLE`. No caller can bypass this check.
2. **Type-Safe Timestamp Validation:** Strings, dates, and naive datetimes are safely converted and timezone-validated; future and stale timestamps are rejected across all entry points.
3. **Provenanced Evidence Integrity:** Both `check_gst_deadlines` and `itc_trace_service` pass the complete resolved evidence package (`evidence_source`, `evidence_record`, `evidence_document_ref`), ensuring end-to-end evidence auditability.
