"use client";

import React, { useEffect, useState } from "react";
import axios from "axios";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import DashboardLayout from "@/components/DashboardLayout";
import { usePeriod } from "@/context/PeriodContext";
import { useToast } from "@/context/ToastContext";
import { useCompany } from "@/context/CompanyContext";
import {
  Scale,
  Calendar,
  RefreshCw,
  Printer,
  Download,
  CheckCircle2,
  AlertTriangle,
  ExternalLink,
  ShieldCheck,
  Building2,
  Wallet,
  Coins,
  ArrowRight,
  Info
} from "lucide-react";

interface LedgerRow {
  ledger_id: string;
  ledger_name: string;
  group_name: string;
  balance: string;
  balance_type: "DR" | "CR";
  is_drawing?: boolean;
}

interface BalanceSheetData {
  company_id: string;
  company_name: string;
  as_of_date: string;
  is_balanced: boolean;
  difference: string;
  liabilities_and_equity: {
    equity: {
      capital_rows: LedgerRow[];
      total_capital: string;
      total_drawings: string;
      net_profit: string;
      effective_equity: string;
    };
    loans: {
      rows: LedgerRow[];
      total: string;
    };
    current_liabilities: {
      rows: LedgerRow[];
      total: string;
    };
    total_liabilities: string;
  };
  assets: {
    fixed_assets: {
      rows: LedgerRow[];
      total: string;
    };
    current_assets: {
      rows: LedgerRow[];
      total: string;
    };
    bank_and_cash: {
      rows: LedgerRow[];
      total: string;
    };
    total_assets: string;
  };
  kpis: {
    working_capital: string;
    current_ratio: number;
    net_worth: string;
  };
}

export default function BalanceSheetPage() {
  const router = useRouter();
  const { toast } = useToast();
  const { toDate } = usePeriod();
  const { activeCompany, companyId: activeCompanyId } = useCompany();

  const [asOfDate, setAsOfDate] = useState<string>(
    toDate || new Date().toISOString().split("T")[0]
  );
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<BalanceSheetData | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }
    loadData();
  }, [asOfDate, router, activeCompanyId]);

  const loadData = async () => {
    setLoading(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      let compId = activeCompanyId;
      if (!compId && typeof window !== "undefined") {
        compId = localStorage.getItem("vouch_active_company_id") || "";
      }

      const params = new URLSearchParams();
      if (compId) params.append("company_id", compId);
      if (asOfDate) params.append("as_of_date", asOfDate);

      const res = await axios.get(
        `${API_BASE_URL}/api/v1/accounting/reports/balance-sheet/?${params.toString()}`,
        { headers }
      );

      if (res.data?.success && res.data?.data) {
        setData(res.data.data);
      }
    } catch (err: any) {
      console.error("Failed to load Balance Sheet:", err);
      toast.error(
        "Failed to load Balance Sheet",
        err.response?.data?.error || err.message
      );
    } finally {
      setLoading(false);
    }
  };

  const formatINR = (val: string | number) => {
    const num = typeof val === "string" ? parseFloat(val) : val;
    if (isNaN(num)) return "0.00";
    return num.toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  };

  const exportCSV = () => {
    if (!data) return;

    const lines: string[] = [
      `"BALANCE SHEET"`,
      `"Company:","${data.company_name}"`,
      `"As of Date:","${data.as_of_date}"`,
      `"Balanced:","${data.is_balanced ? "YES" : "NO"}"`,
      `"Difference:","${data.difference}"`,
      `""`,
      `"=== LIABILITIES & EQUITY ==="`,
      `"Category","Particulars","Group","Amount (INR)"`,
    ];

    data.liabilities_and_equity.equity.capital_rows.forEach((r) => {
      lines.push(
        `"Capital","${r.ledger_name.replace(/"/g, '""')}","${r.group_name.replace(/"/g, '""')}","${r.balance}"`
      );
    });
    lines.push(`"Equity","Net Profit / (Loss) for Period","-","${data.liabilities_and_equity.equity.net_profit}"`);
    lines.push(`"Subtotal","Effective Equity (Net Worth)","","${data.liabilities_and_equity.equity.effective_equity}"`);

    data.liabilities_and_equity.loans.rows.forEach((r) => {
      lines.push(
        `"Loans","${r.ledger_name.replace(/"/g, '""')}","${r.group_name.replace(/"/g, '""')}","${r.balance}"`
      );
    });
    lines.push(`"Subtotal","Total Loans & Borrowings","","${data.liabilities_and_equity.loans.total}"`);

    data.liabilities_and_equity.current_liabilities.rows.forEach((r) => {
      lines.push(
        `"Current Liabilities","${r.ledger_name.replace(/"/g, '""')}","${r.group_name.replace(/"/g, '""')}","${r.balance}"`
      );
    });
    lines.push(`"Subtotal","Total Current Liabilities","","${data.liabilities_and_equity.current_liabilities.total}"`);
    lines.push(`"TOTAL","TOTAL LIABILITIES & EQUITY","","${data.liabilities_and_equity.total_liabilities}"`);

    lines.push(`""`);
    lines.push(`"=== ASSETS ==="`);
    data.assets.fixed_assets.rows.forEach((r) => {
      lines.push(
        `"Fixed Assets","${r.ledger_name.replace(/"/g, '""')}","${r.group_name.replace(/"/g, '""')}","${r.balance}"`
      );
    });
    lines.push(`"Subtotal","Total Fixed Assets","","${data.assets.fixed_assets.total}"`);

    data.assets.current_assets.rows.forEach((r) => {
      lines.push(
        `"Current Assets","${r.ledger_name.replace(/"/g, '""')}","${r.group_name.replace(/"/g, '""')}","${r.balance}"`
      );
    });
    lines.push(`"Subtotal","Total Current Assets","","${data.assets.current_assets.total}"`);

    data.assets.bank_and_cash.rows.forEach((r) => {
      lines.push(
        `"Bank & Cash","${r.ledger_name.replace(/"/g, '""')}","${r.group_name.replace(/"/g, '""')}","${r.balance}"`
      );
    });
    lines.push(`"Subtotal","Total Bank & Cash","","${data.assets.bank_and_cash.total}"`);
    lines.push(`"TOTAL","TOTAL ASSETS","","${data.assets.total_assets}"`);

    const csvContent = "data:text/csv;charset=utf-8," + lines.join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `Balance_Sheet_as_of_${data.as_of_date}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const netProfitNum = data ? parseFloat(data.liabilities_and_equity.equity.net_profit) : 0;
  const isBalanced = data?.is_balanced ?? true;

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
                Balance Sheet
              </h1>
              <p className="text-xs sm:text-sm text-muted-foreground mt-0.5">
                Statement of Financial Position for {data?.company_name || "Company"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-border/60 bg-muted/40">
              <Calendar className="w-3.5 h-3.5 text-primary shrink-0" />
              <span className="text-xs text-muted-foreground font-medium">As of:</span>
              <input
                type="date"
                value={asOfDate}
                onChange={(e) => setAsOfDate(e.target.value)}
                className="bg-transparent text-xs font-semibold text-foreground focus:outline-none cursor-pointer"
              />
            </div>

            <button
              onClick={loadData}
              disabled={loading}
              className="p-2 rounded-xl border border-border/60 bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
              title="Refresh Balance Sheet"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
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
              disabled={!data}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-semibold shadow-md shadow-primary/20 transition-colors cursor-pointer disabled:opacity-50"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Export CSV</span>
            </button>
          </div>
        </div>

        {/* Equilibrium Status Banner */}
        {data && (
          <div
            className={`p-4 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
              isBalanced
                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-500"
                : "bg-rose-500/10 border-rose-500/30 text-rose-500"
            }`}
          >
            <div className="flex items-center gap-3">
              {isBalanced ? (
                <CheckCircle2 className="w-5 h-5 shrink-0" />
              ) : (
                <AlertTriangle className="w-5 h-5 shrink-0" />
              )}
              <div>
                <p className="text-sm font-bold">
                  {isBalanced
                    ? "Balance Sheet is in Equilibrium"
                    : "Balance Sheet Discrepancy Detected"}
                </p>
                <p className="text-xs opacity-90">
                  {isBalanced
                    ? `Total Assets (₹${formatINR(data.assets.total_assets)}) match Total Liabilities & Equity (₹${formatINR(data.liabilities_and_equity.total_liabilities)}) perfectly.`
                    : `Difference of ₹${formatINR(data.difference)} between Total Assets and Total Liabilities.`}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3 text-xs font-mono font-bold">
              <span className="opacity-75">Assets: ₹{formatINR(data.assets.total_assets)}</span>
              <span>=</span>
              <span className="opacity-75">Liab: ₹{formatINR(data.liabilities_and_equity.total_liabilities)}</span>
            </div>
          </div>
        )}

        {/* Top Financial KPI Summary Cards */}
        {data && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Net Worth */}
            <div className="p-4 rounded-2xl bg-card border border-border/60 shadow-sm flex flex-col justify-between">
              <div className="flex items-center justify-between text-muted-foreground mb-2">
                <span className="text-xs font-semibold uppercase tracking-wider">Net Worth (Equity)</span>
                <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
                  <ShieldCheck className="w-4 h-4" />
                </div>
              </div>
              <div>
                <div className="text-2xl font-black text-foreground">
                  ₹{formatINR(data.kpis.net_worth)}
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  Capital + Cumulative Net Profit
                </div>
              </div>
            </div>

            {/* Working Capital */}
            <div className="p-4 rounded-2xl bg-card border border-border/60 shadow-sm flex flex-col justify-between">
              <div className="flex items-center justify-between text-muted-foreground mb-2">
                <span className="text-xs font-semibold uppercase tracking-wider">Working Capital</span>
                <div className="p-1.5 rounded-lg bg-blue-500/10 text-blue-500">
                  <Wallet className="w-4 h-4" />
                </div>
              </div>
              <div>
                <div className="text-2xl font-black text-foreground">
                  ₹{formatINR(data.kpis.working_capital)}
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  Current Assets − Current Liabilities
                </div>
              </div>
            </div>

            {/* Current Ratio */}
            <div className="p-4 rounded-2xl bg-card border border-border/60 shadow-sm flex flex-col justify-between">
              <div className="flex items-center justify-between text-muted-foreground mb-2">
                <span className="text-xs font-semibold uppercase tracking-wider">Current Ratio</span>
                <div className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-500">
                  <Coins className="w-4 h-4" />
                </div>
              </div>
              <div>
                <div className="text-2xl font-black text-foreground">
                  {data.kpis.current_ratio.toFixed(2)} : 1
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  {data.kpis.current_ratio >= 1.5 ? (
                    <span className="text-emerald-500 font-semibold">Healthy Liquidity</span>
                  ) : (
                    <span className="text-amber-500 font-semibold">Watch Cash Flow</span>
                  )}
                </div>
              </div>
            </div>

            {/* Total Balance Sheet Size */}
            <div className="p-4 rounded-2xl bg-card border border-border/60 shadow-sm flex flex-col justify-between">
              <div className="flex items-center justify-between text-muted-foreground mb-2">
                <span className="text-xs font-semibold uppercase tracking-wider">Total Assets Size</span>
                <div className="p-1.5 rounded-lg bg-purple-500/10 text-purple-500">
                  <Building2 className="w-4 h-4" />
                </div>
              </div>
              <div>
                <div className="text-2xl font-black text-foreground">
                  ₹{formatINR(data.assets.total_assets)}
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  Fixed + Current + Bank Assets
                </div>
              </div>
            </div>
          </div>
        )}

        {loading ? (
          <div className="flex flex-col items-center justify-center p-20 space-y-3">
            <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
            <p className="text-xs text-muted-foreground">Compiling Balance Sheet Statement...</p>
          </div>
        ) : !data ? (
          <div className="p-12 text-center text-muted-foreground border border-dashed rounded-2xl bg-card">
            No balance sheet data available.
          </div>
        ) : (
          <div className="space-y-6">
            {/* DUAL-COLUMN BALANCE SHEET */}
            <div className="bg-card border border-border/60 rounded-2xl overflow-hidden shadow-sm">
              <div className="grid grid-cols-1 lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-border/60">
                {/* LEFT SIDE: LIABILITIES & EQUITY */}
                <div className="flex flex-col justify-between">
                  <div>
                    {/* Header */}
                    <div className="bg-muted/40 px-5 py-3 border-b border-border/60 flex items-center justify-between">
                      <h2 className="text-sm font-bold tracking-wide uppercase text-foreground">
                        Liabilities & Equity
                      </h2>
                      <span className="text-xs text-muted-foreground font-mono">Amount (₹)</span>
                    </div>

                    <div className="divide-y divide-border/40 text-xs">
                      {/* SECTION 1: CAPITAL & EQUITY */}
                      <div>
                        <div className="px-4 py-2 bg-muted/20 font-bold text-foreground flex justify-between items-center">
                          <span>1. Capital Account & Reserves</span>
                          <span className="font-mono">
                            ₹{formatINR(data.liabilities_and_equity.equity.effective_equity)}
                          </span>
                        </div>

                        <div className="divide-y divide-border/20 pl-2">
                          {data.liabilities_and_equity.equity.capital_rows.map((row) => (
                            <Link
                              key={row.ledger_id}
                              href={`/ledgers/${row.ledger_id}/statement`}
                              className="px-4 py-2 flex justify-between items-center hover:bg-primary/5 transition-colors group cursor-pointer"
                            >
                              <div>
                                <div className="font-medium text-foreground group-hover:text-primary flex items-center gap-1">
                                  <span>{row.ledger_name}</span>
                                  <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                                </div>
                                <div className="text-[11px] text-muted-foreground">{row.group_name}</div>
                              </div>
                              <span className="font-mono font-medium text-foreground group-hover:text-primary">
                                {formatINR(row.balance)}
                              </span>
                            </Link>
                          ))}

                          {/* Dynamic Net Profit Line */}
                          <div className="px-4 py-2 flex justify-between items-center bg-emerald-500/5 font-semibold text-emerald-500">
                            <div>
                              <div>Add: Net Profit (from P&L Account)</div>
                              <div className="text-[11px] font-normal text-emerald-500/80">Fiscal year-to-date earnings</div>
                            </div>
                            <span className="font-mono">{formatINR(netProfitNum)}</span>
                          </div>

                          {/* Drawings if any */}
                          {parseFloat(data.liabilities_and_equity.equity.total_drawings) > 0 && (
                            <div className="px-4 py-2 flex justify-between items-center text-rose-500 font-semibold">
                              <div>Less: Proprietor / Partner Drawings</div>
                              <span className="font-mono">-₹{formatINR(data.liabilities_and_equity.equity.total_drawings)}</span>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* SECTION 2: LOANS & BORROWINGS */}
                      <div>
                        <div className="px-4 py-2 bg-muted/20 font-bold text-foreground flex justify-between items-center">
                          <span>2. Loans & Borrowings</span>
                          <span className="font-mono">
                            ₹{formatINR(data.liabilities_and_equity.loans.total)}
                          </span>
                        </div>

                        <div className="divide-y divide-border/20 pl-2">
                          {data.liabilities_and_equity.loans.rows.length === 0 ? (
                            <div className="px-4 py-2 text-muted-foreground italic">
                              No loan or borrowing accounts.
                            </div>
                          ) : (
                            data.liabilities_and_equity.loans.rows.map((row) => (
                              <Link
                                key={row.ledger_id}
                                href={`/ledgers/${row.ledger_id}/statement`}
                                className="px-4 py-2 flex justify-between items-center hover:bg-primary/5 transition-colors group cursor-pointer"
                              >
                                <div>
                                  <div className="font-medium text-foreground group-hover:text-primary flex items-center gap-1">
                                    <span>{row.ledger_name}</span>
                                    <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                                  </div>
                                  <div className="text-[11px] text-muted-foreground">{row.group_name}</div>
                                </div>
                                <span className="font-mono font-medium text-foreground group-hover:text-primary">
                                  {formatINR(row.balance)}
                                </span>
                              </Link>
                            ))
                          )}
                        </div>
                      </div>

                      {/* SECTION 3: CURRENT LIABILITIES */}
                      <div>
                        <div className="px-4 py-2 bg-muted/20 font-bold text-foreground flex justify-between items-center">
                          <span>3. Current Liabilities</span>
                          <span className="font-mono">
                            ₹{formatINR(data.liabilities_and_equity.current_liabilities.total)}
                          </span>
                        </div>

                        <div className="divide-y divide-border/20 pl-2">
                          {data.liabilities_and_equity.current_liabilities.rows.length === 0 ? (
                            <div className="px-4 py-2 text-muted-foreground italic">
                              No current liabilities or outstanding trade payables.
                            </div>
                          ) : (
                            data.liabilities_and_equity.current_liabilities.rows.map((row) => (
                              <Link
                                key={row.ledger_id}
                                href={`/ledgers/${row.ledger_id}/statement`}
                                className="px-4 py-2 flex justify-between items-center hover:bg-primary/5 transition-colors group cursor-pointer"
                              >
                                <div>
                                  <div className="font-medium text-foreground group-hover:text-primary flex items-center gap-1">
                                    <span>{row.ledger_name}</span>
                                    <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                                  </div>
                                  <div className="text-[11px] text-muted-foreground">{row.group_name}</div>
                                </div>
                                <span className="font-mono font-medium text-foreground group-hover:text-primary">
                                  {formatINR(row.balance)}
                                </span>
                              </Link>
                            ))
                          )}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* TOTAL LIABILITIES BOTTOM BAR */}
                  <div className="px-5 py-3 bg-muted/40 border-t border-border/60 flex justify-between items-center font-black text-sm text-foreground mt-4">
                    <span>TOTAL LIABILITIES & EQUITY</span>
                    <span className="font-mono text-base text-primary">
                      ₹{formatINR(data.liabilities_and_equity.total_liabilities)}
                    </span>
                  </div>
                </div>

                {/* RIGHT SIDE: ASSETS */}
                <div className="flex flex-col justify-between">
                  <div>
                    {/* Header */}
                    <div className="bg-muted/40 px-5 py-3 border-b border-border/60 flex items-center justify-between">
                      <h2 className="text-sm font-bold tracking-wide uppercase text-foreground">
                        Assets
                      </h2>
                      <span className="text-xs text-muted-foreground font-mono">Amount (₹)</span>
                    </div>

                    <div className="divide-y divide-border/40 text-xs">
                      {/* SECTION 1: FIXED ASSETS */}
                      <div>
                        <div className="px-4 py-2 bg-muted/20 font-bold text-foreground flex justify-between items-center">
                          <span>1. Fixed Assets (Property, Plant & Equipment)</span>
                          <span className="font-mono">
                            ₹{formatINR(data.assets.fixed_assets.total)}
                          </span>
                        </div>

                        <div className="divide-y divide-border/20 pl-2">
                          {data.assets.fixed_assets.rows.length === 0 ? (
                            <div className="px-4 py-2 text-muted-foreground italic">
                              No fixed asset accounts.
                            </div>
                          ) : (
                            data.assets.fixed_assets.rows.map((row) => (
                              <Link
                                key={row.ledger_id}
                                href={`/ledgers/${row.ledger_id}/statement`}
                                className="px-4 py-2 flex justify-between items-center hover:bg-primary/5 transition-colors group cursor-pointer"
                              >
                                <div>
                                  <div className="font-medium text-foreground group-hover:text-primary flex items-center gap-1">
                                    <span>{row.ledger_name}</span>
                                    <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                                  </div>
                                  <div className="text-[11px] text-muted-foreground">{row.group_name}</div>
                                </div>
                                <span className="font-mono font-medium text-foreground group-hover:text-primary">
                                  {formatINR(row.balance)}
                                </span>
                              </Link>
                            ))
                          )}
                        </div>
                      </div>

                      {/* SECTION 2: CURRENT ASSETS */}
                      <div>
                        <div className="px-4 py-2 bg-muted/20 font-bold text-foreground flex justify-between items-center">
                          <span>2. Current Assets & Stock</span>
                          <span className="font-mono">
                            ₹{formatINR(data.assets.current_assets.total)}
                          </span>
                        </div>

                        <div className="divide-y divide-border/20 pl-2">
                          {data.assets.current_assets.rows.map((row) => {
                            const isStockValuation = row.ledger_id === "stock-valuation";
                            return isStockValuation ? (
                              <div
                                key={row.ledger_id}
                                className="px-4 py-2 flex justify-between items-center bg-blue-500/5 font-semibold text-blue-500"
                              >
                                <div>
                                  <div>{row.ledger_name}</div>
                                  <div className="text-[11px] font-normal text-blue-500/80">Computed from product stock & purchase costs</div>
                                </div>
                                <span className="font-mono">{formatINR(row.balance)}</span>
                              </div>
                            ) : (
                              <Link
                                key={row.ledger_id}
                                href={`/ledgers/${row.ledger_id}/statement`}
                                className="px-4 py-2 flex justify-between items-center hover:bg-primary/5 transition-colors group cursor-pointer"
                              >
                                <div>
                                  <div className="font-medium text-foreground group-hover:text-primary flex items-center gap-1">
                                    <span>{row.ledger_name}</span>
                                    <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                                  </div>
                                  <div className="text-[11px] text-muted-foreground">{row.group_name}</div>
                                </div>
                                <span className="font-mono font-medium text-foreground group-hover:text-primary">
                                  {formatINR(row.balance)}
                                </span>
                              </Link>
                            );
                          })}
                        </div>
                      </div>

                      {/* SECTION 3: BANK & CASH BALANCES */}
                      <div>
                        <div className="px-4 py-2 bg-muted/20 font-bold text-foreground flex justify-between items-center">
                          <span>3. Bank & Cash Balances</span>
                          <span className="font-mono">
                            ₹{formatINR(data.assets.bank_and_cash.total)}
                          </span>
                        </div>

                        <div className="divide-y divide-border/20 pl-2">
                          {data.assets.bank_and_cash.rows.length === 0 ? (
                            <div className="px-4 py-2 text-muted-foreground italic">
                              No bank or cash ledgers.
                            </div>
                          ) : (
                            data.assets.bank_and_cash.rows.map((row) => (
                              <Link
                                key={row.ledger_id}
                                href={`/ledgers/${row.ledger_id}/statement`}
                                className="px-4 py-2 flex justify-between items-center hover:bg-primary/5 transition-colors group cursor-pointer"
                              >
                                <div>
                                  <div className="font-medium text-foreground group-hover:text-primary flex items-center gap-1">
                                    <span>{row.ledger_name}</span>
                                    <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                                  </div>
                                  <div className="text-[11px] text-muted-foreground">{row.group_name}</div>
                                </div>
                                <span className="font-mono font-medium text-foreground group-hover:text-primary">
                                  {formatINR(row.balance)}
                                </span>
                              </Link>
                            ))
                          )}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* TOTAL ASSETS BOTTOM BAR */}
                  <div className="px-5 py-3 bg-muted/40 border-t border-border/60 flex justify-between items-center font-black text-sm text-foreground mt-4">
                    <span>TOTAL ASSETS</span>
                    <span className="font-mono text-base text-primary">
                      ₹{formatINR(data.assets.total_assets)}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Bottom Info Note */}
            <div className="p-4 rounded-xl border border-border/60 bg-muted/20 text-xs text-muted-foreground flex items-start gap-3">
              <Info className="w-4 h-4 text-primary shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-foreground">Double-Entry Accounting Principle: </span>
                Assets must strictly equal Liabilities + Equity. Net Profit for the period is transferred dynamically into Effective Equity. Click any account row to view the detailed ledger statement.
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
