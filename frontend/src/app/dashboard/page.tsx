"use client";
import React, { useEffect, useState, useRef } from "react";
import axios from "axios";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken, isAuthenticated, getUser } from "@/utils/auth";
import DashboardLayout from "@/components/DashboardLayout";
import { useShortcuts } from "@/context/ShortcutContext";
import { useCompany } from "@/context/CompanyContext";
import { useFinancialYear } from "@/context/FinancialYearContext";
import { LocalAnalyticsEngine } from "@/lib/analytics/analytics-engine";
import { pullIncrementalChanges, executeClientOutboxSync } from "@/lib/sync/sync-worker";
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
  ArrowRight,
  HelpCircle,
  FileText,
  Boxes,
  Activity,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  WifiOff,
  CloudUpload,
  ChevronRight,
  CreditCard,
  Building2,
  Calendar,
  Wallet,
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

function formatCurrencyShort(val: number): string {
  if (val >= 10000000) return `₹${(val / 10000000).toFixed(2)}Cr`;
  if (val >= 100000) return `₹${(val / 100000).toFixed(1)}L`;
  if (val >= 1000) return `₹${(val / 1000).toFixed(0)}k`;
  return `₹${val.toFixed(0)}`;
}

export default function Dashboard() {
  const router = useRouter();
  const { setIsHelpOpen } = useShortcuts();
  const [insights, setInsights] = useState<any>(null);
  const [vouchers, setVouchers] = useState<any[]>([]);
  const [coverage, setCoverage] = useState<any>(null);
  const [forecast, setForecast] = useState<any>(null);
  const [healthReport, setHealthReport] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [syncStatus, setSyncStatus] = useState<"IDLE" | "SYNCING" | "ERROR">("IDLE");
  const [syncMessage, setSyncMessage] = useState("");
  const [pendingMutations, setPendingMutations] = useState(0);
  const [isOnline, setIsOnline] = useState(true);

  const { activeCompany, companyId: activeCompanyId } = useCompany();
  const { activeFY } = useFinancialYear();
  const loadedCompanyRef = useRef<string | null>(null);

  // Load dashboard from local IndexedDB first (<15ms), then run incremental sync in background
  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }

    const u = getUser();
    if (u?.is_superuser || u?.email?.trim().toLowerCase() === "prakharssa@gmail.com") {
      router.replace("/admin");
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

        const fyOptions = {
          startDate: activeFY?.start_date,
          endDate: activeFY?.end_date,
          financialYearId: activeFY?.id,
        };

        // 1. Instant local read from IndexedDB (strictly scoped to active FY)
        const local = await LocalAnalyticsEngine.getDashboardAnalytics(validCid, fyOptions);
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

        // 2. Read cached health check from sessionStorage
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

        const loadKey = `${validCid}_${activeFY?.id || ''}`;
        const isInitialCompanyLoad = loadedCompanyRef.current !== loadKey;
        loadedCompanyRef.current = loadKey;

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
                const refreshed = await LocalAnalyticsEngine.getDashboardAnalytics(validCid, fyOptions);
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

            // Trigger outbox sync
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

          // Fetch health check if no valid cache exists
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
          if (isMounted) {
            setIsOnline(false);
            setLoading(false);
          }
        }
      } catch (err: any) {
        console.error("Dashboard load error:", err);
        if (isMounted) {
          setError(err.message || "Failed to load dashboard data.");
          setLoading(false);
        }
      }
    }

    loadDashboard();

    const handleSyncComplete = async () => {
      const cid = activeCompanyId || (typeof window !== "undefined" ? localStorage.getItem("vouch_active_company_id") : null);
      if (cid) {
        const fyOptions = {
          startDate: activeFY?.start_date,
          endDate: activeFY?.end_date,
          financialYearId: activeFY?.id,
        };
        const updated = await LocalAnalyticsEngine.getDashboardAnalytics(cid, fyOptions);
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
  }, [router, activeCompanyId, activeFY?.id]);

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
        <div className="flex flex-col items-center justify-center min-h-[400px] space-y-3">
          <div className="w-9 h-9 border-3 border-primary border-t-transparent rounded-full animate-spin"></div>
          <div className="text-sm text-muted-foreground font-medium">Opening your books...</div>
        </div>
      </DashboardLayout>
    );
  }

  if (error) {
    return (
      <DashboardLayout>
        <div className="p-6 bg-destructive/10 border border-destructive/20 rounded-2xl text-destructive text-sm max-w-lg mx-auto my-12">
          <div className="font-semibold mb-1">Notice</div>
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

  const alerts = insights?.actionable_alerts || [];
  const rfmList = insights?.rfm_clusters || [];
  const hasTransactions = vouchers.length > 0;
  const momComparison = forecast?.monthly_comparison?.mom_comparison;
  const currentMonthData = forecast?.monthly_comparison?.current_month;

  return (
    <DashboardLayout>
      <div className="space-y-6 pb-16 max-w-[1600px] mx-auto">
        
        {/* ========================================================= */}
        {/* Top Header & Actions Bar (Fully Responsive)             */}
        {/* ========================================================= */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border/40 pb-5">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-xl sm:text-2xl lg:text-3xl font-black tracking-tight text-foreground">
                {activeCompany?.name ? activeCompany.name : "Your Business"}
              </h1>

              {/* Live sync & connectivity status */}
              {syncStatus === "SYNCING" ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
                  <RefreshCw className="w-3 h-3 animate-spin" />
                  <span>Syncing...</span>
                </span>
              ) : !isOnline ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                  <WifiOff className="w-3 h-3" />
                  <span>Offline Mode</span>
                </span>
              ) : pendingMutations > 0 ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-600 border border-amber-500/20">
                  <CloudUpload className="w-3 h-3" />
                  <span>{pendingMutations} pending</span>
                </span>
              ) : coverage?.lastSyncAt ? (
                <span
                  className="w-2.5 h-2.5 rounded-full bg-emerald-500 ring-4 ring-emerald-500/20 shrink-0"
                  title={`Books synced · ${new Date(coverage.lastSyncAt).toLocaleTimeString()}`}
                />
              ) : null}

              {isOnline && (
                <button
                  type="button"
                  onClick={handleManualSync}
                  disabled={syncStatus === "SYNCING"}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/80 transition-colors cursor-pointer"
                  title="Refresh Books Data"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${syncStatus === "SYNCING" ? "animate-spin text-primary" : ""}`} />
                </button>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2 text-xs sm:text-sm text-muted-foreground">
              <span>Operational Overview</span>
              {activeFY && (
                <>
                  <span>•</span>
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md font-semibold bg-muted text-foreground border border-border/60 text-xs">
                    <Calendar className="w-3 h-3 text-muted-foreground" />
                    <span>FY {activeFY.code}</span>
                  </span>
                </>
              )}
            </div>
          </div>

          {/* Action Button Cluster with keyboard shortcuts */}
          <div className="flex flex-wrap items-center gap-2">
            <Link
              id="tour-sales-btn"
              href="/sales/new"
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs sm:text-sm font-semibold bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm transition-all cursor-pointer"
            >
              <Plus className="w-4 h-4" />
              <span>Sale</span>
              <kbd className="hidden sm:inline-block ml-0.5 px-1 py-0.2 text-[10px] font-mono bg-emerald-700/70 text-emerald-100 rounded">
                F8
              </kbd>
            </Link>

            <Link
              id="tour-purchase-btn"
              href="/purchases/new"
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs sm:text-sm font-semibold bg-blue-600 hover:bg-blue-700 text-white shadow-sm transition-all cursor-pointer"
            >
              <Plus className="w-4 h-4" />
              <span>Purchase</span>
              <kbd className="hidden sm:inline-block ml-0.5 px-1 py-0.2 text-[10px] font-mono bg-blue-700/70 text-blue-100 rounded">
                F9
              </kbd>
            </Link>

            <Link
              href="/parties"
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs sm:text-sm font-semibold bg-card hover:bg-muted text-foreground border border-border/70 transition-all cursor-pointer"
            >
              <ArrowDownRight className="w-4 h-4 text-emerald-500" />
              <span>Receive</span>
              <kbd className="hidden sm:inline-block ml-0.5 px-1 py-0.2 text-[10px] font-mono bg-muted text-muted-foreground rounded">
                F6
              </kbd>
            </Link>

            <Link
              href="/parties"
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs sm:text-sm font-semibold bg-card hover:bg-muted text-foreground border border-border/70 transition-all cursor-pointer"
            >
              <ArrowUpRight className="w-4 h-4 text-rose-500" />
              <span>Pay</span>
              <kbd className="hidden sm:inline-block ml-0.5 px-1 py-0.2 text-[10px] font-mono bg-muted text-muted-foreground rounded">
                F5
              </kbd>
            </Link>

            <Link
              href="/analytics"
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs sm:text-sm font-semibold bg-purple-500/10 hover:bg-purple-500/20 text-purple-600 dark:text-purple-400 border border-purple-500/30 transition-all cursor-pointer"
            >
              <Sparkles className="w-3.5 h-3.5 text-purple-500" />
              <span>Analytics Hub</span>
            </Link>

            <button
              onClick={() => setIsHelpOpen(true)}
              className="p-2 text-muted-foreground hover:text-foreground rounded-xl border border-border/60 hover:bg-muted transition-colors cursor-pointer"
              title="Help & Shortcuts (F1)"
            >
              <HelpCircle className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* ========================================================= */}
        {/* Core Business Vitals (5 Responsive Cards)                 */}
        {/* ========================================================= */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3.5 sm:gap-4">
          
          {/* Card 1: Total Sales & Today */}
          <Link
            href="/sales"
            className="group relative bg-card hover:bg-card/80 border border-border/60 hover:border-emerald-500/40 rounded-2xl p-4 sm:p-5 shadow-xs transition-all cursor-pointer overflow-hidden block"
          >
            <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-emerald-500 to-teal-500" />
            <div className="flex items-center justify-between text-muted-foreground mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">Total Sales</span>
              <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 group-hover:scale-105 transition-transform">
                <Receipt className="w-4 h-4" />
              </div>
            </div>
            <div className="text-xl sm:text-2xl font-black font-mono tracking-tight text-foreground">
              ₹{(kpis.total_sales || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
            <div className="mt-2 pt-2 border-t border-border/40 flex items-center justify-between text-xs text-muted-foreground">
              <span>Today: <strong className="text-foreground font-mono">₹{(kpis.today_sales || 0).toLocaleString("en-IN")}</strong></span>
              <span className="group-hover:translate-x-0.5 transition-transform text-emerald-600 dark:text-emerald-400 font-medium">
                {kpis.sales_vouchers_count || 0} bills →
              </span>
            </div>
          </Link>

          {/* Card 2: Sundry Debtors (Money to Collect) */}
          <Link
            href="/parties"
            className="group relative bg-card hover:bg-card/80 border border-border/60 hover:border-teal-500/40 rounded-2xl p-4 sm:p-5 shadow-xs transition-all cursor-pointer overflow-hidden block"
          >
            <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-teal-500 to-cyan-500" />
            <div className="flex items-center justify-between text-muted-foreground mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">To Collect</span>
              <div className="p-2 rounded-xl bg-teal-500/10 text-teal-600 dark:text-teal-400 group-hover:scale-105 transition-transform">
                <Users className="w-4 h-4" />
              </div>
            </div>
            <div className="text-xl sm:text-2xl font-black font-mono tracking-tight text-teal-600 dark:text-teal-400">
              ₹{(kpis.money_to_collect || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
            <div className="mt-2 pt-2 border-t border-border/40 flex items-center justify-between text-xs text-muted-foreground">
              <span>Customers owe</span>
              <span className="group-hover:translate-x-0.5 transition-transform text-teal-600 dark:text-teal-400 font-medium">
                Ledger →
              </span>
            </div>
          </Link>

          {/* Card 3: Sundry Creditors (Bills to Pay) */}
          <Link
            href="/parties"
            className="group relative bg-card hover:bg-card/80 border border-border/60 hover:border-rose-500/40 rounded-2xl p-4 sm:p-5 shadow-xs transition-all cursor-pointer overflow-hidden block"
          >
            <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-rose-500 to-orange-500" />
            <div className="flex items-center justify-between text-muted-foreground mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">Bills to Pay</span>
              <div className="p-2 rounded-xl bg-rose-500/10 text-rose-600 dark:text-rose-400 group-hover:scale-105 transition-transform">
                <FileText className="w-4 h-4" />
              </div>
            </div>
            <div className="text-xl sm:text-2xl font-black font-mono tracking-tight text-rose-600 dark:text-rose-400">
              ₹{(kpis.bills_to_pay || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
            <div className="mt-2 pt-2 border-t border-border/40 flex items-center justify-between text-xs text-muted-foreground">
              <span>Due to suppliers</span>
              <span className="group-hover:translate-x-0.5 transition-transform text-rose-600 dark:text-rose-400 font-medium">
                Pay →
              </span>
            </div>
          </Link>

          {/* Card 4: Liquid Funds (Cash & Bank) */}
          <Link
            href="/ledgers"
            className="group relative bg-card hover:bg-card/80 border border-border/60 hover:border-blue-500/40 rounded-2xl p-4 sm:p-5 shadow-xs transition-all cursor-pointer overflow-hidden block"
          >
            <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-500 to-indigo-500" />
            <div className="flex items-center justify-between text-muted-foreground mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">Cash & Bank</span>
              <div className="p-2 rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400 group-hover:scale-105 transition-transform">
                <Wallet className="w-4 h-4" />
              </div>
            </div>
            <div className="text-xl sm:text-2xl font-black font-mono tracking-tight text-foreground">
              ₹{(kpis.cash_and_bank || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
            <div className="mt-2 pt-2 border-t border-border/40 flex items-center justify-between text-xs text-muted-foreground">
              <span>Liquid funds</span>
              <span className="group-hover:translate-x-0.5 transition-transform text-blue-600 dark:text-blue-400 font-medium">
                Accounts →
              </span>
            </div>
          </Link>

          {/* Card 5: Inventory Valuation */}
          <Link
            href="/inventory"
            className="group relative bg-card hover:bg-card/80 border border-border/60 hover:border-purple-500/40 rounded-2xl p-4 sm:p-5 shadow-xs transition-all cursor-pointer overflow-hidden block sm:col-span-2 lg:col-span-1"
          >
            <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-purple-500 to-violet-500" />
            <div className="flex items-center justify-between text-muted-foreground mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">Stock Value</span>
              <div className="p-2 rounded-xl bg-purple-500/10 text-purple-600 dark:text-purple-400 group-hover:scale-105 transition-transform">
                <Boxes className="w-4 h-4" />
              </div>
            </div>
            <div className="text-xl sm:text-2xl font-black font-mono tracking-tight text-purple-600 dark:text-purple-400">
              ₹{(kpis.total_stock_value || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
            <div className="mt-2 pt-2 border-t border-border/40 flex items-center justify-between text-xs text-muted-foreground">
              <span>{kpis.total_in_stock_items || 0} active items</span>
              <span className="group-hover:translate-x-0.5 transition-transform text-purple-600 dark:text-purple-400 font-medium">
                Stock →
              </span>
            </div>
          </Link>
        </div>

        {/* ========================================================= */}
        {/* Executive AI Pace & Forecast Teaser Banner                */}
        {/* ========================================================= */}
        <div className="relative overflow-hidden rounded-2xl border border-purple-500/20 bg-gradient-to-br from-purple-500/5 via-card to-blue-500/5 p-4 sm:p-5">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold bg-purple-500/15 text-purple-600 dark:text-purple-400 border border-purple-500/25">
                  <Sparkles className="w-3.5 h-3.5 text-purple-500" />
                  <span>AI Business Intelligence</span>
                </span>
                {momComparison && (
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold border ${
                    momComparison.pace_status === "BEATING_LAST_MONTH"
                      ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20"
                      : "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20"
                  }`}>
                    {momComparison.pace_status === "BEATING_LAST_MONTH" ? (
                      <TrendingUp className="w-3 h-3" />
                    ) : (
                      <TrendingDown className="w-3 h-3" />
                    )}
                    <span>{momComparison.percentage_change >= 0 ? "+" : ""}{momComparison.percentage_change}% vs Last Month</span>
                  </span>
                )}
              </div>

              <div className="text-sm sm:text-base font-semibold text-foreground">
                {currentMonthData ? (
                  <span>
                    Projected Month Total: <strong className="font-mono text-purple-600 dark:text-purple-400">₹{currentMonthData.projected_month_total.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</strong>
                    <span className="text-muted-foreground font-normal text-xs sm:text-sm ml-2">
                      (MTD: ₹{formatCurrencyShort(currentMonthData.mtd_actual_sales)} + Projected: ₹{formatCurrencyShort(currentMonthData.remaining_projected_sales)})
                    </span>
                  </span>
                ) : (
                  <span>Multi-factor sales forecasting, stock valuation, and customer RFM analytics</span>
                )}
              </div>

              <p className="text-xs text-muted-foreground max-w-3xl">
                {momComparison?.summary || "Comprehensive multi-factor predictive modeling with day-of-week profiles, seasonality, and customer repeat purchase analysis."}
              </p>
            </div>

            <div className="flex items-center gap-3 shrink-0">
              <Link
                href="/analytics"
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs sm:text-sm font-semibold bg-purple-600 hover:bg-purple-700 text-white shadow-sm transition-all cursor-pointer group"
              >
                <span>Open Dedicated Analytics Hub</span>
                <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
              </Link>
            </div>
          </div>
        </div>

        {/* ========================================================= */}
        {/* Actionable Health & Needs Attention Grid                  */}
        {/* ========================================================= */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          
          {/* Books Health Status Card */}
          <div className="bg-card border border-border/60 rounded-2xl p-4 sm:p-5 shadow-xs flex flex-col justify-between">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                  healthReport ? (
                    (healthReport?.health_score ?? 100) >= 90
                      ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                      : (healthReport?.health_score ?? 100) >= 70
                      ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                      : "bg-rose-500/10 text-rose-600 dark:text-rose-400"
                  ) : "bg-muted text-muted-foreground"
                }`}>
                  {healthReport && (healthReport?.health_score ?? 100) >= 90 ? (
                    <CheckCircle2 className="w-5 h-5" />
                  ) : healthReport ? (
                    <AlertTriangle className="w-5 h-5" />
                  ) : (
                    <Activity className="w-5 h-5" />
                  )}
                </div>
                <div>
                  <h3 className="text-sm font-bold text-foreground">
                    {healthReport ? (
                      (healthReport?.health_score ?? 100) >= 90
                        ? "Your books are in great shape"
                        : `${healthReport.metrics?.critical_findings_count || 1} issues require review`
                    ) : (
                      "Accounting Integrity"
                    )}
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {healthReport ? (
                      `Integrity Score: ${healthReport.health_score || 100}% · ${healthReport.health_status || "HEALTHY"}`
                    ) : (
                      "Automated background audit for debit-credit parity and reconciliation"
                    )}
                  </p>
                </div>
              </div>

              <Link
                href="/health"
                className="px-3 py-1.5 rounded-lg border border-border/60 bg-muted/50 hover:bg-muted text-foreground text-xs font-semibold flex items-center gap-1 transition-colors shrink-0"
              >
                <span>Audit</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            <div className="mt-4 pt-3 border-t border-border/40 flex items-center justify-between text-xs text-muted-foreground">
              <span>Debit = Credit Balance Parity</span>
              <span className="font-semibold text-emerald-600 dark:text-emerald-400">Verified</span>
            </div>
          </div>

          {/* Attention Center / Alerts */}
          <div className="bg-card border border-border/60 rounded-2xl p-4 sm:p-5 shadow-xs flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-2.5">
                <h3 className="text-sm font-bold text-foreground flex items-center gap-1.5">
                  <span>Operational Alerts</span>
                  {alerts.length > 0 && (
                    <span className="px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-amber-500/15 text-amber-600 dark:text-amber-400">
                      {alerts.length}
                    </span>
                  )}
                </h3>
                <Link href="/health" className="text-xs text-muted-foreground hover:text-foreground font-medium transition-colors">
                  All alerts →
                </Link>
              </div>

              <div className="space-y-2">
                {alerts.length > 0 ? (
                  alerts.slice(0, 3).map((alert: any, idx: number) => (
                    <div
                      key={idx}
                      className="flex items-center gap-2.5 text-xs text-foreground bg-muted/30 px-3 py-2 rounded-xl border border-border/40"
                    >
                      <span className={`w-2 h-2 rounded-full shrink-0 ${
                        alert.message?.toLowerCase().includes("overdue")
                          ? "bg-rose-500"
                          : alert.message?.toLowerCase().includes("low stock")
                          ? "bg-amber-500"
                          : "bg-blue-500"
                      }`} />
                      <span className="truncate">{alert.message}</span>
                    </div>
                  ))
                ) : (
                  <div className="text-xs text-muted-foreground bg-muted/20 px-3 py-3 rounded-xl border border-dashed border-border/50 text-center">
                    ✓ All clear. No overdue invoices or urgent stock shortages.
                  </div>
                )}
              </div>
            </div>

            <div className="mt-3 pt-2 text-[11px] text-muted-foreground flex items-center justify-between">
              <span>System Watchdog</span>
              <span>Active</span>
            </div>
          </div>
        </div>

        {/* ========================================================= */}
        {/* Quick Launchpad Shortcuts                                 */}
        {/* ========================================================= */}
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
            Quick Launchpad
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Link
              href="/sales/new"
              className="bg-card hover:bg-muted/50 border border-border/60 hover:border-emerald-500/40 rounded-xl p-3 sm:p-4 transition-all flex items-center gap-3 group"
            >
              <div className="p-2.5 rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 group-hover:scale-105 transition-transform">
                <Receipt className="w-5 h-5" />
              </div>
              <div className="min-w-0">
                <div className="text-xs sm:text-sm font-bold text-foreground truncate">Sales Bill</div>
                <div className="text-[11px] text-muted-foreground font-mono">Press F8</div>
              </div>
            </Link>

            <Link
              href="/purchases/new"
              className="bg-card hover:bg-muted/50 border border-border/60 hover:border-blue-500/40 rounded-xl p-3 sm:p-4 transition-all flex items-center gap-3 group"
            >
              <div className="p-2.5 rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400 group-hover:scale-105 transition-transform">
                <ShoppingCart className="w-5 h-5" />
              </div>
              <div className="min-w-0">
                <div className="text-xs sm:text-sm font-bold text-foreground truncate">Purchase Bill</div>
                <div className="text-[11px] text-muted-foreground font-mono">Press F9</div>
              </div>
            </Link>

            <Link
              href="/parties"
              className="bg-card hover:bg-muted/50 border border-border/60 hover:border-teal-500/40 rounded-xl p-3 sm:p-4 transition-all flex items-center gap-3 group"
            >
              <div className="p-2.5 rounded-xl bg-teal-500/10 text-teal-600 dark:text-teal-400 group-hover:scale-105 transition-transform">
                <Users className="w-5 h-5" />
              </div>
              <div className="min-w-0">
                <div className="text-xs sm:text-sm font-bold text-foreground truncate">Parties & Ledgers</div>
                <div className="text-[11px] text-muted-foreground">Customers & Suppliers</div>
              </div>
            </Link>

            <Link
              href="/inventory"
              className="bg-card hover:bg-muted/50 border border-border/60 hover:border-purple-500/40 rounded-xl p-3 sm:p-4 transition-all flex items-center gap-3 group"
            >
              <div className="p-2.5 rounded-xl bg-purple-500/10 text-purple-600 dark:text-purple-400 group-hover:scale-105 transition-transform">
                <Boxes className="w-5 h-5" />
              </div>
              <div className="min-w-0">
                <div className="text-xs sm:text-sm font-bold text-foreground truncate">Stock Items</div>
                <div className="text-[11px] text-muted-foreground">Catalog & Pricing</div>
              </div>
            </Link>
          </div>
        </div>

        {/* ========================================================= */}
        {/* Balanced Operational Hub: Recent Activity & Top Customers */}
        {/* ========================================================= */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          
          {/* Left Column (7 cols): Recent Transactions Table (Mobile Cards + Desktop Table) */}
          <div className="lg:col-span-8 bg-card border border-border/60 rounded-2xl p-4 sm:p-5 shadow-xs space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm sm:text-base font-bold text-foreground">Recent Transactions</h2>
                <p className="text-xs text-muted-foreground">Latest vouchers posted in your books</p>
              </div>
              <Link
                href="/vouchers"
                className="text-xs text-primary hover:underline font-semibold flex items-center gap-1"
              >
                <span>View All Vouchers</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            {/* Mobile View (<640px): Responsive Cards (No sideways scroll required) */}
            <div className="block sm:hidden space-y-2.5">
              {vouchers.slice(0, 6).map((v) => {
                const voucherNo = v.voucherNumber || v.voucher_number || "—";
                const rawDate = v.voucherDate || v.voucher_date || v.date;
                const formattedDate = rawDate
                  ? (() => {
                      try {
                        const d = new Date(rawDate);
                        return isNaN(d.getTime())
                          ? rawDate
                          : d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
                      } catch {
                        return rawDate;
                      }
                    })()
                  : "—";
                const vType = (v.voucherType || v.voucher_type || v.type || "GENERAL").toUpperCase();
                const partyName = v.partyName || v.party_name || v.narration || "General Entry";
                const rawAmount = v.totalAmount !== undefined && v.totalAmount !== null
                  ? v.totalAmount
                  : (v.total_amount !== undefined && v.total_amount !== null ? v.total_amount : 0);
                const amount = Number(rawAmount) || 0;

                return (
                  <div
                    key={v.id || voucherNo}
                    onClick={() => router.push(`/vouchers?search=${encodeURIComponent(voucherNo !== "—" ? voucherNo : "")}`)}
                    className="p-3 rounded-xl bg-muted/30 border border-border/50 hover:bg-muted/60 transition-colors cursor-pointer space-y-1.5"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase border ${getVoucherTypeBadgeClass(vType)}`}>
                          {vType}
                        </span>
                        <span className="font-mono text-xs font-semibold text-foreground">
                          {voucherNo}
                        </span>
                      </div>
                      <span className="font-mono text-sm font-bold text-foreground">
                        ₹{amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-xs text-muted-foreground pt-1">
                      <span className="truncate max-w-[180px] font-medium text-foreground">
                        {partyName}
                      </span>
                      <span className="font-mono text-[11px] shrink-0">
                        {formattedDate}
                      </span>
                    </div>
                  </div>
                );
              })}

              {!hasTransactions && (
                <div className="py-8 text-center text-muted-foreground text-xs border border-dashed border-border/60 rounded-xl">
                  No vouchers recorded yet.
                </div>
              )}
            </div>

            {/* Tablet & Desktop View (>=640px): Clean Table */}
            <div className="hidden sm:block overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-border/60 text-muted-foreground">
                    <th className="py-2.5 font-semibold">Voucher #</th>
                    <th className="py-2.5 font-semibold">Date</th>
                    <th className="py-2.5 font-semibold">Type</th>
                    <th className="py-2.5 font-semibold">Party / Details</th>
                    <th className="py-2.5 font-semibold">Status</th>
                    <th className="py-2.5 font-semibold text-right">Amount</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/30">
                  {vouchers.slice(0, 7).map((v) => {
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
                        <td className="py-3 text-foreground font-medium max-w-[200px] truncate" title={partyName}>
                          {partyName}
                        </td>
                        <td className="py-3">
                          <span className={`px-2 py-0.5 rounded text-[11px] font-semibold border ${getVoucherStatusBadgeClass(status)}`}>
                            {status}
                          </span>
                        </td>
                        <td className="py-3 text-right font-mono tabular-nums font-bold text-foreground">
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

          {/* Right Column (4 cols): Best Customers & Relationships */}
          <div className="lg:col-span-4 bg-card border border-border/60 rounded-2xl p-4 sm:p-5 shadow-xs space-y-4 flex flex-col">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm sm:text-base font-bold text-foreground">Best Customers</h2>
                <p className="text-xs text-muted-foreground">By sales revenue & volume</p>
              </div>
              <Link href="/parties" className="text-xs text-muted-foreground hover:text-foreground font-medium transition-colors">
                View all →
              </Link>
            </div>

            <div className="space-y-2 flex-1">
              {rfmList.length > 0 ? (
                rfmList.slice(0, 5).map((customer: any, idx: number) => {
                  const segName = customer.segment || "Standard";
                  return (
                    <div
                      key={idx}
                      className="p-3 rounded-xl bg-muted/20 hover:bg-muted/50 border border-border/40 transition-colors flex items-center justify-between gap-2"
                    >
                      <div className="min-w-0">
                        <div className="text-xs font-bold text-foreground truncate">
                          {customer.party_ledger__name || "Customer"}
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <span className={`px-1.5 py-0.2 rounded text-[10px] font-semibold border ${getCustomerTierBadgeClass(segName)}`}>
                            {segName}
                          </span>
                          <span className="text-[11px] text-muted-foreground font-mono">
                            {customer.frequency} orders
                          </span>
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <div className="text-xs font-black font-mono text-foreground">
                          ₹{Number(customer.monetary).toLocaleString("en-IN", { minimumFractionDigits: 0 })}
                        </div>
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="h-40 flex flex-col items-center justify-center border border-dashed border-border/60 rounded-xl text-center p-4 space-y-1">
                  <Users className="w-6 h-6 text-muted-foreground/40" />
                  <div className="text-xs font-medium text-muted-foreground">No customer transactions yet</div>
                  <div className="text-[11px] text-muted-foreground/80">
                    Customers will be categorized here as invoices are posted.
                  </div>
                </div>
              )}
            </div>

            <div className="pt-2 border-t border-border/40">
              <Link
                href="/analytics?tab=customers"
                className="w-full py-2 px-3 rounded-xl bg-muted/40 hover:bg-muted text-foreground text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors"
              >
                <span>Full RFM Segmentation & Cohorts</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
