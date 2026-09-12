"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';

import { ChevronLeft, ChevronRight, Edit2, Trash2 } from 'lucide-react';
import { useToast } from '@/context/ToastContext';
import { useCompany } from '@/context/CompanyContext';
import { vouchersRepository } from '@/lib/data';
import EditPaymentReceiptModal from '@/components/modals/EditPaymentReceiptModal';
import ConfirmModal from '@/components/modals/ConfirmModal';

export default function VouchersPage() {
  const router = useRouter();
  const { toast } = useToast();
  const { companyId: activeCompanyId } = useCompany();
  const [vouchers, setVouchers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'ALL' | 'PAYMENT' | 'RECEIPT'>('ALL');
  const [page, setPage] = useState<number>(1);
  const [pagination, setPagination] = useState<any>(null);
  const pageSize = 50;

  // Edit and Delete state
  const [editingVoucher, setEditingVoucher] = useState<any | null>(null);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [deleteConfirmParams, setDeleteConfirmParams] = useState<{ id: string; number: string; type: string } | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) { router.push('/login'); return; }
    fetchVouchers('ALL', 1);
  }, [router]);

  const fetchVouchers = async (typeFilter: string = filter, targetPage: number = page) => {
    setLoading(true);
    try {
      let companyId = activeCompanyId;
      if (!companyId && typeof window !== 'undefined') {
        companyId = localStorage.getItem('vouch_active_company_id');
      }
      if (!companyId) {
        const token = getAccessToken();
        const headers = { Authorization: `Bearer ${token}` };
        const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
        companyId = compRes.data?.data?.[0]?.id || compRes.data?.[0]?.id;
      }
      if (!companyId) return;

      const result = await vouchersRepository.getPaymentReceipts(companyId, {
        page: targetPage,
        pageSize,
        type: typeFilter !== 'ALL' ? typeFilter : ['PAYMENT', 'RECEIPT'],
      });

      setVouchers(result.data);
      setPagination({
        page: result.page,
        limit: result.pageSize,
        total_count: result.totalCount,
        total_pages: result.totalPages,
      });
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

  const handleStartEdit = (voucher: any) => {
    setEditingVoucher(voucher);
    setIsEditModalOpen(true);
  };

  const handleDeleteVoucher = (voucherId: string, voucherNumber: string, voucherType: string) => {
    setDeleteConfirmParams({ id: voucherId, number: voucherNumber, type: voucherType });
  };

  const executeDelete = async (voucherId: string) => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.delete(`${API_BASE_URL}/api/vouchers/${voucherId}/`, { headers });

      if (res.data.success) {
        toast.success(res.data.message || 'Voucher deleted and reversed successfully!');
        setVouchers((prev) => prev.filter((v) => v.id !== voucherId));
        setDeleteConfirmParams(null);
      } else {
        toast.error('Failed to delete voucher', res.data.error);
      }
    } catch (err: any) {
      toast.error('Delete failed', err.response?.data?.error || err.message);
    }
  };

  const totalPayments = vouchers.filter(v => v.type === 'PAYMENT').reduce((s, v) => s + parseFloat(v.total_amount), 0);
  const totalReceipts = vouchers.filter(v => v.type === 'RECEIPT').reduce((s, v) => s + parseFloat(v.total_amount), 0);

  return (
    <DashboardLayout>
      <div className="space-y-6">
        
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold">Cash & Bank</h1>
            <p className="text-xs sm:text-sm text-muted-foreground mt-1">Record money you sent and received</p>
          </div>
          <Link href="/vouchers/new" className="w-full sm:w-auto justify-center bg-blue-600 text-foreground px-5 py-2.5 rounded-lg shadow hover:bg-blue-700 transition-colors font-medium flex items-center gap-2">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4"></path></svg>
            <span>New Entry</span>
          </Link>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-6">
          <div className="bg-card border border-border rounded-xl p-4 sm:p-6 shadow-sm text-center">
            <p className="text-muted-foreground text-xs sm:text-sm uppercase tracking-wider font-medium mb-1">Total Entries</p>
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
              <div className="block md:hidden divide-y divide-border">
                {vouchers.map((v: any) => (
                  <div key={v.id} className="p-4 space-y-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono font-semibold text-blue-400 text-sm">{v.voucher_number}</span>
                      <div className="flex items-center gap-1.5">
                        <span className={`text-xs px-2.5 py-0.5 rounded-full font-semibold ${
                          v.type === 'RECEIPT'
                            ? 'bg-green-500/10 text-green-500 border border-green-500/20'
                            : 'bg-red-500/10 text-red-500 border border-red-500/20'
                        }`}>
                          {v.type === 'RECEIPT' ? '↓ Receipt' : '↑ Payment'}
                        </span>
                        <span className={`text-xs px-2 py-0.5 rounded font-mono font-medium ${
                          v.status === 'POSTED' ? 'bg-green-900/30 text-green-400' : 'bg-yellow-900/30 text-yellow-400'
                        }`}>{v.status}</span>
                      </div>
                    </div>

                    <div className="flex items-center justify-between text-sm">
                      <span className="font-semibold text-foreground truncate max-w-[200px]">{v.party_name}</span>
                      <span className="text-muted-foreground font-mono">{v.date}</span>
                    </div>

                    {v.narration && (
                      <p className="text-xs text-muted-foreground truncate">{v.narration}</p>
                    )}

                    <div className="flex items-center justify-between pt-1">
                      <span className={`font-mono tabular-nums font-bold text-lg ${v.type === 'RECEIPT' ? 'text-green-500' : 'text-red-500'}`}>
                        ₹{parseFloat(v.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </span>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleStartEdit(v)}
                          className="px-3 py-1.5 bg-blue-600/15 hover:bg-blue-600/25 text-blue-400 rounded-lg text-xs font-semibold border border-blue-500/30 transition-colors flex items-center gap-1.5 cursor-pointer min-h-[36px]"
                          title="Edit Voucher"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                          <span>Edit</span>
                        </button>
                        <button
                          onClick={() => handleDeleteVoucher(v.id, v.voucher_number, v.type)}
                          className="px-3 py-1.5 bg-rose-600/15 hover:bg-rose-600/25 text-rose-400 rounded-lg text-xs font-semibold border border-rose-500/30 transition-colors flex items-center gap-1.5 cursor-pointer min-h-[36px]"
                          title="Delete Voucher"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          <span>Delete</span>
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Desktop Table (>= md) */}
              <div className="hidden md:block overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead className="bg-muted/40 text-muted-foreground text-xs font-semibold uppercase tracking-wider">
                    <tr>
                      <th className="p-4 border-b border-border">Number</th>
                      <th className="p-4 border-b border-border">Type</th>
                      <th className="p-4 border-b border-border">Date</th>
                      <th className="p-4 border-b border-border">Party</th>
                      <th className="p-4 border-b border-border">Narration</th>
                      <th className="p-4 border-b border-border text-right">Amount (₹)</th>
                      <th className="p-4 border-b border-border text-center">Status</th>
                      <th className="p-4 border-b border-border text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {vouchers.map((v: any) => (
                      <tr key={v.id} className="hover:bg-muted/30 transition-colors">
                        <td className="p-4 whitespace-nowrap font-mono font-semibold text-blue-400 text-sm">{v.voucher_number}</td>
                        <td className="p-4 whitespace-nowrap">
                          <span className={`text-xs px-2.5 py-1 rounded-full font-semibold ${
                            v.type === 'RECEIPT'
                              ? 'bg-green-500/10 text-green-500 border border-green-500/20'
                              : 'bg-red-500/10 text-red-500 border border-red-500/20'
                          }`}>
                            {v.type === 'RECEIPT' ? '↓ Receipt' : '↑ Payment'}
                          </span>
                        </td>
                        <td className="p-4 whitespace-nowrap text-muted-foreground font-mono text-sm">{v.date}</td>
                        <td className="p-4 text-foreground font-semibold text-sm">{v.party_name}</td>
                        <td className="p-4 text-muted-foreground text-sm max-w-xs truncate" title={v.narration}>{v.narration || '-'}</td>
                        <td className={`p-4 text-right font-mono tabular-nums font-bold text-base ${v.type === 'RECEIPT' ? 'text-green-500' : 'text-red-500'}`}>
                          ₹{parseFloat(v.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>
                        <td className="p-4 text-center">
                          <span className={`text-xs px-2 py-1 rounded font-mono font-medium ${
                            v.status === 'POSTED' ? 'bg-green-900/30 text-green-400' : 'bg-yellow-900/30 text-yellow-400'
                          }`}>{v.status}</span>
                        </td>
                        <td className="p-4 text-right whitespace-nowrap">
                          <div className="flex items-center justify-end gap-2" onClick={(e) => e.stopPropagation()}>
                            <button
                              onClick={() => handleStartEdit(v)}
                              className="px-3 py-1.5 bg-blue-600/15 hover:bg-blue-600/25 text-blue-400 rounded-lg text-xs font-semibold border border-blue-500/30 transition-colors flex items-center gap-1.5 cursor-pointer min-h-[36px]"
                              title="Edit Voucher"
                            >
                              <Edit2 className="w-3.5 h-3.5" />
                              <span>Edit</span>
                            </button>
                            <button
                              onClick={() => handleDeleteVoucher(v.id, v.voucher_number, v.type)}
                              className="px-3 py-1.5 bg-rose-600/15 hover:bg-rose-600/25 text-rose-400 rounded-lg text-xs font-semibold border border-rose-500/30 transition-colors flex items-center gap-1.5 cursor-pointer min-h-[36px]"
                              title="Delete Voucher"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                              <span>Delete</span>
                            </button>
                          </div>
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
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-4 py-3 border-t border-border bg-muted/20 text-xs text-muted-foreground">
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
                  className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-input bg-muted/50 text-foreground hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer font-medium min-h-[36px]"
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
                  className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-input bg-muted/50 text-foreground hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer font-medium min-h-[36px]"
                >
                  <span>Next</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Edit Payment / Receipt Modal */}
        <EditPaymentReceiptModal
          isOpen={isEditModalOpen}
          onClose={() => {
            setIsEditModalOpen(false);
            setEditingVoucher(null);
          }}
          voucher={editingVoucher}
          onUpdateSuccess={() => fetchVouchers(filter, page)}
        />

        {/* Confirm Delete Modal */}
        <ConfirmModal
          isOpen={deleteConfirmParams !== null}
          onClose={() => setDeleteConfirmParams(null)}
          onConfirm={() => {
            if (deleteConfirmParams) {
              executeDelete(deleteConfirmParams.id);
            }
          }}
          title={`Delete ${deleteConfirmParams?.type === 'RECEIPT' ? 'Receipt' : 'Payment'} Voucher?`}
          description={
            <span>
              Are you sure you want to permanently delete Voucher{" "}
              <strong className="text-foreground font-mono">#{deleteConfirmParams?.number}</strong>?
              This will cancel the voucher, reverse the party ledger entry, reverse cash/bank ledger entries, and restore original balances.
            </span>
          }
          confirmText="Delete & Reverse"
          variant="danger"
        />
      </div>
    </DashboardLayout>
  );
}
