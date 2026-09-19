"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import { useToast } from '@/context/ToastContext';
import { useCompany } from '@/context/CompanyContext';
import { useFinancialYear } from '@/context/FinancialYearContext';
import ConfirmModal from '@/components/modals/ConfirmModal';
import { 
  Plus, 
  Search, 
  Printer, 
  Trash2, 
  ArrowRight, 
  CheckCircle2, 
  FileText, 
  Clock, 
  ChevronLeft, 
  ChevronRight,
  TrendingUp,
  Receipt,
  Sparkles,
  ExternalLink,
  Loader2,
  Calendar
} from 'lucide-react';

export default function ProformaQuotationListPage() {
  const router = useRouter();
  const { toast } = useToast();
  const { companyId: activeCompanyId } = useCompany();
  const { activeFY } = useFinancialYear();

  const [proformas, setProformas] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [metrics, setMetrics] = useState<any>(null);
  const [page, setPage] = useState<number>(1);
  const [totalCount, setTotalCount] = useState<number>(0);
  const pageSize = 50;

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [typeFilter, setTypeFilter] = useState('ALL');

  // 1-Click Convert State
  const [convertingId, setConvertingId] = useState<string | null>(null);
  const [convertModalDoc, setConvertModalDoc] = useState<any | null>(null);
  const [converting, setConverting] = useState(false);

  // Delete Confirm
  const [deleteConfirmDoc, setDeleteConfirmDoc] = useState<any | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login');
      return;
    }
    fetchProformas(1);
  }, [router, activeCompanyId, statusFilter, typeFilter, activeFY?.id]);

  const fetchProformas = useCallback(async (targetPage: number = page) => {
    setLoading(true);
    try {
      let companyId = activeCompanyId;
      if (!companyId && typeof window !== 'undefined') {
        companyId = localStorage.getItem('vouch_active_company_id') || '';
      }
      if (!companyId) return;

      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      const params = new URLSearchParams();
      params.append('limit', String(pageSize));
      params.append('offset', String((targetPage - 1) * pageSize));
      if (statusFilter !== 'ALL') params.append('status', statusFilter);
      if (typeFilter !== 'ALL') params.append('type', typeFilter);
      if (searchQuery.trim()) params.append('search', searchQuery.trim());
      if (activeFY?.start_date) params.append('start_date', activeFY.start_date);
      if (activeFY?.end_date) params.append('end_date', activeFY.end_date);

      const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/proforma/${companyId}/?${params.toString()}`, { headers });
      if (res.data?.success) {
        setProformas(res.data.data || []);
        setTotalCount(res.data.total_count || 0);
        setMetrics(res.data.metrics || null);
        setPage(targetPage);
      }
    } catch (err: any) {
      console.error(err);
      toast.error('Failed to load documents', err.response?.data?.error || err.message);
    } finally {
      setLoading(false);
    }
  }, [activeCompanyId, statusFilter, typeFilter, searchQuery, activeFY, page, toast]);

  const handleConvert = async (doc: any) => {
    if (doc.status === 'CONVERTED') {
      toast.error('Already Converted', 'This document has already been converted to a GST Tax Invoice.');
      return;
    }

    setConverting(true);
    setConvertingId(doc.id);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      const res = await axios.post(`${API_BASE_URL}/api/v1/accounting/proforma/${doc.id}/convert/`, {}, { headers });
      if (res.data?.success) {
        toast.success(
          'Converted to GST Invoice!',
          `Generated Tax Invoice: ${res.data.data?.voucher_number || 'INV'}`
        );
        setConvertModalDoc(null);
        fetchProformas(page);
      }
    } catch (err: any) {
      console.error(err);
      toast.error('Conversion Failed', err.response?.data?.error || err.message);
    } finally {
      setConverting(false);
      setConvertingId(null);
    }
  };

  const handleDelete = async () => {
    if (!deleteConfirmDoc) return;
    setDeleting(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      await axios.delete(`${API_BASE_URL}/api/v1/accounting/proforma/detail/${deleteConfirmDoc.id}/`, { headers });
      toast.success('Document Deleted', `${deleteConfirmDoc.proforma_number} has been removed.`);
      setDeleteConfirmDoc(null);
      fetchProformas(page);
    } catch (err: any) {
      toast.error('Delete Failed', err.response?.data?.error || err.message);
    } finally {
      setDeleting(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

  return (
    <DashboardLayout>
      <div className="max-w-7xl mx-auto space-y-6 pb-12">
        {/* Header Section */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-border pb-5">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold tracking-tight text-foreground">
                Proforma Invoices &amp; Quotations
              </h1>
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
                1-Click GST Conversion
              </span>
            </div>
            <p className="text-sm text-muted-foreground mt-1">
              Create commercial estimates, price quotes, and convert them to official GST Tax Invoices in 1-click.
            </p>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <Link
              href="/sales"
              className="px-3 py-2 text-xs font-medium rounded-xl border border-border bg-card hover:bg-muted/70 text-foreground transition-colors flex items-center gap-1.5"
            >
              <Receipt className="w-3.5 h-3.5 text-muted-foreground" />
              <span>View GST Sales</span>
            </Link>

            <Link
              href="/sales/proforma/new?type=QUOTATION"
              className="px-3.5 py-2 text-xs font-semibold rounded-xl border border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400 hover:bg-blue-500/20 transition-colors flex items-center gap-1.5 cursor-pointer shadow-xs"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>+ New Quotation</span>
            </Link>

            <Link
              href="/sales/proforma/new?type=PROFORMA"
              className="px-4 py-2 text-xs font-bold rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground transition-colors flex items-center gap-1.5 cursor-pointer shadow-sm"
            >
              <Plus className="w-4 h-4" />
              <span>+ New Proforma Invoice</span>
            </Link>
          </div>
        </div>

        {/* 3 Metric Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {/* Card 1: Total Documents */}
          <div className="p-5 bg-card rounded-2xl border border-border/80 shadow-xs space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Total Estimates &amp; Quotes</span>
              <span className="p-2 bg-muted text-muted-foreground rounded-xl border border-border/60">
                <FileText className="w-4 h-4" />
              </span>
            </div>
            <div>
              <div className="text-3xl font-black text-foreground font-mono">
                {metrics?.total_count ?? 0}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                Value: <span className="font-semibold text-foreground font-mono">₹{(metrics?.total_amount ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
              </div>
            </div>
            <div className="text-[11px] text-muted-foreground flex items-center gap-1">
              <span>Includes draft, sent, and converted documents</span>
            </div>
          </div>

          {/* Card 2: Active / Pending Quotes */}
          <div className="p-5 bg-card rounded-2xl border border-blue-500/30 bg-gradient-to-br from-card via-card to-blue-500/5 shadow-xs space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Pending Orders / Quotes</span>
              <span className="p-2 bg-blue-500/10 text-blue-600 dark:text-blue-400 rounded-xl border border-blue-500/20">
                <Clock className="w-4 h-4" />
              </span>
            </div>
            <div>
              <div className="text-3xl font-black text-blue-600 dark:text-blue-400 font-mono">
                {metrics?.active_count ?? 0}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                Pipeline Value: <span className="font-semibold text-foreground font-mono">₹{(metrics?.active_amount ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
              </div>
            </div>
            <div className="inline-flex items-center gap-1 text-[11px] font-medium text-blue-700 dark:text-blue-300 bg-blue-500/10 px-2 py-0.5 rounded-md">
              Ready to convert to GST Invoice
            </div>
          </div>

          {/* Card 3: Converted to GST Invoices */}
          <div className="p-5 bg-card rounded-2xl border border-emerald-500/30 bg-gradient-to-br from-card via-card to-emerald-500/5 shadow-xs space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Converted to GST Tax Invoices</span>
              <span className="p-2 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded-xl border border-emerald-500/20">
                <CheckCircle2 className="w-4 h-4" />
              </span>
            </div>
            <div>
              <div className="text-3xl font-black text-emerald-600 dark:text-emerald-400 font-mono">
                {metrics?.converted_count ?? 0}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                Revenue Converted: <span className="font-semibold text-foreground font-mono">₹{(metrics?.converted_amount ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
              </div>
            </div>
            <div className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-700 dark:text-emerald-300 bg-emerald-500/10 px-2 py-0.5 rounded-md">
              ✓ 100% posted to accounting &amp; GST returns
            </div>
          </div>
        </div>

        {/* Filter & Search Bar */}
        <div className="bg-card border border-border rounded-2xl p-4 shadow-xs space-y-3">
          <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
            {/* Search Input */}
            <div className="relative flex-1 w-full">
              <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search by quote / proforma #, customer, GSTIN, amount..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') fetchProformas(1);
                }}
                className="w-full pl-9 pr-4 py-2 bg-background border border-border rounded-xl text-xs text-foreground placeholder:text-muted-foreground focus:outline-hidden focus:ring-2 focus:ring-primary/30"
              />
            </div>

            {/* Type Filter */}
            <div className="flex items-center gap-1 bg-muted/40 p-1 rounded-xl border border-border text-xs self-stretch sm:self-auto">
              <button
                type="button"
                onClick={() => setTypeFilter('ALL')}
                className={`px-3 py-1.5 rounded-lg font-semibold transition-colors cursor-pointer ${
                  typeFilter === 'ALL' ? 'bg-card text-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                All Types
              </button>
              <button
                type="button"
                onClick={() => setTypeFilter('PROFORMA')}
                className={`px-3 py-1.5 rounded-lg font-semibold transition-colors cursor-pointer ${
                  typeFilter === 'PROFORMA' ? 'bg-card text-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                Proforma (PI)
              </button>
              <button
                type="button"
                onClick={() => setTypeFilter('QUOTATION')}
                className={`px-3 py-1.5 rounded-lg font-semibold transition-colors cursor-pointer ${
                  typeFilter === 'QUOTATION' ? 'bg-card text-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                Quotations (QTN)
              </button>
            </div>

            {/* Status Filter */}
            <div className="flex items-center gap-1 bg-muted/40 p-1 rounded-xl border border-border text-xs self-stretch sm:self-auto">
              <button
                type="button"
                onClick={() => setStatusFilter('ALL')}
                className={`px-3 py-1.5 rounded-lg font-semibold transition-colors cursor-pointer ${
                  statusFilter === 'ALL' ? 'bg-card text-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                All Status
              </button>
              <button
                type="button"
                onClick={() => setStatusFilter('DRAFT')}
                className={`px-3 py-1.5 rounded-lg font-semibold transition-colors cursor-pointer ${
                  statusFilter === 'DRAFT' ? 'bg-card text-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                Draft
              </button>
              <button
                type="button"
                onClick={() => setStatusFilter('CONVERTED')}
                className={`px-3 py-1.5 rounded-lg font-semibold transition-colors cursor-pointer ${
                  statusFilter === 'CONVERTED' ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                Converted
              </button>
            </div>
          </div>
        </div>

        {/* Documents Table */}
        <div className="bg-card border border-border rounded-2xl overflow-hidden shadow-xs">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border bg-muted/20 text-muted-foreground font-semibold text-[11px] uppercase tracking-wider">
                  <th className="py-3 px-4">Type &amp; Doc #</th>
                  <th className="py-3 px-4">Date</th>
                  <th className="py-3 px-4">Customer / Buyer</th>
                  <th className="py-3 px-4 text-right">Taxable (₹)</th>
                  <th className="py-3 px-4 text-right">Total Amount (₹)</th>
                  <th className="py-3 px-4 text-center">Status</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {loading ? (
                  <tr>
                    <td colSpan={7} className="py-12 text-center text-muted-foreground">
                      <div className="flex flex-col items-center justify-center gap-2">
                        <Loader2 className="w-6 h-6 animate-spin text-primary" />
                        <span>Loading proforma invoices &amp; quotations...</span>
                      </div>
                    </td>
                  </tr>
                ) : proformas.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-12 text-center text-muted-foreground">
                      <div className="flex flex-col items-center justify-center gap-3">
                        <div className="w-12 h-12 rounded-2xl bg-muted flex items-center justify-center text-muted-foreground border border-border">
                          <FileText className="w-6 h-6" />
                        </div>
                        <div className="font-semibold text-foreground text-sm">No Proforma Invoices or Quotations Found</div>
                        <p className="text-xs text-muted-foreground max-w-sm">
                          Create your first quotation or proforma invoice to send commercial quotes to clients and convert them to GST invoices in 1-click.
                        </p>
                        <div className="flex items-center gap-2 pt-2">
                          <Link
                            href="/sales/proforma/new?type=PROFORMA"
                            className="px-3.5 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-semibold"
                          >
                            + Create Proforma
                          </Link>
                          <Link
                            href="/sales/proforma/new?type=QUOTATION"
                            className="px-3.5 py-1.5 bg-muted text-foreground hover:bg-muted/80 rounded-lg text-xs font-semibold"
                          >
                            + Create Quotation
                          </Link>
                        </div>
                      </div>
                    </td>
                  </tr>
                ) : (
                  proformas.map((doc: any) => {
                    const isConverted = doc.status === 'CONVERTED';
                    const isPI = doc.proforma_type === 'PROFORMA';

                    return (
                      <tr
                        key={doc.id}
                        className="hover:bg-muted/30 transition-colors cursor-pointer group"
                        onClick={() => router.push(`/sales/proforma/${doc.id}`)}
                      >
                        {/* Doc Number & Type */}
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                              isPI 
                                ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20'
                                : 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20'
                            }`}>
                              {isPI ? 'PI' : 'QTN'}
                            </span>
                            <span className="font-mono font-bold text-foreground text-xs group-hover:text-primary transition-colors">
                              {doc.proforma_number}
                            </span>
                          </div>
                        </td>

                        {/* Date & Valid until */}
                        <td className="py-3 px-4 font-mono text-muted-foreground text-xs">
                          <div>{doc.date}</div>
                          {doc.valid_until && (
                            <div className="text-[10px] text-muted-foreground font-sans">
                              Valid: {doc.valid_until}
                            </div>
                          )}
                        </td>

                        {/* Customer / Party */}
                        <td className="py-3 px-4">
                          <div className="font-medium text-foreground text-xs">
                            {doc.party_name || doc.buyer_name || 'Customer'}
                          </div>
                          {doc.buyer_gstin ? (
                            <div className="text-[10px] font-mono text-muted-foreground">
                              GSTIN: {doc.buyer_gstin}
                            </div>
                          ) : (
                            <div className="text-[10px] text-muted-foreground">
                              Unregistered / Consumer
                            </div>
                          )}
                        </td>

                        {/* Taxable Amount */}
                        <td className="py-3 px-4 text-right font-mono text-muted-foreground">
                          ₹{Number(doc.taxable_amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>

                        {/* Total Amount */}
                        <td className="py-3 px-4 text-right font-mono font-bold text-foreground text-xs">
                          ₹{Number(doc.total_amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>

                        {/* Status Badge */}
                        <td className="py-3 px-4 text-center">
                          {isConverted ? (
                            <div className="inline-flex flex-col items-center">
                              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                                <CheckCircle2 className="w-3 h-3" />
                                <span>CONVERTED</span>
                              </span>
                              {doc.converted_voucher_number && (
                                <span className="text-[10px] font-mono text-muted-foreground mt-0.5">
                                  {doc.converted_voucher_number}
                                </span>
                              )}
                            </div>
                          ) : doc.status === 'ACCEPTED' ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
                              ACCEPTED
                            </span>
                          ) : doc.status === 'SENT' ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                              SENT
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-muted text-muted-foreground border border-border">
                              DRAFT
                            </span>
                          )}
                        </td>

                        {/* Actions */}
                        <td className="py-3 px-4 text-right" onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center justify-end gap-1.5">
                            {/* 1-Click Convert Button */}
                            {!isConverted ? (
                              <button
                                type="button"
                                onClick={() => setConvertModalDoc(doc)}
                                disabled={convertingId === doc.id}
                                className="px-3 py-1.5 rounded-lg text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white shadow-xs transition-colors flex items-center gap-1 cursor-pointer"
                                title="1-Click Convert to GST Tax Invoice"
                              >
                                {convertingId === doc.id ? (
                                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                ) : (
                                  <Sparkles className="w-3.5 h-3.5 text-amber-300" />
                                )}
                                <span>Convert to GST</span>
                              </button>
                            ) : (
                              <Link
                                href={`/sales`}
                                className="px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-muted/60 text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1"
                                title="View in Sales Invoices"
                              >
                                <span>View GST</span>
                                <ExternalLink className="w-3 h-3" />
                              </Link>
                            )}

                            {/* View / Print */}
                            <Link
                              href={`/sales/proforma/${doc.id}`}
                              className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted/70 rounded-lg transition-colors"
                              title="View / Print Document"
                            >
                              <Printer className="w-4 h-4" />
                            </Link>

                            {/* Delete button (only if not converted) */}
                            {!isConverted && (
                              <button
                                type="button"
                                onClick={() => setDeleteConfirmDoc(doc)}
                                className="p-1.5 text-muted-foreground hover:text-rose-500 hover:bg-rose-500/10 rounded-lg transition-colors cursor-pointer"
                                title="Delete Estimate"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination Footer */}
          {totalPages > 1 && (
            <div className="px-4 py-3 border-t border-border bg-muted/10 flex items-center justify-between text-xs text-muted-foreground">
              <div>
                Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, totalCount)} of {totalCount} documents
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => fetchProformas(page - 1)}
                  disabled={page <= 1}
                  className="p-1.5 rounded-lg border border-border bg-card hover:bg-muted disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span className="font-mono font-medium text-foreground">
                  Page {page} of {totalPages}
                </span>
                <button
                  onClick={() => fetchProformas(page + 1)}
                  disabled={page >= totalPages}
                  className="p-1.5 rounded-lg border border-border bg-card hover:bg-muted disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Convert to GST Invoice Confirmation Modal */}
      {convertModalDoc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in">
          <div className="bg-card border border-border rounded-2xl shadow-2xl max-w-md w-full p-6 space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center border border-emerald-500/20">
                <Sparkles className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-foreground">1-Click Convert to GST Invoice</h3>
                <p className="text-xs text-muted-foreground">
                  Convert {convertModalDoc.proforma_type === 'PROFORMA' ? 'Proforma' : 'Quotation'} {convertModalDoc.proforma_number}
                </p>
              </div>
            </div>

            <div className="p-3 bg-muted/30 border border-border/60 rounded-xl text-xs space-y-2">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Customer:</span>
                <span className="font-semibold text-foreground">{convertModalDoc.party_name || convertModalDoc.buyer_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Total Invoice Value:</span>
                <span className="font-mono font-bold text-foreground">₹{Number(convertModalDoc.total_amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">GST Tax Amount:</span>
                <span className="font-mono text-emerald-600 dark:text-emerald-400 font-semibold">₹{Number(convertModalDoc.total_tax || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
              </div>
            </div>

            <p className="text-xs text-muted-foreground leading-relaxed">
              This will generate the next official <strong>GST Sales Tax Invoice</strong>, post double-entry ledger entries, adjust inventory, and record the tax liability for GSTR-1 &amp; GSTR-3B.
            </p>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setConvertModalDoc(null)}
                disabled={converting}
                className="px-4 py-2 text-xs font-semibold rounded-xl border border-border bg-card hover:bg-muted text-foreground transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => handleConvert(convertModalDoc)}
                disabled={converting}
                className="px-4 py-2 text-xs font-bold rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
              >
                {converting ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Converting...</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-4 h-4" />
                    <span>Confirm &amp; Generate GST Invoice</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteConfirmDoc && (
        <ConfirmModal
          isOpen={true}
          title="Delete Proforma / Quotation"
          description={`Are you sure you want to delete ${deleteConfirmDoc.proforma_number}? This estimate will be permanently removed.`}
          confirmText="Delete"
          isLoading={deleting}
          onConfirm={handleDelete}
          onClose={() => setDeleteConfirmDoc(null)}
          variant="danger"
        />
      )}
    </DashboardLayout>
  );
}
