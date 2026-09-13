"use client";

import React from "react";
import { ReconciliationSummary, BankingActiveTab } from "./types";

interface ReconciliationOverviewCardProps {
  summary: ReconciliationSummary | null;
  onSelectTab: (tab: BankingActiveTab) => void;
}

export default function ReconciliationOverviewCard({
  summary,
  onSelectTab,
}: ReconciliationOverviewCardProps) {
  return (
    <div className="bg-card border border-border/40 rounded-2xl p-5 shadow-sm flex flex-col justify-between">
      <div className="flex items-center justify-between mb-4">
        <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
          Overview
        </span>
        <span className="text-[11px] font-mono text-muted-foreground">
          {summary?.total_transactions || 0} total
        </span>
      </div>

      <div className="space-y-3">
        <button
          onClick={() => onSelectTab("UNRESOLVED")}
          className="flex items-center justify-between w-full group cursor-pointer"
        >
          <div className="flex items-center gap-2.5">
            <div className="w-2.5 h-2.5 rounded-full bg-rose-500 shrink-0" />
            <span className="text-xs font-medium text-muted-foreground group-hover:text-foreground transition-colors">
              Needs Attention
            </span>
          </div>
          <span className="text-sm font-bold font-mono tabular-nums text-foreground">
            {summary?.unresolved_count || 0}
          </span>
        </button>

        <button
          onClick={() => onSelectTab("NEEDS_REVIEW")}
          className="flex items-center justify-between w-full group cursor-pointer"
        >
          <div className="flex items-center gap-2.5">
            <div className="w-2.5 h-2.5 rounded-full bg-amber-500 shrink-0" />
            <span className="text-xs font-medium text-muted-foreground group-hover:text-foreground transition-colors">
              Ready to Confirm
            </span>
          </div>
          <span className="text-sm font-bold font-mono tabular-nums text-foreground">
            {summary?.needs_review_count || 0}
          </span>
        </button>

        <button
          onClick={() => onSelectTab("MATCHED")}
          className="flex items-center justify-between w-full group cursor-pointer"
        >
          <div className="flex items-center gap-2.5">
            <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 shrink-0" />
            <span className="text-xs font-medium text-muted-foreground group-hover:text-foreground transition-colors">
              Completed
            </span>
          </div>
          <span className="text-sm font-bold font-mono tabular-nums text-foreground">
            {(summary?.matched_count || 0) + (summary?.reconciled_count || 0)}
          </span>
        </button>

        {(summary?.excluded_count || 0) > 0 && (
          <button
            onClick={() => onSelectTab("EXCLUDED")}
            className="flex items-center justify-between w-full group cursor-pointer"
          >
            <div className="flex items-center gap-2.5">
              <div className="w-2.5 h-2.5 rounded-full bg-muted-foreground/40 shrink-0" />
              <span className="text-xs font-medium text-muted-foreground group-hover:text-foreground transition-colors">
                Excluded
              </span>
            </div>
            <span className="text-sm font-bold font-mono tabular-nums text-foreground">
              {summary?.excluded_count || 0}
            </span>
          </button>
        )}
      </div>
    </div>
  );
}
