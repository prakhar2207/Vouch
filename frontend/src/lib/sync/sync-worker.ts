import { offlineDb, OfflineVoucher } from "../db/offlineDb";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken } from "@/utils/auth";

export async function queueOfflineVoucher(voucherType: string, payload: any, voucherDate: string) {
  const localId = `local-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
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

      const response = await fetch(`${API_BASE_URL}/api/vouchers/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(item.payload),
      });

      if (response.ok) {
        await offlineDb.vouchers.update(item.id!, {
          status: "SYNCED",
          syncedAt: Date.now(),
        });
      } else {
        const errText = await response.text();
        await offlineDb.vouchers.update(item.id!, {
          status: "FAILED",
          errorMessage: errText,
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
