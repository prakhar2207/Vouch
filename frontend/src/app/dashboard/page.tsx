"use client";
import { API_BASE_URL } from '@/utils/api';
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
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import DashboardLayout from "@/components/DashboardLayout";
import { useShortcuts } from "@/context/ShortcutContext";

export default function Dashboard() {
  const router = useRouter();
  const { startTour, setIsHelpOpen } = useShortcuts();
  const [insights, setInsights] = useState<any>(null);
  const [vouchers, setVouchers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showGrowthExplainer, setShowGrowthExplainer] = useState(false);
  const [showCustomerExplainer, setShowCustomerExplainer] = useState(false);

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
        const companyId = companies[0].id;

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
        <div className="flex flex-col items-center justify-center h-96 space-y-4">
          <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
          <div className="text-gray-400 font-medium">Loading your financial dashboard...</div>
        </div>
      </DashboardLayout>
    );
  }

  if (error) {
    return (
      <DashboardLayout>
        <div className="p-8 bg-red-500/10 border border-red-500/30 rounded-2xl text-red-400">
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
  };

  const trend = insights?.trend_details || {
    status: "Constant",
    slope: 0,
    growth_rate_pct: 0,
    daily_trend: [],
    summary: "Sales volume is steady and consistent.",
  };

  const rfmList = insights?.rfm_clusters || [];

  const trendBadgeColor =
    trend.status === "Booming"
      ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/40"
      : trend.status === "Declining"
      ? "bg-rose-500/20 text-rose-400 border-rose-500/40"
      : "bg-blue-500/20 text-blue-400 border-blue-500/40";

  const trendIcon =
    trend.status === "Booming" ? "🚀" : trend.status === "Declining" ? "📉" : "⚖️";

  return (
    <DashboardLayout>
      <div className="space-y-8 pb-16">
        {/* Header with Quick Actions & Tutorial Trigger */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-border pb-6">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight">Business Overview & Insights</h1>
            <p className="text-sm text-gray-400 mt-1">
              Live tracking of your revenue, sales speed, top customers, and accounts.
            </p>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <button
              onClick={() => setIsHelpOpen(true)}
              className="px-3.5 py-2 bg-zinc-800 hover:bg-zinc-700 text-gray-200 rounded-lg text-xs font-semibold border border-zinc-700 transition-colors flex items-center gap-1.5"
            >
              <span>📖 User Guide & Tutorials (F1)</span>
            </button>
            <Link
              href="/sales/new"
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold shadow-md transition-colors flex items-center gap-1.5"
            >
              <span>+ Sales Invoice</span>
              <kbd className="bg-blue-800 px-1.5 py-0.5 rounded text-[10px]">F8</kbd>
            </Link>
            <Link
              href="/purchases/new"
              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-xs font-bold shadow-md transition-colors flex items-center gap-1.5"
            >
              <span>+ Purchase (AI Scanner)</span>
              <kbd className="bg-purple-800 px-1.5 py-0.5 rounded text-[10px]">F9</kbd>
            </Link>
          </div>
        </div>

        {/* Business Sales Growth Status Card */}
        <div id="tour-business-health" className="bg-gradient-to-r from-zinc-900 to-zinc-950 border border-zinc-800 rounded-2xl p-6 shadow-xl flex flex-col space-y-4">
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <span className="text-xs font-bold uppercase tracking-wider text-gray-400">Current Sales Pace</span>
                <span className={`px-3 py-1 rounded-full text-xs font-bold border flex items-center gap-1.5 ${trendBadgeColor}`}>
                  <span>{trendIcon}</span>
                  {trend.status.toUpperCase()}
                </span>
                <button
                  onClick={() => setShowGrowthExplainer((prev) => !prev)}
                  className="text-xs text-blue-400 hover:text-blue-300 font-medium underline flex items-center gap-1 cursor-pointer"
                >
                  <span>{showGrowthExplainer ? "Hide Explanation" : "💡 What does this mean?"}</span>
                </button>
              </div>
              <p className="text-base text-gray-200 font-medium">{trend.summary}</p>
            </div>

            <div className="flex items-center gap-4 bg-zinc-900/90 border border-zinc-800 p-4 rounded-xl">
              <div className="text-right">
                <div className="text-xs text-gray-400">Net Balance (Sales - Purchases)</div>
                <div className={`text-2xl font-bold font-mono ${kpis.net_position >= 0 ? "text-green-400" : "text-red-400"}`}>
                  ₹{kpis.net_position.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
              </div>
            </div>
          </div>

          {/* Collapsible Easy-to-Understand Explainer */}
          {showGrowthExplainer && (
            <div className="p-4 bg-zinc-950/90 border border-zinc-800 rounded-xl text-xs text-gray-300 space-y-2 animate-in fade-in">
              <div className="font-bold text-white text-sm">How your business pace is evaluated:</div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-1">
                <div className="p-2.5 bg-zinc-900 rounded-lg border border-zinc-800">
                  <div className="font-bold text-emerald-400 mb-1">🚀 Booming</div>
                  <div>Sales are growing rapidly day-over-day. Make sure your inventory and raw materials are well-stocked.</div>
                </div>
                <div className="p-2.5 bg-zinc-900 rounded-lg border border-zinc-800">
                  <div className="font-bold text-blue-400 mb-1">⚖️ Constant</div>
                  <div>Sales are steady and consistent. Your business has predictable daily revenue.</div>
                </div>
                <div className="p-2.5 bg-zinc-900 rounded-lg border border-zinc-800">
                  <div className="font-bold text-rose-400 mb-1">📉 Declining</div>
                  <div>Recent sales have slowed down. Consider contacting customers who haven't ordered recently.</div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* KPI Summary Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          <div className="bg-card p-5 rounded-2xl shadow-sm border border-border space-y-2">
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Total Sales Invoiced</span>
            <div className="text-2xl font-extrabold text-green-500 font-mono">
              ₹{kpis.total_sales.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
            <span className="text-[11px] text-gray-400 block">{kpis.sales_vouchers_count} Customer Invoices Created</span>
          </div>

          <div className="bg-card p-5 rounded-2xl shadow-sm border border-border space-y-2">
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Total Purchases Inward</span>
            <div className="text-2xl font-extrabold text-purple-400 font-mono">
              ₹{kpis.total_purchases.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
            <span className="text-[11px] text-gray-400 block">{kpis.purchase_vouchers_count} Supplier Bills Recorded</span>
          </div>

          <div className="bg-card p-5 rounded-2xl shadow-sm border border-border space-y-2">
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Active Customers</span>
            <div className="text-2xl font-extrabold text-blue-400 font-mono">
              {rfmList.length}
            </div>
            <span className="text-[11px] text-gray-400 block">Grouped by purchase history</span>
          </div>

          <div className="bg-card p-5 rounded-2xl shadow-sm border border-border space-y-2">
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Accounting Vouchers</span>
            <div className="text-2xl font-extrabold text-amber-400 font-mono">
              {vouchers.length}
            </div>
            <span className="text-[11px] text-gray-400 block">Strict balanced ledgers</span>
          </div>
        </div>

        {/* Charts & Customer Groups Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Daily Sales Trend Chart */}
          <div className="bg-card border border-border p-6 rounded-2xl shadow-sm flex flex-col space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-white">Daily Sales Trend</h3>
                <p className="text-xs text-gray-400">Track your day-to-day revenue flow</p>
              </div>
              <span className={`px-2.5 py-1 text-xs font-bold rounded-md font-mono border ${trendBadgeColor}`}>
                {trend.status}
              </span>
            </div>

            <div className="h-64 w-full pt-2">
              {trend.daily_trend && trend.daily_trend.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={trend.daily_trend}>
                    <defs>
                      <linearGradient id="salesGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                    <XAxis dataKey="date" stroke="#71717a" fontSize={11} />
                    <YAxis stroke="#71717a" fontSize={11} />
                    <Tooltip
                      contentStyle={{ backgroundColor: "#18181b", borderColor: "#3f3f46", borderRadius: "8px" }}
                      formatter={(val: any) => [`₹${Number(val).toLocaleString("en-IN")}`, "Sales"]}
                    />
                    <Area type="monotone" dataKey="sales" stroke="#3b82f6" strokeWidth={2} fillOpacity={1} fill="url(#salesGrad)" />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-gray-500 text-sm">
                  Create sales invoices (press F8) to see your trend chart.
                </div>
              )}
            </div>
          </div>

          {/* Customer Value Groups */}
          <div className="bg-card border border-border p-6 rounded-2xl shadow-sm flex flex-col space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-white">Customer Value Groups</h3>
                <p className="text-xs text-gray-400">Identifies your best buyers and customers needing follow-up</p>
              </div>
              <button
                onClick={() => setShowCustomerExplainer((prev) => !prev)}
                className="text-xs text-blue-400 hover:text-blue-300 font-medium underline"
              >
                {showCustomerExplainer ? "Hide Tip" : "💡 How it works"}
              </button>
            </div>

            {showCustomerExplainer && (
              <div className="p-3 bg-zinc-950 border border-zinc-800 rounded-lg text-xs text-gray-300 space-y-1 animate-in fade-in">
                <p><strong>⭐ High Value / VIP:</strong> Top spenders who bought recently. Reward them with great service!</p>
                <p><strong>⚡ Medium Value:</strong> Regular repeat buyers.</p>
                <p><strong>💤 Low Value:</strong> Have not ordered in a while. Call them with special offers to re-engage.</p>
              </div>
            )}

            <div className="overflow-y-auto flex-1 max-h-64 space-y-2">
              {rfmList.length > 0 ? (
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-border text-gray-400">
                      <th className="pb-2 font-semibold">Customer</th>
                      <th className="pb-2 font-semibold">Status Group</th>
                      <th className="pb-2 font-semibold text-right">Orders</th>
                      <th className="pb-2 font-semibold text-right">Total Revenue</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rfmList.map((customer: any, idx: number) => {
                      const segName = customer.segment || "Standard";
                      const badge =
                        segName.includes("High") || segName.includes("VIP")
                          ? "bg-green-500/20 text-green-400 border-green-500/30"
                          : segName.includes("Medium")
                          ? "bg-amber-500/20 text-amber-400 border-amber-500/30"
                          : "bg-blue-500/20 text-blue-400 border-blue-500/30";

                      return (
                        <tr key={idx} className="border-b border-zinc-800/50 hover:bg-zinc-800/40">
                          <td className="py-2.5 font-medium text-white">{customer.party_ledger__name || "Customer"}</td>
                          <td className="py-2.5">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${badge}`}>
                              {segName}
                            </span>
                          </td>
                          <td className="py-2.5 text-right font-mono text-gray-300">{customer.frequency}</td>
                          <td className="py-2.5 text-right font-mono font-bold text-green-400">
                            ₹{Number(customer.monetary).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              ) : (
                <div className="h-48 flex items-center justify-center text-gray-500 text-sm">
                  Add more customer invoices to see customer groupings.
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Recent Transactions Audit Table */}
        <div className="bg-card border border-border p-6 rounded-2xl shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-bold text-white">Recent Transactions</h3>
              <p className="text-xs text-gray-400">Chronological ledger activity log</p>
            </div>
            <Link href="/vouchers" className="text-xs text-blue-400 hover:text-blue-300 font-bold">
              View All →
            </Link>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-border text-gray-400">
                  <th className="py-2.5 font-semibold">Voucher No.</th>
                  <th className="py-2.5 font-semibold">Date</th>
                  <th className="py-2.5 font-semibold">Type</th>
                  <th className="py-2.5 font-semibold">Particulars</th>
                  <th className="py-2.5 font-semibold">Status</th>
                  <th className="py-2.5 font-semibold text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {vouchers.slice(0, 8).map((v) => (
                  <tr key={v.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/40 transition-colors">
                    <td className="py-2.5 font-mono font-medium text-white">{v.voucher_number}</td>
                    <td className="py-2.5 text-gray-400">{v.date || v.voucher_date}</td>
                    <td className="py-2.5">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase font-mono bg-zinc-800 text-gray-300 border border-zinc-700">
                        {v.type || v.voucher_type}
                      </span>
                    </td>
                    <td className="py-2.5 text-gray-300">{v.party_name || "General Entry"}</td>
                    <td className="py-2.5">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        v.status === "POSTED" ? "bg-green-500/20 text-green-400" : "bg-zinc-800 text-gray-400"
                      }`}>
                        {v.status}
                      </span>
                    </td>
                    <td className="py-2.5 text-right font-mono font-bold text-white">
                      ₹{Number(v.total_amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </td>
                  </tr>
                ))}
                {vouchers.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-gray-500">
                      No transactions found. Press F8 to record a sales invoice or F9 for a purchase!
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
