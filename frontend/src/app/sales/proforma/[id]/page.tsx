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
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [isGeneratingShareLink, setIsGeneratingShareLink] = useState(false);

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
  }, [docId]);

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

  // High-Resolution Direct Vector PDF Generator
  const handleDownloadPdf = async () => {
    const element = document.getElementById('proforma-sheet');
    if (!element) return;
    setIsGeneratingPdf(true);

    try {
      const targetWidthPx = 794; // Standard A4 width at 96 DPI
      const targetHeightPx = 1123; // Standard A4 height at 96 DPI (297mm)
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
      if (!isMultiPageExpected) {
        clone.style.height = `${targetHeightPx}px`;
        clone.style.minHeight = `${targetHeightPx}px`;
        clone.style.maxHeight = `${targetHeightPx}px`;
        clone.style.overflow = 'hidden';
      } else {
        clone.style.height = 'auto';
        clone.style.minHeight = 'auto';
      }
      clone.style.backgroundColor = '#ffffff';
      clone.style.boxSizing = 'border-box';
      clone.style.margin = '0';
      clone.style.boxShadow = 'none';
      clone.style.borderRadius = '0';
      clone.style.border = 'none';
      clone.style.padding = '30px 38px';
      clone.style.display = 'flex';
      clone.style.flexDirection = 'column';
      clone.style.justifyContent = 'space-between';

      sandbox.appendChild(clone);
      document.body.appendChild(sandbox);

      // Normalizes any Tailwind v4 OKLAB / OKLCH / color-mix colors to standard RGB/HEX
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
            return ctx.fillStyle;
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

      const origHtmlBg = document.documentElement.style.backgroundColor;
      const origBodyBg = document.body.style.backgroundColor;
      document.documentElement.style.backgroundColor = '#ffffff';
      document.body.style.backgroundColor = '#ffffff';

      const canvas = await (html2canvas as any)(clone, {
        scale: 2,
        useCORS: true,
        allowTaint: true,
        logging: false,
        backgroundColor: '#ffffff',
        width: targetWidthPx,
        windowWidth: targetWidthPx,
        onclone: (clonedDoc: Document, clonedEl: HTMLElement) => {
          if (clonedDoc.documentElement) {
            clonedDoc.documentElement.style.backgroundColor = '#ffffff';
          }
          if (clonedDoc.body) {
            clonedDoc.body.style.backgroundColor = '#ffffff';
          }
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
      document.documentElement.style.backgroundColor = origHtmlBg;
      document.body.style.backgroundColor = origBodyBg;

      const imgData = canvas.toDataURL('image/png');
      const pdf = new jsPDF({
        orientation: 'portrait',
        unit: 'mm',
        format: 'a4',
      });

      const a4Width = 210;
      const a4Height = 297;

      if (!isMultiPageExpected) {
        pdf.addImage(imgData, 'PNG', 0, 0, a4Width, a4Height);
      } else {
        const imgHeight = (canvas.height * a4Width) / canvas.width;
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

      const cleanFilename = `${(doc.proforma_number || 'PROFORMA').replace(/[/\\:*?"<>|]/g, '-').trim()}.pdf`;
      pdf.save(cleanFilename);
      toast.success('PDF Downloaded', `Saved as ${cleanFilename}`);
    } catch (err: any) {
      console.error('PDF Export Error:', err);
      toast.error('Download Failed', err?.message || 'Could not generate PDF directly.');
    } finally {
      setIsGeneratingPdf(false);
    }
  };

  const handleShareWhatsApp = async () => {
    if (!doc) return;
    const docTitle = isPI ? 'Proforma Invoice' : 'Commercial Quotation';
    const partyName = doc.buyer_name || doc.party_name || 'Valued Customer';
    const amountStr = finalGrandTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 });
    
    let rawPhone = (doc.buyer_phone || '').replace(/[^0-9]/g, '');
    if (rawPhone.length === 10) rawPhone = '91' + rawPhone;

    // Get public share URL (generates if needed)
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
      {/* Strict Print CSS */}
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
            color: #1a1a2e !important;
            width: 210mm !important;
            height: ${isMultiPageExpected ? 'auto' : '297mm'} !important;
            max-height: ${isMultiPageExpected ? 'none' : '297mm'} !important;
            overflow: ${isMultiPageExpected ? 'visible' : 'hidden'} !important;
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
          #proforma-sheet {
            box-sizing: border-box !important;
            width: 210mm !important;
            min-width: 210mm !important;
            max-width: 210mm !important;
            height: ${isMultiPageExpected ? 'auto' : '297mm'} !important;
            min-height: ${isMultiPageExpected ? 'auto' : '297mm'} !important;
            max-height: ${isMultiPageExpected ? 'none' : '297mm'} !important;
            padding: 8mm 10mm !important;
            margin: 0 auto !important;
            box-shadow: none !important;
            border: none !important;
            border-radius: 0 !important;
            background-color: #ffffff !important;
            display: flex !important;
            flex-direction: column !important;
            justify-content: space-between !important;
            page-break-after: ${isMultiPageExpected ? 'auto' : 'avoid'} !important;
            break-after: ${isMultiPageExpected ? 'auto' : 'avoid'} !important;
            page-break-inside: avoid !important;
            break-inside: avoid !important;
            overflow: hidden !important;
          }
        }
      `}</style>

      <div className="max-w-5xl mx-auto space-y-4 pb-20 print:p-0 print:m-0 print:pb-0 print:space-y-0">
        
        {/* Action Header (Hidden in Print) */}
        <div className="print:hidden flex flex-col md:flex-row justify-between items-start md:items-center gap-3 bg-card/70 backdrop-blur-md border border-border p-3.5 rounded-2xl shadow-xs">
          
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

          <div className="flex items-center gap-2 flex-wrap w-full md:w-auto justify-end">
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

            <button
              type="button"
              onClick={handleCopyLink}
              disabled={isGeneratingShareLink}
              className="p-1.5 bg-card hover:bg-muted border border-border text-foreground rounded-xl transition-colors cursor-pointer disabled:opacity-50"
              title={shareUrl ? 'Copy Public Link' : 'Generate & Copy Public Share Link'}
            >
              {isGeneratingShareLink ? (
                <Loader2 className="w-3.5 h-3.5 text-muted-foreground animate-spin" />
              ) : copiedLink ? (
                <Check className="w-3.5 h-3.5 text-emerald-500" />
              ) : (
                <Copy className="w-3.5 h-3.5 text-muted-foreground" />
              )}
            </button>

            <button
              type="button"
              onClick={handleShareWhatsApp}
              className="px-3 py-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 dark:hover:bg-emerald-950/60 border border-emerald-300 dark:border-emerald-800 rounded-xl text-xs font-bold transition-colors flex items-center gap-1.5 cursor-pointer"
              title="Share via WhatsApp"
            >
              <MessageCircle className="w-3.5 h-3.5 text-emerald-600" />
              <span>WhatsApp</span>
            </button>

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

        {/* ═══════════════════════════════════════════════════════════════════ */}
        {/* PREMIUM A4 PROFORMA INVOICE — Dark header, elegant tables        */}
        {/* ═══════════════════════════════════════════════════════════════════ */}
        <div className="w-full overflow-x-auto p-2 sm:p-6 flex justify-center bg-slate-100/80 dark:bg-slate-950/40 print:bg-white print:p-0 print:m-0 print:overflow-visible">
          <div
            id="proforma-sheet"
            className="w-[210mm] max-w-[210mm] shrink-0 min-h-[297mm] bg-white text-slate-800 flex flex-col mx-auto font-sans shadow-2xl print:shadow-none print:border-none"
            style={{ boxSizing: 'border-box' }}
          >
            {/* Top Content */}
            <div className="flex-1 flex flex-col">

              {/* ── HEADER BAND ── */}
              <div style={{ background: 'linear-gradient(135deg, #0f172a 0%, #1e3a5f 60%, #0f172a 100%)', padding: '28px 36px 22px 36px', position: 'relative', overflow: 'hidden' }}>
                <div style={{ position: 'absolute', top: -40, right: -40, width: 160, height: 160, borderRadius: '50%', background: 'rgba(255,255,255,0.04)', pointerEvents: 'none' }} />
                <div style={{ position: 'absolute', bottom: -20, left: '42%', width: 80, height: 80, borderRadius: '50%', background: 'rgba(255,255,255,0.03)', pointerEvents: 'none' }} />

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', position: 'relative' }}>
                  {/* Left: Logo + Company */}
                  <div style={{ maxWidth: '58%' }}>
                    {logoSrc ? (
                      <div style={{ marginBottom: 10 }}>
                        <img crossOrigin="anonymous" src={logoSrc} alt="Logo" style={{ maxHeight: 40, maxWidth: 160, objectFit: 'contain', objectPosition: 'left', filter: 'brightness(0) invert(1)', opacity: 0.92 }} onError={(e) => { (e.target as HTMLElement).style.display = 'none'; }} />
                      </div>
                    ) : null}
                    <div style={{ fontSize: 20, fontWeight: 800, color: '#ffffff', letterSpacing: '-0.02em', lineHeight: 1.15 }}>
                      {company.name || 'Company Name'}
                    </div>
                    {company.legal_name && company.legal_name !== company.name && (
                      <div style={{ fontSize: 9, color: '#94a3b8', fontWeight: 600, letterSpacing: '0.12em', textTransform: 'uppercase' as const, marginTop: 2 }}>{company.legal_name}</div>
                    )}
                    {company.address && (
                      <div style={{ fontSize: 9.5, color: '#94a3b8', marginTop: 5, lineHeight: 1.5 }}>
                        {company.address}{company.city ? `, ${company.city}` : ''}{company.state_name ? `, ${company.state_name}` : ''}{company.pincode ? ` – ${company.pincode}` : ''}
                      </div>
                    )}
                    <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: '0 20px', marginTop: 5, fontSize: 9, color: '#64748b' }}>
                      {company.gstin && <span>GSTIN: <strong style={{ color: '#94a3b8', fontFamily: 'monospace' }}>{company.gstin}</strong></span>}
                      {company.pan && <span>PAN: <strong style={{ color: '#94a3b8', fontFamily: 'monospace' }}>{company.pan}</strong></span>}
                      {company.phone && <span>{company.phone}</span>}
                      {company.email && <span>{company.email}</span>}
                    </div>
                  </div>

                  {/* Right: Document Badge */}
                  <div style={{ textAlign: 'right' as const, flexShrink: 0 }}>
                    <div style={{ display: 'inline-block', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, padding: '6px 14px', marginBottom: 10 }}>
                      <div style={{ fontSize: 9, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.18em', textTransform: 'uppercase' as const }}>
                        {isPI ? 'Proforma Invoice' : 'Quotation'}
                      </div>
                      <div style={{ fontSize: 18, fontWeight: 800, color: '#f1f5f9', letterSpacing: '-0.02em', marginTop: 2, fontFamily: 'monospace' }}>
                        {doc.proforma_number}
                      </div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 4, alignItems: 'flex-end' }}>
                      <div style={{ display: 'flex', gap: 16, fontSize: 9.5, color: '#94a3b8' }}>
                        <span>Date</span>
                        <span style={{ color: '#e2e8f0', fontWeight: 600, minWidth: 80 }}>{doc.date}</span>
                      </div>
                      {doc.valid_until && (
                        <div style={{ display: 'flex', gap: 16, fontSize: 9.5, color: '#94a3b8' }}>
                          <span>Valid Until</span>
                          <span style={{ color: '#fde68a', fontWeight: 700, minWidth: 80, fontFamily: 'monospace' }}>{doc.valid_until}</span>
                        </div>
                      )}
                      <div style={{ display: 'flex', gap: 16, fontSize: 9.5, color: '#94a3b8' }}>
                        <span>Supply</span>
                        <span style={{ color: '#e2e8f0', fontWeight: 600, minWidth: 80 }}>{placeOfSupply}</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Tri-color accent */}
                <div style={{ marginTop: 18, display: 'flex', gap: 0, height: 2 }}>
                  <div style={{ flex: 2, background: '#3b82f6' }} />
                  <div style={{ flex: 1, background: '#f59e0b' }} />
                  <div style={{ flex: 3, background: '#1e40af' }} />
                </div>
              </div>

              {/* ── BILL TO + SUPPLY DETAILS ── */}
              <div style={{ padding: '18px 36px 14px 36px', borderBottom: '1px solid #f1f5f9', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 32 }}>
                <div>
                  <div style={{ fontSize: 8.5, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.18em', textTransform: 'uppercase' as const, marginBottom: 6 }}>Bill To</div>
                  <div style={{ fontSize: 13, fontWeight: 800, color: '#0f172a', lineHeight: 1.2, marginBottom: 4 }}>
                    {doc.party_name || doc.buyer_name || 'Valued Customer'}
                  </div>
                  {doc.buyer_address && <div style={{ fontSize: 10, color: '#64748b', lineHeight: 1.55, marginBottom: 4 }}>{doc.buyer_address}</div>}
                  <div style={{ fontSize: 9.5, color: '#64748b', display: 'flex', flexDirection: 'column' as const, gap: 2 }}>
                    <span>GSTIN: <strong style={{ color: '#334155', fontFamily: 'monospace', letterSpacing: '0.04em' }}>{doc.buyer_gstin || 'Unregistered'}</strong></span>
                    {doc.buyer_state_code && <span>State: {STATE_NAMES[doc.buyer_state_code] || doc.buyer_state_code} ({doc.buyer_state_code})</span>}
                    {doc.buyer_phone && <span>Ph: {doc.buyer_phone}</span>}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 8.5, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.18em', textTransform: 'uppercase' as const, marginBottom: 6 }}>Supply Details</div>
                  <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 5, fontSize: 10 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: '#94a3b8' }}>Tax Regime</span>
                      <span style={{ fontWeight: 700, color: '#1e293b' }}>{isInterState ? 'IGST (Inter-State)' : 'CGST + SGST'}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: '#94a3b8' }}>Payment</span>
                      <span style={{ fontWeight: 700, color: '#1e293b' }}>100% Advance</span>
                    </div>
                    {doc.valid_until && (
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: '#94a3b8' }}>Valid Till</span>
                        <span style={{ fontWeight: 700, color: '#b45309', fontFamily: 'monospace' }}>{doc.valid_until}</span>
                      </div>
                    )}
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: '#94a3b8' }}>Status</span>
                      <span style={{ fontWeight: 700, color: isConverted ? '#059669' : doc.status === 'ACCEPTED' ? '#2563eb' : doc.status === 'SENT' ? '#d97706' : '#64748b', textTransform: 'uppercase' as const, letterSpacing: '0.06em', fontSize: 9 }}>{doc.status}</span>
                    </div>
                  </div>
                  {isConverted && doc.converted_voucher_number && (
                    <div style={{ marginTop: 8, background: '#ecfdf5', border: '1px solid #a7f3d0', borderRadius: 6, padding: '5px 10px', fontSize: 9, color: '#065f46', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 5 }}>
                      ✓ Converted → GST Invoice <strong style={{ fontFamily: 'monospace' }}>{doc.converted_voucher_number}</strong>
                    </div>
                  )}
                </div>
              </div>

              {/* ── ITEMS TABLE ── */}
              <div style={{ padding: '0 36px' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' as const, fontSize: 10 }}>
                  <thead>
                    <tr style={{ background: '#0f172a' }}>
                      <th style={{ padding: '8px 6px 8px 8px', textAlign: 'center' as const, width: 24, fontSize: 8, fontWeight: 700, color: '#64748b', letterSpacing: '0.1em', textTransform: 'uppercase' as const }}>#</th>
                      <th style={{ padding: '8px 6px', textAlign: 'left' as const, fontSize: 8, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.1em', textTransform: 'uppercase' as const }}>Item Description</th>
                      <th style={{ padding: '8px 6px', textAlign: 'center' as const, width: 64, fontSize: 8, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.1em', textTransform: 'uppercase' as const }}>HSN/SAC</th>
                      <th style={{ padding: '8px 6px', textAlign: 'right' as const, width: 52, fontSize: 8, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.1em', textTransform: 'uppercase' as const }}>Qty</th>
                      <th style={{ padding: '8px 6px', textAlign: 'right' as const, width: 64, fontSize: 8, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.1em', textTransform: 'uppercase' as const }}>Rate</th>
                      <th style={{ padding: '8px 6px', textAlign: 'right' as const, width: 44, fontSize: 8, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.1em', textTransform: 'uppercase' as const }}>Disc</th>
                      <th style={{ padding: '8px 6px', textAlign: 'right' as const, width: 72, fontSize: 8, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.1em', textTransform: 'uppercase' as const }}>Taxable</th>
                      <th style={{ padding: '8px 6px', textAlign: 'center' as const, width: 40, fontSize: 8, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.1em', textTransform: 'uppercase' as const }}>GST</th>
                      <th style={{ padding: '8px 8px 8px 6px', textAlign: 'right' as const, width: 76, fontSize: 8, fontWeight: 700, color: '#f1f5f9', letterSpacing: '0.1em', textTransform: 'uppercase' as const }}>Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {doc.items?.map((item: any, idx: number) => (
                      <tr key={item.id || idx} style={{ background: idx % 2 === 0 ? '#ffffff' : '#f8fafc', borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '7px 6px 7px 8px', textAlign: 'center' as const, color: '#94a3b8', fontSize: 9 }}>{idx + 1}</td>
                        <td style={{ padding: '7px 6px', fontWeight: 600, color: '#0f172a' }}>{item.item_name}</td>
                        <td style={{ padding: '7px 6px', textAlign: 'center' as const, color: '#64748b', fontFamily: 'monospace', fontSize: 9 }}>{item.hsn_code || '—'}</td>
                        <td style={{ padding: '7px 6px', textAlign: 'right' as const, fontFamily: 'monospace', color: '#475569' }}>
                          {Number(item.quantity).toFixed(2)} <span style={{ fontSize: 8, color: '#94a3b8' }}>{item.unit || 'Pcs'}</span>
                        </td>
                        <td style={{ padding: '7px 6px', textAlign: 'right' as const, fontFamily: 'monospace', color: '#475569' }}>{Number(item.rate).toFixed(2)}</td>
                        <td style={{ padding: '7px 6px', textAlign: 'right' as const, fontFamily: 'monospace', color: '#94a3b8', fontSize: 9 }}>
                          {item.discount_percent > 0 ? `${Number(item.discount_percent).toFixed(1)}%` : '—'}
                        </td>
                        <td style={{ padding: '7px 6px', textAlign: 'right' as const, fontFamily: 'monospace', fontWeight: 600, color: '#334155' }}>
                          {Number(item.taxable_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>
                        <td style={{ padding: '7px 6px', textAlign: 'center' as const, fontFamily: 'monospace', fontSize: 9, color: '#64748b' }}>{item.gst_rate}%</td>
                        <td style={{ padding: '7px 8px 7px 6px', textAlign: 'right' as const, fontFamily: 'monospace', fontWeight: 700, color: '#0f172a' }}>
                          {Number(item.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr style={{ background: '#f1f5f9', borderTop: '2px solid #1e293b' }}>
                      <td colSpan={3} style={{ padding: '7px 6px 7px 8px', fontSize: 8.5, fontWeight: 700, color: '#475569', letterSpacing: '0.1em', textTransform: 'uppercase' as const }}>Total</td>
                      <td style={{ padding: '7px 6px', textAlign: 'right' as const, fontFamily: 'monospace', fontWeight: 700, color: '#0f172a' }}>{totalQty.toFixed(2)}</td>
                      <td colSpan={2} />
                      <td style={{ padding: '7px 6px', textAlign: 'right' as const, fontFamily: 'monospace', fontWeight: 700, color: '#0f172a' }}>₹{totalTaxable.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                      <td />
                      <td style={{ padding: '7px 8px 7px 6px', textAlign: 'right' as const, fontFamily: 'monospace', fontWeight: 800, color: '#0f172a', fontSize: 11 }}>₹{finalGrandTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>

              {/* ── TAX + FINANCIAL SUMMARY ── */}
              <div style={{ padding: '14px 36px 10px 36px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 28 }}>
                {/* Left column */}
                <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 12 }}>
                  {/* Tax Breakdown */}
                  <div>
                    <div style={{ fontSize: 8, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.15em', textTransform: 'uppercase' as const, marginBottom: 6 }}>Tax Breakdown</div>
                    <table style={{ width: '100%', fontSize: 9.5, borderCollapse: 'collapse' as const }}>
                      <thead>
                        <tr style={{ borderBottom: '1px solid #e2e8f0' }}>
                          <th style={{ padding: '3px 4px 3px 0', textAlign: 'left' as const, fontWeight: 600, color: '#64748b' }}>Rate</th>
                          <th style={{ padding: '3px 4px', textAlign: 'right' as const, fontWeight: 600, color: '#64748b' }}>Taxable</th>
                          {!isInterState ? (
                            <>
                              <th style={{ padding: '3px 4px', textAlign: 'right' as const, fontWeight: 600, color: '#64748b' }}>CGST</th>
                              <th style={{ padding: '3px 4px', textAlign: 'right' as const, fontWeight: 600, color: '#64748b' }}>SGST</th>
                            </>
                          ) : (
                            <th style={{ padding: '3px 4px', textAlign: 'right' as const, fontWeight: 600, color: '#64748b' }}>IGST</th>
                          )}
                          <th style={{ padding: '3px 0 3px 4px', textAlign: 'right' as const, fontWeight: 700, color: '#1e293b' }}>Tax</th>
                        </tr>
                      </thead>
                      <tbody>
                        {hsnSummary.map((hs, idx) => (
                          <tr key={idx} style={{ borderBottom: '1px solid #f8fafc' }}>
                            <td style={{ padding: '3px 4px 3px 0', fontFamily: 'monospace', color: '#475569', fontWeight: 600 }}>{hs.gst_rate}%</td>
                            <td style={{ padding: '3px 4px', textAlign: 'right' as const, fontFamily: 'monospace', color: '#475569' }}>{hs.taxable_amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                            {!isInterState ? (
                              <>
                                <td style={{ padding: '3px 4px', textAlign: 'right' as const, fontFamily: 'monospace', color: '#475569' }}>{hs.cgst_amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                                <td style={{ padding: '3px 4px', textAlign: 'right' as const, fontFamily: 'monospace', color: '#475569' }}>{hs.sgst_amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                              </>
                            ) : (
                              <td style={{ padding: '3px 4px', textAlign: 'right' as const, fontFamily: 'monospace', color: '#475569' }}>{hs.igst_amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                            )}
                            <td style={{ padding: '3px 0 3px 4px', textAlign: 'right' as const, fontFamily: 'monospace', fontWeight: 700, color: '#0f172a' }}>{hs.total_tax.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Amount in Words */}
                  <div style={{ background: '#f8fafc', borderRadius: 6, padding: '7px 10px', borderLeft: '3px solid #3b82f6' }}>
                    <div style={{ fontSize: 7.5, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.15em', textTransform: 'uppercase' as const, marginBottom: 3 }}>Amount in Words</div>
                    <div style={{ fontSize: 10, fontWeight: 600, color: '#1e293b', fontStyle: 'italic', lineHeight: 1.45 }}>
                      {numberToWords(finalGrandTotal)}
                    </div>
                  </div>

                  {/* QR + Bank */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ padding: 4, background: '#fff', border: '1px solid #e2e8f0', borderRadius: 6, flexShrink: 0 }}>
                      <QRCode value={upiPayUrl} size={46} level="M" />
                    </div>
                    <div style={{ fontSize: 9, color: '#64748b', lineHeight: 1.6 }}>
                      <div style={{ fontWeight: 700, color: '#334155', marginBottom: 2 }}>
                        {upiId ? '⚡ Scan to Pay via UPI' : '🔒 Digital Verification'}
                      </div>
                      {upiId && <div style={{ fontFamily: 'monospace', color: '#475569' }}>UPI: {upiId}</div>}
                      {company.bank_details?.account_number && (
                        <div style={{ fontFamily: 'monospace', fontSize: 8.5, color: '#94a3b8' }}>
                          A/C: {company.bank_details.account_number} · IFSC: {company.bank_details.ifsc}
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Right column: Financial Summary */}
                <div style={{ display: 'flex', flexDirection: 'column' as const, justifyContent: 'space-between' }}>
                  <div>
                    {[
                      { label: 'Taxable Value', val: `₹${totalTaxable.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` },
                      ...(totalCgst > 0 ? [{ label: 'CGST', val: `₹${totalCgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` }] : []),
                      ...(totalSgst > 0 ? [{ label: 'SGST', val: `₹${totalSgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` }] : []),
                      ...(totalIgst > 0 ? [{ label: 'IGST', val: `₹${totalIgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` }] : []),
                      ...(cartageAmount > 0 ? [{ label: 'Freight / Cartage', val: `₹${cartageAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` }] : []),
                      ...(hasRoundOff ? [{ label: 'Round Off', val: roundOff > 0 ? `+${roundOff.toFixed(2)}` : roundOff.toFixed(2) }] : []),
                    ].map((row, i) => (
                      <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', borderBottom: '1px solid #f1f5f9', fontSize: 10.5 }}>
                        <span style={{ color: '#64748b' }}>{row.label}</span>
                        <span style={{ fontFamily: 'monospace', fontWeight: 600, color: '#334155' }}>{row.val}</span>
                      </div>
                    ))}
                  </div>

                  {/* Grand Total */}
                  <div style={{ marginTop: 12, borderRadius: 8, overflow: 'hidden', boxShadow: '0 2px 12px rgba(15,23,42,0.18)' }}>
                    <div style={{ background: 'linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%)', padding: '12px 16px 10px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <div style={{ fontSize: 8, fontWeight: 700, color: '#64748b', letterSpacing: '0.18em', textTransform: 'uppercase' as const }}>Total Amount Due</div>
                        <div style={{ fontSize: 8.5, color: '#475569', marginTop: 1 }}>Inclusive of all taxes</div>
                      </div>
                      <div style={{ fontSize: 22, fontWeight: 900, fontFamily: 'monospace', color: '#ffffff', letterSpacing: '-0.02em' }}>
                        ₹{finalGrandTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </div>
                    </div>
                    <div style={{ background: 'linear-gradient(90deg, #3b82f6, #f59e0b, #1e40af)', height: 3 }} />
                  </div>
                </div>
              </div>

              {/* ── TERMS ── */}
              <div style={{ padding: '6px 36px 4px 36px', borderTop: '1px solid #f1f5f9' }}>
                <span style={{ fontSize: 8, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.15em', textTransform: 'uppercase' as const }}>Terms: </span>
                <span style={{ fontSize: 9, color: '#64748b', lineHeight: 1.5 }}>
                  {doc.terms_and_conditions || doc.customer_notes || `Prices valid for 15 days. 100% advance required before dispatch. Subject to ${company.city || 'local'} jurisdiction.`}
                </span>
              </div>

            </div>

            {/* ── FOOTER: SIGNATURES + LEGAL ── */}
            <div style={{ padding: '14px 36px 16px 36px', borderTop: '2px solid #e2e8f0', marginTop: 4 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 14 }}>
                {/* Buyer */}
                <div style={{ width: '38%' }}>
                  <div style={{ fontSize: 8, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.15em', textTransform: 'uppercase' as const, marginBottom: 4 }}>Customer Acceptance</div>
                  <div style={{ fontSize: 8.5, color: '#94a3b8', marginBottom: 28 }}>Sign &amp; stamp to confirm</div>
                  <div style={{ borderBottom: '1px solid #94a3b8', width: 140, marginBottom: 4 }} />
                  <div style={{ fontSize: 8.5, color: '#64748b' }}>Authorised Signatory</div>
                </div>
                {/* Seller */}
                <div style={{ textAlign: 'right' as const, width: '40%', display: 'flex', flexDirection: 'column' as const, alignItems: 'flex-end' }}>
                  <div style={{ fontSize: 8, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.15em', textTransform: 'uppercase' as const, marginBottom: 6 }}>
                    For {company.legal_name || company.name || 'Seller'}
                  </div>
                  <div style={{ height: 32, display: 'flex', alignItems: 'center', justifyContent: 'flex-end', marginBottom: 4 }}>
                    {signatureSrc ? (
                      <img crossOrigin="anonymous" src={signatureSrc} alt="Signature" style={{ maxHeight: 32, maxWidth: 130, objectFit: 'contain' }} onError={(e) => { (e.target as HTMLElement).style.display = 'none'; }} />
                    ) : (
                      <div style={{ width: 120, height: 28, border: '1px dashed #cbd5e1', borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 8.5, color: '#94a3b8' }}>Seal / Stamp</div>
                    )}
                  </div>
                  <div style={{ borderBottom: '1px solid #94a3b8', width: 160, marginBottom: 4 }} />
                  <div style={{ fontSize: 10, fontWeight: 700, color: '#1e293b' }}>{company.proprietor_name || 'Authorised Signatory'}</div>
                </div>
              </div>

              {/* Bottom bar + legal */}
              <div style={{ display: 'flex', gap: 0, height: 2, marginBottom: 6 }}>
                <div style={{ flex: 3, background: '#0f172a' }} />
                <div style={{ flex: 1, background: '#3b82f6' }} />
                <div style={{ flex: 1, background: '#f59e0b' }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 8, color: '#94a3b8' }}>
                <span>This is a <strong style={{ color: '#64748b' }}>{isPI ? 'Proforma Invoice' : 'Quotation'}</strong> — <em>not</em> a GST Tax Invoice. Goods dispatched upon advance payment.</span>
                <span style={{ fontFamily: 'monospace', color: '#64748b', flexShrink: 0, marginLeft: 12 }}>{isMultiPageExpected ? 'Page 1 of 2+' : 'Page 1 of 1'}</span>
              </div>
            </div>

          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
