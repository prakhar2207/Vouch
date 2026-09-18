"use client";
import React, { useState, useEffect, Suspense } from "react";
import axios from "axios";
import { useRouter, useSearchParams } from "next/navigation";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import DashboardLayout from "@/components/DashboardLayout";
import { 
  FileText, 
  RotateCcw, 
  Plus, 
  Trash2, 
  Save, 
  ArrowLeft, 
  CheckCircle2, 
  Info,
  Calendar,
  Layers
} from "lucide-react";

interface ProductItem {
  id: string;
  name: string;
  selling_price: number;
  cost_price: number;
  gst_rate: number;
  hsn_code: string;
  unit: string;
  stock_quantity: number;
}

interface LineItem {
  product_id: string;
  product_name: string;
  quantity: number;
  rate: number;
  discount_percent: number;
  gst_rate: number;
  taxable_amount: number;
  cgst_amount: number;
  sgst_amount: number;
  igst_amount: number;
  total_amount: number;
}

function CreditDebitNoteContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialType = (searchParams.get("type") || "CREDIT_NOTE").toUpperCase() as "CREDIT_NOTE" | "DEBIT_NOTE";

  const [noteType, setNoteType] = useState<"CREDIT_NOTE" | "DEBIT_NOTE">(initialType);
  const [companyId, setCompanyId] = useState("");
  const [parties, setParties] = useState<any[]>([]);
  const [products, setProducts] = useState<ProductItem[]>([]);
  
  // Header form
  const [partyId, setPartyId] = useState("");
  const [voucherDate, setVoucherDate] = useState(new Date().toISOString().slice(0, 10));
  const [originalInvoiceNumber, setOriginalInvoiceNumber] = useState("");
  const [reason, setReason] = useState("Sales Return");
  const [narration, setNarration] = useState("");

  // Items
  const [items, setItems] = useState<LineItem[]>([
    {
      product_id: "",
      product_name: "",
      quantity: 1,
      rate: 0,
      discount_percent: 0,
      gst_rate: 18,
      taxable_amount: 0,
      cgst_amount: 0,
      sgst_amount: 0,
      igst_amount: 0,
      total_amount: 0,
    }
  ]);

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }
    fetchMasters();
  }, [router]);

  const fetchMasters = async () => {
    setLoading(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const [compRes, prodRes] = await Promise.all([
        axios.get("http://localhost:8000/api/v1/companies/", { headers }),
        axios.get("http://localhost:8000/api/v1/inventory/products/", { headers }),
      ]);

      const comp = compRes.data.data?.[0];
      if (comp) {
        setCompanyId(comp.id);
        const partyRes = await axios.get(`http://localhost:8000/api/v1/ledgers/parties/?company_id=${comp.id}`, { headers });
        setParties(partyRes.data.data || partyRes.data.results || []);
      }
      setProducts(prodRes.data.data || prodRes.data.results || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const calculateLineItem = (item: LineItem): LineItem => {
    const qty = Number(item.quantity) || 0;
    const rate = Number(item.rate) || 0;
    const disc = Number(item.discount_percent) || 0;
    const gross = qty * rate;
    const discAmt = (gross * disc) / 100;
    const taxable = gross - discAmt;
    const gstRate = Number(item.gst_rate) || 0;

    // Standard 50-50 Intra-state split
    const halfRate = gstRate / 2;
    const cgst = (taxable * halfRate) / 100;
    const sgst = (taxable * halfRate) / 100;
    const total = taxable + cgst + sgst;

    return {
      ...item,
      taxable_amount: Math.round(taxable * 100) / 100,
      cgst_amount: Math.round(cgst * 100) / 100,
      sgst_amount: Math.round(sgst * 100) / 100,
      igst_amount: 0,
      total_amount: Math.round(total * 100) / 100,
    };
  };

  const handleProductSelect = (index: number, prodId: string) => {
    const prod = products.find((p) => p.id === prodId);
    if (!prod) return;

    const newItems = [...items];
    const defaultRate = noteType === "CREDIT_NOTE" ? prod.selling_price : prod.cost_price;
    newItems[index] = calculateLineItem({
      ...newItems[index],
      product_id: prod.id,
      product_name: prod.name,
      rate: defaultRate || 0,
      gst_rate: prod.gst_rate || 18,
    });
    setItems(newItems);
  };

  const handleItemChange = (index: number, field: keyof LineItem, val: any) => {
    const newItems = [...items];
    newItems[index] = calculateLineItem({
      ...newItems[index],
      [field]: val,
    });
    setItems(newItems);
  };

  const addItemRow = () => {
    setItems([
      ...items,
      {
        product_id: "",
        product_name: "",
        quantity: 1,
        rate: 0,
        discount_percent: 0,
        gst_rate: 18,
        taxable_amount: 0,
        cgst_amount: 0,
        sgst_amount: 0,
        igst_amount: 0,
        total_amount: 0,
      }
    ]);
  };

  const removeItemRow = (index: number) => {
    if (items.length <= 1) return;
    setItems(items.filter((_, i) => i !== index));
  };

  const totalTaxable = items.reduce((acc, itm) => acc + (itm.taxable_amount || 0), 0);
  const totalTax = items.reduce((acc, itm) => acc + (itm.cgst_amount || 0) + (itm.sgst_amount || 0) + (itm.igst_amount || 0), 0);
  const grandTotal = items.reduce((acc, itm) => acc + (itm.total_amount || 0), 0);

  const handleSave = async () => {
    if (!partyId) {
      alert("Please select a Party.");
      return;
    }
    const validItems = items.filter((i) => i.product_id && i.quantity > 0);
    if (validItems.length === 0) {
      alert("Please add at least one valid product line item.");
      return;
    }

    setSaving(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      const payload = {
        company_id: companyId,
        voucher_type: noteType,
        party_ledger_id: partyId,
        voucher_date: voucherDate,
        original_invoice_number: originalInvoiceNumber,
        reference_number: originalInvoiceNumber,
        reason: reason,
        narration: narration || `${noteType === "CREDIT_NOTE" ? "Credit Note" : "Debit Note"}: ${reason}`,
        items: validItems.map((itm) => ({
          product_id: itm.product_id,
          quantity: itm.quantity,
          rate: itm.rate,
          discount_percent: itm.discount_percent,
          gst_rate: itm.gst_rate,
        })),
        post_immediately: true,
      };

      const res = await axios.post("http://localhost:8000/api/v1/accounting/vouchers/", payload, { headers });
      setSuccessMessage(`✓ ${noteType === "CREDIT_NOTE" ? "Credit Note" : "Debit Note"} #${res.data.voucher_number || ""} successfully recorded.`);
      setTimeout(() => {
        router.push("/vouchers");
      }, 1500);
    } catch (e: any) {
      console.error(e);
      alert(e.response?.data?.error || "Error recording voucher. Please check inputs.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6 max-w-5xl mx-auto pb-12">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-4">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.back()}
              className="p-2 rounded-xl bg-muted hover:bg-muted/80 text-foreground transition-colors cursor-pointer"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold tracking-tight">
                  {noteType === "CREDIT_NOTE" ? "Credit Note (Alt+F6)" : "Debit Note (Alt+F5)"}
                </h1>
                <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold ${
                  noteType === "CREDIT_NOTE"
                    ? "bg-amber-50 text-amber-800 border border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800"
                    : "bg-blue-50 text-blue-800 border border-blue-200 dark:bg-blue-950/40 dark:text-blue-300 dark:border-blue-800"
                }`}>
                  {noteType === "CREDIT_NOTE" ? "Sales Return & Tax Reversal" : "Purchase Return & Tax Reversal"}
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Record returns, rate adjustments, or post-sale discounts with automatic double-entry and inventory restock.
              </p>
            </div>
          </div>

          {/* Toggle Type */}
          <div className="flex items-center gap-1 p-1 bg-muted rounded-xl">
            <button
              onClick={() => {
                setNoteType("CREDIT_NOTE");
                setReason("Sales Return");
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                noteType === "CREDIT_NOTE" ? "bg-background text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Credit Note (Sales Return)
            </button>
            <button
              onClick={() => {
                setNoteType("DEBIT_NOTE");
                setReason("Purchase Return");
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                noteType === "DEBIT_NOTE" ? "bg-background text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Debit Note (Purchase Return)
            </button>
          </div>
        </div>

        {successMessage && (
          <div className="p-4 bg-emerald-50 border border-emerald-200 text-emerald-900 dark:bg-emerald-950/40 dark:border-emerald-800 dark:text-emerald-300 rounded-xl text-xs flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            <span>{successMessage}</span>
          </div>
        )}

        {/* Voucher Form Header Card */}
        <div className="bg-card border border-border rounded-2xl p-5 shadow-sm grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
          <div>
            <label className="block text-muted-foreground font-semibold mb-1">
              {noteType === "CREDIT_NOTE" ? "Customer / Debtor:" : "Supplier / Creditor:"}
            </label>
            <select
              value={partyId}
              onChange={(e) => setPartyId(e.target.value)}
              className="w-full p-2 bg-background border border-border rounded-lg text-xs font-semibold text-foreground outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">-- Select Party --</option>
              {parties.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} {p.gstin ? `(${p.gstin})` : ""}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-muted-foreground font-semibold mb-1">Voucher Date:</label>
            <input
              type="date"
              value={voucherDate}
              onChange={(e) => setVoucherDate(e.target.value)}
              className="w-full p-2 bg-background border border-border rounded-lg text-xs font-mono font-semibold text-foreground outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-muted-foreground font-semibold mb-1">
              Original Invoice No. (Optional):
            </label>
            <input
              type="text"
              value={originalInvoiceNumber}
              onChange={(e) => setOriginalInvoiceNumber(e.target.value)}
              placeholder="e.g. INV/2026/001"
              className="w-full p-2 bg-background border border-border rounded-lg text-xs font-mono text-foreground outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-muted-foreground font-semibold mb-1">GST Reason Code:</label>
            <select
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="w-full p-2 bg-background border border-border rounded-lg text-xs font-semibold text-foreground outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="Sales Return">01 - Sales Return</option>
              <option value="Purchase Return">01 - Purchase Return</option>
              <option value="Post Sale Discount">02 - Post Sale Discount</option>
              <option value="Deficiency in Services">03 - Deficiency in Services</option>
              <option value="Correction in Invoice">04 - Correction in Invoice</option>
              <option value="Other">05 - Other Adjustment</option>
            </select>
          </div>
        </div>

        {/* Line Items Table Card */}
        <div className="bg-card border border-border rounded-2xl p-5 shadow-sm space-y-4 text-xs">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <h3 className="font-bold text-foreground flex items-center gap-2">
              <Layers className="w-4 h-4 text-muted-foreground" />
              <span>Items Being Returned or Adjusted</span>
            </h3>
            <button
              onClick={addItemRow}
              className="px-3 py-1.5 bg-muted hover:bg-muted/80 text-foreground rounded-lg font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add Row</span>
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-border text-muted-foreground uppercase font-semibold text-[11px]">
                  <th className="pb-2 w-1/3">Item Description</th>
                  <th className="pb-2 text-right">Return Qty</th>
                  <th className="pb-2 text-right">Rate (₹)</th>
                  <th className="pb-2 text-right">Disc %</th>
                  <th className="pb-2 text-right">GST %</th>
                  <th className="pb-2 text-right">Taxable (₹)</th>
                  <th className="pb-2 text-right">Total (₹)</th>
                  <th className="pb-2 text-center w-12"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {items.map((item, idx) => (
                  <tr key={idx}>
                    <td className="py-2.5 pr-2">
                      <select
                        value={item.product_id}
                        onChange={(e) => handleProductSelect(idx, e.target.value)}
                        className="w-full p-2 bg-background border border-border rounded-lg text-xs font-semibold text-foreground outline-none focus:ring-1 focus:ring-blue-500"
                      >
                        <option value="">-- Choose Product --</option>
                        {products.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name} {p.hsn_code ? `[HSN: ${p.hsn_code}]` : ""}
                          </option>
                        ))}
                      </select>
                    </td>

                    <td className="py-2.5 px-2">
                      <input
                        type="number"
                        min="1"
                        value={item.quantity}
                        onChange={(e) => handleItemChange(idx, "quantity", e.target.value)}
                        className="w-20 p-2 bg-background border border-border rounded-lg text-right font-mono font-semibold text-xs"
                      />
                    </td>

                    <td className="py-2.5 px-2">
                      <input
                        type="number"
                        step="0.01"
                        value={item.rate}
                        onChange={(e) => handleItemChange(idx, "rate", e.target.value)}
                        className="w-24 p-2 bg-background border border-border rounded-lg text-right font-mono font-semibold text-xs"
                      />
                    </td>

                    <td className="py-2.5 px-2">
                      <input
                        type="number"
                        value={item.discount_percent}
                        onChange={(e) => handleItemChange(idx, "discount_percent", e.target.value)}
                        className="w-16 p-2 bg-background border border-border rounded-lg text-right font-mono text-xs"
                      />
                    </td>

                    <td className="py-2.5 px-2 text-right font-mono text-xs">
                      {item.gst_rate}%
                    </td>

                    <td className="py-2.5 px-2 text-right font-mono font-semibold text-xs">
                      ₹{item.taxable_amount.toFixed(2)}
                    </td>

                    <td className="py-2.5 pl-2 text-right font-mono font-bold text-foreground text-xs">
                      ₹{item.total_amount.toFixed(2)}
                    </td>

                    <td className="py-2.5 text-center">
                      <button
                        onClick={() => removeItemRow(idx)}
                        disabled={items.length <= 1}
                        className="p-1.5 text-muted-foreground hover:text-red-600 dark:hover:text-red-400 disabled:opacity-30 cursor-pointer transition-colors"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Narration & Summary Bottom Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-4 border-t border-border">
            <div className="space-y-2">
              <label className="block text-muted-foreground font-semibold">Remarks / Narration:</label>
              <textarea
                rows={3}
                value={narration}
                onChange={(e) => setNarration(e.target.value)}
                placeholder="Optional notes regarding reason for return or rate settlement..."
                className="w-full p-2.5 bg-background border border-border rounded-xl text-xs text-foreground outline-none focus:ring-2 focus:ring-primary"
              />
              <div className="flex items-center gap-1.5 text-[11px] text-emerald-700 dark:text-emerald-400 font-medium">
                <Info className="w-3.5 h-3.5" />
                <span>
                  {noteType === "CREDIT_NOTE"
                    ? "Inventory will automatically restock and Output GST will reverse."
                    : "Inventory will decrease and Input Tax Credit will reverse."}
                </span>
              </div>
            </div>

            <div className="bg-muted/40 p-4 rounded-xl border border-border space-y-2 font-mono text-xs">
              <div className="flex justify-between text-muted-foreground">
                <span>Total Taxable Value:</span>
                <span className="font-bold text-foreground font-mono">₹{totalTaxable.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-muted-foreground">
                <span>Reversed GST (CGST+SGST/IGST):</span>
                <span className="font-bold text-foreground font-mono">₹{totalTax.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-sm font-bold text-foreground pt-2 border-t border-border">
                <span>Grand Total Adjustment:</span>
                <span className="text-base text-blue-600 dark:text-blue-400 font-black font-mono">₹{grandTotal.toFixed(2)}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Action Bottom Bar */}
        <div className="flex items-center justify-end gap-3 pt-2">
          <button
            onClick={() => router.back()}
            className="px-5 py-2.5 bg-secondary hover:bg-secondary/80 text-secondary-foreground rounded-xl text-xs font-semibold cursor-pointer border border-border transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-6 py-2.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl text-xs font-bold shadow-md flex items-center gap-2 cursor-pointer transition-all"
          >
            <Save className="w-4 h-4" />
            <span>{saving ? "Posting Note..." : `Post ${noteType === "CREDIT_NOTE" ? "Credit Note" : "Debit Note"} (Ctrl+A)`}</span>
          </button>
        </div>
      </div>
    </DashboardLayout>
  );
}

export default function CreditDebitNotePage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-muted-foreground">Loading form...</div>}>
      <CreditDebitNoteContent />
    </Suspense>
  );
}
