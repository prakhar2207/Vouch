"use client";

import React, { useEffect, useState } from "react";
import { AlertTriangle, LogOut, ShieldAlert, Trash2, X } from "lucide-react";
import { getPendingOfflineSummary, type PendingOfflineSummary } from "@/lib/db/offlineDb";
import { getUser } from "@/utils/auth";

interface LogoutConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirmLogout: (options: { wipeLocalDeviceData: boolean }) => Promise<void> | void;
}

function LogoutConfirmDialog({
  onClose,
  onConfirmLogout,
}: Omit<LogoutConfirmModalProps, "isOpen">) {
  const [summary, setSummary] = useState<PendingOfflineSummary>({
    currentUserCount: 0,
    totalPendingCount: 0,
    companyIds: [],
  });
  const [loadingSummary, setLoadingSummary] = useState(true);
  const [submittingMode, setSubmittingMode] = useState<"standard" | "wipe" | null>(null);
  const [confirmDiscardPending, setConfirmDiscardPending] = useState(false);

  useEffect(() => {
    let active = true;
    const uid = getUser()?.id || null;
    getPendingOfflineSummary(uid)
      .then((res) => {
        if (active) setSummary(res);
      })
      .catch(() => {})
      .finally(() => {
        if (active) setLoadingSummary(false);
      });

    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !submittingMode) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleEsc);
    return () => {
      active = false;
      window.removeEventListener("keydown", handleEsc);
    };
  }, [onClose, submittingMode]);

  const hasUnsyncedForUser = summary.currentUserCount > 0;
  const hasAnyUnsyncedOnDevice = summary.totalPendingCount > 0;
  const wipeRequiresAck = hasAnyUnsyncedOnDevice;
  const isBusy = submittingMode !== null;

  const triggerLogout = async (wipeLocalDeviceData: boolean) => {
    setSubmittingMode(wipeLocalDeviceData ? "wipe" : "standard");
    try {
      await onConfirmLogout({ wipeLocalDeviceData });
    } finally {
      setSubmittingMode(null);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-150"
      role="dialog"
      aria-modal="true"
      aria-labelledby="logout-modal-title"
      onClick={() => !isBusy && onClose()}
    >
      <div
        className="bg-card border border-border rounded-2xl shadow-2xl w-full max-w-md p-6 space-y-5 text-foreground"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-500 shrink-0">
              <LogOut className="w-5 h-5" />
            </div>
            <div>
              <h2 id="logout-modal-title" className="text-base font-extrabold">
                Sign Out of SriLekh
              </h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Choose standard sign-out or wipe all local data for shared devices.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isBusy}
            aria-label="Close sign-out dialog"
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Unsynchronized Offline Work Notice */}
        {!loadingSummary && hasUnsyncedForUser && (
          <div
            role="status"
            className="rounded-xl border border-amber-500/35 bg-amber-500/10 p-3.5 text-xs text-amber-900 dark:text-amber-200 flex items-start gap-2.5"
          >
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-600 dark:text-amber-400" />
            <div className="space-y-1">
              <div className="font-bold">
                {summary.currentUserCount} unsynchronized offline{" "}
                {summary.currentUserCount === 1 ? "record" : "records"} pending
              </div>
              <p className="leading-relaxed opacity-90">
                Standard sign-out preserves your pending drafts safely locked to your user account on
                this device so no accounting work is lost. Other users cannot view or sync them.
              </p>
            </div>
          </div>
        )}

        {/* Option 1: Ordinary Sign-Out */}
        <div className="rounded-xl border border-border bg-muted/30 p-4 space-y-3">
          <div className="space-y-1">
            <div className="text-sm font-bold">Standard Logout (Recommended on Personal Device)</div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Revokes your server session &amp; cookies, stops background sync, clears cached company
              ledgers/vouchers, and preserves any queued offline drafts isolated to your account.
            </p>
          </div>
          <button
            type="button"
            disabled={isBusy}
            onClick={() => triggerLogout(false)}
            className="w-full py-2.5 px-4 rounded-xl bg-[#162C5B] hover:bg-[#0F1E3D] dark:bg-[#E28123] dark:hover:bg-[#c86815] text-white text-xs font-bold flex items-center justify-center gap-2 transition-colors cursor-pointer disabled:opacity-60"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span>{submittingMode === "standard" ? "Signing out..." : "Sign Out"}</span>
          </button>
        </div>

        {/* Option 2: Secure Shared-Device Logout */}
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/5 p-4 space-y-3">
          <div className="flex items-start gap-2">
            <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5 text-rose-500" />
            <div className="space-y-1">
              <div className="text-sm font-bold text-rose-700 dark:text-rose-300">
                Secure Shared-Device Logout (Erase Device Data)
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                Signs out and permanently deletes all local IndexedDB databases
                (`VouchOfflineDB`, `VouchSecurityVault`), pending offline drafts, device keys, and
                Service Worker caches from this browser.
              </p>
            </div>
          </div>

          {wipeRequiresAck && (
            <label className="flex items-start gap-2.5 text-xs text-rose-700 dark:text-rose-300 bg-rose-500/10 border border-rose-500/20 rounded-lg p-2.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={confirmDiscardPending}
                onChange={(e) => setConfirmDiscardPending(e.target.checked)}
                disabled={isBusy}
                className="mt-0.5 rounded border-rose-400"
              />
              <span>
                I understand this permanently deletes{" "}
                <strong>
                  {summary.totalPendingCount} unsynchronized local{" "}
                  {summary.totalPendingCount === 1 ? "record" : "records"}
                </strong>{" "}
                on this shared computer and cannot be undone.
              </span>
            </label>
          )}

          <button
            type="button"
            disabled={isBusy || (wipeRequiresAck && !confirmDiscardPending)}
            onClick={() => triggerLogout(true)}
            className="w-full py-2 px-4 rounded-xl bg-rose-600 hover:bg-rose-700 disabled:bg-rose-600/40 text-white text-xs font-bold flex items-center justify-center gap-2 transition-colors cursor-pointer disabled:cursor-not-allowed"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>
              {submittingMode === "wipe"
                ? "Wiping Local Data & Signing Out..."
                : "Wipe Local Data & Sign Out"}
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}

export default function LogoutConfirmModal({
  isOpen,
  onClose,
  onConfirmLogout,
}: LogoutConfirmModalProps) {
  if (!isOpen) return null;
  return <LogoutConfirmDialog onClose={onClose} onConfirmLogout={onConfirmLogout} />;
}
