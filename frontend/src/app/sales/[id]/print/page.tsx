"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useParams, useRouter } from 'next/navigation';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import QRCode from 'react-qr-code';
import { gstApi, EWayBillData } from '@/lib/api/gst';
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
  ChevronDown
} from 'lucide-react';

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
  const [rememberPreference, setRememberPreference] = useState<boolean>(false);
  const [copiedToClipboard, setCopiedToClipboard] = useState<boolean>(false);

  useEffect(() => {
    if (!isAuthenticated()) { router.push('/login'); return; }
    fetchInvoice();
  }, [invoiceId]);

  const fetchInvoice = async () => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/vouchers/detail/${invoiceId}/`, { headers });
      setInvoice(res.data.data);

      try {
        const ewayRes = await gstApi.getEWayBillForVoucher(invoiceId);
        if (ewayRes.success && ewayRes.data && ewayRes.data.status !== 'CAN') {
          setEwayBill(ewayRes.data);
        }
      } catch (e) {
        // E-Way Bill is optional
      }
    } catch (err) {
      console.error(err);
    }
  };

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

  const generateInvoicePdf = async (): Promise<{ file: File; blobUrl: string } | null> => {
    const element = document.getElementById('invoice-sheet');
    if (!element) return null;

    const isThermal = layoutMode === 'THERMAL';
    
    const canvas = await (html2canvas as any)(element, {
      scale: 2,
      useCORS: true,
      allowTaint: true,
      logging: false,
      backgroundColor: '#ffffff',
    });

    // Also copy canvas image to clipboard if supported so user can paste (Ctrl+V) into WhatsApp
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
    const pdfWidth = isThermal ? 80 : 210;
    const imgHeight = (canvas.height * pdfWidth) / canvas.width;
    const pdfHeight = isThermal ? imgHeight : Math.max(297, imgHeight);

    const pdf = new jsPDF({
      orientation: 'portrait',
      unit: 'mm',
      format: isThermal ? [pdfWidth, pdfHeight] : 'a4',
    });

    pdf.addImage(imgData, 'PNG', 0, 0, pdfWidth, imgHeight);

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
    const filename = getCleanInvoiceFilename();
    return `*Invoice: ${invoice.voucher_number}* from *${invoice.company.name}*\nTotal Amount: *₹${Number(finalGrandTotal).toFixed(2)}*\n\n(PDF file *${filename}* is attached. Thank you for your business!)`;
  };

  const getCleanPhone = () => {
    let phone = invoice?.party?.phone || invoice?.party?.mobile || '';
    phone = phone.replace(/[^0-9]/g, '');
    if (phone.length === 10) {
      phone = '91' + phone;
    }
    return phone;
  };

  const handleOpenWhatsApp = (target: 'web' | 'app') => {
    const text = buildWhatsAppTextMessage();
    const phone = getCleanPhone();

    if (rememberPreference && typeof window !== 'undefined') {
      localStorage.setItem('vouch_whatsapp_preference', target);
    }

    let url = '';
    if (target === 'web') {
      // Direct WhatsApp Web URL
      url = phone
        ? `https://web.whatsapp.com/send?phone=${phone}&text=${encodeURIComponent(text)}`
        : `https://web.whatsapp.com/send?text=${encodeURIComponent(text)}`;
    } else {
      // WhatsApp Application URL protocol
      url = phone
        ? `whatsapp://send?phone=${phone}&text=${encodeURIComponent(text)}`
        : `whatsapp://send?text=${encodeURIComponent(text)}`;
    }

    window.open(url, '_blank');
    setIsWhatsAppModalOpen(false);
  };

  const handleWhatsAppShareClick = async () => {
    if (!invoice) return;
    setIsGeneratingPdf(true);

    try {
      const pdfResult = await generateInvoicePdf();
      if (!pdfResult) {
        alert('Could not render invoice PDF. Please try again.');
        return;
      }

      const { file, blobUrl } = pdfResult;
      const filename = getCleanInvoiceFilename();

      // Check for Mobile / Web Share API with file attachment support
      const isMobileDevice = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
      if (isMobileDevice && navigator.canShare && navigator.canShare({ files: [file] })) {
        try {
          await navigator.share({
            files: [file],
            title: `Invoice ${invoice.voucher_number}`,
            text: `Invoice ${invoice.voucher_number} from ${invoice.company.name}`,
          });
          return;
        } catch (shareErr: any) {
          if (shareErr?.name === 'AbortError') {
            return;
          }
        }
      }

      // Automatically download the PDF named with the invoice number
      triggerPdfDownload(blobUrl, filename);

      // Check if user already set a preference for Web vs App
      const savedPref = typeof window !== 'undefined' ? localStorage.getItem('vouch_whatsapp_preference') : null;
      if (savedPref === 'web' || savedPref === 'app') {
        handleOpenWhatsApp(savedPref as 'web' | 'app');
      } else {
        // Open choice modal to pick between WhatsApp Web or WhatsApp Desktop Application
        setIsWhatsAppModalOpen(true);
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
          <button 
            onClick={() => router.back()} 
            className="text-slate-300 hover:text-white px-3 py-1.5 bg-slate-800 hover:bg-slate-700 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back</span>
          </button>

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
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Download PDF Button */}
          <button
            onClick={handleDownloadPdf}
            disabled={isGeneratingPdf}
            className="bg-slate-800 hover:bg-slate-700 text-white border border-slate-700 px-3.5 py-2 rounded-xl text-xs font-semibold flex items-center gap-1.5 shadow-sm transition-all cursor-pointer disabled:opacity-50"
            title="Download PDF directly to your device"
          >
            {isGeneratingPdf ? <Loader2 className="w-4 h-4 animate-spin text-primary" /> : <Download className="w-4 h-4" />}
            <span>Download PDF</span>
          </button>

          {/* WhatsApp Share Button with Split / Options */}
          <div className="inline-flex rounded-xl shadow-sm">
            <button
              onClick={handleWhatsAppShareClick}
              disabled={isGeneratingPdf}
              className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-l-xl text-xs font-bold flex items-center gap-2 transition-all cursor-pointer disabled:opacity-50"
              title="Share PDF of this invoice via WhatsApp Web or Application"
            >
              {isGeneratingPdf ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <MessageCircle className="w-4 h-4 fill-current" />
              )}
              <span>{isGeneratingPdf ? 'Rendering PDF...' : 'Share on WhatsApp'}</span>
            </button>
            <button
              onClick={() => setIsWhatsAppModalOpen(true)}
              className="bg-emerald-700 hover:bg-emerald-600 text-white px-2 py-2 rounded-r-xl border-l border-emerald-800 text-xs transition-colors cursor-pointer"
              title="Choose WhatsApp Web or Desktop Application"
            >
              <ChevronDown className="w-3.5 h-3.5" />
            </button>
          </div>

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

      {/* WHATSAPP DESTINATION MODAL (Web vs App) */}
      {isWhatsAppModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs print:hidden animate-in fade-in duration-200">
          <div className="bg-slate-900 border border-slate-700 text-white rounded-2xl shadow-2xl max-w-md w-full p-6 space-y-4 relative">
            <button
              onClick={() => setIsWhatsAppModalOpen(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-emerald-500/20 text-emerald-400">
                <MessageCircle className="w-6 h-6 fill-current" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">Share Invoice on WhatsApp</h3>
                <p className="text-xs text-slate-400">
                  Select your preferred WhatsApp platform
                </p>
              </div>
            </div>

            {/* Status Checklist */}
            <div className="p-3 bg-slate-800/80 rounded-xl border border-slate-700/80 space-y-2 text-xs">
              <div className="flex items-center gap-2 text-emerald-400">
                <Check className="w-4 h-4 shrink-0" />
                <span>
                  <strong>{filename}</strong> ready for sending
                </span>
              </div>
              <div className="flex items-center gap-2 text-slate-300">
                <Check className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>Customer: <strong>{invoice.party?.name}</strong> {invoice.party?.phone ? `(${invoice.party.phone})` : ''}</span>
              </div>
              {copiedToClipboard && (
                <div className="flex items-center gap-2 text-blue-400">
                  <Copy className="w-3.5 h-3.5 shrink-0" />
                  <span>Invoice preview copied to clipboard (Press Ctrl+V to paste)</span>
                </div>
              )}
            </div>

            {/* Selection Options */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
              {/* WhatsApp Web */}
              <button
                onClick={() => handleOpenWhatsApp('web')}
                className="flex flex-col items-center text-center p-4 rounded-xl border border-slate-700 bg-slate-800 hover:bg-slate-750 hover:border-emerald-500/60 transition-all cursor-pointer group"
              >
                <div className="p-3 rounded-xl bg-blue-500/10 text-blue-400 group-hover:bg-blue-500/20 mb-2">
                  <Globe className="w-6 h-6" />
                </div>
                <span className="text-sm font-bold text-white">WhatsApp Web</span>
                <span className="text-[11px] text-slate-400 mt-1">Open web.whatsapp.com in browser tab</span>
              </button>

              {/* WhatsApp Application */}
              <button
                onClick={() => handleOpenWhatsApp('app')}
                className="flex flex-col items-center text-center p-4 rounded-xl border border-slate-700 bg-slate-800 hover:bg-slate-750 hover:border-emerald-500/60 transition-all cursor-pointer group"
              >
                <div className="p-3 rounded-xl bg-emerald-500/10 text-emerald-400 group-hover:bg-emerald-500/20 mb-2">
                  <Laptop className="w-6 h-6" />
                </div>
                <span className="text-sm font-bold text-white">WhatsApp App</span>
                <span className="text-[11px] text-slate-400 mt-1">Launch installed Windows/Mac app</span>
              </button>
            </div>

            {/* Remember Preference Checkbox */}
            <div className="flex items-center justify-between pt-2 border-t border-slate-800 text-xs text-slate-400">
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={rememberPreference}
                  onChange={(e) => setRememberPreference(e.target.checked)}
                  className="rounded border-slate-700 text-emerald-500 focus:ring-0 cursor-pointer"
                />
                <span>Remember my choice next time</span>
              </label>
              {typeof window !== 'undefined' && localStorage.getItem('vouch_whatsapp_preference') && (
                <button
                  onClick={() => {
                    localStorage.removeItem('vouch_whatsapp_preference');
                    alert('Preference reset.');
                  }}
                  className="text-slate-500 hover:text-slate-300 underline text-[11px]"
                >
                  Reset saved
                </button>
              )}
            </div>

            {/* Instruction Footer */}
            <div className="text-[11px] text-slate-400 bg-slate-950/60 p-2.5 rounded-lg border border-slate-800 text-center">
              💡 The PDF <strong>{filename}</strong> is saved in your Downloads. Simply click <strong>Attach &gt; Document</strong> or press <strong>Ctrl+V</strong> in the chat.
            </div>
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
          <div id="invoice-sheet" className="w-[210mm] min-h-[297mm] print:min-h-[95vh] bg-white p-6 sm:p-8 shadow-[0_0_15px_rgba(0,0,0,0.15)] print:shadow-none print:p-6 print:pt-10 flex flex-col mx-auto">
          
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
                <div className="grid grid-cols-2 border-b-2 border-black text-sm h-32">
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
                            <tr className="border-b-2 border-black text-center h-8">
                                <th className="w-12 border-r border-black">S.N.</th>
                                <th className="border-r border-black text-left pl-2">Description of Goods</th>
                                <th className="w-20 border-r border-black">HSN</th>
                                <th className="w-16 border-r border-black">Qty.</th>
                                <th className="w-12 border-r border-black">Unit</th>
                                <th className="w-20 border-r border-black">Price</th>
                                <th className="w-16 border-r border-black">Disc%</th>
                                <th className="w-28 text-right pr-2">Amount(Rs.)</th>
                            </tr>
                        </thead>
                        <tbody>
                            {invoice.items.map((item: any, idx: number) => (
                                <tr key={idx} className="h-10 align-top">
                                    <td className="border-r border-black text-center pt-2">{idx + 1}</td>
                                    <td className="border-r border-black text-left pl-2 pt-2 font-medium">{item.product_name}</td>
                                    <td className="border-r border-black text-center pt-2">{item.hsn_code}</td>
                                    <td className="border-r border-black text-right pr-1 pt-2">{Number(item.quantity).toFixed(2)}</td>
                                    <td className="border-r border-black text-center pt-2">{item.unit}</td>
                                    <td className="border-r border-black text-right pr-1 pt-2">{Number(item.rate).toFixed(2)}</td>
                                    <td className="border-r border-black text-center pt-2">{Number(item.discount_percent).toFixed(2)} %</td>
                                    <td className="text-right pr-2 pt-2 font-medium">{Number(item.taxable_amount).toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
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
    </div>
  );
}
