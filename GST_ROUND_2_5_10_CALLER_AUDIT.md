# SriLekh GST — Round 2.5.10 Caller Audit
## Exhaustive Audit of Rule 37A Evidence, Evaluation & Reversal Callers

---

## 1. Scope & Objective

This audit verifies every caller and invocation site of the core Rule 37A compliance functions to guarantee that:
1. No caller converts an `UNKNOWN`, `DATA_UNAVAILABLE`, `PENDING`, or unverified status into a default or reversal.
2. No caller triggers a statutory reversal without verified, non-stale, return-period-specific supplier non-filing evidence.
3. Every caller properly handles edge cases, missing parameters, and fail-closed outcomes.

---

## 2. Caller-by-Caller Verification Matrix

### 2.1 `GSTAllocationService.evaluate_rule37a_status()`

| Caller Location | Context / File | Input Arguments Passed | Handling of `UNKNOWN` / Missing Evidence | Risk of False Default | Status / Audit Finding |
|---|---|---|---|:---:|---|
| `check_gst_deadlines.py:130` | Automated deadline evaluation command | `voucher`, `check_date=check_date`, `supplier_status=ev_res["status"]`, `supplier_return_period=ev_res["return_period"]`, `supplier_gstin=ev_res["supplier_gstin"]`, `is_stale_evidence=ev_res["is_stale"]`, `verification_timestamp=ev_res.get("verification_timestamp")` | When `ev_res["status"]` is `UNKNOWN`, `evaluate_rule37a_status` retains `UNKNOWN`, setting `is_supplier_default=False`. `check_gst_deadlines` does not trigger reversal warning or creation. | **ZERO** | **VERIFIED FAIL-CLOSED** |
| `itc_trace_service.py:132` | Lifecycle ITC tracing / Business Owner View | `voucher`, `check_date=today`, `supplier_status=ev_res["status"]`, `supplier_return_period=ev_res["return_period"]`, `supplier_gstin=ev_res["supplier_gstin"]`, `is_stale_evidence=ev_res["is_stale"]`, `verification_timestamp=ev_res.get("verification_timestamp")` | When `ev_res["status"]` is `UNKNOWN`, `r37a_status["supplier_status"]` is `UNKNOWN`. Trace headline outputs `"Inward ITC Available / Safe"`, never prompting reversal. | **ZERO** | **VERIFIED FAIL-CLOSED** |
| `tests_round2_5_4_statutory_remediation.py` | Historical regression test | `voucher`, `supplier_gstr3b_filed=False` | Without explicit `supplier_status='VERIFIED_NOT_FILED'`, `clean_status` remains `UNKNOWN`, fail-closed (`is_supplier_default=False`). | **ZERO** | **VERIFIED FAIL-CLOSED** |
| `tests_round2_5_8_rule37a_evidence_integrity.py` | Round 2.5.8 test suite | Explicit combinations of `supplier_status`, `is_stale_evidence`, etc. | Validated all 12 statutory negative test cases. | **ZERO** | **VERIFIED COMPLIANT** |
| `tests_round2_5_9_rule37a_evidence_resolution.py` | Round 2.5.9 test suite | Evidence resolver output integration | Enforces exact period, freshness, and conflict handling. | **ZERO** | **VERIFIED COMPLIANT** |
| `tests_round2_5_10_rule37a_unknown_state.py` | Round 2.5.10 dedicated test suite | Explicit testing of `UNKNOWN`, `DATA_UNAVAILABLE`, `PENDING`, null timestamps, and raw boolean flags | 16/16 dedicated scenarios verify absence of default across all unverified states. | **ZERO** | **VERIFIED FAIL-CLOSED** |

---

### 2.2 `Rule37AEvidenceService.resolve_voucher_evidence()`

| Caller Location | Context / File | Input Arguments Passed | Handling of Missing / Stale Evidence | Risk of Premature Default | Status / Audit Finding |
|---|---|---|---|:---:|---|
| `check_gst_deadlines.py:128` | Deadline sweep job | `voucher` | Queries portal filing record and GSTR-2B. When records are missing, returns `{"status": "UNKNOWN", "supplier_gstr3b_filed": False, "verification_timestamp": None}`. | **ZERO** | **VERIFIED FAIL-CLOSED** |
| `itc_trace_service.py:130` | ITC Trace Lifecycle | `voucher` | Resolves evidence provenance. When missing, returns `UNKNOWN`. | **ZERO** | **VERIFIED FAIL-CLOSED** |
| `tests_round2_5_8_...` & `tests_round2_5_9_...` | Regression & Resolution tests | `voucher` | Thoroughly tests resolution precedence: conflicting sources -> `DATA_UNAVAILABLE`, stale records -> `DATA_UNAVAILABLE`. | **ZERO** | **VERIFIED FAIL-CLOSED** |

---

### 2.3 `Rule37AEvidenceService.validate_reversal_evidence()`

| Caller Location | Context / File | Input Arguments Passed | Handling of Missing / Stale Evidence | Risk of Premature Default | Status / Audit Finding |
|---|---|---|---|:---:|---|
| `create_rule37a_reversal_allocation()` | Allocation Service reversal factory | `voucher`, `supplier_status`, `supplier_gstin`, `supplier_return_period`, `evidence_source`, `verification_timestamp`, `check_date`, ... | Strictly rejects any status other than `VERIFIED_NOT_FILED`. Rejects stale evidence (>30 days), period mismatch, GSTIN mismatch, and pre-30-Sep dates with `ValidationError`. | **ZERO** | **VERIFIED FAIL-CLOSED** |
| `tests_round2_5_8_...` | Evidence integrity test suite | 12 statutory negative cases | All 12 negative boundary conditions raise `ValidationError`. | **ZERO** | **VERIFIED FAIL-CLOSED** |

---

### 2.4 `GSTAllocationService.create_rule37a_reversal_allocation()`

| Caller Location | Context / File | Pre-requisites & Evidence Checks | Handling of Unverified States | Status / Audit Finding |
|---|---|---|---|---|
| Direct API / Management / Workflow invocation | Inward ITC reversal creation | Requires mandatory keyword arguments: `supplier_status`, `supplier_gstin`, `supplier_return_period`, `evidence_source`, `verification_timestamp`. | Calls `validate_reversal_evidence()`. Any attempt to pass `UNKNOWN` or unverified data raises `ValidationError`. Duplicate reversals on same invoice are blocked. | **VERIFIED FAIL-CLOSED** |
| `tests_round2_5_8_...` & `tests_round2_5_9_...` | Test suites | Explicit valid and invalid reversal creation | Enforces full idempotency and database provenance persistence. | **VERIFIED FAIL-CLOSED** |

---

### 2.5 `apps.gst.management.commands.check_gst_deadlines`

| Execution Context | Scanning Filter | Evidence Check | Reversal Creation Policy | Status / Audit Finding |
|---|---|---|---|---|
| CLI Command / Scheduled Cron | `status='POSTED'`, `voucher_type='PURCHASE'`, `allocation_type='INWARD_SUPPLY'` | Resolves evidence via `Rule37AEvidenceService.resolve_voucher_evidence(v)` and evaluates status via `evaluate_rule37a_status(...)`. | Only issues reversal warning if `r37a_res["is_supplier_default"] == True`. Since `UNKNOWN`, `DATA_UNAVAILABLE`, and `PENDING` set `is_supplier_default=False`, no false warnings or automated reversals are executed. | **VERIFIED FAIL-CLOSED** |

---

## 3. Summary of Caller Audit Findings

1. **Eradication of Boolean Conversion Leakage:** No caller in the entire codebase can convert an `UNKNOWN` evidence state into an active supplier default.
2. **Deterministic Provenance Verification:** Both `check_gst_deadlines` and `itc_trace_service` strictly pass resolved verification timestamps into `evaluate_rule37a_status`.
3. **Fail-Closed Guarantees:** Absence of evidence, stale evidence (>30 days), period mismatch, and GSTIN mismatch consistently produce safe, non-reversal behavior across all calling code paths.
