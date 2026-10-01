# Protocol Specification: EDI Handshake State Machine

**Version:** 1.0.0
**Phase:** 8 (Transport & Negotiation)

## Abstract
The legacy Vouch EDI protocol utilized a fragile `SEND -> ACCEPT` sequence. If an error occurred mid-flight, the system state became ambiguous. 

The new Distributed Accounting Convergence Protocol implements a rigorous, multi-stage state machine (inspired by the Two-Phase Commit protocol and standard cryptographic handshakes). It explicitly guarantees that neither the Buyer nor the Seller commits to an accounting change unless both endpoints agree on capabilities, cryptographic authenticity, and mathematical validity.

## The State Lifecycle

### 1. Negotiation & Security
* `DISCOVER`: Endpoints locate each other (e.g., via Dynamic QR or GSTIN lookup).
* `CAPABILITY_EXCHANGE`: Endpoints advertise supported features (e.g., Protocol Version 1.0, Ed25519 crypto, specific tax rules).
* `AUTHENTICATE`: Mutual verification of digital signatures and session nonces.

### 2. Transaction Phase
* `PROPOSE`: Initiator sends the Canonical Transaction or operations.
* `RECEIVE`: Counterparty acknowledges receipt.
* `VALIDATE`: Counterparty runs the `InvariantEngine` against the payload locally.

### 3. Consensus Phase (Two-Phase Commit variant)
* `PREPARE`: Both nodes lock the transaction, preventing concurrent offline edits.
* `READY`: Counterparty signals it is mathematically prepared to commit.
* `ACCEPT`: Counterparty formally accepts the terms (User Action / Automated Rule).
* `COMMIT`: Both nodes execute the CRDT merge and generate the `CrossLedgerCommitment`.
* `COMMITTED`: Terminal success state.

## Failure & Mitigation Paths
Any violation during the handshake immediately routes the transaction to a terminal failure state:
* `INVALID_SIGNATURE`: Cryptographic mismatch.
* `VALIDATION_FAILED`: The `InvariantEngine` rejected the payload math.
* `CONFLICT`: A concurrent edit was detected during `PREPARE`.
* `ROLLBACK_REQUIRED`: A failure occurred between `ACCEPT` and `COMMIT`, triggering a deterministic fallback.
