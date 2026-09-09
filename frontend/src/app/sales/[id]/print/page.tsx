"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useParams, useRouter } from 'next/navigation';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import QRCode from 'react-qr-code';

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

  // If the invoice was saved with unrounded amount (or round off was not applied at creation)
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

    return (
    <div className="bg-white text-black min-h-screen">
      <style jsx global>{`
        @page {
          size: A4 portrait;
          margin: 10mm;
        }
        @media print {
          html, body {
            width: 210mm !important;
            height: 297mm !important;
            margin: 0 !important;
            padding: 0 !important;
            background: white !important;
            overflow: hidden !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
          }
          .print\\:hidden {
            display: none !important;
          }
          .print-sheet-wrapper {
            padding: 0 !important;
            margin: 0 !important;
            width: 100% !important;
            height: 100% !important;
            box-shadow: none !important;
            border: none !important;
          }
          .print-sheet {
            width: 190mm !important;
            height: 277mm !important;
            min-height: 277mm !important;
            max-height: 277mm !important;
            padding: 0 !important;
            margin: 0 !important;
            box-shadow: none !important;
            box-sizing: border-box !important;
          }
        }
      `}</style>

      {/* Print Button (Hidden on Print) */}
      <div className="print:hidden p-3 sm:p-4 bg-gray-100 border-b border-gray-300 flex justify-between items-center gap-2">
         <button onClick={() => router.back()} className="text-gray-600 hover:text-gray-900 font-medium text-xs sm:text-sm cursor-pointer">&larr; Back</button>
         <button onClick={() => window.print()} className="bg-blue-600 hover:bg-blue-700 text-white px-4 sm:px-6 py-2 rounded shadow font-semibold text-xs sm:text-sm cursor-pointer transition-colors">
           Print Invoice (A4)
         </button>
      </div>

      {/* A4 Sheet Container Wrapper */}
      <div className="print-sheet-wrapper w-full overflow-x-auto p-2 sm:p-8 flex justify-start sm:justify-center">
        <div className="print-sheet w-[210mm] min-w-[210mm] min-h-[297mm] bg-white p-8 pb-12 shadow-[0_0_10px_rgba(0,0,0,0.1)] print:shadow-none print:p-0 flex flex-col">
        
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
                              <tr><td className="w-32">GR/RR No.</td><td>: </td></tr>
                              <tr><td>Transport</td><td>: </td></tr>
                              <tr><td>Vehicle No.</td><td>: </td></tr>
                              <tr><td>E-Way Bill No.</td><td>: </td></tr>
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
                          {/* Filler Row expanding down to bottom of items table */}
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
                      <div className="h-5"></div> {/* Spacer aligning with subtotal */}
                      
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

            {/* Bottom Footer Section (always pinned firmly at bottom border with full height borders) */}
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
                    {/* Receiver's Signature (Top Row) */}
                    <div className="h-12 p-2 border-b-2 border-black flex items-start">
                        <span className="text-[11px] font-bold">Receiver's Signature :</span>
                    </div>
                    {/* Proprietor Signature (Bottom Row) */}
                    <div className="flex-1 p-2 relative flex flex-col justify-between items-end">
                        <div className="font-bold text-sm text-right mt-1">for {invoice.company.name}</div>
                        
                        <div className="flex justify-end w-full my-auto">
                            {invoice.company?.proprietor_signature && (
                                <img 
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
    </div>
  );
}
