"use client";
import React, { useState, useEffect } from "react";
import axios from "axios";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken } from "@/utils/auth";
import { useToast } from "@/context/ToastContext";
import {
  X,
  Check,
  Calendar,
  Hash,
  FileText,
  User,
  Plus,
  Trash2,
  Package,
  Layers,
  Calculator,
} from "lucide-react";

interface EditableItem {
  id?: string;
  product_name: string;
  hsn_code: string;
  quantity: number;
  unit: string;
  rate: number;
  gst_rate: number;
}

interface EditPurchaseInvoiceModalProps {
  isOpen: boolean;
  onClose: () => void;
  voucher: any;
  onUpdateSuccess: () => void;
}

export default function EditPurchaseInvoiceModal({
  isOpen,
  onClose,
  voucher,
  onUpdateSuccess,
}: EditPurchaseInvoiceModalProps) {
  const { toast } = useToast();

  const [loadingDetails, setLoadingDetails] = useState(false);
  const [invoiceNumber, setInvoiceNumber] = useState("");
  const [invoiceDate, setInvoiceDate] = useState("");
  const [partyName, setPartyName] = useState("");
  const [narration, setNarration] = useState("");
  const [items, setItems] = useState<EditableItem[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isOpen && voucher?.id) {
      loadFullVoucher();
    }
  }, [isOpen, voucher?.id]);

  const loadFullVoucher = async () => {
    setLoadingDetails(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.get(`${API_BASE_URL}/api/vouchers/${voucher.id}/`, { headers });

      if (res.data.success && res.data.data) {
        const v = res.data.data;
        setInvoiceNumber(v.voucher_number || "");
        setInvoiceDate(v.date || "");
        setPartyName(v.party?.name || "");
        setNarration(v.narration || "");

        const loadedItems: EditableItem[] = (v.items || []).map((item: any) => ({
          id: item.id,
          product_name: item.product_name || "",
          hsn_code: item.hsn_code || "",
          quantity: parseFloat(item.quantity) || 1,
          unit: item.unit || "PCS",
          rate: parseFloat(item.rate) || 0,
          gst_rate: parseFloat(item.gst_rate) || 18,
        }));

        if (loadedItems.length === 0) {
          loadedItems.push({
            product_name: "",
            hsn_code: "",
            quantity: 1,
            unit: "PCS",
            rate: 0,
            gst_rate: 18,
          });
        }
        setItems(loadedItems);
      }
    } catch (err: any) {
      console.error(err);
      toast.error("Failed to load full invoice details");
    } finally {
      setLoadingDetails(false);
    }
  };

  if (!isOpen || !voucher) return null;

  const updateItemField = (index: number, field: keyof EditableItem, value: any) => {
    setItems((prev) => {
      const copy = [...prev];
      copy[index] = { ...copy[index], [field]: value };
      return copy;
    });
  };

  const handleAddItem = () => {
    setItems((prev) => [
      ...prev,
      {
        product_name: "",
        hsn_code: "",
        quantity: 1,
        unit: "PCS",
        rate: 0,
        gst_rate: 18,
      },
    ]);
  };

  const handleRemoveItem = (index: number) => {
    if (items.length <= 1) {
      toast.warning("Invoice must contain at least one line item.");
      return;
    }
    setItems((prev) => prev.filter((_, i) => i !== index));
  };

  // Calculations
  const taxableTotal = items.reduce((acc, item) => acc + (item.quantity * item.rate), 0);
  const totalTax = items.reduce(
    (acc, item) => acc + (item.quantity * item.rate * (item.gst_rate / 100)),
    0
  );
  const grandTotal = taxableTotal + totalTax;

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validation
    for (let i = 0; i < items.length; i++) {
      const it = items[i];
      if (!it.product_name.trim()) {
        toast.warning(`Row ${i + 1} is missing an Item Name / Description!`);
        return;
      }
      if (it.quantity <= 0) {
        toast.warning(`Row ${i + 1} must have a quantity greater than 0!`);
        return;
      }
      if (it.rate < 0) {
        toast.warning(`Row ${i + 1} cannot have a negative rate!`);
        return;
      }
    }

    setSaving(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      const payload = {
        voucher_number: invoiceNumber.trim(),
        voucher_date: invoiceDate,
        party_name: partyName.trim(),
        narration: narration.trim(),
        items: items.map((it) => ({
          product_name: it.product_name.trim(),
          hsn_code: it.hsn_code.trim(),
          quantity: it.quantity,
          rate: it.rate,
          unit: it.unit.trim().toUpperCase() || "PCS",
          gst_rate: it.gst_rate,
        })),
      };

      const res = await axios.patch(
        `${API_BASE_URL}/api/vouchers/${voucher.id}/`,
        payload,
        { headers }
      );

      if (res.data.success) {
        toast.success(
          "Invoice updated successfully!",
          "Quantities, rates, HSN, and inventory stock have been recalculated."
        );
        onUpdateSuccess();
        onClose();
      } else {
        toast.error("Failed to update invoice", res.data.error);
      }
    } catch (err: any) {
      toast.error("Update error", err.response?.data?.error || err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/75 backdrop-blur-xs" onClick={onClose} />

      {/* Modal Card */}
      <div className="relative bg-card border border-border/80 w-full max-w-4xl rounded-2xl shadow-2xl overflow-hidden z-10 animate-in fade-in zoom-in-95 duration-200 flex flex-col max-h-[92vh]">
        
        {/* Header */}
        <div className="px-6 py-4 border-b border-border/60 bg-muted/20 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20 flex items-center justify-center">
              <Package className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-base font-bold text-foreground">Edit Purchase Invoice</h3>
              <p className="text-xs text-muted-foreground">
                Modify item names, HSN codes, quantities, rates, and invoice details
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        {loadingDetails ? (
          <div className="flex-1 flex items-center justify-center p-16 text-muted-foreground text-sm">
            Loading full line items & invoice records...
          </div>
        ) : (
          <form onSubmit={handleSave} className="flex-1 overflow-y-auto p-6 space-y-6">
            
            {/* Top Invoice Metadata Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 bg-muted/20 p-4 rounded-xl border border-border/60">
              <div>
                <label className="text-xs font-semibold text-muted-foreground uppercase flex items-center gap-1.5 mb-1">
                  <Hash className="w-3.5 h-3.5 text-blue-400" />
                  Bill / Invoice No. *
                </label>
                <input
                  type="text"
                  required
                  value={invoiceNumber}
                  onChange={(e) => setInvoiceNumber(e.target.value)}
                  className="w-full bg-muted/40 border border-border/70 text-foreground font-mono text-xs px-3 py-1.5 rounded-lg outline-none focus:ring-1 focus:ring-blue-500 font-bold"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-muted-foreground uppercase flex items-center gap-1.5 mb-1">
                  <Calendar className="w-3.5 h-3.5 text-blue-400" />
                  Invoice Date *
                </label>
                <input
                  type="date"
                  required
                  value={invoiceDate}
                  onChange={(e) => setInvoiceDate(e.target.value)}
                  className="w-full bg-muted/40 border border-border/70 text-foreground font-mono text-xs px-3 py-1.5 rounded-lg outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-muted-foreground uppercase flex items-center gap-1.5 mb-1">
                  <User className="w-3.5 h-3.5 text-blue-400" />
                  Supplier / Party Name *
                </label>
                <input
                  type="text"
                  required
                  value={partyName}
                  onChange={(e) => setPartyName(e.target.value)}
                  className="w-full bg-muted/40 border border-border/70 text-foreground text-xs px-3 py-1.5 rounded-lg outline-none focus:ring-1 focus:ring-blue-500 font-semibold"
                />
              </div>
            </div>

            {/* Line Items Grid */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Layers className="w-4 h-4 text-muted-foreground" />
                  <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    Line Items ({items.length})
                  </h4>
                </div>
                <button
                  type="button"
                  onClick={handleAddItem}
                  className="px-3 py-1 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 rounded-lg text-xs font-bold transition-colors flex items-center gap-1 cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Add Line Item</span>
                </button>
              </div>

              <div className="border border-border/70 rounded-xl overflow-hidden">
                <table className="w-full text-xs text-left border-collapse">
                  <thead className="bg-muted/40 border-b border-border/60 text-muted-foreground uppercase text-[10px] tracking-wider font-semibold">
                    <tr>
                      <th className="p-2.5 w-6">#</th>
                      <th className="p-2.5">Item Name / Size</th>
                      <th className="p-2.5 w-24">HSN Code</th>
                      <th className="p-2.5 w-20 text-right">Qty</th>
                      <th className="p-2.5 w-16">Unit</th>
                      <th className="p-2.5 w-24 text-right">Rate (₹)</th>
                      <th className="p-2.5 w-20 text-right">GST %</th>
                      <th className="p-2.5 w-24 text-right">Total (₹)</th>
                      <th className="p-2.5 w-10 text-center"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/30">
                    {items.map((item, idx) => {
                      const lineTaxable = item.quantity * item.rate;
                      const lineTax = lineTaxable * (item.gst_rate / 100);
                      const lineTotal = lineTaxable + lineTax;

                      return (
                        <tr key={idx} className="hover:bg-muted/15">
                          <td className="p-2 text-muted-foreground font-mono text-center">{idx + 1}</td>
                          
                          {/* Item Name */}
                          <td className="p-2">
                            <input
                              type="text"
                              required
                              placeholder="e.g. A-18 V-Belt"
                              value={item.product_name}
                              onChange={(e) => updateItemField(idx, "product_name", e.target.value)}
                              className="w-full bg-muted/40 border border-border/50 text-foreground font-medium px-2 py-1 rounded outline-none focus:ring-1 focus:ring-blue-500"
                            />
                          </td>

                          {/* HSN */}
                          <td className="p-2">
                            <input
                              type="text"
                              placeholder="4010"
                              value={item.hsn_code}
                              onChange={(e) => updateItemField(idx, "hsn_code", e.target.value)}
                              className="w-full bg-muted/40 border border-border/50 text-foreground font-mono px-2 py-1 rounded outline-none focus:ring-1 focus:ring-blue-500 text-center"
                            />
                          </td>

                          {/* Qty */}
                          <td className="p-2 text-right">
                            <input
                              type="number"
                              step="any"
                              min="0.01"
                              required
                              value={item.quantity}
                              onChange={(e) => updateItemField(idx, "quantity", parseFloat(e.target.value) || 0)}
                              className="w-full bg-muted/40 border border-border/50 text-foreground font-mono px-2 py-1 rounded outline-none focus:ring-1 focus:ring-blue-500 text-right font-bold"
                            />
                          </td>

                          {/* Unit */}
                          <td className="p-2">
                            <input
                              type="text"
                              value={item.unit}
                              onChange={(e) => updateItemField(idx, "unit", e.target.value.toUpperCase())}
                              className="w-full bg-muted/40 border border-border/50 text-muted-foreground font-mono text-[11px] px-1.5 py-1 rounded outline-none text-center"
                            />
                          </td>

                          {/* Rate */}
                          <td className="p-2 text-right">
                            <input
                              type="number"
                              step="0.01"
                              min="0"
                              required
                              value={item.rate}
                              onChange={(e) => updateItemField(idx, "rate", parseFloat(e.target.value) || 0)}
                              className="w-full bg-muted/40 border border-border/50 text-foreground font-mono px-2 py-1 rounded outline-none focus:ring-1 focus:ring-blue-500 text-right font-bold"
                            />
                          </td>

                          {/* GST Rate */}
                          <td className="p-2 text-right">
                            <select
                              value={item.gst_rate}
                              onChange={(e) => updateItemField(idx, "gst_rate", parseFloat(e.target.value) || 0)}
                              className="w-full bg-zinc-900 border border-zinc-700 text-white font-mono text-[11px] px-1 py-1 rounded outline-none text-right cursor-pointer"
                            >
                              <option value={0} className="bg-zinc-900 text-white">0%</option>
                              <option value={5} className="bg-zinc-900 text-white">5%</option>
                              <option value={12} className="bg-zinc-900 text-white">12%</option>
                              <option value={18} className="bg-zinc-900 text-white">18%</option>
                              <option value={28} className="bg-zinc-900 text-white">28%</option>
                            </select>
                          </td>

                          {/* Line Total */}
                          <td className="p-2 text-right font-mono font-bold text-emerald-400 whitespace-nowrap">
                            ₹{lineTotal.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </td>

                          {/* Action */}
                          <td className="p-2 text-center">
                            <button
                              type="button"
                              onClick={() => handleRemoveItem(idx)}
                              className="p-1 text-muted-foreground hover:text-rose-400 transition-colors cursor-pointer"
                              title="Delete line"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Bottom Row: Narration & Financial Summary */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
              <div>
                <label className="text-xs font-semibold text-muted-foreground uppercase flex items-center gap-1.5 mb-1.5">
                  <FileText className="w-3.5 h-3.5" />
                  Narration / Notes
                </label>
                <textarea
                  rows={3}
                  value={narration}
                  onChange={(e) => setNarration(e.target.value)}
                  placeholder="Notes, delivery challan reference, or terms..."
                  className="w-full bg-muted/30 border border-border/70 text-foreground text-xs px-3.5 py-2 rounded-xl outline-none focus:ring-1 focus:ring-blue-500 resize-none"
                />
              </div>

              {/* Live Totals Card */}
              <div className="bg-muted/30 p-4 rounded-xl border border-border/70 space-y-2 text-xs">
                <div className="flex justify-between text-muted-foreground">
                  <span>Taxable Subtotal:</span>
                  <span className="font-mono text-foreground">
                    ₹{taxableTotal.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </span>
                </div>
                <div className="flex justify-between text-muted-foreground">
                  <span>Total Taxes (GST):</span>
                  <span className="font-mono text-foreground">
                    ₹{totalTax.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </span>
                </div>
                <div className="flex justify-between border-t border-border/50 pt-2 font-bold text-sm">
                  <span>Net Invoice Amount:</span>
                  <span className="font-mono text-emerald-400 text-base">
                    ₹{grandTotal.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </span>
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="pt-4 border-t border-border/60 flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                Saving will update voucher totals, ledger balances, and recalculate inventory stock.
              </span>

              <div className="flex items-center gap-2.5">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 text-xs font-medium text-muted-foreground hover:text-foreground rounded-lg hover:bg-muted/60 transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="px-5 py-2 bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 rounded-xl text-xs font-bold shadow-sm transition-all flex items-center gap-1.5 cursor-pointer"
                >
                  <Check className="w-4 h-4" />
                  <span>{saving ? "Saving Changes..." : "Save Changes"}</span>
                </button>
              </div>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
