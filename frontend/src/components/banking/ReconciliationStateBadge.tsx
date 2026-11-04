import React from "react";
import { Sparkles, CheckCircle2, Clock, AlertCircle, EyeOff, Ban } from "lucide-react";

export type ReconciliationState =
  | "MATCHED_AUTO"
  | "MATCHED_SUGGESTED"
  | "NEEDS_REVIEW"
  | "UNRESOLVED"
  | "UNPROCESSED"
  | "MATCHED"
  | "RECONCILED"
  | "IGNORED"
  | "EXCLUDED";

interface ReconciliationStateBadgeProps {
  status: string;
  isExcluded?: boolean;
  className?: string;
  size?: "sm" | "md" | "lg";
}

export const ReconciliationStateBadge: React.FC<ReconciliationStateBadgeProps> = ({
  status,
  isExcluded = false,
  className = "",
  size = "md",
}) => {
  if (isExcluded || status === "EXCLUDED") {
    return (
      <span
        className={`inline-flex items-center gap-1 font-bold rounded-md uppercase tracking-wider bg-muted text-muted-foreground border border-border ${
          size === "sm" ? "text-[10px] px-1.5 py-0.5" : "text-[11px] px-2 py-0.5"
        } ${className}`}
      >
        <EyeOff className="w-3 h-3" />
        <span>Excluded</span>
      </span>
    );
  }

  // P0 DEF-FIN-02: Provisional AI suggestions MUST NEVER be displayed as Completed or Reconciled.
  // Distinct Purple Badge: 'AI Suggested'
  if (status === "MATCHED_AUTO" || status === "MATCHED_SUGGESTED") {
    return (
      <span
        className={`inline-flex items-center gap-1 font-bold rounded-md uppercase tracking-wider bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/25 ${
          size === "sm" ? "text-[10px] px-1.5 py-0.5" : "text-[11px] px-2 py-0.5"
        } ${className}`}
      >
        <Sparkles className="w-3 h-3 text-purple-500" />
        <span>AI Suggested</span>
      </span>
    );
  }

  // Green Reconciled: STRICTLY when transaction is RECONCILED with posted voucher outcome
  if (status === "RECONCILED" || status === "MATCHED") {
    return (
      <span
        className={`inline-flex items-center gap-1 font-bold rounded-md uppercase tracking-wider bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/25 ${
          size === "sm" ? "text-[10px] px-1.5 py-0.5" : "text-[11px] px-2 py-0.5"
        } ${className}`}
      >
        <CheckCircle2 className="w-3 h-3 text-emerald-500" />
        <span>Reconciled</span>
      </span>
    );
  }

  if (status === "NEEDS_REVIEW") {
    return (
      <span
        className={`inline-flex items-center gap-1 font-bold rounded-md uppercase tracking-wider bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/25 ${
          size === "sm" ? "text-[10px] px-1.5 py-0.5" : "text-[11px] px-2 py-0.5"
        } ${className}`}
      >
        <Clock className="w-3 h-3 text-amber-500" />
        <span>Ready to Confirm</span>
      </span>
    );
  }

  if (status === "IGNORED") {
    return (
      <span
        className={`inline-flex items-center gap-1 font-bold rounded-md uppercase tracking-wider bg-muted text-muted-foreground border border-border/50 ${
          size === "sm" ? "text-[10px] px-1.5 py-0.5" : "text-[11px] px-2 py-0.5"
        } ${className}`}
      >
        <Ban className="w-3 h-3" />
        <span>Ignored</span>
      </span>
    );
  }

  // UNRESOLVED / UNPROCESSED
  return (
    <span
      className={`inline-flex items-center gap-1 font-bold rounded-md uppercase tracking-wider bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/25 ${
        size === "sm" ? "text-[10px] px-1.5 py-0.5" : "text-[11px] px-2 py-0.5"
      } ${className}`}
    >
      <AlertCircle className="w-3 h-3 text-rose-500" />
      <span>Needs Attention</span>
    </span>
  );
};
