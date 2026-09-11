"use client";
import { useEffect } from "react";
import { executeClientOutboxSync, triggerOutboxSync } from "@/lib/sync/sync-worker";

export default function OfflineSyncHandler() {
  useEffect(() => {
    if (typeof window === "undefined") return;

    // 1. Listen for service worker background sync broadcasts
    let swHandler: ((event: MessageEvent) => void) | null = null;
    if ("serviceWorker" in navigator) {
      swHandler = (event: MessageEvent) => {
        if (event.data && event.data.type === "TRIGGER_OUTBOX_SYNC") {
          executeClientOutboxSync();
        }
      };
      navigator.serviceWorker.addEventListener("message", swHandler);
    }

    // 2. Window online & visibility change listeners (fallback for Safari, iOS, and non-SW envs)
    const handleOnline = () => {
      triggerOutboxSync();
    };
    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        triggerOutboxSync();
      }
    };
    window.addEventListener("online", handleOnline);
    window.addEventListener("visibilitychange", handleVisibility);

    // 3. On app mount, attempt outbox sync immediately if online
    if (navigator.onLine) {
      triggerOutboxSync();
    }

    return () => {
      if (swHandler && "serviceWorker" in navigator) {
        navigator.serviceWorker.removeEventListener("message", swHandler);
      }
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("visibilitychange", handleVisibility);
    };
  }, []);

  return null;
}
