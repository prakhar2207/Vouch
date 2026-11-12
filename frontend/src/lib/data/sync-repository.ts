import { offlineDb } from "../db/offlineDb";
import { executeClientOutboxSync, pullIncrementalChanges, ingestVoucherLocally, triggerFullSync } from "../sync/sync-worker";
import type { SyncedVoucher } from "../db/offlineDb";

export interface SyncStatusInfo {
  status: "IDLE" | "SYNCING" | "ERROR" | "OFFLINE";
  lastSyncAt: number | null;
  pendingMutationsCount: number;
  isInitialComplete: boolean;
  errorMessage?: string;
}

export class SyncRepository {
  /**
   * Triggers a coordinated sync (push outbox mutations then pull incremental changes).
   */
  async triggerSync(companyId: string, force: boolean = false): Promise<boolean> {
    if (!companyId) return false;
    try {
      await executeClientOutboxSync();
      const pullRes = await pullIncrementalChanges(companyId, undefined, { force });
      return pullRes.success;
    } catch (e) {
      console.warn("[SyncRepo] Sync failed:", e);
      return false;
    }
  }

  /**
   * Immediately ingests a created voucher into local IndexedDB before navigation.
   */
  async ingestVoucherLocally(
    companyId: string,
    voucher: Partial<SyncedVoucher> & {
      id: string;
      voucherType: string;
      voucherNumber: string;
      voucherDate: string;
      totalAmount: number | string;
    }
  ): Promise<void> {
    await ingestVoucherLocally(companyId, voucher);
  }

  /**
   * Full push & pull sync.
   */
  async triggerFullSync(companyId?: string): Promise<void> {
    await triggerFullSync(companyId);
  }

  /**
   * Retrieves the current sync and offline mutation status.
   */
  async getSyncStatus(companyId: string): Promise<SyncStatusInfo> {
    if (!companyId) {
      return {
        status: "IDLE",
        lastSyncAt: null,
        pendingMutationsCount: 0,
        isInitialComplete: false,
      };
    }

    const meta = await offlineDb.syncMeta.get(companyId);
    const legacyPending = await offlineDb.vouchers
      .where("status")
      .anyOf(["PENDING", "SYNCING", "FAILED"])
      .filter((v) => {
        const cid = v.payload?.company_id || v.payload?.company;
        return !cid || String(cid) === String(companyId);
      })
      .count();

    const activeOutbox = await offlineDb.outboxQueue
      .where("status")
      .anyOf(["QUEUED", "IN_FLIGHT", "FAILED"])
      .toArray();
    let outboxPendingCount = 0;
    for (const item of activeOutbox) {
      if (item.companyId) {
        if (String(item.companyId) === String(companyId)) outboxPendingCount++;
      } else {
        const op = await offlineDb.operationLog.get(item.operationId);
        const opCompanyId = op?.companyId || op?.payload?.company_id || op?.payload?.company;
        if (String(opCompanyId || "") === String(companyId)) outboxPendingCount++;
      }
    }
    const pendingCount = legacyPending + outboxPendingCount;

    const isOnline = typeof navigator !== "undefined" ? navigator.onLine : true;

    return {
      status: !isOnline ? "OFFLINE" : (meta?.syncStatus || "IDLE"),
      lastSyncAt: meta?.lastSyncAt || null,
      pendingMutationsCount: pendingCount,
      isInitialComplete: meta?.isInitialComplete || false,
      errorMessage: meta?.errorMessage,
    };
  }
}

export const syncRepository = new SyncRepository();
