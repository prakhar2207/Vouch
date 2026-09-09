"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import PurchaseOcrSplitView from '@/components/PurchaseOcrSplitView';
import { useShortcuts } from '@/context/ShortcutContext';
import { useToast } from '@/context/ToastContext';
import { queueOfflineVoucher } from '@/lib/sync/sync-worker';
import { offlineDb } from '@/lib/db/offlineDb';

export default function PurchasePage() {
  const router = useRouter();
  const { toast } = useToast();
  const { workingDate, registerSaveHandler, registerAltCCallback } = useShortcuts();
  const [activeTab, setActiveTab] = useState<'OCR' | 'MANUAL'>('OCR');
  const [companyId, setCompanyId] = useState('');
  const [ledgers, setLedgers] = useState<any[]>([]);
  
  const [partyLedgerId, setPartyLedgerId] = useState('');
  const [purchaseLedgerId, setPurchaseLedgerId] = useState('');
  const [cgstLedgerId, setCgstLedgerId] = useState('');
  const [sgstLedgerId, setSgstLedgerId] = useState('');
  const [igstLedgerId, setIgstLedgerId] = useState('');
  
  const [enableLedgerMapping, setEnableLedgerMapping] = useState(false);
  const [invoiceNumber, setInvoiceNumber] = useState('');
  const [invoiceDate, setInvoiceDate] = useState(workingDate);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [companyStateCode, setCompanyStateCode] = useState('');
  const [cartageAmount, setCartageAmount] = useState<number | string>('');
  
  const [categories, setCategories] = useState<any[]>([]);
  const [groupedItems, setGroupedItems] = useState([
    { category_id: '', hsn_code: '', gst_rate: 18, items: [ { product_name: '', brand: '', quantity: 1, rate: 0, discount_percent: 0 } ] }
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
      // First, attempt to load cached masters from offline IndexedDB
      try {
        const cachedComp = await offlineDb.masters.get('company');
        const cachedLedgers = await offlineDb.masters.get('ledgers');
        const cachedCats = await offlineDb.masters.get('categories');

        if (cachedComp?.data) {
          setCompanyId(cachedComp.data.id);
          setCompanyStateCode(cachedComp.data.state_code || '');
          setEnableLedgerMapping(cachedComp.data.settings?.enable_ledger_mapping || false);
        }
        if (cachedLedgers?.data?.length) {
          setLedgers(cachedLedgers.data);
          applyDefaultPurchaseLedgers(cachedLedgers.data, cachedComp?.data?.settings?.enable_ledger_mapping || false);
        }
        if (cachedCats?.data?.length) setCategories(cachedCats.data);
      } catch (cacheErr) {
        console.warn('Could not read from local offline cache', cacheErr);
      }

      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const comp = compRes.data.data[0];
      const cId = comp?.id;
      if (!cId) return;
      setCompanyId(cId);
      setCompanyStateCode(comp.state_code || '');
      
      const isMappingEnabled = comp.settings?.enable_ledger_mapping || false;
      setEnableLedgerMapping(isMappingEnabled);

      // Cache company
      offlineDb.masters.put({ key: 'company', data: comp, updatedAt: Date.now() }).catch(() => {});

      const ledgersRes = await axios.get(`${API_BASE_URL}/api/v1/ledgers/${cId}/`, { headers });
      const ledgerList = ledgersRes.data.data || [];
      setLedgers(ledgerList);
      
      const catsRes = await axios.get(`${API_BASE_URL}/api/v1/inventory/categories/${cId}/`, { headers });
      const catList = catsRes.data.data || [];
      setCategories(catList);

      offlineDb.masters.put({ key: 'ledgers', data: ledgerList, updatedAt: Date.now() }).catch(() => {});
      offlineDb.masters.put({ key: 'categories', data: catList, updatedAt: Date.now() }).catch(() => {});

      applyDefaultPurchaseLedgers(ledgerList, isMappingEnabled);
    } catch (err) {
      console.error('Network fetch failed, continuing with offline cache if available:', err);
    } finally {
      setLoading(false);
    }
  };

  const applyDefaultPurchaseLedgers = (ledgerList: any[], isMappingEnabled: boolean) => {
    const party = ledgerList.find((l:any) => l.name.includes('Supplier') || l.group.includes('Creditor'));
    const genericPurchase = ledgerList.find((l:any) => l.name === 'Purchase Account' || l.name === 'Local Purchases') || ledgerList.find((l:any) => l.name.toLowerCase().includes('purchase'));
    const purchase = isMappingEnabled 
        ? ledgerList.find((l:any) => l.name.toLowerCase().includes('purchase')) 
        : genericPurchase;
        
    const cgst = ledgerList.find((l:any) => l.name === 'CGST' || l.name === 'Input CGST' || l.name.toLowerCase().includes('cgst'));
    const sgst = ledgerList.find((l:any) => l.name === 'SGST' || l.name === 'Input SGST' || l.name.toLowerCase().includes('sgst'));
    const igst = ledgerList.find((l:any) => l.name === 'IGST' || l.name === 'Input IGST' || l.name.toLowerCase().includes('igst'));
    
    if (party) setPartyLedgerId(party.id);
    if (purchase) setPurchaseLedgerId(purchase.id);
    else if (genericPurchase) setPurchaseLedgerId(genericPurchase.id);
    if (cgst) setCgstLedgerId(cgst.id);
    if (sgst) setSgstLedgerId(sgst.id);
    if (igst) setIgstLedgerId(igst.id);
  };

  const handleSave = async () => {
    if (!partyLedgerId || !purchaseLedgerId) {
      toast.warning("Please select Party and Purchase ledgers!");
      return;
    }
    
    const flatItems: any[] = [];
    for (let i=0; i<groupedItems.length; i++) {
        const group = groupedItems[i];
        if (!group.category_id) {
          toast.warning(`Category Group ${i+1} is missing a category selection!`);
          return;
        }
        for (let j=0; j<group.items.length; j++) {
            const item = group.items[j];
            if (!item.product_name) {
              toast.warning(`Category Group ${i+1}, Row ${j+1} is missing a product name!`);
              return;
            }
            if (item.quantity <= 0) {
              toast.warning(`Category Group ${i+1}, Row ${j+1} must have a quantity > 0!`);
              return;
            }
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
      
      const payload: any = {
        company_id: companyId,
        party_ledger_id: partyLedgerId,
        voucher_number: invoiceNumber || undefined,
        voucher_date: invoiceDate,
        items: flatItems.map((it: any) => {
          const itemCopy = { ...it };
          if (!itemCopy.product_id) delete itemCopy.product_id;
          if (!itemCopy.category_id) delete itemCopy.category_id;
          return itemCopy;
        }),
        post_immediately: true
      };
      if (purchaseLedgerId) payload.purchase_ledger_id = purchaseLedgerId;
      if (cgstLedgerId) payload.input_cgst_ledger_id = cgstLedgerId;
      if (sgstLedgerId) payload.input_sgst_ledger_id = sgstLedgerId;
      if (igstLedgerId) payload.input_igst_ledger_id = igstLedgerId;
      if (cartageAmount && Number(cartageAmount) > 0) {
        payload.cartage_amount = Number(cartageAmount);
      }
      
      try {
        const res = await axios.post(`${API_BASE_URL}/api/v1/accounting/purchase-invoice/`, payload, { headers, timeout: 8000 });
        toast.success(`Purchase Invoice recorded!`, `Voucher: ${res.data.voucher_number}`);
        router.push('/purchases');
        router.refresh();
      } catch (postErr: any) {
        const isNetworkErr = !navigator.onLine || postErr.code === 'ERR_NETWORK' || !postErr.response;
        if (isNetworkErr) {
          const offlineRes = await queueOfflineVoucher('PURCHASE', payload, invoiceDate);
          toast.success(
            "⚡ Saved Offline to Local Database!",
            `Stored securely on device (${offlineRes.localId}). Will sync to Neon cloud automatically.`
          );
          router.push('/purchases');
          router.refresh();
        } else {
          throw postErr;
        }
      }
    } catch (err: any) {
      console.error(err);
      toast.error("Failed to save purchase bill", err.response?.data?.error || err.message);
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
    newGroups[gIndex].items.push({ product_name: '', brand: '', quantity: 1, rate: 0, discount_percent: 0 });
    setGroupedItems(newGroups);
  };

  const removeRow = (gIndex: number, iIndex: number) => {
    const newGroups = [...groupedItems];
    if (newGroups[gIndex].items.length === 1) return;
    newGroups[gIndex].items = newGroups[gIndex].items.filter((_, i) => i !== iIndex);
    setGroupedItems(newGroups);
  };

  const addCategoryGroup = () => {
    setGroupedItems([...groupedItems, { category_id: '', hsn_code: '', gst_rate: 18, items: [ { product_name: '', brand: '', quantity: 1, rate: 0, discount_percent: 0 } ] }]);
  };
  
  const removeCategoryGroup = (gIndex: number) => {
    if (groupedItems.length === 1) return;
    setGroupedItems(groupedItems.filter((_, i) => i !== gIndex));
  };

  const allItems = groupedItems.flatMap(g => g.items.map(i => ({...i, gst_rate: g.gst_rate})));

  // Calculate Subtotals
  const grossTotal = allItems.reduce((sum, item) => sum + (Number(item.quantity) * Number(item.rate)), 0);
  const totalTax = allItems.reduce((sum, item) => {
      const gross = Number(item.quantity) * Number(item.rate);
      const discount = gross * (Number(item.discount_percent)/100);
      const taxable = gross - discount;
      return sum + (taxable * (Number(item.gst_rate)/100));
  }, 0);
  const cartageVal = Number(cartageAmount) || 0;
  const unroundedGrandTotal = allItems.reduce((sum, item) => {
    const gross = Number(item.quantity) * Number(item.rate);
    const discount = gross * (Number(item.discount_percent)/100);
    const taxable = gross - discount;
    return sum + taxable + (taxable * (Number(item.gst_rate)/100));
  }, 0) + cartageVal;

  let grandTotal = 0;
  let roundOff = 0;
  if (unroundedGrandTotal > 0) {
    const integerPart = Math.floor(unroundedGrandTotal);
    const decimalPart = Math.round((unroundedGrandTotal - integerPart) * 100) / 100;
    grandTotal = decimalPart < 0.5 ? integerPart : integerPart + 1;
    roundOff = Math.round((grandTotal - unroundedGrandTotal) * 100) / 100;
  }

  const selectedParty = ledgers.find(l => l.id === partyLedgerId);
  const isInterState = Boolean(selectedParty?.state_code && companyStateCode && selectedParty.state_code !== companyStateCode);

  if (loading) return <DashboardLayout><div className="flex items-center justify-center h-full text-muted-foreground">Loading purchase form...</div></DashboardLayout>;

  return (
    <DashboardLayout>
      <div className="max-w-6xl mx-auto space-y-6 pb-20">
        
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between border-b border-border pb-4 gap-4">
          <div className="flex items-center gap-3 sm:gap-4">
            <Link href="/purchases" className="text-muted-foreground hover:text-foreground transition-colors p-1">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
            </Link>
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold">New Purchase Invoice</h1>
              <p className="text-xs sm:text-sm text-muted-foreground mt-0.5">Automated Accounts Payable & Inward Bills</p>
            </div>
          </div>
          
          {/* Mode Switcher */}
          <div className="w-full sm:w-auto grid grid-cols-2 sm:flex items-center bg-muted/50 border border-input p-1 rounded-xl shadow-inner gap-1">
            <button
              onClick={() => setActiveTab('OCR')}
              type="button"
              className={`px-3 sm:px-4 py-2 sm:py-1.5 rounded-lg text-xs font-bold transition-all text-center justify-center flex items-center gap-1.5 ${
                activeTab === 'OCR'
                  ? 'bg-gradient-to-r from-purple-600 to-blue-600 text-foreground shadow-md'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <span>✨ AI OCR</span>
            </button>
            <button
              onClick={() => setActiveTab('MANUAL')}
              type="button"
              className={`px-3 sm:px-4 py-2 sm:py-1.5 rounded-lg text-xs font-bold transition-all text-center justify-center flex items-center gap-1.5 ${
                activeTab === 'MANUAL'
                  ? 'bg-muted text-foreground shadow-md'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <span>📝 Manual Entry</span>
            </button>
          </div>
        </div>

        {/* AI OCR Split-Screen View */}
        {activeTab === 'OCR' && (
          <PurchaseOcrSplitView companyId={companyId} onSuccess={() => router.push('/purchases')} />
        )}

        {/* Manual Voucher Form */}
        {activeTab === 'MANUAL' && (
          <div className="space-y-6">
            <div className="flex justify-end">
              <button onClick={handleSave} disabled={saving} className="w-full sm:w-auto justify-center bg-red-600 hover:bg-red-700 text-foreground px-6 py-2.5 rounded-lg shadow-lg font-medium transition-colors disabled:opacity-50 flex items-center gap-2 cursor-pointer">
                {saving ? 'Posting...' : 'Post Purchase Invoice'}
              </button>
            </div>
        
        {/* Billing Details Card */}
        <div className="bg-card border border-border rounded-xl shadow-sm p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-foreground">Billing Details</h2>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6 pb-6 border-b border-border">
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1.5">Supplier Invoice No.</label>
              <input type="text" value={invoiceNumber} onChange={e => setInvoiceNumber(e.target.value)} placeholder="e.g. SUP-998" className="w-full bg-muted/50 border border-input text-foreground p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all" />
            </div>
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1.5">Invoice Date</label>
              <input type="date" value={invoiceDate} onChange={e => setInvoiceDate(e.target.value)} className="w-full bg-muted/50 border border-input text-foreground p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all" />
            </div>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <div className="flex justify-between items-center mb-1.5">
                <label className="block text-sm font-medium text-muted-foreground">Party (Supplier)</label>
                <Link href="/purchases/suppliers/new" className="text-xs text-red-500 hover:text-red-400">+ Add New Supplier</Link>
              </div>
              <select value={partyLedgerId} onChange={e => setPartyLedgerId(e.target.value)} className="w-full bg-muted/50 border border-input text-foreground p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all">
                <option value="">-- Select Supplier --</option>
                {ledgers.filter(l => l.group.includes('Debtor') || l.group.includes('Creditor')).map(l => (
                  <option key={l.id} value={l.id}>{l.name}</option>
                ))}
              </select>
            </div>
            {enableLedgerMapping && (
              <div>
                <label className="block text-sm font-medium text-muted-foreground mb-1.5">Purchase Ledger</label>
                <select value={purchaseLedgerId} onChange={e => setPurchaseLedgerId(e.target.value)} className="w-full bg-muted/50 border border-input text-foreground p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all">
                  <option value="">-- Select Purchase Ledger --</option>
                  {ledgers.filter(l => l.group.includes('Expense') || l.name.includes('Purchase')).map(l => (
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
                <h2 className="text-lg font-semibold text-foreground">Line Items by Category</h2>
                <span className="text-xs text-red-400 bg-red-400/10 px-2 py-1 rounded border border-red-400/20">Auto-Creates & Inherits Tax</span>
            </div>
            
            <div className="p-2 space-y-6">
                {groupedItems.map((group, gIndex) => (
                    <div key={gIndex} className="border border-border rounded-lg overflow-hidden bg-zinc-900/30">
                        <div className="p-3 sm:p-4 bg-zinc-900/80 border-b border-border flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                            <div className="flex-1 max-w-md flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
                                <label className="text-sm font-medium text-muted-foreground whitespace-nowrap">Category:</label>
                                <select 
                                    value={group.category_id} 
                                    onChange={(e) => updateGroup(gIndex, 'category_id', e.target.value)}
                                    className="w-full bg-muted border border-input text-foreground p-2 rounded focus:ring-2 focus:ring-blue-500 outline-none text-sm"
                                >
                                    <option value="">-- Select Category --</option>
                                    {categories.map(c => (
                                        <option key={c.id} value={c.id}>{c.name}</option>
                                    ))}
                                </select>
                            </div>
                            <div className="flex flex-wrap items-center justify-between sm:justify-end gap-2 sm:gap-4 text-sm text-muted-foreground">
                                <span className="text-xs sm:text-sm">Default HSN: <strong className="text-foreground/80">{group.hsn_code || 'N/A'}</strong></span>
                                {isInterState ? (
                                    <span className="bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded border border-blue-500/20 text-xs font-medium">
                                        IGST: {group.gst_rate}%
                                    </span>
                                ) : (
                                    <div className="flex gap-2">
                                        <span className="bg-muted text-foreground/80 px-2 py-0.5 rounded border border-input text-xs font-medium">CGST: {(Number(group.gst_rate)/2).toFixed(1)}%</span>
                                        <span className="bg-muted text-foreground/80 px-2 py-0.5 rounded border border-input text-xs font-medium">SGST: {(Number(group.gst_rate)/2).toFixed(1)}%</span>
                                    </div>
                                )}
                                <button onClick={() => removeCategoryGroup(gIndex)} className="text-red-500 hover:text-red-400 ml-auto sm:ml-4 p-1" title="Delete category group">
                                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                                </button>
                            </div>
                        </div>
                        
                        <div className="overflow-x-auto">
                            <table className="w-full min-w-[550px] text-left border-collapse">
                                <thead className="bg-zinc-900/40 text-muted-foreground text-xs uppercase tracking-wider">
                                    <tr>
                                        <th className="p-3 font-medium">Product Name</th>
                                        <th className="p-3 font-medium w-36">Brand</th>
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
                                                <input type="text" placeholder="e.g. Item Name" value={item.product_name} onChange={e => updateItem(gIndex, iIndex, 'product_name', e.target.value)} className="w-full bg-transparent border border-transparent hover:border-input focus:border-blue-500 rounded p-1.5 outline-none text-foreground transition-all text-sm" />
                                            </td>
                                            <td className="p-2">
                                                <input type="text" placeholder="e.g. Fenner" value={item.brand || ''} onChange={e => updateItem(gIndex, iIndex, 'brand', e.target.value)} className="w-full bg-transparent border border-border hover:border-input focus:border-blue-500 rounded p-1.5 outline-none text-foreground transition-all text-sm" />
                                            </td>
                                            <td className="p-2">
                                                <input type="number" min="1" value={item.quantity} onChange={e => updateItem(gIndex, iIndex, 'quantity', e.target.value)} className="w-full bg-transparent border border-transparent hover:border-input focus:border-blue-500 rounded p-1.5 outline-none text-foreground transition-all text-center text-sm" />
                                            </td>
                                            <td className="p-2">
                                                <input type="number" min="0" value={item.rate} onChange={e => updateItem(gIndex, iIndex, 'rate', e.target.value)} className="w-full bg-transparent border border-transparent hover:border-input focus:border-blue-500 rounded p-1.5 outline-none text-foreground transition-all text-right text-sm" />
                                            </td>
                                            <td className="p-2">
                                                <input type="number" min="0" max="100" value={item.discount_percent} onChange={e => updateItem(gIndex, iIndex, 'discount_percent', e.target.value)} className="w-full bg-transparent border border-transparent hover:border-input focus:border-blue-500 rounded p-1.5 outline-none text-foreground transition-all text-center text-sm" />
                                            </td>
                                            <td className="p-2 text-right font-medium text-foreground">
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
                        <div className="p-3 bg-zinc-900/30 border-t border-border">
                            <button onClick={() => addRow(gIndex)} className="text-sm text-red-500 hover:text-red-400 font-medium flex items-center gap-1">
                                + Add item in {categories.find(c=>c.id===group.category_id)?.name || 'this category'}
                            </button>
                        </div>
                    </div>
                ))}
            </div>
            
            <div className="p-4 border-t border-border bg-zinc-900/20">
                <button onClick={addCategoryGroup} className="text-sm text-foreground bg-muted hover:bg-zinc-700 border border-input px-4 py-2 rounded shadow transition-colors font-medium">
                    + Add Another Category Block
                </button>
            </div>
        </div>

        {/* Totals Section */}
        <div className="flex justify-end">
            <div className="w-full max-w-md bg-card border border-border rounded-xl shadow-sm p-6 space-y-3">
                <div className="flex justify-between text-muted-foreground">
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
                        <div className="flex justify-between text-muted-foreground">
                            <span>CGST</span>
                            <span>₹{(totalTax / 2).toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between text-muted-foreground">
                            <span>SGST</span>
                            <span>₹{(totalTax / 2).toFixed(2)}</span>
                        </div>
                    </>
                )}
                <div className="flex justify-between items-center text-muted-foreground">
                    <span>Cartage / Freight Inward</span>
                    <div className="flex items-center gap-1">
                        <span className="text-muted-foreground font-mono text-sm">₹</span>
                        <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={cartageAmount}
                            onChange={(e) => setCartageAmount(e.target.value)}
                            placeholder="0.00"
                            className="w-28 bg-muted/50 border border-input text-foreground text-right px-2 py-1 rounded font-mono text-sm focus:ring-1 focus:ring-blue-500 outline-none"
                        />
                    </div>
                </div>
                <div className="flex justify-between text-muted-foreground">
                    <span>Round Off</span>
                    <span className={roundOff < 0 ? "text-emerald-400 font-mono font-medium" : roundOff > 0 ? "text-amber-400 font-mono font-medium" : "text-muted-foreground font-mono"}>
                        {roundOff > 0 ? `+₹${roundOff.toFixed(2)}` : roundOff < 0 ? `-₹${Math.abs(roundOff).toFixed(2)}` : `₹0.00`}
                    </span>
                </div>
                <div className="border-t border-input pt-3 flex justify-between text-xl font-bold text-foreground">
                    <span>Grand Total</span>
                    <span className="font-mono">₹{grandTotal.toFixed(2)}</span>
                </div>
            </div>
        </div>
          </div>
        )}

      </div>
    </DashboardLayout>
  );
}
