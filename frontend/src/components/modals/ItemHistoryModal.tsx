"use client";
import React, { useState, useEffect } from "react";
import axios from "axios";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken } from "@/utils/auth";
import { useToast } from "@/context/ToastContext";
import {
  X,
  FileText,
  Receipt,
  Calendar,
  User,
  ExternalLink,
  Package,
  Layers,
  ArrowDownLeft,
  ArrowUpRight,
  TrendingUp,
  Tag,
  Clock,
  ShoppingBag
} from "lucide-react";

interface ItemHistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  productId: string | null;
  productName: string;
  companyId: string;
}

export default function ItemHistoryModal({
  isOpen,
  onClose,
  productId,
  productName,
  companyId,
}: ItemHistoryModalProps) {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<"purchases" | "sales" | "timeline">("purchases");

  useEffect(() => {
    if (isOpen && productId && companyId) {
      fetchItemHistory();
    } else {
      setData(null);
    }
  }, [isOpen, productId, companyId]);

  const fetchItemHistory = async () => {
    setLoading(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.get(
        `${API_BASE_URL}/api/v1/inventory/products/${companyId}/${productId}/history/`,
        { headers }
      );
      if (res.data.success) {
        setData(res.data.data);
      } else {
        toast.error("Failed to load item history", res.data.error);
      }
    } catch (err: any) {
      console.error(err);
      toast.error("Error loading history", err.response?.data?.error || err.message);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  const product = data?.product;
  const metrics = data?.metrics;
  const purchases = data?.purchases || [];
  const sales = data?.sales || [];

  // Construct merged chronological timeline
  const timeline = [
    ...purchases.map((p: any) => ({ ...p, type: "PURCHASE" })),
    ...sales.map((s: any) => ({ ...s, type: "SALES" }))
  ].sort((a: any, b: any) => new Date(b.date || 0).getTime() - new Date(a.date || 0).getTime());

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/75 backdrop-blur-xs" onClick={onClose} />

      {/* Modal Dialog */}
      <div className="relative bg-card border border-border/80 w-full max-w-4xl rounded-2xl shadow-2xl overflow-hidden z-10 animate-in fade-in zoom-in-95 duration-200 flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-6 py-4 border-b border-border/60 bg-muted/20 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20 flex items-center justify-center">
              <Package className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-foreground">
                  {product?.name || productName}
                </h3>
                {product?.brand && (
                  <span className="bg-zinc-800 text-blue-400 border border-blue-500/20 text-[11px] px-2 py-0.5 rounded font-bold font-mono">
                    {product.brand}
                  </span>
                )}
                {product?.sku && (
                  <span className="text-[11px] font-mono text-muted-foreground">
                    ({product.sku})
                  </span>
                )}
                {product?.purchase_price_from_invoice && (
                  <span className="text-[10px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-1.5 py-0.5 rounded font-mono font-bold">
                    Invoice
                  </span>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                Item transaction history, purchase bills, and sales invoice analytics
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
        {loading ? (
          <div className="flex-1 flex items-center justify-center p-16 text-muted-foreground text-sm">
            Loading bill history & analytics...
          </div>
        ) : !data ? (
          <div className="flex-1 flex items-center justify-center p-16 text-muted-foreground text-sm">
            Unable to load transaction records.
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {/* KPI Cards Grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {/* Current Stock */}
              <div className="bg-muted/25 border border-border/60 p-3.5 rounded-xl">
                <div className="text-[10px] font-semibold text-muted-foreground uppercase flex items-center gap-1.5">
                  <Package className="w-3.5 h-3.5 text-blue-400" />
                  Current Stock
                </div>
                <div className="mt-1 text-lg font-bold font-mono text-emerald-400">
                  {product?.current_stock?.toLocaleString()} <span className="text-xs font-normal text-muted-foreground">{product?.unit}</span>
                </div>
                <div className="text-[11px] text-muted-foreground mt-0.5 font-mono">
                  {product?.purchase_price > 0 ? `Cost: ₹${product.purchase_price.toFixed(2)}` : "Cost: —"}
                </div>
              </div>

              {/* Total Purchased */}
              <div className="bg-muted/25 border border-border/60 p-3.5 rounded-xl">
                <div className="text-[10px] font-semibold text-muted-foreground uppercase flex items-center gap-1.5">
                  <ArrowDownLeft className="w-3.5 h-3.5 text-emerald-400" />
                  Purchased
                </div>
                <div className="mt-1 text-lg font-bold font-mono text-foreground">
                  {metrics?.total_purchased_qty?.toLocaleString()} <span className="text-xs font-normal text-muted-foreground">{product?.unit}</span>
                </div>
                <div className="text-[11px] text-muted-foreground mt-0.5">
                  {metrics?.purchase_bills_count} bill(s) • ₹{metrics?.total_purchased_val?.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
                </div>
              </div>

              {/* Total Sold */}
              <div className="bg-muted/25 border border-border/60 p-3.5 rounded-xl">
                <div className="text-[10px] font-semibold text-muted-foreground uppercase flex items-center gap-1.5">
                  <ArrowUpRight className="w-3.5 h-3.5 text-amber-400" />
                  Sold Out
                </div>
                <div className="mt-1 text-lg font-bold font-mono text-foreground">
                  {metrics?.total_sold_qty?.toLocaleString()} <span className="text-xs font-normal text-muted-foreground">{product?.unit}</span>
                </div>
                <div className="text-[11px] text-muted-foreground mt-0.5">
                  {metrics?.sales_invoices_count} invoice(s) • ₹{metrics?.total_sold_val?.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
                </div>
              </div>

              {/* Average Prices */}
              <div className="bg-muted/25 border border-border/60 p-3.5 rounded-xl">
                <div className="text-[10px] font-semibold text-muted-foreground uppercase flex items-center gap-1.5">
                  <TrendingUp className="w-3.5 h-3.5 text-indigo-400" />
                  Avg Rates
                </div>
                <div className="mt-1 text-sm font-bold font-mono text-foreground">
                  Buy: ₹{metrics?.avg_purchase_price?.toFixed(2)}
                </div>
                <div className="text-sm font-bold font-mono text-emerald-400 mt-0.5">
                  Sell: ₹{metrics?.avg_selling_price?.toFixed(2)}
                </div>
              </div>
            </div>

            {/* Navigation Tabs */}
            <div className="flex items-center gap-2 border-b border-border/60 pb-2">
              <button
                type="button"
                onClick={() => setActiveTab("purchases")}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                  activeTab === "purchases"
                    ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
                }`}
              >
                <ArrowDownLeft className="w-3.5 h-3.5" />
                <span>Purchased From Bills ({purchases.length})</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab("sales")}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                  activeTab === "sales"
                    ? "bg-blue-500/15 text-blue-400 border border-blue-500/30"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
                }`}
              >
                <ArrowUpRight className="w-3.5 h-3.5" />
                <span>Sold In Invoices ({sales.length})</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab("timeline")}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                  activeTab === "timeline"
                    ? "bg-purple-500/15 text-purple-400 border border-purple-500/30"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
                }`}
              >
                <Clock className="w-3.5 h-3.5" />
                <span>Full Movement Timeline ({timeline.length})</span>
              </button>
            </div>

            {/* Tab 1: Purchase Invoices */}
            {activeTab === "purchases" && (
              <div className="space-y-3">
                {purchases.length === 0 ? (
                  <div className="p-8 text-center bg-muted/15 border border-dashed border-border/70 rounded-xl text-muted-foreground text-xs">
                    No purchase bills recorded for this product yet.
                  </div>
                ) : (
                  <div className="border border-border/70 rounded-xl overflow-x-auto">
                    <table className="w-full text-xs text-left border-collapse">
                      <thead className="bg-muted/40 border-b border-border/60 text-muted-foreground uppercase text-[10px] tracking-wider font-semibold">
                        <tr>
                          <th className="p-2.5">Bill / Voucher #</th>
                          <th className="p-2.5">Date</th>
                          <th className="p-2.5">Supplier / Party</th>
                          <th className="p-2.5 text-right">Qty</th>
                          <th className="p-2.5 text-right">Rate (₹)</th>
                          <th className="p-2.5 text-right">GST %</th>
                          <th className="p-2.5 text-right">Total (₹)</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/30">
                        {purchases.map((p: any, idx: number) => (
                          <tr key={idx} className="hover:bg-muted/15 transition-colors">
                            <td className="p-2.5 font-mono font-bold text-foreground flex items-center gap-1">
                              <span className="text-emerald-400">#{p.voucher_number}</span>
                            </td>
                            <td className="p-2.5 font-mono text-muted-foreground">
                              {p.date}
                            </td>
                            <td className="p-2.5 font-medium text-foreground">
                              {p.party_name}
                            </td>
                            <td className="p-2.5 text-right font-mono font-bold text-emerald-400">
                              +{p.quantity} {p.unit}
                            </td>
                            <td className="p-2.5 text-right font-mono">
                              ₹{p.rate.toFixed(2)}
                            </td>
                            <td className="p-2.5 text-right font-mono text-muted-foreground">
                              {p.gst_rate}%
                            </td>
                            <td className="p-2.5 text-right font-mono font-bold text-foreground">
                              ₹{p.total_amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* Tab 2: Sales Invoices */}
            {activeTab === "sales" && (
              <div className="space-y-3">
                {sales.length === 0 ? (
                  <div className="p-8 text-center bg-muted/15 border border-dashed border-border/70 rounded-xl text-muted-foreground text-xs">
                    No sales invoices recorded for this product yet.
                  </div>
                ) : (
                  <div className="border border-border/70 rounded-xl overflow-x-auto">
                    <table className="w-full text-xs text-left border-collapse">
                      <thead className="bg-muted/40 border-b border-border/60 text-muted-foreground uppercase text-[10px] tracking-wider font-semibold">
                        <tr>
                          <th className="p-2.5">Invoice #</th>
                          <th className="p-2.5">Date</th>
                          <th className="p-2.5">Customer</th>
                          <th className="p-2.5 text-right">Qty</th>
                          <th className="p-2.5 text-right">Rate (₹)</th>
                          <th className="p-2.5 text-right">Disc %</th>
                          <th className="p-2.5 text-right">Total (₹)</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/30">
                        {sales.map((s: any, idx: number) => (
                          <tr key={idx} className="hover:bg-muted/15 transition-colors">
                            <td className="p-2.5 font-mono font-bold text-blue-400">
                              #{s.voucher_number}
                            </td>
                            <td className="p-2.5 font-mono text-muted-foreground">
                              {s.date}
                            </td>
                            <td className="p-2.5 font-medium text-foreground">
                              {s.party_name}
                            </td>
                            <td className="p-2.5 text-right font-mono font-bold text-amber-400">
                              -{s.quantity} {s.unit}
                            </td>
                            <td className="p-2.5 text-right font-mono">
                              ₹{s.rate.toFixed(2)}
                            </td>
                            <td className="p-2.5 text-right font-mono text-muted-foreground">
                              {s.discount_percent > 0 ? `${s.discount_percent}%` : "—"}
                            </td>
                            <td className="p-2.5 text-right font-mono font-bold text-foreground">
                              ₹{s.total_amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* Tab 3: Timeline */}
            {activeTab === "timeline" && (
              <div className="space-y-2">
                {timeline.length === 0 ? (
                  <div className="p-8 text-center bg-muted/15 border border-dashed border-border/70 rounded-xl text-muted-foreground text-xs">
                    No transactions recorded for this item.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {timeline.map((entry: any, idx: number) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between p-3 rounded-xl bg-muted/20 border border-border/60 text-xs"
                      >
                        <div className="flex items-center gap-3">
                          <div
                            className={`w-7 h-7 rounded-lg flex items-center justify-center font-bold text-xs ${
                              entry.type === "PURCHASE"
                                ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                                : "bg-blue-500/15 text-blue-400 border border-blue-500/30"
                            }`}
                          >
                            {entry.type === "PURCHASE" ? <ArrowDownLeft className="w-3.5 h-3.5" /> : <ArrowUpRight className="w-3.5 h-3.5" />}
                          </div>
                          <div>
                            <div className="font-semibold text-foreground flex items-center gap-1.5">
                              <span>{entry.type === "PURCHASE" ? "Purchase Bill" : "Sales Invoice"} #{entry.voucher_number}</span>
                              <span className="text-muted-foreground">•</span>
                              <span className="font-normal text-muted-foreground">{entry.party_name}</span>
                            </div>
                            <div className="text-[10px] text-muted-foreground font-mono">
                              {entry.date}
                            </div>
                          </div>
                        </div>

                        <div className="text-right font-mono">
                          <div
                            className={`font-bold text-sm ${
                              entry.type === "PURCHASE" ? "text-emerald-400" : "text-amber-400"
                            }`}
                          >
                            {entry.type === "PURCHASE" ? `+${entry.quantity}` : `-${entry.quantity}`} {entry.unit}
                          </div>
                          <div className="text-[10px] text-muted-foreground">
                            @ ₹{entry.rate.toFixed(2)} • Total: ₹{entry.total_amount.toFixed(2)}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
