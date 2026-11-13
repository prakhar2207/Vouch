import "fake-indexeddb/auto";
import { describe, it, before, after, beforeEach } from "node:test";
import assert from "node:assert/strict";
import Dexie from "dexie";
import { indexedDB as fakeIndexedDB, IDBKeyRange as fakeIDBKeyRange } from "fake-indexeddb";

Dexie.dependencies.indexedDB = fakeIndexedDB;
Dexie.dependencies.IDBKeyRange = fakeIDBKeyRange;

// 1. Initialize simulated Browser DOM + Storage + IndexedDB BEFORE loading offlineDb / auth modules
class MemoryStorage {
  private map = new Map<string, string>();
  get length() { return this.map.size; }
  clear() { this.map.clear(); }
  getItem(key: string) { return this.map.has(key) ? this.map.get(key)! : null; }
  key(index: number) { return Array.from(this.map.keys())[index] ?? null; }
  removeItem(key: string) { this.map.delete(key); }
  setItem(key: string, value: string) { this.map.set(key, String(value)); }
}

const memStorage = new MemoryStorage();
const mockNavigator: { onLine: boolean; userAgent: string } = {
  onLine: true,
  userAgent: "SriLekh-OfflineSync-Test/1.0",
};

const dispatchedEvents: Array<{ type: string; detail: unknown }> = [];
const windowListeners = new Map<string, Set<(ev: Event) => void>>();
const mockWindow = {
  location: { hostname: "localhost", protocol: "http:", pathname: "/dashboard", replace: () => {} },
  localStorage: memStorage,
  crypto: globalThis.crypto,
  addEventListener: (type: string, fn: (ev: Event) => void) => {
    if (!windowListeners.has(type)) windowListeners.set(type, new Set());
    windowListeners.get(type)!.add(fn);
  },
  removeEventListener: (type: string, fn: (ev: Event) => void) => {
    windowListeners.get(type)?.delete(fn);
  },
  dispatchEvent: (ev: Event & { detail?: unknown }) => {
    dispatchedEvents.push({ type: ev.type, detail: ev.detail });
    for (const fn of windowListeners.get(ev.type) || []) {
      fn(ev);
    }
    return true;
  },
};

Object.defineProperty(globalThis, "localStorage", { value: memStorage, configurable: true, writable: true });
Object.defineProperty(globalThis, "window", { value: mockWindow, configurable: true, writable: true });
Object.defineProperty(globalThis, "navigator", { value: mockNavigator, configurable: true, writable: true });
if (typeof (globalThis as { document?: unknown }).document === "undefined") {
  Object.defineProperty(globalThis, "document", { value: { cookie: "" }, configurable: true, writable: true });
}

await import("fake-indexeddb/auto");
Object.assign(mockWindow, {
  indexedDB: globalThis.indexedDB,
  IDBKeyRange: globalThis.IDBKeyRange,
  CustomEvent: globalThis.CustomEvent,
  Event: globalThis.Event,
});
const axiosModule = await import("axios");
const axios = axiosModule.default;

const { offlineDb, safePurgeTenantData, hasPendingOfflineTransactions } = await import("@/lib/db/offlineDb");
const { ClientOperationManager } = await import("@/lib/crdt/clientOperationManager");
const { executeClientOutboxSync, pullIncrementalChanges, ingestVoucherLocally } = await import("@/lib/sync/sync-worker");
const { syncRepository } = await import("@/lib/data/sync-repository");
const { setUser, setTokens, removeTokens } = await import("@/utils/auth");

function makeMockJwt(userId: string, email: string, role = "OWNER"): string {
  const b64u = (obj: object) => Buffer.from(JSON.stringify(obj)).toString("base64url");
  return `${b64u({ alg: "HS256", typ: "JWT" })}.${b64u({
    user_id: userId,
    email,
    role,
    exp: Math.floor(Date.now() / 1000) + 3600,
  })}.sig`;
}

function setActiveSession(userId: string, email: string, companyId: string, token?: string) {
  setTokens(token || makeMockJwt(userId, email, "OWNER"), "refresh-" + userId);
  setUser({ id: userId, email, role: "OWNER" });
  memStorage.setItem("vouch_active_company_id", companyId);
  memStorage.setItem("activeCompanyId", companyId);
  memStorage.setItem("vouch_active_company", companyId);
}

describe("Stage 4.12 Phase B: Offline-First Sync, Outbox Lifecycle & Tenant/User Isolation", () => {
  const originalAxiosPost = axios.post;
  const originalAxiosGet = axios.get;
  const originalFetch = globalThis.fetch;

  before(async () => {
    if (!offlineDb.isOpen()) {
      await offlineDb.open();
    }
  });

  beforeEach(async () => {
    dispatchedEvents.length = 0;
    memStorage.clear();
    mockNavigator.onLine = true;
    await Promise.all(offlineDb.tables.map((t) => t.clear()));
    axios.post = originalAxiosPost;
    axios.get = originalAxiosGet;
    globalThis.fetch = originalFetch;
  });

  after(() => {
    axios.post = originalAxiosPost;
    axios.get = originalAxiosGet;
    globalThis.fetch = originalFetch;
  });

  it("1. Queues offline SALES voucher locally, exposes pending status, and reconciles cleanly upon reconnect with X-Idempotency-Key & server version", async () => {
    setActiveSession("user-A", "a@pilot.local", "comp-A");
    mockNavigator.onLine = false;

    const localTx = await ClientOperationManager.recordLocalVoucherMutation({
      companyId: "comp-A",
      voucherType: "SALES",
      voucherDate: "2026-11-12",
      payload: {
        party_ledger_id: "party-1",
        party_name: "Offline Buyer",
        voucher_number: "OFF-001",
        total_amount: 1180,
        items: [{ product_name: "Conveyor Belt", quantity: 1, unit_price: 1000, tax_rate_percent: 18 }],
      },
    });

    assert.ok(localTx.operationId.startsWith("OP-CLI-"));
    const queuedOp = await offlineDb.operationLog.get(localTx.operationId);
    assert.equal(queuedOp?.status, "PENDING");
    assert.equal(queuedOp?.companyId, "comp-A");
    assert.equal(queuedOp?.userId, "user-A");

    const outboxRows = await offlineDb.outboxQueue.toArray();
    assert.equal(outboxRows.length, 1);
    assert.equal(outboxRows[0].status, "QUEUED");
    assert.equal(outboxRows[0].companyId, "comp-A");
    assert.equal(outboxRows[0].userId, "user-A");

    const projected = await offlineDb.syncedVouchers.where("companyId").equals("comp-A").toArray();
    assert.equal(projected.length, 1);
    assert.equal(projected[0].status, "PENDING_SYNC");

    const statusOffline = await syncRepository.getSyncStatus("comp-A");
    assert.equal(statusOffline.status, "OFFLINE");
    assert.equal(statusOffline.pendingMutationsCount, 1);
    assert.equal((await syncRepository.getSyncStatus("comp-B")).pendingMutationsCount, 0);

    // Go back online and sync
    mockNavigator.onLine = true;
    const postedHeaders: Array<Record<string, unknown>> = [];
    const axiosClient = axios as unknown as {
      post: (url: string, data?: unknown, config?: { headers?: Record<string, unknown> }) => Promise<{ data: Record<string, unknown> }>;
      get: (url: string, config?: Record<string, unknown>) => Promise<{ data: Record<string, unknown> }>;
    };
    axiosClient.post = async (_url: string, _data: unknown, config?: { headers?: Record<string, unknown> }) => {
      postedHeaders.push(config?.headers || {});
      return {
        data: {
          success: true,
          voucher_id: "srv-voucher-001",
          voucher_number: "INV/26-27/0101",
          total_amount: 1180,
          version: 2,
        },
      };
    };

    const syncRes = await executeClientOutboxSync();
    assert.equal(syncRes.processed, 1);
    assert.equal(postedHeaders.length, 1);
    assert.equal(postedHeaders[0]["X-Company-ID"], "comp-A");
    assert.equal(postedHeaders[0]["X-Idempotency-Key"], localTx.operationId);

    const remainingOutbox = await offlineDb.outboxQueue.toArray();
    assert.equal(remainingOutbox.length, 0);

    const updatedOp = await offlineDb.operationLog.get(localTx.operationId);
    assert.equal(updatedOp?.status, "SYNCED");

    const syncedRecord = await offlineDb.syncedVouchers.get("srv-voucher-001");
    assert.equal(syncedRecord?.status, "POSTED");
    assert.equal(syncedRecord?.version, 2);

    const postSyncStatus = await syncRepository.getSyncStatus("comp-A");
    assert.equal(postSyncStatus.pendingMutationsCount, 0);
  });

  it("2. Recovers orphaned IN_FLIGHT outbox rows after crash/reload and retries FAILED transient errors once backoff expires without duplicate IDs", async () => {
    setActiveSession("user-A", "a@pilot.local", "comp-A");
    mockNavigator.onLine = false;

    const tx = await ClientOperationManager.recordLocalVoucherMutation({
      companyId: "comp-A",
      voucherType: "SALES",
      voucherDate: "2026-11-12",
      payload: {
        party_ledger_id: "party-2",
        party_name: "Retry Buyer",
        total_amount: 500,
        items: [{ product_name: "Idler", quantity: 1, unit_price: 500, tax_rate_percent: 0 }],
      },
    });

    // Simulate browser tab crash mid-POST leaving row stuck IN_FLIGHT
    const row = await offlineDb.outboxQueue.where("operationId").equals(tx.operationId).first();
    assert.ok(row?.id);
    await offlineDb.outboxQueue.update(row!.id!, { status: "IN_FLIGHT" });

    // First online attempt fails with transient 503 error
    mockNavigator.onLine = true;
    let callCount = 0;
    const seenKeys: string[] = [];
    const axiosClient = axios as unknown as {
      post: (url: string, data?: unknown, config?: { headers?: Record<string, string> }) => Promise<{ data: Record<string, unknown> }>;
    };
    axiosClient.post = async (_url: string, _data: unknown, config?: { headers?: Record<string, string> }) => {
      callCount++;
      seenKeys.push(config?.headers?.["X-Idempotency-Key"] || "");
      if (callCount === 1) {
        const err = new Error("Service Unavailable") as Error & { response?: { status: number; data: Record<string, unknown> } };
        err.response = { status: 503, data: { error: "Temporary outage" } };
        throw err;
      }
      return {
        data: { success: true, voucher_id: "srv-voucher-retry", voucher_number: "INV/26-27/0102", total_amount: 500, version: 1 },
      };
    };

    await executeClientOutboxSync();
    assert.equal(callCount, 1);

    const failedRow = await offlineDb.outboxQueue.get(row!.id!);
    assert.equal(failedRow?.status, "FAILED");
    assert.equal(failedRow?.retryCount, 1);
    assert.ok((failedRow?.nextRetryAt || 0) > Date.now() - 500);

    // Immediate retry before backoff window must wait cleanly
    await executeClientOutboxSync();
    assert.equal(callCount, 1);

    // Expire backoff window and retry -> succeeds with identical X-Idempotency-Key
    await offlineDb.outboxQueue.update(row!.id!, { nextRetryAt: Date.now() - 10 });
    await executeClientOutboxSync();
    assert.equal(callCount, 2);
    assert.deepEqual(seenKeys, [tx.operationId, tx.operationId]);
    assert.equal(await offlineDb.outboxQueue.count(), 0);
  });

  it("3. Tenant Switch Safety: purges previous tenant UI caches while preserving its pending outboxQueue and refusing cross-tenant push", async () => {
    setActiveSession("user-A", "a@pilot.local", "comp-A");

    // Seed read cache + pending offline mutation in Company A
    await offlineDb.syncedVouchers.put({
      id: "cached-A-1",
      companyId: "comp-A",
      voucherType: "SALES",
      voucherNumber: "INV-A-1",
      voucherDate: "2026-11-12",
      status: "POSTED",
      version: 3,
      totalAmount: 1000,
      serverUpdatedAt: Date.now(),
    });

    mockNavigator.onLine = false;
    const txA = await ClientOperationManager.recordLocalVoucherMutation({
      companyId: "comp-A",
      voucherType: "SALES",
      voucherDate: "2026-11-12",
      payload: {
        party_ledger_id: "party-A",
        party_name: "Party A",
        total_amount: 900,
        items: [{ product_name: "Belt A", quantity: 1, unit_price: 900, tax_rate_percent: 0 }],
      },
    });

    // Switch Company A -> Company B
    await safePurgeTenantData("comp-A");
    memStorage.setItem("vouch_active_company_id", "comp-B");
    memStorage.setItem("activeCompanyId", "comp-B");
    memStorage.setItem("vouch_active_company", "comp-B");

    // Company A read caches must be gone, while Company A's pending outbox item survives
    assert.equal(await offlineDb.syncedVouchers.where("companyId").equals("comp-A").count(), 0);
    assert.equal(await offlineDb.outboxQueue.count(), 1);
    assert.equal(await hasPendingOfflineTransactions("comp-A"), true);
    assert.equal(await hasPendingOfflineTransactions("comp-B"), false);

    // Go online while active tenant is Company B: Tenant Guard MUST refuse to push Company A's mutation
    mockNavigator.onLine = true;
    const pushedUrls: string[] = [];
    const axiosClient = axios as unknown as {
      post: (url: string, data?: Record<string, unknown>) => Promise<{ data: Record<string, unknown> }>;
    };
    axiosClient.post = async (url: string) => {
      pushedUrls.push(url);
      return { data: { success: true, voucher_id: "WRONG" } };
    };
    globalThis.fetch = async (url: RequestInfo | URL) => {
      pushedUrls.push(String(url));
      return new Response(JSON.stringify({ status: "SYNC_SUCCESS" }), { status: 200 });
    };

    await executeClientOutboxSync();
    assert.equal(pushedUrls.length, 0, "Cross-tenant mutation must NEVER be pushed under Company B context");
    assert.equal((await offlineDb.operationLog.get(txA.operationId))?.status, "PENDING");

    // Switch back to Company A -> preserved outbox item now syncs cleanly
    memStorage.setItem("vouch_active_company_id", "comp-A");
    memStorage.setItem("activeCompanyId", "comp-A");
    memStorage.setItem("vouch_active_company", "comp-A");
    axiosClient.post = async (url: string, data?: Record<string, unknown>) => {
      pushedUrls.push(`${url}:${String(data?.company_id)}`);
      return { data: { success: true, voucher_id: "srv-A-900", voucher_number: "INV/A/900", total_amount: 900, version: 1 } };
    };

    const resumeRes = await executeClientOutboxSync();
    assert.equal(resumeRes.processed, 1);
    assert.deepEqual(pushedUrls, ["http://localhost:8000/api/v1/accounting/sales-invoice/:comp-A"]);
    assert.equal(await offlineDb.outboxQueue.count(), 0);
  });

  it("4. Cross-User Logout Safety: clears read caches & localStorage company state while preserving User A outbox and blocking User B from pushing it", async () => {
    setActiveSession("user-A", "a@pilot.local", "comp-A");
    await offlineDb.syncedVouchers.put({
      id: "secret-userA-cached",
      companyId: "comp-A",
      voucherType: "SALES",
      voucherNumber: "INV-SECRET",
      voucherDate: "2026-11-12",
      status: "POSTED",
      version: 5,
      totalAmount: 25000,
      serverUpdatedAt: Date.now(),
    });
    memStorage.setItem("vouch_cached_companies_list", JSON.stringify([{ id: "comp-A", name: "Secret Co" }]));

    mockNavigator.onLine = false;
    const txA = await ClientOperationManager.recordLocalVoucherMutation({
      companyId: "comp-A",
      voucherType: "PAYMENT",
      voucherDate: "2026-11-12",
      payload: {
        party_ledger_id: "party-A",
        party_name: "Supplier A",
        total_amount: 1200,
        items: [],
      },
    });

    // User A logs out -> caches + localStorage wiped, User A unacknowledged PAYMENT op preserved
    await safePurgeTenantData();
    removeTokens();

    assert.equal(memStorage.getItem("vouch_active_company_id"), null);
    assert.equal(memStorage.getItem("vouch_cached_companies_list"), null);
    assert.equal(memStorage.getItem("vouch_access_token"), null);
    assert.equal(await offlineDb.syncedVouchers.count(), 0);
    assert.equal(await offlineDb.outboxQueue.count(), 1);
    assert.ok(await offlineDb.operationLog.get(txA.operationId));

    // User B logs in on the SAME browser AND even selects comp-A
    setActiveSession("user-B", "b@pilot.local", "comp-A");
    mockNavigator.onLine = true;
    let fetchCalls = 0;
    globalThis.fetch = async () => {
      fetchCalls++;
      return new Response(JSON.stringify({ status: "SYNC_SUCCESS" }), { status: 200 });
    };

    // User Guard MUST block User B from syncing User A's queued operation
    const syncB = await ClientOperationManager.syncOutboxWithServer("http://localhost:8000");
    assert.equal(syncB.syncedCount, 0);
    assert.equal(fetchCalls, 0, "User B must NEVER push User A's queued offline mutation");
    assert.equal((await offlineDb.outboxQueue.count()), 1);

    // Log User A back in -> User A's queued PAYMENT op syncs to /api/v1/protocol/sync/ with X-Idempotency-Key
    await safePurgeTenantData();
    removeTokens();
    setActiveSession("user-A", "a@pilot.local", "comp-A");

    let syncedHeaders: Record<string, string> = {};
    globalThis.fetch = async (url: RequestInfo | URL, init?: RequestInit) => {
      fetchCalls++;
      if (String(url).includes("/register_device/")) {
        return new Response(JSON.stringify({ status: "REGISTERED" }), { status: 200 });
      }
      syncedHeaders = (init?.headers as Record<string, string>) || {};
      return new Response(JSON.stringify({
        status: "SYNC_SUCCESS",
        server_operations_to_apply: [],
        state_commitment: "merkle-01",
      }), { status: 200 });
    };

    const syncA = await ClientOperationManager.syncOutboxWithServer("http://localhost:8000");
    assert.equal(syncA.syncedCount, 1);
    assert.equal(syncedHeaders["X-Company-ID"], "comp-A");
    assert.equal(syncedHeaders["X-Idempotency-Key"], txA.operationId);
    const completedOutbox = await offlineDb.outboxQueue.where("operationId").equals(txA.operationId).first();
    assert.equal(completedOutbox?.status, "COMPLETED");
  });

  it("5. Pull Incremental Changes & Local Ingest preserve server OCC version", async () => {
    setActiveSession("user-A", "a@pilot.local", "comp-A");
    mockNavigator.onLine = true;

    const pullPayload = {
      changes: {
        ledgers: { created: [], updated: [], deleted: [] },
        products: { created: [], updated: [], deleted: [] },
        vouchers: {
          created: [
            {
              id: "v-occ-1",
              company_id: "comp-A",
              voucher_type: "SALES",
              voucher_number: "INV/26-27/0500",
              voucher_date: "2026-11-12",
              status: "POSTED",
              version: 4,
              total_amount: 4200,
            },
          ],
          updated: [],
          deleted: [],
        },
        bank_transactions: { created: [], updated: [], deleted: [] },
        payment_allocations: { created: [], updated: [], deleted: [] },
      },
      next_cursor: "cursor-2",
      has_more: false,
    };
    const axiosClient = axios as unknown as {
      get: (url: string, config?: unknown) => Promise<{ data: typeof pullPayload }>;
    };
    axiosClient.get = async () => ({ data: pullPayload });
    globalThis.fetch = async () => new Response(JSON.stringify(pullPayload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });

    await offlineDb.syncMeta.put({
      companyId: "comp-A",
      isInitialComplete: true,
      changeCursor: "cursor-1",
      syncStatus: "IDLE",
    });

    const pullRes = await pullIncrementalChanges("comp-A", undefined, { force: true });
    assert.equal(pullRes.success, true);
    const pulledVoucher = await offlineDb.syncedVouchers.get("v-occ-1");
    assert.equal(pulledVoucher?.version, 4);

    await ingestVoucherLocally("comp-A", {
      id: "v-occ-1",
      voucher_type: "SALES",
      voucher_number: "INV/26-27/0500",
      voucher_date: "2026-11-12",
      status: "POSTED",
      version: 5,
      total_amount: 4200,
    });
    const updatedVoucher = await offlineDb.syncedVouchers.get("v-occ-1");
    assert.equal(updatedVoucher?.version, 5);
  });
});
