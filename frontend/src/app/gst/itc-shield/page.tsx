"use client";

import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import { API_BASE_URL } from "@/utils/api";
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
  X
} from "lucide-react";

interface SummaryStats {
  itc_at_risk: number;
  itc_safe: number;
  itc_held_total: number;
  matched_count: number;
  mismatched_count: number;
  missing_in_2b_count: number;
  missing_in_books_count: number;
  missing_in_books_itc: number;
  return_period: string;
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
  itc_match_status: "MATCHED" | "MISMATCHED" | "MISSING_IN_2B" | "MISSING_IN_BOOKS" | "UNCHECKED";
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

  // Modals
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
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

  // Fetch summary & radar
  const fetchSummaryAndRadar = useCallback(async () => {
    if (!companyId) return;
    try {
      const token = getAccessToken();
      const res = await axios.get(`${API_BASE_URL}/api/v1/gst/itc/summary/`, {
        headers: {
          Authorization: `Bearer ${token}`,
          "X-Company-ID": companyId,
        },
        params: selectedPeriod ? { return_period: selectedPeriod } : {},
      });
      setSummary(res.data.summary);
      setExpiryRadar(res.data.expiry_radar);
    } catch (err) {
      console.error("Failed to load ITC summary:", err);
    }
  }, [companyId, selectedPeriod]);

  // Fetch reconciliation table
  const fetchItems = useCallback(async () => {
    if (!companyId) return;
    try {
      const token = getAccessToken();
      const res = await axios.get(`${API_BASE_URL}/api/v1/gst/itc/reconciliation/`, {
        headers: {
          Authorization: `Bearer ${token}`,
          "X-Company-ID": companyId,
        },
        params: {
          status: statusFilter,
          return_period: selectedPeriod,
          search: searchQuery,
        },
      });
      setItems(res.data.results || []);
    } catch (err) {
      console.error("Failed to fetch reconciliation records:", err);
    }
  }, [companyId, statusFilter, selectedPeriod, searchQuery]);

  const loadData = useCallback(async () => {
    setLoading(true);
    await Promise.all([fetchSummaryAndRadar(), fetchItems()]);
    setLoading(false);
  }, [fetchSummaryAndRadar, fetchItems]);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }
    loadData();
  }, [loadData, router]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await Promise.all([fetchSummaryAndRadar(), fetchItems()]);
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

    try {
      const token = getAccessToken();
      await axios.post(`${API_BASE_URL}/api/v1/gst/itc/upload-2b/`, formData, {
        headers: {
          Authorization: `Bearer ${token}`,
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
      const token = getAccessToken();
      await axios.post(
        `${API_BASE_URL}/api/v1/gst/itc/hold-gst/`,
        {
          voucher_id: holdModalItem.voucher_id,
          held_amount: parseFloat(heldAmountInput) || 0,
          notes: holdNotesInput,
        },
        {
          headers: {
            Authorization: `Bearer ${token}`,
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
      const token = getAccessToken();
      const res = await axios.get(
        `${API_BASE_URL}/api/v1/gst/itc/vendor-notice/${item.voucher_id}/`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
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
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg border border-border/60 bg-card hover:bg-muted/70 text-foreground transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
              <span>Refresh</span>
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
              onClick={() => setStatusFilter("MISSING_IN_2B")}
              className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-amber-500 text-black hover:bg-amber-400 transition-colors whitespace-nowrap"
            >
              Review Expiring Bills
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
                { key: "ALL", label: "All Bills", count: null },
                { key: "MISSING_IN_2B", label: "Missing in 2B", count: summary?.missing_in_2b_count, color: "text-rose-500 bg-rose-500/10" },
                { key: "MISMATCHED", label: "Mismatches", count: summary?.mismatched_count, color: "text-amber-500 bg-amber-500/10" },
                { key: "MISSING_IN_BOOKS", label: "Missing in Books", count: summary?.missing_in_books_count, color: "text-blue-500 bg-blue-500/10" },
                { key: "MATCHED", label: "Reconciled (Safe)", count: summary?.matched_count, color: "text-emerald-500 bg-emerald-500/10" },
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
                    const isMismatched = item.itc_match_status === "MISMATCHED";
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
                          {isMismatched && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/10 text-amber-500 border border-amber-500/20">
                              <AlertTriangle className="w-3 h-3" />
                              Mismatch
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

      </div>
    </DashboardLayout>
  );
}
