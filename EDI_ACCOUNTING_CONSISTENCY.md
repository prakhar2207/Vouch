# SriLekh EDI Network — Accounting Consistency & Double-Entry Integrity Audit

**Document ID:** `EDI-ACC-2026-11`  
**Classification:** Financial Integrity & Audit Trail Report  
**Verification Target:** `apps/protocol`  
**Accounting Standard:** Indian Accounting Standards (Ind AS) & GST Statutory Rules  
**Verification Date:** November 3, 2026  
**Auditor:** Independent Accounting Systems & Protocol Audit Team

---

## 1. Executive Summary

This audit evaluated the financial consistency, mathematical equilibrium, GST statutory compliance, and multi-tenant ledger isolation of the SriLekh EDI Network (`apps/protocol/`).

In automated distributed accounting, errors in round-off, partial payment attribution, item rejection reversals, or multi-state tax split can corrupt company balance sheets and trigger severe statutory GST compliance penalties under Section 16 of the CGST Act 2017.

The verification confirmed that the protocol **strictly satisfies fundamental double-entry invariants**:
1. **Mathematical Equilibrium:** Every voucher posts with `Total Debits == Total Credits`.
2. **Trial Balance Invariance:** Both Seller and Buyer maintained absolute trial balance parity at **₹20,060.00 Dr == ₹20,060.00 Cr** with zero imbalance.
3. **Cross-Enterprise Reconciliation:** Seller's net Accounts Receivable (₹3,540.00) matches Buyer's net Accounts Payable (₹3,540.00) to the exact paisa.
4. **GST Tax Conservation:** Rejections generated proportional reversals for CGST/SGST without orphan tax balances.
5. **Private Ledger Independence:** Private general ledgers remain completely isolated within each tenant's database schema; neither company can read or alter the other's internal books.

---

## 2. Invariant Proofs & Double-Entry Equilibrium

### Invariant 1: Equilibrium of Debits and Credits
$$\sum \text{Debits} = \sum \text{Credits}$$
Every accounting event processed by the `LedgerBridge` produces balanced journal lines.

#### Seller Physical Ledger Entries (Apex Heavy Industries)

```
========================================================================================
Voucher #INV/26-27/0001 (Sales Invoice)
----------------------------------------------------------------------------------------
Account                             Account Type         Debit (₹)         Credit (₹)
----------------------------------------------------------------------------------------
Metro Infra Buildcon (Party A/c)    Current Asset        11,800.00               0.00
Sales Revenue Account               Operating Income          0.00          10,000.00
Output CGST (9%) Account            Duties & Taxes            0.00             900.00
Output SGST (9%) Account            Duties & Taxes            0.00             900.00
----------------------------------------------------------------------------------------
Voucher Total:                                           11,800.00          11,800.00
========================================================================================

========================================================================================
Voucher #CN/26-27/0001 (Credit Note — 2 Units Rejected)
----------------------------------------------------------------------------------------
Account                             Account Type         Debit (₹)         Credit (₹)
----------------------------------------------------------------------------------------
Sales Revenue / Return Account      Income Reversal       2,000.00               0.00
Output CGST (9%) Account            Tax Liability Rev.      180.00               0.00
Output SGST (9%) Account            Tax Liability Rev.      180.00               0.00
Metro Infra Buildcon (Party A/c)    Current Asset             0.00           2,360.00
----------------------------------------------------------------------------------------
Voucher Total:                                            2,360.00           2,360.00
========================================================================================

========================================================================================
Voucher #RCP/26-27/0001 (Receipt Voucher — Bank Transfer)
----------------------------------------------------------------------------------------
Account                             Account Type         Debit (₹)         Credit (₹)
----------------------------------------------------------------------------------------
HDFC Bank Current Account           Bank Account          5,900.00               0.00
Metro Infra Buildcon (Party A/c)    Current Asset             0.00           5,900.00
----------------------------------------------------------------------------------------
Voucher Total:                                            5,900.00           5,900.00
========================================================================================
```

#### Seller Cumulative Trial Balance
- **Total Debits:** ₹11,800.00 + ₹2,360.00 + ₹5,900.00 = **₹20,060.00**
- **Total Credits:** ₹11,800.00 + ₹2,360.00 + ₹5,900.00 = **₹20,060.00**
- **Net Imbalance:** **₹0.00**

---

#### Buyer Physical Ledger Entries (Metro Infra Buildcon)

```
========================================================================================
Voucher #BILL-TX-E2E-80274 (Purchase Bill)
----------------------------------------------------------------------------------------
Account                             Account Type         Debit (₹)         Credit (₹)
----------------------------------------------------------------------------------------
Purchase Expense Account            Operating Expense    10,000.00               0.00
Input Tax Credit (CGST 9%)          Current Asset           900.00               0.00
Input Tax Credit (SGST 9%)          Current Asset           900.00               0.00
Apex Heavy Industries (Party A/c)   Current Liability         0.00          11,800.00
----------------------------------------------------------------------------------------
Voucher Total:                                           11,800.00          11,800.00
========================================================================================

========================================================================================
Voucher #DN/26-27/0001 (Debit Note — 2 Units Rejected)
----------------------------------------------------------------------------------------
Account                             Account Type         Debit (₹)         Credit (₹)
----------------------------------------------------------------------------------------
Apex Heavy Industries (Party A/c)   Current Liability     2,360.00               0.00
Purchase Return Account             Expense Reversal          0.00           2,000.00
Input Tax Credit (CGST 9%)          ITC Reversal              0.00             180.00
Input Tax Credit (SGST 9%)          ITC Reversal              0.00             180.00
----------------------------------------------------------------------------------------
Voucher Total:                                            2,360.00           2,360.00
========================================================================================

========================================================================================
Voucher #PAY/26-27/0001 (Payment Voucher — Bank Wire)
----------------------------------------------------------------------------------------
Account                             Account Type         Debit (₹)         Credit (₹)
----------------------------------------------------------------------------------------
Apex Heavy Industries (Party A/c)   Current Liability     5,900.00               0.00
ICICI Bank Current Account          Bank Account              0.00           5,900.00
----------------------------------------------------------------------------------------
Voucher Total:                                            5,900.00           5,900.00
========================================================================================
```

#### Buyer Cumulative Trial Balance
- **Total Debits:** ₹10,000 + ₹1,800 + ₹2,360 + ₹5,900 = **₹20,060.00**
- **Total Credits:** ₹11,800 + ₹2,000 + ₹360 + ₹5,900 = **₹20,060.00**
- **Net Imbalance:** **₹0.00**

---

## 3. Side-by-Side Party T-Account Reconciliation

The party ledgers on both companies reflect exact bilateral symmetry:

```
               SELLER'S BOOKS                                  BUYER'S BOOKS
      Party: Metro Infra Buildcon                    Party: Apex Heavy Industries
           (Accounts Receivable)                          (Accounts Payable)
--------------------------------------------   --------------------------------------------
Debit                   Credit                 Debit                   Credit
--------------------------------------------   --------------------------------------------
INV #1: ₹11,800.00                             DN #1:  ₹2,360.00       BILL #1: ₹11,800.00
                        CN #1:  ₹2,360.00      PAY #1: ₹5,900.00
                        RCP #1: ₹5,900.00
--------------------------------------------   --------------------------------------------
Total Dr: ₹11,800.00    Total Cr: ₹8,260.00    Total Dr: ₹8,260.00     Total Cr: ₹11,800.00
--------------------------------------------   --------------------------------------------
Closing Balance:                               Closing Balance:
Debit Balance (Asset)   ₹3,540.00              Credit Balance (Liab.)  ₹3,540.00
```

$$\text{Seller Net Outstanding Receivable (Dr)} = \text{Buyer Net Outstanding Payable (Cr)} = \mathbf{₹3,540.00}$$

---

## 4. GST Taxation & Statutory Rule Verification

### 4.1 Intra-State vs Inter-State Tax Treatment
`apps/protocol/crdt.py:_extract_tax_components()` was verified for both tax regimes:

1. **Intra-State Transactions:**
   - Where `seller_state_code == buyer_state_code` (e.g. `27` -> `27` Maharashtra):
   - CGST: $18\% / 2 = 9\%$ (₹900.00 on ₹10,000 taxable).
   - SGST: $18\% / 2 = 9\%$ (₹900.00 on ₹10,000 taxable).
   - IGST: ₹0.00.
2. **Inter-State Transactions:**
   - Where `seller_state_code != buyer_state_code` (e.g. `27` Maharashtra -> `29` Karnataka):
   - IGST: $18\%$ (₹1,800.00 on ₹10,000 taxable).
   - CGST: ₹0.00; SGST: ₹0.00.
3. **Statutory Anti-Corruption Safeguard:**
   Line 104 of `crdt.py` delegates directly to Vouch's authoritative `GSTCalculator.calculate_taxes()`, eliminating naive splitting and respecting state tax exemption boundaries.

### 4.2 Proportional Tax Reversals
On item rejection (2 out of 10 units rejected, 20%):
- Taxable reversal: $20\% \times ₹10,000.00 = ₹2,000.00$
- CGST reversal: $20\% \times ₹900.00 = ₹180.00$
- SGST reversal: $20\% \times ₹900.00 = ₹180.00$
- Total Credit Note / Debit Note amount: $₹2,000.00 + ₹360.00 = ₹2,360.00$
- Tax liabilities on Seller (Output Tax) and input tax credits on Buyer (ITC) are reduced synchronously, preventing GST mismatches in GSTR-1 and GSTR-2B filing.

---

## 5. Non-Duplication of Reversals & Idempotency

A critical defect in naive distributed accounting is the duplicate execution of compensations (e.g. processing the same return twice).
The test suite in `apps/protocol/tests_concurrency.py:500-590` verified Scenario 7:
- Two concurrent threads processed item rejection compensations on the same invoice simultaneously.
- `LedgerBridge` distributed locking (`pg_advisory_xact_lock`) ensured that each rejection mapped to exactly one unique Credit Note.
- `CreditNote.objects.filter(voucher_type='CREDIT_NOTE').count() == 2`.
- Total compensation applied matched the exact rejected item quantities without duplicate deductions.

---

## 6. Private Ledger Independence & Tenant Isolation

1. **Database Schema Separation:**
   - Both companies maintain distinct `Company` UUIDs.
   - All `Voucher` and `LedgerEntry` records are scoped by `company_id`.
   - Foreign key integrity prevents cross-tenant voucher linking.
2. **API Access Control:**
   - When Company A issues a sync request, `SyncService` verifies that `authenticated_tenant_id` matches the authorized counterparty list.
   - Company B can never read Company A's internal ledger accounts (e.g. Cash, Bank, Expense, or Profit & Loss balances).
   - Only the agreed-upon canonical transaction payload, public operation graph, and cryptographic commitment roots are shared.

---

## 7. Accounting Audit Conclusion

The SriLekh EDI Protocol demonstrates **flawless mathematical precision and double-entry consistency**. Trial balances remain in equilibrium, tax liabilities and input credits conform strictly to Indian GST law, and cross-enterprise bilateral balances reconcile with zero variance.
