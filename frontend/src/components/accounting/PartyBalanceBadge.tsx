"use client";

import React from 'react';
import { ArrowDownLeft, ArrowUpRight, CheckCircle2, Clock } from 'lucide-react';

export type BalanceState = 
  | 'TO_COLLECT' 
  | 'TO_PAY' 
  | 'ADVANCE_RECEIVED' 
  | 'ADVANCE_PAID' 
  | 'SETTLED' 
  | 'DR' 
  | 'CR';

interface PartyBalanceBadgeProps {
  state: BalanceState | string;
  className?: string;
  showIcon?: boolean;
}

export default function PartyBalanceBadge({
  state,
  className = '',
  showIcon = true,
}: PartyBalanceBadgeProps) {
  const normalized = (state || 'SETTLED').toUpperCase();

  switch (normalized) {
    case 'TO_COLLECT':
      return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 ${className}`}>
          {showIcon && <ArrowDownLeft className="w-3 h-3" />}
          <span>To Collect</span>
        </span>
      );
    case 'TO_PAY':
      return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 ${className}`}>
          {showIcon && <ArrowUpRight className="w-3 h-3" />}
          <span>To Pay</span>
        </span>
      );
    case 'ADVANCE_RECEIVED':
      return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20 ${className}`}>
          {showIcon && <Clock className="w-3 h-3" />}
          <span>Advance Received</span>
        </span>
      );
    case 'ADVANCE_PAID':
      return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 ${className}`}>
          {showIcon && <Clock className="w-3 h-3" />}
          <span>Advance Paid</span>
        </span>
      );
    case 'DR':
      return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 ${className}`}>
          <span>Dr</span>
        </span>
      );
    case 'CR':
      return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-orange-500/10 text-orange-600 dark:text-orange-400 border border-orange-500/20 ${className}`}>
          <span>Cr</span>
        </span>
      );
    case 'SETTLED':
    default:
      return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-muted text-muted-foreground border border-border ${className}`}>
          {showIcon && <CheckCircle2 className="w-3 h-3 text-muted-foreground" />}
          <span>Settled</span>
        </span>
      );
  }
}
