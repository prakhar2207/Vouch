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
  Building2,
  QrCode,
  ShieldCheck
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

  // Prioritize DB base64 data to avoid 404 network issues on ephemeral media
  const logoSrc = useMemo(() => {
    const raw = company.logo_data || company.logo_url;
    if (!raw) return '';
    if (raw.startsWith('data:') || raw.startsWith('http://') || raw.startsWith('https://')) return raw;
    return `${API_BASE_URL}${raw.startsWith('/') ? '' : '/'}${raw}`;
  }, [company.logo_data, company.logo_url]);

  const signatureSrc = useMemo(() => {
    const raw = company.signature_data || company.signature_url;
    if (!raw) return '';
    if (raw.startsWith('data:') || raw.startsWith('http://') || raw.startsWith('https://')) return raw;
    return `${API_BASE_URL}${raw.startsWith('/') ? '' : '/'}${raw}`;
  }, [company.signature_data, company.signature_url]);

  const upiId = company.bank_details?.upi_id || company.upi_id || '';
  const upiPayUrl = useMemo(() => {
    if (upiId) {
      return `upi://pay?pa=${encodeURIComponent(upiId)}&pn=${encodeURIComponent(company.legal_name || company.name || 'Merchant')}&am=${finalGrandTotal.toFixed(2)}&tn=${encodeURIComponent(`Adv ${doc?.proforma_number || ''}`)}&cu=INR`;
    }
    return typeof window !== 'undefined' ? window.location.href : '';
  }, [upiId, company.legal_name, company.name, finalGrandTotal, doc?.proforma_number]);

  // High-Resolution Vector PDF Generator (with full modern color normalization to prevent canvas parser crash)
  const handleDownloadPdf = async () => {
    const element = document.getElementById('proforma-sheet');
    if (!element) return;
    setIsGeneratingPdf(true);

    try {
      const targetWidthPx = 794; // Standard A4 width at 96 DPI
      const sandbox = document.createElement('div');
      sandbox.className = 'light print-sandbox-root';
      sandbox.style.position = 'fixed';
      sandbox.style.left = '-99999px';
      sandbox.style.top = '0';
      sandbox.style.width = `${targetWidthPx}px`;
      sandbox.style.minWidth = `${targetWidthPx}px`;
      sandbox.style.maxWidth = `${targetWidthPx}px`;
      sandbox.style.zIndex = '-9999';
      sandbox.style.backgroundColor = '#ffffff';
      sandbox.style.color = '#0f172a';
      sandbox.style.overflow = 'visible';

      const clone = element.cloneNode(true) as HTMLElement;
      clone.style.width = `${targetWidthPx}px`;
      clone.style.minWidth = `${targetWidthPx}px`;
      clone.style.maxWidth = `${targetWidthPx}px`;
      clone.style.backgroundColor = '#ffffff';
      clone.style.boxSizing = 'border-box';
      clone.style.margin = '0 auto';
      clone.style.boxShadow = 'none';

      sandbox.appendChild(clone);
      document.body.appendChild(sandbox);

      // Normalizes any Tailwind v4 OKLAB / OKLCH / color-mix colors to standard RGB/HEX using canvas context
      const canvasHelper = document.createElement('canvas');
      canvasHelper.width = 1;
      canvasHelper.height = 1;
      const ctx = canvasHelper.getContext('2d');

      const sanitizeColorString = (val: string): string => {
        if (!val || typeof val !== 'string') return val;
        if (!/(?:oklab|oklch|color-mix|lab|hwb)\(/i.test(val)) return val;
        if (!ctx) return '#0f172a';
        return val.replace(/(?:oklab|oklch|color-mix|lab|hwb)\([^)]+\)/gi, (match) => {
          try {
            ctx.fillStyle = '#000000';
            ctx.fillStyle = match;
            return ctx.fillStyle; // Converts to #rrggbb or rgb(...) in browser
          } catch {
            return '#0f172a';
          }
        });
      };

      const colorProps = [
        'color', 'backgroundColor', 'borderColor',
        'borderTopColor', 'borderRightColor', 'borderBottomColor', 'borderLeftColor',
        'outlineColor', 'fill', 'stroke'
      ];

      const sanitizeElements = (root: HTMLElement, docRef?: Document) => {
        const allElements = [root, ...Array.from(root.querySelectorAll('*'))] as HTMLElement[];
        allElements.forEach((el) => {
          try {
            // Strip out shadow and filters that carry oklab values
            el.style.boxShadow = 'none';
            el.style.textShadow = 'none';
            el.style.filter = 'none';

            const win = docRef?.defaultView || window;
            const cs = win.getComputedStyle(el);
            colorProps.forEach((prop) => {
              const val = (cs as any)[prop] || cs.getPropertyValue(prop.replace(/([A-Z])/g, '-$1').toLowerCase());
              if (val && /(?:oklab|oklch|color-mix|lab|hwb)/i.test(val)) {
                const converted = sanitizeColorString(val);
                el.style.setProperty(prop.replace(/([A-Z])/g, '-$1').toLowerCase(), converted, 'important');
              }
            });
          } catch {}
        });
      };

      sanitizeElements(clone);

      const canvas = await (html2canvas as any)(clone, {
        scale: 2,
        useCORS: true,
        allowTaint: true,
        logging: false,
        backgroundColor: '#ffffff',
        width: targetWidthPx,
        onclone: (clonedDoc: Document, clonedEl: HTMLElement) => {
          const style = clonedDoc.createElement('style');
          style.innerHTML = `
            * {
              box-shadow: none !important;
              text-shadow: none !important;
              filter: none !important;
            }
          `;
          clonedDoc.head.appendChild(style);
          sanitizeElements(clonedEl, clonedDoc);
        },
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

      if (imgHeight <= a4Height * 1.08) {
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
      `*Note:* This is a Proforma Invoice / Commercial Quotation and NOT a GST Tax Invoice.`;

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

  const itemsCount = doc.items?.length || 0;
  const isMultiPageExpected = itemsCount > 8;

  return (
    <DashboardLayout>
      {/* Strict Print CSS: Ensures Zero Header/Footer Chrome & Strict Single-Page A4 Geometry */}
      <style>{`
        @media print {
          html, body {
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
            margin: 0 !important;
            padding: 0 !important;
            background: #ffffff !important;
            color: #0f172a !important;
            height: auto !important;
            min-height: 100% !important;
          }
          header, nav, aside, [role="navigation"], .print\\:hidden {
            display: none !important;
          }
          @page {
            size: A4 portrait;
            margin: 6mm 8mm;
          }
          #proforma-sheet {
            width: 100% !important;
            min-width: 100% !important;
            max-width: 100% !important;
            min-height: auto !important;
            height: auto !important;
            padding: 0 !important;
            margin: 0 !important;
            box-shadow: none !important;
            border: none !important;
            page-break-after: ${isMultiPageExpected ? 'auto' : 'avoid'} !important;
            break-after: ${isMultiPageExpected ? 'auto' : 'avoid'} !important;
            page-break-inside: avoid !important;
            break-inside: avoid !important;
          }
        }
      `}</style>

      <div className="max-w-5xl mx-auto space-y-4 pb-20 print:p-0 print:m-0 print:pb-0 print:space-y-0">
        
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
        {/* ULTRA-PREMIUM MODERN A4 PROFORMA INVOICE SHEET                            */}
        {/* Clean, Light, Professional Enterprise Standard (Selling Point Aesthetic)  */}
        {/* ========================================================================= */}
        <div className="w-full overflow-x-auto p-2 sm:p-6 flex justify-center bg-slate-100/80 dark:bg-slate-950/40 print:bg-white print:p-0 print:m-0">
          <div 
            id="proforma-sheet"
            className="w-[210mm] max-w-[210mm] shrink-0 min-h-[260mm] print:min-h-0 print:h-auto print:w-full print:max-w-none print:m-0 print:p-0 bg-white text-slate-900 p-8 sm:p-9 print:p-0 flex flex-col justify-between mx-auto font-sans border border-slate-200/90 print:border-none rounded-2xl print:rounded-none transition-all"
            style={{ boxSizing: 'border-box' }}
          >
            {/* Top Section */}
            <div className="flex-1 flex flex-col">
              
              {/* Header Letterhead: Brand Logo / Company Details (Left) & Document Meta (Right) */}
              <div className="flex justify-between items-start gap-4 pb-4 print:pb-3 border-b border-slate-200">
                
                {/* Left: Brand Identity */}
                <div className="max-w-[460px] space-y-1">
                  {/* Dynamic Brand Logo (Saved in DB, auto-compressed, sharp on print/PDF) */}
                  {logoSrc ? (
                    <div className="mb-2.5">
                      <img 
                        crossOrigin="anonymous"
                        src={logoSrc} 
                        alt="Company Logo" 
                        className="max-h-14 max-w-[220px] object-contain object-left"
                        loading="lazy"
                        onError={(e) => {
                          (e.target as HTMLElement).style.display = 'none';
                        }}
                      />
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 mb-2">
                      <div className="w-9 h-9 rounded-xl bg-slate-900 text-white flex items-center justify-center font-black text-base">
                        {(company.name || 'V')[0]?.toUpperCase()}
                      </div>
                      <span className="text-[10px] font-bold tracking-widest text-slate-400 uppercase">ENTERPRISE QUOTATION</span>
                    </div>
                  )}

                  <h1 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight leading-snug">
                    {company.name || 'Company Name'}
                  </h1>
                  {company.legal_name && company.legal_name !== company.name && (
                    <p className="text-[11px] text-slate-500 font-medium leading-none">
                      Legal Name: {company.legal_name}
                    </p>
                  )}
                  {company.tagline && (
                    <p className="text-[10.5px] text-slate-500 italic font-medium">
                      {company.tagline}
                    </p>
                  )}

                  {company.address && (
                    <p className="text-[10.5px] text-slate-600 leading-relaxed pt-0.5">
                      {company.address}{company.city ? `, ${company.city}` : ''}{company.state_name ? `, ${company.state_name}` : ''}{company.pincode ? ` - ${company.pincode}` : ''}
                    </p>
                  )}

                  {/* Tax & Contact Pills */}
                  <div className="pt-1.5 flex flex-wrap gap-1.5 text-[10px] font-mono text-slate-700">
                    {company.gstin && (
                      <span className="px-2 py-0.5 bg-slate-100 rounded border border-slate-200/80 font-bold">
                        GSTIN: <strong className="text-slate-900">{company.gstin}</strong>
                      </span>
                    )}
                    {company.pan && (
                      <span className="px-2 py-0.5 bg-slate-100 rounded border border-slate-200/80">
                        PAN: <strong>{company.pan}</strong>
                      </span>
                    )}
                    {company.phone && (
                      <span className="px-2 py-0.5 bg-slate-50 rounded border border-slate-200/80 font-sans">
                        Tel: {company.phone}
                      </span>
                    )}
                    {company.email && (
                      <span className="px-2 py-0.5 bg-slate-50 rounded border border-slate-200/80 font-sans">
                        Email: {company.email}
                      </span>
                    )}
                  </div>
                </div>

                {/* Right: Document Identification & Validity */}
                <div className="text-right space-y-2 shrink-0">
                  <div>
                    <span className="inline-block px-3 py-1 rounded-lg text-xs font-black tracking-wider uppercase bg-slate-900 text-white">
                      {isPI ? 'PROFORMA INVOICE' : 'COMMERCIAL QUOTATION'}
                    </span>
                    <p className="text-[9.5px] font-bold text-slate-400 uppercase tracking-wider mt-1">
                      Pre-GST Commercial Estimate
                    </p>
                  </div>

                  <div className="text-lg font-black font-mono text-slate-900 tracking-tight">
                    {doc.proforma_number}
                  </div>

                  <div className="text-[11px] text-slate-700 font-mono space-y-1 bg-slate-50 p-2.5 rounded-xl border border-slate-200/80 inline-block text-left min-w-[210px]">
                    <div className="flex justify-between gap-2 border-b border-slate-200/60 pb-1">
                      <span className="font-sans text-slate-500">Document Date:</span>
                      <strong className="text-slate-900">{doc.date}</strong>
                    </div>
                    {doc.valid_until && (
                      <div className="flex justify-between gap-2 border-b border-slate-200/60 pb-1 text-amber-800">
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

              {/* Party Information Grid: Billed To / Recipient & Commercial Scope */}
              <div className="grid grid-cols-2 gap-4 my-3.5 print:my-2 text-xs">
                
                {/* Billed To Customer Card */}
                <div className="p-3.5 print:p-2.5 bg-slate-50/70 rounded-xl border border-slate-200/80 space-y-1.5">
                  <div className="flex justify-between items-center border-b border-slate-200/80 pb-1">
                    <span className="text-[9.5px] font-bold text-slate-400 uppercase tracking-wider">
                      Billed To / Customer:
                    </span>
                    <span className="text-[9.5px] font-mono font-bold px-1.5 py-0.5 rounded bg-slate-200/60 text-slate-600">
                      {doc.buyer_gstin ? 'REGISTERED TAXPAYER' : 'CONSUMER / UNREGISTERED'}
                    </span>
                  </div>
                  
                  <div className="font-black text-sm text-slate-900 leading-snug">
                    {doc.party_name || doc.buyer_name || 'Valued Customer'}
                  </div>
                  
                  {doc.buyer_address && (
                    <div className="text-slate-600 leading-relaxed text-[11px] line-clamp-2">
                      {doc.buyer_address}
                    </div>
                  )}

                  <div className="text-slate-700 font-mono space-y-0.5 pt-1 text-[11px]">
                    <div>GSTIN / UIN: <strong className="text-slate-900">{doc.buyer_gstin || 'Unregistered'}</strong></div>
                    {doc.buyer_state_code && (
                      <div>State: {STATE_NAMES[doc.buyer_state_code] || doc.buyer_state_code} ({doc.buyer_state_code})</div>
                    )}
                    {doc.buyer_phone && <div className="font-sans text-slate-600">Phone: {doc.buyer_phone}</div>}
                  </div>
                </div>

                {/* Commercial Scope Card */}
                <div className="p-3.5 print:p-2.5 bg-slate-50/70 rounded-xl border border-slate-200/80 space-y-1.5 flex flex-col justify-between">
                  <div>
                    <div className="border-b border-slate-200/80 pb-1 mb-1.5">
                      <span className="text-[9.5px] font-bold text-slate-400 uppercase tracking-wider">
                        Commercial Terms &amp; Scope:
                      </span>
                    </div>

                    <div className="space-y-1 text-[11px] text-slate-700">
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
                          <span>Quotation Validity:</span>
                          <strong className="font-mono">{doc.valid_until}</strong>
                        </div>
                      )}
                    </div>
                  </div>

                  {isConverted && doc.converted_voucher_number && (
                    <div className="text-[10.5px] text-emerald-800 bg-emerald-50 px-2.5 py-1 rounded-lg border border-emerald-200 font-semibold flex items-center gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                      <span>Formal GST Tax Invoice Generated: <strong>{doc.converted_voucher_number}</strong></span>
                    </div>
                  )}
                </div>

              </div>

              {/* Line Items Table */}
              <div className="border border-slate-200 rounded-xl overflow-hidden my-3 print:my-2">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-slate-100/80 text-slate-700 font-bold text-[10px] uppercase tracking-wider border-b border-slate-200">
                      <th className="py-2 px-2.5 w-8 text-center">#</th>
                      <th className="py-2 px-2.5">Description of Goods / Services</th>
                      <th className="py-2 px-2.5 text-center w-24">HSN/SAC</th>
                      <th className="py-2 px-2.5 text-right w-20">Qty</th>
                      <th className="py-2 px-2.5 text-right w-24">Unit Rate (₹)</th>
                      <th className="py-2 px-2.5 text-right w-16">Disc %</th>
                      <th className="py-2 px-2.5 text-right w-24">Taxable (₹)</th>
                      <th className="py-2 px-2.5 text-center w-14">GST</th>
                      <th className="py-2 px-2.5 text-right w-28">Amount (₹)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-mono text-[11px]">
                    {doc.items?.map((item: any, idx: number) => (
                      <tr key={item.id || idx} className={idx % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'}>
                        <td className="py-2 px-2.5 text-center text-slate-400 font-sans">{idx + 1}</td>
                        <td className="py-2 px-2.5 font-sans font-medium text-slate-900">
                          {item.item_name}
                        </td>
                        <td className="py-2 px-2.5 text-center text-slate-600">{item.hsn_code || '-'}</td>
                        <td className="py-2 px-2.5 text-right text-slate-900 font-semibold">
                          {Number(item.quantity).toFixed(2)} <span className="text-[9.5px] text-slate-500 font-sans">{item.unit || 'Pcs'}</span>
                        </td>
                        <td className="py-2 px-2.5 text-right text-slate-800">
                          {Number(item.rate).toFixed(2)}
                        </td>
                        <td className="py-2 px-2.5 text-right text-slate-500">
                          {item.discount_percent > 0 ? `${Number(item.discount_percent).toFixed(2)}%` : '-'}
                        </td>
                        <td className="py-2 px-2.5 text-right text-slate-900 font-semibold">
                          {Number(item.taxable_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>
                        <td className="py-2 px-2.5 text-center text-slate-600">
                          {item.gst_rate}%
                        </td>
                        <td className="py-2 px-2.5 text-right font-bold text-slate-900">
                          {Number(item.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="bg-slate-100/90 border-t-2 border-slate-200 font-mono text-xs font-bold text-slate-900">
                      <td colSpan={3} className="py-2 px-2.5 font-sans uppercase text-[10px] text-slate-600">
                        Subtotals:
                      </td>
                      <td className="py-2 px-2.5 text-right">
                        {totalQty.toFixed(2)}
                      </td>
                      <td colSpan={2}></td>
                      <td className="py-2 px-2.5 text-right">
                        ₹{totalTaxable.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                      <td></td>
                      <td className="py-2 px-2.5 text-right text-slate-900">
                        ₹{finalGrandTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>

              {/* Tax Transparency Breakdown (Left) & Financial Calculations (Right) */}
              <div className="grid grid-cols-2 gap-4 my-3 print:my-2 text-xs">
                
                {/* Left: HSN / SAC Tax Breakdown Table & Payment Notes */}
                <div className="space-y-3 print:space-y-1.5 flex flex-col justify-between">
                  
                  {/* HSN Table */}
                  <div className="border border-slate-200 rounded-xl overflow-hidden">
                    <div className="bg-slate-100/90 px-3 py-1 text-[9.5px] font-bold uppercase tracking-wider text-slate-600 border-b border-slate-200">
                      HSN / SAC Tax Transparency Breakdown
                    </div>
                    <table className="w-full text-left text-[10.5px] font-mono border-collapse">
                      <thead>
                        <tr className="bg-slate-50 text-slate-500 border-b border-slate-200 font-semibold">
                          <th className="py-1.5 px-2.5">Tax Rate</th>
                          <th className="py-1.5 px-2.5 text-right">Taxable Amt (₹)</th>
                          {!isInterState ? (
                            <>
                              <th className="py-1.5 px-2.5 text-right">CGST (₹)</th>
                              <th className="py-1.5 px-2.5 text-right">SGST (₹)</th>
                            </>
                          ) : (
                            <th className="py-1.5 px-2.5 text-right">IGST (₹)</th>
                          )}
                          <th className="py-1.5 px-2.5 text-right font-bold text-slate-900">Total Tax (₹)</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {hsnSummary.map((hs, idx) => (
                          <tr key={idx}>
                            <td className="py-1 px-2.5 font-medium text-slate-800">{hs.gst_rate}%</td>
                            <td className="py-1 px-2.5 text-right text-slate-700">{hs.taxable_amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                            {!isInterState ? (
                              <>
                                <td className="py-1 px-2.5 text-right text-slate-700">{hs.cgst_amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                                <td className="py-1 px-2.5 text-right text-slate-700">{hs.sgst_amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                              </>
                            ) : (
                              <td className="py-1 px-2.5 text-right text-slate-700">{hs.igst_amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                            )}
                            <td className="py-1 px-2.5 text-right font-bold text-slate-900">{hs.total_tax.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Amount in Words */}
                  <div className="p-2.5 print:p-1.5 bg-slate-50 rounded-xl border border-slate-200/80">
                    <span className="text-[9.5px] font-bold text-slate-400 uppercase tracking-wider block mb-0.5">
                      Total Amount in Words:
                    </span>
                    <span className="font-semibold text-slate-900 font-sans leading-tight block text-[11px]">
                      {numberToWords(finalGrandTotal)}
                    </span>
                  </div>

                  {/* Instant Advance UPI QR Code & Banking Block */}
                  <div className="p-3 print:p-2 bg-slate-50 rounded-xl border border-slate-200/80 flex items-center gap-3">
                    <div className="p-1.5 bg-white rounded-lg border border-slate-200 shrink-0">
                      <QRCode 
                        value={upiPayUrl}
                        size={56}
                        level="M"
                      />
                    </div>
                    <div className="space-y-0.5 leading-tight flex-1 text-[10.5px]">
                      <div className="font-bold text-slate-900 flex items-center gap-1">
                        <QrCode className="w-3.5 h-3.5 text-emerald-600" />
                        <span>{upiId ? 'Scan & Pay Advance via UPI' : 'Digital Verification QR'}</span>
                      </div>
                      {upiId ? (
                        <div className="font-mono text-emerald-700 font-bold">
                          UPI ID: {upiId}
                        </div>
                      ) : null}
                      {company.bank_details?.account_number && (
                        <div className="font-mono text-slate-600 pt-0.5 text-[10px]">
                          <div>A/C: <strong className="text-slate-900">{company.bank_details.account_number}</strong> | IFSC: <strong className="text-slate-900">{company.bank_details.ifsc}</strong></div>
                          <div>Bank: {company.bank_details.bank_name}{company.bank_details.branch ? ` (${company.bank_details.branch})` : ''}</div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Terms & Conditions */}
                  <div className="text-[10px] text-slate-500 leading-relaxed">
                    <span className="font-bold uppercase tracking-wider text-slate-600 block mb-0.5">
                      Commercial Terms:
                    </span>
                    <p className="whitespace-pre-line">
                      {doc.terms_and_conditions || 
                        `1. Prices valid for 15 days from issue date. 2. 100% advance required before dispatch. 3. Subject to '${company.city || 'Kanpur'}' jurisdiction.`
                      }
                    </p>
                  </div>
                </div>

                {/* Right: Financial Summary Box */}
                <div className="p-4 print:p-2.5 bg-slate-50/80 rounded-xl border border-slate-200/80 font-mono text-xs space-y-2 print:space-y-1 flex flex-col justify-between">
                  <div className="space-y-1.5 print:space-y-0.5">
                    <div className="flex justify-between py-1 print:py-0.5 border-b border-slate-200">
                      <span className="text-slate-600 font-sans">Taxable Value:</span>
                      <span className="font-semibold text-slate-900">
                        ₹{totalTaxable.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </span>
                    </div>

                    {totalCgst > 0 && (
                      <div className="flex justify-between py-1 print:py-0.5 border-b border-slate-200">
                        <span className="text-slate-600 font-sans">Central Tax (CGST):</span>
                        <span className="font-semibold text-slate-900">
                          ₹{totalCgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                      </div>
                    )}

                    {totalSgst > 0 && (
                      <div className="flex justify-between py-1 print:py-0.5 border-b border-slate-200">
                        <span className="text-slate-600 font-sans">State Tax (SGST):</span>
                        <span className="font-semibold text-slate-900">
                          ₹{totalSgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                      </div>
                    )}

                    {totalIgst > 0 && (
                      <div className="flex justify-between py-1 print:py-0.5 border-b border-slate-200">
                        <span className="text-slate-600 font-sans">Integrated Tax (IGST):</span>
                        <span className="font-semibold text-slate-900">
                          ₹{totalIgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                      </div>
                    )}

                    {cartageAmount > 0 && (
                      <div className="flex justify-between py-1 print:py-0.5 border-b border-slate-200">
                        <span className="text-slate-600 font-sans">Freight / Cartage:</span>
                        <span className="font-semibold text-slate-900">
                          ₹{cartageAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                      </div>
                    )}

                    {hasRoundOff && (
                      <div className="flex justify-between py-1 print:py-0.5 border-b border-slate-200 text-slate-500">
                        <span className="font-sans">Round Off Adjustment:</span>
                        <span>{roundOff > 0 ? `+${roundOff.toFixed(2)}` : roundOff.toFixed(2)}</span>
                      </div>
                    )}
                  </div>

                  {/* Grand Total Box */}
                  <div className="mt-3 print:mt-1.5 p-3 print:p-2 bg-slate-900 text-white rounded-xl flex justify-between items-center">
                    <div>
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block leading-tight">
                        Total Payable Amount
                      </span>
                      <span className="text-[10.5px] text-slate-300 font-sans">
                        (Inclusive of all Taxes)
                      </span>
                    </div>
                    <div className="text-xl print:text-lg font-black font-mono tracking-tight text-white">
                      ₹{finalGrandTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                </div>

              </div>

            </div>

            {/* Bottom Signature & Legal Notice Section (Pinned strictly to bottom of page) */}
            <div className="pt-4 print:pt-2 border-t border-slate-200 mt-3 print:mt-2 space-y-2.5 print:space-y-1">
              <div className="flex justify-between items-end text-xs">
                
                {/* Buyer Acceptance Signature */}
                <div className="w-1/2 pr-6 space-y-1">
                  <div className="font-bold text-slate-800 text-[11px] uppercase tracking-wider">
                    Customer Acceptance Signature:
                  </div>
                  <p className="text-[10px] text-slate-500">
                    Sign &amp; stamp to approve commercial quotation
                  </p>
                  <div className="mt-8 print:mt-4 border-b border-slate-400 w-44"></div>
                  <div className="text-[10px] text-slate-400 font-sans">Authorized Buyer Signatory</div>
                </div>

                {/* Seller Signatory */}
                <div className="w-1/2 pl-6 text-right flex flex-col items-end space-y-1">
                  <div className="font-bold text-slate-900 text-[11px] uppercase tracking-wider">
                    For {company.legal_name || company.name || 'Seller'}:
                  </div>
                  
                  {/* Digital Signature Image with smooth fallback */}
                  <div className="h-10 print:h-7 flex items-center justify-end my-0.5">
                    {signatureSrc ? (
                      <img 
                        crossOrigin="anonymous"
                        src={signatureSrc} 
                        alt="Authorized Signature" 
                        className="max-h-10 print:max-h-7 max-w-[150px] object-contain" 
                        loading="lazy"
                        onError={(e) => {
                          (e.target as HTMLElement).style.display = 'none';
                        }}
                      />
                    ) : (
                      <div className="w-32 h-7 border border-dashed border-slate-300 rounded flex items-center justify-center text-[10px] text-slate-400">
                        Official Stamp / Seal
                      </div>
                    )}
                  </div>

                  <div className="border-b border-slate-400 w-48"></div>
                  <div className="font-bold text-slate-800 text-xs">
                    {company.proprietor_name ? company.proprietor_name : 'Authorized Signatory'}
                  </div>
                  <div className="text-[10px] text-slate-400">Authorised Signatory</div>
                </div>

              </div>

              {/* Bottom Legal Disclaimer & Page Tracker */}
              <div className="flex justify-between items-center text-[10px] text-slate-400 pt-2 print:pt-1 border-t border-slate-100">
                <span>
                  <strong>Notice:</strong> This is a Commercial Proforma Invoice / Quotation and is <u>NOT</u> a GST Tax Invoice. Goods dispatched upon advance payment.
                </span>
                <span className="font-mono font-semibold text-slate-500 shrink-0 ml-2">
                  {isMultiPageExpected ? 'Page 1 of 2' : 'Page 1 of 1'}
                </span>
              </div>
            </div>

          </div>
        </div>

      </div>
    </DashboardLayout>
  );
}
