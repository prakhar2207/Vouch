"use client";
import React, { useEffect, useState } from "react";
import axios from "axios";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import DashboardLayout from "@/components/DashboardLayout";
import { useShortcuts } from "@/context/ShortcutContext";
import {
  Plus,
  Sparkles,
  TrendingUp,
  TrendingDown,
  Info,
  Users,
  Receipt,
  ShoppingCart,
  DollarSign,
  ArrowUpRight,
  ArrowDownRight,
  HelpCircle,
  FileText,
  Boxes,
} from "lucide-react";

export default function Dashboard() {
  const router = useRouter();
  const { startTour, setIsHelpOpen } = useShortcuts();
  const [insights, setInsights] = useState<any>(null);
  const [vouchers, setVouchers] = useState<any[]>([]);
  const [forecast, setForecast] = useState<any>(null);
  const [chartMode, setChartMode] = useState<'VELOCITY' | 'FORECAST'>('VELOCITY');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }

    async function fetchData() {
      try {
        const token = getAccessToken();
        const headers = { Authorization: `Bearer ${token}` };

        const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
        const companies = compRes.data.data || [];
        if (companies.length === 0) {
          setError("No companies found. Please create a company first.");
          setLoading(false);
          return;
        }

        const [insightsRes, vouchersRes, forecastRes] = await Promise.all([
          axios.get(`${API_BASE_URL}/api/insights/`, { headers }).catch(() => ({ data: { data: null } })),
          axios.get(`${API_BASE_URL}/api/vouchers/`, { headers }).catch(() => ({ data: { data: [] } })),
          axios.get(`${API_BASE_URL}/api/v1/analytics/forecast/?days=30`, { headers }).catch(() => ({ data: { data: null } })),
        ]);

        setInsights(insightsRes.data?.data);
        setVouchers(vouchersRes.data?.data || []);
        if (forecastRes.data?.success && forecastRes.data?.data) {
          setForecast(forecastRes.data.data);
        }
      } catch (err) {
        console.error(err);
        setError("Failed to fetch dashboard data.");
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, [router]);

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex flex-col items-center justify-center h-96 space-y-3">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
          <div className="text-xs text-muted-foreground font-medium">Loading dashboard overview...</div>
        </div>
      </DashboardLayout>
    );
  }

  if (error) {
    return (
      <DashboardLayout>
        <div className="p-6 bg-destructive/10 border border-destructive/20 rounded-xl text-destructive text-sm">
          {error}
        </div>
      </DashboardLayout>
    );
  }

  const kpis = insights?.kpis || {
    today_sales: 0,
    today_collections: 0,
    money_to_collect: 0,
    bills_to_pay: 0,
    cash_and_bank: 0,
    total_sales: 0,
    total_purchases: 0,
    sales_vouchers_count: 0,
    purchase_vouchers_count: 0,
    total_stock_value: 0,
    total_in_stock_items: 0,
    total_stock_qty: 0,
  };

  const trend = insights?.trend_details || {
    status: "Constant",
    slope: 0,
    growth_rate_pct: 0,
    daily_trend: [],
    summary: "Sales volume is steady and consistent.",
  };

  const alerts = insights?.actionable_alerts || [];
  const rfmList = insights?.rfm_clusters || [];

  const hasSales = kpis.total_sales > 0;
  const hasPurchases = kpis.total_purchases > 0;
  const hasTransactions = vouchers.length > 0;

  return (
    <DashboardLayout>
      <div className="space-y-6 pb-12">
        
        {/* Header & Quick Actions Cluster */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-border/40 pb-5">
          <div>
            <h1 className="text-xl sm:text-2xl font-extrabold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">Business Overview</h1>
            <p className="text-xs text-muted-foreground mt-1">
              Real-time summary of sales, outstandings, and operational cash position.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
            <button
              onClick={() => setIsHelpOpen(true)}
              className="p-2 text-muted-foreground hover:text-foreground rounded-lg border border-border/50 hover:bg-muted/60 transition-colors cursor-pointer"
              title="Help & Shortcuts (F1)"
            >
              <HelpCircle className="w-4 h-4" />
            </button>

            <Link
              id="tour-sales-btn"
              href="/sales/new"
              className="px-4 py-2.5 bg-primary text-primary-foreground hover:bg-primary/90 rounded-xl text-sm font-semibold shadow-sm transition-all flex items-center gap-2 cursor-pointer min-h-[40px]"
            >
              <Plus className="w-4 h-4" />
              <span>Sell</span>
              <kbd className="hidden sm:inline text-xs font-mono font-semibold px-1.5 py-0.5 bg-primary-foreground/20 rounded">F8</kbd>
            </Link>

            <Link
              id="tour-purchase-btn"
              href="/purchases/new"
              className="px-4 py-2.5 bg-secondary text-foreground hover:bg-secondary/80 border border-border/60 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 cursor-pointer min-h-[40px]"
            >
              <Sparkles className="w-4 h-4 text-muted-foreground" />
              <span>Buy</span>
              <kbd className="hidden sm:inline text-xs font-mono font-semibold px-1.5 py-0.5 bg-muted border border-border/50 rounded text-muted-foreground">F9</kbd>
            </Link>

            <Link
              href="/parties"
              className="px-3.5 py-2.5 bg-card hover:bg-muted text-foreground border border-border/60 rounded-xl text-sm font-semibold transition-all flex items-center gap-1.5 cursor-pointer min-h-[40px]"
            >
              <ArrowDownRight className="w-4 h-4 text-emerald-500" />
              <span>Receive</span>
            </Link>

            <Link
              href="/parties"
              className="px-3.5 py-2.5 bg-card hover:bg-muted text-foreground border border-border/60 rounded-xl text-sm font-semibold transition-all flex items-center gap-1.5 cursor-pointer min-h-[40px]"
            >
              <ArrowUpRight className="w-4 h-4 text-rose-500" />
              <span>Pay</span>
            </Link>
          </div>
        </div>

        {/* Actionable Business Alerts Banner (P2-3) */}
        {alerts.length > 0 && (
          <div className="space-y-2">
            {alerts.map((alert: any, idx: number) => (
              <div
                key={idx}
                className="flex items-center gap-3 p-3.5 rounded-xl border border-amber-500/20 bg-amber-500/10 text-foreground text-xs font-medium"
              >
                <Info className="w-4 h-4 text-amber-500 shrink-0" />
                <span>{alert.message}</span>
              </div>
            ))}
          </div>
        )}

        {/* 6-Column Owner-First Metric Grid (P1-12 & P1-13) */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
          {/* Card 1: Today's Sales */}
          <div className="bg-card border border-border/40 rounded-xl p-4 shadow-sm space-y-1 relative overflow-hidden">
            <div className="absolute left-0 top-2 bottom-2 w-1 rounded-r-full bg-gradient-to-b from-blue-500 to-indigo-500" />
            <div className="flex items-center justify-between text-muted-foreground pl-2">
              <span className="text-xs font-medium">Today's Sales</span>
              <Receipt className="w-4 h-4 text-blue-500/70" />
            </div>
            <div className="text-xl font-bold font-mono tabular-nums tracking-tight text-foreground pl-2">
              ₹{(kpis.today_sales || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
            <div className="text-[11px] text-muted-foreground pl-2">
              Total: ₹{kpis.total_sales.toLocaleString("en-IN", { minimumFractionDigits: 0 })}
            </div>
          </div>

          {/* Card 2: Today's Collections */}
          <div className="bg-card border border-border/40 rounded-xl p-4 shadow-sm space-y-1 relative overflow-hidden">
            <div className="absolute left-0 top-2 bottom-2 w-1 rounded-r-full bg-gradient-to-b from-emerald-500 to-teal-500" />
            <div className="flex items-center justify-between text-muted-foreground pl-2">
              <span className="text-xs font-medium">Today's Collected</span>
              <ArrowDownRight className="w-4 h-4 text-emerald-500/70" />
            </div>
            <div className="text-xl font-bold font-mono tabular-nums tracking-tight text-emerald-500 pl-2">
              ₹{(kpis.today_collections || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
            <div className="text-[11px] text-muted-foreground pl-2">
              Incoming cash/receipts
            </div>
          </div>

          {/* Card 3: Money to Collect (Sundry Debtors) */}
          <Link
            href="/parties"
            className="bg-card border border-border/40 hover:border-emerald-500/40 rounded-xl p-4 shadow-sm space-y-1 transition-all group cursor-pointer block relative overflow-hidden"
          >
            <div className="absolute left-0 top-2 bottom-2 w-1 rounded-r-full bg-gradient-to-b from-teal-500 to-emerald-500" />
            <div className="flex items-center justify-between text-muted-foreground group-hover:text-foreground pl-2">
              <span className="text-xs font-medium">Money to Collect</span>
              <Users className="w-4 h-4 text-emerald-400 group-hover:scale-110 transition-transform" />
            </div>
            <div className="text-xl font-bold font-mono tabular-nums tracking-tight text-emerald-400 pl-2">
              ₹{(kpis.money_to_collect || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
            <div className="text-[11px] text-muted-foreground pl-2">
              Customer outstandings &rarr;
            </div>
          </Link>

          {/* Card 4: Bills to Pay (Sundry Creditors) */}
          <Link
            href="/parties"
            className="bg-card border border-border/40 hover:border-rose-500/40 rounded-xl p-4 shadow-sm space-y-1 transition-all group cursor-pointer block relative overflow-hidden"
          >
            <div className="absolute left-0 top-2 bottom-2 w-1 rounded-r-full bg-gradient-to-b from-orange-500 to-rose-500" />
            <div className="flex items-center justify-between text-muted-foreground group-hover:text-foreground pl-2">
              <span className="text-xs font-medium">Bills to Pay</span>
              <ShoppingCart className="w-4 h-4 text-rose-400 group-hover:scale-110 transition-transform" />
            </div>
            <div className="text-xl font-bold font-mono tabular-nums tracking-tight text-rose-400 pl-2">
              ₹{(kpis.bills_to_pay || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
            <div className="text-[11px] text-muted-foreground pl-2">
              Supplier outstandings &rarr;
            </div>
          </Link>

          {/* Card 5: Cash & Bank */}
          <Link
            href="/ledgers"
            className="bg-card border border-border/40 hover:border-blue-500/40 rounded-xl p-4 shadow-sm space-y-1 transition-all group cursor-pointer block relative overflow-hidden"
          >
            <div className="absolute left-0 top-2 bottom-2 w-1 rounded-r-full bg-gradient-to-b from-indigo-500 to-blue-500" />
            <div className="flex items-center justify-between text-muted-foreground group-hover:text-foreground pl-2">
              <span className="text-xs font-medium">Cash & Bank</span>
              <DollarSign className="w-4 h-4 text-indigo-400 group-hover:scale-110 transition-transform" />
            </div>
            <div className="text-xl font-bold font-mono tabular-nums tracking-tight text-foreground pl-2">
              ₹{(kpis.cash_and_bank || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
            <div className="text-[11px] text-muted-foreground pl-2">
              Liquid funds available &rarr;
            </div>
          </Link>

          {/* Card 6: Total Stock Value */}
          <Link 
            href="/inventory"
            className="bg-card border border-border/40 hover:border-cyan-500/40 rounded-xl p-4 shadow-sm space-y-1 transition-all group cursor-pointer block relative overflow-hidden"
          >
            <div className="absolute left-0 top-2 bottom-2 w-1 rounded-r-full bg-gradient-to-b from-cyan-500 to-sky-500" />
            <div className="flex items-center justify-between text-muted-foreground group-hover:text-foreground pl-2">
              <span className="text-xs font-medium">Stock Value</span>
              <Boxes className="w-4 h-4 text-cyan-400 group-hover:scale-110 transition-transform" />
            </div>
            <div className="text-xl font-bold font-mono tabular-nums tracking-tight text-cyan-400 pl-2">
              ₹{(kpis.total_stock_value || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
            <div className="text-[11px] text-muted-foreground pl-2">
              {kpis.total_in_stock_items || 0} items in stock &rarr;
            </div>
          </Link>
        </div>

        {/* Task 4: Clean 2-Column Section (60% Sales Velocity / 40% Top Customers) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          {/* Left: Sales Velocity & Predictive AI Forecast Area Chart (60% width) */}
          <div className="lg:col-span-7 bg-card border border-border/50 rounded-xl p-5 shadow-2xs flex flex-col space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div>
                <h2 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                  <span>{chartMode === 'VELOCITY' ? 'Sales Velocity' : 'AI Sales Forecast (30-Day)'}</span>
                  <span title={chartMode === 'VELOCITY' ? 'Daily revenue trajectory over time' : 'Machine learning linear projection over historical velocity'} className="cursor-help text-muted-foreground hover:text-foreground">
                    <Info className="w-3.5 h-3.5" />
                  </span>
                </h2>
                <p className="text-xs text-muted-foreground">
                  {chartMode === 'VELOCITY' ? 'Day-to-day revenue flow and billing frequency' : 'Predictive revenue trajectory with confidence intervals'}
                </p>
              </div>

              <div className="flex items-center gap-2">
                <div className="flex items-center bg-muted/60 p-1 rounded-lg border border-border/40">
                  <button
                    type="button"
                    onClick={() => setChartMode('VELOCITY')}
                    className={`px-2.5 py-1 text-xs font-semibold rounded transition-colors cursor-pointer ${
                      chartMode === 'VELOCITY'
                        ? 'bg-card text-foreground shadow-sm'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    Historical
                  </button>
                  <button
                    type="button"
                    onClick={() => setChartMode('FORECAST')}
                    className={`px-2.5 py-1 text-xs font-semibold rounded transition-colors flex items-center gap-1 cursor-pointer ${
                      chartMode === 'FORECAST'
                        ? 'bg-purple-600 text-white shadow-sm'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <Sparkles className="w-3 h-3 text-amber-300" />
                    <span>AI Forecast</span>
                  </button>
                </div>

                {chartMode === 'VELOCITY' && trend.growth_rate_pct !== 0 && (
                  <span className={`px-2 py-0.5 text-[11px] font-mono font-medium rounded border ${
                    trend.growth_rate_pct > 0
                      ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20"
                      : "bg-rose-500/10 text-rose-500 border-rose-500/20"
                  }`}>
                    {trend.growth_rate_pct > 0 ? `+${trend.growth_rate_pct}%` : `${trend.growth_rate_pct}%`}
                  </span>
                )}
                {chartMode === 'FORECAST' && forecast && (
                  <span className={`px-2 py-0.5 text-[11px] font-mono font-medium rounded border ${
                    forecast.trend_status === 'Booming'
                      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                      : forecast.trend_status === 'Declining'
                      ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                      : "bg-blue-500/10 text-blue-400 border-blue-500/20"
                  }`}>
                    {forecast.trend_status}
                  </span>
                )}
              </div>
            </div>

            {chartMode === 'FORECAST' ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs px-1 text-muted-foreground font-sans">
                  <div>
                    Projected Total: <span className="font-bold text-foreground font-mono">₹{(forecast?.projected_total || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                  </div>
                  <div>
                    Daily Avg: <span className="font-bold text-foreground font-mono">₹{(forecast?.projected_daily_average || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                  </div>
                </div>

                <div className="h-48 w-full pt-1">
                  {forecast?.daily_forecast && forecast.daily_forecast.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={forecast.daily_forecast}>
                        <defs>
                          <linearGradient id="forecastGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.35} />
                            <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-border/40" />
                        <XAxis dataKey="date" stroke="currentColor" className="text-muted-foreground" fontSize={11} />
                        <YAxis stroke="currentColor" className="text-muted-foreground" fontSize={11} />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: "var(--card)",
                            borderColor: "var(--border)",
                            borderRadius: "8px",
                            fontSize: "12px",
                          }}
                          formatter={(val: any) => [`₹${Number(val).toLocaleString("en-IN")}`, "Projected Sales"]}
                        />
                        <Area
                          type="monotone"
                          dataKey="projected_sales"
                          stroke="#8b5cf6"
                          strokeWidth={2}
                          fillOpacity={1}
                          fill="url(#forecastGrad)"
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
                      No sales data available for projection.
                    </div>
                  )}
                </div>

                {forecast?.trend_summary && (
                  <div className="text-[11px] text-muted-foreground bg-muted/40 px-3 py-1.5 rounded-lg border border-border/40 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-purple-400 shrink-0" />
                    <span>{forecast.trend_summary}</span>
                  </div>
                )}
              </div>
            ) : (
              <div className="h-60 w-full pt-1">
                {trend.daily_trend && trend.daily_trend.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={trend.daily_trend}>
                      <defs>
                        <linearGradient id="salesVelocityGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.25} />
                          <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-border/40" />
                      <XAxis dataKey="date" stroke="currentColor" className="text-muted-foreground" fontSize={12} />
                      <YAxis stroke="currentColor" className="text-muted-foreground" fontSize={12} />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "var(--card)",
                          borderColor: "var(--border)",
                          borderRadius: "8px",
                          fontSize: "12px",
                        }}
                        formatter={(val: any) => [`₹${Number(val).toLocaleString("en-IN")}`, "Sales"]}
                      />
                      <Area
                        type="monotone"
                        dataKey="sales"
                        stroke="#3b82f6"
                        strokeWidth={2}
                        fillOpacity={1}
                        fill="url(#salesVelocityGrad)"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex flex-col items-center justify-center border border-dashed border-border/60 rounded-lg text-center p-6 space-y-1.5">
                    <TrendingUp className="w-6 h-6 text-muted-foreground/40" />
                    <div className="text-xs font-medium text-muted-foreground">No transaction data yet</div>
                    <div className="text-xs text-muted-foreground/80">
                      Create a sales invoice (<kbd className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded border border-border/60 font-semibold">F8</kbd>) to start tracking velocity.
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Right: Top Customers & Outstandings (40% width) */}
          <div className="lg:col-span-5 bg-card border border-border/50 rounded-xl p-5 shadow-2xs flex flex-col space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                  <span>Customer Loyalty & Recency</span>
                  <span title="Recency, Frequency, and Monetary distribution of buyers" className="cursor-help text-muted-foreground hover:text-foreground">
                    <Info className="w-3.5 h-3.5" />
                  </span>
                </h2>
                <p className="text-xs text-muted-foreground">Top customers grouped by ordering frequency</p>
              </div>
              <Link href="/parties" className="text-xs text-muted-foreground hover:text-foreground font-medium transition-colors">
                View all →
              </Link>
            </div>

            <div className="overflow-y-auto flex-1 max-h-60 space-y-2">
              {rfmList.length > 0 ? (
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-border/60 text-muted-foreground">
                      <th className="pb-2 font-medium">Customer</th>
                      <th className="pb-2 font-medium">Tier</th>
                      <th className="pb-2 font-medium text-right">Bills</th>
                      <th className="pb-2 font-medium text-right">Revenue</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/30">
                    {rfmList.slice(0, 5).map((customer: any, idx: number) => {
                      const segName = customer.segment || "Standard";
                      return (
                        <tr key={idx} className="hover:bg-muted/40 transition-colors">
                          <td className="py-3 font-medium text-foreground truncate max-w-[120px]">
                            {customer.party_ledger__name || "Customer"}
                          </td>
                          <td className="py-3">
                            <span className="px-2 py-0.5 rounded text-xs font-semibold bg-muted text-muted-foreground border border-border/50">
                              {segName}
                            </span>
                          </td>
                          <td className="py-3 text-right font-mono tabular-nums text-muted-foreground">
                            {customer.frequency}
                          </td>
                          <td className="py-3 text-right font-mono tabular-nums font-semibold text-foreground">
                            ₹{Number(customer.monetary).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              ) : (
                <div className="h-44 flex flex-col items-center justify-center border border-dashed border-border/60 rounded-lg text-center p-6 space-y-1.5">
                  <Users className="w-6 h-6 text-muted-foreground/40" />
                  <div className="text-xs font-medium text-muted-foreground">No customer records yet</div>
                  <div className="text-xs text-muted-foreground/80">
                    Customer loyalty and order statistics will populate here automatically.
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Recent Ledger Transactions Table */}
        <div className="bg-card border border-border/50 rounded-xl p-5 shadow-2xs space-y-3.5">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-foreground">Recent Transactions</h2>
              <p className="text-xs text-muted-foreground">Audit log of recently posted vouchers</p>
            </div>
            <Link href="/vouchers" className="text-xs text-muted-foreground hover:text-foreground font-medium transition-colors">
              View Day Book →
            </Link>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-border/60 text-muted-foreground">
                  <th className="py-2.5 font-medium">Voucher No.</th>
                  <th className="py-2.5 font-medium">Date</th>
                  <th className="py-2.5 font-medium">Type</th>
                  <th className="py-2.5 font-medium">Particulars</th>
                  <th className="py-2.5 font-medium">Status</th>
                  <th className="py-2.5 font-medium text-right">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/30">
                {vouchers.slice(0, 6).map((v) => (
                  <tr key={v.id} className="hover:bg-muted/40 transition-colors">
                    <td className="py-3 font-mono tabular-nums font-semibold text-foreground">{v.voucher_number}</td>
                    <td className="py-3 text-muted-foreground">{v.date || v.voucher_date}</td>
                    <td className="py-3">
                      <span className="px-2 py-0.5 rounded text-xs font-mono font-semibold uppercase bg-muted text-muted-foreground border border-border/50">
                        {v.type || v.voucher_type}
                      </span>
                    </td>
                    <td className="py-3 text-foreground font-medium">{v.party_name || "General Entry"}</td>
                    <td className="py-3">
                      <span className="px-2 py-0.5 rounded text-xs font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border border-emerald-500/20">
                        {v.status}
                      </span>
                    </td>
                    <td className="py-3 text-right font-mono tabular-nums font-semibold text-foreground">
                      ₹{Number(v.total_amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </td>
                  </tr>
                ))}
                {!hasTransactions && (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-muted-foreground text-xs">
                      No vouchers posted yet. Press <kbd className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded border border-border/60 font-semibold">F8</kbd> for Sales or <kbd className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded border border-border/60 font-semibold">F9</kbd> for Purchases.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
