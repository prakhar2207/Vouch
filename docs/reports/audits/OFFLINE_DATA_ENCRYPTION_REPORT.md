# SRI LEKH — OFFLINE DATA ENCRYPTION REPORT

**Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness`  
**Modules Implemented / Modified:**
- [`offlineCrypto.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/db/offlineCrypto.ts)
- [`offlineDb.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/db/offlineDb.ts)
- [`clientKeyManager.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/crdt/clientKeyManager.ts)
- [`analytics-engine.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/analytics/analytics-engine.ts)
- [`privacy-policy/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/privacy-policy/page.tsx)
- [`stage1_2_offline_auth_privacy.test.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/sync/stage1_2_offline_auth_privacy.test.ts)

---

## 1. Encryption Architecture (AES-GCM-256)

1. **Key Generation & Non-Extractable Custody (`VouchSecurityVault` v2):**
   - [`OfflineCryptoManager`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/db/offlineCrypto.ts) generates a **256-bit `AES-GCM` `CryptoKey`** using WebCrypto `crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"])` with `extractable = false`.
   - The non-extractable `CryptoKey` is structured-cloned directly into IndexedDB database `VouchSecurityVault` (upgraded cleanly from schema v1 to v2 to add object store `offline_crypto_keys` alongside `device_keys`) via [`KeyVaultIDB`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/crdt/clientKeyManager.ts).
   - **Zero keys in web storage:** No raw AES key bytes, JWKs, passphrases, or key seeds are written to `localStorage`, `sessionStorage`, or cookies. Attempting `crypto.subtle.exportKey(...)` rejects cleanly.
2. **Envelope Format & Table Binding (AAD):**
   - Every protected record stores only minimal Dexie index fields (`id`, `companyId`, `userId`, `status`, dates, etc.) at top level so `.where()`, compound indexes, and purge queries operate cleanly, while all sensitive fields (party names, GSTINs, voucher numbers, amounts, narrations, OCR results, bank statement descriptions, UTR references, stock valuations, and CRDT operation payloads) are sealed inside:
     ```json
     {
       "__enc": {
         "__enc": "AES-GCM-v1",
         "kid": "OFFLINE-AES-...",
         "iv": "<base64 96-bit random IV>",
         "ct": "<base64 AES-GCM ciphertext + 128-bit auth tag>"
       }
     }
     ```
   - `AES-GCM` additional authenticated data (`AAD`) binds ciphertext to `"srilekh:offline:<tableName>"`, preventing cross-table ciphertext transplantation.
   - **Protected Tables (`13`):** `vouchers`, `masters`, `ocrCache`, `syncedVouchers`, `syncedLedgers`, `syncedProducts`, `syncMeta`, `analyticsDaily`, `analyticsParty`, `syncedBankTransactions`, `syncedPaymentAllocations`, `operationLog`, and `outboxQueue`.

---

## 2. Transaction Integrity, Migration, Rotation & Erasure

1. **Zero Chromium `TransactionInactiveError` Design:**
   - Because IndexedDB auto-commits active transactions during off-thread WebCrypto `Promise` hops, [`VouchOfflineDB.installEncryptionLayer`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/db/offlineDb.ts) seals payloads **before** opening Dexie write transactions (`put`, `add`, `bulkPut`, `bulkAdd`, `update`) and pre-encrypts batch entries before explicit `offlineDb.transaction("rw", ...)` in [`analytics-engine.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/analytics/analytics-engine.ts).
   - Read queries decrypt asynchronously after `downlevelTable` IDB requests/cursors settle cleanly via Dexie DBCore (`get`, `getMany`, `query`) and wrapped `Collection` resolution (`toArray`, `first`, `last`, `sortBy`), leaving native synchronous cursor iteration intact.
2. **Staged Plaintext Backward Compatibility:**
   - Pre-upgrade unencrypted rows (lacking `__enc`) read back seamlessly without breaking existing offline queued items.
3. **Key Rotation & Non-Destructive Error Handling:**
   - `OfflineCryptoManager.rotateKey()` rotates the active encryption key while indexing previous keys by `kid` so older queued operations remain readable.
   - If a key is missing/corrupted or ciphertext tampering fails GCM verification, `decryptRecordForTable` flags `__decryptionError: true` and refuses to fabricate plaintext **without deleting pending `outboxQueue` / `operationLog` items**.
4. **Cryptographic Erasure on Shared-Device Logout:**
   - `safePurgeTenantData(undefined, { forceDestroyAll: true })` clears in-memory keys (`OfflineCryptoManager.clearInMemoryCache()`), closes `VouchSecurityVault`, and deletes both `VouchOfflineDB` and `VouchSecurityVault`.

---

## 3. Verified Execution Evidence

- **`cd frontend && npm test`:** **`39 / 39` passed (`0` failures)** on Node + `fake-indexeddb` + WebCrypto, including **Tests 6 & 7** of [`stage1_2_offline_auth_privacy.test.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/sync/stage1_2_offline_auth_privacy.test.ts), which directly opened raw `VouchOfflineDB` without Dexie middleware to confirm:
  - Party names, amounts, GSTINs, narrations, and UTRs are absent in plaintext on disk.
  - `active.key.extractable === false` and `exportKey("raw", active.key)` rejects.
  - `localStorage` and `sessionStorage` have `length === 0`.
  - Legacy plaintext rows read cleanly, key rotation works across prior & new `kid`, key loss sets `__decryptionError: true` while leaving `outboxQueue` rows intact, and `forceDestroyAll` wipes both databases.
- **`privacy-policy/page.tsx` Updated:** Updated Sections 7, 9, and 10 to accurately reflect AES-GCM-256 non-extractable encryption of sensitive payloads alongside unencrypted routing/index metadata.
