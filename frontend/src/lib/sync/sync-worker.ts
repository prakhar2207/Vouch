import { offlineDb, OfflineVoucher, SyncedVoucher, SyncedLedger, SyncedProduct } from "../db/offlineDb";
import { LocalAnalyticsEngine } from "../analytics/analytics-engine";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken } from "@/utils/auth";

/**
 * Returns a persistent, anonymous device UUID stored in localStorage.
 * Does NOT use userAgent or PII.
 */
export function getDeviceId(): string {
  if (typeof window === "undefined") return "server-env";
  let did = localStorage.getItem("vouch_device_id");
  if (!did || did.length < 10) {
    did = typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `dev-${Date.now()}-${Math.random().toString(36).substring(2, 10)}`;
    localStorage.setItem("vouch_device_id", did);
  }
  return did;
}

export async function queueOfflineVoucher(voucherType: string, payload: any, voucherDate: string) {
  const localId = typeof crypto !== "undefined" && crypto.randomUUID 
    ? crypto.randomUUID() 
    : `cmd-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
  const entry: OfflineVoucher = {
    localId,
    voucherType,
    voucherDate,
    payload,
    status: "PENDING",
    retryCount: 0,
    createdAt: Date.now(),
  };
  const id = await offlineDb.vouchers.add(entry);
  await triggerOutboxSync();
  return { id, localId, status: "QUEUED_OFFLINE" };
}

let isSyncInProgress = false;

/**
 * Pushes pending outbox mutations from IndexedDB to the backend authoritative command processor.
 * Features:
 * - Concurrency locking (exactly 1 sync execution at a time)
 * - Persistent anonymous UUID device ID
 * - Categorization of retryable vs permanent failures
 * - Exponential backoff on retries (max 10 retries)
 */
const BACKOFF_DELAYS = [2000, 5000, 15000, 30000, 60000];

export async function executeClientOutboxSync(): Promise<{ processed: number; failed: number }> {
  if (typeof window === "undefined" || !navigator.onLine) return { processed: 0, failed: 0 };
  if (isSyncInProgress) return { processed: 0, failed: 0 };
  isSyncInProgress = true;

  let processedCount = 0;
  let failedCount = 0;

  try {
    // Reset any orphaned SYNCING items back to PENDING if previous sync was interrupted
    try {
      const orphaned = await offlineDb.vouchers
        .where("status")
        .equals("SYNCING")
        .toArray();
      for (const orphan of orphaned) {
        if (orphan.id) {
          await offlineDb.vouchers.update(orphan.id, { status: "PENDING" });
        }
      }
    } catch (e) {
      console.warn("Failed to reset orphaned syncing vouchers:", e);
    }

    const allPending = await offlineDb.vouchers
      .where("status")
      .equals("PENDING")
      .toArray();

    const now = Date.now();
    // Only pick up items whose exponential backoff delay has elapsed
    const pending = allPending.filter((item) => !item.nextRetryAt || item.nextRetryAt <= now);

    if (pending.length === 0) return { processed: 0, failed: 0 };

    const token = getAccessToken();
    if (!token) return { processed: 0, failed: 0 };

    const deviceId = getDeviceId();

    for (const item of pending) {
      try {
        await offlineDb.vouchers.update(item.id!, { status: "SYNCING" });

        const commandId = item.localId;
        const companyId = item.payload.company_id || item.payload.company;

        const pushPayload = {
          company_id: companyId,
          commands: [
            {
              command_id: commandId,
              command_type: `CREATE_${item.voucherType.toUpperCase()}`,
              payload: item.payload,
              device_id: deviceId,
            }
          ]
        };

        const response = await fetch(`${API_BASE_URL}/api/v1/sync/push/`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
            "X-Company-ID": companyId || "",
          },
          body: JSON.stringify(pushPayload),
        });

        const resData = await response.json().catch(() => ({}));
        const httpStatus = response.status;

        if (response.ok && (resData.success || resData.processed_count > 0)) {
          const cmdResult = resData.results?.find((r: any) => r.command_id === commandId) || resData.results?.[0];
          if (cmdResult && cmdResult.status === "PROCESSED") {
            await offlineDb.vouchers.update(item.id!, {
              status: "SYNCED",
              voucherNumber: cmdResult?.voucher_number,
              syncedAt: Date.now(),
              nextRetryAt: undefined,
            });
            processedCount++;
          } else {
            const cmdErr = resData.errors?.find((e: any) => e.command_id === commandId)?.error || "Server processing failed";
            await offlineDb.vouchers.update(item.id!, {
              status: "FAILED",
              errorMessage: cmdErr,
              retryCount: (item.retryCount || 0) + 1,
            });
            failedCount++;
          }
        } else if (httpStatus === 400 || httpStatus === 422 || httpStatus === 409) {
          // Permanent validation or conflict failure: do NOT retry in a loop
          const errMsg = resData.errors?.find((e: any) => e.command_id === commandId)?.error || resData.error || `Rejected by server (${httpStatus})`;
          await offlineDb.vouchers.update(item.id!, {
            status: "FAILED",
            errorMessage: errMsg,
            retryCount: (item.retryCount || 0) + 1,
            nextRetryAt: undefined,
          });
          failedCount++;
        } else if (httpStatus === 401 || httpStatus === 403) {
          // Auth or permission failure: requires user login / role fix
          await offlineDb.vouchers.update(item.id!, {
            status: "FAILED",
            errorMessage: `Authorization error (${httpStatus})`,
            retryCount: (item.retryCount || 0) + 1,
            nextRetryAt: undefined,
          });
          failedCount++;
        } else {
          // Retryable error: 408, 429, 500, 502, 503, 504, or network failure
          const newRetry = (item.retryCount || 0) + 1;
          const errMsg = resData.errors?.[0]?.error || resData.error || `Server error (${httpStatus})`;
          if (newRetry >= 5) {
            await offlineDb.vouchers.update(item.id!, {
              status: "FAILED",
              errorMessage: `Exceeded max retry limit (5): ${errMsg}`,
              retryCount: newRetry,
              nextRetryAt: undefined,
            });
            failedCount++;
          } else {
            const delay = BACKOFF_DELAYS[newRetry - 1] || 60000;
            await offlineDb.vouchers.update(item.id!, {
              status: "PENDING",
              errorMessage: errMsg,
              retryCount: newRetry,
              nextRetryAt: Date.now() + delay,
            });
          }
        }
      } catch (err: any) {
        const isOnline = typeof navigator !== "undefined" ? navigator.onLine : false;
        const newRetry = (item.retryCount || 0) + 1;
        if (isOnline && newRetry >= 5) {
          await offlineDb.vouchers.update(item.id!, {
            status: "FAILED",
            errorMessage: err?.message || "Exceeded max network retry limit",
            retryCount: newRetry,
            nextRetryAt: undefined,
          });
          failedCount++;
        } else {
          const delay = BACKOFF_DELAYS[Math.min(newRetry - 1, BACKOFF_DELAYS.length - 1)];
          await offlineDb.vouchers.update(item.id!, {
            status: "PENDING",
            errorMessage: err?.message || "Network error during sync",
            retryCount: newRetry,
            nextRetryAt: Date.now() + delay,
          });
        }
      }
    }

    return { processed: processedCount, failed: failedCount };
  } finally {
    isSyncInProgress = false;
  }
}

export async function retryFailedVoucher(id: number) {
  await offlineDb.vouchers.update(id, { status: "PENDING", errorMessage: undefined, nextRetryAt: undefined, retryCount: 0 });
  await triggerOutboxSync();
}

export async function triggerOutboxSync() {
  if (typeof window === "undefined" || !navigator.onLine) return;

  // Verify there are actually eligible pending items before registering or executing sync
  const now = Date.now();
  const eligiblePending = await offlineDb.vouchers
    .where("status")
    .equals("PENDING")
    .filter((v) => !v.nextRetryAt || v.nextRetryAt <= now)
    .count()
    .catch(() => 0);

  if (eligiblePending === 0) return;

  if ("serviceWorker" in navigator && "SyncManager" in window) {
    try {
      const registration = await navigator.serviceWorker.ready;
      await (registration as any).sync.register("vouch-outbox-sync");
      return;
    } catch (err) {
      // Fallback to direct client-side sync worker loop if registration fails
      await executeClientOutboxSync();
    }
  } else {
    // Fallback for browsers without Background Sync API (e.g., Safari iOS)
    await executeClientOutboxSync();
  }
}

let isPullInProgress = false;

/**
 * Pulls incremental changes (vouchers, ledgers, products) from server into IndexedDB.
 * Uses cursor pagination in a while-loop until all batches are consumed.
 * Updates local analytics aggregate stores.
 */
export async function pullIncrementalChanges(
  companyId: string,
  onProgress?: (msg: string) => void
): Promise<{ success: boolean; totalRecords: number; error?: string }> {
  if (!companyId || typeof window === "undefined" || !navigator.onLine) {
    return { success: false, totalRecords: 0 };
  }
  if (isPullInProgress) {
    return { success: false, totalRecords: 0, error: "Pull already in progress" };
  }
  isPullInProgress = true;

  try {
    const token = getAccessToken();
    if (!token) {
      return { success: false, totalRecords: 0, error: "Authentication required" };
    }

    let meta = await offlineDb.syncMeta.get(companyId);
    if (!meta) {
      meta = {
        companyId,
        lastSyncAt: 0,
        syncStatus: "SYNCING",
        isInitialComplete: false,
        pendingMutationsCount: 0,
      };
      await offlineDb.syncMeta.put(meta);
    } else {
      await offlineDb.syncMeta.update(companyId, { syncStatus: "SYNCING" });
    }

    let hasMore = true;
    let currentCursor = meta.syncCursor || undefined;
    let lastPulledAt = meta.lastSyncAt > 0 ? meta.lastSyncAt : undefined;
    let totalRecords = 0;
    let batchIndex = 0;

    while (hasMore) {
      batchIndex++;
      if (onProgress) {
        onProgress(`Synchronizing operational data (batch ${batchIndex})...`);
      }

      const response = await fetch(`${API_BASE_URL}/api/v1/sync/pull/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
          "X-Company-ID": companyId,
        },
        body: JSON.stringify({
          company_id: companyId,
          cursor: currentCursor,
          last_pulled_at: lastPulledAt,
          limit: 200,
        }),
      });

      if (!response.ok) {
        const errText = await response.text().catch(() => "");
        await offlineDb.syncMeta.update(companyId, {
          syncStatus: "ERROR",
          errorMessage: `Sync pull failed (${response.status}): ${errText}`,
        });
        return { success: false, totalRecords, error: errText };
      }

      const resData = await response.json();
      const changes = resData.changes || {};

      // 1. Ingest Ledgers
      if (changes.ledgers) {
        const toPut: SyncedLedger[] = [
          ...(changes.ledgers.created || []),
          ...(changes.ledgers.updated || []),
        ].map((l: any) => ({
          id: l.id,
          companyId: l.company_id || companyId,
          name: l.name,
          ledgerType: l.ledger_type || "GENERAL",
          gstin: l.gstin,
          stateCode: l.state_code,
          currentBalance: Number(l.current_balance) || 0,
          openingBalance: Number(l.opening_balance) || 0,
          openingBalanceType: l.opening_balance_type || "DEBIT",
          phone: l.phone,
          serverUpdatedAt: l.server_updated_at || Date.now(),
        }));
        if (toPut.length > 0) {
          await offlineDb.syncedLedgers.bulkPut(toPut);
          totalRecords += toPut.length;
        }
        if (changes.ledgers.deleted && changes.ledgers.deleted.length > 0) {
          const toDel = changes.ledgers.deleted.map((l: any) => l.id);
          await offlineDb.syncedLedgers.bulkDelete(toDel);
        }
      }

      // 2. Ingest Products
      if (changes.products) {
        const toPut: SyncedProduct[] = [
          ...(changes.products.created || []),
          ...(changes.products.updated || []),
        ].map((p: any) => ({
          id: p.id,
          companyId: p.company_id || companyId,
          name: p.name,
          sku: p.sku,
          hsnCode: p.hsn_code,
          unit: p.unit || "PCS",
          purchasePrice: Number(p.purchase_price) || 0,
          salesPrice: Number(p.sales_price) || 0,
          gstRate: Number(p.gst_rate) || 0,
          currentStock: Number(p.current_stock) || 0,
          serverUpdatedAt: p.server_updated_at || Date.now(),
        }));
        if (toPut.length > 0) {
          await offlineDb.syncedProducts.bulkPut(toPut);
          totalRecords += toPut.length;
        }
        if (changes.products.deleted && changes.products.deleted.length > 0) {
          const toDel = changes.products.deleted.map((p: any) => p.id);
          await offlineDb.syncedProducts.bulkDelete(toDel);
        }
      }

      // 3. Ingest Vouchers
      if (changes.vouchers) {
        const toPut: SyncedVoucher[] = [
          ...(changes.vouchers.created || []),
          ...(changes.vouchers.updated || []),
        ].map((v: any) => ({
          id: v.id,
          companyId: v.company_id || companyId,
          financialYearId: v.financial_year_id,
          voucherType: v.voucher_type,
          voucherNumber: v.voucher_number,
          voucherDate: v.voucher_date,
          referenceNumber: v.reference_number,
          partyLedgerId: v.party_ledger_id,
          partyName: v.party_name,
          status: v.status,
          totalAmount: Number(v.total_amount) || 0,
          narration: v.narration,
          serverUpdatedAt: v.server_updated_at || Date.now(),
        }));
        if (toPut.length > 0) {
          await offlineDb.syncedVouchers.bulkPut(toPut);
          totalRecords += toPut.length;
        }
        // Deleted/Cancelled/Reversed vouchers update their status or delete
        if (changes.vouchers.deleted && changes.vouchers.deleted.length > 0) {
          const toUpdateCancelled: SyncedVoucher[] = changes.vouchers.deleted.map((v: any) => ({
            id: v.id,
            companyId: v.company_id || companyId,
            financialYearId: v.financial_year_id,
            voucherType: v.voucher_type,
            voucherNumber: v.voucher_number,
            voucherDate: v.voucher_date,
            referenceNumber: v.reference_number,
            partyLedgerId: v.party_ledger_id,
            partyName: v.party_name,
            status: v.status || "CANCELLED",
            totalAmount: Number(v.total_amount) || 0,
            narration: v.narration,
            serverUpdatedAt: v.server_updated_at || Date.now(),
          }));
          await offlineDb.syncedVouchers.bulkPut(toUpdateCancelled);
        }
      }

      hasMore = Boolean(resData.has_more);
      currentCursor = resData.next_cursor;
    }

    // Update sync metadata upon complete consumption
    await offlineDb.syncMeta.put({
      companyId,
      lastSyncAt: Date.now(),
      syncCursor: currentCursor,
      syncStatus: "IDLE",
      isInitialComplete: true,
      pendingMutationsCount: 0,
    });

    // Rebuild local aggregates for fast sequential queries
    await LocalAnalyticsEngine.rebuildLocalAnalytics(companyId);

    // Notify listeners (Dashboard, Navbar, etc.)
    if (typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent("vouch:sync-complete", {
          detail: { companyId, totalRecords, timestamp: Date.now() },
        })
      );
    }

    return { success: true, totalRecords };
  } catch (err: any) {
    console.error("Incremental pull failed:", err);
    await offlineDb.syncMeta.update(companyId, {
      syncStatus: "ERROR",
      errorMessage: err?.message || "Sync pull failed",
    });
    return { success: false, totalRecords: 0, error: err?.message };
  } finally {
    isPullInProgress = false;
  }
}

// Global Service Worker Background Sync message listener
if (typeof window !== "undefined" && "serviceWorker" in navigator) {
  navigator.serviceWorker.addEventListener("message", (event) => {
    if (event.data && event.data.type === "TRIGGER_OUTBOX_SYNC") {
      executeClientOutboxSync();
    }
  });
}

// Auto-register listener for online event inside the PWA container with 30s debounce
let lastVisibilitySyncTime = 0;
if (typeof window !== "undefined") {
  window.addEventListener("online", () => {
    triggerOutboxSync();
  });
  window.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      const now = Date.now();
      if (now - lastVisibilitySyncTime > 30000) {
        lastVisibilitySyncTime = now;
        triggerOutboxSync();
      }
    }
  });
}

