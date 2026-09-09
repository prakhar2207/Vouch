"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';

import { ChevronLeft, ChevronRight } from 'lucide-react';

export default function VouchersPage() {
  const router = useRouter();
  const [vouchers, setVouchers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'ALL' | 'PAYMENT' | 'RECEIPT'>('ALL');
  const [page, setPage] = useState<number>(1);
  const [pagination, setPagination] = useState<any>(null);
  const pageSize = 50;

  useEffect(() => {
    if (!isAuthenticated()) { router.push('/login'); return; }
    fetchVouchers('ALL', 1);
  }, [router]);

  const fetchVouchers = async (typeFilter: string = filter, targetPage: number = page) => {
    setLoading(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const companyId = compRes.data.data[0]?.id;
      if (!companyId) return;

      const offset = (targetPage - 1) * pageSize;
      let url = `${API_BASE_URL}/api/v1/accounting/payment-receipts/${companyId}/?limit=${pageSize}&offset=${offset}`;
      if (typeFilter && typeFilter !== 'ALL') url += `&type=${typeFilter}`;
      
      const res = await axios.get(url, { headers });
      setVouchers(res.data.data || []);
      if (res.data.pagination) {
        setPagination(res.data.pagination);
      }
      setPage(targetPage);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleFilter = (f: 'ALL' | 'PAYMENT' | 'RECEIPT') => {
    setFilter(f);
    fetchVouchers(f, 1);
  };

  const totalPayments = vouchers.filter(v => v.type === 'PAYMENT').reduce((s, v) => s + parseFloat(v.total_amount), 0);
  const totalReceipts = vouchers.filter(v => v.type === 'RECEIPT').reduce((s, v) => s + parseFloat(v.total_amount), 0);

  return (
    <DashboardLayout>
      <div className="space-y-6">
        
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold">Payments & Receipts</h1>
            <p className="text-xs sm:text-sm text-muted-foreground mt-1">Record cash inflows and outflows against parties</p>
          </div>
          <Link href="/vouchers/new" className="w-full sm:w-auto justify-center bg-blue-600 text-foreground px-5 py-2.5 rounded-lg shadow hover:bg-blue-700 transition-colors font-medium flex items-center gap-2">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4"></path></svg>
            <span>New Voucher</span>
          </Link>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-6">
          <div className="bg-card border border-border rounded-xl p-4 sm:p-6 shadow-sm text-center">
            <p className="text-muted-foreground text-xs sm:text-sm uppercase tracking-wider font-medium mb-1">Total Vouchers</p>
            <p className="text-2xl sm:text-3xl font-bold text-foreground">{vouchers.length}</p>
          </div>
          <div className="bg-card border border-border rounded-xl p-4 sm:p-6 shadow-sm text-center">
            <p className="text-muted-foreground text-xs sm:text-sm uppercase tracking-wider font-medium mb-1">Money Paid Out</p>
            <p className="text-2xl sm:text-3xl font-bold text-red-400">₹{totalPayments.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</p>
          </div>
          <div className="bg-card border border-border rounded-xl p-4 sm:p-6 shadow-sm text-center">
            <p className="text-muted-foreground text-xs sm:text-sm uppercase tracking-wider font-medium mb-1">Money Received</p>
            <p className="text-2xl sm:text-3xl font-bold text-green-400">₹{totalReceipts.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</p>
          </div>
        </div>

        {/* Filter Tabs */}
        <div className="flex gap-2 overflow-x-auto pb-1">
          {(['ALL', 'RECEIPT', 'PAYMENT'] as const).map(f => (
            <button key={f} onClick={() => handleFilter(f)}
              className={`px-4 py-2 text-sm rounded-lg font-medium transition-colors border whitespace-nowrap ${
                filter === f
                  ? 'bg-blue-600 text-foreground border-blue-600'
                  : 'bg-muted/50 text-muted-foreground border-input hover:border-zinc-500'
              }`}
            >
              {f === 'ALL' ? 'All' : f === 'RECEIPT' ? '↓ Receipts' : '↑ Payments'}
            </button>
          ))}
        </div>

        {/* Table & Mobile Cards Container */}
        <div className="bg-card border border-border rounded-xl shadow-sm overflow-hidden">
          {loading ? (
            <div className="p-12 text-center text-muted-foreground text-sm">Loading vouchers...</div>
          ) : vouchers.length === 0 ? (
            <div className="p-16 text-center text-muted-foreground">
              <svg className="w-16 h-16 text-zinc-700 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1" d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"></path></svg>
              <p className="text-lg font-medium mb-1">No vouchers yet</p>
              <p className="text-sm">Create your first Payment or Receipt to start tracking cash flow.</p>
            </div>
          ) : (
            <>
              {/* Mobile Card List (< md) */}
              <div className="block md:hidden divide-y divide-zinc-800">
                {vouchers.map((v: any) => (
                  <div key={v.id} className="p-4 space-y-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono font-medium text-blue-400 text-sm">{v.voucher_number}</span>
                      <div className="flex items-center gap-1.5">
                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${
                          v.type === 'RECEIPT'
                            ? 'bg-green-500/10 text-green-400 border border-green-500/20'
                            : 'bg-red-500/10 text-red-400 border border-red-500/20'
                        }`}>
                          {v.type === 'RECEIPT' ? '↓ Receipt' : '↑ Payment'}
                        </span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                          v.status === 'POSTED' ? 'bg-green-900/30 text-green-400' : 'bg-yellow-900/30 text-yellow-400'
                        }`}>{v.status}</span>
                      </div>
                    </div>

                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-foreground truncate max-w-[200px]">{v.party_name}</span>
                      <span className="text-muted-foreground font-mono">{v.date}</span>
                    </div>

                    {v.narration && (
                      <p className="text-xs text-muted-foreground truncate">{v.narration}</p>
                    )}

                    <div className="pt-1 text-right">
                      <span className={`font-mono font-bold text-lg ${v.type === 'RECEIPT' ? 'text-green-400' : 'text-red-400'}`}>
                        ₹{parseFloat(v.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              {/* Desktop Table (>= md) */}
              <div className="hidden md:block overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead className="bg-zinc-900/80 text-muted-foreground text-xs uppercase tracking-wider">
                    <tr>
                      <th className="p-4 font-medium border-b border-border">Voucher No.</th>
                      <th className="p-4 font-medium border-b border-border">Type</th>
                      <th className="p-4 font-medium border-b border-border">Date</th>
                      <th className="p-4 font-medium border-b border-border">Party</th>
                      <th className="p-4 font-medium border-b border-border">Narration</th>
                      <th className="p-4 font-medium border-b border-border text-right">Amount (₹)</th>
                      <th className="p-4 font-medium border-b border-border text-center">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800">
                    {vouchers.map((v: any) => (
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
                        <td className="p-4 whitespace-nowrap text-foreground/80">{v.date}</td>
                        <td className="p-4 text-foreground font-medium">{v.party_name}</td>
                        <td className="p-4 text-muted-foreground max-w-xs truncate" title={v.narration}>{v.narration || '-'}</td>
                        <td className={`p-4 text-right font-bold text-lg ${v.type === 'RECEIPT' ? 'text-green-400' : 'text-red-400'}`}>
                          ₹{parseFloat(v.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>
                        <td className="p-4 text-center">
                          <span className={`text-xs px-2 py-1 rounded ${
                            v.status === 'POSTED' ? 'bg-green-900/30 text-green-400' : 'bg-yellow-900/30 text-yellow-400'
                          }`}>{v.status}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          
          {/* Pagination Controls */}
          {pagination && pagination.total_count > 0 && (
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-4 py-3 border-t border-border bg-zinc-900/30 text-xs text-muted-foreground">
              <div className="font-mono">
                Showing <span className="font-semibold text-foreground">{pagination.offset + 1}</span> to{' '}
                <span className="font-semibold text-foreground">
                  {Math.min(pagination.offset + pagination.limit, pagination.total_count)}
                </span>{' '}
                of <span className="font-semibold text-foreground">{pagination.total_count}</span> vouchers
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => fetchVouchers(filter, page - 1)}
                  disabled={page <= 1 || loading}
                  className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-input bg-muted/50 text-foreground hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer font-medium"
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                  <span>Previous</span>
                </button>

                <div className="px-2.5 py-1 text-xs font-mono font-semibold text-foreground bg-muted rounded border border-input">
                  Page {page} of {pagination.total_pages || 1}
                </div>

                <button
                  type="button"
                  onClick={() => fetchVouchers(filter, page + 1)}
                  disabled={!pagination.has_more || page >= pagination.total_pages || loading}
                  className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-input bg-muted/50 text-foreground hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer font-medium"
                >
                  <span>Next</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
