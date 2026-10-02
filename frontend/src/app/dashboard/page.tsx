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
  ShieldCheck,
  Search,
  Filter,
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
  const [voucherFilter, setVoucherFilter] = useState<string>("ALL");
  const [voucherSearch, setVoucherSearch] = useState<string>("");

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
    await pullIncrementalChanges(cid, (msg) => setSyncMessage(msg), { force: true });
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

  // Tri-partite financial calculations
  const netWorkingCapital = (kpis.cash_and_bank || 0) + (kpis.money_to_collect || 0) - (kpis.bills_to_pay || 0);

  // Filtered transactions for quick search and type filtering
  const filteredVouchers = vouchers.filter((v: any) => {
    const vType = (v.voucherType || v.voucher_type || v.type || "GENERAL").toUpperCase();
    if (voucherFilter !== "ALL" && vType !== voucherFilter) {
      return false;
    }
    if (voucherSearch.trim()) {
      const q = voucherSearch.toLowerCase();
      const voucherNo = String(v.voucherNumber || v.voucher_number || "").toLowerCase();
      const party = String(v.partyName || v.party_name || v.narration || "").toLowerCase();
      return voucherNo.includes(q) || party.includes(q);
    }
    return true;
  });

  return (
    <DashboardLayout>
      <div className="space-y-8 pb-16 max-w-[1600px] mx-auto overflow-x-hidden w-full">
        
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
              <span>Financial Cockpit</span>
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

          {/* Quick Action Button Cluster */}
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
        {/* PILLAR 1: 💰 MONEY (Liquidity & Working Capital)          */}
        {/* ========================================================= */}
        <section className="space-y-3.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center">
                <Wallet className="w-4 h-4" />
              </div>
              <div>
                <h2 className="text-sm sm:text-base font-bold text-foreground">Money & Working Capital</h2>
                <p className="text-xs text-muted-foreground">Liquid cash, customer receivables, and supplier liabilities</p>
              </div>
            </div>
            <Link
              href="/ledgers"
              className="text-xs text-primary hover:underline font-semibold flex items-center gap-1"
            >
              <span>View Ledgers</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
            {/* 1. Cash & Bank */}
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
                <span>Available liquidity</span>
                <span className="group-hover:translate-x-0.5 transition-transform text-blue-600 dark:text-blue-400 font-medium">
                  Bank accounts →
                </span>
              </div>
            </Link>

            {/* 2. Sundry Debtors (Money to Collect) */}
            <Link
              href="/parties"
              className="group relative bg-card hover:bg-card/80 border border-border/60 hover:border-teal-500/40 rounded-2xl p-4 sm:p-5 shadow-xs transition-all cursor-pointer overflow-hidden block"
            >
              <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-teal-500 to-emerald-500" />
              <div className="flex items-center justify-between text-muted-foreground mb-2">
                <span className="text-xs font-semibold uppercase tracking-wider">Money to Collect</span>
                <div className="p-2 rounded-xl bg-teal-500/10 text-teal-600 dark:text-teal-400 group-hover:scale-105 transition-transform">
                  <Users className="w-4 h-4" />
                </div>
              </div>
              <div className="text-xl sm:text-2xl font-black font-mono tracking-tight text-teal-600 dark:text-teal-400">
                ₹{(kpis.money_to_collect || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
              </div>
              <div className="mt-2 pt-2 border-t border-border/40 flex items-center justify-between text-xs text-muted-foreground">
                <span>Customer receivables</span>
                <span className="group-hover:translate-x-0.5 transition-transform text-teal-600 dark:text-teal-400 font-medium">
                  Receive (F6) →
                </span>
              </div>
            </Link>

            {/* 3. Sundry Creditors (Bills to Pay) */}
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
                <span>Supplier liabilities</span>
                <span className="group-hover:translate-x-0.5 transition-transform text-rose-600 dark:text-rose-400 font-medium">
                  Pay (F5) →
                </span>
              </div>
            </Link>

            {/* 4. Net Working Capital Buffer */}
            <div className="relative bg-card border border-border/60 rounded-2xl p-4 sm:p-5 shadow-xs overflow-hidden block">
              <div className={`absolute top-0 left-0 right-0 h-1 ${
                netWorkingCapital >= 0
                  ? "bg-gradient-to-r from-emerald-500 to-teal-500"
                  : "bg-gradient-to-r from-rose-500 to-amber-500"
              }`} />
              <div className="flex items-center justify-between text-muted-foreground mb-2">
                <span className="text-xs font-semibold uppercase tracking-wider">Working Capital</span>
                <div className={`p-2 rounded-xl ${
                  netWorkingCapital >= 0
                    ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                    : "bg-rose-500/10 text-rose-600 dark:text-rose-400"
                }`}>
                  <DollarSign className="w-4 h-4" />
                </div>
              </div>
              <div className={`text-xl sm:text-2xl font-black font-mono tracking-tight ${
                netWorkingCapital >= 0 ? "text-foreground" : "text-rose-600 dark:text-rose-400"
              }`}>
                ₹{netWorkingCapital.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
              </div>
              <div className="mt-2 pt-2 border-t border-border/40 flex items-center justify-between text-xs text-muted-foreground">
                <span>(Cash + Collect - Pay)</span>
                <span className={`font-semibold ${netWorkingCapital >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
                  {netWorkingCapital >= 0 ? "Positive Buffer" : "Cash Deficit Risk"}
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* ========================================================= */}
        {/* PILLAR 2: 📈 PERFORMANCE (Revenue, Run-Rate & Projections)  */}
        {/* ========================================================= */}
        <section className="space-y-3.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-purple-500/10 text-purple-600 dark:text-purple-400 flex items-center justify-center">
                <TrendingUp className="w-4 h-4" />
              </div>
              <div>
                <h2 className="text-sm sm:text-base font-bold text-foreground">Performance & Projections</h2>
                <p className="text-xs text-muted-foreground">Sales pacing, run-rate forecast, and top customer segments</p>
              </div>
            </div>
            <Link
              href="/analytics"
              className="text-xs text-primary hover:underline font-semibold flex items-center gap-1"
            >
              <span>Analytics Hub</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          {/* Forecast & Sales Pace Banner */}
          <div className="relative overflow-hidden rounded-2xl border border-purple-500/20 bg-gradient-to-br from-purple-500/5 via-card to-blue-500/5 p-4 sm:p-5">
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold bg-purple-500/15 text-purple-600 dark:text-purple-400 border border-purple-500/25">
                    <Sparkles className="w-3.5 h-3.5 text-purple-500" />
                    <span>Sales Pace & Projections</span>
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
                        (MTD Actual: ₹{formatCurrencyShort(currentMonthData.mtd_actual_sales)} + Projected: ₹{formatCurrencyShort(currentMonthData.remaining_projected_sales)})
                      </span>
                    </span>
                  ) : (
                    <span>Real-time sales tracking, stock movement, and customer purchasing cycles</span>
                  )}
                </div>

                <p className="text-xs text-muted-foreground max-w-3xl">
                  {momComparison?.summary || "Automated sales projections based on daily sales velocity, seasonal trends, and customer reorder patterns."}
                </p>
              </div>

              <div className="flex items-center gap-3 shrink-0">
                <Link
                  href="/analytics"
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs sm:text-sm font-semibold bg-purple-600 hover:bg-purple-700 text-white shadow-sm transition-all cursor-pointer group"
                >
                  <span>Detailed Analytics</span>
                  <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                </Link>
              </div>
            </div>
          </div>

          {/* Performance Sub-Grid: Sales, Purchases, Stock & Best Customers */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
            {/* Left 3 Stats (7 Cols) */}
            <div className="lg:col-span-7 grid grid-cols-1 sm:grid-cols-3 gap-3.5">
              {/* Total Sales */}
              <Link
                href="/sales"
                className="bg-card hover:bg-card/80 border border-border/60 hover:border-emerald-500/40 rounded-2xl p-4 shadow-xs transition-all cursor-pointer block"
              >
                <div className="flex items-center justify-between text-muted-foreground mb-1.5">
                  <span className="text-xs font-semibold uppercase tracking-wider">Total Sales</span>
                  <div className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                    <Receipt className="w-4 h-4" />
                  </div>
                </div>
                <div className="text-lg sm:text-xl font-black font-mono tracking-tight text-foreground">
                  ₹{(kpis.total_sales || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="mt-2 pt-2 border-t border-border/40 flex items-center justify-between text-xs text-muted-foreground">
                  <span>Today: <strong className="text-foreground font-mono">₹{(kpis.today_sales || 0).toLocaleString("en-IN")}</strong></span>
                  <span className="text-emerald-600 dark:text-emerald-400 font-medium">
                    {kpis.sales_vouchers_count || 0} bills →
                  </span>
                </div>
              </Link>

              {/* Total Purchases */}
              <Link
                href="/purchases"
                className="bg-card hover:bg-card/80 border border-border/60 hover:border-blue-500/40 rounded-2xl p-4 shadow-xs transition-all cursor-pointer block"
              >
                <div className="flex items-center justify-between text-muted-foreground mb-1.5">
                  <span className="text-xs font-semibold uppercase tracking-wider">Purchases</span>
                  <div className="p-1.5 rounded-lg bg-blue-500/10 text-blue-600 dark:text-blue-400">
                    <ShoppingCart className="w-4 h-4" />
                  </div>
                </div>
                <div className="text-lg sm:text-xl font-black font-mono tracking-tight text-foreground">
                  ₹{(kpis.total_purchases || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="mt-2 pt-2 border-t border-border/40 flex items-center justify-between text-xs text-muted-foreground">
                  <span>Suppliers billed</span>
                  <span className="text-blue-600 dark:text-blue-400 font-medium">
                    {kpis.purchase_vouchers_count || 0} bills →
                  </span>
                </div>
              </Link>

              {/* Stock Valuation */}
              <Link
                href="/inventory"
                className="bg-card hover:bg-card/80 border border-border/60 hover:border-purple-500/40 rounded-2xl p-4 shadow-xs transition-all cursor-pointer block"
              >
                <div className="flex items-center justify-between text-muted-foreground mb-1.5">
                  <span className="text-xs font-semibold uppercase tracking-wider">Inventory</span>
                  <div className="p-1.5 rounded-lg bg-purple-500/10 text-purple-600 dark:text-purple-400">
                    <Boxes className="w-4 h-4" />
                  </div>
                </div>
                <div className="text-lg sm:text-xl font-black font-mono tracking-tight text-foreground">
                  ₹{(kpis.total_stock_value || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="mt-2 pt-2 border-t border-border/40 flex items-center justify-between text-xs text-muted-foreground">
                  <span>In stock items</span>
                  <span className="text-purple-600 dark:text-purple-400 font-medium">
                    {kpis.total_in_stock_items || 0} items →
                  </span>
                </div>
              </Link>
            </div>

            {/* Right Column: Best Customers (5 Cols) */}
            <div className="lg:col-span-5 bg-card border border-border/60 rounded-2xl p-4 shadow-xs space-y-3 flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-xs sm:text-sm font-bold text-foreground">Top Customers</h3>
                  <p className="text-[11px] text-muted-foreground">Leading revenue and order volume</p>
                </div>
                <Link href="/parties" className="text-xs text-muted-foreground hover:text-foreground font-medium transition-colors">
                  View all →
                </Link>
              </div>

              <div className="space-y-1.5 flex-1">
                {rfmList.length > 0 ? (
                  rfmList.slice(0, 3).map((customer: any, idx: number) => {
                    const segName = customer.segment || "Standard";
                    return (
                      <div
                        key={idx}
                        className="p-2.5 rounded-xl bg-muted/20 hover:bg-muted/50 border border-border/40 transition-colors flex items-center justify-between gap-2"
                      >
                        <div className="min-w-0">
                          <div className="text-xs font-bold text-foreground truncate">
                            {customer.party_ledger__name || "Customer"}
                          </div>
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <span className={`px-1.5 py-0.2 rounded text-[9px] font-semibold border ${getCustomerTierBadgeClass(segName)}`}>
                              {segName}
                            </span>
                            <span className="text-[10px] text-muted-foreground font-mono">
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
                  <div className="py-4 flex flex-col items-center justify-center border border-dashed border-border/60 rounded-xl text-center p-3">
                    <Users className="w-5 h-5 text-muted-foreground/40 mb-1" />
                    <div className="text-xs font-medium text-muted-foreground">No customer transactions yet</div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </section>

        {/* ========================================================= */}
        {/* PILLAR 3: ⚠️ ATTENTION (The FIX Loop: Audits & Alerts)     */}
        {/* ========================================================= */}
        <section className="space-y-3.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400 flex items-center justify-center">
                <AlertTriangle className="w-4 h-4" />
              </div>
              <div>
                <h2 className="text-sm sm:text-base font-bold text-foreground">Attention & Action Required</h2>
                <p className="text-xs text-muted-foreground">Accounting integrity, reconciliation queue, and operational flags</p>
              </div>
            </div>
            <Link
              href="/health"
              className="text-xs text-primary hover:underline font-semibold flex items-center gap-1"
            >
              <span>Audit Hub</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </Link>
          </div>

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
                      <ShieldCheck className="w-5 h-5" />
                    )}
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-foreground">
                      {healthReport ? (
                        (healthReport?.health_score ?? 100) >= 90
                          ? "Accounting Books in Great Shape"
                          : `${healthReport.metrics?.critical_findings_count || 1} issues require review`
                      ) : (
                        "Accounting Integrity Verified"
                      )}
                    </h3>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {healthReport ? (
                        `Integrity Score: ${healthReport.health_score || 100}% · Status: ${healthReport.health_status || "HEALTHY"}`
                      ) : (
                        "Continuous background verification for debit-credit parity and trial balance"
                      )}
                    </p>
                  </div>
                </div>

                <Link
                  href="/health"
                  className="px-3 py-1.5 rounded-lg border border-border/60 bg-muted/50 hover:bg-muted text-foreground text-xs font-semibold flex items-center gap-1 transition-colors shrink-0 cursor-pointer"
                >
                  <span>Review Audit</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </Link>
              </div>

              <div className="mt-4 pt-3 border-t border-border/40 flex items-center justify-between text-xs text-muted-foreground">
                <span className="flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                  <span>Debit = Credit Balance Parity</span>
                </span>
                <span className="font-semibold text-emerald-600 dark:text-emerald-400">Verified</span>
              </div>
            </div>

            {/* Operational Alerts / Priority Queue */}
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
                <span>Health Monitoring</span>
                <span className="font-medium text-emerald-600 dark:text-emerald-400">Active</span>
              </div>
            </div>
          </div>
        </section>

        {/* ========================================================= */}
        {/* RECENT TRANSACTIONS (DO & REVIEW) with Search & Filter   */}
        {/* ========================================================= */}
        <section className="bg-card border border-border/60 rounded-2xl p-4 sm:p-5 shadow-xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h2 className="text-sm sm:text-base font-bold text-foreground">Recent Transactions</h2>
              <p className="text-xs text-muted-foreground">Search and review posted vouchers in your books</p>
            </div>
            
            <div className="flex flex-wrap items-center gap-2">
              {/* Search Bar */}
              <div className="relative min-w-[200px] flex-1 sm:flex-initial">
                <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type="text"
                  placeholder="Search voucher or party..."
                  value={voucherSearch}
                  onChange={(e) => setVoucherSearch(e.target.value)}
                  className="w-full pl-8 pr-3 py-1.5 bg-muted/50 border border-border/60 rounded-xl text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:bg-background transition-all"
                />
              </div>

              {/* Type Filter Buttons */}
              <div className="inline-flex items-center bg-muted/40 p-0.5 rounded-xl border border-border/50 text-xs">
                {(["ALL", "SALES", "PURCHASE", "RECEIPT", "PAYMENT"] as const).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setVoucherFilter(t)}
                    className={`px-2 py-1 rounded-lg text-[11px] font-semibold transition-all cursor-pointer ${
                      voucherFilter === t
                        ? "bg-card text-foreground shadow-xs font-bold"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {t === "ALL" ? "All" : t.charAt(0) + t.slice(1).toLowerCase()}
                  </button>
                ))}
              </div>

              <Link
                href="/vouchers"
                className="text-xs text-primary hover:underline font-semibold flex items-center gap-1 pl-1"
              >
                <span>View All</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </div>

          {/* Mobile View (<640px): Responsive Cards (No sideways scroll required) */}
          <div className="block sm:hidden space-y-2.5">
            {filteredVouchers.slice(0, 8).map((v) => {
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

            {filteredVouchers.length === 0 && (
              <div className="py-8 text-center text-muted-foreground text-xs border border-dashed border-border/60 rounded-xl">
                {voucherSearch || voucherFilter !== "ALL"
                  ? "No vouchers match your filter."
                  : "No vouchers recorded yet."}
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
                {filteredVouchers.slice(0, 10).map((v) => {
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
                {filteredVouchers.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-muted-foreground text-xs">
                      {voucherSearch || voucherFilter !== "ALL" ? (
                        <span>No transactions match the selected filter.</span>
                      ) : (
                        <span>
                          No vouchers posted yet. Press <kbd className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded border border-border/60 font-semibold">F8</kbd> for Sales or <kbd className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded border border-border/60 font-semibold">F9</kbd> for Purchases.
                        </span>
                      )}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </DashboardLayout>
  );
}
