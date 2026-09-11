"use client";
import React, { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { API_BASE_URL } from '@/utils/api';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import { usePeriod } from '@/context/PeriodContext';
import { useToast } from '@/context/ToastContext';
import { useCompany } from '@/context/CompanyContext';
import {
  Printer,
  Download,
  Calendar,
  Search,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  ArrowRight,
  Scale
} from 'lucide-react';

interface TrialBalanceRow {
  ledger_id: string;
  ledger_name: string;
  group_name: string;
  group_nature: string;
  opening_balance: string;
  opening_type: 'DR' | 'CR';
  period_debit: string;
  period_credit: string;
  closing_balance: string;
  closing_type: 'DR' | 'CR';
}

interface TrialBalanceTotals {
  opening_debit: string;
  opening_credit: string;
  period_debit: string;
  period_credit: string;
  closing_debit: string;
  closing_credit: string;
  is_opening_balanced: boolean;
  is_period_balanced: boolean;
  is_closing_balanced: boolean;
}

export default function TrialBalancePage() {
  const router = useRouter();
  const { toast } = useToast();
  const { fromDate, toDate, displayPeriod, setIsPeriodModalOpen } = usePeriod();

  const { activeCompany, companyId: activeCompanyId } = useCompany();
  const [company, setCompany] = useState<any>(activeCompany || null);
  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState<TrialBalanceRow[]>([]);
  const [totals, setTotals] = useState<TrialBalanceTotals | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedNature, setSelectedNature] = useState<string>('ALL');

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login');
      return;
    }
    loadData();
  }, [fromDate, toDate, router, activeCompanyId]);

  useEffect(() => {
    if (activeCompany) {
      setCompany(activeCompany);
    }
  }, [activeCompany]);

  const loadData = async () => {
    setLoading(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      let activeComp = activeCompany || company;
      if (!activeComp?.id && typeof window !== 'undefined') {
        const savedId = localStorage.getItem('vouch_active_company_id');
        if (savedId) {
          activeComp = { id: savedId };
        }
      }
      if (!activeComp?.id) {
        const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
        const list = Array.isArray(compRes.data) ? compRes.data : (compRes.data?.data || []);
        activeComp = list[0];
        setCompany(activeComp);
      }

      if (!activeComp?.id) {
        setLoading(false);
        return;
      }

      const tbRes = await axios.get(
        `${API_BASE_URL}/api/v1/accounting/period-trial-balance/?company_id=${activeComp.id}&from_date=${fromDate}&to_date=${toDate}`,
        { headers }
      );

      if (tbRes.data?.success && tbRes.data?.data) {
        setRows(tbRes.data.data.rows || []);
        setTotals(tbRes.data.data.totals || null);
      }
    } catch (err: any) {
      console.error('Failed to load trial balance:', err);
      toast.error('Failed to load trial balance', err.response?.data?.error || err.message);
    } finally {
      setLoading(false);
    }
  };

  const filteredRows = useMemo(() => {
    return rows.filter((row) => {
      const matchesSearch =
        searchQuery.trim() === '' ||
        row.ledger_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        row.group_name.toLowerCase().includes(searchQuery.toLowerCase());

      const matchesNature =
        selectedNature === 'ALL' ||
        row.group_nature.toUpperCase() === selectedNature.toUpperCase();

      return matchesSearch && matchesNature;
    });
  }, [rows, searchQuery, selectedNature]);

  const exportCSV = () => {
    if (!rows.length) return;
    const headers = [
      'Ledger Name',
      'Account Group',
      'Nature',
      'Opening Debit',
      'Opening Credit',
      'Period Debit',
      'Period Credit',
      'Closing Debit',
      'Closing Credit',
    ];

    const lines = rows.map((r) => [
      `"${r.ledger_name.replace(/"/g, '""')}"`,
      `"${r.group_name.replace(/"/g, '""')}"`,
      r.group_nature,
      r.opening_type === 'DR' ? r.opening_balance : '0.00',
      r.opening_type === 'CR' ? r.opening_balance : '0.00',
      r.period_debit,
      r.period_credit,
      r.closing_type === 'DR' ? r.closing_balance : '0.00',
      r.closing_type === 'CR' ? r.closing_balance : '0.00',
    ]);

    if (totals) {
      lines.push([
        '"TOTAL"',
        '""',
        '""',
        totals.opening_debit,
        totals.opening_credit,
        totals.period_debit,
        totals.period_credit,
        totals.closing_debit,
        totals.closing_credit,
      ]);
    }

    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...lines.map((l) => l.join(', '))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `trial_balance_${fromDate}_to_${toDate}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const isBalanced = totals?.is_closing_balanced ?? true;

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/40 pb-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-primary/10 rounded-xl text-primary">
              <Scale className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">
                Trial Balance
              </h1>
              <p className="text-xs sm:text-sm text-muted-foreground mt-0.5">
                Double-entry equilibrium of ledger balances for {company?.name || 'Company'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={() => setIsPeriodModalOpen(true)}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-border/60 bg-muted/40 hover:bg-muted text-xs font-semibold text-foreground transition-colors cursor-pointer"
            >
              <Calendar className="w-3.5 h-3.5 text-primary" />
              <span>{displayPeriod || `${fromDate} → ${toDate}`}</span>
              <kbd className="text-[10px] font-mono px-1 py-0.2 bg-muted border border-border/60 rounded text-muted-foreground font-semibold">
                Alt+F2
              </kbd>
            </button>

            <button
              onClick={loadData}
              disabled={loading}
              className="p-2 rounded-xl border border-border/60 bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
              title="Refresh Ledger Balances"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>

            <button
              onClick={() => window.print()}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-border/60 bg-muted/40 hover:bg-muted text-xs font-semibold text-foreground transition-colors cursor-pointer"
            >
              <Printer className="w-3.5 h-3.5 text-muted-foreground" />
              <span className="hidden sm:inline">Print</span>
            </button>

            <button
              onClick={exportCSV}
              disabled={!rows.length}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-semibold shadow-md shadow-primary/20 transition-colors cursor-pointer disabled:opacity-50"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Export CSV</span>
            </button>
          </div>
        </div>

        {/* Equilibrium Status Banner */}
        {totals && (
          <div
            className={`p-4 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
              isBalanced
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-500'
                : 'bg-rose-500/10 border-rose-500/30 text-rose-500'
            }`}
          >
            <div className="flex items-center gap-2.5">
              {isBalanced ? (
                <CheckCircle2 className="w-5 h-5 shrink-0 text-emerald-500" />
              ) : (
                <AlertTriangle className="w-5 h-5 shrink-0 text-rose-500 animate-pulse" />
              )}
              <div>
                <div className="font-bold text-sm text-foreground flex items-center gap-2">
                  {isBalanced ? 'Trial Balance in Equilibrium' : 'Imbalance Detected'}
                  <span
                    className={`text-[10px] font-mono px-2 py-0.5 rounded-full font-bold ${
                      isBalanced
                        ? 'bg-emerald-500/20 text-emerald-400'
                        : 'bg-rose-500/20 text-rose-400'
                    }`}
                  >
                    {isBalanced ? 'BALANCED' : 'OUT OF BALANCE'}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  {isBalanced
                    ? 'Total debits exactly equal total credits across all posted vouchers.'
                    : 'Debits do not match credits. You may run Rebuild Ledger Balances under Settings.'}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-4 text-xs font-mono">
              <div className="px-3 py-1.5 rounded-lg bg-card/60 border border-border/40">
                <span className="text-muted-foreground mr-2 font-sans">Closing Debit:</span>
                <span className="font-bold text-foreground tabular-nums">
                  ₹{Number(totals.closing_debit).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </span>
              </div>
              <div className="px-3 py-1.5 rounded-lg bg-card/60 border border-border/40">
                <span className="text-muted-foreground mr-2 font-sans">Closing Credit:</span>
                <span className="font-bold text-foreground tabular-nums">
                  ₹{Number(totals.closing_credit).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Filter and Search Bar */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto pb-1 sm:pb-0">
            {['ALL', 'ASSET', 'LIABILITY', 'EQUITY', 'REVENUE', 'EXPENSE'].map((nature) => (
              <button
                key={nature}
                onClick={() => setSelectedNature(nature)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors cursor-pointer ${
                  selectedNature === nature
                    ? 'bg-primary text-primary-foreground shadow-sm'
                    : 'bg-muted/50 hover:bg-muted text-muted-foreground hover:text-foreground border border-border/40'
                }`}
              >
                {nature === 'ALL' ? 'All Accounts' : nature.charAt(0) + nature.slice(1).toLowerCase()}
              </button>
            ))}
          </div>

          <div className="relative w-full sm:w-72">
            <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search ledger or group..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-xs bg-muted/40 border border-border/60 rounded-xl text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
        </div>

        {/* Data Table */}
        <div className="bg-card border border-border/40 rounded-xl shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse min-w-[750px]">
              <thead>
                <tr className="bg-muted/40 text-muted-foreground border-b border-border/60 font-semibold">
                  <th rowSpan={2} className="p-3.5 text-left border-r border-border/30">
                    Particulars (Ledger & Group)
                  </th>
                  <th rowSpan={2} className="p-3.5 text-center border-r border-border/30 w-24">
                    Nature
                  </th>
                  <th colSpan={2} className="p-2 text-center border-r border-border/30 border-b border-border/40">
                    Opening Balance
                  </th>
                  <th colSpan={2} className="p-2 text-center border-r border-border/30 border-b border-border/40">
                    Transactions ({displayPeriod || 'Period'})
                  </th>
                  <th colSpan={2} className="p-2 text-center border-b border-border/40">
                    Closing Balance
                  </th>
                </tr>
                <tr className="bg-muted/30 text-muted-foreground border-b border-border/60 font-mono text-[11px]">
                  <th className="py-2 px-3 text-right border-r border-border/30 w-28">Debit (₹)</th>
                  <th className="py-2 px-3 text-right border-r border-border/30 w-28">Credit (₹)</th>
                  <th className="py-2 px-3 text-right border-r border-border/30 w-28">Debit (₹)</th>
                  <th className="py-2 px-3 text-right border-r border-border/30 w-28">Credit (₹)</th>
                  <th className="py-2 px-3 text-right border-r border-border/30 w-28">Debit (₹)</th>
                  <th className="py-2 px-3 text-right w-28">Credit (₹)</th>
                </tr>
              </thead>

              <tbody className="divide-y divide-border/40 font-mono text-xs">
                {loading ? (
                  <tr>
                    <td colSpan={8} className="p-12 text-center text-muted-foreground font-sans">
                      <div className="flex flex-col items-center justify-center space-y-2">
                        <RefreshCw className="w-5 h-5 animate-spin text-primary" />
                        <span>Computing dynamic ledger equilibrium...</span>
                      </div>
                    </td>
                  </tr>
                ) : filteredRows.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="p-12 text-center text-muted-foreground font-sans">
                      No ledger balances matching the filter for this period.
                    </td>
                  </tr>
                ) : (
                  filteredRows.map((r) => {
                    const natureBadge = {
                      ASSET: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
                      LIABILITY: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
                      EQUITY: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
                      REVENUE: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
                      EXPENSE: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
                    }[r.group_nature.toUpperCase()] || 'bg-muted text-muted-foreground border-border/40';

                    const opDr = r.opening_type === 'DR' && Number(r.opening_balance) > 0 ? Number(r.opening_balance) : 0;
                    const opCr = r.opening_type === 'CR' && Number(r.opening_balance) > 0 ? Number(r.opening_balance) : 0;
                    const pDr = Number(r.period_debit) || 0;
                    const pCr = Number(r.period_credit) || 0;
                    const clDr = r.closing_type === 'DR' && Number(r.closing_balance) > 0 ? Number(r.closing_balance) : 0;
                    const clCr = r.closing_type === 'CR' && Number(r.closing_balance) > 0 ? Number(r.closing_balance) : 0;

                    return (
                      <tr
                        key={r.ledger_id}
                        className="hover:bg-muted/40 transition-colors group"
                      >
                        <td className="py-2.5 px-3.5 border-r border-border/30 font-sans">
                          <Link
                            href="/ledgers"
                            className="font-semibold text-foreground hover:text-primary transition-colors flex items-center gap-1.5"
                            title="View Ledger Details"
                          >
                            <span>{r.ledger_name}</span>
                            <ArrowRight className="w-3 h-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                          </Link>
                          <div className="text-[11px] text-muted-foreground font-normal">
                            {r.group_name}
                          </div>
                        </td>

                        <td className="py-2.5 px-3 text-center border-r border-border/30 font-sans">
                          <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${natureBadge}`}>
                            {r.group_nature}
                          </span>
                        </td>

                        <td className="py-2.5 px-3 text-right border-r border-border/30 tabular-nums text-foreground">
                          {opDr > 0 ? opDr.toLocaleString('en-IN', { minimumFractionDigits: 2 }) : '-'}
                        </td>
                        <td className="py-2.5 px-3 text-right border-r border-border/30 tabular-nums text-foreground">
                          {opCr > 0 ? opCr.toLocaleString('en-IN', { minimumFractionDigits: 2 }) : '-'}
                        </td>

                        <td className="py-2.5 px-3 text-right border-r border-border/30 tabular-nums text-foreground">
                          {pDr > 0 ? pDr.toLocaleString('en-IN', { minimumFractionDigits: 2 }) : '-'}
                        </td>
                        <td className="py-2.5 px-3 text-right border-r border-border/30 tabular-nums text-foreground">
                          {pCr > 0 ? pCr.toLocaleString('en-IN', { minimumFractionDigits: 2 }) : '-'}
                        </td>

                        <td className="py-2.5 px-3 text-right border-r border-border/30 tabular-nums font-bold text-foreground">
                          {clDr > 0 ? clDr.toLocaleString('en-IN', { minimumFractionDigits: 2 }) : '-'}
                        </td>
                        <td className="py-2.5 px-3 text-right tabular-nums font-bold text-foreground">
                          {clCr > 0 ? clCr.toLocaleString('en-IN', { minimumFractionDigits: 2 }) : '-'}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>

              {totals && (
                <tfoot>
                  <tr className="bg-muted/60 font-mono text-xs font-bold text-foreground border-t-2 border-border">
                    <td colSpan={2} className="p-3.5 font-sans uppercase tracking-wider text-right border-r border-border/30">
                      Grand Totals
                    </td>
                    <td className="py-3 px-3 text-right border-r border-border/30 tabular-nums">
                      ₹{Number(totals.opening_debit).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </td>
                    <td className="py-3 px-3 text-right border-r border-border/30 tabular-nums">
                      ₹{Number(totals.opening_credit).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </td>
                    <td className="py-3 px-3 text-right border-r border-border/30 tabular-nums">
                      ₹{Number(totals.period_debit).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </td>
                    <td className="py-3 px-3 text-right border-r border-border/30 tabular-nums">
                      ₹{Number(totals.period_credit).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </td>
                    <td className="py-3 px-3 text-right border-r border-border/30 tabular-nums text-primary">
                      ₹{Number(totals.closing_debit).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </td>
                    <td className="py-3 px-3 text-right tabular-nums text-primary">
                      ₹{Number(totals.closing_credit).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
