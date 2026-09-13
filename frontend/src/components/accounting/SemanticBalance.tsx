"use client";

import React from 'react';
import AccountingAmount, { formatIndianCurrency } from './AccountingAmount';
import PartyBalanceBadge, { BalanceState } from './PartyBalanceBadge';

interface SemanticBalanceProps {
  balanceState?: BalanceState | string;
  displayAmount?: number | string;
  currentBalance?: number | string;
  normalBalance?: 'DEBIT' | 'CREDIT' | string;
  balanceDirection?: 'DEBIT' | 'CREDIT' | 'NONE' | string;
  viewMode?: 'owner' | 'accountant';
  size?: 'sm' | 'md' | 'lg' | 'hero';
  showBadge?: boolean;
  className?: string;
}

export default function SemanticBalance({
  balanceState = 'SETTLED',
  displayAmount,
  currentBalance = 0,
  normalBalance = 'DEBIT',
  balanceDirection,
  viewMode = 'owner',
  size = 'md',
  showBadge = true,
  className = '',
}: SemanticBalanceProps) {
  const amt = displayAmount !== undefined ? displayAmount : Math.abs(parseFloat(String(currentBalance || 0)));
  const state = (balanceState || 'SETTLED').toUpperCase();
  const numAmt = typeof amt === 'string' ? parseFloat(amt) : (amt || 0);

  if (viewMode === 'accountant') {
    const dir = balanceDirection || (normalBalance === 'DEBIT' ? (parseFloat(String(currentBalance)) >= 0 ? 'DR' : 'CR') : (parseFloat(String(currentBalance)) >= 0 ? 'CR' : 'DR'));
    return (
      <div className={`inline-flex items-center gap-1.5 ${className}`}>
        <AccountingAmount
          amount={numAmt}
          direction={dir === 'DEBIT' ? 'DR' : (dir === 'CREDIT' ? 'CR' : undefined)}
          className={
            size === 'hero' ? 'text-2xl sm:text-3xl font-bold' :
            size === 'lg' ? 'text-lg font-semibold' :
            size === 'sm' ? 'text-xs' : 'text-sm font-medium'
          }
        />
      </div>
    );
  }

  let colorClass = 'text-foreground';
  if (state === 'TO_COLLECT') colorClass = 'text-emerald-600 dark:text-emerald-400 font-semibold';
  else if (state === 'TO_PAY') colorClass = 'text-amber-600 dark:text-amber-400 font-semibold';
  else if (state === 'ADVANCE_RECEIVED') colorClass = 'text-purple-600 dark:text-purple-400 font-medium';
  else if (state === 'ADVANCE_PAID') colorClass = 'text-blue-600 dark:text-blue-400 font-medium';
  else colorClass = 'text-muted-foreground';

  const amountSizeClass = 
    size === 'hero' ? 'text-2xl sm:text-3xl font-bold' :
    size === 'lg' ? 'text-lg font-semibold' :
    size === 'sm' ? 'text-xs' : 'text-sm font-medium';

  return (
    <div className={`inline-flex items-center gap-2 ${className}`}>
      <span className={`font-mono tabular-nums ${amountSizeClass} ${colorClass}`}>
        ₹{formatIndianCurrency(numAmt)}
      </span>
      {showBadge && state !== 'SETTLED' && (
        <PartyBalanceBadge state={state} />
      )}
    </div>
  );
}
