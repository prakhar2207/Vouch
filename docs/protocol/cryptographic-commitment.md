# Protocol Specification: Cryptographic Commitment Layer

**Version:** 1.0.0
**Phase:** 7 (Integrity & Non-Repudiation)

## Abstract
Standard electronic data interchange models hash a static payload and sign it. This is vulnerable to replay attacks and fails to capture causal history. 

The Vouch Protocol replaces this with a **Cross-Ledger State Commitment (CLSC)**. A CLSC acts as a chained, cryptographically verifiable receipt that both the Buyer and Seller have agreed to an exact mathematical ledger state *after* the CRDT merge sequence completes.

## Commitment Formula
The protocol generates the commitment hash ($C_n$) using strict string concatenation of the underlying state roots:

$$C_n = H( T_n \parallel O_n \parallel S \parallel B \parallel C_{n-1} \parallel V_n )$$

Where:
* $T_n$: The hash of the Canonical Transaction payload.
* $O_n$: The State Root (Merkle root or cumulative hash) of all causally ordered Accounting Operations.
* $S$: The Seller's exact network Identity ID.
* $B$: The Buyer's exact network Identity ID.
* $C_{n-1}$: The hash of the previous commitment in the chain (enforcing order and preventing silent transaction deletion).
* $V_n$: The protocol version.

## Digital Signatures
Once $C_n$ is generated, it must be signed using modern asymmetric cryptography (e.g., Ed25519 or ECDSA).

$\sigma = Sign_{PrivateKey}(C_n)$

The hash algorithm and the signature algorithm are abstracted and explicitly defined in the payload. This ensures the protocol can be upgraded (e.g., to post-quantum algorithms) without breaking the conceptual architecture.

## Guarantees Provided
1. **Integrity:** The state roots ($T_n, O_n$) ensure that no historical operation can be altered without breaking the current commitment hash.
2. **Tamper Detection:** The $C_{n-1}$ chain ensures that an entire transaction cannot be silently deleted from the middle of the ledger.
3. **Non-Repudiation:** Asymmetric signatures guarantee that neither counterparty can deny having accepted the specific converged accounting state.
