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
import { Edit2, Trash2, Printer, Plus } from 'lucide-react';

export default function SalesInvoiceList() {
  const router = useRouter();
  const { toast } = useToast();

  const [invoices, setInvoices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // Edit and Delete state
  const [editingVoucher, setEditingVoucher] = useState<any | null>(null);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [deleteConfirmParams, setDeleteConfirmParams] = useState<{ id: string; number: string } | null>(null);

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
      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const companyId = compRes.data.data[0]?.id;
      if (!companyId) return;

      const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/vouchers/${companyId}/`, { headers });
      
      // Filter only SALES vouchers
      const salesVouchers = (res.data.data || []).filter((v: any) => v.type === 'SALES');
      setInvoices(salesVouchers);
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
      const res = await axios.delete(`${API_BASE_URL}/api/vouchers/detail/${voucherId}/`, { headers });

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
        <div className="flex justify-between items-center border-b border-border pb-4">
          <div>
            <h1 className="text-3xl font-bold">Sales Invoices</h1>
            <p className="text-xs text-muted-foreground mt-1">Outward tax invoices and billing records</p>
          </div>
          <Link href="/sales/new" className="bg-blue-600 text-white px-4 py-2 rounded-xl text-xs font-bold shadow hover:bg-blue-700 transition-all flex items-center gap-1.5">
            <Plus className="w-3.5 h-3.5" />
            <span>Create Invoice</span>
            <kbd className="bg-white/20 px-1.5 py-0.5 rounded text-[10px]">F8</kbd>
          </Link>
        </div>
        
        <div className="bg-card text-card-foreground rounded-2xl shadow-sm border border-border flex-1 overflow-hidden flex flex-col">
          <div className="px-5 py-3.5 border-b border-border bg-gray-50 dark:bg-zinc-800/50 flex items-center justify-between">
            <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Previous Invoices</span>
            <span className="text-xs text-muted-foreground">Use ↑ / ↓ arrow keys to navigate, Ctrl+Enter to edit, Enter to print</span>
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
            <div className="flex-1 w-full overflow-auto flex flex-col justify-between">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-zinc-800 bg-zinc-900/40 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                    <th className="p-4">Invoice No.</th>
                    <th className="p-4">Date</th>
                    <th className="p-4">Party Name</th>
                    <th className="p-4 text-right">Total Amount</th>
                    <th className="p-4 text-center">Status</th>
                    <th className="p-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/50 text-xs">
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
                            ? 'bg-blue-500/10 ring-2 ring-inset ring-blue-500/60 border-l-4 border-l-blue-500'
                            : 'hover:bg-zinc-800/20'
                        }`}
                      >
                        <td className="p-4 font-mono font-medium text-white">{inv.voucher_number}</td>
                        <td className="p-4 text-gray-400 font-mono">{inv.date}</td>
                        <td className="p-4 text-gray-300 font-semibold">{inv.party_name}</td>
                        <td className="p-4 font-bold text-white text-right font-mono">₹ {parseFloat(inv.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                        <td className="p-4 text-center">
                          <span className={`px-2.5 py-1 text-xs font-bold rounded-full border ${inv.status === 'POSTED' ? 'bg-green-500/10 text-green-500 border border-green-500/20' : 'bg-amber-500/10 text-amber-500 border border-amber-500/20'}`}>
                            {inv.status}
                          </span>
                        </td>
                        <td className="p-4 text-right">
                          <div className="flex items-center justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
                            <button
                              onClick={() => handleStartEdit(inv)}
                              className="px-2.5 py-1 bg-blue-600/15 hover:bg-blue-600/25 text-blue-400 rounded-lg text-xs font-semibold border border-blue-500/30 transition-colors flex items-center gap-1 cursor-pointer"
                              title="Edit Sales Invoice"
                            >
                              <Edit2 className="w-3.5 h-3.5" />
                              <span>Edit</span>
                            </button>

                            <Link
                              href={`/sales/${inv.id}/print`}
                              className="px-2.5 py-1 bg-muted/60 hover:bg-muted text-foreground rounded-lg text-xs font-semibold border border-border/70 transition-colors flex items-center gap-1 cursor-pointer"
                              title="Print Invoice"
                            >
                              <Printer className="w-3.5 h-3.5" />
                              <span>Print</span>
                            </Link>

                            <button
                              onClick={() => handleDeleteInvoice(inv.id, inv.voucher_number)}
                              className="px-2.5 py-1 bg-rose-600/15 hover:bg-rose-600/25 text-rose-400 rounded-lg text-xs font-semibold border border-rose-500/30 transition-colors flex items-center gap-1 cursor-pointer"
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

              {/* Keyboard Shortcuts Hint Bar */}
              <div className="p-3 border-t border-zinc-800 bg-zinc-900/30 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs text-muted-foreground">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="flex items-center gap-1">
                    <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded border border-zinc-700 font-mono text-[10px] text-white font-bold">↑</kbd>
                    <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded border border-zinc-700 font-mono text-[10px] text-white font-bold">↓</kbd>
                    <span className="text-[11px]">Navigate</span>
                  </span>
                  <span>•</span>
                  <span className="flex items-center gap-1">
                    <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded border border-zinc-700 font-mono text-[10px] text-white font-bold">Ctrl</kbd>
                    <span>+</span>
                    <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded border border-zinc-700 font-mono text-[10px] text-white font-bold">Enter</kbd>
                    <span className="text-[11px]">Edit Invoice</span>
                  </span>
                  <span>•</span>
                  <span className="flex items-center gap-1">
                    <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded border border-zinc-700 font-mono text-[10px] text-white font-bold">Enter</kbd>
                    <span className="text-[11px]">Print / View</span>
                  </span>
                  <span>•</span>
                  <span className="flex items-center gap-1">
                    <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded border border-zinc-700 font-mono text-[10px] text-white font-bold">Alt</kbd>
                    <span>+</span>
                    <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded border border-zinc-700 font-mono text-[10px] text-white font-bold">D</kbd>
                    <span className="text-[11px]">Delete</span>
                  </span>
                  <span>•</span>
                  <span className="flex items-center gap-1">
                    <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded border border-zinc-700 font-mono text-[10px] text-white font-bold">Esc</kbd>
                    <span className="text-[11px]">Deselect</span>
                  </span>
                </div>
                {focusedIndex >= 0 && (
                  <span className="font-mono text-blue-400 font-semibold text-[11px]">
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
              <strong className="text-white">#{deleteConfirmParams?.number}</strong>?
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
