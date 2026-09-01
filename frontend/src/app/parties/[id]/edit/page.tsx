"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import StateSelect from '@/components/StateSelect';

export default function EditPartyPage() {
  const router = useRouter();
  const params = useParams();
  const partyId = params.id;

  const [companyId, setCompanyId] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    group: '',
    gstin: '',
    state_code: '',
    phone: '',
    email: '',
    address: '',
  });

  useEffect(() => {
    if (!isAuthenticated()) { router.push('/login'); return; }
    fetchParty();
  }, [router, partyId]);

  const fetchParty = async () => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const cid = compRes.data.data[0]?.id;
      if (!cid) return;
      setCompanyId(cid);

      const res = await axios.get(`${API_BASE_URL}/api/v1/ledgers/${cid}/${partyId}/`, { headers });
      const d = res.data.data;
      setFormData({
        name: d.name || '',
        group: d.group || '',
        gstin: d.gstin || '',
        state_code: d.state_code || '',
        phone: d.phone || '',
        email: d.email || '',
        address: d.address || '',
      });
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      const res = await axios.patch(
        `${API_BASE_URL}/api/v1/ledgers/${companyId}/${partyId}/`,
        formData,
        { headers }
      );

      if (res.data.success) {
        alert('Profile updated successfully!');
        router.push('/parties');
      } else {
        alert('Error: ' + res.data.error);
      }
    } catch (err: any) {
      alert('Error: ' + (err.response?.data?.error || err.message));
    } finally {
      setSaving(false);
    }
  };

  const isCustomer = formData.group.includes('Debtor');

  if (loading) return <DashboardLayout><div className="flex items-center justify-center py-20 text-gray-500">Loading profile...</div></DashboardLayout>;

  return (
    <DashboardLayout>
      <div className="space-y-6 max-w-3xl mx-auto pb-12">

        {/* Header */}
        <div className="flex items-center gap-4 border-b border-border pb-4">
          <Link href="/parties" className="text-gray-400 hover:text-white transition-colors">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
          </Link>
          <div>
            <h1 className="text-3xl font-bold">Edit {formData.name}</h1>
            <p className="text-gray-400 mt-1 text-sm">
              Update profile for this {isCustomer ? 'Customer' : 'Supplier'} &middot; <span className="text-zinc-500">{formData.group}</span>
            </p>
          </div>
        </div>

        {/* Type Badge */}
        <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-full border text-sm font-medium ${
          isCustomer
            ? 'text-blue-400 bg-blue-400/10 border-blue-400/20'
            : 'text-red-400 bg-red-400/10 border-red-400/20'
        }`}>
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path></svg>
          {isCustomer ? 'Customer' : 'Supplier'}
        </div>

        {/* Form */}
        <form onSubmit={handleSave} className="bg-card border border-border rounded-xl shadow-sm p-6 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

            {/* Name */}
            <div className="col-span-2">
              <label className="block text-sm font-medium text-gray-400 mb-1.5">Party Name *</label>
              <input
                required
                type="text"
                value={formData.name}
                onChange={e => setFormData({ ...formData, name: e.target.value })}
                className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
              />
            </div>

            {/* GSTIN */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">GSTIN</label>
              <input
                type="text"
                maxLength={15}
                placeholder="e.g. 09ABCDEFG7988P4"
                value={formData.gstin}
                onChange={e => setFormData({ ...formData, gstin: e.target.value.toUpperCase() })}
                className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
              />
            </div>

            {/* State Code */}
            <div>
              <StateSelect
                value={formData.state_code}
                onChange={(code) => setFormData({ ...formData, state_code: code })}
                label="State / Union Territory"
                placeholder="Search state by name or code..."
              />
            </div>

            {/* Phone */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">Phone Number</label>
              <input
                type="text"
                placeholder="+91 XXXXXXXXXX"
                value={formData.phone}
                onChange={e => setFormData({ ...formData, phone: e.target.value })}
                className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
              />
            </div>

            {/* Email */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">Email Address</label>
              <input
                type="email"
                placeholder="party@example.com"
                value={formData.email}
                onChange={e => setFormData({ ...formData, email: e.target.value })}
                className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
              />
            </div>

            {/* Address */}
            <div className="col-span-2">
              <label className="block text-sm font-medium text-gray-400 mb-1.5">Billing Address</label>
              <textarea
                rows={3}
                value={formData.address}
                onChange={e => setFormData({ ...formData, address: e.target.value })}
                className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all resize-none"
              />
            </div>
          </div>

          <div className="flex justify-between items-center pt-4 border-t border-zinc-800">
            <Link href="/parties" className="text-gray-400 hover:text-white text-sm transition-colors">
              ← Cancel
            </Link>
            <button
              type="submit"
              disabled={saving}
              className="bg-blue-600 hover:bg-blue-700 text-white px-8 py-3 rounded-lg font-semibold shadow-lg transition-all disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </DashboardLayout>
  );
}
