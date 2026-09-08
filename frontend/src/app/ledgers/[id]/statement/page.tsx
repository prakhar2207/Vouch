"use client";

import React, { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import Link from 'next/link';
import { useRouter, useParams } from 'next/navigation';
import { API_BASE_URL } from '@/utils/api';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import { useToast } from '@/context/ToastContext';
import {
  ArrowLeft,
  Calendar,
  Download,
  Printer,
  Search,
  FileText,
  Layers,
  Building2,
  Wallet,
  Scale,
  ArrowDownLeft,
  ArrowUpRight,
  RefreshCw,
  ExternalLink,
  ChevronRight,
  ChevronLeft,
  Receipt,
  X
} from 'lucide-react';

interface StatementEntry {
  id: string;
  voucher_id?: string;
  date: string | null;
  particulars: string;
  opposing_ledger_name: string;
  opposing_details: Array<{ ledger_id: string; ledger_name: string; amount: number }>;
  voucher_number: string;
  voucher_type: string;
  narration?: string;
  debit: number;
  credit: number;
  running_balance: number;
  running_balance_type: 'DR' | 'CR';
}

interface PaginationData {
  total_count: number;
  limit: number;
  offset: number;
  has_more: boolean;
  page: number;
  total_pages: number;
}

interface StatementData {
  ledger_id: string;
  ledger_name: string;
  group_name: string;
  nature: 'ASSET' | 'LIABILITY' | 'INCOME' | 'EXPENSE' | 'EQUITY';
  normal_balance_type: 'DEBIT' | 'CREDIT';
  gstin?: string;
  state_code?: string;
  phone?: string;
  email?: string;
  from_date?: string | null;
  to_date?: string | null;
  period_opening_balance: number;
  period_opening_type: 'DEBIT' | 'CREDIT';
  page_opening_balance?: number;
  page_opening_type?: 'DEBIT' | 'CREDIT';
  total_debit: number;
  total_credit: number;
  net_movement: number;
  closing_balance: number;
  closing_type: 'DEBIT' | 'CREDIT';
  entries: StatementEntry[];
  pagination?: PaginationData;
}

export default function LedgerStatementPage() {
  const router = useRouter();
  const params = useParams();
  const ledgerId = params.id as string;
  const { toast } = useToast();

  const [companyId, setCompanyId] = useState('');
  const [statementData, setStatementData] = useState<StatementData | null>(null);
  const [loading, setLoading] = useState(true);

  // Pagination State
  const [page, setPage] = useState<number>(1);
  const pageSize = 50;

  // Date Filters
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [activePreset, setActivePreset] = useState<'ALL' | 'FY' | 'QUARTER' | 'MONTH' | '30DAYS'>('ALL');

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login');
      return;
    }
    fetchStatement();
  }, [router, ledgerId]);

  const fetchStatement = async (overrideFrom?: string, overrideTo?: string, targetPage: number = page) => {
    setLoading(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      // 1. Get current company
      let cid = companyId;
      if (!cid) {
        const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
        cid = compRes.data.data[0]?.id;
        if (!cid) return;
        setCompanyId(cid);
      }

      // 2. Build query parameters
      const fDate = overrideFrom !== undefined ? overrideFrom : fromDate;
      const tDate = overrideTo !== undefined ? overrideTo : toDate;

      const offset = (targetPage - 1) * pageSize;
      const queryParams = new URLSearchParams();
      if (fDate) queryParams.append('from_date', fDate);
      if (tDate) queryParams.append('to_date', tDate);
      queryParams.append('limit', String(pageSize));
      queryParams.append('offset', String(offset));

      const res = await axios.get(
        `${API_BASE_URL}/api/v1/accounting/reports/ledger-statement/${cid}/${ledgerId}/?${queryParams.toString()}`,
        { headers }
      );

      if (res.data.success) {
        setStatementData(res.data.data);
        setPage(targetPage);
      } else {
        toast.error('Failed to load statement', res.data.error || 'Unknown error');
      }
    } catch (err: any) {
      console.error(err);
      toast.error('Error', err.response?.data?.error || err.message);
    } finally {
      setLoading(false);
    }
  };

  // Quick Preset Handler
  const applyPreset = (preset: 'ALL' | 'FY' | 'QUARTER' | 'MONTH' | '30DAYS') => {
    setActivePreset(preset);
    const today = new Date();
    const formatDate = (d: Date) => d.toISOString().split('T')[0];

    if (preset === 'ALL') {
      setFromDate('');
      setToDate('');
      fetchStatement('', '', 1);
    } else if (preset === 'FY') {
      // Indian Financial Year: April 1 to March 31
      const currentYear = today.getMonth() >= 3 ? today.getFullYear() : today.getFullYear() - 1;
      const start = new Date(currentYear, 3, 1);
      const end = new Date(currentYear + 1, 2, 31);
      const f = formatDate(start);
      const t = formatDate(end);
      setFromDate(f);
      setToDate(t);
      fetchStatement(f, t, 1);
    } else if (preset === 'MONTH') {
      const start = new Date(today.getFullYear(), today.getMonth(), 1);
      const end = new Date(today.getFullYear(), today.getMonth() + 1, 0);
      const f = formatDate(start);
      const t = formatDate(end);
      setFromDate(f);
      setToDate(t);
      fetchStatement(f, t, 1);
    } else if (preset === '30DAYS') {
      const start = new Date();
      start.setDate(today.getDate() - 30);
      const f = formatDate(start);
      const t = formatDate(today);
      setFromDate(f);
      setToDate(t);
      fetchStatement(f, t, 1);
    } else if (preset === 'QUARTER') {
      const q = Math.floor(today.getMonth() / 3);
      const start = new Date(today.getFullYear(), q * 3, 1);
      const end = new Date(today.getFullYear(), (q + 1) * 3, 0);
      const f = formatDate(start);
      const t = formatDate(end);
      setFromDate(f);
      setToDate(t);
      fetchStatement(f, t, 1);
    }
  };

  const handleApplyFilter = (e: React.FormEvent) => {
    e.preventDefault();
    setActivePreset('ALL');
    fetchStatement(fromDate, toDate, 1);
  };

  const handleResetFilter = () => {
    setActivePreset('ALL');
    setFromDate('');
    setToDate('');
    setSearchTerm('');
    fetchStatement('', '', 1);
  };

  // Dynamic Running Balance Logic (Continuous Double-Entry Computation)
  const computedRows = useMemo(() => {
    if (!statementData) return [];

    const isDebitNormal =
      statementData.nature === 'ASSET' ||
      statementData.nature === 'EXPENSE' ||
      statementData.normal_balance_type === 'DEBIT';

    const startBalance = statementData.page_opening_balance !== undefined
      ? statementData.page_opening_balance
      : statementData.period_opening_balance;
    const startType = statementData.page_opening_type || statementData.period_opening_type;

    let runningNet = isDebitNormal
      ? (startType === 'DEBIT' ? startBalance : -startBalance)
      : (startType === 'CREDIT' ? startBalance : -startBalance);

    return statementData.entries.map(entry => {
      // If backend calculated running balance, use it directly (preserves exact ledger continuum across pages)
      if (entry.running_balance !== undefined) {
        return {
          ...entry,
          dynamic_balance: entry.running_balance,
          dynamic_balance_type: entry.running_balance_type || 'DR',
        };
      }

      const dr = Number(entry.debit || 0);
      const cr = Number(entry.credit || 0);

      const delta = isDebitNormal ? (dr - cr) : (cr - dr);
      runningNet += delta;

      const dynamicBalance = Math.abs(runningNet);
      const dynamicType: 'DR' | 'CR' = isDebitNormal
        ? (runningNet >= 0 ? 'DR' : 'CR')
        : (runningNet >= 0 ? 'CR' : 'DR');

      return {
        ...entry,
        dynamic_balance: dynamicBalance,
        dynamic_balance_type: dynamicType,
      };
    });
  }, [statementData]);

  // Client-side text filtering
  const filteredRows = useMemo(() => {
    if (!searchTerm.trim()) return computedRows;
    const q = searchTerm.toLowerCase();
    return computedRows.filter(r =>
      r.particulars?.toLowerCase().includes(q) ||
      r.voucher_number?.toLowerCase().includes(q) ||
      r.voucher_type?.toLowerCase().includes(q) ||
      r.narration?.toLowerCase().includes(q) ||
      r.opposing_ledger_name?.toLowerCase().includes(q)
    );
  }, [computedRows, searchTerm]);

  // Export to CSV
  const handleExportCSV = () => {
    if (!statementData) return;

    const headers = [
      'Date',
      'Particulars (Opposing Ledger)',
      'Voucher Type',
      'Voucher No',
      'Debit (Dr)',
      'Credit (Cr)',
      'Running Balance',
      'Balance Type',
      'Narration'
    ];

    const openingRow = [
      statementData.from_date || 'Initial',
      'Opening Balance (b/f)',
      '-',
      '-',
      statementData.period_opening_type === 'DEBIT' ? statementData.period_opening_balance.toFixed(2) : '0.00',
      statementData.period_opening_type === 'CREDIT' ? statementData.period_opening_balance.toFixed(2) : '0.00',
      statementData.period_opening_balance.toFixed(2),
      statementData.period_opening_type === 'DEBIT' ? 'Dr' : 'Cr',
      'Balance brought forward'
    ];

    const dataRows = computedRows.map(r => [
      r.date || '',
      `"${r.particulars.replace(/"/g, '""')}"`,
      r.voucher_type,
      `"${r.voucher_number}"`,
      r.debit > 0 ? r.debit.toFixed(2) : '0.00',
      r.credit > 0 ? r.credit.toFixed(2) : '0.00',
      r.dynamic_balance.toFixed(2),
      r.dynamic_balance_type === 'DR' ? 'Dr' : 'Cr',
      `"${(r.narration || '').replace(/"/g, '""')}"`
    ]);

    const closingRow = [
      statementData.to_date || 'Closing',
      'Closing Balance (c/f)',
      'TOTAL',
      '-',
      statementData.total_debit.toFixed(2),
      statementData.total_credit.toFixed(2),
      statementData.closing_balance.toFixed(2),
      statementData.closing_type === 'DEBIT' ? 'Dr' : 'Cr',
      'Balance carried forward'
    ];

    const csvContent = [
      `"Ledger Account Statement: ${statementData.ledger_name}"`,
      `"Group: ${statementData.group_name} (${statementData.nature})"`,
      `"Period: ${statementData.from_date || 'Start'} to ${statementData.to_date || 'Current'}"`,
      '',
      headers.join(','),
      openingRow.join(','),
      ...dataRows.map(row => row.join(',')),
      closingRow.join(',')
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `${statementData.ledger_name.replace(/\s+/g, '_')}_Statement.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success('Export Successful', `Exported statement for "${statementData.ledger_name}".`);
  };

  // Print Handler
  const handlePrint = () => {
    window.print();
  };

  return (
    <DashboardLayout>
      <div className="max-w-[1600px] mx-auto p-4 sm:p-6 space-y-6 print:p-0 print:m-0">
        {/* Navigation & Actions Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-card border border-border p-5 sm:p-6 rounded-2xl shadow-sm print:hidden">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push('/ledgers')}
              className="p-2.5 rounded-xl border border-border hover:bg-muted text-muted-foreground hover:text-foreground transition-all cursor-pointer"
              title="Back to Chart of Accounts"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Link href="/ledgers" className="hover:text-foreground transition-colors">
                  Chart of Accounts
                </Link>
                <ChevronRight className="w-3.5 h-3.5" />
                <span className="text-foreground font-medium">Ledger Statement</span>
              </div>
              <h1 className="text-2xl font-bold text-foreground tracking-tight mt-1 flex items-center gap-2">
                <span>{statementData?.ledger_name || 'Account Statement'}</span>
                {statementData?.nature && (
                  <span
                    className={`text-[11px] font-semibold px-2 py-0.5 rounded-full uppercase border ${
                      statementData.nature === 'ASSET'
                        ? 'bg-blue-500/10 text-blue-400 border-blue-500/20'
                        : statementData.nature === 'LIABILITY'
                        ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                        : statementData.nature === 'INCOME'
                        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                        : 'bg-rose-500/10 text-rose-400 border-rose-500/20'
                    }`}
                  >
                    {statementData.nature}
                  </span>
                )}
              </h1>
              <p className="text-xs text-muted-foreground mt-0.5">
                {statementData?.group_name ? `Group: ${statementData.group_name} • ` : ''}
                Normal Balance: {statementData?.normal_balance_type === 'DEBIT' ? 'Debit (Dr)' : 'Credit (Cr)'}
                {statementData?.gstin ? ` • GSTIN: ${statementData.gstin}` : ''}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto">
            <button
              onClick={() => fetchStatement()}
              className="p-2.5 rounded-xl border border-border hover:bg-muted text-muted-foreground hover:text-foreground transition-all cursor-pointer"
              title="Refresh Statement"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={handleExportCSV}
              disabled={loading || !statementData}
              className="flex-1 sm:flex-initial flex items-center justify-center gap-1.5 px-3.5 py-2.5 bg-muted hover:bg-muted/80 border border-border text-foreground rounded-xl text-xs font-medium transition-all cursor-pointer disabled:opacity-50"
              title="Download CSV"
            >
              <Download className="w-3.5 h-3.5 text-blue-400" />
              <span>Export CSV</span>
            </button>
            <button
              onClick={handlePrint}
              disabled={loading || !statementData}
              className="flex-1 sm:flex-initial flex items-center justify-center gap-1.5 px-3.5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-medium transition-all shadow-md shadow-blue-500/10 cursor-pointer disabled:opacity-50"
              title="Print Statement"
            >
              <Printer className="w-3.5 h-3.5" />
              <span>Print Statement</span>
            </button>
          </div>
        </div>

        {/* Print-Only Header */}
        <div className="hidden print:block border-b border-zinc-800 pb-4 mb-4">
          <div className="flex justify-between items-start">
            <div>
              <h1 className="text-2xl font-bold text-black font-sans">{statementData?.ledger_name}</h1>
              <p className="text-sm text-zinc-600 font-sans">
                Group: {statementData?.group_name} ({statementData?.nature}) • Normal Balance: {statementData?.normal_balance_type}
              </p>
              {statementData?.gstin && (
                <p className="text-xs text-zinc-600 font-mono">GSTIN: {statementData.gstin}</p>
              )}
            </div>
            <div className="text-right text-xs text-zinc-600 font-sans">
              <p className="font-semibold text-black">Statement Period</p>
              <p>{statementData?.from_date || 'Beginning'} to {statementData?.to_date || 'Today'}</p>
              <p className="text-[10px] text-zinc-400 mt-1">Generated: {new Date().toLocaleDateString()}</p>
            </div>
          </div>
        </div>

        {/* Summary Metric Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 print:grid-cols-5">
          {/* Opening Balance */}
          <div className="bg-card border border-border p-4 rounded-xl shadow-2xs">
            <div className="text-xs text-muted-foreground font-medium flex items-center justify-between">
              <span>Opening Balance</span>
              <span className="text-[10px] bg-muted px-1.5 py-0.2 rounded font-mono">b/f</span>
            </div>
            <div className="text-xl font-bold font-mono text-foreground mt-1.5 flex items-baseline gap-1">
              <span>₹{(statementData?.period_opening_balance || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
              <span className="text-xs font-semibold text-blue-400">
                {statementData?.period_opening_type === 'DEBIT' ? 'Dr' : 'Cr'}
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5 truncate">
              {statementData?.from_date ? `As of ${statementData.from_date}` : 'Initial Opening'}
            </p>
          </div>

          {/* Total Debit */}
          <div className="bg-card border border-border p-4 rounded-xl shadow-2xs">
            <div className="text-xs text-blue-400 font-medium flex items-center justify-between">
              <span className="flex items-center gap-1">
                <ArrowDownLeft className="w-3.5 h-3.5" /> Total Debit (In)
              </span>
              <span className="text-[10px] bg-blue-500/10 border border-blue-500/20 text-blue-400 px-1.5 py-0.2 rounded font-mono">Dr</span>
            </div>
            <div className="text-xl font-bold font-mono text-blue-400 mt-1.5">
              ₹{(statementData?.total_debit || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Total amount debited
            </p>
          </div>

          {/* Total Credit */}
          <div className="bg-card border border-border p-4 rounded-xl shadow-2xs">
            <div className="text-xs text-amber-400 font-medium flex items-center justify-between">
              <span className="flex items-center gap-1">
                <ArrowUpRight className="w-3.5 h-3.5" /> Total Credit (Out)
              </span>
              <span className="text-[10px] bg-amber-500/10 border border-amber-500/20 text-amber-400 px-1.5 py-0.2 rounded font-mono">Cr</span>
            </div>
            <div className="text-xl font-bold font-mono text-amber-400 mt-1.5">
              ₹{(statementData?.total_credit || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Total amount credited
            </p>
          </div>

          {/* Net Movement */}
          <div className="bg-card border border-border p-4 rounded-xl shadow-2xs">
            <div className="text-xs text-purple-400 font-medium flex items-center justify-between">
              <span className="flex items-center gap-1">
                <Scale className="w-3.5 h-3.5" /> Net Flow
              </span>
            </div>
            <div className="text-xl font-bold font-mono text-purple-400 mt-1.5">
              ₹{Math.abs(statementData?.net_movement || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              {(statementData?.net_movement || 0) >= 0 ? 'Net Inflow (+)' : 'Net Outflow (-)'}
            </p>
          </div>

          {/* Closing Balance */}
          <div className="bg-card border border-border p-4 rounded-xl shadow-2xs">
            <div className="text-xs text-emerald-400 font-medium flex items-center justify-between">
              <span>Closing Balance</span>
              <span className="text-[10px] bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 px-1.5 py-0.2 rounded font-mono">c/f</span>
            </div>
            <div className="text-xl font-bold font-mono text-emerald-400 mt-1.5 flex items-baseline gap-1">
              <span>₹{(statementData?.closing_balance || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
              <span className="text-xs font-semibold text-emerald-400">
                {statementData?.closing_type === 'DEBIT' ? 'Dr' : 'Cr'}
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              {statementData?.to_date ? `As of ${statementData.to_date}` : 'Current Closing'}
            </p>
          </div>
        </div>

        {/* Date Filter Toolbar */}
        <div className="bg-card border border-border p-4 rounded-2xl shadow-sm space-y-3 print:hidden">
          <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3">
            {/* Quick Presets */}
            <div className="flex items-center gap-1 bg-muted/60 p-1 rounded-xl border border-border/60 overflow-x-auto">
              {[
                { id: 'ALL', label: 'All Time' },
                { id: 'FY', label: 'This FY' },
                { id: 'QUARTER', label: 'This Quarter' },
                { id: 'MONTH', label: 'This Month' },
                { id: '30DAYS', label: 'Last 30 Days' },
              ].map(preset => (
                <button
                  key={preset.id}
                  onClick={() => applyPreset(preset.id as any)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer whitespace-nowrap ${
                    activePreset === preset.id
                      ? 'bg-card text-foreground shadow-2xs font-semibold'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {preset.label}
                </button>
              ))}
            </div>

            {/* Custom Date Inputs & Search */}
            <form onSubmit={handleApplyFilter} className="flex flex-wrap sm:flex-nowrap items-center gap-2">
              <div className="flex items-center gap-1.5 bg-muted/40 border border-border rounded-xl px-2.5 py-1.5 text-xs">
                <Calendar className="w-3.5 h-3.5 text-muted-foreground" />
                <span className="text-muted-foreground text-[11px]">From:</span>
                <input
                  type="date"
                  value={fromDate}
                  onChange={e => setFromDate(e.target.value)}
                  className="bg-transparent text-foreground focus:outline-none text-xs"
                />
              </div>

              <div className="flex items-center gap-1.5 bg-muted/40 border border-border rounded-xl px-2.5 py-1.5 text-xs">
                <Calendar className="w-3.5 h-3.5 text-muted-foreground" />
                <span className="text-muted-foreground text-[11px]">To:</span>
                <input
                  type="date"
                  value={toDate}
                  onChange={e => setToDate(e.target.value)}
                  className="bg-transparent text-foreground focus:outline-none text-xs"
                />
              </div>

              <button
                type="submit"
                className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-medium transition-all cursor-pointer"
              >
                Apply
              </button>

              {(fromDate || toDate) && (
                <button
                  type="button"
                  onClick={handleResetFilter}
                  className="p-1.5 border border-border hover:bg-muted text-muted-foreground hover:text-foreground rounded-xl transition-all cursor-pointer"
                  title="Reset Filter"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}

              {/* In-table search */}
              <div className="relative w-full sm:w-56">
                <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={searchTerm}
                  onChange={e => setSearchTerm(e.target.value)}
                  placeholder="Search particulars, voucher..."
                  className="w-full pl-8 pr-3 py-1.5 bg-muted/40 border border-border rounded-xl text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>
            </form>
          </div>
        </div>

        {/* Statement Data Table */}
        <div className="bg-card border border-border rounded-2xl shadow-sm overflow-hidden print:border-none print:shadow-none">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead className="bg-muted/40 text-muted-foreground border-b border-border uppercase tracking-wider font-semibold print:bg-zinc-100 print:text-black">
                <tr>
                  <th className="py-3 px-4 w-28">Date</th>
                  <th className="py-3 px-4">Particulars (Opposing Ledger)</th>
                  <th className="py-3 px-4 w-28">Voucher Type</th>
                  <th className="py-3 px-4 w-32">Voucher No.</th>
                  <th className="py-3 px-4 text-right w-32">Debit (Dr)</th>
                  <th className="py-3 px-4 text-right w-32">Credit (Cr)</th>
                  <th className="py-3 px-4 text-right w-36">Running Balance</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60 text-foreground print:divide-zinc-300">
                {/* 1. Opening Balance Row */}
                <tr className="bg-muted/20 font-medium text-muted-foreground">
                  <td className="py-3 px-4 font-mono text-[11px]">
                    {page > 1 ? `Page ${page}` : (statementData?.from_date || 'Initial')}
                  </td>
                  <td className="py-3 px-4">
                    <span className="font-semibold text-foreground">
                      {page > 1 ? `Balance Brought Forward (Page ${page})` : 'Opening Balance (b/f)'}
                    </span>
                    <span className="text-[10px] text-muted-foreground ml-2">
                      {page > 1 ? 'Cumulative balance from prior entries' : 'Balance brought forward'}
                    </span>
                  </td>
                  <td className="py-3 px-4 font-mono text-[11px]">—</td>
                  <td className="py-3 px-4 font-mono text-[11px]">—</td>
                  <td className="py-3 px-4 text-right font-mono">
                    {(() => {
                      const opBal = page > 1 ? (statementData?.page_opening_balance ?? 0) : (statementData?.period_opening_balance ?? 0);
                      const opType = page > 1 ? (statementData?.page_opening_type || 'DEBIT') : (statementData?.period_opening_type || 'DEBIT');
                      return opType === 'DEBIT' && opBal > 0 ? (
                        <span className="text-foreground font-semibold">
                          ₹{opBal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                      ) : (
                        <span>—</span>
                      );
                    })()}
                  </td>
                  <td className="py-3 px-4 text-right font-mono">
                    {(() => {
                      const opBal = page > 1 ? (statementData?.page_opening_balance ?? 0) : (statementData?.period_opening_balance ?? 0);
                      const opType = page > 1 ? (statementData?.page_opening_type || 'CREDIT') : (statementData?.period_opening_type || 'CREDIT');
                      return opType === 'CREDIT' && opBal > 0 ? (
                        <span className="text-foreground font-semibold">
                          ₹{opBal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                      ) : (
                        <span>—</span>
                      );
                    })()}
                  </td>
                  <td className="py-3 px-4 text-right font-mono font-semibold">
                    {(() => {
                      const opBal = page > 1 ? (statementData?.page_opening_balance ?? 0) : (statementData?.period_opening_balance ?? 0);
                      const opType = page > 1 ? (statementData?.page_opening_type || 'DEBIT') : (statementData?.period_opening_type || 'DEBIT');
                      return (
                        <div className="inline-flex items-center justify-end gap-1">
                          <span className="text-foreground">
                            ₹{opBal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                          </span>
                          <span
                            className={`text-[10px] font-bold px-1 rounded ${
                              opType === 'DEBIT'
                                ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                                : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                            }`}
                          >
                            {opType === 'DEBIT' ? 'Dr' : 'Cr'}
                          </span>
                        </div>
                      );
                    })()}
                  </td>
                </tr>

                {/* Loading State */}
                {loading ? (
                  <tr>
                    <td colSpan={7} className="text-center py-16 text-muted-foreground">
                      <div className="flex flex-col items-center justify-center gap-2">
                        <RefreshCw className="w-5 h-5 animate-spin text-blue-500" />
                        <span>Loading ledger transactions...</span>
                      </div>
                    </td>
                  </tr>
                ) : filteredRows.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center py-12 text-muted-foreground">
                      <div className="flex flex-col items-center justify-center gap-2">
                        <FileText className="w-8 h-8 text-zinc-600" />
                        <span>No transactions found for this account in the selected date period.</span>
                      </div>
                    </td>
                  </tr>
                ) : (
                  /* Chronological Transactions */
                  filteredRows.map(entry => (
                    <tr key={entry.id} className="hover:bg-muted/30 transition-colors">
                      {/* Date */}
                      <td className="py-3 px-4 font-mono text-[11px] text-muted-foreground whitespace-nowrap">
                        {entry.date || '—'}
                      </td>

                      {/* Particulars (Opposing Ledger) */}
                      <td className="py-3 px-4">
                        <div className="flex flex-col">
                          <div className="flex items-center gap-1.5 font-semibold text-foreground text-xs">
                            <span>{entry.particulars}</span>
                            {entry.opposing_details?.length > 1 && (
                              <span
                                className="text-[10px] bg-muted px-1 rounded text-muted-foreground cursor-help font-mono"
                                title={entry.opposing_details.map(o => `${o.ledger_name}: ₹${o.amount.toFixed(2)}`).join(' | ')}
                              >
                                details
                              </span>
                            )}
                          </div>
                          {entry.narration && (
                            <span className="text-[11px] text-muted-foreground truncate max-w-md mt-0.5">
                              {entry.narration}
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Voucher Type */}
                      <td className="py-3 px-4">
                        <span
                          className={`text-[10px] font-semibold px-2 py-0.5 rounded uppercase font-mono ${
                            entry.voucher_type === 'SALES'
                              ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                              : entry.voucher_type === 'PURCHASE'
                              ? 'bg-purple-500/10 text-purple-400 border border-purple-500/20'
                              : entry.voucher_type === 'RECEIPT'
                              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                              : entry.voucher_type === 'PAYMENT'
                              ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                              : 'bg-zinc-500/10 text-zinc-400 border border-zinc-500/20'
                          }`}
                        >
                          {entry.voucher_type}
                        </span>
                      </td>

                      {/* Voucher Number */}
                      <td className="py-3 px-4 font-mono text-xs text-foreground whitespace-nowrap font-medium">
                        {entry.voucher_number}
                      </td>

                      {/* Debit (Dr) */}
                      <td className="py-3 px-4 text-right font-mono font-medium">
                        {entry.debit > 0 ? (
                          <span className="text-blue-400 font-semibold">
                            ₹{entry.debit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                          </span>
                        ) : (
                          <span className="text-zinc-600">—</span>
                        )}
                      </td>

                      {/* Credit (Cr) */}
                      <td className="py-3 px-4 text-right font-mono font-medium">
                        {entry.credit > 0 ? (
                          <span className="text-amber-400 font-semibold">
                            ₹{entry.credit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                          </span>
                        ) : (
                          <span className="text-zinc-600">—</span>
                        )}
                      </td>

                      {/* Running Balance */}
                      <td className="py-3 px-4 text-right font-mono font-medium whitespace-nowrap">
                        <div className="inline-flex items-center justify-end gap-1">
                          <span className="text-foreground">
                            ₹{entry.dynamic_balance.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                          </span>
                          <span
                            className={`text-[10px] font-bold px-1 rounded ${
                              entry.dynamic_balance_type === 'DR'
                                ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                                : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                            }`}
                          >
                            {entry.dynamic_balance_type === 'DR' ? 'Dr' : 'Cr'}
                          </span>
                        </div>
                      </td>
                    </tr>
                  ))
                )}

                {/* 3. Totals & Closing Balance Row */}
                {statementData && (
                  <>
                    {/* Period Total Movement */}
                    <tr className="bg-muted/40 font-semibold border-t-2 border-border text-foreground">
                      <td className="py-3 px-4 font-mono text-[11px]" colSpan={4}>
                        <div className="flex items-center justify-between">
                          <span>Total Period Movement ({filteredRows.length} transactions)</span>
                          <span className="text-xs text-muted-foreground font-normal">
                            Net Flow: ₹{Math.abs(statementData.net_movement).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                          </span>
                        </div>
                      </td>
                      <td className="py-3 px-4 text-right font-mono text-blue-400">
                        ₹{statementData.total_debit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                      <td className="py-3 px-4 text-right font-mono text-amber-400">
                        ₹{statementData.total_credit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                      <td className="py-3 px-4 text-right font-mono text-muted-foreground">—</td>
                    </tr>

                    {/* Final Closing Balance Row */}
                    <tr className="bg-card font-bold border-t border-border text-foreground">
                      <td className="py-3 px-4 font-mono text-[11px]">
                        {statementData.to_date || 'Current'}
                      </td>
                      <td className="py-3 px-4" colSpan={5}>
                        <span className="font-bold text-foreground">Closing Balance (c/f)</span>
                        <span className="text-[10px] text-muted-foreground font-normal ml-2">
                          Balance carried forward to subsequent period
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right font-mono font-bold text-sm">
                        <div className="inline-flex items-center justify-end gap-1.5">
                          <span className="text-foreground">
                            ₹{statementData.closing_balance.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                          </span>
                          <span
                            className={`text-xs font-bold px-1.5 py-0.5 rounded ${
                              statementData.closing_type === 'DEBIT'
                                ? 'bg-blue-500/15 text-blue-400 border border-blue-500/30'
                                : 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                            }`}
                          >
                            {statementData.closing_type === 'DEBIT' ? 'Dr' : 'Cr'}
                          </span>
                        </div>
                      </td>
                    </tr>
                  </>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          {statementData?.pagination && statementData.pagination.total_count > 0 && (
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-4 py-3 border-t border-border bg-muted/20 text-xs text-muted-foreground print:hidden">
              <div className="font-mono">
                Showing entries{' '}
                <span className="font-semibold text-foreground">
                  {statementData.pagination.total_count === 0 ? 0 : statementData.pagination.offset + 1}
                </span>{' '}
                to{' '}
                <span className="font-semibold text-foreground">
                  {Math.min(statementData.pagination.offset + statementData.pagination.limit, statementData.pagination.total_count)}
                </span>{' '}
                of <span className="font-semibold text-foreground">{statementData.pagination.total_count}</span>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => fetchStatement(fromDate, toDate, page - 1)}
                  disabled={page <= 1 || loading}
                  className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-border bg-card text-foreground hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer font-medium"
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                  <span>Previous</span>
                </button>

                <div className="px-2.5 py-1 text-xs font-mono font-semibold text-foreground bg-muted/50 rounded border border-border">
                  Page {page} of {statementData.pagination.total_pages || 1}
                </div>

                <button
                  type="button"
                  onClick={() => fetchStatement(fromDate, toDate, page + 1)}
                  disabled={!statementData.pagination.has_more || page >= statementData.pagination.total_pages || loading}
                  className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-border bg-card text-foreground hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer font-medium"
                >
                  <span>Next</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
