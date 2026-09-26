"use client";

import React, { useState, useMemo } from "react";
import {
  X,
  Printer,
  Download,
  Share2,
  Copy,
  Check,
  Building2,
  FileSpreadsheet,
  Trash2,
  Calendar,
  Truck,
  FileText,
  Plus,
  Minus,
} from "lucide-react";
import { useToast } from "@/context/ToastContext";

export interface POOrderItem {
  product_id: string;
  name: string;
  brand: string;
  sku: string;
  unit: string;
  category_name: string;
  current_stock: number;
  order_quantity: number;
  purchase_price: number;
  last_supplier?: string;
  urgency?: string;
  urgency_label?: string;
}

interface PurchaseOrderDraftModalProps {
  isOpen: boolean;
  onClose: () => void;
  items: POOrderItem[];
  companyName: string;
  companyGstin?: string;
  companyAddress?: string;
  onUpdateQuantity?: (productId: string, newQty: number) => void;
  onRemoveItem?: (productId: string) => void;
}

export default function PurchaseOrderDraftModal({
  isOpen,
  onClose,
  items,
  companyName,
  companyGstin,
  companyAddress,
  onUpdateQuantity,
  onRemoveItem,
}: PurchaseOrderDraftModalProps) {
  const { toast } = useToast();
  const [copied, setCopied] = useState(false);

  // Auto-generate PO Number and default Date
  const defaultPoNumber = useMemo(() => {
    const today = new Date();
    const yr = today.getFullYear();
    const mo = String(today.getMonth() + 1).padStart(2, "0");
    const rand = Math.floor(1000 + Math.random() * 9000);
    return `PO-${yr}${mo}-${rand}`;
  }, []);

  const [poNumber, setPoNumber] = useState(defaultPoNumber);
  const [poDate, setPoDate] = useState(() => {
    return new Date().toISOString().split("T")[0];
  });
  const [vendorName, setVendorName] = useState("");
  const [notes, setNotes] = useState("Please confirm stock availability, rates, and dispatch timeline.");

  // Detect unique vendors from items for auto-suggest
  const supplierSuggestions = useMemo(() => {
    const suppliers = new Set<string>();
    items.forEach((it) => {
      if (it.last_supplier && it.last_supplier !== "Catalog Master" && it.last_supplier !== "Direct") {
        suppliers.add(it.last_supplier);
      }
    });
    return Array.from(suppliers);
  }, [items]);

  // Totals calculations
  const totalUnits = useMemo(() => {
    return items.reduce((acc, it) => acc + (Number(it.order_quantity) || 0), 0);
  }, [items]);

  const totalEstimatedCost = useMemo(() => {
    return items.reduce(
      (acc, it) => acc + (Number(it.order_quantity) || 0) * (Number(it.purchase_price) || 0),
      0
    );
  }, [items]);

  if (!isOpen) return null;

  // 1. Download CSV
  const handleDownloadCsv = () => {
    if (items.length === 0) {
      toast.error("No items in purchase order to export");
      return;
    }

    const headers = [
      "S.No",
      "Item Name",
      "Brand",
      "SKU",
      "Category",
      "Current Stock",
      "Order Quantity",
      "Unit",
      "Expected Unit Rate (INR)",
      "Estimated Amount (INR)",
      "Suggested Supplier",
    ];

    const rows = items.map((it, idx) => [
      idx + 1,
      `"${it.name.replace(/"/g, '""')}"`,
      `"${(it.brand || "").replace(/"/g, '""')}"`,
      `"${(it.sku || "").replace(/"/g, '""')}"`,
      `"${(it.category_name || "").replace(/"/g, '""')}"`,
      it.current_stock,
      it.order_quantity,
      it.unit || "PCS",
      (it.purchase_price || 0).toFixed(2),
      ((it.order_quantity || 0) * (it.purchase_price || 0)).toFixed(2),
      `"${(it.last_supplier || "").replace(/"/g, '""')}"`,
    ]);

    const csvContent =
      "data:text/csv;charset=utf-8," +
      [`# PURCHASE ORDER: ${poNumber}`, `# Company: ${companyName}`, `# Date: ${poDate}`, `# Vendor: ${vendorName || "General"}`]
        .join("\n") +
      "\n\n" +
      [headers.join(","), ...rows.map((r) => r.join(","))].join("\n") +
      `\n\nTotal Line Items,${items.length},,,,Total Units,${totalUnits},,Total Estimated Cost,${totalEstimatedCost.toFixed(2)}`;

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `${poNumber}_Purchase_Order.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    toast.success("Purchase Order CSV downloaded successfully");
  };

  // 2. Generate WhatsApp Text
  const generateWhatsAppMessage = () => {
    const formattedDate = new Date(poDate).toLocaleDateString("en-IN", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });

    let msg = `*PURCHASE ORDER: ${poNumber}*\n`;
    msg += `*Company:* ${companyName}\n`;
    if (companyGstin) msg += `*GSTIN:* ${companyGstin}\n`;
    msg += `*Date:* ${formattedDate}\n`;
    if (vendorName) msg += `*To Vendor:* ${vendorName}\n`;
    msg += `----------------------------------------\n`;
    msg += `*REQUIRED ITEMS / INDENT:*\n`;

    items.forEach((it, idx) => {
      const brandStr = it.brand ? ` (${it.brand})` : "";
      const rateStr = it.purchase_price > 0 ? ` @ ₹${it.purchase_price.toFixed(2)}` : "";
      const lineTotal = it.purchase_price > 0 ? ` = ₹${((it.order_quantity || 0) * it.purchase_price).toFixed(2)}` : "";
      msg += `${idx + 1}. *${it.name}*${brandStr} — *${it.order_quantity} ${it.unit || "PCS"}*${rateStr}${lineTotal}\n`;
    });

    msg += `----------------------------------------\n`;
    msg += `*Total Items:* ${items.length} | *Total Units:* ${totalUnits}\n`;
    if (totalEstimatedCost > 0) {
      msg += `*Estimated Total Value:* ₹${totalEstimatedCost.toLocaleString("en-IN", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}\n`;
    }
    if (notes) {
      msg += `\n*Remarks:* ${notes}\n`;
    }

    return msg;
  };

  // 3. Share via WhatsApp
  const handleShareWhatsApp = () => {
    if (items.length === 0) {
      toast.error("No items in purchase order to share");
      return;
    }
    const msg = generateWhatsAppMessage();
    const url = `https://api.whatsapp.com/send?text=${encodeURIComponent(msg)}`;
    window.open(url, "_blank");
  };

  // 4. Copy to Clipboard
  const handleCopyText = async () => {
    if (items.length === 0) return;
    const msg = generateWhatsAppMessage();
    try {
      await navigator.clipboard.writeText(msg);
      setCopied(true);
      toast.success("Purchase order copied to clipboard!");
      setTimeout(() => setCopied(false), 2500);
    } catch {
      toast.error("Failed to copy to clipboard");
    }
  };

  // 5. Print / Save as PDF
  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-2 sm:p-4 overflow-y-auto">
      {/* Printable Document Styles */}
      <style jsx global>{`
        @media print {
          body * {
            visibility: hidden;
          }
          #printable-po-document,
          #printable-po-document * {
            visibility: visible;
          }
          #printable-po-document {
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
            background: white !important;
            color: black !important;
            padding: 24px !important;
            border: none !important;
            box-shadow: none !important;
          }
          .no-print {
            display: none !important;
          }
        }
      `}</style>

      <div className="relative w-full max-w-4xl bg-card border border-border/80 rounded-2xl shadow-2xl flex flex-col max-h-[92vh] overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Modal Top Action Bar */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-border/60 bg-muted/30">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-500/10 text-blue-600 dark:text-blue-400 flex items-center justify-center font-bold">
              <FileText className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm sm:text-base font-bold text-foreground">
                Purchase Order Draft
              </h2>
              <p className="text-[11px] text-muted-foreground">
                Review items, adjust quantities, download, print or share directly with supplier
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handlePrint}
              className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-muted hover:bg-muted/80 text-foreground border border-border/60 transition-colors cursor-pointer"
              title="Print or Save as PDF"
            >
              <Printer className="w-3.5 h-3.5" />
              <span>Print / PDF</span>
            </button>

            <button
              onClick={handleDownloadCsv}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-muted hover:bg-muted/80 text-foreground border border-border/60 transition-colors cursor-pointer"
              title="Download CSV Table"
            >
              <Download className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">CSV</span>
            </button>

            <button
              onClick={handleShareWhatsApp}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white transition-colors cursor-pointer shadow-xs"
              title="Share Order via WhatsApp"
            >
              <Share2 className="w-3.5 h-3.5" />
              <span>WhatsApp</span>
            </button>

            <button
              onClick={handleCopyText}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-muted hover:bg-muted/80 text-foreground border border-border/60 transition-colors cursor-pointer"
              title="Copy to Clipboard"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
              <span className="hidden sm:inline">{copied ? "Copied" : "Copy"}</span>
            </button>

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer ml-1"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Modal Scrollable Body */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-5">
          {/* Printable Document Container */}
          <div id="printable-po-document" className="space-y-5">
            {/* Formal PO Header */}
            <div className="p-4 sm:p-5 rounded-xl border border-border/60 bg-muted/20 space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <Building2 className="w-4 h-4 text-blue-500" />
                    <h3 className="text-base sm:text-lg font-bold text-foreground">
                      {companyName}
                    </h3>
                  </div>
                  {companyAddress && (
                    <p className="text-xs text-muted-foreground mt-0.5 max-w-sm">
                      {companyAddress}
                    </p>
                  )}
                  {companyGstin && (
                    <div className="text-xs font-mono text-muted-foreground mt-1">
                      GSTIN: <span className="font-semibold text-foreground">{companyGstin}</span>
                    </div>
                  )}
                </div>

                {/* PO Number & Date Controls */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 sm:text-right">
                  <div>
                    <label className="text-[10px] uppercase font-bold text-muted-foreground block mb-0.5">
                      PO Number
                    </label>
                    <input
                      type="text"
                      value={poNumber}
                      onChange={(e) => setPoNumber(e.target.value)}
                      className="bg-card border border-border/60 rounded-lg px-2.5 py-1 text-xs font-mono font-bold text-foreground outline-none focus:ring-1 focus:ring-primary w-full sm:w-36 text-left sm:text-right"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] uppercase font-bold text-muted-foreground block mb-0.5">
                      Order Date
                    </label>
                    <input
                      type="date"
                      value={poDate}
                      onChange={(e) => setPoDate(e.target.value)}
                      className="bg-card border border-border/60 rounded-lg px-2.5 py-1 text-xs font-mono font-semibold text-foreground outline-none focus:ring-1 focus:ring-primary w-full sm:w-36 text-left sm:text-right"
                    />
                  </div>
                </div>
              </div>

              {/* Vendor & Delivery Note inputs (non-printed interactive fields or customizable in PO) */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-border/40">
                <div>
                  <label className="text-[10px] uppercase font-bold text-muted-foreground flex items-center gap-1 mb-1">
                    <Truck className="w-3 h-3" />
                    <span>Vendor / Supplier Name</span>
                  </label>
                  <div className="relative">
                    <input
                      type="text"
                      list="supplier-suggestions"
                      placeholder="e.g. Satyam & Co. / PIX Distributor"
                      value={vendorName}
                      onChange={(e) => setVendorName(e.target.value)}
                      className="w-full bg-card border border-border/60 rounded-lg px-3 py-1.5 text-xs text-foreground outline-none focus:ring-1 focus:ring-primary"
                    />
                    <datalist id="supplier-suggestions">
                      {supplierSuggestions.map((s, idx) => (
                        <option key={idx} value={s} />
                      ))}
                    </datalist>
                  </div>
                </div>

                <div>
                  <label className="text-[10px] uppercase font-bold text-muted-foreground flex items-center gap-1 mb-1">
                    <FileText className="w-3 h-3" />
                    <span>Delivery Remarks / Instructions</span>
                  </label>
                  <input
                    type="text"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="e.g. Dispatch via Transport, urgent delivery"
                    className="w-full bg-card border border-border/60 rounded-lg px-3 py-1.5 text-xs text-foreground outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
              </div>
            </div>

            {/* Clean Order Items Table */}
            <div className="rounded-xl border border-border/60 overflow-hidden bg-card">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="bg-muted/40 border-b border-border/60 text-muted-foreground uppercase text-[10px] tracking-wider font-semibold">
                      <th className="py-2.5 px-3 w-10 text-center">#</th>
                      <th className="py-2.5 px-3">Item Description</th>
                      <th className="py-2.5 px-3">Category</th>
                      <th className="py-2.5 px-3 text-right">Current Stock</th>
                      <th className="py-2.5 px-3 text-center w-36">Order Quantity</th>
                      <th className="py-2.5 px-3 text-right">Expected Rate</th>
                      <th className="py-2.5 px-3 text-right">Estimated Amount</th>
                      <th className="py-2.5 px-3 w-10 text-center no-print"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/30">
                    {items.length === 0 ? (
                      <tr>
                        <td colSpan={8} className="py-8 text-center text-xs text-muted-foreground">
                          No items selected for this purchase order. Select items from the Low-Stock Reorder hub.
                        </td>
                      </tr>
                    ) : (
                      items.map((it, idx) => {
                        const lineTotal = (it.order_quantity || 0) * (it.purchase_price || 0);
                        return (
                          <tr key={it.product_id} className="hover:bg-muted/30 transition-colors">
                            <td className="py-2.5 px-3 text-center font-mono text-[11px] text-muted-foreground">
                              {idx + 1}
                            </td>
                            <td className="py-2.5 px-3">
                              <div className="font-semibold text-foreground flex items-center gap-1.5">
                                <span>{it.name}</span>
                                {it.urgency === "OUT_OF_STOCK" && (
                                  <span className="text-[9px] font-bold px-1.5 py-0.2 rounded-full bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20">
                                    OOS
                                  </span>
                                )}
                              </div>
                              <div className="text-[10px] text-muted-foreground font-mono flex items-center gap-2 mt-0.5">
                                {it.brand && <span>Brand: {it.brand}</span>}
                                {it.sku && <span>SKU: {it.sku}</span>}
                                {it.last_supplier && it.last_supplier !== "Catalog Master" && (
                                  <span className="text-blue-500">Last: {it.last_supplier}</span>
                                )}
                              </div>
                            </td>
                            <td className="py-2.5 px-3 text-muted-foreground">
                              {it.category_name || "General"}
                            </td>
                            <td className="py-2.5 px-3 text-right font-mono text-muted-foreground">
                              <span
                                className={`px-1.5 py-0.5 rounded font-bold ${
                                  it.current_stock <= 0
                                    ? "bg-rose-500/10 text-rose-600 dark:text-rose-400"
                                    : it.current_stock <= 3
                                    ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                                    : "text-muted-foreground"
                                }`}
                              >
                                {it.current_stock} {it.unit}
                              </span>
                            </td>
                            <td className="py-2.5 px-3 text-center">
                              {/* Quantity Editor with +/- buttons */}
                              <div className="inline-flex items-center justify-center gap-1">
                                <button
                                  type="button"
                                  onClick={() =>
                                    onUpdateQuantity?.(it.product_id, Math.max(1, (it.order_quantity || 1) - 1))
                                  }
                                  className="w-6 h-6 rounded bg-muted hover:bg-muted/80 text-foreground flex items-center justify-center cursor-pointer no-print"
                                  title="Decrease quantity"
                                >
                                  <Minus className="w-3 h-3" />
                                </button>
                                <input
                                  type="number"
                                  min="1"
                                  value={it.order_quantity || ""}
                                  onChange={(e) => {
                                    const val = Math.max(1, parseInt(e.target.value) || 1);
                                    onUpdateQuantity?.(it.product_id, val);
                                  }}
                                  className="w-14 bg-card border border-border/70 rounded-md py-1 text-center font-mono font-bold text-xs text-foreground outline-none focus:ring-1 focus:ring-primary"
                                />
                                <span className="text-[10px] text-muted-foreground font-mono">{it.unit}</span>
                                <button
                                  type="button"
                                  onClick={() =>
                                    onUpdateQuantity?.(it.product_id, (it.order_quantity || 1) + 1)
                                  }
                                  className="w-6 h-6 rounded bg-muted hover:bg-muted/80 text-foreground flex items-center justify-center cursor-pointer no-print"
                                  title="Increase quantity"
                                >
                                  <Plus className="w-3 h-3" />
                                </button>
                              </div>
                            </td>
                            <td className="py-2.5 px-3 text-right font-mono text-foreground font-medium">
                              ₹{(it.purchase_price || 0).toLocaleString("en-IN", {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}
                            </td>
                            <td className="py-2.5 px-3 text-right font-mono font-bold text-foreground">
                              ₹{lineTotal.toLocaleString("en-IN", {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}
                            </td>
                            <td className="py-2.5 px-3 text-center no-print">
                              <button
                                type="button"
                                onClick={() => onRemoveItem?.(it.product_id)}
                                className="p-1 rounded text-muted-foreground hover:text-rose-500 hover:bg-rose-500/10 transition-colors cursor-pointer"
                                title="Remove item from PO"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                  {items.length > 0 && (
                    <tfoot>
                      <tr className="bg-muted/30 border-t-2 border-border/80 font-bold">
                        <td colSpan={3} className="py-3 px-3 text-foreground uppercase text-[11px] tracking-wider">
                          Total Summary ({items.length} Unique Items)
                        </td>
                        <td className="py-3 px-3 text-right font-mono text-xs text-muted-foreground">
                          —
                        </td>
                        <td className="py-3 px-3 text-center font-mono text-xs text-blue-600 dark:text-blue-400">
                          {totalUnits} Units
                        </td>
                        <td className="py-3 px-3 text-right text-xs text-muted-foreground uppercase text-[10px]">
                          Grand Total
                        </td>
                        <td className="py-3 px-3 text-right font-mono text-sm font-bold text-emerald-600 dark:text-emerald-400">
                          ₹{totalEstimatedCost.toLocaleString("en-IN", {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })}
                        </td>
                        <td className="no-print"></td>
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
            </div>

            {/* Formal Signature block for print */}
            <div className="hidden print:grid grid-cols-2 gap-8 pt-10 text-xs text-gray-700">
              <div className="border-t border-gray-400 pt-2">
                Prepared By: ___________________
              </div>
              <div className="border-t border-gray-400 pt-2 text-right">
                Authorized Signatory: ___________________
              </div>
            </div>
          </div>
        </div>

        {/* Modal Bottom Sticky Footer */}
        <div className="px-5 py-3 border-t border-border/60 bg-muted/20 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="text-xs text-muted-foreground flex items-center gap-3">
            <span>
              <strong className="text-foreground">{items.length}</strong> items selected
            </span>
            <span>•</span>
            <span>
              <strong className="text-foreground">{totalUnits}</strong> total units
            </span>
            <span>•</span>
            <span>
              Est. Value:{" "}
              <strong className="text-emerald-600 dark:text-emerald-400 font-mono">
                ₹{totalEstimatedCost.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
              </strong>
            </span>
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-semibold bg-muted hover:bg-muted/80 text-foreground transition-colors cursor-pointer"
            >
              Close
            </button>
            <button
              type="button"
              onClick={handleShareWhatsApp}
              className="px-4 py-2 rounded-xl text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white transition-colors cursor-pointer flex items-center gap-1.5 shadow-sm"
            >
              <Share2 className="w-3.5 h-3.5" />
              <span>Send via WhatsApp</span>
            </button>
            <button
              type="button"
              onClick={handlePrint}
              className="px-4 py-2 rounded-xl text-xs font-semibold bg-primary text-primary-foreground hover:bg-primary/90 transition-colors cursor-pointer flex items-center gap-1.5 shadow-sm"
            >
              <Printer className="w-3.5 h-3.5" />
              <span>Print / Download PDF</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
