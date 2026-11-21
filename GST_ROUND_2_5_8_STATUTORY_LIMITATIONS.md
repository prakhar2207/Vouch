# SriLekh GST — Round 2.5.8 Statutory Limitations & Operational Boundaries

**Branch:** `fix/round2-5-8-rule37a-evidence-integrity`  
**Base Commit:** `c36e2ae547760d3023e1b80bd52d1c53493953e3`  
**Statutory Scope:** CGST Rules Rule 37A, Section 16(2)(c), Section 50(1)  
**Database Fingerprint:** `6f4741bdaaf4` (`neondb_staging`)  
**Dedicated Sandbox Company:** `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`)

---

## 1. Statutory Context & Scope

Rule 37A of the CGST Rules, 2017 establishes a structured mechanism to enforce Section 16(2)(c) tax payment requirements without unjustly depriving recipients of legitimate input tax credits. While SriLekh Round 2.5.8 hardens the algorithmic, cryptographic, and operational facets of Rule 37A evidence management, certain statutory and real-world boundaries remain intrinsic to the Goods and Services Tax architecture in India.

This document details those boundaries, operational assumptions, and governance guardrails.

---

## 2. External API & GSTN Portal Dependencies

### 2.1 Reliance on GSP / ASP / GSTN APIs
- SriLekh determines supplier filing status from two external data feeds:
  1. `SupplierGSTR3BFilingRecord`: Polled from GST portal Public Search Taxpayer / Return Status APIs via GSP.
  2. `GSTR2BRecord`: Inward auto-drafted statements downloaded from GSTN.
- **Limitation:** In the event of GST portal downtime, API gateway rate limits, or delayed statement generation by GSTN (e.g. GSTR-2B generated on 14th instead of 12th of the month), the engine receives no response.
- **Operational Guardrail:** Under Round 2.5.8, network errors and missing responses are mapped to `DATA_UNAVAILABLE`. The system will **never** presume default in the absence of evidence. Reversals are safely postponed, and an alert is logged in `GSTAuditLog`.

### 2.2 Portal Data Latency vs Verification Freshness
- GSP API caches and GST portal database replication can exhibit latencies of 12 to 48 hours following a supplier's GSTR-3B submission.
- **Limitation:** A supplier might file on 29th September, but portal APIs might continue reporting `NOT_FILED` on 30th September.
- **Operational Guardrail:** SriLekh implements the 30-day evidence freshness rule (`freshness_threshold_days = 30`). Furthermore, the statutory recipient reversal deadline is 30th November—a full 60 days after the 30th September supplier default date. Taxpayers have ample opportunity to refresh evidence before reversing.

---

## 3. Manual Verification Governance

### 3.1 Accountant Manual Confirmation (`MANUALLY_CONFIRMED`)
When automated portal integration is delayed or supplier filing occurs via special jurisdiction processes, an authorized accountant may manually confirm supplier filing.
- **Statutory Requirements:**
  - Must provide explicit documentary reference (e.g., CA Certificate, Form GST DRC-03 reference, or Treasury Challan CIN).
  - Must record the verified user ID of the authorized accountant.
  - Must record an explicit verification timestamp.
- **Limitation:** Software cannot authenticate the physical authenticity of external PDF certificates.
- **Operational Guardrail:** The system computes an immutable SHA-256 evidence hash (`evidence_hash`) binding the voucher ID, document reference, user ID, and timestamp. Any retrospective tampering with audit attributes is cryptographically detectable.

---

## 4. Section 50 Interest Calculations & Estimates

### 4.1 Daily Precision & Leap-Year Arithmetic
- Section 50(1) prescribes interest at 18% per annum for the period of delay.
- SriLekh computes interest using exact day counts:
  $$\text{Interest} = \frac{\text{Tax Amount} \times 18 \times \text{Days of Delay}}{100 \times \text{Days in Year (365 or 366)}}$$
- Reversals executed on or before 30th November carry **zero interest** under the Rule 37A safe harbor.

### 4.2 Legal Nature of Computed Interest
- **Statutory Limitation:** In *Refex Industries Ltd. vs ACCT*, the High Court held that interest under Section 50(1) is only payable on that portion of the tax paid through the electronic cash ledger. If the taxpayer had sufficient unutilized electronic credit ledger balances throughout the delay period, statutory interest liability may be mitigated under Section 50(3).
- **System Design:** The interest figure calculated by `calculate_section_50_interest` is marked with `is_estimate: True`. It serves as a statutory compliance provision estimate, not an inflexible tax assessment.

---

## 5. Permanently Ineligible Credit: Section 17(5) Boundary

- Inward supplies falling under Section 17(5) (e.g. motor vehicles for non-specified purposes, food and beverages, club memberships) are permanently barred from credit.
- **Statutory Guardrail:** In Round 2.5.8, Section 17(5) blocked credits are permanently barred from Rule 37 and Rule 37A reclaims. Even if the supplier subsequently files GSTR-3B and discharges tax, a Section 17(5) invoice cannot be reclaimed. Any attempt to reclaim blocked credit raises an immediate `ValidationError`.

---

## 6. Recommendations for Production Operations

1. **Scheduled Freshness Sync:** Run `check_gst_deadlines` daily between 1st October and 30th November. Re-poll any supplier records with status `DATA_UNAVAILABLE` or `PENDING`.
2. **Pre-Reversal Supplier Notices:** Automated supplier notifications should be dispatched on 15th September alerting non-filing vendors of impending Rule 37A recipient reversals.
3. **Database Maintenance:** The composite index on `(company_id, evidence_supplier_gstin, evidence_return_period)` must be monitored for query optimization as volume scales.
