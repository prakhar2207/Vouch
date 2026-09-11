import { offlineDb, OfflineVoucher } from "../db/offlineDb";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken } from "@/utils/auth";

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

export async function executeClientOutboxSync() {
  if (typeof window === "undefined" || !navigator.onLine) return;
  if (isSyncInProgress) return;
  isSyncInProgress = true;

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

    const pending = await offlineDb.vouchers
      .where("status")
      .equals("PENDING")
      .toArray();

    if (pending.length === 0) return;

    const token = getAccessToken();
    if (!token) return;

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
              device_id: typeof window !== "undefined" ? window.navigator.userAgent.substring(0, 50) : "web-client"
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

        if (response.ok && (resData.success || resData.processed_count > 0)) {
          const cmdResult = resData.results?.find((r: any) => r.command_id === commandId) || resData.results?.[0];
          if (cmdResult && cmdResult.status === "PROCESSED") {
            await offlineDb.vouchers.update(item.id!, {
              status: "SYNCED",
              voucherNumber: cmdResult?.voucher_number,
              syncedAt: Date.now(),
            });
          } else {
            const cmdErr = resData.errors?.find((e: any) => e.command_id === commandId)?.error || "Server processing failed";
            await offlineDb.vouchers.update(item.id!, {
              status: "FAILED",
              errorMessage: cmdErr,
              retryCount: (item.retryCount || 0) + 1,
            });
          }
        } else {
          const errMsg = resData.errors?.find((e: any) => e.command_id === commandId)?.error || resData.errors?.[0]?.error || resData.error || (typeof resData === "string" ? resData : "Server rejected command");
          await offlineDb.vouchers.update(item.id!, {
            status: "FAILED",
            errorMessage: errMsg,
            retryCount: (item.retryCount || 0) + 1,
          });
        }
      } catch (err: any) {
        const isOnline = typeof navigator !== "undefined" ? navigator.onLine : false;
        await offlineDb.vouchers.update(item.id!, {
          status: isOnline ? "FAILED" : "PENDING",
          errorMessage: err?.message || "Network error during sync",
          retryCount: (item.retryCount || 0) + 1,
        });
      }
    }
  } finally {
    isSyncInProgress = false;
  }
}

export async function retryFailedVoucher(id: number) {
  await offlineDb.vouchers.update(id, { status: "PENDING", errorMessage: undefined });
  await triggerOutboxSync();
}

export async function triggerOutboxSync() {
  if (typeof window === "undefined") return;

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

// Auto-register listener for online event inside the PWA container
if (typeof window !== "undefined") {
  window.addEventListener("online", () => {
    triggerOutboxSync();
  });
  window.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      triggerOutboxSync();
    }
  });
}
