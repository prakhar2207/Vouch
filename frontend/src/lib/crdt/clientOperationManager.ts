import { offlineDb, type ClientAccountingOperation, type OutboxItem, type InboxItem } from "../db/offlineDb";

export class ClientOperationManager {
  private static replicaId: string | null = null;

  public static getReplicaId(): string {
    if (this.replicaId) return this.replicaId;
    if (typeof window !== "undefined") {
      let stored = localStorage.getItem("vouch_protocol_replica_id");
      if (!stored) {
        stored = `REPLICA-${Math.random().toString(36).substring(2, 10).toUpperCase()}`;
        localStorage.setItem("vouch_protocol_replica_id", stored);
      }
      this.replicaId = stored;
      return stored;
    }
    return "REPLICA-SSR-CLIENT";
  }

  /**
   * Records a local accounting operation offline in IndexedDB and enqueues to Outbox.
   */
  public static async recordLocalOperation(params: {
    transactionId: string;
    operationType: string;
    operationClass?: string;
    payload: any;
    parents?: string[];
  }): Promise<ClientAccountingOperation> {
    const replicaId = this.getReplicaId();
    const timestamp = Date.now();
    
    // Resolve causal parents from existing operations for this transaction
    let parents = params.parents || [];
    if (parents.length === 0) {
      const existingOps = await offlineDb.operationLog
        .where("transactionId")
        .equals(params.transactionId)
        .sortBy("logicalTimestamp");
      if (existingOps.length > 0) {
        parents = [existingOps[existingOps.length - 1].operationId];
      }
    }

    const logicalTimestamp = (parents.length > 0 ? (await this.getMaxLogicalTimestamp(params.transactionId)) + 1 : 1);
    const randomHex = Math.random().toString(36).substring(2, 10).toUpperCase();
    const operationId = `OP-CLI-${randomHex}`;

    // Simple deterministic hash simulation for client offline payload
    const payloadStr = JSON.stringify({
      operationId,
      transactionId: params.transactionId,
      payload: params.payload,
      logicalTimestamp,
      parents
    });
    const payloadHash = await this.sha256(payloadStr);

    const op: ClientAccountingOperation = {
      operationId,
      transactionId: params.transactionId,
      replicaId,
      operationType: params.operationType,
      operationClass: params.operationClass || "CAUSAL",
      payload: params.payload,
      logicalTimestamp,
      parents,
      payloadHash,
      status: "PENDING",
      createdAt: timestamp
    };

    // Store in local Operation Log
    await offlineDb.operationLog.put(op);

    // Enqueue in Outbox Queue for background sync
    await offlineDb.outboxQueue.add({
      operationId,
      transactionId: params.transactionId,
      status: "QUEUED",
      retryCount: 0,
      createdAt: timestamp,
      nextRetryAt: timestamp
    });

    return op;
  }

  /**
   * Helper to retrieve max logical timestamp for causal sequencing.
   */
  public static async getMaxLogicalTimestamp(transactionId: string): Promise<number> {
    const ops = await offlineDb.operationLog
      .where("transactionId")
      .equals(transactionId)
      .toArray();
    return ops.reduce((max, op) => Math.max(max, op.logicalTimestamp), 0);
  }

  /**
   * Flushes queued outbox operations to the Vouch backend protocol endpoint.
   */
  public static async syncOutboxWithServer(apiBaseUrl: string = "/api/v1/protocol"): Promise<{
    syncedCount: number;
    receivedCount: number;
    status: string;
  }> {
    if (typeof navigator !== "undefined" && !navigator.onLine) {
      return { syncedCount: 0, receivedCount: 0, status: "OFFLINE" };
    }

    const queued = await offlineDb.outboxQueue
      .where("status")
      .equals("QUEUED")
      .toArray();

    if (queued.length === 0) {
      return { syncedCount: 0, receivedCount: 0, status: "IDLE" };
    }

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

      try {
        const payload = {
          transaction_id: txId,
          client_replica_id: this.getReplicaId(),
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

        const res = await fetch(`${apiBaseUrl}/sync/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
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
    // Fallback simple checksum
    let hash = 0;
    for (let i = 0; i < message.length; i++) {
      hash = (hash << 5) - hash + message.charCodeAt(i);
      hash |= 0;
    }
    return Math.abs(hash).toString(16).padStart(64, "0");
  }
}
