"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState } from "react";
import axios from "axios";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import DashboardLayout from "@/components/DashboardLayout";
import { useToast } from "@/context/ToastContext";
import EditPurchaseInvoiceModal from "@/components/modals/EditPurchaseInvoiceModal";
import ConfirmModal from "@/components/modals/ConfirmModal";
import { Edit2, Trash2, Eye, FileText, Plus } from "lucide-react";

export default function PurchaseInvoiceList() {
  const router = useRouter();
  const { toast } = useToast();

  const [invoices, setInvoices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedVoucher, setSelectedVoucher] = useState<any | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [zoomLevel, setZoomLevel] = useState<number>(100);

  // Edit Modal State
  const [editingVoucher, setEditingVoucher] = useState<any | null>(null);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  
  const [deleteConfirmParams, setDeleteConfirmParams] = useState<{ id: string, number: string } | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
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
      const purchaseVouchers = (res.data.data || []).filter((v: any) => v.type === "PURCHASE");
      setInvoices(purchaseVouchers);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenVoucherDetail = async (voucherId: string) => {
    setLoadingDetail(true);
    setSelectedVoucher(null);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.get(`${API_BASE_URL}/api/vouchers/${voucherId}/`, { headers });
      if (res.data.success) {
        setSelectedVoucher(res.data.data);
      }
    } catch (err) {
      console.error("Failed to load voucher detail:", err);
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleStartEdit = (inv: any) => {
    setEditingVoucher(inv);
    setIsEditModalOpen(true);
  };

  const executeDelete = async (voucherId: string) => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.delete(`${API_BASE_URL}/api/vouchers/detail/${voucherId}/`, { headers });

      if (res.data.success) {
        toast.success(res.data.message || `Invoice deleted and reversed successfully!`);
        setInvoices((prev) => prev.filter((i) => i.id !== voucherId));
        if (selectedVoucher?.id === voucherId) {
          setSelectedVoucher(null);
        }
      } else {
        toast.error("Failed to delete invoice", res.data.error);
      }
    } catch (err: any) {
      toast.error("Delete failed", err.response?.data?.error || err.message);
    }
  };

  const handleDeleteInvoice = (voucherId: string, voucherNumber: string) => {
    setDeleteConfirmParams({ id: voucherId, number: voucherNumber });
  };

  const [focusedIndex, setFocusedIndex] = useState<number>(-1);

  const scrollToInvoice = (index: number) => {
    if (index >= 0 && index < invoices.length) {
      const invId = invoices[index].id;
      const el = document.getElementById(`row-invoice-${invId}`);
      if (el) {
        el.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }
    }
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (isEditModalOpen || deleteConfirmParams !== null) return;

      const activeElement = document.activeElement;
      const isInputFocused = activeElement && (
        activeElement.tagName === "INPUT" ||
        activeElement.tagName === "TEXTAREA" ||
        activeElement.tagName === "SELECT"
      );
      if (isInputFocused) return;

      if (invoices.length === 0) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        setFocusedIndex(prev => {
          const next = prev < invoices.length - 1 ? prev + 1 : 0;
          scrollToInvoice(next);
          return next;
        });
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setFocusedIndex(prev => {
          const next = prev > 0 ? prev - 1 : invoices.length - 1;
          scrollToInvoice(next);
          return next;
        });
      } else if (e.key === "Home") {
        e.preventDefault();
        setFocusedIndex(0);
        scrollToInvoice(0);
      } else if (e.key === "End") {
        e.preventDefault();
        setFocusedIndex(invoices.length - 1);
        scrollToInvoice(invoices.length - 1);
      } else if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        // TALLY ALTER SHORTCUT: Ctrl + Enter opens the full Edit Invoice Modal!
        if (focusedIndex >= 0 && focusedIndex < invoices.length) {
          e.preventDefault();
          handleStartEdit(invoices[focusedIndex]);
        }
      } else if (e.key === "Enter") {
        // Enter views details of selected invoice
        if (focusedIndex >= 0 && focusedIndex < invoices.length) {
          e.preventDefault();
          handleOpenVoucherDetail(invoices[focusedIndex].id);
        }
      } else if (e.key.toLowerCase() === "e" && !e.ctrlKey && !e.metaKey) {
        if (focusedIndex >= 0 && focusedIndex < invoices.length) {
          e.preventDefault();
          handleStartEdit(invoices[focusedIndex]);
        }
      } else if ((e.altKey && e.key.toLowerCase() === "d") || e.key === "Delete") {
        if (focusedIndex >= 0 && focusedIndex < invoices.length) {
          e.preventDefault();
          const target = invoices[focusedIndex];
          handleDeleteInvoice(target.id, target.voucher_number);
        }
      } else if (e.key === "Escape") {
        if (selectedVoucher) {
          setSelectedVoucher(null);
        } else {
          setFocusedIndex(-1);
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [invoices, focusedIndex, isEditModalOpen, selectedVoucher]);

  return (
    <DashboardLayout>
      <div className="space-y-6 flex flex-col h-full pb-12">
        
        {/* Header */}
        <div className="flex justify-between items-center border-b border-border pb-4">
          <div>
            <h1 className="text-3xl font-black text-foreground tracking-tight">Purchase Invoices</h1>
            <p className="text-xs text-muted-foreground mt-1">Inward supplier bills and attached documents</p>
          </div>
          <Link
            href="/purchases/new"
            className="bg-primary hover:bg-primary/90 text-primary-foreground px-4 py-2 rounded-xl text-xs font-bold shadow-md transition-all flex items-center gap-1.5"
          >
            <Plus className="w-4 h-4" />
            <span>Create / Scan Invoice</span>
            <kbd className="bg-primary-foreground/20 px-1.5 py-0.5 rounded text-[10px]">F9</kbd>
          </Link>
        </div>

        {/* Invoices Table Card */}
        <div className="bg-card text-card-foreground rounded-2xl shadow-sm border border-border/80 flex-1 overflow-hidden flex flex-col">
          <div className="px-5 py-3.5 border-b border-border/70 bg-muted/20 flex items-center justify-between">
            <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Previous Invoices</span>
            <span className="text-xs text-muted-foreground">Click any row to inspect original bill & line items</span>
          </div>

          {loading ? (
            <div className="flex items-center justify-center p-16 text-muted-foreground text-sm">
              Loading invoices...
            </div>
          ) : invoices.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-16 text-center bg-card">
              <div className="w-16 h-16 rounded-2xl bg-muted/60 text-muted-foreground flex items-center justify-center mb-3">
                <FileText className="w-8 h-8" />
              </div>
              <h3 className="text-xl font-bold mb-1">No Purchase Invoices Yet</h3>
              <p className="text-muted-foreground max-w-md mx-auto mb-6 text-sm">
                Upload your first supplier bill to automatically extract data and store attached documents.
              </p>
              <Link
                href="/purchases/new"
                className="bg-primary hover:bg-primary/90 text-primary-foreground px-5 py-2.5 rounded-xl shadow font-bold text-xs flex items-center gap-1.5"
              >
                <Plus className="w-4 h-4" />
                <span>Scan First Invoice</span>
              </Link>
            </div>
          ) : (
            <div className="flex-1 w-full overflow-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-border/70 bg-muted/30 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    <th className="p-4">Invoice No.</th>
                    <th className="p-4">Date</th>
                    <th className="p-4">Supplier Party</th>
                    <th className="p-4 text-right">Total Amount</th>
                    <th className="p-4 text-center">Status</th>
                    <th className="p-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40 text-xs">
                  {invoices.map((inv, idx) => {
                    const isFocused = focusedIndex === idx;
                    return (
                      <tr
                        id={`row-invoice-${inv.id}`}
                        key={inv.id}
                        onClick={() => {
                          setFocusedIndex(idx);
                          handleOpenVoucherDetail(inv.id);
                        }}
                        className={`transition-all duration-150 cursor-pointer group ${
                          isFocused
                            ? "bg-blue-500/10 ring-2 ring-inset ring-blue-500/60 border-l-4 border-l-blue-500"
                            : "hover:bg-muted/20"
                        }`}
                      >
                      {/* Invoice No */}
                      <td className="p-4 font-mono font-medium text-foreground flex items-center gap-2">
                        <span className="font-bold">{inv.voucher_number}</span>
                        {inv.has_attachment && (
                          <span className="px-1.5 py-0.5 bg-blue-500/15 text-blue-400 rounded text-[10px] font-bold border border-blue-500/30">
                            📎 Doc
                          </span>
                        )}
                      </td>

                      {/* Date */}
                      <td className="p-4 text-muted-foreground font-mono">{inv.date}</td>

                      {/* Party */}
                      <td className="p-4 text-foreground font-semibold">{inv.party_name}</td>

                      {/* Amount */}
                      <td className="p-4 font-bold text-foreground font-mono text-right text-sm">
                        ₹ {parseFloat(inv.total_amount).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </td>

                      {/* Status */}
                      <td className="p-4 text-center">
                        <span className={`px-2.5 py-1 text-[10px] font-bold rounded-full border ${
                          inv.status === "POSTED"
                            ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                            : "bg-amber-500/10 text-amber-400 border-amber-500/20"
                        }`}>
                          {inv.status}
                        </span>
                      </td>

                      {/* Actions */}
                      <td className="p-4 text-right">
                        <div className="flex items-center justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
                          <button
                            onClick={() => handleOpenVoucherDetail(inv.id)}
                            className="px-2.5 py-1 bg-muted/60 hover:bg-muted text-foreground rounded-lg text-xs font-semibold border border-border/70 transition-colors flex items-center gap-1 cursor-pointer"
                            title="View Document"
                          >
                            <Eye className="w-3.5 h-3.5" />
                            <span>View</span>
                          </button>
                          
                          <button
                            onClick={() => handleStartEdit(inv)}
                            className="px-2.5 py-1 bg-blue-600/15 hover:bg-blue-600/25 text-blue-400 rounded-lg text-xs font-semibold border border-blue-500/30 transition-colors flex items-center gap-1 cursor-pointer"
                            title="Edit Invoice"
                          >
                            <Edit2 className="w-3.5 h-3.5" />
                            <span>Edit</span>
                          </button>

                          <button
                            onClick={() => handleDeleteInvoice(inv.id, inv.voucher_number)}
                            className="px-2.5 py-1 bg-rose-600/15 hover:bg-rose-600/25 text-rose-400 rounded-lg text-xs font-semibold border border-rose-500/30 transition-colors flex items-center gap-1 cursor-pointer"
                            title="Delete Invoice & Reverse Stock"
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
              <div className="p-3 border-t border-border/60 bg-muted/20 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs text-muted-foreground">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="flex items-center gap-1">
                    <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">↑</kbd>
                    <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">↓</kbd>
                    <span className="text-[11px]">Navigate</span>
                  </span>
                  <span>•</span>
                  <span className="flex items-center gap-1">
                    <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">Ctrl</kbd>
                    <span>+</span>
                    <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">Enter</kbd>
                    <span className="text-[11px]">Edit Invoice (Tally Alter)</span>
                  </span>
                  <span>•</span>
                  <span className="flex items-center gap-1">
                    <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">Enter</kbd>
                    <span className="text-[11px]">View Bill</span>
                  </span>
                  <span>•</span>
                  <span className="flex items-center gap-1">
                    <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">Alt</kbd>
                    <span>+</span>
                    <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">D</kbd>
                    <span className="text-[11px]">Delete</span>
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

        {/* Voucher Detail & Document Viewer Modal */}
        {(selectedVoucher || loadingDetail) && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-xs p-4 animate-in fade-in">
            <div className="w-full max-w-5xl bg-card border border-border rounded-2xl shadow-2xl overflow-hidden flex flex-col text-foreground max-h-[90vh]">
              
              {/* Modal Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-border/70 bg-muted/20">
                <div className="flex items-center gap-3">
                  <span className="text-xl">🧾</span>
                  <div>
                    <h3 className="font-bold text-base text-foreground">
                      Purchase Invoice #{selectedVoucher?.voucher_number || "..."}
                    </h3>
                    <p className="text-xs text-muted-foreground">
                      Party: {selectedVoucher?.party?.name || "N/A"} • Date: {selectedVoucher?.date}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {selectedVoucher && (
                    <>
                      <button
                        onClick={() => {
                          handleStartEdit(selectedVoucher);
                        }}
                        className="px-3 py-1.5 bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 border border-blue-500/30 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                        <span>Edit</span>
                      </button>

                      <button
                        onClick={() => {
                          handleDeleteInvoice(selectedVoucher.id, selectedVoucher.voucher_number);
                        }}
                        className="px-3 py-1.5 bg-rose-600/20 hover:bg-rose-600/30 text-rose-400 border border-rose-500/30 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                        <span>Delete</span>
                      </button>
                    </>
                  )}

                  <button
                    onClick={() => setSelectedVoucher(null)}
                    className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
                  >
                    ✕
                  </button>
                </div>
              </div>

              {/* Modal Body */}
              <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {loadingDetail ? (
                  <div className="flex items-center justify-center p-12 text-muted-foreground">
                    Loading voucher details & attached invoice...
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Left: Extracted Details & Items */}
                    <div className="space-y-4">
                      <div className="bg-muted/30 p-4 rounded-xl border border-border/70 space-y-2 text-xs">
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Supplier:</span>
                          <span className="font-bold text-foreground">{selectedVoucher?.party?.name}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">GSTIN:</span>
                          <span className="font-mono text-muted-foreground">{selectedVoucher?.party?.gstin || "Unregistered"}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Invoice Number:</span>
                          <span className="font-mono text-foreground">{selectedVoucher?.voucher_number}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Date:</span>
                          <span className="font-mono text-foreground">{selectedVoucher?.date}</span>
                        </div>
                        <div className="flex justify-between border-t border-border/50 pt-2 font-bold text-sm">
                          <span>Total Amount:</span>
                          <span className="text-emerald-400 font-mono">
                            ₹ {parseFloat(selectedVoucher?.total_amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                          </span>
                        </div>
                      </div>

                      {/* Items Table */}
                      <div>
                        <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">
                          Line Items ({selectedVoucher?.items?.length || 0})
                        </h4>
                        <div className="border border-border/70 rounded-xl overflow-hidden">
                          <table className="w-full text-xs text-left">
                            <thead className="bg-muted/40 border-b border-border/60 text-muted-foreground">
                              <tr>
                                <th className="p-2.5">Item</th>
                                <th className="p-2.5 text-right">Qty</th>
                                <th className="p-2.5 text-right">Rate</th>
                                <th className="p-2.5 text-right">Total</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-border/30">
                              {selectedVoucher?.items?.map((item: any, idx: number) => (
                                <tr key={idx} className="hover:bg-muted/20">
                                  <td className="p-2.5">
                                    <p className="font-medium text-foreground">{item.product_name}</p>
                                    <p className="text-[10px] text-muted-foreground font-mono">HSN: {item.hsn_code || "—"}</p>
                                  </td>
                                  <td className="p-2.5 text-right font-mono">{item.quantity} {item.unit}</td>
                                  <td className="p-2.5 text-right font-mono">₹{parseFloat(item.rate).toFixed(2)}</td>
                                  <td className="p-2.5 text-right font-mono font-bold text-emerald-400">
                                    ₹{parseFloat(item.total_amount).toFixed(2)}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </div>

                    {/* Right: Document Preview */}
                    <div className="border border-border/70 rounded-xl overflow-hidden bg-muted/20 flex flex-col min-h-[400px]">
                      <div className="p-2.5 border-b border-border/60 bg-muted/40 flex items-center justify-between text-xs">
                        <span className="font-bold text-muted-foreground">Attached Document</span>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => setZoomLevel((z) => Math.max(50, z - 25))}
                            className="px-2 py-0.5 bg-muted rounded text-[11px] hover:bg-muted/80"
                          >
                            -
                          </button>
                          <span className="text-[11px] font-mono">{zoomLevel}%</span>
                          <button
                            onClick={() => setZoomLevel((z) => Math.min(200, z + 25))}
                            className="px-2 py-0.5 bg-muted rounded text-[11px] hover:bg-muted/80"
                          >
                            +
                          </button>
                        </div>
                      </div>

                      <div className="flex-1 flex items-center justify-center p-4 overflow-auto">
                        {selectedVoucher?.attachment_data ? (
                          selectedVoucher.attachment_mime === "application/pdf" ? (
                            <iframe
                              src={selectedVoucher.attachment_data}
                              className="w-full h-full border-0 rounded-lg min-h-[450px]"
                              style={{ transform: `scale(${zoomLevel / 100})`, transformOrigin: "top center" }}
                              title="Original Invoice PDF"
                            />
                          ) : (
                            <img
                              src={selectedVoucher.attachment_data}
                              alt="Attached Invoice"
                              className="max-w-full max-h-[500px] object-contain rounded-lg shadow-sm"
                              style={{ transform: `scale(${zoomLevel / 100})`, transformOrigin: "center center" }}
                            />
                          )
                        ) : (
                          <div className="text-center p-8 text-muted-foreground">
                            <span className="text-3xl block mb-2">📄</span>
                            <p className="text-xs">No attachment stored for this voucher.</p>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Edit Modal */}
        <EditPurchaseInvoiceModal
          isOpen={isEditModalOpen}
          onClose={() => setIsEditModalOpen(false)}
          voucher={editingVoucher}
          onUpdateSuccess={fetchInvoices}
        />

        {/* Delete Confirm Modal */}
        <ConfirmModal
          isOpen={deleteConfirmParams !== null}
          onClose={() => setDeleteConfirmParams(null)}
          onConfirm={() => deleteConfirmParams && executeDelete(deleteConfirmParams.id)}
          title="Delete Invoice"
          description={
            <>
              Are you sure you want to delete purchase invoice <span className="text-white font-semibold">#{deleteConfirmParams?.number}</span>? 
              This will reverse the stock impact and accounting balances.
            </>
          }
          confirmText="Delete & Reverse"
          cancelText="Cancel"
          variant="danger"
        />
      </div>
    </DashboardLayout>
  );
}
