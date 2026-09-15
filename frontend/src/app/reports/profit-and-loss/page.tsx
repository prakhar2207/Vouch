"use client";

import React, { useEffect, useState, useMemo } from "react";
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
  TrendingUp,
  TrendingDown,
  Calendar,
  RefreshCw,
  Printer,
  Download,
  ArrowUpRight,
  ArrowDownRight,
  ExternalLink,
  DollarSign,
  Package,
  Layers,
  ChevronRight,
  Info
} from "lucide-react";

interface ReportRow {
  ledger_id: string;
  ledger_name: string;
  group_name: string;
  debit: string;
  credit: string;
  amount: string;
}

interface ProfitAndLossData {
  company_id: string;
  company_name: string;
  from_date: string;
  to_date: string;
  trading_account: {
    direct_income: {
      rows: ReportRow[];
      total: string;
    };
    direct_expense: {
      rows: ReportRow[];
      total: string;
    };
    opening_stock: string;
    closing_stock: string;
    gross_profit: string;
    is_gross_profit: boolean;
    gross_profit_percentage: number;
  };
  profit_and_loss: {
    gross_profit_brought_forward: string;
    indirect_income: {
      rows: ReportRow[];
      total: string;
    };
    indirect_expense: {
      rows: ReportRow[];
      total: string;
    };
    net_profit: string;
    is_net_profit: boolean;
    net_profit_percentage: number;
  };
}

export default function ProfitAndLossPage() {
  const router = useRouter();
  const { toast } = useToast();
  const { fromDate, toDate, displayPeriod, setIsPeriodModalOpen } = usePeriod();
  const { activeCompany, companyId: activeCompanyId } = useCompany();

  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<ProfitAndLossData | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }
    loadData();
  }, [fromDate, toDate, router, activeCompanyId]);

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
      if (fromDate) params.append("from_date", fromDate);
      if (toDate) params.append("to_date", toDate);

      const res = await axios.get(
        `${API_BASE_URL}/api/v1/accounting/reports/profit-and-loss/?${params.toString()}`,
        { headers }
      );

      if (res.data?.success && res.data?.data) {
        setData(res.data.data);
      }
    } catch (err: any) {
      console.error("Failed to load Profit & Loss:", err);
      toast.error(
        "Failed to load Profit & Loss",
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
      `"PROFIT & LOSS STATEMENT"`,
      `"Company:","${data.company_name}"`,
      `"Period:","${data.from_date} to ${data.to_date}"`,
      `""`,
      `"=== TRADING ACCOUNT ==="`,
      `"Type","Particulars","Group","Amount (INR)"`,
      `"Direct Income","Opening Stock","-","${data.trading_account.opening_stock}"`,
    ];

    data.trading_account.direct_expense.rows.forEach((r) => {
      lines.push(`"Direct Expense","${r.ledger_name.replace(/"/g, '""')}","${r.group_name.replace(/"/g, '""')}","${r.amount}"`);
    });
    lines.push(`"Subtotal","Total Direct Expenses","","${data.trading_account.direct_expense.total}"`);

    data.trading_account.direct_income.rows.forEach((r) => {
      lines.push(`"Direct Income","${r.ledger_name.replace(/"/g, '""')}","${r.group_name.replace(/"/g, '""')}","${r.amount}"`);
    });
    lines.push(`"Direct Income","Closing Stock","-","${data.trading_account.closing_stock}"`);
    lines.push(`"Subtotal","Total Direct Income","","${data.trading_account.direct_income.total}"`);
    lines.push(`"Trading Result","${data.trading_account.is_gross_profit ? 'GROSS PROFIT' : 'GROSS LOSS'}","","${data.trading_account.gross_profit}"`);

    lines.push(`""`);
    lines.push(`"=== PROFIT & LOSS ACCOUNT ==="`);
    data.profit_and_loss.indirect_expense.rows.forEach((r) => {
      lines.push(`"Indirect Expense","${r.ledger_name.replace(/"/g, '""')}","${r.group_name.replace(/"/g, '""')}","${r.amount}"`);
    });
    lines.push(`"Subtotal","Total Indirect Expenses","","${data.profit_and_loss.indirect_expense.total}"`);

    data.profit_and_loss.indirect_income.rows.forEach((r) => {
      lines.push(`"Indirect Income","${r.ledger_name.replace(/"/g, '""')}","${r.group_name.replace(/"/g, '""')}","${r.amount}"`);
    });
    lines.push(`"Subtotal","Total Indirect Incomes","","${data.profit_and_loss.indirect_income.total}"`);
    lines.push(`"Final Result","${data.profit_and_loss.is_net_profit ? 'NET PROFIT' : 'NET LOSS'}","","${data.profit_and_loss.net_profit}"`);

    const csvContent = "data:text/csv;charset=utf-8," + lines.join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `Profit_and_Loss_${data.from_date}_to_${data.to_date}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const trading = data?.trading_account;
  const pl = data?.profit_and_loss;

  const grossProfitNum = trading ? parseFloat(trading.gross_profit) : 0;
  const netProfitNum = pl ? parseFloat(pl.net_profit) : 0;
  const directIncomeNum = trading ? parseFloat(trading.direct_income.total) : 0;
  const directExpenseNum = trading ? parseFloat(trading.direct_expense.total) : 0;
  const indirectExpenseNum = pl ? parseFloat(pl.indirect_expense.total) : 0;
  const totalExpenseNum = directExpenseNum + indirectExpenseNum;

  // Balancing totals for Trading Account
  const directIncomeWithStock = directIncomeNum + (trading ? parseFloat(trading.closing_stock) : 0);
  const directExpenseWithStock = directExpenseNum + (trading ? parseFloat(trading.opening_stock) : 0);
  const tradingSideTotal = Math.max(directIncomeWithStock, directExpenseWithStock);

  // Balancing totals for P&L Account
  const indirectIncomeTotal = pl ? parseFloat(pl.indirect_income.total) : 0;
  const plCreditSide = (grossProfitNum > 0 ? grossProfitNum : 0) + indirectIncomeTotal;
  const plDebitSide = (grossProfitNum < 0 ? Math.abs(grossProfitNum) : 0) + indirectExpenseNum;
  const plSideTotal = Math.max(plCreditSide, plDebitSide);

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/40 pb-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-primary/10 rounded-xl text-primary">
              <TrendingUp className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">
                Profit & Loss Statement
              </h1>
              <p className="text-xs sm:text-sm text-muted-foreground mt-0.5">
                Trading and Profit & Loss Account for {data?.company_name || "Company"}
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
              title="Refresh Statement"
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

        {/* Top Summary KPI Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Gross Profit Card */}
          <div className="p-4 rounded-2xl bg-card border border-border/60 shadow-sm flex flex-col justify-between">
            <div className="flex items-center justify-between text-muted-foreground mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">Gross Profit</span>
              <div className={`p-1.5 rounded-lg ${grossProfitNum >= 0 ? "bg-emerald-500/10 text-emerald-500" : "bg-rose-500/10 text-rose-500"}`}>
                {grossProfitNum >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
              </div>
            </div>
            <div>
              <div className={`text-2xl font-black ${grossProfitNum >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
                ₹{formatINR(Math.abs(grossProfitNum))}
                {grossProfitNum < 0 && <span className="text-xs ml-1 font-bold">(Loss)</span>}
              </div>
              <div className="text-xs text-muted-foreground mt-1 flex items-center gap-1.5">
                <span className="font-semibold text-foreground">GP Margin:</span>
                <span className={`px-1.5 py-0.5 rounded font-mono font-bold text-[11px] ${grossProfitNum >= 0 ? "bg-emerald-500/15 text-emerald-500" : "bg-rose-500/15 text-rose-500"}`}>
                  {trading?.gross_profit_percentage?.toFixed(2) || "0.00"}%
                </span>
              </div>
            </div>
          </div>

          {/* Net Profit Card */}
          <div className="p-4 rounded-2xl bg-card border border-border/60 shadow-sm flex flex-col justify-between">
            <div className="flex items-center justify-between text-muted-foreground mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">Net Profit</span>
              <div className={`p-1.5 rounded-lg ${netProfitNum >= 0 ? "bg-emerald-500/10 text-emerald-500" : "bg-rose-500/10 text-rose-500"}`}>
                {netProfitNum >= 0 ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownRight className="w-4 h-4" />}
              </div>
            </div>
            <div>
              <div className={`text-2xl font-black ${netProfitNum >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
                ₹{formatINR(Math.abs(netProfitNum))}
                {netProfitNum < 0 && <span className="text-xs ml-1 font-bold">(Loss)</span>}
              </div>
              <div className="text-xs text-muted-foreground mt-1 flex items-center gap-1.5">
                <span className="font-semibold text-foreground">NP Margin:</span>
                <span className={`px-1.5 py-0.5 rounded font-mono font-bold text-[11px] ${netProfitNum >= 0 ? "bg-emerald-500/15 text-emerald-500" : "bg-rose-500/15 text-rose-500"}`}>
                  {pl?.net_profit_percentage?.toFixed(2) || "0.00"}%
                </span>
              </div>
            </div>
          </div>

          {/* Operating Revenue */}
          <div className="p-4 rounded-2xl bg-card border border-border/60 shadow-sm flex flex-col justify-between">
            <div className="flex items-center justify-between text-muted-foreground mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">Turnover / Sales</span>
              <div className="p-1.5 rounded-lg bg-blue-500/10 text-blue-500">
                <DollarSign className="w-4 h-4" />
              </div>
            </div>
            <div>
              <div className="text-2xl font-black text-foreground">
                ₹{formatINR(directIncomeNum)}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                Direct operating revenues
              </div>
            </div>
          </div>

          {/* Total Expenses */}
          <div className="p-4 rounded-2xl bg-card border border-border/60 shadow-sm flex flex-col justify-between">
            <div className="flex items-center justify-between text-muted-foreground mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">Total Expenses</span>
              <div className="p-1.5 rounded-lg bg-amber-500/10 text-amber-500">
                <Layers className="w-4 h-4" />
              </div>
            </div>
            <div>
              <div className="text-2xl font-black text-foreground">
                ₹{formatINR(totalExpenseNum)}
              </div>
              <div className="text-xs text-muted-foreground mt-1 flex items-center gap-2">
                <span>Direct: ₹{formatINR(directExpenseNum)}</span>
                <span>•</span>
                <span>Indirect: ₹{formatINR(indirectExpenseNum)}</span>
              </div>
            </div>
          </div>
        </div>

        {loading ? (
          <div className="flex flex-col items-center justify-center p-20 space-y-3">
            <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
            <p className="text-xs text-muted-foreground">Calculating Trading & P&L Statement...</p>
          </div>
        ) : !data ? (
          <div className="p-12 text-center text-muted-foreground border border-dashed rounded-2xl bg-card">
            No statement data found for this period.
          </div>
        ) : (
          <div className="space-y-8">
            {/* SECTION 1: TRADING ACCOUNT */}
            <div className="bg-card border border-border/60 rounded-2xl overflow-hidden shadow-sm">
              <div className="bg-muted/40 px-5 py-3 border-b border-border/60 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Package className="w-4 h-4 text-primary" />
                  <h2 className="text-sm font-bold tracking-wide uppercase text-foreground">
                    Trading Account (Gross Profit Determination)
                  </h2>
                </div>
                <span className="text-xs text-muted-foreground font-mono">
                  {data.from_date} to {data.to_date}
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-border/60 text-xs">
                {/* Left: Direct Expenses & Costs */}
                <div className="flex flex-col justify-between">
                  <div>
                    <div className="px-4 py-2.5 bg-muted/20 font-bold text-muted-foreground flex justify-between items-center border-b border-border/40">
                      <span>Particulars (Debit - Direct Costs)</span>
                      <span>Amount (₹)</span>
                    </div>

                    <div className="divide-y divide-border/30">
                      {/* Opening Stock */}
                      <div className="px-4 py-2.5 flex justify-between items-center hover:bg-muted/20 transition-colors">
                        <div>
                          <div className="font-semibold text-foreground">To Opening Stock</div>
                          <div className="text-[11px] text-muted-foreground">Calculated from un-invoiced stock (Current + Sold − Purchased)</div>
                        </div>
                        <span className="font-mono font-bold text-foreground">
                          {formatINR(trading?.opening_stock || 0)}
                        </span>
                      </div>

                      {/* Direct Expenses Rows */}
                      {trading?.direct_expense.rows.map((row) => (
                        <Link
                          key={row.ledger_id}
                          href={`/ledgers/${row.ledger_id}/statement?from_date=${fromDate}&to_date=${toDate}`}
                          className="px-4 py-2.5 flex justify-between items-center hover:bg-primary/5 transition-colors group cursor-pointer"
                        >
                          <div>
                            <div className="font-medium text-foreground group-hover:text-primary flex items-center gap-1">
                              <span>To {row.ledger_name}</span>
                              <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                            </div>
                            <div className="text-[11px] text-muted-foreground">{row.group_name}</div>
                          </div>
                          <span className="font-mono font-medium text-foreground group-hover:text-primary">
                            {formatINR(row.amount)}
                          </span>
                        </Link>
                      ))}

                      {/* Gross Profit c/d (if Gross Profit >= 0) */}
                      {grossProfitNum >= 0 && (
                        <div className="px-4 py-2.5 flex justify-between items-center bg-emerald-500/5 font-bold text-emerald-500">
                          <div>
                            <div>To Gross Profit c/d</div>
                            <div className="text-[11px] font-normal text-emerald-500/80">Transferred to P&L Account</div>
                          </div>
                          <span className="font-mono text-sm">{formatINR(grossProfitNum)}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Debit Subtotal */}
                  <div className="px-4 py-2.5 bg-muted/30 border-t border-border/60 flex justify-between items-center font-bold text-foreground mt-4">
                    <span>Total Debit</span>
                    <span className="font-mono text-sm">₹{formatINR(tradingSideTotal)}</span>
                  </div>
                </div>

                {/* Right: Direct Incomes & Revenues */}
                <div className="flex flex-col justify-between">
                  <div>
                    <div className="px-4 py-2.5 bg-muted/20 font-bold text-muted-foreground flex justify-between items-center border-b border-border/40">
                      <span>Particulars (Credit - Direct Revenue)</span>
                      <span>Amount (₹)</span>
                    </div>

                    <div className="divide-y divide-border/30">
                      {/* Direct Incomes Rows */}
                      {trading?.direct_income.rows.map((row) => (
                        <Link
                          key={row.ledger_id}
                          href={`/ledgers/${row.ledger_id}/statement?from_date=${fromDate}&to_date=${toDate}`}
                          className="px-4 py-2.5 flex justify-between items-center hover:bg-primary/5 transition-colors group cursor-pointer"
                        >
                          <div>
                            <div className="font-medium text-foreground group-hover:text-primary flex items-center gap-1">
                              <span>By {row.ledger_name}</span>
                              <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                            </div>
                            <div className="text-[11px] text-muted-foreground">{row.group_name}</div>
                          </div>
                          <span className="font-mono font-medium text-foreground group-hover:text-primary">
                            {formatINR(row.amount)}
                          </span>
                        </Link>
                      ))}

                      {/* Closing Stock */}
                      <div className="px-4 py-2.5 flex justify-between items-center hover:bg-muted/20 transition-colors">
                        <div>
                          <div className="font-semibold text-foreground">By Closing Stock</div>
                          <div className="text-[11px] text-muted-foreground">Inventory valuation / Stock-in-hand</div>
                        </div>
                        <span className="font-mono font-bold text-foreground">
                          {formatINR(trading?.closing_stock || 0)}
                        </span>
                      </div>

                      {/* Gross Loss c/d (if Gross Profit < 0) */}
                      {grossProfitNum < 0 && (
                        <div className="px-4 py-2.5 flex justify-between items-center bg-rose-500/5 font-bold text-rose-500">
                          <div>
                            <div>By Gross Loss c/d</div>
                            <div className="text-[11px] font-normal text-rose-500/80">Transferred to P&L Account</div>
                          </div>
                          <span className="font-mono text-sm">{formatINR(Math.abs(grossProfitNum))}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Credit Subtotal */}
                  <div className="px-4 py-2.5 bg-muted/30 border-t border-border/60 flex justify-between items-center font-bold text-foreground mt-4">
                    <span>Total Credit</span>
                    <span className="font-mono text-sm">₹{formatINR(tradingSideTotal)}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* SECTION 2: PROFIT & LOSS ACCOUNT */}
            <div className="bg-card border border-border/60 rounded-2xl overflow-hidden shadow-sm">
              <div className="bg-muted/40 px-5 py-3 border-b border-border/60 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Layers className="w-4 h-4 text-primary" />
                  <h2 className="text-sm font-bold tracking-wide uppercase text-foreground">
                    Profit & Loss Account (Net Profit Determination)
                  </h2>
                </div>
                <span className="text-xs text-muted-foreground font-mono">
                  {data.from_date} to {data.to_date}
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-border/60 text-xs">
                {/* Left: Indirect Expenses & Overheads */}
                <div className="flex flex-col justify-between">
                  <div>
                    <div className="px-4 py-2.5 bg-muted/20 font-bold text-muted-foreground flex justify-between items-center border-b border-border/40">
                      <span>Particulars (Debit - Operating Expenses)</span>
                      <span>Amount (₹)</span>
                    </div>

                    <div className="divide-y divide-border/30">
                      {/* Gross Loss b/d (if loss) */}
                      {grossProfitNum < 0 && (
                        <div className="px-4 py-2.5 flex justify-between items-center bg-rose-500/5 font-bold text-rose-500">
                          <div>To Gross Loss b/d</div>
                          <span className="font-mono">{formatINR(Math.abs(grossProfitNum))}</span>
                        </div>
                      )}

                      {/* Indirect Expenses Rows */}
                      {pl?.indirect_expense.rows.map((row) => (
                        <Link
                          key={row.ledger_id}
                          href={`/ledgers/${row.ledger_id}/statement?from_date=${fromDate}&to_date=${toDate}`}
                          className="px-4 py-2.5 flex justify-between items-center hover:bg-primary/5 transition-colors group cursor-pointer"
                        >
                          <div>
                            <div className="font-medium text-foreground group-hover:text-primary flex items-center gap-1">
                              <span>To {row.ledger_name}</span>
                              <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                            </div>
                            <div className="text-[11px] text-muted-foreground">{row.group_name}</div>
                          </div>
                          <span className="font-mono font-medium text-foreground group-hover:text-primary">
                            {formatINR(row.amount)}
                          </span>
                        </Link>
                      ))}

                      {pl?.indirect_expense.rows.length === 0 && (
                        <div className="px-4 py-3 text-center text-muted-foreground italic">
                          No indirect operating expenses recorded.
                        </div>
                      )}

                      {/* Net Profit (transferred to Capital) */}
                      {netProfitNum >= 0 && (
                        <div className="px-4 py-2.5 flex justify-between items-center bg-emerald-500/10 font-bold text-emerald-500">
                          <div>
                            <div>To Net Profit</div>
                            <div className="text-[11px] font-normal text-emerald-500/80">Transferred to Capital / Balance Sheet</div>
                          </div>
                          <span className="font-mono text-sm">{formatINR(netProfitNum)}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Debit Total */}
                  <div className="px-4 py-2.5 bg-muted/30 border-t border-border/60 flex justify-between items-center font-bold text-foreground mt-4">
                    <span>Total Debit</span>
                    <span className="font-mono text-sm">₹{formatINR(plSideTotal)}</span>
                  </div>
                </div>

                {/* Right: Indirect Incomes & Revenue */}
                <div className="flex flex-col justify-between">
                  <div>
                    <div className="px-4 py-2.5 bg-muted/20 font-bold text-muted-foreground flex justify-between items-center border-b border-border/40">
                      <span>Particulars (Credit - Non-Operating Incomes)</span>
                      <span>Amount (₹)</span>
                    </div>

                    <div className="divide-y divide-border/30">
                      {/* Gross Profit b/d (if profit) */}
                      {grossProfitNum >= 0 && (
                        <div className="px-4 py-2.5 flex justify-between items-center bg-emerald-500/5 font-bold text-emerald-500">
                          <div>By Gross Profit b/d</div>
                          <span className="font-mono">{formatINR(grossProfitNum)}</span>
                        </div>
                      )}

                      {/* Indirect Incomes Rows */}
                      {pl?.indirect_income.rows.map((row) => (
                        <Link
                          key={row.ledger_id}
                          href={`/ledgers/${row.ledger_id}/statement?from_date=${fromDate}&to_date=${toDate}`}
                          className="px-4 py-2.5 flex justify-between items-center hover:bg-primary/5 transition-colors group cursor-pointer"
                        >
                          <div>
                            <div className="font-medium text-foreground group-hover:text-primary flex items-center gap-1">
                              <span>By {row.ledger_name}</span>
                              <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                            </div>
                            <div className="text-[11px] text-muted-foreground">{row.group_name}</div>
                          </div>
                          <span className="font-mono font-medium text-foreground group-hover:text-primary">
                            {formatINR(row.amount)}
                          </span>
                        </Link>
                      ))}

                      {/* Net Loss (if Net Loss) */}
                      {netProfitNum < 0 && (
                        <div className="px-4 py-2.5 flex justify-between items-center bg-rose-500/10 font-bold text-rose-500">
                          <div>
                            <div>By Net Loss</div>
                            <div className="text-[11px] font-normal text-rose-500/80">Deducted from Capital / Balance Sheet</div>
                          </div>
                          <span className="font-mono text-sm">{formatINR(Math.abs(netProfitNum))}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Credit Total */}
                  <div className="px-4 py-2.5 bg-muted/30 border-t border-border/60 flex justify-between items-center font-bold text-foreground mt-4">
                    <span>Total Credit</span>
                    <span className="font-mono text-sm">₹{formatINR(plSideTotal)}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Bottom Info Note */}
            <div className="p-4 rounded-xl border border-border/60 bg-muted/20 text-xs text-muted-foreground flex items-start gap-3">
              <Info className="w-4 h-4 text-primary shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-foreground">Double-Entry Accounting Note: </span>
                Gross Profit is calculated as <code>(Direct Incomes + Closing Stock) - (Opening Stock + Direct Expenses)</code>.
                Net Profit is transferred dynamically into the Capital account on the Balance Sheet. Click any ledger entry to open its detailed statement of accounts.
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
