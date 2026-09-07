"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';

export default function LedgerStatementPage() {
  const router = useRouter();
  const params = useParams();
  const ledgerId = params.id;
  
  const [statementData, setStatementData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login');
      return;
    }
    fetchStatement();
  }, [router, ledgerId]);

  const fetchStatement = async () => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      
      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const companyId = compRes.data.data[0]?.id;
      if (!companyId) return;

      const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/reports/ledger-statement/${companyId}/${ledgerId}/`, { headers });
      setStatementData(res.data.data);
      
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <DashboardLayout><div className="flex items-center justify-center py-20 text-gray-500">Loading statement...</div></DashboardLayout>;

  return (
    <DashboardLayout>
      <div className="space-y-6 max-w-7xl mx-auto pb-12">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-4">
          <div className="flex items-center gap-3 sm:gap-4">
            <button
              onClick={() => router.back()}
              className="text-gray-400 hover:text-white transition-colors p-1 cursor-pointer"
              title="Go Back"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
            </button>
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold">{statementData?.ledger_name} Statement</h1>
              <p className="text-gray-400 mt-0.5 text-xs sm:text-sm">Ledger Account Statement</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button className="text-xs sm:text-sm border border-zinc-700 bg-zinc-800 hover:bg-zinc-700 text-white px-3 py-1.5 rounded transition-colors flex items-center gap-1.5 cursor-pointer">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
              <span>Export CSV</span>
            </button>
            <button className="text-xs sm:text-sm border border-zinc-700 bg-zinc-800 hover:bg-zinc-700 text-white px-3 py-1.5 rounded transition-colors flex items-center gap-1.5 cursor-pointer">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"></path></svg>
              <span>Print</span>
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-6">
            <div className="bg-card border border-border rounded-xl p-4 sm:p-6 text-center shadow-sm">
                <p className="text-gray-400 text-xs sm:text-sm mb-1 uppercase tracking-wider font-medium">Opening Balance</p>
                <p className="text-2xl sm:text-3xl font-bold text-white font-mono">₹{parseFloat(statementData?.opening_balance || 0).toLocaleString('en-IN', {minimumFractionDigits: 2})} <span className="text-xs sm:text-sm font-medium text-gray-500">{statementData?.opening_balance_type}</span></p>
            </div>
            <div className="bg-card border border-border rounded-xl p-4 sm:p-6 text-center shadow-sm">
                <p className="text-gray-400 text-xs sm:text-sm mb-1 uppercase tracking-wider font-medium">Total Debit (In)</p>
                <p className="text-2xl sm:text-3xl font-bold text-red-400 font-mono">₹{statementData?.entries.reduce((a:any, b:any) => a + parseFloat(b.debit || 0), 0).toLocaleString('en-IN', {minimumFractionDigits: 2})}</p>
            </div>
            <div className="bg-card border border-border rounded-xl p-4 sm:p-6 text-center shadow-sm">
                <p className="text-gray-400 text-xs sm:text-sm mb-1 uppercase tracking-wider font-medium">Total Credit (Out)</p>
                <p className="text-2xl sm:text-3xl font-bold text-green-400 font-mono">₹{statementData?.entries.reduce((a:any, b:any) => a + parseFloat(b.credit || 0), 0).toLocaleString('en-IN', {minimumFractionDigits: 2})}</p>
            </div>
        </div>
        
        <div className="bg-card border border-border rounded-xl shadow-sm overflow-hidden">
            <div className="p-4 sm:p-5 border-b border-border bg-zinc-900/50 flex justify-between items-center">
                <h2 className="text-base sm:text-lg font-semibold text-white">Transaction History</h2>
            </div>

            {statementData?.entries?.length === 0 ? (
                <div className="p-12 text-center text-gray-500">
                    <svg className="w-12 h-12 text-zinc-700 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                    <p>No transactions found for this account.</p>
                </div>
            ) : (
                <>
                    {/* Mobile Cards (< md) */}
                    <div className="block md:hidden divide-y divide-zinc-800">
                        {statementData?.entries.map((entry: any) => (
                            <div key={entry.id} className="p-4 space-y-2">
                                <div className="flex items-center justify-between gap-2">
                                    <span className="font-mono text-xs text-gray-400">{entry.date || '-'}</span>
                                    <span className="bg-zinc-800 text-gray-300 text-[10px] px-2 py-0.5 rounded font-medium">{entry.voucher_type}</span>
                                </div>
                                <div className="flex items-center justify-between">
                                    <span className="font-mono font-medium text-blue-400 text-sm">{entry.voucher_number}</span>
                                    {parseFloat(entry.debit) > 0 && (
                                        <span className="font-mono font-bold text-red-400 text-base">
                                            Dr ₹{parseFloat(entry.debit).toLocaleString('en-IN', {minimumFractionDigits: 2})}
                                        </span>
                                    )}
                                    {parseFloat(entry.credit) > 0 && (
                                        <span className="font-mono font-bold text-green-400 text-base">
                                            Cr ₹{parseFloat(entry.credit).toLocaleString('en-IN', {minimumFractionDigits: 2})}
                                        </span>
                                    )}
                                </div>
                                {entry.narration && (
                                    <p className="text-xs text-gray-400 truncate">{entry.narration}</p>
                                )}
                            </div>
                        ))}
                    </div>

                    {/* Desktop Table (>= md) */}
                    <div className="hidden md:block overflow-x-auto">
                        <table className="w-full text-left border-collapse">
                            <thead className="bg-zinc-900/80 text-gray-400 text-xs uppercase tracking-wider">
                                <tr>
                                    <th className="p-4 font-medium border-b border-zinc-800">Date</th>
                                    <th className="p-4 font-medium border-b border-zinc-800">Voucher No.</th>
                                    <th className="p-4 font-medium border-b border-zinc-800">Type</th>
                                    <th className="p-4 font-medium border-b border-zinc-800">Narration</th>
                                    <th className="p-4 font-medium border-b border-zinc-800 text-right">Debit (₹)</th>
                                    <th className="p-4 font-medium border-b border-zinc-800 text-right">Credit (₹)</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-zinc-800">
                                {statementData?.entries.map((entry: any) => (
                                    <tr key={entry.id} className="hover:bg-zinc-800/30 transition-colors">
                                        <td className="p-4 whitespace-nowrap text-gray-300">{entry.date || '-'}</td>
                                        <td className="p-4 whitespace-nowrap font-medium text-blue-400">{entry.voucher_number}</td>
                                        <td className="p-4 whitespace-nowrap">
                                            <span className="bg-zinc-800 text-gray-300 text-xs px-2 py-1 rounded">{entry.voucher_type}</span>
                                        </td>
                                        <td className="p-4 text-gray-400 max-w-md truncate" title={entry.narration}>{entry.narration || '-'}</td>
                                        <td className="p-4 text-right text-red-400 font-medium font-mono">
                                            {parseFloat(entry.debit) > 0 ? parseFloat(entry.debit).toLocaleString('en-IN', {minimumFractionDigits: 2}) : '-'}
                                        </td>
                                        <td className="p-4 text-right text-green-400 font-medium font-mono">
                                            {parseFloat(entry.credit) > 0 ? parseFloat(entry.credit).toLocaleString('en-IN', {minimumFractionDigits: 2}) : '-'}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </>
            )}
            
            <div className="p-4 sm:p-6 border-t border-border bg-zinc-900/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <span className="text-gray-500 text-xs sm:text-sm">Showing {statementData?.entries?.length || 0} transactions</span>
                <div className="text-sm sm:text-lg text-gray-400 uppercase tracking-wider font-medium flex items-center justify-between sm:justify-end gap-3">
                    <span>Closing Balance:</span>
                    <span className="text-white font-bold font-mono text-2xl sm:text-3xl">₹{parseFloat(statementData?.current_balance || 0).toLocaleString('en-IN', {minimumFractionDigits: 2})}</span>
                </div>
            </div>
        </div>

      </div>
    </DashboardLayout>
  );
}
