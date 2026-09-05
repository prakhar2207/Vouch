"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import StateSelect from '@/components/StateSelect';
import ConfirmModal from '@/components/modals/ConfirmModal';
import { useToast } from '@/context/ToastContext';
import { Trash2 } from 'lucide-react';

export default function EditPartyPage() {
  const router = useRouter();
  const params = useParams();
  const partyId = params.id;
  const { toast } = useToast();

  const [companyId, setCompanyId] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    group: '',
    gstin: '',
    state_code: '',
    phone: '',
    email: '',
    address: '',
    discount_percent: '',
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
        discount_percent: d.discount_percent !== undefined && d.discount_percent !== null ? String(d.discount_percent) : '',
      });
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        const form = document.getElementById('edit-party-form') as HTMLFormElement;
        if (form) form.requestSubmit();
      } else if (e.altKey && e.key.toLowerCase() === 'd') {
        e.preventDefault();
        setIsDeleteOpen(true);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

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
        toast.success(`Party '${formData.name}' updated successfully!`);
        router.push('/parties');
      } else {
        toast.error('Failed to update', res.data.error);
      }
    } catch (err: any) {
      toast.error('Update failed', err.response?.data?.error || err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      const res = await axios.delete(
        `${API_BASE_URL}/api/v1/ledgers/${companyId}/${partyId}/`,
        { headers }
      );

      if (res.data.success) {
        toast.success(res.data.message || `Party '${formData.name}' deleted successfully.`);
        router.push('/parties');
      } else {
        toast.error('Failed to delete', res.data.error);
      }
    } catch (err: any) {
      toast.error('Delete failed', err.response?.data?.error || err.message);
    } finally {
      setDeleting(false);
      setIsDeleteOpen(false);
    }
  };

  const isCustomer = formData.group.includes('Debtor');

  if (loading) return <DashboardLayout><div className="flex items-center justify-center py-20 text-gray-500">Loading profile...</div></DashboardLayout>;

  return (
    <DashboardLayout>
      <div className="space-y-6 max-w-3xl mx-auto pb-12">

        {/* Header */}
        <div className="flex items-center justify-between border-b border-border pb-4">
          <div className="flex items-center gap-4">
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

          <button
            type="button"
            onClick={() => setIsDeleteOpen(true)}
            className="px-3.5 py-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/20 text-xs font-bold flex items-center gap-1.5 transition-colors cursor-pointer"
            title="Delete Party (Alt+D)"
          >
            <Trash2 className="w-4 h-4" />
            <span>Delete Party</span>
          </button>
        </div>

        {/* Type Badge */}
        <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-full border text-sm font-medium ${
          isCustomer 
            ? 'text-blue-400 bg-blue-400/10 border-blue-400/20' 
            : 'text-red-400 bg-red-400/10 border-red-400/20'
        }`}>
          <span className={`w-2 h-2 rounded-full ${isCustomer ? 'bg-blue-400' : 'bg-red-400'}`}></span>
          {isCustomer ? 'Customer (Sundry Debtor)' : 'Supplier (Sundry Creditor)'}
        </div>

        {/* Edit Form */}
        <form id="edit-party-form" onSubmit={handleSave} className="bg-card border border-border rounded-xl p-8 shadow-sm space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

            {/* Name */}
            <div className="col-span-2">
              <label className="block text-sm font-medium text-gray-400 mb-1.5">Party / Business Name *</label>
              <input
                required
                type="text"
                value={formData.name}
                onChange={e => setFormData({ ...formData, name: e.target.value })}
                className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all font-semibold"
              />
            </div>

            {/* GSTIN */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">GSTIN Number</label>
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

            {/* Default Party / Customer Discount */}
            <div className="col-span-2 bg-zinc-900/50 border border-zinc-800 p-4 rounded-xl space-y-2">
              <div className="flex justify-between items-center">
                <label className="block text-sm font-semibold text-gray-200">
                  Default Discount (%)
                </label>
                <span className="text-[11px] text-blue-400 bg-blue-500/10 border border-blue-500/20 px-2 py-0.5 rounded font-mono">
                  Auto-applied in Invoices
                </span>
              </div>
              <div className="relative">
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  placeholder="e.g. 10.00"
                  value={formData.discount_percent}
                  onChange={e => setFormData({ ...formData, discount_percent: e.target.value })}
                  className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 pr-10 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all font-mono"
                />
                <span className="absolute right-3.5 top-3 text-gray-400 text-base font-bold">%</span>
              </div>
              <p className="text-xs text-gray-400">
                This discount automatically populates on invoice line items whenever this customer is selected, and can still be edited or customized per order.
              </p>
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
            <div className="flex items-center gap-3">
              <Link href="/parties" className="text-gray-400 hover:text-white text-sm transition-colors">
                ← Cancel
              </Link>
              <span className="text-zinc-700">•</span>
              <button
                type="button"
                onClick={() => setIsDeleteOpen(true)}
                className="text-rose-500 hover:text-rose-400 text-xs font-semibold transition-colors cursor-pointer"
              >
                Delete (Alt+D)
              </button>
            </div>

            <button
              type="submit"
              disabled={saving}
              className="bg-blue-600 hover:bg-blue-700 text-white px-8 py-3 rounded-xl font-semibold shadow-lg transition-all disabled:opacity-50 text-sm cursor-pointer"
            >
              {saving ? 'Saving...' : 'Save Changes (Ctrl+Enter)'}
            </button>
          </div>
        </form>

        {/* Delete Confirmation Modal */}
        {isDeleteOpen && (
          <ConfirmModal
            isOpen={isDeleteOpen}
            onClose={() => setIsDeleteOpen(false)}
            onConfirm={handleDelete}
            title={`Delete "${formData.name}"?`}
            variant="danger"
            confirmText={deleting ? "Deleting..." : "Delete Party"}
            description={
              <div className="space-y-2 text-xs text-muted-foreground">
                <p>
                  Are you sure you want to permanently delete this party?
                </p>
                <p className="text-amber-400 bg-amber-500/10 p-2 rounded-lg border border-amber-500/20">
                  Note: If this party has associated vouchers or accounting entries, deletion will be blocked to preserve financial audit history.
                </p>
              </div>
            }
          />
        )}
      </div>
    </DashboardLayout>
  );
}
