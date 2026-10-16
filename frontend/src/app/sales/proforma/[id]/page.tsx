"use client";
import React, { useEffect, useState, useCallback, useMemo } from 'react';
import axios from 'axios';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import { api, API_BASE_URL } from '@/utils/api';
import DashboardLayout from '@/components/DashboardLayout';
import { useToast } from '@/context/ToastContext';
import ProformaDocumentSheet from '@/components/documents/ProformaDocumentSheet';
import { 
  ArrowLeft, 
  Printer, 
  Sparkles, 
  CheckCircle2, 
  Download, 
  Loader2, 
  ExternalLink,
  Send,
  MessageCircle,
  Copy,
  Check,
  ShieldCheck,
  Image as ImageIcon,
  Building2,
  Pencil,
  Tag,
  ArrowUpDown,
} from 'lucide-react';

export default function ProformaDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { toast } = useToast();
  const docId = params?.id as string;

  const [doc, setDoc] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [converting, setConverting] = useState(false);
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [isGeneratingPdf, setIsGeneratingPdf] = useState(false);
  const [copiedLink, setCopiedLink] = useState(false);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [isGeneratingShareLink, setIsGeneratingShareLink] = useState(false);
  const [includeWatermark, setIncludeWatermark] = useState<boolean>(true);
  const [includeLogo, setIncludeLogo] = useState<boolean>(true);
  const [firmNameSize, setFirmNameSize] = useState<'large' | 'extra_large' | 'normal'>('large');
  const [showBrand, setShowBrand] = useState<boolean>(() => {
    if (typeof window !== 'undefined') {
      const val = localStorage.getItem('vouch_show_brand_in_proforma');
      return val !== null ? val === 'true' : true;
    }
    return true;
  });

  const fetchDoc = useCallback(async () => {
    if (!docId) return;
    setLoading(true);
    try {
      const activeCompanyId = typeof window !== 'undefined' 
        ? localStorage.getItem('current_company_id') || localStorage.getItem('vouch_active_company_id')
        : null;
      const headers: Record<string, string> = {};
      if (activeCompanyId) {
        headers['X-Company-ID'] = activeCompanyId;
      }
      const res = await api.get(`/api/v1/accounting/proforma/detail/${docId}/`, { headers });
      if (res.data?.success) {
        setDoc(res.data.data);
      }
    } catch (err: any) {
      console.error(err);
      const errorMsg =
        err.response?.data?.error ||
        err.response?.data?.message ||
        (err.response?.status === 403
          ? 'Permission denied. Please ensure you have access to this company.'
          : 'Failed to load document.');
      toast.error('Failed to load document', errorMsg);
    } finally {
      setLoading(false);
    }
  }, [docId, toast]);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login');
      return;
    }
    fetchDoc();
  }, [router, fetchDoc]);

  useEffect(() => {
    if (typeof document !== 'undefined') {
      if (doc?.doc_number) {
        document.title = `${doc.document_type === 'ESTIMATE' ? 'Quotation / Estimate' : 'Proforma Invoice'} ${doc.doc_number} | SriLekh`;
      } else {
        document.title = 'Proforma Invoice | SriLekh';
      }
    }
  }, [doc]);

  const handleConvert = async () => {
    if (!doc || doc.status === 'CONVERTED') return;
    setConverting(true);
    try {
      const activeCompanyId = typeof window !== 'undefined' 
        ? localStorage.getItem('current_company_id') || localStorage.getItem('vouch_active_company_id')
        : null;
      const headers: Record<string, string> = {};
      if (activeCompanyId) {
        headers['X-Company-ID'] = activeCompanyId;
      }
      const res = await api.post(`/api/v1/accounting/proforma/${doc.id}/convert/`, {}, { headers });
      if (res.data?.success) {
        toast.success(
          'Converted to GST Tax Invoice!',
          `Generated Tax Invoice #${res.data.data?.voucher_number || 'INV'}`
        );
        fetchDoc();
      }
    } catch (err: any) {
      console.error(err);
      const errorMsg =
        err.response?.data?.error ||
        err.response?.data?.message ||
        (err.response?.status === 403
          ? 'Permission denied. Please ensure you have access to this company.'
          : 'Failed to convert document.');
      toast.error('Conversion Failed', errorMsg);
    } finally {
      setConverting(false);
    }
  };

  const handleUpdateStatus = async (newStatus: string) => {
    if (!doc || doc.status === 'CONVERTED') return;
    setUpdatingStatus(true);
    try {
      const activeCompanyId = typeof window !== 'undefined' 
        ? localStorage.getItem('current_company_id') || localStorage.getItem('vouch_active_company_id')
        : null;
      const headers: Record<string, string> = {};
      if (activeCompanyId) {
        headers['X-Company-ID'] = activeCompanyId;
      }
      await api.put(`/api/v1/accounting/proforma/detail/${doc.id}/`, { status: newStatus }, { headers });
      toast.success('Status Updated', `Document marked as ${newStatus}`);
      fetchDoc();
    } catch (err: any) {
      console.error(err);
      const errorMsg =
        err.response?.data?.error ||
        err.response?.data?.message ||
        (err.response?.status === 403
          ? 'Permission denied. Please ensure you have access to this company.'
          : 'Failed to update status.');
      toast.error('Failed to update status', errorMsg);
    } finally {
      setUpdatingStatus(false);
    }
  };

  const [isSorting, setIsSorting] = useState(false);

  const handleSort = async (sortAction: 'sort_ascending' | 'sort_descending') => {
    if (!doc || doc.status === 'CONVERTED') return;
    setIsSorting(true);
    try {
      const activeCompanyId = typeof window !== 'undefined' 
        ? localStorage.getItem('current_company_id') || localStorage.getItem('vouch_active_company_id')
        : null;
      const headers: Record<string, string> = {};
      if (activeCompanyId) {
        headers['X-Company-ID'] = activeCompanyId;
      }
      const res = await api.put(`/api/v1/accounting/proforma/detail/${doc.id}/`, { action: sortAction }, { headers });
      if (res.data?.success) {
        const isDesc = sortAction === 'sort_descending';
        toast.success('Items Sorted', `Items arranged in ${isDesc ? 'descending (Z → A)' : 'ascending (A → Z)'} order.`);
        if (res.data.data) {
          setDoc(res.data.data);
        } else {
          fetchDoc();
        }
      }
    } catch (err: any) {
      console.error(err);
      toast.error('Failed to sort items', err.response?.data?.error || 'An error occurred while sorting items.');
    } finally {
      setIsSorting(false);
    }
  };

  const isConverted = doc?.status === 'CONVERTED';
  const isPI = (doc?.proforma_type || 'PROFORMA') === 'PROFORMA';
  const company = doc?.company_details || {};
  const totalAmount = Number(doc?.total_amount || 0);

  // High-Resolution Direct Vector PDF Stream from Backend (Lightweight ~74KB, 100% Vector, Instant)
  const handleDownloadPdf = async () => {
    if (!doc) return;
    setIsGeneratingPdf(true);

    try {
      const cleanFilename = `${(doc.proforma_number || 'PROFORMA').replace(/[/\\:*?"<>|]/g, '-').trim()}.pdf`;
      const wmParam = includeWatermark ? '1' : '0';
      const logoParam = includeLogo ? '1' : '0';
      const brandParam = showBrand ? '1' : '0';

      const response = await api.get(
        `/api/v1/documents/proforma/${doc.id}/pdf/?download=1&watermark=${wmParam}&logo=${logoParam}&brand=${brandParam}&fresh=1`,
        { responseType: 'blob' }
      );

      const blobUrl = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = cleanFilename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(blobUrl);

      toast.success('PDF Downloaded', `Saved as ${cleanFilename}`);
    } catch (err: any) {
      console.error('PDF Export Error:', err);
      toast.error('Download Failed', err?.response?.data?.error || err?.message || 'Could not download official PDF.');
    } finally {
      setIsGeneratingPdf(false);
    }
  };

  const handleGenerateShareLink = async (): Promise<string> => {
    if (shareUrl) return shareUrl;
    setIsGeneratingShareLink(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.post(
        `${API_BASE_URL}/api/v1/documents/proforma/${doc!.id}/share/`,
        { expires_in_days: 30 },
        { headers }
      );
      const url: string = res.data.share_url || '';
      setShareUrl(url);
      return url;
    } catch (err: any) {
      console.error('Share link error:', err);
      toast.error('Share Link Failed', err.response?.data?.error || 'Could not generate a public share link.');
      return '';
    } finally {
      setIsGeneratingShareLink(false);
    }
  };

  const handleCopyLink = async () => {
    const url = await handleGenerateShareLink();
    if (!url) return;
    navigator.clipboard.writeText(url);
    setCopiedLink(true);
    setTimeout(() => setCopiedLink(false), 2000);
    toast.success('Public Link Copied', 'Anyone with this link can view the document (valid 30 days)');
  };

  const handleShareWhatsApp = async () => {
    if (!doc) return;
    const docTitle = isPI ? 'Proforma Invoice' : 'Commercial Quotation';
    const partyName = doc.buyer_name || doc.party_name || 'Valued Customer';
    const amountStr = totalAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 });
    
    let rawPhone = (doc.buyer_phone || '').replace(/[^0-9]/g, '');
    if (rawPhone.length === 10) rawPhone = '91' + rawPhone;

    const publicUrl = await handleGenerateShareLink();
    const shareLink = publicUrl || (typeof window !== 'undefined' ? window.location.href : '');

    const message = 
      `*${docTitle.toUpperCase()} - ${company.name || 'Our Company'}*\n\n` +
      `Dear *${partyName}*,\n` +
      `Please find the commercial estimate for your order:\n\n` +
      `📄 *Doc No:* ${doc.proforma_number}\n` +
      `📅 *Date:* ${doc.date}\n` +
      (doc.valid_until ? `⏳ *Valid Until:* ${doc.valid_until}\n` : '') +
      `💰 *Total Amount:* ₹${amountStr}\n\n` +
      `View & Download Document (public link):\n${shareLink}\n\n` +
      `*Note:* This is a Proforma Invoice / Commercial Quotation and NOT a GST Tax Invoice.`;

    const waUrl = rawPhone
      ? `https://wa.me/${rawPhone}?text=${encodeURIComponent(message)}`
      : `https://wa.me/?text=${encodeURIComponent(message)}`;

    window.open(waUrl, '_blank');
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="py-24 flex flex-col items-center justify-center gap-3">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground font-medium">Loading document preview...</p>
        </div>
      </DashboardLayout>
    );
  }

  if (!doc) {
    return (
      <DashboardLayout>
        <div className="py-24 text-center space-y-4">
          <h2 className="text-xl font-bold text-foreground">Document Not Found</h2>
          <p className="text-xs text-muted-foreground max-w-sm mx-auto">
            The requested proforma invoice or quotation could not be located.
          </p>
          <Link href="/sales/proforma" className="px-4 py-2 bg-primary text-primary-foreground text-xs font-semibold rounded-xl inline-block">
            Back to Proforma List
          </Link>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      {/* Strict Print CSS for exact A4 physical printing */}
      <style>{`
        @media print {
          @page {
            size: A4 portrait;
            margin: 0;
          }
          *, *::before, *::after {
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
            color-adjust: exact !important;
          }
          html, body {
            margin: 0 !important;
            padding: 0 !important;
            background: #ffffff !important;
            color: #0f172a !important;
            width: 210mm !important;
          }
          header, nav, aside, [role="navigation"], .print\\:hidden {
            display: none !important;
          }
          main, main > div, .max-w-5xl, .w-full {
            margin: 0 !important;
            padding: 0 !important;
            width: 100% !important;
            max-width: 100% !important;
            overflow: visible !important;
            background: #ffffff !important;
          }
          .proforma-page-sheet {
            box-sizing: border-box !important;
            width: 100% !important;
            min-width: 100% !important;
            max-width: 100% !important;
            height: 100vh !important;
            max-height: 100vh !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 8mm 10mm !important;
            box-shadow: none !important;
            border: none !important;
            border-radius: 0 !important;
            background-color: #ffffff !important;
            page-break-inside: avoid !important;
            break-inside: avoid !important;
            overflow: hidden !important;
          }
          .proforma-page-sheet:not(:last-child) {
            page-break-after: always !important;
            break-after: page !important;
          }
          .proforma-page-sheet:last-child {
            page-break-after: auto !important;
            break-after: auto !important;
          }
        }
      `}</style>

      <div className="max-w-5xl mx-auto space-y-4 pb-20 print:p-0 print:m-0 print:pb-0 print:space-y-0">
        
        {/* Action Header (Hidden in Print) */}
        <div className="print:hidden bg-card border border-border rounded-2xl p-4 shadow-sm space-y-3.5">
          
          {/* Top Row: Title & Primary Actions */}
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-3">
            <div className="flex items-center gap-3">
              <Link
                href="/sales/proforma"
                className="p-2 rounded-xl bg-muted/60 hover:bg-muted border border-border text-muted-foreground hover:text-foreground transition-all cursor-pointer"
                title="Back to Proformas & Quotations"
              >
                <ArrowLeft className="w-4 h-4" />
              </Link>
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`px-2 py-0.5 rounded text-[10.5px] font-black uppercase tracking-wider ${
                    isPI ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20' : 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20'
                  }`}>
                    {isPI ? 'PROFORMA' : 'QUOTATION'}
                  </span>
                  <h1 className="text-base font-black text-foreground font-mono">
                    {doc.proforma_number}
                  </h1>
                  <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold ${
                    isConverted 
                      ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                      : doc.status === 'ACCEPTED'
                      ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20'
                      : doc.status === 'SENT'
                      ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20'
                      : 'bg-muted text-muted-foreground border border-border'
                  }`}>
                    {doc.status}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Issued on <strong className="text-foreground">{doc.date}</strong> {doc.created_by ? `by ${doc.created_by}` : ''}
                </p>
              </div>
            </div>

            {/* Main Action Buttons */}
            <div className="flex items-center gap-2 flex-wrap w-full md:w-auto justify-end">
              {!isConverted ? (
                <button
                  type="button"
                  onClick={handleConvert}
                  disabled={converting}
                  className="px-3.5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold transition-all shadow-xs flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                  title="Convert this quotation to a GST Tax Invoice"
                >
                  {converting ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Sparkles className="w-3.5 h-3.5 text-amber-300" />
                  )}
                  <span>Convert to Invoice</span>
                </button>
              ) : (
                <Link
                  href="/sales"
                  className="px-3 py-1.5 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30 rounded-xl text-xs font-bold transition-colors flex items-center gap-1.5"
                >
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                  <span>Invoice #{doc.converted_voucher_number || 'INV'}</span>
                  <ExternalLink className="w-3 h-3" />
                </Link>
              )}

              {!isConverted && (
                <Link
                  href={`/sales/proforma/new?edit=${doc.id}`}
                  className="px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-bold transition-all shadow-xs flex items-center gap-1.5 cursor-pointer"
                  title="Edit Proforma / Quotation"
                >
                  <Pencil className="w-3.5 h-3.5" />
                  <span>Edit</span>
                </Link>
              )}

              <button
                type="button"
                onClick={() => window.print()}
                className="px-3 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl text-xs font-bold transition-colors flex items-center gap-1.5 cursor-pointer shadow-xs"
                title="Print Document"
              >
                <Printer className="w-3.5 h-3.5" />
                <span>Print</span>
              </button>

              <button
                type="button"
                onClick={handleDownloadPdf}
                disabled={isGeneratingPdf}
                className="px-3 py-2 bg-slate-900 hover:bg-slate-800 text-white dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white rounded-xl text-xs font-bold transition-colors flex items-center gap-1.5 cursor-pointer shadow-xs disabled:opacity-50"
                title="Download PDF"
              >
                {isGeneratingPdf ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Download className="w-3.5 h-3.5" />
                )}
                <span>Download PDF</span>
              </button>

              <div className="flex items-center gap-1 pl-1">
                <button
                  type="button"
                  onClick={handleShareWhatsApp}
                  className="p-2 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 rounded-xl transition-colors cursor-pointer"
                  title="Share on WhatsApp"
                >
                  <MessageCircle className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  onClick={handleCopyLink}
                  disabled={isGeneratingShareLink}
                  className="p-2 bg-muted hover:bg-muted/80 border border-border text-foreground rounded-xl transition-colors cursor-pointer disabled:opacity-50"
                  title={shareUrl ? 'Copy Public Share Link' : 'Generate & Copy Share Link'}
                >
                  {isGeneratingShareLink ? (
                    <Loader2 className="w-4 h-4 text-muted-foreground animate-spin" />
                  ) : copiedLink ? (
                    <Check className="w-4 h-4 text-emerald-500" />
                  ) : (
                    <Copy className="w-4 h-4 text-muted-foreground" />
                  )}
                </button>
              </div>
            </div>
          </div>

          {/* Bottom Row: Document Settings & Sorting Bar */}
          <div className="pt-3 border-t border-border flex flex-col md:flex-row justify-between items-start md:items-center gap-2.5 text-xs">
            {/* Display Toggles */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">Display:</span>
              <button
                type="button"
                onClick={() => setIncludeWatermark(!includeWatermark)}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all flex items-center gap-1 cursor-pointer border ${
                  includeWatermark
                    ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/30'
                    : 'bg-muted/40 text-muted-foreground hover:text-foreground border-border'
                }`}
                title="Toggle Watermark"
              >
                <ShieldCheck className="w-3 h-3" />
                <span>Watermark {includeWatermark ? 'ON' : 'OFF'}</span>
              </button>

              <button
                type="button"
                onClick={() => setIncludeLogo(!includeLogo)}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all flex items-center gap-1 cursor-pointer border ${
                  includeLogo
                    ? 'bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/30'
                    : 'bg-muted/40 text-muted-foreground hover:text-foreground border-border'
                }`}
                title="Toggle Logo"
              >
                <ImageIcon className="w-3 h-3" />
                <span>Logo {includeLogo ? 'ON' : 'OFF'}</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  const next = !showBrand;
                  setShowBrand(next);
                  if (typeof window !== 'undefined') {
                    localStorage.setItem('vouch_show_brand_in_proforma', String(next));
                  }
                }}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all flex items-center gap-1 cursor-pointer border ${
                  showBrand
                    ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30'
                    : 'bg-muted/40 text-muted-foreground hover:text-foreground border-border'
                }`}
                title="Toggle Brand Column"
              >
                <Tag className="w-3 h-3" />
                <span>Brand {showBrand ? 'ON' : 'OFF'}</span>
              </button>
            </div>

            {/* Right: Item Sorting & Status Quick Actions */}
            <div className="flex items-center gap-3 flex-wrap">
              {doc?.items && doc.items.length > 1 && (
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                    {isSorting ? <Loader2 className="w-3 h-3 animate-spin text-amber-500" /> : <ArrowUpDown className="w-3 h-3 text-amber-500" />}
                    <span>Sort:</span>
                  </span>
                  <div className="inline-flex items-center p-0.5 rounded-lg bg-muted border border-border">
                    <button
                      type="button"
                      onClick={() => handleSort('sort_ascending')}
                      disabled={isSorting}
                      className="px-2 py-0.5 rounded text-xs font-bold text-foreground hover:bg-background transition-colors cursor-pointer disabled:opacity-50"
                      title="Sort items Ascending (A → Z)"
                    >
                      A → Z
                    </button>
                    <div className="w-[1px] h-3 bg-border my-auto" />
                    <button
                      type="button"
                      onClick={() => handleSort('sort_descending')}
                      disabled={isSorting}
                      className="px-2 py-0.5 rounded text-xs font-bold text-foreground hover:bg-background transition-colors cursor-pointer disabled:opacity-50"
                      title="Sort items Descending (Z → A)"
                    >
                      Z → A
                    </button>
                  </div>
                </div>
              )}

              {!isConverted && (
                <div className="flex items-center gap-1.5 border-l border-border pl-3">
                  {doc.status !== 'SENT' && (
                    <button
                      type="button"
                      onClick={() => handleUpdateStatus('SENT')}
                      disabled={updatingStatus}
                      className="px-2 py-1 rounded text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
                    >
                      Mark Sent
                    </button>
                  )}
                  {doc.status !== 'ACCEPTED' && (
                    <button
                      type="button"
                      onClick={() => handleUpdateStatus('ACCEPTED')}
                      disabled={updatingStatus}
                      className="px-2 py-1 rounded text-xs font-semibold text-blue-600 dark:text-blue-400 hover:bg-blue-500/10 transition-colors cursor-pointer"
                    >
                      Mark Accepted
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ═══════════════════════════════════════════════════════════════════ */}
        {/* RESPONSIVE DOCUMENT VIEWER & A4 SHEET CONTAINER                     */}
        {/* ═══════════════════════════════════════════════════════════════════ */}
        <div className="w-full overflow-x-auto p-2 sm:p-6 flex justify-center bg-slate-100/70 dark:bg-slate-950/40 print:bg-white print:p-0 print:m-0 print:overflow-visible">
          <ProformaDocumentSheet
            doc={doc}
            company={company}
            watermarkOverride={includeWatermark}
            logoOverride={includeLogo}
            showBrand={showBrand}
            branding={{
              firm_name_size: firmNameSize,
            }}
          />
        </div>
      </div>
    </DashboardLayout>
  );
}
