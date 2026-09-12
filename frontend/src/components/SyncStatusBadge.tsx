"use client";

import React, { useEffect, useState } from "react";
import { syncRepository, SyncStatusInfo } from "@/lib/data/sync-repository";
import { useCompany } from "@/context/CompanyContext";
import { RefreshCw, CheckCircle2, WifiOff, Clock } from "lucide-react";

export default function SyncStatusBadge() {
  const { companyId } = useCompany();
  const [syncInfo, setSyncInfo] = useState<SyncStatusInfo>({
    status: "IDLE",
    lastSyncAt: null,
    pendingMutationsCount: 0,
    isInitialComplete: false,
  });
  const [isHovered, setIsHovered] = useState(false);
  const [isTriggering, setIsTriggering] = useState(false);

  const loadStatus = async () => {
    if (!companyId) return;
    const info = await syncRepository.getSyncStatus(companyId);
    setSyncInfo(info);
  };

  useEffect(() => {
    loadStatus();
    const interval = setInterval(loadStatus, 15000);

    const handleSyncComplete = () => loadStatus();
    const handleOnline = () => loadStatus();
    const handleOffline = () => loadStatus();

    if (typeof window !== "undefined") {
      window.addEventListener("vouch:sync-complete", handleSyncComplete);
      window.addEventListener("online", handleOnline);
      window.addEventListener("offline", handleOffline);
    }

    return () => {
      clearInterval(interval);
      if (typeof window !== "undefined") {
        window.removeEventListener("vouch:sync-complete", handleSyncComplete);
        window.removeEventListener("online", handleOnline);
        window.removeEventListener("offline", handleOffline);
      }
    };
  }, [companyId]);

  const handleManualSync = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!companyId || isTriggering) return;
    setIsTriggering(true);
    try {
      await syncRepository.triggerSync(companyId);
      await loadStatus();
    } finally {
      setIsTriggering(false);
    }
  };

  const formatLastSync = (ts: number | null) => {
    if (!ts) return "Not yet synced";
    const diffSec = Math.floor((Date.now() - ts) / 1000);
    if (diffSec < 60) return "just now";
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHours = Math.floor(diffMin / 60);
    return `${diffHours}h ago`;
  };

  const isSyncing = syncInfo.status === "SYNCING" || isTriggering;
  const isOffline = syncInfo.status === "OFFLINE";
  const hasPending = syncInfo.pendingMutationsCount > 0;

  let badgeContent;
  let tooltipText;

  if (isOffline) {
    badgeContent = (
      <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-[11px] font-medium bg-amber-500/10 text-amber-500 border border-amber-500/20">
        <WifiOff className="w-3 h-3 shrink-0" />
        <span className="hidden xl:inline">Offline (Local)</span>
      </span>
    );
    tooltipText = "Operating offline on local IndexedDB data. Mutations queued.";
  } else if (isSyncing) {
    badgeContent = (
      <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-[11px] font-medium bg-blue-500/10 text-blue-500 border border-blue-500/20 animate-pulse">
        <RefreshCw className="w-3 h-3 animate-spin shrink-0" />
        <span className="hidden xl:inline">Syncing...</span>
      </span>
    );
    tooltipText = "Synchronizing operational data with Neon.";
  } else if (hasPending) {
    badgeContent = (
      <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-[11px] font-medium bg-purple-500/10 text-purple-400 border border-purple-500/20">
        <Clock className="w-3 h-3 shrink-0" />
        <span className="hidden xl:inline">{syncInfo.pendingMutationsCount} queued</span>
      </span>
    );
    tooltipText = `${syncInfo.pendingMutationsCount} local mutations waiting to sync.`;
  } else if (syncInfo.lastSyncAt) {
    badgeContent = (
      <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-[11px] font-medium bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
        <CheckCircle2 className="w-3 h-3 shrink-0" />
        <span className="hidden xl:inline">Synced {formatLastSync(syncInfo.lastSyncAt)}</span>
      </span>
    );
    tooltipText = `Local database synced with Neon ${formatLastSync(syncInfo.lastSyncAt)}. Click to sync now.`;
  } else {
    badgeContent = (
      <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-[11px] font-medium bg-muted text-muted-foreground border border-border">
        <RefreshCw className="w-3 h-3 shrink-0" />
        <span className="hidden xl:inline">Ready</span>
      </span>
    );
    tooltipText = "Click to synchronize with cloud database.";
  }

  return (
    <button
      onClick={handleManualSync}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className="relative cursor-pointer transition-opacity hover:opacity-80 shrink-0"
      title={tooltipText}
    >
      {badgeContent}
      {isHovered && tooltipText && (
        <div className="absolute top-full mt-1.5 right-0 z-50 px-2.5 py-1 text-[11px] bg-popover text-popover-foreground border border-border rounded-md shadow-lg whitespace-nowrap pointer-events-none">
          {tooltipText}
        </div>
      )}
    </button>
  );
}
