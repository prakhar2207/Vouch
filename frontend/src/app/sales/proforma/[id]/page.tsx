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
  Check
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
  return str.trim() ? str.trim() + ' Only' : '';
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

  // Aggregate item quantities and tax figures
  const totalQty = useMemo(() => {
    return (doc?.items || []).reduce((sum: number, it: any) => sum + Number(it.quantity || 0), 0);
  }, [doc?.items]);

  const totalTaxable = useMemo(() => {
    return Number(doc?.taxable_amount || 0);
  }, [doc?.taxable_amount]);

  const totalCgst = useMemo(() => {
    return Number(doc?.cgst_amount || 0);
  }, [doc?.cgst_amount]);

  const totalSgst = useMemo(() => {
    return Number(doc?.sgst_amount || 0);
  }, [doc?.sgst_amount]);

  const totalIgst = useMemo(() => {
    return Number(doc?.igst_amount || 0);
  }, [doc?.igst_amount]);

  const cartageAmount = useMemo(() => {
    return Number(doc?.cartage_amount || 0);
  }, [doc?.cartage_amount]);

  const roundOff = useMemo(() => {
    return Number(doc?.round_off || 0);
  }, [doc?.round_off]);

  const finalGrandTotal = useMemo(() => {
    return Number(doc?.total_amount || 0);
  }, [doc?.total_amount]);

  const hasRoundOff = Math.abs(roundOff) >= 0.005;

  // HSN Tax Breakdown Summary (Grouped by Rate)
  const hsnSummary = useMemo(() => {
    if (!doc?.items || !Array.isArray(doc.items)) return [];
    const map = new Map<number, {
      gst_rate: number;
      taxable_amount: number;
      cgst_amount: number;
      sgst_amount: number;
      igst_amount: number;
      total_tax: number;
    }>();

    doc.items.forEach((it: any) => {
      const rate = Number(it.gst_rate || 0);
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

      if (!map.has(rate)) {
        map.set(rate, {
          gst_rate: rate,
          taxable_amount: taxable,
          cgst_amount: cgst,
          sgst_amount: sgst,
          igst_amount: igst,
          total_tax: cgst + sgst + igst,
        });
      } else {
        const item = map.get(rate)!;
        item.taxable_amount += taxable;
        item.cgst_amount += cgst;
        item.sgst_amount += sgst;
        item.igst_amount += igst;
        item.total_tax += (cgst + sgst + igst);
      }
    });

    return Array.from(map.values()).sort((a, b) => a.gst_rate - b.gst_rate);
  }, [doc?.items, isInterState]);

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
    ? `upi://pay?pa=${encodeURIComponent(upiId)}&pn=${encodeURIComponent(company.legal_name || company.name || 'Merchant')}&am=${finalGrandTotal.toFixed(2)}&tn=${encodeURIComponent(`Adv ${doc?.proforma_number || ''}`)}&cu=INR`
    : (typeof window !== 'undefined' ? window.location.href : '');

  // 1-Click Direct Vector PDF Generation via html2canvas & jsPDF
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
          border-color: #000000 !important;
          --foreground: #000000 !important;
          --card-foreground: #000000 !important;
          --muted-foreground: #1e293b !important;
          text-shadow: none !important;
          -webkit-print-color-adjust: exact !important;
          print-color-adjust: exact !important;
        }
        .print-sandbox-root .bg-white { background-color: #ffffff !important; }
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
      clone.style.padding = '0';
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

      if (imgHeight <= a4Height * 1.10) {
        const renderHeight = Math.min(imgHeight, a4Height);
        pdf.addImage(imgData, 'PNG', 0, 0, a4Width, renderHeight);
      } else {
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

      const totalPages = (pdf as any).internal.getNumberOfPages();
      for (let i = 1; i <= totalPages; i++) {
        pdf.setPage(i);
        pdf.setFontSize(8);
        pdf.setTextColor(80, 80, 80);
        pdf.text(
          `Page ${i} of ${totalPages}`,
          a4Width - 16,
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
    const amountStr = finalGrandTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 });
    
    let rawPhone = (doc.buyer_phone || '').replace(/[^0-9]/g, '');
    if (rawPhone.length === 10) rawPhone = '91' + rawPhone;

    const message = 
      `*${docTitle.toUpperCase()} - ${company.name || 'Our Company'}*\n\n` +
      `Dear *${partyName}*,\n` +
      `Please find the commercial estimate for your order:\n\n` +
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
      {/* Strict Print CSS: Guarantees Zero Chrome Artifacts & Strict Full-Height A4 Frame */}
      <style>{`
        @media print {
          html, body {
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
            margin: 0 !important;
            padding: 0 !important;
            background: #ffffff !important;
            color: #000000 !important;
          }
          header, nav, aside, [role="navigation"], .print\\:hidden {
            display: none !important;
          }
          @page {
            size: A4 portrait;
            margin: 8mm 6mm;
          }
          #proforma-sheet {
            width: 100% !important;
            min-width: 100% !important;
            max-width: 100% !important;
            min-height: 275mm !important;
            height: 275mm !important;
            padding: 0 !important;
            margin: 0 !important;
            box-shadow: none !important;
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
        {/* A4 PROFORMA INVOICE SHEET (STRICT FULL-HEIGHT INDIAN CORPORATE STANDARD)   */}
        {/* ========================================================================= */}
        <div className="w-full overflow-x-auto p-4 sm:p-6 flex justify-center bg-slate-200 print:bg-white print:p-0">
          <div 
            id="proforma-sheet"
            className="w-[210mm] max-w-[210mm] shrink-0 min-h-[275mm] print:min-h-[275mm] print:w-full print:max-w-none print:m-0 print:p-0 bg-white text-black p-6 sm:p-8 shadow-[0_0_15px_rgba(0,0,0,0.15)] print:shadow-none flex flex-col mx-auto font-sans"
          >
            {/* Outer Main Border Box (Fills 100% of A4 Page Height) */}
            <div className="border-2 border-black flex-1 flex flex-col justify-between">
              
              {/* Top Section */}
              <div className="flex-1 flex flex-col">
                
                {/* Header */}
                <div className="text-center p-3 border-b-2 border-black relative">
                  <div className="flex justify-between items-start text-xs font-bold mb-1">
                    <div>GSTIN : {company.gstin || 'Unregistered'}</div>
                    <div className="italic">Original For Recipient</div>
                  </div>

                  {/* Company Logo (Compressed from DB, rendered cleanly) */}
                  {logoSrc && (
                    <div className="flex justify-center mb-1">
                      <img 
                        crossOrigin="anonymous"
                        src={logoSrc} 
                        alt="Company Logo" 
                        className="max-h-12 max-w-[180px] object-contain"
                        loading="lazy"
                      />
                    </div>
                  )}

                  <h2 className="text-lg font-bold underline mb-0.5 tracking-wider uppercase">
                    {isPI ? 'PROFORMA INVOICE' : 'COMMERCIAL QUOTATION'}
                  </h2>
                  <p className="text-[11px] italic font-semibold text-slate-600 mb-1">
                    Commercial Estimate • Pre-GST Document • Not a Tax Invoice
                  </p>
                  
                  <h1 className="text-2xl sm:text-3xl font-extrabold mb-1 text-slate-900">
                    {company.name || 'Company Name'}
                  </h1>
                  {company.legal_name && company.legal_name !== company.name && (
                    <p className="text-xs text-slate-600 mb-0.5">Legal Name: {company.legal_name}</p>
                  )}
                  {company.address && (
                    <p className="text-sm text-slate-700">
                      {company.address}{company.city ? `, ${company.city}` : ''}{company.state_name ? `, ${company.state_name}` : ''}{company.pincode ? ` - ${company.pincode}` : ''}
                    </p>
                  )}
                  <p className="text-sm text-slate-700">
                    Ph: {company.phone || 'N/A'} | Email: {company.email || 'N/A'}
                  </p>
                  {company.tagline && (
                    <p className="text-sm font-bold mt-1 tracking-widest uppercase text-slate-600">{company.tagline}</p>
                  )}
                </div>

                {/* Meta Grid (2 Columns) */}
                <div className="grid grid-cols-2 border-b-2 border-black text-xs sm:text-sm">
                  <div className="p-2 border-r-2 border-black">
                    <table className="w-full">
                      <tbody>
                        <tr><td className="w-32 text-slate-600">Proforma No.</td><td className="font-bold">: {doc.proforma_number}</td></tr>
                        <tr><td className="text-slate-600">Dated</td><td className="font-bold">: {doc.date}</td></tr>
                        <tr><td className="text-slate-600">Place of Supply</td><td>: {placeOfSupply}</td></tr>
                        <tr><td className="text-slate-600">Reverse Charge</td><td>: N</td></tr>
                      </tbody>
                    </table>
                  </div>
                  <div className="p-2">
                    <table className="w-full">
                      <tbody>
                        <tr>
                          <td className="w-32 text-slate-600">Valid Until</td>
                          <td className="font-bold text-amber-900">: {doc.valid_until || '15 Days from issue'}</td>
                        </tr>
                        <tr>
                          <td className="text-slate-600">Transport</td>
                          <td>: Road</td>
                        </tr>
                        <tr>
                          <td className="text-slate-600">Payment Terms</td>
                          <td className="font-bold">: 100% Advance Prior to Dispatch</td>
                        </tr>
                        <tr>
                          <td className="text-slate-600">Document Type</td>
                          <td>: Commercial Estimate</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Party Grid (Billed to / Shipped to) */}
                <div className="grid grid-cols-2 border-b-2 border-black text-xs sm:text-sm">
                  <div className="p-2 border-r-2 border-black flex flex-col">
                    <span className="italic mb-1 text-slate-600 font-semibold">Billed to :</span>
                    <strong className="text-base text-slate-900">{doc.party_name || doc.buyer_name || 'Valued Customer'}</strong>
                    {doc.buyer_address && <span className="whitespace-pre-wrap text-slate-700 text-xs sm:text-sm">{doc.buyer_address}</span>}
                    <div className="mt-2 pt-1 font-mono text-xs">
                      GSTIN / UIN <span className="ml-4 font-bold">: {doc.buyer_gstin || 'Unregistered'}</span>
                    </div>
                  </div>
                  <div className="p-2 flex flex-col">
                    <span className="italic mb-1 text-slate-600 font-semibold">Shipped to / Commercial Terms :</span>
                    <strong className="text-base text-slate-900">{doc.party_name || doc.buyer_name || 'Valued Customer'}</strong>
                    {doc.buyer_address && <span className="whitespace-pre-wrap text-slate-700 text-xs sm:text-sm">{doc.buyer_address}</span>}
                    <div className="mt-2 pt-1 font-mono text-xs">
                      GSTIN / UIN <span className="ml-4 font-bold">: {doc.buyer_gstin || 'Unregistered'}</span>
                    </div>
                  </div>
                </div>

                {/* Items Table (Expands with Filler Row to Fill 100% Page Height) */}
                <div className="flex-1 flex flex-col min-h-[140px]">
                  <table className="w-full h-full text-xs sm:text-sm border-collapse">
                    <thead>
                      <tr className="border-b-2 border-black text-center min-h-9 font-bold bg-slate-50">
                        <th className="w-12 border-r border-black py-1.5 px-1">S.N.</th>
                        <th className="border-r border-black text-left py-1.5 pl-2">Description of Goods</th>
                        <th className="w-24 border-r border-black py-1.5 px-1 whitespace-nowrap">HSN</th>
                        <th className="w-16 border-r border-black py-1.5 px-1 whitespace-nowrap">Qty.</th>
                        <th className="w-12 border-r border-black py-1.5 px-1 whitespace-nowrap">Unit</th>
                        <th className="w-20 border-r border-black py-1.5 px-1 whitespace-nowrap">Price</th>
                        <th className="w-20 border-r border-black py-1.5 px-1 whitespace-nowrap">Disc%</th>
                        <th className="w-28 text-right py-1.5 pr-2 whitespace-nowrap">Amount(Rs.)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {doc.items?.map((item: any, idx: number) => (
                        <tr key={item.id || idx} className="align-top border-b border-black">
                          <td className="border-r border-black text-center py-2 px-1 font-mono">{idx + 1}</td>
                          <td className="border-r border-black text-left py-2 pl-2 font-medium">{item.item_name}</td>
                          <td className="border-r border-black text-center py-2 px-1 whitespace-nowrap font-mono">{item.hsn_code || '-'}</td>
                          <td className="border-r border-black text-right py-2 pr-1 whitespace-nowrap font-mono font-semibold">{Number(item.quantity).toFixed(2)}</td>
                          <td className="border-r border-black text-center py-2 px-1 whitespace-nowrap">{item.unit || 'Pcs'}</td>
                          <td className="border-r border-black text-right py-2 pr-1 whitespace-nowrap font-mono">{Number(item.rate).toFixed(2)}</td>
                          <td className="border-r border-black text-center py-2 px-1 whitespace-nowrap font-mono">{Number(item.discount_percent || 0).toFixed(2)}%</td>
                          <td className="text-right py-2 pr-2 font-mono font-semibold whitespace-nowrap">{Number(item.taxable_amount).toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
                        </tr>
                      ))}
                      {/* Filler Row: Stretches gracefully so footer pins to exact page bottom */}
                      <tr className="border-b border-black flex-1">
                        <td className="border-r border-black h-full min-h-[60px] print:min-h-[120px]"></td>
                        <td className="border-r border-black"></td>
                        <td className="border-r border-black"></td>
                        <td className="border-r border-black"></td>
                        <td className="border-r border-black"></td>
                        <td className="border-r border-black"></td>
                        <td className="border-r border-black"></td>
                        <td></td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                {/* Subtotals & Taxes (Exact Image 2 Specification) */}
                <div className="flex text-xs">
                  {/* Left side: Taxes labels */}
                  <div className="flex-1 flex flex-col justify-end py-1">
                    <div className="h-5"></div>
                    
                    {isInterState ? (
                      <div className="h-5 flex items-center justify-end pr-12 text-[11px] italic">
                        <div className="flex justify-between items-center w-48">
                          <span>Add : IGST</span>
                          <span>@ {doc.items?.length > 0 ? Number(doc.items[0].gst_rate).toFixed(2) : '18.00'} %</span>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div className="h-5 flex items-center justify-end pr-12 text-[11px] italic">
                          <div className="flex justify-between items-center w-48">
                            <span>Add : CGST</span>
                            <span>@ {doc.items?.length > 0 ? (Number(doc.items[0].gst_rate)/2).toFixed(2) : '9.00'} %</span>
                          </div>
                        </div>
                        <div className="h-5 flex items-center justify-end pr-12 text-[11px] italic">
                          <div className="flex justify-between items-center w-48">
                            <span>Add : SGST</span>
                            <span>@ {doc.items?.length > 0 ? (Number(doc.items[0].gst_rate)/2).toFixed(2) : '9.00'} %</span>
                          </div>
                        </div>
                      </>
                    )}

                    {cartageAmount > 0 && (
                      <div className="h-5 flex items-center justify-end pr-12 text-[11px] italic">
                        <div className="flex justify-between items-center w-48">
                          <span>Add : Cartage</span>
                          <span></span>
                        </div>
                      </div>
                    )}

                    {hasRoundOff && (
                      <div className="h-5 flex items-center justify-end pr-12 text-[11px] italic">
                        <div className="flex justify-between items-center w-48">
                          <span>{roundOff > 0 ? 'Add : Round Off' : 'Less : Round Off'}</span>
                          <span></span>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Right side: Amount Column with Subtotal & Taxes */}
                  <div className="w-28 border-l border-black flex flex-col justify-end py-1">
                    <div className="h-5 flex items-center justify-end pr-2 text-xs font-medium">
                      {totalTaxable.toLocaleString('en-IN', {minimumFractionDigits: 2})}
                    </div>
                    
                    {isInterState ? (
                      <div className="h-5 flex items-center justify-end pr-2 text-xs font-medium">
                        {totalIgst.toLocaleString('en-IN', {minimumFractionDigits: 2})}
                      </div>
                    ) : (
                      <>
                        <div className="h-5 flex items-center justify-end pr-2 text-xs font-medium">
                          {totalCgst.toLocaleString('en-IN', {minimumFractionDigits: 2})}
                        </div>
                        <div className="h-5 flex items-center justify-end pr-2 text-xs font-medium">
                          {totalSgst.toLocaleString('en-IN', {minimumFractionDigits: 2})}
                        </div>
                      </>
                    )}

                    {cartageAmount > 0 && (
                      <div className="h-5 flex items-center justify-end pr-2 text-xs font-medium">
                        {cartageAmount.toLocaleString('en-IN', {minimumFractionDigits: 2})}
                      </div>
                    )}

                    {hasRoundOff && (
                      <div className="h-5 flex items-center justify-end pr-2 text-xs font-medium">
                        {roundOff > 0 ? `+${roundOff.toFixed(2)}` : roundOff.toFixed(2)}
                      </div>
                    )}
                  </div>
                </div>

                {/* Grand Total Row */}
                <div className="flex border-t border-black text-xs font-bold h-7 items-center">
                  <div className="flex-1 flex items-center justify-end pr-12 gap-8">
                    <span>Grand Total</span>
                    <span className="border-b border-black px-4 pb-0.5">{totalQty.toFixed(2)} {doc.items?.[0]?.unit || 'Pcs'}</span>
                  </div>
                  <div className="w-28 border-l border-b border-black h-full flex items-center justify-end pr-2">
                    {finalGrandTotal.toLocaleString('en-IN', {minimumFractionDigits: 2})}
                  </div>
                </div>

                {/* Tax Details Table (Exact Image 2 Specification) */}
                <div className="border-b border-black px-2 py-1 text-[10px]">
                  <table className="border-collapse w-full">
                    <thead>
                      <tr>
                        <th className="text-left font-bold pb-0.5 pr-6">Tax Rate</th>
                        <th className="text-right font-bold pb-0.5 pr-6">Taxable Amt.</th>
                        {!isInterState && <th className="text-right font-bold pb-0.5 pr-6">CGST Amt.</th>}
                        {!isInterState && <th className="text-right font-bold pb-0.5 pr-6">SGST Amt.</th>}
                        {isInterState && <th className="text-right font-bold pb-0.5 pr-6">IGST Amt.</th>}
                        <th className="text-right font-bold pb-0.5">Total Tax</th>
                      </tr>
                    </thead>
                    <tbody>
                      {hsnSummary.map((hs, idx) => (
                        <tr key={idx}>
                          <td className="pt-0.5 pr-6">{hs.gst_rate}%</td>
                          <td className="text-right pt-0.5 pr-6">{hs.taxable_amount.toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
                          {!isInterState && <td className="text-right pt-0.5 pr-6">{hs.cgst_amount.toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>}
                          {!isInterState && <td className="text-right pt-0.5 pr-6">{hs.sgst_amount.toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>}
                          {isInterState && <td className="text-right pt-0.5 pr-6">{hs.igst_amount.toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>}
                          <td className="text-right pt-0.5">{hs.total_tax.toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Total Amount in Words */}
                <div className="p-2 border-b border-black text-[12px]">
                  <span className="font-semibold">Total Amount in Words : </span>
                  <span className="font-bold">₹ {numberToWords(Math.round(finalGrandTotal))}</span>
                </div>

                {/* Bank Details */}
                <div className="p-2 border-b-2 border-black text-center text-xs font-medium">
                  <span className="font-bold underline text-[13px]">BANK DETAILS FOR ADVANCE PAYMENT</span><br/>
                  {company.bank_details?.bank_name || ''} {company.bank_details?.branch ? `(${company.bank_details.branch})` : ''}, ACCOUNT NO- {company.bank_details?.account_number || ''}, IFSCODE: {company.bank_details?.ifsc || ''}
                </div>

              </div>

              {/* Bottom Footer Section (3 Columns matching Image 2) */}
              <div className="flex h-44 print:h-38 text-xs shrink-0">
                
                {/* Column 1: Terms */}
                <div className="w-[45%] p-2 border-r-2 border-black flex flex-col justify-between">
                  <div>
                    <span className="font-bold mb-1 text-[11px] block">Terms &amp; Conditions</span>
                    <span className="font-bold block mb-1">E.&amp; O.E.</span>
                    <span className="block">1. Commercial Proforma Invoice / Quotation only. NOT a GST Tax Invoice.</span>
                    <span className="block">2. 100% advance payment required prior to dispatch.</span>
                    <span className="block">3. Subject to '{company.city || 'Kanpur'}' Jurisdiction only.</span>
                  </div>
                </div>
                
                {/* Column 2: QR Code */}
                <div className="w-[20%] p-2 border-r-2 border-black flex flex-col items-center justify-between">
                  <span className="font-bold text-[10px] mb-1">Advance UPI QR</span>
                  {typeof window !== 'undefined' && (
                    <QRCode value={upiPayUrl} size={90} className="mx-auto my-auto" />
                  )}
                  <span className="text-[9px] text-slate-600 mt-1">Scan to Pay via UPI</span>
                </div>
                
                {/* Column 3: Signatures */}
                <div className="w-[35%] flex flex-col">
                  <div className="h-10 p-2 border-b-2 border-black flex items-start">
                    <span className="text-[11px] font-bold">Receiver's Signature :</span>
                  </div>
                  <div className="flex-1 p-2 relative flex flex-col justify-between items-end">
                    <div className="font-bold text-sm text-right mt-1">for {company.legal_name || company.name}</div>
                    
                    <div className="flex justify-end w-full my-auto">
                      {signatureSrc && (
                        <img 
                          crossOrigin="anonymous"
                          src={signatureSrc} 
                          alt="Signature" 
                          className="h-12 object-contain" 
                          onError={(e) => {
                            (e.target as HTMLElement).style.display = 'none';
                          }}
                        />
                      )}
                    </div>
                    
                    <div className="font-bold text-sm text-right">Authorised Signatory</div>
                  </div>
                </div>

              </div>

            </div>

            {/* Bottom Page Decorations bar matching exact PDF NumberedCanvas */}
            <div className="flex justify-between items-center text-[10px] text-slate-500 pt-1 px-1">
              <span>This is a Computer Generated Proforma Invoice (Commercial Quotation, Not a Tax Invoice)</span>
              <span>{isMultiPageExpected ? 'Page 1 of 2' : 'Page 1 of 1'}</span>
            </div>

          </div>
        </div>

      </div>
    </DashboardLayout>
  );
}
