"use client";
import { useEffect } from "react";

/**
 * Suppresses uncaught errors originating from third-party browser extensions
 * (such as Careerflow / Sentry tracing content scripts calling reportAllChanges on undefined entries)
 * so they do not disrupt the application or clutter the developer console.
 */
export default function ExtensionErrorSuppressor() {
  useEffect(() => {
    const handleError = (event: ErrorEvent) => {
      const msg = event.message || "";
      const filename = event.filename || "";

      if (
        msg.includes("startTime") ||
        msg.includes("reportAllChanges") ||
        filename.includes("chrome-extension") ||
        filename.includes("contentScript") ||
        filename.includes("moz-extension")
      ) {
        event.preventDefault();
        event.stopImmediatePropagation();
        return true;
      }
    };

    const handleRejection = (event: PromiseRejectionEvent) => {
      const reasonMsg = String(event.reason?.message || event.reason || "");
      if (
        reasonMsg.includes("startTime") ||
        reasonMsg.includes("reportAllChanges")
      ) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    };

    window.addEventListener("error", handleError, true);
    window.addEventListener("unhandledrejection", handleRejection, true);

    return () => {
      window.removeEventListener("error", handleError, true);
      window.removeEventListener("unhandledrejection", handleRejection, true);
    };
  }, []);

  return null;
}
