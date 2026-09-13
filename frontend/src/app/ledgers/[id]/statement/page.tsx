"use client";

import React from 'react';
import { useParams } from 'next/navigation';
import DashboardLayout from '@/components/DashboardLayout';
import LedgerStatementView from '@/components/accounting/LedgerStatementView';

export default function LedgerStatementPage() {
  const params = useParams();
  const ledgerId = params.id as string;

  return (
    <DashboardLayout>
      <LedgerStatementView ledgerId={ledgerId} context="account" />
    </DashboardLayout>
  );
}
