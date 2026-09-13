"use client";

import React from "react";
import { CheckCircle2, AlertCircle } from "lucide-react";
import { ReconciliationSummary } from "./types";

interface ReconciliationComparisonCardProps {
  summary: ReconciliationSummary | null;
}

export default function ReconciliationComparisonCard({ summary }: ReconciliationComparisonCardProps) {
  const formattedCutoff = summary?.statement_cutoff_date
    ? new Date(summary.statement_cutoff_date).toLocaleDateString("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      })
    : null;

  return (
    <div className="bg-card border border-border/40 rounded-2xl p-5 shadow-sm flex flex-col justify-between space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider block">
            Reconciliation
          </span>
          {formattedCutoff && (
            <span className="text-[11px] font-mono text-primary font-medium">
              As of {formattedCutoff}
            </span>
          )}
        </div>
        {summary?.reconciliation_state === "FULLY_RECONCILED" ? (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="w-3.5 h-3.5" />
            Reconciled
          </span>
        ) : summary?.is_balanced ? (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="w-3.5 h-3.5" />
            Balanced
          </span>
        ) : summary?.reconciliation_state === "TRANSACTIONS_REVIEWED" ? (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-blue-500/10 text-blue-400 border border-blue-500/20">
            <CheckCircle2 className="w-3.5 h-3.5" />
            Reviewed
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <AlertCircle className="w-3.5 h-3.5" />
            Unreconciled
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-0">
        <div className="p-3 bg-muted/20 rounded-l-xl border border-border/30 border-r-0">
          <div className="text-[11px] text-muted-foreground font-medium">Book</div>
          <div className="text-base font-bold font-mono tabular-nums text-foreground">
            ₹{parseFloat(summary?.book_closing_balance || "0").toLocaleString("en-IN", { minimumFractionDigits: 2 })}
          </div>
        </div>
        <div className="p-3 bg-muted/20 rounded-r-xl border border-border/30">
          <div className="text-[11px] text-muted-foreground font-medium">Statement</div>
          <div className="text-base font-bold font-mono tabular-nums text-foreground">
            ₹{parseFloat(summary?.statement_closing_balance || "0").toLocaleString("en-IN", { minimumFractionDigits: 2 })}
          </div>
        </div>
      </div>

      {!summary?.is_balanced && (summary?.reconciliation_gap || summary?.unresolved_count) ? (
        <div className="flex items-center justify-between p-2.5 rounded-xl bg-amber-500/5 border border-amber-500/15">
          <span className="text-[11px] font-medium text-amber-500">
            Gap: ₹{parseFloat(summary?.reconciliation_gap || "0").toLocaleString("en-IN", { minimumFractionDigits: 2 })}
          </span>
          <span className="text-[11px] text-muted-foreground">
            {summary?.unresolved_count || 0} items to review
          </span>
        </div>
      ) : (
        <p className="text-[11px] text-emerald-500/80 font-medium">
          ✓ Books match bank statement
        </p>
      )}
    </div>
  );
}
