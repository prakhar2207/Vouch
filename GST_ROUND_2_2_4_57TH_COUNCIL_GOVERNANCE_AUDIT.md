# SriLekh GST — Round 2.2.4: 57th Council Directives, CBIC Clarifications & Compliance Register Audit Report

**Auditor:** Independent Statutory GST Compliance Auditor, Tax Engine Architect, Senior Django Engineer & QA Lead  
**Audit Date:** 18 November 2026  
**Repository:** `https://github.com/prakhar2207/Vouch`  
**Active Working Branch:** `fix/stage4-12-day6-remediation`  
**Base Commit:** `6610237` (deployed as `66102371` on Render staging)  
**Staging Backend:** `https://vouch-u3u7.onrender.com`  
**Staging Database:** Neon PostgreSQL `neondb_staging` (`fingerprint: 6f4741bdaaf4`, `is_isolated: true`)  
**Dedicated Sandbox Tenant:** `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`)  
**Protected Production Tenant:** `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) — *Zero Access / Protected Invariant Maintained*  
**Final Audit Verdict:** **PASS WITH LIMITATIONS**

---

## 1. Executive Summary

Following Round 2.2.3 (Current-Law Reconciliation & Effective-Date Remediation), SriLekh GST Round 2.2.4 completes the statutory governance review by reconciling the statutory change register, classification rules, ITC eligibility filters, and administrative guidance against official CBIC releases following the 57th GST Council meeting held on 8 October 2026.

### Core Audit Findings & Actions Taken:
1. **CBIC Circular No. 265/11/2026-GST (Dated 28 October 2026):**
   - **Sublimation Paper (Heading 4809):** Affirmed standard rate of 18% (Schedule III S.No. 112). Enacted statutory rule with "as is where is" past-period regularisation: 12% applied prior to 28-Oct-2026 with `AS_IS_WHERE_IS_REGULARIZATION` is regularised as `VALID`; 12% applied on or after 28-Oct-2026 is flagged as `STATUTORY_MISMATCH` (expected 18%).
   - **Toys & Wheeled Toys (Heading 9503):** Affirmed standard rate of 12% (Schedule II S.No. 228). Enforced strict negative classification checks: general electronic components/batteries not adapted solely for toys attract 18% under Chapter 85 (`STATUTORY_MISMATCH`); video game consoles and arcade games attract 28% under heading 9504 (`STATUTORY_MISMATCH`).
   - **Used Motor Vehicles under Margin Scheme (Notification No. 8/2018-CT(Rate)):** Clarified scope of Section 17 ITC restrictions. Dealer cannot claim ITC on the purchase of the second-hand vehicle (`INELIGIBLE_MARGIN_SCHEME_VEHICLE`). However, ITC on general business inputs, repair/spare parts, and rent is fully **ELIGIBLE** under Section 16. Implemented dedicated `evaluate_margin_scheme_itc` evaluator and 0.00% compensation cess rule.
   - **Seaweed-Extract Bio-Stimulants (Heading 3101):** 5% concessional rate (Schedule I S.No. 182) is strictly conditional on registration under the *Fertiliser (Control) Order (FCO), 1985*. Unregistered bio-stimulants must be classified under heading 3808/3824 @ 18% (`STATUTORY_MISMATCH`). Missing FCO status under strict classification returns `REVIEW_REQUIRED`.

2. **CBIC Instruction No. 02/2026-GST (Dated 30 October 2026):**
   - **Administrative Safeguards:** Implemented dedicated `evaluate_administrative_guidance` method capturing:
     * Section 69 arrest restraints (prior written approval of Principal Commissioner; restricted to organized evasion exceeding statutory threshold).
     * E-Way Bill minor clerical typos (no vehicle detention or Section 129 penalty; nominal maximum ₹1,000 penalty under Section 125).
     * Show Cause Notice threshold of ₹10,000 for petty tax mismatches.
   - **Statutory Engine Invariant:** Administrative instructions are modeled as informational compliance guidance only; they do **not** alter tax rates, voucher values, or return calculations.

3. **Statutory Legal Source Taxonomy:**
   - Formalized 7 structured legal source categories: `GAZETTED_NOTIFICATION`, `STATUTORY_AMENDMENT`, `CBIC_CIRCULAR`, `CBIC_INSTRUCTION`, `GST_COUNCIL_RECOMMENDATION`, `OFFICIAL_FAQ`, `PENDING_LEGAL_ACTION`.
   - Populated complete 12-entry statutory compliance register with issuing authority, document reference, affected module, source URL, and review date.
   - Built query APIs: `get_statutory_change_register`, `get_governance_entry`, `is_legally_enforceable`.

---

## 2. Statutory Change Register Taxonomy & Current Status

| Ref ID | Issuing Authority | Legal Source | Document Reference | Category | HSN/SAC | Enactment Status | Legally Enforceable? | Affected Module | Summary |
|---|---|---|---|---|---|---|---|---|---|
| `55TH-01` | CBIC | `GAZETTED_NOTIFICATION` | Notif 01/2025-CT(Rate) | `RATE_CHANGE` | 9963 | `VERIFIED_ACTIVE` | **YES** | `RATE_ENGINE` | Specified Premises replaces declared tariff w.e.f. 01-Apr-2025 |
| `56TH-01` | CBIC | `GAZETTED_NOTIFICATION` | Notif 10/2025-CT(Rate) | `EXEMPTION` | 0406 | `VERIFIED_ACTIVE` | **YES** | `RATE_ENGINE` | Chenna/paneer reduced from 5% to 0% (Exempt) w.e.f. 22-Sep-2025 |
| `56TH-02` | CBIC | `GAZETTED_NOTIFICATION` | Notif 10/2025-CT(Rate) | `RATE_CHANGE` | 0406 | `VERIFIED_ACTIVE` | **YES** | `RATE_ENGINE` | Cheese (other than paneer) reduced from 12% to 5% w.e.f. 22-Sep-2025 |
| `56TH-03` | CBIC | `GAZETTED_NOTIFICATION` | Notif 10/2025-CT(Rate) | `EXEMPTION` | 0401 | `VERIFIED_ACTIVE` | **YES** | `RATE_ENGINE` | UHT milk (0401 50 00) reduced from 5% to 0% (Exempt) w.e.f. 22-Sep-2025 |
| `57TH-PRESS` | GST Council | `GST_COUNCIL_RECOMMENDATION` | Press Release 08-Oct-2026 | `STATUTORY_REFORM` | - | `PENDING_AMENDMENT` | **NO** | `COMPLIANCE_GUIDANCE` | 57th Council recommendations press release; advisory only |
| `57TH-01` | Parliament/MoF | `STATUTORY_AMENDMENT` | 57th Council Agenda Item 4 | `STATUTORY_REFORM` | - | `PENDING_AMENDMENT` | **NO** | `COMPLIANCE_GUIDANCE` | Decriminalization & prosecution threshold to ₹5 Cr; pending Finance Act |
| `57TH-02` | GST Council | `GST_COUNCIL_RECOMMENDATION` | 57th Council Agenda Item 6 | `COMPLIANCE` | - | `PENDING_NOTIFICATION` | **NO** | `RETURN_PREP` | Automated risk-based processing; pending CBIC notification |
| `CIR-265-4809` | CBIC | `CBIC_CIRCULAR` | Circular 265/11/2026-GST | `CLASSIFICATION_CLARIFICATION` | 4809 | `ENFORCEABLE` | **YES** | `RATE_ENGINE` | Sublimation paper 18%; past periods regularised on as-is basis |
| `CIR-265-9503` | CBIC | `CBIC_CIRCULAR` | Circular 265/11/2026-GST | `CLASSIFICATION_CLARIFICATION` | 9503 | `ENFORCEABLE` | **YES** | `CLASSIFICATION` | Toys 12%; electronic parts 18% (Ch 85); arcade games 28% (9504) |
| `CIR-265-USED-VEH` | CBIC | `CBIC_CIRCULAR` | Circular 265/11/2026-GST | `CLASSIFICATION_CLARIFICATION` | 8703 | `ENFORCEABLE` | **YES** | `ITC_ELIGIBILITY` | Margin Scheme ITC: vehicle blocked; repair spares & rent eligible |
| `CIR-265-3101` | CBIC | `CBIC_CIRCULAR` | Circular 265/11/2026-GST | `CLASSIFICATION_CLARIFICATION` | 3101 | `ENFORCEABLE` | **YES** | `RATE_ENGINE` | Bio-stimulants 5% strictly conditional on FCO 1985 registration |
| `INS-02-2026` | CBIC | `CBIC_INSTRUCTION` | Instruction 02/2026-GST | `ADMINISTRATIVE_INSTRUCTION` | - | `ADMINISTRATIVE_BINDING_ON_DEPT` | **NO (Admin Only)** | `COMPLIANCE_GUIDANCE` | Section 69 arrest restraints, E-way bill typo protections, ₹10k SCN limit |

---

## 3. Product Impact Assessment Across Engine Modules

1. **Rate Engine (`GSTRateScheduleService`):**
   - Rules 13, 14, 15, and 16 added to `STATUTORY_RULES`.
   - Sublimation paper (4809) @ 18% with historical "as is where is" regularisation condition support.
   - Used motor vehicles under margin scheme (8703) evaluated at 18% (or 12%) with 0.00% compensation cess.
   - FCO bio-stimulants evaluated at 5% (Schedule I S.No. 182).

2. **Classification Engine:**
   - Toys (9503) @ 12% strictly disqualified if flagged as `GENERAL_ELECTRONIC_COMPONENT` (attracts 18% under Chapter 85) or `ARCADE_GAME_9504` (attracts 28% under heading 9504).
   - Bio-stimulants (3101) @ 5% strictly disqualified if unregistered under FCO (`UNREGISTERED_BIO_STIMULANT` attracts 18% under heading 3808/3824).

3. **ITC Eligibility Review:**
   - Implemented `evaluate_margin_scheme_itc`: distinguishes blocked vehicle purchases from eligible repair parts and general business overheads under Section 16.
   - Accurately reports `INELIGIBLE_MARGIN_SCHEME_VEHICLE` vs `ELIGIBLE`.

4. **Return Preparation:**
   - Confirms that administrative instructions do not corrupt GSTR-1 outward supplies or GSTR-3B summary numbers.
   - Unnotified 57th Council items remain marked `PENDING_AMENDMENT` / `PENDING_NOTIFICATION`.

5. **Compliance Guidance:**
   - Implemented `evaluate_administrative_guidance` to assist MSMEs faced with procedural notices, minor E-way bill typos, or SCNs under ₹10,000 without mutating accounting balances.

---

## 4. Verification & Test Evidence

### A. New Test Suite: `apps/gst/tests_round2_2_4_council_governance.py`
- Total Tests: **21**
- Passed: **21 (100%)**
- Execution Time: **13.098s**
- Test Coverage:
  1. `test_sublimation_paper_standard_18_percent`: PASS
  2. `test_sublimation_paper_12_percent_post_circular_is_mismatch`: PASS
  3. `test_sublimation_paper_past_period_as_is_where_is_regularization`: PASS
  4. `test_sublimation_paper_past_period_without_regularization_tag`: PASS
  5. `test_toys_standard_12_percent`: PASS
  6. `test_toys_general_electronic_part_disqualification`: PASS
  7. `test_toys_arcade_game_heading_9504_disqualification`: PASS
  8. `test_used_motor_vehicles_margin_scheme_rate_and_zero_cess`: PASS
  9. `test_used_motor_vehicles_margin_scheme_cess_is_mismatch`: PASS
  10. `test_used_motor_vehicles_margin_scheme_standard_28_is_mismatch`: PASS
  11. `test_margin_scheme_itc_differentiation`: PASS
  12. `test_bio_stimulants_fco_registered_qualifies_for_5_percent`: PASS
  13. `test_bio_stimulants_unregistered_is_mismatch_attracts_18_percent`: PASS
  14. `test_bio_stimulants_strict_classification_requires_fco_attribute`: PASS
  15. `test_instruction_02_eway_bill_minor_clerical_typo`: PASS
  16. `test_instruction_02_arrest_safeguards_section_69`: PASS
  17. `test_instruction_02_scn_threshold_10k`: PASS
  18. `test_statutory_change_register_taxonomy_completeness`: PASS
  19. `test_filter_change_register_by_legal_source_and_module`: PASS
  20. `test_enforceability_checks`: PASS
  21. `test_double_entry_accounting_immutability`: PASS

### B. Full GST Regression Matrix
- Total Tests: **116**
- Passed: **116 (100%)**
- Zero Failures, Zero Errors.
- Suites Executed:
  * `apps.gst.tests_round2_2_4_council_governance` (21 tests)
  * `apps.gst.tests_round2_2_3_statutory_reconciliation` (8 tests)
  * `apps.gst.tests_round2_2_2_rate_reference` (18 tests)
  * `apps.gst.tests_round2_2_1_audit` (13 tests)
  * `apps.gst.tests_round2_2_export` (19 tests)
  * `apps.gst.tests_round2_1_audit` (19 tests)
  * `apps.gst.tests_round2_compliance` (18 tests)

---

## 5. Security & Isolation Boundaries

- **Database Isolation:** All verification scripts and test cases ran against `neondb_staging` (`fingerprint: 6f4741bdaaf4`).
- **Sandbox Tenant:** Strictly bound to `Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`).
- **Protected Tenant:** Production tenant `Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) had zero test records created, modified, or accessed.
- **Double-Entry Equilibrium:** Maintained across all ledger postings. Zero orphan entries.

---

## 6. Audit Verdict & Limitations

### Verdict: **PASS WITH LIMITATIONS**

### Explicit Limitations:
1. **Pending Parliamentary Legislation:** 57th GST Council recommendations regarding decriminalization, raising prosecution threshold from ₹2 Crore to ₹5 Crore, and statutory repeal of Section 69 arrest powers require amendment to the CGST Act via the forthcoming Union Finance Act (expected 01-Apr-2027). They remain marked `PENDING_AMENDMENT` and are not operationalized in tax calculation routines.
2. **Administrative Guidance Scope:** CBIC Instruction No. 02/2026-GST provides binding instructions to departmental field formations regarding E-way bill minor errors and ₹10,000 SCN thresholds. They are rendered as informational guidance only and do not alter tax rates or GSTR-1/3B calculations.
3. **External Transmission Boundary:** Live GST Portal transmission and GSP authentication remain strictly out-of-scope for Round 2.2.4.
