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

        const [insightsRes, vouchersRes] = await Promise.all([
          axios.get(`${API_BASE_URL}/api/insights/`, { headers }).catch(() => ({ data: { data: null } })),
          axios.get(`${API_BASE_URL}/api/vouchers/`, { headers }).catch(() => ({ data: { data: [] } })),
        ]);

        setInsights(insightsRes.data?.data);
        setVouchers(vouchersRes.data?.data || []);
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
    total_sales: 0,
    total_purchases: 0,
    sales_vouchers_count: 0,
    purchase_vouchers_count: 0,
    net_position: 0,
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

  const rfmList = insights?.rfm_clusters || [];

  const hasSales = kpis.total_sales > 0;
  const hasPurchases = kpis.total_purchases > 0;
  const hasTransactions = vouchers.length > 0;

  return (
    <DashboardLayout>
      <div className="space-y-6 pb-12">
        
        {/* Task 2: Clean Dashboard Header & Action Cluster */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-foreground">Business Overview</h1>
            <p className="text-xs text-muted-foreground mt-0.5">
              Real-time summary of sales, outstandings, and operational activity.
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              onClick={() => setIsHelpOpen(true)}
              className="p-2 text-muted-foreground hover:text-foreground rounded-lg border border-border/50 hover:bg-muted/60 transition-colors"
              title="Help & Shortcuts (F1)"
            >
              <HelpCircle className="w-4 h-4" />
            </button>

            <Link
              id="tour-sales-btn"
              href="/sales/new"
              className="px-3.5 py-1.5 bg-primary text-primary-foreground hover:bg-primary/90 rounded-lg text-xs font-semibold shadow-2xs transition-all flex items-center gap-1.5"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Sales</span>
              <kbd className="text-[9px] font-mono px-1 py-0.2 bg-primary-foreground/20 rounded">F8</kbd>
            </Link>

            <Link
              id="tour-purchase-btn"
              href="/purchases/new"
              className="px-3.5 py-1.5 bg-secondary text-foreground hover:bg-secondary/80 border border-border/60 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5"
            >
              <Sparkles className="w-3.5 h-3.5 text-muted-foreground" />
              <span>Purchase</span>
              <kbd className="text-[9px] font-mono px-1 py-0.2 bg-muted border border-border/50 rounded text-muted-foreground">F9</kbd>
            </Link>
          </div>
        </div>

        {/* 5-Column Metric Grid with Real-Time Stock Valuation */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          {/* Card 1: Total Sales */}
          <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-medium">Total Sales</span>
              <Receipt className="w-4 h-4 text-muted-foreground/70" />
            </div>
            <div className={`text-2xl font-bold font-mono tracking-tight ${hasSales ? "text-foreground" : "text-foreground/90"}`}>
              ₹{kpis.total_sales.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
            <div className="text-[11px] text-muted-foreground">
              {kpis.sales_vouchers_count} {kpis.sales_vouchers_count === 1 ? "invoice" : "invoices"} this period
            </div>
          </div>

          {/* Card 2: Total Purchases */}
          <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-medium">Total Purchases</span>
              <ShoppingCart className="w-4 h-4 text-muted-foreground/70" />
            </div>
            <div className={`text-2xl font-bold font-mono tracking-tight ${hasPurchases ? "text-foreground" : "text-foreground/90"}`}>
              ₹{kpis.total_purchases.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
            <div className="text-[11px] text-muted-foreground">
              {kpis.purchase_vouchers_count} {kpis.purchase_vouchers_count === 1 ? "bill" : "bills"} inward
            </div>
          </div>

          {/* Card 3: Total Stock Value */}
          <Link 
            href="/inventory"
            className="bg-card border border-border/50 hover:border-blue-500/50 rounded-xl p-4 shadow-2xs space-y-1 transition-all group cursor-pointer block"
            title="View Inventory Breakdown"
          >
            <div className="flex items-center justify-between text-muted-foreground group-hover:text-foreground">
              <span className="text-xs font-medium">Total Stock Value</span>
              <Boxes className="w-4 h-4 text-blue-400 group-hover:scale-110 transition-transform" />
            </div>
            <div className="text-2xl font-bold font-mono tracking-tight text-blue-400">
              ₹{(kpis.total_stock_value || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
            <div className="text-[11px] text-muted-foreground flex items-center justify-between">
              <span>{kpis.total_in_stock_items || 0} items ({Math.round(kpis.total_stock_qty || 0).toLocaleString("en-IN")} pcs)</span>
              <span className="text-blue-400 text-[10px] font-semibold opacity-0 group-hover:opacity-100 transition-opacity">
                &rarr;
              </span>
            </div>
          </Link>

          {/* Card 4: Net Cash / Receivables */}
          <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-medium">Net Position</span>
              <DollarSign className="w-4 h-4 text-muted-foreground/70" />
            </div>
            <div className={`text-2xl font-bold font-mono tracking-tight ${
              kpis.net_position > 0 ? "text-emerald-500" : kpis.net_position < 0 ? "text-rose-500" : "text-foreground/90"
            }`}>
              ₹{Math.abs(kpis.net_position).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
            <div className="text-[11px] text-muted-foreground flex items-center gap-1">
              {kpis.net_position > 0 ? (
                <span className="text-emerald-500 flex items-center font-medium">
                  <ArrowUpRight className="w-3 h-3" /> Surplus
                </span>
              ) : kpis.net_position < 0 ? (
                <span className="text-rose-500 flex items-center font-medium">
                  <ArrowDownRight className="w-3 h-3" /> Outstanding
                </span>
              ) : (
                <span>Balanced</span>
              )}
              <span className="text-muted-foreground/80">· Sales minus Purchases</span>
            </div>
          </div>

          {/* Card 4: Active Parties */}
          <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-medium">Active Parties</span>
              <Users className="w-4 h-4 text-muted-foreground/70" />
            </div>
            <div className="text-2xl font-bold font-mono tracking-tight text-foreground/90">
              {rfmList.length}
            </div>
            <div className="text-[11px] text-muted-foreground">
              Customers & Suppliers on record
            </div>
          </div>
        </div>

        {/* Task 4: Clean 2-Column Section (60% Sales Velocity / 40% Top Customers) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          {/* Left: Sales Velocity Area Chart (60% width) */}
          <div className="lg:col-span-7 bg-card border border-border/50 rounded-xl p-5 shadow-2xs flex flex-col space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                  <span>Sales Velocity</span>
                  <span title="Daily revenue trajectory over time" className="cursor-help text-muted-foreground hover:text-foreground">
                    <Info className="w-3.5 h-3.5" />
                  </span>
                </h2>
                <p className="text-xs text-muted-foreground">Day-to-day revenue flow and billing frequency</p>
              </div>

              {trend.growth_rate_pct !== 0 && (
                <span className={`px-2 py-0.5 text-[11px] font-mono font-medium rounded border ${
                  trend.growth_rate_pct > 0
                    ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20"
                    : "bg-rose-500/10 text-rose-500 border-rose-500/20"
                }`}>
                  {trend.growth_rate_pct > 0 ? `+${trend.growth_rate_pct}%` : `${trend.growth_rate_pct}%`}
                </span>
              )}
            </div>

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
                    <XAxis dataKey="date" stroke="currentColor" className="text-muted-foreground" fontSize={11} />
                    <YAxis stroke="currentColor" className="text-muted-foreground" fontSize={11} />
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
                      strokeWidth={1.5}
                      fillOpacity={1}
                      fill="url(#salesVelocityGrad)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex flex-col items-center justify-center border border-dashed border-border/60 rounded-lg text-center p-6 space-y-1.5">
                  <TrendingUp className="w-6 h-6 text-muted-foreground/40" />
                  <div className="text-xs font-medium text-muted-foreground">No transaction data yet</div>
                  <div className="text-[11px] text-muted-foreground/80">
                    Create a sales invoice (<kbd className="font-mono text-[10px]">F8</kbd>) to start tracking velocity.
                  </div>
                </div>
              )}
            </div>
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
                          <td className="py-2.5 font-medium text-foreground truncate max-w-[120px]">
                            {customer.party_ledger__name || "Customer"}
                          </td>
                          <td className="py-2.5">
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-muted text-muted-foreground border border-border/50">
                              {segName}
                            </span>
                          </td>
                          <td className="py-2.5 text-right font-mono text-muted-foreground">
                            {customer.frequency}
                          </td>
                          <td className="py-2.5 text-right font-mono font-medium text-foreground">
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
                  <div className="text-[11px] text-muted-foreground/80">
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
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-border/60 text-muted-foreground">
                  <th className="py-2 font-medium">Voucher No.</th>
                  <th className="py-2 font-medium">Date</th>
                  <th className="py-2 font-medium">Type</th>
                  <th className="py-2 font-medium">Particulars</th>
                  <th className="py-2 font-medium">Status</th>
                  <th className="py-2 font-medium text-right">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/30">
                {vouchers.slice(0, 6).map((v) => (
                  <tr key={v.id} className="hover:bg-muted/40 transition-colors">
                    <td className="py-2 font-mono font-medium text-foreground">{v.voucher_number}</td>
                    <td className="py-2 text-muted-foreground">{v.date || v.voucher_date}</td>
                    <td className="py-2">
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-medium uppercase bg-muted text-muted-foreground border border-border/50">
                        {v.type || v.voucher_type}
                      </span>
                    </td>
                    <td className="py-2 text-foreground font-medium">{v.party_name || "General Entry"}</td>
                    <td className="py-2">
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-medium text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border border-emerald-500/20">
                        {v.status}
                      </span>
                    </td>
                    <td className="py-2 text-right font-mono font-medium text-foreground">
                      ₹{Number(v.total_amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </td>
                  </tr>
                ))}
                {!hasTransactions && (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-muted-foreground text-xs">
                      No vouchers posted yet. Press <kbd className="font-mono text-[10px] bg-muted px-1 py-0.2 rounded border">F8</kbd> for Sales or <kbd className="font-mono text-[10px] bg-muted px-1 py-0.2 rounded border">F9</kbd> for Purchases.
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
