"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import { useShortcuts } from '@/context/ShortcutContext';

export default function SalesPage() {
  const router = useRouter();
  const { workingDate, registerSaveHandler, registerAltCCallback } = useShortcuts();
  const [companyId, setCompanyId] = useState('');
  const [company, setCompany] = useState<any>(null);
  const [ledgers, setLedgers] = useState<any[]>([]);
  
  const [partyLedgerId, setPartyLedgerId] = useState('');
  const [salesLedgerId, setSalesLedgerId] = useState('');
  const [cgstLedgerId, setCgstLedgerId] = useState('');
  const [sgstLedgerId, setSgstLedgerId] = useState('');
  const [igstLedgerId, setIgstLedgerId] = useState('');
  
  const [enableLedgerMapping, setEnableLedgerMapping] = useState(false);
  const [enableManualInvoice, setEnableManualInvoice] = useState(false);
  const [invoiceNumber, setInvoiceNumber] = useState('');
  const [invoiceDate, setInvoiceDate] = useState(workingDate);
  const [companyStateCode, setCompanyStateCode] = useState('');
  
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  
  const [categories, setCategories] = useState<any[]>([]);
  const [groupedItems, setGroupedItems] = useState([
    { category_id: '', hsn_code: '', gst_rate: 18, items: [ { product_name: '', quantity: 1, rate: 0, discount_percent: 0 } ] }
  ]);

  useEffect(() => {
    if (workingDate) {
      setInvoiceDate(workingDate);
    }
  }, [workingDate]);

  useEffect(() => {
    registerAltCCallback((newEntity: any) => {
      if (newEntity?.group_name || newEntity?.ledger_type) {
        setLedgers((prev) => [...prev, newEntity]);
        setPartyLedgerId(newEntity.id);
      }
    });
  }, [registerAltCCallback]);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login');
      return;
    }
    fetchBaseData();
  }, [router]);

  const fetchBaseData = async () => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const comp = compRes.data.data[0];
      const cId = comp?.id;
      if (!cId) return;
      setCompany(comp);
      setCompanyId(cId);
      setCompanyStateCode(comp.state_code || '');
      
      const isMappingEnabled = comp.settings?.enable_ledger_mapping || false;
      setEnableLedgerMapping(isMappingEnabled);
      setEnableManualInvoice(comp.settings?.enable_manual_invoice_number || false);

      const ledgersRes = await axios.get(`${API_BASE_URL}/api/v1/ledgers/${cId}/`, { headers });
      const ledgerList = ledgersRes.data.data || [];
      setLedgers(ledgerList);
      
      const catsRes = await axios.get(`${API_BASE_URL}/api/v1/inventory/categories/${cId}/`, { headers });
      setCategories(catsRes.data.data || []);
      
      const party = ledgerList.find((l:any) => l.name.includes('Customer') || l.group.includes('Debtors'));
      
      // Default to generic 'Sales Account' if mapping is disabled
      const genericSales = ledgerList.find((l:any) => l.name === 'Sales Account' || l.name === 'Local Sales') || ledgerList.find((l:any) => l.name.toLowerCase().includes('sales'));
      const sales = isMappingEnabled 
          ? ledgerList.find((l:any) => l.name.toLowerCase().includes('sales')) 
          : genericSales;
          
      const cgst = ledgerList.find((l:any) => l.name === 'CGST');
      const sgst = ledgerList.find((l:any) => l.name === 'SGST');
      const igst = ledgerList.find((l:any) => l.name === 'IGST');
      
      if (party) setPartyLedgerId(party.id);
      if (sales) setSalesLedgerId(sales.id);
      else if (genericSales) setSalesLedgerId(genericSales.id);
      if (cgst) setCgstLedgerId(cgst.id);
      if (sgst) setSgstLedgerId(sgst.id);
      if (igst) setIgstLedgerId(igst.id);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!partyLedgerId || !salesLedgerId) return alert("Please select Party and Sales ledgers!");
    
    // Flatten grouped items for payload
    const flatItems: any[] = [];
    for (let i=0; i<groupedItems.length; i++) {
        const group = groupedItems[i];
        if (!group.category_id) return alert(`Category Group ${i+1} is missing a category selection!`);
        for (let j=0; j<group.items.length; j++) {
            const item = group.items[j];
            if (!item.product_name) return alert(`Category Group ${i+1}, Row ${j+1} is missing a product name!`);
            if (item.quantity <= 0) return alert(`Category Group ${i+1}, Row ${j+1} must have a quantity > 0!`);
            flatItems.push({
                ...item,
                category_id: group.category_id,
                hsn_code: group.hsn_code,
                gst_rate: group.gst_rate
            });
        }
    }
    
    setSaving(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      
      const payload = {
        company_id: companyId,
        party_ledger_id: partyLedgerId,
        sales_ledger_id: salesLedgerId,
        cgst_ledger_id: cgstLedgerId,
        sgst_ledger_id: sgstLedgerId,
        igst_ledger_id: igstLedgerId,
        voucher_number: enableManualInvoice ? invoiceNumber : undefined,
        voucher_date: invoiceDate,
        items: flatItems,
        post_immediately: true
      };
      
      const res = await axios.post(`${API_BASE_URL}/api/v1/accounting/sales-invoice/`, payload, { headers });
      alert("Sales Invoice generated successfully! Voucher Number: " + res.data.voucher_number);
      router.push('/sales');
    } catch (err: any) {
      console.error(err);
      alert("Failed to save: " + (err.response?.data?.error || err.message));
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    return registerSaveHandler(handleSave);
  }, [registerSaveHandler, handleSave]);

  const updateGroup = (gIndex: number, field: string, value: any) => {
    const newGroups = [...groupedItems];
    (newGroups[gIndex] as any)[field] = value;
    if (field === 'category_id') {
      const cat = categories.find(c => c.id === value);
      if (cat) {
        newGroups[gIndex].hsn_code = cat.hsn_code;
        newGroups[gIndex].gst_rate = Number(cat.gst_rate);
      }
    }
    setGroupedItems(newGroups);
  };

  const updateItem = (gIndex: number, iIndex: number, field: string, value: any) => {
    const newGroups = [...groupedItems];
    (newGroups[gIndex].items[iIndex] as any)[field] = value;
    setGroupedItems(newGroups);
  };

  const addRow = (gIndex: number) => {
    const newGroups = [...groupedItems];
    newGroups[gIndex].items.push({ product_name: '', quantity: 1, rate: 0, discount_percent: 0 });
    setGroupedItems(newGroups);
  };

  const removeRow = (gIndex: number, iIndex: number) => {
    const newGroups = [...groupedItems];
    if (newGroups[gIndex].items.length === 1) return;
    newGroups[gIndex].items = newGroups[gIndex].items.filter((_, i) => i !== iIndex);
    setGroupedItems(newGroups);
  };

  const addCategoryGroup = () => {
    setGroupedItems([...groupedItems, { category_id: '', hsn_code: '', gst_rate: 18, items: [ { product_name: '', quantity: 1, rate: 0, discount_percent: 0 } ] }]);
  };
  
  const removeCategoryGroup = (gIndex: number) => {
    if (groupedItems.length === 1) return;
    setGroupedItems(groupedItems.filter((_, i) => i !== gIndex));
  };

  // Flatten for calculations
  const allItems = groupedItems.flatMap(g => g.items.map(i => ({...i, gst_rate: g.gst_rate})));

  // Calculate Subtotals
  const grossTotal = allItems.reduce((sum, item) => sum + (Number(item.quantity) * Number(item.rate)), 0);
  const totalTax = allItems.reduce((sum, item) => {
      const gross = Number(item.quantity) * Number(item.rate);
      const discount = gross * (Number(item.discount_percent)/100);
      const taxable = gross - discount;
      return sum + (taxable * (Number(item.gst_rate)/100));
  }, 0);
  const grandTotal = allItems.reduce((sum, item) => {
    const gross = Number(item.quantity) * Number(item.rate);
    const discount = gross * (Number(item.discount_percent)/100);
    const taxable = gross - discount;
    return sum + taxable + (taxable * (Number(item.gst_rate)/100));
  }, 0);

  const selectedParty = ledgers.find(l => l.id === partyLedgerId);
  const isInterState = Boolean(selectedParty?.state_code && companyStateCode && selectedParty.state_code !== companyStateCode);

  if (loading) return <DashboardLayout><div className="flex items-center justify-center h-full text-gray-500">Loading invoice form...</div></DashboardLayout>;

  let missingFields = [];
  if (company) {
    if (!company.proprietor_name) missingFields.push("Proprietor Name");
    if (!company.proprietor_phone) missingFields.push("Proprietor Phone");
    if (!company.proprietor_signature) missingFields.push("Digital Signature");
  }

  if (missingFields.length > 0) {
    return (
      <DashboardLayout>
        <div className="max-w-2xl mx-auto mt-20 p-8 bg-card border border-border rounded-xl shadow-lg text-center">
          <div className="w-16 h-16 bg-amber-500/10 text-amber-500 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">Proprietor Details Required</h2>
          <p className="text-gray-400 mb-4">
            You must complete your firm's profile before you can generate invoices. The following details are missing:
          </p>
          <ul className="text-amber-500 font-medium mb-8 flex flex-col items-center gap-1">
            {missingFields.map(f => <li key={f}>• {f}</li>)}
          </ul>
          <Link href="/settings" className="inline-block bg-blue-600 hover:bg-blue-700 text-white px-8 py-3 rounded-lg font-bold shadow-lg transition-colors">
            Go to Profile Settings
          </Link>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="max-w-6xl mx-auto space-y-6 pb-20">
        
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border pb-4">
          <div className="flex items-center gap-4">
            <Link href="/sales" className="text-gray-400 hover:text-white transition-colors">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
            </Link>
            <h1 className="text-3xl font-bold">New Sales Invoice</h1>
          </div>
          <button onClick={handleSave} disabled={saving} className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2.5 rounded-lg shadow-lg font-medium transition-colors disabled:opacity-50 flex items-center gap-2">
            {saving ? 'Posting...' : 'Post Invoice'}
          </button>
        </div>
        
        {/* Billing Details Card */}
        <div className="bg-card border border-border rounded-xl shadow-sm p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-gray-200">Billing Details</h2>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6 pb-6 border-b border-zinc-800">
            {enableManualInvoice && (
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1.5">Invoice Number</label>
                <input type="text" value={invoiceNumber} onChange={e => setInvoiceNumber(e.target.value)} placeholder="e.g. INV-001" className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all" />
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">Invoice Date</label>
              <input type="date" value={invoiceDate} onChange={e => setInvoiceDate(e.target.value)} className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all" />
            </div>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <div className="flex justify-between items-center mb-1.5">
                <label className="block text-sm font-medium text-gray-400">Party (Customer)</label>
                <Link href="/sales/customers/new" className="text-xs text-blue-500 hover:text-blue-400">+ Add New Customer</Link>
              </div>
              <select value={partyLedgerId} onChange={e => setPartyLedgerId(e.target.value)} className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all">
                <option value="">-- Select Customer --</option>
                {ledgers.filter(l => l.group.includes('Debtor') || l.group.includes('Creditor')).map(l => (
                  <option key={l.id} value={l.id}>{l.name}</option>
                ))}
              </select>
            </div>
            {enableLedgerMapping && (
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1.5">Sales Ledger</label>
                <select value={salesLedgerId} onChange={e => setSalesLedgerId(e.target.value)} className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all">
                  <option value="">-- Select Sales Ledger --</option>
                  {ledgers.filter(l => l.group.includes('Income') || l.name.includes('Sales')).map(l => (
                    <option key={l.id} value={l.id}>{l.name}</option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </div>

        {/* Line Items Card */}
        <div className="bg-card border border-border rounded-xl shadow-sm overflow-hidden">
            <div className="p-6 border-b border-border flex justify-between items-center">
                <h2 className="text-lg font-semibold text-gray-200">Line Items by Category</h2>
                <span className="text-xs text-blue-400 bg-blue-400/10 px-2 py-1 rounded border border-blue-400/20">Auto-Creates & Inherits Tax</span>
            </div>
            
            <div className="p-2 space-y-6">
                {groupedItems.map((group, gIndex) => (
                    <div key={gIndex} className="border border-zinc-800 rounded-lg overflow-hidden bg-zinc-900/30">
                        <div className="p-4 bg-zinc-900/80 border-b border-zinc-800 flex items-center justify-between">
                            <div className="flex-1 max-w-md flex items-center gap-3">
                                <label className="text-sm font-medium text-gray-400 whitespace-nowrap">Category:</label>
                                <select 
                                    value={group.category_id} 
                                    onChange={(e) => updateGroup(gIndex, 'category_id', e.target.value)}
                                    className="w-full bg-zinc-800 border border-zinc-700 text-white p-2 rounded focus:ring-2 focus:ring-blue-500 outline-none text-sm"
                                >
                                    <option value="">-- Select Category --</option>
                                    {categories.map(c => (
                                        <option key={c.id} value={c.id}>{c.name}</option>
                                    ))}
                                </select>
                            </div>
                            <div className="flex items-center gap-4 text-sm text-gray-500">
                                <span>Default HSN: <strong className="text-gray-300">{group.hsn_code || 'N/A'}</strong></span>
                                {isInterState ? (
                                    <span className="bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded border border-blue-500/20 text-xs font-medium">
                                        IGST: {group.gst_rate}%
                                    </span>
                                ) : (
                                    <div className="flex gap-2">
                                        <span className="bg-zinc-800 text-gray-300 px-2 py-0.5 rounded border border-zinc-700 text-xs font-medium">CGST: {(Number(group.gst_rate)/2).toFixed(1)}%</span>
                                        <span className="bg-zinc-800 text-gray-300 px-2 py-0.5 rounded border border-zinc-700 text-xs font-medium">SGST: {(Number(group.gst_rate)/2).toFixed(1)}%</span>
                                    </div>
                                )}
                                <button onClick={() => removeCategoryGroup(gIndex)} className="text-red-500 hover:text-red-400 ml-4 p-1">
                                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                                </button>
                            </div>
                        </div>
                        
                        <div className="overflow-x-auto">
                            <table className="w-full text-left border-collapse">
                                <thead className="bg-zinc-900/40 text-gray-400 text-xs uppercase tracking-wider">
                                    <tr>
                                        <th className="p-3 font-medium">Product Name</th>
                                        <th className="p-3 font-medium w-24">Qty</th>
                                        <th className="p-3 font-medium w-32">Rate (₹)</th>
                                        <th className="p-3 font-medium w-24">Disc %</th>
                                        <th className="p-3 font-medium w-32 text-right">Amount</th>
                                        <th className="p-3 w-12"></th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-zinc-800/50">
                                    {group.items.map((item, iIndex) => {
                                        const gross = Number(item.quantity) * Number(item.rate);
                                        const discount = gross * (Number(item.discount_percent)/100);
                                        const taxable = gross - discount;
                                        
                                        return (
                                        <tr key={iIndex} className="hover:bg-zinc-800/40 transition-colors">
                                            <td className="p-2">
                                                <input type="text" placeholder="e.g. Item Name" value={item.product_name} onChange={e => updateItem(gIndex, iIndex, 'product_name', e.target.value)} className="w-full bg-transparent border border-transparent hover:border-zinc-700 focus:border-blue-500 rounded p-1.5 outline-none text-white transition-all text-sm" />
                                            </td>
                                            <td className="p-2">
                                                <input type="number" min="1" value={item.quantity} onChange={e => updateItem(gIndex, iIndex, 'quantity', e.target.value)} className="w-full bg-transparent border border-transparent hover:border-zinc-700 focus:border-blue-500 rounded p-1.5 outline-none text-white transition-all text-center text-sm" />
                                            </td>
                                            <td className="p-2">
                                                <input type="number" min="0" value={item.rate} onChange={e => updateItem(gIndex, iIndex, 'rate', e.target.value)} className="w-full bg-transparent border border-transparent hover:border-zinc-700 focus:border-blue-500 rounded p-1.5 outline-none text-white transition-all text-right text-sm" />
                                            </td>
                                            <td className="p-2">
                                                <input type="number" min="0" max="100" value={item.discount_percent} onChange={e => updateItem(gIndex, iIndex, 'discount_percent', e.target.value)} className="w-full bg-transparent border border-transparent hover:border-zinc-700 focus:border-blue-500 rounded p-1.5 outline-none text-white transition-all text-center text-sm" />
                                            </td>
                                            <td className="p-2 text-right font-medium text-gray-200">
                                                ₹{taxable.toFixed(2)}
                                            </td>
                                            <td className="p-2 text-center">
                                                <button onClick={() => removeRow(gIndex, iIndex)} className="text-zinc-600 hover:text-red-400 transition-colors p-1">
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                                                </button>
                                            </td>
                                        </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                        <div className="p-3 bg-zinc-900/30 border-t border-zinc-800">
                            <button onClick={() => addRow(gIndex)} className="text-sm text-blue-500 hover:text-blue-400 font-medium flex items-center gap-1">
                                + Add item in {categories.find(c=>c.id===group.category_id)?.name || 'this category'}
                            </button>
                        </div>
                    </div>
                ))}
            </div>
            
            <div className="p-4 border-t border-border bg-zinc-900/20">
                <button onClick={addCategoryGroup} className="text-sm text-white bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 px-4 py-2 rounded shadow transition-colors font-medium">
                    + Add Another Category Block
                </button>
            </div>
        </div>

        {/* Totals Section */}
        <div className="flex justify-end">
            <div className="w-full max-w-md bg-card border border-border rounded-xl shadow-sm p-6 space-y-3">
                <div className="flex justify-between text-gray-400">
                    <span>Gross Total</span>
                    <span>₹{grossTotal.toFixed(2)}</span>
                </div>
                {isInterState ? (
                    <div className="flex justify-between text-blue-400">
                        <span>IGST</span>
                        <span>₹{totalTax.toFixed(2)}</span>
                    </div>
                ) : (
                    <>
                        <div className="flex justify-between text-gray-400">
                            <span>CGST</span>
                            <span>₹{(totalTax / 2).toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between text-gray-400">
                            <span>SGST</span>
                            <span>₹{(totalTax / 2).toFixed(2)}</span>
                        </div>
                    </>
                )}
                <div className="border-t border-zinc-700 pt-3 flex justify-between text-xl font-bold text-white">
                    <span>Grand Total</span>
                    <span>₹{grandTotal.toFixed(2)}</span>
                </div>
            </div>
        </div>

      </div>
    </DashboardLayout>
  );
}
