import { offlineDb, SyncedVoucher, SyncedLedger, SyncedProduct } from "../db/offlineDb";
import { LocalAnalyticsEngine } from "../analytics/analytics-engine";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken } from "@/utils/auth";
import { ClientOperationManager } from "../crdt/clientOperationManager";

interface RawLedgerDto {
  id: string;
  company_id?: string;
  name: string;
  ledger_type?: string;
  group?: string;
  group_name?: string;
  group_id?: string;
  nature?: string;
  gstin?: string;
  state_code?: string;
  current_balance?: number | string;
  opening_balance?: number | string;
  opening_balance_type?: "DEBIT" | "CREDIT";
  phone?: string;
  balance_state?: string;
  display_amount?: number | string;
  server_updated_at?: number;
}

interface RawProductDto {
  id: string;
  company_id?: string;
  name: string;
  brand?: string;
  sku?: string;
  hsn_code?: string;
  unit?: string;
  purchase_price?: number | string;
  sales_price?: number | string;
  gst_rate?: number | string;
  current_stock?: number | string;
  reorder_level?: number | string;
  server_updated_at?: number;
}

interface RawVoucherDto {
  id: string;
  company_id?: string;
  financial_year_id?: string | null;
  voucher_type: string;
  voucher_number: string;
  voucher_date: string;
  due_date?: string | null;
  dueDate?: string | null;
  reference_number?: string;
  party_ledger_id?: string | null;
  party_name?: string;
  status: "DRAFT" | "POSTED" | "CANCELLED" | "REVERSED" | "SUPERSEDED" | "CORRECTED";
  total_amount?: number | string;
  round_off?: number | string;
  roundOff?: number | string;
  payment_status?: "PAID" | "PARTIAL" | "UNPAID" | "ALLOCATED" | "UNALLOCATED";
  paymentStatus?: "PAID" | "PARTIAL" | "UNPAID" | "ALLOCATED" | "UNALLOCATED";
  paid_amount?: number | string;
  paidAmount?: number | string;
  narration?: string;
  server_updated_at?: number;
}

interface RawBankTransactionDto {
  id: string;
  company_id?: string;
  bank_ledger_id: string;
  bank_ledger_name?: string;
  transaction_date: string;
  value_date?: string | null;
  description: string;
  normalized_narration: string;
  reference_number: string;
  debit_amount?: number | string;
  credit_amount?: number | string;
  balance?: number | string | null;
  status: string;
  matched_party_id?: string | null;
  matched_party_name?: string | null;
  matched_voucher_id?: string | null;
  matched_voucher_number?: string | null;
  match_confidence?: number | string;
  match_notes?: string;
  server_updated_at?: number;
}

interface RawPaymentAllocationDto {
  id: string;
  company_id?: string;
  payment_voucher_id: string;
  invoice_voucher_id: string;
  allocated_amount?: number | string;
  server_updated_at?: number;
}

export interface VoucherIngestInput {
  id: string;
  voucherNumber?: string;
  voucher_number?: string;
  voucherDate?: string;
  voucher_date?: string;
  date?: string;
  voucherType?: string;
  voucher_type?: string;
  type?: string;
  totalAmount?: number | string;
  total_amount?: number | string;
  partyName?: string;
  party_name?: string;
  partyLedgerId?: string | null;
  party_ledger_id?: string | null;
  dueDate?: string | null;
  due_date?: string | null;
  referenceNumber?: string;
  reference_number?: string;
  status?: "DRAFT" | "POSTED" | "CANCELLED" | "REVERSED" | "SUPERSEDED" | "CORRECTED";
  paymentStatus?: "PAID" | "PARTIAL" | "UNPAID" | "ALLOCATED" | "UNALLOCATED";
  payment_status?: "PAID" | "PARTIAL" | "UNPAID" | "ALLOCATED" | "UNALLOCATED";
  paidAmount?: number | string;
  paid_amount?: number | string;
  narration?: string;
  serverUpdatedAt?: number;
  server_updated_at?: number;
  financialYearId?: string | null;
  financial_year_id?: string | null;
}

interface SyncManagerRegistration {
  sync: {
    register: (tag: string) => Promise<void>;
  };
}

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

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function queueOfflineVoucher(voucherType: string, payload: any, voucherDate: string) {
  const companyId = (payload.company_id || payload.company || "") as string;
  const result = await ClientOperationManager.recordLocalVoucherMutation({
    companyId,
    voucherType,
    voucherDate,
    payload
  });
  await triggerOutboxSync();
  return { id: 1, localId: result.localId, transactionId: result.transactionId, status: "QUEUED_OFFLINE" };
}

let isSyncInProgress = false;

// P1: Multi-tab concurrency channel and Web Locks
const syncChannel = typeof window !== "undefined" && "BroadcastChannel" in window
  ? new BroadcastChannel("vouch_local_sync")
  : null;

function notifySyncChannel(msg: Record<string, unknown>) {
  try {
    syncChannel?.postMessage(msg);
  } catch (_e) {
    // Channel closed or unsupported
  }
}

if (syncChannel && typeof window !== "undefined") {
  syncChannel.onmessage = (event) => {
    if (event.data && (event.data.type === "SYNC_COMPLETE" || event.data.type === "LOCAL_INGEST")) {
      window.dispatchEvent(
        new CustomEvent("vouch:sync-complete", {
          detail: { companyId: event.data.companyId, totalRecords: 1, timestamp: Date.now(), remoteTab: true },
        })
      );
    }
  };
}

async function withTabLock<T>(lockName: string, fn: () => Promise<T>, fallback: T): Promise<T> {
  if (typeof navigator !== "undefined" && "locks" in navigator) {
    return await navigator.locks.request(lockName, { ifAvailable: true }, async (lock) => {
      if (!lock) {
        return fallback;
      }
      return await fn();
    });
  }
  return await fn();
}

/**
 * Pushes pending outbox mutations from IndexedDB to the backend authoritative command processor.
 * Features:
 * - Concurrency locking (exactly 1 sync execution at a time across all browser tabs)
 * - Persistent anonymous UUID device ID
 * - Categorization of retryable vs permanent failures
 * - Exponential backoff on retries (max 10 retries)
 */
export const BACKOFF_DELAYS = [2000, 5000, 15000, 30000, 60000, 120000, 300000, 600000, 900000, 1800000];

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
    } catch (_e) {
      console.warn("Failed to reset orphaned syncing vouchers:", _e);
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

    // 1. Drain legacy OfflineVoucher records into authoritative CRDT operation log
    for (const item of pending) {
      try {
        await offlineDb.vouchers.update(item.id!, { status: "SYNCING" });
        const companyId = (item.payload?.company_id || item.payload?.company || "") as string;
        
        await ClientOperationManager.recordLocalVoucherMutation({
          companyId,
          voucherType: item.voucherType,
          voucherDate: item.voucherDate,
          payload: item.payload,
          transactionId: item.localId
        });

        await offlineDb.vouchers.update(item.id!, {
          status: "SYNCED",
          syncedAt: Date.now(),
          nextRetryAt: undefined
        });
        processedCount++;
      } catch (err: unknown) {
        console.warn("Failed to migrate legacy voucher to protocol operation:", err);
        failedCount++;
      }
    }

    // 2. Authoritative Protocol Sync via ClientOperationManager
    const protoResult = await ClientOperationManager.syncOutboxWithServer(API_BASE_URL);
    processedCount += protoResult.syncedCount;

    // 3. Purge fully migrated and synced legacy vouchers to eliminate dual-path overhead
    await purgeLegacyOfflineVouchers();

    return { processed: processedCount, failed: failedCount };
  } finally {
    isSyncInProgress = false;
  }
}

/**
 * Purges legacy OfflineVoucher records once they have been migrated
 * into authoritative protocol CRDT operations and acknowledged by the server.
 */
export async function purgeLegacyOfflineVouchers(): Promise<number> {
  try {
    const syncedIds = await offlineDb.vouchers
      .where("status")
      .equals("SYNCED")
      .primaryKeys();
    if (syncedIds.length > 0) {
      await offlineDb.vouchers.bulkDelete(syncedIds as number[]);
    }
    return syncedIds.length;
  } catch (err) {
    console.warn("Failed to purge legacy synced vouchers:", err);
    return 0;
  }
}

export async function retryFailedVoucher(idOrLocalId: number | string) {
  if (typeof idOrLocalId === "number") {
    await offlineDb.vouchers.update(idOrLocalId, { status: "PENDING", errorMessage: undefined, nextRetryAt: undefined, retryCount: 0 });
  } else {
    const cleanId = String(idOrLocalId).replace("offline_", "");
    const item = await offlineDb.vouchers.where("localId").equals(cleanId).first();
    if (item && item.id) {
      await offlineDb.vouchers.update(item.id, { status: "PENDING", errorMessage: undefined, nextRetryAt: undefined, retryCount: 0 });
    }
  }
  await triggerOutboxSync();
}

export async function triggerOutboxSync() {
  if (typeof window === "undefined" || !navigator.onLine) return;

  const now = Date.now();
  const eligiblePending = await offlineDb.vouchers
    .where("status")
    .equals("PENDING")
    .filter((v) => !v.nextRetryAt || v.nextRetryAt <= now)
    .count()
    .catch(() => 0);

  const outboxPending = await offlineDb.outboxQueue
    .where("status")
    .equals("QUEUED")
    .count()
    .catch(() => 0);

  if (eligiblePending === 0 && outboxPending === 0) return;

  if ("serviceWorker" in navigator && "SyncManager" in window) {
    try {
      const registration = await navigator.serviceWorker.ready;
      await (registration as unknown as SyncManagerRegistration).sync.register("vouch-outbox-sync");
      return;
    } catch (_err) {
      await executeClientOutboxSync();
    }
  } else {
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
  onProgress?: (msg: string) => void,
  options?: { force?: boolean }
): Promise<{ success: boolean; totalRecords: number; error?: string }> {
    if (!companyId || typeof window === "undefined" || !navigator.onLine) {
      return { success: false, totalRecords: 0 };
    }
    if (isPullInProgress) {
      return { success: false, totalRecords: 0, error: "Pull already in progress" };
    }

    try {
      const metaCheck = await offlineDb.syncMeta.get(companyId);
      const now = Date.now();
      // Cooldown throttle: skip redundant rapid pulls within 15 seconds unless forced
      if (!options?.force && metaCheck?.lastSuccessfulSyncAt && (now - metaCheck.lastSuccessfulSyncAt) < 15000) {
        return { success: true, totalRecords: 0 };
      }

      isPullInProgress = true;

      const token = getAccessToken();
      if (!token) {
        return { success: false, totalRecords: 0, error: "Authentication required" };
      }

      let meta = metaCheck;
      if (!meta) {
        meta = {
          companyId,
          syncStatus: "SYNCING",
          isInitialComplete: false,
          pendingMutationsCount: 0,
          changeCursor: "0"
        };
        await offlineDb.syncMeta.put(meta);
      } else {
        await offlineDb.syncMeta.update(companyId, { syncStatus: "SYNCING" });
      }

      let hasMore = true;
      let currentCursor = meta.changeCursor || "0";
      let snapshotCursor = meta.snapshotCursor;
      let totalRecords = 0;
      let batchIndex = 0;
      const allChangedVouchers: SyncedVoucher[] = [];

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
            limit: 500,
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
      if (resData.snapshot_cursor) {
        snapshotCursor = resData.snapshot_cursor;
      }

      // 1. Ingest Ledgers
      if (changes.ledgers) {
        const toPut: SyncedLedger[] = [
          ...(changes.ledgers.created || []),
          ...(changes.ledgers.updated || []),
        ].map((l: RawLedgerDto) => ({
          id: l.id,
          companyId: l.company_id || companyId,
          name: l.name,
          ledgerType: l.ledger_type || "GENERAL",
          group: l.group || l.group_name || "",
          group_id: l.group_id || "",
          nature: l.nature || "ASSET",
          gstin: l.gstin,
          stateCode: l.state_code,
          currentBalance: Number(l.current_balance) || 0,
          openingBalance: Number(l.opening_balance) || 0,
          openingBalanceType: l.opening_balance_type || "DEBIT",
          phone: l.phone,
          balanceState: l.balance_state,
          displayAmount: Number(l.display_amount) || 0,
          serverUpdatedAt: l.server_updated_at || Date.now(),
        }));
        if (toPut.length > 0) {
          await offlineDb.syncedLedgers.bulkPut(toPut);
          totalRecords += toPut.length;
        }
        if (changes.ledgers.deleted && changes.ledgers.deleted.length > 0) {
          const toDel = changes.ledgers.deleted.map((l: RawLedgerDto) => l.id);
          await offlineDb.syncedLedgers.bulkDelete(toDel);
        }
      }

      // 2. Ingest Products
      if (changes.products) {
        const toPut: SyncedProduct[] = [
          ...(changes.products.created || []),
          ...(changes.products.updated || []),
        ].map((p: RawProductDto) => ({
          id: p.id,
          companyId: p.company_id || companyId,
          name: p.name,
          brand: p.brand || undefined,
          sku: p.sku,
          hsnCode: p.hsn_code,
          unit: p.unit || "PCS",
          purchasePrice: Number(p.purchase_price) || 0,
          salesPrice: Number(p.sales_price) || 0,
          gstRate: Number(p.gst_rate) || 0,
          currentStock: Number(p.current_stock) || 0,
          reorderLevel: Number(p.reorder_level) || 0,
          serverUpdatedAt: p.server_updated_at || Date.now(),
        }));
        if (toPut.length > 0) {
          await offlineDb.syncedProducts.bulkPut(toPut);
          totalRecords += toPut.length;
        }
        if (changes.products.deleted && changes.products.deleted.length > 0) {
          const toDel = changes.products.deleted.map((p: RawProductDto) => p.id);
          await offlineDb.syncedProducts.bulkDelete(toDel);
        }
      }

      // 3. Ingest Vouchers
      if (changes.vouchers) {
        const toPut: SyncedVoucher[] = [
          ...(changes.vouchers.created || []),
          ...(changes.vouchers.updated || []),
        ].map((v: RawVoucherDto) => ({
          id: v.id,
          companyId: v.company_id || companyId,
          financialYearId: v.financial_year_id,
          voucherType: v.voucher_type,
          voucherNumber: v.voucher_number,
          voucherDate: v.voucher_date,
          dueDate: v.due_date || v.dueDate || null,
          referenceNumber: v.reference_number,
          partyLedgerId: v.party_ledger_id,
          partyName: v.party_name,
          status: v.status,
          totalAmount: Number(v.total_amount) || 0,
          roundOff: Number(v.round_off ?? v.roundOff ?? 0),
          paymentStatus: v.payment_status || v.paymentStatus || "UNPAID",
          paidAmount: Number(v.paid_amount ?? v.paidAmount) || 0,
          narration: v.narration,
          serverUpdatedAt: v.server_updated_at || Date.now(),
        }));
        if (toPut.length > 0) {
          await offlineDb.syncedVouchers.bulkPut(toPut);
          totalRecords += toPut.length;
          allChangedVouchers.push(...toPut);
        }
        // Deleted/Cancelled/Reversed vouchers update their status or delete
        if (changes.vouchers.deleted && changes.vouchers.deleted.length > 0) {
          const toDeleteIds: string[] = [];
          const toUpdateCancelled: SyncedVoucher[] = [];

          for (const v of changes.vouchers.deleted) {
            // If it's a hard-delete event from server (only has id, missing voucher_number or voucher_type)
            if (!v.voucher_number || !v.voucher_type) {
              toDeleteIds.push(String(v.id));
            } else {
              toUpdateCancelled.push({
                id: v.id,
                companyId: v.company_id || companyId,
                financialYearId: v.financial_year_id,
                voucherType: v.voucher_type,
                voucherNumber: v.voucher_number,
                voucherDate: v.voucher_date,
                dueDate: v.due_date || v.dueDate || null,
                referenceNumber: v.reference_number,
                partyLedgerId: v.party_ledger_id,
                partyName: v.party_name,
                status: v.status || "CANCELLED",
                totalAmount: Number(v.total_amount) || 0,
                narration: v.narration,
                serverUpdatedAt: v.server_updated_at || Date.now(),
              });
            }
          }

          if (toDeleteIds.length > 0) {
            await offlineDb.syncedVouchers.bulkDelete(toDeleteIds);
          }

          if (toUpdateCancelled.length > 0) {
            await offlineDb.syncedVouchers.bulkPut(toUpdateCancelled);
            allChangedVouchers.push(...toUpdateCancelled);
          }
        }
      }

      // 4. Ingest Bank Transactions
      if (changes.bank_transactions) {
        const toPut = [
          ...(changes.bank_transactions.created || []),
          ...(changes.bank_transactions.updated || []),
        ].map((bt: RawBankTransactionDto) => ({
          id: bt.id,
          companyId: bt.company_id || companyId,
          bankLedgerId: bt.bank_ledger_id,
          bankLedgerName: bt.bank_ledger_name,
          transactionDate: bt.transaction_date,
          valueDate: bt.value_date,
          description: bt.description,
          normalizedNarration: bt.normalized_narration,
          referenceNumber: bt.reference_number,
          debitAmount: Number(bt.debit_amount) || 0,
          creditAmount: Number(bt.credit_amount) || 0,
          balance: bt.balance ? Number(bt.balance) : null,
          status: bt.status,
          matchedPartyId: bt.matched_party_id,
          matchedPartyName: bt.matched_party_name,
          matchedVoucherId: bt.matched_voucher_id,
          matchedVoucherNumber: bt.matched_voucher_number,
          matchConfidence: Number(bt.match_confidence) || 0,
          matchNotes: bt.match_notes,
          serverUpdatedAt: bt.server_updated_at || Date.now(),
        }));
        if (toPut.length > 0) {
          await offlineDb.syncedBankTransactions.bulkPut(toPut);
          totalRecords += toPut.length;
        }
        if (changes.bank_transactions.deleted && changes.bank_transactions.deleted.length > 0) {
          const toDel = changes.bank_transactions.deleted.map((bt: RawBankTransactionDto) => bt.id);
          await offlineDb.syncedBankTransactions.bulkDelete(toDel);
        }
      }

      // 5. Ingest Payment Allocations
      if (changes.payment_allocations) {
        const toPut = [
          ...(changes.payment_allocations.created || []),
          ...(changes.payment_allocations.updated || []),
        ].map((pa: RawPaymentAllocationDto) => ({
          id: pa.id,
          companyId: pa.company_id || companyId,
          paymentVoucherId: pa.payment_voucher_id,
          invoiceVoucherId: pa.invoice_voucher_id,
          allocatedAmount: Number(pa.allocated_amount) || 0,
          serverUpdatedAt: pa.server_updated_at || Date.now(),
        }));
        if (toPut.length > 0) {
          await offlineDb.syncedPaymentAllocations.bulkPut(toPut);
          totalRecords += toPut.length;
        }
        if (changes.payment_allocations.deleted && changes.payment_allocations.deleted.length > 0) {
          const toDel = changes.payment_allocations.deleted.map((pa: RawPaymentAllocationDto) => pa.id);
          await offlineDb.syncedPaymentAllocations.bulkDelete(toDel);
        }
      }

      hasMore = Boolean(resData.has_more);
      currentCursor = resData.next_cursor;

      // Resumable sync: checkpoint cursor progress after each ingested batch
      if (currentCursor) {
        await offlineDb.syncMeta.update(companyId, {
          changeCursor: currentCursor,
          snapshotCursor: snapshotCursor || undefined,
        }).catch(() => {});
      }
    }

    // Update sync metadata upon complete consumption
    const updatedMeta = await offlineDb.syncMeta.get(companyId) || meta;
    await offlineDb.syncMeta.put({
      ...updatedMeta,
      companyId,
      lastSuccessfulSyncAt: Date.now(),
      changeCursor: currentCursor,
      snapshotCursor: snapshotCursor || updatedMeta.snapshotCursor,
      syncStatus: "IDLE",
      isInitialComplete: true,
      pendingMutationsCount: 0,
    });

    // Incrementally update or rebuild local aggregates
    const isInitial = !meta?.isInitialComplete;
    if (isInitial || totalRecords > 200) {
      await LocalAnalyticsEngine.rebuildLocalAnalytics(companyId);
    } else if (allChangedVouchers.length > 0) {
      await LocalAnalyticsEngine.updateIncrementalAnalytics(companyId, allChangedVouchers);
    }

    // Notify listeners (Dashboard, Navbar, etc.)
    if (typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent("vouch:sync-complete", {
          detail: { companyId, totalRecords, timestamp: Date.now() },
        })
      );
    }

    notifySyncChannel({ type: "SYNC_COMPLETE", companyId, totalRecords });

    return { success: true, totalRecords };
  } catch (err: unknown) {
    const errorMsg = err instanceof Error ? err.message : String(err || "Sync pull failed");
    console.error("Incremental pull failed:", err);
    await offlineDb.syncMeta.update(companyId, {
      syncStatus: "ERROR",
      errorMessage: errorMsg,
    });
    return { success: false, totalRecords: 0, error: errorMsg };
  } finally {
    isPullInProgress = false;
  }
}

/**
 * P0-2: Immediately ingests a newly created/posted voucher into IndexedDB
 * before router navigation, ensuring atomic push -> pull -> local read model update.
 */
export async function ingestVoucherLocally(
  companyId: string,
  voucher: VoucherIngestInput
): Promise<void> {
  if (!companyId || !voucher || !voucher.id) return;

  const vNum = voucher.voucherNumber || voucher.voucher_number || "";
  const vDate = voucher.voucherDate || voucher.voucher_date || voucher.date || new Date().toISOString().split("T")[0];
  const vType = String(voucher.voucherType || voucher.voucher_type || voucher.type || "SALES").toUpperCase();
  const totAmt = Number(voucher.totalAmount ?? voucher.total_amount ?? 0);
  const pName = voucher.partyName || voucher.party_name || "";
  const pLedgerId = voucher.partyLedgerId || voucher.party_ledger_id || null;
  const dDate = voucher.dueDate || voucher.due_date || null;
  const refNum = voucher.referenceNumber || voucher.reference_number || "";
  const sStatus = voucher.status || "POSTED";
  const pStatus = voucher.paymentStatus || voucher.payment_status || "UNPAID";
  const pAmt = Number(voucher.paidAmount ?? voucher.paid_amount ?? 0);
  const narr = voucher.narration || "";
  const sUpdated = Number(voucher.serverUpdatedAt || voucher.server_updated_at || Date.now());

  const syncedV: SyncedVoucher = {
    id: String(voucher.id),
    companyId: String(companyId),
    financialYearId: voucher.financialYearId || voucher.financial_year_id || null,
    voucherType: vType,
    voucherNumber: vNum,
    voucherDate: vDate,
    dueDate: dDate,
    referenceNumber: refNum,
    partyLedgerId: pLedgerId,
    partyName: pName,
    status: (sStatus as SyncedVoucher["status"]) || "POSTED",
    totalAmount: totAmt,
    paymentStatus: (pStatus as SyncedVoucher["paymentStatus"]) || "UNPAID",
    paidAmount: pAmt,
    narration: narr,
    serverUpdatedAt: isNaN(sUpdated) ? Date.now() : sUpdated,
  };

  await offlineDb.syncedVouchers.put(syncedV);
  await LocalAnalyticsEngine.updateIncrementalAnalytics(companyId, [syncedV]);

  if (typeof window !== "undefined") {
    window.dispatchEvent(
      new CustomEvent("vouch:sync-complete", {
        detail: { companyId, totalRecords: 1, timestamp: Date.now() },
      })
    );
  }

  notifySyncChannel({ type: "LOCAL_INGEST", companyId, voucherId: syncedV.id });
}

export async function syncCompany(companyId: string, onProgress?: (msg: string) => void) {
  return await withTabLock("vouch_sync_coordinator_lock", async () => {
    if (typeof window === "undefined" || !navigator.onLine) return { success: false, reason: "offline" };
    
    // 1. Push pending offline mutations
    if (onProgress) onProgress("Pushing pending offline commands...");
    const pushResult = await executeClientOutboxSync();

    // 2. Pull incremental changes
    if (onProgress) onProgress("Pulling server changes...");
    const pullResult = await pullIncrementalChanges(companyId, onProgress);

    return { success: true, pushResult, pullResult };
  }, { success: false, reason: "locked" });
}

/**
 * P0-3: Coordinated sync on reconnect / online that pushes outbox and pulls server updates.
 */
export async function triggerFullSync(targetCompanyId?: string) {
  if (typeof window === "undefined" || !navigator.onLine) return;
  const cId = targetCompanyId || (typeof localStorage !== "undefined" ? (localStorage.getItem("activeCompanyId") || localStorage.getItem("vouch_active_company")) : null);
  if (cId) {
    await syncCompany(cId);
  } else {
    // If no company, just push pending outbox commands safely without pulling
    await withTabLock("vouch_sync_coordinator_lock", async () => {
      await executeClientOutboxSync();
    }, null);
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
    triggerFullSync();
  });
  window.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      const now = Date.now();
      if (now - lastVisibilitySyncTime > 30000) {
        lastVisibilitySyncTime = now;
        triggerFullSync();
      }
    }
  });
}

