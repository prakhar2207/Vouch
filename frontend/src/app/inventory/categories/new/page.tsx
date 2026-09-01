"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';

export default function NewCategoryPage() {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [complexityLevel, setComplexityLevel] = useState(1);
  const [enableLedgerMapping, setEnableLedgerMapping] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    hsn_code: '',
    gst_rate: 18,
    sales_ledger_id: '',
    purchase_ledger_id: '',
  });
  const [ledgers, setLedgers] = useState<any[]>([]);

  useEffect(() => {
    if (!isAuthenticated()) { router.push('/login'); return; }
    fetchLedgers();
  }, [router]);

  const fetchLedgers = async () => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const comp = compRes.data.data[0];
      if (!comp) return;
      setComplexityLevel(comp.settings?.complexity_level || 1);
      setEnableLedgerMapping(comp.settings?.enable_ledger_mapping || false);

      const ledRes = await axios.get(`${API_BASE_URL}/api/v1/ledgers/${comp.id}/`, { headers });
      setLedgers(ledRes.data.data || []);
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
      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const companyId = compRes.data.data[0]?.id;

      const payload: any = { ...formData };
      if (formData.sales_ledger_id === '') delete payload.sales_ledger_id;
      if (formData.purchase_ledger_id === '') delete payload.purchase_ledger_id;

      const res = await axios.post(`${API_BASE_URL}/api/v1/inventory/categories/${companyId}/`, payload, { headers });
      if (res.data.success) {
        alert(`Category "${res.data.data.name}" created successfully!`);
        router.push('/inventory');
      } else {
        alert('Error: ' + res.data.error);
      }
    } catch (err: any) {
      alert('Error: ' + (err.response?.data?.error || err.message));
    } finally {
      setSaving(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6 max-w-2xl mx-auto pb-12">
        
        {/* Header */}
        <div className="flex items-center gap-4 border-b border-border pb-4">
          <Link href="/inventory" className="text-gray-400 hover:text-white transition-colors">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
          </Link>
          <div>
            <h1 className="text-3xl font-bold">New Category</h1>
            <p className="text-gray-400 mt-1 text-sm">Create a product category like V-Belt, Bearings, Phones, etc.</p>
          </div>
        </div>

        <form onSubmit={handleSave} className="bg-card border border-border rounded-xl shadow-sm p-6 space-y-6">
          
          {/* Category Name */}
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1.5">Category Name *</label>
            <input
              required
              type="text"
              placeholder="e.g. V-Belt, Bearings, Mobile Phones"
              value={formData.name}
              onChange={e => setFormData({ ...formData, name: e.target.value })}
              className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all text-lg"
            />
          </div>

          {/* Row 2: HSN and unified GST Rate (with explicit breakdown) */}
          <div className="grid grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">HSN Code</label>
              <input
                type="text"
                placeholder="e.g. 8471"
                value={formData.hsn_code}
                onChange={e => setFormData({ ...formData, hsn_code: e.target.value })}
                className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
              />
              <p className="text-xs text-gray-500 mt-1">Harmonized System of Nomenclature code</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">Total GST Rate (%)</label>
              <select
                value={formData.gst_rate}
                onChange={e => setFormData({ ...formData, gst_rate: Number(e.target.value) })}
                className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
              >
                <option value={0}>0% (Exempt)</option>
                <option value={5}>5%</option>
                <option value={12}>12%</option>
                <option value={18}>18%</option>
                <option value={28}>28%</option>
              </select>
              
              {/* GST Visual Breakdown */}
              <div className="mt-3 bg-zinc-900/50 border border-zinc-800 rounded-lg p-3">
                <p className="text-xs text-gray-500 mb-2">System automatically applies tax based on customer state:</p>
                <div className="grid grid-cols-2 gap-2 text-sm text-gray-300">
                    <div className="bg-zinc-800/80 px-2 py-1.5 rounded flex justify-between border border-zinc-700/50">
                        <span className="text-gray-400">CGST (Local)</span>
                        <span className="font-medium text-white">{(formData.gst_rate / 2).toFixed(1)}%</span>
                    </div>
                    <div className="bg-zinc-800/80 px-2 py-1.5 rounded flex justify-between border border-zinc-700/50">
                        <span className="text-gray-400">SGST (Local)</span>
                        <span className="font-medium text-white">{(formData.gst_rate / 2).toFixed(1)}%</span>
                    </div>
                    <div className="col-span-2 bg-blue-900/10 px-2 py-1.5 rounded flex justify-between border border-blue-800/30">
                        <span className="text-blue-400">IGST (Inter-state)</span>
                        <span className="font-medium text-blue-300">{formData.gst_rate.toFixed(1)}%</span>
                    </div>
                </div>
              </div>
            </div>
          </div>

          <div className="border-t border-zinc-800 pt-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-lg font-medium text-white">Ledger Mapping (Auto-Accounting)</h3>
                <p className="text-xs text-gray-500 mt-1">Advanced users can map specific income/expense accounts.</p>
              </div>
              <button 
                type="button" 
                onClick={() => setEnableLedgerMapping(!enableLedgerMapping)} 
                className={`w-12 h-7 rounded-full transition-all relative ${enableLedgerMapping ? 'bg-blue-600' : 'bg-zinc-700'}`}
              >
                <div className={`w-5 h-5 bg-white rounded-full absolute top-1 transition-all ${enableLedgerMapping ? 'left-6' : 'left-1'}`}></div>
              </button>
            </div>
            
            {enableLedgerMapping && (
              <div className="grid grid-cols-2 gap-6 mt-6 bg-zinc-900/30 p-4 rounded-xl border border-zinc-800/50">
                <div>
                  <label className="block text-sm font-medium text-gray-400 mb-1.5">Sales Ledger</label>
                  <select
                    value={formData.sales_ledger_id || ''}
                    onChange={e => setFormData({ ...formData, sales_ledger_id: e.target.value })}
                    className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                  >
                    <option value="">-- Default Sales Account --</option>
                    {ledgers.filter(l => l.group_name && l.group_name.includes('Sales')).map(l => (
                      <option key={l.id} value={l.id}>{l.name}</option>
                    ))}
                  </select>
                  <p className="text-xs text-gray-500 mt-1">Income account for selling items in this category</p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-400 mb-1.5">Purchase Ledger</label>
                  <select
                    value={formData.purchase_ledger_id || ''}
                    onChange={e => setFormData({ ...formData, purchase_ledger_id: e.target.value })}
                    className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                  >
                    <option value="">-- Default Purchase Account --</option>
                    {ledgers.filter(l => l.group_name && l.group_name.includes('Purchase')).map(l => (
                      <option key={l.id} value={l.id}>{l.name}</option>
                    ))}
                  </select>
                  <p className="text-xs text-gray-500 mt-1">Expense account for buying items in this category</p>
                </div>
              </div>
            )}
          </div>

          {/* Preview */}
          {formData.name && (
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-5">
              <p className="text-xs text-gray-500 uppercase tracking-wider font-medium mb-3">Preview</p>
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 bg-blue-500/10 text-blue-400 rounded-full flex items-center justify-center">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
                </div>
                <div>
                  <p className="text-white font-bold text-lg">{formData.name}</p>
                  <p className="text-gray-500 text-sm">HSN: {formData.hsn_code || '—'} &middot; GST: {formData.gst_rate}%</p>
                </div>
              </div>
            </div>
          )}


          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={saving}
              className="bg-blue-600 hover:bg-blue-700 text-white px-8 py-3 rounded-lg font-semibold shadow-lg transition-all disabled:opacity-50"
            >
              {saving ? 'Creating...' : 'Create Category'}
            </button>
          </div>
        </form>
      </div>
    </DashboardLayout>
  );
}
