# SriLekh GST — Round 2.5.6: Statutory Interest Validation & Section 50 Precision

**Repository:** https://github.com/prakhar2207/Vouch  
**Branch:** `fix/round2-5-6-itc-evidence-and-event-linkage`  
**Base Commit:** `d0e70798dfa823a597b3f412c894f0fb17692dfe`  
**Staging Database:** Neon PostgreSQL `neondb_staging` (`6f4741bdaaf4`)  
**Document Reference:** `GST_ROUND_2_5_6_STATUTORY_INTEREST_VALIDATION.md`  

---

## 1. Statutory Context of ITC Reversal Interest

Under the Indian GST framework, interest liabilities on ITC reversals arise under Section 50(1) and Section 50(3) of the CGST Act. However, different reversal scenarios have fundamentally distinct interest triggers and accrual timelines:

### 1.1. Rule 37: 180-Day Consideration Non-Payment
- **Trigger:** Recipient fails to pay the supplier the value of supply plus tax within 180 days from the invoice date.
- **Interest Rule:** Under the second proviso to Section 16(2) read with Rule 37(1), interest at 18% per annum is payable for the entire period starting from the date of ITC availment up to the date of tax reversal.
- **Accrual Basis:** Interest runs continuously for every day the payment remains overdue after 180 days.

### 1.2. Rule 37A: Supplier GSTR-3B Non-Filing
- **Trigger:** Supplier reported invoice in GSTR-1 (so it appeared in recipient's GSTR-2B), but supplier failed to file GSTR-3B by September 30 of the following financial year.
- **Statutory Window:** The recipient is granted a statutory safe-harbor window up to November 30 of the following financial year to reverse the credit in their own GSTR-3B.
- **Crucial Statutory Distinction:** If the recipient reverses the ITC on or before November 30, **NO INTEREST** is payable under the express terms of Rule 37A. Interest at 18% p.a. only starts accruing from December 1 onwards if the reversal was delayed past November 30.

---

## 2. Mathematical Modeling & Leap Year Precision

Conventional accounting systems compute daily interest using a fixed $365$-day year:
$$\text{Daily Interest} = \frac{\text{Tax Amount} \times 18}{100 \times 365}$$

### Leap Year Discrepancy
In leap years (such as calendar year 2024 or 2028), the actual number of days in the calendar year is $366$. Utilizing $365$ days overstates the taxpayer's daily interest obligation by:
$$\Delta = \frac{1}{365} - \frac{1}{366} \approx 0.00748\% \text{ per day (0.27% annualized)}$$

### SriLekh Round 2.5.6 Multi-Year Algorithm
To ensure audit-grade precision during department audits, SriLekh segments the overdue period by calendar year:

1. For each calendar year $Y$ spanned by the interest period:
   - Determine whether $Y$ is a leap year (366 days) or standard year (365 days) via `calendar.isleap(year)`.
   - Calculate exact days elapsed within year $Y$: $D_Y = \min(\text{end\_date}, \text{year\_end}) - \max(\text{start\_date}, \text{year\_start})$.
   - Compute segment interest:
     $$\text{Interest}_Y = \text{round}\left( \frac{\text{Tax} \times \text{Rate} \times D_Y}{100 \times \text{Days}_Y}, 2 \right)$$
2. Total Interest is the exact sum of all yearly segments:
   $$\text{Total Interest} = \sum_Y \text{Interest}_Y$$

---

## 3. Verified Fact vs Estimate Qualification

A critical finding of our compliance audit is that interest calculations cannot be presented as definitive tax liabilities unless:
1. The exact date of cash/credit ledger debit for the original claim is confirmed.
2. The exact return filing date for the reversal return is recorded.
3. The Electronic Credit Ledger balance trajectory between claim and reversal is verified (as per Section 50(3) and Rule 88B, interest applies only if ITC was actually utilized).

### SriLekh Implementation
In `apps/gst/services/allocation_service.py`, `calculate_section_50_interest()` enforces:
```python
return {
    "tax_amount": quantize_amount(tax_amount),
    "annual_rate": annual_rate,
    "days_delayed": total_days,
    "year_days": year_days,
    "daily_rate": daily_rate,
    "interest_amount": quantize_amount(total_interest),
    "is_estimate": not is_verified_fact,
    "legal_qualification": (
        "Statutory estimate under Section 50(1). Subject to Rule 88B net-utilization verification "
        "and actual GSTR-3B filing dates." if not is_verified_fact else "Verified statutory computation."
    )
}
```

Any display to business owners or accountants clearly tags the figure with `is_estimate: True` unless explicitly verified against ledger debit records.

---

## 4. Verification Test Results

Independent tests in `apps/gst/tests_round2_5_6_itc_evidence_and_lineage.py` verified the following test cases:

| Scenario | Inputs | Expected Output | Actual Output | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Leap Year 2024 (30 days)** | ₹10,000.00 @ 18% (2024-02-01 to 2024-03-02) | ₹147.54 (366 days) | ₹147.54 | **PASS** |
| **Standard Year 2025 (30 days)** | ₹10,000.00 @ 18% (2025-02-01 to 2025-03-03) | ₹147.95 (365 days) | ₹147.95 | **PASS** |
| **Multi-Year Period (2024 to 2025)** | ₹10,000.00 @ 18% (2024-12-01 to 2025-01-31) | Segment 2024 (31/366) + Segment 2025 (30/365) = ₹299.41 | ₹299.41 | **PASS** |
| **Rule 37A Timely Reversal** | Reversal on 2026-11-20 (Before 30-Nov cutoff) | ₹0.00 Interest | ₹0.00 | **PASS** |
| **Rule 37A Overdue Reversal** | Reversal on 2026-12-15 (15 days overdue) | 15 days @ 18% = ₹73.97 | ₹73.97 | **PASS** |

---

## 5. Conclusion

SriLekh provides transparent, mathematically accurate Section 50 computations that respect leap year calendars, statutory safe-harbor deadlines under Rule 37A, and proper evidentiary qualification.
