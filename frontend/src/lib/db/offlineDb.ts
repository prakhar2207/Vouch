/* eslint-disable @typescript-eslint/no-explicit-any */
import Dexie, { type Table } from "dexie";
import { shouldPurgeCacheOnLogout } from "@/lib/pwa/sw-cache-policy";

export interface OfflineVoucher {
  id?: number;
  localId: string;
  voucherType: string;
  voucherNumber?: string;
  voucherDate: string;
  payload: any;
  status: "PENDING" | "SYNCING" | "SYNCED" | "FAILED";
  errorMessage?: string;
  retryCount: number;
  createdAt: number;
  syncedAt?: number;
  nextRetryAt?: number;
}

export interface MasterCache {
  key: string;
  data: any;
  updatedAt: number;
}

export interface OcrCache {
  fileHash: string;
  fileName: string;
  fileSize: number;
  result: any;
  transactions?: any[];
  openingBalance?: number | null;
  closingBalance?: number | null;
  is_synced?: boolean;
  cachedAt: number;
}

export interface SyncedVoucher {
  id: string; // server voucher UUID
  companyId: string;
  financialYearId?: string | null;
  voucherType: string; // SALES, PURCHASE, PAYMENT, RECEIPT, CONTRA, JOURNAL
  voucherNumber: string;
  voucherDate: string; // YYYY-MM-DD
  dueDate?: string | null;
  referenceNumber?: string;
  partyLedgerId?: string | null;
  partyName?: string;
  status: "DRAFT" | "POSTED" | "CANCELLED" | "REVERSED" | "SUPERSEDED" | "CORRECTED" | "PENDING_SYNC";
  version?: number;
  totalAmount: number; // numeric float/decimal representation
  roundOff?: number; // round-off adjustment (+/-)
  paymentStatus?: "PAID" | "PARTIAL" | "UNPAID" | "ALLOCATED" | "UNALLOCATED";
  paidAmount?: number;
  narration?: string;
  serverUpdatedAt: number;
  isOffline?: boolean;
  syncStatus?: "OFFLINE_PENDING" | "SYNCING" | "SYNCED" | "SYNC_FAILED" | string;
  errorMessage?: string;
}

export interface SyncedLedger {
  id: string; // ledger UUID
  companyId: string;
  name: string;
  ledgerType: string; // CUSTOMER, SUPPLIER, BANK, CASH, TAX, EXPENSE, GENERAL, PARTY
  gstin?: string;
  stateCode?: string;
  currentBalance: number;
  openingBalance: number;
  openingBalanceType: "DEBIT" | "CREDIT";
  phone?: string;
  group?: string;
  group_id?: string;
  nature?: string;
  balanceState?: string;
  displayAmount?: number;
  normalBalance?: string;
  balanceDirection?: string;
  serverUpdatedAt: number;
}

export interface SyncedProduct {
  id: string; // product UUID
  companyId: string;
  name: string;
  brand?: string;
  sku?: string;
  hsnCode?: string;
  unit: string;
  purchasePrice: number;
  salesPrice: number;
  gstRate: number;
  currentStock: number;
  reorderLevel: number;
  serverUpdatedAt: number;
}

export interface SyncMeta {
  companyId: string;
  // Legacy timestamps (kept for backwards compatibility during rollout)
  lastSyncAt?: number;
  syncCursor?: string;
  vouchersCursor?: string;
  ledgersLastSyncAt?: number;
  productsLastSyncAt?: number;
  oldestSyncedAt?: number;
  newestSyncedAt?: number;
  
  // New change feed metadata
  changeCursor?: string;
  snapshotCursor?: string;
  lastSuccessfulSyncAt?: number;
  
  syncStatus: "IDLE" | "SYNCING" | "ERROR";
  isInitialComplete: boolean;
  pendingMutationsCount: number;
  errorMessage?: string;
}

export interface AnalyticsDaily {
  id: string; // `${companyId}_${date}`
  companyId: string;
  date: string; // YYYY-MM-DD
  sales: number;
  purchases: number;
  collections: number;
  payments: number;
  salesCount: number;
  purchaseCount: number;
}

export interface AnalyticsParty {
  id: string; // `${companyId}_${partyId}`
  companyId: string;
  partyId: string;
  partyName: string;
  sales: number;
  purchases: number;
  receipts: number;
  payments: number;
  invoiceCount: number;
  lastTransactionDate: string;
  outstanding: number;
}

export interface SyncedBankTransaction {
  id: string; // bank transaction UUID
  companyId: string;
  bankLedgerId: string;
  bankLedgerName?: string;
  transactionDate: string; // YYYY-MM-DD
  valueDate?: string | null;
  description: string;
  normalizedNarration: string;
  referenceNumber: string;
  debitAmount: number;
  creditAmount: number;
  balance?: number | null;
  status: string; // UNRESOLVED, MATCHED_SUGGESTED, MATCHED_AUTO, RECONCILED, NEEDS_REVIEW, etc.
  matchedPartyId?: string | null;
  matchedPartyName?: string | null;
  matchedPartyType?: string | null;
  matchedVoucherId?: string | null;
  matchedVoucherNumber?: string | null;
  matchConfidence?: number;
  matchNotes?: string;
  isExcluded?: boolean;
  exclusionReason?: string | null;
  serverUpdatedAt: number;
}

export interface SyncedPaymentAllocation {
  id: string; // allocation UUID
  companyId: string;
  paymentVoucherId: string;
  invoiceVoucherId: string;
  allocatedAmount: number;
  serverUpdatedAt: number;
}

export interface ClientAccountingOperation {
  operationId: string;
  transactionId: string;
  companyId?: string | null;
  userId?: string | null;
  replicaId: string;
  operationType: string;
  operationClass?: string;
  payload: any;
  logicalTimestamp: number;
  parents: string[];
  payloadHash: string;
  signature?: string;
  status: "PENDING" | "SYNCED" | "COMMITTED" | "REJECTED";
  createdAt: number;
}

export interface OutboxItem {
  id?: number;
  operationId: string;
  transactionId: string;
  companyId?: string | null;
  userId?: string | null;
  status: "QUEUED" | "IN_FLIGHT" | "FAILED" | "COMPLETED";
  retryCount: number;
  lastError?: string;
  createdAt: number;
  nextRetryAt?: number;
}

export interface InboxItem {
  id?: number;
  operationId: string;
  transactionId: string;
  status: "UNAPPLIED" | "APPLIED" | "CONFLICT";
  receivedAt: number;
}

export interface SyncCursor {
  transactionId: string;
  cursor: string;
  lastSyncedAt: number;
}

export class VouchOfflineDB extends Dexie {
  vouchers!: Table<OfflineVoucher, number>;
  masters!: Table<MasterCache, string>;
  ocrCache!: Table<OcrCache, string>;
  syncedVouchers!: Table<SyncedVoucher, string>;
  syncedLedgers!: Table<SyncedLedger, string>;
  syncedProducts!: Table<SyncedProduct, string>;
  syncMeta!: Table<SyncMeta, string>;
  analyticsDaily!: Table<AnalyticsDaily, string>;
  analyticsParty!: Table<AnalyticsParty, string>;
  syncedBankTransactions!: Table<SyncedBankTransaction, string>;
  syncedPaymentAllocations!: Table<SyncedPaymentAllocation, string>;
  operationLog!: Table<ClientAccountingOperation, string>;
  outboxQueue!: Table<OutboxItem, number>;
  inboxQueue!: Table<InboxItem, number>;
  syncCursors!: Table<SyncCursor, string>;

  constructor() {
    super("VouchOfflineDB");
    this.version(1).stores({
      vouchers: "++id, localId, voucherType, status, createdAt",
      masters: "key, updatedAt",
    });
    this.version(2).stores({
      vouchers: "++id, localId, voucherType, status, createdAt",
      masters: "key, updatedAt",
      ocrCache: "fileHash, cachedAt",
    });
    this.version(3).stores({
      vouchers: "++id, localId, voucherType, status, createdAt",
      masters: "key, updatedAt",
      ocrCache: "fileHash, cachedAt",
      syncedVouchers: "id, companyId, voucherType, voucherDate, status, partyLedgerId, serverUpdatedAt, [companyId+voucherDate], [companyId+status], [companyId+voucherType]",
      syncedLedgers: "id, companyId, ledgerType, name, [companyId+ledgerType]",
      syncedProducts: "id, companyId, sku, [companyId+currentStock]",
      syncMeta: "companyId, lastSyncAt, syncStatus",
      analyticsDaily: "id, companyId, date, [companyId+date]",
      analyticsParty: "id, companyId, partyId, [companyId+partyId]",
    });
    this.version(4).stores({
      vouchers: "++id, localId, voucherType, status, createdAt",
      masters: "key, updatedAt",
      ocrCache: "fileHash, cachedAt",
      syncedVouchers: "id, companyId, voucherType, voucherDate, status, partyLedgerId, serverUpdatedAt, [companyId+voucherDate], [companyId+status], [companyId+voucherType]",
      syncedLedgers: "id, companyId, ledgerType, name, [companyId+ledgerType]",
      syncedProducts: "id, companyId, sku, [companyId+currentStock]",
      syncMeta: "companyId, lastSyncAt, syncStatus",
      analyticsDaily: "id, companyId, date, [companyId+date]",
      analyticsParty: "id, companyId, partyId, [companyId+partyId]",
      syncedBankTransactions: "id, companyId, bankLedgerId, status, transactionDate, serverUpdatedAt, [companyId+status], [companyId+bankLedgerId]",
    });
    this.version(5).stores({
      vouchers: "++id, localId, voucherType, status, createdAt",
      masters: "key, updatedAt",
      ocrCache: "fileHash, cachedAt",
      syncedVouchers: "id, companyId, voucherType, voucherDate, dueDate, status, partyLedgerId, serverUpdatedAt, [companyId+voucherDate], [companyId+status], [companyId+voucherType]",
      syncedLedgers: "id, companyId, ledgerType, name, [companyId+ledgerType]",
      syncedProducts: "id, companyId, sku, [companyId+currentStock]",
      syncMeta: "companyId, lastSyncAt, syncStatus",
      analyticsDaily: "id, companyId, date, [companyId+date]",
      analyticsParty: "id, companyId, partyId, [companyId+partyId]",
      syncedBankTransactions: "id, companyId, bankLedgerId, status, transactionDate, serverUpdatedAt, [companyId+status], [companyId+bankLedgerId]",
    });
    this.version(6).stores({
      vouchers: "++id, localId, voucherType, status, createdAt",
      masters: "key, updatedAt",
      ocrCache: "fileHash, cachedAt",
      syncedVouchers: "id, companyId, voucherType, voucherDate, dueDate, status, partyLedgerId, serverUpdatedAt, [companyId+voucherDate], [companyId+status], [companyId+voucherType]",
      syncedLedgers: "id, companyId, ledgerType, name, [companyId+ledgerType]",
      syncedProducts: "id, companyId, sku, [companyId+currentStock]",
      syncMeta: "companyId, lastSyncAt, syncStatus",
      analyticsDaily: "id, companyId, date, [companyId+date]",
      analyticsParty: "id, companyId, partyId, [companyId+partyId]",
      syncedBankTransactions: "id, companyId, bankLedgerId, status, transactionDate, serverUpdatedAt, [companyId+status], [companyId+bankLedgerId]",
      syncedPaymentAllocations: "id, companyId, paymentVoucherId, invoiceVoucherId, [companyId+paymentVoucherId], [companyId+invoiceVoucherId]"
    });
    this.version(7).stores({
      vouchers: "++id, localId, voucherType, status, createdAt",
      masters: "key, updatedAt",
      ocrCache: "fileHash, cachedAt",
      syncedVouchers: "id, companyId, voucherType, voucherDate, dueDate, status, partyLedgerId, serverUpdatedAt, [companyId+voucherDate], [companyId+status], [companyId+voucherType]",
      syncedLedgers: "id, companyId, ledgerType, name, [companyId+ledgerType]",
      syncedProducts: "id, companyId, sku, [companyId+currentStock]",
      syncMeta: "companyId, lastSyncAt, syncStatus",
      analyticsDaily: "id, companyId, date, [companyId+date]",
      analyticsParty: "id, companyId, partyId, [companyId+partyId]",
      syncedBankTransactions: "id, companyId, bankLedgerId, status, transactionDate, serverUpdatedAt, [companyId+status], [companyId+bankLedgerId]",
      syncedPaymentAllocations: "id, companyId, paymentVoucherId, invoiceVoucherId, [companyId+paymentVoucherId], [companyId+invoiceVoucherId]"
    });
    this.version(8).stores({
      vouchers: "++id, localId, voucherType, status, createdAt",
      masters: "key, updatedAt",
      ocrCache: "fileHash, cachedAt",
      syncedVouchers: "id, companyId, voucherType, voucherDate, dueDate, status, partyLedgerId, serverUpdatedAt, [companyId+voucherDate], [companyId+status], [companyId+voucherType]",
      syncedLedgers: "id, companyId, ledgerType, name, [companyId+ledgerType]",
      syncedProducts: "id, companyId, sku, [companyId+currentStock]",
      syncMeta: "companyId, lastSyncAt, syncStatus",
      analyticsDaily: "id, companyId, date, [companyId+date]",
      analyticsParty: "id, companyId, partyId, [companyId+partyId]",
      syncedBankTransactions: "id, companyId, bankLedgerId, status, transactionDate, serverUpdatedAt, [companyId+status], [companyId+bankLedgerId]",
      syncedPaymentAllocations: "id, companyId, paymentVoucherId, invoiceVoucherId, [companyId+paymentVoucherId], [companyId+invoiceVoucherId]",
      operationLog: "operationId, transactionId, replicaId, operationType, logicalTimestamp, status, [transactionId+logicalTimestamp]",
      outboxQueue: "++id, operationId, transactionId, status, retryCount, nextRetryAt",
      inboxQueue: "++id, operationId, transactionId, status, receivedAt",
      syncCursors: "transactionId, lastSyncedAt"
    });
    this.version(9).stores({
      vouchers: "++id, localId, voucherType, status, createdAt",
      masters: "key, updatedAt",
      ocrCache: "fileHash, cachedAt",
      syncedVouchers: "id, companyId, voucherType, voucherDate, dueDate, status, partyLedgerId, serverUpdatedAt, [companyId+voucherDate], [companyId+status], [companyId+voucherType]",
      syncedLedgers: "id, companyId, ledgerType, name, [companyId+ledgerType]",
      syncedProducts: "id, companyId, sku, [companyId+currentStock]",
      syncMeta: "companyId, lastSyncAt, syncStatus",
      analyticsDaily: "id, companyId, date, [companyId+date]",
      analyticsParty: "id, companyId, partyId, [companyId+partyId]",
      syncedBankTransactions: "id, companyId, bankLedgerId, status, transactionDate, serverUpdatedAt, [companyId+status], [companyId+bankLedgerId]",
      syncedPaymentAllocations: "id, companyId, paymentVoucherId, invoiceVoucherId, [companyId+paymentVoucherId], [companyId+invoiceVoucherId]",
      operationLog: "operationId, transactionId, companyId, userId, replicaId, operationType, logicalTimestamp, status, [transactionId+logicalTimestamp]",
      outboxQueue: "++id, operationId, transactionId, companyId, userId, status, retryCount, nextRetryAt",
      inboxQueue: "++id, operationId, transactionId, status, receivedAt",
      syncCursors: "transactionId, lastSyncedAt"
    });
  }
}

export const offlineDb = new VouchOfflineDB();

/**
 * Tab coordination channel to notify all open browser tabs to release
 * IndexedDB locks and flush memory buffers when a tenant switches or logs out.
 */
let coordinationChannel: BroadcastChannel | null = null;
if (typeof window !== "undefined" && "BroadcastChannel" in window) {
  try {
    coordinationChannel = new BroadcastChannel("vouch_offline_coordination");
    (coordinationChannel as unknown as { unref?: () => void }).unref?.();
    coordinationChannel.onmessage = async (event) => {
      const data = event.data;
      if (data?.type === "CLOSE_DB_CONNECTION") {
        try {
          offlineDb.close();
        } catch {}
      } else if (data?.type === "PURGE_COMPLETE") {
        try {
          if (!offlineDb.isOpen()) {
            await offlineDb.open();
          }
        } catch {}
      }
    };
  } catch {}
}

export async function ensureDbOpen(): Promise<void> {
  if (typeof window === "undefined") return;
  if (!offlineDb.isOpen()) {
    try {
      await offlineDb.open();
    } catch (err) {
      console.warn("[offlineDb] Auto-reopen error:", err);
    }
  }
}

/**
 * Safely purges offline IndexedDB and cache storage data.
 * - If targetCompanyId is supplied (company switch): purges all records belonging to that company.
 * - If targetCompanyId is omitted (logout): performs complete purge across all tables, closes connections,
 *   coordinates with open tabs, and attempts resilient database reset without blocking if another tab is active.
 */
export interface PendingOfflineSummary {
  currentUserCount: number;
  totalPendingCount: number;
  companyIds: string[];
}

export async function getPendingOfflineSummary(userId?: string | null): Promise<PendingOfflineSummary> {
  if (typeof window === "undefined") {
    return { currentUserCount: 0, totalPendingCount: 0, companyIds: [] };
  }
  try {
    if (!offlineDb.isOpen()) {
      await offlineDb.open().catch(() => {});
    }
    const pendingOutbox = await offlineDb.outboxQueue
      .where("status")
      .anyOf(["QUEUED", "IN_FLIGHT", "FAILED"])
      .toArray();
    const pendingLegacy = await offlineDb.vouchers
      .where("status")
      .anyOf(["PENDING", "SYNCING", "FAILED"])
      .toArray();

    let currentUserCount = 0;
    const companyIds = new Set<string>();

    for (const item of pendingOutbox) {
      let ownerUid = item.userId || null;
      let cid = item.companyId || "";
      if (!ownerUid || !cid) {
        const op = await offlineDb.operationLog.get(item.operationId).catch(() => undefined);
        ownerUid = ownerUid || op?.userId || null;
        cid = cid || String(op?.companyId || op?.payload?.company_id || op?.payload?.company || "");
      }
      if (cid) companyIds.add(String(cid));
      if (userId && ownerUid && String(ownerUid) === String(userId)) {
        currentUserCount += 1;
      }
    }

    for (const v of pendingLegacy) {
      const cid = String(v.payload?.company_id || v.payload?.company || "");
      const ownerUid = v.payload?.user_id ? String(v.payload.user_id) : null;
      if (cid) companyIds.add(cid);
      if (userId && (!ownerUid || ownerUid === String(userId))) {
        currentUserCount += 1;
      }
    }

    return {
      currentUserCount,
      totalPendingCount: pendingOutbox.length + pendingLegacy.length,
      companyIds: Array.from(companyIds),
    };
  } catch {
    return { currentUserCount: 0, totalPendingCount: 0, companyIds: [] };
  }
}

export async function hasPendingOfflineTransactions(companyId?: string, userId?: string | null): Promise<boolean> {
  if (typeof window === "undefined") return false;
  try {
    if (!offlineDb.isOpen()) {
      await offlineDb.open().catch(() => {});
    }
    const pendingOutbox = await offlineDb.outboxQueue
      .where("status")
      .anyOf(["QUEUED", "IN_FLIGHT", "FAILED"])
      .toArray();
    if (companyId) {
      for (const item of pendingOutbox) {
        const op = (!item.companyId || !item.userId)
          ? await offlineDb.operationLog.get(item.operationId).catch(() => undefined)
          : undefined;
        const resolvedCompanyId = String(item.companyId || op?.companyId || op?.payload?.company_id || "");
        const resolvedUserId = item.userId || op?.userId || null;
        if (resolvedCompanyId !== companyId) continue;
        if (userId && resolvedUserId && String(resolvedUserId) !== String(userId)) continue;
        return true;
      }
      const pendingLegacy = await offlineDb.vouchers
        .where("status")
        .anyOf(["PENDING", "SYNCING", "FAILED"])
        .toArray();
      return pendingLegacy.some((v) => {
        const matchesCompany = String(v.payload?.company_id || v.payload?.company || "") === companyId;
        if (!matchesCompany) return false;
        if (userId && v.payload?.user_id && String(v.payload.user_id) !== String(userId)) return false;
        return true;
      });
    }
    const summary = await getPendingOfflineSummary(userId);
    return userId ? summary.currentUserCount > 0 : summary.totalPendingCount > 0;
  } catch {
    return false;
  }
}

export async function safePurgeTenantData(
  targetCompanyId?: string | null,
  options?: { forceDestroyAll?: boolean }
): Promise<void> {
  if (typeof window === "undefined") return;

  try {
    // 1. Notify other open tabs to close their Dexie connections cleanly on full destroy
    if (!targetCompanyId && options?.forceDestroyAll && coordinationChannel) {
      try {
        coordinationChannel.postMessage({ type: "CLOSE_DB_CONNECTION", targetCompanyId });
      } catch {}
    }

    // 2. Ensure db is open only when selectively clearing tables (avoid reopening before full deleteDatabase)
    if (!options?.forceDestroyAll && !offlineDb.isOpen()) {
      await offlineDb.open().catch(() => {});
    }

    if (targetCompanyId) {
      // Scoped purge for a specific tenant during company switch
      await Promise.allSettled([
        offlineDb.syncedVouchers.where("companyId").equals(targetCompanyId).delete(),
        offlineDb.syncedLedgers.where("companyId").equals(targetCompanyId).delete(),
        offlineDb.syncedProducts.where("companyId").equals(targetCompanyId).delete(),
        offlineDb.syncedBankTransactions.where("companyId").equals(targetCompanyId).delete(),
        offlineDb.syncedPaymentAllocations.where("companyId").equals(targetCompanyId).delete(),
        offlineDb.analyticsDaily.where("companyId").equals(targetCompanyId).delete(),
        offlineDb.analyticsParty.where("companyId").equals(targetCompanyId).delete(),
        offlineDb.syncMeta.where("companyId").equals(targetCompanyId).delete(),
        offlineDb.masters.where("key").startsWith(`company_${targetCompanyId}`).delete(),
      ]);

      // PRESERVE offline outboxQueue and operationLog across tenant switches!
      // Unsynced financial transactions (QUEUED, IN_FLIGHT, FAILED) remain isolated by companyId & userId
      // and are resumed only when an authorized session returns to this company.
    } else if (options?.forceDestroyAll) {
      // Explicit full wipe requested
      if (offlineDb.isOpen()) {
        await Promise.allSettled(offlineDb.tables.map((table) => table.clear().catch(() => {})));
      }
      try {
        offlineDb.close();
      } catch {}
      const deleteIdb = (dbName: string) =>
        new Promise<void>((resolve) => {
          let finished = false;
          const timer = setTimeout(() => {
            if (!finished) {
              finished = true;
              resolve();
            }
          }, 2000);
          (timer as unknown as { unref?: () => void }).unref?.();
          try {
            const req = indexedDB.deleteDatabase(dbName);
            req.onsuccess = req.onerror = req.onblocked = () => {
              if (!finished) {
                finished = true;
                clearTimeout(timer);
                resolve();
              }
            };
          } catch {
            if (!finished) {
              finished = true;
              clearTimeout(timer);
              resolve();
            }
          }
        });
      try {
        const { ClientKeyManager } = await import("@/lib/crdt/clientKeyManager");
        await ClientKeyManager.closeAndResetVault();
      } catch {}
      await Promise.all([deleteIdb("VouchOfflineDB"), deleteIdb("VouchSecurityVault")]);
    } else {
      // Stage 4.12 Phase B: Safe Logout Purge
      // Purge all tenant read caches, inbox, cursors, and masters so no PII/accounting view leaks to the next user,
      // while PRESERVING unacknowledged financial mutations (QUEUED, IN_FLIGHT, FAILED) tagged by userId & companyId.
      await Promise.allSettled([
        offlineDb.syncedVouchers.clear().catch(() => {}),
        offlineDb.syncedLedgers.clear().catch(() => {}),
        offlineDb.syncedProducts.clear().catch(() => {}),
        offlineDb.syncedBankTransactions.clear().catch(() => {}),
        offlineDb.syncedPaymentAllocations.clear().catch(() => {}),
        offlineDb.analyticsDaily.clear().catch(() => {}),
        offlineDb.analyticsParty.clear().catch(() => {}),
        offlineDb.syncMeta.clear().catch(() => {}),
        offlineDb.masters.clear().catch(() => {}),
        offlineDb.ocrCache.clear().catch(() => {}),
        offlineDb.inboxQueue.clear().catch(() => {}),
        offlineDb.syncCursors.clear().catch(() => {}),
        offlineDb.vouchers.where("status").equals("SYNCED").delete().catch(() => {}),
        offlineDb.outboxQueue.where("status").equals("COMPLETED").delete().catch(() => {}),
      ]);

      const remainingOutbox = await offlineDb.outboxQueue.toArray().catch(() => []);
      const activeOpIds = new Set(remainingOutbox.map((item) => item.operationId));
      const allOps = await offlineDb.operationLog.toArray().catch(() => []);
      const opsToDelete = allOps
        .filter((op) => !activeOpIds.has(op.operationId) && op.status !== "PENDING")
        .map((op) => op.operationId);
      if (opsToDelete.length > 0) {
        await offlineDb.operationLog.bulkDelete(opsToDelete).catch(() => {});
      }
    }

    // 3. Purge Service Worker and CacheStorage caches (including legacy cross-origin / api caches)
    if ("caches" in window) {
      try {
        const cacheNames = await caches.keys().catch(() => []);
        for (const name of cacheNames) {
          if (shouldPurgeCacheOnLogout(name)) {
            await caches.delete(name).catch(() => {});
          }
        }
      } catch {}
    }

    // 4. Notify coordination channel that purge completed
    if (coordinationChannel) {
      try {
        coordinationChannel.postMessage({ type: "PURGE_COMPLETE", targetCompanyId });
      } catch {}
    }
  } catch (err) {
    console.error("[safePurgeTenantData] Error purging offline tenant data:", err);
  }
}
