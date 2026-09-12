import { offlineDb } from "../db/offlineDb";
import { executeClientOutboxSync, pullIncrementalChanges } from "../sync/sync-worker";

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
  async triggerSync(companyId: string): Promise<boolean> {
    if (!companyId) return false;
    try {
      await executeClientOutboxSync();
      const pullRes = await pullIncrementalChanges(companyId);
      return pullRes.success;
    } catch (e) {
      console.warn("[SyncRepo] Sync failed:", e);
      return false;
    }
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
    const pendingCount = await offlineDb.vouchers
      .where("status")
      .anyOf(["PENDING", "SYNCING", "FAILED"])
      .count();

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
