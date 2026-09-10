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

export async function executeClientOutboxSync() {
  if (typeof window === "undefined" || !navigator.onLine) return;

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

      const response = await fetch(`${API_BASE_URL}/api/v1/accounting/sync/push/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(pushPayload),
      });

      const resData = await response.json();

      if (response.ok && (resData.success || resData.processed_count > 0)) {
        const cmdResult = resData.results?.[0];
        await offlineDb.vouchers.update(item.id!, {
          status: "SYNCED",
          voucherNumber: cmdResult?.voucher_number,
          syncedAt: Date.now(),
        });
      } else {
        const errMsg = resData.errors?.[0]?.error || (typeof resData === "string" ? resData : JSON.stringify(resData));
        await offlineDb.vouchers.update(item.id!, {
          status: "FAILED",
          errorMessage: errMsg,
          retryCount: (item.retryCount || 0) + 1,
        });
      }
    } catch (err: any) {
      await offlineDb.vouchers.update(item.id!, {
        status: "PENDING",
        errorMessage: err?.message || "Network error during sync",
        retryCount: (item.retryCount || 0) + 1,
      });
    }
  }
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
}
