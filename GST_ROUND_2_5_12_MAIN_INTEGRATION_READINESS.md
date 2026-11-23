# SriLekh GST — Round 2.5.12 Main Integration Readiness
## Final Compliance Review & Pre-Merge Statutory Certification

---

### 1. Integration Scope & Evolution

Over Rounds 2.5.7 through 2.5.12, the SriLekh GST engine underwent rigorous statutory hardening to resolve every aspect of Rule 37A compliance:

- **Round 2.5.7:** Payment evidence certification & statutory limitation periods.
- **Round 2.5.8:** Evidence integrity remediation & supplier filing validation baseline.
- **Round 2.5.9:** GSTR-2B exact return-period enforcement & Section 16(2)(c) outward supply guards.
- **Round 2.5.10:** UNKNOWN-state fail-closed remediation (missing evidence must never default to non-filing).
- **Round 2.5.11:** Missing-timestamp & evidence provenance fail-closed correction (negative evidence requires non-null, fresh timestamp).
- **Round 2.5.12:** Authoritative positive filing evidence contract, reclaim authorization lifecycle, dual row-level locking, partial reclaim tracking, and cryptographic provenance.

---

### 2. Dual Invariant Statutory Symmetry

The GST engine now enforces complete mathematical and statutory symmetry between ITC Reversals and ITC Reclaims:

| Statutory Dimension | Rule 37A Reversal (Negative Lifecyle) | Rule 37A Reclaim (Positive Lifecycle) |
|:---|:---|:---|
| **Governing Law** | CGST Rules, 2017 — Rule 37A | CGST Rules, 2017 — Proviso to Rule 37A |
| **Trigger Condition** | Supplier failure to file GSTR-3B by 30th September post FY end | Supplier subsequent furnishing of GSTR-3B return |
| **Evidence Standard** | Verified non-filing evidence (`VERIFIED_NOT_FILED`) | Verified positive filing proof (`VERIFIED_FILED` / `MANUALLY_CONFIRMED`) |
| **Freshness Rule** | Strict 30-day freshness (re-verification required if stale) | Immutable historical fact (no artificial 30-day expiry once filed) |
| **Proof Requirements** | Verified portal/2B record + non-null timestamp + exact GSTIN & period | ARN + filing date + persisted DB record / documented manual reason + user |
| **Missing/Unknown Evidence** | **FAILS CLOSED** to `DATA_UNAVAILABLE` (NO reversal) | **FAILS CLOSED** to `reclaim_eligible=False` (NO reclaim) |
| **Concurrency Safeguard** | Row-level locking on voucher | Dual `select_for_update()` on voucher and source reversal |
| **Lineage Tracking** | Cryptographic hash chained to inward supply | `GSTReversalReclaimLineage` audit record linked to reversal |

---

### 3. Verification & Regression Metrics

| Test Suite | Tests Run | Result | Duration | Coverage Target |
|:---|:---:|:---:|:---:|:---|
| `tests_round2_5_12_rule37a_positive_evidence_reclaim.py` | 28 | **PASS** | 163.5s | Positive evidence, reclaim authorization, partial reclaims, concurrency |
| `tests_round2_5_11_rule37a_missing_timestamp.py` | 14 | **PASS** | 106.8s | Missing-timestamp fail-closed guards |
| `tests_round2_5_10_rule37a_unknown_state.py` | 16 | **PASS** | 124.2s | UNKNOWN-state fail-closed guards |
| **Cumulative Total** | **58** | **58/58 (100%)** | **394.5s** | Full Rule 37A Statutory Lifecycle |

- **PostgreSQL Database:** Neon staging `test_neondb_staging` (`6f4741bdaaf4`).
- **Sandbox Tenant:** Apex Belting Store (`4e62863a-08f9-4e99-b0bd-64873acfdd33`).
- **Zero Production Interaction:** Real tenant `Maa Annapurna Belting Store` (`5d2e5dea-fe86-4871-b2af-fe1c5a05c03c`) untouched.
- **Zero Schema Migrations Required:** Models and DB schema remain completely stable (`makemigrations --dry-run` reports 0 changes).

---

### 4. Controlled Deployment & Merge Guidelines

> **MANDATORY POLICY DIRECTIVE:**
> Do NOT merge into `main` or deploy to production without explicit separate authorization from the project lead.

#### Pre-Merge Verification Checklist:
- [x] All 58 statutory tests passing on PostgreSQL staging.
- [x] Database migrations verified clean (0 pending migrations).
- [x] System check reports 0 issues.
- [x] Dedicated staging tenant used exclusively for all automated verification.
- [x] Protected production tenant books completely isolated.
- [x] Implementation report, test results report, positive evidence audit, caller audit, and integration readiness reports authored.
- [x] Remote branch pushed cleanly to `origin fix/round2-5-12-rule37a-positive-evidence-reclaim-guard`.

---

### 5. Final Primary Verdict

```
========================================================================================
FINAL CERTIFICATION VERDICT:
PASS — READY FOR FINAL INTEGRATION REVIEW
========================================================================================
```
The codebase satisfies every statutory requirement under Rule 37A and Section 16(2)(c) of the CGST Act, 2017. All positive filing evidence contracts, reclaim authorizations, concurrency controls, and fail-closed invariants are certified complete and ready for integration review.
