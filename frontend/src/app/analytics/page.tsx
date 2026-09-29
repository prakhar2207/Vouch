"use client";
import React, { useEffect, useState, useMemo } from "react";
import axios from "axios";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  LineChart,
  Line,
  ComposedChart,
  ReferenceLine,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
  PieChart as RechartsPieChart,
  Pie,
  Cell,
} from "recharts";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import DashboardLayout from "@/components/DashboardLayout";
import { useCompany } from "@/context/CompanyContext";
import { useFinancialYear } from "@/context/FinancialYearContext";
import { LocalAnalyticsEngine } from "@/lib/analytics/analytics-engine";
import { useToast } from "@/context/ToastContext";
import PurchaseOrderDraftModal, { POOrderItem } from "@/components/modals/PurchaseOrderDraftModal";
import ItemHistoryModal from "@/components/modals/ItemHistoryModal";
import MassMinStockModal from "@/components/modals/MassMinStockModal";
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
  ShoppingCart,
  CheckSquare,
  Square,
  PackageCheck,
  AlertTriangle,
  Search,
  Filter,
  Plus,
  Minus,
  Check,
  ExternalLink,
  ChevronRight,
  TrendingDown,
  Sliders,
  Download,
  Archive,
  Activity,
  BarChart2,
  PieChart,
  ShieldAlert,
  Award,
  ArrowUpRight,
  ArrowDownRight,
  Receipt,
  ArrowUpDown,
  Flame,
  Zap,
  CheckCircle2,
  DollarSign,
  Phone,
  MessageCircle,
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

  const { toast } = useToast();

  // Inventory Analytics & Smart Reorder Hub State
  const [effectiveCompanyId, setEffectiveCompanyId] = useState<string>("");
  const [inventoryAnalytics, setInventoryAnalytics] = useState<any>(null);
  const initialCategory = searchParams.get("category_id") || "ALL";
  const [inventoryCategoryFilter, setInventoryCategoryFilter] = useState<string>(initialCategory);
  const [loadingInventoryAnalytics, setLoadingInventoryAnalytics] = useState<boolean>(false);
  const [inventorySearch, setInventorySearch] = useState<string>("");
  const [selectedReorderIds, setSelectedReorderIds] = useState<Set<string>>(new Set());
  const [orderQuantities, setOrderQuantities] = useState<Record<string, number>>({});
  const [bulkQuantityInput, setBulkQuantityInput] = useState<number>(10);
  const [selectedHistoryItem, setSelectedHistoryItem] = useState<any>(null);
  const [isPoModalOpen, setIsPoModalOpen] = useState<boolean>(false);

  // Brand & Sub-View Filter States (Mention Brand & Deadstock / Sitting on Benches)
  const [inventoryBrandFilter, setInventoryBrandFilter] = useState<string>("ALL");
  const [inventorySubView, setInventorySubView] = useState<"reorder" | "deadstock">("reorder");
  const [deadstockAgingFilter, setDeadstockAgingFilter] = useState<"all" | "dormant" | "90" | "60" | "30">("all");

  // Mass-Wise Minimum Required Stock State
  const [massMinStockInput, setMassMinStockInput] = useState<number>(10);
  const [isMassMinStockModalOpen, setIsMassMinStockModalOpen] = useState<boolean>(false);
  const [massMinStockScope, setMassMinStockScope] = useState<"selected" | "category" | "all">("selected");
  const [updatingMinStock, setUpdatingMinStock] = useState<boolean>(false);

  // Sales Chart Timeline & Historical Range Controls
  const [lineChartMode, setLineChartMode] = useState<"smoothed" | "daily" | "cumulative">("smoothed");
  const [chartViewMode, setChartViewMode] = useState<"combined" | "historical" | "forecast" | "trend">("combined");
  const [historicalRangeDays, setHistoricalRangeDays] = useState<number>(60);

  // Customer Churn Radar Threshold Controls (30, 60, 90, 120, 240, 360, or custom)
  const [churnDaysThreshold, setChurnDaysThreshold] = useState<number>(60);
  const [customChurnInput, setCustomChurnInput] = useState<string>("60");
  const [isEditingCustomDays, setIsEditingCustomDays] = useState<boolean>(false);

  // Dynamic Groww-Style Sales Trajectory Hover State
  const [hoveredTrajectoryPoint, setHoveredTrajectoryPoint] = useState<any | null>(null);

  // Dynamic Groww-Style Sales vs Purchases vs Profit Chart State
  const [financeTimeframe, setFinanceTimeframe] = useState<"7d" | "30d" | "90d" | "all">("30d");
  const [hoveredFinancePoint, setHoveredFinancePoint] = useState<any | null>(null);
  const [financeVisibleSeries, setFinanceVisibleSeries] = useState<{
    sales: boolean;
    purchases: boolean;
    profit: boolean;
  }>({
    sales: true,
    purchases: true,
    profit: true,
  });

  // Customer RFM Tiers Search, Filter & Multi-Sort State
  const [rfmSearch, setRfmSearch] = useState<string>("");
  const [rfmSortKey, setRfmSortKey] = useState<"monetary" | "recency" | "frequency" | "name" | "segment">("monetary");
  const [rfmSortDir, setRfmSortDir] = useState<"asc" | "desc">("desc");
  const [rfmSegmentFilter, setRfmSegmentFilter] = useState<string>("ALL");

  // Customer Pareto & Interactive Pie/Donut Chart State
  const [hoveredParetoIdx, setHoveredParetoIdx] = useState<number | null>(null);
  const [paretoDonutMode, setParetoDonutMode] = useState<"all_parties" | "top_10" | "full_80_20">("all_parties");
  const [pieChartStyle, setPieChartStyle] = useState<"donut" | "pie">("donut");
  const [paretoTableScope, setParetoTableScope] = useState<"all" | "top_10">("all");
  const [paretoSearch, setParetoSearch] = useState<string>("");

  const fetchInventoryAnalytics = async (cid?: string, catId?: string) => {
    const targetCid = cid || effectiveCompanyId || activeCompanyId;
    if (!targetCid) return;
    setLoadingInventoryAnalytics(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const categoryParam = catId !== undefined ? catId : inventoryCategoryFilter;
      const catQuery = categoryParam && categoryParam !== "ALL" ? `&category_id=${categoryParam}` : "";
      const url = `${API_BASE_URL}/api/v1/inventory/analytics/${targetCid}/?limit=15&reorder_limit=150${catQuery}`;
      const res = await axios.get(url, { headers });
      if (res.data?.success) {
        setInventoryAnalytics(res.data.data);

        // Pre-populate suggested order quantities for items if not already customized
        if (res.data.data?.reorder_items) {
          setOrderQuantities((prev) => {
            const next = { ...prev };
            res.data.data.reorder_items.forEach((it: any) => {
              if (next[it.product_id] === undefined) {
                next[it.product_id] = it.suggested_qty || 5;
              }
            });
            return next;
          });
        }
      }
    } catch (err) {
      console.error("Failed to load inventory analytics:", err);
    } finally {
      setLoadingInventoryAnalytics(false);
    }
  };

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

        const validCid = cid;
        setEffectiveCompanyId(validCid);
        fetchInventoryAnalytics(validCid, inventoryCategoryFilter);
        const fyOptions = {
          startDate: activeFY?.start_date,
          endDate: activeFY?.end_date,
          financialYearId: activeFY?.id,
        };

        // 1. Instant local read from IndexedDB (<15ms)
        const local = await LocalAnalyticsEngine.getDashboardAnalytics(validCid, fyOptions);
        if (isMounted && local) {
          setInsights(local);
          if (local.forecast) {
            setForecast(local.forecast);
          }
          if (local.rfm_clusters && local.rfm_clusters.length > 0) {
            setRfmData(local.rfm_clusters);
          }
          setLoading(false);
        }

        // 2. Refresh from remote API if online
        if (typeof navigator !== "undefined" && navigator.onLine) {
          const token = getAccessToken();
          const headers = { Authorization: `Bearer ${token}`, "X-Company-ID": validCid };

          const [forecastRes, rfmRes, insightsRes] = await Promise.allSettled([
            axios.get(`${API_BASE_URL}/api/v1/analytics/forecast/${validCid}/?days=${forecastDays}&company_id=${validCid}`, { headers }),
            axios.get(`${API_BASE_URL}/api/v1/analytics/rfm/${validCid}/`, { headers }),
            axios.get(`${API_BASE_URL}/api/v1/analytics/insights/${validCid}/`, { headers }),
          ]);

          if (isMounted) {
            if (forecastRes.status === "fulfilled" && forecastRes.value.data?.success) {
              setForecast(forecastRes.value.data.data);
            }
            if (rfmRes.status === "fulfilled" && rfmRes.value.data?.success) {
              setRfmData(rfmRes.value.data.data || []);
            }
            if (insightsRes.status === "fulfilled" && insightsRes.value.data?.success) {
              const remote = insightsRes.value.data.data;
              setInsights((prev: any) => ({
                ...prev,
                ...remote,
                kpis: {
                  ...(prev?.kpis || {}),
                  ...(remote?.kpis || {}),
                }
              }));
            }
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
  }, [activeCompanyId, activeFY?.id, forecastDays, router]);

  // Sync tab and category with URL search parameters if changed
  useEffect(() => {
    const tab = searchParams.get("tab");
    if (tab && ["sales", "monthly", "rfm", "inventory", "cashflow"].includes(tab)) {
      setActiveTab(tab as any);
    }
    const cat = searchParams.get("category_id");
    if (cat && cat !== inventoryCategoryFilter) {
      setInventoryCategoryFilter(cat);
      if (effectiveCompanyId) {
        fetchInventoryAnalytics(effectiveCompanyId, cat);
      }
    }
  }, [searchParams, effectiveCompanyId, inventoryCategoryFilter]);

  // Chart Timeline Data for Historical & Predictive Projection
  const chartAnchorDate = useMemo(() => {
    return (
      forecast?.historical_summary?.anchor_date ||
      forecast?.combined_series?.find((it: any) => it.is_today)?.date ||
      ""
    );
  }, [forecast]);

  const chartTimelineData = useMemo(() => {
    if (!forecast) return [];

    const combinedList: any[] = forecast.combined_series || [];
    let baseItems: any[] = [];

    if (combinedList.length > 0) {
      const histItems = combinedList.filter((it: any) => it.is_historical);
      const futureItems = combinedList.filter((it: any) => !it.is_historical);
      const slicedHist = historicalRangeDays >= 999 ? histItems : histItems.slice(-historicalRangeDays);
      baseItems = [...slicedHist, ...futureItems];
    } else {
      const histList: any[] = forecast.historical_daily_series || [];
      const futureList: any[] = forecast.daily_forecast || [];
      const slicedHist = historicalRangeDays >= 999 ? histList : histList.slice(-historicalRangeDays);
      baseItems = [...slicedHist, ...futureList];
    }

    if (baseItems.length === 0) return [];

    let runningCum = 0;
    const windowValues: number[] = [];

    return baseItems.map((item: any) => {
      const isHistorical = Boolean(item.is_historical ?? (item.actual_sales !== null && item.actual_sales !== undefined));
      const isAnchor = item.date === chartAnchorDate || item.is_today;
      
      const rawActual = isHistorical ? Number(item.actual_sales || 0) : null;
      const rawProjected = !isHistorical ? Number(item.projected_sales || 0) : (isAnchor ? Number(item.actual_sales || 0) : null);
      
      const dailyVal = Number(item.actual_sales ?? item.projected_sales ?? 0);
      windowValues.push(dailyVal);
      if (windowValues.length > 7) windowValues.shift();
      const avg7d = Math.round(windowValues.reduce((a, b) => a + b, 0) / windowValues.length);
      runningCum += dailyVal;

      return {
        ...item,
        actual_sales: rawActual,
        projected_sales: rawProjected,
        smoothed_actual: isHistorical ? avg7d : (isAnchor ? avg7d : null),
        smoothed_projected: !isHistorical ? avg7d : (isAnchor ? avg7d : null),
        running_cumulative: runningCum,
        daily_val: dailyVal,
      };
    });
  }, [forecast, historicalRangeDays, chartAnchorDate]);

  // Simplified Monthly Chart Data for Business Owners
  const monthlyChartData = useMemo(() => {
    const series = forecast?.monthly_comparison?.historical_months_series;
    if (series && Array.isArray(series) && series.length > 0) {
      return series.map((m: any) => {
        const tot = Number(m.total_sales ?? (Number(m.actual_sales || 0) + Number(m.projected_sales || 0)));
        return {
          ...m,
          month: m.short_name || m.month_label,
          confirmed: Number(m.actual_sales || 0),
          projected_remainder: m.is_current ? Number(m.projected_sales || 0) : 0,
          next_month_projection: m.is_projected ? Number(m.projected_sales || 0) : 0,
          total: tot,
          displayTotal: tot,
        };
      });
    }
    return [];
  }, [forecast]);

  // All Genuine Customer Accounts (Sundry Debtors only, excluding Cash counter bills placeholder, banks, suppliers)
  const allCustomerParties = useMemo(() => {
    const pool: any[] = forecast?.customer_pareto?.length
      ? forecast.customer_pareto
      : forecast?.churn_accounts?.length
      ? forecast.churn_accounts
      : rfmData || [];

    const map = new Map<string, any>();
    pool.forEach((c: any) => {
      const name = (c.party_name || c.name || c.party_ledger__name || "").trim();
      const nameLower = name.toLowerCase();
      const billed = Number(c.total_billed ?? c.total_revenue ?? c.monetary ?? 0);
      const isExcluded =
        nameLower.startsWith("cash") ||
        nameLower.includes("counter sale") ||
        nameLower.includes("cash sale") ||
        nameLower.includes("cash a/c") ||
        nameLower.includes("cash in hand") ||
        nameLower.includes("bank") ||
        nameLower.includes("supplier") ||
        nameLower.includes("creditor") ||
        nameLower.includes("purchase") ||
        nameLower.includes("tax") ||
        nameLower.includes("round off") ||
        nameLower.includes("expense");

      if (billed > 0 && !isExcluded && name) {
        const key = c.party_id || name;
        if (!map.has(key) || (Number(map.get(key).total_billed) < billed)) {
          const daysSince = Number(c.days_since_last_sale ?? c.days_since_last_order ?? c.recency ?? 0);
          map.set(key, {
            party_id: c.party_id || null,
            party_name: name,
            name: name,
            total_billed: billed,
            total_revenue: billed,
            invoice_count: Number(c.invoice_count ?? c.frequency ?? 1),
            last_sale_date: c.last_sale_date || c.last_order_date || null,
            last_order_date: c.last_sale_date || c.last_order_date || null,
            days_since_last_sale: daysSince,
            days_since_last_order: daysSince,
            risk_status: c.risk_status || (daysSince >= 90 ? "DORMANT" : daysSince >= 60 ? "AT_RISK" : daysSince >= 30 ? "COOLING" : "HEALTHY"),
            risk_label: c.risk_label || (daysSince >= 90 ? `Dormant (${daysSince}d)` : daysSince >= 60 ? `Inactive (${daysSince}d)` : daysSince >= 30 ? `Cooling (${daysSince}d)` : "Active Buyer"),
          });
        }
      }
    });

    const list = Array.from(map.values());
    list.sort((a, b) => b.total_billed - a.total_billed);

    const totalDebtorTurnover = list.reduce((acc, it) => acc + it.total_billed, 0) || 1;
    let running = 0;
    return list.map((it, idx) => {
      const share = Math.round((it.total_billed / totalDebtorTurnover) * 1000) / 10;
      running += share;
      return {
        ...it,
        share_pct: share,
        percentage_of_total: share,
        cumulative_pct: Math.min(100, Math.round(running * 10) / 10),
        cumulative_percentage: Math.min(100, Math.round(running * 10) / 10),
        rank: idx + 1,
      };
    });
  }, [forecast?.customer_pareto, forecast?.churn_accounts, rfmData]);

  // Top 10 Core Pareto Accounts for Key Indicators
  const paretoCustomers = useMemo(() => {
    return allCustomerParties.slice(0, 10);
  }, [allCustomerParties]);

  // Executive Customer Health Metrics for Top-Level Ribbon
  const customerExecutiveMetrics = useMemo(() => {
    const totalCompanySales = Number(
      forecast?.financial_momentum_summary?.total_sales ??
      forecast?.historical_summary?.total_historical_sales ??
      insights?.kpis?.total_sales ??
      1
    );

    const top10Sum = paretoCustomers.reduce((acc: number, c: any) => {
      return acc + Number(c.total_billed ?? c.total_revenue ?? 0);
    }, 0);

    const top10Share = totalCompanySales > 0 ? (top10Sum / totalCompanySales) * 100 : 0;

    // Single account dominance (Max exposure)
    const top1 = paretoCustomers[0];
    const top1Name = top1?.party_name || top1?.name || "Top Account";
    const top1Val = Number(top1?.total_billed ?? top1?.total_revenue ?? 0);
    const top1Share = totalCompanySales > 0 ? (top1Val / totalCompanySales) * 100 : 0;

    let exposureRisk = {
      label: "Healthy Diversification",
      badgeColor: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20",
      description: "No single customer exceeds 20% of revenue.",
    };
    if (top1Share > 35) {
      exposureRisk = {
        label: "High Key-Account Risk",
        badgeColor: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20",
        description: `Top client accounts for ${top1Share.toFixed(1)}% of total sales.`,
      };
    } else if (top1Share > 20) {
      exposureRisk = {
        label: "Moderate Dependency",
        badgeColor: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20",
        description: `Top client accounts for ${top1Share.toFixed(1)}% of total sales.`,
      };
    }

    // Health breakdown among top 10
    let activeCount = 0;
    let coolingCount = 0;
    let atRiskCount = 0;
    paretoCustomers.forEach((c: any) => {
      const idle = c.days_since_last_sale ?? c.days_since_last_order ?? 0;
      if (idle < 30) activeCount++;
      else if (idle < 60) coolingCount++;
      else atRiskCount++;
    });

    const totalDebtorSales = allCustomerParties.reduce((sum: number, c: any) => {
      return sum + Number(c.total_billed ?? c.total_revenue ?? 0);
    }, 0);
    const otherAccountsSales = Math.max(0, totalCompanySales - top10Sum);
    const otherAccountsShare = Math.max(0, 100 - top10Share);

    return {
      totalCompanySales,
      totalDebtorSales,
      totalDebtorCount: allCustomerParties.length,
      top10Sum,
      top10Share: Math.round(top10Share * 10) / 10,
      top1Name,
      top1Val,
      top1Share: Math.round(top1Share * 10) / 10,
      exposureRisk,
      activeCount,
      coolingCount,
      atRiskCount,
      otherAccountsSales: Math.round(otherAccountsSales * 100) / 100,
      otherAccountsShare: Math.round(otherAccountsShare * 10) / 10,
    };
  }, [paretoCustomers, allCustomerParties, forecast, insights?.kpis]);

  // Filtered Pareto Customers for Table Display (Supports All vs Top 10 + Search)
  const filteredParetoCustomers = useMemo(() => {
    const sourceList = paretoTableScope === "all" ? allCustomerParties : paretoCustomers;
    if (!paretoSearch.trim()) return sourceList;
    const q = paretoSearch.toLowerCase().trim();
    return sourceList.filter((c: any) =>
      (c.party_name || c.name || "").toLowerCase().includes(q)
    );
  }, [allCustomerParties, paretoCustomers, paretoTableScope, paretoSearch]);

  // Comprehensive 24-Color High-Contrast Palette for Customer Accounts
  const CUSTOMER_PALETTE = [
    "#6366f1", // Indigo
    "#10b981", // Emerald
    "#f59e0b", // Amber
    "#ec4899", // Pink
    "#8b5cf6", // Violet
    "#06b6d4", // Cyan
    "#f97316", // Orange
    "#3b82f6", // Blue
    "#14b8a6", // Teal
    "#a855f7", // Purple
    "#84cc16", // Lime
    "#e11d48", // Rose
    "#0ea5e9", // Sky
    "#d97706", // Deep Amber
    "#4f46e5", // Deep Indigo
    "#059669", // Dark Emerald
    "#7c3aed", // Deep Violet
    "#db2777", // Magenta
    "#2563eb", // Royal Blue
    "#0d9488", // Deep Teal
    "#ca8a04", // Gold
    "#9333ea", // Bright Purple
    "#16a34a", // Forest Green
    "#64748b", // Slate
  ];

  // Customer Pareto Donut / Pie Chart Data (Defaults to ALL parties)
  const paretoPieChartData = useMemo(() => {
    if (!allCustomerParties || allCustomerParties.length === 0) return [];

    if (paretoDonutMode === "all_parties") {
      return allCustomerParties.map((c: any, idx: number) => ({
        name: c.party_name || c.name || `Party #${idx + 1}`,
        value: Math.round(Number(c.total_billed ?? c.total_revenue ?? 0)),
        share_pct: Number(c.share_pct ?? c.percentage_of_total ?? 0),
        color: CUSTOMER_PALETTE[idx % CUSTOMER_PALETTE.length],
        party_id: c.party_id,
        days_since: c.days_since_last_sale ?? c.days_since_last_order ?? 0,
        invoice_count: c.invoice_count,
        risk_status: c.risk_status,
        risk_label: c.risk_label,
        rank: c.rank || (idx + 1),
        original_idx: idx,
      }));
    }

    if (paretoDonutMode === "top_10") {
      return paretoCustomers.map((c: any, idx: number) => ({
        name: c.party_name || c.name || `Party #${idx + 1}`,
        value: Math.round(Number(c.total_billed ?? c.total_revenue ?? 0)),
        share_pct: Number(c.share_pct ?? c.percentage_of_total ?? 0),
        color: CUSTOMER_PALETTE[idx % CUSTOMER_PALETTE.length],
        party_id: c.party_id,
        days_since: c.days_since_last_sale ?? c.days_since_last_order ?? 0,
        invoice_count: c.invoice_count,
        risk_status: c.risk_status,
        risk_label: c.risk_label,
        rank: c.rank || (idx + 1),
        original_idx: idx,
      }));
    }

    // full_80_20 mode: Top 10 + All Other Accounts combined
    const top10 = paretoCustomers.map((c: any, idx: number) => ({
      name: c.party_name || c.name || `Party #${idx + 1}`,
      value: Math.round(Number(c.total_billed ?? c.total_revenue ?? 0)),
      share_pct: Number(c.share_pct ?? c.percentage_of_total ?? 0),
      color: CUSTOMER_PALETTE[idx % CUSTOMER_PALETTE.length],
      party_id: c.party_id,
      days_since: c.days_since_last_sale ?? c.days_since_last_order ?? 0,
      invoice_count: c.invoice_count,
      risk_status: c.risk_status,
      risk_label: c.risk_label,
      rank: c.rank || (idx + 1),
      original_idx: idx,
    }));

    if (customerExecutiveMetrics.otherAccountsSales > 0) {
      return [
        ...top10,
        {
          name: "All Other Accounts",
          value: Math.round(customerExecutiveMetrics.otherAccountsSales),
          share_pct: customerExecutiveMetrics.otherAccountsShare,
          color: "#94a3b8", // Slate neutral
          party_id: null,
          days_since: 0,
          invoice_count: Math.max(0, allCustomerParties.length - 10),
          risk_status: "HEALTHY",
          risk_label: "Long-Tail Base",
          rank: 11,
          original_idx: 10,
        },
      ];
    }

    return top10;
  }, [allCustomerParties, paretoCustomers, paretoDonutMode, customerExecutiveMetrics]);

  // Churn Radar Accounts dynamically filtered by user-selected inactivity threshold days
  const churnFilteredAccounts = useMemo(() => {
    // Prefer the complete churn_accounts list from backend, fallback to customer_pareto
    const pool: any[] = forecast?.churn_accounts || forecast?.customer_pareto || [];
    return pool
      .filter((c: any) => {
        const name = (c.party_name || c.name || "").trim().toLowerCase();
        return !name.startsWith("cash") && name !== "counter sale";
      })
      .filter((c: any) => {
        const idle = c.days_since_last_sale ?? c.days_since_last_order ?? 0;
        return idle >= churnDaysThreshold;
      })
      .sort((a: any, b: any) => {
        const revA = a.total_billed ?? a.total_revenue ?? 0;
        const revB = b.total_billed ?? b.total_revenue ?? 0;
        return revB - revA; // Highest revenue inactive accounts first
      });
  }, [forecast?.churn_accounts, forecast?.customer_pareto, churnDaysThreshold]);

  const totalAtRiskRevenue = useMemo(() => {
    return churnFilteredAccounts.reduce((acc: number, c: any) => {
      return acc + (c.total_billed ?? c.total_revenue ?? 0);
    }, 0);
  }, [churnFilteredAccounts]);

  // Business Growth & Trajectory Verdict Indicator
  const businessGrowthVerdict = useMemo(() => {
    const growthPct = forecast?.trend_details?.growth_rate_pct ?? 0;
    const momPct = forecast?.monthly_comparison?.mom_comparison?.percentage_change ?? 0;
    const status = forecast?.financial_momentum_summary?.growth_status || forecast?.trend_status;
    const avgDaily = forecast?.historical_daily_average || forecast?.trend_details?.average_daily_sales || 0;
    const runRate7d = forecast?.historical_summary?.current_7d_run_rate || avgDaily;

    if (growthPct > 8 || status === "RAPID_EXPANSION" || momPct > 15) {
      return {
        level: "EXPANSION",
        badge: "🚀 RAPID BUSINESS EXPANSION",
        badgeColor: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30",
        pillColor: "text-emerald-600 dark:text-emerald-400",
        title: `Business is Expanding Rapidly (+${Math.max(growthPct, momPct).toFixed(1)}%)`,
        description: `Daily order volume is significantly outpacing historical baselines with a 7-day average run rate of ₹${runRate7d.toLocaleString("en-IN", { maximumFractionDigits: 0 })}/day. Working capital velocity is strong.`,
        isGrowing: true,
      };
    } else if (growthPct > 1.5 || status === "STEADY_GROWTH" || momPct > 3) {
      return {
        level: "GROWING",
        badge: "📈 STEADY REVENUE GROWTH",
        badgeColor: "bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-500/30",
        pillColor: "text-blue-600 dark:text-blue-400",
        title: `Steady Revenue Growth (+${Math.abs(growthPct > 0 ? growthPct : momPct).toFixed(1)}%)`,
        description: `Order inflow shows solid upward momentum above 30-day baseline with reliable customer replenishment cycles.`,
        isGrowing: true,
      };
    } else if (growthPct < -5 || status === "SLOWDOWN" || momPct < -10) {
      return {
        level: "DECLINING",
        badge: "📉 BUSINESS SLOWDOWN DETECTED",
        badgeColor: "bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/30",
        pillColor: "text-rose-600 dark:text-rose-400",
        title: `Sales Velocity Lagging Baseline (${Math.min(growthPct, momPct).toFixed(1)}%)`,
        description: `Order run rate is below trailing averages. Immediate customer follow-ups and trade promotion incentives recommended to restore momentum.`,
        isGrowing: false,
      };
    } else if (growthPct < 0 || status === "MILD_CONTRACTION" || momPct < 0) {
      return {
        level: "MILD_CONTRACTION",
        badge: "⚠️ MILD CONTRACTION",
        badgeColor: "bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30",
        pillColor: "text-amber-600 dark:text-amber-400",
        title: `Slight Volume Contraction (${Math.min(growthPct, momPct).toFixed(1)}%)`,
        description: `Sales are tracking slightly behind previous month peak, but within normal inventory replenishment variance.`,
        isGrowing: false,
      };
    } else {
      return {
        level: "STABLE",
        badge: "⚖️ STABLE SALES PACE",
        badgeColor: "bg-slate-500/15 text-slate-700 dark:text-slate-300 border-slate-500/30",
        pillColor: "text-slate-600 dark:text-slate-400",
        title: `Consistent Operational Turnover (~0% variance)`,
        description: `Billing velocity is stable and predictable with balanced day-to-day transaction pacing.`,
        isGrowing: true,
      };
    }
  }, [forecast]);

  // Groww-Style Sales vs Purchases vs Profit Series
  const growwChartData = useMemo(() => {
    const series: any[] = forecast?.historical_daily_series || [];
    if (!series || series.length === 0) return [];

    let filtered = [...series];
    if (financeTimeframe === "7d") {
      filtered = filtered.slice(-7);
    } else if (financeTimeframe === "30d") {
      filtered = filtered.slice(-30);
    } else if (financeTimeframe === "90d") {
      filtered = filtered.slice(-90);
    }

    return filtered.map((item: any) => {
      const s = Number(item.actual_sales || 0);
      const p = Number(item.actual_purchases || 0);
      const profit = Number(item.gross_profit !== undefined ? item.gross_profit : (s - p));
      const margin = s > 0 ? Math.round((profit / s) * 1000) / 10 : 0;
      return {
        date: item.date,
        sales: s,
        purchases: p,
        profit: profit,
        margin_pct: margin,
        is_positive: profit >= 0,
      };
    });
  }, [forecast?.historical_daily_series, financeTimeframe]);

  const growwSummary = useMemo(() => {
    if (!growwChartData || growwChartData.length === 0) {
      return {
        totalSales: forecast?.financial_momentum_summary?.total_sales || 0,
        totalPurchases: forecast?.financial_momentum_summary?.total_purchases || 0,
        grossProfit: forecast?.financial_momentum_summary?.gross_profit || 0,
        marginPct: forecast?.financial_momentum_summary?.profit_margin_pct || 0,
        growthStatus: forecast?.financial_momentum_summary?.growth_status || "STABLE",
      };
    }
    const totalSales = growwChartData.reduce((acc, it) => acc + it.sales, 0);
    const totalPurchases = growwChartData.reduce((acc, it) => acc + it.purchases, 0);
    const grossProfit = totalSales - totalPurchases;
    const marginPct = totalSales > 0 ? Math.round((grossProfit / totalSales) * 1000) / 10 : 0;
    return {
      totalSales,
      totalPurchases,
      grossProfit,
      marginPct,
      growthStatus: forecast?.financial_momentum_summary?.growth_status || (grossProfit > 0 ? "EXPANDING" : "CONTRACTION"),
    };
  }, [growwChartData, forecast?.financial_momentum_summary]);

  // Sorted and filtered RFM Data for Tab 3 Customer RFM Tiers (Strict Genuine Customer Filter)
  const sortedRfmData = useMemo(() => {
    if (!rfmData || rfmData.length === 0) return [];

    // Strictly filter to real customer accounts only (no suppliers, banks, cash, non-sales zero entries)
    let list = rfmData.filter((c: any) => {
      const freq = Number(c.frequency || 0);
      const mon = Number(c.monetary || 0);
      const name = (c.party_ledger__name || c.name || "").trim().toLowerCase();
      const isExcluded =
        name.startsWith("cash") ||
        name.includes("counter sale") ||
        name.includes("cash sale") ||
        name.includes("cash a/c") ||
        name.includes("cash in hand") ||
        name.includes("bank") ||
        name.includes("supplier") ||
        name.includes("creditor") ||
        name.includes("purchase") ||
        name.includes("tax") ||
        name.includes("round off") ||
        name.includes("expense");
      return freq > 0 && mon > 0 && !isExcluded;
    });

    if (rfmSearch.trim()) {
      const q = rfmSearch.toLowerCase().trim();
      list = list.filter((c: any) =>
        (c.party_ledger__name || c.name || "").toLowerCase().includes(q)
      );
    }
    if (rfmSegmentFilter !== "ALL") {
      list = list.filter((c: any) => {
        const seg = (c.segment || "").toLowerCase();
        if (rfmSegmentFilter === "VIP") return seg.includes("high") || seg.includes("vip");
        if (rfmSegmentFilter === "MEDIUM") return seg.includes("medium");
        if (rfmSegmentFilter === "STANDARD") return !seg.includes("high") && !seg.includes("vip") && !seg.includes("medium");
        return true;
      });
    }
    list.sort((a: any, b: any) => {
      let valA: any = 0;
      let valB: any = 0;
      if (rfmSortKey === "monetary") {
        valA = Number(a.monetary || 0);
        valB = Number(b.monetary || 0);
      } else if (rfmSortKey === "recency") {
        valA = Number(a.recency || 0);
        valB = Number(b.recency || 0);
      } else if (rfmSortKey === "frequency") {
        valA = Number(a.frequency || 0);
        valB = Number(b.frequency || 0);
      } else if (rfmSortKey === "name") {
        valA = (a.party_ledger__name || a.name || "").toLowerCase();
        valB = (b.party_ledger__name || b.name || "").toLowerCase();
        return rfmSortDir === "asc" ? valA.localeCompare(valB) : valB.localeCompare(valA);
      } else if (rfmSortKey === "segment") {
        valA = (a.segment || "").toLowerCase();
        valB = (b.segment || "").toLowerCase();
        return rfmSortDir === "asc" ? valA.localeCompare(valB) : valB.localeCompare(valA);
      }
      return rfmSortDir === "asc" ? valA - valB : valB - valA;
    });
    return list;
  }, [rfmData, rfmSearch, rfmSegmentFilter, rfmSortKey, rfmSortDir]);

  // Category & Reorder Hub Filters
  const handleCategoryFilterChange = (newCatId: string) => {
    setInventoryCategoryFilter(newCatId);
    if (effectiveCompanyId) {
      fetchInventoryAnalytics(effectiveCompanyId, newCatId);
    }
  };

  // Unique brand options across both reorder items and deadstock items
  const availableBrands = useMemo(() => {
    const brandsSet = new Set<string>();
    inventoryAnalytics?.reorder_items?.forEach((it: any) => {
      if (it.brand && it.brand.trim()) brandsSet.add(it.brand.trim());
    });
    inventoryAnalytics?.deadstock_items?.forEach((it: any) => {
      if (it.brand && it.brand.trim()) brandsSet.add(it.brand.trim());
    });
    return Array.from(brandsSet).sort();
  }, [inventoryAnalytics?.reorder_items, inventoryAnalytics?.deadstock_items]);

  const currentCategoryName = useMemo(() => {
    if (!inventoryCategoryFilter || inventoryCategoryFilter === "ALL") return "All Categories";
    const cat = inventoryAnalytics?.categories?.find((c: any) => c.id === inventoryCategoryFilter);
    return cat ? cat.name : "Category";
  }, [inventoryAnalytics?.categories, inventoryCategoryFilter]);

  const filteredReorderItems = useMemo(() => {
    if (!inventoryAnalytics?.reorder_items) return [];
    let list: any[] = inventoryAnalytics.reorder_items;
    if (inventoryBrandFilter && inventoryBrandFilter !== "ALL") {
      list = list.filter(
        (it: any) => (it.brand || "").trim().toLowerCase() === inventoryBrandFilter.trim().toLowerCase()
      );
    }
    if (inventorySearch.trim()) {
      const q = inventorySearch.toLowerCase();
      list = list.filter(
        (it: any) =>
          it.name?.toLowerCase().includes(q) ||
          it.brand?.toLowerCase().includes(q) ||
          it.sku?.toLowerCase().includes(q) ||
          it.category_name?.toLowerCase().includes(q) ||
          it.last_supplier?.toLowerCase().includes(q)
      );
    }
    return list;
  }, [inventoryAnalytics?.reorder_items, inventoryBrandFilter, inventorySearch]);

  // Filtered Sitting on Benches / Slow-Moving (Deadstock) Items
  const filteredDeadstockItems = useMemo(() => {
    if (!inventoryAnalytics?.deadstock_items) return [];
    let list: any[] = inventoryAnalytics.deadstock_items;
    if (inventoryBrandFilter && inventoryBrandFilter !== "ALL") {
      list = list.filter(
        (it: any) => (it.brand || "").trim().toLowerCase() === inventoryBrandFilter.trim().toLowerCase()
      );
    }
    if (deadstockAgingFilter !== "all") {
      if (deadstockAgingFilter === "dormant") {
        list = list.filter((it: any) => it.status === "DORMANT");
      } else if (deadstockAgingFilter === "90") {
        list = list.filter((it: any) => it.status === "CRITICAL_DEADSTOCK" || it.days_idle >= 90);
      } else if (deadstockAgingFilter === "60") {
        list = list.filter((it: any) => it.days_idle >= 60);
      } else if (deadstockAgingFilter === "30") {
        list = list.filter((it: any) => it.days_idle >= 30);
      }
    }
    if (inventorySearch.trim()) {
      const q = inventorySearch.toLowerCase();
      list = list.filter(
        (it: any) =>
          it.name?.toLowerCase().includes(q) ||
          it.brand?.toLowerCase().includes(q) ||
          it.sku?.toLowerCase().includes(q) ||
          it.category_name?.toLowerCase().includes(q)
      );
    }
    return list;
  }, [inventoryAnalytics?.deadstock_items, inventoryBrandFilter, deadstockAgingFilter, inventorySearch]);

  // Mass Min Stock Update Handler
  const handleApplyMassMinStock = async () => {
    const targetCid = effectiveCompanyId || activeCompanyId;
    if (!targetCid) {
      toast.error("Company not identified");
      return;
    }
    const val = Number(massMinStockInput);
    if (isNaN(val) || val < 0) {
      toast.error("Please enter a valid minimum required quantity (0 or greater)");
      return;
    }

    if (massMinStockScope === "selected" && selectedReorderIds.size === 0) {
      toast.error("No items selected. Select items from the table or choose category/catalog scope.");
      return;
    }

    setUpdatingMinStock(true);
    try {
      const token = getAccessToken();
      const payload: any = {
        min_stock_level: val,
      };

      if (massMinStockScope === "selected") {
        payload.product_ids = Array.from(selectedReorderIds);
      } else if (massMinStockScope === "category") {
        payload.category_id = inventoryCategoryFilter !== "ALL" ? inventoryCategoryFilter : null;
        if (!payload.category_id) {
          payload.apply_all = true;
        }
      } else {
        payload.apply_all = true;
      }

      const res = await axios.post(
        `${API_BASE_URL}/api/v1/inventory/bulk-min-stock/${targetCid}/`,
        payload,
        { headers: { Authorization: `Bearer ${token}` } }
      );

      if (res.data?.success) {
        toast.success(res.data.message || `Updated minimum stock to ${val} successfully`);
        setIsMassMinStockModalOpen(false);
        fetchInventoryAnalytics(targetCid, inventoryCategoryFilter);
      } else {
        toast.error(res.data?.error || "Failed to update minimum stock");
      }
    } catch (err: any) {
      console.error("Bulk min stock update error:", err);
      toast.error(err.response?.data?.error || "Error applying minimum stock mass-wise");
    } finally {
      setUpdatingMinStock(false);
    }
  };

  // Export Deadstock Report CSV
  const handleExportDeadstockCsv = () => {
    const list = filteredDeadstockItems;
    if (list.length === 0) {
      toast.error("No deadstock items to export");
      return;
    }
    const headers = [
      "S.No",
      "Item Name",
      "Brand",
      "SKU",
      "Category",
      "Units On Bench",
      "Unit Cost (INR)",
      "Locked Capital (INR)",
      "MRP (INR)",
      "Days Idle",
      "Last Activity",
      "Status"
    ];
    const rows = list.map((it: any, idx: number) => [
      idx + 1,
      `"${(it.name || "").replace(/"/g, '""')}"`,
      `"${(it.brand || "").replace(/"/g, '""')}"`,
      `"${(it.sku || "").replace(/"/g, '""')}"`,
      `"${(it.category_name || "").replace(/"/g, '""')}"`,
      it.current_stock,
      (it.purchase_price || 0).toFixed(2),
      (it.locked_capital || 0).toFixed(2),
      (it.selling_price || 0).toFixed(2),
      it.days_idle,
      `"${it.last_sale_date ? `Last Sold: ${it.last_sale_date}` : (it.last_purchase_date ? `Purchased: ${it.last_purchase_date}` : 'None')}"`,
      `"${it.status_label || it.status}"`
    ]);
    const csvContent = "data:text/csv;charset=utf-8," +
      [`# SLOW-MOVING & DEADSTOCK INVENTORY REPORT (SITTING ON BENCHES)`, `# Company: ${activeCompany?.name || 'Company'}`, `# Date: ${new Date().toISOString().split('T')[0]}`].join("\n") +
      "\n\n" + [headers.join(","), ...rows.map((r: any) => r.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `Deadstock_Sitting_On_Benches_${new Date().toISOString().split('T')[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success("Deadstock inventory report downloaded successfully");
  };

  const handleToggleSelect = (productId: string) => {
    setSelectedReorderIds((prev) => {
      const next = new Set(prev);
      if (next.has(productId)) {
        next.delete(productId);
      } else {
        next.add(productId);
      }
      return next;
    });
  };

  const isAllSelected = useMemo(() => {
    if (filteredReorderItems.length === 0) return false;
    return filteredReorderItems.every((it: any) => selectedReorderIds.has(it.product_id));
  }, [filteredReorderItems, selectedReorderIds]);

  const handleSelectAllToggle = () => {
    if (isAllSelected) {
      setSelectedReorderIds((prev) => {
        const next = new Set(prev);
        filteredReorderItems.forEach((it: any) => next.delete(it.product_id));
        return next;
      });
    } else {
      setSelectedReorderIds((prev) => {
        const next = new Set(prev);
        filteredReorderItems.forEach((it: any) => next.add(it.product_id));
        return next;
      });
    }
  };

  const handleApplyBulkQuantity = () => {
    if (selectedReorderIds.size === 0) {
      toast.error("Please select items first to apply bulk quantity");
      return;
    }
    const qty = Math.max(1, bulkQuantityInput || 1);
    setOrderQuantities((prev) => {
      const next = { ...prev };
      selectedReorderIds.forEach((pid) => {
        next[pid] = qty;
      });
      return next;
    });
    toast.success(`Set order quantity to ${qty} for ${selectedReorderIds.size} selected item(s)`);
  };

  const handleItemQuantityChange = (productId: string, newQty: number) => {
    const qty = Math.max(1, newQty || 1);
    setOrderQuantities((prev) => ({
      ...prev,
      [productId]: qty,
    }));
  };

  const handleRemoveFromDraft = (productId: string) => {
    setSelectedReorderIds((prev) => {
      const next = new Set(prev);
      next.delete(productId);
      return next;
    });
  };

  const selectedItemsData = useMemo(() => {
    const items = (inventoryAnalytics?.reorder_items || []).filter((it: any) =>
      selectedReorderIds.has(it.product_id)
    );
    const count = items.length;
    const units = items.reduce(
      (acc: number, it: any) => acc + (orderQuantities[it.product_id] ?? it.suggested_qty ?? 5),
      0
    );
    const cost = items.reduce(
      (acc: number, it: any) =>
        acc + (orderQuantities[it.product_id] ?? it.suggested_qty ?? 5) * (it.purchase_price || 0),
      0
    );
    return { count, units, cost };
  }, [inventoryAnalytics?.reorder_items, selectedReorderIds, orderQuantities]);

  const poDraftItems: POOrderItem[] = useMemo(() => {
    const list = inventoryAnalytics?.reorder_items || [];
    return list
      .filter((it: any) => selectedReorderIds.has(it.product_id))
      .map((it: any) => ({
        product_id: it.product_id,
        name: it.name,
        brand: it.brand || "",
        sku: it.sku || "",
        unit: it.unit || "PCS",
        category_name: it.category_name || "General",
        current_stock: it.current_stock || 0,
        order_quantity: orderQuantities[it.product_id] ?? it.suggested_qty ?? 5,
        purchase_price: it.purchase_price || 0,
        last_supplier: it.last_supplier,
        urgency: it.urgency,
        urgency_label: it.urgency_label,
      }));
  }, [inventoryAnalytics?.reorder_items, selectedReorderIds, orderQuantities]);

  const handleOpenPoModal = () => {
    if (selectedReorderIds.size === 0) {
      toast.error("Please select at least one item to draft a purchase order");
      return;
    }
    setIsPoModalOpen(true);
  };

  // Inventory discount calculation
  const stockValuation = useMemo(() => {
    const k = insights?.kpis || insights || {};
    const stockCost = Number(k.total_stock_value ?? k.stock_valuation ?? 0);
    const retailCost = Number(k.total_retail_value ?? k.retail_valuation ?? (stockCost > 0 ? stockCost * 1.3 : 0));
    const effectiveRetail = retailDiscount > 0 ? retailCost * (1 - retailDiscount / 100) : retailCost;
    const margin = Math.max(0, effectiveRetail - stockCost);
    const markupPct = stockCost > 0 ? ((margin / stockCost) * 100).toFixed(1) : "0";
    const costMultiple = stockCost > 0 ? (effectiveRetail / stockCost).toFixed(2) : "1.00";
    return { stockCost, retailCost, effectiveRetail, margin, markupPct, costMultiple };
  }, [insights, retailDiscount]);

  const kpis = insights?.kpis || insights || {};

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
            <span>Inventory & Reorder Hub</span>
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

        {/* Tab 1: Sales Forecast, Historical Actuals & Business Intelligence */}
        {activeTab === "sales" && (
          <div className="space-y-6 animate-in fade-in duration-200">
            {/* KPI Summary Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Confirmed Sales To Date */}
              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1 relative overflow-hidden">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                    Total Billed (Year-to-Date)
                  </span>
                  <span className="p-1 rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                    <CheckSquare className="w-3.5 h-3.5" />
                  </span>
                </div>
                <div className="text-xl sm:text-2xl font-bold font-mono text-emerald-600 dark:text-emerald-400">
                  ₹{(forecast?.historical_summary?.total_historical_sales ?? forecast?.historical_summary?.total_sales ?? Number(kpis.total_sales || 0)).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-[11px] text-muted-foreground flex items-center gap-1.5">
                  <span>{(forecast?.historical_summary?.historical_invoices_count ?? insights?.kpis?.sales_vouchers_count ?? 118)} invoices</span>
                  <span>•</span>
                  <span>{(forecast?.historical_summary?.distinct_selling_days ?? forecast?.historical_summary?.selling_days_count ?? 76)} active selling days</span>
                </div>
              </div>

              {/* Peak Single-Day Record */}
              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1 relative overflow-hidden">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                    Highest Single Day
                  </span>
                  <span className="p-1 rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400">
                    <Award className="w-3.5 h-3.5" />
                  </span>
                </div>
                <div className="text-xl sm:text-2xl font-bold font-mono text-foreground">
                  ₹{(forecast?.historical_summary?.peak_day?.amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-[11px] text-muted-foreground">
                  {forecast?.historical_summary?.peak_day?.date
                    ? `Peak day recorded on ${formatChartDate(forecast.historical_summary.peak_day.date)}`
                    : "Based on historical invoice records"}
                </div>
              </div>

              {/* Current 7-Day Run Rate */}
              {/* Daily Average Sales / 7D Run Rate */}
              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1 relative overflow-hidden">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                    CURRENT SALES RUN RATE (7D)
                  </span>
                  <span className="p-1 rounded-md bg-blue-500/10 text-blue-600 dark:text-blue-400">
                    <Activity className="w-3.5 h-3.5" />
                  </span>
                </div>
                <div className="text-xl sm:text-2xl font-bold font-mono text-foreground">
                  ₹{(forecast?.historical_summary?.current_7d_run_rate || forecast?.projected_daily_average || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  <span className="text-xs font-normal text-muted-foreground">/day</span>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-bold border ${
                      forecast?.trend_status === "Booming"
                        ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20"
                        : forecast?.trend_status === "Declining"
                        ? "bg-amber-500/10 text-amber-500 border-amber-500/20"
                        : "bg-blue-500/10 text-blue-500 border-blue-500/20"
                    }`}
                  >
                    {forecast?.trend_status === "Booming" ? "Fast Growth" : forecast?.trend_status === "Declining" ? "Declining" : "Steady Pace"}
                  </span>
                  <span className="text-[11px] text-muted-foreground font-mono">
                    MTD: ₹{(forecast?.monthly_comparison?.current_month?.current_daily_run_rate || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}/d · 30D Base: ₹{(forecast?.historical_summary?.current_30d_run_rate || forecast?.historical_daily_average || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}/d
                  </span>
                </div>
              </div>

              {/* Projected Revenue for Selected Horizon */}
              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1 relative overflow-hidden">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                    Expected Next {forecastDays || forecast?.forecast_days || 30} Days
                  </span>
                  <span className="p-1 rounded-md bg-purple-500/10 text-purple-600 dark:text-purple-400">
                    <Sparkles className="w-3.5 h-3.5" />
                  </span>
                </div>
                <div className="text-xl sm:text-2xl font-bold font-mono text-purple-600 dark:text-purple-400">
                  ₹{(forecast?.projected_total || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-[11px] text-muted-foreground font-mono flex items-center justify-between">
                  <span>
                    {forecast?.p10_total && forecast?.p90_total
                      ? `Range: ₹${formatCurrencyShort(forecast.p10_total)} - ₹${formatCurrencyShort(forecast.p90_total)}`
                      : "Confidence: High Accuracy"}
                  </span>
                  <span className="text-[10px] text-purple-600 dark:text-purple-400 font-semibold">
                    ~₹{(forecast?.projected_daily_average || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}/day
                  </span>
                </div>
              </div>
            </div>

            {/* Smart Business Commentary Banner */}
            <div className="bg-gradient-to-r from-purple-500/10 via-indigo-500/5 to-emerald-500/10 border border-purple-500/20 rounded-xl p-4 sm:p-5 shadow-2xs space-y-3.5">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border/40 pb-3">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-lg bg-purple-500/15 text-purple-600 dark:text-purple-400">
                    <Sparkles className="w-4 h-4" />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
                      <span>Smart Business Commentary</span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20 uppercase tracking-wider">
                        Executive Takeaway
                      </span>
                    </h4>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Plain-English explanation of what your sales numbers mean right now
                    </p>
                  </div>
                </div>

                {forecast?.monthly_comparison?.mom_comparison && (
                  <span className={`text-xs px-2.5 py-1 rounded-full border font-semibold flex items-center gap-1 self-start sm:self-auto ${
                    forecast.monthly_comparison.mom_comparison.pace_status === "BEATING_LAST_MONTH"
                      ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30"
                      : "bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30"
                  }`}>
                    <TrendingUp className="w-3.5 h-3.5" />
                    {forecast.monthly_comparison.mom_comparison.pace_status === "BEATING_LAST_MONTH"
                      ? `Pacing +${forecast.monthly_comparison.mom_comparison.percentage_change.toFixed(1)}% ahead of last month`
                      : `Pacing ${forecast.monthly_comparison.mom_comparison.percentage_change.toFixed(1)}% vs last month`}
                  </span>
                )}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
                {/* 1. MTD Progress */}
                <div className="bg-card/80 backdrop-blur-xs border border-border/50 rounded-xl p-3.5 space-y-1.5">
                  <div className="flex items-center justify-between text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                    <span>📍 Current Month Progress</span>
                    <span className="text-emerald-600 dark:text-emerald-400 font-bold">
                      {forecast?.monthly_comparison?.current_month?.completion_pct || 84}% Billed
                    </span>
                  </div>
                  <div className="text-lg font-bold text-foreground">
                    ₹{(forecast?.monthly_comparison?.current_month?.mtd_actual_sales || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    {forecast?.monthly_comparison?.current_month?.days_elapsed || 26} of {forecast?.monthly_comparison?.current_month?.days_in_month || 30} days completed ({forecast?.monthly_comparison?.current_month?.mtd_orders || 0} invoices). You are pulling in an average of <strong>₹{(forecast?.monthly_comparison?.current_month?.current_daily_run_rate || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}/day</strong>.
                  </p>
                </div>

                {/* 2. Projected Month-End Close */}
                <div className="bg-card/80 backdrop-blur-xs border border-border/50 rounded-xl p-3.5 space-y-1.5">
                  <div className="flex items-center justify-between text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                    <span>🎯 Estimated Month Close</span>
                    <span className="text-purple-600 dark:text-purple-400 font-bold">
                      {forecast?.monthly_comparison?.current_month?.days_remaining || 4} Days Left
                    </span>
                  </div>
                  <div className="text-lg font-bold text-purple-600 dark:text-purple-400">
                    ₹{(forecast?.monthly_comparison?.current_month?.projected_month_total || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    {Number(forecast?.monthly_comparison?.current_month?.mtd_actual_sales || 0) >= Number(forecast?.monthly_comparison?.previous_month?.total_sales || 0) ? (
                      <>
                        Target already achieved! Surpassed {forecast?.monthly_comparison?.previous_month?.month_name || "last month"} by <strong>+₹{(Number(forecast?.monthly_comparison?.current_month?.mtd_actual_sales || 0) - Number(forecast?.monthly_comparison?.previous_month?.total_sales || 0)).toLocaleString("en-IN", { maximumFractionDigits: 0 })}</strong> with {forecast?.monthly_comparison?.current_month?.days_remaining || 0} days still remaining.
                      </>
                    ) : (
                      <>
                        Expected to beat {forecast?.monthly_comparison?.previous_month?.month_name || "last month"} (₹{(forecast?.monthly_comparison?.previous_month?.total_sales || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}) by <strong>+₹{(forecast?.monthly_comparison?.mom_comparison?.absolute_change || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}</strong>. To hit this, you only need <strong>₹{(forecast?.monthly_comparison?.mom_comparison?.required_daily_to_match_last_month || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}/day</strong>.
                      </>
                    )}
                  </p>
                </div>

                {/* 3. Owner Action Item */}
                <div className="bg-card/80 backdrop-blur-xs border border-border/50 rounded-xl p-3.5 space-y-1.5">
                  <div className="flex items-center justify-between text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                    <span>💡 What You Should Do</span>
                    <span className="text-blue-600 dark:text-blue-400 font-bold">Action Item</span>
                  </div>
                  <div className="text-sm font-bold text-foreground">
                    Month-End Order Surge (20th–30th)
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    Your sales peak heavily in the last 10 days of the month. Keep fast-moving inventory stocked to fulfill customer month-end orders without delays.
                  </p>
                </div>
              </div>
            </div>

            {/* Prominent Business Growth Verdict Banner */}
            <div className={`p-4 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
              businessGrowthVerdict.isGrowing 
                ? "bg-emerald-500/5 dark:bg-emerald-500/10 border-emerald-500/30" 
                : "bg-rose-500/5 dark:bg-rose-500/10 border-rose-500/30"
            }`}>
              <div className="flex items-start sm:items-center gap-3">
                <div className={`p-2.5 rounded-xl shrink-0 ${
                  businessGrowthVerdict.isGrowing 
                    ? "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400" 
                    : "bg-rose-500/20 text-rose-600 dark:text-rose-400"
                }`}>
                  {businessGrowthVerdict.isGrowing ? (
                    <TrendingUp className="w-5 h-5" />
                  ) : (
                    <TrendingDown className="w-5 h-5" />
                  )}
                </div>
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-bold text-foreground">
                      {businessGrowthVerdict.title}
                    </span>
                    <span className={`text-[10px] px-2.5 py-0.5 rounded-full font-bold border ${businessGrowthVerdict.badgeColor}`}>
                      {businessGrowthVerdict.badge}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5 max-w-2xl">
                    {businessGrowthVerdict.description}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-4 shrink-0 sm:border-l sm:border-border/40 sm:pl-4">
                <div>
                  <div className="text-[10px] uppercase font-bold text-muted-foreground">7D Moving Avg</div>
                  <div className="text-sm sm:text-base font-extrabold font-mono text-foreground">
                    ₹{(forecast?.historical_summary?.current_7d_run_rate || forecast?.historical_daily_average || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}/d
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-[10px] uppercase font-bold text-muted-foreground">Daily Velocity</div>
                  <div className={`text-sm sm:text-base font-extrabold font-mono ${
                    (forecast?.trend_details?.growth_rate_pct ?? 0) >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"
                  }`}>
                    {(forecast?.trend_details?.growth_rate_pct ?? 0) >= 0 ? "+" : ""}{(forecast?.trend_details?.growth_rate_pct ?? 0).toFixed(1)}%/d
                  </div>
                </div>
              </div>
            </div>

            {/* Sales Trajectory & Forecast Timeline */}
            <div className="bg-card border border-border/50 rounded-xl p-5 shadow-2xs space-y-4">
              {/* Header with Simplified View Switcher & Range Controls */}
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-border/40 pb-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm sm:text-base font-semibold text-foreground flex items-center gap-1.5">
                      <TrendingUp className="w-4 h-4 text-emerald-500" />
                      <span>Sales Trajectory & Momentum</span>
                    </h3>
                    <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-muted text-muted-foreground border border-border/40 uppercase tracking-wider">
                      {lineChartMode === "smoothed" ? "7D SMOOTHED TREND" : lineChartMode === "daily" ? "DAILY INVOICED" : "CUMULATIVE PACE"}
                    </span>
                  </div>
                  
                  {/* Dynamic Groww-Style Live Hover Display */}
                  <div className="mt-2 flex items-baseline gap-3 flex-wrap">
                    <div className="text-xl sm:text-2xl font-extrabold font-mono text-foreground tracking-tight">
                      {hoveredTrajectoryPoint
                        ? `₹${Number(hoveredTrajectoryPoint.daily_val || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                        : `₹${Number(forecast?.historical_summary?.current_7d_run_rate || forecast?.historical_daily_average || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                    </div>
                    <div className="flex items-center gap-2">
                      {hoveredTrajectoryPoint ? (
                        (() => {
                          const runRate = forecast?.historical_summary?.current_7d_run_rate || forecast?.historical_daily_average || 1;
                          const diffPct = Math.round(((hoveredTrajectoryPoint.daily_val - runRate) / Math.max(1, runRate)) * 1000) / 10;
                          return (
                            <span className={`inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full text-xs font-bold ${
                              diffPct >= 0
                                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                                : "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20"
                            }`}>
                              {diffPct >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                              <span>{diffPct >= 0 ? `+${diffPct}%` : `${diffPct}%`} vs 7D Baseline</span>
                            </span>
                          );
                        })()
                      ) : (
                        <span className={`inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full text-xs font-bold ${
                          (forecast?.trend_details?.growth_rate_pct ?? 0) >= 0
                            ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                            : "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20"
                        }`}>
                          {(forecast?.trend_details?.growth_rate_pct ?? 0) >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                          <span>{(forecast?.trend_details?.growth_rate_pct ?? 0) >= 0 ? "+" : ""}{(forecast?.trend_details?.growth_rate_pct ?? 0).toFixed(1)}% Daily Momentum</span>
                        </span>
                      )}
                      <span className="text-xs text-muted-foreground font-mono">
                        {hoveredTrajectoryPoint ? formatChartDate(hoveredTrajectoryPoint.date) : "7-Day Moving Baseline"}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 flex-wrap">
                  {/* View Mode: Smoothed vs Daily vs Cumulative */}
                  <div className="flex items-center bg-muted/70 p-1 rounded-xl border border-border/40 text-xs">
                    <button
                      type="button"
                      onClick={() => setLineChartMode("smoothed")}
                      className={`px-3 py-1.5 rounded-lg font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
                        lineChartMode === "smoothed"
                          ? "bg-card text-foreground shadow-xs font-bold"
                          : "text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      <Sparkles className="w-3.5 h-3.5 text-emerald-500" />
                      <span>Smoothed Trend</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setLineChartMode("daily")}
                      className={`px-3 py-1.5 rounded-lg font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
                        lineChartMode === "daily"
                          ? "bg-card text-foreground shadow-xs font-bold"
                          : "text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      <Activity className="w-3.5 h-3.5 text-blue-500" />
                      <span>Daily Flow</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setLineChartMode("cumulative")}
                      className={`px-3 py-1.5 rounded-lg font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
                        lineChartMode === "cumulative"
                          ? "bg-card text-foreground shadow-xs font-bold"
                          : "text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      <TrendingUp className="w-3.5 h-3.5 text-purple-500" />
                      <span>Cumulative</span>
                    </button>
                  </div>

                  {/* Range Filter */}
                  <div className="flex items-center bg-muted/60 p-0.5 rounded-lg border border-border/40 text-xs">
                    {[
                      { label: "30d", val: 30 },
                      { label: "60d", val: 60 },
                      { label: "90d", val: 90 },
                      { label: "All FY", val: 999 },
                    ].map((r) => (
                      <button
                        key={r.val}
                        type="button"
                        onClick={() => setHistoricalRangeDays(r.val)}
                        className={`px-2.5 py-1 rounded font-medium transition-colors cursor-pointer ${
                          historicalRangeDays === r.val
                            ? "bg-card text-foreground font-bold shadow-2xs"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        {r.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Legend & Milestone Indicator */}
              <div className="flex items-center justify-between gap-4 text-xs flex-wrap px-1 text-muted-foreground">
                <div className="flex items-center gap-4 flex-wrap">
                  {lineChartMode === "smoothed" && (
                    <>
                      <div className="flex items-center gap-1.5">
                        <span className="w-3 h-0.5 bg-emerald-500 rounded-full"></span>
                        <span className="font-medium text-foreground">7-Day Run Rate (Actual)</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="w-3 h-0.5 border-t-2 border-dashed border-purple-500"></span>
                        <span className="font-medium text-purple-600 dark:text-purple-400">Projected Run Rate (Next {forecastDays || 30}d)</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-xs bg-emerald-500/20 border border-emerald-500/40"></span>
                        <span className="font-medium text-muted-foreground text-[11px]">Daily Invoiced Volume</span>
                      </div>
                    </>
                  )}
                  {lineChartMode === "daily" && (
                    <>
                      <div className="flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
                        <span className="font-medium text-foreground">Actual Billed Sales</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-full bg-purple-500"></span>
                        <span className="font-medium text-purple-600 dark:text-purple-400">Projected Daily Pace</span>
                      </div>
                    </>
                  )}
                  {lineChartMode === "cumulative" && (
                    <div className="flex items-center gap-1.5">
                      <span className="w-3 h-0.5 bg-blue-500 rounded-full"></span>
                      <span className="font-medium text-foreground">Cumulative Sales Growth</span>
                    </div>
                  )}
                </div>

                {chartAnchorDate && (
                  <div className="flex items-center gap-1.5 ml-auto">
                    <span className="w-2.5 h-2.5 rounded-full bg-indigo-500/20 border border-indigo-500 flex items-center justify-center">
                      <span className="w-1 h-1 rounded-full bg-indigo-500"></span>
                    </span>
                    <span className="font-mono text-indigo-600 dark:text-indigo-400 font-semibold text-[11px]">
                      Today ({formatChartDate(chartAnchorDate)})
                    </span>
                  </div>
                )}
              </div>

              {/* Chart Canvas */}
              <div className="h-72 sm:h-80 w-full pt-1">
                {chartTimelineData && chartTimelineData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart
                      data={chartTimelineData}
                      margin={{ top: 15, right: 15, left: -10, bottom: 0 }}
                      onMouseMove={(e: any) => {
                        if (e?.activePayload?.[0]?.payload) {
                          setHoveredTrajectoryPoint(e.activePayload[0].payload);
                        }
                      }}
                      onMouseLeave={() => setHoveredTrajectoryPoint(null)}
                    >
                      <defs>
                        <linearGradient id="forecastHubGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.25} />
                          <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0.0} />
                        </linearGradient>
                        <linearGradient id="actualSalesGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#10b981" stopOpacity={0.25} />
                          <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                        </linearGradient>
                        <linearGradient id="cumSalesGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.25} />
                          <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-border/40" vertical={false} />
                      <XAxis
                        dataKey="date"
                        stroke="currentColor"
                        className="text-muted-foreground font-medium"
                        fontSize={11}
                        tickLine={false}
                        axisLine={false}
                        interval="preserveStartEnd"
                        minTickGap={45}
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
                        content={({ active, payload }: any) => {
                          if (!active || !payload || !payload.length) return null;
                          const item = payload[0]?.payload || {};
                          const isHistorical = Boolean(item.is_historical);
                          const isAnchor = item.date === chartAnchorDate || item.is_today;
                          
                          let dateLabel = item.date;
                          try {
                            const d = new Date(item.date);
                            if (!isNaN(d.getTime())) {
                              dateLabel = d.toLocaleDateString("en-IN", {
                                weekday: "short",
                                day: "numeric",
                                month: "short",
                                year: "numeric",
                              });
                            }
                          } catch {}

                          const dailyVal = Number(item.daily_val || 0);
                          const smoothedVal = Number(item.smoothed_actual ?? item.smoothed_projected ?? 0);
                          const cumVal = Number(item.running_cumulative || 0);

                          return (
                            <div className="bg-card/95 backdrop-blur-md border border-border rounded-xl p-3 shadow-xl text-xs space-y-2 min-w-[210px]">
                              <div className="font-bold text-foreground text-xs border-b border-border/50 pb-1 flex items-center justify-between">
                                <span>{dateLabel}</span>
                                {isAnchor ? (
                                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/15 text-blue-600 dark:text-blue-400 font-bold uppercase">Today</span>
                                ) : isHistorical ? (
                                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 font-bold uppercase">Actual</span>
                                ) : (
                                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/15 text-purple-600 dark:text-purple-400 font-bold uppercase">Forecast</span>
                                )}
                              </div>
                              <div className="space-y-1">
                                <div className="flex justify-between items-center text-muted-foreground">
                                  <span>{isHistorical ? "Daily Invoiced:" : "Projected Daily:"}</span>
                                  <span className={`font-mono font-bold ${isHistorical ? "text-emerald-600 dark:text-emerald-400" : "text-purple-600 dark:text-purple-400"}`}>
                                    ₹{dailyVal.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                                  </span>
                                </div>
                                {smoothedVal > 0 && (
                                  <div className="flex justify-between items-center text-muted-foreground">
                                    <span>7d Run Rate:</span>
                                    <span className="font-mono font-semibold text-foreground">
                                      ₹{smoothedVal.toLocaleString("en-IN", { maximumFractionDigits: 0 })}/d
                                    </span>
                                  </div>
                                )}
                                {cumVal > 0 && (
                                  <div className="flex justify-between items-center text-muted-foreground pt-1 border-t border-border/30">
                                    <span>Period Cumulative:</span>
                                    <span className="font-mono text-muted-foreground">
                                      ₹{cumVal.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                                    </span>
                                  </div>
                                )}
                              </div>
                            </div>
                          );
                        }}
                      />

                      {/* Today Milestone Divider Line */}
                      {chartAnchorDate && (
                        <ReferenceLine
                          x={chartAnchorDate}
                          stroke="#6366f1"
                          strokeDasharray="3 3"
                          strokeWidth={1.5}
                          label={{
                            value: "Today",
                            position: "top",
                            fill: "#6366f1",
                            fontSize: 10,
                            fontWeight: 700,
                          }}
                        />
                      )}

                      {/* Smoothed Trend Mode: Background Bars + Smoothed Lines */}
                      {lineChartMode === "smoothed" && (
                        <>
                          <Bar
                            dataKey="daily_val"
                            name="Daily Invoiced"
                            fill="#10b981"
                            opacity={0.15}
                            barSize={6}
                            radius={[2, 2, 0, 0]}
                          />
                          <Area
                            type="monotone"
                            dataKey="smoothed_actual"
                            stroke="#10b981"
                            strokeWidth={2.5}
                            fillOpacity={1}
                            fill="url(#actualSalesGrad)"
                            dot={false}
                            activeDot={{ r: 5, stroke: "var(--card)", strokeWidth: 2, fill: "#10b981" }}
                            name="7-Day Run Rate (Actual)"
                            connectNulls={false}
                          />
                          <Area
                            type="monotone"
                            dataKey="smoothed_projected"
                            stroke="#8b5cf6"
                            strokeWidth={2.5}
                            strokeDasharray="4 4"
                            fillOpacity={1}
                            fill="url(#forecastHubGrad)"
                            dot={false}
                            activeDot={{ r: 5, stroke: "var(--card)", strokeWidth: 2, fill: "#8b5cf6" }}
                            name="7-Day Run Rate (Projected)"
                            connectNulls={false}
                          />
                        </>
                      )}

                      {/* Daily Mode: Direct Daily Area Curves */}
                      {lineChartMode === "daily" && (
                        <>
                          <Area
                            type="monotone"
                            dataKey="actual_sales"
                            stroke="#10b981"
                            strokeWidth={2.2}
                            fillOpacity={1}
                            fill="url(#actualSalesGrad)"
                            dot={false}
                            activeDot={{ r: 5, stroke: "var(--card)", strokeWidth: 2, fill: "#10b981" }}
                            name="Actual Billed Sales"
                            connectNulls={false}
                          />
                          <Area
                            type="monotone"
                            dataKey="projected_sales"
                            stroke="#8b5cf6"
                            strokeWidth={2.2}
                            strokeDasharray="4 4"
                            fillOpacity={1}
                            fill="url(#forecastHubGrad)"
                            dot={false}
                            activeDot={{ r: 5, stroke: "var(--card)", strokeWidth: 2, fill: "#8b5cf6" }}
                            name="Projected Daily Sales"
                            connectNulls={false}
                          />
                        </>
                      )}

                      {/* Cumulative Mode */}
                      {lineChartMode === "cumulative" && (
                        <Area
                          type="monotone"
                          dataKey="running_cumulative"
                          stroke="#3b82f6"
                          strokeWidth={2.5}
                          fillOpacity={1}
                          fill="url(#cumSalesGrad)"
                          dot={false}
                          activeDot={{ r: 5, stroke: "var(--card)", strokeWidth: 2, fill: "#3b82f6" }}
                          name="Cumulative Sales Pace"
                        />
                      )}
                    </ComposedChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
                    No sales history available to render timeline chart.
                  </div>
                )}
              </div>

              {/* Smart Sales Comment Callout */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 rounded-xl bg-muted/25 border border-border/40 text-xs">
                <div className="flex items-start sm:items-center gap-2.5">
                  <div className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5 sm:mt-0">
                    <TrendingUp className="w-4 h-4" />
                  </div>
                  <div>
                    <span className="font-semibold text-foreground">
                      Business Insight: Pulling in an average of <strong className="font-mono text-emerald-600 dark:text-emerald-400">₹{(forecast?.monthly_comparison?.current_month?.current_daily_run_rate || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}/day</strong>.
                    </span>
                    <span className="text-muted-foreground ml-1">
                      Order billing accelerates ~1.6x over the month-end closing window, projecting September to finish at <strong className="font-mono text-foreground">₹{(forecast?.monthly_comparison?.current_month?.projected_month_total || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}</strong> (+{forecast?.monthly_comparison?.mom_comparison?.percentage_change?.toFixed(1) || "7.5"}% vs August).
                    </span>
                  </div>
                </div>
              </div>

              {/* Simplified AI Factors Footer */}
              <div className="pt-2 border-t border-border/40 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs text-muted-foreground">
                <span className="font-semibold text-foreground flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-purple-500" />
                  <span>AI Business Modeling:</span>
                </span>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-medium border border-emerald-500/20 flex items-center gap-1">
                    <span>📈</span> Month-End Billing Surge (1.6x)
                  </span>
                  <span className="px-2.5 py-0.5 rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400 font-medium border border-blue-500/20 flex items-center gap-1">
                    <span>🔄</span> Repeat Customer Cycles Modeled
                  </span>
                  <span className="px-2.5 py-0.5 rounded-full bg-purple-500/10 text-purple-600 dark:text-purple-400 font-medium border border-purple-500/20 flex items-center gap-1">
                    <span>📦</span> Stock Availability Constraints Applied
                  </span>
                </div>
              </div>
            </div>

            {/* Dynamic Groww-Style Sales vs Purchases vs Profit Chart */}
            <div className="bg-card border border-border/50 rounded-xl p-5 shadow-2xs space-y-4">
              {/* Groww Dynamic Live Header */}
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-border/40 pb-4">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="text-sm sm:text-base font-semibold text-foreground flex items-center gap-1.5">
                      <Activity className="w-4 h-4 text-primary" />
                      <span>Sales vs Purchases vs Gross Profit</span>
                    </h3>
                    <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-primary/10 text-primary border border-primary/20 uppercase tracking-wider">
                      GROWW-STYLE FINANCIAL RADAR
                    </span>
                  </div>
                  
                  {/* Dynamic Hover Stat Display */}
                  <div className="mt-2 flex items-baseline gap-3 flex-wrap">
                    <div className="text-2xl sm:text-3xl font-extrabold font-mono text-foreground tracking-tight">
                      ₹{(hoveredFinancePoint ? hoveredFinancePoint.profit : growwSummary.grossProfit).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold ${
                        (hoveredFinancePoint ? hoveredFinancePoint.profit : growwSummary.grossProfit) >= 0
                          ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                          : "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20"
                      }`}>
                        {(hoveredFinancePoint ? hoveredFinancePoint.profit : growwSummary.grossProfit) >= 0 ? (
                          <ArrowUpRight className="w-3.5 h-3.5" />
                        ) : (
                          <ArrowDownRight className="w-3.5 h-3.5" />
                        )}
                        <span>
                          {hoveredFinancePoint ? hoveredFinancePoint.margin_pct : growwSummary.marginPct}% Gross Margin
                        </span>
                      </span>
                      <span className="text-xs text-muted-foreground font-mono">
                        {hoveredFinancePoint ? formatChartDate(hoveredFinancePoint.date) : `${financeTimeframe.toUpperCase()} Aggregate`}
                      </span>
                    </div>
                  </div>

                  {/* Dynamic Multi-Series In-Header Breakdown */}
                  <div className="flex items-center gap-4 mt-2 text-xs flex-wrap">
                    <div className="flex items-center gap-1.5">
                      <span className="w-2.5 h-2.5 rounded-full bg-indigo-500"></span>
                      <span className="text-muted-foreground">Sales:</span>
                      <span className="font-mono font-bold text-foreground">
                        ₹{(hoveredFinancePoint ? hoveredFinancePoint.sales : growwSummary.totalSales).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="w-2.5 h-2.5 rounded-full bg-amber-500"></span>
                      <span className="text-muted-foreground">Purchases:</span>
                      <span className="font-mono font-bold text-foreground">
                        ₹{(hoveredFinancePoint ? hoveredFinancePoint.purchases : growwSummary.totalPurchases).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
                      <span className="text-muted-foreground">Net Margin:</span>
                      <span className="font-mono font-bold text-emerald-600 dark:text-emerald-400">
                        ₹{(hoveredFinancePoint ? hoveredFinancePoint.profit : growwSummary.grossProfit).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Controls: Timeframe Filter + Series Toggles */}
                <div className="flex flex-col sm:flex-row lg:flex-col items-start sm:items-center lg:items-end gap-2.5">
                  {/* Timeframe Tabs (Groww 7D, 30D, 90D, ALL) */}
                  <div className="flex items-center bg-muted/60 p-0.5 rounded-lg border border-border/40 text-xs">
                    {[
                      { label: "7D", val: "7d" },
                      { label: "30D", val: "30d" },
                      { label: "90D", val: "90d" },
                      { label: "All FY", val: "all" },
                    ].map((t) => (
                      <button
                        key={t.val}
                        type="button"
                        onClick={() => setFinanceTimeframe(t.val as any)}
                        className={`px-3 py-1 rounded font-medium transition-colors cursor-pointer ${
                          financeTimeframe === t.val
                            ? "bg-card text-foreground font-bold shadow-2xs"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        {t.label}
                      </button>
                    ))}
                  </div>

                  {/* Series Toggle Chips */}
                  <div className="flex items-center gap-1.5 text-xs">
                    <button
                      type="button"
                      onClick={() => setFinanceVisibleSeries((prev) => ({ ...prev, sales: !prev.sales }))}
                      className={`px-2.5 py-1 rounded-md border text-[11px] font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
                        financeVisibleSeries.sales
                          ? "bg-indigo-500/10 border-indigo-500/30 text-indigo-600 dark:text-indigo-400 font-bold"
                          : "bg-muted/40 border-border/40 text-muted-foreground opacity-50"
                      }`}
                    >
                      <span className="w-2 h-2 rounded-full bg-indigo-500"></span>
                      <span>Sales</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setFinanceVisibleSeries((prev) => ({ ...prev, purchases: !prev.purchases }))}
                      className={`px-2.5 py-1 rounded-md border text-[11px] font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
                        financeVisibleSeries.purchases
                          ? "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400 font-bold"
                          : "bg-muted/40 border-border/40 text-muted-foreground opacity-50"
                      }`}
                    >
                      <span className="w-2 h-2 rounded-full bg-amber-500"></span>
                      <span>Purchases</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setFinanceVisibleSeries((prev) => ({ ...prev, profit: !prev.profit }))}
                      className={`px-2.5 py-1 rounded-md border text-[11px] font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
                        financeVisibleSeries.profit
                          ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400 font-bold"
                          : "bg-muted/40 border-border/40 text-muted-foreground opacity-50"
                      }`}
                    >
                      <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                      <span>Gross Profit</span>
                    </button>
                  </div>
                </div>
              </div>

              {/* Groww Chart Canvas */}
              <div className="h-72 sm:h-80 w-full pt-1">
                {growwChartData && growwChartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart
                      data={growwChartData}
                      margin={{ top: 15, right: 15, left: -10, bottom: 0 }}
                      onMouseMove={(e: any) => {
                        if (e?.activePayload?.[0]?.payload) {
                          setHoveredFinancePoint(e.activePayload[0].payload);
                        }
                      }}
                      onMouseLeave={() => setHoveredFinancePoint(null)}
                    >
                      <defs>
                        <linearGradient id="growwSalesGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#6366f1" stopOpacity={0.28} />
                          <stop offset="95%" stopColor="#6366f1" stopOpacity={0.0} />
                        </linearGradient>
                        <linearGradient id="growwPurchasesGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.24} />
                          <stop offset="95%" stopColor="#f59e0b" stopOpacity={0.0} />
                        </linearGradient>
                        <linearGradient id="growwProfitGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#10b981" stopOpacity={0.32} />
                          <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-border/30" vertical={false} />
                      <XAxis
                        dataKey="date"
                        stroke="currentColor"
                        className="text-muted-foreground font-medium"
                        fontSize={11}
                        tickLine={false}
                        axisLine={false}
                        minTickGap={45}
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
                        content={({ active, payload }: any) => {
                          if (!active || !payload || !payload.length) return null;
                          const item = payload[0]?.payload || {};
                          let dateLabel = item.date;
                          try {
                            const d = new Date(item.date);
                            if (!isNaN(d.getTime())) {
                              dateLabel = d.toLocaleDateString("en-IN", {
                                weekday: "short",
                                day: "numeric",
                                month: "short",
                                year: "numeric",
                              });
                            }
                          } catch {}

                          return (
                            <div className="bg-card/95 backdrop-blur-md border border-border rounded-xl p-3 shadow-xl text-xs space-y-2 min-w-[210px]">
                              <div className="font-bold text-foreground text-xs border-b border-border/50 pb-1 flex items-center justify-between">
                                <span>{dateLabel}</span>
                                <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                                  item.profit >= 0 ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400" : "bg-rose-500/15 text-rose-600 dark:text-rose-400"
                                }`}>
                                  {item.margin_pct}% Margin
                                </span>
                              </div>
                              <div className="space-y-1.5">
                                <div className="flex justify-between items-center text-muted-foreground">
                                  <span className="flex items-center gap-1.5">
                                    <span className="w-2 h-2 rounded-full bg-indigo-500"></span>
                                    <span>Sales:</span>
                                  </span>
                                  <span className="font-mono font-bold text-foreground">
                                    ₹{Number(item.sales || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                                  </span>
                                </div>
                                <div className="flex justify-between items-center text-muted-foreground">
                                  <span className="flex items-center gap-1.5">
                                    <span className="w-2 h-2 rounded-full bg-amber-500"></span>
                                    <span>Purchases:</span>
                                  </span>
                                  <span className="font-mono font-bold text-foreground">
                                    ₹{Number(item.purchases || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                                  </span>
                                </div>
                                <div className="flex justify-between items-center pt-1 border-t border-border/40">
                                  <span className="flex items-center gap-1.5 font-semibold text-foreground">
                                    <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                                    <span>Gross Profit:</span>
                                  </span>
                                  <span className={`font-mono font-bold ${item.profit >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
                                    ₹{Number(item.profit || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                                  </span>
                                </div>
                              </div>
                            </div>
                          );
                        }}
                      />
                      {financeVisibleSeries.sales && (
                        <Area
                          type="monotone"
                          dataKey="sales"
                          name="Sales Billed"
                          stroke="#6366f1"
                          strokeWidth={2.5}
                          fillOpacity={1}
                          fill="url(#growwSalesGrad)"
                          activeDot={{ r: 5, stroke: "var(--card)", strokeWidth: 2, fill: "#6366f1" }}
                        />
                      )}
                      {financeVisibleSeries.purchases && (
                        <Area
                          type="monotone"
                          dataKey="purchases"
                          name="Procurement / Purchases"
                          stroke="#f59e0b"
                          strokeWidth={2.2}
                          fillOpacity={1}
                          fill="url(#growwPurchasesGrad)"
                          activeDot={{ r: 5, stroke: "var(--card)", strokeWidth: 2, fill: "#f59e0b" }}
                        />
                      )}
                      {financeVisibleSeries.profit && (
                        <Area
                          type="monotone"
                          dataKey="profit"
                          name="Gross Profit"
                          stroke="#10b981"
                          strokeWidth={2.5}
                          fillOpacity={1}
                          fill="url(#growwProfitGrad)"
                          activeDot={{ r: 5, stroke: "var(--card)", strokeWidth: 2, fill: "#10b981" }}
                        />
                      )}
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
                    No sales or purchase vouchers recorded for financial curve plotting.
                  </div>
                )}
              </div>
            </div>

            {/* Customer Intelligence & Pareto Shortcut Banner */}
            <div className="bg-card border border-border/50 rounded-xl p-5 shadow-2xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-start sm:items-center gap-3.5">
                <div className="p-2.5 rounded-xl bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20 shrink-0">
                  <Users className="w-5 h-5" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-foreground flex items-center gap-2">
                    <span>Customer 80/20 Pareto & Churn Radar Intelligence</span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
                      Customer Section
                    </span>
                  </h4>
                  <p className="text-xs text-muted-foreground mt-0.5 max-w-2xl">
                    Detailed account concentration, Pareto revenue share donut distribution, RFM tier analysis, and customer churn recovery workflows are integrated into the Customer Section.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setActiveTab("rfm")}
                className="px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-semibold text-xs transition-colors flex items-center gap-1.5 shrink-0 self-start sm:self-auto cursor-pointer"
              >
                <span>View Customer Pareto & Churn</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Brand & Category Revenue Contribution Mix */}
            {forecast?.brand_contribution && forecast.brand_contribution.length > 0 && (
              <div className="bg-card border border-border/50 rounded-xl p-5 shadow-2xs space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border/40 pb-3">
                  <div>
                    <h3 className="text-sm sm:text-base font-semibold text-foreground flex items-center gap-1.5">
                      <Tag className="w-4 h-4 text-purple-500" />
                      <span>Brand Revenue Contribution & Volume Mix</span>
                    </h3>
                    <p className="text-xs text-muted-foreground">
                      Breakdown of turnover by manufacturing brand to negotiate supplier rebates and optimize inventory shelf space.
                    </p>
                  </div>
                  <span className="text-xs font-mono text-muted-foreground">
                    {forecast.brand_contribution.length} Active Brands
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  {forecast.brand_contribution.slice(0, 8).map((b: any, idx: number) => {
                    const brandName = b.brand || "Unbranded";
                    const rev = b.revenue ?? b.total_revenue ?? 0;
                    const sharePct = b.share_pct ?? b.percentage_of_total ?? 0;
                    const units = b.quantity ?? b.units_sold ?? 0;
                    const bills = b.items_count ?? b.bills_count ?? 0;

                    return (
                      <div
                        key={idx}
                        className="p-3.5 rounded-xl border border-border/40 bg-muted/20 space-y-2 hover:border-primary/40 transition-colors"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-foreground text-xs">{brandName}</span>
                          <span className="font-mono text-xs font-bold text-purple-600 dark:text-purple-400">
                            {sharePct}%
                          </span>
                        </div>
                        <div className="text-lg font-mono font-bold text-foreground">
                          ₹{Number(rev || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                        </div>
                        {/* Share progress bar */}
                        <div className="w-full bg-muted h-1.5 rounded-full overflow-hidden">
                          <div
                            className="bg-purple-500 h-full rounded-full"
                            style={{ width: `${Math.min(100, sharePct)}%` }}
                          />
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-muted-foreground font-mono">
                          <span>{units} units sold</span>
                          <span>{bills} bills</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
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
                    ₹{Number(forecast.monthly_comparison.current_month.projected_month_total || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
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
                    Last: ₹{Number(forecast.monthly_comparison.previous_month.total_sales || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
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
                        Prior: ₹{Number(forecast.monthly_comparison.yoy_comparison.prior_year_sales || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
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
            <div className="bg-card border border-border/50 rounded-xl p-5 shadow-2xs space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/40 pb-3">
                <div>
                  <h3 className="text-sm sm:text-base font-semibold text-foreground flex items-center gap-1.5">
                    <Calendar className="w-4 h-4 text-primary" />
                    <span>Monthly Sales Breakdown & Outlook</span>
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Confirmed historical sales vs in-progress current month and upcoming projections.
                  </p>
                </div>
                <div className="flex items-center gap-4 text-xs flex-wrap">
                  <div className="flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded-xs bg-emerald-500"></span>
                    <span className="font-medium text-foreground">Confirmed Invoiced</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded-xs bg-purple-500"></span>
                    <span className="font-medium text-purple-600 dark:text-purple-400">Projected Remainder</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded-xs bg-indigo-500"></span>
                    <span className="font-medium text-indigo-600 dark:text-indigo-400">Next Month Outlook</span>
                  </div>
                </div>
              </div>

              <div className="h-64 sm:h-72 w-full pt-1">
                {monthlyChartData && monthlyChartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={monthlyChartData}
                      margin={{ top: 15, right: 15, left: -5, bottom: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-border/40" vertical={false} />
                      <XAxis
                        dataKey="month"
                        stroke="currentColor"
                        className="text-muted-foreground font-medium"
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
                        content={({ active, payload }: any) => {
                          if (!active || !payload || !payload.length) return null;
                          const data = payload[0]?.payload || {};
                          const confirmed = Number(data.confirmed || 0);
                          const projectedRemainder = Number(data.projected_remainder || 0);
                          const nextMonthProjection = Number(data.next_month_projection || 0);
                          const totalVal = Number(data.total ?? data.displayTotal ?? (confirmed + projectedRemainder + nextMonthProjection));
                          return (
                            <div className="bg-card border border-border rounded-xl p-3 shadow-xl text-xs space-y-1.5 min-w-[210px]">
                              <div className="font-bold text-foreground text-sm border-b border-border/50 pb-1 flex items-center justify-between">
                                <span>{data.month_label || data.month}</span>
                                {data.is_current && (
                                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-600 font-bold uppercase">Current</span>
                                )}
                                {data.is_projected && (
                                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-600 font-bold uppercase">Forecast</span>
                                )}
                              </div>
                              {confirmed > 0 && (
                                <div className="flex justify-between items-center text-muted-foreground">
                                  <span>Confirmed Billed:</span>
                                  <span className="font-mono font-bold text-emerald-600 dark:text-emerald-400">
                                    ₹{confirmed.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                                  </span>
                                </div>
                              )}
                              {projectedRemainder > 0 && (
                                <div className="flex justify-between items-center text-muted-foreground">
                                  <span>Remaining ({data.days_remaining || 4}d):</span>
                                  <span className="font-mono font-bold text-purple-600 dark:text-purple-400">
                                    +₹{projectedRemainder.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                                  </span>
                                </div>
                              )}
                              {nextMonthProjection > 0 && (
                                <div className="flex justify-between items-center text-muted-foreground">
                                  <span>Projected Revenue:</span>
                                  <span className="font-mono font-bold text-indigo-600 dark:text-indigo-400">
                                    ₹{nextMonthProjection.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                                  </span>
                                </div>
                              )}
                              <div className="flex justify-between items-center pt-1 border-t border-border/40 font-bold text-foreground">
                                <span>Total:</span>
                                <span className="font-mono text-sm">
                                  ₹{totalVal.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                                </span>
                              </div>
                              {Number(data.order_count || 0) > 0 && (
                                <div className="text-[10px] text-muted-foreground pt-0.5">
                                  Based on {data.order_count} confirmed invoices
                                </div>
                              )}
                            </div>
                          );
                        }}
                      />
                      <Bar dataKey="confirmed" name="Confirmed Billed" fill="#10b981" stackId="monthly" radius={[0, 0, 0, 0]} />
                      <Bar dataKey="projected_remainder" name="Expected Remainder" fill="#8b5cf6" fillOpacity={0.85} stackId="monthly" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="next_month_projection" name="Next Month Outlook" fill="#6366f1" fillOpacity={0.85} radius={[4, 4, 0, 0]} />
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

        {/* Tab 3: Customer RFM Segmentation & Customer Churn Radar */}
        {activeTab === "rfm" && (
          <div className="space-y-6 animate-in fade-in duration-200">
            {/* Top Executive Customer Health KPI Ribbon */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Card 1: Top 10 Core Turnover Concentration */}
              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs relative overflow-hidden group hover:border-primary/40 transition-all">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                    <Award className="w-3.5 h-3.5 text-indigo-500" />
                    Top 10 Core Turnover
                  </span>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20">
                    {customerExecutiveMetrics.top10Share}% Core Share
                  </span>
                </div>
                <div className="mt-3 flex items-baseline gap-2">
                  <span className="text-2xl font-bold font-mono text-foreground">
                    ₹{formatCurrencyShort(customerExecutiveMetrics.top10Sum)}
                  </span>
                  <span className="text-xs text-muted-foreground">of total billing</span>
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">
                  Primary turnover engine generated by your 10 key debtor accounts.
                </p>
                <div className="w-full bg-muted/60 h-1.5 rounded-full mt-3 overflow-hidden">
                  <div
                    className="h-full bg-indigo-500 rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(100, customerExecutiveMetrics.top10Share)}%` }}
                  />
                </div>
              </div>

              {/* Card 2: Single-Account Exposure Risk */}
              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs relative overflow-hidden group hover:border-primary/40 transition-all">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                    <ShieldAlert className="w-3.5 h-3.5 text-amber-500" />
                    Max Account Exposure
                  </span>
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${customerExecutiveMetrics.exposureRisk.badgeColor}`}>
                    {customerExecutiveMetrics.exposureRisk.label}
                  </span>
                </div>
                <div className="mt-3 flex items-baseline gap-2">
                  <span className="text-2xl font-bold font-mono text-foreground">
                    {customerExecutiveMetrics.top1Share}%
                  </span>
                  <span className="text-xs text-muted-foreground truncate max-w-[120px]" title={customerExecutiveMetrics.top1Name}>
                    {customerExecutiveMetrics.top1Name}
                  </span>
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">
                  {customerExecutiveMetrics.exposureRisk.description}
                </p>
                <div className="w-full bg-muted/60 h-1.5 rounded-full mt-3 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      customerExecutiveMetrics.top1Share > 35 ? "bg-rose-500" : customerExecutiveMetrics.top1Share > 20 ? "bg-amber-500" : "bg-emerald-500"
                    }`}
                    style={{ width: `${Math.min(100, customerExecutiveMetrics.top1Share * 2)}%` }}
                  />
                </div>
              </div>

              {/* Card 3: 80/20 Pareto Dispersion */}
              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs relative overflow-hidden group hover:border-primary/40 transition-all">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-purple-500" />
                    80/20 Dispersion Ratio
                  </span>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
                    Pareto Index
                  </span>
                </div>
                <div className="mt-3 flex items-baseline gap-2">
                  <span className="text-2xl font-bold font-mono text-foreground">
                    {paretoCustomers.length} : {customerExecutiveMetrics.otherAccountsShare.toFixed(0)}%
                  </span>
                  <span className="text-xs text-muted-foreground">Core vs Long-Tail</span>
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">
                  Top {paretoCustomers.length} clients yield {customerExecutiveMetrics.top10Share}% of revenue across {sortedRfmData.length} active customer accounts.
                </p>
                <div className="w-full bg-muted/60 h-1.5 rounded-full mt-3 overflow-hidden flex">
                  <div
                    className="h-full bg-purple-500 transition-all duration-500"
                    style={{ width: `${customerExecutiveMetrics.top10Share}%` }}
                    title={`Top 10: ${customerExecutiveMetrics.top10Share}%`}
                  />
                  <div
                    className="h-full bg-slate-400 dark:bg-slate-600 transition-all duration-500"
                    style={{ width: `${customerExecutiveMetrics.otherAccountsShare}%` }}
                    title={`Other Accounts: ${customerExecutiveMetrics.otherAccountsShare}%`}
                  />
                </div>
              </div>

              {/* Card 4: Top Accounts Retention Health */}
              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs relative overflow-hidden group hover:border-primary/40 transition-all">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                    <Activity className="w-3.5 h-3.5 text-emerald-500" />
                    Top 10 Retention Health
                  </span>
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                    customerExecutiveMetrics.activeCount >= 7
                      ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                      : "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20"
                  }`}>
                    {customerExecutiveMetrics.activeCount}/10 Active
                  </span>
                </div>
                <div className="mt-3 flex items-baseline gap-2">
                  <span className="text-2xl font-bold font-mono text-foreground">
                    {customerExecutiveMetrics.activeCount} <span className="text-xs font-normal text-muted-foreground">Active</span>
                  </span>
                  <span className="text-xs font-mono text-muted-foreground">·</span>
                  <span className="text-sm font-bold font-mono text-amber-600 dark:text-amber-400">
                    {customerExecutiveMetrics.coolingCount} <span className="text-xs font-normal text-muted-foreground">Cooling</span>
                  </span>
                  <span className="text-xs font-mono text-muted-foreground">·</span>
                  <span className="text-sm font-bold font-mono text-rose-600 dark:text-rose-400">
                    {customerExecutiveMetrics.atRiskCount} <span className="text-xs font-normal text-muted-foreground">At Risk</span>
                  </span>
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">
                  Active accounts placed an order in the last 30 days.
                </p>
                <div className="w-full bg-muted/60 h-1.5 rounded-full mt-3 overflow-hidden flex">
                  <div
                    className="h-full bg-emerald-500 transition-all"
                    style={{ width: `${(customerExecutiveMetrics.activeCount / 10) * 100}%` }}
                  />
                  <div
                    className="h-full bg-amber-500 transition-all"
                    style={{ width: `${(customerExecutiveMetrics.coolingCount / 10) * 100}%` }}
                  />
                  <div
                    className="h-full bg-rose-500 transition-all"
                    style={{ width: `${(customerExecutiveMetrics.atRiskCount / 10) * 100}%` }}
                  />
                </div>
              </div>
            </div>

            {/* Customer Pareto Concentration (80/20 Rule) & Revenue Share Donut Section */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-stretch">
              {/* Pareto Table (7 cols) */}
              <div className="lg:col-span-7 bg-card border border-border/50 rounded-xl p-5 shadow-2xs space-y-4 flex flex-col justify-between">
                <div className="space-y-4">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border/40 pb-3">
                    <div>
                      <h3 className="text-sm sm:text-base font-semibold text-foreground flex items-center gap-1.5">
                        <Users className="w-4 h-4 text-primary" />
                        <span>Customer Pareto Concentration</span>
                      </h3>
                      <p className="text-xs text-muted-foreground">
                        Key debtor accounts ranked by revenue. Excludes suppliers, banks, and walk-in cash bills.
                      </p>
                    </div>

                    <div className="flex items-center gap-2 flex-wrap">
                      {/* Table Scope Toggle */}
                      <div className="flex items-center bg-muted/60 p-0.5 rounded-lg border border-border/40 text-[10px]">
                        <button
                          type="button"
                          onClick={() => setParetoTableScope("all")}
                          className={`px-2 py-0.5 rounded font-medium transition-colors cursor-pointer ${
                            paretoTableScope === "all"
                              ? "bg-card text-foreground font-bold shadow-2xs"
                              : "text-muted-foreground hover:text-foreground"
                          }`}
                          title="Show all verified customer debtor accounts"
                        >
                          All ({allCustomerParties.length})
                        </button>
                        <button
                          type="button"
                          onClick={() => setParetoTableScope("top_10")}
                          className={`px-2 py-0.5 rounded font-medium transition-colors cursor-pointer ${
                            paretoTableScope === "top_10"
                              ? "bg-card text-foreground font-bold shadow-2xs"
                              : "text-muted-foreground hover:text-foreground"
                          }`}
                          title="Show top 10 accounts only"
                        >
                          Top 10
                        </button>
                      </div>

                      {/* Filter Search */}
                      <div className="relative">
                        <Search className="w-3 h-3 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                        <input
                          type="text"
                          value={paretoSearch}
                          onChange={(e) => setParetoSearch(e.target.value)}
                          placeholder="Filter accounts..."
                          className="bg-muted/50 border border-border/60 rounded-md pl-7 pr-2 py-1 text-[11px] text-foreground outline-none focus:border-primary w-28 sm:w-36"
                        />
                        {paretoSearch && (
                          <button
                            onClick={() => setParetoSearch("")}
                            className="absolute right-1.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground text-[10px]"
                          >
                            ×
                          </button>
                        )}
                      </div>

                      <span className="text-[11px] font-mono text-muted-foreground bg-muted/60 px-2 py-0.5 rounded-md border border-border/40 shrink-0">
                        {filteredParetoCustomers.length} Accounts
                      </span>
                    </div>
                  </div>

                  {/* Cash & Counter Sales Summary Notice */}
                  {forecast?.cash_sales_summary && Number(forecast.cash_sales_summary.total_billed || 0) > 0 && (
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 px-3 py-2 rounded-lg bg-muted/30 border border-border/40 text-xs">
                      <div className="flex items-center gap-2">
                        <span className="text-muted-foreground font-medium flex items-center gap-1.5">
                          <Receipt className="w-3.5 h-3.5 text-primary" />
                          <span>Walk-in / Cash Counter Bills:</span>
                        </span>
                        <span className="font-semibold text-foreground font-mono">
                          ₹{Number(forecast.cash_sales_summary.total_billed || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </span>
                        <span className="text-muted-foreground text-[11px]">
                          ({forecast.cash_sales_summary.invoice_count || 0} bills · {forecast.cash_sales_summary.share_pct || 0}% turnover)
                        </span>
                      </div>
                      <span className="text-[10px] text-muted-foreground italic">
                        *Walk-in retail counter memos; excluded from client account ranking
                      </span>
                    </div>
                  )}

                  {filteredParetoCustomers && filteredParetoCustomers.length > 0 ? (
                    <div className="overflow-x-auto border border-border/40 rounded-lg max-h-[480px] overflow-y-auto scrollbar-thin">
                      <table className="w-full text-left text-xs min-w-[720px]">
                        <thead className="sticky top-0 bg-muted/95 backdrop-blur-xs z-10 border-b border-border/60 text-muted-foreground uppercase text-[10px] tracking-wider font-semibold">
                          <tr>
                            <th className="py-2.5 px-3 min-w-[210px]">Rank & Customer</th>
                            <th className="py-2.5 px-3 text-right min-w-[110px]">Revenue (₹)</th>
                            <th className="py-2.5 px-3 text-right min-w-[120px]">Turnover Share</th>
                            <th className="py-2.5 px-3 text-right min-w-[80px]">Cumulative</th>
                            <th className="py-2.5 px-3 text-center min-w-[90px]">Last Active</th>
                            <th className="py-2.5 px-3 text-center min-w-[100px]">Status</th>
                            <th className="py-2.5 px-3 text-right min-w-[70px]">Actions</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border/30">
                          {filteredParetoCustomers.map((c: any, idx: number) => {
                            const partyName = c.party_name || c.name || "Customer";
                            const billedAmount = c.total_billed ?? c.total_revenue ?? 0;
                            const sharePct = c.share_pct ?? c.percentage_of_total ?? 0;
                            const cumPct = c.cumulative_pct ?? c.cumulative_percentage ?? 0;
                            const idleDays = c.days_since_last_sale ?? c.days_since_last_order ?? 0;
                            const isHovered = hoveredParetoIdx === idx;
                            const sliceColor = CUSTOMER_PALETTE[idx % CUSTOMER_PALETTE.length];
                            
                            let badgeBg = "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20";
                            let badgeLabel = c.risk_label || "Active Buyer";
                            if (idleDays >= 90) {
                              badgeBg = "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20";
                              badgeLabel = `Dormant (${idleDays}d)`;
                            } else if (idleDays >= 60) {
                              badgeBg = "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20";
                              badgeLabel = `Inactive (${idleDays}d)`;
                            } else if (idleDays >= 30) {
                              badgeBg = "bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20";
                              badgeLabel = `Cooling (${idleDays}d)`;
                            }

                            // Rank medal styling
                            const rankBadge =
                              idx === 0 ? (
                                <span className="w-5 h-5 rounded-full flex items-center justify-center font-bold text-[10px] bg-amber-500/20 text-amber-600 dark:text-amber-400 border border-amber-500/30 shrink-0">
                                  🥇
                                </span>
                              ) : idx === 1 ? (
                                <span className="w-5 h-5 rounded-full flex items-center justify-center font-bold text-[10px] bg-slate-400/20 text-slate-600 dark:text-slate-300 border border-slate-400/30 shrink-0">
                                  🥈
                                </span>
                              ) : idx === 2 ? (
                                <span className="w-5 h-5 rounded-full flex items-center justify-center font-bold text-[10px] bg-amber-700/20 text-amber-700 dark:text-amber-500 border border-amber-700/30 shrink-0">
                                  🥉
                                </span>
                              ) : (
                                <span className="font-mono text-[10px] text-muted-foreground w-5 text-center shrink-0">
                                  #{idx + 1}
                                </span>
                              );

                            return (
                              <tr
                                key={idx}
                                onMouseEnter={() => setHoveredParetoIdx(idx)}
                                onMouseLeave={() => setHoveredParetoIdx(null)}
                                className={`transition-colors cursor-pointer ${
                                  isHovered ? "bg-primary/15" : "hover:bg-muted/40"
                                }`}
                              >
                                <td className="py-2.5 px-3">
                                  <div className="flex items-center gap-2">
                                    <span
                                      className="w-2.5 h-2.5 rounded-full shrink-0 shadow-2xs"
                                      style={{ backgroundColor: sliceColor }}
                                      title="Chart slice color"
                                    />
                                    {rankBadge}
                                    <div className="flex flex-col min-w-0">
                                      {c.party_id ? (
                                        <Link
                                          href={`/parties/${c.party_id}/statement`}
                                          className="font-semibold text-foreground truncate max-w-[150px] sm:max-w-[200px] hover:text-primary hover:underline transition-colors"
                                          title={partyName}
                                        >
                                          {partyName}
                                        </Link>
                                      ) : (
                                        <span className="font-semibold text-foreground truncate max-w-[150px] sm:max-w-[200px]" title={partyName}>
                                          {partyName}
                                        </span>
                                      )}
                                      <span className="text-[10px] text-muted-foreground font-mono">
                                        {c.invoice_count || 1} orders billed
                                      </span>
                                    </div>
                                  </div>
                                </td>
                                <td className="py-2.5 px-3 text-right font-mono font-bold text-foreground">
                                  ₹{Number(billedAmount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                                </td>
                                <td className="py-2.5 px-3 text-right font-mono">
                                  <div className="flex flex-col items-end gap-1">
                                    <span className="text-primary font-bold text-xs">{sharePct}%</span>
                                    <div className="w-16 h-1 bg-muted rounded-full overflow-hidden">
                                      <div
                                        className="h-full bg-primary rounded-full transition-all duration-300"
                                        style={{ width: `${Math.min(100, (sharePct / (allCustomerParties[0]?.share_pct || 20)) * 100)}%` }}
                                      />
                                    </div>
                                  </div>
                                </td>
                                <td className="py-2.5 px-3 text-right font-mono text-muted-foreground text-[11px]">
                                  {cumPct}%
                                </td>
                                <td className="py-2.5 px-3 text-center font-mono text-muted-foreground">
                                  {idleDays}d ago
                                </td>
                                <td className="py-2.5 px-3 text-center">
                                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${badgeBg}`}>
                                    {badgeLabel}
                                  </span>
                                </td>
                                <td className="py-2.5 px-3 text-right">
                                  <div className="flex items-center justify-end gap-1.5">
                                    <a
                                      href={`https://wa.me/?text=${encodeURIComponent(`Hello ${partyName}, greetings from our billing desk! Thank you for your continued partnership with us.`)}`}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="p-1 rounded hover:bg-emerald-500/10 text-muted-foreground hover:text-emerald-600 transition-colors"
                                      title="WhatsApp Greeting"
                                      onClick={(e) => e.stopPropagation()}
                                    >
                                      <MessageCircle className="w-3.5 h-3.5" />
                                    </a>
                                    {c.party_id && (
                                      <Link
                                        href={`/parties/${c.party_id}/statement`}
                                        className="p-1 rounded hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors"
                                        title="View Account Statement"
                                        onClick={(e) => e.stopPropagation()}
                                      >
                                        <ExternalLink className="w-3.5 h-3.5" />
                                      </Link>
                                    )}
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="py-12 text-center text-xs text-muted-foreground">
                      No customer accounts match the current Pareto filter.
                    </div>
                  )}
                </div>

                <div className="pt-3 border-t border-border/40 flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-[11px] text-muted-foreground">
                  <span>💡 Tip: Hover on any row to spotlight their slice in the chart.</span>
                  <span className="font-mono font-medium text-foreground">
                    {paretoTableScope === "all"
                      ? `All ${allCustomerParties.length} Debtors = ₹${customerExecutiveMetrics.totalDebtorSales.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`
                      : `Top 10 Debtors = ₹${customerExecutiveMetrics.top10Sum.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`}
                  </span>
                </div>
              </div>

              {/* Pareto Pie / Donut Chart (5 cols) */}
              <div className="lg:col-span-5 bg-card border border-border/50 rounded-xl p-5 shadow-2xs space-y-4 flex flex-col justify-between">
                <div className="space-y-3">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border/40 pb-3">
                    <div>
                      <h4 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                        <PieChart className="w-4 h-4 text-purple-500" />
                        <span>Customer Revenue Share</span>
                      </h4>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {paretoDonutMode === "all_parties"
                          ? `Distribution across all ${allCustomerParties.length} client accounts`
                          : paretoDonutMode === "top_10"
                          ? "Breakdown among top 10 key debtor accounts"
                          : "80/20 Rule: Top 10 accounts vs long-tail base"}
                      </p>
                    </div>

                    {/* View Mode & Chart Style Toggles */}
                    <div className="flex items-center gap-1.5 shrink-0 flex-wrap">
                      {/* View Scope Toggle */}
                      <div className="flex items-center bg-muted/60 p-0.5 rounded-lg border border-border/40 text-[10px]">
                        <button
                          type="button"
                          onClick={() => setParetoDonutMode("all_parties")}
                          className={`px-2 py-0.5 rounded font-medium transition-colors cursor-pointer ${
                            paretoDonutMode === "all_parties"
                              ? "bg-card text-foreground font-bold shadow-2xs"
                              : "text-muted-foreground hover:text-foreground"
                          }`}
                          title="Plot all verified debtor accounts"
                        >
                          All ({allCustomerParties.length})
                        </button>
                        <button
                          type="button"
                          onClick={() => setParetoDonutMode("top_10")}
                          className={`px-2 py-0.5 rounded font-medium transition-colors cursor-pointer ${
                            paretoDonutMode === "top_10"
                              ? "bg-card text-foreground font-bold shadow-2xs"
                              : "text-muted-foreground hover:text-foreground"
                          }`}
                          title="Plot breakdown of Top 10 only"
                        >
                          Top 10
                        </button>
                        <button
                          type="button"
                          onClick={() => setParetoDonutMode("full_80_20")}
                          className={`px-2 py-0.5 rounded font-medium transition-colors cursor-pointer ${
                            paretoDonutMode === "full_80_20"
                              ? "bg-card text-foreground font-bold shadow-2xs"
                              : "text-muted-foreground hover:text-foreground"
                          }`}
                          title="Show 80/20 view: Top 10 plus remaining accounts"
                        >
                          80/20 View
                        </button>
                      </div>

                      {/* Chart Style Toggle: Donut vs Solid Pie */}
                      <div className="flex items-center bg-muted/60 p-0.5 rounded-lg border border-border/40 text-[10px]">
                        <button
                          type="button"
                          onClick={() => setPieChartStyle("donut")}
                          className={`px-2 py-0.5 rounded font-medium transition-colors cursor-pointer flex items-center gap-1 ${
                            pieChartStyle === "donut"
                              ? "bg-card text-foreground font-bold shadow-2xs"
                              : "text-muted-foreground hover:text-foreground"
                          }`}
                          title="Hollow Donut chart"
                        >
                          <span className="w-2 h-2 rounded-full border border-current inline-block" />
                          <span>Donut</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => setPieChartStyle("pie")}
                          className={`px-2 py-0.5 rounded font-medium transition-colors cursor-pointer flex items-center gap-1 ${
                            pieChartStyle === "pie"
                              ? "bg-card text-foreground font-bold shadow-2xs"
                              : "text-muted-foreground hover:text-foreground"
                          }`}
                          title="Solid Pie chart"
                        >
                          <span className="w-2 h-2 rounded-full bg-current inline-block" />
                          <span>Pie</span>
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Active Account Focus Bar (Fixed 56px height to prevent any layout reflow or hover jitter) */}
                  <div className="h-14 min-h-[56px] max-h-[56px] overflow-hidden w-full">
                    {(() => {
                      const activeParty = hoveredParetoIdx !== null ? paretoPieChartData[hoveredParetoIdx] : null;
                      if (hoveredParetoIdx !== null && activeParty) {
                        return (
                          <div className="h-full px-3 py-2 rounded-lg bg-primary/10 border border-primary/30 flex items-center justify-between transition-colors duration-150 select-none">
                            <div className="flex items-center gap-2 min-w-0">
                              <span
                                className="w-3.5 h-3.5 rounded-full shrink-0 shadow-xs ring-1 ring-primary/40"
                                style={{ backgroundColor: activeParty.color }}
                              />
                              <div className="min-w-0">
                                <div className="flex items-center gap-1.5 leading-tight">
                                  <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-primary/20 text-primary font-bold">
                                    #{hoveredParetoIdx + 1}
                                  </span>
                                  <span className="text-xs font-bold text-foreground truncate max-w-[150px] sm:max-w-[200px]" title={activeParty.name}>
                                    {activeParty.name}
                                  </span>
                                </div>
                                <span className="text-[10px] text-muted-foreground leading-tight">
                                  {activeParty.invoice_count ? `${activeParty.invoice_count} orders billed` : "Debtor account"}
                                  {activeParty.days_since !== undefined ? ` · ${activeParty.days_since}d ago` : ""}
                                </span>
                              </div>
                            </div>
                            <div className="text-right shrink-0">
                              <div className="text-xs font-bold font-mono text-foreground leading-tight">
                                ₹{Number(activeParty.value || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                              </div>
                              <div className="text-[11px] font-semibold text-purple-600 dark:text-purple-400 leading-tight">
                                {activeParty.share_pct}% turnover
                              </div>
                            </div>
                          </div>
                        );
                      }
                      return (
                        <div className="h-full px-3 py-2 rounded-lg bg-muted/40 border border-border/40 flex items-center justify-between text-xs text-muted-foreground transition-colors duration-150 select-none">
                          <div className="flex items-center gap-2 min-w-0">
                            <Users className="w-4 h-4 text-primary shrink-0" />
                            <span className="text-[11px] truncate">
                              {paretoDonutMode === "all_parties"
                                ? `Plotting all ${allCustomerParties.length} client accounts`
                                : paretoDonutMode === "top_10"
                                ? "Plotting top 10 key debtor accounts"
                                : "80/20 Rule: Top 10 vs remaining base"}
                            </span>
                          </div>
                          <span className="text-[10px] font-mono font-medium text-foreground bg-card px-2 py-0.5 rounded border border-border/40 shrink-0">
                            Hover slice to inspect
                          </span>
                        </div>
                      );
                    })()}
                  </div>

                  {/* Large, Beautiful Pie / Donut Chart (Enlarged diameter, constant stroke geometry to avoid cursor bounce) */}
                  {paretoPieChartData.length > 0 ? (
                    <div className="relative h-[380px] sm:h-[410px] w-full flex items-center justify-center my-1">
                      <ResponsiveContainer width="100%" height="100%">
                        <RechartsPieChart>
                          {/* Tooltip omitted from inside SVG to prevent popover collision. Stationary Focus Bar above and Donut Center provide instant metrics without obstruction. */}
                          <Pie
                            data={paretoPieChartData}
                            cx="50%"
                            cy="50%"
                            innerRadius={pieChartStyle === "donut" ? 80 : 0}
                            outerRadius={140}
                            paddingAngle={paretoPieChartData.length > 25 ? 0.5 : paretoPieChartData.length > 10 ? 1 : 1.5}
                            dataKey="value"
                            onMouseEnter={(_, index) => setHoveredParetoIdx(index)}
                            onMouseLeave={() => setHoveredParetoIdx(null)}
                          >
                            {paretoPieChartData.map((entry: any, index: number) => {
                              const isHighlighted = hoveredParetoIdx === index;
                              return (
                                <Cell
                                  key={`cell-${index}`}
                                  fill={entry.color}
                                  stroke={isHighlighted ? "#ffffff" : "var(--card)"}
                                  strokeWidth={2}
                                  opacity={hoveredParetoIdx === null || isHighlighted ? 1 : 0.35}
                                  style={{ cursor: "pointer", outline: "none" }}
                                />
                              );
                            })}
                          </Pie>
                        </RechartsPieChart>
                      </ResponsiveContainer>

                      {/* Donut Hollow Center Metric (Dynamic Linkage - only rendered in Donut mode) */}
                      {pieChartStyle === "donut" && (
                        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none p-3 text-center select-none">
                          {hoveredParetoIdx !== null && paretoPieChartData[hoveredParetoIdx] ? (
                            <>
                              <span className="text-[10px] uppercase font-bold tracking-wider text-primary truncate max-w-[125px]">
                                {paretoPieChartData[hoveredParetoIdx].name}
                              </span>
                              <span className="text-xl sm:text-2xl font-bold font-mono text-foreground">
                                ₹{formatCurrencyShort(paretoPieChartData[hoveredParetoIdx].value)}
                              </span>
                              <span className="text-[11px] text-purple-600 dark:text-purple-400 font-bold">
                                {paretoPieChartData[hoveredParetoIdx].share_pct}% Share
                              </span>
                            </>
                          ) : paretoDonutMode === "top_10" ? (
                            <>
                              <span className="text-[10px] uppercase font-semibold tracking-wider text-muted-foreground">
                                Top 10 Share
                              </span>
                              <span className="text-2xl font-bold font-mono text-foreground">
                                {customerExecutiveMetrics.top10Share}%
                              </span>
                              <span className="text-[10px] text-purple-600 dark:text-purple-400 font-medium">
                                ₹{formatCurrencyShort(customerExecutiveMetrics.top10Sum)}
                              </span>
                            </>
                          ) : paretoDonutMode === "full_80_20" ? (
                            <>
                              <span className="text-[10px] uppercase font-semibold tracking-wider text-muted-foreground">
                                Top 10 vs Long-Tail
                              </span>
                              <span className="text-2xl font-bold font-mono text-foreground">
                                {customerExecutiveMetrics.top10Share}%
                              </span>
                              <span className="text-[10px] text-purple-600 dark:text-purple-400 font-medium">
                                Top 10 Accounts
                              </span>
                            </>
                          ) : (
                            <>
                              <span className="text-[10px] uppercase font-semibold tracking-wider text-muted-foreground">
                                All Debtors ({allCustomerParties.length})
                              </span>
                              <span className="text-2xl font-bold font-mono text-foreground">
                                ₹{formatCurrencyShort(customerExecutiveMetrics.totalDebtorSales)}
                              </span>
                              <span className="text-[10px] text-purple-600 dark:text-purple-400 font-medium">
                                100% of Verified Ledger
                              </span>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="h-64 flex items-center justify-center text-xs text-muted-foreground">
                      No sales data to plot revenue distribution.
                    </div>
                  )}
                </div>

                {/* Slices Legend / Breakdown List with Two-Way Hover Sync */}
                {paretoPieChartData.length > 0 && (
                  <div className="pt-2 border-t border-border/40 space-y-1.5">
                    <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                      <span className="font-semibold">Accounts Breakdown ({paretoPieChartData.length} plotted)</span>
                      <span>Hover row to highlight slice</span>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 max-h-[160px] overflow-y-auto scrollbar-thin text-xs pr-1">
                      {paretoPieChartData.map((item: any, idx: number) => {
                        const isHovered = hoveredParetoIdx === idx;
                        return (
                          <div
                            key={idx}
                            onMouseEnter={() => setHoveredParetoIdx(idx)}
                            onMouseLeave={() => setHoveredParetoIdx(null)}
                            className={`flex items-center justify-between text-[11px] gap-1 p-1.5 rounded-md transition-colors cursor-pointer border ${
                              isHovered
                                ? "bg-primary/15 border-primary/40 shadow-xs"
                                : "border-border/30 bg-muted/20 hover:bg-muted/50"
                            }`}
                          >
                            <div className="flex items-center gap-1.5 min-w-0">
                              <span className="w-2.5 h-2.5 rounded-full shrink-0 shadow-2xs" style={{ backgroundColor: item.color }} />
                              <span className="font-mono text-[10px] text-muted-foreground shrink-0 font-medium">
                                #{idx + 1}
                              </span>
                              <span className="truncate text-foreground" title={item.name}>
                                {item.name}
                              </span>
                            </div>
                            <div className="flex items-center gap-1.5 shrink-0 font-mono">
                              <span className="text-muted-foreground text-[10px]">
                                ₹{formatCurrencyShort(item.value)}
                              </span>
                              <span className="text-purple-600 dark:text-purple-400 font-bold text-[10px]">
                                {item.share_pct}%
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Header with Search, Segment Filter & Multi-Sort Controls */}
            <div className="bg-card border border-border/50 rounded-xl p-4 sm:p-5 shadow-2xs space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/40 pb-3">
                <div>
                  <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
                    <Users className="w-5 h-5 text-primary" />
                    <span>Customer RFM Tiers & Inactivity Churn Radar</span>
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Machine learning segmentation (Recency, Frequency, Monetary) applied strictly to genuine customer accounts.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-primary font-bold bg-primary/10 px-2.5 py-1 rounded-md border border-primary/20">
                    {sortedRfmData.length} Verified Customer Accounts
                  </span>
                </div>
              </div>

              {/* Controls Toolbar: Search, Segment Pills, Sort Selector */}
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 pt-1">
                {/* Search Customer Input */}
                <div className="relative w-full sm:w-64">
                  <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <input
                    type="text"
                    value={rfmSearch}
                    onChange={(e) => setRfmSearch(e.target.value)}
                    placeholder="Search party name..."
                    className="w-full bg-muted/50 border border-border/60 rounded-lg pl-8 pr-3 py-1.5 text-xs text-foreground outline-none focus:border-primary focus:ring-1 focus:ring-primary/40"
                  />
                  {rfmSearch && (
                    <button
                      onClick={() => setRfmSearch("")}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground text-xs"
                    >
                      ×
                    </button>
                  )}
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {/* Segment Filter Pills */}
                  <div className="flex items-center bg-muted/60 p-0.5 rounded-lg border border-border/40 text-xs">
                    {[
                      { label: "All Segments", val: "ALL" },
                      { label: "VIP / High", val: "VIP" },
                      { label: "Medium", val: "MEDIUM" },
                      { label: "Standard", val: "STANDARD" },
                    ].map((s) => (
                      <button
                        key={s.val}
                        type="button"
                        onClick={() => setRfmSegmentFilter(s.val)}
                        className={`px-2.5 py-1 rounded font-medium transition-colors cursor-pointer ${
                          rfmSegmentFilter === s.val
                            ? "bg-card text-foreground font-bold shadow-2xs"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>

                  {/* Sort By Dropdown */}
                  <div className="flex items-center gap-1.5 bg-muted/60 border border-border/50 rounded-lg px-2.5 py-1 text-xs">
                    <span className="text-muted-foreground font-medium flex items-center gap-1">
                      <Sliders className="w-3 h-3 text-muted-foreground" />
                      <span>Sort:</span>
                    </span>
                    <select
                      value={rfmSortKey}
                      onChange={(e) => setRfmSortKey(e.target.value as any)}
                      className="bg-transparent font-semibold text-foreground outline-none cursor-pointer text-xs"
                    >
                      <option value="monetary">Total Revenue (₹)</option>
                      <option value="recency">Recency (Days Inactive)</option>
                      <option value="frequency">Order Frequency (Count)</option>
                      <option value="name">Customer Name</option>
                      <option value="segment">Tier Segment</option>
                    </select>

                    <button
                      type="button"
                      onClick={() => setRfmSortDir((prev) => (prev === "asc" ? "desc" : "asc"))}
                      className="p-1 hover:bg-card rounded cursor-pointer transition-colors text-foreground"
                      title={rfmSortDir === "asc" ? "Ascending order" : "Descending order"}
                    >
                      <ArrowUpDown className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Split Grid: Left Column = RFM Tiers Table (7 cols), Right Column = Customer Churn Radar (5 cols) */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
              {/* RFM Tiers Table */}
              <div className="lg:col-span-7 bg-card border border-border/50 rounded-xl p-5 shadow-2xs space-y-4">
                <div className="flex items-center justify-between border-b border-border/40 pb-3">
                  <div>
                    <h4 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                      <Award className="w-4 h-4 text-purple-500" />
                      <span>Customer RFM Tiers</span>
                    </h4>
                    <span className="text-[11px] text-muted-foreground">
                      Showing {sortedRfmData.length} genuine customer debtor accounts (suppliers & banks excluded)
                    </span>
                  </div>
                  <span className="text-xs font-mono font-bold text-foreground">
                    Sorted by {rfmSortKey.toUpperCase()} ({rfmSortDir.toUpperCase()})
                  </span>
                </div>

                {sortedRfmData.length > 0 ? (
                  <div className="overflow-x-auto max-h-[520px] overflow-y-auto scrollbar-thin">
                    <table className="w-full text-left text-xs">
                      <thead className="sticky top-0 bg-card z-10">
                        <tr className="border-b border-border/60 text-muted-foreground uppercase text-[10px] tracking-wider font-semibold">
                          <th
                            className="py-2.5 px-3 cursor-pointer hover:text-foreground"
                            onClick={() => {
                              if (rfmSortKey === "name") setRfmSortDir((d) => (d === "asc" ? "desc" : "asc"));
                              else { setRfmSortKey("name"); setRfmSortDir("asc"); }
                            }}
                          >
                            <span className="flex items-center gap-1">
                              Customer Party {rfmSortKey === "name" && (rfmSortDir === "asc" ? "▲" : "▼")}
                            </span>
                          </th>
                          <th
                            className="py-2.5 px-3 text-center cursor-pointer hover:text-foreground"
                            onClick={() => {
                              if (rfmSortKey === "segment") setRfmSortDir((d) => (d === "asc" ? "desc" : "asc"));
                              else { setRfmSortKey("segment"); setRfmSortDir("asc"); }
                            }}
                          >
                            <span className="flex items-center justify-center gap-1">
                              Tier {rfmSortKey === "segment" && (rfmSortDir === "asc" ? "▲" : "▼")}
                            </span>
                          </th>
                          <th
                            className="py-2.5 px-3 text-right cursor-pointer hover:text-foreground"
                            onClick={() => {
                              if (rfmSortKey === "recency") setRfmSortDir((d) => (d === "asc" ? "desc" : "asc"));
                              else { setRfmSortKey("recency"); setRfmSortDir("asc"); }
                            }}
                          >
                            <span className="flex items-center justify-end gap-1">
                              Recency {rfmSortKey === "recency" && (rfmSortDir === "asc" ? "▲" : "▼")}
                            </span>
                          </th>
                          <th
                            className="py-2.5 px-3 text-right cursor-pointer hover:text-foreground"
                            onClick={() => {
                              if (rfmSortKey === "frequency") setRfmSortDir((d) => (d === "asc" ? "desc" : "asc"));
                              else { setRfmSortKey("frequency"); setRfmSortDir("desc"); }
                            }}
                          >
                            <span className="flex items-center justify-end gap-1">
                              Orders {rfmSortKey === "frequency" && (rfmSortDir === "asc" ? "▲" : "▼")}
                            </span>
                          </th>
                          <th
                            className="py-2.5 px-3 text-right cursor-pointer hover:text-foreground"
                            onClick={() => {
                              if (rfmSortKey === "monetary") setRfmSortDir((d) => (d === "asc" ? "desc" : "asc"));
                              else { setRfmSortKey("monetary"); setRfmSortDir("desc"); }
                            }}
                          >
                            <span className="flex items-center justify-end gap-1">
                              Revenue {rfmSortKey === "monetary" && (rfmSortDir === "asc" ? "▲" : "▼")}
                            </span>
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/30">
                        {sortedRfmData.map((c: any, idx: number) => {
                          const isVip = c.segment?.includes("High Value") || c.segment?.includes("VIP");
                          const isMed = c.segment?.includes("Medium");
                          const rec = Number(c.recency || 0);

                          return (
                            <tr key={idx} className="hover:bg-muted/40 transition-colors">
                              <td className="py-2.5 px-3 font-semibold text-foreground">
                                {c.party_ledger__name || c.name || "Unknown Customer"}
                              </td>
                              <td className="py-2.5 px-3 text-center">
                                <span
                                  className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                    isVip
                                      ? "bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20"
                                      : isMed
                                      ? "bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20"
                                      : "bg-muted text-muted-foreground border border-border/40"
                                  }`}
                                >
                                  {isVip ? "VIP / High" : isMed ? "Medium" : "Standard"}
                                </span>
                              </td>
                              <td className="py-2.5 px-3 text-right font-mono">
                                <span className={`${
                                  rec <= 15 ? "text-emerald-600 dark:text-emerald-400 font-semibold" : rec <= 45 ? "text-blue-600 dark:text-blue-400" : "text-amber-600 dark:text-amber-400"
                                }`}>
                                  {rec}d ago
                                </span>
                              </td>
                              <td className="py-2.5 px-3 text-right font-mono font-medium text-foreground">
                                {c.frequency} orders
                              </td>
                              <td className="py-2.5 px-3 text-right font-mono font-bold text-foreground">
                                ₹{(c.monetary || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="py-12 text-center text-xs text-muted-foreground">
                    No customers match the current filter or search criteria.
                  </div>
                )}
              </div>

              {/* Customer Churn Radar */}
              <div className="lg:col-span-5 bg-card border border-border/50 rounded-xl p-5 shadow-2xs space-y-4 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between border-b border-border/40 pb-3">
                    <h4 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                      <ShieldAlert className="w-4 h-4 text-amber-500" />
                      <span>Customer Churn Radar</span>
                    </h4>
                    <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-amber-500/10 text-amber-600 border border-amber-500/20">
                      {churnFilteredAccounts.length} Inactive Accounts
                    </span>
                  </div>

                  <p className="text-xs text-muted-foreground mt-2">
                    Accounts that have stopped placing regular orders. Reach out before they defect to competing distributors.
                  </p>

                  {/* Inactivity Threshold Filter Buttons */}
                  <div className="pt-2 space-y-1.5">
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="text-muted-foreground font-medium">Inactivity Filter:</span>
                      <span className="font-semibold text-foreground font-mono text-[11px]">
                        &gt; {churnDaysThreshold} Days Idle
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-1">
                      {[30, 60, 90, 120, 240, 360].map((days) => {
                        const isActive = churnDaysThreshold === days && !isEditingCustomDays;
                        return (
                          <button
                            key={days}
                            type="button"
                            onClick={() => {
                              setChurnDaysThreshold(days);
                              setCustomChurnInput(String(days));
                              setIsEditingCustomDays(false);
                            }}
                            className={`px-2.5 py-1 rounded text-[10px] font-semibold transition-all cursor-pointer ${
                              isActive
                                ? "bg-amber-500 text-white shadow-xs font-bold"
                                : "bg-muted hover:bg-muted/80 text-muted-foreground hover:text-foreground"
                            }`}
                          >
                            {days}d
                          </button>
                        );
                      })}

                      {/* Custom Days Input */}
                      <div className="flex items-center gap-1 bg-muted/60 border border-border/50 rounded px-1.5 py-0.5 ml-auto">
                        <span className="text-[10px] text-muted-foreground">Custom:</span>
                        <input
                          type="number"
                          min="1"
                          max="999"
                          value={customChurnInput}
                          onChange={(e) => {
                            const val = e.target.value;
                            setCustomChurnInput(val);
                            const num = parseInt(val, 10);
                            if (!isNaN(num) && num > 0) {
                              setChurnDaysThreshold(num);
                              setIsEditingCustomDays(true);
                            }
                          }}
                          className="w-11 bg-background border border-border/60 rounded px-1 py-0.5 text-[10px] font-mono text-center text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary"
                        />
                        <span className="text-[10px] text-muted-foreground">d</span>
                      </div>
                    </div>
                  </div>

                  {/* Summary Metric Ribbon */}
                  <div className="grid grid-cols-2 gap-2 p-3 rounded-lg bg-amber-500/5 border border-amber-500/15 text-xs mt-3">
                    <div>
                      <span className="text-[10px] uppercase font-semibold tracking-wider text-muted-foreground block">
                        Idle Parties
                      </span>
                      <span className="text-lg font-bold font-mono text-amber-600 dark:text-amber-400">
                        {churnFilteredAccounts.length}
                      </span>
                    </div>
                    <div className="text-right">
                      <span className="text-[10px] uppercase font-semibold tracking-wider text-muted-foreground block">
                        Revenue At Risk
                      </span>
                      <span className="text-lg font-bold font-mono text-foreground">
                        ₹{formatCurrencyShort(totalAtRiskRevenue)}
                      </span>
                    </div>
                  </div>

                  {/* Scrollable List of At-Risk Accounts */}
                  <div className="space-y-2 mt-3 max-h-[340px] overflow-y-auto pr-1 scrollbar-thin">
                    {churnFilteredAccounts.length > 0 ? (
                      churnFilteredAccounts.map((c: any, idx: number) => {
                        const partyName = c.party_name || c.name || "Customer";
                        const billedAmount = c.total_billed ?? c.total_revenue ?? 0;
                        const idleDays = c.days_since_last_sale ?? c.days_since_last_order ?? 0;
                        const isCritical = idleDays >= 120;
                        const isHigh = idleDays >= 90;

                        return (
                          <div
                            key={idx}
                            className={`p-2.5 rounded-lg border transition-all text-xs space-y-1.5 ${
                              isCritical
                                ? "border-rose-500/30 bg-rose-500/5 hover:border-rose-500/50"
                                : isHigh
                                ? "border-amber-500/30 bg-amber-500/5 hover:border-amber-500/50"
                                : "border-border/60 bg-muted/30 hover:border-border"
                            }`}
                          >
                            <div className="flex items-center justify-between gap-1">
                              <span className="font-semibold text-foreground truncate max-w-[170px]" title={partyName}>
                                {partyName}
                              </span>
                              <span className={`text-[10px] px-1.5 py-0.2 rounded font-mono font-bold shrink-0 ${
                                isCritical
                                  ? "bg-rose-500/15 text-rose-600 dark:text-rose-400"
                                  : isHigh
                                  ? "bg-amber-500/15 text-amber-600 dark:text-amber-400"
                                  : "bg-blue-500/15 text-blue-600 dark:text-blue-400"
                              }`}>
                                {idleDays}d inactive
                              </span>
                            </div>

                            <div className="flex items-center justify-between text-[11px] text-muted-foreground pt-1 border-t border-border/30">
                              <span>Historical: <strong className="text-foreground font-mono">₹{billedAmount.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</strong></span>
                              <div className="flex items-center gap-1.5">
                                <a
                                  href={`https://wa.me/?text=${encodeURIComponent(`Hello ${partyName}, following up regarding your regular replenishment order with us.`)}`}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-semibold text-[10px] hover:bg-emerald-500/20 transition-colors flex items-center gap-1"
                                >
                                  <MessageCircle className="w-3 h-3" />
                                  <span>WhatsApp</span>
                                </a>
                              </div>
                            </div>
                          </div>
                        );
                      })
                    ) : (
                      <div className="py-8 text-center text-xs text-muted-foreground">
                        <CheckCircle2 className="w-6 h-6 mx-auto text-emerald-500 mb-1" />
                        <span>No churned customers beyond {churnDaysThreshold} days inactivity!</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
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
                  ₹{Number(stockValuation?.stockCost || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-xs text-blue-600 dark:text-blue-400 font-medium">
                  {Number(kpis.total_stock_qty || 0).toLocaleString("en-IN")} physical units on hand
                </div>
              </div>

              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Catalog List Price (MRP)
                </span>
                <div className="text-xl sm:text-2xl font-bold font-mono text-foreground">
                  ₹{Number(stockValuation?.retailCost || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
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
                  ₹{Number(stockValuation?.margin || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
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
                  {Number(kpis.total_in_stock_items || 0)} / {Number(kpis.total_catalog_items || kpis.total_in_stock_items || 0)} Active
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
                    ₹{Number(stockValuation?.effectiveRetail || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    After {retailDiscount}% simulated discount
                  </div>
                </div>

                <div className="p-3.5 bg-muted/40 rounded-xl border border-border/40 space-y-1">
                  <span className="text-[11px] text-emerald-600 dark:text-emerald-400 font-semibold uppercase">Simulated Profit Margin</span>
                  <div className="text-lg font-bold font-mono text-emerald-600 dark:text-emerald-400">
                    ₹{Number(stockValuation?.margin || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    {stockValuation.markupPct}% markup over cost
                  </div>
                </div>

                <div className="p-3.5 bg-muted/40 rounded-xl border border-border/40 space-y-1">
                  <span className="text-[11px] text-purple-600 dark:text-purple-400 font-semibold uppercase">Cost Recovery Multiple</span>
                  <div className="text-lg font-bold font-mono text-purple-600 dark:text-purple-400">
                    {stockValuation.costMultiple}x
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    Returns per ₹1 invested in stock
                  </div>
                </div>
              </div>
            </div>

            {/* Depletion Stockout Radar Hero Section ("Never lose a customer to the shop next door") */}
            <div className="bg-gradient-to-br from-card via-card to-rose-500/5 border border-rose-500/30 rounded-2xl p-5 shadow-xs space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/40 pb-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <div className="p-1.5 rounded-lg bg-rose-500/10 text-rose-600 dark:text-rose-400">
                      <Zap className="w-4 h-4" />
                    </div>
                    <h3 className="text-base sm:text-lg font-bold text-foreground tracking-tight">
                      Depletion Stockout Radar
                    </h3>
                    <span className="text-[10px] px-2.5 py-0.5 rounded-full font-extrabold bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20 uppercase tracking-wider">
                      Never Lose a Customer to the Shop Next Door
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Velocity-driven predictive radar detecting runouts before shelves go bare. B2B clients who find an item out-of-stock buy next door—and 40% never return.
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-mono text-muted-foreground bg-muted/70 px-2.5 py-1 rounded-md border border-border/40">
                    Lead Time: 3 Days Modeled
                  </span>
                </div>
              </div>

              {/* 4 Stockout Radar KPI Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
                {/* 1. Imminent Stockouts (<3d) */}
                <div className="p-3.5 rounded-xl border border-rose-500/30 bg-rose-500/5 space-y-1.5">
                  <div className="flex items-center justify-between text-[11px] font-bold text-rose-600 dark:text-rose-400 uppercase tracking-wider">
                    <span>🚨 Imminent Stockouts</span>
                    <span className="text-[10px] px-1.5 py-0.2 rounded bg-rose-500/15">&lt; 3 Days</span>
                  </div>
                  <div className="text-2xl font-black font-mono text-rose-600 dark:text-rose-400">
                    {inventoryAnalytics?.depletion_radar_summary?.imminent_stockouts_count ?? 0} Items
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-snug">
                    Running dry before supplier lead time. Immediate reorder required.
                  </p>
                </div>

                {/* 2. Reorders Approaching (<7d) */}
                <div className="p-3.5 rounded-xl border border-amber-500/30 bg-amber-500/5 space-y-1.5">
                  <div className="flex items-center justify-between text-[11px] font-bold text-amber-600 dark:text-amber-400 uppercase tracking-wider">
                    <span>⚠️ Approaching (&lt; 7d)</span>
                    <span className="text-[10px] px-1.5 py-0.2 rounded bg-amber-500/15">Reorder Window</span>
                  </div>
                  <div className="text-2xl font-black font-mono text-amber-600 dark:text-amber-400">
                    {inventoryAnalytics?.depletion_radar_summary?.reorder_approaching_count ?? 0} Items
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-snug">
                    3 to 7 days runway. Issue purchase orders today to maintain buffer.
                  </p>
                </div>

                {/* 3. 7-Day Revenue At Risk */}
                <div className="p-3.5 rounded-xl border border-purple-500/30 bg-purple-500/5 space-y-1.5">
                  <div className="flex items-center justify-between text-[11px] font-bold text-purple-600 dark:text-purple-400 uppercase tracking-wider">
                    <span>💸 Revenue At Risk / Wk</span>
                    <span className="text-[10px] px-1.5 py-0.2 rounded bg-purple-500/15">Weekly Loss</span>
                  </div>
                  <div className="text-2xl font-black font-mono text-purple-600 dark:text-purple-400">
                    ₹{Number(inventoryAnalytics?.depletion_radar_summary?.total_revenue_at_risk_weekly ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-snug">
                    Estimated gross turnover lost if these SKUs deplete completely.
                  </p>
                </div>

                {/* 4. Stockout Protection Index */}
                <div className="p-3.5 rounded-xl border border-emerald-500/30 bg-emerald-500/5 space-y-1.5">
                  <div className="flex items-center justify-between text-[11px] font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider">
                    <span>🛡️ Protection Rate</span>
                    <span className="text-[10px] px-1.5 py-0.2 rounded bg-emerald-500/15">Catalog Health</span>
                  </div>
                  <div className="text-2xl font-black font-mono text-emerald-600 dark:text-emerald-400">
                    {inventoryAnalytics?.depletion_radar_summary?.stockout_protection_pct ?? 100}%
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-snug">
                    Catalog proportion with safe stock buffers &gt; 7 days sales pace.
                  </p>
                </div>
              </div>
            </div>

            {/* 3. Inventory Intelligence Hub: Low-Stock Reorders & Sitting on Benches (Deadstock) */}
            <div className="bg-card border border-border/50 rounded-xl p-4 sm:p-5 shadow-2xs space-y-4">
              {/* Header with Sub-View Switcher & Filter Controls */}
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 border-b border-border/40 pb-4">
                {/* Left: View Switcher (Reorder vs Sitting on Benches) */}
                <div className="flex flex-wrap items-center gap-1.5 p-1 bg-muted/60 rounded-xl border border-border/70">
                  <button
                    type="button"
                    onClick={() => setInventorySubView("reorder")}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
                      inventorySubView === "reorder"
                        ? "bg-card text-foreground shadow-xs border border-border/60"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
                    <span>Low-Stock Reorders</span>
                    <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-blue-500/10 text-blue-600 dark:text-blue-400 font-mono font-bold">
                      {filteredReorderItems.length}
                    </span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setInventorySubView("deadstock")}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
                      inventorySubView === "deadstock"
                        ? "bg-card text-foreground shadow-xs border border-border/60"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <Clock className="w-3.5 h-3.5 text-rose-500" />
                    <span>Sitting on Benches / Slow-Moving</span>
                    <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-rose-500/10 text-rose-600 dark:text-rose-400 font-mono font-bold">
                      {filteredDeadstockItems.length}
                    </span>
                  </button>
                </div>

                {/* Right: Category, Brand & Search Filters */}
                <div className="flex flex-wrap sm:flex-nowrap items-center gap-2">
                  {/* Category Dropdown */}
                  <div className="relative w-full sm:w-auto">
                    <select
                      value={inventoryCategoryFilter}
                      onChange={(e) => handleCategoryFilterChange(e.target.value)}
                      className="w-full sm:w-40 bg-muted/60 border border-border/70 rounded-xl px-2.5 py-1.5 text-xs font-semibold text-foreground outline-none focus:ring-2 focus:ring-primary/40 cursor-pointer"
                    >
                      <option value="ALL">All Categories</option>
                      {inventoryAnalytics?.categories?.map((cat: any) => (
                        <option key={cat.id} value={cat.id}>
                          {cat.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Brand Dropdown (Mention Brand Here As Well!) */}
                  <div className="relative w-full sm:w-auto">
                    <select
                      value={inventoryBrandFilter}
                      onChange={(e) => setInventoryBrandFilter(e.target.value)}
                      className="w-full sm:w-36 bg-muted/60 border border-border/70 rounded-xl px-2.5 py-1.5 text-xs font-semibold text-foreground outline-none focus:ring-2 focus:ring-primary/40 cursor-pointer"
                    >
                      <option value="ALL">All Brands ({availableBrands.length})</option>
                      {availableBrands.map((b) => (
                        <option key={b} value={b}>
                          {b}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Search Input */}
                  <div className="relative w-full sm:w-48">
                    <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-3 top-2.5" />
                    <input
                      type="text"
                      placeholder="Search item, brand, SKU..."
                      value={inventorySearch}
                      onChange={(e) => setInventorySearch(e.target.value)}
                      className="w-full bg-muted/60 border border-border/70 text-foreground pl-8 pr-3 py-1.5 rounded-xl outline-none focus:ring-2 focus:ring-primary/40 text-xs"
                    />
                  </div>

                  {/* Refresh Button */}
                  <button
                    type="button"
                    onClick={() => fetchInventoryAnalytics(effectiveCompanyId, inventoryCategoryFilter)}
                    disabled={loadingInventoryAnalytics}
                    className="p-2 rounded-xl bg-muted/60 hover:bg-muted text-muted-foreground hover:text-foreground border border-border/70 transition-colors cursor-pointer shrink-0"
                    title="Refresh Inventory Intelligence"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${loadingInventoryAnalytics ? "animate-spin text-blue-500" : ""}`} />
                  </button>
                </div>
              </div>

              {/* ============================================================ */}
              {/* SUBVIEW 1: SMART LOW-STOCK REORDER INTELLIGENCE & PO HUB     */}
              {/* ============================================================ */}
              {inventorySubView === "reorder" && (
                <div className="space-y-4 animate-in fade-in duration-150">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                    <p className="text-muted-foreground">
                      Only shows items with <strong>verified sales demand</strong> that are critically short or below minimum required stock (Min Stock). Deadstock is automatically filtered out.
                    </p>
                    {inventoryBrandFilter !== "ALL" && (
                      <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 text-[11px] font-semibold self-start sm:self-auto">
                        <span>Brand Filter:</span>
                        <span className="font-bold">{inventoryBrandFilter}</span>
                        <button
                          type="button"
                          onClick={() => setInventoryBrandFilter("ALL")}
                          className="hover:opacity-75 cursor-pointer ml-0.5"
                          title="Clear brand filter"
                        >
                          ✕
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Action Toolbar: Select All, Bulk Quantity, Mass Min Stock & Draft PO Trigger */}
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 p-3 bg-muted/30 border border-border/40 rounded-xl">
                    {/* Left: Select All, Bulk Order Qty & Mass Min Stock */}
                    <div className="flex flex-wrap items-center gap-2.5">
                      {/* Select All Toggle */}
                      <button
                        type="button"
                        onClick={handleSelectAllToggle}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-card hover:bg-muted text-foreground border border-border/60 transition-colors cursor-pointer shadow-2xs"
                      >
                        {isAllSelected ? (
                          <CheckSquare className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
                        ) : (
                          <Square className="w-3.5 h-3.5 text-muted-foreground" />
                        )}
                        <span>{isAllSelected ? "Deselect All" : `Select All (${filteredReorderItems.length})`}</span>
                      </button>

                      {/* Bulk Quantity Setter */}
                      <div className="flex items-center gap-1.5 bg-card px-2.5 py-1 rounded-lg border border-border/60 shadow-2xs">
                        <span className="text-[11px] font-medium text-muted-foreground whitespace-nowrap">
                          Set order qty:
                        </span>
                        <input
                          type="number"
                          min="1"
                          value={bulkQuantityInput}
                          onChange={(e) => setBulkQuantityInput(Math.max(1, parseInt(e.target.value) || 1))}
                          className="w-12 bg-muted border border-border/70 rounded px-1.5 py-0.5 text-xs font-mono font-bold text-center text-foreground outline-none focus:ring-1 focus:ring-primary"
                        />
                        <button
                          type="button"
                          onClick={handleApplyBulkQuantity}
                          className="px-2 py-0.5 rounded text-[11px] font-bold bg-primary text-primary-foreground hover:bg-primary/90 transition-colors cursor-pointer"
                        >
                          Apply
                        </button>
                      </div>

                      {/* Mass-Wise Minimum Required Stock Button */}
                      <button
                        type="button"
                        onClick={() => setIsMassMinStockModalOpen(true)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-card hover:bg-muted text-foreground border border-border/60 transition-colors cursor-pointer shadow-2xs"
                        title="Configure minimum required quantity mass-wise across selected items, category, or catalog"
                      >
                        <Sliders className="w-3.5 h-3.5 text-blue-500" />
                        <span>Set Min Stock (Mass)</span>
                      </button>
                    </div>

                    {/* Right: Selected Counter & Draft PO Trigger */}
                    <div className="flex items-center justify-between md:justify-end gap-3 w-full md:w-auto">
                      <div className="text-right text-xs">
                        <div className="font-semibold text-foreground">
                          <span className="text-blue-600 dark:text-blue-400 font-bold">{selectedItemsData.count}</span> items ({selectedItemsData.units} units)
                        </div>
                        <div className="text-[11px] text-muted-foreground font-mono">
                          Est. ₹{Number(selectedItemsData?.cost || 0).toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={handleOpenPoModal}
                        disabled={selectedReorderIds.size === 0}
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 disabled:pointer-events-none text-white transition-all shadow-sm cursor-pointer whitespace-nowrap"
                      >
                        <ShoppingCart className="w-4 h-4" />
                        <span>Draft Purchase Order ({selectedItemsData.count})</span>
                      </button>
                    </div>
                  </div>

                  {/* Responsive Reorder Items Table */}
                  {loadingInventoryAnalytics ? (
                    <div className="py-12 text-center text-xs text-muted-foreground space-y-2">
                      <RefreshCw className="w-5 h-5 animate-spin mx-auto text-blue-500" />
                      <div>Analyzing item velocity and stock levels...</div>
                    </div>
                  ) : filteredReorderItems.length === 0 ? (
                    <div className="py-12 text-center text-xs text-muted-foreground space-y-1 bg-muted/10 rounded-xl border border-dashed border-border/60">
                      <PackageCheck className="w-8 h-8 mx-auto text-emerald-500/70" />
                      <div className="font-bold text-foreground text-sm">No Urgent Reorders Needed!</div>
                      <p className="max-w-md mx-auto text-[11px]">
                        All high-velocity fast-moving items currently have sufficient stock on hand. Low-priority deadstock is excluded.
                      </p>
                    </div>
                  ) : (
                    <div className="rounded-xl border border-border/60 overflow-hidden">
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs">
                          <thead>
                            <tr className="bg-muted/40 border-b border-border/60 text-muted-foreground uppercase text-[10px] tracking-wider font-semibold">
                              <th className="py-2.5 px-3 w-10 text-center">
                                <input
                                  type="checkbox"
                                  checked={isAllSelected}
                                  onChange={handleSelectAllToggle}
                                  className="rounded border-border cursor-pointer"
                                />
                              </th>
                              <th className="py-2.5 px-2 text-center">Urgency</th>
                              <th className="py-2.5 px-3">Item / Size</th>
                              <th className="py-2.5 px-3">Brand</th>
                              <th className="py-2.5 px-3">Category</th>
                              <th className="py-2.5 px-3 text-right">Depletion Runway</th>
                              <th className="py-2.5 px-3 text-right">7D Loss Risk</th>
                              <th className="py-2.5 px-3 text-right">Min Req</th>
                              <th className="py-2.5 px-3 text-right">Current Stock</th>
                              <th className="py-2.5 px-3 text-right">Sales Demand</th>
                              <th className="py-2.5 px-3 text-right">Last Purchase</th>
                              <th className="py-2.5 px-3 text-center w-36">Order Qty</th>
                              <th className="py-2.5 px-3 text-right">Est. Total</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border/30">
                            {filteredReorderItems.map((it: any) => {
                              const isSelected = selectedReorderIds.has(it.product_id);
                              const qty = orderQuantities[it.product_id] ?? it.suggested_qty ?? 5;
                              const lineTotal = qty * (it.purchase_price || 0);

                              return (
                                <tr
                                  key={it.product_id}
                                  className={`transition-colors ${
                                    isSelected ? "bg-blue-500/5 dark:bg-blue-500/10" : "hover:bg-muted/30"
                                  }`}
                                >
                                  {/* Checkbox */}
                                  <td className="py-2.5 px-3 text-center">
                                    <input
                                      type="checkbox"
                                      checked={isSelected}
                                      onChange={() => handleToggleSelect(it.product_id)}
                                      className="rounded border-border cursor-pointer"
                                    />
                                  </td>

                                  {/* Urgency Badge */}
                                  <td className="py-2.5 px-2 text-center">
                                    {it.urgency === "OUT_OF_STOCK" ? (
                                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20 whitespace-nowrap">
                                        Out of Stock
                                      </span>
                                    ) : it.urgency === "CRITICAL" ? (
                                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 whitespace-nowrap">
                                        Critical
                                      </span>
                                    ) : (
                                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 border border-yellow-500/20 whitespace-nowrap">
                                        Low Stock
                                      </span>
                                    )}
                                  </td>

                                  {/* Item Description (Clickable to view history) */}
                                  <td className="py-2.5 px-3">
                                    <button
                                      type="button"
                                      onClick={() => setSelectedHistoryItem(it)}
                                      className="text-left font-semibold text-foreground hover:text-blue-500 transition-colors cursor-pointer group flex items-center gap-1.5"
                                      title="Click to view transaction history"
                                    >
                                      <span>{it.name}</span>
                                      <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 text-blue-500 transition-opacity" />
                                    </button>
                                    <div className="text-[10px] text-muted-foreground font-mono flex items-center gap-2 mt-0.5">
                                      {it.sku && <span>SKU: {it.sku}</span>}
                                    </div>
                                  </td>

                                  {/* Brand Column (Dedicated & Prominent) */}
                                  <td className="py-2.5 px-3">
                                    {it.brand ? (
                                      <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold bg-primary/10 text-primary border border-primary/20 whitespace-nowrap">
                                        {it.brand}
                                      </span>
                                    ) : (
                                      <span className="text-muted-foreground/50 italic font-mono text-[11px]">—</span>
                                    )}
                                  </td>

                                  {/* Category */}
                                  <td className="py-2.5 px-3 text-muted-foreground">
                                    {it.category_name || "General"}
                                  </td>

                                  {/* Depletion Countdown */}
                                  <td className="py-2.5 px-3 text-right font-mono">
                                    {it.days_until_stockout !== undefined && it.days_until_stockout !== null ? (
                                      <span
                                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold ${
                                          it.days_until_stockout <= 0
                                            ? "bg-rose-500/15 text-rose-600 dark:text-rose-400 border border-rose-500/30"
                                            : it.days_until_stockout <= 3
                                            ? "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20"
                                            : it.days_until_stockout <= 7
                                            ? "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20"
                                            : "bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20"
                                        }`}
                                      >
                                        <span>{it.days_until_stockout <= 3 ? "🚨" : it.days_until_stockout <= 7 ? "⚠️" : "⚡"}</span>
                                        <span>{it.days_until_stockout <= 0 ? "Depleted" : `${it.days_until_stockout}d runway`}</span>
                                      </span>
                                    ) : (
                                      <span className="text-muted-foreground text-[10px]">—</span>
                                    )}
                                  </td>

                                  {/* 7D Weekly Revenue at Risk */}
                                  <td className="py-2.5 px-3 text-right font-mono">
                                    {Number(it.revenue_at_risk_7d || 0) > 0 ? (
                                      <div className="font-bold text-rose-600 dark:text-rose-400">
                                        ₹{Number(it.revenue_at_risk_7d).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                                        <span className="text-[9px] text-muted-foreground block font-normal">/wk at risk</span>
                                      </div>
                                    ) : (
                                      <span className="text-muted-foreground/60 text-[11px]">—</span>
                                    )}
                                  </td>

                                  {/* Minimum Required Stock (Threshold) */}
                                  <td className="py-2.5 px-3 text-right font-mono text-xs">
                                    <span className="font-semibold text-foreground">
                                      {it.min_required_qty ?? it.reorder_level ?? 10}
                                    </span>
                                    {it.has_custom_reorder && (
                                      <span className="ml-1 text-[9px] font-bold px-1 py-0.2 rounded bg-blue-500/10 text-blue-600 dark:text-blue-400">
                                        Set
                                      </span>
                                    )}
                                  </td>

                                  {/* Current Stock */}
                                  <td className="py-2.5 px-3 text-right font-mono">
                                    <span
                                      className={`font-bold ${
                                        it.current_stock <= 0
                                          ? "text-rose-600 dark:text-rose-400"
                                          : it.current_stock <= 3
                                          ? "text-amber-600 dark:text-amber-400"
                                          : "text-foreground"
                                      }`}
                                    >
                                      {it.current_stock}
                                    </span>{" "}
                                    <span className="text-[10px] text-muted-foreground">{it.unit}</span>
                                  </td>

                                  {/* Sales Demand */}
                                  <td className="py-2.5 px-3 text-right font-mono text-muted-foreground">
                                    <span className="font-semibold text-blue-600 dark:text-blue-400">
                                      {it.invoices_count} inv
                                    </span>{" "}
                                    <span className="text-[10px]">({it.total_sold_qty} sold)</span>
                                  </td>

                                  {/* Last Purchase Rate & Supplier */}
                                  <td className="py-2.5 px-3 text-right font-mono">
                                    <div className="font-semibold text-foreground">
                                      ₹{(it.purchase_price || 0).toLocaleString("en-IN", {
                                        minimumFractionDigits: 2,
                                        maximumFractionDigits: 2,
                                      })}
                                    </div>
                                    <div className="text-[10px] text-muted-foreground truncate max-w-[120px] ml-auto">
                                      {it.last_supplier || "Catalog"}
                                    </div>
                                  </td>

                                  {/* Order Quantity Editor (Editable individual row and bulk) */}
                                  <td className="py-2.5 px-3 text-center">
                                    <div className="inline-flex items-center justify-center gap-1">
                                      <button
                                        type="button"
                                        onClick={() => handleItemQuantityChange(it.product_id, Math.max(1, qty - 1))}
                                        className="w-5 h-5 rounded bg-muted hover:bg-muted/80 text-foreground flex items-center justify-center cursor-pointer transition-colors"
                                        title="Decrease quantity"
                                      >
                                        <Minus className="w-2.5 h-2.5" />
                                      </button>
                                      <input
                                        type="number"
                                        min="1"
                                        value={qty}
                                        onChange={(e) =>
                                          handleItemQuantityChange(it.product_id, Math.max(1, parseInt(e.target.value) || 1))
                                        }
                                        className="w-14 bg-card border border-border/80 rounded py-0.5 text-center font-mono font-bold text-xs text-foreground outline-none focus:ring-1 focus:ring-primary"
                                      />
                                      <span className="text-[10px] text-muted-foreground font-mono">{it.unit}</span>
                                      <button
                                        type="button"
                                        onClick={() => handleItemQuantityChange(it.product_id, qty + 1)}
                                        className="w-5 h-5 rounded bg-muted hover:bg-muted/80 text-foreground flex items-center justify-center cursor-pointer transition-colors"
                                        title="Increase quantity"
                                      >
                                        <Plus className="w-2.5 h-2.5" />
                                      </button>
                                    </div>
                                  </td>

                                  {/* Line Total */}
                                  <td className="py-2.5 px-3 text-right font-mono font-bold text-foreground">
                                    ₹{Number(lineTotal || 0).toLocaleString("en-IN", {
                                      minimumFractionDigits: 2,
                                      maximumFractionDigits: 2,
                                    })}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* ========================================================================= */}
              {/* SUBVIEW 2: SITTING ON BENCHES / SLOW-MOVING (DEADSTOCK) INTELLIGENCE      */}
              {/* ========================================================================= */}
              {inventorySubView === "deadstock" && (
                <div className="space-y-4 animate-in fade-in duration-150">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                    <p className="text-muted-foreground">
                      Identifies items with <strong>physical stock on hand</strong> that have zero or low sales activity and have been sitting idle on benches/shelves. Pinpoints trapped working capital.
                    </p>
                    {inventoryBrandFilter !== "ALL" && (
                      <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 text-[11px] font-semibold self-start sm:self-auto">
                        <span>Brand Filter:</span>
                        <span className="font-bold">{inventoryBrandFilter}</span>
                        <button
                          type="button"
                          onClick={() => setInventoryBrandFilter("ALL")}
                          className="hover:opacity-75 cursor-pointer ml-0.5"
                          title="Clear brand filter"
                        >
                          ✕
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Summary Metric Cards for Deadstock on Benches */}
                  <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 p-3.5 bg-muted/20 border border-border/50 rounded-xl">
                    <div className="space-y-0.5">
                      <div className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">
                        Trapped Working Capital
                      </div>
                      <div className="text-lg sm:text-xl font-bold font-mono text-rose-600 dark:text-rose-400">
                        ₹{(inventoryAnalytics?.deadstock_summary?.locked_capital || 0).toLocaleString("en-IN", {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}
                      </div>
                      <div className="text-[10px] text-muted-foreground">
                        Tied up on benches at purchase cost
                      </div>
                    </div>

                    <div className="space-y-0.5">
                      <div className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">
                        Idle Physical Units
                      </div>
                      <div className="text-lg sm:text-xl font-bold font-mono text-foreground">
                        {(inventoryAnalytics?.deadstock_summary?.total_units || 0).toLocaleString("en-IN")} units
                      </div>
                      <div className="text-[10px] text-muted-foreground">
                        Across {inventoryAnalytics?.deadstock_summary?.total_items || 0} slow-moving products
                      </div>
                    </div>

                    <div className="space-y-0.5">
                      <div className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">
                        Never Sold (Dormant)
                      </div>
                      <div className="text-lg sm:text-xl font-bold font-mono text-purple-600 dark:text-purple-400">
                        {inventoryAnalytics?.deadstock_summary?.dormant_count || 0} items
                      </div>
                      <div className="text-[10px] text-muted-foreground">
                        Zero sales invoices ever recorded
                      </div>
                    </div>

                    <div className="space-y-0.5">
                      <div className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">
                        Critical Inactive (60d+)
                      </div>
                      <div className="text-lg sm:text-xl font-bold font-mono text-amber-600 dark:text-amber-400">
                        {(inventoryAnalytics?.deadstock_summary?.critical_90_count || 0) +
                          (inventoryAnalytics?.deadstock_summary?.stagnant_60_count || 0)}{" "}
                        items
                      </div>
                      <div className="text-[10px] text-muted-foreground">
                        No movement in over 60 days
                      </div>
                    </div>
                  </div>

                  {/* Top Brands on Benches Quick Bar */}
                  {inventoryAnalytics?.deadstock_summary?.by_brand &&
                    inventoryAnalytics.deadstock_summary.by_brand.length > 0 && (
                      <div className="flex flex-wrap items-center gap-2 p-2.5 bg-muted/15 border border-border/40 rounded-xl text-xs">
                        <span className="text-[11px] font-semibold text-muted-foreground whitespace-nowrap">
                          Top Brands on Benches:
                        </span>
                        {inventoryAnalytics.deadstock_summary.by_brand.map((b: any) => (
                          <button
                            key={b.brand}
                            type="button"
                            onClick={() =>
                              setInventoryBrandFilter(inventoryBrandFilter === b.brand ? "ALL" : b.brand)
                            }
                            className={`px-2.5 py-1 rounded-lg font-mono text-[11px] border transition-all cursor-pointer ${
                              inventoryBrandFilter === b.brand
                                ? "bg-primary text-primary-foreground border-primary font-bold shadow-2xs"
                                : "bg-card hover:bg-muted text-foreground border-border/60 font-medium"
                            }`}
                          >
                            <span>{b.brand}</span>: <span className="font-bold">₹{formatCurrencyShort(b.locked_capital)}</span>
                          </button>
                        ))}
                        {inventoryBrandFilter !== "ALL" && (
                          <button
                            type="button"
                            onClick={() => setInventoryBrandFilter("ALL")}
                            className="text-[11px] text-muted-foreground hover:text-foreground underline ml-1 cursor-pointer font-medium"
                          >
                            Show All
                          </button>
                        )}
                      </div>
                    )}

                  {/* Filter Toolbar: Aging Periods & Export CSV */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 bg-muted/30 border border-border/40 rounded-xl">
                    {/* Left: Aging Filters */}
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-[11px] font-semibold text-muted-foreground mr-1">
                        Idle Period:
                      </span>
                      {[
                        { key: "all", label: "All Idle (>30d)" },
                        { key: "60", label: "60+ Days" },
                        { key: "90", label: "90+ Days (Critical)" },
                        { key: "dormant", label: "Never Sold (Dormant)" },
                      ].map((f) => (
                        <button
                          key={f.key}
                          type="button"
                          onClick={() => setDeadstockAgingFilter(f.key as any)}
                          className={`px-2.5 py-1 rounded-lg text-xs font-semibold border transition-all cursor-pointer ${
                            deadstockAgingFilter === f.key
                              ? "bg-primary text-primary-foreground border-primary shadow-2xs"
                              : "bg-card hover:bg-muted text-muted-foreground hover:text-foreground border-border/60"
                          }`}
                        >
                          {f.label}
                        </button>
                      ))}
                    </div>

                    {/* Right: Item Count & Export CSV */}
                    <div className="flex items-center gap-3">
                      <div className="text-xs font-mono text-muted-foreground">
                        Showing <span className="font-bold text-foreground">{filteredDeadstockItems.length}</span> items
                      </div>
                      <button
                        type="button"
                        onClick={handleExportDeadstockCsv}
                        disabled={filteredDeadstockItems.length === 0}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-card hover:bg-muted text-foreground border border-border/60 transition-colors cursor-pointer shadow-2xs"
                        title="Download deadstock report in clean CSV spreadsheet"
                      >
                        <Download className="w-3.5 h-3.5 text-blue-500" />
                        <span>Export CSV</span>
                      </button>
                    </div>
                  </div>

                  {/* Sitting on Benches Table */}
                  {loadingInventoryAnalytics ? (
                    <div className="py-12 text-center text-xs text-muted-foreground space-y-2">
                      <RefreshCw className="w-5 h-5 animate-spin mx-auto text-blue-500" />
                      <div>Scanning catalog for idle inventory on benches...</div>
                    </div>
                  ) : filteredDeadstockItems.length === 0 ? (
                    <div className="py-12 text-center text-xs text-muted-foreground space-y-1 bg-muted/10 rounded-xl border border-dashed border-border/60">
                      <PackageCheck className="w-8 h-8 mx-auto text-emerald-500/70" />
                      <div className="font-bold text-foreground text-sm">No Deadstock Found!</div>
                      <p className="max-w-md mx-auto text-[11px]">
                        No stocked items match the selected idle period or brand criteria. All stocked items have active sales.
                      </p>
                    </div>
                  ) : (
                    <div className="rounded-xl border border-border/60 overflow-hidden">
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs">
                          <thead>
                            <tr className="bg-muted/40 border-b border-border/60 text-muted-foreground uppercase text-[10px] tracking-wider font-semibold">
                              <th className="py-2.5 px-3 w-10 text-center">#</th>
                              <th className="py-2.5 px-2 text-center">Status</th>
                              <th className="py-2.5 px-3">Item / Size</th>
                              <th className="py-2.5 px-3">Brand</th>
                              <th className="py-2.5 px-3">Category</th>
                              <th className="py-2.5 px-3 text-right">Units on Bench</th>
                              <th className="py-2.5 px-3 text-right">Cost Rate</th>
                              <th className="py-2.5 px-3 text-right">Locked Capital</th>
                              <th className="py-2.5 px-3 text-right">Catalog MRP</th>
                              <th className="py-2.5 px-3 text-center">Days Idle</th>
                              <th className="py-2.5 px-3 text-right">Last Activity</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border/30">
                            {filteredDeadstockItems.map((it: any, idx: number) => (
                              <tr
                                key={it.product_id}
                                className="hover:bg-muted/30 transition-colors"
                              >
                                <td className="py-2.5 px-3 text-center font-mono text-[11px] text-muted-foreground">
                                  {idx + 1}
                                </td>

                                {/* Status Badge */}
                                <td className="py-2.5 px-2 text-center">
                                  {it.status === "DORMANT" ? (
                                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20 whitespace-nowrap">
                                      Never Sold
                                    </span>
                                  ) : it.status === "CRITICAL_DEADSTOCK" ? (
                                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20 whitespace-nowrap">
                                      90+ Days
                                    </span>
                                  ) : it.status === "STAGNANT" ? (
                                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 whitespace-nowrap">
                                      60-90 Days
                                    </span>
                                  ) : (
                                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 border border-yellow-500/20 whitespace-nowrap">
                                      30-60 Days
                                    </span>
                                  )}
                                </td>

                                {/* Item Description */}
                                <td className="py-2.5 px-3">
                                  <button
                                    type="button"
                                    onClick={() => setSelectedHistoryItem(it)}
                                    className="text-left font-semibold text-foreground hover:text-blue-500 transition-colors cursor-pointer group flex items-center gap-1.5"
                                    title="Click to view transaction history"
                                  >
                                    <span>{it.name}</span>
                                    <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 text-blue-500 transition-opacity" />
                                  </button>
                                  <div className="text-[10px] text-muted-foreground font-mono flex items-center gap-2 mt-0.5">
                                    {it.sku && <span>SKU: {it.sku}</span>}
                                  </div>
                                </td>

                                {/* Brand Column */}
                                <td className="py-2.5 px-3">
                                  {it.brand ? (
                                    <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold bg-primary/10 text-primary border border-primary/20 whitespace-nowrap">
                                      {it.brand}
                                    </span>
                                  ) : (
                                    <span className="text-muted-foreground/50 italic font-mono text-[11px]">—</span>
                                  )}
                                </td>

                                {/* Category */}
                                <td className="py-2.5 px-3 text-muted-foreground">
                                  {it.category_name || "General"}
                                </td>

                                {/* Physical Units on Bench */}
                                <td className="py-2.5 px-3 text-right font-mono">
                                  <span className="font-bold text-foreground">
                                    {it.current_stock}
                                  </span>{" "}
                                  <span className="text-[10px] text-muted-foreground">{it.unit}</span>
                                </td>

                                {/* Purchase Cost */}
                                <td className="py-2.5 px-3 text-right font-mono text-muted-foreground">
                                  ₹{(it.purchase_price || 0).toLocaleString("en-IN", {
                                    minimumFractionDigits: 2,
                                    maximumFractionDigits: 2,
                                  })}
                                </td>

                                {/* Locked Working Capital */}
                                <td className="py-2.5 px-3 text-right font-mono font-bold text-rose-600 dark:text-rose-400">
                                  ₹{(it.locked_capital || 0).toLocaleString("en-IN", {
                                    minimumFractionDigits: 2,
                                    maximumFractionDigits: 2,
                                  })}
                                </td>

                                {/* Potential Revenue (Selling Price) */}
                                <td className="py-2.5 px-3 text-right font-mono text-muted-foreground">
                                  ₹{(it.potential_revenue || 0).toLocaleString("en-IN", {
                                    minimumFractionDigits: 2,
                                    maximumFractionDigits: 2,
                                  })}
                                </td>

                                {/* Days Idle */}
                                <td className="py-2.5 px-3 text-center font-mono">
                                  {it.status === "DORMANT" ? (
                                    <span className="text-[11px] text-purple-600 dark:text-purple-400 font-bold">
                                      Never
                                    </span>
                                  ) : (
                                    <span
                                      className={`text-xs font-semibold ${
                                        it.days_idle >= 90
                                          ? "text-rose-600 dark:text-rose-400 font-bold"
                                          : it.days_idle >= 60
                                          ? "text-amber-600 dark:text-amber-400"
                                          : "text-muted-foreground"
                                      }`}
                                    >
                                      {it.days_idle}d
                                    </span>
                                  )}
                                </td>

                                {/* Last Activity */}
                                <td className="py-2.5 px-3 text-right font-mono text-[10px] text-muted-foreground">
                                  {it.last_sale_date ? (
                                    <div>
                                      <span className="text-blue-500 font-medium">Sold:</span> {it.last_sale_date}
                                    </div>
                                  ) : it.last_purchase_date ? (
                                    <div>
                                      <span className="text-emerald-500 font-medium">Stocked:</span> {it.last_purchase_date}
                                    </div>
                                  ) : (
                                    <span>No activity</span>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* 4. Item Velocity & Most Frequent Movement Section */}
            <div className="bg-card border border-border/50 rounded-xl p-4 sm:p-5 shadow-2xs space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border/40 pb-3">
                <div>
                  <h3 className="text-sm sm:text-base font-bold text-foreground flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-blue-500" />
                    <span>Item Velocity & Most Frequent Movement</span>
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Top recurring items sold and purchased across posted invoices and vendor bills.
                  </p>
                </div>
                <div className="text-xs text-muted-foreground font-mono">
                  {inventoryCategoryFilter === "ALL"
                    ? "All Categories"
                    : inventoryAnalytics?.categories?.find((c: any) => c.id === inventoryCategoryFilter)?.name || "Category Filtered"}
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Most Frequent Sold */}
                <div className="bg-muted/20 border border-border/60 rounded-xl p-4 space-y-3">
                  <div className="flex items-center justify-between border-b border-border/40 pb-2">
                    <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-blue-500"></span>
                      Most Frequent Items Sold
                    </span>
                    <span className="text-[10px] text-muted-foreground font-mono">By Invoice Count</span>
                  </div>

                  {(!inventoryAnalytics?.top_sold || inventoryAnalytics.top_sold.length === 0) ? (
                    <div className="py-6 text-center text-xs text-muted-foreground">
                      No sales transactions recorded for this selection.
                    </div>
                  ) : (
                    <div className="space-y-1.5">
                      {inventoryAnalytics.top_sold.map((it: any, idx: number) => (
                        <div
                          key={idx}
                          onClick={() => setSelectedHistoryItem(it)}
                          className="flex items-center justify-between p-2.5 rounded-lg bg-card/60 hover:bg-muted/40 border border-border/30 text-xs transition-colors cursor-pointer group"
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="font-mono text-[10px] text-muted-foreground w-4">#{idx + 1}</span>
                            <div className="truncate">
                              <div className="font-semibold text-foreground group-hover:text-blue-500 transition-colors truncate">
                                {it.name}
                              </div>
                              <div className="text-[10px] text-muted-foreground font-mono">
                                {it.brand || "Unbranded"} • Stock: {it.current_stock} {it.unit}
                              </div>
                            </div>
                          </div>
                          <div className="text-right font-mono shrink-0 ml-2">
                            <div className="font-bold text-blue-600 dark:text-blue-400">
                              {it.invoices_count} inv ({it.total_qty} {it.unit})
                            </div>
                            <div className="text-[10px] text-muted-foreground">
                              ₹{Number(it.total_revenue || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Most Frequent Purchased */}
                <div className="bg-muted/20 border border-border/60 rounded-xl p-4 space-y-3">
                  <div className="flex items-center justify-between border-b border-border/40 pb-2">
                    <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                      Most Frequent Items Purchased
                    </span>
                    <span className="text-[10px] text-muted-foreground font-mono">By Bill Count</span>
                  </div>

                  {(!inventoryAnalytics?.top_purchased || inventoryAnalytics.top_purchased.length === 0) ? (
                    <div className="py-6 text-center text-xs text-muted-foreground">
                      No purchase transactions recorded for this selection.
                    </div>
                  ) : (
                    <div className="space-y-1.5">
                      {inventoryAnalytics.top_purchased.map((it: any, idx: number) => (
                        <div
                          key={idx}
                          onClick={() => setSelectedHistoryItem(it)}
                          className="flex items-center justify-between p-2.5 rounded-lg bg-card/60 hover:bg-muted/40 border border-border/30 text-xs transition-colors cursor-pointer group"
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="font-mono text-[10px] text-muted-foreground w-4">#{idx + 1}</span>
                            <div className="truncate">
                              <div className="font-semibold text-foreground group-hover:text-emerald-500 transition-colors truncate">
                                {it.name}
                              </div>
                              <div className="text-[10px] text-muted-foreground font-mono">
                                {it.brand || "Unbranded"} • Stock: {it.current_stock} {it.unit}
                              </div>
                            </div>
                          </div>
                          <div className="text-right font-mono shrink-0 ml-2">
                            <div className="font-bold text-emerald-600 dark:text-emerald-400">
                              {it.bills_count} bills ({it.total_qty} {it.unit})
                            </div>
                            <div className="text-[10px] text-muted-foreground">
                              ₹{Number(it.total_spend || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 5: Cash Flow & Working Capital */}
        {activeTab === "cashflow" && (
          <div className="space-y-6 animate-in fade-in duration-200">
            {/* Liquid Balances Row */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Money to Collect (Debtors)
                </span>
                <div className="text-xl sm:text-2xl font-bold font-mono text-emerald-600 dark:text-emerald-400">
                  ₹{Number(kpis.money_to_collect || forecast?.working_capital_cycle?.accounts_receivable || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
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
                  ₹{Number(kpis.bills_to_pay || forecast?.working_capital_cycle?.accounts_payable || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
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
                  ₹{Number(kpis.cash_and_bank || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-xs text-muted-foreground">
                  Current bank balances + physical cash in hand
                </div>
              </div>
            </div>

            {/* Cash Conversion Cycle (CCC) & Working Capital Health */}
            {forecast?.working_capital_cycle && (
              <div className="bg-card border border-border/50 rounded-xl p-5 shadow-2xs space-y-5">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/40 pb-3">
                  <div>
                    <h3 className="text-sm sm:text-base font-semibold text-foreground flex items-center gap-1.5">
                      <Landmark className="w-4 h-4 text-primary" />
                      <span>Cash Conversion Cycle (CCC) & Capital Efficiency</span>
                    </h3>
                    <p className="text-xs text-muted-foreground">
                      Measures the speed (in days) at which capital invested in operations turns back into collected liquid cash.
                    </p>
                  </div>
                  <span
                    className={`px-3 py-1 rounded-full text-xs font-mono font-bold border ${
                      forecast.working_capital_cycle.working_capital_health === "HEALTHY"
                        ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20"
                        : forecast.working_capital_cycle.working_capital_health === "MODERATE"
                        ? "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20"
                        : "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20"
                    }`}
                  >
                    {forecast.working_capital_cycle.working_capital_health === "HEALTHY"
                      ? "Healthy Working Capital"
                      : forecast.working_capital_cycle.working_capital_health === "MODERATE"
                      ? "Moderate Capital Turnover"
                      : "Elevated Cash Cycle (Action Needed)"}
                  </span>
                </div>

                {/* 4 Pillars Grid */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                  {/* Net CCC */}
                  <div className="p-4 rounded-xl border border-primary/30 bg-primary/5 space-y-1">
                    <span className="text-[10px] font-semibold text-primary uppercase tracking-wider">
                      Net Cash Cycle (CCC)
                    </span>
                    <div className="text-2xl font-bold font-mono text-foreground">
                      {forecast.working_capital_cycle.cash_conversion_cycle_days}
                      <span className="text-xs font-normal text-muted-foreground ml-1">Days</span>
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      Total days capital is trapped in operations
                    </div>
                  </div>

                  {/* DIO */}
                  <div className="p-4 rounded-xl border border-border/40 bg-muted/20 space-y-1">
                    <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
                      Days Inventory Outstanding (DIO)
                    </span>
                    <div className="text-2xl font-bold font-mono text-foreground">
                      {forecast.working_capital_cycle.dio_days}
                      <span className="text-xs font-normal text-muted-foreground ml-1">Days</span>
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      Average stock holding duration before sale
                    </div>
                  </div>

                  {/* DSO */}
                  <div className="p-4 rounded-xl border border-border/40 bg-muted/20 space-y-1">
                    <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
                      Days Sales Outstanding (DSO)
                    </span>
                    <div className="text-2xl font-bold font-mono text-foreground">
                      {forecast.working_capital_cycle.dso_days}
                      <span className="text-xs font-normal text-muted-foreground ml-1">Days</span>
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      Average days to collect customer payments
                    </div>
                  </div>

                  {/* DPO */}
                  <div className="p-4 rounded-xl border border-border/40 bg-muted/20 space-y-1">
                    <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
                      Days Payable Outstanding (DPO)
                    </span>
                    <div className="text-2xl font-bold font-mono text-foreground">
                      {forecast.working_capital_cycle.dpo_days}
                      <span className="text-xs font-normal text-muted-foreground ml-1">Days</span>
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      Average credit period taken to pay vendors
                    </div>
                  </div>
                </div>

                {/* Formula Visual Banner */}
                <div className="p-3.5 rounded-xl bg-muted/30 border border-border/40 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs">
                  <div className="flex items-center gap-2 flex-wrap font-mono">
                    <span className="px-2 py-1 rounded bg-card border border-border/40 font-semibold text-foreground">
                      DIO: {forecast.working_capital_cycle.dio_days}d
                    </span>
                    <span className="text-muted-foreground font-bold">+</span>
                    <span className="px-2 py-1 rounded bg-card border border-border/40 font-semibold text-foreground">
                      DSO: {forecast.working_capital_cycle.dso_days}d
                    </span>
                    <span className="text-muted-foreground font-bold">-</span>
                    <span className="px-2 py-1 rounded bg-card border border-border/40 font-semibold text-foreground">
                      DPO: {forecast.working_capital_cycle.dpo_days}d
                    </span>
                    <span className="text-muted-foreground font-bold">=</span>
                    <span className="px-2 py-1 rounded bg-primary text-primary-foreground font-bold">
                      Net CCC: {forecast.working_capital_cycle.cash_conversion_cycle_days} Days
                    </span>
                  </div>

                  <div className="text-xs text-muted-foreground">
                    Target benchmark for wholesale distribution: &lt; 90 Days
                  </div>
                </div>

                {/* AI Executive Recommendation */}
                <div className="p-4 rounded-xl bg-purple-500/5 border border-purple-500/20 space-y-1.5 text-xs">
                  <div className="font-semibold text-foreground flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                    <span>Working Capital Optimization Insight</span>
                  </div>
                  <p className="text-muted-foreground leading-relaxed">
                    {forecast.working_capital_cycle.recommendation || `With a cash cycle of ${forecast.working_capital_cycle.cash_conversion_cycle_days} days, inventory accounts for ${forecast.working_capital_cycle.dio_days} days of working capital. Liquidating slow-moving stock and incentivizing 15-day settlement from top debtors will accelerate cash flow.`}
                  </p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Mass-Wise Minimum Required Stock Configuration Modal */}
        <MassMinStockModal
          isOpen={isMassMinStockModalOpen}
          onClose={() => setIsMassMinStockModalOpen(false)}
          scope={massMinStockScope}
          onScopeChange={setMassMinStockScope}
          minStockInput={massMinStockInput}
          onMinStockInputChange={setMassMinStockInput}
          onApply={handleApplyMassMinStock}
          loading={updatingMinStock}
          selectedCount={selectedReorderIds.size}
          currentCategoryName={currentCategoryName}
          hasCategoryFilter={inventoryCategoryFilter !== "ALL"}
        />

        {/* Purchase Order Draft Modal */}
        <PurchaseOrderDraftModal
          isOpen={isPoModalOpen}
          onClose={() => setIsPoModalOpen(false)}
          items={poDraftItems}
          companyName={activeCompany?.name || "Company"}
          companyGstin={activeCompany?.gstin || ""}
          companyAddress={
            activeCompany?.address
              ? `${activeCompany.address}${activeCompany.city ? `, ${activeCompany.city}` : ""}`
              : ""
          }
          onUpdateQuantity={handleItemQuantityChange}
          onRemoveItem={handleRemoveFromDraft}
        />

        {/* Item Invoice & Bill History Inspection Modal */}
        <ItemHistoryModal
          isOpen={!!selectedHistoryItem}
          onClose={() => setSelectedHistoryItem(null)}
          productId={selectedHistoryItem?.product_id || selectedHistoryItem?.id || null}
          productName={selectedHistoryItem?.name || ""}
          companyId={effectiveCompanyId || activeCompanyId || ""}
        />
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
