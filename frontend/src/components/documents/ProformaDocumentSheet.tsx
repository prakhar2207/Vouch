"use client";
import React, { useMemo } from 'react';
import QRCode from 'react-qr-code';
import { 
  Building2, 
  Phone, 
  Mail, 
  Globe, 
  MapPin, 
  CheckCircle2, 
  Calendar, 
  Clock, 
  FileText, 
  CreditCard, 
  ShieldCheck, 
  QrCode as QrCodeIcon 
} from 'lucide-react';
import { API_BASE_URL } from '@/utils/api';

export interface DocumentBrandingConfig {
  accent_color?: string; // e.g. '#0f172a', '#2563eb', '#4f46e5'
  logo_position?: 'left' | 'center';
  logo_height?: number; // e.g. 36 to 80, default 52
  firm_name_size?: 'normal' | 'large' | 'extra_large'; // default 'large'
  show_logo?: boolean; // default true
  watermark_enabled?: boolean; // default true
  show_bank_details?: boolean; // default true
  show_upi_qr?: boolean; // default true
  show_terms?: boolean; // default true
  show_amount_in_words?: boolean; // default true
  show_hsn_summary?: boolean; // default true
  default_terms_conditions?: string;
  default_notes?: string;
  show_promo_footer?: boolean; // default false
  promo_tagline?: string;
  promo_website?: string;
  promo_social?: string;
  promo_support_phone?: string;
  promo_support_email?: string;
  promo_message?: string;
  promo_qr_url?: string;
}

export interface ProformaDocumentSheetProps {
  doc: any;
  company: any;
  branding?: DocumentBrandingConfig;
  watermarkOverride?: boolean;
  logoOverride?: boolean;
  titleOverride?: string;
  legalNoteOverride?: string;
  isPreviewMode?: boolean;
}

export const STATE_NAMES: Record<string, string> = {
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

export function formatIndianCurrency(amount: number | string | null | undefined): string {
  const val = Number(amount || 0);
  return '₹ ' + val.toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function numberToWords(numAmount: number): string {
  const a = ['', 'One ', 'Two ', 'Three ', 'Four ', 'Five ', 'Six ', 'Seven ', 'Eight ', 'Nine ', 'Ten ', 'Eleven ', 'Twelve ', 'Thirteen ', 'Fourteen ', 'Fifteen ', 'Sixteen ', 'Seventeen ', 'Eighteen ', 'Nineteen '];
  const b = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety'];
  const numStr = Math.floor(Math.abs(numAmount)).toString();
  if (numStr.length > 9) return 'overflow';
  const n = ('000000000' + numStr).slice(-9).match(/^(\d{2})(\d{2})(\d{2})(\d{1})(\d{2})$/);
  if (!n) return '';
  let str = '';
  str += (n[1] !== '00') ? (a[Number(n[1])] || b[Number(n[1][0])] + ' ' + a[Number(n[1][1])]) + 'Crore ' : '';
  str += (n[2] !== '00') ? (a[Number(n[2])] || b[Number(n[2][0])] + ' ' + a[Number(n[2][1])]) + 'Lakh ' : '';
  str += (n[3] !== '00') ? (a[Number(n[3])] || b[Number(n[3][0])] + ' ' + a[Number(n[3][1])]) + 'Thousand ' : '';
  str += (n[4] !== '0') ? (a[Number(n[4])] || b[Number(n[4][0])] + ' ' + a[Number(n[4][1])]) + 'Hundred ' : '';
  str += (n[5] !== '00') ? ((str !== '') ? 'and ' : '') + (a[Number(n[5])] || b[Number(n[5][0])] + ' ' + a[Number(n[5][1])]) : '';
  return str.trim() ? 'INR ' + str.trim() + ' Rupees Only' : 'Zero Rupees Only';
}

function resolveMediaUrl(raw?: string): string {
  if (!raw) return '';
  if (raw.startsWith('data:') || raw.startsWith('http://') || raw.startsWith('https://')) return raw;
  return `${API_BASE_URL}${raw.startsWith('/') ? '' : '/'}${raw}`;
}

export default function ProformaDocumentSheet({
  doc,
  company,
  branding: propBranding,
  watermarkOverride,
  logoOverride,
  titleOverride,
  legalNoteOverride,
  isPreviewMode = false,
}: ProformaDocumentSheetProps) {
  // Merge branding configs
  const branding: DocumentBrandingConfig = useMemo(() => {
    const fromComp = company?.settings?.document_branding || {};
    return {
      accent_color: '#0f172a',
      logo_position: 'left',
      logo_height: 52,
      show_logo: true,
      watermark_enabled: true,
      show_bank_details: true,
      show_upi_qr: true,
      show_terms: true,
      show_amount_in_words: true,
      show_hsn_summary: true,
      default_terms_conditions: '',
      default_notes: '',
      show_promo_footer: false,
      ...fromComp,
      ...propBranding,
    };
  }, [company?.settings?.document_branding, propBranding]);

  const accentColor = branding.accent_color || '#0f172a';
  const showLogo = logoOverride !== undefined ? logoOverride : (branding.show_logo !== false);
  const showWatermark = watermarkOverride !== undefined ? watermarkOverride : (branding.watermark_enabled !== false);
  const showBankDetails = branding.show_bank_details !== false;
  const showUpiQr = branding.show_upi_qr !== false;
  const showTerms = branding.show_terms !== false;
  const showAmountInWords = branding.show_amount_in_words !== false;
  const showHsnSummary = branding.show_hsn_summary !== false;
  const showPromoFooter = Boolean(branding.show_promo_footer);

  // Company logo, signature, and stamp assets
  const logoSrc = useMemo(() => {
    return resolveMediaUrl(company?.logo_data || company?.logo_url || company?.logo);
  }, [company?.logo_data, company?.logo_url, company?.logo]);

  const signatureSrc = useMemo(() => {
    return resolveMediaUrl(company?.signature_data || company?.signature_url || company?.proprietor_signature);
  }, [company?.signature_data, company?.signature_url, company?.proprietor_signature]);

  const stampSrc = useMemo(() => {
    return resolveMediaUrl(company?.stamp_data || company?.stamp_url || company?.stamp);
  }, [company?.stamp_data, company?.stamp_url, company?.stamp]);

  // Parties & Location info
  const compStateCode = (company?.state_code || '').toString().padStart(2, '0');
  const compStateName = company?.state_name || (compStateCode ? STATE_NAMES[compStateCode] : '') || '';

  const buyerStateCode = (doc?.buyer_state_code || doc?.party_state_code || doc?.party_ledger?.state_code || '').toString().padStart(2, '0');
  const buyerStateName = buyerStateCode ? (STATE_NAMES[buyerStateCode] || buyerStateCode) : (doc?.place_of_supply || '');

  const isInterState = useMemo(() => {
    if (!compStateCode || !buyerStateCode) return false;
    return compStateCode !== buyerStateCode;
  }, [compStateCode, buyerStateCode]);

  // Document labels
  const isPI = (doc?.proforma_type || 'PROFORMA') === 'PROFORMA';
  const documentTitle = titleOverride || (isPI ? 'PROFORMA INVOICE' : 'COMMERCIAL QUOTATION');
  const legalNote = legalNoteOverride || (isPI ? 'This is a Commercial Proforma — Not a GST Tax Invoice' : 'Commercial Estimate / Quotation — Not a GST Tax Invoice');

  // Amounts
  const subtotal = Number(doc?.subtotal || doc?.taxable_amount || 0);
  const totalCgst = Number(doc?.cgst_amount || 0);
  const totalSgst = Number(doc?.sgst_amount || 0);
  const totalIgst = Number(doc?.igst_amount || 0);
  const totalTax = Number(doc?.total_tax || (totalCgst + totalSgst + totalIgst));
  const cartageAmount = Number(doc?.cartage_amount || 0);
  const roundOff = Number(doc?.round_off || 0);
  const finalGrandTotal = Number(doc?.total_amount || 0);

  // UPI payment URL
  const upiId = company?.bank_details?.upi_id || company?.upi_id || company?.bank_account_number || '';
  const upiPayUrl = useMemo(() => {
    if (upiId && upiId.includes('@')) {
      return `upi://pay?pa=${encodeURIComponent(upiId)}&pn=${encodeURIComponent(company?.legal_name || company?.name || 'Merchant')}&am=${finalGrandTotal.toFixed(2)}&tn=${encodeURIComponent(`Adv ${doc?.proforma_number || ''}`)}&cu=INR`;
    }
    return '';
  }, [upiId, company?.legal_name, company?.name, finalGrandTotal, doc?.proforma_number]);

  // Terms and Notes
  const termsText = doc?.terms_and_conditions || branding.default_terms_conditions || "1. Goods once sold will not be taken back or exchanged.\n2. Payment terms: 100% advance or as agreed.\n3. Quotation / Proforma valid for 30 days from date of issue.";
  const customerNotes = doc?.customer_notes || branding.default_notes || "";

  // HSN Tax Breakdown Summary
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
      const key = `${hsn}-${rate}`;
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

    return Array.from(map.values()).sort((a, b) => a.gst_rate - b.gst_rate);
  }, [doc?.items, isInterState]);

  // ═══════════════════════════════════════════════════════════════════════════
  // PAGINATION ENGINE: CALCULATES SHEET SPLITS WITH ORPHAN ROW PREVENTER
  // ═══════════════════════════════════════════════════════════════════════════
  const pages = useMemo(() => {
    const rawItems: any[] = Array.isArray(doc?.items) ? doc.items : [];
    const items = rawItems.length > 0 ? rawItems : [
      {
        item_name: 'Sample Item or Service',
        hsn_code: '998311',
        quantity: 1,
        unit: 'NOS',
        rate: 0,
        discount_percent: 0,
        taxable_amount: 0,
        gst_rate: 18,
        total_amount: 0,
      }
    ];

    // Single-page limit: up to 12 items fit on 1 sheet with compact spacing
    if (items.length <= 12) {
      return [{
        pageNumber: 1,
        totalPages: 1,
        items,
        isFirstPage: true,
        isLastPage: true,
        startIndex: 0,
        broughtForwardSubtotal: 0,
        carriedOverSubtotal: 0,
      }];
    }

    // Multi-page document:
    // Tally-Exact Proportional Balancing & Orphan Prevention:
    // - Page 1 Capacity: Header + Parties + ~12 items (no closing footer)
    // - Middle pages: Compact Header + ~16 items
    // - Last page: Compact Header + Totals & Signatures block + up to 10 items
    const chunks: any[][] = [];
    let remaining = [...items];

    if (remaining.length <= 22) {
      // 2 Pages: Proportionately balance items so neither page looks empty
      const finalPageCount = Math.max(3, Math.min(10, Math.floor(remaining.length * 0.45)));
      const p1Count = remaining.length - finalPageCount;
      chunks.push(remaining.slice(0, p1Count));
      chunks.push(remaining.slice(p1Count));
    } else {
      // 3 or more pages:
      const p1Count = 12;
      chunks.push(remaining.slice(0, p1Count));
      remaining = remaining.slice(p1Count);

      while (remaining.length > 0) {
        if (remaining.length <= 10) {
          if (remaining.length <= 2 && chunks.length > 0) {
            const prev = chunks[chunks.length - 1];
            if (prev.length > 4) {
              const borrowCount = 3 - remaining.length;
              const borrowed = prev.splice(prev.length - borrowCount, borrowCount);
              remaining.unshift(...borrowed);
            }
          }
          chunks.push(remaining);
          break;
        } else {
          const take = Math.min(16, remaining.length - 3);
          chunks.push(remaining.slice(0, take));
          remaining = remaining.slice(take);
        }
      }
    }

    const totalPagesCount = chunks.length;
    let runningSubtotal = 0;
    let runningItemIndex = 0;

    return chunks.map((chunkItems, idx) => {
      const pageNumber = idx + 1;
      const isFirst = pageNumber === 1;
      const isLast = pageNumber === totalPagesCount;
      const broughtForward = runningSubtotal;

      const chunkTaxableSum = chunkItems.reduce((acc, it) => {
        const qty = Number(it.quantity || 1);
        const rate = Number(it.rate || 0);
        const disc = Number(it.discount_percent || 0);
        const taxable = Number(it.taxable_amount || (qty * rate * (1 - disc / 100)));
        return acc + taxable;
      }, 0);

      runningSubtotal += chunkTaxableSum;
      const carriedOver = isLast ? 0 : runningSubtotal;
      const startIndex = runningItemIndex;
      runningItemIndex += chunkItems.length;

      return {
        pageNumber,
        totalPages: totalPagesCount,
        items: chunkItems,
        isFirstPage: isFirst,
        isLastPage: isLast,
        startIndex,
        broughtForwardSubtotal: broughtForward,
        carriedOverSubtotal: carriedOver,
      };
    });
  }, [doc?.items]);

  const totalPagesCount = pages.length;

  return (
    <div className="w-full flex flex-col items-center gap-6 print:gap-0 print:m-0 print:p-0">
      {pages.map((page) => {
        const { 
          pageNumber, 
          totalPages, 
          items: pageItems, 
          isFirstPage, 
          isLastPage, 
          startIndex, 
          broughtForwardSubtotal, 
          carriedOverSubtotal 
        } = page;

        return (
          <div
            key={`page-${pageNumber}`}
            id={isFirstPage ? 'proforma-sheet' : undefined}
            className={`proforma-page-sheet w-[210mm] min-w-[210mm] max-w-[210mm] min-h-[297mm] max-h-[297mm] bg-white text-slate-900 flex flex-col justify-between mx-auto font-sans border border-slate-200 shadow-md print:shadow-none print:border-none relative overflow-hidden box-border p-8 sm:p-10 ${
              !isLastPage ? 'break-after-page page-break-after-always' : ''
            }`}
            style={{
              boxSizing: 'border-box',
              breakAfter: isLastPage ? 'auto' : 'page',
              pageBreakAfter: isLastPage ? 'auto' : 'always',
            }}
          >
            {/* ═══════════════════════════════════════════════════════════════════ */}
            {/* WATERMARK LAYER (Centered Company Logo or Subtle Angled Text)      */}
            {/* ═══════════════════════════════════════════════════════════════════ */}
            {showWatermark && (
              <div
                className="absolute inset-0 flex items-center justify-center pointer-events-none select-none overflow-hidden z-0"
                aria-hidden="true"
              >
                {showLogo && logoSrc ? (
                  <img
                    crossOrigin="anonymous"
                    src={logoSrc}
                    alt=""
                    className="w-[280px] max-w-[50%] max-h-[280px] object-contain opacity-[0.045] grayscale dark:invert"
                  />
                ) : (
                  <div className="flex flex-col items-center justify-center opacity-[0.035] -rotate-12 transform">
                    <span className="text-3xl font-black uppercase tracking-[0.25em] text-slate-800 text-center max-w-md">
                      {company?.name || 'PROFORMA INVOICE'}
                    </span>
                  </div>
                )}
              </div>
            )}

            {/* ═══════════════════════════════════════════════════════════════════ */}
            {/* SHEET CONTENT AREA                                                */}
            {/* ═══════════════════════════════════════════════════════════════════ */}
            <div className="relative z-10 flex-1 flex flex-col justify-between">
              
              {/* TOP SECTION: HEADER & PARTIES */}
              <div>
                {isFirstPage ? (
                  /* ── FULL HEADER (PAGE 1) ── */
                  <div className="pb-5 border-b border-slate-200">
                    <div className="flex justify-between items-start gap-6">
                      {/* Left: Brand Logo & Seller Identity */}
                      <div className="flex-1 min-w-0">
                        <div className={`flex items-start gap-4 mb-2.5 ${branding.logo_position === 'center' ? 'flex-col items-center text-center' : ''}`}>
                          {/* Dedicated Logo Container (Only rendered when logo is enabled & available) */}
                          {showLogo && logoSrc && (
                            <div 
                              className="flex items-center justify-start shrink-0"
                              style={{ 
                                height: `${branding.logo_height || 52}px`,
                                maxWidth: '220px' 
                              }}
                            >
                              <img
                                crossOrigin="anonymous"
                                src={logoSrc}
                                alt={company?.name || 'Company Logo'}
                                className="max-h-full max-w-full object-contain"
                              />
                            </div>
                          )}

                          <div className="min-w-0">
                            <h2 
                              className={`${
                                branding?.firm_name_size === 'extra_large'
                                  ? 'text-2xl sm:text-3xl'
                                  : branding?.firm_name_size === 'normal'
                                  ? 'text-base sm:text-lg'
                                  : 'text-xl sm:text-2xl'
                              } font-black tracking-tight uppercase leading-tight`}
                              style={{ color: accentColor }}
                            >
                              {company?.legal_name || company?.name || 'Company Name'}
                            </h2>
                            {company?.tagline && (
                              <p className="text-[11px] text-slate-500 font-medium italic mt-0.5">
                                {company.tagline}
                              </p>
                            )}
                          </div>
                        </div>

                        {/* Company Details */}
                        <div className="text-[11.5px] text-slate-600 leading-snug space-y-0.5 font-normal">
                          {company?.address && (
                            <p className="text-slate-700">{company.address}</p>
                          )}
                          <p>
                            {[
                              company?.city,
                              compStateName ? `${compStateName} (${compStateCode})` : '',
                              company?.pincode
                            ].filter(Boolean).join(', ')}
                          </p>
                          <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 pt-0.5 text-[11px]">
                            {company?.gstin && (
                              <span>GSTIN: <strong className="text-slate-900 font-semibold">{company.gstin}</strong></span>
                            )}
                            {company?.pan && (
                              <span>PAN: <strong className="text-slate-900 font-semibold">{company.pan}</strong></span>
                            )}
                            {company?.phone && <span>Ph: {company.phone}</span>}
                            {company?.email && <span>Email: {company.email}</span>}
                            {company?.website && <span>Web: {company.website}</span>}
                          </div>
                        </div>
                      </div>

                      {/* Right: Document Title & Metadata Box */}
                      <div className="w-64 shrink-0 text-right">
                        <div 
                          className="inline-block px-3 py-1 rounded text-xs font-black uppercase tracking-wider mb-1"
                          style={{ 
                            backgroundColor: `${accentColor}12`,
                            color: accentColor,
                            border: `1px solid ${accentColor}25` 
                          }}
                        >
                          {documentTitle}
                        </div>
                        <p className="text-[10px] text-slate-400 font-medium mb-3">
                          {legalNote}
                        </p>

                        <div className="bg-slate-50/70 border border-slate-200/80 rounded-lg p-2.5 text-left text-xs space-y-1">
                          <div className="flex justify-between items-center py-0.5 border-b border-slate-200/60">
                            <span className="text-slate-500 font-medium text-[11px]">
                              {isPI ? 'Proforma No:' : 'Quotation No:'}
                            </span>
                            <span className="font-bold text-slate-900 font-mono text-[11.5px]">
                              {doc?.proforma_number || 'PI-0001'}
                            </span>
                          </div>

                          <div className="flex justify-between items-center py-0.5 border-b border-slate-200/60">
                            <span className="text-slate-500 font-medium text-[11px]">Date:</span>
                            <span className="font-semibold text-slate-800 text-[11.5px]">
                              {doc?.date || '—'}
                            </span>
                          </div>

                          {doc?.valid_until && (
                            <div className="flex justify-between items-center py-0.5 border-b border-slate-200/60">
                              <span className="text-slate-500 font-medium text-[11px]">Valid Until:</span>
                              <span className="font-semibold text-amber-700 text-[11.5px]">
                                {doc.valid_until}
                              </span>
                            </div>
                          )}

                          <div className="flex justify-between items-center py-0.5">
                            <span className="text-slate-500 font-medium text-[11px]">Place of Supply:</span>
                            <span className="font-semibold text-slate-800 text-[11px] text-right truncate max-w-[130px]" title={buyerStateName}>
                              {buyerStateName || '—'}
                            </span>
                          </div>
                        </div>

                        {/* Optional Status Badge (Hidden when printing draft) */}
                        {doc?.status && doc.status !== 'DRAFT' && (
                          <div className="mt-1.5 print:hidden">
                            <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold tracking-wide uppercase ${
                              doc.status === 'CONVERTED' 
                                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' 
                                : doc.status === 'ACCEPTED'
                                ? 'bg-blue-50 text-blue-700 border border-blue-200'
                                : 'bg-slate-100 text-slate-700 border border-slate-200'
                            }`}>
                              Status: {doc.status}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* ── PARTIES GRID: BILL TO & SHIP TO ── */}
                    <div className="grid grid-cols-2 gap-4 mt-4 pt-3.5 border-t border-slate-200/70 text-xs">
                      {/* Bill To */}
                      <div className="bg-slate-50/50 border border-slate-200/80 rounded-lg p-3">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
                          Bill To (Customer Details)
                        </span>
                        <h3 className="font-bold text-slate-900 text-sm leading-snug">
                          {doc?.buyer_name || doc?.party_name || doc?.party_ledger?.name || 'Valued Customer'}
                        </h3>
                        {doc?.buyer_address && (
                          <p className="text-slate-600 text-[11.5px] mt-1 leading-relaxed">
                            {doc.buyer_address}
                          </p>
                        )}
                        <div className="mt-2 pt-1.5 border-t border-slate-200/60 text-[11px] text-slate-600 space-y-0.5">
                          <div>
                            GSTIN: <strong className="text-slate-800 font-semibold">{doc?.buyer_gstin || 'Unregistered'}</strong>
                          </div>
                          <div>
                            State: <span className="font-medium text-slate-800">{buyerStateName || 'N/A'} {buyerStateCode ? `(${buyerStateCode})` : ''}</span>
                          </div>
                          {doc?.buyer_phone && <div>Phone: {doc.buyer_phone}</div>}
                          {doc?.buyer_email && <div>Email: {doc.buyer_email}</div>}
                        </div>
                      </div>

                      {/* Ship To / Dispatch Info */}
                      <div className="bg-slate-50/50 border border-slate-200/80 rounded-lg p-3">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
                          Ship To / Place of Delivery
                        </span>
                        <h3 className="font-bold text-slate-900 text-sm leading-snug">
                          {doc?.ship_to_name || doc?.buyer_name || doc?.party_name || doc?.party_ledger?.name || 'Same as Bill To'}
                        </h3>
                        <p className="text-slate-600 text-[11.5px] mt-1 leading-relaxed">
                          {doc?.ship_to_address || doc?.buyer_address || 'Delivery address as agreed.'}
                        </p>
                        <div className="mt-2 pt-1.5 border-t border-slate-200/60 text-[11px] text-slate-600 space-y-0.5">
                          <div>
                            Destination State: <span className="font-medium text-slate-800">{buyerStateName || compStateName}</span>
                          </div>
                          <div>
                            Supply Mode: <span className="font-medium text-slate-800">{isInterState ? 'Inter-State (IGST Applicable)' : 'Intra-State (CGST + SGST Applicable)'}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  /* ── COMPACT HEADER (PAGES 2+) ── */
                  <div className="pb-3 border-b border-slate-200 flex justify-between items-center text-xs">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-slate-900 uppercase" style={{ color: accentColor }}>
                        {company?.legal_name || company?.name}
                      </span>
                      <span className="text-slate-400">•</span>
                      <span className="text-slate-600 font-medium">{documentTitle}</span>
                    </div>
                    <div className="flex items-center gap-3 font-mono text-[11.5px] text-slate-700">
                      <span>Doc: <strong>{doc?.proforma_number}</strong></span>
                      <span>Date: <strong>{doc?.date}</strong></span>
                    </div>
                  </div>
                )}

                {/* ── ITEMS TABLE ── */}
                <div className="mt-4">
                  <table className="w-full text-xs border-collapse">
                    <thead>
                      <tr 
                        className="text-[11px] font-bold uppercase tracking-wider text-slate-700 border-y border-slate-200"
                        style={{ backgroundColor: `${accentColor}06` }}
                      >
                        <th className="py-2 px-2 text-center w-8">#</th>
                        <th className="py-2 px-2 text-left">Description of Goods / Services</th>
                        <th className="py-2 px-2 text-center w-16">HSN/SAC</th>
                        <th className="py-2 px-2 text-right w-12">Qty</th>
                        <th className="py-2 px-1 text-left w-10">Unit</th>
                        <th className="py-2 px-2 text-right w-20">Rate</th>
                        <th className="py-2 px-1 text-right w-12">Disc%</th>
                        <th className="py-2 px-2 text-right w-24">Taxable</th>
                        <th className="py-2 px-1 text-center w-14">GST</th>
                        <th className="py-2 px-2 text-right w-24">Amount</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {/* Tally Brought Forward row on Page 2+ */}
                      {!isFirstPage && (
                        <tr className="border-b-2 border-slate-300 font-semibold bg-slate-50/80 text-xs">
                          <td colSpan={7} className="py-2 px-3 text-right italic text-slate-700">
                            Total Brought Forward from Page {pageNumber - 1} &rarr;
                          </td>
                          <td className="py-2 px-2 text-right font-mono font-bold text-slate-900 whitespace-nowrap">
                            {broughtForwardSubtotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                          </td>
                          <td colSpan={2} className="py-2"></td>
                        </tr>
                      )}

                      {pageItems.map((item: any, idx: number) => {
                        const serial = startIndex + idx + 1;
                        const qty = Number(item.quantity || 1);
                        const rate = Number(item.rate || 0);
                        const disc = Number(item.discount_percent || 0);
                        const taxable = Number(item.taxable_amount || (qty * rate * (1 - disc / 100)));
                        const gstRate = Number(item.gst_rate || 0);
                        const total = Number(item.total_amount || (taxable * (1 + gstRate / 100)));

                        return (
                          <tr key={`item-${serial}`} className="hover:bg-slate-50/50 transition-colors">
                            <td className="py-2.5 px-2 text-center text-slate-400 font-mono text-[11px]">
                              {serial}
                            </td>
                            <td className="py-2.5 px-2 text-left">
                              <p className="font-semibold text-slate-900 leading-snug">
                                {item.item_name || 'Standard Item'}
                              </p>
                              {item.description && (
                                <p className="text-[10.5px] text-slate-500 mt-0.5 leading-snug">
                                  {item.description}
                                </p>
                              )}
                            </td>
                            <td className="py-2.5 px-2 text-center font-mono text-[11px] text-slate-600">
                              {item.hsn_code || '—'}
                            </td>
                            <td className="py-2.5 px-2 text-right font-medium text-slate-800">
                              {qty}
                            </td>
                            <td className="py-2.5 px-1 text-left text-slate-500 text-[11px]">
                              {item.unit || 'PCS'}
                            </td>
                            <td className="py-2.5 px-2 text-right font-mono text-slate-800">
                              {rate.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                            </td>
                            <td className="py-2.5 px-1 text-right text-slate-500">
                              {disc > 0 ? `${disc}%` : '—'}
                            </td>
                            <td className="py-2.5 px-2 text-right font-mono font-medium text-slate-900">
                              {taxable.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                            </td>
                            <td className="py-2.5 px-1 text-center font-mono text-[11px] text-slate-600">
                              {gstRate}%
                            </td>
                            <td className="py-2.5 px-2 text-right font-mono font-bold text-slate-900">
                              {total.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                            </td>
                          </tr>
                        );
                      })}

                      {/* Tally Carried Over row on Intermediate Pages */}
                      {!isLastPage && (
                        <tr className="border-t-2 border-slate-300 font-semibold bg-slate-50/80 text-xs">
                          <td colSpan={7} className="py-2 px-3 text-right italic text-slate-700">
                            Total Carried Over to Page {pageNumber + 1} &rarr;
                          </td>
                          <td className="py-2 px-2 text-right font-mono font-bold text-slate-900 whitespace-nowrap">
                            {carriedOverSubtotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                          </td>
                          <td colSpan={2} className="py-2"></td>
                        </tr>
                      )}

                      {/* Filler empty rows if only 1 page with <= 4 items to keep elegant height */}
                      {isFirstPage && isLastPage && pageItems.length <= 4 && (
                        Array.from({ length: 4 - pageItems.length }).map((_, fIdx) => (
                          <tr key={`filler-${fIdx}`} className="h-8 border-none pointer-events-none">
                            <td colSpan={10}>&nbsp;</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* ── BOTTOM TOTALS & SUMMARY BLOCK (ONLY ON FINAL PAGE) ── */}
              {isLastPage ? (
                <div className="pt-4 border-t border-slate-200 mt-auto">
                  
                  {/* Two Column Layout: Left Details / Right Calculations */}
                  <div className="grid grid-cols-12 gap-6 items-start">
                    
                    {/* Left 7 Columns: Words, Bank Details, UPI QR, Notes & Terms */}
                    <div className="col-span-7 space-y-3">
                      
                      {/* Amount in words */}
                      {showAmountInWords && (
                        <div className="bg-slate-50/70 border border-slate-200/80 rounded-lg p-2.5 text-xs">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-0.5">
                            Amount Chargeable (in words)
                          </span>
                          <p className="font-semibold text-slate-800 italic leading-snug">
                            {numberToWords(finalGrandTotal)}
                          </p>
                        </div>
                      )}

                      {/* Bank Details & UPI QR */}
                      {(showBankDetails || showUpiQr) && (company?.bank_name || upiPayUrl) && (
                        <div className="grid grid-cols-12 gap-3 bg-slate-50/60 border border-slate-200/80 rounded-lg p-2.5 text-xs">
                          {showBankDetails && company?.bank_name && (
                            <div className={showUpiQr && upiPayUrl ? "col-span-8 space-y-0.5 text-[11px]" : "col-span-12 space-y-0.5 text-[11px]"}>
                              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
                                Bank Payment Details
                              </span>
                              <div>Bank: <strong className="text-slate-800 font-semibold">{company.bank_name}</strong></div>
                              <div>A/C No: <strong className="font-mono text-slate-900 font-bold">{company.bank_account_number || company.account_number}</strong></div>
                              <div>IFSC: <strong className="font-mono text-slate-800 font-semibold">{company.bank_ifsc || company.ifsc}</strong></div>
                              {company.bank_branch && <div>Branch: {company.bank_branch}</div>}
                            </div>
                          )}

                          {showUpiQr && upiPayUrl && (
                            <div className={showBankDetails && company?.bank_name ? "col-span-4 flex flex-col items-center justify-center pl-2 border-l border-slate-200" : "col-span-12 flex flex-col items-center justify-center"}>
                              <div className="p-1 bg-white border border-slate-200 rounded">
                                <QRCode value={upiPayUrl} size={58} />
                              </div>
                              <span className="text-[9px] font-bold text-slate-500 mt-1 uppercase tracking-wide">
                                Scan & Pay UPI
                              </span>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Terms & Conditions */}
                      {showTerms && termsText && (
                        <div className="text-[10.5px] text-slate-500 leading-snug space-y-0.5">
                          <span className="font-bold text-slate-600 uppercase tracking-wider text-[10px] block">
                            Terms & Conditions
                          </span>
                          <p className="whitespace-pre-line text-slate-600">
                            {termsText}
                          </p>
                        </div>
                      )}

                      {/* Customer Notes */}
                      {customerNotes && (
                        <div className="text-[10.5px] text-slate-500 leading-snug">
                          <span className="font-bold text-slate-600 uppercase tracking-wider text-[10px] block">
                            Remarks / Notes:
                          </span>
                          <p className="italic text-slate-600">{customerNotes}</p>
                        </div>
                      )}
                    </div>

                    {/* Right 5 Columns: Subtotals Breakdown & Highlighted Grand Total */}
                    <div className="col-span-5 space-y-2">
                      <div className="bg-slate-50/70 border border-slate-200/80 rounded-lg p-3 text-xs space-y-1.5">
                        
                        <div className="flex justify-between items-center text-slate-600">
                          <span>Taxable Amount</span>
                          <span className="font-mono font-semibold text-slate-900">
                            {subtotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                          </span>
                        </div>

                        {!isInterState ? (
                          <>
                            <div className="flex justify-between items-center text-slate-600">
                              <span>Central GST (CGST)</span>
                              <span className="font-mono font-medium text-slate-800">
                                {totalCgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                              </span>
                            </div>
                            <div className="flex justify-between items-center text-slate-600">
                              <span>State GST (SGST)</span>
                              <span className="font-mono font-medium text-slate-800">
                                {totalSgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                              </span>
                            </div>
                          </>
                        ) : (
                          <div className="flex justify-between items-center text-slate-600">
                            <span>Integrated GST (IGST)</span>
                            <span className="font-mono font-medium text-slate-800">
                              {totalIgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                            </span>
                          </div>
                        )}

                        {cartageAmount > 0 && (
                          <div className="flex justify-between items-center text-slate-600">
                            <span>Cartage / Delivery</span>
                            <span className="font-mono font-medium text-slate-800">
                              {cartageAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                            </span>
                          </div>
                        )}

                        {Math.abs(roundOff) >= 0.005 && (
                          <div className="flex justify-between items-center text-slate-500 text-[11px]">
                            <span>Round Off</span>
                            <span className="font-mono">
                              {roundOff > 0 ? `+${roundOff.toFixed(2)}` : roundOff.toFixed(2)}
                            </span>
                          </div>
                        )}

                        {/* Grand Total Pill */}
                        <div 
                          className="flex justify-between items-center pt-2.5 pb-1 border-t border-slate-300 font-bold"
                          style={{ color: accentColor }}
                        >
                          <span className="text-sm font-extrabold uppercase tracking-wide">Grand Total</span>
                          <span className="text-base font-mono font-black">
                            {formatIndianCurrency(finalGrandTotal)}
                          </span>
                        </div>
                      </div>

                      {/* Small HSN Summary Table (if enabled) */}
                      {showHsnSummary && hsnSummary.length > 0 && (
                        <div className="border border-slate-200/80 rounded-lg overflow-hidden text-[10px]">
                          <table className="w-full text-right border-collapse">
                            <thead>
                              <tr className="bg-slate-100/70 text-slate-600 font-bold border-b border-slate-200">
                                <th className="p-1 text-left">HSN</th>
                                <th className="p-1">Taxable</th>
                                <th className="p-1">Tax</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 text-slate-700">
                              {hsnSummary.map((hsnRow, hIdx) => (
                                <tr key={`hsn-${hIdx}`}>
                                  <td className="p-1 text-left font-mono">{hsnRow.hsn_code} ({hsnRow.gst_rate}%)</td>
                                  <td className="p-1 font-mono">{hsnRow.taxable_amount.toFixed(2)}</td>
                                  <td className="p-1 font-mono font-semibold">{hsnRow.total_tax.toFixed(2)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* ── SIGNATURES BLOCK ── */}
                  <div className="grid grid-cols-2 gap-8 mt-5 pt-4 border-t border-slate-200 text-xs">
                    
                    {/* Left: Customer Acceptance */}
                    <div className="flex flex-col justify-between h-24 border border-dashed border-slate-300 rounded-lg p-2.5">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Customer Acceptance / Seal & Signature
                      </span>
                      <div className="flex justify-between items-end text-[10px] text-slate-400 pt-2 border-t border-slate-200/60">
                        <span>Authorized Signatory</span>
                        <span>Date: ____________</span>
                      </div>
                    </div>

                    {/* Right: Seller Authorized Signatory */}
                    <div className="flex flex-col justify-between h-24 border border-slate-200/80 rounded-lg p-2.5 bg-slate-50/40 text-right">
                      <span className="text-[10.5px] font-bold text-slate-700">
                        For {company?.legal_name || company?.name || 'SriLekh Merchant'}
                      </span>
                      
                      <div className="flex items-center justify-end gap-3 my-auto">
                        {stampSrc && (
                          <img
                            crossOrigin="anonymous"
                            src={stampSrc}
                            alt="Official Stamp"
                            className="h-10 max-w-[80px] object-contain opacity-80"
                          />
                        )}
                        {signatureSrc ? (
                          <img
                            crossOrigin="anonymous"
                            src={signatureSrc}
                            alt="Authorized Signature"
                            className="h-10 max-w-[120px] object-contain"
                          />
                        ) : (
                          <div className="h-12" />
                        )}
                      </div>

                      <div className="text-[10px] font-bold text-slate-600 border-t border-slate-200/60 pt-1">
                        Authorised Signatory
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                /* Tally Intermediate Page Continuation Banner */
                <div className="pt-3 pb-1 border-t-2 border-slate-300 flex items-center justify-between text-xs font-semibold text-slate-600 bg-slate-50/60 px-3 rounded-lg mt-auto">
                  <span className="italic text-slate-700">
                    Document continued on Page {pageNumber + 1} of {totalPages}...
                  </span>
                  <span className="text-[11px] text-slate-500">
                    (Commercial Summary, Bank Details &amp; Signatures on Page {totalPages})
                  </span>
                </div>
              )}
            </div>

            {/* ═══════════════════════════════════════════════════════════════════ */}
            {/* FOOTER: OPTIONAL PROMOTIONAL STRIP & PAGE NUMBER STRIP            */}
            {/* ═══════════════════════════════════════════════════════════════════ */}
            <div className="relative z-10 pt-3 border-t border-slate-200/80 mt-3 text-slate-500">
              
              {/* Promotional Strip (if configured) */}
              {showPromoFooter && (
                <div className="pb-2 mb-2 border-b border-slate-200/60 flex items-center justify-between gap-4 text-[10px]">
                  <div className="flex-1 space-y-0.5">
                    {branding.promo_tagline && (
                      <p className="font-bold text-slate-800 uppercase tracking-wider text-[9.5px]">
                        {branding.promo_tagline}
                      </p>
                    )}
                    {branding.promo_message && (
                      <p className="italic text-slate-600 text-[10px] line-clamp-1">
                        &ldquo;{branding.promo_message}&rdquo;
                      </p>
                    )}
                    <div className="flex flex-wrap items-center gap-x-3 text-[9.5px] text-slate-500">
                      {branding.promo_website && <span>🌐 {branding.promo_website}</span>}
                      {branding.promo_social && <span>🔗 {branding.promo_social}</span>}
                      {branding.promo_support_phone && <span>📞 {branding.promo_support_phone}</span>}
                      {branding.promo_support_email && <span>✉️ {branding.promo_support_email}</span>}
                    </div>
                  </div>
                  {branding.promo_qr_url && (
                    <div className="shrink-0 flex items-center gap-1.5 p-1 bg-white border border-slate-200 rounded">
                      <QRCode value={branding.promo_qr_url} size={28} />
                      <span className="text-[8px] font-bold text-slate-500 uppercase tracking-tighter">
                        PROMO
                      </span>
                    </div>
                  )}
                </div>
              )}

              {/* Standard Page Footer */}
              <div className="flex justify-between items-center text-[10px] text-slate-400 font-medium">
                <div>
                  <span className="font-mono font-semibold text-slate-500">{doc?.proforma_number || 'PROFORMA'}</span>
                  <span className="mx-1.5">•</span>
                  <span>{legalNote}</span>
                </div>
                <div className="font-semibold text-slate-600">
                  Page {pageNumber} of {totalPages}
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
