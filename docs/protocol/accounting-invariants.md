# Protocol Specification: Accounting Invariant Engine

**Version:** 1.0.0
**Phase:** 3 (Validation Layer)

## Abstract
The Accounting Invariant Engine acts as the strict mathematical gatekeeper for the Distributed Accounting Convergence Protocol. 

Before a CRDT merge sequence can finalize and commit to the database, the resulting mathematical state MUST pass a series of deterministic invariants. A CRDT in Vouch is not simply "conflict-free"—it is **conflict-free while maintaining accounting validity.**

## Enforced Invariants

### 1. Double-Entry Invariant
Every transaction and every compensating operation must perfectly balance.
`SUM(Debits) == SUM(Credits)`

### 2. Invoice Totals Invariant
The overall header totals of a transaction must algebraically resolve.
`GrandTotal = TaxableAmount + TotalTax + ShippingCharges - TotalDiscount`

### 3. Tax Decomposition Invariant
The top-level tax metric must equal the sum of its jurisdictional components, according to Indian GST routing.
`TotalTax = CGST + SGST + IGST + Cess`

### 4. Inventory Invariant
Inventory adjustments resulting from the transaction (including rejections or returns) must be tracked deterministically.
`NetStockChange = Inbound - Outbound + Adjustments`

### 5. Causal Integrity Invariant
Every compensating operation (e.g., a quantity adjustment or rejection) MUST contain a cryptographic reference to the specific transaction and parent operation it modifies. Orphaned adjustments are strictly rejected.

## Protocol Behavior on Violation
If an offline replica produces an operation that violates these invariants (e.g., rejecting an item without crediting Accounts Payable), the `InvariantEngine` prevents the commit. The system must then mathematically derive the required `CompensatingOperation` to restore the invariant before proceeding.
