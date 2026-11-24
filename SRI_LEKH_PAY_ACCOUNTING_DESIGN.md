# SriLekh Pay — Double-Entry Accounting Design

## 1. Accounting Invariants & Principles
SriLekh adheres to strict double-entry bookkeeping invariants:
1. **Mathematical Equilibrium**: For every voucher created by SriLekh Pay, $\sum \text{Debits} \equiv \sum \text{Credits}$.
2. **Immutable Audit Trails**: Direct modification of ledger balances is strictly prohibited. All ledger balance shifts occur strictly via posted `Voucher` documents containing discrete `LedgerEntry` rows.
3. **Audit User Invariant**: All automated and webhook-driven voucher creations must attribute an authorized user (`created_by_id`), resolved deterministically via `AccountingPostingService._resolve_audit_user`.
4. **FIFO Allocation**: When an invoice is referenced or outstanding bills exist, `PaymentAllocationService.auto_allocate_voucher` locks the invoice rows (`select_for_update`) and monotonically reduces outstanding amounts, writing audit-linked allocation records.

---

## 2. Dual-Party Cross-Company Posting Architecture

When both parties in a transaction are tenants on SriLekh, a single verified payment confirmation triggers symmetric double-entry postings across both companies' isolated books:

```
[ Payer Company Books: Apex Belting ]
Transaction Type: PAYMENT
Voucher Number: PAY/26-27/0001
Status: POSTED
-----------------------------------------------------------
Account Name                    Debit (₹)       Credit (₹)
-----------------------------------------------------------
Dr. Saksham Industrial Belts    12,000.00            -
Cr. Apex Current Bank Account       -            12,000.00
-----------------------------------------------------------
Total                           12,000.00        12,000.00

           <---> Network Confirmation (UTR: 411223344556) <--->

[ Recipient Company Books: Saksham Belts ]
Transaction Type: RECEIPT
Voucher Number: RCP/26-27/0001
Status: POSTED
-----------------------------------------------------------
Account Name                    Debit (₹)       Credit (₹)
-----------------------------------------------------------
Dr. SriLekh Payment Clearing   12,000.00            -
Cr. Apex Belting Store              -            12,000.00
-----------------------------------------------------------
Total                           12,000.00        12,000.00
```

---

## 3. Provider Settlement & Gateway Fee Reconciliation

When the payment gateway / bank partner settles funds into the recipient's bank account, a `JOURNAL` voucher reconciles gross sales, merchant service fees (MDR), and net bank deposits:

```
[ Recipient Company Books: Settlement Journal ]
Transaction Type: JOURNAL
Voucher Number: JRN/26-27/0001
-----------------------------------------------------------
Account Name                    Debit (₹)       Credit (₹)
-----------------------------------------------------------
Dr. Primary Bank Account        9,980.00             -
Dr. Payment Gateway Charges        20.00             -
Cr. SriLekh Payment Clearing        -            10,000.00
-----------------------------------------------------------
Total                           10,000.00        10,000.00
```

---

## 4. Suspense & Unmatched Payment Handling

If funds arrive at a merchant with an unknown payer identifier or no matching customer ledger, SriLekh Pay **never** posts unverified vouchers or corrupts customer subledgers:
1. The payment is flagged as `AccountingPostingStatus.UNMATCHED`.
2. An `UnmatchedPaymentRecord` is generated with full UTR, amount, and payer metadata.
3. The merchant accountant views the suspense item in `/pay` (Unmatched tray) and maps it to the correct customer ledger or invoice with 1 click, converting the suspense record into an authorized `RECEIPT` voucher.
