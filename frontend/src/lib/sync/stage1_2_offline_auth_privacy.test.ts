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
});
