"use client";

import React from 'react';
import { CheckCircle2, Sparkles, AlertCircle, EyeOff, MinusCircle } from 'lucide-react';

interface ReconciliationStateBadgeProps {
  status: string;
  isExcluded?: boolean;
  className?: string;
}

export default function ReconciliationStateBadge({
  status,
  isExcluded = false,
  className = '',
}: ReconciliationStateBadgeProps) {
  if (isExcluded || status === 'EXCLUDED') {
    return (
      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-muted text-muted-foreground border border-border ${className}`}>
        <EyeOff className="w-3 h-3 text-muted-foreground" />
        <span>Excluded</span>
      </span>
    );
  }

  const st = (status || 'UNRESOLVED').toUpperCase();

  switch (st) {
    case 'FULLY_RECONCILED':
    case 'RECONCILED':
    case 'MATCHED_AUTO':
      return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 ${className}`}>
          <CheckCircle2 className="w-3 h-3" />
          <span>Reconciled</span>
        </span>
      );
    case 'MATCHED_SUGGESTED':
    case 'NEEDS_REVIEW':
    case 'SUGGESTED':
      return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20 ${className}`}>
          <Sparkles className="w-3 h-3 text-purple-500" />
          <span>Suggested Match</span>
        </span>
      );
    case 'IGNORED':
      return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-muted text-muted-foreground border border-border ${className}`}>
          <MinusCircle className="w-3 h-3" />
          <span>Ignored</span>
        </span>
      );
    case 'UNPROCESSED':
    case 'UNRESOLVED':
    default:
      return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 ${className}`}>
          <AlertCircle className="w-3 h-3 text-amber-500" />
          <span>Unresolved</span>
        </span>
      );
  }
}
