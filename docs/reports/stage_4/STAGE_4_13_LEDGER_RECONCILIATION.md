# SRI LEKH — STAGE 4.13 LEDGER RECONCILIATION & COHORT AUDIT

**Date:** 2026-11-12  
**Database Verified:** `neondb_staging` (`ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`, fingerprint `6f4741bdaaf4`)  
**Total Ledgers Audited:** `113` across all `5` synthetic MSME pilot tenants

---

## 1. Root Cause Analysis

Two distinct causes produced ledger balance drift in `neondb_staging`:

1. **Reversed-Voucher Filter Inconsistency (Root Application Bug):**
   - `VoucherService.create_reversal_voucher()` preserves `LedgerEntry` rows on the original voucher (whose status changes to `'REVERSED'`) and posts offsetting entries on the `REV-*` counter-voucher (`status='POSTED'`).
   - Authoritative accounting totals MUST filter `voucher__status__in=EffectiveVoucherService.ACCOUNTING_STATUSES` (`('POSTED', 'REVERSED', 'CORRECTED')`).
   - Four components previously filtered `voucher__status='POSTED'` only, omitting the original `'REVERSED'` entries while still counting the `REV-*` counter entries:
     - [apps/accounting/services/report_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/report_service.py) (`ReportService.generate_trial_balance` — and when invoked with `auto_reconcile=True`, it overwrote Alpha's cached balances with wrong `POSTED`-only sums, creating the `-Rs 8,260` Saksham and `-Rs 7,000` Domestic Sales drift!)
     - [apps/accounting/services/period_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/period_service.py)
     - [apps/accounting/period_views.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/period_views.py) (`PeriodLedgerStatementAPIView`)
     - [apps/accounting/services/sales_service.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/sales_service.py)
   - *Note on `Staging Beta Engineering Supplies Ltd`:* `ICICI Bank Staging` (`-12000.00`) and `Interstate Dealer Gujarat (Staging Be)` (`27661.00`) already held the accurate `ACCOUNTING_STATUSES` cached balance; only `POSTED`-only Trial Balance queries falsely flagged `+/- Rs 444.00` variance before this code fix.

2. **Bypassed Voucher Posting Cache Update in Historical Stage 4.10 / 4.11 Synthetic Scripts:**
   - Stage 4.10 (`Garodia Bearing & Power Transmission`, `CN/26-27/0003`) and Stage 4.11 (`Precision Agro Tools Pvt Ltd`, `CN/26-27/0003`) synthetic scripts saved credit-note statuses via `.save()` directly instead of `VoucherService.post_voucher()`, leaving 8 `Ledger.current_balance` caches stale pre-credit-note.

---

## 2. Controlled Atomic Reconciliation Executed on `neondb_staging`

Inside a single atomic transaction (`VoucherService.recalculate_ledger_balance`), all **12 drifted ledgers** (`4` Alpha Belts, `4` Garodia, `4` Precision Agro) were reconciled against `EffectiveVoucherService.ACCOUNTING_STATUSES`, each accompanied by a tamper-evident `'RECONCILE'` `AuditLog` entry:

| Tenant | AuditLog `seq` | Ledger Name | Ledger UUID | Before Cache (Rs) | After Cache / GL (Rs) | Variance Resolved (Rs) |
|---|---|---|---|---:|---:|---:|
| Garodia Bearing & Power Transmission | 70 | Domestic Sales 18% | `6bb9491d-3cdd-4269-9659-97a3f571a549` | 281,590.53 | 277,372.81 | -4,217.72 |
| Garodia Bearing & Power Transmission | 71 | MSME Client Phase F Stock 185600 | `6d66c256-4064-44d0-8f82-7dc92a7ca08e` | 12,442.00 | 7,465.10 | -4,976.90 |
| Garodia Bearing & Power Transmission | 72 | Output CGST | `b1daed6f-ca99-4fd2-94c0-addc43966d37` | 20,931.33 | 20,551.74 | -379.59 |
| Garodia Bearing & Power Transmission | 73 | Output SGST | `6d9a79fd-3653-4213-9eb0-df8436294a88` | 20,931.33 | 20,551.74 | -379.59 |
| Staging MSME Alpha Belts Pvt Ltd | 465 | Customer Saksham Staging | `f1035785-402d-47fb-a4bd-b4edd804fde2` | 580,398.26 | 588,658.26 | +8,260.00 |
| Staging MSME Alpha Belts Pvt Ltd | 466 | Domestic Sales | `8a0b43d6-0af0-4cef-ba96-5c08b393ee96` | 743,493.12 | 750,493.12 | +7,000.00 |
| Staging MSME Alpha Belts Pvt Ltd | 467 | Output CGST | `582f86ad-4300-45e1-86ff-82dc040e4ce4` | 14,913.76 | 15,543.76 | +630.00 |
| Staging MSME Alpha Belts Pvt Ltd | 468 | Output SGST | `6a6d4084-8ca2-4c3c-82cb-7f3a107d4af9` | 14,913.76 | 15,543.76 | +630.00 |
| Precision Agro Tools Pvt Ltd | 556 | Domestic Sales 18% | `27b3679e-62cf-42d4-b3bc-a2956f385d69` | 1,227,830.74 | 1,223,030.06 | -4,800.68 |
| Precision Agro Tools Pvt Ltd | 557 | MSME Concur Client 948000 | `f3e1e6aa-135b-4a5e-8dbd-e353e7f63c9e` | 14,162.00 | 8,497.20 | -5,664.80 |
| Precision Agro Tools Pvt Ltd | 558 | Output CGST | `d21db358-c7a7-4d3e-9236-61243dca374b` | 101,234.73 | 100,802.67 | -432.06 |
| Precision Agro Tools Pvt Ltd | 559 | Output SGST | `54175788-9b63-4ab7-8a0f-dc1769b97512` | 101,234.73 | 100,802.67 | -432.06 |

---

## 3. Post-Remediation 5-Tenant Pilot Cohort Financial Census

Verified via independent `phase_e_independent_verify.py` (`auto_reconcile=False`) across all 5 synthetic staging tenants:

| Tenant | Vouchers (POSTED / DRAFT / REV) | Trial Balance Dr == Cr (Rs) | Balance Sheet Assets == Liab+Eq (Rs) | P&L Net Profit (Rs) | Receivables / Payables Outst. (Rs) | Ledger Drifts |
|---|---:|---:|---:|---:|---:|---:|
| Garodia Bearing & Power Transmission | 63 (62 / 1 / 0) | 678,241.20 | 849,310.20 | 163,014.80 | 332,339.00 / 3,540.00 | **0** |
| Precision Agro Tools Pvt Ltd | 534 (523 / 11 / 0) | 1,694,738.70 | 1,845,954.26 | 1,116,043.40 | 1,331,995.10 / 4,725.74 | **0** |
| Shree Radhe Industrial Hardware | 60 (60 / 0 / 0) | 505,813.79 | 672,482.00 | 158,006.35 | 314,131.00 / 4,838.00 | **0** |
| Staging Beta Engineering Supplies Ltd | 46 (42 / 0 / 4) | 287,835.00 | 417,193.00 | 81,775.73 | 275,835.00 / 12,000.00 | **0** |
| Staging MSME Alpha Belts Pvt Ltd | 543 (444 / 92 / 7) | 831,328.66 | 947,429.66 | 587,016.50 | 690,149.00 / 42,102.00 | **0** |

- **Trial Balance == Period Trial Balance** across all 5 companies (`100%` exact closing debit/credit parity).
- **Double-Entry Global Invariants:** `1,131` `POSTED` vouchers, `0` zero-entry posted vouchers, `0` unbalanced posted vouchers, `0` orphaned `LedgerEntry` rows.
