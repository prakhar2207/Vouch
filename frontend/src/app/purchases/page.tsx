"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState, useMemo, useCallback } from "react";
import axios from "axios";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import DashboardLayout from "@/components/DashboardLayout";
import { useToast } from "@/context/ToastContext";
import { useCompany } from "@/context/CompanyContext";
import { useFinancialYear } from "@/context/FinancialYearContext";
import EditPurchaseInvoiceModal from "@/components/modals/EditPurchaseInvoiceModal";
import ConfirmModal from "@/components/modals/ConfirmModal";
import {
  Edit2,
  Trash2,
  Eye,
  FileText,
  Plus,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
  RefreshCw,
  CheckCircle,
  AlertTriangle,
  CloudOff,
  TrendingUp,
  ShoppingCart,
  Calendar,
  ArrowUpRight,
  Scale,
  Clock,
  Filter,
  ArrowRight,
  Check
} from "lucide-react";
import { offlineDb } from "@/lib/db/offlineDb";
import { retryFailedVoucher, pullIncrementalChanges } from "@/lib/sync/sync-worker";
import { vouchersRepository } from "@/lib/data";
import { PeriodPreset, computePeriodDateRange, formatFriendlyDate } from "@/utils/periodRanges";

export default function PurchaseInvoiceList() {
  const router = useRouter();
  const { toast } = useToast();
  const { companyId: activeCompanyId } = useCompany();
  const { activeFY } = useFinancialYear();

  const [invoices, setInvoices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [page, setPage] = useState<number>(1);
  const [pagination, setPagination] = useState<any>(null);
  const pageSize = 50;

  // Period Selection & Overview State
  const [periodPreset, setPeriodPreset] = useState<PeriodPreset>("ALL");
  const [customStart, setCustomStart] = useState<string>("");
  const [customEnd, setCustomEnd] = useState<string>("");
  const [filterTableByPeriod, setFilterTableByPeriod] = useState<boolean>(false);
  const [periodMetrics, setPeriodMetrics] = useState({
    totalPurchases: 0,
    purchaseCount: 0,
    totalInputGst: 0,
    inputCgst: 0,
    inputSgst: 0,
    inputIgst: 0,
    paidPurchases: 0,
    paidCount: 0,
    unpaidPurchases: 0,
    unpaidCount: 0,
    totalSales: 0,
    salesCount: 0,
  });
  const [loadingMetrics, setLoadingMetrics] = useState<boolean>(false);

  const [selectedVoucher, setSelectedVoucher] = useState<any | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [zoomLevel, setZoomLevel] = useState<number>(100);

  // Edit Modal State
  const [editingVoucher, setEditingVoucher] = useState<any | null>(null);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  
  const [deleteConfirmParams, setDeleteConfirmParams] = useState<{ id: string, number: string } | null>(null);

  const activeDateRange = useMemo(() => {
    return computePeriodDateRange(periodPreset, activeFY, customStart, customEnd);
  }, [periodPreset, activeFY, customStart, customEnd]);

  const calculatePeriodMetrics = useCallback(async (targetCompanyId?: string) => {
    let companyId = targetCompanyId || activeCompanyId;
    if (!companyId && typeof window !== "undefined") {
      companyId = localStorage.getItem("vouch_active_company_id");
    }
    if (!companyId) return;

    setLoadingMetrics(true);
    try {
      const { startDate, endDate } = activeDateRange;
      const token = getAccessToken();
      let serverSummaryFetched = false;

      if (token) {
        try {
          const headers = { Authorization: `Bearer ${token}`, "X-Company-ID": companyId };
          const params = new URLSearchParams();
          if (startDate) params.append("start_date", startDate);
          if (endDate) params.append("end_date", endDate);
          if (activeFY?.id) params.append("financial_year_id", activeFY.id);

          const res = await axios.get(
            `${API_BASE_URL}/api/v1/accounting/reports/purchase-period-summary/${companyId}/?${params.toString()}`,
            { headers, timeout: 6000 }
          );

          if (res.data?.success && res.data?.data) {
            const d = res.data.data;
            setPeriodMetrics({
              totalPurchases: Number(d.total_purchases) || 0,
              purchaseCount: Number(d.purchase_count) || 0,
              totalInputGst: Number(d.total_input_gst) || 0,
              inputCgst: Number(d.input_cgst) || 0,
              inputSgst: Number(d.input_sgst) || 0,
              inputIgst: Number(d.input_igst) || 0,
              paidPurchases: Number(d.paid_purchases) || 0,
              paidCount: Number(d.paid_count) || 0,
              unpaidPurchases: Number(d.unpaid_purchases) || 0,
              unpaidCount: Number(d.unpaid_count) || 0,
              totalSales: Number(d.total_sales) || 0,
              salesCount: Number(d.sales_count) || 0,
            });
            serverSummaryFetched = true;
          }
        } catch (serverErr) {
          console.warn("[PurchaseOverview] Server summary fetch failed, falling back to local calculation:", serverErr);
        }
      }

      if (!serverSummaryFetched) {
        let vouchers = await offlineDb.syncedVouchers
          .where("companyId")
          .equals(companyId)
          .toArray();

        let salesTot = 0;
        let salesCnt = 0;
        let purchasesTot = 0;
        let purchasesCnt = 0;
        let paidPurchases = 0;
        let paidCnt = 0;

        for (const v of vouchers) {
          const st = String(v.status || "").toUpperCase();
          if (st === "CANCELLED" || st === "REVERSED" || st === "SUPERSEDED") continue;

          const vDate = v.voucherDate || (v as any).voucher_date || (v as any).date || "";
          if (startDate && vDate < startDate) continue;
          if (endDate && vDate > endDate) continue;

          const vType = String(v.voucherType || (v as any).voucher_type || (v as any).type || "").toUpperCase();
          const tot = Number(v.totalAmount !== undefined && v.totalAmount !== null ? v.totalAmount : (v as any).total_amount) || 0;
          const paid = Number(v.paidAmount !== undefined && v.paidAmount !== null ? v.paidAmount : (v as any).paid_amount) || 0;

          if (vType === "SALES") {
            salesTot += tot;
            salesCnt += 1;
          } else if (vType === "PURCHASE") {
            purchasesTot += tot;
            purchasesCnt += 1;
            paidPurchases += paid;
            if (paid > 0) paidCnt += 1;
          }
        }

        const estTax = Math.round(purchasesTot * 0.18 / 1.18 * 100) / 100;

        setPeriodMetrics({
          totalPurchases: Math.round(purchasesTot * 100) / 100,
          purchaseCount: purchasesCnt,
          totalInputGst: estTax,
          inputCgst: Math.round(estTax / 2 * 100) / 100,
          inputSgst: Math.round(estTax / 2 * 100) / 100,
          inputIgst: 0,
          paidPurchases: Math.round(paidPurchases * 100) / 100,
          paidCount: paidCnt,
          unpaidPurchases: Math.round(Math.max(0, purchasesTot - paidPurchases) * 100) / 100,
          unpaidCount: Math.max(0, purchasesCnt - paidCnt),
          totalSales: Math.round(salesTot * 100) / 100,
          salesCount: salesCnt,
        });
      }
    } catch (err) {
      console.error("calculatePeriodMetrics error:", err);
    } finally {
      setLoadingMetrics(false);
    }
  }, [activeCompanyId, activeDateRange, activeFY]);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }
    fetchInvoices(1);
    calculatePeriodMetrics();
  }, [router, activeCompanyId, activeFY?.id, filterTableByPeriod, activeDateRange.startDate, activeDateRange.endDate]);

  const fetchInvoices = async (targetPage: number = page) => {
    setLoading(true);
    setFetchError(null);

    try {
      let companyId = activeCompanyId;
      if (!companyId && typeof window !== "undefined") {
        companyId = localStorage.getItem("vouch_active_company_id");
      }
      if (!companyId) {
        const token = getAccessToken();
        const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, {
          headers: { Authorization: `Bearer ${token}` },
          timeout: 8000,
        });
        const list = Array.isArray(compRes.data) ? compRes.data : compRes.data?.data || [];
        companyId = list[0]?.id;
      }

      if (!companyId) {
        setFetchError("No company found for the current user.");
        return;
      }

      const dateFilters = filterTableByPeriod
        ? {
            startDate: activeDateRange.startDate,
            endDate: activeDateRange.endDate,
            financialYearId: undefined,
          }
        : {
            financialYearId: activeFY?.id,
            startDate: activeFY?.start_date,
            endDate: activeFY?.end_date,
          };

      const result = await vouchersRepository.getPurchaseInvoices(companyId, {
        page: targetPage,
        pageSize,
        status: "ACTIVE",
        ...dateFilters,
      });

      setInvoices(result.data);
      setPagination({
        page: result.page,
        limit: result.pageSize,
        offset: result.offset ?? (targetPage - 1) * pageSize,
        total_count: result.totalCount,
        total_pages: result.totalPages,
        has_more: result.hasMore ?? (targetPage < result.totalPages),
      });
      setPage(targetPage);
      setFetchError(null);

      // Background incremental sync to ensure any server-side cancellations/reversals update IndexedDB
      pullIncrementalChanges(companyId).then((pullRes) => {
        if (pullRes.success && pullRes.totalRecords > 0) {
          vouchersRepository.getPurchaseInvoices(companyId, {
            page: targetPage,
            pageSize,
            status: "ACTIVE",
            ...dateFilters,
          }).then((fresh) => {
            setInvoices(fresh.data);
            setPagination({
              page: fresh.page,
              limit: fresh.pageSize,
              offset: fresh.offset ?? (targetPage - 1) * pageSize,
              total_count: fresh.totalCount,
              total_pages: fresh.totalPages,
              has_more: fresh.hasMore ?? (targetPage < fresh.totalPages),
            });
            calculatePeriodMetrics(companyId);
          });
        }
      }).catch(() => {});
    } catch (err: any) {
      console.error("fetchInvoices error:", err);
      const errorMsg = err.response?.data?.error || err.response?.data?.message || err.message || "Failed to load purchase invoices";
      setFetchError(errorMsg);
      toast.error("Failed to load invoices", errorMsg);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenVoucherDetail = async (voucherId: string) => {
    setLoadingDetail(true);
    setSelectedVoucher(null);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.get(`${API_BASE_URL}/api/vouchers/${voucherId}/`, { headers });
      if (res.data.success) {
        const vData = res.data.data;
        if (vData.has_attachment && !vData.attachment_data) {
          try {
            const attRes = await axios.get(`${API_BASE_URL}/api/vouchers/${voucherId}/attachment/`, { headers });
            if (attRes.data?.success && attRes.data?.attachment_data) {
              vData.attachment_data = attRes.data.attachment_data;
              vData.attachment_mime = attRes.data.attachment_mime || vData.attachment_mime;
            }
          } catch (attErr) {
            console.warn("Could not load on-demand attachment:", attErr);
          }
        }
        setSelectedVoucher(vData);
      }
    } catch (err) {
      console.error("Failed to load voucher detail:", err);
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleStartEdit = (inv: any) => {
    setEditingVoucher(inv);
    setIsEditModalOpen(true);
  };

  const executeDelete = async (voucherId: string) => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.delete(`${API_BASE_URL}/api/vouchers/${voucherId}/`, { headers });

      if (res.data.success) {
        toast.success(res.data.message || `Invoice deleted and reversed successfully!`);
        setInvoices((prev) => prev.filter((i) => i.id !== voucherId));
        await vouchersRepository.deleteVoucher(voucherId);
        setDeleteConfirmParams(null);
        if (selectedVoucher?.id === voucherId) {
          setSelectedVoucher(null);
        }
      } else {
        toast.error("Failed to delete invoice", res.data.error);
      }
    } catch (err: any) {
      if (err.response?.status === 404) {
        setInvoices((prev) => prev.filter((i) => i.id !== voucherId));
        await vouchersRepository.deleteVoucher(voucherId);
        setDeleteConfirmParams(null);
        if (selectedVoucher?.id === voucherId) {
          setSelectedVoucher(null);
        }
        toast.success("Voucher cleaned up from local records.");
        return;
      }
      toast.error("Delete failed", err.response?.data?.error || err.message);
    }
  };

  const handleDeleteInvoice = (voucherId: string, voucherNumber: string) => {
    setDeleteConfirmParams({ id: voucherId, number: voucherNumber });
  };

  const [focusedIndex, setFocusedIndex] = useState<number>(-1);

  const scrollToInvoice = (index: number) => {
    if (index >= 0 && index < invoices.length) {
      const invId = invoices[index].id;
      const el = document.getElementById(`row-invoice-${invId}`);
      if (el) {
        el.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }
    }
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (isEditModalOpen || deleteConfirmParams !== null) return;

      const activeElement = document.activeElement;
      const isInputFocused = activeElement && (
        activeElement.tagName === "INPUT" ||
        activeElement.tagName === "TEXTAREA" ||
        activeElement.tagName === "SELECT"
      );
      if (isInputFocused) return;

      if (invoices.length === 0) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        setFocusedIndex(prev => {
          const next = prev < invoices.length - 1 ? prev + 1 : 0;
          scrollToInvoice(next);
          return next;
        });
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setFocusedIndex(prev => {
          const next = prev > 0 ? prev - 1 : invoices.length - 1;
          scrollToInvoice(next);
          return next;
        });
      } else if (e.key === "Home") {
        e.preventDefault();
        setFocusedIndex(0);
        scrollToInvoice(0);
      } else if (e.key === "End") {
        e.preventDefault();
        setFocusedIndex(invoices.length - 1);
        scrollToInvoice(invoices.length - 1);
      } else if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        // TALLY ALTER SHORTCUT: Ctrl + Enter opens the full Edit Invoice Modal!
        if (focusedIndex >= 0 && focusedIndex < invoices.length) {
          e.preventDefault();
          handleStartEdit(invoices[focusedIndex]);
        }
      } else if (e.key === "Enter") {
        // Enter views details of selected invoice
        if (focusedIndex >= 0 && focusedIndex < invoices.length) {
          e.preventDefault();
          handleOpenVoucherDetail(invoices[focusedIndex].id);
        }
      } else if (e.key.toLowerCase() === "e" && !e.ctrlKey && !e.metaKey) {
        if (focusedIndex >= 0 && focusedIndex < invoices.length) {
          e.preventDefault();
          handleStartEdit(invoices[focusedIndex]);
        }
      } else if ((e.altKey && e.key.toLowerCase() === "d") || e.key === "Delete") {
        if (focusedIndex >= 0 && focusedIndex < invoices.length) {
          e.preventDefault();
          const target = invoices[focusedIndex];
          handleDeleteInvoice(target.id, target.voucher_number);
        }
      } else if (e.key === "Escape") {
        if (selectedVoucher) {
          setSelectedVoucher(null);
        } else {
          setFocusedIndex(-1);
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [invoices, focusedIndex, isEditModalOpen, selectedVoucher]);

  return (
    <DashboardLayout>
      <div className="space-y-6 flex flex-col h-full pb-12">
        
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/40 pb-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">Purchase Invoices</h1>
            <p className="text-xs text-muted-foreground mt-1">Inward supplier bills and attached documents</p>
          </div>
          <Link
            href="/purchases/new"
            className="w-full sm:w-auto justify-center bg-primary hover:bg-primary/90 text-primary-foreground px-4 py-2.5 rounded-xl text-xs font-bold shadow-md shadow-primary/20 transition-all flex items-center gap-1.5"
          >
            <Plus className="w-4 h-4" />
            <span>Create / Scan Invoice</span>
            <kbd className="hidden sm:inline bg-primary-foreground/20 px-1.5 py-0.5 rounded text-[10px]">F9</kbd>
          </Link>
        </div>

        {/* Period Performance & Overview Section */}
        <div className="bg-card text-card-foreground rounded-2xl shadow-sm border border-border/40 p-4 sm:p-5 space-y-4">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 border-b border-border/40 pb-3">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-500">
                <Calendar className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <h2 className="text-base font-bold text-foreground">Period Performance &amp; Purchases Overview</h2>
                  <span className="text-[11px] bg-blue-500/10 text-blue-400 border border-blue-500/20 px-2 py-0.5 rounded-full font-medium">
                    {activeDateRange.formattedRange}
                  </span>
                  <Link
                    href="/sales"
                    className="text-[11px] bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 hover:border-emerald-500/40 px-2.5 py-0.5 rounded-full font-medium flex items-center gap-1 transition-all"
                    title="View Sales Invoices for this period"
                  >
                    <TrendingUp className="w-3 h-3" />
                    <span>Sales: ₹{periodMetrics.totalSales.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
                    <ArrowRight className="w-2.5 h-2.5 opacity-70" />
                  </Link>
                  {loadingMetrics && (
                    <RefreshCw className="w-3.5 h-3.5 text-muted-foreground animate-spin" />
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  Track inward purchases, Input GST (ITC), settled payments, and pending dues
                </p>
              </div>
            </div>

            {/* Period presets and table filter toggle */}
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-1 bg-muted/70 p-1 rounded-xl border border-border/50 text-xs overflow-x-auto">
                <button
                  type="button"
                  onClick={() => setPeriodPreset("ALL")}
                  className={`px-3 py-1 rounded-lg font-semibold transition-all cursor-pointer whitespace-nowrap ${
                    periodPreset === "ALL"
                      ? "bg-background text-foreground shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  Full FY
                </button>
                <button
                  type="button"
                  onClick={() => setPeriodPreset("THIS_MONTH")}
                  className={`px-3 py-1 rounded-lg font-semibold transition-all cursor-pointer whitespace-nowrap ${
                    periodPreset === "THIS_MONTH"
                      ? "bg-background text-foreground shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  This Month
                </button>
                <button
                  type="button"
                  onClick={() => setPeriodPreset("LAST_MONTH")}
                  className={`px-3 py-1 rounded-lg font-semibold transition-all cursor-pointer whitespace-nowrap ${
                    periodPreset === "LAST_MONTH"
                      ? "bg-background text-foreground shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  Last Month
                </button>
                <button
                  type="button"
                  onClick={() => setPeriodPreset("THIS_QUARTER")}
                  className={`px-3 py-1 rounded-lg font-semibold transition-all cursor-pointer whitespace-nowrap ${
                    periodPreset === "THIS_QUARTER"
                      ? "bg-background text-foreground shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  This Quarter
                </button>
                <button
                  type="button"
                  onClick={() => setPeriodPreset("TODAY")}
                  className={`px-3 py-1 rounded-lg font-semibold transition-all cursor-pointer whitespace-nowrap ${
                    periodPreset === "TODAY"
                      ? "bg-background text-foreground shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  Today
                </button>
                <button
                  type="button"
                  onClick={() => setPeriodPreset("CUSTOM")}
                  className={`px-3 py-1 rounded-lg font-semibold transition-all cursor-pointer whitespace-nowrap ${
                    periodPreset === "CUSTOM"
                      ? "bg-background text-foreground shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  Custom
                </button>
              </div>

              {/* Table filter sync switch */}
              <button
                type="button"
                onClick={() => setFilterTableByPeriod(!filterTableByPeriod)}
                className={`px-3 py-1.5 rounded-xl border text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
                  filterTableByPeriod
                    ? "bg-primary/10 text-primary border-primary/30 shadow-xs"
                    : "bg-muted/40 text-muted-foreground border-border/60 hover:text-foreground"
                }`}
                title="When enabled, the previous invoices list below will strictly show bills within this period"
              >
                <Filter className="w-3.5 h-3.5" />
                <span>Filter Table</span>
                <span className={`w-2 h-2 rounded-full ${filterTableByPeriod ? "bg-primary" : "bg-muted-foreground/40"}`} />
              </button>
            </div>
          </div>

          {/* Custom Date Picker row if CUSTOM selected */}
          {periodPreset === "CUSTOM" && (
            <div className="flex flex-wrap items-center gap-3 bg-muted/30 p-3 rounded-xl border border-border/40 text-xs">
              <span className="font-semibold text-muted-foreground">Select Date Range:</span>
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">From</span>
                <input
                  type="date"
                  value={customStart}
                  onChange={(e) => setCustomStart(e.target.value)}
                  className="bg-background border border-border rounded-lg px-2.5 py-1 text-xs text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary"
                />
              </div>
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">To</span>
                <input
                  type="date"
                  value={customEnd}
                  onChange={(e) => setCustomEnd(e.target.value)}
                  className="bg-background border border-border rounded-lg px-2.5 py-1 text-xs text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary"
                />
              </div>
              {(customStart || customEnd) && (
                <button
                  type="button"
                  onClick={() => {
                    setCustomStart("");
                    setCustomEnd("");
                  }}
                  className="text-xs text-muted-foreground hover:text-foreground underline cursor-pointer"
                >
                  Reset
                </button>
              )}
            </div>
          )}

          {/* 4 Summary Cards Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
            {/* Card 1: Total Purchases */}
            <div className="bg-muted/20 border border-blue-500/20 rounded-xl p-4 shadow-xs flex flex-col justify-between relative overflow-hidden group hover:border-blue-500/40 transition-all">
              <div className="absolute top-0 right-0 w-24 h-24 bg-blue-500/5 rounded-bl-full pointer-events-none -mr-4 -mt-4" />
              <div className="flex items-center justify-between gap-2 mb-2">
                <div className="flex items-center gap-1.5 text-xs font-bold text-blue-500 tracking-wider uppercase">
                  <ShoppingCart className="w-3.5 h-3.5" />
                  <span>Total Purchases</span>
                </div>
                <span className="px-1.5 py-0.2 rounded text-[10px] font-bold bg-blue-500/10 text-blue-400 border border-blue-500/20">
                  Inward
                </span>
              </div>
              <div>
                <p className="text-2xl sm:text-3xl font-black text-foreground font-mono">
                  ₹{periodMetrics.totalPurchases.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </p>
                <div className="flex items-center justify-between text-[11px] text-muted-foreground mt-1.5 pt-1.5 border-t border-border/40 font-mono">
                  <span>{periodMetrics.purchaseCount} purchase bills</span>
                  <span>Avg: ₹{periodMetrics.purchaseCount > 0 ? Math.round(periodMetrics.totalPurchases / periodMetrics.purchaseCount).toLocaleString("en-IN") : "0"}</span>
                </div>
              </div>
            </div>

            {/* Card 2: Total Input GST */}
            <div className="bg-muted/20 border border-indigo-500/20 rounded-xl p-4 shadow-xs flex flex-col justify-between relative overflow-hidden group hover:border-indigo-500/40 transition-all">
              <div className="absolute top-0 right-0 w-24 h-24 bg-indigo-500/5 rounded-bl-full pointer-events-none -mr-4 -mt-4" />
              <div className="flex items-center justify-between gap-2 mb-2">
                <div className="flex items-center gap-1.5 text-xs font-bold text-indigo-500 dark:text-indigo-400 tracking-wider uppercase">
                  <FileText className="w-3.5 h-3.5" />
                  <span>Total Input GST</span>
                </div>
                <span className="px-1.5 py-0.2 rounded text-[10px] font-bold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                  ITC Claimable
                </span>
              </div>
              <div>
                <p className="text-2xl sm:text-3xl font-black text-indigo-500 dark:text-indigo-400 font-mono">
                  ₹{periodMetrics.totalInputGst.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </p>
                <div className="flex items-center justify-between text-[11px] text-muted-foreground mt-1.5 pt-1.5 border-t border-border/40 font-mono">
                  <span>CGST: ₹{periodMetrics.inputCgst.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
                  <span>SGST: ₹{periodMetrics.inputSgst.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
                  {periodMetrics.inputIgst > 0 && (
                    <span className="hidden xl:inline">IGST: ₹{periodMetrics.inputIgst.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
                  )}
                </div>
              </div>
            </div>

            {/* Card 3: Paid Amount */}
            <div className="bg-muted/20 border border-emerald-500/20 rounded-xl p-4 shadow-xs flex flex-col justify-between relative overflow-hidden group hover:border-emerald-500/40 transition-all">
              <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-500/5 rounded-bl-full pointer-events-none -mr-4 -mt-4" />
              <div className="flex items-center justify-between gap-2 mb-2">
                <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-500 tracking-wider uppercase">
                  <CheckCircle className="w-3.5 h-3.5" />
                  <span>Paid Amount</span>
                </div>
                <span className="px-1.5 py-0.2 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  Settled
                </span>
              </div>
              <div>
                <p className="text-2xl sm:text-3xl font-black text-emerald-500 dark:text-emerald-400 font-mono">
                  ₹{periodMetrics.paidPurchases.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </p>
                <div className="flex items-center justify-between text-[11px] text-muted-foreground mt-1.5 pt-1.5 border-t border-border/40 font-mono">
                  <span>{periodMetrics.paidCount} bills settled</span>
                  <span>{periodMetrics.totalPurchases > 0 ? Math.round((periodMetrics.paidPurchases / periodMetrics.totalPurchases) * 100) : 0}% cleared</span>
                </div>
              </div>
            </div>

            {/* Card 4: Yet to Pay */}
            <div className="bg-muted/20 border border-amber-500/20 rounded-xl p-4 shadow-xs flex flex-col justify-between relative overflow-hidden group hover:border-amber-500/40 transition-all">
              <div className="absolute top-0 right-0 w-24 h-24 bg-amber-500/5 rounded-bl-full pointer-events-none -mr-4 -mt-4" />
              <div className="flex items-center justify-between gap-2 mb-2">
                <div className="flex items-center gap-1.5 text-xs font-bold text-amber-500 tracking-wider uppercase">
                  <Clock className="w-3.5 h-3.5" />
                  <span>Yet to Pay</span>
                </div>
                <span className="px-1.5 py-0.2 rounded text-[10px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                  Pending Due
                </span>
              </div>
              <div>
                <p className="text-2xl sm:text-3xl font-black text-amber-500 dark:text-amber-400 font-mono">
                  ₹{periodMetrics.unpaidPurchases.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </p>
                <div className="flex items-center justify-between text-[11px] text-muted-foreground mt-1.5 pt-1.5 border-t border-border/40 font-mono">
                  <span>{periodMetrics.unpaidCount} bills due</span>
                  <span>To Suppliers</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Invoices Table Card */}
        <div className="bg-card text-card-foreground rounded-2xl shadow-sm border border-border/40 flex-1 overflow-hidden flex flex-col">
          <div className="px-4 sm:px-5 py-3.5 border-b border-border/70 bg-muted/20 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Previous Invoices</span>
              {filterTableByPeriod && (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-primary/10 text-primary border border-primary/20">
                  Filtered: {activeDateRange.formattedRange}
                </span>
              )}
            </div>
            <span className="text-xs text-muted-foreground hidden sm:inline">Click any row to inspect original bill &amp; line items</span>
          </div>

          {loading ? (
            <div className="flex items-center justify-center p-16 text-muted-foreground text-sm">
              Loading invoices...
            </div>
          ) : fetchError && invoices.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-16 text-center bg-card">
              <div className="w-16 h-16 rounded-2xl bg-destructive/10 text-destructive flex items-center justify-center mb-3 border border-destructive/20">
                <AlertCircle className="w-8 h-8" />
              </div>
              <h3 className="text-lg font-bold mb-1 text-foreground">Unable to Load Invoices</h3>
              <p className="text-muted-foreground max-w-md mx-auto mb-5 text-xs font-mono">
                {fetchError}
              </p>
              <button
                type="button"
                onClick={() => fetchInvoices(page)}
                className="px-4 py-2 bg-primary text-primary-foreground hover:bg-primary/90 rounded-xl text-xs font-bold shadow-sm flex items-center gap-1.5 cursor-pointer transition-all"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Retry Connection</span>
              </button>
            </div>
          ) : invoices.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-16 text-center bg-card">
              <div className="w-16 h-16 rounded-2xl bg-muted/60 text-muted-foreground flex items-center justify-center mb-3">
                <FileText className="w-8 h-8" />
              </div>
              <h3 className="text-xl font-bold mb-1">No Purchase Invoices Yet</h3>
              <p className="text-muted-foreground max-w-md mx-auto mb-6 text-sm">
                Upload your first supplier bill to automatically extract data and store attached documents.
              </p>
              <Link
                href="/purchases/new"
                className="bg-primary hover:bg-primary/90 text-primary-foreground px-5 py-2.5 rounded-xl shadow-md shadow-primary/20 font-bold text-xs flex items-center gap-1.5"
              >
                <Plus className="w-4 h-4" />
                <span>Scan First Invoice</span>
              </Link>
            </div>
          ) : (
            <div className="flex-1 w-full overflow-auto">
              {/* Mobile Card List (< md) */}
              <div className="block md:hidden divide-y divide-border/40">
                {invoices.map((inv, idx) => (
                  <div
                    key={inv.id}
                    onClick={() => {
                      setFocusedIndex(idx);
                      handleOpenVoucherDetail(inv.id);
                    }}
                    className="p-4 space-y-2.5 cursor-pointer hover:bg-muted/10 active:bg-muted/20 transition-colors"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-foreground text-sm">{inv.voucher_number}</span>
                        {inv.has_attachment && (
                          <span className="px-1.5 py-0.5 bg-blue-500/15 text-blue-400 rounded text-[10px] font-bold border border-blue-500/30">
                            📎 Doc
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5">
                        {inv.payment_status === 'PAID' ? (
                          <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono">
                            PAID
                          </span>
                        ) : inv.payment_status === 'PARTIAL' ? (
                          <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 font-mono">
                            PARTIAL
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20 font-mono">
                            UNPAID
                          </span>
                        )}
                        {inv.syncStatus === 'SYNC_FAILED' ? (
                          <div className="flex items-center gap-1">
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold rounded-full bg-rose-500/10 text-rose-500 border border-rose-500/30" title={inv.errorMessage || "Action requires attention"}>
                              <AlertTriangle className="w-2.5 h-2.5" />
                              Sync failed
                            </span>
                            {inv.dexieId && (
                              <button
                                type="button"
                                onClick={async (e) => {
                                  e.stopPropagation();
                                  await retryFailedVoucher(inv.dexieId);
                                  fetchInvoices(page);
                                }}
                                className="p-0.5 hover:bg-rose-500/20 text-rose-400 rounded"
                                title="Retry sync now"
                              >
                                <RefreshCw className="w-2.5 h-2.5" />
                              </button>
                            )}
                          </div>
                        ) : inv.syncStatus === 'OFFLINE_PENDING' || inv.isOffline || inv.status === 'PENDING_SYNC' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold rounded-full bg-amber-500/10 text-amber-500 border border-amber-500/30" title="Saved locally on this device. Will sync automatically when connected.">
                            <CloudOff className="w-2.5 h-2.5" />
                            Saved offline — waiting to sync
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold rounded-full bg-emerald-500/10 text-emerald-500 border border-emerald-500/20" title="Authoritatively synced and posted on server">
                            <CheckCircle className="w-2.5 h-2.5" />
                            Saved &amp; synced
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium text-foreground truncate max-w-[200px]">{inv.party_name}</span>
                      <span className="text-muted-foreground font-mono">{inv.date}</span>
                    </div>

                    <div className="flex items-center justify-between pt-1">
                      <div className="flex flex-col items-start font-mono">
                        <span className="font-bold text-base text-foreground">
                          ₹{(() => {
                            const raw = parseFloat(inv.total_amount) || 0;
                            const rounded = Math.abs(raw % 1) > 0 ? (raw % 1 < 0.5 ? Math.floor(raw) : Math.ceil(raw)) : raw;
                            return rounded.toLocaleString("en-IN", { minimumFractionDigits: 2 });
                          })()}
                        </span>
                        {(() => {
                          const ro = inv.round_off !== undefined && inv.round_off !== null && inv.round_off !== 0
                            ? Number(inv.round_off)
                            : (inv.total_amount % 1 !== 0 ? Number((Math.round(inv.total_amount) - inv.total_amount).toFixed(2)) : 0);
                          if (Math.abs(ro) >= 0.005) {
                            return (
                              <span className={`text-[10px] font-semibold ${
                                ro < 0 ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400"
                              }`}>
                                R/O: {ro > 0 ? `+₹${ro.toFixed(2)}` : `-₹${Math.abs(ro).toFixed(2)}`}
                              </span>
                            );
                          }
                          return null;
                        })()}
                      </div>
                      <div className="flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => handleOpenVoucherDetail(inv.id)}
                          className="p-2 bg-muted/60 hover:bg-muted text-foreground rounded-lg text-xs font-semibold border border-border/70 transition-colors cursor-pointer"
                          title="View Document"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleStartEdit(inv)}
                          className="p-2 bg-blue-600/15 hover:bg-blue-600/25 text-blue-400 rounded-lg text-xs font-semibold border border-blue-500/30 transition-colors cursor-pointer"
                          title="Edit Invoice"
                        >
                          <Edit2 className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDeleteInvoice(inv.id, inv.voucher_number)}
                          className="p-2 bg-rose-600/15 hover:bg-rose-600/25 text-rose-400 rounded-lg text-xs font-semibold border border-rose-500/30 transition-colors cursor-pointer"
                          title="Delete Invoice"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Desktop Table (>= md) */}
              <div className="hidden md:block">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-border/70 bg-muted/30 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    <th className="p-4">Invoice No.</th>
                    <th className="p-4">Date</th>
                    <th className="p-4">Supplier Party</th>
                    <th className="p-4 text-right">Total Amount</th>
                    <th className="p-4 text-center">Payment</th>
                    <th className="p-4 text-center">Status</th>
                    <th className="p-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40 text-xs">
                  {invoices.map((inv, idx) => {
                    const isFocused = focusedIndex === idx;
                    return (
                      <tr
                        id={`row-invoice-${inv.id}`}
                        key={inv.id}
                        onClick={() => {
                          setFocusedIndex(idx);
                          handleOpenVoucherDetail(inv.id);
                        }}
                        className={`transition-all duration-150 cursor-pointer group ${
                          isFocused
                            ? "bg-blue-500/10 ring-2 ring-inset ring-blue-500/60 border-l-4 border-l-blue-500"
                            : "hover:bg-muted/20"
                        }`}
                      >
                      {/* Invoice No */}
                      <td className="p-4 font-mono font-medium text-foreground flex items-center gap-2">
                        <span className="font-bold text-sm">{inv.voucher_number}</span>
                        {inv.has_attachment && (
                          <span className="px-2 py-0.5 bg-blue-500/15 text-blue-400 rounded text-xs font-semibold border border-blue-500/30">
                            📎 Doc
                          </span>
                        )}
                      </td>

                      {/* Date */}
                      <td className="p-4 text-muted-foreground font-mono">{inv.date}</td>

                      {/* Party */}
                      <td className="p-4 text-foreground font-semibold text-sm">{inv.party_name}</td>

                      {/* Amount */}
                      <td className="p-4 font-bold text-foreground font-mono tabular-nums text-right text-sm">
                        <div>
                          ₹{(() => {
                            const raw = parseFloat(inv.total_amount) || 0;
                            const rounded = Math.abs(raw % 1) > 0 ? (raw % 1 < 0.5 ? Math.floor(raw) : Math.ceil(raw)) : raw;
                            return rounded.toLocaleString("en-IN", { minimumFractionDigits: 2 });
                          })()}
                        </div>
                        {(() => {
                          const ro = inv.round_off !== undefined && inv.round_off !== null && inv.round_off !== 0
                            ? Number(inv.round_off)
                            : (inv.total_amount % 1 !== 0 ? Number((Math.round(inv.total_amount) - inv.total_amount).toFixed(2)) : 0);
                          if (Math.abs(ro) >= 0.005) {
                            return (
                              <div className={`text-[11px] font-semibold font-mono flex items-center justify-end gap-1 ${
                                ro < 0 ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400"
                              }`}>
                                <span className="text-[10px] text-muted-foreground font-sans">R/O:</span>
                                <span>{ro > 0 ? `+₹${ro.toFixed(2)}` : `-₹${Math.abs(ro).toFixed(2)}`}</span>
                              </div>
                            );
                          }
                          return null;
                        })()}
                      </td>

                      {/* Payment */}
                      <td className="p-4 text-center">
                        {inv.payment_status === 'PAID' ? (
                          <span className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono">
                            PAID
                          </span>
                        ) : inv.payment_status === 'PARTIAL' ? (
                          <span
                            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 font-mono"
                            title={`Paid: ₹${inv.paid_amount || 0}`}
                          >
                            PARTIAL (₹{Number(inv.paid_amount || 0).toLocaleString('en-IN')})
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20 font-mono">
                            UNPAID
                          </span>
                        )}
                      </td>

                      {/* Status */}
                      <td className="p-4 text-center">
                        {inv.syncStatus === 'SYNC_FAILED' ? (
                          <div className="flex items-center gap-1.5 justify-center">
                            <span
                              className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-full bg-rose-500/10 text-rose-500 border border-rose-500/30"
                              title={inv.errorMessage || "Action requires attention"}
                            >
                              <AlertTriangle className="w-3.5 h-3.5" />
                              Sync failed — action requires attention
                            </span>
                            {inv.dexieId && (
                              <button
                                type="button"
                                onClick={async (e) => {
                                  e.stopPropagation();
                                  await retryFailedVoucher(inv.dexieId);
                                  fetchInvoices(page);
                                }}
                                className="p-1 hover:bg-rose-500/20 text-rose-400 rounded transition-colors cursor-pointer"
                                title="Retry sync now"
                              >
                                <RefreshCw className="w-3.5 h-3.5" />
                              </button>
                            )}
                          </div>
                        ) : inv.syncStatus === 'OFFLINE_PENDING' || inv.isOffline || inv.status === 'PENDING_SYNC' ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-full bg-amber-500/10 text-amber-500 border border-amber-500/30" title="Saved locally on this device. Will sync automatically when connected.">
                            <CloudOff className="w-3.5 h-3.5" />
                            Saved offline — waiting to sync
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-500/10 text-emerald-500 border border-emerald-500/20" title="Authoritatively synced and posted on server">
                            <CheckCircle className="w-3.5 h-3.5" />
                            Saved &amp; synced
                          </span>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="p-4 text-right">
                        <div className="flex items-center justify-end gap-2" onClick={(e) => e.stopPropagation()}>
                          <button
                            onClick={() => handleOpenVoucherDetail(inv.id)}
                            className="px-3 py-1.5 bg-muted/60 hover:bg-muted text-foreground rounded-lg text-xs font-semibold border border-border transition-colors flex items-center gap-1.5 cursor-pointer min-h-[36px]"
                            title="View Document"
                          >
                            <Eye className="w-3.5 h-3.5" />
                            <span>View</span>
                          </button>
                          
                          <button
                            onClick={() => handleStartEdit(inv)}
                            className="px-3 py-1.5 bg-blue-600/15 hover:bg-blue-600/25 text-blue-400 rounded-lg text-xs font-semibold border border-blue-500/30 transition-colors flex items-center gap-1.5 cursor-pointer min-h-[36px]"
                            title="Edit Invoice"
                          >
                            <Edit2 className="w-3.5 h-3.5" />
                            <span>Edit</span>
                          </button>

                          <button
                            onClick={() => handleDeleteInvoice(inv.id, inv.voucher_number)}
                            className="px-3 py-1.5 bg-rose-600/15 hover:bg-rose-600/25 text-rose-400 rounded-lg text-xs font-semibold border border-rose-500/30 transition-colors flex items-center gap-1.5 cursor-pointer min-h-[36px]"
                            title="Delete Invoice & Reverse Stock"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                            <span>Delete</span>
                          </button>
                        </div>
                      </td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
              </div>

              {/* Pagination Controls */}
              {pagination && pagination.total_count > 0 && (
                <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-4 py-3 border-t border-border/60 bg-muted/20 text-xs text-muted-foreground">
                  <div className="font-mono">
                    Showing <span className="font-semibold text-foreground">{pagination.total_count === 0 ? 0 : ((pagination.offset ?? (page - 1) * pageSize) + 1)}</span> to{' '}
                    <span className="font-semibold text-foreground">
                      {Math.min((pagination.offset ?? (page - 1) * pageSize) + (pagination.limit ?? pageSize), pagination.total_count)}
                    </span>{' '}
                    of <span className="font-semibold text-foreground">{pagination.total_count}</span> purchase invoices
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => fetchInvoices(page - 1)}
                      disabled={page <= 1 || loading}
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-border bg-card text-foreground hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer font-medium"
                    >
                      <ChevronLeft className="w-3.5 h-3.5" />
                      <span>Previous</span>
                    </button>

                    <div className="px-2.5 py-1 text-xs font-mono font-semibold text-foreground bg-muted rounded border border-border">
                      Page {page} of {pagination.total_pages || 1}
                    </div>

                    <button
                      type="button"
                      onClick={() => fetchInvoices(page + 1)}
                      disabled={page >= (pagination.total_pages || 1) || loading}
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-border bg-card text-foreground hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer font-medium"
                    >
                      <span>Next</span>
                      <ChevronRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              )}

              {/* Keyboard Shortcuts Hint Bar */}
              <div className="p-3 border-t border-border/60 bg-muted/20 hidden sm:flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs text-muted-foreground">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="flex items-center gap-1">
                    <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">↑</kbd>
                    <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">↓</kbd>
                    <span className="text-[11px]">Navigate</span>
                  </span>
                  <span>•</span>
                  <span className="flex items-center gap-1">
                    <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">Ctrl</kbd>
                    <span>+</span>
                    <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">Enter</kbd>
                    <span className="text-[11px]">Edit Invoice (Tally Alter)</span>
                  </span>
                  <span>•</span>
                  <span className="flex items-center gap-1">
                    <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">Enter</kbd>
                    <span className="text-[11px]">View Bill</span>
                  </span>
                  <span>•</span>
                  <span className="flex items-center gap-1">
                    <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">Alt</kbd>
                    <span>+</span>
                    <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">D</kbd>
                    <span className="text-[11px]">Delete</span>
                  </span>
                </div>
                {focusedIndex >= 0 && (
                  <span className="font-mono text-blue-400 font-semibold text-[11px]">
                    Invoice {focusedIndex + 1} of {invoices.length} selected
                  </span>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Voucher Detail & Document Viewer Modal */}
        {(selectedVoucher || loadingDetail) && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-xs p-4 animate-in fade-in">
            <div className="w-full max-w-5xl bg-card border border-border/40 rounded-2xl shadow-2xl overflow-hidden flex flex-col text-foreground max-h-[90vh]">
              
              {/* Modal Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-border/70 bg-muted/20">
                <div className="flex items-center gap-3">
                  <span className="text-xl">🧾</span>
                  <div>
                    <h3 className="font-bold text-base text-foreground">
                      Purchase Invoice #{selectedVoucher?.voucher_number || "..."}
                    </h3>
                    <p className="text-xs text-muted-foreground">
                      Party: {selectedVoucher?.party?.name || "N/A"} • Date: {selectedVoucher?.date}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {selectedVoucher && (
                    <>
                      <button
                        onClick={() => {
                          handleStartEdit(selectedVoucher);
                        }}
                        className="px-3 py-1.5 bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 border border-blue-500/30 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                        <span>Edit</span>
                      </button>

                      <button
                        onClick={() => {
                          handleDeleteInvoice(selectedVoucher.id, selectedVoucher.voucher_number);
                        }}
                        className="px-3 py-1.5 bg-rose-600/20 hover:bg-rose-600/30 text-rose-400 border border-rose-500/30 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                        <span>Delete</span>
                      </button>
                    </>
                  )}

                  <button
                    onClick={() => setSelectedVoucher(null)}
                    className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
                  >
                    ✕
                  </button>
                </div>
              </div>

              {/* Modal Body */}
              <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {loadingDetail ? (
                  <div className="flex items-center justify-center p-12 text-muted-foreground">
                    Loading voucher details & attached invoice...
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Left: Extracted Details & Items */}
                    <div className="space-y-4">
                      <div className="bg-muted/30 p-4 rounded-xl border border-border/70 space-y-2 text-xs">
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Supplier:</span>
                          <span className="font-bold text-foreground">{selectedVoucher?.party?.name}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">GSTIN:</span>
                          <span className="font-mono text-muted-foreground">{selectedVoucher?.party?.gstin || "Unregistered"}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Invoice Number:</span>
                          <span className="font-mono text-foreground">{selectedVoucher?.voucher_number}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Date:</span>
                          <span className="font-mono text-foreground">{selectedVoucher?.date}</span>
                        </div>
                        {(() => {
                          const vItemsTotal = (selectedVoucher?.items || []).reduce((sum: number, it: any) => sum + (parseFloat(it.total_amount) || 0), 0);
                          const vRoundOff = (parseFloat(selectedVoucher?.total_amount) || 0) - vItemsTotal;
                          if (Math.abs(vRoundOff) >= 0.005) {
                            return (
                              <div className="flex justify-between text-muted-foreground">
                                <span>Round Off:</span>
                                <span className={vRoundOff < 0 ? "text-emerald-400 font-mono" : "text-amber-400 font-mono"}>
                                  {vRoundOff > 0 ? `+₹${vRoundOff.toFixed(2)}` : `-₹${Math.abs(vRoundOff).toFixed(2)}`}
                                </span>
                              </div>
                            );
                          }
                          return null;
                        })()}
                        <div className="flex justify-between border-t border-border/50 pt-2 font-bold text-sm">
                          <span>Total Amount:</span>
                          <span className="text-emerald-400 font-mono">
                            ₹ {parseFloat(selectedVoucher?.total_amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                          </span>
                        </div>
                      </div>

                      {/* Items Table */}
                      <div>
                        <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">
                          Line Items ({selectedVoucher?.items?.length || 0})
                        </h4>
                        <div className="border border-border/70 rounded-xl overflow-hidden">
                          <table className="w-full text-xs text-left">
                            <thead className="bg-muted/40 border-b border-border/60 text-muted-foreground">
                              <tr>
                                <th className="p-2.5">Item</th>
                                <th className="p-2.5 text-right">Qty</th>
                                <th className="p-2.5 text-right">Rate</th>
                                <th className="p-2.5 text-right">Total</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-border/30">
                              {selectedVoucher?.items?.map((item: any, idx: number) => (
                                <tr key={idx} className="hover:bg-muted/20">
                                  <td className="p-2.5">
                                    <p className="font-medium text-foreground">{item.product_name}</p>
                                    <p className="text-[10px] text-muted-foreground font-mono">HSN: {item.hsn_code || "—"}</p>
                                  </td>
                                  <td className="p-2.5 text-right font-mono">{item.quantity} {item.unit}</td>
                                  <td className="p-2.5 text-right font-mono">₹{parseFloat(item.rate).toFixed(2)}</td>
                                  <td className="p-2.5 text-right font-mono font-bold text-emerald-400">
                                    ₹{parseFloat(item.total_amount).toFixed(2)}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </div>

                    {/* Right: Document Preview */}
                    <div className="border border-border/70 rounded-xl overflow-hidden bg-muted/20 flex flex-col min-h-[400px]">
                      <div className="p-2.5 border-b border-border/60 bg-muted/40 flex items-center justify-between text-xs">
                        <span className="font-bold text-muted-foreground">Attached Document</span>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => setZoomLevel((z) => Math.max(50, z - 25))}
                            className="px-3 py-1 bg-muted rounded-lg text-xs font-semibold hover:bg-muted/80 border border-border min-h-[30px] min-w-[30px]"
                          >
                            -
                          </button>
                          <span className="text-xs font-mono font-semibold">{zoomLevel}%</span>
                          <button
                            onClick={() => setZoomLevel((z) => Math.min(200, z + 25))}
                            className="px-3 py-1 bg-muted rounded-lg text-xs font-semibold hover:bg-muted/80 border border-border min-h-[30px] min-w-[30px]"
                          >
                            +
                          </button>
                        </div>
                      </div>

                      <div className="flex-1 flex items-center justify-center p-4 overflow-auto">
                        {selectedVoucher?.attachment_data ? (
                          selectedVoucher.attachment_mime === "application/pdf" ? (
                            <iframe
                              src={selectedVoucher.attachment_data}
                              className="w-full h-full border-0 rounded-lg min-h-[450px]"
                              style={{ transform: `scale(${zoomLevel / 100})`, transformOrigin: "top center" }}
                              title="Original Invoice PDF"
                            />
                          ) : (
                            <img
                              src={selectedVoucher.attachment_data}
                              alt="Attached Invoice"
                              className="max-w-full max-h-[500px] object-contain rounded-lg shadow-sm"
                              style={{ transform: `scale(${zoomLevel / 100})`, transformOrigin: "center center" }}
                            />
                          )
                        ) : (
                          <div className="text-center p-8 text-muted-foreground">
                            <span className="text-3xl block mb-2">📄</span>
                            <p className="text-xs">No attachment stored for this voucher.</p>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Edit Modal */}
        <EditPurchaseInvoiceModal
          isOpen={isEditModalOpen}
          onClose={() => setIsEditModalOpen(false)}
          voucher={editingVoucher}
          onUpdateSuccess={fetchInvoices}
        />

        {/* Delete Confirm Modal */}
        <ConfirmModal
          isOpen={deleteConfirmParams !== null}
          onClose={() => setDeleteConfirmParams(null)}
          onConfirm={() => deleteConfirmParams && executeDelete(deleteConfirmParams.id)}
          title="Delete Invoice"
          description={
            <>
              Are you sure you want to delete purchase invoice <span className="text-foreground font-semibold">#{deleteConfirmParams?.number}</span>? 
              This will reverse the stock impact and accounting balances.
            </>
          }
          confirmText="Delete & Reverse"
          cancelText="Cancel"
          variant="danger"
        />
      </div>
    </DashboardLayout>
  );
}
