"use client";
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';

export default function VouchersPage() {
  const router = useRouter();
  const [vouchers, setVouchers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'ALL' | 'PAYMENT' | 'RECEIPT'>('ALL');

  useEffect(() => {
    if (!isAuthenticated()) { router.push('/login'); return; }
    fetchVouchers();
  }, [router]);

  const fetchVouchers = async (typeFilter?: string) => {
    setLoading(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const compRes = await axios.get('http://localhost:8000/api/v1/companies/', { headers });
      const companyId = compRes.data.data[0]?.id;
      if (!companyId) return;

      let url = `http://localhost:8000/api/v1/accounting/payment-receipts/${companyId}/`;
      if (typeFilter && typeFilter !== 'ALL') url += `?type=${typeFilter}`;
      
      const res = await axios.get(url, { headers });
      setVouchers(res.data.data || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleFilter = (f: 'ALL' | 'PAYMENT' | 'RECEIPT') => {
    setFilter(f);
    fetchVouchers(f);
  };

  const totalPayments = vouchers.filter(v => v.type === 'PAYMENT').reduce((s, v) => s + parseFloat(v.total_amount), 0);
  const totalReceipts = vouchers.filter(v => v.type === 'RECEIPT').reduce((s, v) => s + parseFloat(v.total_amount), 0);

  return (
    <DashboardLayout>
      <div className="space-y-6">
        
        {/* Header */}
        <div className="flex justify-between items-center border-b border-border pb-4">
          <div>
            <h1 className="text-3xl font-bold">Payments & Receipts</h1>
            <p className="text-sm text-gray-400 mt-1">Record cash inflows and outflows against parties</p>
          </div>
          <Link href="/vouchers/new" className="bg-blue-600 text-white px-5 py-2.5 rounded-lg shadow hover:bg-blue-700 transition-colors font-medium flex items-center gap-2">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4"></path></svg>
            New Voucher
          </Link>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-card border border-border rounded-xl p-6 shadow-sm text-center">
            <p className="text-gray-400 text-sm uppercase tracking-wider font-medium mb-1">Total Vouchers</p>
            <p className="text-3xl font-bold text-white">{vouchers.length}</p>
          </div>
          <div className="bg-card border border-border rounded-xl p-6 shadow-sm text-center">
            <p className="text-gray-400 text-sm uppercase tracking-wider font-medium mb-1">Money Paid Out</p>
            <p className="text-3xl font-bold text-red-400">₹{totalPayments.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</p>
          </div>
          <div className="bg-card border border-border rounded-xl p-6 shadow-sm text-center">
            <p className="text-gray-400 text-sm uppercase tracking-wider font-medium mb-1">Money Received</p>
            <p className="text-3xl font-bold text-green-400">₹{totalReceipts.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</p>
          </div>
        </div>

        {/* Filter Tabs */}
        <div className="flex gap-2">
          {(['ALL', 'RECEIPT', 'PAYMENT'] as const).map(f => (
            <button key={f} onClick={() => handleFilter(f)}
              className={`px-4 py-2 text-sm rounded-lg font-medium transition-colors border ${
                filter === f
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-zinc-900 text-gray-400 border-zinc-700 hover:border-zinc-500'
              }`}
            >
              {f === 'ALL' ? 'All' : f === 'RECEIPT' ? '↓ Receipts' : '↑ Payments'}
            </button>
          ))}
        </div>

        {/* Table */}
        <div className="bg-card border border-border rounded-xl shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead className="bg-zinc-900/80 text-gray-400 text-xs uppercase tracking-wider">
                <tr>
                  <th className="p-4 font-medium border-b border-zinc-800">Voucher No.</th>
                  <th className="p-4 font-medium border-b border-zinc-800">Type</th>
                  <th className="p-4 font-medium border-b border-zinc-800">Date</th>
                  <th className="p-4 font-medium border-b border-zinc-800">Party</th>
                  <th className="p-4 font-medium border-b border-zinc-800">Narration</th>
                  <th className="p-4 font-medium border-b border-zinc-800 text-right">Amount (₹)</th>
                  <th className="p-4 font-medium border-b border-zinc-800 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {loading ? (
                  <tr><td colSpan={7} className="p-12 text-center text-gray-500">Loading...</td></tr>
                ) : vouchers.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="p-16 text-center text-gray-500">
                      <svg className="w-16 h-16 text-zinc-700 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1" d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"></path></svg>
                      <p className="text-lg font-medium mb-1">No vouchers yet</p>
                      <p className="text-sm">Create your first Payment or Receipt to start tracking cash flow.</p>
                    </td>
                  </tr>
                ) : (
                  vouchers.map((v: any) => (
                    <tr key={v.id} className="hover:bg-zinc-800/30 transition-colors">
                      <td className="p-4 whitespace-nowrap font-medium text-blue-400">{v.voucher_number}</td>
                      <td className="p-4 whitespace-nowrap">
                        <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                          v.type === 'RECEIPT'
                            ? 'bg-green-500/10 text-green-400 border border-green-500/20'
                            : 'bg-red-500/10 text-red-400 border border-red-500/20'
                        }`}>
                          {v.type === 'RECEIPT' ? '↓ Receipt' : '↑ Payment'}
                        </span>
                      </td>
                      <td className="p-4 whitespace-nowrap text-gray-300">{v.date}</td>
                      <td className="p-4 text-white font-medium">{v.party_name}</td>
                      <td className="p-4 text-gray-400 max-w-xs truncate" title={v.narration}>{v.narration || '-'}</td>
                      <td className={`p-4 text-right font-bold text-lg ${v.type === 'RECEIPT' ? 'text-green-400' : 'text-red-400'}`}>
                        ₹{parseFloat(v.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                      <td className="p-4 text-center">
                        <span className={`text-xs px-2 py-1 rounded ${
                          v.status === 'POSTED' ? 'bg-green-900/30 text-green-400' : 'bg-yellow-900/30 text-yellow-400'
                        }`}>{v.status}</span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          
          {vouchers.length > 0 && (
            <div className="p-4 border-t border-border bg-zinc-900/30 text-right">
              <span className="text-gray-500 text-sm">Showing {vouchers.length} voucher(s)</span>
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
