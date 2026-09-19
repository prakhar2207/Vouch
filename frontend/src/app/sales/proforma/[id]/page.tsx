"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import { useToast } from '@/context/ToastContext';
import { 
  ArrowLeft, 
  Printer, 
  Sparkles, 
  CheckCircle2, 
  Download, 
  Loader2, 
  ExternalLink,
  Calendar,
  Building2,
  FileText,
  Clock,
  Send
} from 'lucide-react';

function numberToWords(numAmount: number): string {
  const a = ['', 'One ', 'Two ', 'Three ', 'Four ', 'Five ', 'Six ', 'Seven ', 'Eight ', 'Nine ', 'Ten ', 'Eleven ', 'Twelve ', 'Thirteen ', 'Fourteen ', 'Fifteen ', 'Sixteen ', 'Seventeen ', 'Eighteen ', 'Nineteen '];
  const b = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety'];
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

  if (loading) {
    return (
      <DashboardLayout>
        <div className="py-24 flex flex-col items-center justify-center gap-3">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Loading document preview...</p>
        </div>
      </DashboardLayout>
    );
  }

  if (!doc) {
    return (
      <DashboardLayout>
        <div className="py-24 text-center space-y-3">
          <h2 className="text-lg font-bold text-foreground">Document Not Found</h2>
          <p className="text-xs text-muted-foreground">The requested proforma invoice or quotation could not be located.</p>
          <Link href="/sales/proforma" className="px-4 py-2 bg-primary text-primary-foreground text-xs font-semibold rounded-xl inline-block">
            Back to List
          </Link>
        </div>
      </DashboardLayout>
    );
  }

  const isConverted = doc.status === 'CONVERTED';
  const isPI = doc.proforma_type === 'PROFORMA';
  const company = doc.company_details || {};

  return (
    <DashboardLayout>
      <div className="max-w-5xl mx-auto space-y-6 pb-20">
        {/* Action Header (Hidden in Print) */}
        <div className="print:hidden flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-border pb-4">
          <div className="flex items-center gap-3">
            <Link
              href="/sales/proforma"
              className="p-2 rounded-xl bg-card border border-border hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div>
              <div className="flex items-center gap-2">
                <span className={`px-2 py-0.5 rounded text-xs font-bold uppercase ${
                  isPI ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400' : 'bg-purple-500/10 text-purple-600 dark:text-purple-400'
                }`}>
                  {isPI ? 'Proforma Invoice' : 'Quotation'}
                </span>
                <h1 className="text-lg font-bold text-foreground font-mono">
                  {doc.proforma_number}
                </h1>
                <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold ${
                  isConverted 
                    ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                    : doc.status === 'ACCEPTED'
                    ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400'
                    : 'bg-muted text-muted-foreground'
                }`}>
                  {doc.status}
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Created on {doc.date} by {doc.created_by}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {/* Convert to GST Tax Invoice Button */}
            {!isConverted ? (
              <button
                type="button"
                onClick={handleConvert}
                disabled={converting}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
              >
                {converting ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Sparkles className="w-3.5 h-3.5 text-amber-300" />
                )}
                <span>Convert to GST Tax Invoice</span>
              </button>
            ) : (
              <Link
                href="/sales"
                className="px-4 py-2 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30 rounded-xl text-xs font-bold transition-colors flex items-center gap-1.5"
              >
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                <span>Converted: {doc.converted_voucher_number || 'INV'}</span>
                <ExternalLink className="w-3 h-3" />
              </Link>
            )}

            {/* Status updates */}
            {!isConverted && doc.status !== 'SENT' && (
              <button
                type="button"
                onClick={() => handleUpdateStatus('SENT')}
                disabled={updatingStatus}
                className="px-3 py-2 bg-card hover:bg-muted border border-border rounded-xl text-xs font-semibold text-foreground transition-colors cursor-pointer flex items-center gap-1"
              >
                <Send className="w-3.5 h-3.5" />
                <span>Mark Sent</span>
              </button>
            )}

            {!isConverted && doc.status !== 'ACCEPTED' && (
              <button
                type="button"
                onClick={() => handleUpdateStatus('ACCEPTED')}
                disabled={updatingStatus}
                className="px-3 py-2 bg-blue-500/10 text-blue-600 dark:text-blue-400 hover:bg-blue-500/20 border border-blue-500/30 rounded-xl text-xs font-bold transition-colors cursor-pointer flex items-center gap-1"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Mark Accepted</span>
              </button>
            )}

            {/* Print Button */}
            <button
              type="button"
              onClick={() => window.print()}
              className="px-3.5 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl text-xs font-bold transition-colors flex items-center gap-1.5 cursor-pointer shadow-xs"
            >
              <Printer className="w-4 h-4" />
              <span>Print / Download</span>
            </button>
          </div>
        </div>

        {/* Printable Document Container */}
        <div className="bg-white text-slate-900 border border-slate-200 rounded-2xl shadow-xl overflow-hidden print:border-none print:shadow-none print:rounded-none">
          {/* Official Top Notice Banner */}
          <div className="bg-slate-100 border-b border-slate-200 px-6 py-2 text-center text-[11px] font-bold uppercase tracking-wider text-slate-600">
            {isPI ? 'PROFORMA INVOICE' : 'COMMERCIAL QUOTATION / ESTIMATE'} — THIS IS NOT A GST TAX INVOICE
          </div>

          <div className="p-8 space-y-6">
            {/* Header: Seller Info & Document Meta */}
            <div className="flex flex-col sm:flex-row justify-between items-start gap-6 border-b border-slate-200 pb-6">
              <div>
                <h2 className="text-xl font-black text-slate-900 tracking-tight">
                  {company.name || 'Your Company Name'}
                </h2>
                {company.address && (
                  <p className="text-xs text-slate-600 mt-1 max-w-sm whitespace-pre-line">
                    {company.address}
                  </p>
                )}
                <div className="text-xs text-slate-700 mt-2 space-y-0.5 font-mono">
                  {company.gstin && <div>GSTIN: <strong>{company.gstin}</strong></div>}
                  {company.pan && <div>PAN: <strong>{company.pan}</strong></div>}
                  {company.phone && <div className="font-sans">Phone: {company.phone}</div>}
                  {company.email && <div className="font-sans">Email: {company.email}</div>}
                </div>
              </div>

              <div className="sm:text-right space-y-1 bg-slate-50 p-4 rounded-xl border border-slate-200 min-w-[240px]">
                <div className="text-xs font-bold uppercase tracking-wider text-slate-500">
                  {isPI ? 'Proforma Invoice' : 'Quotation'}
                </div>
                <div className="text-lg font-black font-mono text-slate-900">
                  {doc.proforma_number}
                </div>
                <div className="text-xs text-slate-600 pt-1 font-mono">
                  Date: <span className="font-semibold text-slate-900">{doc.date}</span>
                </div>
                {doc.valid_until && (
                  <div className="text-xs text-slate-600 font-mono">
                    Valid Until: <span className="font-semibold text-slate-900">{doc.valid_until}</span>
                  </div>
                )}
                <div className="pt-2">
                  <span className={`inline-block px-2.5 py-0.5 rounded text-[11px] font-bold ${
                    isConverted ? 'bg-emerald-100 text-emerald-800' : 'bg-blue-100 text-blue-800'
                  }`}>
                    {doc.status}
                  </span>
                </div>
              </div>
            </div>

            {/* Buyer Details */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 bg-slate-50/70 p-4 rounded-xl border border-slate-200">
              <div>
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block mb-1">
                  Quotation / Bill To:
                </span>
                <div className="font-bold text-sm text-slate-900">
                  {doc.party_name || doc.buyer_name || 'Valued Customer'}
                </div>
                {doc.buyer_address && (
                  <div className="text-xs text-slate-600 mt-1 whitespace-pre-line">
                    {doc.buyer_address}
                  </div>
                )}
                <div className="text-xs text-slate-700 mt-2 space-y-0.5 font-mono">
                  {doc.buyer_gstin && <div>GSTIN: <strong>{doc.buyer_gstin}</strong></div>}
                  {doc.buyer_state_code && <div>State Code: {doc.buyer_state_code}</div>}
                  {doc.buyer_phone && <div className="font-sans">Phone: {doc.buyer_phone}</div>}
                  {doc.buyer_email && <div className="font-sans">Email: {doc.buyer_email}</div>}
                </div>
              </div>

              <div>
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block mb-1">
                  Commercial Terms Summary:
                </span>
                <div className="text-xs text-slate-700 space-y-1">
                  <div>Document Type: <strong>{doc.proforma_type}</strong></div>
                  <div>Place of Supply: <strong>{doc.buyer_state_code ? `State Code ${doc.buyer_state_code}` : 'Intra-State'}</strong></div>
                  {doc.valid_until && <div>Quote Expiry: <strong>{doc.valid_until}</strong></div>}
                  {isConverted && doc.converted_voucher_number && (
                    <div className="text-emerald-700 font-semibold pt-1">
                      ✓ Converted to Tax Invoice: {doc.converted_voucher_number}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Items Table */}
            <div className="overflow-x-auto border border-slate-200 rounded-xl">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="bg-slate-100 border-b border-slate-200 text-slate-600 font-semibold text-[11px] uppercase tracking-wider">
                    <th className="py-2.5 px-3 w-10 text-center">#</th>
                    <th className="py-2.5 px-3">Item Description</th>
                    <th className="py-2.5 px-3 text-center">HSN/SAC</th>
                    <th className="py-2.5 px-3 text-right">Qty</th>
                    <th className="py-2.5 px-3 text-right">Rate (₹)</th>
                    <th className="py-2.5 px-3 text-right">Disc %</th>
                    <th className="py-2.5 px-3 text-right">Taxable (₹)</th>
                    <th className="py-2.5 px-3 text-center">GST</th>
                    <th className="py-2.5 px-3 text-right">Total (₹)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 font-mono">
                  {doc.items?.map((it: any, i: number) => (
                    <tr key={it.id || i} className="hover:bg-slate-50">
                      <td className="py-2.5 px-3 text-center text-slate-500">{i + 1}</td>
                      <td className="py-2.5 px-3 font-sans font-medium text-slate-900">
                        {it.item_name}
                      </td>
                      <td className="py-2.5 px-3 text-center text-slate-600">{it.hsn_code || '-'}</td>
                      <td className="py-2.5 px-3 text-right text-slate-900 font-semibold">
                        {it.quantity} {it.unit}
                      </td>
                      <td className="py-2.5 px-3 text-right text-slate-900">
                        {Number(it.rate).toFixed(2)}
                      </td>
                      <td className="py-2.5 px-3 text-right text-slate-600">
                        {it.discount_percent > 0 ? `${it.discount_percent}%` : '-'}
                      </td>
                      <td className="py-2.5 px-3 text-right text-slate-900 font-semibold">
                        {Number(it.taxable_amount).toFixed(2)}
                      </td>
                      <td className="py-2.5 px-3 text-center text-slate-600">
                        {it.gst_rate}%
                      </td>
                      <td className="py-2.5 px-3 text-right font-bold text-slate-900">
                        {Number(it.total_amount).toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Bottom Section: Notes & Totals */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-8 pt-2">
              {/* Left Side: Notes, Terms, Bank Details */}
              <div className="space-y-4 text-xs">
                {/* Amount in words */}
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
                  <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block mb-0.5">
                    Amount in Words:
                  </span>
                  <div className="font-semibold text-slate-800">
                    {numberToWords(doc.total_amount)}
                  </div>
                </div>

                {/* Bank Details */}
                {company.bank_details?.account_number && (
                  <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-1">
                    <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block mb-1">
                      Bank Details for Advance Payment:
                    </span>
                    <div className="font-mono space-y-0.5 text-slate-700">
                      <div>Bank: <strong>{company.bank_details.bank_name}</strong></div>
                      <div>A/C Number: <strong>{company.bank_details.account_number}</strong></div>
                      <div>IFSC: <strong>{company.bank_details.ifsc}</strong></div>
                      {company.bank_details.branch && <div>Branch: {company.bank_details.branch}</div>}
                    </div>
                  </div>
                )}

                {/* Terms & Conditions */}
                {doc.terms_and_conditions && (
                  <div className="space-y-1">
                    <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block">
                      Terms &amp; Conditions:
                    </span>
                    <p className="text-slate-600 whitespace-pre-line leading-relaxed text-[11px]">
                      {doc.terms_and_conditions}
                    </p>
                  </div>
                )}

                {/* Customer Notes */}
                {doc.customer_notes && (
                  <div className="space-y-1">
                    <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block">
                      Notes:
                    </span>
                    <p className="text-slate-600 whitespace-pre-line text-[11px]">
                      {doc.customer_notes}
                    </p>
                  </div>
                )}
              </div>

              {/* Right Side: Totals */}
              <div className="space-y-2 border border-slate-200 rounded-xl p-4 bg-slate-50 font-mono text-xs">
                <div className="flex justify-between py-1 border-b border-slate-200">
                  <span className="text-slate-600 font-sans">Taxable Value:</span>
                  <span className="font-semibold text-slate-900">
                    ₹{Number(doc.taxable_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </span>
                </div>

                {doc.cgst_amount > 0 && (
                  <div className="flex justify-between py-1 border-b border-slate-200">
                    <span className="text-slate-600 font-sans">CGST:</span>
                    <span className="font-semibold text-slate-900">
                      ₹{Number(doc.cgst_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                )}

                {doc.sgst_amount > 0 && (
                  <div className="flex justify-between py-1 border-b border-slate-200">
                    <span className="text-slate-600 font-sans">SGST / UTGST:</span>
                    <span className="font-semibold text-slate-900">
                      ₹{Number(doc.sgst_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                )}

                {doc.igst_amount > 0 && (
                  <div className="flex justify-between py-1 border-b border-slate-200">
                    <span className="text-slate-600 font-sans">IGST:</span>
                    <span className="font-semibold text-slate-900">
                      ₹{Number(doc.igst_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                )}

                {doc.cartage_amount > 0 && (
                  <div className="flex justify-between py-1 border-b border-slate-200">
                    <span className="text-slate-600 font-sans">Cartage / Freight:</span>
                    <span className="font-semibold text-slate-900">
                      ₹{Number(doc.cartage_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                )}

                {doc.round_off !== 0 && (
                  <div className="flex justify-between py-1 border-b border-slate-200 text-slate-500">
                    <span className="font-sans">Round Off:</span>
                    <span>₹{Number(doc.round_off).toFixed(2)}</span>
                  </div>
                )}

                <div className="flex justify-between pt-3 text-base font-black text-slate-900 border-t-2 border-slate-300">
                  <span className="font-sans">Total Payable:</span>
                  <span className="text-primary font-mono">
                    ₹{Number(doc.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </span>
                </div>
              </div>
            </div>

            {/* Signature Block */}
            <div className="flex justify-between items-end pt-12 text-xs border-t border-slate-200 text-slate-600">
              <div>
                <div className="font-semibold text-slate-800">Customer Acceptance Signature:</div>
                <div className="text-[11px] text-slate-500 mt-1">Sign &amp; date to approve quotation</div>
                <div className="mt-8 border-b border-slate-400 w-48"></div>
              </div>

              <div className="text-right">
                <div className="font-semibold text-slate-800">For {company.name || 'Seller'}:</div>
                <div className="mt-10 border-b border-slate-400 w-48 ml-auto"></div>
                <div className="text-[11px] text-slate-500 mt-1">Authorized Signatory</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
