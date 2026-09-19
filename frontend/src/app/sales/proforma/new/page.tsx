"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useState, useEffect, useMemo, useCallback } from 'react';
import axios from 'axios';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import { useCompany } from '@/context/CompanyContext';
import { useFinancialYear } from '@/context/FinancialYearContext';
import { useToast } from '@/context/ToastContext';
import { 
  Plus, 
  Trash2, 
  ArrowLeft, 
  CheckCircle2, 
  Sparkles, 
  FileText, 
  Calendar, 
  User, 
  Truck, 
  Info,
  ChevronDown,
  Loader2,
  Receipt
} from 'lucide-react';

interface LineItem {
  id: string;
  product_id?: string;
  item_name: string;
  hsn_code: string;
  quantity: number;
  unit: string;
  rate: number;
  discount_percent: number;
  gst_rate: number;
}

export default function NewProformaQuotationPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { toast } = useToast();
  const { activeCompany, companyId: activeCompanyId } = useCompany();
  const { activeFY } = useFinancialYear();

  const initialType = searchParams.get('type')?.toUpperCase() === 'QUOTATION' ? 'QUOTATION' : 'PROFORMA';
  const [proformaType, setProformaType] = useState<'PROFORMA' | 'QUOTATION'>(initialType);

  const [companyId, setCompanyId] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Document metadata
  const [docNumber, setDocNumber] = useState('');
  const [autoNumber, setAutoNumber] = useState('');
  const [enableManualNumber, setEnableManualNumber] = useState(false);
  const [date, setDate] = useState(new Date().toISOString().split('T')[0]);
  const [validUntil, setValidUntil] = useState('');

  // Customer / Party details
  const [parties, setParties] = useState<any[]>([]);
  const [selectedPartyId, setSelectedPartyId] = useState('');
  const [buyerName, setBuyerName] = useState('');
  const [buyerAddress, setBuyerAddress] = useState('');
  const [buyerGstin, setBuyerGstin] = useState('');
  const [buyerStateCode, setBuyerStateCode] = useState('');
  const [buyerPhone, setBuyerPhone] = useState('');
  const [buyerEmail, setBuyerEmail] = useState('');
  const [showAdHocBuyer, setShowAdHocBuyer] = useState(false);

  // Inventory products for autocomplete
  const [products, setProducts] = useState<any[]>([]);

  // Line items
  const [items, setItems] = useState<LineItem[]>([
    {
      id: '1',
      item_name: '',
      hsn_code: '',
      quantity: 1,
      unit: 'PCS',
      rate: 0,
      discount_percent: 0,
      gst_rate: 18,
    }
  ]);

  // Cartage / Freight
  const [cartageAmount, setCartageAmount] = useState<number | string>('');

  // Terms & Notes
  const [customerNotes, setCustomerNotes] = useState('');
  const [terms, setTerms] = useState(
    '1. Prices quoted are valid for 15 days from the date of issuance.\n' +
    '2. Delivery within 3-5 business days upon order confirmation.\n' +
    '3. 100% payment required prior to dispatch / delivery.\n' +
    '4. Applicable GST will be invoiced on the final Tax Invoice.'
  );

  // Determine Company State Code
  const companyStateCode = useMemo(() => {
    if (activeCompany?.gstin && activeCompany.gstin.length >= 2) {
      return activeCompany.gstin.substring(0, 2);
    }
    return '09'; // Uttar Pradesh fallback
  }, [activeCompany]);

  // Determine Inter-State vs Intra-State
  const isInterState = useMemo(() => {
    let partyState = buyerStateCode;
    if (!partyState && buyerGstin && buyerGstin.length >= 2) {
      partyState = buyerGstin.substring(0, 2);
    }
    if (!partyState && selectedPartyId) {
      const p = parties.find((x) => x.id === selectedPartyId);
      if (p?.state_code) partyState = p.state_code;
      else if (p?.gstin && p.gstin.length >= 2) partyState = p.gstin.substring(0, 2);
    }
    if (!partyState) return false;
    return partyState !== companyStateCode;
  }, [buyerStateCode, buyerGstin, selectedPartyId, parties, companyStateCode]);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login');
      return;
    }

    let cid = activeCompanyId || '';
    if (!cid && typeof window !== 'undefined') {
      cid = localStorage.getItem('vouch_active_company_id') || '';
    }
    setCompanyId(cid);

    if (cid) {
      loadInitialData(cid);
    }
  }, [router, activeCompanyId]);

  const loadInitialData = async (cid: string) => {
    setLoading(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      // 1. Fetch parties (Sundry Debtors)
      const partiesRes = await axios.get(`${API_BASE_URL}/api/v1/ledgers/${cid}/?limit=500`, { headers }).catch(() => null);
      if (partiesRes?.data?.data) {
        const partyList = partiesRes.data.data.filter((l: any) => 
          l.ledger_type === 'PARTY' || 
          l.group_nature === 'ASSET' ||
          (l.group_name && l.group_name.toLowerCase().includes('debtor'))
        );
        setParties(partyList.length > 0 ? partyList : partiesRes.data.data);
      }

      // 2. Fetch products
      const prodRes = await axios.get(`${API_BASE_URL}/api/v1/inventory/products/${cid}/?limit=500`, { headers }).catch(() => null);
      if (prodRes?.data?.data) {
        setProducts(prodRes.data.data);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  // Preview Sequence Number
  useEffect(() => {
    const fetchSeq = async () => {
      if (!companyId) return;
      try {
        const token = getAccessToken();
        const headers = { Authorization: `Bearer ${token}` };
        const prefix = proformaType === 'PROFORMA' ? 'PI' : 'QTN';
        const res = await axios.get(
          `${API_BASE_URL}/api/v1/financial-years/sequence-preview/?voucher_type=${proformaType}&date=${date}`,
          { headers }
        ).catch(() => null);

        if (res?.data?.success && res.data.data?.preview_number) {
          setAutoNumber(res.data.data.preview_number);
        } else {
          const fyCode = activeFY?.code || '26-27';
          setAutoNumber(`${prefix}/${fyCode}/0001`);
        }
      } catch (err) {
        const prefix = proformaType === 'PROFORMA' ? 'PI' : 'QTN';
        setAutoNumber(`${prefix}/26-27/0001`);
      }
    };
    fetchSeq();
  }, [companyId, proformaType, date, activeFY]);

  // Handle Party Selection
  const handleSelectParty = (ledgerId: string) => {
    setSelectedPartyId(ledgerId);
    if (!ledgerId) {
      setBuyerName('');
      setBuyerAddress('');
      setBuyerGstin('');
      setBuyerStateCode('');
      setBuyerPhone('');
      return;
    }

    const party = parties.find((p) => p.id === ledgerId);
    if (party) {
      setBuyerName(party.name || '');
      setBuyerAddress(party.address || '');
      setBuyerGstin(party.gstin || '');
      setBuyerStateCode(party.state_code || (party.gstin ? party.gstin.substring(0, 2) : ''));
      setBuyerPhone(party.phone || '');
    }
  };

  // Item Management
  const handleItemChange = (index: number, field: keyof LineItem, val: any) => {
    setItems((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], [field]: val };
      return next;
    });
  };

  const handleSelectProduct = (index: number, productId: string) => {
    const prod = products.find((p) => p.id === productId);
    if (!prod) return;

    setItems((prev) => {
      const next = [...prev];
      next[index] = {
        ...next[index],
        product_id: prod.id,
        item_name: prod.name,
        hsn_code: prod.hsn_code || '',
        rate: Number(prod.sale_price || prod.price || 0),
        unit: prod.unit || 'PCS',
        gst_rate: Number(prod.tax_rate || 18),
      };
      return next;
    });
  };

  const addItemRow = () => {
    setItems((prev) => [
      ...prev,
      {
        id: String(Date.now()),
        item_name: '',
        hsn_code: '',
        quantity: 1,
        unit: 'PCS',
        rate: 0,
        discount_percent: 0,
        gst_rate: 18,
      }
    ]);
  };

  const removeItemRow = (index: number) => {
    if (items.length <= 1) {
      toast.error('Item Required', 'A document must have at least one line item.');
      return;
    }
    setItems((prev) => prev.filter((_, i) => i !== index));
  };

  // Computed Totals
  const totals = useMemo(() => {
    let taxableTotal = 0;
    let cgstTotal = 0;
    let sgstTotal = 0;
    let igstTotal = 0;

    items.forEach((it) => {
      const gross = Number(it.quantity || 0) * Number(it.rate || 0);
      const discount = gross * (Number(it.discount_percent || 0) / 100);
      const taxable = Math.max(0, gross - discount);
      const gstRate = Number(it.gst_rate || 0);

      taxableTotal += taxable;

      if (isInterState) {
        igstTotal += taxable * (gstRate / 100);
      } else {
        const halfRate = gstRate / 2;
        cgstTotal += taxable * (halfRate / 100);
        sgstTotal += taxable * (halfRate / 100);
      }
    });

    const taxTotal = cgstTotal + sgstTotal + igstTotal;
    const cartage = Number(cartageAmount || 0);
    const rawGrandTotal = taxableTotal + taxTotal + cartage;
    const roundedTotal = Math.round(rawGrandTotal);
    const roundOff = roundedTotal - rawGrandTotal;

    return {
      taxableTotal,
      cgstTotal,
      sgstTotal,
      igstTotal,
      taxTotal,
      cartage,
      roundOff,
      grandTotal: roundedTotal,
    };
  }, [items, isInterState, cartageAmount]);

  // Save Document
  const handleSave = async (convertImmediately = false) => {
    // Basic validation
    if (!buyerName.trim() && !selectedPartyId) {
      toast.error('Customer Required', 'Please select an existing customer or enter walk-in buyer details.');
      return;
    }

    const validItems = items.filter((it) => it.item_name.trim());
    if (validItems.length === 0) {
      toast.error('Items Required', 'Please enter at least one item with a valid description.');
      return;
    }

    setSaving(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      const payload = {
        company_id: companyId,
        proforma_type: proformaType,
        proforma_number: enableManualNumber && docNumber.trim() ? docNumber.trim() : undefined,
        date,
        valid_until: validUntil || undefined,
        party_ledger_id: selectedPartyId || undefined,
        buyer_name: buyerName.trim() || undefined,
        buyer_address: buyerAddress.trim() || undefined,
        buyer_gstin: buyerGstin.trim().toUpperCase() || undefined,
        buyer_state_code: buyerStateCode.trim() || undefined,
        buyer_phone: buyerPhone.trim() || undefined,
        buyer_email: buyerEmail.trim() || undefined,
        cartage_amount: totals.cartage,
        customer_notes: customerNotes.trim(),
        terms_and_conditions: terms.trim(),
        items: validItems.map((it) => ({
          product_id: it.product_id || undefined,
          item_name: it.item_name.trim(),
          hsn_code: it.hsn_code.trim(),
          quantity: Number(it.quantity || 1),
          unit: it.unit || 'PCS',
          rate: Number(it.rate || 0),
          discount_percent: Number(it.discount_percent || 0),
          gst_rate: Number(it.gst_rate || 18),
        })),
        convert_immediately: convertImmediately,
      };

      const res = await axios.post(`${API_BASE_URL}/api/v1/accounting/proforma/`, payload, { headers });

      if (res.data?.success) {
        if (convertImmediately) {
          toast.success(
            'Converted to GST Invoice!',
            `Created ${proformaType} and converted to Tax Invoice ${res.data.conversion?.voucher_number || 'INV'}!`
          );
          router.push(`/sales`);
        } else {
          toast.success(
            `${proformaType === 'PROFORMA' ? 'Proforma Invoice' : 'Quotation'} Created`,
            `Document #${res.data.data?.proforma_number} saved successfully.`
          );
          router.push(`/sales/proforma/${res.data.data?.id}`);
        }
      }
    } catch (err: any) {
      console.error(err);
      toast.error('Save Failed', err.response?.data?.error || err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="max-w-6xl mx-auto space-y-6 pb-16">
        {/* Top Header / Breadcrumb */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-border pb-4">
          <div className="flex items-center gap-3">
            <Link
              href="/sales/proforma"
              className="p-2 rounded-xl bg-card border border-border hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold text-foreground">
                  New {proformaType === 'PROFORMA' ? 'Proforma Invoice' : 'Quotation / Estimate'}
                </h1>
                <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400 font-semibold border border-blue-500/20">
                  Pre-Sale Document
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Issued for commercial estimates without triggering GST liability until converted.
              </p>
            </div>
          </div>

          {/* Type Toggle */}
          <div className="flex items-center gap-1 bg-muted/60 p-1 rounded-xl border border-border text-xs">
            <button
              type="button"
              onClick={() => setProformaType('PROFORMA')}
              className={`px-3.5 py-1.5 rounded-lg font-bold transition-all cursor-pointer ${
                proformaType === 'PROFORMA'
                  ? 'bg-card text-foreground shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              Proforma Invoice (PI)
            </button>
            <button
              type="button"
              onClick={() => setProformaType('QUOTATION')}
              className={`px-3.5 py-1.5 rounded-lg font-bold transition-all cursor-pointer ${
                proformaType === 'QUOTATION'
                  ? 'bg-card text-foreground shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              Quotation / Estimate (QTN)
            </button>
          </div>
        </div>

        {/* Form Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main Form (Left 2 cols) */}
          <div className="lg:col-span-2 space-y-6">
            {/* Customer Information Card */}
            <div className="bg-card border border-border rounded-2xl p-5 shadow-xs space-y-4">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <div className="flex items-center gap-2">
                  <User className="w-4 h-4 text-primary" />
                  <h2 className="text-sm font-bold text-foreground">Customer &amp; Billing Details</h2>
                </div>
                <button
                  type="button"
                  onClick={() => setShowAdHocBuyer(!showAdHocBuyer)}
                  className="text-xs font-semibold text-primary hover:underline cursor-pointer"
                >
                  {showAdHocBuyer ? 'Select Registered Customer' : '+ Walk-in / Ad-hoc Customer'}
                </button>
              </div>

              {!showAdHocBuyer ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="sm:col-span-2">
                    <label className="block text-xs font-medium text-muted-foreground mb-1">
                      Customer (Sundry Debtor) <span className="text-rose-500">*</span>
                    </label>
                    <select
                      value={selectedPartyId}
                      onChange={(e) => handleSelectParty(e.target.value)}
                      className="w-full px-3 py-2 bg-background border border-border rounded-xl text-xs text-foreground focus:outline-hidden focus:ring-2 focus:ring-primary/30"
                    >
                      <option value="">-- Select Customer / Ledger --</option>
                      {parties.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name} {p.gstin ? `(${p.gstin})` : ''}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Buyer GSTIN</label>
                    <input
                      type="text"
                      value={buyerGstin}
                      onChange={(e) => setBuyerGstin(e.target.value.toUpperCase())}
                      placeholder="e.g. 09ABCDE1234F1Z5"
                      maxLength={15}
                      className="w-full px-3 py-2 bg-background border border-border rounded-xl text-xs font-mono uppercase text-foreground focus:outline-hidden"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">State Code / Place of Supply</label>
                    <input
                      type="text"
                      value={buyerStateCode}
                      onChange={(e) => setBuyerStateCode(e.target.value)}
                      placeholder="e.g. 09 (UP), 07 (Delhi)"
                      maxLength={2}
                      className="w-full px-3 py-2 bg-background border border-border rounded-xl text-xs font-mono text-foreground focus:outline-hidden"
                    />
                  </div>

                  <div className="sm:col-span-2">
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Billing Address</label>
                    <textarea
                      rows={2}
                      value={buyerAddress}
                      onChange={(e) => setBuyerAddress(e.target.value)}
                      placeholder="Customer address..."
                      className="w-full px-3 py-2 bg-background border border-border rounded-xl text-xs text-foreground focus:outline-hidden resize-none"
                    />
                  </div>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">
                      Customer / Business Name <span className="text-rose-500">*</span>
                    </label>
                    <input
                      type="text"
                      value={buyerName}
                      onChange={(e) => setBuyerName(e.target.value)}
                      placeholder="Enter customer name..."
                      className="w-full px-3 py-2 bg-background border border-border rounded-xl text-xs text-foreground focus:outline-hidden"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Phone Number</label>
                    <input
                      type="text"
                      value={buyerPhone}
                      onChange={(e) => setBuyerPhone(e.target.value)}
                      placeholder="Mobile / Phone number..."
                      className="w-full px-3 py-2 bg-background border border-border rounded-xl text-xs text-foreground focus:outline-hidden"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">GSTIN (Optional)</label>
                    <input
                      type="text"
                      value={buyerGstin}
                      onChange={(e) => setBuyerGstin(e.target.value.toUpperCase())}
                      placeholder="15-digit GSTIN..."
                      maxLength={15}
                      className="w-full px-3 py-2 bg-background border border-border rounded-xl text-xs font-mono uppercase text-foreground focus:outline-hidden"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">State Code</label>
                    <input
                      type="text"
                      value={buyerStateCode}
                      onChange={(e) => setBuyerStateCode(e.target.value)}
                      placeholder="e.g. 09"
                      maxLength={2}
                      className="w-full px-3 py-2 bg-background border border-border rounded-xl text-xs font-mono text-foreground focus:outline-hidden"
                    />
                  </div>

                  <div className="sm:col-span-2">
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Billing Address</label>
                    <textarea
                      rows={2}
                      value={buyerAddress}
                      onChange={(e) => setBuyerAddress(e.target.value)}
                      placeholder="Customer address..."
                      className="w-full px-3 py-2 bg-background border border-border rounded-xl text-xs text-foreground focus:outline-hidden resize-none"
                    />
                  </div>
                </div>
              )}

              {/* Tax Supply Notice */}
              <div className="p-2.5 rounded-xl bg-muted/40 border border-border/60 text-xs flex items-center justify-between">
                <span className="text-muted-foreground">GST Supply Type:</span>
                <span className="font-semibold text-foreground font-mono">
                  {isInterState ? 'IGST (Inter-State Outward Supply)' : 'CGST + SGST (Intra-State Supply)'}
                </span>
              </div>
            </div>

            {/* Line Items Card */}
            <div className="bg-card border border-border rounded-2xl p-5 shadow-xs space-y-4">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <div className="flex items-center gap-2">
                  <FileText className="w-4 h-4 text-primary" />
                  <h2 className="text-sm font-bold text-foreground">Items, Products &amp; Price Breakdown</h2>
                </div>
                <button
                  type="button"
                  onClick={addItemRow}
                  className="px-3 py-1 bg-primary/10 hover:bg-primary/20 text-primary rounded-lg text-xs font-bold transition-colors flex items-center gap-1 cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Add Line</span>
                </button>
              </div>

              {/* Line items list */}
              <div className="space-y-3">
                {items.map((item, idx) => {
                  const gross = Number(item.quantity || 0) * Number(item.rate || 0);
                  const discount = gross * (Number(item.discount_percent || 0) / 100);
                  const taxable = Math.max(0, gross - discount);
                  const gstAmount = taxable * (Number(item.gst_rate || 0) / 100);
                  const lineTotal = taxable + gstAmount;

                  return (
                    <div
                      key={item.id}
                      className="p-3.5 bg-muted/20 hover:bg-muted/30 border border-border rounded-xl space-y-3 transition-colors"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-muted-foreground uppercase">
                          Item #{idx + 1}
                        </span>
                        {items.length > 1 && (
                          <button
                            type="button"
                            onClick={() => removeItemRow(idx)}
                            className="p-1 text-muted-foreground hover:text-rose-500 hover:bg-rose-500/10 rounded transition-colors cursor-pointer"
                            title="Remove line"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>

                      {/* Product select + description */}
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div className="sm:col-span-2">
                          <label className="block text-[11px] font-medium text-muted-foreground mb-1">
                            Item Description / Product Name <span className="text-rose-500">*</span>
                          </label>
                          <div className="space-y-1.5">
                            {products.length > 0 && (
                              <select
                                value={item.product_id || ''}
                                onChange={(e) => handleSelectProduct(idx, e.target.value)}
                                className="w-full px-2.5 py-1.5 bg-background border border-border rounded-lg text-xs text-foreground focus:outline-hidden mb-1"
                              >
                                <option value="">-- Choose from Inventory Product Catalog --</option>
                                {products.map((prod) => (
                                  <option key={prod.id} value={prod.id}>
                                    {prod.name} {prod.hsn_code ? `[HSN: ${prod.hsn_code}]` : ''} — ₹{prod.sale_price || prod.price || 0}
                                  </option>
                                ))}
                              </select>
                            )}
                            <input
                              type="text"
                              value={item.item_name}
                              onChange={(e) => handleItemChange(idx, 'item_name', e.target.value)}
                              placeholder="Type item description..."
                              className="w-full px-3 py-1.5 bg-background border border-border rounded-lg text-xs text-foreground focus:outline-hidden"
                            />
                          </div>
                        </div>

                        <div>
                          <label className="block text-[11px] font-medium text-muted-foreground mb-1">HSN / SAC Code</label>
                          <input
                            type="text"
                            value={item.hsn_code}
                            onChange={(e) => handleItemChange(idx, 'hsn_code', e.target.value)}
                            placeholder="e.g. 4010"
                            className="w-full px-3 py-1.5 bg-background border border-border rounded-lg text-xs font-mono text-foreground focus:outline-hidden"
                          />
                        </div>
                      </div>

                      {/* Numbers grid: Qty, Unit, Rate, Disc %, GST % */}
                      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 pt-1">
                        <div>
                          <label className="block text-[11px] font-medium text-muted-foreground mb-1">Qty</label>
                          <input
                            type="number"
                            min="0.01"
                            step="any"
                            value={item.quantity}
                            onChange={(e) => handleItemChange(idx, 'quantity', parseFloat(e.target.value) || 0)}
                            className="w-full px-2.5 py-1.5 bg-background border border-border rounded-lg text-xs font-mono text-foreground focus:outline-hidden"
                          />
                        </div>

                        <div>
                          <label className="block text-[11px] font-medium text-muted-foreground mb-1">Unit</label>
                          <select
                            value={item.unit}
                            onChange={(e) => handleItemChange(idx, 'unit', e.target.value)}
                            className="w-full px-2.5 py-1.5 bg-background border border-border rounded-lg text-xs text-foreground focus:outline-hidden"
                          >
                            <option value="PCS">PCS</option>
                            <option value="MTR">MTR</option>
                            <option value="KGS">KGS</option>
                            <option value="SET">SET</option>
                            <option value="NOS">NOS</option>
                            <option value="BOX">BOX</option>
                            <option value="ROLL">ROLL</option>
                          </select>
                        </div>

                        <div>
                          <label className="block text-[11px] font-medium text-muted-foreground mb-1">Unit Rate (₹)</label>
                          <input
                            type="number"
                            min="0"
                            step="any"
                            value={item.rate}
                            onChange={(e) => handleItemChange(idx, 'rate', parseFloat(e.target.value) || 0)}
                            className="w-full px-2.5 py-1.5 bg-background border border-border rounded-lg text-xs font-mono text-foreground focus:outline-hidden"
                          />
                        </div>

                        <div>
                          <label className="block text-[11px] font-medium text-muted-foreground mb-1">Disc %</label>
                          <input
                            type="number"
                            min="0"
                            max="100"
                            step="any"
                            value={item.discount_percent}
                            onChange={(e) => handleItemChange(idx, 'discount_percent', parseFloat(e.target.value) || 0)}
                            className="w-full px-2.5 py-1.5 bg-background border border-border rounded-lg text-xs font-mono text-foreground focus:outline-hidden"
                          />
                        </div>

                        <div>
                          <label className="block text-[11px] font-medium text-muted-foreground mb-1">GST Rate</label>
                          <select
                            value={item.gst_rate}
                            onChange={(e) => handleItemChange(idx, 'gst_rate', parseFloat(e.target.value) || 0)}
                            className="w-full px-2.5 py-1.5 bg-background border border-border rounded-lg text-xs font-mono text-foreground focus:outline-hidden"
                          >
                            <option value="0">0% (Nil)</option>
                            <option value="5">5%</option>
                            <option value="12">12%</option>
                            <option value="18">18%</option>
                            <option value="28">28%</option>
                          </select>
                        </div>
                      </div>

                      {/* Line Subtotal row */}
                      <div className="flex items-center justify-between text-xs pt-1 border-t border-border/40 font-mono">
                        <span className="text-muted-foreground">
                          Taxable: ₹{taxable.toFixed(2)} | GST: ₹{gstAmount.toFixed(2)}
                        </span>
                        <span className="font-bold text-foreground">
                          Total: ₹{lineTotal.toFixed(2)}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="pt-2">
                <button
                  type="button"
                  onClick={addItemRow}
                  className="w-full py-2 border-2 border-dashed border-border hover:border-primary/50 text-muted-foreground hover:text-primary rounded-xl text-xs font-semibold transition-colors flex items-center justify-center gap-1.5 cursor-pointer"
                >
                  <Plus className="w-4 h-4" />
                  <span>Add Another Product Line</span>
                </button>
              </div>
            </div>

            {/* Terms & Notes Card */}
            <div className="bg-card border border-border rounded-2xl p-5 shadow-xs space-y-4">
              <h2 className="text-sm font-bold text-foreground">Commercial Terms &amp; Customer Notes</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">Customer Notes</label>
                  <textarea
                    rows={4}
                    value={customerNotes}
                    onChange={(e) => setCustomerNotes(e.target.value)}
                    placeholder="Notes visible on quotation (e.g. Thanks for your inquiry!)..."
                    className="w-full px-3 py-2 bg-background border border-border rounded-xl text-xs text-foreground focus:outline-hidden resize-none"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">Terms &amp; Conditions</label>
                  <textarea
                    rows={4}
                    value={terms}
                    onChange={(e) => setTerms(e.target.value)}
                    className="w-full px-3 py-2 bg-background border border-border rounded-xl text-xs text-foreground focus:outline-hidden resize-none"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Right Sidebar (Summary, Date, Actions) */}
          <div className="space-y-6">
            {/* Document Meta Card */}
            <div className="bg-card border border-border rounded-2xl p-5 shadow-xs space-y-4">
              <h2 className="text-sm font-bold text-foreground">Document Details</h2>

              <div className="space-y-3">
                {/* Number */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-xs font-medium text-muted-foreground">Document Number</label>
                    <button
                      type="button"
                      onClick={() => setEnableManualNumber(!enableManualNumber)}
                      className="text-[10px] text-primary hover:underline cursor-pointer"
                    >
                      {enableManualNumber ? 'Auto Sequence' : 'Custom #'}
                    </button>
                  </div>
                  <input
                    type="text"
                    disabled={!enableManualNumber}
                    value={enableManualNumber ? docNumber : autoNumber}
                    onChange={(e) => setDocNumber(e.target.value)}
                    placeholder="Auto-generated..."
                    className="w-full px-3 py-2 bg-background border border-border rounded-xl text-xs font-mono font-bold text-foreground focus:outline-hidden disabled:opacity-75"
                  />
                </div>

                {/* Date */}
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">
                    Document Date <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="date"
                    value={date}
                    onChange={(e) => setDate(e.target.value)}
                    className="w-full px-3 py-2 bg-background border border-border rounded-xl text-xs font-mono text-foreground focus:outline-hidden"
                  />
                </div>

                {/* Valid Until */}
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">Valid Until (Expiry)</label>
                  <input
                    type="date"
                    value={validUntil}
                    onChange={(e) => setValidUntil(e.target.value)}
                    className="w-full px-3 py-2 bg-background border border-border rounded-xl text-xs font-mono text-foreground focus:outline-hidden"
                  />
                </div>

                {/* Freight / Cartage */}
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">Cartage / Freight Outward (₹)</label>
                  <input
                    type="number"
                    min="0"
                    step="any"
                    value={cartageAmount}
                    onChange={(e) => setCartageAmount(e.target.value)}
                    placeholder="0.00"
                    className="w-full px-3 py-2 bg-background border border-border rounded-xl text-xs font-mono text-foreground focus:outline-hidden"
                  />
                </div>
              </div>
            </div>

            {/* Financial Summary Card */}
            <div className="bg-card border border-border rounded-2xl p-5 shadow-xs space-y-3 font-mono text-xs">
              <h2 className="text-sm font-bold font-sans text-foreground">Summary &amp; Taxes</h2>

              <div className="space-y-2 divide-y divide-border/40">
                <div className="flex justify-between pt-1">
                  <span className="text-muted-foreground font-sans">Taxable Subtotal:</span>
                  <span className="font-semibold text-foreground">
                    ₹{totals.taxableTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </span>
                </div>

                {isInterState ? (
                  <div className="flex justify-between pt-2">
                    <span className="text-muted-foreground font-sans">IGST:</span>
                    <span className="font-semibold text-blue-600 dark:text-blue-400">
                      ₹{totals.igstTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                ) : (
                  <>
                    <div className="flex justify-between pt-2">
                      <span className="text-muted-foreground font-sans">CGST:</span>
                      <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                        ₹{totals.cgstTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </span>
                    </div>
                    <div className="flex justify-between pt-2">
                      <span className="text-muted-foreground font-sans">SGST:</span>
                      <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                        ₹{totals.sgstTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </span>
                    </div>
                  </>
                )}

                {totals.cartage > 0 && (
                  <div className="flex justify-between pt-2">
                    <span className="text-muted-foreground font-sans">Cartage / Freight:</span>
                    <span className="font-semibold text-foreground">
                      ₹{totals.cartage.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                )}

                {totals.roundOff !== 0 && (
                  <div className="flex justify-between pt-2 text-muted-foreground">
                    <span className="font-sans">Round Off:</span>
                    <span>₹{totals.roundOff.toFixed(2)}</span>
                  </div>
                )}

                <div className="flex justify-between pt-3 text-base font-black text-foreground">
                  <span className="font-sans">Total Quote:</span>
                  <span className="text-primary">
                    ₹{totals.grandTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </span>
                </div>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="space-y-2.5">
              {/* 1-Click Convert Directly */}
              <button
                type="button"
                onClick={() => handleSave(true)}
                disabled={saving}
                className="w-full py-3 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold transition-all shadow-md flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
              >
                {saving ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Sparkles className="w-4 h-4 text-amber-300" />
                )}
                <span>Save &amp; Convert to GST Invoice</span>
              </button>

              {/* Save as Proforma / Quote */}
              <button
                type="button"
                onClick={() => handleSave(false)}
                disabled={saving}
                className="w-full py-2.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl text-xs font-bold transition-colors shadow-xs flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
              >
                {saving ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="w-4 h-4" />
                )}
                <span>Save {proformaType === 'PROFORMA' ? 'Proforma Invoice' : 'Quotation'}</span>
              </button>

              <Link
                href="/sales/proforma"
                className="w-full py-2 bg-card hover:bg-muted/70 text-muted-foreground hover:text-foreground border border-border rounded-xl text-xs font-semibold transition-colors flex items-center justify-center cursor-pointer"
              >
                Cancel
              </Link>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
