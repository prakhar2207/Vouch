# SriLekh GST — Round 2.5.10 Implementation Report
## Rule 37A UNKNOWN-State Fail-Closed Remediation & Main Integration Readiness

---

## 1. Executive Summary & Verification Context

- **Repository:** `prakhar2207/Vouch`
- **Base Commit:** `2e0d5f6a098c8b60eb461a2fe89f09e6700cd33a`
- **Base Branch:** `fix/round2-5-9-rule37a-evidence-resolution-hardening`
- **Working Branch:** `fix/round2-5-10-rule37a-unknown-state-guard`
- **Target Subsystem:** SriLekh GST Compliance & Reporting Engine (CGST Rules, 2017 — Rule 37A & Section 16(2)(c))
- **Mandatory Policy Conformance:**
  - **Dedicated Staging Database:** `neondb_staging` (Host: Neon AWS Pooler, Fingerprint: `6f4741bdaaf4` verified).
  - **Dedicated Sandbox Company ONLY:** `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`).
  - **Production Tenant Protection:** `Maa Annapurna Belting Store` (`5d2e5dea-fe86-4871-b2af-fe1c5a05c03c`) & Production DB `neondb` — **STRICTLY ZERO ACCESS / UNTOUCHED**.
  - **Production Deployments / Direct Merges:** **NONE (STRICTLY PROHIBITED)**.

---

## 2. Core Statutory Invariant Enforced

> **Statutory Evidence Invariant (CGST Rule 37A):**
> Missing supplier filing evidence can **NEVER** be interpreted as verified non-filing, even when the statutory default date (30th September post FY end) has passed.
> A statutory ITC reversal requires independently verified, supplier-specific, return-period-specific, affirmative evidence of non-filing.
> `UNKNOWN`, `DATA_UNAVAILABLE`, `PENDING`, `null`, and missing evidence states must always **fail closed** (`is_supplier_default = False`).
> A raw boolean (`False` / `True`) without validated evidence provenance can never establish non-filing or filing.

---

## 3. Root Cause Analysis of P0 Defect

In Round 2.5.9, when no filing records or GSTR-2B entries were present for an invoice voucher, `Rule37AEvidenceService.resolve_voucher_evidence(voucher)` returned:
```python
{
    "status": "UNKNOWN",
    "supplier_gstr3b_filed": False,
    "return_period": inv_period,
    "supplier_gstin": supp_gstin,
    "is_stale": False,
    "verification_timestamp": None,
    ...
}
```

However, in `GSTAllocationService.evaluate_rule37a_status()`, an unsafe fallback remained:
```python
clean_status = (supplier_status or 'UNKNOWN').upper()
if clean_status == 'UNKNOWN' and supplier_gstr3b_filed is not None:
    clean_status = 'VERIFIED_FILED' if supplier_gstr3b_filed else 'VERIFIED_NOT_FILED'
```

Because `supplier_gstr3b_filed` was populated with the default `False` (representing absence of confirmed filing rather than affirmative proof of default), `clean_status` was implicitly converted to `'VERIFIED_NOT_FILED'`. Consequently, once `check_date >= default_date` (30th September), the evaluator marked:
```python
is_supplier_default = True
default_reason = f"Supplier confirmed NOT FILED as of {today.strftime('%d-%m-%Y')} (past 30-Sep default date {default_date.strftime('%d-%m-%Y')})."
```
This violated the statutory invariant by manufacturing a false default and proposing an unlawful statutory reversal on compliant or uninspected taxpayers.

---

## 4. Engineering Remediations Implemented

### 4.1 Eradication of Implicit Conversion (`apps/gst/services/allocation_service.py`)
- Removed the unsafe implicit status reassignment block completely.
- Ensured that `clean_status == 'UNKNOWN'` remains `'UNKNOWN'` regardless of any passed boolean flag.
- Set `is_supplier_default = False` whenever `clean_status` is in `('UNKNOWN', 'DATA_UNAVAILABLE', 'PENDING')`.

### 4.2 Hardened `VERIFIED_NOT_FILED` Statutory Boundary (`apps/gst/services/allocation_service.py`)
In `evaluate_rule37a_status()`, explicit `VERIFIED_NOT_FILED` status must satisfy multi-point verification checks before `is_supplier_default = True` is permitted:
1. **Supplier GSTIN Validation:** `clean_supp_gstin` and `clean_inv_gstin` must both be non-empty and match exactly. Mismatch or empty converts status to `DATA_UNAVAILABLE`.
2. **Return Period Validation:** `clean_period` and `inv_period` must both be non-empty and match exactly. Mismatch or empty converts status to `DATA_UNAVAILABLE`.
3. **Staleness Flag:** `is_stale_evidence=True` immediately converts status to `DATA_UNAVAILABLE`.
4. **Verification Timestamp & Freshness:** If `verification_timestamp` is provided, the age of the verification relative to `check_date`/system clock must not exceed `freshness_threshold_days` (default 30 days) and must not be in the future. Stale timestamps convert status to `DATA_UNAVAILABLE`.

### 4.3 Fail-Closed Reclaim Qualification (`apps/gst/services/allocation_service.py`)
In `evaluate_rule37a_status()`, reclaim eligibility previously allowed `or bool(supplier_gstr3b_filed)`:
```python
# Remediation: Eliminated raw boolean fallback
supplier_has_filed = clean_status in ('VERIFIED_FILED', 'MANUALLY_CONFIRMED')
```
Statutory reclaim now strictly requires verified status provenance and cannot be triggered by an unverified boolean `True`.

### 4.4 Parameter Threading & Deadline Command Hardening (`apps/gst/management/commands/check_gst_deadlines.py`)
Updated `check_gst_deadlines.py` to forward `verification_timestamp=ev_res.get("verification_timestamp")` to `GSTAllocationService.evaluate_rule37a_status()`, ensuring portal/GSTR-2B timestamps are validated during automated cron deadline sweeps.

### 4.5 ITC Trace Service Hardening & Bug Fix (`apps/gst/services/itc_trace_service.py`)
- Threaded `verification_timestamp=ev_res.get("verification_timestamp")` into `evaluate_rule37a_status()`.
- Fixed latent bug: line 144 had omitted the assignment of `supp_status`, which previously raised a runtime `NameError: name 'supp_status' is not defined` when evaluating non-reversal trace paths. Added `supp_status = r37a_status.get("supplier_status", "UNKNOWN")`.

---

## 5. Summary of Modified & Untracked Files

| File | Status | Description |
|---|---|---|
| `apps/gst/services/allocation_service.py` | Modified | Eradicated `UNKNOWN` to `VERIFIED_NOT_FILED` conversion; hardened `VERIFIED_NOT_FILED` and reclaim validation |
| `apps/gst/management/commands/check_gst_deadlines.py` | Modified | Forwarded `verification_timestamp` into `evaluate_rule37a_status` |
| `apps/gst/services/itc_trace_service.py` | Modified | Forwarded `verification_timestamp`; fixed latent `supp_status` `NameError` |
| `apps/gst/tests_round2_5_10_rule37a_unknown_state.py` | Created | Dedicated 16-test suite covering all UNKNOWN/evidence-state scenarios |

---

## 6. Verification Status

All 16 dedicated Round 2.5.10 tests and 63 regression tests (Round 2.5.9 and Round 2.5.8) pass cleanly on `neondb_staging` (`6f4741bdaaf4`). Zero database migrations were required, and Django system check reports zero issues.
