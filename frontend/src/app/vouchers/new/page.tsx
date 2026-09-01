"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';

export default function NewVoucherPage() {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [companyId, setCompanyId] = useState('');
  const [ledgers, setLedgers] = useState<any[]>([]);

  const [voucherType, setVoucherType] = useState<'RECEIPT' | 'PAYMENT'>('RECEIPT');
  const [partyLedgerId, setPartyLedgerId] = useState('');
  const [paymentLedgerId, setPaymentLedgerId] = useState('');
  const [amount, setAmount] = useState('');
  const [narration, setNarration] = useState('');
  const [voucherDate, setVoucherDate] = useState(new Date().toISOString().split('T')[0]);

  useEffect(() => {
    if (!isAuthenticated()) { router.push('/login'); return; }
    fetchLedgers();
  }, [router]);

  const fetchLedgers = async () => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const cid = compRes.data.data[0]?.id;
      if (!cid) return;
      setCompanyId(cid);

      const res = await axios.get(`${API_BASE_URL}/api/v1/ledgers/${cid}/`, { headers });
      setLedgers(res.data.data || []);
    } catch (err) {
      console.error(err);
    }
  };

  // Filter ledgers for dropdowns
  const partyLedgers = ledgers.filter(l =>
    l.group === 'Sundry Debtors' || l.group === 'Sundry Creditors'
  );
  const cashBankLedgers = ledgers.filter(l =>
    l.group === 'Cash-in-Hand' || l.group === 'Bank Accounts'
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!partyLedgerId || !paymentLedgerId || !amount) {
      alert('Please fill all required fields.');
      return;
    }
    setSaving(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      const payload = {
        company_id: companyId,
        voucher_type: voucherType,
        party_ledger_id: partyLedgerId,
        payment_ledger_id: paymentLedgerId,
        amount: parseFloat(amount),
        narration,
        voucher_date: voucherDate,
      };

      const res = await axios.post(`${API_BASE_URL}/api/v1/accounting/payment-receipt/`, payload, { headers });
      
      if (res.data.success) {
        alert(`${voucherType === 'RECEIPT' ? 'Receipt' : 'Payment'} ${res.data.voucher_number} posted successfully! Amount: ₹${res.data.amount}`);
        router.push('/vouchers');
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
      <div className="space-y-6 max-w-3xl mx-auto pb-12">

        {/* Header */}
        <div className="flex items-center gap-4 border-b border-border pb-4">
          <Link href="/vouchers" className="text-gray-400 hover:text-white transition-colors">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
          </Link>
          <div>
            <h1 className="text-3xl font-bold">New Payment / Receipt</h1>
            <p className="text-gray-400 mt-1 text-sm">Record a cash inflow or outflow against a party</p>
          </div>
        </div>

        {/* Type Selector */}
        <div className="grid grid-cols-2 gap-4">
          <button
            type="button"
            onClick={() => setVoucherType('RECEIPT')}
            className={`p-6 rounded-xl border-2 text-center transition-all ${
              voucherType === 'RECEIPT'
                ? 'border-green-500 bg-green-500/5'
                : 'border-zinc-700 bg-card hover:border-zinc-500'
            }`}
          >
            <div className={`w-12 h-12 mx-auto rounded-full flex items-center justify-center mb-3 ${
              voucherType === 'RECEIPT' ? 'bg-green-500/20 text-green-400' : 'bg-zinc-800 text-gray-400'
            }`}>
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 14l-7 7m0 0l-7-7m7 7V3"></path></svg>
            </div>
            <p className={`text-lg font-bold ${voucherType === 'RECEIPT' ? 'text-green-400' : 'text-white'}`}>Receipt</p>
            <p className="text-gray-500 text-sm mt-1">Money received from customer</p>
          </button>
          <button
            type="button"
            onClick={() => setVoucherType('PAYMENT')}
            className={`p-6 rounded-xl border-2 text-center transition-all ${
              voucherType === 'PAYMENT'
                ? 'border-red-500 bg-red-500/5'
                : 'border-zinc-700 bg-card hover:border-zinc-500'
            }`}
          >
            <div className={`w-12 h-12 mx-auto rounded-full flex items-center justify-center mb-3 ${
              voucherType === 'PAYMENT' ? 'bg-red-500/20 text-red-400' : 'bg-zinc-800 text-gray-400'
            }`}>
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 10l7-7m0 0l7 7m-7-7v18"></path></svg>
            </div>
            <p className={`text-lg font-bold ${voucherType === 'PAYMENT' ? 'text-red-400' : 'text-white'}`}>Payment</p>
            <p className="text-gray-500 text-sm mt-1">Money paid to supplier</p>
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="bg-card border border-border rounded-xl shadow-sm p-6 space-y-6">
          
          <div className="grid grid-cols-2 gap-6">
            {/* Party */}
            <div className="col-span-2">
              <label className="block text-sm font-medium text-gray-400 mb-1.5">
                {voucherType === 'RECEIPT' ? 'Customer (Receiving From) *' : 'Supplier (Paying To) *'}
              </label>
              <select
                required
                value={partyLedgerId}
                onChange={e => setPartyLedgerId(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
              >
                <option value="">-- Select Party --</option>
                {partyLedgers.map(l => (
                  <option key={l.id} value={l.id}>{l.name} ({l.group})</option>
                ))}
              </select>
              <div className="mt-2">
                <Link href={voucherType === 'RECEIPT' ? '/sales/customers/new' : '/purchases/suppliers/new'} className="text-blue-500 hover:text-blue-400 text-xs font-medium">
                  + Add New {voucherType === 'RECEIPT' ? 'Customer' : 'Supplier'}
                </Link>
              </div>
            </div>

            {/* Cash / Bank */}
            <div className="col-span-2">
              <label className="block text-sm font-medium text-gray-400 mb-1.5">
                {voucherType === 'RECEIPT' ? 'Received Into (Cash / Bank) *' : 'Paid From (Cash / Bank) *'}
              </label>
              <select
                required
                value={paymentLedgerId}
                onChange={e => setPaymentLedgerId(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
              >
                <option value="">-- Select Cash / Bank Account --</option>
                {cashBankLedgers.map(l => (
                  <option key={l.id} value={l.id}>{l.name}</option>
                ))}
              </select>
            </div>
            
            {/* Amount */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">Amount (₹) *</label>
              <input
                required
                type="number"
                step="0.01"
                min="0.01"
                placeholder="0.00"
                value={amount}
                onChange={e => setAmount(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all text-2xl font-bold"
              />
            </div>
            
            {/* Date */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">Voucher Date *</label>
              <input
                required
                type="date"
                value={voucherDate}
                onChange={e => setVoucherDate(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
              />
            </div>
            
            {/* Narration */}
            <div className="col-span-2">
              <label className="block text-sm font-medium text-gray-400 mb-1.5">Narration / Reference</label>
              <textarea
                rows={3}
                placeholder="e.g. Payment against invoice PUR-0001 via NEFT"
                value={narration}
                onChange={e => setNarration(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all resize-none"
              />
            </div>
          </div>

          {/* Summary */}
          {amount && parseFloat(amount) > 0 && (
            <div className={`rounded-xl p-6 border-2 ${
              voucherType === 'RECEIPT' ? 'border-green-500/30 bg-green-500/5' : 'border-red-500/30 bg-red-500/5'
            }`}>
              <div className="flex justify-between items-center">
                <div>
                  <p className="text-gray-400 text-sm font-medium uppercase tracking-wider">
                    {voucherType === 'RECEIPT' ? 'Amount to Receive' : 'Amount to Pay'}
                  </p>
                  <p className="text-gray-500 text-xs mt-1">
                    {voucherType === 'RECEIPT' ? 'Debit: Cash/Bank → Credit: Customer' : 'Debit: Supplier → Credit: Cash/Bank'}
                  </p>
                </div>
                <p className={`text-4xl font-bold ${voucherType === 'RECEIPT' ? 'text-green-400' : 'text-red-400'}`}>
                  ₹{parseFloat(amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </p>
              </div>
            </div>
          )}

          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={saving}
              className={`px-8 py-3 rounded-lg font-semibold text-white shadow-lg transition-all ${
                voucherType === 'RECEIPT'
                  ? 'bg-green-600 hover:bg-green-700'
                  : 'bg-red-600 hover:bg-red-700'
              } disabled:opacity-50`}
            >
              {saving ? 'Posting...' : `Post ${voucherType === 'RECEIPT' ? 'Receipt' : 'Payment'}`}
            </button>
          </div>
        </form>
      </div>
    </DashboardLayout>
  );
}
