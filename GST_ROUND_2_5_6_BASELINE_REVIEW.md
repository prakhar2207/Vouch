# SriLekh GST — Round 2.5.6: Baseline Review & Statutory Defect Audit

**Repository:** https://github.com/prakhar2207/Vouch  
**Branch:** `fix/round2-5-6-itc-evidence-and-event-linkage`  
**Base Commit:** `d0e70798dfa823a597b3f412c894f0fb17692dfe` (`fix/round2-5-5-reversal-reclaim-integrity`)  
**Base Main Commit:** `dd1a7ca226c459a7dcc2657222122409128248da`  
**Target Database:** Neon PostgreSQL `neondb_staging` (`ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`)  
**Staging Database Fingerprint:** `6f4741bdaaf4` (`is_isolated=True`)  
**Protected Production Tenant:** `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) — STRICTLY UNTOUCHED (0 queries, 0 rows)  
**Dedicated Sandbox Tenant:** `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`)  
**Audit Date:** November 20, 2026  

---

## 1. Executive Summary

Following the completion and certification of Round 2.5.5 (`d0e70798dfa823a597b3f412c894f0fb17692dfe`), an independent statutory and architectural audit was conducted on the entire Input Tax Credit (ITC) reversal, reclaim, and compliance engine.

While Round 2.5.5 successfully introduced proportional Rule 37 reversal/reclaim calculations and established basic 180-day aging, deep architectural inspection revealed six critical vulnerabilities that prevented SriLekh from meeting the statutory proof standard required for commercial deployment:

1. **GSTR-1 vs GSTR-3B Statutory Evidence Substitution (P0 Defect):**  
   The deadline monitoring engine (`check_gst_deadlines.py`, line 140) accepted `gstr2b_record.filing_date` (which strictly represents the supplier's outward GSTR-1 / IFF filing date) as proof of the supplier's GSTR-3B return filing. Under Section 16(2)(c) of the CGST Act, outward invoice disclosure in GSTR-1 does not discharge supplier tax liability; only GSTR-3B filing does.
2. **Unsafe Rule 37A Reversal Defaults (P0 Defect):**  
   The reversal allocation service permitted callers to trigger Rule 37A reversals without affirmative proof of supplier default, incorrectly treating `UNKNOWN`, `DATA_UNAVAILABLE`, or missing portal data as non-filing.
3. **Missing Reversal-to-Reclaim Event Lineage (P0 Defect):**  
   Reclaims were validated purely against aggregate ledger balances rather than linking directly to the specific qualifying reversal events that gave rise to the reclaimed credit.
4. **Payment-Event Idempotency Flaw (P0 Defect):**  
   Idempotency keys depended solely on amount and assigned period (`f"{voucher.id}:{period}:{amount}"`). In an active MSME environment where multiple legitimate installment payments of identical amounts occur within the same month (e.g. two ₹5,000 NEFT transfers), genuine payments collided or were blocked.
5. **Section 50 Interest Approximation (P1 Defect):**  
   Interest calculations utilized a static 365-day denominator across all years, producing statutory miscalculations during leap years (such as FY 2023-24 / calendar year 2024 with 366 days). Furthermore, rough projections were presented without distinguishing estimates from verified statutory facts.
6. **Section 16 False-Positive Cutoff Alerts (P1 Defect):**  
   The Section 16(4) time-bar detector evaluated only whether a voucher had an active allocation, causing legitimate unclaimable states (such as goods pending receipt or Section 17(5) blocked credits) and statutory relief provisions (Finance Act 2024 Section 16(5) & 16(6)) to be erroneously flagged as statute-barred.

---

## 2. Baseline Architecture Audit & Detailed Vulnerability Analysis

### 2.1. Defect P0-A: GSTR-1 vs GSTR-3B Statutory Evidence Substitution
- **Statutory Authority:** CGST Act 2017 § 16(2)(c), CGST Rules 2017 Rule 37A, Rule 60(7).
- **Baseline Flaw:** In `apps/gst/management/commands/check_gst_deadlines.py` (line 140):
  ```python
  # BASELINE FLAW (Round 2.5.5)
  if gstr2b_rec and gstr2b_rec.filing_date:
      supplier_filed = True
      supplier_filing_date = gstr2b_rec.filing_date
  ```
  `gstr2b_rec.filing_date` is the date when the supplier filed their outward GSTR-1 / Invoice Furnishing Facility (IFF). Auto-populated GSTR-2B generated on the 14th of the following month reflects GSTR-1 filings.
- **Statutory Consequence:** A fraudulent or defaulting supplier who uploads invoices into GSTR-1 but defaults on paying taxes via GSTR-3B would be marked as compliant. The recipient MSME would fail to reverse ITC by 30th November, exposing them to Section 50 interest penalties (18% p.a.) and audit notices under Section 73/74.

### 2.2. Defect P0-B: Unsafe Rule 37A Reversal Defaults
- **Statutory Authority:** CGST Rules 2017 Rule 37A (inserted vide Notification No. 26/2022-CT).
- **Baseline Flaw:** Callers invoking `create_rule37a_reversal_allocation()` were allowed to execute reversals when provider status was missing, empty, or `DATA_UNAVAILABLE`.
- **Statutory Consequence:** If the GST portal or GST Suvidha Provider (GSP) experienced an API outage or returned an empty response, the engine could incorrectly mark compliant suppliers as defaulting and reverse valid ITC, severely impacting recipient MSME working capital.

### 2.3. Defect P0-C: Aggregate Balance vs Explicit Event Lineage
- **Statutory Authority:** CGST Rules 2017 Rule 37(4) and Rule 37A proviso; Section 155 (Burden of Proof).
- **Baseline Flaw:** `create_rule37_reclaim_allocation()` checked:
  `existing_reclaimed + new_reclaim <= total_reversed`
  It did not associate which specific reversal allocation was being restored, nor did it track individual tax components (IGST, CGST, SGST, Cess).
- **Statutory Consequence:** In multi-period, multi-reversal scenarios (e.g. partial reversal in July, secondary reversal in August), an auditor cannot determine which reversal was cured by which payment. Reclaim of CGST/SGST could offset prior reversals of IGST without detection.

### 2.4. Defect P0-D: Amount/Period Idempotency Collisions
- **Baseline Flaw:** Idempotency key pattern:
  `idempotency_key = f"RULE37_REC:{voucher.id}:{assigned_period}:{quantize_amount(paid_amount)}"`
  And database unique constraint:
  `UniqueConstraint(fields=['company', 'voucher', 'event_type'], condition=Q(is_active=True))`
- **Business Reality:** MSMEs frequently issue multiple identical installment checks or bank transfers in the same month (e.g. ₹10,000 on 5th August, ₹10,000 on 20th August). The second genuine payment was either treated as a duplicate or triggered a DB integrity error.

### 2.5. Defect P1-A: Section 50 Interest Leap Year & Estimation Precision
- **Statutory Authority:** CGST Act § 50(1) read with Rule 37(1) & Rule 37A.
- **Baseline Flaw:** Daily interest rate computed strictly as `Decimal('18.00') / (100 * 365)`.
- **Statutory Consequence:** In calendar year 2024 (a leap year with 366 days), daily interest was overstated by 0.27%, leading to non-compliant statutory tax computations during tax authority audits.

### 2.6. Defect P1-B: Section 16 False-Positive Cutoff Warnings
- **Statutory Authority:** CGST Act § 16(2)(b), § 16(4), § 16(5), § 16(6) (Finance Act 2024).
- **Baseline Flaw:** `check_gst_deadlines.py` treated any purchase voucher lacking an active eligible allocation prior to 30th November as statute-barred under Section 16(4).
- **Statutory Consequence:** Invoices where goods were not yet received (§ 16(2)(b)), motor vehicles blocked under § 17(5), or invoices eligible for retroactive relief under Finance Act 2024 § 16(5) (FY 17-18 to 20-21) were erroneously alerted as missed claim deadlines, creating operational panic for MSME users.

---

## 3. Git Lineage & Verification Preconditions

| Metric | Required Specification | Verified Baseline Status |
| :--- | :--- | :--- |
| **Active Branch** | `fix/round2-5-6-itc-evidence-and-event-linkage` | Verified |
| **Base Commit SHA** | `d0e70798dfa823a597b3f412c894f0fb17692dfe` | Verified |
| **Main Branch Anchor** | `dd1a7ca226c459a7dcc2657222122409128248da` | Verified |
| **Target Database Engine** | Neon PostgreSQL 16 | Verified |
| **Staging DB Target** | `neondb_staging` | Verified |
| **DB Identity Fingerprint**| `6f4741bdaaf4` | Verified (`is_isolated=True`) |
| **Protected Prod Tenant** | `5d2e5dea-ff86-4871-b2af-fe1c5a05c03c` | Zero records (`count=0`) |
| **Sandbox Tenant ID** | `4e62863a-08f9-4e99-b0bd-64873acfdd33` | Active & Verified |

---

## 4. Remediation Blueprint for Round 2.5.6

To achieve complete statutory hardening, Round 2.5.6 executes:
1. **Model Architecture:**
   - Extend `GSTR2BRecord` with dedicated GSTR-3B filing attributes (`gstr3b_filing_date`, `gstr3b_filing_arn`, `gstr3b_return_period`, `gstr3b_verification_source`, `gstr3b_verified_at`).
   - Create `SupplierGSTR3BFilingRecord` to maintain an immutable log of portal/API-verified GSTR-3B filings per supplier GSTIN and return period.
   - Extend `GSTReportingAllocation` with `source_reversal`, `payment_allocation`, `payment_event_id`, and `payment_reference`.
   - Create `GSTReversalReclaimLineage` mapping every reclaim rupee directly to its originating reversal allocation across all 4 tax components (IGST, CGST, SGST, Cess).
2. **Database Constraints:**
   - Update `unique_active_allocation_per_voucher_event` to exempt both `ITC_RECLAIM` and `ITC_REVERSAL_RULE_37`, allowing multiple partial events.
   - Enforce `unique_active_reclaim_per_payment_event` on `['company', 'voucher', 'payment_event_id']`.
3. **Statutory Logic:**
   - Enforce explicit `VERIFIED_NOT_FILED` status for Rule 37A reversals; reject `UNKNOWN` or `DATA_UNAVAILABLE`.
   - Require affirmative GSTR-3B filing evidence for Rule 37A reclaims; forbid GSTR-1 date substitution.
   - Implement multi-reversal FIFO consumption and tax component equilibrium.
   - Implement leap-year precision (366/365 days) and `is_estimate` flags for Section 50 interest.
   - Implement `evaluate_section_16_status()` distinguishing 10 statutory conditions including Finance Act 2024 relief.
4. **Transparency & Explanation:**
   - Build `ITCTraceService` delivering dual views: Business Owner View (plain English, financial summary, risk level, action steps) and Professional Auditor View (statutory citations, full event trail, lineage graph).
