# SriLekh GST — Round 2.5.9 Statutory Limitations & Auditor Advisory
## Rule 37A & Section 16/17 Statutory Boundaries

---

## 1. Statutory Context & Legislative Framework

Rule 37A was inserted into the Central Goods and Services Tax Rules, 2017 via Notification No. 26/2022-Central Tax dated 26-12-2022 to prescribe the mechanism for reversal and re-claim of input tax credit (ITC) availed by a registered person where the supplier has furnished details in GSTR-1 / IFF but failed to furnish the corresponding return in FORM GSTR-3B by the 30th September following the end of the financial year in which ITC was availed.

---

## 2. Core Statutory Invariants

### 2.1 The Negative Evidence Invariant
> **Legal Principle:** Absence of evidence is not evidence of absence.
> SriLekh never infers non-filing merely because an API query returned an error, timed out, or because a taxpayer's filing records are incomplete. Under Section 155, the burden of proof for claiming ITC rests on the taxpayer, but penal or statutory reversals cannot be automated without affirmative, verified evidence of non-filing. When evidence is missing, stale (>30 days), or ambiguous, SriLekh assigns `DATA_UNAVAILABLE` and prevents automated reversals.

### 2.2 Strict Return Period Specificity
> **Legal Principle:** Compliance is period-specific under GST law.
> A supplier filing GSTR-3B for May 2024 does not discharge their tax liability for April 2024. SriLekh strictly validates 6-digit `MMYYYY` return periods against the exact invoice period. Batch statement periods (such as GSTR-2B import batch generation dates) are strictly prohibited from serving as substitutes for the supplier's actual return period.

### 2.3 GSTR-1 vs GSTR-3B Non-Equivalence
> **Legal Principle:** Section 16(2)(c) tax discharge requirement.
> GSTR-1 is merely an outward statement of supplies, not a tax payment return. The appearance of an invoice in GSTR-2A/2B only proves the supplier declared the outward supply; it does not prove payment of tax under Section 16(2)(c). SriLekh strictly rejects GSTR-1 filing dates as proof of GSTR-3B filing. Reclaim under Rule 37A proviso strictly requires verified proof of FORM GSTR-3B filing (ARN and filing date).

### 2.4 Timelines & Statutory Windows
1. **Statutory Default Date:** 30th September following the end of the financial year in which ITC was availed.
   - Any reversal executed prior to 30th September is legally premature and is blocked by SriLekh with a `ValidationError`.
2. **Statutory Reversal Window:** On or before 30th November following the end of the financial year.
   - If reversed on or before 30th November: **NO INTEREST** liability under Section 50(1).
   - If reversed after 30th November: Statutory interest applies from the date of wrongful utilization until the date of reversal.
3. **Statutory Reclaim:** Proviso to Rule 37A explicitly exempts reclaims from the time-limit bar of Section 16(4). When the supplier subsequently furnishes FORM GSTR-3B, the recipient may reclaim the reversed ITC at any time without limitation, provided prior active reversal is proven and available.

### 2.5 Section 17(5) Permanent Ineligibility
> **Legal Principle:** Blocked credits cannot be resurrected.
> Credit permanently blocked under Section 17(5) (e.g. motor vehicles, food and beverages, gifts) cannot be availed or reclaimed under the guise of Rule 37A. SriLekh enforces this block upfront.

---

## 3. Technical Boundaries & Operational Safeguards

1. **Staleness Boundary:** Negative evidence verified more than 30 days prior is automatically downgraded to `DATA_UNAVAILABLE` to ensure suppliers who recently complied are not wrongfully subjected to ITC reversal.
2. **Re-Import Handling:** Re-imported GSTR-2B statements deterministically resolve to the record with the latest verified timestamp, preventing stale snapshots from resurrecting discarded statuses.
3. **Double Reversal / Over-Reclaim Prevention:** Cryptographic lineage tracking (`GSTReversalReclaimLineage`) prevents duplicate reversals and caps total reclaim amounts to the active, un-reclaimed balance of the prior reversal.

---

## 4. Auditor & Compliance Advisory

- **Audit Trail Integrity:** All evidence hashes are cryptographically chained using SHA-256 fingerprints comprising company, voucher, GSTIN, return period, and verification timestamp.
- **Manual Adjustments:** Manual confirmations (`MANUALLY_CONFIRMED`) strictly require an explicit user reference, supporting document reference (e.g. CA certificate or tax challan CIN), and verification timestamp.
