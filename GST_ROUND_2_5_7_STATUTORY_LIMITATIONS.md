# SriLekh GST Engine — Round 2.5.7: Statutory Limitations & Section 16 Decision Matrix

**Product:** SriLekh — GST-Enabled Double-Entry Accounting SaaS for Indian MSMEs  
**Release Round:** Round 2.5.7 (Payment Event Integrity & Supplier Evidence Certification)  
**Parent Release:** Round 2.5.6 (`b3058ba7b4667c8ced89bcb9720a33997ea7e79e`)  
**Feature Branch:** `fix/round2-5-7-payment-evidence-certification`  
**Target Database:** Neon PostgreSQL `neondb_staging` (`ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`)  
**Staging Database Fingerprint:** `6f4741bdaaf4` (`is_isolated=True`)  
**Primary Sandbox Tenant:** `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`)  
**Protected Production Tenant:** `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c` — 0 records touched)

---

## 1. Statutory Decision Matrix: Section 16 & Section 17

SriLekh Round 2.5.7 formalizes a complete decision-table evaluator in `GSTAllocationService.evaluate_section_16_status()` that maps every purchase transaction into distinct, mutually exclusive statutory categories:

| Status Code | Explicit `category` | Statutory Authority | Eligible for ITC? | Action / System Behavior |
| :--- | :--- | :--- | :--- | :--- |
| `BLOCKED_SEC_17_5` | `PERMANENTLY_BLOCKED` | Section 17(5) of the CGST Act | **No** (Permanent) | Excluded from Table 4(A)(5). Reported in Table 4(B)(1) as Ineligible ITC. Cannot be reclaimed under any circumstances. |
| `RECEIPT_PENDING` | `NOT_YET_ELIGIBLE` | Section 16(2)(b) of the CGST Act | **No** (Pending) | Held in reserve. Excluded from active monthly GSTR-3B until affirmative receipt confirmation. |
| `PARTIAL_RECEIPT` | `PARTIALLY_ELIGIBLE` | First Proviso to Section 16(2) | **Proportionate** | Eligible only for the received fraction ($f$). Remaining fraction held pending subsequent delivery lots. |
| `ALREADY_CLAIMED` | `CLAIMED` | Section 16(1) of the CGST Act | **Yes** (Filed) | Availed in already filed or reported return workspace. Prevents duplicate claims. |
| `CLAIMABLE` | `ELIGIBLE` | Section 16(1) & 16(2) | **Yes** | Fully eligible for claim in active open return workspace (Table 4(A)(5)). |
| `REVERSED_RULE_37` | `REVERSED_CONDITIONAL` | Third Proviso to Section 16(2) & Rule 37 | **No** (Temporary) | Reversed in Table 4(B)(2) for non-payment within 180 days. Reclaimable in Table 4(A)(5) upon supplier payment under Rule 37(4). |
| `REVERSED_RULE_37A` | `REVERSED_CONDITIONAL` | Section 16(2)(c) & Rule 37A | **No** (Temporary) | Reversed in Table 4(B)(2) due to supplier GSTR-3B default past 30-Sep. Reclaimable under Proviso to Rule 37A when supplier files GSTR-3B. |
| `RECLAIMED` | `ELIGIBLE_CLAIMED` | Rule 37(4) / Proviso to Rule 37A | **Yes** (Restored) | Reclaimed in Table 4(A)(5) and reported in Table 4(D)(1) for audit transparency. Linked via `GSTReversalReclaimLineage`. |
| `RELIEF_SEC_16_5` | `SPECIAL_STATUTORY_EXCEPTION` | Section 16(5) (Finance Act 2024) | **Yes** (Statutory) | Special retrospective relief for FY 2017-18, 2018-19, 2019-20, and 2020-21. Deadline statutorily extended to **30th November 2021**. |
| `RELIEF_SEC_16_6` | `SPECIAL_STATUTORY_EXCEPTION` | Section 16(6) (Finance Act 2024) | **Yes** (Statutory) | Revocation relief: Eligible up to the later of the ordinary Section 16(4) deadline or **30 days** post registration revocation order. |
| `STATUTE_BARRED_SEC_16_4` | `TIME_BARRED` | Section 16(4) of the CGST Act | **No** (Lapsed) | Passed 30th November following financial year end without statutory exception. Credit permanently lapsed. |

---

## 2. Section 50(1) Statutory Interest Engine

### 2.1 Leap-Year Mathematical Precision

Under Section 50(1) of the CGST Act, interest is payable at the notified rate (currently **18% p.a.**) for every day of delay. A standard year contains 365 days, but a leap year contains 366 days. 

SriLekh Round 2.5.7 computes interest with daily calendar precision by splitting multi-year delays across annual calendar boundaries:

$$\text{Interest} = \sum_{i} \frac{P \times R \times D_i}{100 \times Y_i}$$

Where:
- $P$: Tax Amount Subject to Interest (`quantize_amount(tax_amount)`)
- $R$: Annual Statutory Rate (`18.00%`)
- $D_i$: Days of delay falling strictly within calendar year $i$
- $Y_i$: Days in calendar year $i$ ($366$ if `calendar.isleap(year)` else $365$)

#### Concrete Benchmark Comparison:
For a tax liability of ₹100,000 delayed for 100 days:
- **In Leap Year 2024 (366 days):**
  $$\text{Interest} = \frac{100000 \times 18 \times 100}{100 \times 366} = \frac{1800000}{366} = ₹4,918.03$$
- **In Standard Year 2025 (365 days):**
  $$\text{Interest} = \frac{100000 \times 18 \times 100}{100 \times 365} = \frac{1800000}{365} = ₹4,931.51$$

The ₹13.48 differential per ₹100,000 represents statutory precision that prevents audit adjustments during GST assessments.

### 2.2 Rule 37 vs Rule 37A Interest Mechanics

| Provision | Trigger Condition | Interest Safe Harbor | Interest Start Date |
| :--- | :--- | :--- | :--- |
| **Rule 37** (180-Day Non-Payment) | Supplier invoice unpaid after 180 days from invoice date. | **None** | Interest is payable under Section 50(1) from the date of initial ITC availment until the date of reversal. |
| **Rule 37A** (Supplier GSTR-3B Default) | Supplier failed to furnish GSTR-3B for invoice period by 30-Sep post FY end. | **Yes** (Reversals on or before **30th November** carry **zero interest**) | If reversed after 30th November, interest runs from **1st December** following the financial year end until the date of reversal. |

### 2.3 Estimate vs Verified Liability

The engine tags all automated interest calculations with `is_estimate`:
- Automated deadline monitoring and dashboard alerts carry `is_estimate: True` (estimate pending formal tax return filing or DRC-03 adjustment).
- User-confirmed or portal-assessed liabilities carry `is_estimate: False`.

---

## 3. Architectural Boundaries & System Limitations

SriLekh explicitly defines its technical and architectural boundaries:

1. **No Unauthenticated External Reliance:** SriLekh evaluates GST status based on verified records stored in `SupplierGSTR3BFilingRecord` and `GSTR2BRecord`. It never attempts unauthenticated live portal scraping or bypassing GST portal captcha gates.
2. **Double-Entry Immutability:** Tax allocations, reversals, and reclaims exist strictly in the reporting allocation layer (`GSTReportingAllocation`, `GSTReversalReclaimLineage`). They **NEVER** insert, mutate, or delete core accounting ledgers, journals, or vouchers. Double-entry mathematical equilibrium ($\sum \text{Debits} == \sum \text{Credits}$) is permanently preserved.
3. **No Automated Live Filing:** SriLekh prepares complete GSTR-1, GSTR-3B, and Table 4 data structures, but requires affirmative MSME user confirmation before live portal filing.
4. **Tenant Isolation:** Multi-tenant boundaries are strictly enforced via tenant-scoped unique constraints and foreign keys. Cross-tenant queries are blocked at both ORM and database schema levels.
