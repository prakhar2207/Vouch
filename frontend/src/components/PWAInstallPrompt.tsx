"use client";
import React, { useEffect, useState } from "react";
import { Download, X } from "lucide-react";

export default function PWAInstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState<any>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    // Check 7-day dismissal window
    const dismissedUntil = localStorage.getItem("pwa_install_dismissed_until");
    if (dismissedUntil && Number(dismissedUntil) > Date.now()) {
      return;
    }

    const handleBeforeInstallPrompt = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e);
      setIsVisible(true);
    };

    const handleAppInstalled = () => {
      setIsVisible(false);
      setDeferredPrompt(null);
      // Mark as permanently or long-term installed
      localStorage.setItem(
        "pwa_install_dismissed_until",
        String(Date.now() + 30 * 24 * 60 * 60 * 1000)
      );
    };

    window.addEventListener("beforeinstallprompt", handleBeforeInstallPrompt);
    window.addEventListener("appinstalled", handleAppInstalled);

    return () => {
      window.removeEventListener("beforeinstallprompt", handleBeforeInstallPrompt);
      window.removeEventListener("appinstalled", handleAppInstalled);
    };
  }, []);

  const handleInstallClick = async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    if (outcome === "accepted") {
      setIsVisible(false);
      setDeferredPrompt(null);
    }
  };

  const handleDismiss = () => {
    setIsVisible(false);
    // 7-day dismissal persistence in localStorage
    localStorage.setItem(
      "pwa_install_dismissed_until",
      String(Date.now() + 7 * 24 * 60 * 60 * 1000)
    );
  };

  if (!isVisible) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 w-full max-w-sm animate-in fade-in slide-in-from-bottom-4 duration-300">
      <div className="bg-card/95 border border-border/80 backdrop-blur-md text-card-foreground p-3.5 rounded-xl shadow-xl flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0 border border-primary/20">
            <Download className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <div className="text-xs font-semibold text-foreground truncate">Install Vouch App</div>
            <div className="text-[11px] text-muted-foreground truncate">
              Faster keyboard navigation & offline access
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <button
            onClick={handleInstallClick}
            className="px-2.5 py-1 bg-primary text-primary-foreground hover:bg-primary/90 rounded-md text-xs font-semibold shadow-2xs transition-all cursor-pointer"
          >
            Install
          </button>
          <button
            onClick={handleDismiss}
            className="p-1 text-muted-foreground hover:text-foreground rounded-md hover:bg-muted/60 transition-colors cursor-pointer"
            aria-label="Dismiss for 7 days"
            title="Dismiss for 7 days"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
