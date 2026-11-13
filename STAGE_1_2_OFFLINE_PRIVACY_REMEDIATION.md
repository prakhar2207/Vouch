# SRI LEKH — STAGE 1.2: OFFLINE PRIVACY & ENCRYPTION ASSESSMENT REPORT

**Date:** 2026-11-12  
**Branch:** `fix/stage4-12-day6-remediation`  
**Gap Addressed:** **P1 — Offline financial data retained after logout** & **VouchSecurityVault / IndexedDB Encryption Assessment**

---

## 1. IndexedDB & Local Storage Data Handling Inventory

| Store / Mechanism | Stored Contents | Persistence Across Ordinary Logout | Persistence Across Secure Shared-Device Logout |
| :--- | :--- | :--- | :--- |
| **`VouchOfflineDB` Read Caches** (`syncedVouchers`, `syncedLedgers`, `syncedProducts`, `syncedBankTransactions`, `syncedPaymentAllocations`, `analyticsDaily`, `analyticsParty`, `masters`, `ocrCache`, `inboxQueue`, `syncCursors`, `syncMeta`) | Company vouchers, party GSTINs, balances, inventory, bank transactions, OCR caches, sync cursors. | **Cleared** (`safePurgeTenantData()`). | **Deleted** (`deleteDatabase("VouchOfflineDB")`). |
| **`VouchOfflineDB` Outbox** (`outboxQueue`, `operationLog`, legacy `vouchers`) | Unsynchronized `QUEUED`, `IN_FLIGHT`, `FAILED` transactions tagged with `userId` and `companyId`. | **Preserved** so pending accounting work is never silently lost; `COMPLETED`/`SYNCED` items cleared. | **Deleted** with explicit user warning and confirmation checkbox when pending items > 0. |
| **`VouchSecurityVault` (`device_keys`)** | Non-extractable Web Crypto `Ed25519` private key (`primary_ed25519_key`) for CRDT operation signing. | Preserved for device key continuity. | **Deleted** after closing open IDB handle (`ClientKeyManager.closeAndResetVault()` + `deleteDatabase("VouchSecurityVault")`). |
| **`localStorage` / `sessionStorage` Caches** | `vouch_session_meta`, `vouch_user`, `vouch_active_company_*`, `vouch_cached_companies_list`, `vouch_authoritative_forecast_*`, `vouch_health_*`, `vouch_device_id`, `vouch_ed25519_*`. | User/company/forecast/health caches **cleared**; anonymous device identifiers retained unless device wipe chosen. | **All `vouch_*` keys cleared**, including device & public-key metadata. |

---

## 2. Encryption Assessment (`VouchSecurityVault` & `VouchOfflineDB`)

Per Stage 1.2 Section 3, `VouchSecurityVault` ([`clientKeyManager.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/crdt/clientKeyManager.ts)) and [`offlineDb.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/db/offlineDb.ts) were audited **without** rebuilding a new encryption scheme:

1. **Which IndexedDB records are encrypted:** **None.** Zero business/financial tables in `VouchOfflineDB` use client-side symmetric payload encryption at rest. `VouchSecurityVault` provides **Ed25519 digital signing** for CRDT operation integrity/authentication against `AuthorizedDevice`, not at-rest encryption of IndexedDB rows.
2. **Which records remain plaintext:** All operational accounting, party, GSTIN, inventory, bank reconciliation, OCR result, and queued voucher payloads stored inside `VouchOfflineDB`, plus cached dashboard forecast/health blobs while signed in.
3. **How keys are stored:** The Web Crypto Ed25519 private signing key (`primary_ed25519_key`) is stored in IndexedDB `VouchSecurityVault` (`device_keys` object store) as a structured-clone `CryptoKey` with `extractable = false` (cannot be exported as JWK/raw bytes). Public metadata (`vouch_device_id`, `vouch_protocol_replica_id`, `vouch_ed25519_key_id`, `vouch_ed25519_pub_hex`) resides in `localStorage`.
4. **Whether keys are separated by user/device:** Separated per browser profile/origin (`primary_ed25519_key`), **NOT** separated per user account on the same browser profile.
5. **What happens when a key is lost:** `ClientKeyManager.getOrCreateIdentity()` detects the missing key and generates a new Ed25519 keypair, registering the new public key via `/api/v1/protocol/devices/register/` when next syncing online. Already-signed `operationLog` items retain their existing `signature` values unless wiped alongside the database.
6. **Whether existing offline data can be recovered:** Because `VouchOfflineDB` is stored as structured plaintext in browser IndexedDB (not wrapped by `VouchSecurityVault`), losing `VouchSecurityVault` alone does **not** lock out `VouchOfflineDB` data. Conversely, executing **Secure Shared-Device Logout** explicitly wipes both `VouchOfflineDB` and `VouchSecurityVault`, permanently removing un-synced drafts from that browser.
7. **Future Encryption Task (Documented, Not Rebuilt):** Full per-user Web Crypto AES-GCM wrapping of `VouchOfflineDB` records (derived from server/passkey/PIN unlock secret with explicit key-escrow/recovery handling) should be scheduled as a dedicated future task **only** once recovery UX for forgotten unlock secrets and offline availability guarantees are designed. *Severity: Moderate-High on unattended shared terminals if users retain un-synced offline items via Standard Logout.*

---

## 3. Remediations Implemented (Logout, Tenant Switching, Outbox, Stale Tabs & Shared Devices)

1. **Strict Ownership Filtering on Read & Badge State ([`sync-repository.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/data/sync-repository.ts), [`offlineDb.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/db/offlineDb.ts), [`vouchers-repository.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/data/vouchers-repository.ts)):**
   - Fixed a Stage 1.2 finding where `SyncRepository.getSyncStatus(companyId)` counted `outboxQueue` items by `companyId` without checking `userId`, which would expose User A's pending count to User B on the same company. Now filtered strictly by `userId` and `companyId`.
   - Added [`getPendingOfflineSummary(userId)`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/db/offlineDb.ts) and user-scoped `hasPendingOfflineTransactions(companyId, userId)`.
   - Added `user_id` guard on legacy `offlineDb.vouchers` merge inside `VouchersRepository`.
2. **Positive User & Tenant Sync Guards ([`sync-worker.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/sync/sync-worker.ts), [`clientOperationManager.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/crdt/clientOperationManager.ts)):**
   - Both `pushPendingSalesInvoices()` and `ClientOperationManager._doSyncOutboxWithServer()` require **non-empty `currentUserId` and exact match on `activeCompanyId`**, refusing queued mutations if no user/company is active or if mismatched.
   - `triggerOutboxSync()`, `triggerFullSync()`, and `syncCompany()` exit immediately when `!isAuthenticated()`.
3. **In-Flight Request Cancellation & Post-Logout / Tenant-Switch Write Blocking ([`auth.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/auth.ts), [`sync-worker.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/sync/sync-worker.ts), `repositories`):**
   - Added `authEpoch` monotonic counter and shared `AbortController` (`getAuthAbortSignal()`) bumped & aborted immediately inside `removeTokens()` / logout.
   - `pullIncrementalChanges()`, `pushPendingSalesInvoices()`, `ClientOperationManager._doSyncOutboxWithServer()`, and offline-caching repositories (`ledgers`, `products`, `vouchers`, `bank-transactions`) capture `(startEpoch, startUserId, companyId)` before network calls and re-verify before every IndexedDB write (`bulkPut`, `bulkDelete`, `syncMeta`, `outboxQueue`, `operationLog`). Late-resolving responses after logout or company switch are discarded without touching local storage.
4. **Multi-Tab Stale-Tab Revocation (`BroadcastChannel` + `storage` fallback):**
   - Logging out or encountering a rejected refresh (`401`) broadcasts `AUTH_LOGOUT` across open tabs (`vouch_auth_coordination` + `localStorage` fallback), bumping `authEpoch`, aborting in-flight API/sync calls, wiping local session/forecast caches, and redirecting stale tabs to `/login?expired=1` — paired on the server with `User.token_version` increment (`401` on any stale credential).
5. **Distinguished Ordinary vs Secure Shared-Device Logout ([`LogoutConfirmModal.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/components/modals/LogoutConfirmModal.tsx), [`DashboardLayout.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/components/DashboardLayout.tsx), [`admin/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/admin/page.tsx)):**
   - **Standard Logout:** Clears server session & cookies, stops background sync, clears read caches & Service Worker caches, and preserves User A's unsynchronized outbox locked by `userId` & `companyId` (displaying exact pending count notice).
   - **Secure Shared-Device Logout:** Explicitly warns about `N` unsynchronized local records, requires checking a confirmation box before enabling **Wipe Local Data & Sign Out**, closes & deletes `VouchOfflineDB` and `VouchSecurityVault`, wipes all `vouch_*` storage keys, and clears Service Worker caches.

---

## 4. Remaining Offline Privacy Risks

1. **Plaintext Pending Outbox During Standard Logout:** Because `VouchOfflineDB` is unencrypted, if User A performs *Standard Logout* (intentionally preserving un-synced offline drafts) on an untrusted kiosk instead of choosing *Secure Shared-Device Logout*, an attacker with physical/OS filesystem or DevTools access to that browser profile could inspect raw IndexedDB `outboxQueue`/`operationLog` entries directly (even though User B's SriLekh session cannot view or sync them).
2. **Legacy `offlineDb.vouchers` Rows Missing `user_id`:** While active offline creation (`ClientOperationManager.recordLocalVoucherMutation`) always stamps `userId` and `companyId` on both `operationLog` and `outboxQueue`, pre-Stage-4.12 legacy `vouchers` rows created without `payload.user_id` rely on `vouchers` table wipe during shared-device logout.
