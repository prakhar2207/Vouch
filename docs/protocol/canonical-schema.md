# Protocol Specification: Canonical Transaction Model

**Version:** 1.0.0
**Phase:** 1 (Data Representation Layer)

## Abstract
The Canonical Transaction Model represents a business event (Sale, Purchase, Payment, etc.) independently of any specific accounting software (Vouch, Tally, Zoho). It serves as the deterministic foundation for the Distributed Accounting Convergence Protocol. 

Foreign payloads must be semantically normalized into this exact structure before they can generate `AccountingOperations` or enter the DE-CRDT merge engine.

## Conceptual Schema (JSON)

```json
{
  "protocol_version": "1.0",
  "transaction_id": "TX-9A8B7C6D5E",
  "transaction_type": "SALES_INVOICE",
  "state_version": 1,
  "issued_at": "2026-10-01T10:00:00Z",
  "expires_at": "2026-10-31T23:59:59Z",
  
  "source_entity": {
    "identity_type": "GSTIN",
    "identity_value": "29ABCDE1234F1Z5",
    "name": "Supplier Corp Ltd",
    "state_code": "29"
  },
  
  "destination_entity": {
    "identity_type": "GSTIN",
    "identity_value": "27XYZAB9876C1Z2",
    "name": "Buyer Enterprises",
    "state_code": "27"
  },
  
  "items": [
    {
      "line_id": "L-001",
      "sku": "IP17P-256",
      "name": "iPhone 17 Pro 256GB",
      "hsn_code": "851712",
      "quantity": 10.0,
      "unit": "PCS",
      "unit_price": 100000.00,
      "discount_amount": 0.00,
      "taxable_amount": 1000000.00,
      "tax_rate_percent": 18.0
    }
  ],
  
  "tax_summary": {
    "cgst_amount": 0.00,
    "sgst_amount": 0.00,
    "igst_amount": 180000.00,
    "cess_amount": 0.00
  },
  
  "totals": {
    "subtotal": 1000000.00,
    "total_tax": 180000.00,
    "shipping_charges": 0.00,
    "total_discount": 0.00,
    "grand_total": 1180000.00
  },
  
  "references": [
    {
      "ref_type": "PO",
      "ref_id": "PO-2026-99"
    }
  ],
  
  "causal_dependencies": [],

  "cryptography": {
    "signature_algorithm": "Ed25519",
    "public_key_id": "KEY-SELLER-01",
    "payload_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "signature": "..."
  }
}
```

## Schema Enforcements & Invariants
1. **Mathematical Integrity:** `totals.grand_total` MUST strictly equal `totals.subtotal` + `totals.total_tax` + `totals.shipping_charges` - `totals.total_discount`.
2. **Tax Integrity:** The sum of `tax_summary` fields MUST equal `totals.total_tax`.
3. **Causality:** If `transaction_type` is `CREDIT_NOTE` or `DEBIT_NOTE`, `causal_dependencies` MUST contain the `transaction_id` of the original invoice.
4. **Immutability:** Once a Canonical Transaction is converted into an `AccountingOperation` and enters the CRDT graph, its core fields cannot be mutated. Any semantic changes require generating a *new* Compensating Operation referencing this `transaction_id`.
