"use client";

import React, { useEffect, useState, useMemo } from "react";
import axios from "axios";
import { useRouter } from "next/navigation";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import DashboardLayout from "@/components/DashboardLayout";
import { useToast } from "@/context/ToastContext";
import { useCompany } from "@/context/CompanyContext";
import {
  Activity,
  ShieldCheck,
  AlertTriangle,
  AlertOctagon,
  CheckCircle2,
  Info,
  RefreshCw,
  Search,
  Wrench,
  Sparkles,
  ArrowRight,
  HelpCircle,
  TrendingDown,
  TrendingUp,
  FileSpreadsheet,
  X,
  History,
  FileCheck2,
  ChevronDown,
  ChevronUp,
  Scale,
  DollarSign,
  Layers,
  ArrowDownRight,
  ArrowUpRight,
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
  score_breakdown: {
    base_score: number;
    critical_deductions: number;
    warning_deductions: number;
    unresolved_bank_deductions: number;
    formula: string;
  };
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
  const [activeTab, setActiveTab] = useState<"ALL" | "CRITICAL" | "WARNING" | "ACTIONABLE">("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Diagnostic tool state
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

  const filteredFindings = useMemo(() => {
    if (!report?.findings) return [];
    let list = report.findings;

    if (activeTab === "CRITICAL") {
      list = list.filter((f) => f.severity === "CRITICAL");
    } else if (activeTab === "WARNING") {
      list = list.filter((f) => f.severity === "WARNING");
    } else if (activeTab === "ACTIONABLE") {
      list = list.filter((f) => f.is_actionable);
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(
        (f) =>
          f.title.toLowerCase().includes(q) ||
          f.description.toLowerCase().includes(q) ||
          f.category.toLowerCase().includes(q)
      );
    }

    return list;
  }, [report, activeTab, searchQuery]);

  return (
    <DashboardLayout>
      <div className="space-y-6 pb-12">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-border/40 pb-5">
          <div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 text-[10px] font-black uppercase tracking-wider bg-primary/10 text-primary border border-primary/20 rounded-md">
                VOUCH CHECK
              </span>
              <h1 className="text-xl sm:text-2xl font-extrabold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">
                Books Health
              </h1>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Vouch checks your books for things that need attention
            </p>
          </div>

          <div className="flex items-center gap-2.5 flex-wrap">
            <button
              onClick={runDiagnostic}
              className="px-3.5 py-2 rounded-xl border border-border/60 bg-card hover:bg-muted text-foreground text-xs font-semibold flex items-center gap-2 cursor-pointer shadow-2xs transition-all"
            >
              <Scale className="w-3.5 h-3.5 text-blue-400" />
              <span>Why don't my books match?</span>
            </button>

            <button
              onClick={() => fetchHealthReport()}
              disabled={refreshing}
              className="px-4 py-2 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-bold flex items-center gap-2 cursor-pointer shadow-md shadow-primary/20 transition-all disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
              <span>Run Health Audit</span>
            </button>
          </div>
        </div>

        {/* TOP METRIC CARDS: Health Score Gauge & Score Deductions */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Health Score Gauge */}
          <div className="bg-card border border-border/40 rounded-2xl p-6 shadow-sm flex items-center gap-6">
            <div className="relative w-24 h-24 sm:w-28 sm:h-28 flex items-center justify-center shrink-0">
              <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
                <circle
                  className="text-muted/40"
                  strokeWidth="8"
                  stroke="currentColor"
                  fill="transparent"
                  r="40"
                  cx="50"
                  cy="50"
                />
                <circle
                  className={
                    (report?.health_score ?? 0) >= 90
                      ? "text-emerald-500"
                      : (report?.health_score ?? 0) >= 70
                      ? "text-amber-500"
                      : "text-rose-500"
                  }
                  strokeWidth="8"
                  strokeDasharray={`${2.51 * (report?.health_score ?? 0)} 251`}
                  strokeLinecap="round"
                  stroke="currentColor"
                  fill="transparent"
                  r="40"
                  cx="50"
                  cy="50"
                />
              </svg>
              <div className="absolute flex flex-col items-center justify-center">
                <span className="text-2xl sm:text-3xl font-black font-mono tracking-tight text-foreground">
                  {report ? `${report.health_score}%` : "--"}
                </span>
              </div>
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <span
                  className={`text-xs font-extrabold px-2.5 py-0.5 rounded-full uppercase tracking-wider ${
                    report?.health_status === "HEALTHY"
                      ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                      : report?.health_status === "NEEDS_ATTENTION"
                      ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                      : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                  }`}
                >
                  {report?.health_status ? report.health_status.replace("_", " ") : "Calculating"}
                </span>
              </div>
              <h2 className="text-sm font-bold text-foreground">Books health</h2>
              <p className="text-[11px] text-muted-foreground">
                {report?.health_status === "HEALTHY"
                  ? "Everything looks good. No issues found."
                  : report?.health_status === "NEEDS_ATTENTION"
                  ? "Minor reconciliation gaps or tax warnings need your review."
                  : "Critical accounting balance violations require immediate review."}
              </p>
            </div>
          </div>

          {/* Mathematical Score Formula Breakdown */}
          <div className="bg-card border border-border/40 rounded-2xl p-5 shadow-sm space-y-3 flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
                HOW IT'S CALCULATED
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-muted text-muted-foreground">
                Automated
              </span>
            </div>

            <div className="space-y-1.5 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Base Starting Score:</span>
                <span className="font-mono font-bold text-foreground">100%</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-rose-400">Critical Violations (-15% ea):</span>
                <span className="font-mono font-bold text-rose-400">
                  -{report?.score_breakdown?.critical_deductions ?? 0}%
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-amber-400">Warnings (-5% ea):</span>
                <span className="font-mono font-bold text-amber-400">
                  -{report?.score_breakdown?.warning_deductions ?? 0}%
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-blue-400">Unresolved Bank Tx (-1% ea):</span>
                <span className="font-mono font-bold text-blue-400">
                  -{report?.score_breakdown?.unresolved_bank_deductions ?? 0}%
                </span>
              </div>
            </div>

            <div className="text-[10px] text-muted-foreground border-t border-border/40 pt-2 font-mono">
              Audit Date: {report?.timestamp ? new Date(report.timestamp).toLocaleString("en-IN") : "Now"}
            </div>
          </div>

          {/* Quick Metrics Grid */}
          <div className="bg-card border border-border/40 rounded-2xl p-5 shadow-sm grid grid-cols-2 gap-3">
            <div className="p-3 bg-emerald-500/5 rounded-xl border border-emerald-500/20 space-y-1">
              <div className="text-[11px] font-semibold text-emerald-500 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" />
                Passed Checks
              </div>
              <div className="text-2xl font-black font-mono text-foreground">
                {report ? `${report.metrics?.passed_checks}/${report.metrics?.total_checks}` : "--"}
              </div>
              <div className="text-[10px] text-muted-foreground">Checks passing</div>
            </div>

            <div className="p-3 bg-rose-500/5 rounded-xl border border-rose-500/20 space-y-1">
              <div className="text-[11px] font-semibold text-rose-500 flex items-center gap-1">
                <AlertOctagon className="w-3 h-3" />
                Critical Issues
              </div>
              <div className="text-2xl font-black font-mono text-foreground">
                {report?.metrics?.critical_findings_count ?? 0}
              </div>
              <div className="text-[10px] text-muted-foreground">Require correction</div>
            </div>

            <div className="p-3 bg-amber-500/5 rounded-xl border border-amber-500/20 space-y-1">
              <div className="text-[11px] font-semibold text-amber-500 flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" />
                Warnings
              </div>
              <div className="text-2xl font-black font-mono text-foreground">
                {report?.metrics?.warning_findings_count ?? 0}
              </div>
              <div className="text-[10px] text-muted-foreground">Needs review</div>
            </div>

            <div className="p-3 bg-primary/5 rounded-xl border border-primary/20 space-y-1">
              <div className="text-[11px] font-semibold text-primary flex items-center gap-1">
                <Sparkles className="w-3 h-3" />
                Assistant Fixes
              </div>
              <div className="text-2xl font-black font-mono text-foreground">
                {report?.findings?.filter((f) => f.is_actionable).length ?? 0}
              </div>
              <div className="text-[10px] text-muted-foreground">1-Click preview available</div>
            </div>
          </div>
        </div>

        {/* 1-CLICK INVESTIGATIVE DIAGNOSTIC SECTION */}
        {isDiagnosticOpen && (
          <div className="bg-card border border-blue-500/30 rounded-2xl p-5 shadow-lg space-y-4 animate-in fade-in duration-200">
            <div className="flex items-center justify-between pb-3 border-b border-border/40">
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-xl bg-blue-500/10 text-blue-400">
                  <Scale className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-foreground">Investigative Diagnostic Report</h3>
                  <p className="text-xs text-muted-foreground">Detailed root-cause analysis of book imbalances</p>
                </div>
              </div>
              <button
                onClick={() => setIsDiagnosticOpen(false)}
                className="text-muted-foreground hover:text-foreground p-1 rounded-lg cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {diagnosing ? (
              <div className="flex items-center justify-center p-8 space-y-2">
                <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
                <span className="text-xs text-muted-foreground ml-3">Running forensic balance diagnosis...</span>
              </div>
            ) : diagnosticResult ? (
              <div className="space-y-4 text-xs">
                {/* Status overview */}
                <div className="p-3 rounded-xl bg-muted/40 border border-border/40 flex items-center justify-between">
                  <span className="font-bold text-foreground">Diagnosis Summary:</span>
                  <span className="font-bold text-primary">{diagnosticResult.diagnostic_summary}</span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {/* Trial balance */}
                  <div className="p-3 rounded-xl bg-muted/20 border border-border/40 space-y-1">
                    <div className="text-[11px] text-muted-foreground font-bold">Trial Balance Net Gap</div>
                    <div className="text-base font-bold font-mono text-foreground">
                      ₹{diagnosticResult.trial_balance?.net_imbalance || "0.00"}
                    </div>
                    <div className="text-[10px] text-muted-foreground">
                      Total Dr: ₹{diagnosticResult.trial_balance?.total_debit || "0"} | Total Cr: ₹
                      {diagnosticResult.trial_balance?.total_credit || "0"}
                    </div>
                  </div>

                  {/* Bank gap */}
                  <div className="p-3 rounded-xl bg-muted/20 border border-border/40 space-y-1">
                    <div className="text-[11px] text-muted-foreground font-bold">Bank Statement Gap</div>
                    <div className="text-base font-bold font-mono text-foreground">
                      ₹{diagnosticResult.bank_reconciliation?.reconciliation_gap || "0.00"}
                    </div>
                    <div className="text-[10px] text-muted-foreground">
                      Unreconciled bank transactions awaiting resolution
                    </div>
                  </div>

                  {/* Opening balance suspense */}
                  <div className="p-3 rounded-xl bg-muted/20 border border-border/40 space-y-1">
                    <div className="text-[11px] text-muted-foreground font-bold">Opening Balance Suspense</div>
                    <div className="text-base font-bold font-mono text-foreground">
                      ₹{diagnosticResult.opening_balance_suspense?.suspense_amount || "0.00"}
                    </div>
                    <div className="text-[10px] text-muted-foreground">
                      {diagnosticResult.opening_balance_suspense?.is_balanced ? "Balanced" : "Suspense difference"}
                    </div>
                  </div>
                </div>

                {/* Specific Party Discrepancies if any */}
                {diagnosticResult.party_discrepancies?.mismatch_count > 0 && (
                  <div className="space-y-2">
                    <div className="font-bold text-foreground">Party Balances Deviating from History:</div>
                    <div className="space-y-1.5">
                      {diagnosticResult.party_discrepancies.mismatched_parties.map((p: any) => (
                        <div
                          key={p.ledger_id}
                          className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-between"
                        >
                          <div>
                            <span className="font-bold text-foreground">{p.ledger_name}</span>
                            <span className="text-[10px] text-muted-foreground ml-2 font-mono">
                              Cached Bal: ₹{p.stored_balance} vs Calculated: ₹{p.calculated_balance}
                            </span>
                          </div>
                          <span className="font-mono font-bold text-amber-400">Diff: ₹{p.difference}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Recommendations */}
                {diagnosticResult.recommended_actions?.length > 0 && (
                  <div className="p-3 rounded-xl bg-primary/5 border border-primary/20 space-y-1">
                    <div className="font-bold text-primary">Recommended Actions:</div>
                    <ul className="list-disc list-inside space-y-0.5 text-muted-foreground text-[11px]">
                      {diagnosticResult.recommended_actions.map((rec: string, i: number) => (
                        <li key={i}>{rec}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : null}
          </div>
        )}

        {/* 11-POINT INTEGRITY CHECKLIST STATUS */}
        <div className="bg-card border border-border/40 rounded-2xl p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-bold text-foreground">Automated Checks</h2>
              <p className="text-xs text-muted-foreground">
                Vouch automatically runs these checks on your books
              </p>
            </div>
            <span className="text-xs font-mono font-bold text-muted-foreground">
              {report?.checks ? `${report.checks.filter((c) => c.status === "PASSED").length}/${report.checks.length} Passing` : "--"}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {report?.checks?.map((check) => (
              <div
                key={check.name}
                className="p-3.5 rounded-xl border border-border/40 bg-muted/20 hover:bg-muted/40 transition-colors space-y-1.5"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-foreground">{check.name}</span>
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider ${
                      check.status === "PASSED"
                        ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                        : check.status === "WARNING"
                        ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                        : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                    }`}
                  >
                    {check.status}
                  </span>
                </div>
                <p className="text-[11px] text-muted-foreground line-clamp-2">{check.description}</p>
                {check.findings_count > 0 && (
                  <div className="text-[10px] font-mono font-bold text-rose-400 pt-1">
                    {check.findings_count} {check.findings_count === 1 ? "issue" : "issues"} detected
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* FINDINGS & FIXES ASSISTANT FEED */}
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row justify-between items-stretch sm:items-center gap-3">
            <div className="flex items-center gap-1 p-1 bg-muted/40 border border-border/40 rounded-xl">
              <button
                onClick={() => setActiveTab("ALL")}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                  activeTab === "ALL"
                    ? "bg-card text-foreground shadow-sm border border-border/60"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                All Findings ({report?.findings?.length || 0})
              </button>

              <button
                onClick={() => setActiveTab("CRITICAL")}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                  activeTab === "CRITICAL"
                    ? "bg-card text-foreground shadow-sm border border-border/60"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <span>Critical</span>
                {(report?.metrics?.critical_findings_count || 0) > 0 && (
                  <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono font-bold bg-rose-500/20 text-rose-500">
                    {report?.metrics?.critical_findings_count}
                  </span>
                )}
              </button>

              <button
                onClick={() => setActiveTab("WARNING")}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                  activeTab === "WARNING"
                    ? "bg-card text-foreground shadow-sm border border-border/60"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <span>Warnings</span>
                {(report?.metrics?.warning_findings_count || 0) > 0 && (
                  <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono font-bold bg-amber-500/20 text-amber-500">
                    {report?.metrics?.warning_findings_count}
                  </span>
                )}
              </button>

              <button
                onClick={() => setActiveTab("ACTIONABLE")}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                  activeTab === "ACTIONABLE"
                    ? "bg-card text-foreground shadow-sm border border-border/60"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Sparkles className="w-3.5 h-3.5 text-primary" />
                <span>Fixable Now</span>
              </button>
            </div>

            <div className="relative min-w-[260px]">
              <Search className="w-4 h-4 text-muted-foreground absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search findings, ledgers, vouchers..."
                className="w-full bg-card border border-border/60 rounded-xl pl-10 pr-4 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
            </div>
          </div>

          {/* Findings List */}
          {loading ? (
            <div className="flex flex-col items-center justify-center p-16 space-y-3">
              <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
              <p className="text-xs text-muted-foreground">Checking your books...</p>
            </div>
          ) : filteredFindings.length === 0 ? (
            <div className="bg-card border border-border/40 rounded-2xl p-12 text-center space-y-3 shadow-sm">
              <div className="w-12 h-12 rounded-full bg-emerald-500/10 text-emerald-400 flex items-center justify-center mx-auto">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <h3 className="text-base font-bold text-foreground">
                {activeTab === "ALL" ? "All Checks In Balance!" : `No ${activeTab.toLowerCase()} findings detected`}
              </h3>
              <p className="text-xs text-muted-foreground max-w-sm mx-auto">
                {activeTab === "ALL"
                  ? "All automated checks passed. Your books are balanced and in order."
                  : `There are currently no items flagged under ${activeTab.toLowerCase()}.`}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {filteredFindings.map((finding) => (
                <div
                  key={finding.id}
                  className="bg-card border border-border/40 hover:border-border/80 transition-all rounded-2xl p-5 shadow-sm space-y-3"
                >
                  <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                    <div className="flex items-start gap-3">
                      <div
                        className={`p-2.5 rounded-xl shrink-0 mt-0.5 ${
                          finding.severity === "CRITICAL"
                            ? "bg-rose-500/10 text-rose-500"
                            : finding.severity === "WARNING"
                            ? "bg-amber-500/10 text-amber-500"
                            : "bg-blue-500/10 text-blue-500"
                        }`}
                      >
                        {finding.severity === "CRITICAL" ? (
                          <AlertOctagon className="w-5 h-5" />
                        ) : (
                          <AlertTriangle className="w-5 h-5" />
                        )}
                      </div>

                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span
                            className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider ${
                              finding.severity === "CRITICAL"
                                ? "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                                : finding.severity === "WARNING"
                                ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                                : "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                            }`}
                          >
                            {finding.severity}
                          </span>
                          <span className="text-[10px] font-mono px-2 py-0.5 bg-muted/60 text-muted-foreground rounded border border-border/40">
                            {finding.category}
                          </span>
                          <span className="text-[10px] font-mono text-muted-foreground">Code: {finding.code}</span>
                        </div>

                        <h4 className="text-sm font-bold text-foreground">{finding.title}</h4>
                        <p className="text-xs text-muted-foreground leading-relaxed">{finding.description}</p>
                      </div>
                    </div>

                    {finding.is_actionable && (
                      <button
                        onClick={() => openFixPreview(finding)}
                        className="px-4 py-2 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-bold transition-all shadow-sm flex items-center gap-1.5 shrink-0 cursor-pointer w-full sm:w-auto justify-center"
                      >
                        <Wrench className="w-3.5 h-3.5" />
                        <span>Review & Fix</span>
                      </button>
                    )}
                  </div>

                  {/* Evidence & Suggested Fix */}
                  <div className="bg-muted/30 border border-border/40 rounded-xl p-3 text-xs space-y-2">
                    {finding.suggested_fix && (
                      <div className="flex items-start gap-2 text-foreground">
                        <Sparkles className="w-3.5 h-3.5 text-primary shrink-0 mt-0.5" />
                        <span>
                          <strong>Recommended Fix:</strong> {finding.suggested_fix}
                        </span>
                      </div>
                    )}

                    {finding.evidence && Object.keys(finding.evidence).length > 0 && (
                      <div className="pt-2 border-t border-border/30 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 font-mono text-[11px] text-muted-foreground">
                        {Object.entries(finding.evidence).map(([k, v]) => (
                          <div key={k} className="p-1.5 rounded bg-muted/40 border border-border/20 truncate">
                            <span className="text-foreground/70">{k}:</span> {typeof v === "object" ? JSON.stringify(v) : String(v)}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* INTERACTIVE BEFORE VS AFTER FIX PREVIEW MODAL */}
        {previewFinding && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
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
                  <X className="w-5 h-5" />
                </button>
              </div>

              {loadingPreview ? (
                <div className="flex flex-col items-center justify-center p-12 space-y-3">
                  <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
                  <span className="text-xs text-muted-foreground">Generating financial BEFORE vs AFTER preview...</span>
                </div>
              ) : previewData ? (
                <div className="p-5 space-y-4">
                  {/* Summary Callout */}
                  <div className="p-3.5 rounded-xl bg-muted/40 border border-border/50 text-xs text-foreground leading-relaxed">
                    <strong>Proposed Fix Action:</strong> {previewData.summary}
                  </div>

                  {/* History Preservation Guarantee */}
                  <div className="p-3 rounded-xl bg-blue-500/10 border border-blue-500/20 text-xs text-blue-300 space-y-1">
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
                              <td className="p-2.5 text-right font-mono tabular-nums font-bold text-emerald-400">
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
                          <span>Applying Reversible Fix...</span>
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
