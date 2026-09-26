"use client";

import React, { useEffect, useState, useMemo } from "react";
import axios from "axios";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import DashboardLayout from "@/components/DashboardLayout";
import { useToast } from "@/context/ToastContext";
import { useCompany } from "@/context/CompanyContext";
import {
  ShieldCheck,
  AlertTriangle,
  AlertOctagon,
  CheckCircle2,
  RefreshCw,
  Search,
  Wrench,
  Sparkles,
  X,
  ChevronDown,
  ChevronUp,
  Scale,
  Layers,
  History,
  Check,
  Package,
  ArrowRight,
  TrendingDown,
} from "lucide-react";

interface HealthCheckSummary {
  name: string;
  category: string;
  status: "PASSED" | "WARNING" | "CRITICAL";
  findings_count: number;
  description: string;
}

interface AccountingFindingItem {
  id: string;
  code: string;
  category: string;
  severity: "CRITICAL" | "WARNING" | "INFO";
  title: string;
  description: string;
  suggested_fix?: string;
  evidence: Record<string, any>;
  is_actionable: boolean;
  fix_type?: string;
  status: "UNRESOLVED" | "RESOLVED" | "IGNORED";
  created_at: string;
}

interface HealthReport {
  timestamp: string;
  health_score: number;
  health_status: "HEALTHY" | "NEEDS_ATTENTION" | "CRITICAL";
  metrics: {
    total_checks: number;
    passed_checks: number;
    critical_findings_count: number;
    warning_findings_count: number;
    info_findings_count: number;
  };
  checks: HealthCheckSummary[];
  findings: AccountingFindingItem[];
}

interface FixPreviewData {
  finding_id: string;
  finding_title: string;
  fix_type: string;
  summary: string;
  requires_user_confirmation: boolean;
  history_preservation_note: string;
  before: Record<string, any>;
  after: Record<string, any>;
  preview_comparison: Array<{
    account: string;
    before_balance: string;
    after_balance: string;
    impact: string;
  }>;
}

export default function HealthPage() {
  const router = useRouter();
  const { toast } = useToast();

  const { activeCompany, companyId: activeCompanyId } = useCompany();
  const [companyId, setCompanyId] = useState<string>(activeCompanyId || "");
  const [report, setReport] = useState<HealthReport | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<"ALL" | "DUPLICATES" | "CRITICAL" | "WARNING" | "ACTIONABLE">("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Expandable audits checklist
  const [isChecksExpanded, setIsChecksExpanded] = useState<boolean>(false);

  // Forensic Balance Diagnostic Dialog
  const [isDiagnosticOpen, setIsDiagnosticOpen] = useState<boolean>(false);
  const [diagnosing, setDiagnosing] = useState<boolean>(false);
  const [diagnosticResult, setDiagnosticResult] = useState<any | null>(null);

  // Fix Preview Modal State
  const [previewFinding, setPreviewFinding] = useState<AccountingFindingItem | null>(null);
  const [previewData, setPreviewData] = useState<FixPreviewData | null>(null);
  const [loadingPreview, setLoadingPreview] = useState<boolean>(false);
  const [executingFix, setExecutingFix] = useState<boolean>(false);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }
    initializeData();
  }, [router, activeCompanyId]);

  useEffect(() => {
    if (activeCompanyId && activeCompanyId !== companyId) {
      setCompanyId(activeCompanyId);
      fetchHealthReport(activeCompanyId);
    }
  }, [activeCompanyId]);

  const getHeaders = () => {
    const token = getAccessToken();
    return {
      Authorization: `Bearer ${token}`,
      "X-Company-ID": companyId,
    };
  };

  const initializeData = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = getAccessToken();
      let cid = activeCompanyId;
      if (!cid && typeof window !== "undefined") {
        cid = localStorage.getItem("vouch_active_company_id");
      }
      if (!cid) {
        const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const list = Array.isArray(compRes.data) ? compRes.data : (compRes.data.data || []);
        cid = list[0]?.id;
      }
      if (!cid) {
        setError("No active company found. Please create or select a company first.");
        setLoading(false);
        return;
      }
      setCompanyId(cid);
      await fetchHealthReport(cid);
    } catch (err: any) {
      console.error(err);
      setError(err.message || "Failed to initialize health audit");
    } finally {
      setLoading(false);
    }
  };

  const fetchHealthReport = async (cid?: string) => {
    const targetCid = cid || companyId;
    if (!targetCid) return;
    setRefreshing(true);
    setError(null);
    try {
      const token = getAccessToken();
      const headers = {
        Authorization: `Bearer ${token}`,
        "X-Company-ID": targetCid,
      };
      const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/health/?company_id=${targetCid}`, { headers });
      setReport(res.data);
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.error || err.message || "Could not complete accounting checks.");
      toast.error("Audit error", err.message || "Could not complete accounting checks.");
    } finally {
      setRefreshing(false);
    }
  };

  const runDiagnostic = async () => {
    if (!companyId) return;
    setDiagnosing(true);
    setIsDiagnosticOpen(true);
    try {
      const headers = getHeaders();
      const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/health/diagnose-balance/?company_id=${companyId}`, { headers });
      setDiagnosticResult(res.data);
    } catch (err: any) {
      toast.error("Diagnostic failed", err.message || "Could not diagnose balance.");
    } finally {
      setDiagnosing(false);
    }
  };

  const openFixPreview = async (finding: AccountingFindingItem) => {
    setPreviewFinding(finding);
    setLoadingPreview(true);
    try {
      const headers = getHeaders();
      const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/health/findings/${finding.id}/preview/?company_id=${companyId}`, {
        headers,
      });
      setPreviewData(res.data);
    } catch (err: any) {
      toast.error("Preview unavailable", err.response?.data?.error || err.message);
      setPreviewFinding(null);
    } finally {
      setLoadingPreview(false);
    }
  };

  const executeFix = async () => {
    if (!previewFinding) return;
    setExecutingFix(true);
    try {
      const headers = getHeaders();
      const res = await axios.post(
        `${API_BASE_URL}/api/v1/accounting/health/findings/${previewFinding.id}/fix/`,
        { company_id: companyId },
        { headers }
      );

      toast.success(
        "Fix applied successfully",
        res.data.reversal_voucher_number
          ? `Created Reversal ${res.data.reversal_voucher_number} & Correction ${res.data.correction_voucher_number}. Accounting history preserved.`
          : res.data.message || "Ledger balances updated."
      );

      setPreviewFinding(null);
      setPreviewData(null);
      fetchHealthReport();
    } catch (err: any) {
      console.error(err);
      toast.error("Fix failed", err.response?.data?.error || err.message);
    } finally {
      setExecutingFix(false);
    }
  };

  // Helper formatting functions
  const formatAmount = (val: any) => {
    if (val === undefined || val === null || val === "") return "₹0.00";
    const num = typeof val === "number" ? val : parseFloat(String(val).replace(/,/g, ""));
    if (isNaN(num)) return String(val);
    return `₹${num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return "";
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return dateStr;
      return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
    } catch {
      return dateStr;
    }
  };

  const getCategoryBadge = (category: string, fixType?: string) => {
    const cat = (category || "").toUpperCase();
    if (cat.startsWith("DUPLICATE_INV") || fixType === "MERGE_INVENTORY_ITEMS") {
      return { label: "Duplicate Product", bg: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/25" };
    }
    if (cat.startsWith("DUPLICATE_BANK") || fixType === "EXCLUDE_DUPLICATE_BANK") {
      return { label: "Duplicate Bank Feed", bg: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/25" };
    }
    if (cat.startsWith("DUPLICATE") || fixType === "VOID_DUPLICATE_VOUCHER") {
      return { label: "Duplicate Voucher", bg: "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/25" };
    }
    if (cat.includes("PARTY_BALANCE")) {
      return { label: "Party Ledger Drift", bg: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/25" };
    }
    if (cat.includes("WRONG_PARTY")) {
      return { label: "Party Allocation", bg: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/25" };
    }
    if (cat.includes("BANK")) {
      return { label: "Bank Reconciliation", bg: "bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 border-cyan-500/25" };
    }
    if (cat.includes("INVENTORY")) {
      return { label: "Inventory Stock", bg: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/25" };
    }
    if (cat.includes("TRIAL_BALANCE")) {
      return { label: "Trial Balance Gap", bg: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/25" };
    }
    if (cat.includes("GST")) {
      return { label: "GST Compliance", bg: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/25" };
    }
    if (cat.includes("OPENING")) {
      return { label: "Opening Balances", bg: "bg-muted text-muted-foreground border-border/40" };
    }
    return { label: category.replace(/_/g, " "), bg: "bg-muted text-muted-foreground border-border/40" };
  };

  const duplicateFindingsCount = useMemo(() => {
    return report?.findings?.filter((f) => f.category?.startsWith("DUPLICATE") || f.fix_type === "VOID_DUPLICATE_VOUCHER")?.length || 0;
  }, [report]);

  const criticalCount = report?.metrics?.critical_findings_count || 0;
  const warningCount = (report?.metrics?.warning_findings_count || 0) + (report?.metrics?.info_findings_count || 0);
  const actionableCount = report?.findings?.filter((f) => f.is_actionable).length || 0;

  const filteredFindings = useMemo(() => {
    if (!report?.findings) return [];
    let list = report.findings;

    if (activeTab === "DUPLICATES") {
      list = list.filter((f) => f.category?.startsWith("DUPLICATE") || f.fix_type === "VOID_DUPLICATE_VOUCHER");
    } else if (activeTab === "CRITICAL") {
      list = list.filter((f) => f.severity === "CRITICAL");
    } else if (activeTab === "WARNING") {
      list = list.filter((f) => f.severity === "WARNING" || f.severity === "INFO");
    } else if (activeTab === "ACTIONABLE") {
      list = list.filter((f) => f.is_actionable);
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(
        (f) =>
          f.title.toLowerCase().includes(q) ||
          f.description.toLowerCase().includes(q) ||
          f.category.toLowerCase().includes(q) ||
          (f.evidence?.party_name && String(f.evidence.party_name).toLowerCase().includes(q)) ||
          (f.evidence?.primary_voucher_number && String(f.evidence.primary_voucher_number).toLowerCase().includes(q))
      );
    }

    return list;
  }, [report, activeTab, searchQuery]);

  return (
    <DashboardLayout>
      <div className="space-y-5 pb-12 max-w-7xl mx-auto">
        
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 border-b border-border/40 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider bg-primary/10 text-primary border border-primary/20 rounded-md">
                Accounting Integrity
              </span>
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground">
                Books Health
              </h1>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Automated double-entry audits, duplicate transaction detection & 1-click fixes
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={runDiagnostic}
              className="px-3.5 py-1.5 rounded-xl border border-border/60 bg-card hover:bg-muted text-foreground text-xs font-semibold flex items-center gap-2 cursor-pointer shadow-2xs transition-all min-h-[36px]"
              title="Forensic Trial Balance & Suspense check"
            >
              <Scale className="w-3.5 h-3.5 text-blue-500" />
              <span>Balance Diagnostic</span>
            </button>

            <button
              onClick={() => fetchHealthReport()}
              disabled={refreshing}
              className="px-3.5 py-1.5 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-bold flex items-center gap-2 cursor-pointer shadow-sm transition-all disabled:opacity-50 min-h-[36px]"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
              <span>Run Audit</span>
            </button>
          </div>
        </div>

        {/* Clean Executive Overview (2-Card Hero) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          
          {/* Health Score & Status Banner (5 cols) */}
          <div className="lg:col-span-5 bg-card border border-border/50 rounded-2xl p-5 shadow-2xs flex items-center gap-4.5">
            {/* Circular Gauge */}
            <div className="relative w-18 h-18 sm:w-20 sm:h-20 flex items-center justify-center shrink-0">
              <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
                <circle
                  className="text-muted/30"
                  strokeWidth="8"
                  stroke="currentColor"
                  fill="transparent"
                  r="38"
                  cx="50"
                  cy="50"
                />
                <circle
                  className={
                    criticalCount === 0
                      ? warningCount === 0
                        ? "text-emerald-500"
                        : "text-amber-500"
                      : "text-rose-500"
                  }
                  strokeWidth="8"
                  strokeDasharray={`${2.38 * (report?.health_score ?? 0)} 238`}
                  strokeLinecap="round"
                  stroke="currentColor"
                  fill="transparent"
                  r="38"
                  cx="50"
                  cy="50"
                />
              </svg>
              <div className="absolute flex flex-col items-center justify-center">
                <span className="text-base sm:text-lg font-black font-mono tracking-tight text-foreground">
                  {report?.health_score ?? 0}%
                </span>
              </div>
            </div>

            {/* Status Information */}
            <div className="space-y-1 flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span
                  className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider border ${
                    criticalCount === 0
                      ? warningCount === 0
                        ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/25"
                        : "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/25"
                      : "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/25"
                  }`}
                >
                  {criticalCount === 0
                    ? warningCount === 0
                      ? "All Books Balanced"
                      : "Needs Review"
                    : "Action Required"}
                </span>
              </div>

              <h2 className="text-sm font-bold text-foreground truncate">
                {criticalCount === 0
                  ? warningCount === 0
                    ? "Books are healthy & audit-ready"
                    : `${warningCount} items require verification`
                  : `${criticalCount} critical issues need attention`}
              </h2>

              <p className="text-[11px] text-muted-foreground line-clamp-2 leading-relaxed">
                {criticalCount === 0
                  ? warningCount === 0
                    ? "Every debit matches credit, sequential numbering is valid, and zero duplicate entries exist."
                    : "Trial balance is balanced. Review unallocated bank transactions or party balance warnings."
                  : duplicateFindingsCount > 0
                  ? `Includes ${duplicateFindingsCount} duplicate transactions. Review and apply 1-click fixes below.`
                  : "Accounting inconsistencies detected. Review critical entries below."}
              </p>

              <div className="text-[10px] text-muted-foreground/80 font-mono pt-0.5">
                Last checked: {report?.timestamp ? new Date(report.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "Just now"}
              </div>
            </div>
          </div>

          {/* 4 Key Stat Tiles (7 cols) */}
          <div className="lg:col-span-7 grid grid-cols-2 sm:grid-cols-4 gap-2.5">
            
            {/* Passed Checks */}
            <div className="p-3.5 bg-card border border-border/50 rounded-2xl shadow-2xs space-y-1">
              <div className="text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                <span>Audits Passed</span>
              </div>
              <div className="text-xl sm:text-2xl font-black font-mono text-foreground">
                {report ? `${report.metrics?.passed_checks}/${report.metrics?.total_checks}` : "--"}
              </div>
              <div className="text-[10px] text-muted-foreground">Core integrity rules</div>
            </div>

            {/* Critical Issues */}
            <div className="p-3.5 bg-card border border-border/50 rounded-2xl shadow-2xs space-y-1">
              <div className="text-[11px] font-semibold text-rose-600 dark:text-rose-400 flex items-center gap-1.5">
                <AlertOctagon className="w-3.5 h-3.5 shrink-0" />
                <span>Critical Issues</span>
              </div>
              <div className="text-xl sm:text-2xl font-black font-mono text-rose-600 dark:text-rose-400">
                {criticalCount}
              </div>
              <div className="text-[10px] text-muted-foreground">Require correction</div>
            </div>

            {/* Pending Warnings */}
            <div className="p-3.5 bg-card border border-border/50 rounded-2xl shadow-2xs space-y-1">
              <div className="text-[11px] font-semibold text-amber-600 dark:text-amber-400 flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                <span>Needs Review</span>
              </div>
              <div className="text-xl sm:text-2xl font-black font-mono text-amber-600 dark:text-amber-400">
                {warningCount}
              </div>
              <div className="text-[10px] text-muted-foreground">Items to verify</div>
            </div>

            {/* 1-Click Fixes */}
            <div className="p-3.5 bg-card border border-border/50 rounded-2xl shadow-2xs space-y-1">
              <div className="text-[11px] font-semibold text-primary flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 shrink-0" />
                <span>Auto-Fixes</span>
              </div>
              <div className="text-xl sm:text-2xl font-black font-mono text-primary">
                {actionableCount}
              </div>
              <div className="text-[10px] text-muted-foreground">1-Click ready</div>
            </div>
          </div>
        </div>

        {/* Sleek, Expandable 11-Point Integrity Checklist Card */}
        <div className="bg-card border border-border/50 rounded-2xl p-4 shadow-2xs space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 min-w-0">
              <div className="w-8 h-8 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shrink-0">
                <ShieldCheck className="w-4 h-4" />
              </div>
              <div className="truncate">
                <h3 className="text-xs sm:text-sm font-bold text-foreground flex items-center gap-2">
                  <span>11 Automated Accounting Audits</span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-muted text-muted-foreground font-normal">
                    {report?.checks ? `${report.checks.filter((c) => c.status === "PASSED").length}/11 Passing` : "--"}
                  </span>
                </h3>
                <p className="text-[11px] text-muted-foreground truncate hidden sm:block">
                  Trial balance, duplicate entries, party balances, GST compliance, and document numbering
                </p>
              </div>
            </div>

            <button
              onClick={() => setIsChecksExpanded(!isChecksExpanded)}
              className="px-3 py-1.5 rounded-xl border border-border/50 bg-muted/30 hover:bg-muted/70 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1.5 shrink-0 cursor-pointer"
            >
              <span>{isChecksExpanded ? "Hide Audits" : "View All 11 Audits"}</span>
              {isChecksExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          </div>

          {/* Expanded 11 Checks Grid */}
          {isChecksExpanded && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5 pt-2 border-t border-border/40 animate-in fade-in">
              {report?.checks?.map((check) => {
                const isPassed = check.status === "PASSED";
                const isCritical = check.status === "CRITICAL";
                return (
                  <div
                    key={check.name}
                    onClick={() => {
                      if (check.name.toLowerCase().includes("duplicate")) {
                        setActiveTab("DUPLICATES");
                      } else if (!isPassed) {
                        setActiveTab("ALL");
                        setSearchQuery(check.name);
                      }
                    }}
                    className={`p-3 rounded-xl border transition-colors cursor-pointer group ${
                      isPassed
                        ? "bg-muted/15 border-border/40 hover:bg-muted/30"
                        : isCritical
                        ? "bg-rose-500/5 border-rose-500/20 hover:bg-rose-500/10"
                        : "bg-amber-500/5 border-amber-500/20 hover:bg-amber-500/10"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-semibold text-foreground group-hover:text-primary transition-colors truncate">
                        {check.name}
                      </span>
                      <span
                        className={`text-[9px] font-bold px-1.5 py-0.2 rounded uppercase tracking-wider shrink-0 ${
                          isPassed
                            ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                            : isCritical
                            ? "bg-rose-500/10 text-rose-600 dark:text-rose-400"
                            : "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                        }`}
                      >
                        {isPassed ? "Pass" : `${check.findings_count} issue${check.findings_count === 1 ? '' : 's'}`}
                      </span>
                    </div>
                    <p className="text-[10px] text-muted-foreground line-clamp-1 mt-1">
                      {check.description}
                    </p>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Forensic Balance Diagnostic Modal Dialog */}
        {isDiagnosticOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in">
            <div className="bg-card border border-border rounded-2xl max-w-lg w-full p-5 shadow-2xl space-y-4 animate-in zoom-in-95">
              <div className="flex items-center justify-between pb-3 border-b border-border/40">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-xl bg-blue-500/10 text-blue-500 flex items-center justify-center">
                    <Scale className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-foreground">Forensic Balance Diagnostic</h3>
                    <p className="text-[11px] text-muted-foreground">Trial balance equilibrium & suspense status</p>
                  </div>
                </div>
                <button
                  onClick={() => setIsDiagnosticOpen(false)}
                  className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {diagnosing ? (
                <div className="flex items-center justify-center p-8 space-y-2">
                  <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
                  <span className="text-xs text-muted-foreground ml-3">Running balance diagnosis...</span>
                </div>
              ) : diagnosticResult ? (
                <div className="space-y-3.5 text-xs">
                  {/* 3 Core Forensic Check Tiles */}
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div className="p-2.5 rounded-xl bg-muted/30 border border-border/40">
                      <div className="text-[10px] text-muted-foreground font-semibold">Trial Balance Gap</div>
                      <div className="text-sm font-bold font-mono text-foreground mt-0.5">
                        {formatAmount(diagnosticResult.trial_balance?.net_imbalance || diagnosticResult.discrepancy || "0.00")}
                      </div>
                      <div className="text-[9px] text-emerald-500 font-semibold mt-0.5">
                        {diagnosticResult.trial_balance?.is_balanced !== false ? "✓ Balanced" : "⚠ Imbalance"}
                      </div>
                    </div>

                    <div className="p-2.5 rounded-xl bg-muted/30 border border-border/40">
                      <div className="text-[10px] text-muted-foreground font-semibold">Bank Recon Gap</div>
                      <div className="text-sm font-bold font-mono text-foreground mt-0.5">
                        {formatAmount(diagnosticResult.bank_reconciliation?.reconciliation_gap || "0.00")}
                      </div>
                      <div className="text-[9px] text-emerald-500 font-semibold mt-0.5">
                        ✓ Reconciled
                      </div>
                    </div>

                    <div className="p-2.5 rounded-xl bg-muted/30 border border-border/40">
                      <div className="text-[10px] text-muted-foreground font-semibold">Suspense Gap</div>
                      <div className="text-sm font-bold font-mono text-foreground mt-0.5">
                        {formatAmount(diagnosticResult.opening_balance_suspense?.suspense_amount || "0.00")}
                      </div>
                      <div className="text-[9px] text-emerald-500 font-semibold mt-0.5">
                        ✓ Cleared
                      </div>
                    </div>
                  </div>

                  {/* Plain Language Verdict */}
                  <div className={`p-3 rounded-xl border text-xs leading-relaxed ${
                    diagnosticResult.is_balanced
                      ? "bg-emerald-500/10 border-emerald-500/25 text-emerald-800 dark:text-emerald-200"
                      : "bg-rose-500/10 border-rose-500/25 text-rose-800 dark:text-rose-200"
                  }`}>
                    {diagnosticResult.is_balanced ? (
                      <div className="space-y-1">
                        <div className="font-bold flex items-center gap-1.5">
                          <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                          <span>Debits and Credits are in Balance</span>
                        </div>
                        <p className="text-[11px] text-muted-foreground">
                          {diagnosticResult.message || `Total Debits equal Total Credits (${formatAmount(diagnosticResult.total_debit)}). Zero imbalance detected.`}
                        </p>
                        <p className="text-[10px] text-muted-foreground/90 pt-1">
                          Notice: Any issues listed on Books Health are operational entries (such as duplicate vouchers or inventory records) rather than mathematical ledger imbalances.
                        </p>
                      </div>
                    ) : (
                      <div className="space-y-1">
                        <div className="font-bold flex items-center gap-1.5 text-rose-600 dark:text-rose-400">
                          <AlertOctagon className="w-4 h-4 shrink-0" />
                          <span>Trial Balance Discrepancy Found</span>
                        </div>
                        <p className="text-[11px]">
                          {diagnosticResult.message}
                        </p>
                      </div>
                    )}
                  </div>

                  <div className="flex justify-end pt-1">
                    <button
                      onClick={() => setIsDiagnosticOpen(false)}
                      className="px-4 py-2 rounded-xl text-xs font-semibold bg-muted hover:bg-muted/80 text-foreground transition-colors cursor-pointer"
                    >
                      Close Diagnostic
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        )}

        {/* Findings Feed & Filter Tabs */}
        <div className="space-y-3.5">
          <div className="flex flex-col sm:flex-row justify-between items-stretch sm:items-center gap-3">
            
            {/* Filter Tabs */}
            <div className="flex items-center gap-1 p-1 bg-muted/30 border border-border/40 rounded-xl overflow-x-auto">
              <button
                onClick={() => setActiveTab("ALL")}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer shrink-0 ${
                  activeTab === "ALL"
                    ? "bg-card text-foreground shadow-xs border border-border/60"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                All Issues ({report?.findings?.length || 0})
              </button>

              <button
                onClick={() => setActiveTab("DUPLICATES")}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5 shrink-0 ${
                  activeTab === "DUPLICATES"
                    ? "bg-card text-foreground shadow-xs border border-border/60"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Layers className="w-3 h-3 text-purple-500" />
                <span>Duplicates</span>
                {duplicateFindingsCount > 0 && (
                  <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono font-bold bg-purple-500/20 text-purple-600 dark:text-purple-400">
                    {duplicateFindingsCount}
                  </span>
                )}
              </button>

              <button
                onClick={() => setActiveTab("CRITICAL")}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5 shrink-0 ${
                  activeTab === "CRITICAL"
                    ? "bg-card text-foreground shadow-xs border border-border/60"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <AlertOctagon className="w-3 h-3 text-rose-500" />
                <span>Critical</span>
                {criticalCount > 0 && (
                  <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono font-bold bg-rose-500/20 text-rose-600 dark:text-rose-400">
                    {criticalCount}
                  </span>
                )}
              </button>

              <button
                onClick={() => setActiveTab("WARNING")}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5 shrink-0 ${
                  activeTab === "WARNING"
                    ? "bg-card text-foreground shadow-xs border border-border/60"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <AlertTriangle className="w-3 h-3 text-amber-500" />
                <span>Needs Review</span>
                {warningCount > 0 && (
                  <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono font-bold bg-amber-500/20 text-amber-600 dark:text-amber-400">
                    {warningCount}
                  </span>
                )}
              </button>

              <button
                onClick={() => setActiveTab("ACTIONABLE")}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5 shrink-0 ${
                  activeTab === "ACTIONABLE"
                    ? "bg-card text-foreground shadow-xs border border-border/60"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Sparkles className="w-3 h-3 text-primary" />
                <span>Auto-Fixable</span>
                {actionableCount > 0 && (
                  <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono font-bold bg-primary/20 text-primary">
                    {actionableCount}
                  </span>
                )}
              </button>
            </div>

            {/* Search Input */}
            <div className="relative min-w-[240px]">
              <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search issues, vouchers, party..."
                className="w-full bg-card border border-border/50 rounded-xl pl-9 pr-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 min-h-[36px]"
              />
            </div>
          </div>

          {/* Findings List */}
          {loading ? (
            <div className="flex flex-col items-center justify-center p-16 space-y-2">
              <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
              <p className="text-xs text-muted-foreground">Running integrity audit...</p>
            </div>
          ) : filteredFindings.length === 0 ? (
            <div className="bg-card border border-border/40 rounded-2xl p-10 text-center space-y-2.5 shadow-2xs">
              <div className="w-10 h-10 rounded-full bg-emerald-500/10 text-emerald-500 flex items-center justify-center mx-auto">
                <CheckCircle2 className="w-5 h-5" />
              </div>
              <h3 className="text-sm font-bold text-foreground">
                {activeTab === "ALL"
                  ? "All Accounting Checks Passing!"
                  : activeTab === "DUPLICATES"
                  ? "Zero Duplicate Transactions Found"
                  : activeTab === "CRITICAL"
                  ? "Zero Critical Issues Found"
                  : activeTab === "WARNING"
                  ? "Zero Warnings Pending"
                  : "No Actionable Fixes Pending"}
              </h3>
              <p className="text-xs text-muted-foreground max-w-sm mx-auto">
                {activeTab === "DUPLICATES"
                  ? "All vouchers, bank transactions, and inventory items are unique and deduplicated."
                  : "Your double-entry books are consistent and balanced."}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {filteredFindings.map((finding) => {
                const categoryBadge = getCategoryBadge(finding.category, finding.fix_type);
                const isDuplicateVoucher = finding.fix_type === "VOID_DUPLICATE_VOUCHER" || finding.category?.startsWith("DUPLICATE_VOUCHER");
                const isDuplicateInventory = finding.fix_type === "MERGE_INVENTORY_ITEMS" || finding.category?.startsWith("DUPLICATE_INVENTORY");
                const isPartyDrift = finding.category?.includes("PARTY_BALANCE") || finding.evidence?.stored_balance !== undefined;

                return (
                  <div
                    key={finding.id}
                    className="bg-card border border-border/40 hover:border-border/80 transition-all rounded-2xl p-4 sm:p-5 shadow-2xs space-y-3"
                  >
                    {/* Top Row: Category, Severity & Action Button */}
                    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span
                          className={`text-[9px] font-bold px-2 py-0.5 rounded uppercase tracking-wider border ${
                            finding.severity === "CRITICAL"
                              ? "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/25"
                              : finding.severity === "WARNING"
                              ? "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/25"
                              : "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/25"
                          }`}
                        >
                          {finding.severity}
                        </span>

                        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-md border ${categoryBadge.bg}`}>
                          {categoryBadge.label}
                        </span>

                        {finding.created_at && (
                          <span className="text-[10px] text-muted-foreground/80 font-mono">
                            {formatDate(finding.created_at)}
                          </span>
                        )}
                      </div>

                      {/* Primary 1-Click Fix Button */}
                      {finding.is_actionable && (
                        <button
                          onClick={() => openFixPreview(finding)}
                          className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all shadow-2xs flex items-center gap-1.5 shrink-0 cursor-pointer w-full sm:w-auto justify-center min-h-[34px] ${
                            isDuplicateVoucher
                              ? "bg-purple-600 hover:bg-purple-700 text-white"
                              : isDuplicateInventory
                              ? "bg-blue-600 hover:bg-blue-700 text-white"
                              : "bg-primary text-primary-foreground hover:bg-primary/90"
                          }`}
                        >
                          <Wrench className="w-3 h-3" />
                          <span>
                            {isDuplicateVoucher
                              ? "Fix Duplicate"
                              : isDuplicateInventory
                              ? "Merge Products"
                              : "Review & Fix"}
                          </span>
                        </button>
                      )}
                    </div>

                    {/* Title & Human Description */}
                    <div className="space-y-1">
                      <h4 className="text-sm font-bold text-foreground">
                        {finding.title}
                      </h4>
                      <p className="text-xs text-muted-foreground leading-relaxed">
                        {finding.description}
                      </p>
                    </div>

                    {/* Specialized Clean Issue Cards */}
                    {/* Case 1: Duplicate Voucher Side-by-Side Comparison */}
                    {isDuplicateVoucher && finding.evidence?.primary_voucher_number && (
                      <div className="p-3 rounded-xl bg-purple-500/5 border border-purple-500/20 grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs">
                        {/* Primary Record to Keep */}
                        <div className="p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20 space-y-1">
                          <div className="text-[10px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                            <Check className="w-3 h-3" />
                            Primary Record (Retained)
                          </div>
                          <div className="font-mono font-bold text-foreground">
                            #{finding.evidence.primary_voucher_number}
                          </div>
                          <div className="text-muted-foreground text-[11px]">
                            {finding.evidence.voucher_date} • {formatAmount(finding.evidence.amount)} • {finding.evidence.party_name}
                          </div>
                        </div>

                        {/* Duplicate Record to Void */}
                        <div className="p-2.5 rounded-lg bg-rose-500/5 border border-rose-500/20 space-y-1">
                          <div className="text-[10px] font-bold uppercase tracking-wider text-rose-600 dark:text-rose-400 flex items-center gap-1">
                            <AlertOctagon className="w-3 h-3" />
                            Duplicate Entry (To Void & Cancel)
                          </div>
                          <div className="font-mono font-bold text-foreground line-through decoration-rose-500/60">
                            #{finding.evidence.duplicate_voucher_number}
                          </div>
                          <div className="text-muted-foreground text-[11px]">
                            Safe cancellation preserves audit log and restores ledger balance
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Case 2: Duplicate Inventory Item Comparison */}
                    {isDuplicateInventory && finding.evidence?.primary_sku && (
                      <div className="p-3 rounded-xl bg-blue-500/5 border border-blue-500/20 grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs">
                        <div className="p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20 space-y-1">
                          <div className="text-[10px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                            <Package className="w-3 h-3" />
                            Primary Product (Retained)
                          </div>
                          <div className="font-mono font-bold text-foreground">
                            SKU: {finding.evidence.primary_sku} ({finding.evidence.primary_stock} units)
                          </div>
                          <div className="text-muted-foreground text-[11px]">
                            Target Combined: {finding.evidence.combined_stock} units
                          </div>
                        </div>

                        <div className="p-2.5 rounded-lg bg-amber-500/5 border border-amber-500/20 space-y-1">
                          <div className="text-[10px] font-bold uppercase tracking-wider text-amber-600 dark:text-amber-400 flex items-center gap-1">
                            <Layers className="w-3 h-3" />
                            Duplicate Item (To Consolidate)
                          </div>
                          <div className="font-mono font-bold text-foreground">
                            SKU: {finding.evidence.duplicate_sku} ({finding.evidence.duplicate_stock} units)
                          </div>
                          <div className="text-muted-foreground text-[11px]">
                            Stock movements will be repointed to primary product
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Case 3: Party Balance Drift Details */}
                    {isPartyDrift && finding.evidence?.difference && (
                      <div className="p-2.5 rounded-xl bg-amber-500/5 border border-amber-500/20 flex flex-wrap items-center justify-between gap-2 text-xs">
                        <div className="text-foreground">
                          <strong>Recorded:</strong> {formatAmount(finding.evidence.stored_balance)} vs{" "}
                          <strong>Calculated:</strong> {formatAmount(finding.evidence.calculated_balance)}
                        </div>
                        <div className="font-mono font-bold text-amber-600 dark:text-amber-400">
                          Discrepancy: {formatAmount(finding.evidence.difference)}
                        </div>
                      </div>
                    )}

                    {/* Recommended Action Pill (if present and not duplicate comparison) */}
                    {!isDuplicateVoucher && !isDuplicateInventory && finding.suggested_fix && (
                      <div className="p-2.5 rounded-xl bg-muted/30 border border-border/40 text-xs flex items-center gap-2 text-foreground">
                        <Sparkles className="w-3.5 h-3.5 text-primary shrink-0" />
                        <span><strong>Recommended Fix:</strong> {finding.suggested_fix}</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* INTERACTIVE BEFORE VS AFTER FIX PREVIEW MODAL */}
        {previewFinding && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-200">
            <div
              className="bg-card border border-border rounded-2xl shadow-2xl w-full max-w-xl overflow-hidden animate-in zoom-in-95 duration-200"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between p-5 border-b border-border">
                <div className="flex items-center gap-2">
                  <div className="p-2 rounded-xl bg-primary/10 text-primary">
                    <Wrench className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-foreground">Review & Apply Fix</h3>
                    <p className="text-xs text-muted-foreground">{previewFinding.title}</p>
                  </div>
                </div>
                <button
                  onClick={() => setPreviewFinding(null)}
                  className="text-muted-foreground hover:text-foreground p-1 rounded-lg cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {loadingPreview ? (
                <div className="flex flex-col items-center justify-center p-12 space-y-3">
                  <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
                  <span className="text-xs text-muted-foreground">Generating financial impact preview...</span>
                </div>
              ) : previewData ? (
                <div className="p-5 space-y-4">
                  {/* Summary Callout */}
                  <div className="p-3.5 rounded-xl bg-muted/40 border border-border/50 text-xs text-foreground leading-relaxed">
                    <strong>Proposed Fix Action:</strong> {previewData.summary}
                  </div>

                  {/* History Preservation Guarantee */}
                  <div className="p-3 rounded-xl bg-blue-500/10 border border-blue-500/20 text-xs text-blue-600 dark:text-blue-300 space-y-1">
                    <div className="font-bold flex items-center gap-1.5">
                      <History className="w-4 h-4" />
                      Double-Entry History Preservation
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      {previewData.history_preservation_note ||
                        "Nothing financially significant is silently rewritten. An explicit reversal voucher is created, preserving full audit trail."}
                    </div>
                  </div>

                  {/* Financial Comparison Table: BEFORE vs AFTER */}
                  {previewData.preview_comparison?.length > 0 && (
                    <div>
                      <div className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">
                        Financial Balance Impact (Before vs After)
                      </div>
                      <div className="border border-border/60 rounded-xl overflow-hidden text-xs">
                        <table className="w-full">
                          <thead className="bg-muted/40 border-b border-border/40 text-muted-foreground text-left">
                            <tr>
                              <th className="p-2.5">Account / Party</th>
                              <th className="p-2.5 text-right font-mono">Before Balance</th>
                              <th className="p-2.5 text-right font-mono">After Balance</th>
                              <th className="p-2.5 text-right font-mono">Net Change</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border/30">
                            {previewData.preview_comparison?.map((row, idx) => (
                              <tr key={idx} className="hover:bg-muted/20">
                                <td className="p-2.5 font-bold text-foreground">{row.account}</td>
                                <td className="p-2.5 text-right font-mono tabular-nums text-muted-foreground">
                                  {row.before_balance}
                                </td>
                                <td className="p-2.5 text-right font-mono tabular-nums font-bold text-emerald-500">
                                  {row.after_balance}
                                </td>
                                <td className="p-2.5 text-right font-mono tabular-nums text-primary font-bold">
                                  {row.impact}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  <div className="flex items-center gap-3 pt-2">
                    <button
                      type="button"
                      onClick={() => setPreviewFinding(null)}
                      className="flex-1 py-2.5 rounded-xl text-xs font-bold text-muted-foreground hover:text-foreground bg-muted hover:bg-muted/80 transition-colors cursor-pointer"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={executeFix}
                      disabled={executingFix}
                      className="flex-1 py-2.5 rounded-xl text-xs font-bold text-primary-foreground bg-primary hover:bg-primary/90 transition-all cursor-pointer flex items-center justify-center gap-2 disabled:opacity-50"
                    >
                      {executingFix ? (
                        <>
                          <div className="w-4 h-4 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin"></div>
                          <span>Applying Safe Fix...</span>
                        </>
                      ) : (
                        <span>Confirm & Apply Fix</span>
                      )}
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
