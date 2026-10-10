"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState, useMemo, useCallback } from 'react';
import axios from 'axios';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import { useToast } from '@/context/ToastContext';
import { useCompany } from '@/context/CompanyContext';
import { useFinancialYear } from '@/context/FinancialYearContext';
import { useAccountingPeriod } from '@/context/PeriodContext';
import EditSalesInvoiceModal from '@/components/modals/EditSalesInvoiceModal';
import ConfirmModal from '@/components/modals/ConfirmModal';
import EWayBillModal from '@/components/gst/EWayBillModal';
import { 
  Edit2, 
  Trash2, 
  Printer, 
  Plus, 
  ChevronLeft, 
  ChevronRight, 
  CloudOff, 
  CheckCircle, 
  AlertTriangle, 
  RefreshCw, 
  Truck, 
  Download, 
  MessageCircle, 
  Share2,
  Users,
  Building2,
  Search,
  Clock,
  FileText,
  ArrowUpRight,
  TrendingUp,
  ShoppingCart,
  Calendar,
  Filter,
  ArrowRight,
  Receipt
} from 'lucide-react';
import { offlineDb } from '@/lib/db/offlineDb';
import { PeriodPreset, computePeriodDateRange } from "@/utils/periodRanges";

import { retryFailedVoucher, pullIncrementalChanges } from '@/lib/sync/sync-worker';
import { vouchersRepository, ledgersRepository } from '@/lib/data';
import SemanticBalance from '@/components/accounting/SemanticBalance';

function SalesInvoiceListContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const filterParam = searchParams.get('filter');
  const tabParam = searchParams.get('tab');
  const { toast } = useToast();
  const { companyId: activeCompanyId } = useCompany();
  const { activeFY } = useFinancialYear();
  const { fromDate, toDate, displayPeriod, isCustomPeriod } = useAccountingPeriod();

  // View toggle: Invoices vs Customers (Debtors)
  const [activeTab, setActiveTab] = useState<'invoices' | 'customers'>(() => {
    return tabParam === 'customers' ? 'customers' : 'invoices';
  });

  // Payment status filter: ALL | UNPAID (Money to Collect) | PAID
  const [paymentFilter, setPaymentFilter] = useState<'ALL' | 'UNPAID' | 'PAID'>(() => {
    if (filterParam === 'unpaid') return 'UNPAID';
    if (filterParam === 'paid') return 'PAID';
    return 'ALL';
  });

  // Period Selection & Overview State
  const [periodPreset, setPeriodPreset] = useState<PeriodPreset>("ALL");
  const [customStart, setCustomStart] = useState<string>("");
  const [customEnd, setCustomEnd] = useState<string>("");
  const [filterTableByPeriod, setFilterTableByPeriod] = useState<boolean>(false);
  const [periodMetrics, setPeriodMetrics] = useState({
    totalSales: 0,
    salesCount: 0,
    totalOutputGst: 0,
    outputCgst: 0,
    outputSgst: 0,
    outputIgst: 0,
    paidSales: 0,
    paidCount: 0,
    unpaidSales: 0,
    unpaidCount: 0,
    totalPurchases: 0,
    purchaseCount: 0,
  });
  const [loadingMetrics, setLoadingMetrics] = useState<boolean>(false);

  const activeDateRange = useMemo(() => {
    if (periodPreset !== "ALL" || customStart || customEnd) {
      return computePeriodDateRange(periodPreset, activeFY, customStart, customEnd);
    }
    const sDate = fromDate || activeFY?.start_date || "";
    const eDate = toDate || activeFY?.end_date || "";
    return {
      startDate: sDate,
      endDate: eDate,
      formattedRange: isCustomPeriod
        ? displayPeriod
        : activeFY ? `FY ${activeFY.code}` : "All Period",
    };
  }, [periodPreset, activeFY, customStart, customEnd, fromDate, toDate, isCustomPeriod, displayPeriod]);

  const effectiveStartDate = (filterTableByPeriod && activeDateRange.startDate) ? activeDateRange.startDate : (fromDate || activeFY?.start_date);
  const effectiveEndDate = (filterTableByPeriod && activeDateRange.endDate) ? activeDateRange.endDate : (toDate || activeFY?.end_date);

  // Customers view state
  const [customers, setCustomers] = useState<any[]>([]);
  const [loadingCustomers, setLoadingCustomers] = useState<boolean>(false);
  const [customerSearch, setCustomerSearch] = useState<string>('');
  const [customerFilter, setCustomerFilter] = useState<'ALL' | 'UNPAID'>('UNPAID');

  useEffect(() => {
    if (filterParam === 'unpaid') {
      setPaymentFilter('UNPAID');
      setCustomerFilter('UNPAID');
      setActiveTab('invoices');
    } else if (filterParam === 'paid') {
      setPaymentFilter('PAID');
      setActiveTab('invoices');
    }
    if (tabParam === 'customers') {
      setActiveTab('customers');
    }
  }, [filterParam, tabParam]);

  const [invoices, setInvoices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState<number>(1);
  const [pagination, setPagination] = useState<any>(null);
  const pageSize = 50;

  // Edit and Delete state
  const [editingVoucher, setEditingVoucher] = useState<any | null>(null);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [deleteConfirmParams, setDeleteConfirmParams] = useState<{ id: string; number: string } | null>(null);

  // Status Filter state
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'ACTIVE' | 'SUPERSEDED'>('ALL');

  // E-Way Bill state
  const [ewayVoucher, setEwayVoucher] = useState<any | null>(null);
  const [isEwayModalOpen, setIsEwayModalOpen] = useState(false);

  const calculatePeriodMetrics = useCallback(async (targetCompanyId?: string) => {
    let companyId = targetCompanyId || activeCompanyId;
    if (!companyId && typeof window !== "undefined") {
      companyId = localStorage.getItem("vouch_active_company_id");
    }
    if (!companyId) return;

    setLoadingMetrics(true);
    try {
      const startDate = activeDateRange.startDate || fromDate || activeFY?.start_date;
      const endDate = activeDateRange.endDate || toDate || activeFY?.end_date;
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
            `${API_BASE_URL}/api/v1/accounting/reports/sales-period-summary/${companyId}/?${params.toString()}`,
            { headers, timeout: 6000 }
          );

          if (res.data?.success && res.data?.data) {
            const d = res.data.data;
            setPeriodMetrics({
              totalSales: Number(d.total_sales) || 0,
              salesCount: Number(d.sales_count) || 0,
              totalOutputGst: Number(d.total_output_gst) || 0,
              outputCgst: Number(d.output_cgst) || 0,
              outputSgst: Number(d.output_sgst) || 0,
              outputIgst: Number(d.output_igst) || 0,
              paidSales: Number(d.paid_sales) || 0,
              paidCount: Number(d.paid_count) || 0,
              unpaidSales: Number(d.unpaid_sales) || 0,
              unpaidCount: Number(d.unpaid_count) || 0,
              totalPurchases: Number(d.total_purchases) || 0,
              purchaseCount: Number(d.purchase_count) || 0,
            });
            serverSummaryFetched = true;
          }
        } catch (serverErr) {
          console.warn("[SalesOverview] Server summary fetch failed, falling back to local calculation:", serverErr);
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
        let paidSales = 0;
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
            paidSales += paid;
            if (paid > 0) paidCnt += 1;
          } else if (vType === "PURCHASE") {
            purchasesTot += tot;
            purchasesCnt += 1;
          }
        }

        const estTax = Math.round(salesTot * 0.18 / 1.18 * 100) / 100;

        setPeriodMetrics({
          totalSales: Math.round(salesTot * 100) / 100,
          salesCount: salesCnt,
          totalOutputGst: estTax,
          outputCgst: Math.round(estTax / 2 * 100) / 100,
          outputSgst: Math.round(estTax / 2 * 100) / 100,
          outputIgst: 0,
          paidSales: Math.round(paidSales * 100) / 100,
          paidCount: paidCnt,
          unpaidSales: Math.round(Math.max(0, salesTot - paidSales) * 100) / 100,
          unpaidCount: Math.max(0, salesCnt - paidCnt),
          totalPurchases: Math.round(purchasesTot * 100) / 100,
          purchaseCount: purchasesCnt,
        });
      }
    } catch (err) {
      console.error("calculatePeriodMetrics error:", err);
    } finally {
      setLoadingMetrics(false);
    }
  }, [activeCompanyId, activeDateRange, activeFY, fromDate, toDate]);

  const fetchCustomers = useCallback(async (targetCompanyId?: string) => {
    let companyId = targetCompanyId || activeCompanyId;
    if (!companyId && typeof window !== "undefined") {
      companyId = localStorage.getItem("vouch_active_company_id");
    }
    if (!companyId) return;

    setLoadingCustomers(true);
    try {
      const { data } = await ledgersRepository.getParties(companyId, {
        role: "CUSTOMER",
        financialYearId: activeFY?.id,
        startDate: effectiveStartDate,
        endDate: effectiveEndDate,
      });
      setCustomers(data || []);
    } catch (err) {
      console.error("fetchCustomers error:", err);
    } finally {
      setLoadingCustomers(false);
    }
  }, [activeCompanyId, activeFY?.id, effectiveStartDate, effectiveEndDate]);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login');
      return;
    }
    fetchInvoices(1);
    fetchCustomers();
    calculatePeriodMetrics();
  }, [router, activeCompanyId, statusFilter, activeFY?.id, filterTableByPeriod, activeDateRange.startDate, activeDateRange.endDate, fromDate, toDate, fetchCustomers, calculatePeriodMetrics]);

  const isCustomerReceivable = useCallback((p: any) => {
    const state = String(p.balance_state || "").toUpperCase();
    const dir = String(p.balance_direction || "").toUpperCase();
    const bal = Number(p.current_balance || 0);
    return state === "TO_COLLECT" || state === "DR" || dir === "RECEIVABLE" || (bal > 0 && p.normal_balance === "DEBIT");
  }, []);

  const customersToCollectCount = useMemo(() => {
    return customers.filter(isCustomerReceivable).length;
  }, [customers, isCustomerReceivable]);

  const totalReceivableAmount = useMemo(() => {
    return customers.reduce((sum, p) => {
      if (isCustomerReceivable(p)) {
        const amt = p.display_amount !== undefined ? Number(p.display_amount) : Math.abs(Number(p.current_balance || 0));
        return sum + (isNaN(amt) ? 0 : amt);
      }
      return sum;
    }, 0);
  }, [customers, isCustomerReceivable]);

  const filteredCustomers = useMemo(() => {
    return customers.filter((p) => {
      if (customerFilter === "UNPAID" && !isCustomerReceivable(p)) {
        return false;
      }
      if (customerSearch.trim()) {
        const q = customerSearch.toLowerCase();
        const matchName = p.name?.toLowerCase().includes(q);
        const matchGstin = p.gstin?.toLowerCase().includes(q);
        const matchPhone = p.phone?.toLowerCase().includes(q);
        return matchName || matchGstin || matchPhone;
      }
      return true;
    });
  }, [customers, customerFilter, customerSearch, isCustomerReceivable]);

  const { unpaidInvoicesCount, paidInvoicesCount } = useMemo(() => {
    let unpaid = 0;
    let paid = 0;
    for (const inv of invoices) {
      if (inv.payment_status === "PAID") {
        paid++;
      } else {
        unpaid++;
      }
    }
    return { unpaidInvoicesCount: unpaid, paidInvoicesCount: paid };
  }, [invoices]);

  const displayedInvoices = useMemo(() => {
    return invoices.filter((inv) => {
      const isUnpaid = inv.payment_status === "UNPAID" || inv.payment_status === "PARTIAL";
      if (paymentFilter === "UNPAID") return isUnpaid;
      if (paymentFilter === "PAID") return inv.payment_status === "PAID";
      return true;
    });
  }, [invoices, paymentFilter]);

  const fetchInvoices = async (targetPage: number = page) => {
    setLoading(true);
    try {
      let companyId = activeCompanyId;
      if (!companyId && typeof window !== 'undefined') {
        companyId = localStorage.getItem('vouch_active_company_id');
      }
      if (!companyId) {
        const token = getAccessToken();
        const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        const list = Array.isArray(compRes.data) ? compRes.data : (compRes.data.data || []);
        companyId = list[0]?.id;
      }

      if (companyId) {
        let result = await vouchersRepository.getSalesInvoices(companyId, {
          page: targetPage,
          pageSize,
          status: statusFilter,
          financialYearId: activeFY?.id,
          startDate: effectiveStartDate,
          endDate: effectiveEndDate,
        });

        // Network fallback if local IndexedDB is empty or out of sync
        if (!result.data || result.data.length === 0) {
          try {
            const token = getAccessToken();
            if (token) {
              const headers = { Authorization: `Bearer ${token}`, "X-Company-ID": companyId };
              const params = new URLSearchParams();
              params.append("type", "SALES");
              params.append("limit", "500");
              params.append("offset", String((targetPage - 1) * pageSize));
              if (activeFY?.id) params.append("financial_year_id", activeFY.id);
              if (effectiveStartDate) params.append("start_date", effectiveStartDate);
              if (effectiveEndDate) params.append("end_date", effectiveEndDate);

              const sRes = await axios.get(`${API_BASE_URL}/api/v1/accounting/vouchers/${companyId}/?${params.toString()}`, { headers, timeout: 6000 });
              if (sRes.data?.data && sRes.data.data.length > 0) {
                const serverList = sRes.data.data;
                const toPut: any[] = serverList.map((v: any) => ({
                  id: String(v.id),
                  companyId,
                  financialYearId: v.financial_year_id || v.financialYearId || null,
                  voucherType: String(v.voucherType || v.type || v.voucher_type || 'SALES').toUpperCase(),
                  voucherNumber: v.voucherNumber || v.voucher_number || '',
                  voucherDate: v.voucherDate || v.date || v.voucher_date || '',
                  referenceNumber: v.referenceNumber || v.reference_number || '',
                  partyLedgerId: v.partyLedgerId || v.party_ledger_id || null,
                  partyName: v.partyName || v.party_name || '',
                  status: v.status || 'POSTED',
                  totalAmount: Number(v.totalAmount ?? v.total_amount) || 0,
                  paymentStatus: v.paymentStatus || v.payment_status || 'UNPAID',
                  paidAmount: Number(v.paidAmount ?? v.paid_amount) || 0,
                  narration: v.narration || '',
                  serverUpdatedAt: Number(v.serverUpdatedAt || v.server_updated_at || Date.now()),
                }));
                await offlineDb.syncedVouchers.bulkPut(toPut);
                result = await vouchersRepository.getSalesInvoices(companyId, {
                  page: targetPage,
                  pageSize,
                  status: statusFilter,
                  financialYearId: activeFY?.id,
                  startDate: effectiveStartDate,
                  endDate: effectiveEndDate,
                });
              }
            }
          } catch (serverErr) {
            console.warn('Server fallback failed:', serverErr);
          }
        }

        const isGhostVoucher = (v: any) => {
          const vNum = String(v.voucher_number || v.voucherNumber || '').trim();
          const isUUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(vNum);
          return isUUID || vNum === String(v.id) || (v.status === 'CANCELLED' && Number(v.total_amount || v.totalAmount || 0) === 0 && !v.party_name && !v.partyName);
        };

        const cleanList = (result.data || []).filter((v: any) => !isGhostVoucher(v));
        setInvoices(cleanList);

        // Async purge any detected ghosts from IndexedDB
        const ghosts = (result.data || []).filter(isGhostVoucher);
        if (ghosts.length > 0) {
          await Promise.all(ghosts.map((g: any) => vouchersRepository.deleteVoucher(g.id)));
        }

        setPagination({
          page: result.page || targetPage,
          limit: result.pageSize || pageSize,
          offset: result.offset ?? (targetPage - 1) * pageSize,
          total_count: result.totalCount || 0,
          total_pages: result.totalPages || 1,
          has_more: result.hasMore ?? (targetPage < (result.totalPages || 1)),
        });
        setPage(targetPage);

        // Background incremental sync to ensure server cancellations/reversals sync to IndexedDB
        pullIncrementalChanges(companyId).then((pullRes) => {
          if (pullRes.success && pullRes.totalRecords > 0) {
            vouchersRepository.getSalesInvoices(companyId, {
              page: targetPage,
              pageSize,
              status: statusFilter,
              financialYearId: activeFY?.id,
              startDate: effectiveStartDate,
              endDate: effectiveEndDate,
            }).then((fresh) => {
              const cleanFresh = (fresh.data || []).filter((v: any) => !isGhostVoucher(v));
              setInvoices(cleanFresh);
              setPagination({
                page: fresh.page,
                limit: fresh.pageSize,
                offset: fresh.offset ?? (targetPage - 1) * pageSize,
                total_count: fresh.totalCount,
                total_pages: fresh.totalPages,
                has_more: fresh.hasMore ?? (targetPage < fresh.totalPages),
              });
            });
          }
        }).catch(() => {});
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleStartEdit = (inv: any) => {
    setEditingVoucher(inv);
    setIsEditModalOpen(true);
  };

  const handleDeleteInvoice = (voucherId: string, voucherNumber: string) => {
    setDeleteConfirmParams({ id: voucherId, number: voucherNumber });
  };

  const executeDelete = async (voucherId: string) => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.delete(`${API_BASE_URL}/api/vouchers/${voucherId}/`, { headers });

      if (res.data.success) {
        toast.success(res.data.message || 'Sales invoice deleted successfully!');
        setInvoices((prev) => prev.filter((i) => i.id !== voucherId));
        await vouchersRepository.deleteVoucher(voucherId);
        setDeleteConfirmParams(null);
      } else {
        toast.error('Failed to delete invoice', res.data.error);
      }
    } catch (err: any) {
      if (err.response?.status === 404) {
        setInvoices((prev) => prev.filter((i) => i.id !== voucherId));
        await vouchersRepository.deleteVoucher(voucherId);
        setDeleteConfirmParams(null);
        toast.success('Voucher cleaned up from local records.');
        return;
      }
      toast.error('Delete failed', err.response?.data?.error || err.message);
    }
  };

  const handleDownloadPdf = async (inv: any) => {
    if (inv.isOffline || String(inv.id).startsWith('offline_')) {
      toast.error('This invoice is saved offline and waiting to sync. Please sync before downloading the server PDF.');
      return;
    }
    try {
      toast.info('Downloading Tax Invoice PDF...');
      const token = getAccessToken();
      const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/vouchers/${inv.id}/pdf/?download=true&fresh=1&t=${Date.now()}`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
        responseType: 'blob',
      });
      const blob = new Blob([res.data], { type: 'application/pdf' });
      const blobUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      const cleanNum = (inv.voucher_number || 'INVOICE').replace(/[/\\:*?"<>|]/g, '-').trim();
      link.download = `Tax_Invoice_${cleanNum}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(blobUrl);
      toast.success('Invoice PDF downloaded!');
    } catch (err: any) {
      console.error('Failed to download invoice PDF:', err);
      toast.error('Failed to download invoice PDF.');
    }
  };

  const isMobileOrPWA = (): boolean => {
    if (typeof window === 'undefined') return false;
    const ua = navigator.userAgent || '';
    const isMobileUA = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile/i.test(ua);
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches || (window.navigator as any).standalone === true;
    const isTouchDevice = navigator.maxTouchPoints > 0 || 'ontouchstart' in window;
    return isMobileUA || isStandalone || isTouchDevice;
  };

  const handleShareWhatsApp = async (inv: any) => {
    if (inv.isOffline || String(inv.id).startsWith('offline_')) {
      toast.error('This invoice is waiting to sync with the cloud. Please sync before sharing.');
      return;
    }
    try {
      toast.info('Preparing WhatsApp share...');
      const token = getAccessToken();
      const activeCo = activeCompanyId || (typeof window !== 'undefined' ? localStorage.getItem('vouch_active_company_id') || '' : '');
      const headers = {
        Authorization: `Bearer ${token}`,
        'X-Company-ID': activeCo,
      };

      // 1. Obtain official secure document share token & message
      let waMessage = '';
      let shareToken = '';
      try {
        const shareRes = await axios.post(
          `${API_BASE_URL}/api/v1/documents/vouchers/${inv.id}/share/`,
          { expires_in_days: 30 },
          { headers }
        );
        if (shareRes.data?.raw_token) {
          shareToken = shareRes.data.raw_token;
        }
        if (shareRes.data?.whatsapp_message) {
          waMessage = shareRes.data.whatsapp_message;
        }
      } catch (e) {
        console.warn('Documents share endpoint fallback:', e);
      }

      // Fallback to legacy dispatch-details if documents share didn't supply waMessage
      if (!waMessage) {
        try {
          const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/vouchers/${inv.id}/dispatch-details/`, { headers });
          waMessage = res.data?.whatsapp_message || '';
          if (res.data?.claim_token && !shareToken) {
            shareToken = res.data.claim_token;
          }
        } catch (e) {
          console.warn('Dispatch details fallback failed:', e);
        }
      }

      if (!waMessage) {
        const invoiceNo = inv.voucher_number || 'INVOICE';
        const total = Number(inv.total_amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 });
        const origin = typeof window !== 'undefined' ? window.location.origin : 'https://srilekh.com';
        const partyName = inv.party?.name || inv.buyer_name || 'Valued Customer';
        const companyName = inv.company?.name || 'Our Company';
        const invDate = inv.voucher_date || inv.date || 'Today';
        const claimLink = shareToken ? `${origin}/claim?token=${encodeURIComponent(shareToken)}` : `${origin}/sales/${inv.id}/print`;
        waMessage = (
          `🧾 *TAX INVOICE #${invoiceNo}*\n\n` +
          `Dear *${partyName}*,\n\n` +
          `Here is your tax invoice from *${companyName}*:\n` +
          `• *Invoice Number:* ${invoiceNo}\n` +
          `• *Invoice Date:* ${invDate}\n` +
          `• *Invoice Amount:* ₹${total}\n\n` +
          `📄 *View & Download Official PDF:*\n` +
          `${origin}/sales/${inv.id}/print\n\n` +
          `⚡ *1-Click Import (Auto-Book Purchase in SriLekh):*\n` +
          `${claimLink}\n\n` +
          `Thank you for doing business with us!\n` +
          `*${companyName}*`
        );
      }

      // Clean phone number
      const rawPhone = inv.party?.phone || inv.party_phone || '';
      let phone = String(rawPhone).replace(/[^0-9]/g, '');
      if (phone.length === 10) phone = '91' + phone;

      const cleanNum = (inv.voucher_number || 'INVOICE').replace(/[/\\:*?"<>|]/g, '-').trim();
      const filename = `Tax_Invoice_${cleanNum}.pdf`;

      // Fetch official PDF blob
      let pdfFile: File | null = null;
      let pdfBlobUrl: string | null = null;
      try {
        const pdfRes = await axios.get(`${API_BASE_URL}/api/v1/documents/vouchers/${inv.id}/pdf/?fresh=1&t=${Date.now()}`, {
          headers,
          responseType: 'blob',
        });
        pdfFile = new File([pdfRes.data], filename, { type: 'application/pdf' });
        pdfBlobUrl = window.URL.createObjectURL(pdfRes.data);
      } catch (pdfErr) {
        console.warn('PDF fetch failed:', pdfErr);
      }

      const isMobile = isMobileOrPWA();

      // ================= 1. MOBILE / PWA FLOW =================
      if (isMobile) {
        // Use native Web Share API to share BOTH PDF file and link message into WhatsApp!
        if (typeof navigator !== 'undefined' && navigator.share && pdfFile) {
          if (navigator.canShare && navigator.canShare({ files: [pdfFile] })) {
            try {
              await navigator.share({
                files: [pdfFile],
                title: filename,
                text: waMessage,
              });
              toast.success('Shared to WhatsApp successfully!');
              return;
            } catch (shareErr: any) {
              if (shareErr?.name === 'AbortError') {
                return; // User dismissed share sheet
              }
              console.warn('Native share with file failed, falling back to WhatsApp direct link:', shareErr);
            }
          }
        }

        // Direct WhatsApp deep link on mobile without downloading file to device
        const encoded = encodeURIComponent(waMessage);
        const appUrl = phone ? `whatsapp://send?phone=${phone}&text=${encoded}` : `whatsapp://send?text=${encoded}`;
        window.location.href = appUrl;
        return;
      }

      // ================= 2. DESKTOP / LAPTOP FLOW =================
      // On desktop, download file for convenience so user can drag into WhatsApp Web
      if (pdfBlobUrl) {
        const dlLink = document.createElement('a');
        dlLink.href = pdfBlobUrl;
        dlLink.download = filename;
        document.body.appendChild(dlLink);
        dlLink.click();
        document.body.removeChild(dlLink);
        window.URL.revokeObjectURL(pdfBlobUrl);
      }

      toast.success('Opening WhatsApp Web...');
      const encoded = encodeURIComponent(waMessage);
      const webUrl = phone 
        ? `https://web.whatsapp.com/send?phone=${phone}&text=${encoded}` 
        : `https://web.whatsapp.com/send?text=${encoded}`;
      window.open(webUrl, '_blank');

    } catch (err: any) {
      console.error('Failed to prepare WhatsApp share:', err);
      toast.error('Failed to prepare WhatsApp share.');
    }
  };

  const [focusedIndex, setFocusedIndex] = useState<number>(-1);

  const scrollToInvoice = (index: number) => {
    if (index >= 0 && index < displayedInvoices.length) {
      const invId = displayedInvoices[index].id;
      const el = document.getElementById(`row-sales-${invId}`);
      if (el) {
        el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (isEditModalOpen || deleteConfirmParams !== null) return;
      if (activeTab !== 'invoices') return;

      const activeElement = document.activeElement;
      const isInputFocused = activeElement && (
        activeElement.tagName === 'INPUT' ||
        activeElement.tagName === 'TEXTAREA' ||
        activeElement.tagName === 'SELECT'
      );
      if (isInputFocused) return;

      if (displayedInvoices.length === 0) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setFocusedIndex(prev => {
          const next = prev < displayedInvoices.length - 1 ? prev + 1 : 0;
          scrollToInvoice(next);
          return next;
        });
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setFocusedIndex(prev => {
          const next = prev > 0 ? prev - 1 : displayedInvoices.length - 1;
          scrollToInvoice(next);
          return next;
        });
      } else if (e.key === 'Home') {
        e.preventDefault();
        setFocusedIndex(0);
        scrollToInvoice(0);
      } else if (e.key === 'End') {
        e.preventDefault();
        setFocusedIndex(displayedInvoices.length - 1);
        scrollToInvoice(displayedInvoices.length - 1);
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        // TALLY SHORTCUT: Ctrl + Enter edits the selected invoice
        if (focusedIndex >= 0 && focusedIndex < displayedInvoices.length) {
          e.preventDefault();
          handleStartEdit(displayedInvoices[focusedIndex]);
        }
      } else if (e.key === 'Enter') {
        // Enter opens print view
        if (focusedIndex >= 0 && focusedIndex < displayedInvoices.length) {
          e.preventDefault();
          router.push(`/sales/${displayedInvoices[focusedIndex].id}/print`);
        }
      } else if (e.key.toLowerCase() === 'e' && !e.ctrlKey && !e.metaKey) {
        if (focusedIndex >= 0 && focusedIndex < displayedInvoices.length) {
          e.preventDefault();
          handleStartEdit(displayedInvoices[focusedIndex]);
        }
      } else if ((e.altKey && e.key.toLowerCase() === 'd') || e.key === 'Delete') {
        if (focusedIndex >= 0 && focusedIndex < displayedInvoices.length) {
          e.preventDefault();
          const target = displayedInvoices[focusedIndex];
          handleDeleteInvoice(target.id, target.voucher_number);
        }
      } else if (e.key.toLowerCase() === 'p' && !e.ctrlKey && !e.metaKey) {
        if (focusedIndex >= 0 && focusedIndex < displayedInvoices.length) {
          e.preventDefault();
          router.push(`/sales/${displayedInvoices[focusedIndex].id}/print`);
        }
      } else if (e.key === 'Escape') {
        setFocusedIndex(-1);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [displayedInvoices, focusedIndex, router, isEditModalOpen, deleteConfirmParams, activeTab]);

  return (
    <DashboardLayout>
      <div className="space-y-6 flex flex-col h-full">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/40 pb-5">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">
                {activeTab === 'invoices' ? 'Sales Invoices' : 'Customers'}
              </h1>
              {displayPeriod && (
                <span className="text-[11px] bg-primary/10 text-primary border border-primary/20 px-2 py-0.5 rounded-full font-medium">
                  {displayPeriod}
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {activeTab === 'invoices'
                ? 'Outward tax invoices, receivables tracking, and billing records'
                : 'Customer directory, outstanding receivables (money to collect), and ledger balances'}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Link
              href="/sales/proforma/new"
              className="px-3.5 py-2.5 rounded-xl text-xs font-semibold border border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400 hover:bg-blue-500/20 transition-all flex items-center justify-center gap-1.5 cursor-pointer shadow-xs"
              title="Create commercial quotation or price estimate"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>New Estimate / Quote</span>
            </Link>
            {activeTab === 'invoices' ? (
              <Link href="/sales/new" className="bg-primary text-primary-foreground px-4 py-2.5 rounded-xl text-xs font-bold shadow-md shadow-primary/20 hover:bg-primary/90 transition-all flex items-center justify-center gap-1.5">
                <Plus className="w-3.5 h-3.5" />
                <span>Create Invoice</span>
                <kbd className="bg-primary-foreground/20 px-1.5 py-0.5 rounded text-[10px]">F8</kbd>
              </Link>
            ) : (
              <Link href="/sales/customers/new" className="bg-primary hover:bg-primary/90 text-primary-foreground px-4 py-2.5 rounded-xl text-xs font-bold shadow-md shadow-primary/20 transition-all flex items-center justify-center gap-1.5">
                <Plus className="w-3.5 h-3.5" />
                <span>Add Customer</span>
              </Link>
            )}
          </div>
        </div>

        {/* View Switcher: Invoices vs Customers vs Proforma Estimates */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-card p-2 rounded-2xl border border-border/40 shadow-xs">
          <div className="flex items-center gap-1.5 p-1 bg-muted/60 rounded-xl border border-border/40 text-xs flex-wrap sm:flex-nowrap">
            <button
              type="button"
              onClick={() => setActiveTab('invoices')}
              className={`px-4 py-2 rounded-lg font-bold transition-all flex items-center gap-2 cursor-pointer ${
                activeTab === 'invoices'
                  ? 'bg-background text-foreground shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <FileText className="w-4 h-4 text-emerald-500" />
              <span>Sales Invoices</span>
              <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-mono font-bold ${
                unpaidInvoicesCount > 0
                  ? 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30'
                  : 'bg-muted text-muted-foreground'
              }`}>
                {unpaidInvoicesCount > 0 ? `${unpaidInvoicesCount} Due` : invoices.length}
              </span>
            </button>
            <Link
              href="/sales/proforma"
              className="px-4 py-2 rounded-lg font-bold transition-all flex items-center gap-2 text-muted-foreground hover:text-foreground hover:bg-background/60 cursor-pointer"
              title="Commercial estimates and quotations with 1-click GST conversion"
            >
              <Receipt className="w-4 h-4 text-blue-500" />
              <span>Proforma & Estimates</span>
              <span className="px-1.5 py-0.5 rounded-full text-[10px] font-mono font-bold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
                Quotes
              </span>
            </Link>
            <button
              type="button"
              onClick={() => setActiveTab('customers')}
              className={`px-4 py-2 rounded-lg font-bold transition-all flex items-center gap-2 cursor-pointer ${
                activeTab === 'customers'
                  ? 'bg-background text-foreground shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Users className="w-4 h-4 text-primary" />
              <span>Customers</span>
              <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-mono font-bold ${
                customersToCollectCount > 0
                  ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30'
                  : 'bg-muted text-muted-foreground'
              }`}>
                {customersToCollectCount > 0 ? `${customersToCollectCount} To Collect` : customers.length}
              </span>
            </button>
          </div>

          <div className="flex items-center gap-2 text-xs text-muted-foreground px-2">
            {activeTab === 'invoices' ? (
              <span>
                {paymentFilter === 'UNPAID' 
                  ? 'Filtered to Unpaid Invoices (Money to Collect)' 
                  : paymentFilter === 'PAID' 
                  ? 'Filtered to Settled Invoices' 
                  : 'Showing all sales invoices'}
              </span>
            ) : (
              <span>
                {customerFilter === 'UNPAID'
                  ? `Showing ${filteredCustomers.length} customers with money to collect`
                  : `Showing ${filteredCustomers.length} customers`}
              </span>
            )}
          </div>
        </div>

        {activeTab === 'invoices' ? (
          <>
            {/* Period Performance & Overview Section */}
            <div className="bg-card text-card-foreground rounded-2xl shadow-sm border border-border/40 p-4 sm:p-5 space-y-4">
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 border-b border-border/40 pb-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-9 h-9 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-500">
                    <Calendar className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <h2 className="text-base font-bold text-foreground">Period Performance &amp; Sales Overview</h2>
                      <span className="text-[11px] bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded-full font-medium">
                        {activeDateRange.formattedRange}
                      </span>
                      <Link
                        href="/purchases"
                        className="text-[11px] bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 hover:border-blue-500/40 px-2.5 py-0.5 rounded-full font-medium flex items-center gap-1 transition-all"
                        title="View Purchase Invoices for this period"
                      >
                        <ShoppingCart className="w-3 h-3" />
                        <span>Purchases: ₹{periodMetrics.totalPurchases.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
                        <ArrowRight className="w-2.5 h-2.5 opacity-70" />
                      </Link>
                      {loadingMetrics && (
                        <RefreshCw className="w-3.5 h-3.5 text-muted-foreground animate-spin" />
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Track outward sales, Output GST liability, collected payments, and pending receivables
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
                    title="When enabled, the invoices list below will strictly show bills within this period"
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
                {/* Card 1: Total Sales */}
                <div 
                  onClick={() => setPaymentFilter('ALL')}
                  className={`bg-muted/20 border rounded-xl p-4 shadow-xs flex flex-col justify-between relative overflow-hidden group transition-all cursor-pointer ${
                    paymentFilter === 'ALL' ? 'border-emerald-500 ring-2 ring-emerald-500/30 bg-emerald-500/5' : 'border-emerald-500/20 hover:border-emerald-500/40'
                  }`}
                  title="Click to view all sales invoices"
                >
                  <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-500/5 rounded-bl-full pointer-events-none -mr-4 -mt-4" />
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-600 dark:text-emerald-400 tracking-wider uppercase">
                      <TrendingUp className="w-3.5 h-3.5" />
                      <span>Total Sales</span>
                    </div>
                    <span className="px-1.5 py-0.2 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                      {paymentFilter === 'ALL' ? 'Selected' : 'All Sales'}
                    </span>
                  </div>
                  <div>
                    <p className="text-2xl sm:text-3xl font-black text-foreground font-mono">
                      ₹{periodMetrics.totalSales.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </p>
                    <div className="flex items-center justify-between text-[11px] text-muted-foreground mt-1.5 pt-1.5 border-t border-border/40 font-mono">
                      <span>{periodMetrics.salesCount} invoices</span>
                      <span className="text-emerald-600 dark:text-emerald-400 font-medium">Show all →</span>
                    </div>
                  </div>
                </div>

                {/* Card 2: Total Output GST */}
                <div className="bg-muted/20 border border-indigo-500/20 rounded-xl p-4 shadow-xs flex flex-col justify-between relative overflow-hidden group hover:border-indigo-500/40 transition-all">
                  <div className="absolute top-0 right-0 w-24 h-24 bg-indigo-500/5 rounded-bl-full pointer-events-none -mr-4 -mt-4" />
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <div className="flex items-center gap-1.5 text-xs font-bold text-indigo-500 dark:text-indigo-400 tracking-wider uppercase">
                      <FileText className="w-3.5 h-3.5" />
                      <span>Total Output GST</span>
                    </div>
                    <span className="px-1.5 py-0.2 rounded text-[10px] font-bold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                      Output Liability
                    </span>
                  </div>
                  <div>
                    <p className="text-2xl sm:text-3xl font-black text-indigo-500 dark:text-indigo-400 font-mono">
                      ₹{periodMetrics.totalOutputGst.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </p>
                    <div className="flex items-center justify-between text-[11px] text-muted-foreground mt-1.5 pt-1.5 border-t border-border/40 font-mono">
                      <span>CGST: ₹{periodMetrics.outputCgst.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
                      <span>SGST: ₹{periodMetrics.outputSgst.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
                      {periodMetrics.outputIgst > 0 && (
                        <span className="hidden xl:inline">IGST: ₹{periodMetrics.outputIgst.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Card 3: Collected Amount */}
                <div 
                  onClick={() => setPaymentFilter('PAID')}
                  className={`bg-muted/20 border rounded-xl p-4 shadow-xs flex flex-col justify-between relative overflow-hidden group transition-all cursor-pointer ${
                    paymentFilter === 'PAID' ? 'border-blue-500 ring-2 ring-blue-500/30 bg-blue-500/5' : 'border-blue-500/20 hover:border-blue-500/40'
                  }`}
                  title="Click to view paid invoices"
                >
                  <div className="absolute top-0 right-0 w-24 h-24 bg-blue-500/5 rounded-bl-full pointer-events-none -mr-4 -mt-4" />
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <div className="flex items-center gap-1.5 text-xs font-bold text-blue-500 tracking-wider uppercase">
                      <CheckCircle className="w-3.5 h-3.5" />
                      <span>Collected Amount</span>
                    </div>
                    <span className="px-1.5 py-0.2 rounded text-[10px] font-bold bg-blue-500/10 text-blue-400 border border-blue-500/20">
                      {paymentFilter === 'PAID' ? 'Selected' : 'Settled'}
                    </span>
                  </div>
                  <div>
                    <p className="text-2xl sm:text-3xl font-black text-blue-500 dark:text-blue-400 font-mono">
                      ₹{periodMetrics.paidSales.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </p>
                    <div className="flex items-center justify-between text-[11px] text-muted-foreground mt-1.5 pt-1.5 border-t border-border/40 font-mono">
                      <span>{periodMetrics.paidCount} invoices collected</span>
                      <span className="text-blue-500 dark:text-blue-400 font-medium">Show paid →</span>
                    </div>
                  </div>
                </div>

                {/* Card 4: Money to Collect (Due) */}
                <div 
                  onClick={() => setPaymentFilter('UNPAID')}
                  className={`bg-muted/20 border rounded-xl p-4 shadow-xs flex flex-col justify-between relative overflow-hidden group transition-all cursor-pointer ${
                    paymentFilter === 'UNPAID' ? 'border-amber-500 ring-2 ring-amber-500/30 bg-amber-500/5' : 'border-amber-500/20 hover:border-amber-500/40'
                  }`}
                  title="Click to view unpaid sales invoices (Money to Collect)"
                >
                  <div className="absolute top-0 right-0 w-24 h-24 bg-amber-500/5 rounded-bl-full pointer-events-none -mr-4 -mt-4" />
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <div className="flex items-center gap-1.5 text-xs font-bold text-amber-500 tracking-wider uppercase">
                      <Clock className="w-3.5 h-3.5" />
                      <span>Money to Collect (Due)</span>
                    </div>
                    <span className="px-1.5 py-0.2 rounded text-[10px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                      {paymentFilter === 'UNPAID' ? 'Selected' : 'Pending Due'}
                    </span>
                  </div>
                  <div>
                    <p className="text-2xl sm:text-3xl font-black text-amber-500 dark:text-amber-400 font-mono">
                      ₹{periodMetrics.unpaidSales.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </p>
                    <div className="flex items-center justify-between text-[11px] text-muted-foreground mt-1.5 pt-1.5 border-t border-border/40 font-mono">
                      <span>{periodMetrics.unpaidCount} invoices due</span>
                      <span className="text-amber-500 dark:text-amber-400 font-bold">Unpaid Invoices →</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Invoices Table Card */}
            <div className="bg-card text-card-foreground rounded-2xl shadow-sm border border-border/40 flex-1 overflow-hidden flex flex-col">
              <div className="px-5 py-3 border-b border-border/40 bg-muted/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  {/* Payment Filter Tabs */}
                  <div className="flex items-center gap-1 bg-muted/80 p-1 rounded-xl border border-border/50 text-xs">
                    <button
                      type="button"
                      onClick={() => setPaymentFilter('ALL')}
                      className={`px-3 py-1.5 rounded-lg font-semibold transition-all cursor-pointer ${
                        paymentFilter === 'ALL'
                          ? 'bg-background text-foreground shadow-xs font-bold'
                          : 'text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      All Invoices ({invoices.length})
                    </button>
                    <button
                      type="button"
                      onClick={() => setPaymentFilter('UNPAID')}
                      className={`px-3 py-1.5 rounded-lg font-semibold transition-all flex items-center gap-1.5 cursor-pointer ${
                        paymentFilter === 'UNPAID'
                          ? 'bg-amber-500/20 text-amber-500 dark:text-amber-400 border border-amber-500/30 shadow-xs font-bold'
                          : 'text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      <Clock className="w-3.5 h-3.5" />
                      <span>Unpaid (Collect) ({unpaidInvoicesCount})</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setPaymentFilter('PAID')}
                      className={`px-3 py-1.5 rounded-lg font-semibold transition-all flex items-center gap-1.5 cursor-pointer ${
                        paymentFilter === 'PAID'
                          ? 'bg-emerald-500/20 text-emerald-500 dark:text-emerald-400 border border-emerald-500/30 shadow-xs font-bold'
                          : 'text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      <CheckCircle className="w-3.5 h-3.5" />
                      <span>Paid ({paidInvoicesCount})</span>
                    </button>
                  </div>

                  {filterTableByPeriod && (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-primary/10 text-primary border border-primary/20">
                      Filtered: {activeDateRange.formattedRange}
                    </span>
                  )}

                {/* Status Filter Tabs */}
                <div className="flex items-center gap-1 bg-muted/60 p-1 rounded-xl border border-border/40 text-xs">
                  <button
                    onClick={() => setStatusFilter('ALL')}
                    className={`px-2.5 py-1 rounded-lg transition-all cursor-pointer ${
                      statusFilter === 'ALL'
                        ? 'bg-background text-foreground shadow-xs font-medium'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    All
                  </button>
                  <button
                    onClick={() => setStatusFilter('ACTIVE')}
                    className={`px-2.5 py-1 rounded-lg transition-all cursor-pointer ${
                      statusFilter === 'ACTIVE'
                        ? 'bg-background text-foreground shadow-xs font-medium'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    Active
                  </button>
                  <button
                    onClick={() => setStatusFilter('SUPERSEDED')}
                    className={`px-2.5 py-1 rounded-lg transition-all cursor-pointer ${
                      statusFilter === 'SUPERSEDED'
                        ? 'bg-background text-foreground shadow-xs font-medium'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    Superseded
                  </button>
                </div>
              </div>
              <span className="text-xs text-muted-foreground hidden lg:inline">Use ↑ / ↓ arrow keys to navigate, Ctrl+Enter to edit, Enter to print</span>
            </div>

            {loading ? (
              <div className="flex flex-col items-center justify-center h-full py-20 text-muted-foreground gap-3">
                <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                <span className="text-sm font-medium">Loading invoices...</span>
              </div>
            ) : invoices.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center p-12 bg-card">
                <svg className="w-20 h-20 text-muted-foreground dark:text-gray-600 mb-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                </svg>
                <h3 className="text-2xl font-bold mb-2">No Invoices Found</h3>
                <p className="text-muted-foreground max-w-md mx-auto mb-8">No invoices found matching the current period.</p>
                <Link href="/sales/new" className="bg-blue-600 text-white px-6 py-2.5 rounded-lg shadow hover:bg-blue-700 transition-colors font-medium">
                  + Create Invoice
                </Link>
              </div>
            ) : displayedInvoices.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center p-12 bg-card">
                <Clock className="w-16 h-16 text-muted-foreground mb-4 opacity-40" />
                <h3 className="text-xl font-bold mb-2 text-foreground">
                  {paymentFilter === 'UNPAID' ? 'No Pending Invoices to Collect' : 'No Paid Invoices Found'}
                </h3>
                <p className="text-muted-foreground text-xs max-w-md mx-auto mb-6">
                  {paymentFilter === 'UNPAID'
                    ? 'All sales invoices in this period are settled! There are no unpaid receivables.'
                    : 'No invoices with paid status were found for this period.'}
                </p>
                <button
                  type="button"
                  onClick={() => setPaymentFilter('ALL')}
                  className="px-4 py-2 bg-muted hover:bg-muted/80 text-foreground rounded-xl text-xs font-bold transition-all cursor-pointer"
                >
                  View All Invoices ({invoices.length})
                </button>
              </div>
            ) : (
              <div className="flex-1 w-full overflow-auto flex flex-col justify-between">
                {/* Mobile Cards (block md:hidden) */}
                <div className="block md:hidden divide-y divide-border/60">
                  {displayedInvoices.map((inv, idx) => (
                    <div key={inv.id || idx} className="p-3.5 space-y-3 bg-card">
                      <div className="flex items-start justify-between gap-2">
                        <span className="font-mono font-bold text-foreground text-sm whitespace-nowrap truncate">{inv.voucher_number}</span>
                        <span className="text-xs text-muted-foreground font-mono whitespace-nowrap shrink-0">{inv.date}</span>
                      </div>

                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-foreground text-sm truncate">{inv.party_name}</span>
                        <span className="font-bold text-emerald-500 dark:text-emerald-400 font-mono text-[15px] whitespace-nowrap shrink-0">
                          ₹{(() => {
                            const raw = parseFloat(inv.total_amount) || 0;
                            const rounded = Math.abs(raw % 1) > 0 ? (raw % 1 < 0.5 ? Math.floor(raw) : Math.ceil(raw)) : raw;
                            return rounded.toLocaleString('en-IN', { minimumFractionDigits: 2 });
                          })()}
                        </span>
                      </div>

                      <div className="flex items-center gap-2 flex-wrap">
                        {inv.payment_status === 'PAID' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold rounded-full bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 font-mono">
                            PAID
                          </span>
                        ) : inv.payment_status === 'PARTIAL' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold rounded-full bg-amber-500/10 text-amber-500 border border-amber-500/20 font-mono">
                            PARTIAL (₹{Number(inv.paid_amount || 0).toLocaleString('en-IN')})
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold rounded-full bg-rose-500/10 text-rose-500 border border-rose-500/20 font-mono">
                            UNPAID
                          </span>
                        )}

                        {inv.status === 'SUPERSEDED' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold rounded-full bg-amber-500/10 text-amber-500 border border-amber-500/30">
                            SUPERSEDED
                          </span>
                        ) : inv.status === 'CANCELLED' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold rounded-full bg-rose-500/10 text-rose-500 border border-rose-500/30">
                            CANCELLED
                          </span>
                        ) : inv.syncStatus === 'SYNC_FAILED' ? (
                          <div className="flex items-center gap-1">
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold rounded-full bg-rose-500/10 text-rose-500 border border-rose-500/30">
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
                              >
                                <RefreshCw className="w-2.5 h-2.5" />
                              </button>
                            )}
                          </div>
                        ) : inv.syncStatus === 'OFFLINE_PENDING' || inv.isOffline || inv.status === 'PENDING_SYNC' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold rounded-full bg-amber-500/10 text-amber-500 border border-amber-500/30">
                            <CloudOff className="w-2.5 h-2.5" />
                            Saved offline — waiting to sync
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold rounded-full bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                            <CheckCircle className="w-2.5 h-2.5" />
                            Saved &amp; synced
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2 pt-2 border-t border-border/40 overflow-x-auto pb-1" style={{ scrollbarWidth: 'none' }}>
                        <button
                          onClick={() => handleStartEdit(inv)}
                          className="px-3 py-1.5 bg-blue-600/10 text-blue-500 dark:text-blue-400 rounded-lg text-xs font-semibold border border-blue-500/20 flex items-center gap-1.5 whitespace-nowrap shrink-0"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                          <span>Edit</span>
                        </button>
                        <Link
                          href={`/sales/${inv.id}/print`}
                          className="px-3 py-1.5 bg-muted/60 text-foreground rounded-lg text-xs font-semibold border border-border/70 flex items-center gap-1.5 whitespace-nowrap shrink-0"
                        >
                          <Printer className="w-3.5 h-3.5" />
                          <span>Print</span>
                        </Link>
                        <button
                          onClick={async (e) => {
                            e.stopPropagation();
                            if (navigator.share) {
                              try {
                                await navigator.share({
                                  title: `Tax Invoice ${inv.voucher_number}`,
                                  text: `Here is your tax invoice ${inv.voucher_number} for ₹${inv.total_amount}.`,
                                  url: `${window.location.origin}/sales/${inv.id}/print`
                                });
                              } catch (err) {
                                console.log('Share error:', err);
                              }
                            } else {
                              toast.error('Share API is not supported in this browser.');
                            }
                          }}
                          className="px-3 py-1.5 bg-purple-600/10 text-purple-500 rounded-lg text-xs font-semibold border border-purple-500/20 flex items-center gap-1.5 whitespace-nowrap shrink-0"
                        >
                          <Share2 className="w-3.5 h-3.5" />
                          <span>Share</span>
                        </button>
                        <button
                          onClick={() => handleShareWhatsApp(inv)}
                          className="px-3 py-1.5 bg-emerald-600/10 text-emerald-500 rounded-lg text-xs font-semibold border border-emerald-500/20 flex items-center gap-1.5 whitespace-nowrap shrink-0"
                        >
                          <MessageCircle className="w-3.5 h-3.5" />
                          <span>WhatsApp</span>
                        </button>
                        <button
                          onClick={() => handleDownloadPdf(inv)}
                          className="px-3 py-1.5 bg-blue-600/10 text-blue-500 dark:text-blue-400 rounded-lg text-xs font-semibold border border-blue-500/20 flex items-center gap-1.5 whitespace-nowrap shrink-0"
                        >
                          <Download className="w-3.5 h-3.5" />
                          <span>PDF</span>
                        </button>
                        <button
                          onClick={() => handleDeleteInvoice(inv.id, inv.voucher_number)}
                          className="px-3 py-1.5 bg-rose-600/10 text-rose-500 rounded-lg text-xs font-semibold border border-rose-500/20 flex items-center gap-1.5 whitespace-nowrap shrink-0"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          <span>Delete</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Desktop Table (hidden md:block) */}
                <div className="hidden md:block overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="border-b border-border bg-muted/50 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                        <th className="p-4">Invoice No.</th>
                        <th className="p-4">Date</th>
                        <th className="p-4">Party Name</th>
                        <th className="p-4 text-right">Total Amount</th>
                        <th className="p-4 text-center">Payment</th>
                        <th className="p-4 text-center">Status</th>
                        <th className="p-4 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border text-xs">
                      {displayedInvoices.map((inv, idx) => {
                        const isFocused = focusedIndex === idx;
                        return (
                          <tr
                            id={`row-sales-${inv.id}`}
                            key={inv.id || idx}
                            onClick={() => setFocusedIndex(idx)}
                            onDoubleClick={() => router.push(`/sales/${inv.id}/print`)}
                            className={`transition-all duration-150 cursor-pointer group ${
                              isFocused
                                ? 'bg-primary/10 ring-2 ring-inset ring-primary/40 border-l-4 border-l-primary'
                                : 'hover:bg-muted/40'
                            }`}
                          >
                            <td className="p-4 font-mono font-semibold text-foreground text-sm">{inv.voucher_number}</td>
                            <td className="p-4 text-muted-foreground font-mono">{inv.date}</td>
                            <td className="p-4 text-foreground font-semibold text-sm">{inv.party_name}</td>
                            <td className="p-4 font-bold text-foreground text-right font-mono tabular-nums text-sm">
                              ₹{(() => {
                                const raw = parseFloat(inv.total_amount) || 0;
                                const rounded = Math.abs(raw % 1) > 0 ? (raw % 1 < 0.5 ? Math.floor(raw) : Math.ceil(raw)) : raw;
                                return rounded.toLocaleString('en-IN', { minimumFractionDigits: 2 });
                              })()}
                            </td>
                            <td className="p-4 text-center">
                              {inv.payment_status === 'PAID' ? (
                                <span className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 font-mono">
                                  PAID
                                </span>
                              ) : inv.payment_status === 'PARTIAL' ? (
                                <span
                                  className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded-full bg-amber-500/10 text-amber-500 border border-amber-500/20 font-mono"
                                  title={`Paid: ₹${inv.paid_amount || 0}`}
                                >
                                  PARTIAL (₹{Number(inv.paid_amount || 0).toLocaleString('en-IN')})
                                </span>
                              ) : (
                                <span className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded-full bg-rose-500/10 text-rose-500 border border-rose-500/20 font-mono">
                                  UNPAID
                                </span>
                              )}
                            </td>
                            <td className="p-4 text-center">
                              {inv.status === 'SUPERSEDED' ? (
                                <span
                                  className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-full bg-amber-500/10 text-amber-500 border border-amber-500/30"
                                  title="This invoice was superseded and corrected by a newer revision"
                                >
                                  SUPERSEDED
                                </span>
                              ) : inv.status === 'CANCELLED' ? (
                                <span
                                  className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-full bg-rose-500/10 text-rose-500 border border-rose-500/30"
                                  title="This invoice was cancelled and reversed"
                                >
                                  CANCELLED
                                </span>
                              ) : inv.syncStatus === 'SYNC_FAILED' ? (
                                <div className="flex items-center gap-1.5 justify-center">
                                  <span
                                    className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-full bg-rose-500/10 text-rose-500 border border-rose-500/30"
                                    title={inv.errorMessage || "Action requires attention"}
                                  >
                                    <AlertTriangle className="w-3.5 h-3.5" />
                                    Sync failed — action requires attention
                                  </span>
                                  {(inv.dexieId || inv.localId || inv.id) && (
                                    <button
                                      type="button"
                                      onClick={async (e) => {
                                        e.stopPropagation();
                                        await retryFailedVoucher(inv.dexieId || inv.localId || inv.id);
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
                            <td className="p-4 text-right">
                              <div className="flex items-center justify-end gap-2" onClick={(e) => e.stopPropagation()}>
                                <button
                                  onClick={() => {
                                    setEwayVoucher(inv);
                                    setIsEwayModalOpen(true);
                                  }}
                                  className="px-3 py-1.5 bg-emerald-600/15 hover:bg-emerald-600/25 text-emerald-500 rounded-lg text-xs font-semibold border border-emerald-500/30 transition-colors flex items-center gap-1.5 cursor-pointer min-h-[36px]"
                                  title="Generate or View GST E-Way Bill"
                                >
                                  <Truck className="w-3.5 h-3.5" />
                                  <span>E-Way Bill</span>
                                </button>

                                <button
                                  onClick={() => handleStartEdit(inv)}
                                  className="px-3 py-1.5 bg-blue-600/15 hover:bg-blue-600/25 text-blue-400 rounded-lg text-xs font-semibold border border-blue-500/30 transition-colors flex items-center gap-1.5 cursor-pointer min-h-[36px]"
                                  title="Edit Sales Invoice"
                                >
                                  <Edit2 className="w-3.5 h-3.5" />
                                  <span>Edit</span>
                                </button>

                                <Link
                                  href={`/sales/${inv.id}/print`}
                                  className="px-2.5 py-1.5 bg-muted/60 hover:bg-muted text-foreground rounded-lg text-xs font-semibold border border-border transition-colors flex items-center gap-1.5 cursor-pointer min-h-[36px]"
                                  title="Print Invoice"
                                >
                                  <Printer className="w-3.5 h-3.5" />
                                  <span>Print</span>
                                </Link>

                                <button
                                  onClick={() => handleDownloadPdf(inv)}
                                  className="px-2.5 py-1.5 bg-blue-600/10 hover:bg-blue-600/20 text-blue-500 dark:text-blue-400 rounded-lg text-xs font-semibold border border-blue-500/20 transition-colors flex items-center gap-1.5 cursor-pointer min-h-[36px]"
                                  title="Download Official PDF"
                                >
                                  <Download className="w-3.5 h-3.5" />
                                  <span>PDF</span>
                                </button>

                                <button
                                  onClick={() => handleShareWhatsApp(inv)}
                                  className="px-2.5 py-1.5 bg-emerald-600/15 hover:bg-emerald-600/25 text-emerald-500 rounded-lg text-xs font-semibold border border-emerald-500/30 transition-colors flex items-center gap-1.5 cursor-pointer min-h-[36px]"
                                  title="Share on WhatsApp"
                                >
                                  <MessageCircle className="w-3.5 h-3.5" />
                                  <span>WhatsApp</span>
                                </button>

                                <button
                                  onClick={async (e) => {
                                    e.stopPropagation();
                                    if (navigator.share) {
                                      try {
                                        await navigator.share({
                                          title: `Tax Invoice ${inv.voucher_number}`,
                                          text: `Here is your tax invoice ${inv.voucher_number} for ₹${inv.total_amount}.`,
                                          url: `${window.location.origin}/sales/${inv.id}/print`
                                        });
                                      } catch (err) {
                                        console.log('Share error:', err);
                                      }
                                    } else {
                                      toast.error('Share API is not supported in this browser.');
                                    }
                                  }}
                                  className="px-2.5 py-1.5 bg-purple-600/10 hover:bg-purple-600/20 text-purple-500 rounded-lg text-xs font-semibold border border-purple-500/20 transition-colors flex items-center gap-1.5 cursor-pointer min-h-[36px]"
                                  title="Native Share"
                                >
                                  <Share2 className="w-3.5 h-3.5" />
                                  <span>Share</span>
                                </button>

                                <button
                                  onClick={() => handleDeleteInvoice(inv.id, inv.voucher_number)}
                                  className="px-3 py-1.5 bg-rose-600/15 hover:bg-rose-600/25 text-rose-400 rounded-lg text-xs font-semibold border border-rose-500/30 transition-colors flex items-center gap-1.5 cursor-pointer min-h-[36px]"
                                  title="Delete Invoice"
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
                  <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-5 py-3.5 border-t border-border bg-muted/20 text-xs text-muted-foreground">
                    <div className="font-mono tabular-nums">
                      Showing <span className="font-semibold text-foreground">{pagination.total_count === 0 ? 0 : ((pagination.offset ?? (page - 1) * pageSize) + 1)}</span> to{' '}
                      <span className="font-semibold text-foreground">
                        {Math.min((pagination.offset ?? (page - 1) * pageSize) + (pagination.limit ?? pageSize), pagination.total_count)}
                      </span>{' '}
                      of <span className="font-semibold text-foreground">{pagination.total_count}</span> invoices
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => fetchInvoices(page - 1)}
                        disabled={page <= 1 || loading}
                        className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-input bg-muted/50 text-foreground hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer font-medium min-h-[36px]"
                      >
                        <ChevronLeft className="w-4 h-4" />
                        <span>Previous</span>
                      </button>

                      <div className="px-3 py-1.5 text-xs font-mono font-semibold text-foreground bg-muted rounded-lg border border-input">
                        Page {page} of {pagination.total_pages || 1}
                      </div>

                      <button
                        type="button"
                        onClick={() => fetchInvoices(page + 1)}
                        disabled={page >= (pagination.total_pages || 1) || loading}
                        className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-input bg-muted/50 text-foreground hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer font-medium min-h-[36px]"
                      >
                        <span>Next</span>
                        <ChevronRight className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                )}

                {/* Keyboard Shortcuts Hint Bar */}
                <div className="p-3.5 border-t border-border bg-muted/30 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs text-muted-foreground">
                  <div className="hidden sm:flex items-center gap-2.5 flex-wrap">
                    <span className="flex items-center gap-1">
                      <kbd className="px-2 py-0.5 bg-muted rounded border border-input font-mono text-xs text-foreground font-semibold">↑</kbd>
                      <kbd className="px-2 py-0.5 bg-muted rounded border border-input font-mono text-xs text-foreground font-semibold">↓</kbd>
                      <span className="text-xs">Navigate</span>
                    </span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <kbd className="px-2 py-0.5 bg-muted rounded border border-input font-mono text-xs text-foreground font-semibold">Ctrl</kbd>
                      <span>+</span>
                      <kbd className="px-2 py-0.5 bg-muted rounded border border-input font-mono text-xs text-foreground font-semibold">Enter</kbd>
                      <span className="text-xs">Edit Invoice</span>
                    </span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <kbd className="px-2 py-0.5 bg-muted rounded border border-input font-mono text-xs text-foreground font-semibold">Enter</kbd>
                      <span className="text-xs">Print / View</span>
                    </span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <kbd className="px-2 py-0.5 bg-muted rounded border border-input font-mono text-xs text-foreground font-semibold">Alt</kbd>
                      <span>+</span>
                      <kbd className="px-2 py-0.5 bg-muted rounded border border-input font-mono text-xs text-foreground font-semibold">D</kbd>
                      <span className="text-xs">Delete</span>
                    </span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <kbd className="px-2 py-0.5 bg-muted rounded border border-input font-mono text-xs text-foreground font-semibold">Esc</kbd>
                      <span className="text-xs">Deselect</span>
                    </span>
                  </div>
                  {focusedIndex >= 0 && (
                    <span className="font-mono tabular-nums text-blue-400 font-semibold text-xs">
                      Invoice {focusedIndex + 1} of {displayedInvoices.length} selected
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
          </>
        ) : (
          /* ================= CUSTOMERS DIRECTORY VIEW ================= */
          <div className="space-y-4 flex-1 flex flex-col">
            {/* Customers Toolbar */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-card border border-border/40 p-3 sm:p-4 rounded-2xl shadow-xs">
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5 flex-1">
                {/* Search */}
                <div className="relative flex-1 sm:max-w-xs">
                  <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-2.5" />
                  <input
                    type="text"
                    placeholder="Search customer name, phone, GSTIN..."
                    value={customerSearch}
                    onChange={(e) => setCustomerSearch(e.target.value)}
                    className="bg-muted/50 border border-border/50 text-foreground pl-9 pr-4 py-2 rounded-xl focus:ring-2 focus:ring-primary/40 outline-none w-full text-xs min-h-[36px]"
                  />
                  {customerSearch && (
                    <button
                      onClick={() => setCustomerSearch('')}
                      className="absolute right-3 top-2.5 text-xs text-muted-foreground hover:text-foreground cursor-pointer"
                    >
                      ✕
                    </button>
                  )}
                </div>

                {/* Filter Pills */}
                <div className="flex items-center gap-1 bg-muted/70 p-1 rounded-xl border border-border/50 text-xs">
                  <button
                    type="button"
                    onClick={() => setCustomerFilter('ALL')}
                    className={`px-3 py-1.5 rounded-lg font-semibold transition-all cursor-pointer ${
                      customerFilter === 'ALL'
                        ? 'bg-background text-foreground shadow-xs font-bold'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    All Customers ({customers.length})
                  </button>
                  <button
                    type="button"
                    onClick={() => setCustomerFilter('UNPAID')}
                    className={`px-3 py-1.5 rounded-lg font-semibold transition-all flex items-center gap-1.5 cursor-pointer ${
                      customerFilter === 'UNPAID'
                        ? 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 shadow-xs font-bold'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <Clock className="w-3.5 h-3.5" />
                    <span>Money to Collect ({customersToCollectCount})</span>
                  </button>
                </div>
              </div>

              {/* Total Receivable Summary */}
              {totalReceivableAmount > 0 && (
                <div className="px-3.5 py-1.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-xs font-mono font-bold flex items-center justify-between sm:justify-end gap-2">
                  <span className="text-muted-foreground font-sans font-normal text-[11px]">Total Customer Dues:</span>
                  <span>₹{totalReceivableAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                </div>
              )}
            </div>

            {/* Customers Content */}
            {loadingCustomers ? (
              <div className="flex flex-col items-center justify-center p-20 text-muted-foreground gap-3 bg-card rounded-2xl border border-border/40">
                <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                <span className="text-sm font-medium">Loading customers &amp; balances...</span>
              </div>
            ) : filteredCustomers.length === 0 ? (
              <div className="flex flex-col items-center justify-center text-center p-16 bg-card rounded-2xl border border-border/40 shadow-xs">
                <Users className="w-16 h-16 text-muted-foreground mb-3 opacity-40" />
                <h3 className="text-lg font-bold mb-1 text-foreground">
                  {customerFilter === 'UNPAID' ? 'No Pending Money to Collect' : 'No Customers Found'}
                </h3>
                <p className="text-muted-foreground text-xs max-w-md mx-auto mb-6">
                  {customerSearch
                    ? `No customers match "${customerSearch}".`
                    : customerFilter === 'UNPAID'
                    ? 'All customer accounts are completely settled! No outstanding amounts to collect.'
                    : 'No customer accounts found for this company yet.'}
                </p>
                {customerFilter === 'UNPAID' ? (
                  <button
                    type="button"
                    onClick={() => setCustomerFilter('ALL')}
                    className="px-4 py-2 bg-muted hover:bg-muted/80 text-foreground rounded-xl text-xs font-bold transition-all cursor-pointer"
                  >
                    View All Customers ({customers.length})
                  </button>
                ) : (
                  <Link
                    href="/sales/customers/new"
                    className="bg-primary hover:bg-primary/90 text-primary-foreground px-5 py-2.5 rounded-xl text-xs font-bold shadow-sm transition-all cursor-pointer flex items-center gap-1.5"
                  >
                    <Plus className="w-4 h-4" />
                    <span>Add First Customer</span>
                  </Link>
                )}
              </div>
            ) : (
              <div className="bg-card text-card-foreground rounded-2xl shadow-sm border border-border/40 overflow-hidden flex flex-col">
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="border-b border-border bg-muted/50 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                        <th className="p-4">Customer Name</th>
                        <th className="p-4">GSTIN</th>
                        <th className="p-4">Phone</th>
                        <th className="p-4 text-center">Collection Status</th>
                        <th className="p-4 text-right">Outstanding Balance</th>
                        <th className="p-4 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border text-xs">
                      {filteredCustomers.map((customer) => {
                        const isReceivable = isCustomerReceivable(customer);
                        return (
                          <tr
                            key={customer.id}
                            className={`transition-colors duration-150 hover:bg-muted/40 group ${
                              isReceivable ? 'bg-emerald-500/[0.02]' : ''
                            }`}
                          >
                            {/* Customer Name */}
                            <td className="p-4">
                              <div className="flex items-center gap-2 flex-wrap">
                                <Link
                                  href={`/parties/${customer.id}/statement`}
                                  className="font-bold text-foreground text-sm hover:text-primary transition-colors"
                                  title={`View statement for ${customer.name}`}
                                >
                                  {customer.name}
                                </Link>
                                <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-semibold shrink-0">
                                  Customer
                                </span>
                              </div>
                            </td>

                            {/* GSTIN */}
                            <td className="p-4">
                              {customer.gstin ? (
                                <span className="font-mono text-xs text-foreground bg-muted/50 px-2 py-1 rounded border border-border/50">
                                  {customer.gstin}
                                </span>
                              ) : (
                                <span className="text-muted-foreground font-mono">—</span>
                              )}
                            </td>

                            {/* Phone */}
                            <td className="p-4 font-mono text-muted-foreground">
                              {customer.phone ? (
                                <span className="text-foreground">{customer.phone}</span>
                              ) : (
                                '—'
                              )}
                            </td>

                            {/* Collection Status */}
                            <td className="p-4 text-center">
                              {isReceivable ? (
                                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 font-mono">
                                  <Clock className="w-3.5 h-3.5" />
                                  <span>To Collect</span>
                                </span>
                              ) : Number(customer.current_balance || 0) === 0 ? (
                                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-full bg-muted text-muted-foreground font-mono">
                                  <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
                                  <span>Settled (₹0)</span>
                                </span>
                              ) : (
                                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-full bg-blue-500/10 text-blue-500 border border-blue-500/20 font-mono">
                                  <span>Credit Balance</span>
                                </span>
                              )}
                            </td>

                            {/* Balance */}
                            <td className="p-4 text-right">
                              <SemanticBalance
                                balanceState={customer.balance_state}
                                displayAmount={customer.display_amount}
                                currentBalance={customer.current_balance}
                                normalBalance={customer.normal_balance}
                                balanceDirection={customer.balance_direction}
                                size="md"
                              />
                            </td>

                            {/* Actions */}
                            <td className="p-4 text-right">
                              <div className="flex items-center justify-end gap-2">
                                {isReceivable ? (
                                  <Link
                                    href={`/vouchers/new?type=RECEIPT&party=${customer.id}`}
                                    className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold shadow-xs transition-colors flex items-center gap-1 min-h-[34px]"
                                  >
                                    <span>Receive (F6)</span>
                                  </Link>
                                ) : (
                                  <Link
                                    href={`/vouchers/new?type=RECEIPT&party=${customer.id}`}
                                    className="px-3 py-1.5 rounded-lg bg-muted/70 hover:bg-muted text-foreground text-xs font-semibold border border-border/50 transition-colors flex items-center gap-1 min-h-[34px]"
                                  >
                                    <span>Record Receipt</span>
                                  </Link>
                                )}

                                <Link
                                  href={`/parties/${customer.id}/statement`}
                                  className="px-2.5 py-1.5 rounded-lg bg-muted/60 hover:bg-muted text-foreground text-xs font-semibold border border-border transition-colors flex items-center gap-1 min-h-[34px]"
                                  title="View Customer Statement"
                                >
                                  <span>Statement</span>
                                  <ArrowUpRight className="w-3.5 h-3.5" />
                                </Link>

                                <Link
                                  href={`/parties/${customer.id}/edit`}
                                  className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted border border-border/40 transition-colors min-h-[34px] min-w-[34px] flex items-center justify-center"
                                  title="Edit Customer"
                                >
                                  <Edit2 className="w-3.5 h-3.5" />
                                </Link>
                              </div>
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

        {/* Edit Sales Invoice Modal */}
        <EditSalesInvoiceModal
          isOpen={isEditModalOpen}
          onClose={() => {
            setIsEditModalOpen(false);
            setEditingVoucher(null);
          }}
          voucher={editingVoucher}
          onUpdateSuccess={fetchInvoices}
        />

        {/* GST E-Way Bill Modal */}
        <EWayBillModal
          isOpen={isEwayModalOpen}
          onClose={() => {
            setIsEwayModalOpen(false);
            setEwayVoucher(null);
          }}
          voucher={ewayVoucher}
          companyId={activeCompanyId || undefined}
          onSuccess={() => fetchInvoices(page)}
        />

        {/* Confirm Delete Modal */}
        <ConfirmModal
          isOpen={deleteConfirmParams !== null}
          onClose={() => setDeleteConfirmParams(null)}
          onConfirm={() => {
            if (deleteConfirmParams) {
              executeDelete(deleteConfirmParams.id);
            }
          }}
          title="Delete Sales Invoice?"
          description={
            <span>
              Are you sure you want to permanently delete Sales Invoice{" "}
              <strong className="text-foreground">#{deleteConfirmParams?.number}</strong>?
              This will cancel the voucher, reverse the customer ledger entry, restore deducted inventory stock, and reverse GST liability.
            </span>
          }
          confirmText="Delete & Reverse"
          variant="danger"
        />
      </div>
    </DashboardLayout>
  );
}

export default function SalesInvoiceList() {
  return (
    <React.Suspense fallback={
      <DashboardLayout>
        <div className="flex flex-col items-center justify-center min-h-[60vh] gap-3">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <span className="text-sm font-medium text-muted-foreground">Loading sales...</span>
        </div>
      </DashboardLayout>
    }>
      <SalesInvoiceListContent />
    </React.Suspense>
  );
}
