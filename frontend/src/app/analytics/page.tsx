"use client";
import React, { useEffect, useState, useMemo } from "react";
import axios from "axios";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import DashboardLayout from "@/components/DashboardLayout";
import { useCompany } from "@/context/CompanyContext";
import { useFinancialYear } from "@/context/FinancialYearContext";
import { LocalAnalyticsEngine } from "@/lib/analytics/analytics-engine";
import {
  TrendingUp,
  Sparkles,
  Boxes,
  Users,
  Calendar,
  Layers,
  Tag,
  ShieldCheck,
  RefreshCw,
  Clock,
  Landmark,
  FileText,
  AlertCircle,
} from "lucide-react";

function formatCurrencyShort(val: number): string {
  if (val >= 10000000) return `₹${(val / 10000000).toFixed(1)}Cr`;
  if (val >= 100000) return `₹${(val / 100000).toFixed(1)}L`;
  if (val >= 1000) return `₹${(val / 1000).toFixed(0)}k`;
  return `₹${Math.round(val)}`;
}

function formatChartDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  } catch {
    return dateStr;
  }
}

function AnalyticsHubContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialTab = searchParams.get("tab") || "sales";

  const [activeTab, setActiveTab] = useState<"sales" | "monthly" | "rfm" | "inventory" | "cashflow">(
    (initialTab as any) || "sales"
  );
  const [forecastDays, setForecastDays] = useState<number>(30);
  const [forecast, setForecast] = useState<any>(null);
  const [rfmData, setRfmData] = useState<any[]>([]);
  const [insights, setInsights] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [retailDiscount, setRetailDiscount] = useState<number>(0);

  const { activeCompany, companyId: activeCompanyId } = useCompany();
  const { activeFY } = useFinancialYear();

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }

    let isMounted = true;
    async function loadAnalytics() {
      setLoading(true);
      try {
        let cid = activeCompanyId;
        if (!cid && typeof window !== "undefined") {
          cid = localStorage.getItem("vouch_active_company_id");
        }
        if (!cid) {
          const token = getAccessToken();
          const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          const companies = Array.isArray(compRes.data) ? compRes.data : compRes.data.data || [];
          if (companies.length > 0) {
            cid = companies[0].id;
          }
        }

        if (!cid) {
          if (isMounted) setLoading(false);
          return;
        }

        // Try remote API first with local fallback
        const token = getAccessToken();
        const headers = { Authorization: `Bearer ${token}`, "X-Company-ID": cid };

        const [forecastRes, rfmRes, insightsRes] = await Promise.allSettled([
          axios.get(`${API_BASE_URL}/api/v1/analytics/forecast/${cid}/?days=${forecastDays}&company_id=${cid}`, { headers }),
          axios.get(`${API_BASE_URL}/api/v1/analytics/rfm/${cid}/`, { headers }),
          axios.get(`${API_BASE_URL}/api/v1/analytics/insights/${cid}/`, { headers }),
        ]);

        if (isMounted) {
          if (forecastRes.status === "fulfilled" && forecastRes.value.data?.success) {
            setForecast(forecastRes.value.data.data);
          } else {
            // Local fallback
            const localData = await LocalAnalyticsEngine.getDashboardAnalytics(cid);
            if (localData.forecast) {
              setForecast(localData.forecast);
            }
          }

          if (rfmRes.status === "fulfilled" && rfmRes.value.data?.success) {
            setRfmData(rfmRes.value.data.data || []);
          }

          if (insightsRes.status === "fulfilled" && insightsRes.value.data?.success) {
            setInsights(insightsRes.value.data.data);
          }
        }
      } catch (err) {
        console.error("Failed loading analytics hub data:", err);
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    loadAnalytics();
    return () => {
      isMounted = false;
    };
  }, [activeCompanyId, forecastDays, router]);

  // Sync tab with URL search parameter if changed
  useEffect(() => {
    const tab = searchParams.get("tab");
    if (tab && ["sales", "monthly", "rfm", "inventory", "cashflow"].includes(tab)) {
      setActiveTab(tab as any);
    }
  }, [searchParams]);

  // Inventory discount calculation
  const stockValuation = useMemo(() => {
    const stockCost = Number(insights?.stock_valuation || 0);
    const retailCost = Number(insights?.retail_valuation || stockCost * 1.3);
    const effectiveRetail = retailDiscount > 0 ? retailCost * (1 - retailDiscount / 100) : retailCost;
    const margin = Math.max(0, effectiveRetail - stockCost);
    const markupPct = stockCost > 0 ? ((margin / stockCost) * 100).toFixed(1) : "0";
    return { stockCost, retailCost, effectiveRetail, margin, markupPct };
  }, [insights, retailDiscount]);

  return (
    <DashboardLayout>
      <div className="space-y-6 pb-16 max-w-7xl mx-auto px-1 sm:px-2">
        {/* Header Banner */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border/40 pb-5">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl sm:text-2xl font-extrabold text-foreground tracking-tight">
                Analytics & Business Intelligence
              </h1>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
                AI Engine
              </span>
            </div>
            <p className="text-xs sm:text-sm text-muted-foreground mt-1">
              Multi-factor sales forecasting, monthly trajectory benchmarks, customer RFM tiers & inventory valuation.
            </p>
          </div>

          {/* Quick Info & Horizon Select */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-muted-foreground font-medium">Horizon:</span>
            <div className="flex items-center bg-muted/60 p-0.5 rounded-lg border border-border/40 text-xs">
              {[14, 30, 60, 90].map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setForecastDays(d)}
                  className={`px-2.5 py-1 rounded font-medium transition-colors cursor-pointer ${
                    forecastDays === d ? "bg-card text-foreground font-bold shadow-2xs" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {d}d
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Executive Tab Navigation */}
        <div className="flex items-center gap-1.5 border-b border-border/40 pb-2 overflow-x-auto no-scrollbar">
          <button
            type="button"
            onClick={() => setActiveTab("sales")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all flex items-center gap-1.5 cursor-pointer ${
              activeTab === "sales"
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5" />
            <span>Sales Forecast</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("monthly")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all flex items-center gap-1.5 cursor-pointer ${
              activeTab === "monthly"
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
            }`}
          >
            <Calendar className="w-3.5 h-3.5" />
            <span>Monthly Benchmark (MoM/YoY)</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("rfm")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all flex items-center gap-1.5 cursor-pointer ${
              activeTab === "rfm"
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
            }`}
          >
            <Users className="w-3.5 h-3.5" />
            <span>Customer RFM Tiers</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("inventory")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all flex items-center gap-1.5 cursor-pointer ${
              activeTab === "inventory"
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
            }`}
          >
            <Boxes className="w-3.5 h-3.5" />
            <span>Inventory Valuation & Margin</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("cashflow")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all flex items-center gap-1.5 cursor-pointer ${
              activeTab === "cashflow"
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
            }`}
          >
            <Landmark className="w-3.5 h-3.5" />
            <span>Cash Flow & Working Capital</span>
          </button>
        </div>

        {/* Tab 1: Sales & Predictive Forecast */}
        {activeTab === "sales" && (
          <div className="space-y-5 animate-in fade-in duration-200">
            {/* KPI Summary Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Projected {forecastDays}-Day Revenue
                </span>
                <div className="text-xl sm:text-2xl font-bold font-mono text-foreground">
                  ₹{(forecast?.projected_total || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                {forecast?.p10_total && forecast?.p90_total && (
                  <div className="text-[11px] text-muted-foreground font-mono">
                    Range: ₹{formatCurrencyShort(forecast.p10_total)} - ₹{formatCurrencyShort(forecast.p90_total)} (P10-P90)
                  </div>
                )}
              </div>

              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Projected Daily Average
                </span>
                <div className="text-xl sm:text-2xl font-bold font-mono text-foreground">
                  ₹{(forecast?.projected_daily_average || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-[11px] text-muted-foreground">
                  Historical Mean: ₹{(forecast?.historical_daily_average || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}/day
                </div>
              </div>

              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Growth Trajectory
                </span>
                <div className="flex items-center gap-2">
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-xs font-mono font-bold border ${
                      forecast?.trend_status === "Booming"
                        ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20"
                        : forecast?.trend_status === "Declining"
                        ? "bg-amber-500/10 text-amber-500 border-amber-500/20"
                        : "bg-blue-500/10 text-blue-500 border-blue-500/20"
                    }`}
                  >
                    {forecast?.trend_status || "Stable"}
                  </span>
                  <span className="text-xs text-muted-foreground font-medium">Confidence: {forecast?.confidence || "HIGH"}</span>
                </div>
                <div className="text-[11px] text-muted-foreground">
                  Based on {forecast?.sample_size_days || 0} active selling days
                </div>
              </div>

              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Realization Pipeline
                </span>
                <div className="text-xl sm:text-2xl font-bold font-mono text-purple-600 dark:text-purple-400">
                  ₹{(forecast?.factors_analyzed?.open_proforma_pipeline || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-[11px] text-muted-foreground">
                  Open proforma quotes converting in next 14 days
                </div>
              </div>
            </div>

            {/* Main Area Chart */}
            <div className="bg-card border border-border/50 rounded-xl p-5 shadow-2xs space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                    <span>Multi-Factor Sales Trajectory & Confidence Band</span>
                    <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Synthesizes day-of-week dispatch patterns, month-end GST rush, customer replenishment cadence, and physical stock guards.
                  </p>
                </div>
              </div>

              <div className="h-64 sm:h-72 w-full pt-2">
                {forecast?.daily_forecast && forecast.daily_forecast.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={forecast.daily_forecast} margin={{ top: 10, right: 15, left: -10, bottom: 0 }}>
                      <defs>
                        <linearGradient id="forecastHubGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.35} />
                          <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-border/40" vertical={false} />
                      <XAxis
                        dataKey="date"
                        stroke="currentColor"
                        className="text-muted-foreground"
                        fontSize={11}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={formatChartDate}
                      />
                      <YAxis
                        stroke="currentColor"
                        className="text-muted-foreground"
                        fontSize={11}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={formatCurrencyShort}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "var(--card)",
                          borderColor: "var(--border)",
                          borderRadius: "12px",
                          boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.3)",
                          fontSize: "12px",
                        }}
                        labelFormatter={(label: any) => {
                          try {
                            const d = new Date(label);
                            if (!isNaN(d.getTime())) {
                              return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
                            }
                          } catch {}
                          return label;
                        }}
                        formatter={(val: any) => [`₹${Number(val).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`, "Projected Sales"]}
                      />
                      <Area
                        type="monotone"
                        dataKey="projected_sales"
                        stroke="#8b5cf6"
                        strokeWidth={2.5}
                        fillOpacity={1}
                        fill="url(#forecastHubGrad)"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
                    No sales history available to project forecast.
                  </div>
                )}
              </div>

              {/* Factors Analyzed Breakdown */}
              <div className="pt-2 border-t border-border/40">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-2">
                  Active B2B Factors Evaluated:
                </span>
                <div className="flex flex-wrap gap-2">
                  <span
                    className={`text-xs px-2.5 py-1 rounded-full border font-medium ${
                      forecast?.factors_analyzed?.yoy_seasonality_applied
                        ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20"
                        : "bg-muted text-muted-foreground border-border/40"
                    }`}
                  >
                    {forecast?.factors_analyzed?.yoy_seasonality_applied
                      ? "✓ YoY Seasonality Active (From Past Records)"
                      : "YoY Seasonality Excluded (< 1 yr data)"}
                  </span>
                  <span className="text-xs px-2.5 py-1 rounded-full border font-medium bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20">
                    Day-of-Week Dispatch Pattern (Mon-Fri Peak)
                  </span>
                  <span className="text-xs px-2.5 py-1 rounded-full border font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20">
                    Month-End GST Surge ({forecast?.factors_analyzed?.month_end_surge_multiplier || 1.2}x)
                  </span>
                  {(forecast?.factors_analyzed?.repeat_buyers_modeled || 0) > 0 && (
                    <span className="text-xs px-2.5 py-1 rounded-full border font-medium bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/20">
                      {forecast.factors_analyzed.repeat_buyers_modeled} Repeat Customer Cycles Scheduled
                    </span>
                  )}
                  {forecast?.factors_analyzed?.stock_constraint_applied && (
                    <span className="text-xs px-2.5 py-1 rounded-full border font-medium bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20">
                      Physical Stock Fulfillment Constraint Active
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 2: Monthly Performance & Forecast Benchmark */}
        {activeTab === "monthly" && (
          <div className="space-y-5 animate-in fade-in duration-200">
            {/* Monthly Benchmark KPI Cards */}
            {forecast?.monthly_comparison && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Present Month Card */}
                <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-2">
                  <div className="flex items-center justify-between text-xs text-muted-foreground font-medium">
                    <span>{forecast.monthly_comparison.current_month.month_name} (Current)</span>
                    <span className="font-mono text-purple-600 dark:text-purple-400 font-bold">
                      {forecast.monthly_comparison.current_month.completion_pct}% Achieved
                    </span>
                  </div>
                  <div className="text-2xl font-bold font-mono text-foreground">
                    ₹{forecast.monthly_comparison.current_month.projected_month_total.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </div>
                  <div className="text-xs text-muted-foreground flex items-center justify-between">
                    <span>MTD Achieved: <strong className="text-foreground">₹{formatCurrencyShort(forecast.monthly_comparison.current_month.mtd_actual_sales)}</strong></span>
                    <span>+ Forecast: <strong className="text-purple-500">₹{formatCurrencyShort(forecast.monthly_comparison.current_month.remaining_projected_sales)}</strong></span>
                  </div>
                  {/* Progress Bar */}
                  <div className="w-full bg-muted h-2 rounded-full overflow-hidden flex">
                    <div
                      className="bg-blue-500 h-full transition-all duration-300"
                      style={{ width: `${Math.min(100, forecast.monthly_comparison.current_month.completion_pct)}%` }}
                    />
                    <div
                      className="bg-purple-500/60 h-full transition-all duration-300"
                      style={{ width: `${Math.max(0, 100 - forecast.monthly_comparison.current_month.completion_pct)}%` }}
                    />
                  </div>
                  <div className="text-[11px] text-muted-foreground pt-1">
                    {forecast.monthly_comparison.current_month.days_remaining} calendar days remaining in current month.
                  </div>
                </div>

                {/* vs Last Month Card */}
                <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-2">
                  <div className="flex items-center justify-between text-xs text-muted-foreground font-medium">
                    <span>vs Last Month ({forecast.monthly_comparison.previous_month.short_name || "M-1"})</span>
                    <span
                      className={`text-xs font-mono px-2 py-0.5 rounded-full font-bold ${
                        forecast.monthly_comparison.mom_comparison.pace_status === "BEATING_LAST_MONTH"
                          ? "bg-emerald-500/10 text-emerald-500 border border-emerald-500/20"
                          : forecast.monthly_comparison.mom_comparison.pace_status === "PACING_BEHIND"
                          ? "bg-amber-500/10 text-amber-500 border border-amber-500/20"
                          : "bg-muted text-muted-foreground border border-border/40"
                      }`}
                    >
                      {forecast.monthly_comparison.mom_comparison.percentage_change >= 0 ? "+" : ""}
                      {forecast.monthly_comparison.mom_comparison.percentage_change}%
                    </span>
                  </div>
                  <div className="text-2xl font-bold font-mono text-foreground">
                    Last: ₹{(forecast.monthly_comparison.previous_month.total_sales || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {forecast.monthly_comparison.mom_comparison.summary}
                  </div>
                  {forecast.monthly_comparison.mom_comparison.required_daily_to_match_last_month > 0 && (
                    <div className="text-xs text-purple-600 dark:text-purple-400 font-medium">
                      Target Run-Rate: ₹{formatCurrencyShort(forecast.monthly_comparison.mom_comparison.required_daily_to_match_last_month)}/day needed to surpass
                    </div>
                  )}
                </div>

                {/* Annual YoY Benchmark */}
                <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-2">
                  <div className="text-xs text-muted-foreground font-medium">
                    Annual Year-over-Year (YoY) Benchmark
                  </div>
                  {forecast.monthly_comparison.yoy_comparison?.available ? (
                    <>
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold text-foreground">
                          {forecast.monthly_comparison.yoy_comparison.prior_year_month_name}
                        </span>
                        <span
                          className={`text-xs font-mono px-2 py-0.5 rounded-full font-bold ${
                            forecast.monthly_comparison.yoy_comparison.percentage_change >= 0
                              ? "bg-emerald-500/10 text-emerald-500"
                              : "bg-rose-500/10 text-rose-500"
                          }`}
                        >
                          {forecast.monthly_comparison.yoy_comparison.percentage_change >= 0 ? "+" : ""}
                          {forecast.monthly_comparison.yoy_comparison.percentage_change}%
                        </span>
                      </div>
                      <div className="text-xl font-bold font-mono text-foreground">
                        Prior: ₹{(forecast.monthly_comparison.yoy_comparison.prior_year_sales || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </div>
                      <div className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                        {forecast.monthly_comparison.yoy_comparison.summary}
                      </div>
                    </>
                  ) : (
                    <div className="space-y-1.5 pt-2">
                      <span className="inline-block px-2.5 py-0.5 bg-muted rounded border border-border/40 text-xs text-muted-foreground font-medium">
                        YoY Excluded (&lt; 1 yr history)
                      </span>
                      <p className="text-xs text-muted-foreground">
                        Following strict business modeling rules, annual seasonal multipliers are only applied when verified prior-year historical records exist.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Comparative Multi-Month Stacked Bar Chart */}
            <div className="bg-card border border-border/50 rounded-xl p-5 shadow-2xs space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-foreground">
                    Historical Completed Months vs Present In-Progress & Forecast
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Blue bars represent confirmed historical actual sales. Purple stacked segments represent forecasted sales.
                  </p>
                </div>
              </div>

              <div className="h-64 sm:h-72 w-full pt-2">
                {forecast?.monthly_comparison?.historical_months_series && forecast.monthly_comparison.historical_months_series.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={forecast.monthly_comparison.historical_months_series}
                      margin={{ top: 10, right: 15, left: -10, bottom: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-border/40" vertical={false} />
                      <XAxis
                        dataKey="short_name"
                        stroke="currentColor"
                        className="text-muted-foreground"
                        fontSize={11}
                        tickLine={false}
                        axisLine={false}
                      />
                      <YAxis
                        stroke="currentColor"
                        className="text-muted-foreground"
                        fontSize={11}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={formatCurrencyShort}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "var(--card)",
                          borderColor: "var(--border)",
                          borderRadius: "12px",
                          boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.3)",
                          fontSize: "12px",
                        }}
                        formatter={(val: any, name?: any) => [
                          `₹${Number(val).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`,
                          name === "actual_sales" ? "Actual Sales" : "Forecasted Sales",
                        ]}
                        labelFormatter={(label: any, items?: any) => {
                          const item = (items as any)?.[0]?.payload;
                          return item ? item.month_label : label;
                        }}
                      />
                      <Legend
                        wrapperStyle={{ fontSize: "11px", paddingTop: "4px" }}
                        formatter={(value) => (value === "actual_sales" ? "Actual Sales" : "Forecasted Sales")}
                      />
                      <Bar dataKey="actual_sales" stackId="monthStack" fill="#3b82f6" radius={[0, 0, 0, 0]} />
                      <Bar dataKey="projected_sales" stackId="monthStack" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
                    No multi-month historical records available.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: Customer RFM Segmentation */}
        {activeTab === "rfm" && (
          <div className="space-y-5 animate-in fade-in duration-200">
            <div className="bg-card border border-border/50 rounded-xl p-5 shadow-2xs space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border/40 pb-3">
                <div>
                  <h3 className="text-base font-semibold text-foreground">
                    Customer Recency, Frequency & Monetary (RFM) Segmentation
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Clustered via scikit-learn machine learning based on purchase frequency, invoice spend, and recency of last order.
                  </p>
                </div>
                <span className="text-xs text-muted-foreground font-mono">
                  {rfmData.length} Active Customers Analyzed
                </span>
              </div>

              {rfmData.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-border/60 text-muted-foreground uppercase text-[10px] tracking-wider font-semibold">
                        <th className="py-2.5 px-3">Customer Party</th>
                        <th className="py-2.5 px-3 text-center">Tier Segment</th>
                        <th className="py-2.5 px-3 text-right">Recency (Days)</th>
                        <th className="py-2.5 px-3 text-right">Frequency (Orders)</th>
                        <th className="py-2.5 px-3 text-right">Total Revenue</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/30">
                      {rfmData.slice(0, 30).map((c: any, idx: number) => (
                        <tr key={idx} className="hover:bg-muted/40 transition-colors">
                          <td className="py-2.5 px-3 font-medium text-foreground">
                            {c.party_ledger__name || "Unknown Customer"}
                          </td>
                          <td className="py-2.5 px-3 text-center">
                            <span
                              className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                c.segment?.includes("High Value") || c.segment?.includes("VIP")
                                  ? "bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20"
                                  : c.segment?.includes("Medium")
                                  ? "bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20"
                                  : "bg-muted text-muted-foreground border border-border/40"
                              }`}
                            >
                              {c.segment || "Standard"}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono text-muted-foreground">
                            {c.recency}d ago
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono font-medium text-foreground">
                            {c.frequency} orders
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono font-bold text-foreground">
                            ₹{(c.monetary || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="py-12 text-center text-xs text-muted-foreground">
                  No sales invoices recorded yet for customer clustering.
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tab 4: Inventory Valuation & Margin Simulation */}
        {activeTab === "inventory" && (
          <div className="space-y-5 animate-in fade-in duration-200">
            {/* Inventory Valuation Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Total Stock Value (At Cost)
                </span>
                <div className="text-xl sm:text-2xl font-bold font-mono text-foreground">
                  ₹{stockValuation.stockCost.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-xs text-blue-600 dark:text-blue-400 font-medium">
                  {insights?.total_stock_qty || 0} physical units on hand
                </div>
              </div>

              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Catalog List Price (MRP)
                </span>
                <div className="text-xl sm:text-2xl font-bold font-mono text-foreground">
                  ₹{stockValuation.retailCost.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-xs text-muted-foreground">
                  Maximum potential revenue at full MRP
                </div>
              </div>

              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider">
                  Gross Profit Margin
                </span>
                <div className="text-xl sm:text-2xl font-bold font-mono text-emerald-600 dark:text-emerald-400">
                  ₹{stockValuation.margin.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-xs text-muted-foreground">
                  {stockValuation.markupPct}% markup over cost
                </div>
              </div>

              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Stock Health & Fulfillment
                </span>
                <div className="text-xl sm:text-2xl font-bold font-mono text-purple-600 dark:text-purple-400">
                  {insights?.in_stock_items || 0} / {insights?.catalog_items || 0} Active
                </div>
                <div className="text-xs text-muted-foreground">
                  Items ready for immediate dispatch
                </div>
              </div>
            </div>

            {/* Interactive Margin & Discount Simulator */}
            <div className="bg-card border border-border/50 rounded-xl p-5 shadow-2xs space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/40 pb-3">
                <div>
                  <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                    <Tag className="w-4 h-4 text-purple-500" />
                    <span>Interactive Wholesale Retail Discount & Margin Simulator</span>
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Simulate how trade discounts impact gross margins across the inventory catalog.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-muted-foreground">Discount Rate:</span>
                  <input
                    type="number"
                    min="0"
                    max="90"
                    value={retailDiscount || ""}
                    placeholder="0"
                    onChange={(e) => setRetailDiscount(Math.max(0, Math.min(90, parseFloat(e.target.value) || 0)))}
                    className="w-16 bg-muted border border-border/60 rounded-lg px-2.5 py-1 text-sm font-mono font-bold text-right outline-none focus:border-purple-500"
                  />
                  <span className="text-xs font-bold text-muted-foreground">%</span>
                  {retailDiscount > 0 && (
                    <button
                      onClick={() => setRetailDiscount(0)}
                      className="text-xs text-muted-foreground hover:text-foreground px-2 py-1 bg-muted rounded cursor-pointer"
                    >
                      Reset
                    </button>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-1">
                <div className="p-3.5 bg-muted/40 rounded-xl border border-border/40 space-y-1">
                  <span className="text-[11px] text-muted-foreground font-semibold uppercase">Effective Realizable Value</span>
                  <div className="text-lg font-bold font-mono text-foreground">
                    ₹{stockValuation.effectiveRetail.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    After {retailDiscount}% simulated discount
                  </div>
                </div>

                <div className="p-3.5 bg-muted/40 rounded-xl border border-border/40 space-y-1">
                  <span className="text-[11px] text-emerald-600 dark:text-emerald-400 font-semibold uppercase">Simulated Profit Margin</span>
                  <div className="text-lg font-bold font-mono text-emerald-600 dark:text-emerald-400">
                    ₹{stockValuation.margin.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    {stockValuation.markupPct}% markup over cost
                  </div>
                </div>

                <div className="p-3.5 bg-muted/40 rounded-xl border border-border/40 space-y-1">
                  <span className="text-[11px] text-purple-600 dark:text-purple-400 font-semibold uppercase">Cost Recovery Multiple</span>
                  <div className="text-lg font-bold font-mono text-purple-600 dark:text-purple-400">
                    {stockValuation.stockCost > 0 ? (stockValuation.effectiveRetail / stockValuation.stockCost).toFixed(2) : "1.00"}x
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    Returns per ₹1 invested in stock
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 5: Cash Flow & Working Capital */}
        {activeTab === "cashflow" && (
          <div className="space-y-5 animate-in fade-in duration-200">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Money to Collect (Debtors)
                </span>
                <div className="text-xl sm:text-2xl font-bold font-mono text-emerald-600 dark:text-emerald-400">
                  ₹{(insights?.money_to_collect || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-xs text-muted-foreground">
                  Pending customer receivables
                </div>
              </div>

              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Bills to Pay (Creditors)
                </span>
                <div className="text-xl sm:text-2xl font-bold font-mono text-rose-600 dark:text-rose-400">
                  ₹{(insights?.bills_to_pay || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-xs text-muted-foreground">
                  Vendor payables due
                </div>
              </div>

              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Available Liquid Cash & Bank
                </span>
                <div className="text-xl sm:text-2xl font-bold font-mono text-blue-600 dark:text-blue-400">
                  ₹{(insights?.cash_and_bank || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-xs text-muted-foreground">
                  Current bank balances + physical cash in hand
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}

export default function AnalyticsHubPage() {
  return (
    <React.Suspense
      fallback={
        <DashboardLayout>
          <div className="flex flex-col items-center justify-center min-h-[400px] space-y-3">
            <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
            <div className="text-xs text-muted-foreground font-medium">Loading analytics hub...</div>
          </div>
        </DashboardLayout>
      }
    >
      <AnalyticsHubContent />
    </React.Suspense>
  );
}
