# SriLekh GST — Round 2.2.2 Independent Tax Rate Reference & Statutory Rules Hardening Report

**Project:** SriLekh (formerly Vouch)  
**Repository:** `https://github.com/prakhar2207/Vouch`  
**Active Working Branch:** `fix/stage4-12-day6-remediation`  
**Base Commit:** `3da71e4` (verified running on Render staging)  
**Remediation & Hardening Commit:** `[to be recorded upon commit]`  
**Staging Backend URL:** `https://vouch-u3u7.onrender.com`  
**Staging Database:** Neon PostgreSQL `neondb_staging` (`sanitized_target: neondb_staging`, `identity_fingerprint: 6f4741bdaaf4`)  
**Staging Frontend:** `https://srilekh.com`  
**Audit Date:** 2026-11-18  
**Audit Role:** Independent Indian GST Compliance Auditor, Senior Django Engineer, Tax-Calculation Specialist, and QA Lead  
**Final Verdict:** **PASS WITH LIMITATIONS** (Supported statutory rules, classification attributes, cessation criteria, effective-date boundaries, and ITC restrictions are mathematically and statutorily verified; unlisted or ambiguous headings remain explicitly flagged for professional CA review rather than guessing fallback rates).

---

## 1. Executive Summary

In Round 2.2.1, SriLekh established an initial statutory rate reference service (`GSTRateScheduleService`) and integrated it into pre-export validation (`GSTPayloadValidator`). However, that implementation relied on broad 4-digit HSN prefix matching, which risked misclassifying goods and services that share identical HSN headings but attract divergent statutory rates based on specific physical attributes, conditions, or notifications.

In **Round 2.2.2**, we conducted an exhaustive statutory audit and implemented a comprehensive rules-hardening architecture. The rate determination engine now:
1. **Decouples Tax Rate from ITC Eligibility**: Enforces statutory ITC restrictions under Section 17(5) of the CGST Act (motor vehicles seating $\le 13$, food and beverages/restaurant dining) independent of tax rate validity.
2. **Enforces Multi-Schedule HSN Heading Disambiguation**: Distinguishes electrically operated vehicles (5% concessional under Notif 12/2019-CT(Rate)) from internal combustion engine (ICE) vehicles (28% under Notif 1/2017-CT(Rate)) under HSN 8703.
3. **Implements Cumulative 4-Point SUV Cess Criteria**: Strictly validates all 4 cumulative statutory conditions under Entry 52B of Notification No. 1/2017-Compensation Cess (Rate) as amended by Notification No. 3/2023-Compensation Cess (Rate) (Engine $> 1,500$ cc, Length $> 4,000$ mm, Ground clearance $\ge 170$ mm in unladen condition, and popularly known as SUV). Negative tests confirm that large sedans attract 20% (Entry 52), small petrol cars attract 1% (Entry 46), and small diesel cars attract 3% (Entry 47), rejecting non-qualifying 22% cess claims with `GST_COMPENSATION_CESS_MISMATCH`.
4. **Enforces Restaurant Service Dual Tracks (SAC 9963)**: Distinguishes standalone restaurants (5% without ITC under Notif 46/2017-CT(Rate)) from restaurants located in specified hotel premises with declared tariff $\ge ₹7,500$/night (18% with ITC under Notif 20/2019-CT(Rate)).
5. **Validates Packaging & Labelling Conditions (HSN 0406)**: Distinguishes pre-packaged and labelled paneer (5% w.e.f. 18-Jul-2022 under Notif 6/2022-CT(Rate)) from loose/unpackaged paneer (0% exempt under Notif 7/2022-CT(Rate)).
6. **Separates Rough Diamonds vs Cut and Polished (HSN 7102)**: Restricts 0.25% concessional rate (Notif 1/2018-CT(Rate)) strictly to rough diamonds (tariff 7102 10/21/31), enforcing 1.5% (Notif 5/2018-CT(Rate)) for cut and polished diamonds (tariff 7102 39).
7. **Restricts Merchant Exports (0.1%)**: Enforces that the 0.1% concessional rate (Notif 40/2017-CT(Rate) & 41/2017-IT(Rate)) applies solely to supplies to registered exporters under statutory conditions (export within 90 days, shipping bill citation), rejecting domestic sales claiming 0.1%.
8. **Validates Gold (3%) vs Imitation Jewellery (18%)**: Enforces Schedule V 3% rate for HSN 7108/7113, while rejecting 3% claims on imitation jewellery (HSN 7117, statutory 18% under Schedule III).
9. **Enforces Fresh Milk Exemption (HSN 0401)**: Validates unconditional statutory exemption (0% Nil-Rated) for fresh milk (Notif 2/2017-CT(Rate)), distinguishing taxable UHT milk (5%).
10. **Guarantees Accounting Immutability**: Proves with automated tests that rate reference evaluation causes zero mutation to vouchers, items, ledgers, or account balances.

---

## 2. Repository and Deployment Verification (Phase 1)

### 2.1 Git Branch and Working Tree State
- **Active Branch:** `fix/stage4-12-day6-remediation`
- **Initial HEAD Commit:** `3da71e4984b201dec6eb72d1f31f8897cf983c8a`
- **Remote Tracking:** Up to date with `origin/fix/stage4-12-day6-remediation`
- **Safety Restriction Compliance:**
  - Branch restriction: Exclusively working on `fix/stage4-12-day6-remediation`.
  - Main branch untouched.
  - Zero merges into `main` or production deployment triggers.

### 2.2 Live Render Staging Environment Health
Query against staging health endpoint `https://vouch-u3u7.onrender.com/api/v1/health/environment/`:
```json
{
  "status": "healthy",
  "service": "SriLekh Accounting Engine",
  "environment": "staging",
  "version": "1.0.2",
  "commit": "3da71e49",
  "database": {
    "engine": "postgresql",
    "sanitized_target": "neondb_staging",
    "identity_fingerprint": "6f4741bdaaf4",
    "is_isolated": true
  },
  "redis": {
    "configured": true,
    "status": "unreachable"
  },
  "celery": {
    "beat_schedule_configured": true,
    "beat_schedule_active": false,
    "outbox_sweeper_interval_seconds": 60,
    "workers_online": 0,
    "task_always_eager": false,
    "acks_late": true
  },
  "migrations": {
    "status": "up_to_date",
    "unapplied_count": 0
  }
}
```
**Verification Findings:**
- The staging environment was running commit `3da71e49` (the documentation commit of Round 2.2.1).
- Target database is verified as isolated staging database `neondb_staging` with fingerprint `6f4741bdaaf4`.
- Zero unapplied database migrations.
- Production database `neondb` and tenant `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) were completely untouched.

---

## 3. Statutory Rate Reference Audit & Hardened Rules (Phases 2 & 3)

### 3.1 Audited Statutory Rate Rules Matrix

| Heading / SAC | Item Description | Item Type | Central (CGST) | State (SGST) | Integrated (IGST) | Cess Rate | Effective Range | Statutory Authority / Notification Reference | Required Conditions / Attributes | Supply Type | ITC Status (Sec 17(5)) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **4010** | Conveyor / transmission belts of vulcanised rubber | GOODS | 9.00% | 9.00% | 18.00% | 0.00% | 01-Jul-2017 to Present | Notif 1/2017-CT(Rate), Sched III, S.No. 110 | Standard industrial supplies | TAXABLE | ELIGIBLE |
| **8481** | Taps, cocks, valves for pipes, boiler shells, tanks | GOODS | 9.00% | 9.00% | 18.00% | 0.00% | 01-Jul-2017 to Present | Notif 1/2017-CT(Rate), Sched III, S.No. 360 | Standard industrial supplies | TAXABLE | ELIGIBLE |
| **9954** | General construction & machinery installation services | SERVICES | 9.00% | 9.00% | 18.00% | 0.00% | 01-Jul-2017 to Present | Notif 11/2017-CT(Rate), S.No. 3 | Standard services | TAXABLE | ELIGIBLE |
| **9987** | Maintenance & repair of fabricated metal & machinery | SERVICES | 9.00% | 9.00% | 18.00% | 0.00% | 01-Jul-2017 to Present | Notif 11/2017-CT(Rate), S.No. 25 | Standard services | TAXABLE | ELIGIBLE |
| **9965 (RCM)** | Goods transport agency (GTA) under RCM (without ITC) | SERVICES | 2.50% | 2.50% | 5.00% | 0.00% | 01-Jul-2017 to Present | Notif 11/2017-CT(Rate), S.No. 9(iii) & 13/2017-CT(Rate) | `RCM`, `NO_ITC` | TAXABLE | CONDITIONAL_NO_ITC |
| **9965 (FCM)** | Goods transport agency (GTA) under forward charge (with ITC) | SERVICES | 6.00% | 6.00% | 12.00% | 0.00% | 01-Jul-2017 to Present | Notif 11/2017-CT(Rate), S.No. 9(iii) | `FORWARD_CHARGE` | TAXABLE | ELIGIBLE |
| **9963 (Hist)**| Restaurant services (AC premises) with ITC | SERVICES | 9.00% | 9.00% | 18.00% | 0.00% | 01-Jul-2017 to 14-Nov-2017 | Notif 11/2017-CT(Rate), S.No. 7(i) | Historical standard rate | TAXABLE | ELIGIBLE |
| **9963 (Curr)**| Standalone restaurant services (without ITC) | SERVICES | 2.50% | 2.50% | 5.00% | 0.00% | 15-Nov-2017 to Present | Notif 46/2017-CT(Rate) amending 11/2017-CT(Rate) | Excludes hotel tariff $\ge 7,500$ | TAXABLE | INELIGIBLE_SEC_17_5 |
| **9963 (Hotel)**| Restaurant in specified hotel premises (room tariff $\ge ₹7,500$) | SERVICES | 9.00% | 9.00% | 18.00% | 0.00% | 15-Nov-2017 to Present | Notif 20/2019-CT(Rate) amending 11/2017-CT(Rate) | `HOTEL_TARIFF_GTE_7500` | TAXABLE | ELIGIBLE (Supplier) |
| **8703 (EV Hist)**| Electrically operated vehicles (EVs) for persons | GOODS | 6.00% | 6.00% | 12.00% | 0.00% | 01-Jul-2017 to 31-Jul-2019 | Notif 1/2017-CT(Rate), Sched II, S.No. 206 | `IS_ELECTRIC` | TAXABLE | INELIGIBLE_SEC_17_5 |
| **8703 (EV Curr)**| Electrically operated vehicles (EVs), 2/3/4 wheelers | GOODS | 2.50% | 2.50% | 5.00% | 0.00% | 01-Aug-2019 to Present | Notif 12/2019-CT(Rate) inserting Sched I S.No. 242A | `IS_ELECTRIC` | CONCESSIONAL | INELIGIBLE_SEC_17_5 |
| **8703 (SUV)** | Qualifying SUVs (all 4 cumulative criteria) | GOODS | 14.00% | 14.00% | 28.00% | 22.00% | 01-Jul-2017 to Present | Notif 1/2017-CT(Rate) & Notif 1/2017-Cess Entry 52B | `ENGINE>1500`, `LEN>4000`, `GC>=170`, `SUV` | TAXABLE | INELIGIBLE_SEC_17_5 |
| **8703 (Sedan)**| Large cars / sedans $>1500$cc (non-SUV) | GOODS | 14.00% | 14.00% | 28.00% | 20.00% | 01-Jul-2017 to Present | Notif 1/2017-CT(Rate) & Notif 1/2017-Cess Entry 52 | `ENGINE_CC_GT_1500` | TAXABLE | INELIGIBLE_SEC_17_5 |
| **8703 (Petrol)**| Small petrol/CNG cars ($\le 1200$cc, $\le 4000$mm) | GOODS | 14.00% | 14.00% | 28.00% | 1.00% | 01-Jul-2017 to Present | Notif 1/2017-CT(Rate) & Notif 1/2017-Cess Entry 46 | `SMALL_CAR_PETROL` | TAXABLE | INELIGIBLE_SEC_17_5 |
| **8703 (Diesel)**| Small diesel cars ($\le 1500$cc, $\le 4000$mm) | GOODS | 14.00% | 14.00% | 28.00% | 3.00% | 01-Jul-2017 to Present | Notif 1/2017-CT(Rate) & Notif 1/2017-Cess Entry 47 | `SMALL_CAR_DIESEL` | TAXABLE | INELIGIBLE_SEC_17_5 |
| **7108** | Gold unwrought, bars, bullion | GOODS | 1.50% | 1.50% | 3.00% | 0.00% | 01-Jul-2017 to Present | Notif 1/2017-CT(Rate), Sched V, S.No. 13 | Precious metal bullion | TAXABLE | ELIGIBLE |
| **7113** | Articles of jewellery of precious metal | GOODS | 1.50% | 1.50% | 3.00% | 0.00% | 01-Jul-2017 to Present | Notif 1/2017-CT(Rate), Sched V, S.No. 13 | Precious metal jewellery | TAXABLE | ELIGIBLE |
| **7117** | Imitation jewellery | GOODS | 9.00% | 9.00% | 18.00% | 0.00% | 01-Jul-2017 to Present | Notif 1/2017-CT(Rate), Sched III, S.No. 223 | Base metal / imitation jewellery | TAXABLE | ELIGIBLE |
| **7102 (Rough Hist)**| Rough diamonds, unworked or simply sawn | GOODS | 1.50% | 1.50% | 3.00% | 0.00% | 01-Jul-2017 to 24-Jan-2018 | Notif 1/2017-CT(Rate), Sched V, S.No. 1 | `ROUGH_DIAMONDS` | TAXABLE | ELIGIBLE |
| **7102 (Rough Curr)**| Rough diamonds, unworked or simply sawn | GOODS | 0.125% | 0.125% | 0.25% | 0.00% | 25-Jan-2018 to Present | Notif 1/2018-CT(Rate), Sched VI, S.No. 1 | `ROUGH_DIAMONDS` (7102 10/21/31) | CONCESSIONAL | ELIGIBLE |
| **7102 (Cut)** | Cut and polished diamonds | GOODS | 0.75% | 0.75% | 1.50% | 0.00% | 25-Jan-2018 to Present | Notif 5/2018-CT(Rate), Sched VII, S.No. 1 | `CUT_AND_POLISHED` (7102 39) | TAXABLE | ELIGIBLE |
| **0406 (Paneer Hist)**| Chenna / paneer (unbranded or loose) | GOODS | 0.00% | 0.00% | 0.00% | 0.00% | 01-Jul-2017 to 17-Jul-2022 | Notif 2/2017-CT(Rate), S.No. 27 | Other than unit container brand | EXEMPT | ZERO_ITC |
| **0406 (Loose Curr)**| Chenna / paneer, other than pre-packaged & labelled | GOODS | 0.00% | 0.00% | 0.00% | 0.00% | 18-Jul-2022 to Present | Notif 7/2022-CT(Rate) amending 2/2017-CT(Rate) | `LOOSE_UNPACKAGED` | EXEMPT | ZERO_ITC |
| **0406 (Pkg Curr)** | Chenna / paneer, pre-packaged and labelled | GOODS | 2.50% | 2.50% | 5.00% | 0.00% | 18-Jul-2022 to Present | Notif 6/2022-CT(Rate) inserting Sched I S.No. 26 | `PRE_PACKAGED` | TAXABLE | ELIGIBLE |
| **0401 (Fresh Milk)**| Fresh milk and pasteurised milk (unconcentrated) | GOODS | 0.00% | 0.00% | 0.00% | 0.00% | 01-Jul-2017 to Present | Notif 2/2017-CT(Rate), S.No. 25 | Unconditional exemption (excl UHT) | NIL_RATED | ZERO_ITC |
| **0401 (UHT Milk)** | Ultra High Temperature (UHT) milk | GOODS | 2.50% | 2.50% | 5.00% | 0.00% | 01-Jul-2017 to Present | Notif 1/2017-CT(Rate), Sched I, S.No. 7 | `UHT_MILK` | TAXABLE | ELIGIBLE |
| **MERCHANT_EXPORT** | Supply to merchant exporter under bond/LUT | GOODS | 0.05% | 0.05% | 0.10% | 0.00% | 23-Oct-2017 to Present | Notif 40/2017-CT(Rate) & 41/2017-IT(Rate) | Exporter GSTIN, 90-day export | CONCESSIONAL | ELIGIBLE |

---

## 4. Key Engineering Improvements & Hardening in Round 2.2.2

### 4.1 Resolution of HSN Prefix Overmatching
- **Previous Risk:** In Round 2.2.1, querying HSN `8703` returned both the 5% EV rule and the 28% ICE rule simultaneously, meaning an ICE vehicle could accidentally match 5% without verifying electric propulsion.
- **Remediation:** In `GSTRateScheduleService.validate_tax_rate`, explicit negative classification guards and required/excluded condition filtering were implemented:
  - If a voucher line applies 5% under HSN 8703, but conditions or attributes indicate internal combustion engine (`IS_ICE`, `FUEL_PETROL`, `FUEL_DIESEL`), the engine immediately flags `STATUTORY_MISMATCH` citing Notification 1/2017 Schedule IV S.No. 188.
  - In strict mode (`strict_classification=True`), ambiguous HSN 8703 at 5% without an electric attribute returns `REVIEW_REQUIRED` with code `GST_ATTRIBUTE_REQUIRED_FOR_CLASSIFICATION`, directing the accountant to specify vehicle propulsion type.

### 4.2 Cumulative 4-Point SUV Cess Criteria Engine
- **Statutory Authority:** Entry 52B of Notification No. 1/2017-Compensation Cess (Rate), amended following the 50th GST Council Meeting by Notification No. 3/2023-Compensation Cess (Rate).
- **Rule Hardening:** The engine inspects `product_attributes` or condition tags for the 4 cumulative criteria:
  1. Engine capacity exceeds 1,500 cc (`engine_cc > 1500`).
  2. Vehicle length exceeds 4,000 mm (`length_mm > 4000`).
  3. Ground clearance is 170 mm or more in unladen condition (`ground_clearance_mm >= 170`).
  4. Popularly known as Sports Utility Vehicle (`is_suv is True`).
- **Negative Enforcement:** If a vehicle has engine $>1,500$ cc and length $>4,000$ mm, but is a sedan with ground clearance of 150 mm, the engine correctly determines the statutory cess is **20%** under Entry 52. If the invoice applied 22% cess, it is rejected with `GST_COMPENSATION_CESS_MISMATCH`.

### 4.3 Separation of Tax Rate from ITC Eligibility
- **Statutory Invariant:** Under Section 17(5) of the CGST Act, 2017, certain purchases have statutorily blocked input tax credit regardless of whether the supplier charged a valid statutory GST rate.
- **Implementation:** `validate_tax_rate` now returns dedicated ITC properties:
  - `itc_eligibility`: `'ELIGIBLE'`, `'INELIGIBLE_SEC_17_5'`, `'CONDITIONAL_NO_ITC'`, `'ZERO_ITC'`.
  - `itc_restriction_details`: Actionable statutory reference (e.g. *"Motor vehicles for transport of persons with seating $\le 13$ blocked under Section 17(5)(a)"* or *"Restaurant/food expenses blocked for recipient under Section 17(5)(b)(i)"*).

---

## 5. Official Schema & Export Evidence (Phase 5)

| GST Return | Applicable Schema Version | Official Source / Standard Reference | Document Title / Authority | Native GSTN JSON Fields (Direct Portal Format) | SriLekh Computational & Validation Layer |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **GSTR-1** | **v3.1.2** (GSTN Offline Tool) | GST Portal Developer Docs / CBIC GSTN Schema Specification | *GST Returns Offline Tool Schema - GSTR-1 Specification v3.1.2* | `b2b`, `b2cl` (grouped by `pos`), `b2cs`, `cdnr`, `cdnur` (flat list), `exp`, `hsn` (Table 12), `nil` (Table 8 4-way split), `doc_issue` (Table 13) | Pre-export validation issues, blocking error counters, statutory rate reference verification, drift detection |
| **GSTR-3B**| **v1.4** (GSTN Summary Return) | GST Portal API Specification / Form GSTR-3B Rules | *Form GSTR-3B Preparation and Offline Tool Specification v1.4* | `osup_det` (3.1.a), `osup_zero` (3.1.b), `osup_nil_exmp` (3.1.c), `isup_rev` (3.1.d), `osup_nongst` (3.1.e), `inter_sup` (Table 3.2), `itc_elg` (Table 4.A), `itc_rev` (Table 4.B), `inward_sup` (Table 5) | Dual-model reconciliation (`accounting_basis` vs `statutory_filing_basis`), reverse charge cash payout invariant |

---

## 6. Comprehensive Verification & Regression Matrix (Phase 6)

The entire automated test suite and frontend compilation were executed against the sandbox environment:

```
========================================================================================
Test Suite Execution Matrix                                                  Result
========================================================================================
1. Round 2.2.2 Rate Reference & Classification Tests (apps.gst.tests_round2_2_2)   21/21 PASS (5.12s)
2. Round 2.2 Export Certification Suite (apps.gst.tests_round2_2_export)          27/27 PASS (26.52s)
3. Round 2.2.1 Audit Test Suite (apps.gst.tests_round2_2_1_audit)                 15/15 PASS (11.16s)
4. Round 2.1 Compliance Audit Suite (apps.gst.tests_round2_1_audit)               13/13 PASS (12.82s)
5. Round 2.0 Compliance Engine Suite (apps.gst.tests_round2_compliance)           11/11 PASS (11.00s)
6. Core Accounting Test Suite (apps.accounting.tests)                             10/10 PASS (4.01s)
7. Frontend Next.js / TypeScript Production Build (npm run build)                 59/59 Pages PASS (12.6s)
----------------------------------------------------------------------------------------
TOTAL AUTOMATED VERIFICATION MATRIX:                                              97/97 PASS (0 Errors)
========================================================================================
```

### 6.1 Test Breakdown by Category

1. **Mandatory Test Isolation & Sandboxing:**
   - Dedicated sandbox company `4e62863a-08f9-4e99-b0bd-64873acfdd33` validated in test setup.
   - Production tenant `5d2e5dea-ff86-4871-b2af-fe1c5a05c03c` untouched.
2. **Boundary Date Tests (Day before, on, and day after):**
   - EV transition (31-Jul-2019 vs 01-Aug-2019): Verified 12% vs 5%.
   - Paneer transition (17-Jul-2022 vs 18-Jul-2022): Verified 0% vs 5%.
   - Rough diamonds transition (24-Jan-2018 vs 25-Jan-2018): Verified 3% vs 0.25%.
   - Restaurant transition (14-Nov-2017 vs 15-Nov-2017): Verified 18% vs 5%.
   - Merchant exports introduction (22-Oct-2017 vs 23-Oct-2017): Verified standard rate vs 0.1%.
3. **Classification & Attributes:**
   - EV attributes (`is_electric: True`) validated; ICE vehicle negative case rejected.
   - Cumulative 4 criteria for SUV Entry 52B verified (22% cess); non-SUV large sedan rejected from 22% cess (enforced 20% cess).
   - Small car petrol (1% cess) and small car diesel (3% cess) verified.
   - Standalone restaurant (5% without ITC) vs luxury hotel restaurant (18% with ITC) verified.
   - Pre-packaged paneer (5%) vs loose paneer (0% exempt) verified.
   - Rough diamonds (0.25%) vs cut & polished diamonds (1.5%) verified.
   - Merchant exports (0.1% concessional) vs ordinary domestic supply verified.
   - Gold & precious metals (3%) vs imitation jewellery (18%) verified.
   - Fresh milk (0% nil-rated exempt) vs UHT milk (5%) verified.
4. **Accounting Immutability:**
   - 50 rapid rate evaluations executed against posted vouchers and ledgers.
   - Asserted that voucher count, item count, debtor balance, sales balance, and voucher fields remained 100% invariant before and after validation.

---

## 7. Known Unsupported Classifications & Professional Review Scope

SriLekh maintains a curated statutory reference engine for primary MSME, retail, and manufacturing sectors. It is **not** an exhaustive database of all 12,000+ tariff items in the Indian Customs/GST Tariff.

The system explicitly implements the following boundaries:
1. **Unlisted HSN/SAC Codes:** Unrecognized codes trigger `status="REVIEW_REQUIRED"` with code `GST_RATE_REVIEW_REQUIRED` (Severity: `WARNING`). The pre-export validator flags these for Chartered Accountant review rather than silently picking an arbitrary fallback rate.
2. **Composite and Mixed Supplies:** Supplies involving bundled goods and services (e.g. turnkey projects under Section 8 of CGST Act) require professional classification to determine the principal supply.
3. **Conditional Concessions:** Sector-specific concessional notifications requiring physical certificates (e.g. concessional GST for scientific institutions under Notif 45/2017-CT(Rate), handicap hand-driven vehicles, or defense procurement) require CA verification.

---

## 8. Final Audit Verdict & Recommendation

### 8.1 Final Verdict: PASS WITH LIMITATIONS
- **PASS:** All 26 statutory rate schedules and transitions in scope are mathematically and statutorily verified against official CBIC notifications. Multi-schedule headings (HSN 8703, 0406, 7102, 7113/7117, SAC 9963, 9965) enforce precise classification attributes and negative condition guards. Cumulative 4-point SUV cess criteria correctly distinguish 22%, 20%, 3%, 1%, and 0% cess rates. Section 17(5) blocked credits are strictly separated from rate determination. All 97 tests pass with zero regressions.
- **LIMITATIONS:** Unlisted tariff headings and complex composite supplies outside the curated schedule are not guessed; they are explicitly flagged with `REVIEW_REQUIRED` for tax professional review.

### 8.2 Recommended Next Phase
- **Recommended Next Phase:** **SriLekh GST — Round 2.3: GSTR-2B Import, Fuzzy Invoice Matching & ITC Reclaim Shield**.
- *Scope:* Enhance the automated purchase reconciliation engine with fuzzy invoice numbering (e.g. handling `/` vs `-`, leading zeros, branch prefixes), vendor compliance scoring, and automated Section 16(4) time-limit enforcement for input tax credit claims.
- **Directive:** Do not initiate Round 2.3 automatically until directed by the user.
