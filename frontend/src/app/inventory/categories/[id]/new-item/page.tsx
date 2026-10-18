"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import { useCompany } from '@/context/CompanyContext';
import { useToast } from '@/context/ToastContext';
import BarcodeScannerModal from '@/components/modals/BarcodeScannerModal';
import { 
  Plus, 
  Trash2, 
  Barcode as BarcodeIcon, 
  Camera, 
  Tag, 
  Smartphone, 
  Palette, 
  Check, 
  X, 
  ShieldCheck, 
  Sparkles, 
  Layers,
  Cpu
} from 'lucide-react';

export default function NewItemInCategoryPage() {
  const router = useRouter();
  const params = useParams();
  const categoryId = params.id as string;
  const { toast } = useToast();
  const { activeCompany, companyId: activeCompanyId } = useCompany();

  const [saving, setSaving] = useState(false);
  const [category, setCategory] = useState<any>(null);
  const [companyId, setCompanyId] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Features, Custom Attributes & Multi-IMEI State
  const [attributes, setAttributes] = useState<Record<string, any>>({});
  const [imeiList, setImeiList] = useState<string[]>([]);
  const [currentImeiInput, setCurrentImeiInput] = useState('');
  const [isScannerOpen, setIsScannerOpen] = useState(false);
  const [scannerTarget, setScannerTarget] = useState<'BARCODE' | 'IMEI'>('IMEI');
  const [customKeyInput, setCustomKeyInput] = useState('');
  const [customValInput, setCustomValInput] = useState('');
  const [showAddCustomModal, setShowAddCustomModal] = useState(false);
  const [activeFeatureTab, setActiveFeatureTab] = useState<'ALL' | 'IMEI' | 'COLOR' | 'SPECS'>('ALL');

  const [formData, setFormData] = useState({
    name: '',
    alias: '',
    brand: '',
    sku: '',
    unit: 'PCS',
    alternate_unit: '',
    conversion_factor: 1,
    selling_price: '',
    wholesaler_price: '',
    min_selling_price: '',
    purchase_price: '',
    costing_method: 'AVG_COST',
    opening_qty: '',
    warehouse_id: '',
    opening_batch_number: '',
    opening_expiry_date: '',
    opening_serial_number: '',
    reorder_level: '',
    description: '',
    barcode: '',
    tax_override: false,
    override_hsn_code: '',
    override_gst_rate: 18,
  });

  // Smart toggles
  const [trackBatch, setTrackBatch] = useState(false);
  const [trackSerial, setTrackSerial] = useState(false);
  
  const [complexityLevel, setComplexityLevel] = useState(1);
  const [enableAdvancedItemCreation, setEnableAdvancedItemCreation] = useState(false);
  const [warehouses, setWarehouses] = useState<any[]>([]);

  useEffect(() => {
    if (!isAuthenticated()) { router.push('/login'); return; }
    fetchData();
  }, [router, categoryId, activeCompanyId]);

  const fetchData = async () => {
    try {
      const resolvedCid = activeCompanyId || (typeof window !== 'undefined' ? localStorage.getItem('vouch_active_company_id') : null);
      const token = getAccessToken();
      const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
      if (resolvedCid) headers['X-Company-ID'] = resolvedCid;

      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const compList = Array.isArray(compRes.data) ? compRes.data : (compRes.data?.data || []);
      const comp = (resolvedCid ? compList.find((c: any) => c.id === resolvedCid) : null) || compList[0];
      if (!comp) return;

      setCompanyId(comp.id);
      setComplexityLevel(comp.settings?.complexity_level || 1);
      setEnableAdvancedItemCreation(comp.settings?.enable_advanced_item_creation || false);

      const catRes = await axios.get(`${API_BASE_URL}/api/v1/inventory/categories/${comp.id}/`, { headers });
      const cat = (catRes.data?.data || (Array.isArray(catRes.data) ? catRes.data : [])).find((c: any) => c.id === categoryId);
      setCategory(cat);
      
      const whRes = await axios.get(`${API_BASE_URL}/api/v1/inventory/warehouses/${comp.id}/`, { headers }).catch(() => null);
      if (whRes && whRes.data) {
        setWarehouses(whRes.data.data || []);
      }
    } catch (err) {
      console.error(err);
    }
  };

  // IMEI management
  const handleAddImei = (code: string) => {
    const clean = code.trim();
    if (!clean) return;
    if (imeiList.includes(clean)) {
      toast.warning('Duplicate IMEI', `IMEI "${clean}" is already in the list.`);
      return;
    }
    const updated = [...imeiList, clean];
    setImeiList(updated);
    setAttributes(prev => ({ ...prev, imei_numbers: updated }));

    // Sync into description for electronics invoices & quotations
    setFormData(prev => {
      const parts = prev.description ? prev.description.split(' | ').filter(p => !p.startsWith('IMEI:')) : [];
      parts.push(`IMEI: ${updated.join(', ')}`);
      // If opening stock is 0 or less than IMEI count, update opening stock to match IMEI count
      const currentStock = parseFloat(prev.opening_qty) || 0;
      const newStock = Math.max(currentStock, updated.length);
      return { 
        ...prev, 
        description: parts.join(' | '),
        opening_qty: newStock.toString()
      };
    });
    setCurrentImeiInput('');
    toast.success('IMEI Attached', `Added ${clean} (${updated.length} total)`);
  };

  const handleRemoveImei = (indexToRemove: number) => {
    const updated = imeiList.filter((_, idx) => idx !== indexToRemove);
    setImeiList(updated);
    setAttributes(prev => {
      const next = { ...prev };
      if (updated.length > 0) next.imei_numbers = updated;
      else delete next.imei_numbers;
      return next;
    });
    setFormData(prev => {
      const parts = prev.description ? prev.description.split(' | ').filter(p => !p.startsWith('IMEI:')) : [];
      if (updated.length > 0) parts.push(`IMEI: ${updated.join(', ')}`);
      return { ...prev, description: parts.join(' | ') };
    });
  };

  const handleSetColor = (colorName: string) => {
    const clean = colorName.trim();
    setAttributes(prev => {
      const next = { ...prev };
      if (clean) next.color = clean;
      else delete next.color;
      return next;
    });
    setFormData(prev => {
      const parts = prev.description ? prev.description.split(' | ').filter(p => !p.startsWith('Color:')) : [];
      if (clean) parts.unshift(`Color: ${clean}`);
      return { ...prev, description: parts.join(' | ') };
    });
  };

  const handleAddCustomAttribute = (key: string, value: string) => {
    const k = key.trim();
    const v = value.trim();
    if (!k || !v) return;
    setAttributes(prev => ({ ...prev, [k]: v }));
    setShowAddCustomModal(false);
    setCustomKeyInput('');
    setCustomValInput('');
    toast.success('Feature Added', `${k}: ${v}`);
  };

  const handleRemoveAttribute = (key: string) => {
    setAttributes(prev => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
    if (key === 'color') {
      setFormData(prev => {
        const parts = prev.description ? prev.description.split(' | ').filter(p => !p.startsWith('Color:')) : [];
        return { ...prev, description: parts.join(' | ') };
      });
    }
  };

  const handleBarcodeScanned = (scannedCode: string) => {
    if (scannerTarget === 'BARCODE') {
      setFormData(prev => ({ ...prev, barcode: scannedCode }));
      toast.success('Barcode Scanned', scannedCode);
      setIsScannerOpen(false);
    } else {
      handleAddImei(scannedCode);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      const payload = {
        ...formData,
        attributes,
        selling_price: parseFloat(formData.selling_price) || 0,
        wholesaler_price: parseFloat(formData.wholesaler_price) || 0,
        min_selling_price: parseFloat(formData.min_selling_price) || 0,
        purchase_price: parseFloat(formData.purchase_price) || 0,
        opening_qty: parseFloat(formData.opening_qty) || 0,
        reorder_level: parseFloat(formData.reorder_level) || 0,
        conversion_factor: parseFloat(formData.conversion_factor.toString()) || 1,
        category_id: categoryId,
        track_batches: trackBatch,
        track_serial_numbers: trackSerial || imeiList.length > 0,
      };

      const res = await axios.post(`${API_BASE_URL}/api/v1/inventory/products/${companyId}/`, payload, { headers });
      if (res.data.success) {
        toast.success(`Item "${res.data.data.name}" added to ${category?.name || 'Category'}!`);
        router.push(`/inventory/categories/${categoryId}`);
        router.refresh();
      } else {
        toast.error('Failed to add item', res.data.error);
      }
    } catch (err: any) {
      toast.error('Error adding item', err.response?.data?.error || err.message);
    } finally {
      setSaving(false);
    }
  };

  const units = [
    { value: 'PCS', label: 'Pieces', icon: '🔩' },
    { value: 'NOS', label: 'Numbers', icon: '#️⃣' },
    { value: 'KG', label: 'Kilograms', icon: '⚖️' },
    { value: 'LTR', label: 'Litres', icon: '💧' },
    { value: 'MTR', label: 'Metres', icon: '📏' },
    { value: 'SET', label: 'Set', icon: '📦' },
    { value: 'BOX', label: 'Box', icon: '📦' },
    { value: 'PAIR', label: 'Pair', icon: '👟' },
  ];

  const margin = formData.selling_price && formData.purchase_price
    ? ((parseFloat(formData.selling_price) - parseFloat(formData.purchase_price)) / parseFloat(formData.selling_price) * 100)
    : 0;

  const activeHsn = formData.tax_override ? formData.override_hsn_code : category?.hsn_code;
  const activeGst = formData.tax_override ? formData.override_gst_rate : category?.gst_rate;

  return (
    <DashboardLayout>
      <div className="pb-12">
        <div className="max-w-5xl mx-auto">

          {/* Header */}
          <div className="flex items-center gap-4 border-b border-border pb-5 mb-6">
            <Link href={`/inventory/categories/${categoryId}`} className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded-lg hover:bg-muted">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
            </Link>
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold text-foreground">Add New Item</h1>
              <p className="text-muted-foreground mt-1 text-sm">Adding to <span className="text-primary font-semibold">{category?.name || '...'}</span></p>
            </div>
          </div>

          <form onSubmit={handleSave}>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

              {/* ──── LEFT: Form (2 cols) ──── */}
              <div className="lg:col-span-2 space-y-6">

                {/* ───── ZONE 1: THE ESSENTIALS ───── */}
                <div className="bg-card border border-border rounded-xl shadow-sm p-6">
                  <div className="flex items-center gap-2.5 mb-5">
                    <div className="w-8 h-8 bg-blue-500/10 text-blue-600 dark:text-blue-400 rounded-lg flex items-center justify-center text-sm font-bold">1</div>
                    <h2 className="text-lg font-semibold text-foreground">Essentials</h2>
                  </div>

                  <div className="space-y-5">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      {/* Item Name */}
                      <div>
                        <label className="block text-sm font-medium text-foreground/80 mb-1.5">Item Name / Size *</label>
                        <input
                          required
                          type="text"
                          autoFocus
                          placeholder="e.g. A-32, iPhone 15 Pro"
                          value={formData.name}
                          onChange={e => setFormData({ ...formData, name: e.target.value })}
                          className="w-full bg-background border border-input text-foreground placeholder:text-muted-foreground p-3 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all text-base sm:text-lg shadow-xs"
                        />
                      </div>
                      
                      {/* Alias */}
                      <div>
                        <label className="block text-sm font-medium text-muted-foreground mb-1.5">Alias / Short Name</label>
                        <input
                          type="text"
                          placeholder="Alternative search name"
                          value={formData.alias}
                          onChange={e => setFormData({ ...formData, alias: e.target.value })}
                          className="w-full bg-background border border-input text-foreground placeholder:text-muted-foreground p-3 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all text-base sm:text-lg shadow-xs"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      {/* Brand */}
                      <div>
                        <label className="block text-sm font-medium text-muted-foreground mb-1.5">Brand</label>
                        <input
                          type="text"
                          placeholder="e.g. PIX, SKF, Samsung"
                          value={formData.brand}
                          onChange={e => setFormData({ ...formData, brand: e.target.value })}
                          className="w-full bg-background border border-input text-foreground placeholder:text-muted-foreground p-3 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all shadow-xs"
                        />
                      </div>
                    </div>

                    {/* Unit Selector */}
                    <div>
                      <label className="block text-sm font-medium text-muted-foreground mb-2">Primary Unit of Measure</label>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                        {units.map(u => {
                          const isSelected = formData.unit === u.value;
                          return (
                            <button
                              key={u.value}
                              type="button"
                              onClick={() => setFormData({ ...formData, unit: u.value })}
                              className={`p-2.5 rounded-lg border text-sm font-medium transition-all flex items-center justify-center gap-1.5 shadow-xs cursor-pointer ${
                                isSelected
                                  ? 'bg-blue-50 border-blue-500 text-blue-700 dark:bg-blue-950/40 dark:border-blue-500 dark:text-blue-300 ring-1 ring-blue-500/20 font-semibold'
                                  : 'bg-muted/40 border-border text-muted-foreground hover:bg-muted hover:text-foreground'
                              }`}
                            >
                              <span>{u.icon}</span>
                              <span>{u.label}</span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                    {/* Pricing, Costing & Stock */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-6 pt-6 border-t border-border">
                      <div>
                        <label className="block text-sm font-medium text-blue-600 dark:text-blue-400 mb-1.5">Maximum Retail Price (MRP) (₹) *</label>
                        <input
                          required
                          type="number"
                          step="0.01"
                          placeholder="0.00"
                          value={formData.selling_price}
                          onChange={e => setFormData({ ...formData, selling_price: e.target.value })}
                          className="w-full bg-background border border-blue-500/40 text-emerald-600 dark:text-emerald-400 font-bold p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all shadow-xs"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-emerald-600 dark:text-emerald-400 mb-1.5">Purchase / Cost Price (₹)</label>
                        <input
                          type="number"
                          step="0.01"
                          placeholder="0.00"
                          value={formData.purchase_price}
                          onChange={e => setFormData({ ...formData, purchase_price: e.target.value })}
                          className="w-full bg-background border border-input text-foreground font-medium p-3 rounded-lg focus:ring-2 focus:ring-emerald-500 outline-none transition-all shadow-xs"
                        />
                        {parseFloat(formData.selling_price) > 0 && parseFloat(formData.purchase_price) > 0 && (
                          <p className="text-[11px] text-muted-foreground mt-1">
                            Margin: <span className={margin >= 0 ? "text-emerald-600 dark:text-emerald-400 font-semibold" : "text-rose-600 dark:text-rose-400 font-semibold"}>
                              {margin >= 0 ? `+${margin.toFixed(1)}%` : `${margin.toFixed(1)}%`}
                            </span>
                          </p>
                        )}
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-amber-600 dark:text-amber-400 mb-1.5">Costing / Valuation Method</label>
                        <select
                          value={formData.costing_method}
                          onChange={e => setFormData({ ...formData, costing_method: e.target.value })}
                          className="w-full bg-background border border-input text-foreground p-3 rounded-lg focus:ring-2 focus:ring-amber-500 outline-none transition-all text-sm shadow-xs cursor-pointer"
                        >
                          <option value="AVG_COST" className="bg-background text-foreground">Average Cost (Moving)</option>
                          <option value="FIFO" className="bg-background text-foreground">FIFO (First-In, First-Out)</option>
                          <option value="STD_COST" className="bg-background text-foreground">Standard Cost</option>
                          <option value="LIFO" className="bg-background text-foreground">LIFO (Last-In, First-Out)</option>
                        </select>
                        <p className="text-[11px] text-muted-foreground mt-1">
                          Determines COGS calculation & export valuation
                        </p>
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-muted-foreground mb-1.5">Opening Quantity (Optional)</label>
                        <input
                          type="number"
                          placeholder="0"
                          value={formData.opening_qty}
                          onChange={e => setFormData({ ...formData, opening_qty: e.target.value })}
                          className="w-full bg-background border border-input text-foreground p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all shadow-xs"
                        />
                        {parseFloat(formData.opening_qty) > 0 && parseFloat(formData.purchase_price) > 0 && (
                          <p className="text-[11px] text-muted-foreground mt-1">
                            Opening Val: <span className="text-emerald-600 dark:text-emerald-400 font-semibold font-mono">
                              ₹{(parseFloat(formData.opening_qty) * parseFloat(formData.purchase_price)).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                            </span>
                          </p>
                        )}
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-blue-600 dark:text-blue-400 mb-1.5 flex items-center justify-between">
                          <span>Minimum Required Quantity (Min Stock)</span>
                          <span className="text-[11px] text-muted-foreground font-normal">Reorder Threshold</span>
                        </label>
                        <input
                          type="number"
                          min="0"
                          placeholder="e.g. 10"
                          value={formData.reorder_level}
                          onChange={e => setFormData({ ...formData, reorder_level: e.target.value })}
                          className="w-full bg-background border border-input text-foreground p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all shadow-xs"
                        />
                        <p className="text-[11px] text-muted-foreground mt-1">
                          Below this quantity, the item will be flagged as low on stock in Reorder Analytics.
                        </p>
                      </div>
                    </div>
                  </div>

                {/* ───── FEATURES & CUSTOM ATTRIBUTES (ELECTRONICS / IMEI / SPECS) ───── */}
                <div className="bg-card border border-border rounded-xl shadow-sm p-6 space-y-5">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-4">
                    <div className="flex items-center gap-2.5">
                      <div className="w-8 h-8 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 rounded-lg flex items-center justify-center text-sm font-bold">
                        <Sparkles className="w-4 h-4" />
                      </div>
                      <div>
                        <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
                          <span>Features & Attributes</span>
                          {Object.keys(attributes).length > 0 && (
                            <span className="text-xs bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20 px-2 py-0.5 rounded-full font-bold">
                              {Object.keys(attributes).length} Active
                            </span>
                          )}
                        </h2>
                        <p className="text-xs text-muted-foreground">Add Color, Multi-IMEI numbers, Specifications, or Custom product tags.</p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 flex-wrap">
                      <button
                        type="button"
                        onClick={() => setShowAddCustomModal(true)}
                        className="px-3 py-1.5 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/30 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
                      >
                        <Plus className="w-3.5 h-3.5" />
                        <span>+ Add Feature</span>
                      </button>
                    </div>
                  </div>

                  {/* Feature Quick-Add Pills */}
                  <div className="flex items-center gap-2 flex-wrap">
                    <button
                      type="button"
                      onClick={() => {
                        setScannerTarget('IMEI');
                        setIsScannerOpen(true);
                      }}
                      className="px-3 py-1.5 rounded-lg border border-purple-500/30 bg-purple-500/10 text-purple-700 dark:text-purple-300 text-xs font-semibold flex items-center gap-1.5 hover:bg-purple-500/20 transition-colors cursor-pointer"
                    >
                      <Camera className="w-3.5 h-3.5 text-purple-500" />
                      <span>📷 Scan Barcode / IMEI</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        const defaultColors = ['Space Black', 'Titanium Gray', 'Silver', 'Gold', 'Midnight Blue', 'White'];
                        const currentColor = attributes.color || '';
                        const nextIndex = (defaultColors.indexOf(currentColor) + 1) % defaultColors.length;
                        handleSetColor(defaultColors[nextIndex]);
                      }}
                      className={`px-3 py-1.5 rounded-lg border text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer ${
                        attributes.color
                          ? 'border-blue-500/40 bg-blue-500/15 text-blue-700 dark:text-blue-300 font-bold'
                          : 'border-border bg-muted/40 text-muted-foreground hover:bg-muted hover:text-foreground'
                      }`}
                    >
                      <Palette className="w-3.5 h-3.5 text-blue-500" />
                      <span>{attributes.color ? `Color: ${attributes.color}` : '+ Add Color'}</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => handleAddCustomAttribute('Storage', '128GB')}
                      className={`px-3 py-1.5 rounded-lg border text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer ${
                        attributes.Storage
                          ? 'border-emerald-500/40 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 font-bold'
                          : 'border-border bg-muted/40 text-muted-foreground hover:bg-muted hover:text-foreground'
                      }`}
                    >
                      <Cpu className="w-3.5 h-3.5 text-emerald-500" />
                      <span>{attributes.Storage ? `Storage: ${attributes.Storage}` : '+ Storage (128GB)'}</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => handleAddCustomAttribute('Warranty', '1 Year')}
                      className={`px-3 py-1.5 rounded-lg border text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer ${
                        attributes.Warranty
                          ? 'border-amber-500/40 bg-amber-500/15 text-amber-700 dark:text-amber-300 font-bold'
                          : 'border-border bg-muted/40 text-muted-foreground hover:bg-muted hover:text-foreground'
                      }`}
                    >
                      <ShieldCheck className="w-3.5 h-3.5 text-amber-500" />
                      <span>{attributes.Warranty ? `Warranty: ${attributes.Warranty}` : '+ 1 Year Warranty'}</span>
                    </button>
                  </div>

                  {/* Multi-IMEI / Serial Manager for Electronics Shops */}
                  <div className="p-4 bg-muted/30 dark:bg-muted/10 border border-border rounded-xl space-y-3">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <Smartphone className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                        <span className="text-xs font-bold uppercase tracking-wider text-foreground">
                          IMEI / Serial Numbers ({imeiList.length})
                        </span>
                        <span className="text-[10px] text-muted-foreground bg-muted px-2 py-0.5 rounded font-mono">
                          Single Item Master Tracking
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          setScannerTarget('IMEI');
                          setIsScannerOpen(true);
                        }}
                        className="px-2.5 py-1 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-xs font-bold flex items-center gap-1.5 cursor-pointer shadow-xs transition-colors self-start sm:self-auto"
                      >
                        <Camera className="w-3.5 h-3.5" />
                        <span>Scan IMEI Barcode</span>
                      </button>
                    </div>

                    <p className="text-xs text-muted-foreground leading-relaxed">
                      For mobile & electronics shops: All unique 15-digit IMEIs for this model are attached here under this single item. Searching any IMEI will find this product.
                    </p>

                    {/* IMEI Input & Add */}
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        placeholder="Type 15-digit IMEI or Serial number and hit Enter..."
                        value={currentImeiInput}
                        onChange={e => setCurrentImeiInput(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === 'Enter') {
                            e.preventDefault();
                            handleAddImei(currentImeiInput);
                          }
                        }}
                        className="flex-1 bg-background border border-input text-foreground px-3 py-2 rounded-lg text-xs font-mono outline-none focus:ring-2 focus:ring-purple-500 shadow-xs"
                      />
                      <button
                        type="button"
                        onClick={() => handleAddImei(currentImeiInput)}
                        disabled={!currentImeiInput.trim()}
                        className="px-3.5 py-2 bg-muted hover:bg-muted/80 text-foreground border border-input rounded-lg text-xs font-bold disabled:opacity-50 transition-colors cursor-pointer"
                      >
                        Add IMEI
                      </button>
                    </div>

                    {/* IMEI Chips List */}
                    {imeiList.length > 0 ? (
                      <div className="flex items-center gap-2 flex-wrap pt-1 max-h-48 overflow-y-auto">
                        {imeiList.map((imei, idx) => (
                          <div
                            key={idx}
                            className="bg-purple-500/10 text-purple-700 dark:text-purple-300 border border-purple-500/25 px-2.5 py-1 rounded-lg text-xs font-mono font-bold flex items-center gap-2 shadow-2xs group"
                          >
                            <span className="text-[10px] text-purple-400 font-normal">#{idx + 1}</span>
                            <span>{imei}</span>
                            <button
                              type="button"
                              onClick={() => handleRemoveImei(idx)}
                              className="text-purple-400 hover:text-red-500 transition-colors p-0.5 rounded cursor-pointer"
                              title="Remove IMEI"
                            >
                              <X className="w-3 h-3" />
                            </button>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-[11px] text-muted-foreground italic">
                        No IMEIs attached yet. Scan with camera or type above to add.
                      </p>
                    )}
                  </div>

                  {/* Color Selector / Custom Attributes List */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {/* Color Input */}
                    <div className="p-3 bg-muted/20 border border-border rounded-xl space-y-2">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-bold text-foreground flex items-center gap-1.5">
                          <Palette className="w-3.5 h-3.5 text-blue-500" />
                          <span>Product Color</span>
                        </label>
                        {attributes.color && (
                          <button
                            type="button"
                            onClick={() => handleRemoveAttribute('color')}
                            className="text-[10px] text-rose-500 hover:underline cursor-pointer"
                          >
                            Clear
                          </button>
                        )}
                      </div>
                      <input
                        type="text"
                        placeholder="e.g. Space Black, Titanium Gray, Silver"
                        value={attributes.color || ''}
                        onChange={e => handleSetColor(e.target.value)}
                        className="w-full bg-background border border-input text-foreground px-3 py-1.5 rounded-lg text-xs outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </div>

                    {/* Active Attributes Badges */}
                    <div className="p-3 bg-muted/20 border border-border rounded-xl space-y-2">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-bold text-foreground flex items-center gap-1.5">
                          <Tag className="w-3.5 h-3.5 text-emerald-500" />
                          <span>Active Specifications ({Object.keys(attributes).filter(k => k !== 'imei_numbers' && k !== 'color').length})</span>
                        </label>
                        <button
                          type="button"
                          onClick={() => setShowAddCustomModal(true)}
                          className="text-[11px] text-primary hover:underline cursor-pointer font-semibold"
                        >
                          + Add New
                        </button>
                      </div>

                      <div className="flex items-center gap-1.5 flex-wrap">
                        {Object.entries(attributes)
                          .filter(([k]) => k !== 'imei_numbers' && k !== 'color')
                          .map(([key, val]) => (
                            <span
                              key={key}
                              className="bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-500/20 px-2 py-0.5 rounded text-xs font-medium flex items-center gap-1.5"
                            >
                              <span className="font-semibold text-emerald-600 dark:text-emerald-400">{key}:</span>
                              <span>{String(val)}</span>
                              <button
                                type="button"
                                onClick={() => handleRemoveAttribute(key)}
                                className="text-muted-foreground hover:text-red-500 cursor-pointer"
                              >
                                <X className="w-3 h-3" />
                              </button>
                            </span>
                          ))}
                        {Object.keys(attributes).filter(k => k !== 'imei_numbers' && k !== 'color').length === 0 && (
                          <span className="text-[11px] text-muted-foreground italic">No custom specs added.</span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>

                {/* ───── ZONE 2 & 3: ADVANCED (Conditionally rendered) ───── */}
                {enableAdvancedItemCreation && (
                  <>
                    <div className="bg-card border border-border rounded-xl shadow-sm p-6">
                      <div className="flex items-center gap-2.5 mb-5">
                        <div className="w-8 h-8 bg-purple-500/10 text-purple-600 dark:text-purple-400 rounded-lg flex items-center justify-center text-sm font-bold">2</div>
                        <h2 className="text-lg font-semibold text-foreground">Advanced Pricing & Options</h2>
                      </div>

                      {/* Pricing Matrix */}
                      <div className="mb-6">
                        <label className="block text-sm font-medium text-muted-foreground mb-3">Unified Pricing Matrix</label>
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                          <div className="bg-muted/30 dark:bg-muted/10 border border-border rounded-lg p-3 shadow-xs">
                            <p className="text-xs text-muted-foreground mb-1">Purchase Price</p>
                            <div className="flex items-center gap-1">
                              <span className="text-muted-foreground font-medium">₹</span>
                              <input type="number" step="0.01" placeholder="0.00" value={formData.purchase_price} onChange={e => setFormData({ ...formData, purchase_price: e.target.value })} className="bg-transparent text-foreground w-full outline-none font-bold text-base" />
                            </div>
                          </div>
                          <div className="bg-muted/30 dark:bg-muted/10 border border-border rounded-lg p-3 shadow-xs">
                            <p className="text-xs text-muted-foreground mb-1">Min Sell Price</p>
                            <div className="flex items-center gap-1">
                              <span className="text-muted-foreground font-medium">₹</span>
                              <input type="number" step="0.01" placeholder="0.00" value={formData.min_selling_price} onChange={e => setFormData({ ...formData, min_selling_price: e.target.value })} className="bg-transparent text-foreground w-full outline-none font-bold text-base" />
                            </div>
                          </div>
                          <div className="bg-muted/30 dark:bg-muted/10 border border-border rounded-lg p-3 shadow-xs">
                            <p className="text-xs text-muted-foreground mb-1">Wholesale Price</p>
                            <div className="flex items-center gap-1">
                              <span className="text-muted-foreground font-medium">₹</span>
                              <input type="number" step="0.01" placeholder="0.00" value={formData.wholesaler_price} onChange={e => setFormData({ ...formData, wholesaler_price: e.target.value })} className="bg-transparent text-foreground w-full outline-none font-bold text-base" />
                            </div>
                          </div>
                          <div className="bg-blue-50/60 dark:bg-blue-950/20 border border-blue-500/30 rounded-lg p-3 ring-1 ring-blue-500/20 shadow-xs">
                            <p className="text-xs text-blue-600 dark:text-blue-400 font-medium mb-1">Maximum Retail Price (MRP) *</p>
                            <div className="flex items-center gap-1">
                              <span className="text-blue-600 dark:text-blue-400 font-medium">₹</span>
                              <input required type="number" step="0.01" placeholder="0.00" value={formData.selling_price} onChange={e => setFormData({ ...formData, selling_price: e.target.value })} className="bg-transparent text-emerald-600 dark:text-emerald-400 w-full outline-none font-bold text-base" />
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Toggles */}
                      <div className="space-y-3">
                        {complexityLevel > 1 && (
                          <>
                            <div className="flex items-center justify-between bg-muted/30 dark:bg-muted/10 border border-border rounded-lg p-4">
                              <div>
                                <p className="text-foreground font-medium text-sm">Track Batches & Expiry Dates</p>
                                <p className="text-muted-foreground text-xs mt-0.5">Enable for perishable goods, medicines, food items</p>
                              </div>
                              <button type="button" onClick={() => setTrackBatch(!trackBatch)} className={`w-12 h-7 rounded-full transition-all relative cursor-pointer ${trackBatch ? 'bg-primary' : 'bg-muted-foreground/30'}`}>
                                <div className={`w-5 h-5 bg-white rounded-full absolute top-1 transition-all shadow-sm ${trackBatch ? 'left-6' : 'left-1'}`}></div>
                              </button>
                            </div>
                            
                            <div className="flex items-center justify-between bg-muted/30 dark:bg-muted/10 border border-border rounded-lg p-4">
                              <div>
                                <p className="text-foreground font-medium text-sm">Serial Number / IMEI Tracking</p>
                                <p className="text-muted-foreground text-xs mt-0.5">Enable for phones, laptops, electronics with unique serial numbers</p>
                              </div>
                              <button type="button" onClick={() => setTrackSerial(!trackSerial)} className={`w-12 h-7 rounded-full transition-all relative cursor-pointer ${trackSerial ? 'bg-primary' : 'bg-muted-foreground/30'}`}>
                                <div className={`w-5 h-5 bg-white rounded-full absolute top-1 transition-all shadow-sm ${trackSerial ? 'left-6' : 'left-1'}`}></div>
                              </button>
                            </div>
                          </>
                        )}
                        
                        <div className="flex items-start gap-3 bg-muted/30 dark:bg-muted/10 border border-border rounded-lg p-4">
                          <input 
                            type="checkbox" 
                            id="alt_unit"
                            checked={!!formData.alternate_unit}
                            onChange={(e) => setFormData({...formData, alternate_unit: e.target.checked ? 'BOX' : '', conversion_factor: 1})}
                            className="mt-1 w-4 h-4 rounded border-input text-primary focus:ring-primary cursor-pointer"
                          />
                          <div className="flex-1">
                            <label htmlFor="alt_unit" className="text-foreground font-medium text-sm block cursor-pointer">Sell this item in multiple packaging types</label>
                            <p className="text-muted-foreground text-xs mt-0.5 mb-3">e.g., Allow selling in both Pieces and Boxes</p>
                            {formData.alternate_unit && (
                              <div className="flex items-center gap-3 bg-background p-3 rounded-lg border border-border shadow-xs">
                                <span className="text-sm font-medium text-foreground">1</span>
                                <select 
                                  value={formData.alternate_unit}
                                  onChange={e => setFormData({...formData, alternate_unit: e.target.value})}
                                  className="bg-muted/50 text-foreground text-sm p-1.5 rounded border border-input outline-none cursor-pointer"
                                >
                                  <option value="BOX" className="bg-background text-foreground">BOX</option>
                                  <option value="SET" className="bg-background text-foreground">SET</option>
                                  <option value="DOZ" className="bg-background text-foreground">DOZEN</option>
                                  <option value="PACK" className="bg-background text-foreground">PACK</option>
                                </select>
                                <span className="text-sm text-muted-foreground">=</span>
                                <input 
                                  type="number" step="0.01" 
                                  value={formData.conversion_factor}
                                  onChange={e => setFormData({...formData, conversion_factor: parseFloat(e.target.value) || 1})}
                                  className="bg-muted/50 text-foreground text-sm p-1.5 rounded border border-input outline-none w-20 text-center font-medium" 
                                />
                                <span className="text-sm font-medium text-foreground">{formData.unit}</span>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="bg-card border border-border rounded-xl shadow-sm overflow-hidden">
                      <button
                        type="button"
                        onClick={() => setShowAdvanced(!showAdvanced)}
                        className="w-full p-5 flex items-center justify-between hover:bg-muted/50 transition-colors cursor-pointer"
                      >
                        <div className="flex items-center gap-2.5">
                          <div className="w-8 h-8 bg-muted text-muted-foreground rounded-lg flex items-center justify-center text-sm font-bold">3</div>
                          <h2 className="text-lg font-semibold text-foreground">Inventory & Tax Details</h2>
                          <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded ml-1 font-medium">Optional</span>
                        </div>
                        <svg className={`w-5 h-5 text-muted-foreground transition-transform ${showAdvanced ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path></svg>
                      </button>

                      {showAdvanced && (
                        <div className="p-6 pt-0 space-y-6 border-t border-border">
                          
                          {/* Tax Override */}
                          <div className="bg-muted/30 dark:bg-muted/10 border border-border p-4 rounded-lg mt-4">
                            <div className="flex items-center justify-between mb-4">
                              <div>
                                <h4 className="text-sm font-medium text-foreground">Tax Override</h4>
                                <p className="text-xs text-muted-foreground">Override the default {category?.gst_rate}% GST from {category?.name}</p>
                              </div>
                              <button type="button" onClick={() => setFormData({...formData, tax_override: !formData.tax_override})} className={`w-10 h-6 rounded-full transition-all relative cursor-pointer ${formData.tax_override ? 'bg-red-500' : 'bg-muted-foreground/30'}`}>
                                <div className={`w-4 h-4 bg-white rounded-full absolute top-1 transition-all shadow-sm ${formData.tax_override ? 'left-5' : 'left-1'}`}></div>
                              </button>
                            </div>
                            {formData.tax_override && (
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                <div>
                                  <label className="block text-xs text-muted-foreground mb-1">Custom HSN Code</label>
                                  <input type="text" value={formData.override_hsn_code} onChange={e => setFormData({...formData, override_hsn_code: e.target.value})} className="w-full bg-background border border-input text-foreground p-2 rounded-lg text-sm outline-none shadow-xs" />
                                </div>
                                <div>
                                  <label className="block text-xs text-muted-foreground mb-1">Custom GST Rate (%)</label>
                                  <select value={formData.override_gst_rate} onChange={e => setFormData({...formData, override_gst_rate: parseFloat(e.target.value)})} className="w-full bg-background border border-input text-foreground p-2 rounded-lg text-sm outline-none shadow-xs cursor-pointer">
                                    <option value={0} className="bg-background text-foreground">0%</option>
                                    <option value={5} className="bg-background text-foreground">5%</option>
                                    <option value={12} className="bg-background text-foreground">12%</option>
                                    <option value={18} className="bg-background text-foreground">18%</option>
                                    <option value={28} className="bg-background text-foreground">28%</option>
                                  </select>
                                </div>
                              </div>
                            )}
                          </div>

                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div>
                              <label className="block text-sm font-medium text-muted-foreground mb-1.5">SKU Code</label>
                              <input type="text" placeholder="Auto-generated if blank" value={formData.sku} onChange={e => setFormData({ ...formData, sku: e.target.value })} className="w-full bg-background border border-input text-foreground p-2.5 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none text-sm shadow-xs" />
                            </div>
                            <div>
                              <div className="flex items-center justify-between mb-1.5">
                                <label className="block text-sm font-medium text-muted-foreground">Barcode</label>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setScannerTarget('BARCODE');
                                    setIsScannerOpen(true);
                                  }}
                                  className="text-xs text-primary hover:underline flex items-center gap-1 cursor-pointer font-medium"
                                >
                                  <Camera className="w-3 h-3" />
                                  <span>Scan</span>
                                </button>
                              </div>
                              <input type="text" placeholder="Scan or enter barcode" value={formData.barcode} onChange={e => setFormData({ ...formData, barcode: e.target.value })} className="w-full bg-background border border-input text-foreground p-2.5 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none text-sm shadow-xs" />
                            </div>
                          </div>

                          {/* Opening Stock */}
                          <div className="bg-muted/30 dark:bg-muted/10 border border-border rounded-lg p-4 space-y-4">
                            <h4 className="text-sm font-medium text-foreground border-b border-border pb-2">Opening Stock Balance</h4>
                            
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                              <div>
                                <label className="block text-xs text-muted-foreground mb-1">Quantity</label>
                                <input type="number" placeholder="0" value={formData.opening_qty} onChange={e => setFormData({ ...formData, opening_qty: e.target.value })} className="w-full bg-background border border-input text-foreground p-2 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none text-sm shadow-xs" />
                              </div>
                              {complexityLevel > 1 && (
                                <div>
                                  <label className="block text-xs text-muted-foreground mb-1">Godown / Warehouse</label>
                                  <select value={formData.warehouse_id} onChange={e => setFormData({...formData, warehouse_id: e.target.value})} className="w-full bg-background border border-input text-foreground p-2 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none text-sm shadow-xs cursor-pointer">
                                    <option value="" className="bg-background text-foreground">Default Warehouse</option>
                                    {warehouses?.map(w => <option key={w.id} value={w.id} className="bg-background text-foreground">{w.name}</option>)}
                                  </select>
                                </div>
                              )}
                            </div>

                            {(trackBatch || trackSerial) && parseFloat(formData.opening_qty) > 0 && (
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 p-3 bg-muted/40 rounded-lg border border-border">
                                {trackBatch && (
                                  <>
                                    <div>
                                      <label className="block text-xs text-muted-foreground mb-1">Batch Number</label>
                                      <input type="text" value={formData.opening_batch_number} onChange={e => setFormData({...formData, opening_batch_number: e.target.value})} className="w-full bg-background border border-input text-foreground p-1.5 rounded-lg text-sm outline-none shadow-xs" />
                                    </div>
                                    <div>
                                      <label className="block text-xs text-muted-foreground mb-1">Expiry Date</label>
                                      <input type="date" value={formData.opening_expiry_date} onChange={e => setFormData({...formData, opening_expiry_date: e.target.value})} className="w-full bg-background border border-input text-foreground p-1.5 rounded-lg text-sm outline-none shadow-xs" />
                                    </div>
                                  </>
                                )}
                                {trackSerial && (
                                  <div className="col-span-1 sm:col-span-2">
                                    <label className="block text-xs text-muted-foreground mb-1">Serial Number</label>
                                    <input type="text" placeholder="Enter comma separated serials if multiple" value={formData.opening_serial_number} onChange={e => setFormData({...formData, opening_serial_number: e.target.value})} className="w-full bg-background border border-input text-foreground p-1.5 rounded-lg text-sm outline-none shadow-xs" />
                                  </div>
                                )}
                              </div>
                            )}
                          </div>

                          <div>
                            <label className="block text-sm font-medium text-muted-foreground mb-1.5">Description / Notes</label>
                            <textarea rows={2} placeholder="Internal notes about this item..." value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })} className="w-full bg-background border border-input text-foreground p-2.5 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none text-sm resize-none shadow-xs" />
                          </div>
                        </div>
                      )}
                    </div>
                  </>
                )}

                {/* Submit */}
                <div className="flex justify-between items-center pt-2">
                  <Link href={`/inventory/categories/${categoryId}`} className="text-muted-foreground hover:text-foreground text-sm transition-colors">
                    ← Cancel
                  </Link>
                  <button
                    type="submit"
                    disabled={saving}
                    className="bg-primary hover:bg-primary/90 text-primary-foreground px-10 py-3 rounded-lg font-semibold shadow-md transition-all disabled:opacity-50 text-base sm:text-lg cursor-pointer"
                  >
                    {saving ? 'Adding Item...' : 'Add Item'}
                  </button>
                </div>
              </div>

              {/* ──── RIGHT: Live Preview (1 col) ──── */}
              <div className="lg:col-span-1">
                <div className="sticky top-8 space-y-4">

                  {/* Invoice Preview */}
                  <div className="bg-card border border-border rounded-xl shadow-sm overflow-hidden">
                    <div className="bg-muted/50 px-4 py-3 border-b border-border">
                      <p className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">Live Invoice Preview</p>
                    </div>
                    <div className="p-4">
                      <div className="border border-border rounded-lg overflow-hidden bg-background">
                        <div className="bg-muted/40 px-3 py-2 text-xs text-muted-foreground grid grid-cols-4 gap-1 border-b border-border font-medium">
                          <span className="col-span-2">Item</span>
                          <span className="text-right">Rate</span>
                          <span className="text-right">Amt</span>
                        </div>
                        <div className="px-3 py-3 grid grid-cols-4 gap-1 items-start">
                          <div className="col-span-2">
                            <p className="text-foreground font-semibold text-sm truncate">{formData.name || 'Item Name'}</p>
                            <p className="text-muted-foreground text-xs mt-0.5">
                              {formData.alias && <span className="text-foreground/70">({formData.alias}) </span>}
                              {formData.brand && <span>{formData.brand} · </span>}
                              {category?.name || 'Category'}
                            </p>
                            <p className="text-muted-foreground/80 text-xs mt-0.5 font-mono">
                              HSN: {activeHsn || '—'} · GST: {activeGst || 18}%
                            </p>
                          </div>
                          <p className="text-right text-emerald-600 dark:text-emerald-400 font-semibold text-sm">
                            ₹{formData.selling_price ? parseFloat(formData.selling_price).toLocaleString('en-IN', { minimumFractionDigits: 2 }) : '0.00'}
                          </p>
                          <p className="text-right text-foreground font-bold text-sm">
                            ₹{formData.selling_price ? parseFloat(formData.selling_price).toLocaleString('en-IN', { minimumFractionDigits: 2 }) : '0.00'}
                          </p>
                        </div>
                        <div className="border-t border-border px-3 py-2 flex justify-between text-xs">
                          <span className="text-muted-foreground">1 × {formData.unit}</span>
                          <span className="text-muted-foreground font-medium">
                            Tax: ₹{formData.selling_price ? (parseFloat(formData.selling_price) * (parseFloat(activeGst?.toString() || '18') / 100)).toFixed(2) : '0.00'}
                          </span>
                        </div>
                        {parseFloat(formData.purchase_price) > 0 && (
                          <div className="border-t border-border bg-muted/20 px-3 py-2 flex justify-between text-xs font-mono">
                            <span className="text-muted-foreground">Purchase / Cost:</span>
                            <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
                              ₹{parseFloat(formData.purchase_price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Inherited Info */}
                  <div className="bg-card border border-border rounded-xl shadow-sm p-4 space-y-3">
                    <p className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">Auto-Inherited Rules</p>
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">Category</span>
                        <span className="text-blue-600 dark:text-blue-400 font-semibold">{category?.name || '—'}</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">HSN Code</span>
                        <span className={`font-mono font-medium ${formData.tax_override ? 'text-rose-600 dark:text-rose-400' : 'text-foreground'}`}>{activeHsn || '—'}</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">GST Rate</span>
                        <span className={`font-medium ${formData.tax_override ? 'text-rose-600 dark:text-rose-400' : 'text-foreground'}`}>{activeGst || 18}%</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">Sales Ledger</span>
                        <span className="text-foreground truncate max-w-[120px] text-right font-medium">Linked</span>
                      </div>
                    </div>
                    {formData.tax_override ? (
                      <div className="bg-rose-500/10 border border-rose-500/20 rounded-lg p-3 mt-2">
                         <p className="text-xs text-rose-600 dark:text-rose-400">
                          Tax override is enabled. This item will not inherit updates from its category.
                         </p>
                      </div>
                    ) : (
                      <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-3 mt-2">
                        <p className="text-xs text-blue-700 dark:text-blue-300">
                          <svg className="w-3.5 h-3.5 inline mr-1 -mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                          Tax & accounting ledgers are managed automatically via the {category?.name} category.
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Active Features */}
                  <div className="bg-card border border-border rounded-xl shadow-sm p-4">
                    <p className="text-xs text-muted-foreground uppercase tracking-wider font-semibold mb-3">Active Features</p>
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-sm">
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${imeiList.length > 0 ? 'bg-purple-500' : 'bg-muted-foreground/40'}`}></span>
                          <span className={imeiList.length > 0 ? 'text-foreground font-medium' : 'text-muted-foreground'}>IMEI / Serial</span>
                        </div>
                        {imeiList.length > 0 && (
                          <span className="text-[10px] font-mono font-bold bg-purple-500/10 text-purple-600 dark:text-purple-400 px-1.5 py-0.5 rounded">
                            {imeiList.length} items
                          </span>
                        )}
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${Object.keys(attributes).length > 0 ? 'bg-indigo-500' : 'bg-muted-foreground/40'}`}></span>
                          <span className={Object.keys(attributes).length > 0 ? 'text-foreground font-medium' : 'text-muted-foreground'}>Attributes</span>
                        </div>
                        {Object.keys(attributes).length > 0 && (
                          <span className="text-[10px] font-mono font-bold bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 px-1.5 py-0.5 rounded">
                            {Object.keys(attributes).length} active
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-sm">
                        <span className={`w-2 h-2 rounded-full ${trackBatch ? 'bg-emerald-500' : 'bg-muted-foreground/40'}`}></span>
                        <span className={trackBatch ? 'text-foreground font-medium' : 'text-muted-foreground'}>Batch Tracking</span>
                      </div>
                      <div className="flex items-center gap-2 text-sm">
                        <span className={`w-2 h-2 rounded-full ${trackSerial || imeiList.length > 0 ? 'bg-emerald-500' : 'bg-muted-foreground/40'}`}></span>
                        <span className={trackSerial || imeiList.length > 0 ? 'text-foreground font-medium' : 'text-muted-foreground'}>Serial Tracking</span>
                      </div>
                      <div className="flex items-center gap-2 text-sm">
                        <span className={`w-2 h-2 rounded-full ${formData.alternate_unit ? 'bg-emerald-500' : 'bg-muted-foreground/40'}`}></span>
                        <span className={formData.alternate_unit ? 'text-foreground font-medium' : 'text-muted-foreground'}>Multi-unit Pricing</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </form>

          {/* Barcode & IMEI Scanner Modal */}
          {isScannerOpen && (
            <BarcodeScannerModal
              isOpen={isScannerOpen}
              onClose={() => setIsScannerOpen(false)}
              onScan={handleBarcodeScanned}
              title={scannerTarget === 'BARCODE' ? "Scan Product Barcode" : "Scan IMEI / Serial Barcode"}
              continuous={scannerTarget === 'IMEI'}
            />
          )}

          {/* Add Custom Attribute / Specification Modal */}
          {showAddCustomModal && (
            <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
              <div className="bg-card border border-border rounded-xl shadow-xl w-full max-w-sm p-5 space-y-4 animate-in fade-in zoom-in-95">
                <div className="flex items-center justify-between border-b border-border pb-3">
                  <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
                    <Tag className="w-4 h-4 text-primary" />
                    <span>Add Product Feature / Spec</span>
                  </h3>
                  <button
                    type="button"
                    onClick={() => setShowAddCustomModal(false)}
                    className="text-muted-foreground hover:text-foreground p-1 rounded cursor-pointer"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                <div className="space-y-3">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Feature Name</label>
                    <input
                      type="text"
                      placeholder="e.g. Storage, RAM, Battery, Processor"
                      value={customKeyInput}
                      onChange={e => setCustomKeyInput(e.target.value)}
                      className="w-full bg-background border border-input text-foreground px-3 py-2 rounded-lg text-xs outline-none focus:ring-2 focus:ring-primary shadow-xs"
                      autoFocus
                    />
                  </div>

                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Feature Value</label>
                    <input
                      type="text"
                      placeholder="e.g. 256GB, 12GB, 5000mAh, Snapdragon 8 Gen 3"
                      value={customValInput}
                      onChange={e => setCustomValInput(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          handleAddCustomAttribute(customKeyInput, customValInput);
                        }
                      }}
                      className="w-full bg-background border border-input text-foreground px-3 py-2 rounded-lg text-xs outline-none focus:ring-2 focus:ring-primary shadow-xs"
                    />
                  </div>
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
                  <button
                    type="button"
                    onClick={() => setShowAddCustomModal(false)}
                    className="px-3 py-1.5 rounded-lg border border-input text-muted-foreground hover:text-foreground text-xs cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => handleAddCustomAttribute(customKeyInput, customValInput)}
                    disabled={!customKeyInput.trim() || !customValInput.trim()}
                    className="px-4 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-bold disabled:opacity-50 cursor-pointer"
                  >
                    Add Feature
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
