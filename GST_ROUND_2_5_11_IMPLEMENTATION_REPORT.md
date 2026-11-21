# SriLekh GST — Round 2.5.11 Implementation Report
## Rule 37A Missing-Timestamp & Evidence-Provenance Fail-Closed Correction

---

## 1. Executive Summary & Verification Safeguards

- **Repository:** `prakhar2207/Vouch`
- **Base Commit:** `3c8045b39166f248032792c046fa26725cb8c4bb` (`fix/round2-5-10-rule37a-unknown-state-guard`)
- **New Working Branch:** `fix/round2-5-11-rule37a-missing-timestamp-guard`
- **Target Architecture:** SriLekh GST Compliance & Reporting Engine (CGST Rules, 2017 — Rule 37A & Section 16(2)(c))
- **Environment & Tenant Isolation Safeguards:**
  - **Database:** Dedicated Neon PostgreSQL Staging `neondb_staging` (Host: Neon Pooler, Fingerprint: `6f4741bdaaf4` verified).
  - **Sandbox Company ONLY:** `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`).
  - **Protected Production Tenant:** `Maa Annapurna Belting Store` (`5d2e5dea-fe86-4871-b2af-fe1c5a05c03c`) & Production DB `neondb` — **STRICTLY ZERO ACCESS / 100% UNTOUCHED**.
  - **Production Deployments / Direct Merges:** **NONE EXECUTED (STRICTLY PROHIBITED)**.

---

## 2. Core Invariant & Transparent Defect Attribution

> **Statutory Evidence Invariant (CGST Rule 37A):**
> Absence of evidence must NEVER be interpreted as affirmative evidence of supplier non-filing.
> A statutory ITC reversal or default determination requires independently verified, invoice-period-specific, supplier-specific, fresh negative filing evidence.
> Missing (`None`), empty, malformed, future, or stale timestamps must strictly fail closed to `DATA_UNAVAILABLE` (`is_supplier_default = False`).
> Under no circumstances may a missing verification timestamp establish a supplier default.

### 2.1 Transparent Defect Analysis (Round 2.5.10 Gap)
During independent audit of Round 2.5.10, a P0 defect was identified in `GSTAllocationService.evaluate_rule37a_status()`:
- **What Round 2.5.10 Claimed:** The Round 2.5.10 report stated that missing timestamps on negative evidence were rejected and prevented default.
- **The Actual Code Flaw:** In `apps/gst/services/allocation_service.py`, the `VERIFIED_NOT_FILED` branch was implemented as:
  ```python
  elif verification_timestamp is not None:
      ...
  elif today >= default_date:
      is_supplier_default = True
      default_reason = f"Supplier confirmed NOT FILED as of {today.strftime('%d-%m-%Y')}..."
  ```
  When `verification_timestamp` was `None`, the `if verification_timestamp is not None:` condition evaluated to `False`. Execution then dropped straight into the fallback `elif today >= default_date: is_supplier_default = True`.
- **The Failure in Historical Tests:** In `tests_round2_5_10_rule37a_unknown_state.py`, `test_r25910_12` tested `is_stale_evidence=True`, an older timestamp, and `validate_reversal_evidence()`, but never actually tested `evaluate_rule37a_status()` with `verification_timestamp=None`. Consequently, the fallback went undetected during that turn.
- **Remediation in Round 2.5.11:** We acknowledge this gap transparently. In Round 2.5.11, the missing-timestamp fallback has been completely eradicated, and dedicated regression tests now assert fail-closed rejection of missing, empty, and malformed timestamps.

---

## 3. Engineering Remediations Implemented

### 3.1 Eradication of Timestamp Fallbacks (`apps/gst/services/allocation_service.py`)
In `GSTAllocationService.evaluate_rule37a_status()`:
- Enforced mandatory verification timestamp validation for `VERIFIED_NOT_FILED`.
- If `verification_timestamp` is `None`, empty string (`""` or whitespace), or invalid type:
  - Effective status immediately transitions to `DATA_UNAVAILABLE`.
  - `is_supplier_default = False`.
  - `default_reason = 'Missing verification timestamp on supplier filing evidence. Provenance cannot be established.'`.
- Completely removed the unauthenticated fallback `elif today >= default_date: is_supplier_default = True`.

### 3.2 Robust Timestamp Parsing & Freshness Validation (`apps/gst/services/allocation_service.py`)
- Handled `datetime`, `date`, and ISO string timestamps safely.
- Timezone naive timestamps are made aware via `timezone.get_current_timezone()`.
- Future timestamps (`vt_parsed > now + timedelta(minutes=5)`) fail closed to `DATA_UNAVAILABLE`.
- Stale timestamps (`age_days > freshness_threshold_days` or `age_days < 0`) fail closed to `DATA_UNAVAILABLE`.

### 3.3 Evidence Source & Record Provenance Consistency (`apps/gst/services/allocation_service.py`)
- Evaluator now validates `evidence_source`:
  - Must belong to approved sources: `PORTAL`, `GSTN_PORTAL`, `GSTR2B`, `SUPPLIER_RECORD`, `MANUAL`.
  - Inconclusive sources (`NONE`, `CONFLICTING_SOURCES`, `AMBIGUOUS_SOURCES`) fail closed to `DATA_UNAVAILABLE`.
- Evaluator now validates supporting record:
  - If `evidence_source == 'MANUAL'`: strictly requires `evidence_document_ref`, `manual_verification_reason`, and `user`. Missing manual metadata fails closed to `DATA_UNAVAILABLE`.
  - For portal/record sources: requires active, non-stale `SupplierGSTR3BFilingRecord` or `GSTR2BRecord` matching company, GSTIN, and return period. If no record is present or resolvable, fails closed to `DATA_UNAVAILABLE`.

### 3.4 Reversal Validation Hardening (`apps/gst/services/rule37a_evidence_service.py`)
- In `Rule37AEvidenceService.validate_reversal_evidence()`:
  - Added import `timedelta`.
  - Enforced strict timestamp validation: rejects `None`, empty strings, and malformed strings with `ValidationError`.
  - Converted naive timestamps to aware datetimes.
  - Rejects future timestamps (`vt > timezone.now() + timedelta(minutes=5)`) with `ValidationError`.

### 3.5 Caller Contract Threading
- `apps/gst/management/commands/check_gst_deadlines.py`: Updated invocation of `evaluate_rule37a_status()` to forward `evidence_source`, `evidence_record`, and `evidence_document_ref` from `Rule37AEvidenceService.resolve_voucher_evidence()`.
- `apps/gst/services/itc_trace_service.py`: Forwarded `evidence_source`, `evidence_record`, and `evidence_document_ref`.

---

## 4. Summary of Modified & Created Files

| File | Status | Description |
|---|---|---|
| `apps/gst/services/allocation_service.py` | Modified | Eradicated missing-timestamp fallback; added fail-closed timestamp, source, and record provenance validation |
| `apps/gst/services/rule37a_evidence_service.py` | Modified | Added `timedelta` import; hardened `validate_reversal_evidence` timestamp parsing and future checks |
| `apps/gst/management/commands/check_gst_deadlines.py` | Modified | Forwarded resolved evidence source, record, and document ref into `evaluate_rule37a_status` |
| `apps/gst/services/itc_trace_service.py` | Modified | Forwarded resolved evidence source, record, and document ref into `evaluate_rule37a_status` |
| `apps/gst/tests_round2_5_10_rule37a_unknown_state.py` | Modified | Added Case D & E to `test_r25910_12` explicitly asserting `None` and `""` timestamps fail closed |
| `apps/gst/tests_round2_5_11_rule37a_missing_timestamp.py` | Created | Dedicated 14-scenario test suite verifying missing, malformed, future, stale timestamps and provenance |

---

## 5. Verification Status

Targeted test execution results:
- **Round 2.5.11 Dedicated Suite:** **14 / 14 PASSED** (83.4s)
- **Round 2.5.10 Directly Affected Suite:** **16 / 16 PASSED** (91.1s)
- **Round 2.5.8 Reversal Evidence Validation Suite:** **14 / 14 PASSED** (69.8s)
- **Cumulative Active Tests Executed in Round 2.5.11:** **44 / 44 PASSED (100% SUCCESS)**
- **System Check:** Identified 0 issues.
- **Migration Check:** No schema changes detected (zero migrations required).
