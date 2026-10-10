"use client";
import { API_BASE_URL, api } from '@/utils/api';
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
  ShieldCheck,
  Sparkles,
  LogIn,
  History,
  Tag,
  Maximize2,
  Truck
} from 'lucide-react';
import AuditHistoryModal from '@/components/modals/AuditHistoryModal';

export type InvoiceCopyMode = 
  | 'ORIGINAL'
  | 'TRANSPORTER'
  | 'SUPPLIER'
  | 'BUNDLE_LOCAL'
  | 'BUNDLE_TRANSPORT';

interface SheetConfig {
  copyType: 'ORIGINAL' | 'TRANSPORTER' | 'SUPPLIER';
  badgeTitle: string;
  signatoryTitle: string;
  pageNumber: number;
  totalPages: number;
  highlightTransport?: boolean;
  pageItems: any[];
  itemStartIndex: number;
  isFirstPage: boolean;
  isLastPage: boolean;
  broughtForwardSubtotal: number;
  carriedOverSubtotal: number;
}

interface PageChunk {
  pageNumber: number;
  items: any[];
  itemStartIndex: number;
  isFirstPage: boolean;
  isLastPage: boolean;
  broughtForwardSubtotal: number;
  carriedOverSubtotal: number;
}

function chunkInvoiceItems(items: any[]): PageChunk[] {
  if (!items || items.length === 0) {
    return [{
      pageNumber: 1,
      items: [],
      itemStartIndex: 0,
      isFirstPage: true,
      isLastPage: true,
      broughtForwardSubtotal: 0,
      carriedOverSubtotal: 0,
    }];
  }

  // Single page threshold: up to 8 items fit comfortably on 1 page with full header & full footer
  if (items.length <= 8) {
    return [{
      pageNumber: 1,
      items: items,
      itemStartIndex: 0,
      isFirstPage: true,
      isLastPage: true,
      broughtForwardSubtotal: 0,
      carriedOverSubtotal: 0,
    }];
  }

  // Multi-page splitting:
  // Page 1 has full header, so it takes up to 8 items (or balanced for 2 pages).
  // Last page has full statutory footer, so it takes up to 9-10 items.
  // Intermediate pages have compact header and continuation banner, so up to 14 items.
  const chunks: any[][] = [];
  let remaining = [...items];

  // For 2-page split (items <= 18):
  if (items.length <= 18) {
    const p1Count = Math.min(8, Math.max(5, Math.ceil(items.length / 2)));
    chunks.push(remaining.slice(0, p1Count));
    chunks.push(remaining.slice(p1Count));
  } else {
    // 3 or more pages:
    chunks.push(remaining.slice(0, 8));
    remaining = remaining.slice(8);

    while (remaining.length > 10) {
      const take = Math.min(14, remaining.length - 8);
      chunks.push(remaining.slice(0, take));
      remaining = remaining.slice(take);
    }
    if (remaining.length > 0) {
      chunks.push(remaining);
    }
  }

  const totalPages = chunks.length;
  let runningSubtotal = 0;
  let runningItemIndex = 0;

  return chunks.map((chunkItems, idx) => {
    const pageNumber = idx + 1;
    const isFirst = pageNumber === 1;
    const isLast = pageNumber === totalPages;
    const broughtForward = runningSubtotal;

    const chunkTaxableSum = chunkItems.reduce((acc, it) => acc + Number(it.taxable_amount || 0), 0);
    runningSubtotal += chunkTaxableSum;
    const carriedOver = isLast ? 0 : runningSubtotal;
    const startIndex = runningItemIndex;
    runningItemIndex += chunkItems.length;

    return {
      pageNumber,
      items: chunkItems,
      itemStartIndex: startIndex,
      isFirstPage: isFirst,
      isLastPage: isLast,
      broughtForwardSubtotal: broughtForward,
      carriedOverSubtotal: carriedOver,
    };
  });
}

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
  const [copyMode, setCopyMode] = useState<InvoiceCopyMode>('ORIGINAL');
  const [isGeneratingPdf, setIsGeneratingPdf] = useState<boolean>(false);
  const [isWhatsAppModalOpen, setIsWhatsAppModalOpen] = useState<boolean>(false);
  const [copiedToClipboard, setCopiedToClipboard] = useState<boolean>(false);
  const [shareStatusMessage, setShareStatusMessage] = useState<string | null>(null);
  const [shareToken, setShareToken] = useState<string>('');
  const [isAuth, setIsAuth] = useState<boolean>(false);
  const [copiedLink, setCopiedLink] = useState<boolean>(false);
  const [copiedMessage, setCopiedMessage] = useState<boolean>(false);
  const [preferredWhatsAppClient, setPreferredWhatsAppClient] = useState<'web' | 'app'>('web');
  const [isAuditModalOpen, setIsAuditModalOpen] = useState<boolean>(false);
  const [showBrand, setShowBrand] = useState<boolean>(() => {
    if (typeof window !== 'undefined') {
      const val = localStorage.getItem('vouch_show_brand_in_sales_invoice');
      return val !== null ? val === 'true' : true;
    }
    return true;
  });

  const toggleShowBrand = () => {
    const next = !showBrand;
    setShowBrand(next);
    if (typeof window !== 'undefined') {
      localStorage.setItem('vouch_show_brand_in_sales_invoice', String(next));
    }
  };

  // Fit to page mode (stretch invoice height to fill A4 page with zero leftover bottom space)
  const [fitToPage, setFitToPage] = useState<boolean>(() => {
    if (typeof window !== 'undefined') {
      const val = localStorage.getItem('vouch_print_fit_to_page');
      return val !== null ? val === 'true' : true;
    }
    return true;
  });

  const toggleFitToPage = () => {
    const next = !fitToPage;
    setFitToPage(next);
    if (typeof window !== 'undefined') {
      localStorage.setItem('vouch_print_fit_to_page', String(next));
    }
  };

  // Mobile responsiveness and dynamic scaling
  const [scaleMode, setScaleMode] = useState<'fit' | '100'>('fit');
  const [viewportWidth, setViewportWidth] = useState<number>(typeof window !== 'undefined' ? window.innerWidth : 794);
  const [sheetHeight, setSheetHeight] = useState<number>(1123);
  const sheetRef = React.useRef<HTMLDivElement>(null);

  // Dynamic QR Code & Recipient Status
  const [qrMode, setQrMode] = useState<'SMART' | 'UPI' | 'E-INVOICE'>('SMART');
  const [recipientStatus, setRecipientStatus] = useState<any>(null);

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
      const urlParams = new URLSearchParams(window.location.search);
      const incomingCopy = urlParams.get('copy')?.toUpperCase();
      if (incomingCopy && ['ORIGINAL', 'TRANSPORTER', 'SUPPLIER', 'BUNDLE_LOCAL', 'BUNDLE_TRANSPORT'].includes(incomingCopy)) {
        setCopyMode(incomingCopy as InvoiceCopyMode);
      }
    }
    fetchInvoice();
  }, [invoiceId]);

  useEffect(() => {
    const handleResize = () => {
      setViewportWidth(window.innerWidth);
      if (sheetRef.current) {
        setSheetHeight(sheetRef.current.offsetHeight);
      }
    };
    window.addEventListener('resize', handleResize);
    handleResize();

    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => {
      if (sheetRef.current) {
        setSheetHeight(sheetRef.current.offsetHeight);
      }
    }) : null;

    if (ro && sheetRef.current) {
      ro.observe(sheetRef.current);
    }

    return () => {
      window.removeEventListener('resize', handleResize);
      ro?.disconnect();
    };
  }, [invoice, layoutMode]);

  // Recipient check for logged-in users
  useEffect(() => {
    if (invoiceId && isAuth && !String(invoiceId).startsWith('offline_')) {
      const checkRecipient = async () => {
        try {
          const tokenStr = getAccessToken();
          const activeCompId = typeof window !== 'undefined' ? localStorage.getItem('vouch_active_company_id') || '' : '';
          const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/vouchers/${invoiceId}/recipient-status/`, {
            headers: {
              Authorization: `Bearer ${tokenStr}`,
              'X-Company-ID': activeCompId
            }
          });
          setRecipientStatus(res.data);
        } catch (e) {
          // Non-blocking
        }
      };
      checkRecipient();
    }
  }, [invoiceId, isAuth]);

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
                brand: it.brand || '',
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
        // Public viewing for recipients with a valid share or claim token (e.g. via QR scan or share link)
        const urlParams = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
        const incomingToken = urlParams?.get('token') || urlParams?.get('share_token') || urlParams?.get('claim_token') || '';
        if (incomingToken) {
          setShareToken(incomingToken);
        }
        const publicUrl = incomingToken
          ? `${API_BASE_URL}/api/v1/accounting/vouchers/public/${invoiceId}/?token=${encodeURIComponent(incomingToken)}`
          : `${API_BASE_URL}/api/v1/accounting/vouchers/public/${invoiceId}/`;
        res = await axios.get(publicUrl);
      }

      if (res?.data?.data) {
        const invData = res.data.data;
        setInvoice(invData);

        if (token) {
          try {
            const shareRes = await api.post(`/api/v1/documents/vouchers/${invoiceId}/share/`, { expires_in_days: 30 });
            if (shareRes.data?.raw_token) {
              setShareToken(shareRes.data.raw_token);
            }
          } catch (e) {
            // Optional share prefetch
          }
        }

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

  const hasTransportDetails = Boolean(
    (ewayBill && (ewayBill.vehicle_no || ewayBill.transporter_name || ewayBill.trans_doc_no || ewayBill.eway_bill_number)) ||
    invoice?.transport_name || 
    invoice?.vehicle_number || 
    invoice?.gr_rr_no
  );

  const getSheetsToRender = (): SheetConfig[] => {
    const rawItems = invoice?.items || [];
    const itemChunks = chunkInvoiceItems(rawItems);
    const pagesPerCopy = itemChunks.length;

    const buildSheetsForCopy = (
      copyType: 'ORIGINAL' | 'TRANSPORTER' | 'SUPPLIER',
      badgeTitle: string,
      signatoryTitle: string,
      highlightTransport?: boolean
    ): SheetConfig[] => {
      return itemChunks.map((chunk) => ({
        copyType,
        badgeTitle,
        signatoryTitle,
        pageNumber: chunk.pageNumber,
        totalPages: pagesPerCopy,
        highlightTransport,
        pageItems: chunk.items,
        itemStartIndex: chunk.itemStartIndex,
        isFirstPage: chunk.isFirstPage,
        isLastPage: chunk.isLastPage,
        broughtForwardSubtotal: chunk.broughtForwardSubtotal,
        carriedOverSubtotal: chunk.carriedOverSubtotal,
      }));
    };

    if (copyMode === 'ORIGINAL') {
      return buildSheetsForCopy('ORIGINAL', 'Original For Recipient', "Receiver's Signature :");
    }
    if (copyMode === 'TRANSPORTER') {
      return buildSheetsForCopy('TRANSPORTER', 'Duplicate For Transporter', "Transporter / Driver Signature :", true);
    }
    if (copyMode === 'SUPPLIER') {
      return buildSheetsForCopy(
        'SUPPLIER',
        hasTransportDetails ? 'Triplicate For Supplier' : 'Duplicate For Supplier',
        "Customer's Acknowledgment :"
      );
    }
    if (copyMode === 'BUNDLE_LOCAL') {
      return [
        ...buildSheetsForCopy('ORIGINAL', 'Original For Recipient', "Receiver's Signature :"),
        ...buildSheetsForCopy('SUPPLIER', 'Duplicate For Supplier', "Customer's Acknowledgment :"),
      ];
    }
    if (copyMode === 'BUNDLE_TRANSPORT') {
      return [
        ...buildSheetsForCopy('ORIGINAL', 'Original For Recipient', "Receiver's Signature :"),
        ...buildSheetsForCopy('TRANSPORTER', 'Duplicate For Transporter', "Transporter / Driver Signature :", true),
        ...buildSheetsForCopy('SUPPLIER', 'Triplicate For Supplier', "Customer's Acknowledgment :"),
      ];
    }
    return buildSheetsForCopy('ORIGINAL', 'Original For Recipient', "Receiver's Signature :");
  };
  
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

  const getQrData = () => {
    // 1. Official GST E-Invoice IRN QR
    if (invoice?.signed_qr_code && (qrMode === 'E-INVOICE' || (!invoice?.company?.upi_id && qrMode === 'SMART'))) {
      return {
        value: invoice.signed_qr_code,
        label: 'GST E-Invoice QR Code',
        sublabel: 'Official GSTN Verification'
      };
    }

    // 2. Direct NPCI UPI QR (for counter POS / direct payment apps)
    if (qrMode === 'UPI' && invoice?.company?.upi_id) {
      const vpa = invoice.company.upi_id.trim();
      const payeeName = (invoice.company.name || 'Merchant').replace(/[^\w\s]/g, '').trim();
      const amount = finalGrandTotal > 0 ? finalGrandTotal.toFixed(2) : '';
      const invoiceNo = (invoice.voucher_number || '').trim();
      const upiUrl = `upi://pay?pa=${encodeURIComponent(vpa)}&pn=${encodeURIComponent(payeeName)}&am=${amount}&cu=INR&tn=${encodeURIComponent('Invoice ' + invoiceNo)}`;
      return {
        value: upiUrl,
        label: 'Scan & Pay via UPI',
        sublabel: 'GPay • PhonePe • Paytm • BHIM'
      };
    }

    // 3. Dynamic Smart Vouch Link (Default: Public View + Instant UPI + B2B Auto-Book)
    const origin = typeof window !== 'undefined' ? window.location.origin : 'https://vouchapp.in';
    const smartUrl = shareToken ? `${origin}/claim?token=${encodeURIComponent(shareToken)}` : `${origin}/sales/${invoiceId}/print`;
    return {
      value: smartUrl,
      label: 'Scan to View, Pay & Add to Books',
      sublabel: 'Public View • UPI Pay • Auto-Book'
    };
  };

  const getSignatureUrl = (sig: string | null | undefined) => {
    if (!sig) return '';
    if (sig.startsWith('data:') || sig.startsWith('http://') || sig.startsWith('https://')) {
      return sig;
    }
    return `${API_BASE_URL}${sig.startsWith('/') ? '' : '/'}${sig}`;
  };

  const getCleanInvoiceFilename = (mode: InvoiceCopyMode = copyMode) => {
    const rawInvoiceNo = invoice?.voucher_number || 'INVOICE';
    const cleanNo = rawInvoiceNo.replace(/[/\\:*?"<>|]/g, '-').trim();
    let suffix = '';
    if (mode === 'TRANSPORTER') suffix = '_Transporter_Copy';
    else if (mode === 'SUPPLIER') suffix = '_Office_Copy';
    else if (mode === 'BUNDLE_LOCAL') suffix = '_Local_2Copies';
    else if (mode === 'BUNDLE_TRANSPORT') suffix = '_Triplicate_3Copies';
    else suffix = '_Original';
    return `${cleanNo}${suffix}.pdf`;
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
    const ua = navigator.userAgent || '';
    const isMobileUA = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile/i.test(ua);
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches || (window.navigator as any).standalone === true;
    const isTouch = navigator.maxTouchPoints > 0 || 'ontouchstart' in window;
    return isMobileUA || isStandalone || isTouch;
  };

  const generateInvoicePdf = async (): Promise<{ file: File; blobUrl: string } | null> => {
    const isThermal = layoutMode === 'THERMAL';
    const targetWidthPx = isThermal ? 302 : 794;

    const sheetElements = isThermal
      ? ([document.getElementById('invoice-sheet')].filter(Boolean) as HTMLElement[])
      : (Array.from(document.querySelectorAll('.invoice-print-sheet')) as HTMLElement[]);

    if (sheetElements.length === 0) {
      const fallback = document.getElementById('invoice-sheet');
      if (fallback) sheetElements.push(fallback);
    }
    if (sheetElements.length === 0) return null;

    let pdf: jsPDF;
    if (isThermal) {
      pdf = new jsPDF({
        orientation: 'portrait',
        unit: 'mm',
        format: [80, 297],
      });
    } else {
      pdf = new jsPDF({
        orientation: 'portrait',
        unit: 'mm',
        format: 'a4',
      });
    }

    const a4Width = 210;
    const a4Height = 297;

    for (let sheetIdx = 0; sheetIdx < sheetElements.length; sheetIdx++) {
      const element = sheetElements[sheetIdx];

      // Create an isolated off-screen sandbox container with forced LIGHT theme.
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
        clone.style.minHeight = '270mm';
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

      // Copy canvas image of first sheet to clipboard for instant Ctrl+V pasting in WhatsApp Web or Desktop App
      if (sheetIdx === 0) {
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
      }

      const imgData = canvas.toDataURL('image/png');

      if (sheetIdx > 0) {
        pdf.addPage(isThermal ? [80, Math.max(100, (canvas.height * 80) / canvas.width)] : 'a4', 'portrait');
      }

      if (isThermal) {
        const pdfWidth = 80;
        const imgHeight = (canvas.height * pdfWidth) / canvas.width;
        pdf.addImage(imgData, 'PNG', 0, 0, pdfWidth, imgHeight);
      } else {
        const imgHeight = (canvas.height * a4Width) / canvas.width;
        if (imgHeight <= a4Height * 1.15) {
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
      }
    }

    const filename = getCleanInvoiceFilename(copyMode);
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
    const partyName = invoice.party?.name || invoice.buyer_name || 'Valued Customer';
    const total = Number(invoice.total_amount || 0).toLocaleString('en-IN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    
    const origin = typeof window !== 'undefined' ? window.location.origin : 'https://vouch-pi-one.vercel.app';
    const copyQuery = copyMode !== 'ORIGINAL' ? `?copy=${copyMode}` : '';
    const publicInvoiceUrl = `${origin}/sales/${invoiceId}/print${copyQuery}`;
    const claimUrl = shareToken ? `${origin}/claim?token=${encodeURIComponent(shareToken)}` : publicInvoiceUrl;
    const invDate = invoice.date || invoice.voucher_date || 'Today';

    const copyLabel = 
      copyMode === 'TRANSPORTER' ? ' (Duplicate for Transporter)' :
      copyMode === 'SUPPLIER' ? ' (Supplier / Office Copy)' :
      copyMode === 'BUNDLE_LOCAL' ? ' (Original + Office Copies)' :
      copyMode === 'BUNDLE_TRANSPORT' ? ' (Triplicate Set: Recipient + Transporter + Supplier)' :
      ' (Original for Recipient)';

    const transportInfo = (copyMode === 'TRANSPORTER' && (ewayBill?.vehicle_no || invoice?.vehicle_number || ewayBill?.transporter_name || invoice?.transport_name))
      ? `• *Transport:* ${ewayBill?.transporter_name || invoice?.transport_name || 'Direct / Road'}\n• *Vehicle:* ${ewayBill?.vehicle_no || invoice?.vehicle_number || 'N/A'}\n`
      : '';

    return (
      `🧾 *TAX INVOICE #${invoiceNo}*${copyLabel ? ` - *${copyLabel}*` : ''}\n\n` +
      `Dear *${partyName}*,\n\n` +
      `Here is your tax invoice from *${companyName}*:\n` +
      `• *Invoice Number:* ${invoiceNo}\n` +
      `• *Invoice Date:* ${invDate}\n` +
      `• *Invoice Amount:* ₹${total}\n` +
      transportInfo +
      `\n` +
      `📄 *View & Download Official PDF:*\n` +
      `${publicInvoiceUrl}\n\n` +
      `⚡ *1-Click Import (Auto-Book Purchase in Vouch):*\n` +
      `${claimUrl}\n\n` +
      `Thank you for doing business with us!\n` +
      `*${companyName}*`
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
      const filename = getCleanInvoiceFilename(copyMode);
      const isMobile = isMobileOrPWA();
      if (!isMobile && pdfResult) {
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
      const filename = getCleanInvoiceFilename(copyMode);
      const phone = getCleanPhone();
      const isMobile = isMobileOrPWA();

      // Create official secure share token and message
      let waMessage = buildWhatsAppTextMessage();

      try {
        const shareRes = await api.post(`/api/v1/documents/vouchers/${invoiceId}/share/`, { expires_in_days: 30 });
        if (shareRes.data?.raw_token) {
          setShareToken(shareRes.data.raw_token);
        }
        if (shareRes.data?.whatsapp_message) {
          waMessage = shareRes.data.whatsapp_message;
        }
      } catch (shareErr) {
        console.warn('Could not generate document share token, using fallback URL:', shareErr);
      }

      // Fetch official high-definition deterministic PDF
      let pdfFile: File | null = null;
      let pdfBlobUrl: string | null = null;

      try {
        const pdfResp = await api.get(`/api/v1/documents/vouchers/${invoiceId}/pdf/?fresh=1&copy=${copyMode}&t=${Date.now()}`, { responseType: 'blob' });
        pdfFile = new File([pdfResp.data], filename, { type: 'application/pdf' });
        pdfBlobUrl = window.URL.createObjectURL(pdfResp.data);
      } catch (pdfErr) {
        const fallbackResult = await generateInvoicePdf();
        if (fallbackResult) {
          pdfFile = fallbackResult.file;
          pdfBlobUrl = fallbackResult.blobUrl;
        }
      }

      // ================= 1. MOBILE / PWA MODE =================
      if (isMobile) {
        // Copy message to clipboard so user can also paste anywhere
        if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
          try {
            await navigator.clipboard.writeText(waMessage);
          } catch (clipErr) {}
        }

        // Directly launch WhatsApp with complete pre-filled message
        // containing document details, PDF link, and 1-Click Import link
        const encoded = encodeURIComponent(waMessage);
        const appUrl = phone ? `whatsapp://send?phone=${phone}&text=${encoded}` : `whatsapp://send?text=${encoded}`;
        const fallbackUrl = phone ? `https://api.whatsapp.com/send?phone=${phone}&text=${encoded}` : `https://api.whatsapp.com/send?text=${encoded}`;

        try {
          window.location.href = appUrl;
        } catch (e) {
          window.open(fallbackUrl, '_blank');
        }
        return;
      }

      // ================= 2. LAPTOP / DESKTOP MODE =================
      if (pdfBlobUrl) {
        triggerPdfDownload(pdfBlobUrl, filename);
      }

      const encoded = encodeURIComponent(waMessage);
      const webUrl = phone ? `https://web.whatsapp.com/send?phone=${phone}&text=${encoded}` : `https://web.whatsapp.com/send?text=${encoded}`;
      const appUrl = phone ? `whatsapp://send?phone=${phone}&text=${encoded}` : `whatsapp://send?text=${encoded}`;

      if (preferredWhatsAppClient === 'web') {
        window.open(webUrl, '_blank');
        setShareStatusMessage(`WhatsApp Web opened! Official Invoice PDF (${filename}) downloaded.`);
        setTimeout(() => setShareStatusMessage(null), 8000);
      } else {
        setShareStatusMessage(`Opening WhatsApp with invoice details & PDF link...`);
        setTimeout(() => setShareStatusMessage(null), 8000);
        try {
          window.location.href = appUrl;
        } catch (e) {}
        setTimeout(() => {
          if (document.hasFocus()) {
            window.open(webUrl, '_blank');
          }
        }, 1500);
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
      const filename = getCleanInvoiceFilename(copyMode);
      // 1. Download official high-definition deterministic vector PDF from backend
      try {
        const response = await api.get(`/api/v1/documents/vouchers/${invoiceId}/pdf/?download=1&fresh=1&copy=${copyMode}&t=${Date.now()}`, {
          responseType: 'blob',
        });
        const blobUrl = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
        triggerPdfDownload(blobUrl, filename);
        return;
      } catch (backendErr) {
        console.warn('Backend PDF stream failed, falling back to client-side renderer:', backendErr);
      }

      // 2. Offline fallback
      const pdfResult = await generateInvoicePdf();
      if (!pdfResult) return;
      triggerPdfDownload(pdfResult.blobUrl, filename);
    } catch (err: any) {
      console.error('PDF download failed:', err);
    } finally {
      setIsGeneratingPdf(false);
    }
  };

  const filename = invoice ? getCleanInvoiceFilename(copyMode) : 'INVOICE.pdf';

  const isMobile = viewportWidth < 794;
  const padding = viewportWidth < 640 ? 16 : 32;
  const scale = isMobile ? Math.min(1, Math.max(0.35, (viewportWidth - padding) / 794)) : 1;
  const activeScale = scaleMode === 'fit' && isMobile ? scale : 1;

  const renderA4Sheet = (sheet: SheetConfig, sheetIndex: number, totalSheets: number) => {
    return (
      <div 
        key={`${sheet.copyType}-p${sheet.pageNumber}-${sheetIndex}`}
        id={sheetIndex === 0 ? "invoice-sheet" : undefined}
        ref={sheetIndex === 0 ? sheetRef : undefined}
        style={
          activeScale < 1
            ? {
                transform: `scale(${activeScale})`,
                transformOrigin: '0 0',
                width: '794px',
                minWidth: '794px',
                maxWidth: '794px',
                position: 'absolute',
                top: 0,
                left: 0,
              }
            : undefined
        }
        className="invoice-print-sheet w-[210mm] max-w-[210mm] shrink-0 min-h-[270mm] print:min-h-[270mm] print:w-full print:max-w-none print:m-0 print:p-0 bg-white text-black p-6 sm:p-8 shadow-[0_0_15px_rgba(0,0,0,0.15)] print:shadow-none flex flex-col mx-auto print:static print:transform-none"
      >
        {/* Main Border Box */}
        <div className="border-2 border-black flex-1 flex flex-col justify-between">
            {/* Top Section */}
            <div className="flex-1 flex flex-col">
              {sheet.isFirstPage ? (
                <>
                  {/* Header */}
                  <div className="text-center p-3 border-b-2 border-black">
                  <div className="flex justify-between items-start text-xs font-bold mb-2">
                      <div>GSTIN : {invoice.company.gstin || 'Unregistered'}</div>
                      <div className={`italic ${sheet.highlightTransport ? 'font-extrabold text-blue-900 underline' : 'font-bold'}`}>
                        {sheet.badgeTitle}
                      </div>
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
                  <div className={`p-2 ${sheet.highlightTransport ? 'bg-blue-50/60 ring-1 ring-blue-400/40 rounded-xs' : ''}`}>
                      <table className="w-full">
                          <tbody>
                              <tr>
                                <td className="w-32">GR/RR No.</td>
                                <td className={sheet.highlightTransport ? 'font-bold' : ''}>: {ewayBill?.trans_doc_no || invoice?.gr_rr_no || 'N/A'}</td>
                              </tr>
                              <tr>
                                <td>Transport</td>
                                <td className={sheet.highlightTransport ? 'font-bold text-blue-900' : ''}>
                                  : {ewayBill?.transporter_name || invoice?.transport_name || ewayBill?.trans_mode_display || 'Road'}
                                </td>
                              </tr>
                              <tr>
                                <td>Vehicle No.</td>
                                <td className="font-bold">: {ewayBill?.vehicle_no || invoice?.vehicle_number || 'N/A'}</td>
                              </tr>
                              <tr>
                                <td>E-Way Bill No.</td>
                                <td className="font-bold">: {ewayBill?.eway_bill_number ? `${ewayBill.eway_bill_number} (Exp: ${new Date(ewayBill.valid_upto).toLocaleDateString('en-IN')})` : (invoice?.eway_bill_number || 'N/A')}</td>
                              </tr>
                          </tbody>
                      </table>
                      {sheet.highlightTransport && (
                        <div className="mt-1 pt-1 border-t border-blue-200 text-[10px] text-blue-800 flex items-center justify-between">
                          <span className="font-semibold uppercase tracking-wider">Logistics Copy</span>
                          <span className="italic">{hasTransportDetails ? 'Vehicle / E-Way verified' : 'Counter / Local Transport'}</span>
                        </div>
                      )}
                  </div>
              </div>

              {/* Party Grid */}
              <div className="grid grid-cols-2 border-b-2 border-black text-sm">
                  <div className="p-2 border-r-2 border-black flex flex-col">
                      <span className="italic mb-1">Billed to :</span>
                      <strong className="text-base">{invoice.party.name}</strong>
                      {invoice.party.address && <span className="whitespace-pre-wrap">{invoice.party.address}</span>}
                      <div className="mt-2 pt-1">
                          GSTIN / UIN <span className="ml-4 font-bold">: {invoice.party.gstin || 'Unregistered'}</span>
                      </div>
                  </div>
                  <div className="p-2 flex flex-col">
                      <span className="italic mb-1">Shipped to :</span>
                      <strong className="text-base">{invoice.party.name}</strong>
                      {invoice.party.address && <span className="whitespace-pre-wrap">{invoice.party.address}</span>}
                      <div className="mt-2 pt-1">
                          GSTIN / UIN <span className="ml-4 font-bold">: {invoice.party.gstin || 'Unregistered'}</span>
                      </div>
                  </div>
              </div>
            </>
          ) : (
            /* Compact Continuation Header for Page 2+ */
            <div className="p-2.5 border-b-2 border-black bg-slate-50/30">
              <div className="flex justify-between items-center text-xs font-bold mb-1">
                <div className="text-left">
                  <span className="font-extrabold text-sm tracking-wide">{invoice.company.name}</span>
                  <span className="ml-3 font-normal text-slate-700 text-xs">GSTIN: {invoice.company.gstin || 'Unregistered'}</span>
                </div>
                <div className={`italic ${sheet.highlightTransport ? 'font-extrabold text-blue-900 underline' : 'font-bold'}`}>
                  {sheet.badgeTitle} • Page {sheet.pageNumber} of {sheet.totalPages}
                </div>
              </div>
              <div className="flex justify-between items-center text-xs pt-1 border-t border-slate-300">
                <div className="flex gap-4">
                  <span>Invoice No: <strong className="font-bold">{invoice.voucher_number}</strong></span>
                  <span>Dated: <strong className="font-bold">{invoice.date}</strong></span>
                </div>
                <div className="text-right">
                  <span>Billed to: <strong className="font-bold">{invoice.party.name}</strong></span>
                </div>
              </div>
            </div>
          )}

              {/* Items Table */}
              <div className="flex-1 flex flex-col invoice-items-table-container">
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
                          {/* If continuation page (Page > 1), show Brought Forward row */}
                          {!sheet.isFirstPage && (
                            <tr className="border-b border-black font-semibold bg-slate-50/60">
                              <td colSpan={7} className="border-r border-black py-1.5 px-3 text-right italic text-xs">
                                Total Brought Forward from Page {sheet.pageNumber - 1} &rarr;
                              </td>
                              <td className="text-right py-1.5 pr-2 font-bold font-mono text-xs whitespace-nowrap">
                                {sheet.broughtForwardSubtotal.toLocaleString('en-IN', {minimumFractionDigits: 2})}
                              </td>
                            </tr>
                          )}

                          {sheet.pageItems.map((item: any, idx: number) => (
                              <tr key={idx} className="align-top border-b border-black">
                                  <td className="border-r border-black text-center py-2 px-1">
                                    {sheet.itemStartIndex + idx + 1}
                                  </td>
                                  <td className="border-r border-black text-left py-2 pl-2 font-medium">
                                      <div>{item.product_name}</div>
                                      {showBrand && item.brand && (
                                          <div className="text-[10px] text-slate-600 font-normal mt-0.5">
                                              Brand: {item.brand}
                                          </div>
                                      )}
                                  </td>
                                  <td className="border-r border-black text-center py-2 px-1 whitespace-nowrap">{item.hsn_code}</td>
                                  <td className="border-r border-black text-right py-2 pr-1 whitespace-nowrap">{Number(item.quantity).toFixed(2)}</td>
                                  <td className="border-r border-black text-center py-2 px-1 whitespace-nowrap">{item.unit}</td>
                                  <td className="border-r border-black text-right py-2 pr-1 whitespace-nowrap">{Number(item.rate).toFixed(2)}</td>
                                  <td className="border-r border-black text-center py-2 px-1 whitespace-nowrap">{Number(item.discount_percent).toFixed(2)}%</td>
                                  <td className="text-right py-2 pr-2 font-medium whitespace-nowrap">{Number(item.taxable_amount).toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
                              </tr>
                          ))}
                          {/* Filler Row */}
                          <tr className="border-b border-black h-full flex-1" style={{ height: '100%' }}>
                              <td className="border-r border-black h-full min-h-[40px]"></td>
                              <td className="border-r border-black"></td>
                              <td className="border-r border-black"></td>
                              <td className="border-r border-black"></td>
                              <td className="border-r border-black"></td>
                              <td className="border-r border-black"></td>
                              <td className="border-r border-black"></td>
                              <td></td>
                          </tr>

                          {/* If not last page, show Carried Over row at bottom of table */}
                          {!sheet.isLastPage && (
                            <tr className="border-t-2 border-black font-semibold bg-slate-50/60">
                              <td colSpan={7} className="border-r border-black py-1.5 px-3 text-right italic text-xs">
                                Total Carried Over to Page {sheet.pageNumber + 1} &rarr;
                              </td>
                              <td className="text-right py-1.5 pr-2 font-bold font-mono text-xs whitespace-nowrap">
                                {sheet.carriedOverSubtotal.toLocaleString('en-IN', {minimumFractionDigits: 2})}
                              </td>
                            </tr>
                          )}
                      </tbody>
                  </table>
              </div>

              {/* Subtotals & Taxes OR Continuation Banner */}
              {!sheet.isLastPage ? (
                <div className="border-t-2 border-black p-3 bg-slate-50 flex items-center justify-between text-xs font-semibold">
                  <div className="italic text-slate-700">
                    Invoice continued on Page {sheet.pageNumber + 1} of {sheet.totalPages}...
                  </div>
                  <div className="text-right text-[11px] text-slate-500">
                    (Statutory Tax breakup, Bank Details &amp; Signatures on Page {sheet.totalPages})
                  </div>
                </div>
              ) : (
                <>
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
                  <span className="font-bold underline text-[13px]">BANK & PAYMENT DETAILS</span><br/>
                  {invoice.company.bank_name || ''} {invoice.company.bank_branch || ''}
                  {invoice.company.bank_account_number ? `, ACCOUNT NO- ${invoice.company.bank_account_number}` : ''}
                  {invoice.company.bank_ifsc ? `, IFSCODE: ${invoice.company.bank_ifsc}` : ''}
                  {invoice.company.upi_id ? ` • UPI ID: ${invoice.company.upi_id}` : ''}
              </div>
                </>
              )}
            </div>

            {/* Bottom Footer Section */}
            {sheet.isLastPage && (
            <div className="flex h-44 print:h-38 text-xs shrink-0">
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
                <div className="w-[20%] p-2 border-r-2 border-black flex flex-col items-center justify-between text-center">
                    <span className="font-bold text-[10px] mb-1">{getQrData().label}</span>
                    {typeof window !== 'undefined' && (
                        <QRCode value={getQrData().value} size={92} className="mx-auto my-auto" />
                    )}
                    <span className="text-[8px] text-slate-600 font-mono tracking-tighter text-center">{getQrData().sublabel}</span>
                </div>
                
                {/* Column 3: Signatures */}
                <div className="w-[35%] flex flex-col">
                    <div className="h-12 p-2 border-b-2 border-black flex items-start">
                        <span className={`text-[11px] font-bold ${sheet.highlightTransport ? 'text-blue-900 font-extrabold' : ''}`}>
                          {sheet.signatoryTitle}
                        </span>
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
            )}

        </div>
        {/* Bottom Page Decorations bar matching exact PDF NumberedCanvas */}
        <div className="flex justify-between items-center text-[10px] text-slate-500 pt-1 px-1">
          <span>This is a Computer Generated Invoice • {sheet.badgeTitle}</span>
          <span>Page {sheet.pageNumber} of {sheet.totalPages}</span>
        </div>
      </div>
    );
  };

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
              margin: 8mm 6mm;
            }
            html, body {
              height: auto !important;
              margin: 0 !important;
              padding: 0 !important;
            }
            #invoice-sheet, .invoice-print-sheet {
              position: static !important;
              transform: none !important;
              width: 100% !important;
              min-width: 100% !important;
              max-width: 100% !important;
              ${
                fitToPage
                  ? `
              height: 280mm !important;
              min-height: 280mm !important;
              max-height: 280mm !important;
              `
                  : `
              min-height: 279mm !important;
              `
              }
              padding: 0 !important;
              margin: 0 !important;
              box-shadow: none !important;
              display: flex !important;
              flex-direction: column !important;
              justify-content: space-between !important;
              box-sizing: border-box !important;
              page-break-inside: avoid !important;
              break-inside: avoid !important;
            }
            .invoice-print-sheet:not(:last-child) {
              page-break-after: always !important;
              break-after: page !important;
            }
            .invoice-print-sheet:last-child {
              page-break-after: auto !important;
              break-after: auto !important;
            }
            .invoice-print-wrapper {
              display: block !important;
              width: 100% !important;
            }
            .invoice-print-wrapper:not(:last-child) {
              page-break-after: always !important;
              break-after: page !important;
            }
            ${
              fitToPage
                ? `
            #invoice-sheet > .border-2, .invoice-print-sheet > .border-2 {
              height: calc(100% - 16px) !important;
              min-height: calc(100% - 16px) !important;
              display: flex !important;
              flex-direction: column !important;
              justify-content: space-between !important;
            }
            #invoice-sheet .invoice-items-table-container, .invoice-print-sheet .invoice-items-table-container {
              flex: 1 1 auto !important;
              display: flex !important;
              flex-direction: column !important;
              min-height: 0 !important;
            }
            #invoice-sheet .invoice-items-table-container table, .invoice-print-sheet .invoice-items-table-container table {
              height: 100% !important;
              display: table !important;
            }
            #invoice-sheet .invoice-items-table-container tbody, .invoice-print-sheet .invoice-items-table-container tbody {
              height: 100% !important;
            }
            `
                : ''
            }
            `
          }
        }
      `}</style>

      {/* Print Controls Bar (Hidden on Print) */}
      <div className="print:hidden bg-slate-900 text-white sticky top-0 z-50 shadow-md">
        {/* Recipient Notification Banner if logged-in user is recipient */}
        {recipientStatus?.is_recipient && (
          <div className={`px-4 py-2 text-xs flex items-center justify-between border-b ${
            recipientStatus.already_added 
              ? 'bg-amber-500/10 border-amber-500/20 text-amber-300' 
              : 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300'
          }`}>
            <div className="flex items-center gap-2 truncate">
              {recipientStatus.already_added ? (
                <ShieldCheck className="w-4 h-4 text-amber-400 shrink-0" />
              ) : (
                <Sparkles className="w-4 h-4 text-emerald-400 shrink-0" />
              )}
              <span className="truncate">
                {recipientStatus.already_added
                  ? `Recorded in your books as Voucher #${recipientStatus.purchase_voucher_number || 'RECORDED'}`
                  : `Issued to ${recipientStatus.active_company_name}. Ready to book!`
                }
              </span>
            </div>
            {recipientStatus.already_added ? (
              <button
                type="button"
                onClick={() => router.push(recipientStatus.purchase_voucher_id ? `/sales/${recipientStatus.purchase_voucher_id}/print` : '/purchase')}
                className="underline font-bold text-amber-400 hover:text-amber-300 shrink-0 ml-2 cursor-pointer"
              >
                View
              </button>
            ) : (
              <button
                type="button"
                onClick={() => router.push(`/network/inbox?open_request=${recipientStatus.edi_request_id || ''}`)}
                className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-lg text-[10px] shrink-0 ml-2 cursor-pointer shadow-xs"
              >
                1-Click Book
              </button>
            )}
          </div>
        )}

        {/* Mobile Toolbar (sm:hidden) */}
        <div className="p-2.5 space-y-2 sm:hidden border-b border-slate-800">
          <div className="flex items-center justify-between gap-1.5">
            {isAuth ? (
              <button
                onClick={() => router.back()}
                className="text-slate-300 hover:text-white p-1.5 bg-slate-800 rounded-lg text-xs font-semibold flex items-center gap-1 cursor-pointer"
              >
                <ArrowLeft className="w-4 h-4" />
                <span>Back</span>
              </button>
            ) : (
              <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-200 truncate">
                <FileText className="w-4 h-4 text-emerald-400 shrink-0" />
                <span className="truncate font-mono">#{invoice?.voucher_number || 'INVOICE'}</span>
              </div>
            )}

            <div className="flex items-center gap-1.5">
              {!isAuth && (
                <button
                  onClick={() => router.push(`/login?redirect=${encodeURIComponent(window.location.pathname)}`)}
                  className="px-2.5 py-1.5 bg-slate-800 text-slate-200 text-xs rounded-lg font-medium flex items-center gap-1"
                >
                  <LogIn className="w-3.5 h-3.5 text-primary" />
                  <span>Sign In</span>
                </button>
              )}
              <button
                onClick={handleWhatsAppShareClick}
                disabled={isGeneratingPdf}
                className="bg-emerald-600 hover:bg-emerald-500 text-white p-2 rounded-lg text-xs font-bold flex items-center justify-center shadow-xs cursor-pointer disabled:opacity-50"
                title="Share on WhatsApp"
              >
                <MessageCircle className="w-4 h-4" />
              </button>
              <button
                onClick={handleDownloadPdf}
                disabled={isGeneratingPdf}
                className="bg-slate-800 hover:bg-slate-700 text-white border border-slate-700 p-2 rounded-lg text-xs font-bold flex items-center justify-center cursor-pointer disabled:opacity-50"
                title="Download PDF"
              >
                <Download className="w-4 h-4 text-primary" />
              </button>
              <button
                onClick={() => window.print()}
                className="bg-primary text-primary-foreground hover:bg-primary/90 p-2 rounded-lg text-xs font-bold flex items-center justify-center cursor-pointer"
                title="Print"
              >
                <Printer className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Row 2 on Mobile: Segmented Controls */}
          <div className="flex items-center justify-between gap-1.5 pt-1 text-[11px]">
            <div className="flex items-center p-0.5 bg-slate-800 rounded-lg border border-slate-700 font-semibold">
              <button
                onClick={() => setLayoutMode('A4')}
                className={`px-2 py-1 rounded-md transition-all ${
                  layoutMode === 'A4' ? 'bg-primary text-primary-foreground shadow-xs' : 'text-slate-400'
                }`}
              >
                A4
              </button>
              <button
                onClick={() => setLayoutMode('THERMAL')}
                className={`px-2 py-1 rounded-md transition-all ${
                  layoutMode === 'THERMAL' ? 'bg-primary text-primary-foreground shadow-xs' : 'text-slate-400'
                }`}
              >
                POS
              </button>
            </div>

            <button
              type="button"
              onClick={toggleShowBrand}
              className={`px-2 py-1 rounded-md border font-semibold flex items-center gap-1 transition-all cursor-pointer ${
                showBrand
                  ? 'bg-blue-600/20 text-blue-300 border-blue-500/40'
                  : 'bg-slate-800 text-slate-400 border-slate-700'
              }`}
              title="Toggle brand visibility on invoice"
            >
              <Tag className="w-3 h-3" />
              <span>Brand: {showBrand ? 'ON' : 'OFF'}</span>
            </button>

            {invoice?.company?.upi_id && (
              <div className="flex items-center p-0.5 bg-slate-800 rounded-lg border border-slate-700 font-semibold">
                <button
                  onClick={() => setQrMode('SMART')}
                  className={`px-2 py-1 rounded-md transition-all ${
                    qrMode === 'SMART' ? 'bg-emerald-600 text-white' : 'text-slate-400'
                  }`}
                  title="Dynamic Vouch Link QR"
                >
                  Smart QR
                </button>
                <button
                  onClick={() => setQrMode('UPI')}
                  className={`px-2 py-1 rounded-md transition-all ${
                    qrMode === 'UPI' ? 'bg-emerald-600 text-white' : 'text-slate-400'
                  }`}
                  title="Direct UPI Payment QR"
                >
                  UPI QR
                </button>
              </div>
            )}

            {isAuth && (
              <button
                onClick={() => setIsAuditModalOpen(true)}
                className="bg-slate-800 text-slate-300 p-1.5 rounded-lg border border-slate-700"
                title="Audit Trail"
              >
                <History className="w-3.5 h-3.5 text-blue-400" />
              </button>
            )}
          </div>

          {/* Row 3 on Mobile: Copy Selection when in A4 mode */}
          {layoutMode === 'A4' && (
            <div className="flex items-center gap-1.5 pt-1 text-[11px]">
              <div className="flex items-center gap-1.5 w-full bg-slate-800 rounded-lg border border-slate-700 px-2 py-1">
                <Copy className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                <span className="text-slate-400 text-[10px] uppercase font-bold shrink-0">Copy:</span>
                <select
                  value={copyMode}
                  onChange={(e) => setCopyMode(e.target.value as InvoiceCopyMode)}
                  className="bg-transparent text-slate-200 font-medium focus:outline-hidden cursor-pointer text-[11px] w-full"
                >
                  <option value="ORIGINAL" className="bg-slate-900">Original (Recipient Copy)</option>
                  <option value="TRANSPORTER" className="bg-slate-900">Transporter Copy (Duplicate)</option>
                  <option value="SUPPLIER" className="bg-slate-900">Office Copy ({hasTransportDetails ? 'Triplicate' : 'Duplicate'})</option>
                  <option value="BUNDLE_LOCAL" className="bg-slate-900">2 Copies: Local (Receiver + Office)</option>
                  <option value="BUNDLE_TRANSPORT" className="bg-slate-900">3 Copies: Triplicate (With Transporter)</option>
                </select>
              </div>
            </div>
          )}
        </div>

        {/* Desktop Toolbar (hidden sm:flex) */}
        <div className="hidden sm:flex p-3 gap-3 justify-between items-center">
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
                  <span>Invoice {invoice?.voucher_number}</span>
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

            {/* Copy Mode Selector (A4) */}
            {layoutMode === 'A4' && (
              <div className="relative flex items-center">
                <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-slate-800 rounded-xl border border-slate-700 text-xs font-semibold text-slate-200">
                  <Copy className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                  <select
                    value={copyMode}
                    onChange={(e) => setCopyMode(e.target.value as InvoiceCopyMode)}
                    className="bg-transparent text-slate-200 font-semibold focus:outline-hidden cursor-pointer pr-4 text-xs"
                    title="Select Statutory Copy Type (Rule 48 CGST)"
                  >
                    <optgroup label="Single Copy View" className="bg-slate-900 text-slate-200">
                      <option value="ORIGINAL">Original (Recipient Copy)</option>
                      <option value="TRANSPORTER">Transporter Copy (Duplicate)</option>
                      <option value="SUPPLIER">Office Copy ({hasTransportDetails ? 'Triplicate' : 'Duplicate'})</option>
                    </optgroup>
                    <optgroup label="Print / Download Bundles" className="bg-slate-900 text-slate-200">
                      <option value="BUNDLE_LOCAL">2 Copies: Local (Receiver + Office)</option>
                      <option value="BUNDLE_TRANSPORT">3 Copies: Triplicate (With Transporter)</option>
                    </optgroup>
                  </select>
                  <ChevronDown className="w-3.5 h-3.5 text-slate-400 pointer-events-none -ml-3" />
                </div>
              </div>
            )}

            {/* Brand Toggle on Bill */}
            <button
              type="button"
              onClick={toggleShowBrand}
              className={`px-3 py-1.5 rounded-xl border text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
                showBrand
                  ? 'bg-blue-600/20 text-blue-300 border-blue-500/40 hover:bg-blue-600/30'
                  : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-white'
              }`}
              title="Toggle brand visibility on printed invoice"
            >
              <Tag className="w-3.5 h-3.5" />
              <span>Brand: {showBrand ? 'Visible' : 'Hidden'}</span>
            </button>

            {/* Dynamic QR Mode Toggle on Desktop */}
            {invoice?.company?.upi_id && (
              <div className="flex items-center p-1 bg-slate-800 rounded-xl border border-slate-700 text-xs font-semibold">
                <button
                  onClick={() => setQrMode('SMART')}
                  className={`px-3 py-1 rounded-lg transition-all cursor-pointer ${
                    qrMode === 'SMART' ? 'bg-emerald-600 text-white shadow-xs' : 'text-slate-400 hover:text-white'
                  }`}
                  title="Dynamic QR: Public View, Pay UPI, Register/Add to Purchase"
                >
                  Smart QR
                </button>
                <button
                  onClick={() => setQrMode('UPI')}
                  className={`px-3 py-1 rounded-lg transition-all cursor-pointer ${
                    qrMode === 'UPI' ? 'bg-emerald-600 text-white shadow-xs' : 'text-slate-400 hover:text-white'
                  }`}
                  title="Direct UPI Payment QR"
                >
                  UPI QR
                </button>
              </div>
            )}

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

            {/* WhatsApp Share Button */}
            <button
              onClick={handleWhatsAppShareClick}
              disabled={isGeneratingPdf}
              className="bg-emerald-600 hover:bg-emerald-500 text-white px-3.5 py-2 rounded-xl text-xs font-bold flex items-center gap-1.5 shadow-sm transition-all cursor-pointer disabled:opacity-50"
              title="Share on WhatsApp with Official PDF & Link"
            >
              {isGeneratingPdf ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <MessageCircle className="w-4 h-4" />
              )}
              <span>Share</span>
            </button>

            {/* Download PDF Button */}
            <button
              onClick={handleDownloadPdf}
              disabled={isGeneratingPdf}
              className="bg-slate-800 hover:bg-slate-700 text-slate-100 border border-slate-700 px-3.5 py-2 rounded-xl text-xs font-bold flex items-center gap-1.5 shadow-sm transition-all cursor-pointer disabled:opacity-50"
              title="Download Official PDF"
            >
              {isGeneratingPdf ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Download className="w-4 h-4 text-primary" />
              )}
              <span>PDF</span>
            </button>

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
      </div>

      {/* Share Status Message Banner */}
      {shareStatusMessage && (
        <div className="print:hidden bg-emerald-950/90 border-b border-emerald-500/30 text-emerald-200 px-4 py-2.5 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Check className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>{shareStatusMessage}</span>
          </div>
          <button onClick={() => setShareStatusMessage(null)} className="text-emerald-400 hover:text-white p-1 cursor-pointer">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

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
                  <div className="font-bold flex items-baseline justify-between gap-1">
                    <span>{item.product_name}</span>
                    {showBrand && item.brand && (
                      <span className="text-[10px] font-normal text-slate-600 shrink-0">
                        ({item.brand})
                      </span>
                    )}
                  </div>
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

            {/* Bank & Payment Details */}
            {invoice.company?.bank_account_number && (
              <div className="py-2 border-b border-dashed border-black text-[10px] text-center">
                <div className="font-bold">BANK DETAILS FOR PAYMENT</div>
                <div>{invoice.company.bank_name || ''}</div>
                <div>A/C: {invoice.company.bank_account_number}</div>
                <div>IFSC: {invoice.company.bank_ifsc || ''}</div>
                {invoice.company.upi_id && (
                  <div className="font-mono font-bold mt-1 text-[10px] text-emerald-800">UPI: {invoice.company.upi_id}</div>
                )}
              </div>
            )}

            {/* QR Code */}
            <div className="py-2 flex flex-col items-center justify-center border-b border-dashed border-black text-center">
              {typeof window !== 'undefined' && (
                <QRCode value={getQrData().value} size={80} />
              )}
              <span className="text-[10px] font-bold mt-1.5 text-slate-900">{getQrData().label}</span>
              <span className="text-[8px] text-slate-500 font-mono tracking-tighter">{getQrData().sublabel}</span>
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
        <div className="w-full overflow-x-auto p-2 sm:p-8 flex flex-col items-center justify-start bg-slate-200 print:bg-white print:p-0">
          
          {/* Mobile Screen Scaling Controls Pill */}
          {viewportWidth < 794 && (
            <div className="mb-2.5 flex items-center justify-between w-full max-w-sm px-3.5 py-1.5 bg-slate-800 text-white rounded-full text-[11px] shadow-sm border border-slate-700 print:hidden">
              <span className="text-slate-300 font-mono">
                {scaleMode === 'fit' ? `Screen Fit: ${Math.round(scale * 100)}%` : 'Full Size: 100%'}
              </span>
              <button
                type="button"
                onClick={() => setScaleMode(scaleMode === 'fit' ? '100' : 'fit')}
                className="font-bold text-primary hover:underline ml-2 cursor-pointer"
              >
                {scaleMode === 'fit' ? 'Zoom 100%' : 'Fit Screen'}
              </button>
            </div>
          )}

          {/* Render Sheets depending on Copy Mode & Page Chunks */}
          <div className="w-full flex flex-col items-center gap-6 print:gap-0 print:block">
            {getSheetsToRender().map((sheet, sheetIdx, allSheets) => (
              <div key={`${sheet.copyType}-p${sheet.pageNumber}-${sheetIdx}`} className="w-full flex flex-col items-center invoice-print-wrapper print:block print:w-full">
                {/* On-screen visual page break divider if multi-sheet bundle */}
                {sheetIdx > 0 && (
                  <div className="print:hidden my-4 sm:my-6 flex items-center justify-center gap-3 w-full max-w-[210mm]">
                    <div className="h-px bg-slate-300 flex-1" />
                    <span className="text-[11px] sm:text-xs font-semibold text-slate-600 uppercase tracking-wider bg-slate-100 px-3 py-1 rounded-full border border-slate-300 shadow-xs flex items-center gap-1.5">
                      <Copy className="w-3 h-3 text-blue-600" />
                      Page {sheet.pageNumber} of {sheet.totalPages} • {sheet.badgeTitle}
                    </span>
                    <div className="h-px bg-slate-300 flex-1" />
                  </div>
                )}

                <div
                  style={
                    activeScale < 1
                      ? {
                          width: `${794 * activeScale}px`,
                          height: `${sheetHeight * activeScale}px`,
                          position: 'relative',
                          overflow: 'hidden',
                          margin: '0 auto',
                          transition: 'width 0.15s ease, height 0.15s ease',
                        }
                      : undefined
                  }
                  className="print:w-full print:h-auto print:overflow-visible transition-all flex justify-center"
                >
                  {renderA4Sheet(sheet, sheetIdx, allSheets.length)}
                </div>
              </div>
            ))}
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
