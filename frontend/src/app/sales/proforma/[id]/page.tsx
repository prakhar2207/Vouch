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
  Building2,
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
        {/* LIGHT, MINIMALISTIC & PROFESSIONAL PROFORMA INVOICE SHEET        */}
        {/* ═══════════════════════════════════════════════════════════════════ */}
        <div className="w-full overflow-x-auto p-2 sm:p-6 flex justify-center bg-slate-100/70 dark:bg-slate-950/40 print:bg-white print:p-0 print:m-0 print:overflow-visible">
          <div
            id="proforma-sheet"
            className="w-[210mm] max-w-[210mm] shrink-0 min-h-[297mm] bg-white text-slate-900 flex flex-col mx-auto font-sans border border-slate-200/90 shadow-md print:shadow-none print:border-none p-8 sm:p-10"
            style={{ boxSizing: 'border-box' }}
          >
            {/* Top Content */}
            <div className="flex-1 flex flex-col">

              {/* ── HEADER: COMPANY LOGO & IDENTITY + DOCUMENT BADGE ── */}
              <div className="flex justify-between items-start gap-8 pb-6 border-b border-slate-200/90">
                
                {/* Left: Dedicated Logo Space & Company Details */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-start gap-4 mb-3.5">
                    {/* Dedicated Logo Container */}
                    <div className="h-14 min-w-[56px] max-w-[200px] flex items-center justify-start shrink-0">
                      {logoSrc ? (
                        <img 
                          crossOrigin="anonymous"
                          src={logoSrc} 
                          alt={company.name || 'Company Logo'} 
                          className="max-h-14 max-w-[200px] object-contain object-left"
                          loading="lazy"
                          onError={(e) => {
                            (e.target as HTMLElement).style.display = 'none';
                          }}
                        />
                      ) : (
                        <div className="h-14 w-14 rounded-xl border border-dashed border-slate-300 bg-slate-50 flex flex-col items-center justify-center text-slate-400 p-1">
                          <Building2 className="w-6 h-6 text-slate-400 stroke-[1.5]" />
                          <span className="text-[7.5px] font-semibold uppercase tracking-wider text-slate-400 mt-0.5">Logo</span>
                        </div>
                      )}
                    </div>

                    <div className="min-w-0">
                      <h1 className="text-xl font-bold tracking-tight text-slate-900 leading-tight">
                        {company.name || 'Company Name'}
                      </h1>
                      {company.legal_name && company.legal_name !== company.name && (
                        <p className="text-[10.5px] font-medium text-slate-500 uppercase tracking-wider mt-0.5">
                          {company.legal_name}
                        </p>
                      )}
                    </div>
                  </div>

                  {company.address && (
                    <p className="text-[11px] text-slate-600 leading-relaxed max-w-md">
                      {company.address}{company.city ? `, ${company.city}` : ''}{company.state_name ? `, ${company.state_name}` : ''}{company.pincode ? ` – ${company.pincode}` : ''}
                    </p>
                  )}

                  <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-[10.5px] text-slate-500">
                    {company.gstin && (
                      <span>GSTIN: <strong className="font-mono text-slate-800 font-semibold">{company.gstin}</strong></span>
                    )}
                    {company.pan && (
                      <span>PAN: <strong className="font-mono text-slate-800 font-semibold">{company.pan}</strong></span>
                    )}
                    {company.phone && <span>Tel: {company.phone}</span>}
                    {company.email && <span>{company.email}</span>}
                  </div>
                </div>

                {/* Right: Clean Minimalist Document Badge */}
                <div className="text-right shrink-0">
                  <div className="inline-block bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-right mb-2.5">
                    <span className="text-[9.5px] font-bold uppercase tracking-widest text-slate-500 block">
                      {isPI ? 'Proforma Invoice' : 'Quotation'}
                    </span>
                    <span className="text-xl font-extrabold font-mono text-slate-900 tracking-tight block mt-0.5">
                      {doc.proforma_number}
                    </span>
                  </div>

                  <div className="space-y-1 text-[11px] text-slate-500">
                    <div className="flex justify-end gap-3">
                      <span className="text-slate-400">Date:</span>
                      <strong className="text-slate-800 font-semibold">{doc.date}</strong>
                    </div>
                    {doc.valid_until && (
                      <div className="flex justify-end gap-3">
                        <span className="text-slate-400">Valid Until:</span>
                        <strong className="text-amber-700 font-mono font-semibold">{doc.valid_until}</strong>
                      </div>
                    )}
                    <div className="flex justify-end gap-3">
                      <span className="text-slate-400">Place of Supply:</span>
                      <strong className="text-slate-800 font-medium">{placeOfSupply}</strong>
                    </div>
                  </div>
                </div>
              </div>

              {/* ── BILL TO + COMMERCIAL TERMS GRID ── */}
              <div className="grid grid-cols-2 gap-6 p-4 bg-slate-50/70 rounded-xl border border-slate-200/80 my-5">
                
                {/* Bill To */}
                <div className="space-y-1">
                  <div className="text-[9.5px] font-bold uppercase tracking-widest text-slate-400 mb-1">
                    Bill To
                  </div>
                  <div className="text-sm font-bold text-slate-900 leading-snug">
                    {doc.party_name || doc.buyer_name || 'Valued Customer'}
                  </div>
                  {doc.buyer_address && (
                    <div className="text-[10.5px] text-slate-600 leading-relaxed">
                      {doc.buyer_address}
                    </div>
                  )}
                  <div className="text-[10.5px] text-slate-500 space-y-0.5 pt-1">
                    <div>
                      GSTIN: <span className="font-mono text-slate-800 font-semibold">{doc.buyer_gstin || 'Unregistered'}</span>
                    </div>
                    {doc.buyer_state_code && (
                      <div>
                        State: {STATE_NAMES[doc.buyer_state_code] || doc.buyer_state_code} ({doc.buyer_state_code})
                      </div>
                    )}
                    {doc.buyer_phone && <div>Tel: {doc.buyer_phone}</div>}
                  </div>
                </div>

                {/* Commercial Details */}
                <div className="space-y-1.5 pl-6 border-l border-slate-200">
                  <div className="text-[9.5px] font-bold uppercase tracking-widest text-slate-400 mb-1">
                    Commercial Terms
                  </div>
                  <div className="space-y-1.5 text-[11px]">
                    <div className="flex justify-between">
                      <span className="text-slate-500">Tax Application:</span>
                      <span className="font-semibold text-slate-800">
                        {isInterState ? 'IGST (Inter-State)' : 'CGST + SGST (Intra-State)'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Payment Terms:</span>
                      <span className="font-semibold text-slate-800">100% Advance Payment</span>
                    </div>
                    {doc.valid_until && (
                      <div className="flex justify-between">
                        <span className="text-slate-500">Quotation Validity:</span>
                        <span className="font-semibold font-mono text-amber-700">{doc.valid_until}</span>
                      </div>
                    )}
                    <div className="flex justify-between items-center">
                      <span className="text-slate-500">Document Status:</span>
                      <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border ${
                        isConverted 
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200' 
                          : doc.status === 'ACCEPTED' 
                          ? 'bg-blue-50 text-blue-700 border-blue-200' 
                          : doc.status === 'SENT' 
                          ? 'bg-amber-50 text-amber-700 border-amber-200' 
                          : 'bg-slate-100 text-slate-600 border-slate-200'
                      }`}>
                        {doc.status}
                      </span>
                    </div>
                  </div>
                  {isConverted && doc.converted_voucher_number && (
                    <div className="mt-2 p-1.5 bg-emerald-50 rounded border border-emerald-200 text-[10.5px] text-emerald-800 font-semibold flex items-center gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 shrink-0 text-emerald-600" />
                      <span>Converted to GST Invoice <strong>{doc.converted_voucher_number}</strong></span>
                    </div>
                  )}
                </div>
              </div>

              {/* ── LINE ITEMS TABLE ── */}
              <div className="mb-5 overflow-hidden rounded-xl border border-slate-200">
                <table className="w-full text-left border-collapse text-[11px]">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 text-[9.5px] font-bold uppercase tracking-wider text-slate-500">
                      <th className="py-2.5 px-2 text-center w-8">#</th>
                      <th className="py-2.5 px-3">Item Description</th>
                      <th className="py-2.5 px-2 text-center w-20">HSN/SAC</th>
                      <th className="py-2.5 px-2 text-right w-16">Qty</th>
                      <th className="py-2.5 px-2 text-right w-20">Rate (₹)</th>
                      <th className="py-2.5 px-2 text-right w-14">Disc %</th>
                      <th className="py-2.5 px-2 text-right w-24">Taxable (₹)</th>
                      <th className="py-2.5 px-2 text-center w-14">GST %</th>
                      <th className="py-2.5 px-3 text-right w-24">Amount (₹)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {doc.items?.map((item: any, idx: number) => (
                      <tr key={item.id || idx} className="hover:bg-slate-50/50">
                        <td className="py-2.5 px-2 text-center text-slate-400 text-[10px]">{idx + 1}</td>
                        <td className="py-2.5 px-3 font-medium text-slate-900">{item.item_name}</td>
                        <td className="py-2.5 px-2 text-center font-mono text-[10px] text-slate-500">{item.hsn_code || '—'}</td>
                        <td className="py-2.5 px-2 text-right font-mono text-slate-700">
                          {Number(item.quantity).toFixed(2)} <span className="text-[9.5px] text-slate-400">{item.unit || 'Pcs'}</span>
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono text-slate-700">{Number(item.rate).toFixed(2)}</td>
                        <td className="py-2.5 px-2 text-right font-mono text-slate-400 text-[10px]">
                          {item.discount_percent > 0 ? `${Number(item.discount_percent).toFixed(1)}%` : '—'}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono font-medium text-slate-800">
                          {Number(item.taxable_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>
                        <td className="py-2.5 px-2 text-center font-mono text-[10px] text-slate-500">{item.gst_rate}%</td>
                        <td className="py-2.5 px-3 text-right font-mono font-semibold text-slate-900">
                          {Number(item.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t-2 border-slate-200 font-bold bg-slate-50/80 text-[11px]">
                      <td colSpan={3} className="py-2.5 px-3 text-slate-600 uppercase text-[9.5px] tracking-wider">Total Quantity &amp; Taxable</td>
                      <td className="py-2.5 px-2 text-right font-mono text-slate-900">{totalQty.toFixed(2)}</td>
                      <td colSpan={2}></td>
                      <td className="py-2.5 px-2 text-right font-mono text-slate-900">
                        ₹{totalTaxable.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                      <td></td>
                      <td className="py-2.5 px-3 text-right font-mono text-slate-900 text-xs font-black">
                        ₹{finalGrandTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>

              {/* ── TAX BREAKDOWN & FINANCIAL TOTALS ── */}
              <div className="grid grid-cols-2 gap-6 mb-5 items-start">
                
                {/* Left Column: Tax breakdown + Words + UPI Bank */}
                <div className="space-y-3">
                  
                  {/* GST Breakdown */}
                  <div className="rounded-xl border border-slate-200 p-3 bg-white">
                    <div className="text-[9.5px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">
                      GST Breakdown
                    </div>
                    <table className="w-full text-left text-[10px] border-collapse">
                      <thead>
                        <tr className="border-b border-slate-200 text-slate-400 font-medium">
                          <th className="py-1 px-1">GST Rate</th>
                          <th className="py-1 px-1 text-right">Taxable</th>
                          {!isInterState ? (
                            <>
                              <th className="py-1 px-1 text-right">CGST</th>
                              <th className="py-1 px-1 text-right">SGST</th>
                            </>
                          ) : (
                            <th className="py-1 px-1 text-right">IGST</th>
                          )}
                          <th className="py-1 px-1 text-right">Total Tax</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 font-mono text-slate-600">
                        {hsnSummary.map((hs, idx) => (
                          <tr key={idx}>
                            <td className="py-1 px-1 font-sans">{hs.gst_rate}%</td>
                            <td className="py-1 px-1 text-right">₹{hs.taxable_amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                            {!isInterState ? (
                              <>
                                <td className="py-1 px-1 text-right">₹{hs.cgst_amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                                <td className="py-1 px-1 text-right">₹{hs.sgst_amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                              </>
                            ) : (
                              <td className="py-1 px-1 text-right">₹{hs.igst_amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                            )}
                            <td className="py-1 px-1 text-right font-semibold text-slate-900">₹{hs.total_tax.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Amount Chargeable in words */}
                  <div className="p-3 bg-slate-50/80 rounded-xl border border-slate-200">
                    <span className="text-[9.5px] font-bold uppercase tracking-wider text-slate-400 block mb-0.5">
                      Amount Chargeable (in words)
                    </span>
                    <span className="text-[10.5px] font-medium text-slate-800 italic leading-snug">
                      {numberToWords(finalGrandTotal)}
                    </span>
                  </div>

                  {/* UPI QR & Bank Information */}
                  <div className="flex items-center gap-3 p-3 bg-slate-50/80 rounded-xl border border-slate-200">
                    <div className="p-1.5 bg-white border border-slate-200 rounded-lg shrink-0">
                      <QRCode value={upiPayUrl} size={50} level="M" />
                    </div>
                    <div className="text-[10px] text-slate-500 space-y-0.5">
                      <div className="font-semibold text-slate-800">
                        {upiId ? 'Scan to Pay via UPI' : 'Digital Payment Verification'}
                      </div>
                      {upiId && (
                        <div>
                          UPI ID: <strong className="font-mono text-slate-800">{upiId}</strong>
                        </div>
                      )}
                      {company.bank_details?.account_number && (
                        <div className="font-mono text-[9.5px] text-slate-600">
                          A/C: {company.bank_details.account_number} · IFSC: {company.bank_details.ifsc}
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Right Column: Calculations & Grand Total */}
                <div className="space-y-2">
                  <div className="rounded-xl border border-slate-200 p-3.5 bg-white space-y-1.5 text-[11px]">
                    <div className="flex justify-between py-1 border-b border-slate-100 text-slate-600">
                      <span>Taxable Amount</span>
                      <span className="font-mono font-medium text-slate-900">
                        ₹{totalTaxable.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </span>
                    </div>
                    {totalCgst > 0 && (
                      <div className="flex justify-between py-1 border-b border-slate-100 text-slate-600">
                        <span>Total CGST</span>
                        <span className="font-mono text-slate-800">
                          ₹{totalCgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                      </div>
                    )}
                    {totalSgst > 0 && (
                      <div className="flex justify-between py-1 border-b border-slate-100 text-slate-600">
                        <span>Total SGST</span>
                        <span className="font-mono text-slate-800">
                          ₹{totalSgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                      </div>
                    )}
                    {totalIgst > 0 && (
                      <div className="flex justify-between py-1 border-b border-slate-100 text-slate-600">
                        <span>Total IGST</span>
                        <span className="font-mono text-slate-800">
                          ₹{totalIgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                      </div>
                    )}
                    {cartageAmount > 0 && (
                      <div className="flex justify-between py-1 border-b border-slate-100 text-slate-600">
                        <span>Freight / Cartage</span>
                        <span className="font-mono text-slate-800">
                          ₹{cartageAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                      </div>
                    )}
                    {hasRoundOff && (
                      <div className="flex justify-between py-1 border-b border-slate-100 text-slate-500 text-[10px]">
                        <span>Round Off</span>
                        <span className="font-mono">
                          {roundOff > 0 ? `+₹${roundOff.toFixed(2)}` : `-₹${Math.abs(roundOff).toFixed(2)}`}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Clean Minimalist Light Total Box */}
                  <div className="p-4 bg-slate-50 border-2 border-slate-200/90 rounded-xl flex justify-between items-center">
                    <div>
                      <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500 block leading-tight">
                        Total Payable Amount
                      </span>
                      <span className="text-[10.5px] text-slate-400 font-sans">
                        (Inclusive of all taxes)
                      </span>
                    </div>
                    <div className="text-2xl font-bold font-mono tracking-tight text-slate-900">
                      ₹{finalGrandTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                </div>
              </div>

              {/* ── TERMS & CONDITIONS ── */}
              <div className="text-[10px] text-slate-500 leading-relaxed mb-4">
                <span className="font-bold uppercase tracking-wider text-slate-600">Terms &amp; Conditions: </span>
                {doc.terms_and_conditions || doc.customer_notes || `Prices valid for 15 days from issue date. 100% advance payment required prior to dispatch. Subject to ${company.city || 'local'} jurisdiction.`}
              </div>

            </div>

            {/* ── FOOTER: SIGNATURES & LEGAL NOTICE ── */}
            <div className="pt-4 border-t border-slate-200 mt-auto">
              <div className="flex justify-between items-end mb-4">
                
                {/* Customer Signature */}
                <div className="space-y-1 w-2/5">
                  <span className="text-[9.5px] font-bold uppercase tracking-wider text-slate-400 block">
                    Customer Acceptance
                  </span>
                  <p className="text-[9.5px] text-slate-400">
                    Sign &amp; stamp to approve quotation
                  </p>
                  <div className="mt-8 border-b border-slate-300 w-36"></div>
                  <div className="text-[9.5px] text-slate-500">Authorised Buyer Signatory</div>
                </div>

                {/* Seller Signature */}
                <div className="text-right space-y-1 w-2/5 flex flex-col items-end">
                  <span className="text-[9.5px] font-bold uppercase tracking-wider text-slate-400 block">
                    For {company.legal_name || company.name || 'Seller'}
                  </span>
                  <div className="h-10 flex items-center justify-end my-0.5">
                    {signatureSrc ? (
                      <img 
                        crossOrigin="anonymous" 
                        src={signatureSrc} 
                        alt="Authorised Signature" 
                        className="max-h-10 max-w-[140px] object-contain"
                        loading="lazy"
                        onError={(e) => {
                          (e.target as HTMLElement).style.display = 'none';
                        }}
                      />
                    ) : (
                      <div className="w-28 h-8 border border-dashed border-slate-300 rounded flex items-center justify-center text-[9px] text-slate-400">
                        Official Seal / Stamp
                      </div>
                    )}
                  </div>
                  <div className="border-b border-slate-300 w-44"></div>
                  <div className="text-[10px] font-semibold text-slate-800">
                    {company.proprietor_name || 'Authorised Signatory'}
                  </div>
                </div>
              </div>

              {/* Bottom legal notice & Page count */}
              <div className="flex justify-between items-center text-[9px] text-slate-400 pt-2 border-t border-slate-100">
                <span>
                  This is a <strong className="text-slate-600">{isPI ? 'Proforma Invoice' : 'Quotation'}</strong> and is <u>not</u> a GST Tax Invoice. Goods dispatched upon advance payment.
                </span>
                <span className="font-mono text-slate-500 shrink-0 ml-3">
                  {isMultiPageExpected ? 'Page 1 of 2+' : 'Page 1 of 1'}
                </span>
              </div>
            </div>

          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
