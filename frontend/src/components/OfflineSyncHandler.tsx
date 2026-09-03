"use client";
import { useEffect } from "react";
import { executeClientOutboxSync, triggerOutboxSync } from "@/lib/sync/sync-worker";

export default function OfflineSyncHandler() {
  useEffect(() => {
    if (typeof window === "undefined") return;

    // Listen for service worker background sync broadcasts
    if ("serviceWorker" in navigator) {
      const handleMessage = (event: MessageEvent) => {
        if (event.data && event.data.type === "TRIGGER_OUTBOX_SYNC") {
          executeClientOutboxSync();
        }
      };
      navigator.serviceWorker.addEventListener("message", handleMessage);

      // On app mount, attempt outbox sync if online
      if (navigator.onLine) {
        triggerOutboxSync();
      }

      return () => {
        navigator.serviceWorker.removeEventListener("message", handleMessage);
      };
    }
  }, []);

  return null;
}
