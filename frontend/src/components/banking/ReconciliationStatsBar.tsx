"use client";

import React from "react";
import { Search } from "lucide-react";
import { ReconciliationSummary, BankingActiveTab } from "./types";

interface ReconciliationStatsBarProps {
  summary: ReconciliationSummary | null;
  activeTab: BankingActiveTab;
  onTabChange: (tab: BankingActiveTab) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
}

export default function ReconciliationStatsBar({
  summary,
  activeTab,
  onTabChange,
  searchQuery,
  onSearchChange,
}: ReconciliationStatsBarProps) {
  return (
    <div className="flex flex-col sm:flex-row justify-between items-stretch sm:items-center gap-3">
      <div className="flex items-center gap-1.5 p-1 bg-muted/30 border border-border/40 rounded-xl flex-wrap">
        <button
          onClick={() => onTabChange("UNRESOLVED")}
          className={`px-3.5 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer flex items-center gap-2 ${
            activeTab === "UNRESOLVED"
              ? "bg-card text-foreground shadow-sm border border-border/60"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <div className="w-2 h-2 rounded-full bg-rose-500 shrink-0" />
          <span>Attention</span>
          {(summary?.unresolved_count || 0) > 0 && (
            <span className="px-1.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-rose-500/15 text-rose-500 leading-none">
              {summary?.unresolved_count}
            </span>
          )}
        </button>

        <button
          onClick={() => onTabChange("NEEDS_REVIEW")}
          className={`px-3.5 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer flex items-center gap-2 ${
            activeTab === "NEEDS_REVIEW"
              ? "bg-card text-foreground shadow-sm border border-border/60"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <div className="w-2 h-2 rounded-full bg-amber-500 shrink-0" />
          <span>Review</span>
          {(summary?.needs_review_count || 0) > 0 && (
            <span className="px-1.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-amber-500/15 text-amber-500 leading-none">
              {summary?.needs_review_count}
            </span>
          )}
        </button>

        <button
          onClick={() => onTabChange("MATCHED")}
          className={`px-3.5 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer flex items-center gap-2 ${
            activeTab === "MATCHED"
              ? "bg-card text-foreground shadow-sm border border-border/60"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <div className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
          <span>Done</span>
          {((summary?.matched_count || 0) + (summary?.reconciled_count || 0)) > 0 && (
            <span className="px-1.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-emerald-500/15 text-emerald-500 leading-none">
              {(summary?.matched_count || 0) + (summary?.reconciled_count || 0)}
            </span>
          )}
        </button>

        <button
          onClick={() => onTabChange("EXCLUDED")}
          className={`px-3.5 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer flex items-center gap-2 ${
            activeTab === "EXCLUDED"
              ? "bg-card text-foreground shadow-sm border border-border/60"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <span>Excluded</span>
          {(summary?.excluded_count || 0) > 0 && (
            <span className="px-1.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-muted text-muted-foreground leading-none">
              {summary?.excluded_count}
            </span>
          )}
        </button>

        <button
          onClick={() => onTabChange("ALL")}
          className={`px-3.5 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${
            activeTab === "ALL"
              ? "bg-card text-foreground shadow-sm border border-border/60"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          All
        </button>
      </div>

      <div className="relative min-w-[260px]">
        <Search className="w-4 h-4 text-muted-foreground absolute left-3.5 top-1/2 -translate-y-1/2" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search narration, ref #, or party..."
          className="w-full bg-card border border-border/60 rounded-xl pl-10 pr-4 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
        />
      </div>
    </div>
  );
}
