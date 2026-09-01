"use client";
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';

export default function SalesInvoiceList() {
  const router = useRouter();
  const [invoices, setInvoices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login');
      return;
    }
    fetchInvoices();
  }, [router]);

  const fetchInvoices = async () => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const compRes = await axios.get('http://localhost:8000/api/v1/companies/', { headers });
      const companyId = compRes.data.data[0]?.id;
      if (!companyId) return;

      const res = await axios.get(`http://localhost:8000/api/v1/accounting/vouchers/${companyId}/`, { headers });
      
      // Filter only SALES vouchers
      const salesVouchers = (res.data.data || []).filter((v: any) => v.type === 'SALES');
      setInvoices(salesVouchers);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6 flex flex-col h-full">
        <div className="flex justify-between items-center border-b border-border pb-4">
          <h1 className="text-3xl font-bold">Sales Invoices</h1>
          <Link href="/sales/new" className="bg-blue-600 text-white px-4 py-2 rounded shadow hover:bg-blue-700 transition-colors">
            + Create Invoice
          </Link>
        </div>
        
        <div className="bg-card text-card-foreground p-2 rounded-xl shadow-sm border border-border flex-1 h-[600px] overflow-hidden flex flex-col">
          <div className="px-4 py-3 border-b border-border bg-gray-50 dark:bg-zinc-800/50 flex items-center justify-between">
            <span className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Previous Invoices</span>
            <span className="text-xs text-gray-400">Use column headers to filter, sort, and search</span>
          </div>
          {loading ? (
            <div className="flex items-center justify-center h-full text-gray-500">Loading invoices...</div>
          ) : invoices.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center p-12 bg-card">
              <svg className="w-20 h-20 text-gray-400 dark:text-gray-600 mb-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
              </svg>
              <h3 className="text-2xl font-bold mb-2">No Sales Invoices Yet</h3>
              <p className="text-gray-500 max-w-md mx-auto mb-8">It looks like you haven't created any sales invoices. Create your first invoice to start tracking your revenue and updating your inventory automatically.</p>
              <Link href="/sales/new" className="bg-blue-600 text-white px-6 py-2.5 rounded-lg shadow hover:bg-blue-700 transition-colors font-medium">
                + Create First Invoice
              </Link>
            </div>
          ) : (
            <div className="flex-1 w-full overflow-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-zinc-800 bg-zinc-900/40 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                    <th className="p-4 rounded-tl-lg">Invoice No.</th>
                    <th className="p-4">Date</th>
                    <th className="p-4">Party Name</th>
                    <th className="p-4">Total Amount</th>
                    <th className="p-4">Status</th>
                    <th className="p-4 rounded-tr-lg text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/50">
                  {invoices.map((inv, idx) => (
                    <tr key={idx} className="hover:bg-zinc-800/20 transition-colors group">
                      <td className="p-4 font-medium text-white">{inv.voucher_number}</td>
                      <td className="p-4 text-gray-400">{inv.date}</td>
                      <td className="p-4 text-gray-300">{inv.party_name}</td>
                      <td className="p-4 font-semibold text-white">₹ {parseFloat(inv.total_amount).toFixed(2)}</td>
                      <td className="p-4">
                        <span className={`px-2.5 py-1 text-xs font-bold rounded-full ${inv.status === 'POSTED' ? 'bg-green-500/10 text-green-500 border border-green-500/20' : 'bg-amber-500/10 text-amber-500 border border-amber-500/20'}`}>
                          {inv.status}
                        </span>
                      </td>
                      <td className="p-4 text-right">
                        <Link href={`/sales/${inv.id}/print`} className="text-blue-500 hover:text-blue-400 underline text-sm font-medium">
                          Print Invoice
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
