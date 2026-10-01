import { offlineDb, type ClientAccountingOperation, type OutboxItem, type InboxItem, type SyncedVoucher } from "../db/offlineDb";
import { ClientKeyManager } from "./clientKeyManager";
import { getAccessToken } from "@/utils/auth";
import { API_BASE_URL } from "@/utils/api";

export interface VoucherMutationParams {
  companyId: string;
  voucherType: "SALES" | "PURCHASE" | "PAYMENT" | "RECEIPT" | "CONTRA" | "JOURNAL" | "CREDIT_NOTE" | "DEBIT_NOTE" | string;
  voucherDate: string;
  payload: any;
  transactionId?: string;
}

export class ClientOperationManager {
  private static syncChannel = typeof window !== "undefined" && "BroadcastChannel" in window
    ? new BroadcastChannel("vouch_local_sync")
    : null;

  public static getReplicaId(): string {
    return ClientKeyManager.getReplicaId();
  }

  /**
   * Unified authoritative entry point for recording local voucher mutations offline.
   * Generates a Canonical Transaction, creates a signed AccountingOperation,
   * stores to IndexedDB operationLog, updates local projections (vouchers, products, ledgers),
   * and queues to Outbox for protocol CRDT merge.
   */
  public static async recordLocalVoucherMutation(params: VoucherMutationParams): Promise<{
    localId: string;
    transactionId: string;
    operationId: string;
    status: string;
  }> {
    const replicaId = this.getReplicaId();
    const timestamp = Date.now();
    const localId = typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `cmd-${timestamp}-${Math.random().toString(36).substring(2, 9)}`;

    const transactionId = params.transactionId || `TX-${params.voucherType.toUpperCase()}-${localId.substring(0, 10).toUpperCase()}`;

    // 1. Determine causal parents
    const existingOps = await offlineDb.operationLog
      .where("transactionId")
      .equals(transactionId)
      .sortBy("logicalTimestamp");
    const parents = existingOps.length > 0 ? [existingOps[existingOps.length - 1].operationId] : [];
    const logicalTimestamp = existingOps.length > 0 ? existingOps[existingOps.length - 1].logicalTimestamp + 1 : 1;

    // 2. Map voucherType to protocol OperationType
    let operationType = "TRANSACTION_ISSUED";
    let operationClass = "CAUSAL";
    const vTypeUpper = params.voucherType.toUpperCase();
    if (vTypeUpper === "PURCHASE") {
      operationType = "PURCHASE_INVOICE_CREATED";
    } else if (vTypeUpper === "PAYMENT" || vTypeUpper === "RECEIPT") {
      operationType = "PAYMENT_ALLOCATED";
      operationClass = "COMMUTATIVE";
    } else if (vTypeUpper === "CREDIT_NOTE") {
      operationType = "CREDIT_NOTE_ISSUED";
      operationClass = "COMPENSATING";
    } else if (vTypeUpper === "DEBIT_NOTE") {
      operationType = "DEBIT_NOTE_ISSUED";
      operationClass = "COMPENSATING";
    } else if (vTypeUpper === "CONTRA") {
      operationType = "CONTRA_CREATED";
      operationClass = "COMMUTATIVE";
    } else if (vTypeUpper === "JOURNAL") {
      operationType = "JOURNAL_CREATED";
    }

    // 3. Compute deterministic Canonical Transaction Hash
    const canonicalEnvelope = {
      protocol_version: "1.0",
      transaction_id: transactionId,
      transaction_type: params.voucherType.toUpperCase(),
      company_id: params.companyId,
      issued_at: params.voucherDate,
      payload: params.payload
    };
    const canonicalTxHash = await this.sha256(JSON.stringify(canonicalEnvelope));

    // 4. Construct AccountingOperation and sign with Ed25519
    const randomHex = Math.random().toString(36).substring(2, 10).toUpperCase();
    const operationId = `OP-CLI-${randomHex}`;

    const opPayload = {
      ...params.payload,
      company_id: params.companyId,
      voucher_type: params.voucherType,
      voucher_date: params.voucherDate,
      canonical_tx_hash: canonicalTxHash
    };

    const opContentToHash = JSON.stringify({
      operationId,
      transactionId,
      replicaId,
      operationType,
      payload: opPayload,
      logicalTimestamp,
      parents
    });
    const payloadHash = await this.sha256(opContentToHash);

    // Cryptographic Ed25519 signing using ClientKeyManager
    let signature = "";
    try {
      signature = await ClientKeyManager.signPayloadHash(payloadHash);
    } catch (sigErr) {
      console.warn("Could not sign operation with Ed25519; proceeding with digest hash:", sigErr);
      signature = payloadHash;
    }

    const op: ClientAccountingOperation = {
      operationId,
      transactionId,
      replicaId,
      operationType,
      operationClass,
      payload: opPayload,
      logicalTimestamp,
      parents,
      payloadHash,
      signature,
      status: "PENDING",
      createdAt: timestamp
    };

    // 5. Store in local Operation Log and Outbox Queue
    await offlineDb.operationLog.put(op);
    await offlineDb.outboxQueue.add({
      operationId,
      transactionId,
      status: "QUEUED",
      retryCount: 0,
      createdAt: timestamp,
      nextRetryAt: timestamp
    });

    // 6. Project mutation immediately into local IndexedDB projections
    await this.applyLocalProjections({
      localId,
      transactionId,
      companyId: params.companyId,
      voucherType: params.voucherType,
      voucherDate: params.voucherDate,
      payload: params.payload
    });

    // 7. Notify other tabs & UI via BroadcastChannel & DOM events
    this.broadcastLocalMutation(params.companyId);

    // 8. Trigger background sync if online
    if (typeof navigator !== "undefined" && navigator.onLine) {
      this.syncOutboxWithServer().catch(err => console.warn("Background sync error:", err));
    }

    return {
      localId,
      transactionId,
      operationId,
      status: "QUEUED_OFFLINE"
    };
  }

  /**
   * Applies the local operation onto IndexedDB synced tables (syncedVouchers, syncedProducts, syncedLedgers)
   * so the offline UI reflects state changes immediately without waiting for server sync.
   */
  private static async applyLocalProjections(params: {
    localId: string;
    transactionId: string;
    companyId: string;
    voucherType: string;
    voucherDate: string;
    payload: any;
  }) {
    try {
      const p = params.payload;
      const totalAmount = Number(p.total_amount || p.grand_total || p.totalAmount || 0);
      const partyName = p.party_name || p.partyName || p.customer_name || p.supplier_name || "Party";
      const partyLedgerId = p.party_ledger_id || p.partyLedgerId || p.party_id || null;

      // Projection 1: Local SyncedVoucher
      const projectedVoucher: SyncedVoucher = {
        id: params.localId,
        companyId: params.companyId,
        voucherType: params.voucherType.toUpperCase(),
        voucherNumber: params.transactionId,
        voucherDate: params.voucherDate,
        dueDate: p.due_date || params.voucherDate,
        partyLedgerId,
        partyName,
        status: "POSTED",
        totalAmount,
        narration: p.narration || `Created offline via Vouch Protocol`,
        serverUpdatedAt: Date.now()
      };
      await offlineDb.syncedVouchers.put(projectedVoucher);

      // Projection 2: Local Product Inventory Movements
      const items = p.items || [];
      if (Array.isArray(items)) {
        for (const item of items) {
          const productId = item.product_id || item.productId;
          const qty = Number(item.quantity || 0);
          if (productId && qty > 0) {
            const product = await offlineDb.syncedProducts.get(productId);
            if (product) {
              const delta = params.voucherType.toUpperCase() === "SALES" ? -qty : (params.voucherType.toUpperCase() === "PURCHASE" ? qty : 0);
              const newStock = Math.max(0, (product.currentStock || 0) + delta);
              await offlineDb.syncedProducts.update(productId, {
                currentStock: newStock,
                serverUpdatedAt: Date.now()
              });
            }
          }
        }
      }

      // Projection 3: Local Party Ledger Balance
      if (partyLedgerId) {
        const ledger = await offlineDb.syncedLedgers.get(partyLedgerId);
        if (ledger) {
          const isSales = params.voucherType.toUpperCase() === "SALES";
          const isPurchase = params.voucherType.toUpperCase() === "PURCHASE";
          const delta = isSales ? totalAmount : (isPurchase ? -totalAmount : 0);
          await offlineDb.syncedLedgers.update(partyLedgerId, {
            currentBalance: (ledger.currentBalance || 0) + delta,
            serverUpdatedAt: Date.now()
          });
        }
      }
    } catch (projErr) {
      console.warn("Failed to apply local projection:", projErr);
    }
  }

  private static broadcastLocalMutation(companyId: string) {
    try {
      this.syncChannel?.postMessage({ type: "LOCAL_INGEST", companyId });
      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("vouch:sync-complete", {
            detail: { companyId, totalRecords: 1, timestamp: Date.now(), localMutation: true }
          })
        );
      }
    } catch (e) {
      // Ignore broadcast errors
    }
  }

  /**
   * Flushes queued outbox operations to the Vouch backend protocol endpoint.
   */
  public static async syncOutboxWithServer(apiBaseUrl?: string): Promise<{
    syncedCount: number;
    receivedCount: number;
    status: string;
  }> {
    if (typeof navigator !== "undefined" && !navigator.onLine) {
      return { syncedCount: 0, receivedCount: 0, status: "OFFLINE" };
    }

    const baseUrl = apiBaseUrl || API_BASE_URL || "";
    const queued = await offlineDb.outboxQueue
      .where("status")
      .equals("QUEUED")
      .toArray();

    if (queued.length === 0) {
      return { syncedCount: 0, receivedCount: 0, status: "IDLE" };
    }

    const token = getAccessToken();
    const replicaId = this.getReplicaId();

    // Group outbox items by transactionId
    const byTx: Record<string, OutboxItem[]> = {};
    for (const item of queued) {
      if (!byTx[item.transactionId]) byTx[item.transactionId] = [];
      byTx[item.transactionId].push(item);
    }

    let totalSynced = 0;
    let totalReceived = 0;

    for (const [txId, items] of Object.entries(byTx)) {
      const opIds = items.map(i => i.operationId);
      const ops = await offlineDb.operationLog.where("operationId").anyOf(opIds).toArray();
      if (ops.length === 0) continue;

      const firstOp = ops[0];
      const companyId = firstOp.payload?.company_id || firstOp.payload?.company || "";
      const canonicalTxHash = firstOp.payload?.canonical_tx_hash || await this.sha256(`TX-${txId}`);

      // Ensure device is registered with server
      if (companyId && token) {
        try {
          await ClientKeyManager.registerDeviceWithServer({
            companyId,
            accessToken: token,
            apiBaseUrl: baseUrl
          });
        } catch (regErr) {
          console.warn("Device registration check failed, proceeding with sync:", regErr);
        }
      }

      try {
        const payload = {
          transaction_id: txId,
          client_replica_id: replicaId,
          company_id: companyId,
          canonical_tx_hash: canonicalTxHash,
          client_operations: ops.map(o => ({
            operation_id: o.operationId,
            transaction_id: o.transactionId,
            replica_id: o.replicaId,
            operation_type: o.operationType,
            operation_class: o.operationClass,
            payload: o.payload,
            logical_timestamp: o.logicalTimestamp,
            parents: o.parents,
            signature: o.signature
          }))
        };

        const headers: Record<string, string> = { "Content-Type": "application/json" };
        if (token) {
          headers["Authorization"] = `Bearer ${token}`;
        }
        if (companyId) {
          headers["X-Company-ID"] = companyId;
        }

        const res = await fetch(`${baseUrl}/api/v1/protocol/sync/`, {
          method: "POST",
          headers,
          body: JSON.stringify(payload)
        });

        if (res.ok) {
          const data = await res.json();
          if (data.status === "SYNC_SUCCESS") {
            // Mark items as COMPLETED
            for (const item of items) {
              if (item.id) {
                await offlineDb.outboxQueue.update(item.id, { status: "COMPLETED" });
              }
              await offlineDb.operationLog.update(item.operationId, { status: "SYNCED" });
            }
            totalSynced += items.length;

            // Ingest server operations for 2-way sync
            const serverOps = data.server_operations_to_apply || [];
            for (const sOp of serverOps) {
              const existing = await offlineDb.operationLog.get(sOp.operation_id);
              if (!existing) {
                const incomingOp: ClientAccountingOperation = {
                  operationId: sOp.operation_id,
                  transactionId: sOp.transaction_id,
                  replicaId: sOp.replica_id,
                  operationType: sOp.operation_type,
                  operationClass: sOp.operation_class,
                  payload: sOp.payload,
                  logicalTimestamp: sOp.logical_timestamp,
                  parents: sOp.parents || [],
                  payloadHash: sOp.payload_hash || "",
                  signature: sOp.signature,
                  status: "COMMITTED",
                  createdAt: Date.now()
                };
                await offlineDb.operationLog.put(incomingOp);
                await offlineDb.inboxQueue.add({
                  operationId: sOp.operation_id,
                  transactionId: sOp.transaction_id,
                  status: "APPLIED",
                  receivedAt: Date.now()
                });
                totalReceived++;
              }
            }

            // Update sync cursor
            await offlineDb.syncCursors.put({
              transactionId: txId,
              cursor: data.state_commitment || "",
              lastSyncedAt: Date.now()
            });
          } else {
            for (const item of items) {
              if (item.id) {
                await offlineDb.outboxQueue.update(item.id, {
                  status: "FAILED",
                  retryCount: item.retryCount + 1,
                  lastError: data.reason || `Status: ${data.status}`
                });
              }
            }
          }
        } else {
          for (const item of items) {
            if (item.id) {
              await offlineDb.outboxQueue.update(item.id, {
                status: "FAILED",
                retryCount: item.retryCount + 1,
                lastError: `HTTP ${res.status}`
              });
            }
          }
        }
      } catch (err: any) {
        for (const item of items) {
          if (item.id) {
            await offlineDb.outboxQueue.update(item.id, {
              status: "FAILED",
              retryCount: item.retryCount + 1,
              lastError: err?.message || "Network Error"
            });
          }
        }
      }
    }

    return { syncedCount: totalSynced, receivedCount: totalReceived, status: "SYNC_DONE" };
  }

  private static async sha256(message: string): Promise<string> {
    if (typeof crypto !== "undefined" && crypto.subtle) {
      const msgBuffer = new TextEncoder().encode(message);
      const hashBuffer = await crypto.subtle.digest("SHA-256", msgBuffer);
      const hashArray = Array.from(new Uint8Array(hashBuffer));
      return hashArray.map(b => b.toString(16).padStart(2, "0")).join("");
    }
    let hash = 0;
    for (let i = 0; i < message.length; i++) {
      hash = (hash << 5) - hash + message.charCodeAt(i);
      hash |= 0;
    }
    return Math.abs(hash).toString(16).padStart(64, "0");
  }
}
