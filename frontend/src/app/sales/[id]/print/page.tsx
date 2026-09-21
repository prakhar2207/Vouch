"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useParams, useRouter } from 'next/navigation';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import QRCode from 'react-qr-code';
import { gstApi, EWayBillData } from '@/lib/api/gst';
import { offlineDb } from '@/lib/db/offlineDb';
import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';
import { 
  Printer, 
  ArrowLeft, 
  Share2, 
  FileText, 
  Receipt,
  MessageCircle,
  Download,
  Loader2,
  ExternalLink,
  Globe,
  Laptop,
  Check,
  Copy,
  X,
  ChevronDown,
  Lock,
  ShieldAlert,
  LogIn,
  History
} from 'lucide-react';
import AuditHistoryModal from '@/components/modals/AuditHistoryModal';

function numberToWords(numAmount: number): string {
  const a = ['','One ','Two ','Three ','Four ', 'Five ','Six ','Seven ','Eight ','Nine ','Ten ','Eleven ','Twelve ','Thirteen ','Fourteen ','Fifteen ','Sixteen ','Seventeen ','Eighteen ','Nineteen '];
  const b = ['', '', 'Twenty','Thirty','Forty','Fifty', 'Sixty','Seventy','Eighty','Ninety'];
  const numStr = Math.floor(numAmount).toString();
  if (numStr.length > 9) return 'overflow';
  let n = ('000000000' + numStr).slice(-9).match(/^(\d{2})(\d{2})(\d{2})(\d{1})(\d{2})$/);
  if (!n) return '';
  let str = '';
  str += (n[1] != '00') ? (a[Number(n[1])] || b[Number(n[1][0])] + ' ' + a[Number(n[1][1])]) + 'Crore ' : '';
  str += (n[2] != '00') ? (a[Number(n[2])] || b[Number(n[2][0])] + ' ' + a[Number(n[2][1])]) + 'Lakh ' : '';
  str += (n[3] != '00') ? (a[Number(n[3])] || b[Number(n[3][0])] + ' ' + a[Number(n[3][1])]) + 'Thousand ' : '';
  str += (n[4] != '0') ? (a[Number(n[4])] || b[Number(n[4][0])] + ' ' + a[Number(n[4][1])]) + 'Hundred ' : '';
  str += (n[5] != '00') ? ((str != '') ? 'and ' : '') + (a[Number(n[5])] || b[Number(n[5][0])] + ' ' + a[Number(n[5][1])]) : '';
  return str.trim() + ' Only';
}

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

export default function PrintInvoicePage() {
  const params = useParams();
  const router = useRouter();
  const invoiceId = params.id as string;
  const [invoice, setInvoice] = useState<any>(null);
  const [ewayBill, setEwayBill] = useState<EWayBillData | null>(null);
  const [layoutMode, setLayoutMode] = useState<'A4' | 'THERMAL'>('A4');
  const [isGeneratingPdf, setIsGeneratingPdf] = useState<boolean>(false);
  const [isWhatsAppModalOpen, setIsWhatsAppModalOpen] = useState<boolean>(false);
  const [copiedToClipboard, setCopiedToClipboard] = useState<boolean>(false);
  const [shareStatusMessage, setShareStatusMessage] = useState<string | null>(null);
  const [isAuth, setIsAuth] = useState<boolean>(false);
  const [copiedLink, setCopiedLink] = useState<boolean>(false);
  const [copiedMessage, setCopiedMessage] = useState<boolean>(false);
  const [preferredWhatsAppClient, setPreferredWhatsAppClient] = useState<'web' | 'app'>('web');
  const [isAuditModalOpen, setIsAuditModalOpen] = useState<boolean>(false);

  const [downloadPermission, setDownloadPermission] = useState<{
    can_download: boolean;
    reason?: string;
    company_type?: string;
    user_role?: string;
    allowed_roles?: string[];
  } | null>(null);
  const [authModalOpen, setAuthModalOpen] = useState<boolean>(false);
  const [authModalReason, setAuthModalReason] = useState<string>('');

  useEffect(() => {
    setIsAuth(isAuthenticated());
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('vouch_preferred_wa_client') as 'web' | 'app';
      if (saved === 'web' || saved === 'app') {
        setPreferredWhatsAppClient(saved);
      }
    }
    fetchInvoice();
  }, [invoiceId]);

  const [loadError, setLoadError] = useState<string | null>(null);

  const fetchInvoice = async () => {
    try {
      // 1. Handle offline invoices directly from client IndexedDB
      if (invoiceId && String(invoiceId).startsWith('offline_')) {
        const localId = String(invoiceId).replace('offline_', '');
        try {
          const localVoucher = await offlineDb.vouchers.where('localId').equals(localId).first();
          if (localVoucher && localVoucher.payload) {
            const p = localVoucher.payload;
            const activeCompId = (typeof window !== 'undefined' ? localStorage.getItem('vouch_active_company_id') : '') || p.company_id || '';
            let compInfo = { name: p.company_name || 'My Company', gstin: p.company_gstin || '', state_code: p.company_state_code || '' };
            if (activeCompId) {
              try {
                const cachedComp = await offlineDb.masters.get(`company_${activeCompId}`);
                if (cachedComp && cachedComp.data) {
                  compInfo = { ...compInfo, ...cachedComp.data };
                }
              } catch {}
            }

            const offlineInvoice = {
              id: invoiceId,
              voucher_number: localVoucher.voucherNumber || p.voucher_number || 'PENDING SYNC',
              voucher_date: localVoucher.voucherDate || p.voucher_date || new Date().toISOString().split('T')[0],
              total_amount: Number(p.total_amount || p.round_off_total || 0),
              round_off: Number(p.round_off || 0),
              is_offline: true,
              sync_status: localVoucher.status,
              error_message: localVoucher.errorMessage,
              company: compInfo,
              party: {
                name: p.party_name || p.buyer_name || 'Customer',
                gstin: p.party_gstin || p.buyer_gstin || '',
                phone: p.party_phone || p.buyer_phone || '',
                state_code: p.party_state_code || p.buyer_state_code || '',
              },
              items: (p.items || []).map((it: any) => ({
                product_name: it.product_name || it.name || it.description || 'Item',
                hsn_code: it.hsn_code || '',
                quantity: Number(it.quantity || 1),
                unit_rate: Number(it.unit_rate || it.rate || 0),
                taxable_amount: Number(it.taxable_amount || 0),
                cgst_rate: Number(it.cgst_rate || 0),
                sgst_rate: Number(it.sgst_rate || 0),
                igst_rate: Number(it.igst_rate || 0),
                total_amount: Number(it.total_amount || 0),
              })),
            };
            setInvoice(offlineInvoice);
            setDownloadPermission({ can_download: true });
            return;
          }
        } catch (offlineErr) {
          console.warn('Failed to load local offline voucher:', offlineErr);
        }
        setLoadError('This offline invoice is not available on this device. Please ensure it has synced to the cloud.');
        return;
      }

      let res;
      const token = getAccessToken();
      const headers = token ? { Authorization: `Bearer ${token}` } : {};

      if (token) {
        try {
          res = await axios.get(`${API_BASE_URL}/api/v1/accounting/vouchers/detail/${invoiceId}/`, { headers });
        } catch (authErr) {
          // Fallback to public endpoint with auth headers so backend can evaluate user permissions
          res = await axios.get(`${API_BASE_URL}/api/v1/accounting/vouchers/public/${invoiceId}/`, { headers });
        }
      } else {
        // Public viewing for recipients without an account (e.g. via QR scan)
        res = await axios.get(`${API_BASE_URL}/api/v1/accounting/vouchers/public/${invoiceId}/`);
      }

      if (res?.data?.data) {
        const invData = res.data.data;
        setInvoice(invData);

        if (invData.download_permission) {
          setDownloadPermission(invData.download_permission);
        }

        if (invData.eway_bill && invData.eway_bill.status !== 'CAN') {
          setEwayBill(invData.eway_bill);
        } else if (token) {
          try {
            const ewayRes = await gstApi.getEWayBillForVoucher(invoiceId);
            if (ewayRes.success && ewayRes.data && ewayRes.data.status !== 'CAN') {
              setEwayBill(ewayRes.data);
            }
          } catch (e) {
            // E-Way Bill is optional
          }
        }
      } else {
        setLoadError('Invoice data not found.');
      }
    } catch (err: any) {
      console.error('Failed to load invoice:', err);
      setLoadError(err.response?.data?.error || 'Invoice not found or could not be loaded.');
    }
  };

  const checkCanDownload = async (): Promise<boolean> => {
    // 1. If download permission already cached from invoice detail payload
    if (downloadPermission !== null) {
      if (downloadPermission.can_download) {
        return true;
      }
      setAuthModalReason(downloadPermission.reason || (isAuthenticated() ? 'ROLE_RESTRICTED' : 'UNAUTHENTICATED'));
      setAuthModalOpen(true);
      return false;
    }

    // 2. Fetch permission dynamically
    try {
      const token = getAccessToken();
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/vouchers/${invoiceId}/download-permission/`, { headers });
      if (res.data?.success && res.data?.data) {
        const perm = res.data.data;
        setDownloadPermission(perm);
        if (perm.can_download) {
          return true;
        } else {
          setAuthModalReason(perm.reason || (token ? 'ROLE_RESTRICTED' : 'UNAUTHENTICATED'));
          setAuthModalOpen(true);
          return false;
        }
      }
    } catch (e) {
      // Fallback
    }

    if (!isAuthenticated()) {
      setAuthModalReason('UNAUTHENTICATED');
      setAuthModalOpen(true);
      return false;
    }
    return true;
  };

  // Auto-download PDF if URL contains ?download=true or ?auto_download=true
  useEffect(() => {
    if (invoice && typeof window !== 'undefined') {
      const urlParams = new URLSearchParams(window.location.search);
      if (urlParams.get('download') === 'true' || urlParams.get('auto_download') === 'true') {
        window.history.replaceState({}, '', window.location.pathname);
        handleDownloadPdf();
      }
    }
  }, [invoice]);

  if (loadError) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900 text-white p-4">
        <div className="max-w-md w-full bg-slate-800 border border-slate-700 rounded-2xl p-6 text-center space-y-4">
          <div className="w-12 h-12 rounded-full bg-rose-500/20 text-rose-400 flex items-center justify-center mx-auto">
            <FileText className="w-6 h-6" />
          </div>
          <h2 className="text-lg font-bold">Invoice Not Found</h2>
          <p className="text-xs text-slate-400">{loadError}</p>
          <button
            onClick={() => router.push('/sales')}
            className="w-full py-2.5 px-4 text-xs font-semibold rounded-xl bg-blue-600 hover:bg-blue-500 text-white transition-colors cursor-pointer"
          >
            Back to Sales Invoices
          </button>
        </div>
      </div>
    );
  }

  if (!invoice) return <div className="p-10 text-center font-mono">Loading Invoice Data...</div>;

  // Calculations
  const isInterState = invoice.company.state_code !== invoice.party.state_code && invoice.company.state_code && invoice.party.state_code;
  
  const companyStateCode = invoice.company?.state_code || '';
  const companyStateName = invoice.company?.state_name || (companyStateCode ? STATE_NAMES[companyStateCode] : '') || '';
  const placeOfSupply = companyStateName 
    ? `${companyStateName}${companyStateCode ? ` (${companyStateCode})` : ''}` 
    : (companyStateCode || 'N/A');
  
  let totalQty = 0;
  let totalTaxable = 0;
  let totalCgst = 0;
  let totalSgst = 0;
  let totalIgst = 0;

  invoice.items.forEach((item: any) => {
    totalQty += Number(item.quantity);
    totalTaxable += Number(item.taxable_amount);
    
    // Reverse calculate tax amounts
    const taxAmt = Number(item.total_amount) - Number(item.taxable_amount);
    if (isInterState) {
        totalIgst += taxAmt;
    } else {
        totalCgst += taxAmt / 2;
        totalSgst += taxAmt / 2;
    }
  });

  const cartageAmount = Number(invoice.cartage_amount || 0);
  const subtotalWithTaxes = totalTaxable + (isInterState ? totalIgst : (totalCgst + totalSgst)) + cartageAmount;
  
  let finalGrandTotal = Number(invoice.total_amount);
  let roundOff = Math.round((finalGrandTotal - subtotalWithTaxes) * 100) / 100;

  const integerPart = Math.floor(subtotalWithTaxes);
  const decimalPart = Math.round((subtotalWithTaxes - integerPart) * 100) / 100;

  if (Math.abs(roundOff) < 0.005 && decimalPart > 0) {
    finalGrandTotal = decimalPart < 0.5 ? integerPart : integerPart + 1;
    roundOff = Math.round((finalGrandTotal - subtotalWithTaxes) * 100) / 100;
  }

  const hasRoundOff = Math.abs(roundOff) >= 0.005;

  const getSignatureUrl = (sig: string | null | undefined) => {
    if (!sig) return '';
    if (sig.startsWith('data:') || sig.startsWith('http://') || sig.startsWith('https://')) {
      return sig;
    }
    return `${API_BASE_URL}${sig.startsWith('/') ? '' : '/'}${sig}`;
  };

  const getCleanInvoiceFilename = () => {
    const rawInvoiceNo = invoice?.voucher_number || 'INVOICE';
    return `${rawInvoiceNo.replace(/[/\\:*?"<>|]/g, '-').trim()}.pdf`;
  };

  const getCleanPhone = () => {
    let phone = invoice?.party?.phone || invoice?.party?.mobile || '';
    phone = phone.replace(/[^0-9]/g, '');
    if (phone.length === 10) {
      phone = '91' + phone;
    }
    return phone;
  };

  const isMobileOrPWA = () => {
    if (typeof window === 'undefined') return false;
    const isMobileUA = /Android|iPhone|iPad|iPod|Windows Phone|webOS/i.test(navigator.userAgent);
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches || (window.navigator as any).standalone === true;
    const isTouch = 'ontouchstart' in window && window.innerWidth <= 820;
    return isMobileUA || isStandalone || isTouch;
  };

  const generateInvoicePdf = async (): Promise<{ file: File; blobUrl: string } | null> => {
    const element = document.getElementById('invoice-sheet');
    if (!element) return null;

    const isThermal = layoutMode === 'THERMAL';
    // Standard A4 width: 210mm = 794px at 96 DPI
    // Standard 80mm thermal width: 80mm = 302px at 96 DPI
    const targetWidthPx = isThermal ? 302 : 794;

    // Create an isolated off-screen sandbox container with forced LIGHT theme.
    // This completely prevents dark mode styles from turning invoice text white/faint!
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

    // Inject strict high-contrast printing styles into the sandbox
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
      .print-sandbox-root .bg-white {
        background-color: #ffffff !important;
      }
      .print-sandbox-root .text-slate-500, .print-sandbox-root .text-slate-600, .print-sandbox-root .text-slate-700 {
        color: #1e293b !important;
      }
      .print-sandbox-root .text-emerald-400, .print-sandbox-root .text-emerald-500, .print-sandbox-root .text-emerald-600 {
        color: #059669 !important;
      }
      .print-sandbox-root .border-dashed {
        border-style: dashed !important;
      }
      .print-sandbox-root .border-dotted {
        border-style: dotted !important;
      }
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

    if (!isThermal) {
      // Remove min-height override and adjust padding so standard invoices fit cleanly on 1 page
      clone.style.minHeight = 'unset';
      clone.style.padding = '18px 24px';
      clone.style.margin = '0 auto';
    }
    sandbox.appendChild(clone);
    document.body.appendChild(sandbox);

    let canvas;
    try {
      canvas = await (html2canvas as any)(clone, {
        scale: 2,
        useCORS: true,
        allowTaint: true,
        logging: false,
        backgroundColor: '#ffffff',
        windowWidth: isThermal ? 400 : 1200,
        width: targetWidthPx,
      });
    } finally {
      document.body.removeChild(sandbox);
    }

    // Copy canvas image to clipboard for instant Ctrl+V pasting in WhatsApp Web or Desktop App
    try {
      canvas.toBlob((blob: Blob | null) => {
        if (blob && typeof ClipboardItem !== 'undefined' && navigator.clipboard?.write) {
          navigator.clipboard.write([
            new ClipboardItem({ 'image/png': blob })
          ]).then(() => setCopiedToClipboard(true)).catch(() => {});
        }
      }, 'image/png');
    } catch (e) {
      // Clipboard copy optional
    }

    const imgData = canvas.toDataURL('image/png');
    let pdf: jsPDF;

    if (isThermal) {
      const pdfWidth = 80;
      const imgHeight = (canvas.height * pdfWidth) / canvas.width;
      pdf = new jsPDF({
        orientation: 'portrait',
        unit: 'mm',
        format: [pdfWidth, Math.max(100, imgHeight)],
      });
      pdf.addImage(imgData, 'PNG', 0, 0, pdfWidth, imgHeight);
    } else {
      // Standard A4 PDF (strictly 210mm x 297mm)
      pdf = new jsPDF({
        orientation: 'portrait',
        unit: 'mm',
        format: 'a4',
      });
      const a4Width = 210;
      const a4Height = 297;
      const imgHeight = (canvas.height * a4Width) / canvas.width;

      // Fit single-sheet invoices on exactly 1 single A4 page
      // Allow up to 15% margin for subpixel rendering variations to stay strictly on 1 page
      if (imgHeight <= a4Height * 1.15) {
        // Fits comfortably on a single standard A4 sheet
        const renderHeight = Math.min(imgHeight, a4Height);
        pdf.addImage(imgData, 'PNG', 0, 0, a4Width, renderHeight);
      } else {
        // Multi-page standard A4 splitting for invoices with many items
        let heightLeft = imgHeight;
        let position = 0;

        pdf.addImage(imgData, 'PNG', 0, position, a4Width, imgHeight);
        heightLeft -= a4Height;

        while (heightLeft > 8) { // 8mm threshold to avoid microscopic second page
          position -= a4Height;
          pdf.addPage('a4', 'portrait');
          pdf.addImage(imgData, 'PNG', 0, position, a4Width, imgHeight);
          heightLeft -= a4Height;
        }
      }
    }

    const filename = getCleanInvoiceFilename();
    const pdfBlob = pdf.output('blob');
    const file = new File([pdfBlob], filename, { type: 'application/pdf' });
    const blobUrl = URL.createObjectURL(file);

    return { file, blobUrl };
  };

  const triggerPdfDownload = (blobUrl: string, filename: string) => {
    const downloadLink = document.createElement('a');
    downloadLink.href = blobUrl;
    downloadLink.download = filename;
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);
  };

  const buildWhatsAppTextMessage = () => {
    if (!invoice) return '';
    const invoiceNo = invoice.voucher_number || 'Invoice';
    const companyName = invoice.company?.name || 'Our Company';
    const partyName = invoice.party?.name || 'Valued Customer';
    const total = Number(invoice.total_amount || 0).toLocaleString('en-IN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    
    const origin = typeof window !== 'undefined' ? window.location.origin : '';
    const publicInvoiceUrl = `${origin}/sales/${invoiceId}/print`;

    return (
      `*TAX INVOICE: ${invoiceNo}*\n` +
      `*Company:* ${companyName}\n` +
      `*Customer:* ${partyName}\n` +
      `*Total Amount:* ₹${total}\n\n` +
      `📄 *View & Download Official PDF Invoice:*\n` +
      `${publicInvoiceUrl}\n\n` +
      `Thank you for your business!`
    );
  };

  const getWhatsAppUrls = () => {
    const phone = getCleanPhone();
    const message = buildWhatsAppTextMessage();
    const encoded = encodeURIComponent(message);

    const appUrl = phone 
      ? `whatsapp://send?phone=${phone}&text=${encoded}` 
      : `whatsapp://send?text=${encoded}`;

    const webUrl = phone 
      ? `https://web.whatsapp.com/send?phone=${phone}&text=${encoded}` 
      : `https://web.whatsapp.com/send?text=${encoded}`;

    return { appUrl, webUrl, message };
  };

  const openDesktopWithAutoFallback = (phone: string, filename: string) => {
    const { appUrl, webUrl } = getWhatsAppUrls();

    let appOpened = false;
    const onBlur = () => {
      appOpened = true;
    };
    window.addEventListener('blur', onBlur, { once: true });

    setShareStatusMessage(`Opening WhatsApp with invoice details & PDF link...`);
    setTimeout(() => setShareStatusMessage(null), 8000);

    // Attempt to launch installed desktop WhatsApp application
    try {
      window.location.href = appUrl;
    } catch (e) {}

    // If after 1.5s browser is still focused, WhatsApp desktop app is not installed -> auto-fallback to WhatsApp Web!
    setTimeout(() => {
      window.removeEventListener('blur', onBlur);
      if (!appOpened && document.hasFocus()) {
        window.open(webUrl, '_blank');
      }
    }, 1500);
  };

  const handleOpenExplicitWhatsApp = async (target: 'web' | 'app') => {
    if (!invoice) return;
    const canDownload = await checkCanDownload();
    if (!canDownload) {
      setIsWhatsAppModalOpen(false);
      return;
    }

    setPreferredWhatsAppClient(target);
    if (typeof window !== 'undefined') {
      localStorage.setItem('vouch_preferred_wa_client', target);
    }
    setIsGeneratingPdf(true);
    try {
      const pdfResult = await generateInvoicePdf();
      const filename = getCleanInvoiceFilename();
      if (pdfResult) {
        triggerPdfDownload(pdfResult.blobUrl, filename);
      }
      const { appUrl, webUrl } = getWhatsAppUrls();
      if (target === 'web') {
        window.open(webUrl, '_blank');
        setShareStatusMessage(`Opening WhatsApp Web... Invoice PDF (${filename}) downloaded! Press Ctrl+V in chat to paste image.`);
      } else {
        try {
          window.location.href = appUrl;
        } catch (e) {}
        setShareStatusMessage(`Launching WhatsApp Desktop App... Invoice PDF (${filename}) downloaded! Press Ctrl+V in chat to paste image.`);
      }
      setTimeout(() => setShareStatusMessage(null), 8000);
    } catch (e) {
      console.error('Failed to prepare PDF for WhatsApp:', e);
    } finally {
      setIsGeneratingPdf(false);
      setIsWhatsAppModalOpen(false);
    }
  };

  const handleCopyInvoiceLink = () => {
    if (typeof window === 'undefined') return;
    const publicUrl = `${window.location.origin}/sales/${invoiceId}/print`;
    navigator.clipboard.writeText(publicUrl);
    setCopiedLink(true);
    setTimeout(() => setCopiedLink(false), 3000);
  };

  const handleCopyMessageText = () => {
    const text = buildWhatsAppTextMessage();
    navigator.clipboard.writeText(text);
    setCopiedMessage(true);
    setTimeout(() => setCopiedMessage(false), 3000);
  };

  const handleWhatsAppShareClick = async () => {
    if (!invoice) return;
    const canDownload = await checkCanDownload();
    if (!canDownload) return;

    setIsGeneratingPdf(true);

    try {
      const pdfResult = await generateInvoicePdf();
      if (!pdfResult) {
        alert('Could not render invoice PDF. Please try again.');
        return;
      }

      const { file, blobUrl } = pdfResult;
      const filename = getCleanInvoiceFilename();
      const phone = getCleanPhone();
      const isMobile = isMobileOrPWA();

      // ================= 1. MOBILE / PWA MODE =================
      if (isMobile) {
        // Use Web Share API if available.
        // CRITICAL: We pass ONLY files: [file] without any 'text' parameter!
        // On Android WhatsApp, if 'text' is provided with 'files', WhatsApp discards the file and only sends text.
        // Passing ONLY files: [file] ensures WhatsApp attaches the actual PDF!
        if (typeof navigator !== 'undefined' && navigator.canShare && navigator.canShare({ files: [file] })) {
          try {
            await navigator.share({
              files: [file],
              title: filename,
            });
            return;
          } catch (shareErr: any) {
            if (shareErr?.name === 'AbortError') {
              return; // User cancelled share dialog
            }
          }
        }

        // If Web Share API is not available on mobile, launch WhatsApp with prefilled text and public link
        const { appUrl } = getWhatsAppUrls();
        window.location.href = appUrl;
        return;
      }

      // ================= 2. LAPTOP / DESKTOP MODE =================
      // 1. Download the PDF with the exact invoice number filename
      triggerPdfDownload(blobUrl, filename);

      // 2. Open according to user's preference
      if (preferredWhatsAppClient === 'web') {
        const { webUrl } = getWhatsAppUrls();
        window.open(webUrl, '_blank');
        setShareStatusMessage(`WhatsApp Web opened! Invoice PDF (${filename}) downloaded. Press Ctrl+V in chat to paste image.`);
        setTimeout(() => setShareStatusMessage(null), 8000);
      } else {
        openDesktopWithAutoFallback(phone, filename);
      }

    } catch (err: any) {
      console.error('Failed to share PDF:', err);
      alert(`Could not share invoice PDF: ${err.message || err}`);
    } finally {
      setIsGeneratingPdf(false);
    }
  };

  const handleDownloadPdf = async () => {
    if (!invoice) return;
    const canDownload = await checkCanDownload();
    if (!canDownload) return;

    setIsGeneratingPdf(true);
    try {
      const pdfResult = await generateInvoicePdf();
      if (!pdfResult) return;
      const filename = getCleanInvoiceFilename();
      triggerPdfDownload(pdfResult.blobUrl, filename);
    } catch (err: any) {
      console.error('PDF download failed:', err);
    } finally {
      setIsGeneratingPdf(false);
    }
  };

  const filename = invoice ? getCleanInvoiceFilename() : 'INVOICE.pdf';

  return (
    <div className="bg-white text-black min-h-screen">
      <style>{`
        @media print {
          html, body {
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
            margin: 0 !important;
            padding: 0 !important;
          }
          .print\\:hidden {
            display: none !important;
          }
          ${
            layoutMode === 'THERMAL'
              ? `
            @page {
              size: 80mm auto;
              margin: 2mm;
            }
            body {
              width: 80mm !important;
              max-width: 80mm !important;
            }
            `
              : `
            @page {
              size: A4 portrait;
              margin: 8mm;
            }
            `
          }
        }
      `}</style>

      {/* Print Controls Bar (Hidden on Print) */}
      <div className="print:hidden p-3 bg-slate-900 text-white flex flex-wrap gap-3 justify-between items-center sticky top-0 z-50 shadow-md">
        <div className="flex items-center gap-2">
          {isAuth ? (
            <button 
              onClick={() => router.back()} 
              className="text-slate-300 hover:text-white px-3 py-1.5 bg-slate-800 hover:bg-slate-700 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back</span>
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-800 rounded-lg text-xs font-semibold text-slate-200 border border-slate-700">
                <FileText className="w-3.5 h-3.5 text-emerald-400" />
                <span>Invoice {invoice.voucher_number}</span>
              </div>
              <span className="text-[10px] px-2.5 py-1 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-medium">
                Public View
              </span>
            </div>
          )}

          {/* Layout Toggle: A4 vs 80mm POS Thermal */}
          <div className="flex items-center p-1 bg-slate-800 rounded-xl border border-slate-700 text-xs font-semibold">
            <button
              onClick={() => setLayoutMode('A4')}
              className={`px-3 py-1 rounded-lg flex items-center gap-1.5 transition-all cursor-pointer ${
                layoutMode === 'A4' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-slate-400 hover:text-white'
              }`}
            >
              <FileText className="w-3.5 h-3.5" />
              <span>A4 Invoice</span>
            </button>
            <button
              onClick={() => setLayoutMode('THERMAL')}
              className={`px-3 py-1 rounded-lg flex items-center gap-1.5 transition-all cursor-pointer ${
                layoutMode === 'THERMAL' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-slate-400 hover:text-white'
              }`}
            >
              <Receipt className="w-3.5 h-3.5" />
              <span>80mm POS Thermal</span>
            </button>
          </div>

          {isAuth && (
            <button
              onClick={() => setIsAuditModalOpen(true)}
              className="bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer border border-slate-700"
              title="MCA Statutory Audit Trail & Version History"
            >
              <History className="w-3.5 h-3.5 text-blue-400" />
              <span>Version History</span>
            </button>
          )}
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {!isAuth && (
            <button
              onClick={() => {
                const redirectUrl = encodeURIComponent(window.location.pathname + '?download=true');
                router.push(`/login?redirect=${redirectUrl}`);
              }}
              className="text-slate-300 hover:text-white px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              <LogIn className="w-3.5 h-3.5 text-primary" />
              <span>Sign In</span>
            </button>
          )}

          {/* Print Button */}
          <button
            onClick={() => window.print()}
            className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-xl text-xs font-bold flex items-center gap-2 shadow-sm transition-all cursor-pointer"
          >
            <Printer className="w-4 h-4" />
            <span>Print {layoutMode === 'THERMAL' ? 'Receipt' : 'Invoice'}</span>
          </button>
        </div>
      </div>

      {/* DOWNLOAD AUTHENTICATION / PERMISSION MODAL */}
      {authModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs print:hidden animate-in fade-in duration-200">
          <div className="bg-slate-900 border border-slate-700 text-white rounded-2xl shadow-2xl max-w-md w-full p-6 space-y-4 relative">
            <button
              onClick={() => setAuthModalOpen(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>

            {authModalReason === 'UNAUTHENTICATED' ? (
              <>
                <div className="flex items-center gap-3">
                  <div className="p-3 rounded-xl bg-amber-500/20 text-amber-400">
                    <Lock className="w-6 h-6" />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-white">Login Required to Download</h3>
                    <p className="text-xs text-slate-400">Official GST Tax Invoice</p>
                  </div>
                </div>

                <div className="p-3.5 bg-slate-800/80 rounded-xl border border-slate-700 space-y-2 text-xs text-slate-300">
                  <p>
                    Anyone can view this invoice. However, downloading the official PDF is restricted to authorized <strong>Owners</strong>, <strong>Accountants (CA)</strong>, or <strong>Employees</strong> of either:
                  </p>
                  <ul className="list-disc list-inside space-y-1 text-slate-400 pl-1 font-mono text-[11px]">
                    <li>Billing Company: <span className="text-emerald-400 font-sans">{invoice?.company?.name}</span></li>
                    <li>Recipient: <span className="text-blue-400 font-sans">{invoice?.party?.name}</span></li>
                  </ul>
                  <p className="text-slate-400 pt-1">
                    Please log in to verify your account role and download the official PDF.
                  </p>
                </div>

                <div className="flex items-center gap-3 pt-2">
                  <button
                    onClick={() => {
                      const redirectUrl = encodeURIComponent(window.location.pathname + '?download=true');
                      router.push(`/login?redirect=${redirectUrl}`);
                    }}
                    className="flex-1 bg-primary hover:bg-primary/90 text-primary-foreground py-2.5 px-4 rounded-xl text-xs font-bold flex items-center justify-center gap-2 shadow-sm transition-all cursor-pointer"
                  >
                    <LogIn className="w-4 h-4" />
                    <span>Log In to Download</span>
                  </button>
                  <button
                    onClick={() => setAuthModalOpen(false)}
                    className="px-4 py-2.5 rounded-xl border border-slate-700 hover:bg-slate-800 text-slate-300 hover:text-white text-xs font-semibold transition-colors cursor-pointer"
                  >
                    Continue Viewing
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="flex items-center gap-3">
                  <div className="p-3 rounded-xl bg-rose-500/20 text-rose-400">
                    <ShieldAlert className="w-6 h-6" />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-white">Download Permission Restricted</h3>
                    <p className="text-xs text-slate-400">Role Verification Notice</p>
                  </div>
                </div>

                <div className="p-3.5 bg-slate-800/80 rounded-xl border border-slate-700 space-y-2 text-xs text-slate-300">
                  <p>
                    Your current account does not have permission to download this official invoice PDF.
                  </p>
                  <p className="text-slate-400">
                    {authModalReason === 'VIEWER_RESTRICTED' || downloadPermission?.user_role === 'VIEWER'
                      ? 'You are signed in with a Viewer role. Official PDF downloads are restricted to Owners, Accountants/CAs, and Employees.'
                      : authModalReason === 'UNRELATED_COMPANY'
                      ? 'Your account is not associated with either the billing company or the recipient company on this invoice.'
                      : 'Only authorized Owners, Accountants/CAs, or Employees of either company can download official tax invoice PDFs.'}
                  </p>
                  <div className="p-2.5 bg-slate-950/60 rounded-lg text-[11px] text-slate-400 space-y-1">
                    <div>Your Role: <span className="text-amber-400 font-semibold">{downloadPermission?.user_role || 'Viewer / Restricted'}</span></div>
                    <div>Permitted Roles: <span className="text-emerald-400 font-semibold">Owner, CA, Employee</span></div>
                  </div>
                </div>

                <div className="flex items-center gap-3 pt-2">
                  <button
                    onClick={() => setAuthModalOpen(false)}
                    className="w-full bg-slate-800 hover:bg-slate-700 text-white py-2.5 px-4 rounded-xl text-xs font-bold transition-all cursor-pointer"
                  >
                    Understood (Keep Viewing)
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {layoutMode === 'THERMAL' ? (
        /* ================= 80MM POS THERMAL RECEIPT LAYOUT ================= */
        <div className="w-full overflow-x-auto p-4 flex justify-center bg-slate-200 print:bg-white print:p-0">
          <div id="invoice-sheet" className="w-[80mm] max-w-[340px] bg-white p-3 font-mono text-black shadow-lg print:shadow-none mx-auto text-xs leading-tight">
            {/* Store Header */}
            <div className="text-center pb-2 border-b border-dashed border-black">
              <h1 className="text-base font-black tracking-wider uppercase">{invoice.company.name}</h1>
              <p className="text-[11px] mt-0.5">{invoice.company.address}</p>
              <p className="text-[11px]">Ph: {invoice.company.phone || 'N/A'}</p>
              <p className="text-[11px] font-bold">GSTIN: {invoice.company.gstin || 'Unregistered'}</p>
              {invoice.company.tagline && (
                <p className="text-[10px] italic mt-0.5">{invoice.company.tagline}</p>
              )}
            </div>

            {/* Bill Info */}
            <div className="py-2 border-b border-dashed border-black text-[11px]">
              <div className="flex justify-between">
                <span>Bill No: <strong className="font-bold">{invoice.voucher_number}</strong></span>
                <span>Date: {invoice.date}</span>
              </div>
              <div className="mt-1">
                <span>Cust: <strong className="font-bold">{invoice.party.name}</strong></span>
              </div>
              {invoice.party.phone && (
                <div>
                  <span>Phone: {invoice.party.phone}</span>
                </div>
              )}
              {invoice.party.gstin && (
                <div>
                  <span>GSTIN: {invoice.party.gstin}</span>
                </div>
              )}
              <div>
                <span>Place of Supply: {placeOfSupply}</span>
              </div>
            </div>

            {/* Items Header */}
            <div className="py-1 border-b border-dashed border-black font-bold text-[11px] flex justify-between">
              <span className="w-1/2">ITEM</span>
              <span className="w-1/4 text-right">QTY x RATE</span>
              <span className="w-1/4 text-right">AMT</span>
            </div>

            {/* Items List */}
            <div className="py-1 border-b border-dashed border-black divide-y divide-dotted divide-slate-300 text-[11px]">
              {invoice.items.map((item: any, idx: number) => (
                <div key={idx} className="py-1">
                  <div className="font-bold">{item.product_name}</div>
                  <div className="flex justify-between text-[10px] text-slate-700">
                    <span>HSN: {item.hsn_code || '-'} | GST: {item.gst_rate}%</span>
                    <span>
                      {Number(item.quantity).toFixed(2)} {item.unit || ''} x {Number(item.rate).toFixed(2)}
                    </span>
                    <span className="font-bold text-black text-right">
                      ₹{Number(item.taxable_amount).toFixed(2)}
                    </span>
                  </div>
                </div>
              ))}
            </div>

            {/* Subtotal & Taxes Calculation */}
            <div className="py-2 border-b border-dashed border-black text-[11px] space-y-1">
              <div className="flex justify-between">
                <span>Taxable Amount:</span>
                <span className="font-semibold">₹{totalTaxable.toFixed(2)}</span>
              </div>

              {isInterState ? (
                <div className="flex justify-between">
                  <span>Add IGST:</span>
                  <span>₹{totalIgst.toFixed(2)}</span>
                </div>
              ) : (
                <>
                  <div className="flex justify-between">
                    <span>Add CGST:</span>
                    <span>₹{totalCgst.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Add SGST:</span>
                    <span>₹{totalSgst.toFixed(2)}</span>
                  </div>
                </>
              )}

              {cartageAmount > 0 && (
                <div className="flex justify-between">
                  <span>Add Cartage:</span>
                  <span>₹{cartageAmount.toFixed(2)}</span>
                </div>
              )}

              {hasRoundOff && (
                <div className="flex justify-between">
                  <span>Round Off:</span>
                  <span>{roundOff > 0 ? `+₹${roundOff.toFixed(2)}` : `-₹${Math.abs(roundOff).toFixed(2)}`}</span>
                </div>
              )}
            </div>

            {/* Grand Total */}
            <div className="py-2 border-b-2 border-black flex justify-between items-center text-sm font-black">
              <span>NET PAYABLE:</span>
              <span className="text-base">₹{finalGrandTotal.toFixed(2)}</span>
            </div>

            {/* Totals Summary */}
            <div className="py-1 text-[10px] text-center text-slate-700">
              Total Items: {invoice.items.length} | Total Qty: {totalQty.toFixed(2)} {invoice.items[0]?.unit || 'Pcs'}
            </div>

            {/* Amount in Words */}
            <div className="py-1 text-[10px] border-b border-dashed border-black italic text-center">
              ₹ {numberToWords(Math.round(finalGrandTotal))}
            </div>

            {/* Bank Details */}
            {invoice.company?.bank_account_number && (
              <div className="py-2 border-b border-dashed border-black text-[10px] text-center">
                <div className="font-bold">BANK DETAILS FOR PAYMENT</div>
                <div>{invoice.company.bank_name || ''}</div>
                <div>A/C: {invoice.company.bank_account_number}</div>
                <div>IFSC: {invoice.company.bank_ifsc || ''}</div>
              </div>
            )}

            {/* QR Code */}
            <div className="py-2 flex flex-col items-center justify-center border-b border-dashed border-black">
              {typeof window !== 'undefined' && (
                <QRCode value={window.location.href} size={75} />
              )}
              <span className="text-[9px] mt-1 text-slate-600">Scan to Verify Invoice</span>
            </div>

            {/* Receipt Footer */}
            <div className="pt-2 text-center text-[10px] space-y-0.5">
              <p className="font-bold tracking-widest uppercase">*** THANK YOU ***</p>
              <p>Goods once sold will not be returned.</p>
              <p className="text-[9px] text-slate-500 mt-1">Software by Vouch ERP</p>
            </div>
          </div>
        </div>
      ) : (
        /* ================= A4 STANDARD TAX INVOICE LAYOUT ================= */
        <div className="w-full overflow-x-auto p-4 sm:p-8 flex justify-center bg-slate-200 print:bg-white print:p-0">
          <div id="invoice-sheet" className="w-[210mm] min-w-[210mm] max-w-[210mm] shrink-0 min-h-[297mm] print:min-h-[95vh] bg-white text-black p-6 sm:p-8 shadow-[0_0_15px_rgba(0,0,0,0.15)] print:shadow-none print:p-6 print:pt-10 flex flex-col mx-auto">
          
          {/* Main Border Box */}
          <div className="border-2 border-black flex-1 flex flex-col justify-between">
              
              {/* Top Section */}
              <div className="flex-1 flex flex-col">
                {/* Header */}
                <div className="text-center p-3 border-b-2 border-black">
                    <div className="flex justify-between items-start text-xs font-bold mb-2">
                        <div>GSTIN : {invoice.company.gstin || 'Unregistered'}</div>
                        <div className="italic">Original For Recipient</div>
                    </div>
                    <h2 className="text-lg font-bold underline mb-1 tracking-wider">TAX INVOICE</h2>
                    <h1 className="text-3xl font-extrabold mb-1">{invoice.company.name}</h1>
                    <p className="text-sm">{invoice.company.address}</p>
                    <p className="text-sm">Ph: {invoice.company.phone || 'N/A'} | Email: {invoice.company.email || 'N/A'}</p>
                    {invoice.company.tagline && (
                      <p className="text-sm font-bold mt-1 tracking-widest uppercase">{invoice.company.tagline}</p>
                    )}
                </div>

                {/* Meta Grid */}
                <div className="grid grid-cols-2 border-b-2 border-black text-sm">
                    <div className="p-2 border-r-2 border-black">
                        <table className="w-full">
                            <tbody>
                                <tr><td className="w-32">Invoice No.</td><td className="font-bold">: {invoice.voucher_number}</td></tr>
                                <tr><td>Dated</td><td className="font-bold">: {invoice.date}</td></tr>
                                <tr><td>Place of Supply</td><td>: {placeOfSupply}</td></tr>
                                <tr><td>Reverse Charge</td><td>: N</td></tr>
                            </tbody>
                        </table>
                    </div>
                    <div className="p-2">
                        <table className="w-full">
                            <tbody>
                                <tr>
                                  <td className="w-32">GR/RR No.</td>
                                  <td>: {ewayBill?.trans_doc_no || 'N/A'}</td>
                                </tr>
                                <tr>
                                  <td>Transport</td>
                                  <td>: {ewayBill?.transporter_name || ewayBill?.trans_mode_display || 'Road'}</td>
                                </tr>
                                <tr>
                                  <td>Vehicle No.</td>
                                  <td className="font-bold">: {ewayBill?.vehicle_no || 'N/A'}</td>
                                </tr>
                                <tr>
                                  <td>E-Way Bill No.</td>
                                  <td className="font-bold">: {ewayBill?.eway_bill_number ? `${ewayBill.eway_bill_number} (Exp: ${new Date(ewayBill.valid_upto).toLocaleDateString('en-IN')})` : 'N/A'}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                {/* Party Grid */}
                <div className="grid grid-cols-2 border-b-2 border-black text-sm min-h-32">
                    <div className="p-2 border-r-2 border-black flex flex-col">
                        <span className="italic mb-1">Billed to :</span>
                        <strong className="text-base">{invoice.party.name}</strong>
                        <span className="whitespace-pre-wrap">{invoice.party.address}</span>
                        <div className="mt-auto pt-2">
                            GSTIN / UIN <span className="ml-4 font-bold">: {invoice.party.gstin || 'Unregistered'}</span>
                        </div>
                    </div>
                    <div className="p-2 flex flex-col">
                        <span className="italic mb-1">Shipped to :</span>
                        <strong className="text-base">{invoice.party.name}</strong>
                        <span className="whitespace-pre-wrap">{invoice.party.address}</span>
                        <div className="mt-auto pt-2">
                            GSTIN / UIN <span className="ml-4 font-bold">: {invoice.party.gstin || 'Unregistered'}</span>
                        </div>
                    </div>
                </div>

                {/* Items Table */}
                <div className="flex-1 flex flex-col">
                    <table className="w-full h-full text-sm border-collapse">
                        <thead>
                            <tr className="border-b-2 border-black text-center min-h-9">
                                <th className="w-12 border-r border-black py-1.5 px-1">S.N.</th>
                                <th className="border-r border-black text-left py-1.5 pl-2">Description of Goods</th>
                                <th className="w-20 border-r border-black py-1.5 px-1 whitespace-nowrap">HSN</th>
                                <th className="w-16 border-r border-black py-1.5 px-1 whitespace-nowrap">Qty.</th>
                                <th className="w-12 border-r border-black py-1.5 px-1 whitespace-nowrap">Unit</th>
                                <th className="w-20 border-r border-black py-1.5 px-1 whitespace-nowrap">Price</th>
                                <th className="w-20 border-r border-black py-1.5 px-1 whitespace-nowrap">Disc%</th>
                                <th className="w-28 text-right py-1.5 pr-2 whitespace-nowrap">Amount(Rs.)</th>
                            </tr>
                        </thead>
                        <tbody>
                            {invoice.items.map((item: any, idx: number) => (
                                <tr key={idx} className="align-top">
                                    <td className="border-r border-black text-center py-2 px-1">{idx + 1}</td>
                                    <td className="border-r border-black text-left py-2 pl-2 font-medium">{item.product_name}</td>
                                    <td className="border-r border-black text-center py-2 px-1 whitespace-nowrap">{item.hsn_code}</td>
                                    <td className="border-r border-black text-right py-2 pr-1 whitespace-nowrap">{Number(item.quantity).toFixed(2)}</td>
                                    <td className="border-r border-black text-center py-2 px-1 whitespace-nowrap">{item.unit}</td>
                                    <td className="border-r border-black text-right py-2 pr-1 whitespace-nowrap">{Number(item.rate).toFixed(2)}</td>
                                    <td className="border-r border-black text-center py-2 px-1 whitespace-nowrap">{Number(item.discount_percent).toFixed(2)}%</td>
                                    <td className="text-right py-2 pr-2 font-medium whitespace-nowrap">{Number(item.taxable_amount).toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
                                </tr>
                            ))}
                            {/* Filler Row */}
                            <tr className="border-b border-black">
                                <td className="border-r border-black h-full min-h-[60px]"></td>
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

                {/* Subtotals & Taxes */}
                <div className="flex text-xs">
                    {/* Left side: Taxes labels */}
                    <div className="flex-1 flex flex-col justify-end py-1">
                        <div className="h-5"></div>
                        
                        {isInterState ? (
                            <div className="h-5 flex items-center justify-end pr-12 text-[11px] italic">
                                <div className="flex justify-between items-center w-48">
                                    <span>Add : IGST</span>
                                    <span>@ {invoice.items.length > 0 ? Number(invoice.items[0].gst_rate).toFixed(2) : '18.00'} %</span>
                                </div>
                            </div>
                        ) : (
                            <>
                                <div className="h-5 flex items-center justify-end pr-12 text-[11px] italic">
                                    <div className="flex justify-between items-center w-48">
                                        <span>Add : CGST</span>
                                        <span>@ {invoice.items.length > 0 ? (Number(invoice.items[0].gst_rate)/2).toFixed(2) : '9.00'} %</span>
                                    </div>
                                </div>
                                <div className="h-5 flex items-center justify-end pr-12 text-[11px] italic">
                                    <div className="flex justify-between items-center w-48">
                                        <span>Add : SGST</span>
                                        <span>@ {invoice.items.length > 0 ? (Number(invoice.items[0].gst_rate)/2).toFixed(2) : '9.00'} %</span>
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
                        <span className="border-b border-black px-4 pb-0.5">{totalQty.toFixed(2)} {invoice.items[0]?.unit || 'Pcs'}</span>
                    </div>
                    <div className="w-28 border-l border-b border-black h-full flex items-center justify-end pr-2">
                        {finalGrandTotal.toLocaleString('en-IN', {minimumFractionDigits: 2})}
                    </div>
                </div>

                {/* Tax Details Table */}
                <div className="border-b border-black px-2 py-1 text-[10px]">
                    <table className="border-collapse">
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
                            {Array.from(new Set(invoice.items.map((i:any)=>Number(i.gst_rate)))).map((rate: any) => {
                                const items = invoice.items.filter((i:any)=>Number(i.gst_rate) === rate);
                                const tAmt = items.reduce((s:number,i:any)=>s+Number(i.taxable_amount),0);
                                const tax = items.reduce((s:number,i:any)=>s+(Number(i.total_amount)-Number(i.taxable_amount)),0);
                                return (
                                    <tr key={rate}>
                                        <td className="pt-0.5 pr-6">{rate}%</td>
                                        <td className="text-right pt-0.5 pr-6">{tAmt.toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
                                        {!isInterState && <td className="text-right pt-0.5 pr-6">{(tax/2).toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>}
                                        {!isInterState && <td className="text-right pt-0.5 pr-6">{(tax/2).toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>}
                                        {isInterState && <td className="text-right pt-0.5 pr-6">{tax.toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>}
                                        <td className="text-right pt-0.5">{tax.toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
                                    </tr>
                                )
                            })}
                        </tbody>
                    </table>
                </div>

                {/* Amount in Words */}
                <div className="p-2 border-b border-black text-[12px]">
                    <span className="font-semibold">Total Amount in Words : </span>
                    <span className="font-bold">₹ {numberToWords(Math.round(finalGrandTotal))}</span>
                </div>

                {/* Bank Details */}
                <div className="p-2 border-b-2 border-black text-center text-xs font-medium">
                    <span className="font-bold underline text-[13px]">BANK DETAILS</span><br/>
                    {invoice.company.bank_name || ''} {invoice.company.bank_branch || ''}, ACCOUNT NO- {invoice.company.bank_account_number || ''}, IFSCODE: {invoice.company.bank_ifsc || ''}
                </div>
              </div>

              {/* Bottom Footer Section */}
              <div className="flex h-44 text-xs shrink-0">
                  {/* Column 1: Terms */}
                  <div className="w-[45%] p-2 border-r-2 border-black flex flex-col justify-between">
                      <div>
                        <span className="font-bold mb-1 text-[11px] block">Terms & Conditions</span>
                        <span className="font-bold block mb-1">E.& O.E.</span>
                        <span className="block">1. Goods once sold will not be taken back.</span>
                        <span className="block">2. Interest @ 18% p.a. will be charged if the payment is not made within 45 days.</span>
                        <span className="block">3. Subject to '{invoice.company.city || 'Kanpur'}' Jurisdiction only.</span>
                      </div>
                  </div>
                  
                  {/* Column 2: QR Code */}
                  <div className="w-[20%] p-2 border-r-2 border-black flex flex-col items-center justify-between">
                      <span className="font-bold text-[10px] mb-2">E-Invoice QR Code</span>
                      {typeof window !== 'undefined' && (
                          <QRCode value={window.location.href} size={100} className="mx-auto my-auto" />
                      )}
                      <div className="h-2"></div>
                  </div>
                  
                  {/* Column 3: Signatures */}
                  <div className="w-[35%] flex flex-col">
                      <div className="h-12 p-2 border-b-2 border-black flex items-start">
                          <span className="text-[11px] font-bold">Receiver's Signature :</span>
                      </div>
                      <div className="flex-1 p-2 relative flex flex-col justify-between items-end">
                          <div className="font-bold text-sm text-right mt-1">for {invoice.company.name}</div>
                          
                          <div className="flex justify-end w-full my-auto">
                              {invoice.company?.proprietor_signature && (
                                  <img 
                                      crossOrigin="anonymous"
                                      src={getSignatureUrl(invoice.company.proprietor_signature)} 
                                      alt="Signature" 
                                      className="h-14 object-contain" 
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
        </div>
        </div>
      )}

      {invoice && (
        <AuditHistoryModal
          voucherId={invoiceId}
          voucherNumber={invoice?.voucher_number || ""}
          isOpen={isAuditModalOpen}
          onClose={() => setIsAuditModalOpen(false)}
        />
      )}
    </div>
  );
}
