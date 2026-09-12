"use client";
import React, { useEffect, useState, useRef } from "react";
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
import { useCompany } from "@/context/CompanyContext";
import { LocalAnalyticsEngine, LocalDashboardResult } from "@/lib/analytics/analytics-engine";
import { pullIncrementalChanges, triggerOutboxSync, executeClientOutboxSync } from "@/lib/sync/sync-worker";
import { offlineDb } from "@/lib/db/offlineDb";
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
  Activity,
  Landmark,
  ShieldCheck,
  RefreshCw,
  CheckCircle2,
  WifiOff,
  CloudUpload,
} from "lucide-react";

function getVoucherTypeBadgeClass(type: string): string {
  switch (type) {
    case "SALES":
      return "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20";
    case "PURCHASE":
      return "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20";
    case "PAYMENT":
      return "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20";
    case "RECEIPT":
      return "bg-teal-500/10 text-teal-600 dark:text-teal-400 border-teal-500/20";
    case "CONTRA":
      return "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20";
    case "JOURNAL":
    default:
      return "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20";
  }
}

function getVoucherStatusBadgeClass(status: string): string {
  switch (status) {
    case "POSTED":
    case "CORRECTED":
      return "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20";
    case "DRAFT":
      return "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20";
    case "CANCELLED":
    case "REVERSED":
      return "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20";
    default:
      return "bg-muted text-muted-foreground border-border/50";
  }
}

function getCustomerTierBadgeClass(segment: string): string {
  const s = segment.toLowerCase();
  if (s.includes("vip") || s.includes("high")) {
    return "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20";
  }
  if (s.includes("frequent") || s.includes("regular")) {
    return "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20";
  }
  if (s.includes("moderate") || s.includes("growth")) {
    return "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20";
  }
  return "bg-muted text-muted-foreground border-border/50";
}

function formatChartDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
  } catch {
    return dateStr;
  }
}

function formatCurrencyShort(val: number): string {
  if (val >= 100000) return `₹${(val / 100000).toFixed(1)}L`;
  if (val >= 1000) return `₹${(val / 1000).toFixed(0)}k`;
  return `₹${val}`;
}

export default function Dashboard() {
  const router = useRouter();
  const { startTour, setIsHelpOpen } = useShortcuts();
  const [insights, setInsights] = useState<any>(null);
  const [vouchers, setVouchers] = useState<any[]>([]);
  const [coverage, setCoverage] = useState<any>(null);
  const [forecast, setForecast] = useState<any>(null);
  const [healthReport, setHealthReport] = useState<any>(null);
  const [chartMode, setChartMode] = useState<'VELOCITY' | 'FORECAST'>('VELOCITY');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [syncStatus, setSyncStatus] = useState<"IDLE" | "SYNCING" | "ERROR">("IDLE");
  const [syncMessage, setSyncMessage] = useState("");
  const [pendingMutations, setPendingMutations] = useState(0);
  const [isOnline, setIsOnline] = useState(true);

  const { activeCompany, companyId: activeCompanyId } = useCompany();
  const loadedCompanyRef = useRef<string | null>(null);

  // Load dashboard from local IndexedDB first (<15ms), then run incremental sync in background
  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }

    let isMounted = true;

    async function loadDashboard() {
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
          const companies = Array.isArray(compRes.data) ? compRes.data : (compRes.data.data || []);
          if (companies.length === 0) {
            if (isMounted) {
              setError("No companies found. Please create a company first.");
              setLoading(false);
            }
            return;
          }
          cid = companies[0].id;
          if (cid && typeof window !== "undefined") {
            localStorage.setItem("vouch_active_company_id", cid);
          }
        }

        if (!cid) {
          if (isMounted) setLoading(false);
          return;
        }
        const validCid = cid;

        // 1. Instant local read from IndexedDB
        const local = await LocalAnalyticsEngine.getDashboardAnalytics(validCid);
        if (isMounted) {
          setInsights(local);
          setVouchers(local.recent_vouchers || []);
          setCoverage(local.coverage);
          if (local.forecast) {
            setForecast(local.forecast);
          }
          // Check pending outbox mutations
          const pendingCount = await offlineDb.vouchers
            .where("status")
            .equals("PENDING")
            .count()
            .catch(() => 0);
          setPendingMutations(pendingCount);

          // If local data exists or initial sync is already complete, render immediately!
          if (local.coverage.totalVouchersCount > 0 || local.coverage.isComplete) {
            setLoading(false);
          }
        }

        // 2. Read cached health check from sessionStorage (strictly avoiding repeated server audits)
        let hasValidHealthCache = false;
        if (typeof window !== "undefined") {
          try {
            const cachedHealthStr = sessionStorage.getItem(`vouch_health_${validCid}`);
            if (cachedHealthStr) {
              const cached = JSON.parse(cachedHealthStr);
              if (Date.now() - (cached._cachedAt || 0) < 5 * 60 * 1000) {
                if (isMounted) setHealthReport(cached);
                hasValidHealthCache = true;
              }
            }
          } catch (e) {}
        }

        // Avoid repeated network dispatch if this exact company was already loaded on this component instance
        const isInitialCompanyLoad = loadedCompanyRef.current !== validCid;
        loadedCompanyRef.current = validCid;

        // 3. Trigger background incremental delta sync if online
        if (typeof navigator !== "undefined" && navigator.onLine) {
          if (isInitialCompanyLoad) {
            if (isMounted) {
              setSyncStatus("SYNCING");
              setSyncMessage("Updating local books...");
            }
            
            pullIncrementalChanges(validCid, (msg) => {
              if (isMounted) setSyncMessage(msg);
            }).then(async (res) => {
              if (!isMounted) return;
              if (res.success) {
                const refreshed = await LocalAnalyticsEngine.getDashboardAnalytics(validCid);
                setInsights(refreshed);
                setVouchers(refreshed.recent_vouchers || []);
                setCoverage(refreshed.coverage);
                if (refreshed.forecast) {
                  setForecast(refreshed.forecast);
                }
                setSyncStatus("IDLE");
                setSyncMessage("");
              } else {
                setSyncStatus("ERROR");
                setSyncMessage(res.error || "Sync update paused");
              }
              setLoading(false);
            }).catch(() => {
              if (isMounted) {
                setSyncStatus("ERROR");
                setLoading(false);
              }
            });

            // Also trigger outbox sync for any pending offline commands
            executeClientOutboxSync().then(async () => {
              if (isMounted) {
                const cnt = await offlineDb.vouchers
                  .where("status")
                  .equals("PENDING")
                  .count()
                  .catch(() => 0);
                setPendingMutations(cnt);
              }
            });
          }

          // Fetch health check ONLY IF no valid cache exists
          if (!hasValidHealthCache) {
            const token = getAccessToken();
            const headers = { Authorization: `Bearer ${token}`, "X-Company-ID": validCid };
            axios.get(`${API_BASE_URL}/api/v1/accounting/health/?company_id=${validCid}`, { headers })
              .then((hRes) => {
                if (isMounted && hRes.data) {
                  const reportWithTs = { ...hRes.data, _cachedAt: Date.now() };
                  setHealthReport(reportWithTs);
                  if (typeof window !== "undefined") {
                    sessionStorage.setItem(`vouch_health_${validCid}`, JSON.stringify(reportWithTs));
                  }
                }
              })
              .catch(() => {});
          }
        } else {
          // Offline mode
          if (isMounted) {
            setIsOnline(false);
            setLoading(false);
          }
        }
      } catch (err: any) {
        console.error("Dashboard local-first load error:", err);
        if (isMounted) {
          setError(err.message || "Failed to load dashboard data.");
          setLoading(false);
        }
      }
    }

    loadDashboard();

    // Listen for custom sync completion broadcasts
    const handleSyncComplete = async (e: any) => {
      const cid = activeCompanyId || (typeof window !== "undefined" ? localStorage.getItem("vouch_active_company_id") : null);
      if (cid) {
        const updated = await LocalAnalyticsEngine.getDashboardAnalytics(cid);
        if (isMounted) {
          setInsights(updated);
          setVouchers(updated.recent_vouchers || []);
          setCoverage(updated.coverage);
          if (updated.forecast) {
            setForecast(updated.forecast);
          }
          const cnt = await offlineDb.vouchers
            .where("status")
            .equals("PENDING")
            .count()
            .catch(() => 0);
          setPendingMutations(cnt);
          setSyncStatus("IDLE");
        }
      }
    };

    const handleOnline = () => {
      if (isMounted) setIsOnline(true);
      loadDashboard();
    };

    const handleOffline = () => {
      if (isMounted) setIsOnline(false);
    };

    window.addEventListener("vouch:sync-complete", handleSyncComplete);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      isMounted = false;
      window.removeEventListener("vouch:sync-complete", handleSyncComplete);
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, [router, activeCompanyId]);

  // Lazy-load forecast when user toggles to AI Forecast mode or company changes
  useEffect(() => {
    const cid = activeCompanyId || (typeof window !== "undefined" ? localStorage.getItem("vouch_active_company_id") : null);
    if (!cid) return;

    if (chartMode === 'FORECAST' && (!forecast || !forecast.daily_forecast?.length) && typeof navigator !== "undefined" && navigator.onLine) {
      const token = getAccessToken();
      const headers: Record<string, string> = {
        "X-Company-ID": cid,
      };
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }
      axios.get(`${API_BASE_URL}/api/v1/analytics/forecast/${cid}/?days=30&company_id=${cid}`, {
        headers,
      }).then((res) => {
        if (res.data?.success && res.data?.data) {
          setForecast(res.data.data);
        }
      }).catch(() => {});
    }
  }, [chartMode, forecast, activeCompanyId]);

  const handleManualSync = async () => {
    const cid = activeCompanyId || (typeof window !== "undefined" ? localStorage.getItem("vouch_active_company_id") : null);
    if (!cid || typeof navigator === "undefined" || !navigator.onLine) return;
    setSyncStatus("SYNCING");
    setSyncMessage("Syncing local books...");
    await executeClientOutboxSync();
    await pullIncrementalChanges(cid, (msg) => setSyncMessage(msg));
    const refreshed = await LocalAnalyticsEngine.getDashboardAnalytics(cid);
    setInsights(refreshed);
    setVouchers(refreshed.recent_vouchers || []);
    setCoverage(refreshed.coverage);
    if (refreshed.forecast) {
      setForecast(refreshed.forecast);
    }

    // On explicit user sync, also refresh server health audit
    const token = getAccessToken();
    const headers = { Authorization: `Bearer ${token}`, "X-Company-ID": cid };
    axios.get(`${API_BASE_URL}/api/v1/accounting/health/?company_id=${cid}`, { headers })
      .then((hRes) => {
        if (hRes.data) {
          const reportWithTs = { ...hRes.data, _cachedAt: Date.now() };
          setHealthReport(reportWithTs);
          if (typeof window !== "undefined") {
            sessionStorage.setItem(`vouch_health_${cid}`, JSON.stringify(reportWithTs));
          }
        }
      })
      .catch(() => {});

    setSyncStatus("IDLE");
    setSyncMessage("");
  };

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
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-xl sm:text-2xl font-extrabold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">
                {activeCompany?.name ? `${activeCompany.name}` : "Your Business"}
              </h1>
              
              {/* Minimal sync indicator — dot only */}
              {syncStatus === "SYNCING" ? (
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-blue-500/10 text-blue-500 border border-blue-500/20" title="Updating your books...">
                  <RefreshCw className="w-3 h-3 animate-spin" />
                  <span>Updating...</span>
                </span>
              ) : !isOnline ? (
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-muted text-muted-foreground border border-border/60" title="You're offline. Changes will sync when you're back online.">
                  <WifiOff className="w-3 h-3" />
                  <span>Offline</span>
                </span>
              ) : pendingMutations > 0 ? (
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-500 border border-amber-500/20" title="Changes will sync automatically">
                  <CloudUpload className="w-3.5 h-3.5" />
                  <span>{pendingMutations} pending</span>
                </span>
              ) : coverage?.lastSyncAt ? (
                <span className="w-2 h-2 rounded-full bg-emerald-400 shrink-0" title={`Up to date · Last checked ${new Date(coverage.lastSyncAt).toLocaleTimeString()}`}></span>
              ) : null}

              {/* Sync Refresh Button */}
              {isOnline && (
                <button
                  type="button"
                  onClick={handleManualSync}
                  disabled={syncStatus === "SYNCING"}
                  className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer"
                  title="Refresh"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${syncStatus === "SYNCING" ? "animate-spin text-primary" : ""}`} />
                </button>
              )}
            </div>

            <p className="text-sm text-muted-foreground mt-1">
              Here&apos;s how your business is doing today
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
              <span>New Sale</span>
            </Link>

            <Link
              id="tour-purchase-btn"
              href="/purchases/new"
              className="px-4 py-2.5 bg-secondary text-foreground hover:bg-secondary/80 border border-border/60 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 cursor-pointer min-h-[40px]"
            >
              <ShoppingCart className="w-4 h-4 text-muted-foreground" />
              <span>New Purchase</span>
            </Link>

            <Link
              href="/parties"
              className="px-3.5 py-2.5 bg-card hover:bg-muted text-foreground border border-border/60 rounded-xl text-sm font-semibold transition-all flex items-center gap-1.5 cursor-pointer min-h-[40px]"
            >
              <ArrowDownRight className="w-4 h-4 text-emerald-500" />
              <span>Receive Money</span>
            </Link>

            <Link
              href="/parties"
              className="px-3.5 py-2.5 bg-card hover:bg-muted text-foreground border border-border/60 rounded-xl text-sm font-semibold transition-all flex items-center gap-1.5 cursor-pointer min-h-[40px]"
            >
              <ArrowUpRight className="w-4 h-4 text-rose-500" />
              <span>Pay Supplier</span>
            </Link>
          </div>
        </div>

        {/* Attention Center — compact grouped alerts */}
        {alerts.length > 0 && (
          <div className="bg-card border border-border/40 rounded-xl p-4 shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-foreground">Needs your attention</h2>
              <Link href="/health" className="text-xs text-muted-foreground hover:text-foreground font-medium transition-colors">
                View all →
              </Link>
            </div>
            <div className="space-y-2">
              {alerts.slice(0, 5).map((alert: any, idx: number) => (
                <div
                  key={idx}
                  className="flex items-center gap-2.5 py-1.5 text-xs text-foreground"
                >
                  <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                    alert.message?.toLowerCase().includes('overdue') ? 'bg-rose-400' :
                    alert.message?.toLowerCase().includes('low stock') ? 'bg-amber-400' :
                    'bg-blue-400'
                  }`}></span>
                  <span>{alert.message}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Books Status — simple health indicator */}
        <div className="bg-card border border-border/40 rounded-xl p-4 shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
              healthReport ? (
                (healthReport?.health_score ?? 100) >= 90
                  ? "bg-emerald-500/10 text-emerald-400"
                  : (healthReport?.health_score ?? 100) >= 70
                  ? "bg-amber-500/10 text-amber-400"
                  : "bg-rose-500/10 text-rose-400"
              ) : "bg-muted text-muted-foreground"
            }`}>
              {healthReport && (healthReport?.health_score ?? 100) >= 90 ? (
                <CheckCircle2 className="w-4 h-4" />
              ) : healthReport ? (
                <Info className="w-4 h-4" />
              ) : (
                <Activity className="w-4 h-4" />
              )}
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">
                {healthReport ? (
                  (healthReport?.health_score ?? 100) >= 90
                    ? "Your books look good"
                    : healthReport.health_status === "CRITICAL"
                    ? `${healthReport.metrics?.critical_findings_count || 1} things need review`
                    : "Some things need attention"
                ) : (
                  "Books status"
                )}
              </h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                {healthReport ? (
                  (healthReport?.health_score ?? 100) >= 90
                    ? `Last checked ${healthReport._cachedAt ? new Date(healthReport._cachedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'recently'}`
                    : "Review recommended"
                ) : (
                  "Run a check to see how your books are doing"
                )}
              </p>
            </div>
          </div>
          <Link
            href="/health"
            className="px-3.5 py-2 rounded-xl border border-border/60 bg-muted/40 hover:bg-muted text-foreground text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors"
          >
            <span>{healthReport && (healthReport?.health_score ?? 100) < 90 ? "Review now" : "View details"}</span>
            <ArrowUpRight className="w-3 h-3" />
          </Link>
        </div>

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
              <span className="text-xs font-medium">Received Today</span>
              <ArrowDownRight className="w-4 h-4 text-emerald-500/70" />
            </div>
            <div className="text-xl font-bold font-mono tabular-nums tracking-tight text-emerald-500 pl-2">
              ₹{(kpis.today_collections || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
            <div className="text-[11px] text-muted-foreground pl-2">
              Payments received
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
              Customers owe you &rarr;
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
              You owe suppliers &rarr;
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
              Cash &amp; bank balance &rarr;
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
                  <span>{chartMode === 'VELOCITY' ? 'Sales over time' : 'Sales forecast'}</span>
                  <span title={chartMode === 'VELOCITY' ? 'Daily sales over time' : 'Projected sales based on past performance'} className="cursor-help text-muted-foreground hover:text-foreground">
                    <Info className="w-3.5 h-3.5" />
                  </span>
                </h2>
                <p className="text-xs text-muted-foreground">
                  {chartMode === 'VELOCITY' ? 'See how your sales are changing' : 'Expected sales based on your recent trends'}
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
                    <span>Forecast</span>
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
                      <AreaChart data={forecast.daily_forecast} margin={{ top: 10, right: 15, left: -10, bottom: 0 }}>
                        <defs>
                          <linearGradient id="forecastGrad" x1="0" y1="0" x2="0" y2="1">
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
                          tickMargin={8}
                          minTickGap={16}
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
                    <AreaChart data={trend.daily_trend} margin={{ top: 10, right: 15, left: -10, bottom: 0 }}>
                      <defs>
                        <linearGradient id="salesVelocityGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.25} />
                          <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
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
                        tickMargin={8}
                        minTickGap={16}
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
                        formatter={(val: any) => [`₹${Number(val).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`, "Sales"]}
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
                  <span>Your best customers</span>
                </h2>
                <p className="text-xs text-muted-foreground">Customers by sales volume</p>
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
                      <th className="pb-2 font-medium">Status</th>
                      <th className="pb-2 font-medium text-right">Orders</th>
                      <th className="pb-2 font-medium text-right">Sales</th>
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
                            <span className={`px-2 py-0.5 rounded text-xs font-semibold border ${getCustomerTierBadgeClass(segName)}`}>
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
              <p className="text-xs text-muted-foreground">Your latest transactions</p>
            </div>
            <Link href="/vouchers" className="text-xs text-primary hover:underline font-medium transition-colors">
              View all →
            </Link>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-border/60 text-muted-foreground">
                  <th className="py-2.5 font-medium">Number</th>
                  <th className="py-2.5 font-medium">Date</th>
                  <th className="py-2.5 font-medium">Type</th>
                  <th className="py-2.5 font-medium">Details / Party</th>
                  <th className="py-2.5 font-medium">Status</th>
                  <th className="py-2.5 font-medium text-right">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/30">
                {vouchers.slice(0, 8).map((v) => {
                  const voucherNo = v.voucherNumber || v.voucher_number || "—";
                  const rawDate = v.voucherDate || v.voucher_date || v.date;
                  const formattedDate = rawDate
                    ? (() => {
                        try {
                          const d = new Date(rawDate);
                          return isNaN(d.getTime())
                            ? rawDate
                            : d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
                        } catch {
                          return rawDate;
                        }
                      })()
                    : "—";
                  const vType = (v.voucherType || v.voucher_type || v.type || "GENERAL").toUpperCase();
                  const partyName = v.partyName || v.party_name || v.narration || "General Entry";
                  const status = v.status || "POSTED";
                  const rawAmount = v.totalAmount !== undefined && v.totalAmount !== null
                    ? v.totalAmount
                    : (v.total_amount !== undefined && v.total_amount !== null ? v.total_amount : 0);
                  const amount = Number(rawAmount) || 0;

                  return (
                    <tr
                      key={v.id || voucherNo}
                      onClick={() => router.push(`/vouchers?search=${encodeURIComponent(voucherNo !== "—" ? voucherNo : "")}`)}
                      className="hover:bg-muted/40 transition-colors cursor-pointer group"
                    >
                      <td className="py-3 font-mono tabular-nums font-semibold text-foreground group-hover:text-primary transition-colors">
                        {voucherNo}
                      </td>
                      <td className="py-3 text-muted-foreground font-mono tabular-nums">
                        {formattedDate}
                      </td>
                      <td className="py-3">
                        <span className={`px-2 py-0.5 rounded text-[11px] font-mono font-semibold uppercase border ${getVoucherTypeBadgeClass(vType)}`}>
                          {vType}
                        </span>
                      </td>
                      <td className="py-3 text-foreground font-medium max-w-[220px] truncate" title={partyName}>
                        {partyName}
                      </td>
                      <td className="py-3">
                        <span className={`px-2 py-0.5 rounded text-[11px] font-semibold border ${getVoucherStatusBadgeClass(status)}`}>
                          {status}
                        </span>
                      </td>
                      <td className="py-3 text-right font-mono tabular-nums font-semibold text-foreground">
                        ₹{amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </td>
                    </tr>
                  );
                })}
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
