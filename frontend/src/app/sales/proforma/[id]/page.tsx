"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState, useCallback, useMemo } from 'react';
import axios from 'axios';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import { useToast } from '@/context/ToastContext';
import QRCode from 'react-qr-code';
import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';
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
  QrCode,
  MapPin,
  Phone,
  Mail,
  Building2
} from 'lucide-react';

const STATE_NAMES: Record<string, string> = {
  '01': 'Jammu & Kashmir',
  '02': 'Himachal Pradesh',
  '03': 'Punjab',
  '04': 'Chandigarh',
  '05': 'Uttarakhand',
  '06': 'Haryana',
  '07': 'Delhi',
  '08': 'Rajasthan',
  '09': 'Uttar Pradesh',
  '10': 'Bihar',
  '11': 'Sikkim',
  '12': 'Arunachal Pradesh',
  '13': 'Nagaland',
  '14': 'Manipur',
  '15': 'Mizoram',
  '16': 'Tripura',
  '17': 'Meghalaya',
  '18': 'Assam',
  '19': 'West Bengal',
  '20': 'Jharkhand',
  '21': 'Odisha',
  '22': 'Chhattisgarh',
  '23': 'Madhya Pradesh',
  '24': 'Gujarat',
  '26': 'Dadra and Nagar Haveli and Daman and Diu',
  '27': 'Maharashtra',
  '28': 'Andhra Pradesh',
  '29': 'Karnataka',
  '30': 'Goa',
  '31': 'Lakshadweep',
  '32': 'Kerala',
  '33': 'Tamil Nadu',
  '34': 'Puducherry',
  '35': 'Andaman & Nicobar Islands',
  '36': 'Telangana',
  '37': 'Andhra Pradesh',
  '38': 'Ladakh',
  '97': 'Other Territory',
};

function numberToWords(numAmount: number): string {
  const a = ['', 'One ', 'Two ', 'Three ', 'Four ', 'Five ', 'Six ', 'Seven ', 'Eight ', 'Nine ', 'Ten ', 'Eleven ', 'Twelve ', 'Thirteen ', 'Fourteen ', 'Fifteen ', 'Sixteen ', 'Seventeen ', 'Eighteen ', 'Nineteen '];
  const b = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety'];
  const numStr = Math.floor(numAmount).toString();
  if (numStr.length > 9) return 'overflow';
  const n = ('000000000' + numStr).slice(-9).match(/^(\d{2})(\d{2})(\d{2})(\d{1})(\d{2})$/);
  if (!n) return '';
  let str = '';
  str += (n[1] !== '00') ? (a[Number(n[1])] || b[Number(n[1][0])] + ' ' + a[Number(n[1][1])]) + 'Crore ' : '';
  str += (n[2] !== '00') ? (a[Number(n[2])] || b[Number(n[2][0])] + ' ' + a[Number(n[2][1])]) + 'Lakh ' : '';
  str += (n[3] !== '00') ? (a[Number(n[3])] || b[Number(n[3][0])] + ' ' + a[Number(n[3][1])]) + 'Thousand ' : '';
  str += (n[4] !== '0') ? (a[Number(n[4])] || b[Number(n[4][0])] + ' ' + a[Number(n[4][1])]) + 'Hundred ' : '';
  str += (n[5] !== '00') ? ((str !== '') ? 'and ' : '') + (a[Number(n[5])] || b[Number(n[5][0])] + ' ' + a[Number(n[5][1])]) : '';
  return str.trim() ? str.trim() + ' Rupees Only' : '';
}

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

  const fetchDoc = useCallback(async () => {
    if (!docId) return;
    setLoading(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/proforma/detail/${docId}/`, { headers });
      if (res.data?.success) {
        setDoc(res.data.data);
      }
    } catch (err: any) {
      console.error(err);
      toast.error('Failed to load document', err.response?.data?.error || err.message);
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

  const handleConvert = async () => {
    if (!doc || doc.status === 'CONVERTED') return;
    setConverting(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.post(`${API_BASE_URL}/api/v1/accounting/proforma/${doc.id}/convert/`, {}, { headers });
      if (res.data?.success) {
        toast.success(
          'Converted to GST Tax Invoice!',
          `Generated Tax Invoice #${res.data.data?.voucher_number || 'INV'}`
        );
        fetchDoc();
      }
    } catch (err: any) {
      console.error(err);
      toast.error('Conversion Failed', err.response?.data?.error || err.message);
    } finally {
      setConverting(false);
    }
  };

  const handleUpdateStatus = async (newStatus: string) => {
    if (!doc || doc.status === 'CONVERTED') return;
    setUpdatingStatus(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      await axios.put(`${API_BASE_URL}/api/v1/accounting/proforma/detail/${doc.id}/`, { status: newStatus }, { headers });
      toast.success('Status Updated', `Document marked as ${newStatus}`);
      fetchDoc();
    } catch (err: any) {
      toast.error('Failed to update status', err.response?.data?.error || err.message);
    } finally {
      setUpdatingStatus(false);
    }
  };

  const isConverted = doc?.status === 'CONVERTED';
  const isPI = doc?.proforma_type === 'PROFORMA';
  const company = doc?.company_details || {};

  const isInterState = useMemo(() => {
    const sellerCode = company.state_code;
    const buyerCode = doc?.buyer_state_code;
    return sellerCode && buyerCode && sellerCode !== buyerCode;
  }, [company.state_code, doc?.buyer_state_code]);

  const placeOfSupply = useMemo(() => {
    const code = doc?.buyer_state_code || company.state_code || '';
    const name = STATE_NAMES[code] || '';
    return name ? `${name} (${code})` : (code || 'Intra-State');
  }, [doc?.buyer_state_code, company.state_code]);

  // Group items by HSN Code and GST Rate for standard statutory tax summary
  const hsnSummary = useMemo(() => {
    if (!doc?.items || !Array.isArray(doc.items)) return [];
    const map = new Map<string, {
      hsn_code: string;
      gst_rate: number;
      taxable_amount: number;
      cgst_amount: number;
      sgst_amount: number;
      igst_amount: number;
      total_tax: number;
    }>();

    doc.items.forEach((it: any) => {
      const hsn = (it.hsn_code || 'N/A').trim();
      const rate = Number(it.gst_rate || 0);
      const key = `${hsn}_${rate}`;

      const taxable = Number(it.taxable_amount || 0);
      let cgst = Number(it.cgst_amount || 0);
      let sgst = Number(it.sgst_amount || 0);
      let igst = Number(it.igst_amount || 0);

      if (cgst === 0 && sgst === 0 && igst === 0 && rate > 0 && taxable > 0) {
        if (isInterState) {
          igst = (taxable * rate) / 100;
        } else {
          cgst = (taxable * rate) / 200;
          sgst = (taxable * rate) / 200;
        }
      }

      if (!map.has(key)) {
        map.set(key, {
          hsn_code: hsn,
          gst_rate: rate,
          taxable_amount: taxable,
          cgst_amount: cgst,
          sgst_amount: sgst,
          igst_amount: igst,
          total_tax: cgst + sgst + igst,
        });
      } else {
        const item = map.get(key)!;
        item.taxable_amount += taxable;
        item.cgst_amount += cgst;
        item.sgst_amount += sgst;
        item.igst_amount += igst;
        item.total_tax += (cgst + sgst + igst);
      }
    });

    return Array.from(map.values());
  }, [doc, isInterState]);

  const getSignatureUrl = (sig: string | null | undefined) => {
    if (!sig) return '';
    if (sig.startsWith('data:') || sig.startsWith('http://') || sig.startsWith('https://')) {
      return sig;
    }
    return `${API_BASE_URL}${sig.startsWith('/') ? '' : '/'}${sig}`;
  };

  const getLogoUrl = (lUrl: string | null | undefined) => {
    if (!lUrl) return '';
    if (lUrl.startsWith('data:') || lUrl.startsWith('http://') || lUrl.startsWith('https://')) {
      return lUrl;
    }
    return `${API_BASE_URL}${lUrl.startsWith('/') ? '' : '/'}${lUrl}`;
  };

  const upiId = company.bank_details?.upi_id || company.upi_id || '';
  const upiPayUrl = upiId
    ? `upi://pay?pa=${encodeURIComponent(upiId)}&pn=${encodeURIComponent(company.legal_name || company.name || 'Merchant')}&am=${Number(doc?.total_amount || 0).toFixed(2)}&tn=${encodeURIComponent(`Adv ${doc?.proforma_number || ''}`)}&cu=INR`
    : (typeof window !== 'undefined' ? window.location.href : '');

  // Direct High-Resolution Vector-Quality PDF Download (Strictly 1 Page when items fit)
  const handleDownloadPdf = async () => {
    const element = document.getElementById('proforma-sheet');
    if (!element) return;
    setIsGeneratingPdf(true);

    try {
      const targetWidthPx = 794; // Standard A4 width at 96 DPI
      const sandbox = document.createElement('div');
      sandbox.className = 'light print-sandbox-root';
      sandbox.setAttribute('data-theme', 'light');
      sandbox.style.position = 'fixed';
      sandbox.style.left = '-99999px';
      sandbox.style.top = '0';
      sandbox.style.width = `${targetWidthPx}px`;
      sandbox.style.minWidth = `${targetWidthPx}px`;
      sandbox.style.maxWidth = `${targetWidthPx}px`;
      sandbox.style.zIndex = '-9999';
      sandbox.style.backgroundColor = '#ffffff';
      sandbox.style.color = '#000000';
      sandbox.style.overflow = 'visible';

      const printStyle = document.createElement('style');
      printStyle.textContent = `
        .print-sandbox-root, .print-sandbox-root * {
          color: #000000 !important;
          border-color: #cbd5e1 !important;
          --foreground: #000000 !important;
          --card-foreground: #000000 !important;
          --muted-foreground: #475569 !important;
          text-shadow: none !important;
          -webkit-print-color-adjust: exact !important;
          print-color-adjust: exact !important;
        }
        .print-sandbox-root .bg-white { background-color: #ffffff !important; }
        .print-sandbox-root .bg-slate-900 { background-color: #0f172a !important; color: #ffffff !important; }
        .print-sandbox-root .bg-slate-900 * { color: #ffffff !important; }
        .print-sandbox-root .bg-slate-800 { background-color: #1e293b !important; color: #ffffff !important; }
        .print-sandbox-root .bg-slate-800 * { color: #ffffff !important; }
        .print-sandbox-root .bg-slate-100 { background-color: #f1f5f9 !important; }
        .print-sandbox-root .bg-slate-50 { background-color: #f8fafc !important; }
        .print-sandbox-root .text-slate-900 { color: #0f172a !important; }
        .print-sandbox-root .text-slate-800 { color: #1e293b !important; }
        .print-sandbox-root .text-slate-700 { color: #334155 !important; }
        .print-sandbox-root .text-slate-600 { color: #475569 !important; }
        .print-sandbox-root .text-slate-500 { color: #64748b !important; }
      `;
      sandbox.appendChild(printStyle);

      const clone = element.cloneNode(true) as HTMLElement;
      clone.classList.remove('dark');
      clone.classList.add('light');
      clone.style.width = `${targetWidthPx}px`;
      clone.style.minWidth = `${targetWidthPx}px`;
      clone.style.maxWidth = `${targetWidthPx}px`;
      clone.style.backgroundColor = '#ffffff';
      clone.style.color = '#000000';
      clone.style.boxSizing = 'border-box';
      clone.style.padding = '14px 18px';
      clone.style.margin = '0 auto';
      sandbox.appendChild(clone);
      document.body.appendChild(sandbox);

      const canvas = await (html2canvas as any)(clone, {
        scale: 2,
        useCORS: true,
        allowTaint: true,
        logging: false,
        backgroundColor: '#ffffff',
        width: targetWidthPx,
      });

      document.body.removeChild(sandbox);

      const imgData = canvas.toDataURL('image/png');
      const pdf = new jsPDF({
        orientation: 'portrait',
        unit: 'mm',
        format: 'a4',
      });

      const a4Width = 210;
      const a4Height = 297;
      const imgHeight = (canvas.height * a4Width) / canvas.width;

      // When the invoice content height is within standard single A4 page
      if (imgHeight <= a4Height * 1.08) {
        const renderHeight = Math.min(imgHeight, a4Height);
        pdf.addImage(imgData, 'PNG', 0, 0, a4Width, renderHeight);
      } else {
        // Multi-page splitting when item counts naturally exceed single sheet capacity
        let heightLeft = imgHeight;
        let position = 0;
        pdf.addImage(imgData, 'PNG', 0, position, a4Width, imgHeight);
        heightLeft -= a4Height;

        while (heightLeft > 8) {
          position -= a4Height;
          pdf.addPage('a4', 'portrait');
          pdf.addImage(imgData, 'PNG', 0, position, a4Width, imgHeight);
          heightLeft -= a4Height;
        }
      }

      // Add dynamic page footer to all generated pages
      const totalPages = (pdf as any).internal.getNumberOfPages();
      for (let i = 1; i <= totalPages; i++) {
        pdf.setPage(i);
        pdf.setFontSize(8);
        pdf.setTextColor(100, 116, 139);
        pdf.text(
          `Page ${i} of ${totalPages}`,
          a4Width - 14,
          a4Height - 5,
          { align: 'right' }
        );
      }

      const cleanFilename = `${(doc.proforma_number || 'PROFORMA').replace(/[/\\:*?"<>|]/g, '-').trim()}.pdf`;
      pdf.save(cleanFilename);
      toast.success('PDF Downloaded', `Saved as ${cleanFilename}`);
    } catch (err: any) {
      console.error(err);
      toast.error('PDF Generation Failed', err.message || 'Could not export PDF');
    } finally {
      setIsGeneratingPdf(false);
    }
  };

  const handleShareWhatsApp = () => {
    if (!doc) return;
    const docTitle = isPI ? 'Proforma Invoice' : 'Commercial Quotation';
    const partyName = doc.buyer_name || doc.party_name || 'Valued Customer';
    const amountStr = Number(doc.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 });
    
    let rawPhone = (doc.buyer_phone || '').replace(/[^0-9]/g, '');
    if (rawPhone.length === 10) rawPhone = '91' + rawPhone;

    const message = 
      `*${docTitle.toUpperCase()} - ${company.name || 'Our Company'}*\n\n` +
      `Dear *${partyName}*,\n` +
      `Please find the commercial estimate of your order:\n\n` +
      `📄 *Doc No:* ${doc.proforma_number}\n` +
      `📅 *Date:* ${doc.date}\n` +
      (doc.valid_until ? `⏳ *Valid Until:* ${doc.valid_until}\n` : '') +
      `💰 *Total Amount:* ₹${amountStr}\n\n` +
      `View and verify document:\n${typeof window !== 'undefined' ? window.location.href : ''}\n\n` +
      `*Note:* This is a Proforma Invoice / Commercial Quotation and not a GST Tax Invoice.`;

    const waUrl = rawPhone
      ? `https://wa.me/${rawPhone}?text=${encodeURIComponent(message)}`
      : `https://wa.me/?text=${encodeURIComponent(message)}`;

    window.open(waUrl, '_blank');
  };

  const handleCopyLink = () => {
    if (typeof window !== 'undefined') {
      navigator.clipboard.writeText(window.location.href);
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2000);
      toast.success('Link Copied', 'Quotation link copied to clipboard');
    }
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

  const logoSrc = getLogoUrl(company.logo_data || company.logo_url);
  const signatureSrc = getSignatureUrl(company.signature_url);
  const itemsCount = doc.items?.length || 0;
  const isMultiPageExpected = itemsCount > 8;

  return (
    <DashboardLayout>
      {/* Strict Print CSS: Ensures Zero Header/Footer Artifacts & Strict 1-Page Geometry */}
      <style>{`
        @media print {
          @page {
            size: A4 portrait;
            margin: 6mm 6mm 6mm 6mm;
          }
          html, body {
            background: #ffffff !important;
            color: #000000 !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
            margin: 0 !important;
            padding: 0 !important;
            width: 100% !important;
          }
          /* Strictly hide application navbar, drawer, tours, buttons */
          header, nav, aside, [role="navigation"], .print\\:hidden {
            display: none !important;
          }
          /* Proforma sheet fills 100% of printable area with no margin shift */
          #proforma-sheet {
            width: 100% !important;
            min-width: 100% !important;
            max-width: 100% !important;
            margin: 0 !important;
            padding: 0 !important;
            box-shadow: none !important;
            border: none !important;
            border-radius: 0 !important;
          }
          .no-break {
            page-break-inside: avoid !important;
            break-inside: avoid !important;
          }
        }
      `}</style>

      <div className="max-w-5xl mx-auto space-y-4 pb-20">
        
        {/* Action Header (Completely Hidden in Print Mode) */}
        <div className="print:hidden flex flex-col md:flex-row justify-between items-start md:items-center gap-3 bg-card/70 backdrop-blur-md border border-border p-3.5 rounded-2xl shadow-xs">
          
          {/* Left: Navigation and Document Badge */}
          <div className="flex items-center gap-3">
            <Link
              href="/sales/proforma"
              className="p-2 rounded-xl bg-card border border-border hover:bg-muted text-muted-foreground hover:text-foreground transition-all cursor-pointer shadow-2xs"
              title="Back to Proformas"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`px-2 py-0.5 rounded text-[10.5px] font-black uppercase tracking-wider ${
                  isPI ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20' : 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20'
                }`}>
                  {isPI ? 'PROFORMA INVOICE' : 'QUOTATION'}
                </span>
                <h1 className="text-base font-black text-foreground font-mono">
                  {doc.proforma_number}
                </h1>
                <span className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${
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

          {/* Right: Actions (Convert, Share, Download, Print) */}
          <div className="flex items-center gap-2 flex-wrap w-full md:w-auto justify-end">
            
            {/* Convert to GST Tax Invoice */}
            {!isConverted ? (
              <button
                type="button"
                onClick={handleConvert}
                disabled={converting}
                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold transition-all shadow-xs flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
              >
                {converting ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Sparkles className="w-3.5 h-3.5 text-amber-300" />
                )}
                <span>Convert to Tax Invoice</span>
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

            {/* Quick Status Mark */}
            {!isConverted && doc.status !== 'SENT' && (
              <button
                type="button"
                onClick={() => handleUpdateStatus('SENT')}
                disabled={updatingStatus}
                className="px-2.5 py-1.5 bg-card hover:bg-muted border border-border rounded-xl text-xs font-semibold text-foreground transition-colors cursor-pointer flex items-center gap-1"
              >
                <Send className="w-3 h-3 text-slate-500" />
                <span>Sent</span>
              </button>
            )}

            {!isConverted && doc.status !== 'ACCEPTED' && (
              <button
                type="button"
                onClick={() => handleUpdateStatus('ACCEPTED')}
                disabled={updatingStatus}
                className="px-2.5 py-1.5 bg-blue-500/10 text-blue-600 dark:text-blue-400 hover:bg-blue-500/20 border border-blue-500/30 rounded-xl text-xs font-bold transition-colors cursor-pointer flex items-center gap-1"
              >
                <CheckCircle2 className="w-3 h-3" />
                <span>Accept</span>
              </button>
            )}

            {/* Copy Link */}
            <button
              type="button"
              onClick={handleCopyLink}
              className="p-1.5 bg-card hover:bg-muted border border-border text-foreground rounded-xl transition-colors cursor-pointer"
              title="Copy Quotation Link"
            >
              {copiedLink ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5 text-muted-foreground" />}
            </button>

            {/* WhatsApp Share */}
            <button
              type="button"
              onClick={handleShareWhatsApp}
              className="px-3 py-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 dark:hover:bg-emerald-950/60 border border-emerald-300 dark:border-emerald-800 rounded-xl text-xs font-bold transition-colors flex items-center gap-1.5 cursor-pointer"
              title="Share via WhatsApp"
            >
              <MessageCircle className="w-3.5 h-3.5 text-emerald-600" />
              <span>WhatsApp</span>
            </button>

            {/* Direct PDF Download */}
            <button
              type="button"
              onClick={handleDownloadPdf}
              disabled={isGeneratingPdf}
              className="px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-white dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white rounded-xl text-xs font-bold transition-colors flex items-center gap-1.5 cursor-pointer shadow-xs disabled:opacity-50"
              title="Download Clean A4 PDF"
            >
              {isGeneratingPdf ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Download className="w-3.5 h-3.5" />
              )}
              <span>Download PDF</span>
            </button>

            {/* Browser Print / Clean Print */}
            <button
              type="button"
              onClick={() => window.print()}
              className="px-3 py-1.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl text-xs font-bold transition-colors flex items-center gap-1.5 cursor-pointer shadow-xs"
              title="Print Document"
            >
              <Printer className="w-3.5 h-3.5" />
              <span>Print</span>
            </button>
          </div>
        </div>

        {/* ========================================================================= */}
        {/* ULTRA-PREMIUM CORPORATE A4 PROFORMA INVOICE SHEET                         */}
        {/* ========================================================================= */}
        <div 
          id="proforma-sheet"
          className="bg-white text-slate-900 border border-slate-200/90 rounded-xl shadow-lg print:border-none print:shadow-none print:rounded-none max-w-[820px] mx-auto p-6 sm:p-7 print:p-0 transition-all font-sans leading-normal"
        >
          {/* Header Block: Brand Logo / Company Info (Left) & Document Meta (Right) */}
          <div className="flex flex-row justify-between items-start gap-4 pb-3.5 border-b border-slate-200">
            
            {/* Left: Brand Identity */}
            <div className="max-w-[460px] space-y-1">
              {/* Dynamic Company Logo (Loads for print and download, compressed from DB) */}
              {logoSrc ? (
                <div className="mb-2">
                  <img 
                    crossOrigin="anonymous"
                    src={logoSrc} 
                    alt="Company Logo" 
                    className="max-h-12 max-w-[200px] object-contain object-left"
                    loading="lazy"
                  />
                </div>
              ) : (
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-8 h-8 rounded-lg bg-slate-900 text-white flex items-center justify-center font-black text-sm">
                    {(company.name || 'V')[0]?.toUpperCase()}
                  </div>
                  <span className="text-[10px] font-bold tracking-widest text-slate-400 uppercase">OFFICIAL ESTIMATE</span>
                </div>
              )}

              <h2 className="text-lg font-black text-slate-900 tracking-tight leading-snug">
                {company.name || 'Company Name'}
              </h2>
              {company.legal_name && company.legal_name !== company.name && (
                <p className="text-[10.5px] text-slate-500 font-medium leading-none">
                  Legal Name: {company.legal_name}
                </p>
              )}
              {company.tagline && (
                <p className="text-[10px] text-slate-500 italic">
                  {company.tagline}
                </p>
              )}

              {company.address && (
                <p className="text-[10px] text-slate-600 leading-tight pt-0.5">
                  {company.address}{company.city ? `, ${company.city}` : ''}{company.state_name ? `, ${company.state_name}` : ''}{company.pincode ? ` - ${company.pincode}` : ''}
                </p>
              )}

              {/* Tax & Contact Pills */}
              <div className="pt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-slate-700 font-mono">
                {company.gstin && <span>GSTIN: <strong className="text-slate-900">{company.gstin}</strong></span>}
                {company.pan && <span>PAN: <strong>{company.pan}</strong></span>}
                {company.phone && <span className="font-sans">Tel: {company.phone}</span>}
                {company.email && <span className="font-sans">Email: {company.email}</span>}
              </div>
            </div>

            {/* Right: Document Identification */}
            <div className="text-right space-y-1.5 shrink-0">
              <div>
                <span className="inline-block px-2.5 py-0.5 rounded text-[11px] font-black tracking-wider uppercase bg-slate-900 text-white">
                  {isPI ? 'PROFORMA INVOICE' : 'COMMERCIAL QUOTATION'}
                </span>
                <p className="text-[9px] font-semibold text-slate-500 uppercase tracking-wider mt-0.5">
                  Pre-GST Commercial Estimate
                </p>
              </div>

              <div className="text-base font-black font-mono text-slate-900">
                {doc.proforma_number}
              </div>

              <div className="text-[10.5px] text-slate-600 font-mono space-y-0.5 bg-slate-50 p-2 rounded-lg border border-slate-200/80 inline-block text-left min-w-[190px]">
                <div className="flex justify-between gap-2">
                  <span className="font-sans text-slate-500">Date:</span>
                  <strong className="text-slate-900">{doc.date}</strong>
                </div>
                {doc.valid_until && (
                  <div className="flex justify-between gap-2 text-amber-800">
                    <span className="font-sans">Valid Until:</span>
                    <strong className="font-bold">{doc.valid_until}</strong>
                  </div>
                )}
                <div className="flex justify-between gap-2">
                  <span className="font-sans text-slate-500">Place of Supply:</span>
                  <strong className="text-slate-800 font-sans">{placeOfSupply}</strong>
                </div>
              </div>
            </div>

          </div>

          {/* Party Grid: Billed To / Recipient & Commercial Terms */}
          <div className="grid grid-cols-2 gap-3 my-3 text-[10.5px]">
            
            {/* Buyer Details */}
            <div className="p-2.5 bg-slate-50/70 rounded-lg border border-slate-200/80 space-y-1">
              <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block">
                Billed To / Customer:
              </span>
              <div className="font-bold text-xs text-slate-900 leading-snug">
                {doc.party_name || doc.buyer_name || 'Valued Customer'}
              </div>
              {doc.buyer_address && (
                <div className="text-slate-600 leading-tight line-clamp-2">
                  {doc.buyer_address}
                </div>
              )}
              <div className="text-slate-700 font-mono space-y-0.5 pt-0.5">
                <div>GSTIN: <strong className="text-slate-900">{doc.buyer_gstin || 'Unregistered'}</strong></div>
                {doc.buyer_state_code && (
                  <div>State: {STATE_NAMES[doc.buyer_state_code] || doc.buyer_state_code} ({doc.buyer_state_code})</div>
                )}
                {doc.buyer_phone && <div className="font-sans">Phone: {doc.buyer_phone}</div>}
              </div>
            </div>

            {/* Commercial Terms Summary */}
            <div className="p-2.5 bg-slate-50/70 rounded-lg border border-slate-200/80 space-y-1 flex flex-col justify-between">
              <div>
                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block">
                  Supply &amp; Payment Terms:
                </span>
                <div className="space-y-0.5 pt-0.5 text-slate-700">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Tax Type:</span>
                    <strong className="text-slate-900">{isInterState ? 'Inter-State (IGST)' : 'Intra-State (CGST + SGST)'}</strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Payment Terms:</span>
                    <strong className="text-slate-900">100% Advance Prior to Dispatch</strong>
                  </div>
                  {doc.valid_until && (
                    <div className="flex justify-between text-amber-800">
                      <span>Price Validity:</span>
                      <strong className="font-mono">{doc.valid_until}</strong>
                    </div>
                  )}
                </div>
              </div>

              {isConverted && doc.converted_voucher_number && (
                <div className="text-[10px] text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 font-semibold flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3 text-emerald-600 shrink-0" />
                  <span>Tax Invoice #{doc.converted_voucher_number}</span>
                </div>
              )}
            </div>

          </div>

          {/* Line Items Table */}
          <div className="border border-slate-300 rounded-lg overflow-hidden my-3">
            <table className="w-full text-left text-[10.5px] border-collapse">
              <thead>
                <tr className="bg-slate-100 text-slate-800 font-bold text-[9px] uppercase tracking-wider border-b border-slate-300">
                  <th className="py-1.5 px-2 w-7 text-center">#</th>
                  <th className="py-1.5 px-2">Item Description</th>
                  <th className="py-1.5 px-2 text-center w-20">HSN/SAC</th>
                  <th className="py-1.5 px-2 text-right w-16">Qty</th>
                  <th className="py-1.5 px-2 text-right w-20">Rate (₹)</th>
                  <th className="py-1.5 px-2 text-right w-14">Disc %</th>
                  <th className="py-1.5 px-2 text-right w-20">Taxable (₹)</th>
                  <th className="py-1.5 px-2 text-center w-12">GST</th>
                  <th className="py-1.5 px-2 text-right w-22">Total (₹)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 font-mono text-[10.5px]">
                {doc.items?.map((it: any, i: number) => (
                  <tr key={it.id || i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                    <td className="py-1.5 px-2 text-center text-slate-400">{i + 1}</td>
                    <td className="py-1.5 px-2 font-sans font-medium text-slate-900">
                      {it.item_name}
                    </td>
                    <td className="py-1.5 px-2 text-center text-slate-600">{it.hsn_code || '-'}</td>
                    <td className="py-1.5 px-2 text-right text-slate-900 font-semibold">
                      {it.quantity} <span className="text-[9px] text-slate-500 font-sans">{it.unit || ''}</span>
                    </td>
                    <td className="py-1.5 px-2 text-right text-slate-800">
                      {Number(it.rate).toFixed(2)}
                    </td>
                    <td className="py-1.5 px-2 text-right text-slate-500">
                      {it.discount_percent > 0 ? `${it.discount_percent}%` : '-'}
                    </td>
                    <td className="py-1.5 px-2 text-right text-slate-900 font-semibold">
                      {Number(it.taxable_amount).toFixed(2)}
                    </td>
                    <td className="py-1.5 px-2 text-center text-slate-600">
                      {it.gst_rate}%
                    </td>
                    <td className="py-1.5 px-2 text-right font-bold text-slate-900">
                      {Number(it.total_amount).toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="bg-slate-100 border-t-2 border-slate-300 font-mono text-[10.5px] font-bold text-slate-900">
                  <td colSpan={3} className="py-1.5 px-2 font-sans uppercase text-[9.5px] text-slate-600">
                    Subtotal:
                  </td>
                  <td className="py-1.5 px-2 text-right">
                    {doc.items?.reduce((sum: number, it: any) => sum + Number(it.quantity || 0), 0)}
                  </td>
                  <td colSpan={2}></td>
                  <td className="py-1.5 px-2 text-right">
                    ₹{Number(doc.taxable_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </td>
                  <td></td>
                  <td className="py-1.5 px-2 text-right">
                    ₹{Number(doc.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>

          {/* HSN / SAC Statutory Tax Breakdown Summary (Compact) */}
          {hsnSummary.length > 0 && (
            <div className="no-break border border-slate-200 rounded-lg overflow-hidden my-2.5">
              <div className="bg-slate-100 px-2.5 py-1 text-[9px] font-bold uppercase tracking-wider text-slate-600 border-b border-slate-200">
                HSN / SAC Tax Transparency Breakdown
              </div>
              <table className="w-full text-left text-[10px] font-mono border-collapse">
                <thead>
                  <tr className="bg-slate-50 text-slate-500 border-b border-slate-200">
                    <th className="py-1 px-2.5">HSN/SAC</th>
                    <th className="py-1 px-2.5 text-right">Taxable Value (₹)</th>
                    {!isInterState ? (
                      <>
                        <th className="py-1 px-2.5 text-right">CGST (₹)</th>
                        <th className="py-1 px-2.5 text-right">SGST (₹)</th>
                      </>
                    ) : (
                      <th className="py-1 px-2.5 text-right">IGST (₹)</th>
                    )}
                    <th className="py-1 px-2.5 text-right font-bold text-slate-800">Total Tax (₹)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {hsnSummary.map((hs, idx) => (
                    <tr key={idx}>
                      <td className="py-1 px-2.5 font-medium text-slate-800">
                        {hs.hsn_code} <span className="text-[9px] text-slate-400 font-sans">({hs.gst_rate}%)</span>
                      </td>
                      <td className="py-1 px-2.5 text-right text-slate-700">{hs.taxable_amount.toFixed(2)}</td>
                      {!isInterState ? (
                        <>
                          <td className="py-1 px-2.5 text-right text-slate-700">{hs.cgst_amount.toFixed(2)}</td>
                          <td className="py-1 px-2.5 text-right text-slate-700">{hs.sgst_amount.toFixed(2)}</td>
                        </>
                      ) : (
                        <td className="py-1 px-2.5 text-right text-slate-700">{hs.igst_amount.toFixed(2)}</td>
                      )}
                      <td className="py-1 px-2.5 text-right font-bold text-slate-900">{hs.total_tax.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Bottom Split: Payment Info & Calculation Summary */}
          <div className="no-break grid grid-cols-2 gap-3 my-2.5 text-[10.5px]">
            
            {/* Left Column: Words, Advance QR Code, Bank, Terms */}
            <div className="space-y-2">
              
              {/* Amount in words */}
              <div className="p-2 bg-slate-50/80 rounded-lg border border-slate-200/80">
                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block">
                  Amount Chargeable (in words):
                </span>
                <span className="font-semibold text-slate-900 font-sans leading-tight block pt-0.5">
                  {numberToWords(doc.total_amount)}
                </span>
              </div>

              {/* Instant Advance Payment QR Code + Bank Details Combined */}
              <div className="p-2.5 bg-slate-50/80 rounded-lg border border-slate-200/80 flex items-center gap-3">
                <div className="p-1.5 bg-white rounded border border-slate-200 shadow-2xs shrink-0">
                  <QRCode 
                    value={upiPayUrl}
                    size={56}
                    level="M"
                  />
                </div>
                <div className="space-y-0.5 leading-tight flex-1">
                  <div className="font-bold text-slate-900 text-[10px] flex items-center gap-1">
                    <QrCode className="w-3 h-3 text-emerald-600" />
                    <span>{upiId ? 'Scan & Pay Advance via UPI' : 'Digital Quotation QR'}</span>
                  </div>
                  {upiId ? (
                    <div className="text-[10px] font-mono text-emerald-700 font-bold">
                      UPI ID: {upiId}
                    </div>
                  ) : null}
                  {company.bank_details?.account_number && (
                    <div className="text-[9.5px] font-mono text-slate-600 pt-0.5">
                      <div>A/C: <strong className="text-slate-900">{company.bank_details.account_number}</strong> | IFSC: <strong className="text-slate-900">{company.bank_details.ifsc}</strong></div>
                      <div>Bank: {company.bank_details.bank_name}{company.bank_details.branch ? ` (${company.bank_details.branch})` : ''}</div>
                    </div>
                  )}
                </div>
              </div>

              {/* Terms and Conditions (Clean & Compact) */}
              <div className="text-[9.5px] text-slate-500 leading-tight">
                <span className="font-bold uppercase tracking-wider text-slate-600 block mb-0.5">
                  Commercial Terms:
                </span>
                <p className="whitespace-pre-line">
                  {doc.terms_and_conditions || 
                    `1. Valid for 15 days from issue date. 2. 100% advance required before dispatch. 3. Subject to '${company.city || 'Kanpur'}' jurisdiction.`
                  }
                </p>
              </div>
            </div>

            {/* Right Column: Financial Calculations */}
            <div className="p-3 bg-slate-50/80 rounded-lg border border-slate-200/80 font-mono text-[10.5px] space-y-1.5 flex flex-col justify-between">
              <div className="space-y-1">
                <div className="flex justify-between py-0.5 border-b border-slate-200">
                  <span className="text-slate-600 font-sans">Taxable Value:</span>
                  <span className="font-semibold text-slate-900">
                    ₹{Number(doc.taxable_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </span>
                </div>

                {doc.cgst_amount > 0 && (
                  <div className="flex justify-between py-0.5 border-b border-slate-200">
                    <span className="text-slate-600 font-sans">Central Tax (CGST):</span>
                    <span className="font-semibold text-slate-900">
                      ₹{Number(doc.cgst_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                )}

                {doc.sgst_amount > 0 && (
                  <div className="flex justify-between py-0.5 border-b border-slate-200">
                    <span className="text-slate-600 font-sans">State Tax (SGST):</span>
                    <span className="font-semibold text-slate-900">
                      ₹{Number(doc.sgst_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                )}

                {doc.igst_amount > 0 && (
                  <div className="flex justify-between py-0.5 border-b border-slate-200">
                    <span className="text-slate-600 font-sans">Integrated Tax (IGST):</span>
                    <span className="font-semibold text-slate-900">
                      ₹{Number(doc.igst_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                )}

                {doc.cartage_amount > 0 && (
                  <div className="flex justify-between py-0.5 border-b border-slate-200">
                    <span className="text-slate-600 font-sans">Freight / Cartage:</span>
                    <span className="font-semibold text-slate-900">
                      ₹{Number(doc.cartage_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                )}

                {doc.round_off !== 0 && (
                  <div className="flex justify-between py-0.5 border-b border-slate-200 text-slate-500">
                    <span className="font-sans">Round Off:</span>
                    <span>₹{Number(doc.round_off).toFixed(2)}</span>
                  </div>
                )}
              </div>

              {/* Total Payable Box */}
              <div className="mt-2 p-2 bg-slate-900 text-white rounded-md flex justify-between items-center shadow-xs">
                <div>
                  <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400 block leading-none">
                    Total Payable Amount
                  </span>
                  <span className="text-[9.5px] text-slate-300 font-sans">
                    (Inclusive of all Taxes)
                  </span>
                </div>
                <div className="text-lg font-black font-mono tracking-tight text-white">
                  ₹{Number(doc.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
              </div>
            </div>

          </div>

          {/* Signatures & Seal Section (Compact) */}
          <div className="no-break flex flex-row justify-between items-end pt-5 text-[10.5px] border-t border-slate-200 text-slate-600">
            
            {/* Customer Acceptance */}
            <div className="w-1/2 pr-4 space-y-1">
              <div className="font-bold text-slate-800 text-[10px] uppercase tracking-wider">
                Customer Acceptance Signature:
              </div>
              <p className="text-[9px] text-slate-400">
                Sign &amp; date to approve quotation
              </p>
              <div className="mt-8 border-b border-slate-400 w-36"></div>
              <div className="text-[9px] text-slate-400 font-sans">Authorized Buyer Signatory</div>
            </div>

            {/* Seller Signatory */}
            <div className="w-1/2 pl-4 text-right flex flex-col items-end space-y-0.5">
              <div className="font-bold text-slate-900 text-[10px] uppercase tracking-wider">
                For {company.legal_name || company.name || 'Seller'}:
              </div>
              
              {/* Digital Signature Image */}
              <div className="h-10 flex items-center justify-end my-0.5">
                {signatureSrc ? (
                  <img 
                    crossOrigin="anonymous"
                    src={signatureSrc} 
                    alt="Authorized Signature" 
                    className="max-h-9 max-w-[130px] object-contain" 
                    loading="lazy"
                    onError={(e) => {
                      (e.target as HTMLElement).style.display = 'none';
                    }}
                  />
                ) : (
                  <div className="w-28 h-7 border border-dashed border-slate-300 rounded flex items-center justify-center text-[9px] text-slate-400">
                    Official Stamp / Seal
                  </div>
                )}
              </div>

              <div className="border-b border-slate-400 w-40"></div>
              <div className="font-bold text-slate-800 text-[10px]">
                {company.proprietor_name ? company.proprietor_name : 'Authorized Signatory'}
              </div>
              <div className="text-[9px] text-slate-400">Authorised Signatory</div>
            </div>

          </div>

          {/* Footer Ribbon with Explicit Proforma Notice and Page Number */}
          <div className="flex justify-between items-center text-[9px] text-slate-500 pt-3 mt-3 border-t border-slate-100">
            <span>
              <strong>Note:</strong> This is a Commercial Proforma Invoice / Quotation and is <u>NOT</u> a GST Tax Invoice. Goods/Services dispatched upon advance payment.
            </span>
            <span className="font-mono font-semibold text-slate-600 shrink-0 ml-2">
              {isMultiPageExpected ? 'Page 1 of 2' : 'Page 1 of 1'}
            </span>
          </div>

        </div>

      </div>
    </DashboardLayout>
  );
}
