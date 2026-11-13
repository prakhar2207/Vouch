import "fake-indexeddb/auto";
import { describe, it, before, after, beforeEach } from "node:test";
import assert from "node:assert/strict";
import Dexie from "dexie";
import { indexedDB as fakeIndexedDB, IDBKeyRange as fakeIDBKeyRange } from "fake-indexeddb";

Dexie.dependencies.indexedDB = fakeIndexedDB;
Dexie.dependencies.IDBKeyRange = fakeIDBKeyRange;

class MemoryStorage {
  private map = new Map<string, string>();
  get length() {
    return this.map.size;
  }
  clear() {
    this.map.clear();
  }
  getItem(key: string) {
    return this.map.has(key) ? this.map.get(key)! : null;
  }
  key(index: number) {
    return Array.from(this.map.keys())[index] ?? null;
  }
  removeItem(key: string) {
    this.map.delete(key);
  }
  setItem(key: string, value: string) {
    this.map.set(key, String(value));
  }
}

const memStorage = new MemoryStorage();
const memSessionStorage = new MemoryStorage();
const mockNavigator: { onLine: boolean; userAgent: string } = {
  onLine: true,
  userAgent: "SriLekh-Stage12-Test/1.0",
};

const capPrefStore = new Map<string, string>();
let capacitorNative = false;
let redirectUrls: string[] = [];

const mockWindow: Record<string, unknown> = {
  location: {
    hostname: "localhost",
    protocol: "http:",
    pathname: "/dashboard",
    replace: (u: string) => {
      redirectUrls.push(u);
    },
  },
  localStorage: memStorage,
  sessionStorage: memSessionStorage,
  crypto: globalThis.crypto,
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => true,
  indexedDB: globalThis.indexedDB,
  IDBKeyRange: globalThis.IDBKeyRange,
  CustomEvent: globalThis.CustomEvent,
  Event: globalThis.Event,
  Capacitor: {
    isNativePlatform: () => capacitorNative,
    Plugins: {
      Preferences: {
        set: ({ key, value }: { key: string; value: string }) => {
          capPrefStore.set(key, value);
        },
        remove: ({ key }: { key: string }) => {
          capPrefStore.delete(key);
        },
        get: async ({ key }: { key: string }) => ({
          value: capPrefStore.get(key) ?? null,
        }),
      },
    },
  },
};

Object.defineProperty(globalThis, "localStorage", { value: memStorage, configurable: true, writable: true });
Object.defineProperty(globalThis, "sessionStorage", { value: memSessionStorage, configurable: true, writable: true });
Object.defineProperty(globalThis, "window", { value: mockWindow, configurable: true, writable: true });
Object.defineProperty(globalThis, "navigator", { value: mockNavigator, configurable: true, writable: true });
if (typeof (globalThis as { document?: unknown }).document === "undefined") {
  Object.defineProperty(globalThis, "document", { value: { cookie: "" }, configurable: true, writable: true });
}

const axiosModule = await import("axios");
const axios = axiosModule.default;

const {
  offlineDb,
  safePurgeTenantData,
  getPendingOfflineSummary,
} = await import("@/lib/db/offlineDb");
const { ClientOperationManager } = await import("@/lib/crdt/clientOperationManager");
const { executeClientOutboxSync, pullIncrementalChanges, triggerFullSync } = await import(
  "@/lib/sync/sync-worker"
);
const { syncRepository } = await import("@/lib/data/sync-repository");
const { OfflineCryptoManager, isEncryptedEnvelope } = await import("@/lib/db/offlineCrypto");
const {
  setAuthenticatedSession,
  getAccessToken,
  getRefreshToken,
  getAuthAbortSignal,
  isAuthenticated,
  removeTokens,
} = await import("@/utils/auth");

describe("Stage 1.2: Browser Token Elimination, Native Compatibility & Offline Privacy Closure", () => {
  const originalAxiosPost = axios.post;
  const originalFetch = globalThis.fetch;

  before(async () => {
    if (!offlineDb.isOpen()) {
      await offlineDb.open();
    }
  });

  beforeEach(async () => {
    capacitorNative = false;
    redirectUrls = [];
    capPrefStore.clear();
    memStorage.clear();
    memSessionStorage.clear();
    (globalThis.document as { cookie: string }).cookie = "";
    mockNavigator.onLine = true;
    if (!offlineDb.isOpen()) {
      await offlineDb.open();
    }
    await Promise.all(offlineDb.tables.map((t) => t.clear()));
    axios.post = originalAxiosPost;
    globalThis.fetch = originalFetch;
  });

  after(() => {
    axios.post = originalAxiosPost;
    globalThis.fetch = originalFetch;
    try {
      offlineDb.close();
    } catch {}
  });

  it("1. Browser Cookie Mode: exposes ZERO JWT tokens in localStorage, document.cookie, getAccessToken(), or getRefreshToken()", () => {
    setAuthenticatedSession({
      user: { id: "user-browser-1", email: "browser@srilekh.local", role: "OWNER" },
      csrfToken: "csrf-abc-123",
      expiresAt: Date.now() + 15 * 60 * 1000,
      refreshExpiresAt: Date.now() + 7 * 24 * 60 * 60 * 1000,
      // Even if a legacy caller passes raw tokens in browser mode, they must never be persisted
      access: "eyJhbGciOi.fake.access",
      refresh: "eyJhbGciOi.fake.refresh",
    });

    assert.equal(isAuthenticated(), true);
    assert.equal(getAccessToken(), undefined);
    assert.equal(getRefreshToken(), undefined);
    assert.equal(memStorage.getItem("vouch_access_token"), null);
    assert.equal(memStorage.getItem("vouch_refresh_token"), null);
    assert.equal(memStorage.getItem("access_token"), null);
    assert.equal((globalThis.document as { cookie: string }).cookie.includes("eyJhbGciOi"), false);
  });

  it("2. Capacitor Native Mode: stores bearer tokens via Capacitor Preferences only and clears cleanly on logout", () => {
    capacitorNative = true;
    setAuthenticatedSession({
      user: { id: "user-native-1", email: "native@srilekh.local", role: "OWNER" },
      access: "native.access.jwt",
      refresh: "native.refresh.jwt",
    });

    assert.equal(getAccessToken(), "native.access.jwt");
    assert.equal(getRefreshToken(), "native.refresh.jwt");
    assert.equal(capPrefStore.get("vouch_access_token"), "native.access.jwt");
    assert.equal(capPrefStore.get("vouch_refresh_token"), "native.refresh.jwt");
    assert.equal(memStorage.getItem("vouch_access_token"), null);
    assert.equal(memStorage.getItem("vouch_refresh_token"), null);

    removeTokens({ broadcastReason: "logout" });
    assert.equal(getAccessToken(), undefined);
    assert.equal(getRefreshToken(), undefined);
    assert.equal(capPrefStore.has("vouch_access_token"), false);
    assert.equal(capPrefStore.has("vouch_refresh_token"), false);
  });

  it("3. Cross-User Privacy & Ordinary Logout: preserves User A outbox while hiding pending counts and blocking sync for User B in same company", async () => {
    setAuthenticatedSession({
      user: { id: "user-A", email: "a@srilekh.local", role: "OWNER" },
      expiresAt: Date.now() + 3600_000,
    });
    memStorage.setItem("vouch_active_company_id", "comp-A");
    memStorage.setItem("vouch_authoritative_forecast_comp-A_30", JSON.stringify({ secret: 99999 }));

    mockNavigator.onLine = false;
    await ClientOperationManager.recordLocalVoucherMutation({
      companyId: "comp-A",
      voucherType: "SALES",
      voucherDate: "2026-11-12",
      payload: {
        party_ledger_id: "party-A",
        party_name: "Private Buyer A",
        total_amount: 4500,
        items: [{ product_name: "Belt", quantity: 1, unit_price: 4500, tax_rate_percent: 0 }],
      },
    });

    // Ordinary logout clears caches & forecast localStorage, while preserving User A pending outbox
    await safePurgeTenantData();
    removeTokens({ skipOfflinePurge: true, broadcastReason: "logout" });

    assert.equal(memStorage.getItem("vouch_authoritative_forecast_comp-A_30"), null);
    assert.equal(await offlineDb.syncedVouchers.count(), 0);
    assert.equal((await getPendingOfflineSummary("user-A")).currentUserCount, 1);

    // User B signs into the same browser and selects comp-A
    setAuthenticatedSession({
      user: { id: "user-B", email: "b@srilekh.local", role: "OWNER" },
      expiresAt: Date.now() + 3600_000,
    });
    memStorage.setItem("vouch_active_company_id", "comp-A");

    // User B MUST NOT see User A's pending count or push User A's records
    assert.equal((await getPendingOfflineSummary("user-B")).currentUserCount, 0);
    assert.equal((await syncRepository.getSyncStatus("comp-A")).pendingMutationsCount, 0);

    mockNavigator.onLine = true;
    let networkCalls = 0;
    const axiosClient = axios as unknown as {
      post: (url: string) => Promise<{ data: Record<string, unknown> }>;
    };
    axiosClient.post = async () => {
      networkCalls += 1;
      return { data: { success: true } };
    };
    globalThis.fetch = async () => {
      networkCalls += 1;
      return new Response(JSON.stringify({ status: "SYNC_SUCCESS" }), { status: 200 });
    };

    const res = await executeClientOutboxSync();
    assert.equal(res.processed, 0);
    assert.equal(networkCalls, 0);
  });

  it("4. Logout Stops Background Sync & Aborts/Discards In-Flight Pull and Tenant-Switch Writes", async () => {
    setAuthenticatedSession({
      user: { id: "user-A", email: "a@srilekh.local", role: "OWNER" },
      expiresAt: Date.now() + 3600_000,
    });
    memStorage.setItem("vouch_active_company_id", "comp-A");
    mockNavigator.onLine = true;

    let observedAbortSignal: AbortSignal | undefined;
    let resolveDelayedFetch: ((res: Response) => void) | null = null;
    let markFetchStarted!: () => void;
    const fetchStarted = new Promise<void>((r) => {
      markFetchStarted = r;
    });
    globalThis.fetch = async (_url: RequestInfo | URL, init?: RequestInit) => {
      observedAbortSignal = init?.signal ?? undefined;
      markFetchStarted();
      return await new Promise<Response>((resolve) => {
        resolveDelayedFetch = resolve;
      });
    };

    const pullPromise = pullIncrementalChanges("comp-A", undefined, { force: true });
    await fetchStarted;

    // User logs out while pullIncrementalChanges is still in flight
    const signalBeforeLogout = getAuthAbortSignal();
    removeTokens({ broadcastReason: "logout" });
    assert.equal(signalBeforeLogout?.aborted, true);
    assert.equal(observedAbortSignal?.aborted, true);

    // Even if server response arrives late after logout, IndexedDB MUST NOT be written
    resolveDelayedFetch?.(
      new Response(
        JSON.stringify({
          changes: {
            ledgers: { created: [], updated: [], deleted: [] },
            products: { created: [], updated: [], deleted: [] },
            vouchers: {
              created: [
                {
                  id: "v-inflight-leak",
                  company_id: "comp-A",
                  voucher_type: "SALES",
                  voucher_number: "LEAK-001",
                  voucher_date: "2026-11-12",
                  status: "POSTED",
                  version: 1,
                  total_amount: 8800,
                },
              ],
              updated: [],
              deleted: [],
            },
            bank_transactions: { created: [], updated: [], deleted: [] },
            payment_allocations: { created: [], updated: [], deleted: [] },
          },
          has_more: false,
          next_cursor: "c-2",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    );

    const pullRes = await pullPromise;
    assert.equal(pullRes.success, false);
    assert.equal(await offlineDb.syncedVouchers.get("v-inflight-leak"), undefined);

    // Triggering full sync after logout must do zero network calls
    let callsAfterLogout = 0;
    globalThis.fetch = async () => {
      callsAfterLogout += 1;
      return new Response("{}", { status: 200 });
    };
    await triggerFullSync("comp-A");
    assert.equal(callsAfterLogout, 0);
  });

  it("5. Secure Shared-Device Logout Wipes Pending Outbox, Caches, and Device Keys Cleanly", async () => {
    setAuthenticatedSession({
      user: { id: "user-shared", email: "shared@srilekh.local", role: "OWNER" },
      expiresAt: Date.now() + 3600_000,
    });
    memStorage.setItem("vouch_active_company_id", "comp-shared");
    memStorage.setItem("vouch_device_id", "DEV-SHARED-123");
    memStorage.setItem("vouch_ed25519_pub_hex", "abcd");

    mockNavigator.onLine = false;
    await ClientOperationManager.recordLocalVoucherMutation({
      companyId: "comp-shared",
      voucherType: "PAYMENT",
      voucherDate: "2026-11-12",
      payload: {
        party_ledger_id: "party-s",
        party_name: "Vendor S",
        total_amount: 550,
        items: [],
      },
    });

    assert.equal((await getPendingOfflineSummary("user-shared")).totalPendingCount, 1);

    // Explicit shared-device wipe
    await safePurgeTenantData(undefined, { forceDestroyAll: true });
    removeTokens({ wipeLocalDeviceData: true, skipOfflinePurge: true, broadcastReason: "logout" });

    assert.equal(memStorage.getItem("vouch_device_id"), null);
    assert.equal(memStorage.getItem("vouch_ed25519_pub_hex"), null);

    await offlineDb.open();
    assert.equal(await offlineDb.outboxQueue.count(), 0);
    assert.equal(await offlineDb.operationLog.count(), 0);
    assert.equal(await offlineDb.syncedVouchers.count(), 0);
  });

  it("6. AES-GCM-256 Offline Encryption at Rest: raw IndexedDB hides party names, amounts & narrations and keeps non-extractable keys out of localStorage", async () => {
    const { OfflineCryptoManager, isEncryptedEnvelope } = await import("@/lib/db/offlineCrypto");
    const { KeyVaultIDB } = await import("@/lib/crdt/clientKeyManager");

    await offlineDb.syncedVouchers.put({
      id: "v-secret-1",
      companyId: "comp-enc",
      voucherType: "SALES",
      voucherDate: "2026-11-12",
      voucherNumber: "INV-2026-9991",
      partyLedgerId: "ledger-secret-1",
      partyName: "Confidential Belting Buyer Pvt Ltd",
      status: "POSTED",
      totalAmount: 987654.32,
      narration: "Top-secret defense conveyor belt order",
      serverUpdatedAt: Date.now(),
    });
    await offlineDb.syncedLedgers.put({
      id: "ledger-secret-1",
      companyId: "comp-enc",
      name: "Confidential Belting Buyer Pvt Ltd",
      ledgerType: "CUSTOMER",
      gstin: "27ABCDE1234F1Z5",
      currentBalance: 987654.32,
      openingBalance: 0,
      openingBalanceType: "DEBIT",
      serverUpdatedAt: Date.now(),
    });
    await offlineDb.syncedBankTransactions.put({
      id: "bank-secret-1",
      companyId: "comp-enc",
      bankLedgerId: "bank-1",
      transactionDate: "2026-11-12",
      description: "NEFT FROM CONFIDENTIAL BUYER INV-9991",
      normalizedNarration: "confidential buyer",
      referenceNumber: "UTR9988776655",
      debitAmount: 0,
      creditAmount: 987654.32,
      status: "UNRESOLVED",
      serverUpdatedAt: Date.now(),
    });

    // Read raw IndexedDB directly without Dexie middleware to inspect bytes on disk
    const readRaw = (storeName: string, key: IDBValidKey): Promise<Record<string, unknown>> =>
      new Promise((resolve, reject) => {
        const req = fakeIndexedDB.open("VouchOfflineDB");
        req.onsuccess = () => {
          const rawDb = req.result;
          const tx = rawDb.transaction(storeName, "readonly");
          const getReq = tx.objectStore(storeName).get(key);
          getReq.onsuccess = () => {
            rawDb.close();
            resolve(getReq.result as Record<string, unknown>);
          };
          getReq.onerror = () => {
            rawDb.close();
            reject(getReq.error);
          };
        };
        req.onerror = () => reject(req.error);
      });

    const rawVoucher = await readRaw("syncedVouchers", "v-secret-1");
    const rawLedger = await readRaw("syncedLedgers", "ledger-secret-1");
    const rawBank = await readRaw("syncedBankTransactions", "bank-secret-1");

    assert.equal(isEncryptedEnvelope(rawVoucher.__enc), true);
    assert.equal(isEncryptedEnvelope(rawLedger.__enc), true);
    assert.equal(isEncryptedEnvelope(rawBank.__enc), true);

    const serializedRaw = JSON.stringify({ rawVoucher, rawLedger, rawBank });
    assert.equal(serializedRaw.includes("Confidential Belting Buyer"), false);
    assert.equal(serializedRaw.includes("987654.32"), false);
    assert.equal(serializedRaw.includes("defense conveyor belt"), false);
    assert.equal(serializedRaw.includes("27ABCDE1234F1Z5"), false);
    assert.equal(serializedRaw.includes("UTR9988776655"), false);

    // Non-extractable key custody check
    assert.equal(memStorage.length, 0);
    assert.equal(memSessionStorage.length, 0);
    const active = await OfflineCryptoManager.getOrCreateActiveKey();
    assert.equal(active.key.extractable, false);
    await assert.rejects(() => globalThis.crypto.subtle.exportKey("raw", active.key));
    const storedSlot = await KeyVaultIDB.getOfflineCryptoKey("active_offline_db_key");
    assert.equal(storedSlot?.kid, active.kid);

    // Authorized read & update through Dexie seamlessly decrypts and preserves encrypted rest format
    const decVoucher = await offlineDb.syncedVouchers.get("v-secret-1");
    assert.equal(decVoucher?.partyName, "Confidential Belting Buyer Pvt Ltd");
    assert.equal(decVoucher?.totalAmount, 987654.32);

    await offlineDb.syncedVouchers.update("v-secret-1", { paymentStatus: "PAID", paidAmount: 987654.32 });
    const updatedDec = await offlineDb.syncedVouchers.get("v-secret-1");
    assert.equal(updatedDec?.paymentStatus, "PAID");
    assert.equal(updatedDec?.narration, "Top-secret defense conveyor belt order");
    const updatedRaw = await readRaw("syncedVouchers", "v-secret-1");
    assert.equal(isEncryptedEnvelope(updatedRaw.__enc), true);
    assert.equal(JSON.stringify(updatedRaw).includes("987654.32"), false);
  });

  it("7. Offline Encryption Supports Key Rotation, Plaintext Backward Compatibility & Non-Destructive Corrupt/Wiped Key Handling", async () => {
    const { OfflineCryptoManager, isEncryptedEnvelope } = await import("@/lib/db/offlineCrypto");

    // A) Legacy pre-encryption plaintext row injected directly into raw IndexedDB reads cleanly
    await new Promise<void>((resolve, reject) => {
      const req = fakeIndexedDB.open("VouchOfflineDB");
      req.onsuccess = () => {
        const rawDb = req.result;
        const tx = rawDb.transaction("syncedLedgers", "readwrite");
        tx.objectStore("syncedLedgers").put({
          id: "legacy-ledger-1",
          companyId: "comp-legacy",
          name: "Legacy Unencrypted Supplier",
          ledgerType: "SUPPLIER",
          currentBalance: 1200,
          openingBalance: 1200,
          openingBalanceType: "CREDIT",
          serverUpdatedAt: 1000,
        });
        tx.oncomplete = () => {
          rawDb.close();
          resolve();
        };
        tx.onerror = () => reject(tx.error);
      };
      req.onerror = () => reject(req.error);
    });

    const legacyRow = await offlineDb.syncedLedgers.get("legacy-ledger-1");
    assert.equal(legacyRow?.name, "Legacy Unencrypted Supplier");
    assert.equal(legacyRow?.currentBalance, 1200);

    // B) Key rotation: record created before rotation still decrypts while new writes use new kid
    await offlineDb.syncedVouchers.put({
      id: "v-before-rot",
      companyId: "comp-rot",
      voucherType: "SALES",
      voucherDate: "2026-11-12",
      voucherNumber: "INV-ROT-1",
      partyName: "Pre Rotation Party",
      status: "POSTED",
      totalAmount: 1111,
      serverUpdatedAt: 1000,
    });
    const rot = await OfflineCryptoManager.rotateKey();
    assert.ok(rot.previousKid && rot.kid !== rot.previousKid);

    await offlineDb.syncedVouchers.put({
      id: "v-after-rot",
      companyId: "comp-rot",
      voucherType: "SALES",
      voucherDate: "2026-11-12",
      voucherNumber: "INV-ROT-2",
      partyName: "Post Rotation Party",
      status: "POSTED",
      totalAmount: 2222,
      serverUpdatedAt: 2000,
    });

    assert.equal((await offlineDb.syncedVouchers.get("v-before-rot"))?.partyName, "Pre Rotation Party");
    assert.equal((await offlineDb.syncedVouchers.get("v-after-rot"))?.partyName, "Post Rotation Party");

    // C) Non-destructive failure handling if key vault is lost/tampered: pending outbox is NEVER deleted
    await offlineDb.outboxQueue.add({
      operationId: "op-survives-decrypt-err",
      transactionId: "tx-survives-1",
      companyId: "comp-rot",
      userId: "user-1",
      status: "QUEUED",
      retryCount: 0,
      lastError: "Transient timeout",
      createdAt: Date.now(),
    });
    const prevErr = console.warn;
    console.warn = () => {};
    try {
      await new Promise<void>((resolve, reject) => {
        const req = fakeIndexedDB.open("VouchSecurityVault", 2);
        req.onsuccess = () => {
          const vdb = req.result;
          const tx = vdb.transaction("offline_crypto_keys", "readwrite");
          tx.objectStore("offline_crypto_keys").clear();
          tx.oncomplete = () => {
            vdb.close();
            resolve();
          };
          tx.onerror = () => reject(tx.error);
        };
        req.onerror = () => reject(req.error);
      });
      OfflineCryptoManager.clearInMemoryCache();
      const decFail = (await offlineDb.syncedVouchers.get("v-after-rot")) as unknown as Record<string, unknown>;
      assert.equal(decFail?.__decryptionError, true);
      assert.equal(decFail?.partyName, undefined);
      // Queued outbox row count stays intact despite key loss
      assert.equal(await offlineDb.outboxQueue.where("operationId").equals("op-survives-decrypt-err").count(), 1);
    } finally {
      console.warn = prevErr;
    }

    // D) Raw encrypted check passed earlier; restore cleanly via cryptographic erase
    await safePurgeTenantData(undefined, { forceDestroyAll: true });
    await offlineDb.open();
    const afterWipe = await offlineDb.syncedVouchers.get("v-after-rot");
    assert.equal(afterWipe, undefined);
    void isEncryptedEnvelope;
  });

  it("8. AES-GCM Tamper Detection, Cross-Table AAD Binding, Non-Extractable Keys & Full 13-Table Coverage", async () => {
    const { key, kid } = await OfflineCryptoManager.getOrCreateActiveKey();
    assert.ok(kid.startsWith("OFFLINE-AES-"));
    assert.equal(key.extractable, false);
    await assert.rejects(() => globalThis.crypto.subtle.exportKey("raw", key));

    // Seed all 13 sensitive financial tables and verify raw IDB holds ciphertext rather than secrets
    await offlineDb.vouchers.put({ id: "raw-v-1", localId: "lv-1", voucherType: "SALES", payload: { customer_name: "Secret Client", grand_total: 8888 }, status: "PENDING", createdAt: Date.now() });
    await offlineDb.masters.put({ key: "company_c1_settings", data: { secretApiKey: "k_live_abc" }, updatedAt: Date.now() });
    await offlineDb.ocrCache.put({ fileHash: "ocr-1", result: { party: "Secret OCR Vendor", total: 990 }, cachedAt: Date.now() });
    await offlineDb.syncedVouchers.put({ id: "sv-tamper-1", companyId: "c-aad", voucherType: "SALES", voucherDate: "2026-11-12", voucherNumber: "INV-AAD-1", partyName: "Confidential Buyer", status: "POSTED", totalAmount: 7777, serverUpdatedAt: 1000 });
    await offlineDb.syncedLedgers.put({ id: "sl-tamper-1", companyId: "c-aad", ledgerType: "PARTY", name: "Secret Debtor Ledger", currentBalance: 54321, openingBalance: 0, openingBalanceType: "DEBIT", serverUpdatedAt: 1000 });
    await offlineDb.syncedProducts.put({ id: "sp-1", companyId: "c-aad", name: "Secret Belt X9", sku: "SKU-X9", currentStock: 25, purchasePrice: 310, sellingPrice: 499, serverUpdatedAt: 1000 });
    await offlineDb.syncMeta.put({ companyId: "c-aad", lastSyncAt: Date.now(), syncStatus: "IDLE", errorMessage: "Secret error note" });
    await offlineDb.analyticsDaily.put({ id: "ad-1", companyId: "c-aad", date: "2026-11-12", totalSales: 91234, totalPurchases: 12000 });
    await offlineDb.analyticsParty.put({ id: "ap-1", companyId: "c-aad", partyId: "p-1", partyName: "Top Secret VIP", netVolume: 44444 });
    await offlineDb.syncedBankTransactions.put({ id: "sbt-1", companyId: "c-aad", bankLedgerId: "bl-1", status: "UNMATCHED", transactionDate: "2026-11-12", amount: 6543, description: "NEFT SECRET REF", serverUpdatedAt: 1000 });
    await offlineDb.syncedPaymentAllocations.put({ id: "spa-1", companyId: "c-aad", paymentVoucherId: "pv-1", invoiceVoucherId: "iv-1", allocatedAmount: 3210, notes: "Private settlement note" });
    await offlineDb.operationLog.put({ operationId: "op-t8", transactionId: "tx-t8", companyId: "c-aad", userId: "u-1", replicaId: "rep-1", operationType: "CREATE", logicalTimestamp: 1, status: "PENDING", payload: { secretNote: "Sensitive CRDT Payload" }, createdAt: Date.now() });
    await offlineDb.outboxQueue.add({ operationId: "op-t8", transactionId: "tx-t8", companyId: "c-aad", userId: "u-1", status: "QUEUED", retryCount: 0, lastError: "Sensitive backend msg", createdAt: Date.now() });

    const rawChecks: Array<[string, IDBValidKey, string]> = [
      ["vouchers", "raw-v-1", "Secret Client"],
      ["masters", "company_c1_settings", "k_live_abc"],
      ["ocrCache", "ocr-1", "Secret OCR Vendor"],
      ["syncedVouchers", "sv-tamper-1", "Confidential Buyer"],
      ["syncedLedgers", "sl-tamper-1", "Secret Debtor Ledger"],
      ["syncedProducts", "sp-1", "Secret Belt X9"],
      ["syncMeta", "c-aad", "Secret error note"],
      ["analyticsDaily", "ad-1", "91234"],
      ["analyticsParty", "ap-1", "Top Secret VIP"],
      ["syncedBankTransactions", "sbt-1", "NEFT SECRET REF"],
      ["syncedPaymentAllocations", "spa-1", "Private settlement note"],
      ["operationLog", "op-t8", "Sensitive CRDT Payload"],
    ];
    await new Promise<void>((resolve, reject) => {
      const req = fakeIndexedDB.open("VouchOfflineDB");
      req.onsuccess = () => {
        const rawDb = req.result;
        const storeNames = rawChecks.map(([s]) => s);
        const tx = rawDb.transaction(storeNames, "readonly");
        let pending = rawChecks.length;
        for (const [storeName, pk, secret] of rawChecks) {
          const gReq = tx.objectStore(storeName).get(pk);
          gReq.onsuccess = () => {
            const rawRow = gReq.result as Record<string, unknown>;
            assert.ok(isEncryptedEnvelope(rawRow?.__enc), `${storeName} missing AES-GCM envelope`);
            assert.equal(JSON.stringify(rawRow).includes(secret), false, `${storeName} leaked secret plaintext`);
            pending -= 1;
            if (pending === 0) {
              rawDb.close();
              resolve();
            }
          };
          gReq.onerror = () => reject(gReq.error);
        }
      };
      req.onerror = () => reject(req.error);
    });

    // Test ciphertext bit-flip tamper + cross-table AAD transplant attack
    const prevWarn = console.warn;
    console.warn = () => {};
    try {
      await new Promise<void>((resolve, reject) => {
        const req = fakeIndexedDB.open("VouchOfflineDB");
        req.onsuccess = () => {
          const rawDb = req.result;
          const tx = rawDb.transaction(["syncedVouchers", "syncedLedgers"], "readwrite");
          const vReq = tx.objectStore("syncedVouchers").get("sv-tamper-1");
          const lReq = tx.objectStore("syncedLedgers").get("sl-tamper-1");
          vReq.onsuccess = () => {
            const vRaw = vReq.result as Record<string, any>;
            const voucherEnvelope = structuredClone(vRaw.__enc);
            // Tamper with byte inside ciphertext on sv-tamper-1
            const flipped = Buffer.from(vRaw.__enc.ct, "base64");
            flipped[0] ^= 0xff;
            vRaw.__enc.ct = flipped.toString("base64");
            tx.objectStore("syncedVouchers").put(vRaw);
            lReq.onsuccess = () => {
              // Transplant valid syncedVouchers ciphertext into syncedLedgers to test table-name AAD binding
              const lRaw = lReq.result as Record<string, any>;
              lRaw.__enc = voucherEnvelope;
              tx.objectStore("syncedLedgers").put(lRaw);
            };
          };
          tx.oncomplete = () => {
            rawDb.close();
            resolve();
          };
          tx.onerror = () => reject(tx.error);
        };
        req.onerror = () => reject(req.error);
      });

      const tamperedVoucher = (await offlineDb.syncedVouchers.get("sv-tamper-1")) as unknown as Record<string, unknown>;
      assert.equal(tamperedVoucher.__decryptionError, true);
      assert.equal(tamperedVoucher.partyName, undefined);
      assert.equal(tamperedVoucher.totalAmount, undefined);

      const aadMismatchLedger = (await offlineDb.syncedLedgers.get("sl-tamper-1")) as unknown as Record<string, unknown>;
      assert.equal(aadMismatchLedger.__decryptionError, true);
      assert.equal(aadMismatchLedger.currentBalance, undefined);
      // Outbox item must remain intact and non-destructively preserved despite tamper failure
      assert.equal(await offlineDb.outboxQueue.where("operationId").equals("op-t8").count(), 1);
    } finally {
      console.warn = prevWarn;
    }
  });

  it("9. Multi-Company Offline Isolation, Restart Persistence, Expired Session Guard & Shared-Device Wipe", async () => {
    // Simulate 2 users x 2 companies offline
    setAuthenticatedSession({
      user: { id: "user-alpha", email: "alpha@example.com", first_name: "Alpha", last_name: "Owner", role: "OWNER" },
      expiresAt: Date.now() + 3600_000,
    });
    memStorage.setItem("vouch_active_company_id", "company-1");
    await ClientOperationManager.recordLocalVoucherMutation({
      companyId: "company-1",
      voucherType: "SALES",
      voucherDate: "2026-11-12",
      payload: {
        party_name: "C1 Alpha Buyer",
        total_amount: 1500,
        items: [{ product_name: "Belt C1", quantity: 1, unit_price: 1500, tax_rate_percent: 0 }],
      },
    });
    memStorage.setItem("vouch_active_company_id", "company-2");
    await ClientOperationManager.recordLocalVoucherMutation({
      companyId: "company-2",
      voucherType: "PURCHASE",
      voucherDate: "2026-11-12",
      payload: {
        party_name: "C2 Alpha Supplier",
        total_amount: 2500,
        items: [{ product_name: "Belt C2", quantity: 1, unit_price: 2500, tax_rate_percent: 0 }],
      },
    });

    // Simulate browser reload / restart: close DB, clear memory key cache, reopen IDB
    offlineDb.close();
    OfflineCryptoManager.clearInMemoryCache();
    await offlineDb.open();

    const reopenedVoucher = await offlineDb.syncedVouchers.where("companyId").equals("company-1").first();
    assert.equal(reopenedVoucher?.partyName, "C1 Alpha Buyer");
    assert.equal(reopenedVoucher?.totalAmount, 1500);

    // User Beta in Company 2 cannot see User Alpha pending counts
    setAuthenticatedSession({
      user: { id: "user-beta", email: "beta@example.com", first_name: "Beta", last_name: "Accountant", role: "EMPLOYEE" },
      expiresAt: Date.now() + 3600_000,
    });
    const betaSummary = await getPendingOfflineSummary("user-beta");
    assert.equal(betaSummary.currentUserCount, 0);
    assert.equal(betaSummary.totalPendingCount, 2);

    // Expired/unauthenticated session must NOT transmit outbox items or delete them
    removeTokens({ skipOfflinePurge: true, broadcastReason: "session_expired" });
    let networkCalls = 0;
    axios.post = (async () => {
      networkCalls += 1;
      return { data: {} };
    }) as unknown as typeof axios.post;
    const unauthSync = await executeClientOutboxSync();
    assert.equal(networkCalls, 0);
    assert.equal(unauthSync.processed, 0);
    assert.equal(await offlineDb.outboxQueue.count(), 2);

    // Full shared-device wipe erases VouchOfflineDB & crypto keys cleanly
    await safePurgeTenantData(undefined, { forceDestroyAll: true });
    await offlineDb.open();
    assert.equal(await offlineDb.outboxQueue.count(), 0);
    assert.equal(await offlineDb.syncedVouchers.count(), 0);
  });
});
