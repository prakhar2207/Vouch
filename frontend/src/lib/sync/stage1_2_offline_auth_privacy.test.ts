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
});
