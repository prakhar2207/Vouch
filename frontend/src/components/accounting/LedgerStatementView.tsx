"use client";

import React, { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { API_BASE_URL } from '@/utils/api';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import { useCompany } from '@/context/CompanyContext';
import { useFinancialYear } from '@/context/FinancialYearContext';
import { 
  ArrowLeft, 
  Download, 
  Printer, 
  Calendar, 
  SlidersHorizontal, 
  Eye, 
  EyeOff, 
  CheckCircle2, 
  AlertCircle,
  HelpCircle,
  ChevronLeft,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  Scale
} from 'lucide-react';

interface LedgerStatementViewProps {
  ledgerId: string;
  context?: 'party' | 'account';
}

export default function LedgerStatementView({ ledgerId, context = 'party' }: LedgerStatementViewProps) {
  const router = useRouter();
  const { companyId: activeCompanyId } = useCompany();
  const { activeFY } = useFinancialYear();

  const [statementData, setStatementData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters & Options - initialize with activeFY if available
  const [fromDate, setFromDate] = useState<string>(activeFY?.start_date || '');
  const [toDate, setToDate] = useState<string>(activeFY?.end_date || '');
  const [offset, setOffset] = useState<number>(0);
  const limit = 50;
  const [showAccountingDetails, setShowAccountingDetails] = useState<boolean>(false);

  // Synchronize dates whenever active Financial Year changes
  useEffect(() => {
    if (activeFY?.start_date && activeFY?.end_date) {
      setFromDate(activeFY.start_date);
      setToDate(activeFY.end_date);
      setOffset(0);
    }
  }, [activeFY?.id]);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login');
      return;
    }
    fetchStatement();
  }, [ledgerId, activeCompanyId, fromDate, toDate, offset, activeFY?.id]);

  const fetchStatement = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      let cid = activeCompanyId;
      if (!cid) {
        cid = localStorage.getItem('vouch_active_company_id') || '';
      }
      if (!cid) {
        const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
        const list = Array.isArray(compRes.data) ? compRes.data : (compRes.data?.data || []);
        cid = list[0]?.id || '';
      }

      if (!cid) {
        setError('No active company found.');
        return;
      }

      const params = new URLSearchParams();
      params.append('limit', String(limit));
      params.append('offset', String(offset));
      if (fromDate) params.append('from_date', fromDate);
      if (toDate) params.append('to_date', toDate);
      if (activeFY?.id) params.append('financial_year_id', activeFY.id);

      const res = await axios.get(
        `${API_BASE_URL}/api/v1/accounting/reports/ledger-statement/${cid}/${ledgerId}/?${params.toString()}`,
        { headers }
      );

      if (res.data?.success && res.data?.data) {
        setStatementData(res.data.data);
      } else {
        setError('Failed to load statement data.');
      }
    } catch (err: any) {
      console.error('Error fetching statement:', err);
      setError(err?.response?.data?.error || 'Failed to fetch statement.');
    } finally {
      setLoading(false);
    }
  };

  const handleExportCsv = () => {
    if (!statementData?.entries?.length) return;
    const headers = showAccountingDetails
      ? ['Date', 'Voucher #', 'Type', 'Particulars', 'Narration', 'Debit', 'Credit', 'Running Balance', 'Dr/Cr']
      : ['Date', 'Transaction', 'Voucher #', 'Amount', 'Effect', 'Balance'];

    const rows = statementData.entries.map((e: any) => {
      if (showAccountingDetails) {
        return [
          e.date || '',
          e.voucher_number || '',
          e.voucher_type || '',
          `"${(e.particulars || '').replace(/"/g, '""')}"`,
          `"${(e.narration || '').replace(/"/g, '""')}"`,
          e.debit || '0.00',
          e.credit || '0.00',
          e.running_balance || '0.00',
          e.running_balance_type || ''
        ];
      } else {
        return [
          e.date || '',
          e.voucher_type || '',
          e.voucher_number || '',
          e.amount || '0.00',
          e.effect_on_balance || '',
          `${e.running_balance} (${e.running_balance_state || e.running_balance_type})`
        ];
      }
    });

    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((r: any[]) => r.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `statement_${statementData.ledger?.name || 'account'}_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handlePrint = () => {
    window.print();
  };

  const role = statementData?.party_role || 'OTHER';
  const isParty = role === 'CUSTOMER' || role === 'SUPPLIER';
  const state = statementData?.semantic_state || 'SETTLED';
  const displayAmount = parseFloat(statementData?.display_amount || 0);

  // Status badge & owner text
  const statusConfig = useMemo(() => {
    if (state === 'TO_PAY') {
      return {
        badgeBg: 'bg-rose-500/10 border-rose-500/30 text-rose-400',
        headline: 'YOU NEED TO PAY',
        explanation: statementData?.explanation || `You owe this supplier ₹${displayAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`,
        colorClass: 'text-rose-400'
      };
    }
    if (state === 'TO_COLLECT') {
      return {
        badgeBg: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
        headline: 'TO COLLECT',
        explanation: statementData?.explanation || `This customer owes you ₹${displayAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`,
        colorClass: 'text-emerald-400'
      };
    }
    if (state === 'ADVANCE_PAID') {
      return {
        badgeBg: 'bg-blue-500/10 border-blue-500/30 text-blue-400',
        headline: 'ADVANCE PAID',
        explanation: statementData?.explanation || `You have paid ₹${displayAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })} more than billed`,
        colorClass: 'text-blue-400'
      };
    }
    if (state === 'ADVANCE_RECEIVED') {
      return {
        badgeBg: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
        headline: 'ADVANCE RECEIVED',
        explanation: statementData?.explanation || `Customer has paid ₹${displayAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })} more than billed`,
        colorClass: 'text-amber-400'
      };
    }
    return {
      badgeBg: 'bg-muted border-border/40 text-muted-foreground',
      headline: 'SETTLED',
      explanation: 'Nothing outstanding. All bills and payments are balanced.',
      colorClass: 'text-foreground'
    };
  }, [state, displayAmount, statementData]);

  if (loading && !statementData) {
    return (
      <div className="flex flex-col items-center justify-center py-24 space-y-3">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
        <p className="text-xs text-muted-foreground">Loading statement...</p>
      </div>
    );
  }

  if (error && !statementData) {
    return (
      <div className="bg-card border border-rose-500/30 rounded-2xl p-12 text-center max-w-xl mx-auto space-y-4">
        <AlertCircle className="w-10 h-10 text-rose-400 mx-auto" />
        <h2 className="text-lg font-bold text-foreground">Unable to load statement</h2>
        <p className="text-xs text-muted-foreground">{error}</p>
        <button
          onClick={() => router.back()}
          className="px-4 py-2 rounded-xl bg-muted hover:bg-muted/80 text-xs font-semibold text-foreground cursor-pointer"
        >
          Go Back
        </button>
      </div>
    );
  }

  const pagination = statementData?.pagination || { limit: 50, offset: 0, total_count: 0, has_more: false };
  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil((pagination.total_count || 0) / limit));

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Top Breadcrumb & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/40 pb-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.back()}
            className="p-2 rounded-xl bg-card border border-border/60 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            title="Go Back"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl sm:text-2xl font-extrabold tracking-tight text-foreground">
                {statementData?.ledger?.name || 'Account'}
              </h1>
              {role !== 'OTHER' ? (
                <span className="bg-primary/10 text-primary text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider border border-primary/20">
                  {role}
                </span>
              ) : (
                <span className="bg-muted text-muted-foreground text-[10px] font-semibold px-2 py-0.5 rounded-full border border-border/40">
                  {statementData?.ledger?.ledger_type || 'Account'}
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              {context === 'party' ? 'Party Account Statement' : 'General Ledger Account Statement'}
            </p>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setShowAccountingDetails(!showAccountingDetails)}
            className={`px-3 py-1.5 rounded-xl border text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
              showAccountingDetails
                ? 'bg-primary/10 border-primary text-primary'
                : 'bg-card border-border/60 hover:bg-muted text-muted-foreground hover:text-foreground'
            }`}
            title="Toggle detailed accounting view (Dr/Cr, opposing ledgers, vouchers)"
          >
            {showAccountingDetails ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
            <span>{showAccountingDetails ? 'Accounting Details: ON' : 'View Accounting Details'}</span>
          </button>

          <button
            onClick={handleExportCsv}
            disabled={!statementData?.entries?.length}
            className="px-3 py-1.5 rounded-xl bg-card border border-border/60 hover:bg-muted text-muted-foreground hover:text-foreground text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
          >
            <Download className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Export CSV</span>
          </button>

          <button
            onClick={handlePrint}
            className="px-3 py-1.5 rounded-xl bg-card border border-border/60 hover:bg-muted text-muted-foreground hover:text-foreground text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
          >
            <Printer className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Print</span>
          </button>
        </div>
      </div>

      {/* Hero Card for Business Owner */}
      <div className="bg-card border border-border/50 rounded-2xl p-5 sm:p-6 shadow-sm relative overflow-hidden">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className={`text-xs font-mono font-bold px-2.5 py-0.5 rounded-full border uppercase tracking-wider ${statusConfig.badgeBg}`}>
                {statusConfig.headline}
              </span>
              {showAccountingDetails && (
                <span className="text-[10px] font-mono text-muted-foreground">
                  Normal: {statementData?.ledger?.normal_balance || 'DEBIT'}
                </span>
              )}
            </div>
            <div className="flex items-baseline gap-2 pt-1">
              <span className={`text-3xl sm:text-4xl font-extrabold font-mono tracking-tight ${statusConfig.colorClass}`}>
                ₹{displayAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
              {showAccountingDetails && (
                <span className="text-xs font-bold text-muted-foreground uppercase">
                  {statementData?.closing_balance_type}
                </span>
              )}
            </div>
            <p className="text-xs sm:text-sm text-muted-foreground font-medium pt-0.5">
              {statusConfig.explanation}
            </p>
          </div>

          {/* Date Filter Controls */}
          <div className="flex items-center gap-2 bg-muted/40 border border-border/40 p-2 rounded-xl text-xs flex-wrap sm:flex-nowrap w-full sm:w-auto">
            {activeFY && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold bg-primary/10 text-primary border border-primary/20 whitespace-nowrap">
                FY {activeFY.code}
              </span>
            )}
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <Calendar className="w-3.5 h-3.5" />
              <span className="font-medium">From:</span>
              <input
                type="date"
                value={fromDate}
                onChange={(e) => { setFromDate(e.target.value); setOffset(0); }}
                className="bg-card border border-border/60 rounded-lg px-2 py-1 text-foreground focus:outline-none focus:ring-1 focus:ring-primary text-xs"
              />
            </div>
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <span className="font-medium">To:</span>
              <input
                type="date"
                value={toDate}
                onChange={(e) => { setToDate(e.target.value); setOffset(0); }}
                className="bg-card border border-border/60 rounded-lg px-2 py-1 text-foreground focus:outline-none focus:ring-1 focus:ring-primary text-xs"
              />
            </div>
            {(fromDate || toDate) && (
              <button
                onClick={() => {
                  setFromDate(activeFY?.start_date || '');
                  setToDate(activeFY?.end_date || '');
                  setOffset(0);
                }}
                className="text-[11px] font-semibold text-primary hover:underline px-1 cursor-pointer"
                title="Reset to Financial Year default"
              >
                Reset
              </button>
            )}
          </div>
        </div>
      </div>

      {/* 4 Summary Metric Cards (Authoritative from Backend) */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <div className="bg-card border border-border/40 rounded-xl p-4 shadow-sm space-y-1">
          <p className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">Opening Balance</p>
          <div className="flex items-baseline gap-1.5">
            <span className="text-lg sm:text-xl font-bold font-mono text-foreground">
              ₹{parseFloat(statementData?.opening_balance || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </span>
            <span className="text-[10px] font-mono font-semibold text-muted-foreground">
              {statementData?.opening_balance_type}
            </span>
          </div>
          <p className="text-[10px] text-muted-foreground">Before period transactions</p>
        </div>

        <div className="bg-card border border-border/40 rounded-xl p-4 shadow-sm space-y-1">
          <p className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>Total Debits</span>
            <TrendingUp className="w-3.5 h-3.5 text-blue-400" />
          </p>
          <div className="flex items-baseline gap-1.5">
            <span className="text-lg sm:text-xl font-bold font-mono text-blue-400">
              ₹{parseFloat(statementData?.period_debit || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </span>
          </div>
          <p className="text-[10px] text-muted-foreground">Inflow / charges during period</p>
        </div>

        <div className="bg-card border border-border/40 rounded-xl p-4 shadow-sm space-y-1">
          <p className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>Total Credits</span>
            <TrendingDown className="w-3.5 h-3.5 text-emerald-400" />
          </p>
          <div className="flex items-baseline gap-1.5">
            <span className="text-lg sm:text-xl font-bold font-mono text-emerald-400">
              ₹{parseFloat(statementData?.period_credit || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </span>
          </div>
          <p className="text-[10px] text-muted-foreground">Outflow / payments during period</p>
        </div>

        <div className="bg-card border border-border/40 rounded-xl p-4 shadow-sm space-y-1">
          <p className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>Closing Balance</span>
            <Scale className="w-3.5 h-3.5 text-foreground" />
          </p>
          <div className="flex items-baseline gap-1.5">
            <span className="text-lg sm:text-xl font-bold font-mono text-foreground">
              ₹{parseFloat(statementData?.closing_balance || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </span>
            <span className="text-[10px] font-mono font-semibold text-muted-foreground">
              {statementData?.closing_balance_type}
            </span>
          </div>
          <p className="text-[10px] text-muted-foreground">Final net balance</p>
        </div>
      </div>

      {/* Transaction History Table */}
      <div className="bg-card border border-border/50 rounded-2xl shadow-sm overflow-hidden">
        <div className="p-4 sm:p-5 border-b border-border/40 bg-muted/20 flex justify-between items-center flex-wrap gap-2">
          <div>
            <h2 className="text-sm sm:text-base font-bold text-foreground">Transaction History</h2>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Showing {statementData?.entries?.length || 0} entries of {pagination.total_count || 0} total
            </p>
          </div>
          <div className="text-xs font-mono text-muted-foreground">
            Page {currentPage} of {totalPages}
          </div>
        </div>

        {statementData?.entries?.length === 0 ? (
          <div className="p-16 text-center space-y-3">
            <div className="w-12 h-12 rounded-full bg-muted/50 border border-border/60 flex items-center justify-center mx-auto text-muted-foreground">
              <Calendar className="w-6 h-6 opacity-60" />
            </div>
            <p className="text-xs font-semibold text-foreground">No transactions found</p>
            <p className="text-[11px] text-muted-foreground max-w-sm mx-auto">
              There are no recorded vouchers for this account during the selected date range.
            </p>
          </div>
        ) : (
          <>
            {/* Desktop Table */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-muted/30 border-b border-border/40 text-muted-foreground font-bold uppercase tracking-wider text-[10px]">
                  <tr>
                    <th className="py-3 px-4">Date</th>
                    <th className="py-3 px-4">Voucher</th>
                    <th className="py-3 px-4">Type</th>
                    <th className="py-3 px-4">Particulars</th>
                    {showAccountingDetails ? (
                      <>
                        <th className="py-3 px-4 text-right">Debit (Dr)</th>
                        <th className="py-3 px-4 text-right">Credit (Cr)</th>
                        <th className="py-3 px-4 text-right">Running Balance</th>
                      </>
                    ) : (
                      <>
                        <th className="py-3 px-4 text-right">Amount</th>
                        <th className="py-3 px-4 text-right">Effect</th>
                        <th className="py-3 px-4 text-right">Balance</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/30">
                  {statementData.entries.map((entry: any) => {
                    const dr = parseFloat(entry.debit || 0);
                    const cr = parseFloat(entry.credit || 0);
                    const amt = parseFloat(entry.amount || (dr > 0 ? dr : cr));
                    const isPositive = entry.effect_sign === '+';

                    return (
                      <tr key={entry.id} className="hover:bg-muted/20 transition-colors">
                        <td className="py-3 px-4 whitespace-nowrap text-muted-foreground font-mono">
                          {entry.date || '-'}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap font-mono font-semibold text-foreground">
                          {entry.voucher_number || '-'}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <span className="bg-muted text-muted-foreground text-[10px] font-semibold px-2 py-0.5 rounded border border-border/40">
                            {entry.voucher_type || 'VOUCHER'}
                          </span>
                        </td>
                        <td className="py-3 px-4 max-w-xs truncate text-foreground font-medium">
                          {entry.particulars}
                          {entry.narration && entry.narration !== entry.particulars && (
                            <span className="block text-[10px] text-muted-foreground font-normal truncate">
                              {entry.narration}
                            </span>
                          )}
                        </td>

                        {showAccountingDetails ? (
                          <>
                            <td className="py-3 px-4 text-right font-mono font-semibold tabular-nums text-blue-400">
                              {dr > 0 ? `₹${dr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : '—'}
                            </td>
                            <td className="py-3 px-4 text-right font-mono font-semibold tabular-nums text-emerald-400">
                              {cr > 0 ? `₹${cr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : '—'}
                            </td>
                            <td className="py-3 px-4 text-right font-mono font-bold tabular-nums text-foreground">
                              ₹{parseFloat(entry.running_balance || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}{' '}
                              <span className="text-[10px] font-semibold text-muted-foreground">
                                {entry.running_balance_type}
                              </span>
                            </td>
                          </>
                        ) : (
                          <>
                            <td className="py-3 px-4 text-right font-mono font-bold tabular-nums text-foreground">
                              ₹{amt.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                            </td>
                            <td className="py-3 px-4 text-right font-mono font-semibold tabular-nums">
                              <span className={isPositive ? 'text-emerald-400' : 'text-rose-400'}>
                                {entry.effect_on_balance || `₹${amt.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`}
                              </span>
                            </td>
                            <td className="py-3 px-4 text-right font-mono font-bold tabular-nums text-foreground">
                              ₹{parseFloat(entry.running_balance || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                            </td>
                          </>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Mobile Cards (< md) */}
            <div className="block md:hidden divide-y divide-border/30">
              {statementData.entries.map((entry: any) => {
                const dr = parseFloat(entry.debit || 0);
                const cr = parseFloat(entry.credit || 0);
                const amt = parseFloat(entry.amount || (dr > 0 ? dr : cr));
                const isPositive = entry.effect_sign === '+';

                return (
                  <div key={entry.id} className="p-4 space-y-2">
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="font-mono text-muted-foreground">{entry.date || '-'}</span>
                      <span className="bg-muted text-muted-foreground text-[10px] font-semibold px-2 py-0.5 rounded border border-border/40">
                        {entry.voucher_type}
                      </span>
                    </div>

                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <span className="font-mono font-bold text-foreground text-xs">{entry.voucher_number}</span>
                        <p className="text-xs font-medium text-foreground mt-0.5">{entry.particulars}</p>
                        {entry.narration && entry.narration !== entry.particulars && (
                          <p className="text-[10px] text-muted-foreground mt-0.5">{entry.narration}</p>
                        )}
                      </div>
                      <div className="text-right">
                        <span className="font-mono font-extrabold text-foreground text-sm">
                          ₹{amt.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                        <span className={`block font-mono text-[11px] font-bold ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {entry.effect_on_balance}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center justify-between pt-2 border-t border-border/20 text-[11px] text-muted-foreground">
                      <span>Running Balance:</span>
                      <span className="font-mono font-bold text-foreground">
                        ₹{parseFloat(entry.running_balance || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}{' '}
                        {showAccountingDetails ? entry.running_balance_type : ''}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}

        {/* Pagination Footer */}
        {totalPages > 1 && (
          <div className="p-4 border-t border-border/40 bg-muted/10 flex items-center justify-between text-xs">
            <button
              onClick={() => setOffset(Math.max(0, offset - limit))}
              disabled={offset === 0}
              className="px-3 py-1.5 rounded-xl border border-border/60 bg-card hover:bg-muted text-muted-foreground hover:text-foreground font-semibold flex items-center gap-1 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
              <span>Previous</span>
            </button>
            <span className="text-muted-foreground font-mono">
              Page {currentPage} of {totalPages}
            </span>
            <button
              onClick={() => setOffset(offset + limit)}
              disabled={!pagination.has_more}
              className="px-3 py-1.5 rounded-xl border border-border/60 bg-card hover:bg-muted text-muted-foreground hover:text-foreground font-semibold flex items-center gap-1 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <span>Next</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
