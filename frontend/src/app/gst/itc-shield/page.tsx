"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { isAuthenticated } from "@/utils/auth";
import { api } from "@/utils/api";
import { useCompany } from "@/context/CompanyContext";
import DashboardLayout from "@/components/DashboardLayout";
import {
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  UploadCloud,
  RefreshCw,
  Search,
  MessageCircle,
  Lock,
  Unlock,
  ExternalLink,
  Calendar,
  FileSpreadsheet,
  FileCode,
  CheckCircle2,
  XCircle,
  HelpCircle,
  ArrowRight,
  Info,
  Clock,
  ChevronRight,
  X,
  RotateCcw
} from "lucide-react";
import { gstApi, GSTRegistration } from "@/lib/api/gst";
import MonthPickerInput, { parsePeriodToDisplay } from "@/components/ui/MonthPickerInput";

interface SummaryStats {
  itc_at_risk: number;
  itc_safe: number;
  itc_held_total: number;
  matched_count: number;
  mismatched_count: number;
  missing_in_2b_count: number;
  missing_in_books_count: number;
  missing_in_books_itc: number;
  missing_in_books_gross_itc?: number;
  missing_in_books_credit_itc?: number;
  review_required_count?: number;
  later_period_count?: number;
  amended_count?: number;
  not_yet_reflected_count?: number;
  data_unavailable_count?: number;
  unmapped_gstin_count?: number;
  unchecked_count?: number;
  gross_invoices_count?: number;
  credit_notes_count?: number;
  debit_notes_count?: number;
  return_period: string;
}

interface AvailablePeriod {
  period: string;
  label: string;
  financial_year: string;
  has_ingested_data: boolean;
  has_book_data: boolean;
}

interface ExpiryRadar {
  deadline: string;
  days_remaining: number;
  is_critical: boolean;
  total_expiring_itc: number;
  expiring_count: number;
  items: Array<{
    voucher_id: string;
    voucher_number: string;
    invoice_number: string;
    supplier_name: string;
    voucher_date: string;
    tax_amount: number;
    match_status: string;
  }>;
}

interface ReconciliationItem {
  source: "BOOKS" | "GSTR2B";
  voucher_id?: string;
  record_id?: string;
  invoice_number: string;
  invoice_date: string;
  supplier_name: string;
  supplier_gstin: string;
  books_taxable: number;
  books_tax: number;
  books_total: number;
  itc_match_status: "MATCHED" | "MISMATCHED" | "MISSING_IN_2B" | "MISSING_IN_BOOKS" | "UNCHECKED" | "DATA_UNAVAILABLE" | "UNMAPPED_GSTIN" | "LATER_PERIOD_MATCH" | "AMENDED" | "REVIEW_REQUIRED" | "NOT_YET_REFLECTED" | string;
  itc_held_amount: number;
  itc_notes: string;
  gstr2b_record?: {
    invoice_number: string;
    invoice_date: string;
    taxable_value: number;
    total_tax: number;
    cgst: number;
    sgst: number;
    igst: number;
    mismatch_details?: any;
  } | null;
}

interface PeriodSyncResult {
  period: string;
  period_label?: string;
  status: "SUCCESS" | "FAILED" | "PENDING" | "NOT_APPLICABLE" | string;
  fetch_status?: string;
  ingestion_status?: string;
  reconciliation_status?: string;
  invoice_count?: number;
  invoices_ingested?: number;
  invoices_reconciled?: number;
  records_created?: number;
  records_updated?: number;
  records_unchanged?: number;
  error_category?: string;
  error_code?: string;
  error_message?: string;
  is_form_not_applicable?: boolean;
}

export default function VendorITCRiskShieldPage() {
  const router = useRouter();
  const { activeCompany, companyId: activeCompanyId } = useCompany();
  const companyId =
    activeCompanyId ||
    (typeof window !== "undefined" ? localStorage.getItem("vouch_active_company_id") || "" : "");

  // State
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [summary, setSummary] = useState<SummaryStats | null>(null);
  const [expiryRadar, setExpiryRadar] = useState<ExpiryRadar | null>(null);
  const [items, setItems] = useState<ReconciliationItem[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedPeriod, setSelectedPeriod] = useState<string>("");
  const [availablePeriods, setAvailablePeriods] = useState<AvailablePeriod[]>([]);

  // Multi-GSTIN Registrations
  const [registrations, setRegistrations] = useState<GSTRegistration[]>([]);
  const [selectedRegistrationId, setSelectedRegistrationId] = useState<string>("");

  // Modals
  const [isSyncModalOpen, setIsSyncModalOpen] = useState(false);
  const [syncMode, setSyncMode] = useState<"range" | "single">("range");
  const [syncRangePreset, setSyncRangePreset] = useState<"2025" | "2026" | "custom">("2025");
  const [syncFromPeriod, setSyncFromPeriod] = useState<string>("042025");
  const [syncToPeriod, setSyncToPeriod] = useState<string>("102025");
  const [syncPeriod, setSyncPeriod] = useState<string>("102025");
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [syncSuccess, setSyncSuccess] = useState<string | null>(null);

  // Sync Results Breakdown
  const [periodResults, setPeriodResults] = useState<PeriodSyncResult[]>([]);
  const [failedPeriods, setFailedPeriods] = useState<string[]>([]);
  const [overallSyncStatus, setOverallSyncStatus] = useState<"SUCCESS" | "PARTIAL_SUCCESS" | "FAILED" | "API_ACCESS_DISABLED" | "AUTHENTICATION_REQUIRED" | null>(null);

  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [isExpiryModalOpen, setIsExpiryModalOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadPeriod, setUploadPeriod] = useState<string>("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Hold GST Modal
  const [holdModalItem, setHoldModalItem] = useState<ReconciliationItem | null>(null);
  const [heldAmountInput, setHeldAmountInput] = useState<string>("");
  const [holdNotesInput, setHoldNotesInput] = useState<string>("");
  const [savingHold, setSavingHold] = useState(false);

  // WhatsApp Notice Modal
  const [noticeModalItem, setNoticeModalItem] = useState<ReconciliationItem | null>(null);
  const [noticeData, setNoticeData] = useState<any>(null);
  const [loadingNotice, setLoadingNotice] = useState(false);

  // Helper to format period string e.g. 042026 -> 042026 (Apr 2026)
  const formatPeriodLabel = (p: string) => {
    if (!p || p.length !== 6) return p;
    const monthNum = parseInt(p.substring(0, 2), 10);
    const year = p.substring(2);
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const mName = months[monthNum - 1] || p.substring(0, 2);
    return `${p} (${mName} ${year})`;
  };

  // Fetch registrations on load
  useEffect(() => {
    if (!companyId) return;
    gstApi.getRegistrations(companyId)
      .then((data) => {
        const list = Array.isArray(data) ? data : [];
        setRegistrations(list);
        const primary = list.find((r) => r.is_primary);
        if (primary) {
          setSelectedRegistrationId(primary.id);
        } else if (list.length > 0) {
          setSelectedRegistrationId(list[0].id);
        }
      })
      .catch((err) => {
        console.error("Failed to load GST registrations:", err);
      });
  }, [companyId]);

  // Fetch summary & radar
  const fetchSummaryAndRadar = useCallback(async () => {
    if (!companyId) return;
    try {
      const params: any = {};
      if (selectedPeriod) params.return_period = selectedPeriod;
      if (selectedRegistrationId) params.registration_id = selectedRegistrationId;

      const res = await api.get('/api/v1/gst/itc/summary/', {
        headers: {
          "X-Company-ID": companyId,
        },
        params,
      });
      setSummary(res.data.summary);
      setExpiryRadar(res.data.expiry_radar);
    } catch (err) {
      console.error("Failed to load ITC summary:", err);
    }
  }, [companyId, selectedPeriod, selectedRegistrationId]);

  // Fetch reconciliation table
  const fetchItems = useCallback(async () => {
    if (!companyId) return;
    try {
      const params: any = {
        status: statusFilter,
        search: searchQuery,
      };
      if (selectedPeriod) params.return_period = selectedPeriod;
      if (selectedRegistrationId) params.registration_id = selectedRegistrationId;

      const res = await api.get('/api/v1/gst/itc/reconciliation/', {
        headers: {
          "X-Company-ID": companyId,
        },
        params,
      });
      setItems(res.data.results || []);
    } catch (err) {
      console.error("Failed to fetch reconciliation records:", err);
    }
  }, [companyId, statusFilter, selectedPeriod, selectedRegistrationId, searchQuery]);

  // Fetch dynamic available periods
  const fetchAvailablePeriods = useCallback(async () => {
    if (!companyId) return;
    try {
      const params: any = {};
      if (selectedRegistrationId) params.registration_id = selectedRegistrationId;
      const res = await api.get('/api/v1/gst/itc/periods/', {
        headers: { "X-Company-ID": companyId },
        params,
      });
      if (res.data?.periods) {
        setAvailablePeriods(res.data.periods);
      }
    } catch (err) {
      console.error("Failed to fetch available periods:", err);
    }
  }, [companyId, selectedRegistrationId]);

  const loadData = useCallback(async () => {
    setLoading(true);
    await Promise.all([fetchSummaryAndRadar(), fetchItems(), fetchAvailablePeriods()]);
    setLoading(false);
  }, [fetchSummaryAndRadar, fetchItems, fetchAvailablePeriods]);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }
    loadData();
  }, [loadData, router]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await Promise.all([fetchSummaryAndRadar(), fetchItems(), fetchAvailablePeriods()]);
    setRefreshing(false);
  };

  // Upload handler
  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile) {
      setUploadError("Please select a GSTR-2B JSON or Excel file.");
      return;
    }
    setUploading(true);
    setUploadError(null);

    const formData = new FormData();
    formData.append("file", uploadFile);
    if (uploadPeriod) {
      formData.append("return_period", uploadPeriod);
    }
    if (selectedRegistrationId) {
      formData.append("registration_id", selectedRegistrationId);
    }

    try {
      await api.post('/api/v1/gst/itc/upload-2b/', formData, {
        headers: {
          "X-Company-ID": companyId,
          "Content-Type": "multipart/form-data",
        },
      });
      setIsUploadModalOpen(false);
      setUploadFile(null);
      setUploadPeriod("");
      await handleRefresh();
    } catch (err: any) {
      setUploadError(err.response?.data?.error || "Failed to process GSTR-2B upload.");
    } finally {
      setUploading(false);
    }
  };

  // Direct Portal Sync Handler
  const handleSyncSubmit = async (e?: React.FormEvent, retryPeriods?: string[]) => {
    if (e) e.preventDefault();
    setSyncing(true);
    setSyncError(null);
    setSyncSuccess(null);

    let payload: any = {};
    if (retryPeriods && retryPeriods.length > 0) {
      payload = { periods: retryPeriods };
    } else if (syncMode === "range") {
      if (!syncFromPeriod || syncFromPeriod.length !== 6 || !syncToPeriod || syncToPeriod.length !== 6) {
        setSyncError("Please select both a valid From Month and To Month.");
        setSyncing(false);
        return;
      }
      const fM = parseInt(syncFromPeriod.slice(0, 2), 10);
      const fY = parseInt(syncFromPeriod.slice(2), 10);
      const tM = parseInt(syncToPeriod.slice(0, 2), 10);
      const tY = parseInt(syncToPeriod.slice(2), 10);
      const fDate = new Date(fY, fM - 1, 1);
      const tDate = new Date(tY, tM - 1, 1);
      if (fDate > tDate) {
        setSyncError("Reversed return period range: From Month cannot be later than To Month.");
        setSyncing(false);
        return;
      }
      payload = {
        from_period: syncFromPeriod,
        to_period: syncToPeriod,
      };
    } else {
      let cleanPeriod = syncPeriod.replace(/[-/]/g, '').trim();
      if (cleanPeriod.length === 8 && /^\d{8}$/.test(cleanPeriod)) {
        // Automatically normalize DDMMYYYY to MMYYYY
        cleanPeriod = cleanPeriod.slice(2);
      }
      if (!cleanPeriod || cleanPeriod.length !== 6 || !/^\d{6}$/.test(cleanPeriod)) {
        setSyncError("Please enter a valid 6-digit return period (MMYYYY, e.g. 102025 for October 2025).");
        setSyncing(false);
        return;
      }
      payload = { period: cleanPeriod };
    }

    if (selectedRegistrationId) {
      payload.registration_id = selectedRegistrationId;
    }

    try {
      const res = await api.post(
        `/api/v1/gst/reconciliation/gstr2b/sync/${companyId}/`,
        payload,
        { headers: { "X-Company-ID": companyId } }
      );
      const data = res.data;
      const pResults: PeriodSyncResult[] = data.period_results || [];
      setPeriodResults(pResults);
      const failed = data.periods_failed || [];
      setFailedPeriods(failed);
      const status = data.status || (data.success ? "SUCCESS" : "FAILED");
      setOverallSyncStatus(status);

      if (status === "SUCCESS") {
        const count = data.total_invoices_ingested ?? data.invoices_ingested ?? 0;
        const syncedCount = data.periods_synced?.length || (data.period ? 1 : 0);
        const notAppCount = data.not_applicable_periods_count || data.periods_not_applicable?.length || 0;
        const msg = notAppCount > 0
          ? `Synced ${syncedCount} statement(s) successfully (${notAppCount} interim months auto-covered under QRMP quarterly filing). Ingested ${count} GSTR-2B invoices.`
          : `Synced ${syncedCount} period(s) successfully! Ingested ${count} GSTR-2B invoices.`;
        setSyncSuccess(msg);
        await handleRefresh();
      } else if (status === "PARTIAL_SUCCESS") {
        const syncedCount = data.periods_synced?.length || 0;
        const count = data.total_invoices_ingested ?? 0;
        const notAppCount = data.not_applicable_periods_count || data.periods_not_applicable?.length || 0;
        const msg = `Partially synced: ${syncedCount} period(s) succeeded (${count} invoices ingested). ${failed.length} period(s) failed${notAppCount > 0 ? `, ${notAppCount} not applicable under QRMP` : ''}.`;
        setSyncSuccess(msg);
        await handleRefresh();
      } else if (status === "NOT_APPLICABLE") {
        setSyncError(data.error || "GSTR-2B form is not applicable for this period under the QRMP scheme. Under QRMP, official GSTR-2B is generated on quarter-ends (June, September, December, March).");
      } else {
        setSyncError(data.error || "Failed to fetch GSTR-2B from GST Portal.");
      }
    } catch (err: any) {
      const errData = err.response?.data;
      if (errData?.period_results) {
        setPeriodResults(errData.period_results);
        setFailedPeriods(errData.periods_failed || (errData.period ? [errData.period] : []));
      } else if (errData?.period || errData?.return_period) {
        const p = errData.period || errData.return_period;
        setPeriodResults([{
          period: p,
          status: errData.status || "FAILED",
          error_category: errData.error_category || errData.error_code,
          error_code: errData.error_code || errData.error_category,
          error_message: errData.error,
          is_form_not_applicable: errData.is_form_not_applicable || errData.error_code === "FORM_NOT_APPLICABLE",
        }]);
        setFailedPeriods([p]);
      }
      setOverallSyncStatus(errData?.status || "FAILED");
      setSyncError(errData?.error || "Failed to fetch GSTR-2B from GST Portal. Please ensure GST Portal is connected in Settings.");
    } finally {
      setSyncing(false);
    }
  };

  // Open Hold Modal
  const openHoldModal = (item: ReconciliationItem) => {
    setHoldModalItem(item);
    setHeldAmountInput(
      item.itc_held_amount > 0 ? String(item.itc_held_amount) : String(item.books_tax)
    );
    setHoldNotesInput(item.itc_notes || `GST payment held until reflected in GSTR-2B.`);
  };

  // Save Hold
  const handleSaveHold = async () => {
    if (!holdModalItem || !holdModalItem.voucher_id) return;
    setSavingHold(true);
    try {
      await api.post(
        '/api/v1/gst/itc/hold-gst/',
        {
          voucher_id: holdModalItem.voucher_id,
          held_amount: parseFloat(heldAmountInput) || 0,
          notes: holdNotesInput,
        },
        {
          headers: {
            "X-Company-ID": companyId,
          },
        }
      );
      setHoldModalItem(null);
      await handleRefresh();
    } catch (err) {
      console.error("Failed to save GST hold:", err);
    } finally {
      setSavingHold(false);
    }
  };

  // Open WhatsApp Notice Modal
  const openNoticeModal = async (item: ReconciliationItem) => {
    if (!item.voucher_id) return;
    setNoticeModalItem(item);
    setLoadingNotice(true);
    try {
      const res = await api.get(
        `/api/v1/gst/itc/vendor-notice/${item.voucher_id}/`,
        {
          headers: {
            "X-Company-ID": companyId,
          },
        }
      );
      setNoticeData(res.data);
    } catch (err) {
      console.error("Failed to generate notice:", err);
    } finally {
      setLoadingNotice(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-6">
        
        {/* SECTION 1: HEADER & ACTION BAR */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border/40 pb-5">
          <div>
            <div className="flex items-center gap-2.5">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-amber-600 to-rose-600 flex items-center justify-center text-white shadow-lg shadow-rose-500/20">
                <ShieldAlert className="w-5 h-5" />
              </div>
              <div>
                <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
                  Vendor ITC Risk Shield
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-rose-500/10 text-rose-500 border border-rose-500/20">
                    Section 16(2)(aa)
                  </span>
                </h1>
                <p className="text-xs sm:text-sm text-muted-foreground">
                  GSTR-2B reconciliation, supplier non-filing radar, and automated cash-flow protection.
                </p>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            {/* Multi-GSTIN Registration Selector */}
            {registrations.length > 0 && (
              <select
                value={selectedRegistrationId}
                onChange={(e) => setSelectedRegistrationId(e.target.value)}
                className="px-2.5 py-2 text-xs font-mono font-medium rounded-lg border border-border/60 bg-card hover:bg-muted/70 text-foreground cursor-pointer focus:outline-none focus:ring-1 focus:ring-primary"
                title="Filter by GST Registration (GSTIN)"
              >
                <option value="">All Registrations</option>
                {registrations.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.gstin} {r.trade_name ? `(${r.trade_name})` : `(${r.legal_name})`}
                  </option>
                ))}
              </select>
            )}

            {/* Dynamic Return Period Selector */}
            <select
              value={selectedPeriod}
              onChange={(e) => setSelectedPeriod(e.target.value)}
              className="px-2.5 py-2 text-xs font-mono font-medium rounded-lg border border-border/60 bg-card hover:bg-muted/70 text-foreground cursor-pointer focus:outline-none focus:ring-1 focus:ring-primary"
              title="Filter by Return Period"
            >
              <option value="">All Periods</option>
              {availablePeriods.length > 0 ? (
                availablePeriods.map((p) => (
                  <option key={p.period} value={p.period}>
                    {p.period} &mdash; {p.label} (FY {p.financial_year})
                  </option>
                ))
              ) : (
                <>
                  <option value="102026">102026 &mdash; Oct 2026 (FY 2026-27)</option>
                  <option value="092026">092026 &mdash; Sep 2026 (FY 2026-27)</option>
                  <option value="082026">082026 &mdash; Aug 2026 (FY 2026-27)</option>
                  <option value="072026">072026 &mdash; Jul 2026 (FY 2026-27)</option>
                  <option value="062026">062026 &mdash; Jun 2026 (FY 2026-27)</option>
                  <option value="052026">052026 &mdash; May 2026 (FY 2026-27)</option>
                  <option value="042026">042026 &mdash; Apr 2026 (FY 2026-27)</option>
                  <option value="102025">102025 &mdash; Oct 2025 (FY 2025-26)</option>
                  <option value="092025">092025 &mdash; Sep 2025 (FY 2025-26)</option>
                  <option value="082025">082025 &mdash; Aug 2025 (FY 2025-26)</option>
                  <option value="072025">072025 &mdash; Jul 2025 (FY 2025-26)</option>
                  <option value="062025">062025 &mdash; Jun 2025 (FY 2025-26)</option>
                  <option value="052025">052025 &mdash; May 2025 (FY 2025-26)</option>
                  <option value="042025">042025 &mdash; Apr 2025 (FY 2025-26)</option>
                </>
              )}
            </select>

            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg border border-border/60 bg-card hover:bg-muted/70 text-foreground transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>

            <button
              onClick={() => {
                setSyncError(null);
                setSyncSuccess(null);
                setPeriodResults([]);
                setFailedPeriods([]);
                setOverallSyncStatus(null);
                setIsSyncModalOpen(true);
              }}
              className="inline-flex items-center gap-2 px-4 py-2 text-xs sm:text-sm font-semibold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white shadow-md shadow-emerald-500/20 transition-all cursor-pointer"
            >
              <RefreshCw className="w-4 h-4" />
              <span>Sync from GST Portal</span>
            </button>

            <button
              onClick={() => setIsUploadModalOpen(true)}
              className="inline-flex items-center gap-2 px-4 py-2 text-xs sm:text-sm font-semibold rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white shadow-md shadow-blue-500/20 transition-all cursor-pointer"
            >
              <UploadCloud className="w-4 h-4" />
              <span>Upload GSTR-2B</span>
            </button>
          </div>
        </div>

        {/* SECTION 2: SECTION 16(4) EXPIRY RADAR BANNER */}
        {expiryRadar && expiryRadar.expiring_count > 0 && (
          <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-amber-500/20 flex items-center justify-center text-amber-500 shrink-0">
                <Clock className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-sm font-bold text-amber-500 flex items-center gap-2">
                  Section 16(4) Expiry Radar: {expiryRadar.days_remaining} Days Remaining
                </h4>
                <p className="text-xs text-muted-foreground">
                  You have <strong>{expiryRadar.expiring_count} purchase invoices</strong> worth{" "}
                  <strong className="text-foreground">₹{expiryRadar.total_expiring_itc.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</strong>{" "}
                  unclaimed from preceding FY approaching the hard Nov 30 cutoff.
                </p>
              </div>
            </div>
            <button
              onClick={() => {
                setStatusFilter("EXPIRING_SEC16_4");
                setIsExpiryModalOpen(true);
              }}
              className="text-xs font-semibold px-3.5 py-1.5 rounded-lg bg-amber-500 text-black hover:bg-amber-400 transition-colors whitespace-nowrap cursor-pointer flex items-center gap-1.5 shadow-sm"
            >
              <span>Review {expiryRadar.expiring_count} Expiring Bills</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* SECTION 3: TOP METRIC STAT CARDS */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Card 1: Total ITC at Risk */}
          <div className="bg-card border border-rose-500/30 rounded-xl p-4.5 shadow-sm relative overflow-hidden group">
            <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-rose-600 to-rose-400" />
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-rose-500 uppercase tracking-wider">
                Total ITC at Risk
              </span>
              <ShieldAlert className="w-4 h-4 text-rose-500" />
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-extrabold text-foreground">
                ₹{summary?.itc_at_risk?.toLocaleString("en-IN", { minimumFractionDigits: 2 }) || "0.00"}
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground mt-1">
              {(summary?.missing_in_2b_count || 0) + (summary?.mismatched_count || 0)} bills unfiled or mismatched
            </p>
          </div>

          {/* Card 2: Ghost Bills / Missing in 2B */}
          <div className="bg-card border border-amber-500/30 rounded-xl p-4.5 shadow-sm relative overflow-hidden">
            <div className="absolute top-0 left-0 right-0 h-1 bg-amber-500" />
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-amber-500 uppercase tracking-wider">
                Missing in GSTR-2B
              </span>
              <AlertTriangle className="w-4 h-4 text-amber-500" />
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-extrabold text-foreground">
                {summary?.missing_in_2b_count || 0}
              </span>
              <span className="text-xs text-muted-foreground">invoices</span>
            </div>
            <p className="text-[11px] text-muted-foreground mt-1">
              Vendors haven&apos;t filed GSTR-1
            </p>
          </div>

          {/* Card 3: Smart Payment Hold Active */}
          <div className="bg-card border border-indigo-500/30 rounded-xl p-4.5 shadow-sm relative overflow-hidden">
            <div className="absolute top-0 left-0 right-0 h-1 bg-indigo-500" />
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-indigo-400 uppercase tracking-wider">
                Active GST Payment Hold
              </span>
              <Lock className="w-4 h-4 text-indigo-400" />
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-extrabold text-foreground">
                ₹{summary?.itc_held_total?.toLocaleString("en-IN", { minimumFractionDigits: 2 }) || "0.00"}
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground mt-1">
              Cash protected in your bank account
            </p>
          </div>

          {/* Card 4: Safe Reconciled ITC */}
          <div className="bg-card border border-emerald-500/30 rounded-xl p-4.5 shadow-sm relative overflow-hidden">
            <div className="absolute top-0 left-0 right-0 h-1 bg-emerald-500" />
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-emerald-500 uppercase tracking-wider">
                Safe Reconciled ITC
              </span>
              <ShieldCheck className="w-4 h-4 text-emerald-500" />
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-extrabold text-foreground">
                ₹{summary?.itc_safe?.toLocaleString("en-IN", { minimumFractionDigits: 2 }) || "0.00"}
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground mt-1">
              {summary?.matched_count || 0} invoices verified in GSTR-2B
            </p>
          </div>
        </div>

        {/* SECTION 4: FILTER TABS & SEARCH */}
        <div className="bg-card border border-border/40 rounded-xl p-3 sm:p-4 space-y-3">
          <div className="flex flex-col md:flex-row items-center justify-between gap-3">
            {/* Status Tabs */}
            <div className="flex flex-wrap items-center gap-1.5 w-full md:w-auto">
              {[
                {
                  key: "ALL",
                  label: "All Bills",
                  count: summary
                    ? (summary.matched_count || 0) +
                      (summary.mismatched_count || 0) +
                      (summary.missing_in_2b_count || 0) +
                      (summary.missing_in_books_count || 0) +
                      (summary.data_unavailable_count || 0) +
                      (summary.unmapped_gstin_count || 0) +
                      (summary.unchecked_count || 0) +
                      (summary.review_required_count || 0)
                    : null,
                  color: "text-muted-foreground bg-muted",
                },
                ...(expiryRadar && expiryRadar.expiring_count > 0
                  ? [
                      {
                        key: "EXPIRING_SEC16_4",
                        label: "Expiring Nov 30",
                        count: expiryRadar.expiring_count,
                        color: "text-amber-700 bg-amber-500/20 dark:text-amber-300 font-bold border border-amber-500/30",
                      },
                    ]
                  : []),
                { key: "MISSING_IN_2B", label: "Missing in 2B", count: summary?.missing_in_2b_count, color: "text-rose-500 bg-rose-500/10" },
                { key: "MISMATCHED", label: "Mismatches", count: summary?.mismatched_count, color: "text-amber-500 bg-amber-500/10" },
                { key: "MISSING_IN_BOOKS", label: "Missing in Books", count: summary?.missing_in_books_count, color: "text-blue-500 bg-blue-500/10" },
                { key: "MATCHED", label: "Reconciled (Safe)", count: summary?.matched_count, color: "text-emerald-500 bg-emerald-500/10" },
                ...(summary?.data_unavailable_count ? [{ key: "DATA_UNAVAILABLE", label: "Statement Pending", count: summary.data_unavailable_count, color: "text-slate-500 bg-slate-500/10" }] : []),
                ...(summary?.unmapped_gstin_count ? [{ key: "UNMAPPED_GSTIN", label: "Unmapped GSTIN", count: summary.unmapped_gstin_count, color: "text-purple-500 bg-purple-500/10" }] : []),
                ...(summary?.unchecked_count ? [{ key: "UNCHECKED", label: "Unchecked", count: summary.unchecked_count, color: "text-zinc-500 bg-zinc-500/10" }] : []),
                ...(summary?.later_period_count ? [{ key: "LATER_PERIOD_MATCH", label: "Later 2B Period", count: summary.later_period_count, color: "text-cyan-500 bg-cyan-500/10" }] : []),
                ...(summary?.amended_count ? [{ key: "AMENDED", label: "Amended", count: summary.amended_count, color: "text-indigo-500 bg-indigo-500/10" }] : []),
                ...(summary?.review_required_count ? [{ key: "REVIEW_REQUIRED", label: "Review Required", count: summary.review_required_count, color: "text-orange-500 bg-orange-500/10" }] : []),
              ].map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setStatusFilter(tab.key)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5 cursor-pointer ${
                    statusFilter === tab.key
                      ? "bg-primary text-primary-foreground font-semibold shadow-sm"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                  }`}
                >
                  <span>{tab.label}</span>
                  {tab.count !== null && tab.count !== undefined && (
                    <span className={`text-[10px] px-1.5 py-0.2 rounded-full ${statusFilter === tab.key ? "bg-primary-foreground/20 text-primary-foreground" : tab.color}`}>
                      {tab.count}
                    </span>
                  )}
                </button>
              ))}
            </div>

            {/* Search Input */}
            <div className="relative w-full md:w-64">
              <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search vendor, invoice, GSTIN..."
                className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg border border-border/60 bg-background focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          </div>
        </div>

        {/* SECTION 5: RECONCILIATION DATA TABLE */}
        <div className="bg-card border border-border/40 rounded-xl overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-muted/50 border-b border-border/40 text-muted-foreground font-semibold">
                  <th className="p-3 w-28">Match Status</th>
                  <th className="p-3">Vendor / Supplier</th>
                  <th className="p-3">Invoice Details</th>
                  <th className="p-3 text-right">Your Books (₹)</th>
                  <th className="p-3 text-right">GSTR-2B (₹)</th>
                  <th className="p-3">Discrepancy / Risk</th>
                  <th className="p-3 text-center w-36">Smart Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/20">
                {loading ? (
                  <tr>
                    <td colSpan={7} className="p-8 text-center text-muted-foreground">
                      <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-primary" />
                      Loading reconciliation data...
                    </td>
                  </tr>
                ) : items.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="p-12 text-center text-muted-foreground">
                      <ShieldCheck className="w-10 h-10 text-muted-foreground/40 mx-auto mb-3" />
                      <p className="font-semibold text-foreground text-sm">No records found matching filters</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Upload your latest GSTR-2B JSON or Excel file to trigger auto-reconciliation.
                      </p>
                    </td>
                  </tr>
                ) : (
                  items.map((item, idx) => {
                    const isMatched = item.itc_match_status === "MATCHED";
                    const isLaterPeriod = item.itc_match_status === "LATER_PERIOD_MATCH";
                    const isAmended = item.itc_match_status === "AMENDED";
                    const isMismatched = item.itc_match_status === "MISMATCHED";
                    const isReviewRequired = item.itc_match_status === "REVIEW_REQUIRED";
                    const isNotYetReflected = item.itc_match_status === "NOT_YET_REFLECTED";
                    const isDataUnavailable = item.itc_match_status === "DATA_UNAVAILABLE";
                    const isUnmappedGSTIN = item.itc_match_status === "UNMAPPED_GSTIN";
                    const isUnchecked = item.itc_match_status === "UNCHECKED";
                    const isMissing2B = item.itc_match_status === "MISSING_IN_2B";
                    const isMissingBooks = item.itc_match_status === "MISSING_IN_BOOKS";

                    return (
                      <tr key={idx} className="hover:bg-muted/30 transition-colors">
                        {/* Status Badge */}
                        <td className="p-3 align-top">
                          {isMatched && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                              <CheckCircle2 className="w-3 h-3" />
                              Matched
                            </span>
                          )}
                          {isLaterPeriod && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 border border-cyan-500/20" title="Filed in a later GSTR-2B period by vendor">
                              <CheckCircle2 className="w-3 h-3" />
                              Later 2B
                            </span>
                          )}
                          {isAmended && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
                              <Info className="w-3 h-3" />
                              Amended
                            </span>
                          )}
                          {isMismatched && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/10 text-amber-500 border border-amber-500/20">
                              <AlertTriangle className="w-3 h-3" />
                              Mismatch
                            </span>
                          )}
                          {isReviewRequired && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-orange-500/10 text-orange-600 dark:text-orange-400 border border-orange-500/20">
                              <AlertTriangle className="w-3 h-3" />
                              Review Req
                            </span>
                          )}
                          {isNotYetReflected && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-500/10 text-slate-600 dark:text-slate-400 border border-slate-500/20" title="Within current GSTR-1 vendor filing window">
                              <Clock className="w-3 h-3" />
                              Pending 2B
                            </span>
                          )}
                          {isDataUnavailable && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-500/10 text-slate-600 dark:text-slate-400 border border-slate-500/20" title="GSTR-2B statement not yet imported for this return period">
                              <Clock className="w-3 h-3" />
                              Statement Pending
                            </span>
                          )}
                          {isUnmappedGSTIN && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20" title="Buyer GSTIN not registered in company profile">
                              <AlertTriangle className="w-3 h-3" />
                              Unmapped GSTIN
                            </span>
                          )}
                          {isUnchecked && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-zinc-500/10 text-zinc-500 border border-zinc-500/20" title="Unreconciled against GSTR-2B">
                              <Clock className="w-3 h-3" />
                              Unchecked
                            </span>
                          )}
                          {isMissing2B && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-500/10 text-rose-500 border border-rose-500/20">
                              <XCircle className="w-3 h-3" />
                              Missing in 2B
                            </span>
                          )}
                          {isMissingBooks && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-500/10 text-blue-500 border border-blue-500/20">
                              <Info className="w-3 h-3" />
                              Missing in Books
                            </span>
                          )}
                        </td>

                        {/* Vendor & GSTIN */}
                        <td className="p-3 align-top">
                          <div className="font-semibold text-foreground">{item.supplier_name}</div>
                          <div className="font-mono text-[10px] text-muted-foreground mt-0.5">
                            {item.supplier_gstin || "URP"}
                          </div>
                        </td>

                        {/* Invoice # & Date */}
                        <td className="p-3 align-top">
                          <div className="font-medium text-foreground">{item.invoice_number}</div>
                          <div className="text-[10px] text-muted-foreground">{item.invoice_date}</div>
                        </td>

                        {/* Books Values */}
                        <td className="p-3 align-top text-right">
                          <div className="font-semibold text-foreground">
                            ₹{item.books_taxable.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                          </div>
                          <div className="text-[10px] text-muted-foreground">
                            Tax: ₹{item.books_tax.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                          </div>
                        </td>

                        {/* GSTR-2B Values */}
                        <td className="p-3 align-top text-right">
                          {item.gstr2b_record ? (
                            <>
                              <div className="font-semibold text-foreground">
                                ₹{item.gstr2b_record.taxable_value.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                              </div>
                              <div className="text-[10px] text-muted-foreground">
                                Tax: ₹{item.gstr2b_record.total_tax.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                              </div>
                            </>
                          ) : isDataUnavailable ? (
                            <span className="text-[11px] text-slate-400 italic">Statement Pending</span>
                          ) : isUnmappedGSTIN ? (
                            <span className="text-[11px] text-purple-400 italic">Unmapped GSTIN</span>
                          ) : isUnchecked ? (
                            <span className="text-[11px] text-zinc-400 italic">Unchecked</span>
                          ) : (
                            <span className="text-[11px] text-rose-400 italic">Not in GSTR-2B</span>
                          )}
                        </td>

                        {/* Discrepancy Note */}
                        <td className="p-3 align-top max-w-xs">
                          <div className="text-[11px] text-muted-foreground line-clamp-2">
                            {item.itc_notes || "None"}
                          </div>
                          {item.itc_held_amount > 0 && (
                            <div className="mt-1 flex items-center gap-1 text-[10px] font-semibold text-indigo-400 bg-indigo-500/10 px-1.5 py-0.5 rounded w-fit">
                              <Lock className="w-2.5 h-2.5" />
                              <span>Hold Active: ₹{item.itc_held_amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
                            </div>
                          )}
                        </td>

                        {/* Actions */}
                        <td className="p-3 align-top text-center space-y-1">
                          {item.voucher_id && (
                            <div className="flex items-center justify-center gap-1">
                              {/* Hold GST Button */}
                              <button
                                onClick={() => openHoldModal(item)}
                                title="Hold GST Portion"
                                className="p-1.5 rounded-lg border border-indigo-500/30 text-indigo-400 hover:bg-indigo-500/10 transition-colors"
                              >
                                <Lock className="w-3.5 h-3.5" />
                              </button>

                              {/* WhatsApp Notice Button */}
                              <button
                                onClick={() => openNoticeModal(item)}
                                title="Send WhatsApp Notice to Vendor"
                                className="p-1.5 rounded-lg border border-emerald-500/30 text-emerald-500 hover:bg-emerald-500/10 transition-colors"
                              >
                                <MessageCircle className="w-3.5 h-3.5" />
                              </button>

                              {/* View Voucher Link */}
                              <Link
                                href={`/vouchers?search=${encodeURIComponent(item.invoice_number)}`}
                                title="View Voucher in Books"
                                className="p-1.5 rounded-lg border border-border/40 text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
                              >
                                <ExternalLink className="w-3.5 h-3.5" />
                              </Link>
                            </div>
                          )}

                          {isMissingBooks && (
                            <Link
                              href="/purchases/new"
                              className="text-[10px] font-semibold px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-500 inline-block"
                            >
                              + Book Purchase
                            </Link>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* MODAL 0: SYNC FROM GST PORTAL */}
        {isSyncModalOpen && (
          <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-card border border-border/40 rounded-2xl p-6 max-w-xl w-full max-h-[90vh] overflow-y-auto shadow-2xl space-y-4 animate-in fade-in zoom-in-95">
              <div className="flex items-center justify-between border-b border-border/40 pb-3">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-emerald-500/10 flex items-center justify-center text-emerald-600 dark:text-emerald-400">
                    <RefreshCw className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="font-bold text-foreground text-sm">Sync GSTR-2B from GST Portal</h3>
                    <p className="text-[11px] text-muted-foreground">Directly fetch official auto-drafted ITC statement</p>
                  </div>
                </div>
                <button
                  onClick={() => setIsSyncModalOpen(false)}
                  className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* GSTIN Registration Selector if multiple */}
              {registrations.length > 0 && (
                <div>
                  <label className="block text-xs font-semibold text-muted-foreground mb-1">
                    GST Registration (GSTIN)
                  </label>
                  <select
                    value={selectedRegistrationId}
                    onChange={(e) => setSelectedRegistrationId(e.target.value)}
                    className="w-full px-3 py-2 text-xs rounded-lg border border-border/60 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary font-mono cursor-pointer"
                  >
                    <option value="">All Registrations / Primary</option>
                    {registrations.map((reg) => (
                      <option key={reg.id} value={reg.id}>
                        {reg.gstin} {reg.trade_name ? `(${reg.trade_name})` : `(${reg.legal_name})`} {reg.is_primary ? "★ Primary" : ""}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Sync Mode Selection Tabs */}
              <div className="grid grid-cols-3 gap-2 p-1 bg-muted/40 rounded-xl border border-border/40">
                <button
                  type="button"
                  onClick={() => {
                    setSyncMode("range");
                    setSyncFromPeriod("042025");
                    setSyncToPeriod("102025");
                  }}
                  className={`px-2.5 py-2 text-xs font-semibold rounded-lg transition-all flex flex-col items-center justify-center gap-0.5 cursor-pointer ${
                    syncMode === "range" && syncFromPeriod.endsWith("2025")
                      ? "bg-card text-foreground shadow-sm border border-border/50 font-bold"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <span>FY 2025&ndash;26</span>
                  <span className="text-[9px] uppercase px-1.5 py-0.2 rounded bg-blue-500/15 text-blue-600 dark:text-blue-400 font-bold">
                    Apr &ndash; Oct &apos;25
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setSyncMode("range");
                    setSyncFromPeriod("042026");
                    setSyncToPeriod("102026");
                  }}
                  className={`px-2.5 py-2 text-xs font-semibold rounded-lg transition-all flex flex-col items-center justify-center gap-0.5 cursor-pointer ${
                    syncMode === "range" && syncFromPeriod.endsWith("2026")
                      ? "bg-card text-foreground shadow-sm border border-border/50 font-bold"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <span>FY 2026&ndash;27</span>
                  <span className="text-[9px] uppercase px-1.5 py-0.2 rounded bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 font-bold">
                    Apr &ndash; Oct &apos;26
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => setSyncMode("single")}
                  className={`px-2.5 py-2 text-xs font-semibold rounded-lg transition-all flex flex-col items-center justify-center gap-0.5 cursor-pointer ${
                    syncMode === "single"
                      ? "bg-card text-foreground shadow-sm border border-border/50 font-bold"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <span>Single Month</span>
                  <span className="text-[9px] text-muted-foreground">Any Month</span>
                </button>
              </div>

              <form onSubmit={(e) => handleSyncSubmit(e)} className="space-y-4">
                {syncMode === "range" ? (
                  <div className="space-y-3">
                    <div className="p-3 rounded-xl bg-primary/5 border border-primary/20 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                          <Calendar className="w-3.5 h-3.5 text-primary" />
                          {syncFromPeriod.endsWith("2025") ? "FY 2025–26 (April to October 2025)" : "FY 2026–27 (April to October 2026)"}
                        </span>
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                          Multi-Month Range
                        </span>
                      </div>
                      <p className="text-[11px] text-muted-foreground leading-relaxed">
                        Fetches official auto-drafted GSTR-2B statements from GST Portal and idempotently reconciles your purchase invoices.
                      </p>
                    </div>

                    <div className="grid grid-cols-2 gap-3 pt-1">
                      <MonthPickerInput
                        label="From Month"
                        value={syncFromPeriod}
                        onChange={(norm) => {
                          setSyncFromPeriod(norm);
                          if (syncToPeriod) {
                            const fM = parseInt(norm.slice(0, 2), 10);
                            const fY = parseInt(norm.slice(2), 10);
                            const tM = parseInt(syncToPeriod.slice(0, 2), 10);
                            const tY = parseInt(syncToPeriod.slice(2), 10);
                            if (new Date(fY, fM - 1, 1) > new Date(tY, tM - 1, 1)) {
                              setSyncError("From Month cannot be later than To Month.");
                            } else {
                              setSyncError(null);
                            }
                          }
                        }}
                        placeholder="April 2026"
                      />
                      <MonthPickerInput
                        label="To Month"
                        value={syncToPeriod}
                        onChange={(norm) => {
                          setSyncToPeriod(norm);
                          if (syncFromPeriod) {
                            const fM = parseInt(syncFromPeriod.slice(0, 2), 10);
                            const fY = parseInt(syncFromPeriod.slice(2), 10);
                            const tM = parseInt(norm.slice(0, 2), 10);
                            const tY = parseInt(norm.slice(2), 10);
                            if (new Date(fY, fM - 1, 1) > new Date(tY, tM - 1, 1)) {
                              setSyncError("From Month cannot be later than To Month.");
                            } else {
                              setSyncError(null);
                            }
                          }
                        }}
                        placeholder="October 2026"
                      />
                    </div>

                    {/* Selected Range Display */}
                    <div className="p-2.5 rounded-xl bg-muted/40 border border-border/50 flex items-center justify-between text-xs">
                      <span className="text-muted-foreground font-medium">Selected range:</span>
                      <span className="font-bold text-foreground font-mono">
                        {parsePeriodToDisplay(syncFromPeriod) || syncFromPeriod} &ndash; {parsePeriodToDisplay(syncToPeriod) || syncToPeriod}
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <MonthPickerInput
                      label="Return Period (Month & Year)"
                      value={syncPeriod}
                      onChange={(norm) => {
                        setSyncPeriod(norm);
                        setSyncError(null);
                      }}
                      placeholder="e.g. October 2026"
                    />

                    {/* Selected Single Period Display */}
                    <div className="p-2.5 rounded-xl bg-muted/40 border border-border/50 flex items-center justify-between text-xs">
                      <span className="text-muted-foreground font-medium">Selected period:</span>
                      <span className="font-bold text-foreground font-mono">
                        {parsePeriodToDisplay(syncPeriod) || syncPeriod}
                      </span>
                    </div>
                    <p className="text-[11px] text-muted-foreground">
                      Type directly (e.g. <strong>April 2026</strong>, <strong>04/2026</strong>, <strong>042026</strong>) or use the month calendar picker.
                    </p>
                  </div>
                )}

                {syncError && (() => {
                  const errLower = syncError.toLowerCase();
                  const isPrivilegeOrApiError =
                    overallSyncStatus === "API_ACCESS_DISABLED" ||
                    errLower.includes("privilege") ||
                    errLower.includes("api access") ||
                    errLower.includes("manage api");

                  const isSessionAuthError =
                    overallSyncStatus === "AUTHENTICATION_REQUIRED" ||
                    errLower.includes("session") ||
                    errLower.includes("reconnect") ||
                    errLower.includes("token");

                  if (isPrivilegeOrApiError) {
                    return (
                      <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs text-amber-900 dark:text-amber-200 space-y-2.5">
                        <div className="flex items-start gap-2">
                          <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                          <div className="space-y-1">
                            <div className="font-bold text-amber-800 dark:text-amber-300">
                              GST Portal API Access Required
                            </div>
                            <p className="text-[11px] leading-relaxed text-muted-foreground">
                              The GST Portal returned <code className="font-mono text-rose-500 bg-rose-500/10 px-1 py-0.5 rounded">Insufficient privilege</code>. Your GST API access is currently disabled or expired on the government portal (<strong className="text-foreground">services.gst.gov.in</strong>).
                            </p>
                          </div>
                        </div>

                        <div className="bg-background/60 p-2.5 rounded-lg border border-amber-500/20 text-[11px] space-y-1 text-muted-foreground">
                          <div className="font-semibold text-foreground">How to enable in 4 simple steps:</div>
                          <ol className="list-decimal list-inside space-y-0.5">
                            <li>Sign in to <strong className="text-foreground">services.gst.gov.in</strong></li>
                            <li>Navigate to <strong className="text-foreground">My Profile &gt; Manage API Access</strong></li>
                            <li>Toggle master switch <strong className="text-foreground">&apos;Enable API Request&apos;</strong> to <strong className="text-emerald-600 dark:text-emerald-400 font-bold">Yes</strong> (duration: 30 days) and Save</li>
                            <li>Select <strong className="text-foreground">Quicko Infosoft</strong> as authorized GSP</li>
                          </ol>
                        </div>

                        <div className="pt-1 flex flex-wrap items-center gap-2">
                          <a
                            href="https://services.gst.gov.in"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-semibold flex items-center gap-1 transition-colors shadow-sm"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                            <span>Open GST Portal ↗</span>
                          </a>
                          <Link
                            href="/settings"
                            className="px-3 py-1.5 bg-muted hover:bg-muted/80 text-foreground rounded-lg text-xs font-semibold flex items-center gap-1 transition-colors border border-border"
                          >
                            <span>Reconnect in Settings →</span>
                          </Link>
                        </div>
                      </div>
                    );
                  }

                  if (isSessionAuthError) {
                    return (
                      <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs text-amber-900 dark:text-amber-200 space-y-2">
                        <div className="flex items-start gap-2">
                          <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                          <div className="space-y-1">
                            <div className="font-bold text-amber-800 dark:text-amber-300">
                              GST Portal Session Expired
                            </div>
                            <p className="text-[11px] leading-relaxed text-muted-foreground">
                              {syncError}
                            </p>
                          </div>
                        </div>
                        <div className="pt-1">
                          <Link
                            href="/settings"
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground hover:bg-primary/90 rounded-lg text-xs font-semibold transition-colors"
                          >
                            <span>Reconnect GST Portal in Settings →</span>
                          </Link>
                        </div>
                      </div>
                    );
                  }

                  return (
                    <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-xs text-rose-500 flex items-start gap-2">
                      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                      <span>{syncError}</span>
                    </div>
                  );
                })()}

                {syncSuccess && (
                  <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-600 dark:text-emerald-400 flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 shrink-0" />
                    <span>{syncSuccess}</span>
                  </div>
                )}

                {/* Period Results Breakdown Table */}
                {periodResults.length > 0 && (
                  <div className="space-y-3 pt-2">
                    <div className="flex items-center justify-between">
                      <h4 className="text-xs font-bold text-foreground uppercase tracking-wider">
                        Period-by-Period Sync Status
                      </h4>
                      <span className="text-[11px] text-muted-foreground">
                        {periodResults.filter(p => p.status === 'SUCCESS').length} of {periodResults.length} periods synced
                      </span>
                    </div>

                    <div className="border border-border/50 rounded-xl overflow-hidden bg-muted/20">
                      <table className="w-full text-left border-collapse text-xs">
                        <thead>
                          <tr className="bg-muted/60 border-b border-border/40 text-[11px] text-muted-foreground font-semibold">
                            <th className="p-2.5">Period</th>
                            <th className="p-2.5">GSTR-2B Invoices</th>
                            <th className="p-2.5">Reconciled</th>
                            <th className="p-2.5 text-right">Status</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border/20">
                          {periodResults.map((pr) => {
                            const isSuccess = pr.status === "SUCCESS" || pr.fetch_status === "SUCCESS";
                            const isNotApplicable =
                              pr.status === "NOT_APPLICABLE" ||
                              pr.fetch_status === "NOT_APPLICABLE" ||
                              pr.error_code === "FORM_NOT_APPLICABLE" ||
                              pr.is_form_not_applicable ||
                              (pr.error_message && pr.error_message.toLowerCase().includes("not applicable"));

                            const isApiDisabled =
                              pr.status === "API_ACCESS_DISABLED" ||
                              pr.error_category === "API_ACCESS_DISABLED" ||
                              (pr.error_message && (pr.error_message.toLowerCase().includes("privilege") || pr.error_message.toLowerCase().includes("api access")));

                            const invCount = pr.invoice_count ?? pr.invoices_ingested ?? 0;
                            const recCount = pr.records_created ?? pr.invoices_reconciled ?? 0;

                            return (
                              <tr key={pr.period} className="hover:bg-muted/30">
                                <td className="p-2.5 font-medium text-foreground">
                                  <div className="font-mono">{formatPeriodLabel(pr.period)}</div>
                                  {pr.error_message && !isSuccess && !isNotApplicable && (
                                    <div
                                      className="text-[10px] text-rose-500 font-sans font-normal mt-0.5 max-w-[200px] leading-tight"
                                      title={pr.error_message}
                                    >
                                      {isApiDisabled
                                        ? "API Access Disabled on Portal"
                                        : (pr.error_message.length > 35 ? `${pr.error_message.slice(0, 35)}...` : pr.error_message)}
                                    </div>
                                  )}
                                </td>
                                <td className="p-2.5">
                                  {isSuccess ? (
                                    <span className="text-foreground">{invCount} invoices</span>
                                  ) : isNotApplicable ? (
                                    <span className="text-muted-foreground text-[11px]">QRMP Interim</span>
                                  ) : (
                                    <span className="text-muted-foreground">-</span>
                                  )}
                                </td>
                                <td className="p-2.5">
                                  {isSuccess ? (
                                    <span className="text-foreground">{recCount} bills</span>
                                  ) : isNotApplicable ? (
                                    <span className="text-muted-foreground text-[11px]">Quarterly</span>
                                  ) : (
                                    <span className="text-muted-foreground">-</span>
                                  )}
                                </td>
                                <td className="p-2.5 text-right">
                                  {isSuccess ? (
                                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                                      <CheckCircle2 className="w-3 h-3" /> Synced
                                    </span>
                                  ) : isNotApplicable ? (
                                    <span
                                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20"
                                      title={pr.error_message || "Form not applicable (QRMP quarterly filer)"}
                                    >
                                      <Info className="w-3 h-3" /> QRMP (Quarterly)
                                    </span>
                                  ) : (
                                    <span
                                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-500/10 text-rose-500 border border-rose-500/20"
                                      title={pr.error_message || "Sync failed"}
                                    >
                                      <XCircle className="w-3 h-3" />
                                      {isApiDisabled ? "API Disabled" : "Failed"}
                                    </span>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>

                    {/* QRMP Information Banner */}
                    {periodResults.some(
                      (pr) =>
                        pr.error_code === "FORM_NOT_APPLICABLE" ||
                        pr.is_form_not_applicable ||
                        (pr.error_message && pr.error_message.toLowerCase().includes("not applicable"))
                    ) && (
                      <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs text-amber-800 dark:text-amber-300 space-y-1">
                        <div className="font-bold flex items-center gap-1.5">
                          <Info className="w-4 h-4 shrink-0 text-amber-600 dark:text-amber-400" />
                          <span>QRMP Scheme Notice &mdash; Quarterly Filing</span>
                        </div>
                        <p className="text-[11px] leading-relaxed">
                          Under GST rules, taxpayers under the <strong>Quarterly Return Monthly Payment (QRMP)</strong> scheme have GSTR-2B generated quarterly at quarter-end months (June, September, December, March). Months 1 and 2 (e.g., April, May, July, August) do not generate auto-drafted monthly GSTR-2B statements.
                        </p>
                      </div>
                    )}

                    {/* Government GST Portal Action Required Banner (API Access / Privilege error) */}
                    {periodResults.some(
                      (pr) =>
                        pr.status === "API_ACCESS_DISABLED" ||
                        pr.error_category === "API_ACCESS_DISABLED" ||
                        (pr.error_message && (pr.error_message.toLowerCase().includes("privilege") || pr.error_message.toLowerCase().includes("api access")))
                    ) && (
                      <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs text-amber-900 dark:text-amber-200 space-y-2">
                        <div className="font-bold flex items-center gap-1.5 text-amber-800 dark:text-amber-300">
                          <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
                          <span>Government GST Portal Action Required</span>
                        </div>
                        <p className="text-[11px] leading-relaxed text-muted-foreground">
                          All failed periods above encountered <code className="font-mono text-rose-500 bg-rose-500/10 px-1 py-0.5 rounded">Insufficient privilege</code> from the official GST Portal. API access must be activated on the government portal before statements can be downloaded.
                        </p>
                        <ol className="list-decimal list-inside space-y-0.5 text-[11px] text-muted-foreground">
                          <li>Log in to <strong className="text-foreground">services.gst.gov.in</strong></li>
                          <li>Go to <strong className="text-foreground">My Profile &gt; Manage API Access</strong></li>
                          <li>Set <strong className="text-foreground">&apos;Enable API Request&apos;</strong> to <strong className="text-emerald-600 dark:text-emerald-400 font-bold">Yes</strong> (duration: 30 days) and Save</li>
                          <li>Authorize <strong className="text-foreground">Quicko Infosoft</strong> as GSP</li>
                        </ol>
                        <div className="pt-1 flex flex-wrap items-center gap-2">
                          <a
                            href="https://services.gst.gov.in"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-[11px] font-semibold flex items-center gap-1 transition-colors shadow-sm"
                          >
                            <ExternalLink className="w-3 h-3" /> Open services.gst.gov.in ↗
                          </a>
                          <Link
                            href="/settings"
                            className="px-3 py-1.5 bg-muted hover:bg-muted/80 text-foreground rounded-lg text-[11px] font-semibold flex items-center gap-1 transition-colors border border-border"
                          >
                            Reconnect in Settings →
                          </Link>
                        </div>
                      </div>
                    )}

                    {/* Retry Button for Failed Periods (transient/network/portal errors) */}
                    {failedPeriods.filter((p) => {
                      const match = periodResults.find((pr) => pr.period === p);
                      return !(
                        match?.error_code === "FORM_NOT_APPLICABLE" ||
                        match?.is_form_not_applicable ||
                        (match?.error_message && match.error_message.toLowerCase().includes("not applicable"))
                      );
                    }).length > 0 && (
                      <div className="flex items-center justify-between p-2.5 rounded-xl bg-rose-500/5 border border-rose-500/20">
                        <span className="text-[11px] text-muted-foreground">
                          Failed periods can be retried once API access is active.
                        </span>
                        <button
                          type="button"
                          disabled={syncing}
                          onClick={() => {
                            const retryList = failedPeriods.filter((p) => {
                              const match = periodResults.find((pr) => pr.period === p);
                              return !(
                                match?.error_code === "FORM_NOT_APPLICABLE" ||
                                match?.is_form_not_applicable ||
                                (match?.error_message && match.error_message.toLowerCase().includes("not applicable"))
                              );
                            });
                            handleSyncSubmit(undefined, retryList);
                          }}
                          className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-amber-600 hover:bg-amber-500 text-white flex items-center gap-1.5 shadow-sm disabled:opacity-50 cursor-pointer"
                        >
                          <RotateCcw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : ''}`} />
                          <span>Retry Failed Periods</span>
                        </button>
                      </div>
                    )}
                  </div>
                )}

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/40">
                  <button
                    type="button"
                    onClick={() => setIsSyncModalOpen(false)}
                    className="px-4 py-2 text-xs font-medium rounded-lg text-muted-foreground hover:bg-muted/60 cursor-pointer"
                  >
                    {periodResults.length > 0 ? "Close" : "Cancel"}
                  </button>
                  <button
                    type="submit"
                    disabled={syncing}
                    className="px-4 py-2 text-xs font-semibold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-50 cursor-pointer flex items-center gap-2 shadow-sm"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : ''}`} />
                    <span>
                      {syncing
                        ? "Fetching from GST Portal..."
                        : syncMode === "range"
                        ? "Sync Selected Periods"
                        : "Sync & Reconcile"}
                    </span>
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* MODAL 1: UPLOAD GSTR-2B */}
        {isUploadModalOpen && (
          <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-card border border-border/40 rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4 animate-in fade-in zoom-in-95">
              <div className="flex items-center justify-between border-b border-border/40 pb-3">
                <div className="flex items-center gap-2">
                  <UploadCloud className="w-5 h-5 text-primary" />
                  <h3 className="font-bold text-foreground">Upload GSTR-2B</h3>
                </div>
                <button
                  onClick={() => setIsUploadModalOpen(false)}
                  className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <form onSubmit={handleUploadSubmit} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-muted-foreground mb-1.5">
                    Return Period (Optional - e.g. 082026 for Aug 2026)
                  </label>
                  <input
                    type="text"
                    value={uploadPeriod}
                    onChange={(e) => setUploadPeriod(e.target.value)}
                    placeholder="Auto-detected from file if blank"
                    className="w-full px-3 py-2 text-xs rounded-lg border border-border/60 bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-muted-foreground mb-1.5">
                    Select File (.json or .xlsx)
                  </label>
                  <div className="border-2 border-dashed border-border/60 rounded-xl p-6 text-center hover:border-primary/50 transition-colors cursor-pointer bg-muted/20">
                    <input
                      type="file"
                      accept=".json,.xlsx,.xls"
                      onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                      className="hidden"
                      id="gstr2b-file-input"
                    />
                    <label htmlFor="gstr2b-file-input" className="cursor-pointer space-y-2 block">
                      <FileSpreadsheet className="w-8 h-8 text-muted-foreground mx-auto" />
                      <div className="text-xs text-foreground font-medium">
                        {uploadFile ? uploadFile.name : "Click to browse or drag & drop"}
                      </div>
                      <div className="text-[10px] text-muted-foreground">
                        Official GSTR-2B JSON or Excel downloaded from the GST Portal
                      </div>
                    </label>
                  </div>
                </div>

                {uploadError && (
                  <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-500 text-xs">
                    {uploadError}
                  </div>
                )}

                <div className="flex items-center justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setIsUploadModalOpen(false)}
                    className="px-4 py-2 text-xs font-medium rounded-lg text-muted-foreground hover:bg-muted/60"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={uploading || !uploadFile}
                    className="px-4 py-2 text-xs font-semibold rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                  >
                    {uploading ? "Reconciling..." : "Upload & Reconcile"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* MODAL 2: SMART PAYMENT HOLD */}
        {holdModalItem && (
          <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-card border border-border/40 rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4 animate-in fade-in zoom-in-95">
              <div className="flex items-center justify-between border-b border-border/40 pb-3">
                <div className="flex items-center gap-2">
                  <Lock className="w-5 h-5 text-indigo-400" />
                  <h3 className="font-bold text-foreground">Smart GST Payment Hold</h3>
                </div>
                <button
                  onClick={() => setHoldModalItem(null)}
                  className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="bg-muted/40 rounded-xl p-3 space-y-1 text-xs">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Supplier:</span>
                  <span className="font-semibold text-foreground">{holdModalItem.supplier_name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Invoice #:</span>
                  <span className="font-semibold text-foreground">{holdModalItem.invoice_number}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Invoice Total:</span>
                  <span className="font-semibold text-foreground">₹{holdModalItem.books_total.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Base Value (Safe to Pay):</span>
                  <span className="font-semibold text-emerald-500">₹{holdModalItem.books_taxable.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">GST Portion (Risk):</span>
                  <span className="font-semibold text-rose-500">₹{holdModalItem.books_tax.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
                </div>
              </div>

              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-semibold text-muted-foreground mb-1">
                    Amount to Place on HOLD (₹)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={heldAmountInput}
                    onChange={(e) => setHeldAmountInput(e.target.value)}
                    className="w-full px-3 py-2 text-xs rounded-lg border border-border/60 bg-background font-mono font-bold focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                  <p className="text-[10px] text-muted-foreground mt-1">
                    Recommended: Hold ₹{holdModalItem.books_tax.toFixed(2)} until supplier files GSTR-1.
                  </p>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-muted-foreground mb-1">
                    Hold Reason / Internal Note
                  </label>
                  <textarea
                    rows={2}
                    value={holdNotesInput}
                    onChange={(e) => setHoldNotesInput(e.target.value)}
                    className="w-full px-3 py-1.5 text-xs rounded-lg border border-border/60 bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setHoldModalItem(null)}
                  className="px-4 py-2 text-xs font-medium rounded-lg text-muted-foreground hover:bg-muted/60"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={savingHold}
                  onClick={handleSaveHold}
                  className="px-4 py-2 text-xs font-semibold rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50"
                >
                  {savingHold ? "Saving..." : "Apply Payment Hold"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* MODAL 3: WHATSAPP NOTICE CHASER */}
        {noticeModalItem && (
          <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-card border border-border/40 rounded-2xl p-6 max-w-lg w-full shadow-2xl space-y-4 animate-in fade-in zoom-in-95">
              <div className="flex items-center justify-between border-b border-border/40 pb-3">
                <div className="flex items-center gap-2">
                  <MessageCircle className="w-5 h-5 text-emerald-500" />
                  <h3 className="font-bold text-foreground">WhatsApp Supplier Filing Notice</h3>
                </div>
                <button
                  onClick={() => {
                    setNoticeModalItem(null);
                    setNoticeData(null);
                  }}
                  className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {loadingNotice || !noticeData ? (
                <div className="p-8 text-center text-muted-foreground">
                  <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-emerald-500" />
                  Generating legal notice payload...
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="bg-muted/30 border border-border/40 rounded-xl p-4 font-mono text-xs whitespace-pre-wrap text-foreground max-h-64 overflow-y-auto leading-relaxed">
                    {noticeData.message_text}
                  </div>

                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>
                      Vendor Mobile:{" "}
                      <strong className="text-foreground">
                        {noticeData.supplier_phone ? `+${noticeData.supplier_phone}` : "Not on file"}
                      </strong>
                    </span>
                  </div>

                  <div className="flex items-center justify-end gap-2 pt-2">
                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(noticeData.message_text);
                        alert("Notice copied to clipboard!");
                      }}
                      className="px-3 py-2 text-xs font-medium rounded-lg border border-border/60 hover:bg-muted/60 text-foreground"
                    >
                      Copy Text
                    </button>
                    <a
                      href={noticeData.whatsapp_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-lg bg-emerald-600 text-white hover:bg-emerald-500 shadow-md shadow-emerald-500/20"
                    >
                      <MessageCircle className="w-3.5 h-3.5" />
                      <span>Send on WhatsApp</span>
                    </a>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* MODAL 4: SECTION 16(4) EXPIRING BILLS REVIEW */}
        {isExpiryModalOpen && expiryRadar && (
          <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-card border border-border/40 rounded-2xl p-6 max-w-2xl w-full shadow-2xl space-y-5 animate-in fade-in zoom-in-95">
              <div className="flex items-center justify-between border-b border-border/40 pb-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-9 h-9 rounded-xl bg-amber-500/20 text-amber-500 flex items-center justify-center shrink-0">
                    <Clock className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="font-bold text-foreground text-base">
                      Section 16(4) Preceding FY Expiring Invoices
                    </h3>
                    <p className="text-xs text-amber-600 dark:text-amber-400 font-semibold">
                      Hard Cutoff: 30 November ({expiryRadar.days_remaining} Days Remaining)
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setIsExpiryModalOpen(false)}
                  className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="p-3.5 bg-amber-500/10 border border-amber-500/20 text-amber-900 dark:text-amber-300 rounded-xl space-y-1 text-xs leading-relaxed">
                <div className="font-bold flex items-center gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                  <span>Statutory Section 16(4) Lapse Notice</span>
                </div>
                <p>
                  Under <strong>Section 16(4) of the CGST Act</strong>, Input Tax Credit on invoices issued in the preceding financial year can strictly only be claimed up to <strong>30th November</strong>. After this cutoff, this <strong>₹{expiryRadar.total_expiring_itc.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</strong> tax credit will be permanently forfeited on the GST portal.
                </p>
              </div>

              {/* Invoices List */}
              <div className="border border-border/40 rounded-xl overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="bg-muted/50 border-b border-border/40 text-muted-foreground font-semibold">
                    <tr>
                      <th className="p-2.5">Vendor / Supplier</th>
                      <th className="p-2.5">Invoice # & Date</th>
                      <th className="p-2.5 text-right">Tax at Risk</th>
                      <th className="p-2.5 text-center">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/20">
                    {expiryRadar.items.map((expItem, idx) => (
                      <tr key={idx} className="hover:bg-muted/30">
                        <td className="p-2.5 font-medium text-foreground">
                          {expItem.supplier_name}
                        </td>
                        <td className="p-2.5">
                          <span className="font-semibold text-foreground">{expItem.invoice_number}</span>
                          <span className="block text-[10px] text-muted-foreground">{expItem.voucher_date}</span>
                        </td>
                        <td className="p-2.5 text-right font-mono font-bold text-rose-500">
                          ₹{expItem.tax_amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </td>
                        <td className="p-2.5 text-center">
                          <button
                            onClick={() => {
                              setIsExpiryModalOpen(false);
                              openNoticeModal({
                                source: "BOOKS",
                                voucher_id: expItem.voucher_id,
                                invoice_number: expItem.invoice_number,
                                invoice_date: expItem.voucher_date,
                                supplier_name: expItem.supplier_name,
                                supplier_gstin: "",
                                books_taxable: 0,
                                books_tax: expItem.tax_amount,
                                books_total: 0,
                                itc_match_status: "MISSING_IN_2B",
                                itc_held_amount: 0,
                                itc_notes: "",
                              });
                            }}
                            className="px-2.5 py-1 text-[11px] font-semibold rounded-lg bg-emerald-600 text-white hover:bg-emerald-500 inline-flex items-center gap-1 cursor-pointer"
                          >
                            <MessageCircle className="w-3 h-3" />
                            <span>WhatsApp Notice</span>
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex items-center justify-between pt-2">
                <span className="text-xs text-muted-foreground">
                  Showing <strong>{expiryRadar.expiring_count}</strong> critical expiring invoices
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      setStatusFilter("EXPIRING_SEC16_4");
                      setIsExpiryModalOpen(false);
                    }}
                    className="px-3.5 py-2 text-xs font-semibold rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 cursor-pointer"
                  >
                    View in Main Table
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

      </div>
    </DashboardLayout>
  );
}
