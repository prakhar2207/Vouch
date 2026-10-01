# Protocol Specification: Compensating Operations

**Version:** 1.0.0
**Phase:** 5 (Resolution Layer)

## Abstract
The Compensating Operations model guarantees that the original canonical transaction is never mutated. When offline semantic divergence occurs (e.g., a buyer rejects 2 out of 10 shipped items), the protocol evaluates the semantic delta and generates a deterministic, mathematically balanced "Compensating Operation."

## Deterministic Derivation Formula
When semantic divergence $\Delta$ is detected:
`Correction = F(Δ, TransactionHistory, AccountingRules)`

Because $F(\Delta)$ is deterministic, it does not matter if Replica A or Replica B discovers the discrepancy first. Both will generate the exact same logical compensating operation.

## Example Workflows

### 1. Item Rejection
* **User Action:** Buyer marks 2 items of SKU `IP17P` as damaged.
* **Semantic Delta (Δ):** `-2 units`
* **Compensating Engine:** 
  1. Identifies the original unit price, discount, and tax tier.
  2. Calculates the proportional taxable reduction.
  3. Calculates the proportional tax reduction.
  4. Generates an `ITEM_REJECTED` operation.
* **Accounting Effect:** Dr Sales Return (Taxable), Dr Output Tax, Cr Accounts Receivable.

### 2. Price Adjustment (Downward)
* **User Action:** Seller realizes they overcharged by ₹500 on an item and issues an adjustment.
* **Compensating Engine:** Generates a `PRICE_ADJUSTED` operation containing the negative delta.
* **Accounting Effect:** Mathematically equivalent to an isolated Credit Note against that specific line item.

## Immutability Guarantee
Because every compensation is balanced in isolation, if a compensation is later revoked (e.g. the buyer realizes the items weren't damaged), the protocol issues a *new* compensating operation reversing the prior compensation. History is strictly append-only.
