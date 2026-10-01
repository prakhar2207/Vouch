# Vouch Distributed Accounting: Production Key Management & Cryptographic Custody Strategy

## 1. Executive Summary & Core Security Guarantees

The Vouch Distributed Accounting Protocol operates on an absolute zero-trust cryptographic model. Every ledger mutation, counterparty agreement, item rejection, and settlement payment is cryptographically non-repudiable via asymmetric Ed25519 digital signatures.

This document details the production key custody architecture, device authorization lifecycle, KMS/HSM integration specifications, and emergency response runbooks required to maintain financial-grade security.

---

## 2. Cryptographic Identity Hierarchy

```mermaid
flowchart TD
    subgraph Enterprise ["Enterprise Core (Cloud / On-Premise)"]
        ROOT["Enterprise Master Key (FIPS 140-2 Level 3 Cloud KMS / HSM)"]
        ADMIN["Authorized Company Administrator"]
        ROOT --> |Authorizes & Audits| SESS_KEY["Server LedgerBridge Commitment Key"]
    end

    subgraph Client ["Client Device Tier (Browser / Mobile POS)"]
        WC["Web Crypto API (Ed25519 Asymmetric Keypair)"]
        NON_EXP["extractable: false (Private Key Unexportable)"]
        IDB_VAULT[("IndexedDB: VouchSecurityVault (CryptoKey Structured Clone)")]
        WC --> NON_EXP --> IDB_VAULT
    end

    subgraph Server_DB ["Server Authorization Registry"]
        AUTH_DEV[("AuthorizedDevice (status: ACTIVE / REVOKED / ROTATED)")]
        AUDIT_LOG[("DeviceKeyRotationAudit (Immutable History)")]
    end

    WC --> |POST /register/ (409 on Duplicate)| AUTH_DEV
    ADMIN --> |Authorize Rotation| AUDIT_LOG
    IDB_VAULT --> |Sign Rotation Proof| AUDIT_LOG
    AUDIT_LOG --> AUTH_DEV
```

### 2.1. Separation of Concerns
1. **Device Operational Keys (Ed25519):** Dedicated per physical replica device (browser instance, mobile tablet, ERP gateway). Used strictly for offline operation signing and CRDT DAG non-repudiation.
2. **Enterprise Settlement Keys (Cloud KMS / HSM):** Held in dedicated hardware security modules for cross-enterprise Merkle state commitment signing and statutory tax sealing.
3. **Admin User Credentials:** JWT Bearer authentication backed by enterprise role-based access control (RBAC), restricting administrative device enrollment and key rotation.

---

## 3. Browser Client Key Custody Architecture

### 3.1. Non-Exportable Web Crypto Isolation
Private keys are generated directly in the browser's cryptographic boundary:
```typescript
const keyPair = await window.crypto.subtle.generateKey(
  { name: "Ed25519" },
  false, // extractable: FALSE (strictly prevents export via .exportKey)
  ["sign", "verify"]
);
```

### 3.2. Structured Clone Storage in IndexedDB (`VouchSecurityVault`)
* **Zero Plaintext Storage:** Private keys are stored exclusively as native `CryptoKey` handles inside IndexedDB's `VouchSecurityVault` object store.
* **XSS Defense:** Even if malicious JavaScript is injected via a third-party dependency, the private key bytes cannot be extracted because `extractable: false` prevents serialization. The attacker can at most request the browser to sign messages while the tab is active, but cannot exfiltrate the private key material to an external server.
* **Storage Audit Guarantee:** Private keys **never** touch `localStorage`, `sessionStorage`, or plaintext HTTP cookies.

---

## 4. Device Lifecycle & Authorization Protocol

### 4.1. Registration Protocol (`POST /api/v1/protocol/devices/register/`)
* **Duplicate Protection:** Re-registering an existing `device_id` or `replica_id` is strictly rejected with `HTTP 409 Conflict` (`DEVICE_ALREADY_REGISTERED` / `REPLICA_ALREADY_BOUND`). Overwriting existing active keys via the registration endpoint is physically prohibited.
* **Atomic Race Barrier:** Database uniqueness constraints on `(device_id)` and `(company, replica_id)` catch concurrent registration attempts via `IntegrityError` and return `409 Conflict`.

### 4.2. Secure Key Rotation Protocol (`POST /api/v1/protocol/devices/rotate/`)
Key rotation replaces a device's public key with a new active key while preserving audit lineage. Rotation requires one of two strict authorization methods:
1. **Cryptographic Proof of Possession:**
   - The request contains a cryptographic signature `rotation_signature` over `ROTATE:{device_id}:{new_public_key_hex}:{new_key_id}`.
   - The server verifies this signature using the device's **existing active public key**.
   - If verified, `authorization_method = "CRYPTOGRAPHIC_PROOF"`.
2. **Company Administrator Override:**
   - If the previous key was lost or hardware replaced, an authenticated user with role `ADMIN` or `OWNER` in the company must authorize the change.
   - If verified, `authorization_method = "COMPANY_ADMIN"`.
3. **Fail-Closed Enforcement:** Any rotation request lacking both valid cryptographic proof and admin rights is rejected with `HTTP 403 Forbidden` (`UNAUTHORIZED_KEY_ROTATION`).

### 4.3. Immutable Key Rotation Audit Trail (`DeviceKeyRotationAudit`)
Every key rotation event permanently appends an immutable record to `protocol_device_key_rotations`:
```sql
CREATE TABLE protocol_device_key_rotations (
    id BIGSERIAL PRIMARY KEY,
    device_id VARCHAR(100) REFERENCES protocol_authorized_devices(device_id),
    old_public_key_hex VARCHAR(128) NOT NULL,
    old_key_id VARCHAR(100) NOT NULL,
    new_public_key_hex VARCHAR(128) NOT NULL,
    new_key_id VARCHAR(100) NOT NULL,
    rotated_by_id UUID REFERENCES accounts_user(id),
    authorization_method VARCHAR(50) NOT NULL,
    rotation_signature VARCHAR(512),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 4.4. Emergency Revocation Protocol (`POST /api/v1/protocol/devices/revoke/`)
* When a device is reported lost, stolen, or compromised, an administrator triggers instant revocation.
* The device's status is permanently updated to `REVOKED`.
* **Zero-Latency Invalidation:** The sync service inspects device status on **every** synchronization request. Any operation signed by a `REVOKED` device is rejected immediately (`SYNC_REJECTED: Replica device has status 'REVOKED'`).
* Revoked devices cannot be un-revoked or rotated; they must be discarded.

---

## 5. Enterprise Cloud KMS & HSM Integration

For enterprise multi-tenant deployments, server-side commitment signing interfaces with dedicated cryptographic hardware (`apps/protocol/kms.py`):

| Deployment Tier | Provider Class | Cryptographic Backend | Security Standard | Production Latency |
|---|---|---|---|---|
| **Development / Test** | `LocalSoftwareKMS` | Python `cryptography` in-memory Ed25519 | Local automated tests | ~45 microseconds |
| **AWS Cloud Production** | `CloudKMSProvider` | AWS KMS Asymmetric Keys (`ECC_ED25519`) | FIPS 140-2 Level 3 | 15 – 25 ms |
| **Google Cloud Production** | `CloudKMSProvider` | Google Cloud HSM | FIPS 140-2 Level 3 | 18 – 30 ms |
| **On-Premise / Sovereign** | `CloudKMSProvider` | PKCS#11 Hardware Security Module (Thales/YubiHSM) | FIPS 140-2 Level 4 | 5 – 12 ms |

---

## 6. Security Incident Response Runbook

### 6.1. Lost or Stolen Client Terminal
1. **Immediate Revocation:** Company admin calls `POST /api/v1/protocol/devices/revoke/` with `device_id`.
2. **Audit Verification:** Inspect `protocol_bridge_executions` for any operations submitted by the compromised replica between loss time and revocation time.
3. **Issue Compensating Vouchers:** If fraudulent transactions were synced, emit compensatory reversals (`CREDIT_NOTE_ISSUED` / `VOUCHER_CANCELLED`) signed by authorized company keys.

### 6.2. Suspected Key Drift or Signature Desynchronization
1. Execute `python apps/protocol/test_canonical_vectors.py` to confirm cross-language canonical serialization integrity.
2. Verify that public key pinned in `protocol_authorized_devices` matches the active key in `VouchSecurityVault`.
3. If desynchronization occurred, trigger authorized rotation via `POST /api/v1/protocol/devices/rotate/`.
