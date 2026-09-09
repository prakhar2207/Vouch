"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import { useToast } from '@/context/ToastContext';
import EditSalesInvoiceModal from '@/components/modals/EditSalesInvoiceModal';
import ConfirmModal from '@/components/modals/ConfirmModal';
import { Edit2, Trash2, Printer, Plus, ChevronLeft, ChevronRight, CloudOff } from 'lucide-react';
import { offlineDb } from '@/lib/db/offlineDb';

export default function SalesInvoiceList() {
  const router = useRouter();
  const { toast } = useToast();

  const [invoices, setInvoices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState<number>(1);
  const [pagination, setPagination] = useState<any>(null);
  const pageSize = 50;

  // Edit and Delete state
  const [editingVoucher, setEditingVoucher] = useState<any | null>(null);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [deleteConfirmParams, setDeleteConfirmParams] = useState<{ id: string; number: string } | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login');
      return;
    }
    fetchInvoices(1);
  }, [router]);

  const fetchInvoices = async (targetPage: number = page) => {
    setLoading(true);
    try {
      // 1. Fetch pending offline vouchers from Dexie
      let offlineList: any[] = [];
      try {
        const pendingOffline = await offlineDb.vouchers
          .where('voucherType')
          .equals('SALES')
          .filter(v => v.status === 'PENDING' || v.status === 'SYNCING')
          .toArray();

        offlineList = pendingOffline.map(v => {
          const payload = v.payload || {};
          const lineItems = payload.items || [];
          const total = lineItems.reduce((sum: number, it: any) => {
            const gross = Number(it.quantity || 0) * Number(it.rate || 0);
            const disc = gross * (Number(it.discount_percent || 0) / 100);
            const taxable = gross - disc;
            return sum + taxable + (taxable * (Number(it.gst_rate || 18) / 100));
          }, 0);

          return {
            id: v.localId,
            isOffline: true,
            voucher_number: payload.voucher_number || v.localId.substring(0, 15).toUpperCase(),
            date: v.voucherDate || payload.voucher_date,
            party_name: payload.buyer_name || 'Offline Customer',
            total_amount: Math.round(total),
            status: 'PENDING_SYNC'
          };
        });
      } catch (offlineErr) {
        console.warn('Could not read offline vouchers', offlineErr);
      }

      // 2. Fetch remote invoices if online
      let remoteVouchers: any[] = [];
      try {
        const token = getAccessToken();
        const headers = { Authorization: `Bearer ${token}` };
        const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
        const companyId = compRes.data.data[0]?.id;
        if (companyId) {
          const offset = (targetPage - 1) * pageSize;
          const res = await axios.get(
            `${API_BASE_URL}/api/v1/accounting/vouchers/${companyId}/?type=SALES&limit=${pageSize}&offset=${offset}`,
            { headers, timeout: 6000 }
          );
          remoteVouchers = (res.data.data || []).filter((v: any) => v.type === 'SALES');
          if (res.data.pagination) {
            setPagination(res.data.pagination);
          }
          // Cache remote invoices for offline viewing
          offlineDb.masters.put({ key: 'cached_sales_invoices', data: remoteVouchers, updatedAt: Date.now() }).catch(() => {});
        }
      } catch (remoteErr) {
        console.warn('Backend unavailable, falling back to cached invoices', remoteErr);
        const cached = await offlineDb.masters.get('cached_sales_invoices');
        if (cached?.data?.length) {
          remoteVouchers = cached.data;
        }
      }

      // Merge: offline pending vouchers appear at the top!
      setInvoices([...offlineList, ...remoteVouchers]);
      setPage(targetPage);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleStartEdit = (inv: any) => {
    setEditingVoucher(inv);
    setIsEditModalOpen(true);
  };

  const handleDeleteInvoice = (voucherId: string, voucherNumber: string) => {
    setDeleteConfirmParams({ id: voucherId, number: voucherNumber });
  };

  const executeDelete = async (voucherId: string) => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.delete(`${API_BASE_URL}/api/vouchers/${voucherId}/`, { headers });

      if (res.data.success) {
        toast.success(res.data.message || 'Sales invoice deleted and reversed successfully!');
        setInvoices((prev) => prev.filter((i) => i.id !== voucherId));
        setDeleteConfirmParams(null);
      } else {
        toast.error('Failed to delete invoice', res.data.error);
      }
    } catch (err: any) {
      toast.error('Delete failed', err.response?.data?.error || err.message);
    }
  };

  const [focusedIndex, setFocusedIndex] = useState<number>(-1);

  const scrollToInvoice = (index: number) => {
    if (index >= 0 && index < invoices.length) {
      const invId = invoices[index].id;
      const el = document.getElementById(`row-sales-${invId}`);
      if (el) {
        el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (isEditModalOpen || deleteConfirmParams !== null) return;

      const activeElement = document.activeElement;
      const isInputFocused = activeElement && (
        activeElement.tagName === 'INPUT' ||
        activeElement.tagName === 'TEXTAREA' ||
        activeElement.tagName === 'SELECT'
      );
      if (isInputFocused) return;

      if (invoices.length === 0) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setFocusedIndex(prev => {
          const next = prev < invoices.length - 1 ? prev + 1 : 0;
          scrollToInvoice(next);
          return next;
        });
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setFocusedIndex(prev => {
          const next = prev > 0 ? prev - 1 : invoices.length - 1;
          scrollToInvoice(next);
          return next;
        });
      } else if (e.key === 'Home') {
        e.preventDefault();
        setFocusedIndex(0);
        scrollToInvoice(0);
      } else if (e.key === 'End') {
        e.preventDefault();
        setFocusedIndex(invoices.length - 1);
        scrollToInvoice(invoices.length - 1);
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        // TALLY SHORTCUT: Ctrl + Enter edits the selected invoice
        if (focusedIndex >= 0 && focusedIndex < invoices.length) {
          e.preventDefault();
          handleStartEdit(invoices[focusedIndex]);
        }
      } else if (e.key === 'Enter') {
        // Enter opens print view
        if (focusedIndex >= 0 && focusedIndex < invoices.length) {
          e.preventDefault();
          router.push(`/sales/${invoices[focusedIndex].id}/print`);
        }
      } else if (e.key.toLowerCase() === 'e' && !e.ctrlKey && !e.metaKey) {
        if (focusedIndex >= 0 && focusedIndex < invoices.length) {
          e.preventDefault();
          handleStartEdit(invoices[focusedIndex]);
        }
      } else if ((e.altKey && e.key.toLowerCase() === 'd') || e.key === 'Delete') {
        if (focusedIndex >= 0 && focusedIndex < invoices.length) {
          e.preventDefault();
          const target = invoices[focusedIndex];
          handleDeleteInvoice(target.id, target.voucher_number);
        }
      } else if (e.key.toLowerCase() === 'p' && !e.ctrlKey && !e.metaKey) {
        if (focusedIndex >= 0 && focusedIndex < invoices.length) {
          e.preventDefault();
          router.push(`/sales/${invoices[focusedIndex].id}/print`);
        }
      } else if (e.key === 'Escape') {
        setFocusedIndex(-1);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [invoices, focusedIndex, router, isEditModalOpen, deleteConfirmParams]);

  return (
    <DashboardLayout>
      <div className="space-y-6 flex flex-col h-full">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/40 pb-5">
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">Sales Invoices</h1>
            <p className="text-xs text-muted-foreground mt-1">Outward tax invoices and billing records</p>
          </div>
          <Link href="/sales/new" className="bg-primary text-primary-foreground px-4 py-2.5 rounded-xl text-xs font-bold shadow-md shadow-primary/20 hover:bg-primary/90 transition-all flex items-center justify-center gap-1.5">
            <Plus className="w-3.5 h-3.5" />
            <span>Create Invoice</span>
            <kbd className="bg-primary-foreground/20 px-1.5 py-0.5 rounded text-[10px]">F8</kbd>
          </Link>
        </div>
        
        <div className="bg-card text-card-foreground rounded-2xl shadow-sm border border-border/40 flex-1 overflow-hidden flex flex-col">
          <div className="px-5 py-3.5 border-b border-border/40 bg-muted/30 flex items-center justify-between">
            <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Previous Invoices</span>
            <span className="text-xs text-muted-foreground hidden sm:inline">Use ↑ / ↓ arrow keys to navigate, Ctrl+Enter to edit, Enter to print</span>
          </div>
          {loading ? (
            <div className="flex items-center justify-center h-full text-muted-foreground">Loading invoices...</div>
          ) : invoices.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center p-12 bg-card">
              <svg className="w-20 h-20 text-muted-foreground dark:text-gray-600 mb-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
              </svg>
              <h3 className="text-2xl font-bold mb-2">No Sales Invoices Yet</h3>
              <p className="text-muted-foreground max-w-md mx-auto mb-8">It looks like you haven't created any sales invoices. Create your first invoice to start tracking your revenue and updating your inventory automatically.</p>
              <Link href="/sales/new" className="bg-blue-600 text-foreground px-6 py-2.5 rounded-lg shadow hover:bg-blue-700 transition-colors font-medium">
                + Create First Invoice
              </Link>
            </div>
          ) : (
            <div className="flex-1 w-full overflow-auto flex flex-col justify-between">
              {/* Mobile Cards (block md:hidden) */}
              <div className="block md:hidden divide-y divide-border/60">
                {invoices.map((inv, idx) => (
                  <div key={inv.id || idx} className="p-3.5 space-y-2.5 bg-card">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-foreground text-sm">{inv.voucher_number}</span>
                        {inv.isOffline || inv.status === 'PENDING_SYNC' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/30">
                            <CloudOff className="w-2.5 h-2.5" />
                            Pending Sync
                          </span>
                        ) : (
                          <span className={`px-2 py-0.5 text-[10px] font-bold rounded-full border ${inv.status === 'POSTED' ? 'bg-green-500/10 text-green-500 border-green-500/20' : 'bg-amber-500/10 text-amber-500 border-amber-500/20'}`}>
                            {inv.status}
                          </span>
                        )}
                      </div>
                      <span className="text-xs text-muted-foreground font-mono">{inv.date}</span>
                    </div>

                    <div className="flex items-baseline justify-between gap-2">
                      <span className="font-semibold text-foreground text-xs truncate max-w-[180px]">{inv.party_name}</span>
                      <span className="font-bold text-emerald-400 font-mono text-sm">
                        ₹{parseFloat(inv.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </span>
                    </div>

                    <div className="flex items-center justify-end gap-1.5 pt-1 border-t border-border/40">
                      <button
                        onClick={() => handleStartEdit(inv)}
                        className="px-2.5 py-1 bg-blue-600/15 text-blue-400 rounded-lg text-xs font-semibold border border-blue-500/30 flex items-center gap-1"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                        <span>Edit</span>
                      </button>
                      <Link
                        href={`/sales/${inv.id}/print`}
                        className="px-2.5 py-1 bg-muted/60 text-foreground rounded-lg text-xs font-semibold border border-border/70 flex items-center gap-1"
                      >
                        <Printer className="w-3.5 h-3.5" />
                        <span>Print</span>
                      </Link>
                      <button
                        onClick={() => handleDeleteInvoice(inv.id, inv.voucher_number)}
                        className="px-2.5 py-1 bg-rose-600/15 text-rose-400 rounded-lg text-xs font-semibold border border-rose-500/30 flex items-center gap-1"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                        <span>Delete</span>
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              {/* Desktop Table (hidden md:block) */}
              <div className="hidden md:block overflow-x-auto">
                <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-border bg-muted/50 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    <th className="p-4">Invoice No.</th>
                    <th className="p-4">Date</th>
                    <th className="p-4">Party Name</th>
                    <th className="p-4 text-right">Total Amount</th>
                    <th className="p-4 text-center">Status</th>
                    <th className="p-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border text-xs">
                  {invoices.map((inv, idx) => {
                    const isFocused = focusedIndex === idx;
                    return (
                      <tr
                        id={`row-sales-${inv.id}`}
                        key={inv.id || idx}
                        onClick={() => setFocusedIndex(idx)}
                        onDoubleClick={() => router.push(`/sales/${inv.id}/print`)}
                        className={`transition-all duration-150 cursor-pointer group ${
                          isFocused
                            ? 'bg-primary/10 ring-2 ring-inset ring-primary/40 border-l-4 border-l-primary'
                            : 'hover:bg-muted/40'
                        }`}
                      >
                        <td className="p-4 font-mono font-semibold text-foreground text-sm">{inv.voucher_number}</td>
                        <td className="p-4 text-muted-foreground font-mono">{inv.date}</td>
                        <td className="p-4 text-foreground font-semibold text-sm">{inv.party_name}</td>
                        <td className="p-4 font-bold text-foreground text-right font-mono tabular-nums text-sm">₹{parseFloat(inv.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                        <td className="p-4 text-center">
                          {inv.isOffline || inv.status === 'PENDING_SYNC' ? (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/30">
                              <CloudOff className="w-3.5 h-3.5" />
                              Pending Sync
                            </span>
                          ) : (
                            <span className={`px-2.5 py-1 text-xs font-semibold rounded-full border ${inv.status === 'POSTED' ? 'bg-green-500/10 text-green-500 border-green-500/20' : 'bg-amber-500/10 text-amber-500 border-amber-500/20'}`}>
                              {inv.status}
                            </span>
                          )}
                        </td>
                        <td className="p-4 text-right">
                          <div className="flex items-center justify-end gap-2" onClick={(e) => e.stopPropagation()}>
                            <button
                              onClick={() => handleStartEdit(inv)}
                              className="px-3 py-1.5 bg-blue-600/15 hover:bg-blue-600/25 text-blue-400 rounded-lg text-xs font-semibold border border-blue-500/30 transition-colors flex items-center gap-1.5 cursor-pointer min-h-[36px]"
                              title="Edit Sales Invoice"
                            >
                              <Edit2 className="w-3.5 h-3.5" />
                              <span>Edit</span>
                            </button>

                            <Link
                              href={`/sales/${inv.id}/print`}
                              className="px-3 py-1.5 bg-muted/60 hover:bg-muted text-foreground rounded-lg text-xs font-semibold border border-border transition-colors flex items-center gap-1.5 cursor-pointer min-h-[36px]"
                              title="Print Invoice"
                            >
                              <Printer className="w-3.5 h-3.5" />
                              <span>Print</span>
                            </Link>

                            <button
                              onClick={() => handleDeleteInvoice(inv.id, inv.voucher_number)}
                              className="px-3 py-1.5 bg-rose-600/15 hover:bg-rose-600/25 text-rose-400 rounded-lg text-xs font-semibold border border-rose-500/30 transition-colors flex items-center gap-1.5 cursor-pointer min-h-[36px]"
                              title="Delete Invoice"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                              <span>Delete</span>
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              </div>

              {/* Pagination Controls */}
              {pagination && pagination.total_count > 0 && (
                <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-5 py-3.5 border-t border-border bg-muted/20 text-xs text-muted-foreground">
                  <div className="font-mono tabular-nums">
                    Showing <span className="font-semibold text-foreground">{pagination.offset + 1}</span> to{' '}
                    <span className="font-semibold text-foreground">
                      {Math.min(pagination.offset + pagination.limit, pagination.total_count)}
                    </span>{' '}
                    of <span className="font-semibold text-foreground">{pagination.total_count}</span> invoices
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => fetchInvoices(page - 1)}
                      disabled={page <= 1 || loading}
                      className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-input bg-muted/50 text-foreground hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer font-medium min-h-[36px]"
                    >
                      <ChevronLeft className="w-4 h-4" />
                      <span>Previous</span>
                    </button>

                    <div className="px-3 py-1.5 text-xs font-mono font-semibold text-foreground bg-muted rounded-lg border border-input">
                      Page {page} of {pagination.total_pages || 1}
                    </div>

                    <button
                      type="button"
                      onClick={() => fetchInvoices(page + 1)}
                      disabled={!pagination.has_more || page >= pagination.total_pages || loading}
                      className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-input bg-muted/50 text-foreground hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer font-medium min-h-[36px]"
                    >
                      <span>Next</span>
                      <ChevronRight className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              )}

              {/* Keyboard Shortcuts Hint Bar */}
              <div className="p-3.5 border-t border-border bg-muted/30 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs text-muted-foreground">
                <div className="hidden sm:flex items-center gap-2.5 flex-wrap">
                  <span className="flex items-center gap-1">
                    <kbd className="px-2 py-0.5 bg-muted rounded border border-input font-mono text-xs text-foreground font-semibold">↑</kbd>
                    <kbd className="px-2 py-0.5 bg-muted rounded border border-input font-mono text-xs text-foreground font-semibold">↓</kbd>
                    <span className="text-xs">Navigate</span>
                  </span>
                  <span>•</span>
                  <span className="flex items-center gap-1">
                    <kbd className="px-2 py-0.5 bg-muted rounded border border-input font-mono text-xs text-foreground font-semibold">Ctrl</kbd>
                    <span>+</span>
                    <kbd className="px-2 py-0.5 bg-muted rounded border border-input font-mono text-xs text-foreground font-semibold">Enter</kbd>
                    <span className="text-xs">Edit Invoice</span>
                  </span>
                  <span>•</span>
                  <span className="flex items-center gap-1">
                    <kbd className="px-2 py-0.5 bg-muted rounded border border-input font-mono text-xs text-foreground font-semibold">Enter</kbd>
                    <span className="text-xs">Print / View</span>
                  </span>
                  <span>•</span>
                  <span className="flex items-center gap-1">
                    <kbd className="px-2 py-0.5 bg-muted rounded border border-input font-mono text-xs text-foreground font-semibold">Alt</kbd>
                    <span>+</span>
                    <kbd className="px-2 py-0.5 bg-muted rounded border border-input font-mono text-xs text-foreground font-semibold">D</kbd>
                    <span className="text-xs">Delete</span>
                  </span>
                  <span>•</span>
                  <span className="flex items-center gap-1">
                    <kbd className="px-2 py-0.5 bg-muted rounded border border-input font-mono text-xs text-foreground font-semibold">Esc</kbd>
                    <span className="text-xs">Deselect</span>
                  </span>
                </div>
                {focusedIndex >= 0 && (
                  <span className="font-mono tabular-nums text-blue-400 font-semibold text-xs">
                    Invoice {focusedIndex + 1} of {invoices.length} selected
                  </span>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Edit Sales Invoice Modal */}
        <EditSalesInvoiceModal
          isOpen={isEditModalOpen}
          onClose={() => {
            setIsEditModalOpen(false);
            setEditingVoucher(null);
          }}
          voucher={editingVoucher}
          onUpdateSuccess={fetchInvoices}
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
          title="Delete Sales Invoice?"
          description={
            <span>
              Are you sure you want to permanently delete Sales Invoice{" "}
              <strong className="text-foreground">#{deleteConfirmParams?.number}</strong>?
              This will cancel the voucher, reverse the customer ledger entry, restore deducted inventory stock, and reverse GST liability.
            </span>
          }
          confirmText="Delete & Reverse"
          variant="danger"
        />
      </div>
    </DashboardLayout>
  );
}
