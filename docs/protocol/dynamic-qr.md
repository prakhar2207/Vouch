# Protocol Specification: Dynamic QR Session Bootstrap

**Version:** 1.0.0
**Phase:** 9 (Transport Layer)

## Abstract
In traditional systems (including older versions of Vouch), B2B QR codes often attempt to cram the entire invoice payload (JSON/XML) into the optical matrix. This creates dense, hard-to-scan codes, risks exposing PII, and forces offline processing constraints.

The **Vouch Dynamic QR** completely deprecates data-bearing QRs. Instead, the QR acts exclusively as an **Ephemeral Session Bootstrap**. It contains just enough cryptographic material to authenticate the optical scan and establish a secure, network-based EDI Handshake (Phase 8).

## QR Payload Schema
The payload is minimized to fit comfortably within a low-density QR code (fast scanning):
```json
{
  "v": "1.0",
  "tx": "TX-9A8B7C",
  "sid": "SESS-1234",
  "n": "nonce_88291a",
  "iss": "GSTIN-SELLER-01",
  "dig": "sha256_canonical_digest...",
  "exp": 1727763000,
  "sig": "ed25519_signature..."
}
```

## Security Pipeline (Scan to Session)
When the Buyer scans the QR using the Vouch App (or PWA):
1. **Decode & Extract:** Parse the Base64 JSON.
2. **Expiry Verification:** If `current_time > exp`, explicitly reject. Dynamic QRs should expire rapidly (e.g., 5-15 minutes) to prevent interception and later replay.
3. **Nonce Deduplication:** The server verifies `nonce_88291a` has never been used for this `session_id`. Replay attacks are rejected.
4. **Authenticity Check:** The `sig` is verified against the `iss` (Issuer's) public key.
5. **Session Initiation:** If all checks pass, the Vouch app instantiates an `EdiStateMachine` (from Phase 8) and automatically advances to `CAPABILITY_EXCHANGE` to fetch the actual canonical transaction over the network.

## Single Protocol Guarantee
As mandated in Rule 22: "Make QR and EDI two transports for the same protocol." 
Once the QR bootstrap succeeds, the exact same Canonical Schema (Phase 1), CRDT (Phase 4), and Invariants (Phase 3) handle the data. The QR is simply a physical pointer to the distributed state machine.
