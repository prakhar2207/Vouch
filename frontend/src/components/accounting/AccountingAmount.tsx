"use client";

import React from 'react';

interface AccountingAmountProps {
  amount: number | string;
  currency?: string;
  direction?: 'DR' | 'CR' | 'NONE' | null;
  sign?: '+' | '-' | null;
  className?: string;
  showZeroAsBlank?: boolean;
}

export const formatIndianCurrency = (val: number | string): string => {
  const num = typeof val === 'string' ? parseFloat(val) : val;
  if (isNaN(num)) return '0.00';
  return num.toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
};

export default function AccountingAmount({
  amount,
  currency = '₹',
  direction,
  sign,
  className = '',
  showZeroAsBlank = false,
}: AccountingAmountProps) {
  const num = typeof amount === 'string' ? parseFloat(amount) : amount;
  
  if (isNaN(num) || (showZeroAsBlank && num === 0)) {
    return <span className={`font-mono tabular-nums ${className}`}>—</span>;
  }

  const formatted = formatIndianCurrency(Math.abs(num));
  const signPrefix = sign ? sign : (num < 0 ? '-' : '');

  return (
    <span className={`font-mono tabular-nums tracking-tight ${className}`}>
      {signPrefix}{currency}{formatted}
      {direction && direction !== 'NONE' && (
        <span className="ml-1 text-[0.8em] font-sans font-medium text-muted-foreground uppercase">
          {direction === 'DR' ? 'Dr' : 'Cr'}
        </span>
      )}
    </span>
  );
}
