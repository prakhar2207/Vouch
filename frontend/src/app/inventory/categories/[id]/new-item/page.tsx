"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';

export default function NewItemInCategoryPage() {
  const router = useRouter();
  const params = useParams();
  const categoryId = params.id as string;

  const [saving, setSaving] = useState(false);
  const [category, setCategory] = useState<any>(null);
  const [companyId, setCompanyId] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);

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
  }, [router, categoryId]);

  const fetchData = async () => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const comp = compRes.data.data[0];
      if (!comp) return;
      setCompanyId(comp.id);
      setComplexityLevel(comp.settings?.complexity_level || 1);
      setEnableAdvancedItemCreation(comp.settings?.enable_advanced_item_creation || false);

      const catRes = await axios.get(`${API_BASE_URL}/api/v1/inventory/categories/${comp.id}/`, { headers });
      const cat = (catRes.data.data || []).find((c: any) => c.id === categoryId);
      setCategory(cat);
      
      const whRes = await axios.get(`${API_BASE_URL}/api/v1/inventory/warehouses/${comp.id}/`, { headers }).catch(() => null);
      if (whRes && whRes.data) {
        setWarehouses(whRes.data.data || []);
      }
    } catch (err) {
      console.error(err);
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
        selling_price: parseFloat(formData.selling_price) || 0,
        wholesaler_price: parseFloat(formData.wholesaler_price) || 0,
        min_selling_price: parseFloat(formData.min_selling_price) || 0,
        purchase_price: parseFloat(formData.purchase_price) || 0,
        opening_qty: parseFloat(formData.opening_qty) || 0,
        reorder_level: parseFloat(formData.reorder_level) || 0,
        conversion_factor: parseFloat(formData.conversion_factor.toString()) || 1,
        category_id: categoryId,
        track_batches: trackBatch,
        track_serial_numbers: trackSerial,
      };

      const res = await axios.post(`${API_BASE_URL}/api/v1/inventory/products/${companyId}/`, payload, { headers });
      if (res.data.success) {
        alert(`Item "${res.data.data.name}" added to ${category?.name}!`);
        router.push(`/inventory/categories/${categoryId}`);
      } else {
        alert('Error: ' + res.data.error);
      }
    } catch (err: any) {
      alert('Error: ' + (err.response?.data?.error || err.message));
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
            <Link href={`/inventory/categories/${categoryId}`} className="text-gray-400 hover:text-white transition-colors">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
            </Link>
            <div>
              <h1 className="text-3xl font-bold">Add New Item</h1>
              <p className="text-gray-400 mt-1 text-sm">Adding to <span className="text-blue-400 font-medium">{category?.name || '...'}</span></p>
            </div>
          </div>

          <form onSubmit={handleSave}>
            <div className="grid grid-cols-3 gap-6">

              {/* ──── LEFT: Form (2 cols) ──── */}
              <div className="col-span-2 space-y-6">

                {/* ───── ZONE 1: THE ESSENTIALS ───── */}
                <div className="bg-card border border-border rounded-xl shadow-sm p-6">
                  <div className="flex items-center gap-2 mb-5">
                    <div className="w-8 h-8 bg-blue-500/10 text-blue-400 rounded-lg flex items-center justify-center text-sm font-bold">1</div>
                    <h2 className="text-lg font-semibold text-white">Essentials</h2>
                  </div>

                  <div className="space-y-5">
                    <div className="grid grid-cols-2 gap-4">
                      {/* Item Name */}
                      <div>
                        <label className="block text-sm font-medium text-gray-400 mb-1.5">Item Name / Size *</label>
                        <input
                          required
                          type="text"
                          autoFocus
                          placeholder="e.g. A-32, iPhone 15 Pro"
                          value={formData.name}
                          onChange={e => setFormData({ ...formData, name: e.target.value })}
                          className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all text-lg"
                        />
                      </div>
                      
                      {/* Alias */}
                      <div>
                        <label className="block text-sm font-medium text-gray-400 mb-1.5">Alias / Short Name</label>
                        <input
                          type="text"
                          placeholder="Alternative search name"
                          value={formData.alias}
                          onChange={e => setFormData({ ...formData, alias: e.target.value })}
                          className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all text-lg"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      {/* Brand */}
                      <div>
                        <label className="block text-sm font-medium text-gray-400 mb-1.5">Brand</label>
                        <input
                          type="text"
                          placeholder="e.g. PIX, SKF, Samsung"
                          value={formData.brand}
                          onChange={e => setFormData({ ...formData, brand: e.target.value })}
                          className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                        />
                      </div>
                    </div>

                    {/* Unit Selector */}
                    <div>
                      <label className="block text-sm font-medium text-gray-400 mb-2">Primary Unit of Measure</label>
                      <div className="grid grid-cols-4 gap-2">
                        {units.map(u => (
                          <button
                            key={u.value}
                            type="button"
                            onClick={() => setFormData({ ...formData, unit: u.value })}
                            className={`p-2.5 rounded-lg border text-sm font-medium transition-all flex items-center justify-center gap-1.5 ${
                              formData.unit === u.value
                                ? 'bg-blue-600/10 border-blue-500 text-blue-400'
                                : 'bg-zinc-900 border-zinc-700 text-gray-400 hover:border-zinc-500'
                            }`}
                          >
                            <span>{u.icon}</span>
                            <span>{u.label}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                    {/* Simplified Pricing & Stock (Only visible if advanced mode is disabled) */}
                    {!enableAdvancedItemCreation && (
                      <div className="grid grid-cols-2 gap-4 mt-6 pt-6 border-t border-zinc-800">
                        <div>
                          <label className="block text-sm font-medium text-blue-400 mb-1.5">Retail Price (₹) *</label>
                          <input
                            required
                            type="number"
                            step="0.01"
                            placeholder="0.00"
                            value={formData.selling_price}
                            onChange={e => setFormData({ ...formData, selling_price: e.target.value })}
                            className="w-full bg-zinc-900 border border-blue-500/30 text-green-400 font-bold p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                          />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-400 mb-1.5">Opening Quantity (Optional)</label>
                          <input
                            type="number"
                            placeholder="0"
                            value={formData.opening_qty}
                            onChange={e => setFormData({ ...formData, opening_qty: e.target.value })}
                            className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                          />
                        </div>
                      </div>
                    )}
                  </div>

                {/* ───── ZONE 2 & 3: ADVANCED (Conditionally rendered) ───── */}
                {enableAdvancedItemCreation && (
                  <>
                    <div className="bg-card border border-border rounded-xl shadow-sm p-6">
                      <div className="flex items-center gap-2 mb-5">
                        <div className="w-8 h-8 bg-purple-500/10 text-purple-400 rounded-lg flex items-center justify-center text-sm font-bold">2</div>
                        <h2 className="text-lg font-semibold text-white">Advanced Pricing & Options</h2>
                      </div>

                      {/* Pricing Matrix */}
                      <div className="mb-6">
                        <label className="block text-sm font-medium text-gray-400 mb-3">Unified Pricing Matrix</label>
                        <div className="grid grid-cols-4 gap-3">
                          <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-3">
                            <p className="text-xs text-gray-500 mb-1">Purchase Price</p>
                            <div className="flex items-center gap-1">
                              <span className="text-gray-500">₹</span>
                              <input type="number" step="0.01" placeholder="0.00" value={formData.purchase_price} onChange={e => setFormData({ ...formData, purchase_price: e.target.value })} className="bg-transparent text-white w-full outline-none font-bold" />
                            </div>
                          </div>
                          <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-3">
                            <p className="text-xs text-gray-500 mb-1">Min Sell Price</p>
                            <div className="flex items-center gap-1">
                              <span className="text-gray-500">₹</span>
                              <input type="number" step="0.01" placeholder="0.00" value={formData.min_selling_price} onChange={e => setFormData({ ...formData, min_selling_price: e.target.value })} className="bg-transparent text-white w-full outline-none font-bold" />
                            </div>
                          </div>
                          <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-3">
                            <p className="text-xs text-gray-500 mb-1">Wholesale Price</p>
                            <div className="flex items-center gap-1">
                              <span className="text-gray-500">₹</span>
                              <input type="number" step="0.01" placeholder="0.00" value={formData.wholesaler_price} onChange={e => setFormData({ ...formData, wholesaler_price: e.target.value })} className="bg-transparent text-white w-full outline-none font-bold" />
                            </div>
                          </div>
                          <div className="bg-zinc-900 border border-blue-500/30 rounded-lg p-3 ring-1 ring-blue-500/20">
                            <p className="text-xs text-blue-400 font-medium mb-1">Retail Price *</p>
                            <div className="flex items-center gap-1">
                              <span className="text-blue-400">₹</span>
                              <input required type="number" step="0.01" placeholder="0.00" value={formData.selling_price} onChange={e => setFormData({ ...formData, selling_price: e.target.value })} className="bg-transparent text-green-400 w-full outline-none font-bold" />
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Toggles */}
                      <div className="space-y-3">
                        {complexityLevel > 1 && (
                          <>
                            <div className="flex items-center justify-between bg-zinc-900 border border-zinc-700 rounded-lg p-4">
                              <div>
                                <p className="text-white font-medium text-sm">Track Batches & Expiry Dates</p>
                                <p className="text-gray-500 text-xs mt-0.5">Enable for perishable goods, medicines, food items</p>
                              </div>
                              <button type="button" onClick={() => setTrackBatch(!trackBatch)} className={`w-12 h-7 rounded-full transition-all relative ${trackBatch ? 'bg-blue-600' : 'bg-zinc-700'}`}>
                                <div className={`w-5 h-5 bg-white rounded-full absolute top-1 transition-all ${trackBatch ? 'left-6' : 'left-1'}`}></div>
                              </button>
                            </div>
                            
                            <div className="flex items-center justify-between bg-zinc-900 border border-zinc-700 rounded-lg p-4">
                              <div>
                                <p className="text-white font-medium text-sm">Serial Number / IMEI Tracking</p>
                                <p className="text-gray-500 text-xs mt-0.5">Enable for phones, laptops, electronics with unique serial numbers</p>
                              </div>
                              <button type="button" onClick={() => setTrackSerial(!trackSerial)} className={`w-12 h-7 rounded-full transition-all relative ${trackSerial ? 'bg-blue-600' : 'bg-zinc-700'}`}>
                                <div className={`w-5 h-5 bg-white rounded-full absolute top-1 transition-all ${trackSerial ? 'left-6' : 'left-1'}`}></div>
                              </button>
                            </div>
                          </>
                        )}
                        
                        <div className="flex items-start gap-3 bg-zinc-900 border border-zinc-700 rounded-lg p-4">
                          <input 
                            type="checkbox" 
                            id="alt_unit"
                            checked={!!formData.alternate_unit}
                            onChange={(e) => setFormData({...formData, alternate_unit: e.target.checked ? 'BOX' : '', conversion_factor: 1})}
                            className="mt-1 w-4 h-4 rounded bg-zinc-800 border-zinc-600 text-blue-600"
                          />
                          <div className="flex-1">
                            <label htmlFor="alt_unit" className="text-white font-medium text-sm block cursor-pointer">Sell this item in multiple packaging types</label>
                            <p className="text-gray-500 text-xs mt-0.5 mb-3">e.g., Allow selling in both Pieces and Boxes</p>
                            {formData.alternate_unit && (
                              <div className="flex items-center gap-3 bg-zinc-800 p-3 rounded border border-zinc-700">
                                <span className="text-sm">1</span>
                                <select 
                                  value={formData.alternate_unit}
                                  onChange={e => setFormData({...formData, alternate_unit: e.target.value})}
                                  className="bg-zinc-900 text-white text-sm p-1.5 rounded border border-zinc-600 outline-none"
                                >
                                  <option value="BOX">BOX</option>
                                  <option value="SET">SET</option>
                                  <option value="DOZ">DOZEN</option>
                                  <option value="PACK">PACK</option>
                                </select>
                                <span className="text-sm text-gray-400">=</span>
                                <input 
                                  type="number" step="0.01" 
                                  value={formData.conversion_factor}
                                  onChange={e => setFormData({...formData, conversion_factor: parseFloat(e.target.value) || 1})}
                                  className="bg-zinc-900 text-white text-sm p-1.5 rounded border border-zinc-600 outline-none w-20 text-center" 
                                />
                                <span className="text-sm">{formData.unit}</span>
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
                        className="w-full p-5 flex items-center justify-between hover:bg-zinc-800/30 transition-colors"
                      >
                        <div className="flex items-center gap-2">
                          <div className="w-8 h-8 bg-zinc-700/50 text-gray-400 rounded-lg flex items-center justify-center text-sm font-bold">3</div>
                          <h2 className="text-lg font-semibold text-gray-400">Inventory & Tax Details</h2>
                          <span className="text-xs text-gray-600 bg-zinc-800 px-2 py-0.5 rounded ml-1">Optional</span>
                        </div>
                        <svg className={`w-5 h-5 text-gray-500 transition-transform ${showAdvanced ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path></svg>
                      </button>

                      {showAdvanced && (
                        <div className="p-6 pt-0 space-y-6 border-t border-zinc-800">
                          
                          {/* Tax Override */}
                          <div className="bg-zinc-900/50 border border-zinc-800 p-4 rounded-lg mt-4">
                            <div className="flex items-center justify-between mb-4">
                              <div>
                                <h4 className="text-sm font-medium text-white">Tax Override</h4>
                                <p className="text-xs text-gray-500">Override the default {category?.gst_rate}% GST from {category?.name}</p>
                              </div>
                              <button type="button" onClick={() => setFormData({...formData, tax_override: !formData.tax_override})} className={`w-10 h-6 rounded-full transition-all relative ${formData.tax_override ? 'bg-red-500/80' : 'bg-zinc-700'}`}>
                                <div className={`w-4 h-4 bg-white rounded-full absolute top-1 transition-all ${formData.tax_override ? 'left-5' : 'left-1'}`}></div>
                              </button>
                            </div>
                            {formData.tax_override && (
                              <div className="grid grid-cols-2 gap-4">
                                <div>
                                  <label className="block text-xs text-gray-400 mb-1">Custom HSN Code</label>
                                  <input type="text" value={formData.override_hsn_code} onChange={e => setFormData({...formData, override_hsn_code: e.target.value})} className="w-full bg-zinc-800 border border-zinc-700 text-white p-2 rounded text-sm outline-none" />
                                </div>
                                <div>
                                  <label className="block text-xs text-gray-400 mb-1">Custom GST Rate (%)</label>
                                  <select value={formData.override_gst_rate} onChange={e => setFormData({...formData, override_gst_rate: parseFloat(e.target.value)})} className="w-full bg-zinc-800 border border-zinc-700 text-white p-2 rounded text-sm outline-none">
                                    <option value={0}>0%</option>
                                    <option value={5}>5%</option>
                                    <option value={12}>12%</option>
                                    <option value={18}>18%</option>
                                    <option value={28}>28%</option>
                                  </select>
                                </div>
                              </div>
                            )}
                          </div>

                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <label className="block text-sm font-medium text-gray-400 mb-1.5">SKU Code</label>
                              <input type="text" placeholder="Auto-generated if blank" value={formData.sku} onChange={e => setFormData({ ...formData, sku: e.target.value })} className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none text-sm" />
                            </div>
                            <div>
                              <label className="block text-sm font-medium text-gray-400 mb-1.5">Barcode</label>
                              <input type="text" placeholder="Scan or enter barcode" value={formData.barcode} onChange={e => setFormData({ ...formData, barcode: e.target.value })} className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none text-sm" />
                            </div>
                          </div>

                          {/* Opening Stock */}
                          <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-4 space-y-4">
                            <h4 className="text-sm font-medium text-white border-b border-zinc-800 pb-2">Opening Stock Balance</h4>
                            
                            <div className="grid grid-cols-2 gap-4">
                              <div>
                                <label className="block text-xs text-gray-400 mb-1">Quantity</label>
                                <input type="number" placeholder="0" value={formData.opening_qty} onChange={e => setFormData({ ...formData, opening_qty: e.target.value })} className="w-full bg-zinc-800 border border-zinc-700 text-white p-2 rounded focus:ring-2 focus:ring-blue-500 outline-none text-sm" />
                              </div>
                              {complexityLevel > 1 && (
                                <div>
                                  <label className="block text-xs text-gray-400 mb-1">Godown / Warehouse</label>
                                  <select value={formData.warehouse_id} onChange={e => setFormData({...formData, warehouse_id: e.target.value})} className="w-full bg-zinc-800 border border-zinc-700 text-white p-2 rounded focus:ring-2 focus:ring-blue-500 outline-none text-sm">
                                    <option value="">Default Warehouse</option>
                                    {warehouses?.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                                  </select>
                                </div>
                              )}
                            </div>

                            {(trackBatch || trackSerial) && parseFloat(formData.opening_qty) > 0 && (
                              <div className="grid grid-cols-2 gap-4 p-3 bg-zinc-800/50 rounded border border-zinc-700">
                                {trackBatch && (
                                  <>
                                    <div>
                                      <label className="block text-xs text-gray-400 mb-1">Batch Number</label>
                                      <input type="text" value={formData.opening_batch_number} onChange={e => setFormData({...formData, opening_batch_number: e.target.value})} className="w-full bg-zinc-900 border border-zinc-700 text-white p-1.5 rounded text-sm outline-none" />
                                    </div>
                                    <div>
                                      <label className="block text-xs text-gray-400 mb-1">Expiry Date</label>
                                      <input type="date" value={formData.opening_expiry_date} onChange={e => setFormData({...formData, opening_expiry_date: e.target.value})} className="w-full bg-zinc-900 border border-zinc-700 text-white p-1.5 rounded text-sm outline-none" />
                                    </div>
                                  </>
                                )}
                                {trackSerial && (
                                  <div className="col-span-2">
                                    <label className="block text-xs text-gray-400 mb-1">Serial Number</label>
                                    <input type="text" placeholder="Enter comma separated serials if multiple" value={formData.opening_serial_number} onChange={e => setFormData({...formData, opening_serial_number: e.target.value})} className="w-full bg-zinc-900 border border-zinc-700 text-white p-1.5 rounded text-sm outline-none" />
                                  </div>
                                )}
                              </div>
                            )}
                          </div>

                          <div>
                            <label className="block text-sm font-medium text-gray-400 mb-1.5">Description / Notes</label>
                            <textarea rows={2} placeholder="Internal notes about this item..." value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })} className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none text-sm resize-none" />
                          </div>
                        </div>
                      )}
                    </div>
                  </>
                )}

                {/* Submit */}
                <div className="flex justify-between items-center">
                  <Link href={`/inventory/categories/${categoryId}`} className="text-gray-400 hover:text-white text-sm transition-colors">
                    ← Cancel
                  </Link>
                  <button
                    type="submit"
                    disabled={saving}
                    className="bg-blue-600 hover:bg-blue-700 text-white px-10 py-3 rounded-lg font-semibold shadow-lg transition-all disabled:opacity-50 text-lg"
                  >
                    {saving ? 'Adding Item...' : 'Add Item'}
                  </button>
                </div>
              </div>

              {/* ──── RIGHT: Live Preview (1 col) ──── */}
              <div className="col-span-1">
                <div className="sticky top-8 space-y-4">

                  {/* Invoice Preview */}
                  <div className="bg-card border border-border rounded-xl shadow-sm overflow-hidden">
                    <div className="bg-zinc-900/80 px-4 py-3 border-b border-zinc-800">
                      <p className="text-xs text-gray-500 uppercase tracking-wider font-medium">Live Invoice Preview</p>
                    </div>
                    <div className="p-4">
                      <div className="border border-zinc-800 rounded-lg overflow-hidden">
                        <div className="bg-zinc-900/50 px-3 py-2 text-xs text-gray-500 grid grid-cols-4 gap-1 border-b border-zinc-800">
                          <span className="col-span-2">Item</span>
                          <span className="text-right">Rate</span>
                          <span className="text-right">Amt</span>
                        </div>
                        <div className="px-3 py-3 grid grid-cols-4 gap-1 items-start">
                          <div className="col-span-2">
                            <p className="text-white font-medium text-sm truncate">{formData.name || 'Item Name'}</p>
                            <p className="text-gray-500 text-xs mt-0.5">
                              {formData.alias && <span className="text-gray-400">({formData.alias}) </span>}
                              {formData.brand && <span>{formData.brand} · </span>}
                              {category?.name || 'Category'}
                            </p>
                            <p className="text-gray-600 text-xs mt-0.5">
                              HSN: {activeHsn || '—'} · GST: {activeGst || 18}%
                            </p>
                          </div>
                          <p className="text-right text-green-400 font-medium text-sm">
                            ₹{formData.selling_price ? parseFloat(formData.selling_price).toLocaleString('en-IN', { minimumFractionDigits: 2 }) : '0.00'}
                          </p>
                          <p className="text-right text-white font-bold text-sm">
                            ₹{formData.selling_price ? parseFloat(formData.selling_price).toLocaleString('en-IN', { minimumFractionDigits: 2 }) : '0.00'}
                          </p>
                        </div>
                        <div className="border-t border-zinc-800 px-3 py-2 flex justify-between text-xs">
                          <span className="text-gray-500">1 × {formData.unit}</span>
                          <span className="text-gray-400">
                            Tax: ₹{formData.selling_price ? (parseFloat(formData.selling_price) * (parseFloat(activeGst?.toString() || '18') / 100)).toFixed(2) : '0.00'}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Inherited Info */}
                  <div className="bg-card border border-border rounded-xl shadow-sm p-4 space-y-3">
                    <p className="text-xs text-gray-500 uppercase tracking-wider font-medium">Auto-Inherited Rules</p>
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-500">Category</span>
                        <span className="text-blue-400 font-medium">{category?.name || '—'}</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-500">HSN Code</span>
                        <span className={`font-mono ${formData.tax_override ? 'text-red-400' : 'text-gray-300'}`}>{activeHsn || '—'}</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-500">GST Rate</span>
                        <span className={formData.tax_override ? 'text-red-400' : 'text-gray-300'}>{activeGst || 18}%</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-500">Sales Ledger</span>
                        <span className="text-gray-300 truncate max-w-[120px] text-right">Linked</span>
                      </div>
                    </div>
                    {formData.tax_override ? (
                      <div className="bg-red-500/5 border border-red-500/20 rounded-lg p-3 mt-2">
                         <p className="text-xs text-red-400">
                          Tax override is enabled. This item will not inherit updates from its category.
                         </p>
                      </div>
                    ) : (
                      <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-3 mt-2">
                        <p className="text-xs text-blue-300">
                          <svg className="w-3.5 h-3.5 inline mr-1 -mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                          Tax & accounting ledgers are managed automatically via the {category?.name} category.
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Active Features */}
                  <div className="bg-card border border-border rounded-xl shadow-sm p-4">
                    <p className="text-xs text-gray-500 uppercase tracking-wider font-medium mb-3">Active Features</p>
                    <div className="space-y-2">
                      <div className="flex items-center gap-2 text-sm">
                        <span className={`w-2 h-2 rounded-full ${trackBatch ? 'bg-green-400' : 'bg-zinc-600'}`}></span>
                        <span className={trackBatch ? 'text-white' : 'text-gray-600'}>Batch Tracking</span>
                      </div>
                      <div className="flex items-center gap-2 text-sm">
                        <span className={`w-2 h-2 rounded-full ${trackSerial ? 'bg-green-400' : 'bg-zinc-600'}`}></span>
                        <span className={trackSerial ? 'text-white' : 'text-gray-600'}>Serial Tracking</span>
                      </div>
                      <div className="flex items-center gap-2 text-sm">
                        <span className={`w-2 h-2 rounded-full ${formData.alternate_unit ? 'bg-green-400' : 'bg-zinc-600'}`}></span>
                        <span className={formData.alternate_unit ? 'text-white' : 'text-gray-600'}>Multi-unit Pricing</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </form>
        </div>
      </div>
    </DashboardLayout>
  );
}
