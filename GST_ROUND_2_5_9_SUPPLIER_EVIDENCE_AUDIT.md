# SriLekh GST — Round 2.5.9 Supplier Evidence Audit
## Rule 37A Statutory Source Hierarchy, Freshness & Reconciliation

---

## 1. Executive Summary

This audit evaluates the supplier filing evidence resolution mechanism in SriLekh after Round 2.5.9 hardening. The objective is to verify that the system satisfies all evidentiary burdens under Section 16(2)(c), Section 155, and Rule 37A of the CGST Rules, 2017.

---

## 2. Statutory Hierarchy of Evidence Sources

```
+-------------------------------------------------------------+
|               Invoice Voucher Evaluation                     |
+-------------------------------------------------------------+
                               |
                               v
               Resolve Exact Supplier GSTIN
               Resolve Exact Invoice Period (MMYYYY)
                               |
        +----------------------+----------------------+
        |                                             |
        v                                             v
[Primary Source]                              [Fallback Source]
SupplierGSTR3BFilingRecord                    GSTR2BRecord
- Exact Supplier GSTIN                        - Matched to Voucher
- Exact Return Period                         - Exact Supplier GSTIN
- Valid Status (FILED / NOT_FILED)            - Valid Exact GSTR-3B Period
- Verified Timestamp                          - Verified Timestamp
        |                                             |
        +----------------------+----------------------+
                               |
                               v
               Cross-Source Conflict & Staleness Engine
                               |
        +----------------------+----------------------+
        |                      |                      |
[Direct Contradiction]   [Ambiguity]            [Reconciled Evidence]
FILED vs NOT_FILED       NOT_FILED vs PENDING   Single Source / Priority
        |                      |                      |
        v                      v                      v
 DATA_UNAVAILABLE       DATA_UNAVAILABLE       Statutory Action
 (Automation Blocked)   (Manual Review)        (Reversal / Reclaim)
```

### 2.1 Primary Evidence Source: `SupplierGSTR3BFilingRecord`
- Holds authoritative portal filing status fetched directly via GSP/GSTN taxpayer API.
- Unique invariant: `UniqueConstraint(company, supplier_gstin, return_period)`.
- Reversal requires affirmative `VERIFIED_NOT_FILED` status with fresh `verified_at` timestamp.
- Reclaim requires affirmative `VERIFIED_FILED` status with non-empty `arn` and `filing_date`.

### 2.2 Fallback Evidence Source: `GSTR2BRecord`
- Utilizes recipient GSTR-2B monthly statements where supplier GSTR-3B filing indicators are present.
- Guard 1: Must be matched to the exact invoice voucher.
- Guard 2: Must match the exact supplier GSTIN.
- Guard 3: Must contain a valid 6-digit GSTR-3B return period (`gstr3b_return_period`) matching the invoice period.
- **Invariance:** Never falls back to the GSTR-2B import statement period (`import_batch.return_period`).
- Guard 4: When multiple GSTR-2B records match the same voucher (due to multiple statement imports), the record with the latest `gstr3b_verified_at` timestamp is deterministically selected.

---

## 3. Freshness, Staleness & Timestamp Preservation

### 3.1 Staleness Threshold (30 Days)
- Statutory requirement: Negative evidence (supplier non-filing) is transient, because suppliers may file returns at any time prior to statutory cut-offs.
- Invariant: Any negative evidence older than 30 days (`(now - verified_at).days > 30`) is converted to `DATA_UNAVAILABLE`. Automated reversal is strictly prohibited on stale negative evidence.

### 3.2 Elimination of Fake / Synthesized Timestamps
- In Round 2.5.8, missing timestamps were masked using `chosen["timestamp"] or timezone.now()`.
- Round 2.5.9 eliminated all timestamp synthesis:
  - If a negative record lacks `verified_at`, it resolves as `DATA_UNAVAILABLE` with `verification_timestamp=None`.
  - In `SupplierGSTR3BFilingRecord`, `verified_at` was converted from `auto_now=True` to nullable DateTime with `default=timezone.now`. Historical timestamps are never overwritten upon record updates.

### 3.3 Positive Filing Fact Immutability
- An affirmative return filing verified with ARN and filing date is an immutable historical event under Section 155.
- Once verified filed, staleness checks do not invalidate the fact of filing.
- The source verification timestamp is preserved separately from the return filing date.

---

## 4. Cross-Source Reconciliation Audit

| Scenario | Primary Source | Fallback Source | Result Status | Action Taken |
|---|---|---|---|---|
| Direct Contradiction | `VERIFIED_FILED` | `NOT_FILED` | `DATA_UNAVAILABLE` | Fails closed; reversal & reclaim blocked |
| Direct Contradiction | `VERIFIED_NOT_FILED` | `FILED` | `DATA_UNAVAILABLE` | Fails closed; reversal & reclaim blocked |
| Ambiguity | `VERIFIED_NOT_FILED` | `PENDING` | `DATA_UNAVAILABLE` | Prevents automated default; manual audit required |
| Ambiguity | `PENDING` | `VERIFIED_NOT_FILED` | `DATA_UNAVAILABLE` | Prevents automated default; manual audit required |
| Confirmed Filing | `VERIFIED_FILED` (with ARN) | `PENDING` | `VERIFIED_FILED` | Positive filing fact preserved over pending state |
| GSTR-1 Declaration Only | None | GSTR-1 date present, GSTR-3B date missing | `DATA_UNAVAILABLE` | Blocks credit assumption; tax payment unproven |
| Missing Exact Period | None | Period is blank or mismatched | `DATA_UNAVAILABLE` | Excluded from matching; prevents false defaults |

---

## 5. Multi-Tenant Isolation & Concurrency Audit

1. **Multi-Tenant Scoping:**
   - All evidence queries strictly filter by `company=voucher.company`.
   - String-normalized UUID comparisons (`str(record.company_id) == str(voucher.company_id)`) prevent type-mismatch bypasses across models.
   - Cross-company evidence (records belonging to Company B) are completely invisible to Company A.

2. **Concurrency Serialization:**
   - Handled via PostgreSQL row-level locks (`select_for_update()`) and database uniqueness constraints.
   - Tested with genuine multi-threaded connections against PostgreSQL staging.
   - Concurrent duplicate reversals: exactly 1 succeeds, 1 rejected.
   - Concurrent duplicate reclaims: exactly 1 succeeds, 1 rejected with balance exhaustion.
