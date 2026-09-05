"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import StateSelect from '@/components/StateSelect';
import { useToast } from '@/context/ToastContext';

export default function NewSupplierPage() {
  const router = useRouter();
  const { toast } = useToast();
  const [companyId, setCompanyId] = useState('');
  const [saving, setSaving] = useState(false);
  
  const [formData, setFormData] = useState({
    name: '',
    gstin: '',
    state_code: '',
    phone: '',
    email: '',
    address: '',
    discount_percent: ''
  });

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login');
      return;
    }
    const token = getAccessToken();
    const headers = { Authorization: `Bearer ${token}` };
    axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers }).then(res => {
      setCompanyId(res.data.data[0]?.id);
    });
  }, [router]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const token = getAccessToken();
      await axios.post(`${API_BASE_URL}/api/v1/ledgers/${companyId}/`, {
          ...formData,
          discount_percent: formData.discount_percent ? parseFloat(formData.discount_percent) : 0,
          group_name: 'Creditors', // Maps to Sundry Creditors
          ledger_type: 'SUPPLIER'
      }, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success("Supplier created successfully!", `"${formData.name}" has been saved.`);
      router.push('/purchases/new');
    } catch (err: any) {
      toast.error("Failed to create supplier", err.response?.data?.error || err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="flex items-center gap-4 border-b border-border pb-4">
          <Link href="/purchases/new" className="text-gray-400 hover:text-white transition-colors">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
          </Link>
          <h1 className="text-3xl font-bold">New Supplier</h1>
        </div>
        
        <form onSubmit={handleSave} className="bg-card border border-border rounded-xl shadow-sm p-6 space-y-6">
          <div className="grid grid-cols-2 gap-6">
            <div className="col-span-2">
              <label className="block text-sm font-medium text-gray-400 mb-1.5">Supplier / Company Name *</label>
              <input required type="text" value={formData.name} onChange={e => setFormData({...formData, name: e.target.value})} className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all" />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">GSTIN</label>
              <input type="text" placeholder="15-digit GSTIN" value={formData.gstin} onChange={e => setFormData({...formData, gstin: e.target.value})} className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all" />
            </div>
            
            <div>
              <StateSelect
                value={formData.state_code}
                onChange={(code) => setFormData({...formData, state_code: code})}
                label="State / Union Territory"
                placeholder="Search state by name or code..."
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">Email Address</label>
              <input type="email" value={formData.email} onChange={e => setFormData({...formData, email: e.target.value})} className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all" />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">Phone Number</label>
              <input type="text" value={formData.phone} onChange={e => setFormData({...formData, phone: e.target.value})} className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all" />
            </div>

            {/* Default Supplier Discount */}
            <div className="col-span-2 bg-zinc-900/50 border border-zinc-800 p-4 rounded-xl space-y-2">
              <div className="flex justify-between items-center">
                <label className="block text-sm font-semibold text-gray-200">
                  Default Discount (%)
                </label>
                <span className="text-[11px] text-red-400 bg-red-500/10 border border-red-500/20 px-2 py-0.5 rounded font-mono">
                  Default Discount Rate
                </span>
              </div>
              <div className="relative">
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  placeholder="e.g. 5.00"
                  value={formData.discount_percent}
                  onChange={e => setFormData({...formData, discount_percent: e.target.value})}
                  className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 pr-10 rounded-lg focus:ring-2 focus:ring-red-500 outline-none transition-all font-mono"
                />
                <span className="absolute right-3.5 top-3 text-gray-400 text-base font-bold">%</span>
              </div>
            </div>
            
            <div className="col-span-2">
              <label className="block text-sm font-medium text-gray-400 mb-1.5">Billing Address</label>
              <textarea rows={3} value={formData.address} onChange={e => setFormData({...formData, address: e.target.value})} className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"></textarea>
            </div>
          </div>
          
          <div className="flex justify-end pt-4">
            <button type="submit" disabled={saving} className="bg-red-600 hover:bg-red-700 text-white px-8 py-3 rounded-lg shadow-lg font-medium transition-colors disabled:opacity-50">
              {saving ? 'Saving...' : 'Save Supplier'}
            </button>
          </div>
        </form>
      </div>
    </DashboardLayout>
  );
}
