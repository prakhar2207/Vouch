"use client";
import React, { useState, useEffect, Suspense } from "react";
import axios from "axios";
import { useRouter, useSearchParams } from "next/navigation";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import { API_BASE_URL } from "@/utils/api";
import { useCompany } from "@/context/CompanyContext";
import { useToast } from "@/context/ToastContext";
import DashboardLayout from "@/components/DashboardLayout";
import ConfirmModal from "@/components/modals/ConfirmModal";
import { vouchersRepository } from "@/lib/data";
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
  Layers,
  History,
  Search,
  AlertCircle,
  Tag,
  ArrowUpRight,
  ArrowDownLeft
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
  const { toast } = useToast();
  const initialType = (searchParams.get("type") || "CREDIT_NOTE").toUpperCase() as "CREDIT_NOTE" | "DEBIT_NOTE";
  const initialTab = searchParams.get("tab") === "history" ? "history" : "new";

  const { activeCompany, companyId: activeCompanyId } = useCompany();
  const [activeMainTab, setActiveMainTab] = useState<"new" | "history">(initialTab);
  const [noteType, setNoteType] = useState<"CREDIT_NOTE" | "DEBIT_NOTE">(initialType);
  const companyId = activeCompanyId || (typeof window !== "undefined" ? localStorage.getItem("vouch_active_company_id") || "" : "");
  
  // Master data
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

  // History tab state
  const [historyNotes, setHistoryNotes] = useState<any[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [historyFilterType, setHistoryFilterType] = useState<"ALL" | "CREDIT_NOTE" | "DEBIT_NOTE">("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; number: string; type: string } | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }
    if (companyId) {
      fetchMasters();
      fetchHistory();
    }
  }, [router, companyId]);

  const fetchMasters = async () => {
    if (!companyId) return;
    setLoading(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const [partyRes, prodRes] = await Promise.all([
        axios.get(`${API_BASE_URL}/api/v1/ledgers/parties/?company_id=${companyId}`, { headers }),
        axios.get(`${API_BASE_URL}/api/v1/inventory/products/`, { headers }),
      ]);

      setParties(partyRes.data.data || partyRes.data.results || []);
      setProducts(prodRes.data.data || prodRes.data.results || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const fetchHistory = async () => {
    if (!companyId) return;
    setLoadingHistory(true);
    try {
      // 1. Try local IndexedDB
      try {
        const local = await vouchersRepository.getVouchers(companyId, {
          type: ["CREDIT_NOTE", "DEBIT_NOTE"],
          status: "ACTIVE",
          pageSize: 100,
        });
        if (local && local.data && local.data.length > 0) {
          setHistoryNotes(local.data);
        }
      } catch {}

      // 2. Fetch fresh server data
      const token = getAccessToken();
      if (token) {
        const headers = { Authorization: `Bearer ${token}` };
        const res = await axios.get(
          `${API_BASE_URL}/api/v1/accounting/vouchers/${companyId}/?type=CREDIT_NOTE,DEBIT_NOTE&status=ACTIVE&limit=100`,
          { headers }
        );
        if (res.data && res.data.data) {
          setHistoryNotes(res.data.data);
        }
      }
    } catch (err) {
      console.error("Error fetching credit note history:", err);
    } finally {
      setLoadingHistory(false);
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

      const res = await axios.post(`${API_BASE_URL}/api/v1/accounting/vouchers/`, payload, { headers });
      const newVoucherNumber = res.data.voucher_number || "";
      toast.success(
        `${noteType === "CREDIT_NOTE" ? "Credit Note" : "Debit Note"} #${newVoucherNumber} Posted`,
        "Voucher successfully recorded with automatic stock and double-entry adjustment."
      );
      setSuccessMessage(`✓ ${noteType === "CREDIT_NOTE" ? "Credit Note" : "Debit Note"} #${newVoucherNumber} successfully recorded.`);

      // Reset form
      setItems([
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
      setOriginalInvoiceNumber("");
      setNarration("");

      // Refresh history and switch to History tab
      fetchHistory();
      setTimeout(() => {
        setActiveMainTab("history");
        setSuccessMessage(null);
      }, 1200);
    } catch (e: any) {
      console.error(e);
      toast.error("Error Recording Note", e.response?.data?.error || "Please check your inputs.");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.delete(`${API_BASE_URL}/api/vouchers/${deleteTarget.id}/`, { headers });

      if (res.data.success) {
        toast.success(
          `${deleteTarget.type === "CREDIT_NOTE" ? "Credit Note" : "Debit Note"} Deleted`,
          res.data.message || "Voucher cancelled and ledger balances restored."
        );
        setHistoryNotes((prev) => prev.filter((v) => v.id !== deleteTarget.id));
        await vouchersRepository.deleteVoucher(deleteTarget.id);
        setDeleteTarget(null);
      } else {
        toast.error("Delete Failed", res.data.error || "Unable to delete voucher.");
      }
    } catch (err: any) {
      console.error(err);
      toast.error("Delete Error", err.response?.data?.error || err.message || "An error occurred.");
    } finally {
      setDeleting(false);
    }
  };

  // Filtered History list
  const filteredHistory = historyNotes.filter((v) => {
    const vType = String(v.voucherType || v.voucher_type || v.type || "").toUpperCase();
    if (historyFilterType !== "ALL" && vType !== historyFilterType) {
      return false;
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const num = String(v.voucherNumber || v.voucher_number || "").toLowerCase();
      const party = String(v.partyName || v.party_name || "").toLowerCase();
      const ref = String(v.referenceNumber || v.reference_number || "").toLowerCase();
      const narr = String(v.narration || "").toLowerCase();
      if (!num.includes(q) && !party.includes(q) && !ref.includes(q) && !narr.includes(q)) {
        return false;
      }
    }
    return true;
  });

  const totalCreditNotesValue = historyNotes
    .filter((v) => String(v.voucherType || v.voucher_type || v.type).toUpperCase() === "CREDIT_NOTE")
    .reduce((acc, v) => acc + Number(v.totalAmount ?? v.total_amount ?? 0), 0);

  const totalDebitNotesValue = historyNotes
    .filter((v) => String(v.voucherType || v.voucher_type || v.type).toUpperCase() === "DEBIT_NOTE")
    .reduce((acc, v) => acc + Number(v.totalAmount ?? v.total_amount ?? 0), 0);

  return (
    <DashboardLayout>
      <div className="space-y-6 max-w-6xl mx-auto pb-12">
        {/* Top Header */}
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
                <h1 className="text-2xl font-bold tracking-tight">Credit & Debit Notes</h1>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-50 text-amber-800 border border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800">
                  Returns & Rate Adjustments
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Issue and track customer sales returns (Credit Notes) and supplier purchase returns (Debit Notes) with automatic stock and double-entry adjustments.
              </p>
            </div>
          </div>

          {/* Main Tab Controller */}
          <div className="flex items-center gap-1.5 p-1 bg-muted rounded-xl border border-border/50">
            <button
              onClick={() => setActiveMainTab("new")}
              className={`px-4 py-2 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                activeMainTab === "new"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Plus className="w-4 h-4" />
              <span>Create Note</span>
            </button>
            <button
              onClick={() => setActiveMainTab("history")}
              className={`px-4 py-2 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                activeMainTab === "history"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <History className="w-4 h-4" />
              <span>History & Notes</span>
              {historyNotes.length > 0 && (
                <span className={`px-2 py-0.2 rounded-full text-[10px] font-mono font-bold ${
                  activeMainTab === "history" ? "bg-white/20 text-white" : "bg-card text-foreground border border-border"
                }`}>
                  {historyNotes.length}
                </span>
              )}
            </button>
          </div>
        </div>

        {successMessage && (
          <div className="p-4 bg-emerald-50 border border-emerald-200 text-emerald-900 dark:bg-emerald-950/40 dark:border-emerald-800 dark:text-emerald-300 rounded-xl text-xs flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            <span>{successMessage}</span>
          </div>
        )}

        {/* TAB 1: CREATE NEW NOTE FORM */}
        {activeMainTab === "new" && (
          <div className="space-y-6">
            {/* Form Mode Sub-toggle */}
            <div className="flex items-center justify-between gap-3 p-3 bg-muted/30 rounded-xl border border-border">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Select Note Type:</span>
                <div className="flex items-center gap-1 bg-muted p-1 rounded-lg">
                  <button
                    onClick={() => {
                      setNoteType("CREDIT_NOTE");
                      setReason("Sales Return");
                    }}
                    className={`px-3 py-1.5 rounded-md text-xs font-bold transition-all cursor-pointer ${
                      noteType === "CREDIT_NOTE"
                        ? "bg-background text-foreground shadow-xs"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    Credit Note (Sales Return)
                  </button>
                  <button
                    onClick={() => {
                      setNoteType("DEBIT_NOTE");
                      setReason("Purchase Return");
                    }}
                    className={`px-3 py-1.5 rounded-md text-xs font-bold transition-all cursor-pointer ${
                      noteType === "DEBIT_NOTE"
                        ? "bg-background text-foreground shadow-xs"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    Debit Note (Purchase Return)
                  </button>
                </div>
              </div>

              <div className="hidden sm:flex items-center gap-1.5 text-xs text-muted-foreground">
                <Tag className="w-3.5 h-3.5" />
                <span>
                  {noteType === "CREDIT_NOTE" ? "Shortcuts: Alt + F6" : "Shortcuts: Alt + F5"}
                </span>
              </div>
            </div>

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
        )}

        {/* TAB 2: HISTORY & MANAGEMENT VIEW */}
        {activeMainTab === "history" && (
          <div className="space-y-6">
            {/* Summary KPI Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-6">
              <div className="bg-card border border-border rounded-xl p-4 sm:p-5 shadow-sm text-center">
                <p className="text-muted-foreground text-xs uppercase tracking-wider font-semibold mb-1">Total Notes Issued</p>
                <p className="text-2xl sm:text-3xl font-bold text-foreground font-mono">{historyNotes.length}</p>
                <p className="text-[11px] text-muted-foreground mt-1">Across all customers & suppliers</p>
              </div>

              <div className="bg-card border border-border rounded-xl p-4 sm:p-5 shadow-sm text-center">
                <p className="text-muted-foreground text-xs uppercase tracking-wider font-semibold mb-1 flex items-center justify-center gap-1">
                  <ArrowDownLeft className="w-3.5 h-3.5 text-amber-500" />
                  <span>Total Sales Returned (Credit Notes)</span>
                </p>
                <p className="text-2xl sm:text-3xl font-bold text-amber-600 dark:text-amber-400 font-mono">
                  ₹{totalCreditNotesValue.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </p>
                <p className="text-[11px] text-muted-foreground mt-1">Deducted from sales turnover</p>
              </div>

              <div className="bg-card border border-border rounded-xl p-4 sm:p-5 shadow-sm text-center">
                <p className="text-muted-foreground text-xs uppercase tracking-wider font-semibold mb-1 flex items-center justify-center gap-1">
                  <ArrowUpRight className="w-3.5 h-3.5 text-blue-500" />
                  <span>Total Purchases Returned (Debit Notes)</span>
                </p>
                <p className="text-2xl sm:text-3xl font-bold text-blue-600 dark:text-blue-400 font-mono">
                  ₹{totalDebitNotesValue.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </p>
                <p className="text-[11px] text-muted-foreground mt-1">Deducted from supplier bills</p>
              </div>
            </div>

            {/* Filter Pills and Search Bar */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-card border border-border p-3 rounded-xl">
              <div className="flex items-center gap-1.5 overflow-x-auto">
                <button
                  onClick={() => setHistoryFilterType("ALL")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors cursor-pointer ${
                    historyFilterType === "ALL"
                      ? "bg-primary text-primary-foreground shadow-xs"
                      : "bg-muted/50 text-muted-foreground hover:text-foreground"
                  }`}
                >
                  All ({historyNotes.length})
                </button>
                <button
                  onClick={() => setHistoryFilterType("CREDIT_NOTE")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors cursor-pointer ${
                    historyFilterType === "CREDIT_NOTE"
                      ? "bg-amber-600 text-white shadow-xs"
                      : "bg-muted/50 text-muted-foreground hover:text-foreground"
                  }`}
                >
                  Credit Notes (Sales Returns)
                </button>
                <button
                  onClick={() => setHistoryFilterType("DEBIT_NOTE")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors cursor-pointer ${
                    historyFilterType === "DEBIT_NOTE"
                      ? "bg-blue-600 text-white shadow-xs"
                      : "bg-muted/50 text-muted-foreground hover:text-foreground"
                  }`}
                >
                  Debit Notes (Purchase Returns)
                </button>
              </div>

              <div className="relative min-w-[220px]">
                <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-muted-foreground" />
                <input
                  type="text"
                  placeholder="Search party, voucher #, inv..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-8 pr-3 py-1.5 text-xs bg-background border border-border rounded-lg text-foreground outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
            </div>

            {/* Notes List Container */}
            <div className="bg-card border border-border rounded-2xl shadow-sm overflow-hidden">
              {loadingHistory ? (
                <div className="p-16 text-center text-muted-foreground text-sm">
                  <div className="animate-spin w-6 h-6 border-2 border-primary border-t-transparent rounded-full mx-auto mb-3" />
                  Loading credit and debit notes...
                </div>
              ) : filteredHistory.length === 0 ? (
                <div className="p-16 text-center text-muted-foreground space-y-3">
                  <RotateCcw className="w-12 h-12 mx-auto text-muted-foreground/40" />
                  <p className="text-base font-bold text-foreground">No Credit or Debit Notes Found</p>
                  <p className="text-xs max-w-sm mx-auto">
                    {historyNotes.length === 0
                      ? "You haven't issued any credit or debit notes yet. Click 'Create Note' above to record a sales or purchase return."
                      : "No notes match your current search or type filter."}
                  </p>
                  {historyNotes.length === 0 && (
                    <button
                      onClick={() => setActiveMainTab("new")}
                      className="mt-2 px-4 py-2 bg-primary text-primary-foreground rounded-xl text-xs font-bold shadow hover:bg-primary/90 transition-colors inline-flex items-center gap-1.5 cursor-pointer"
                    >
                      <Plus className="w-4 h-4" />
                      <span>Create First Note</span>
                    </button>
                  )}
                </div>
              ) : (
                <>
                  {/* Desktop Table */}
                  <div className="hidden md:block overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-border bg-muted/40 text-muted-foreground font-semibold uppercase text-[11px]">
                          <th className="py-3 px-4">Date</th>
                          <th className="py-3 px-3">Note #</th>
                          <th className="py-3 px-3">Type</th>
                          <th className="py-3 px-3">Party Name</th>
                          <th className="py-3 px-3">Original Invoice</th>
                          <th className="py-3 px-3">Narration / Reason</th>
                          <th className="py-3 px-4 text-right">Total Amount</th>
                          <th className="py-3 px-3 text-center">Status</th>
                          <th className="py-3 px-4 text-center">Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {filteredHistory.map((note) => {
                          const vType = String(note.voucherType || note.voucher_type || note.type || "").toUpperCase();
                          const vNum = note.voucherNumber || note.voucher_number || "-";
                          const vDate = note.voucherDate || note.voucher_date || note.date || "-";
                          const pName = note.partyName || note.party_name || (note.party_ledger?.name) || "-";
                          const refNo = note.referenceNumber || note.reference_number || "-";
                          const totAmt = Number(note.totalAmount ?? note.total_amount ?? 0);
                          const isCredit = vType === "CREDIT_NOTE";

                          return (
                            <tr key={note.id} className="hover:bg-muted/30 transition-colors">
                              <td className="py-3 px-4 font-mono text-muted-foreground whitespace-nowrap">
                                {vDate}
                              </td>
                              <td className="py-3 px-3 font-mono font-bold text-foreground whitespace-nowrap">
                                {vNum}
                              </td>
                              <td className="py-3 px-3 whitespace-nowrap">
                                <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                  isCredit
                                    ? "bg-amber-50 text-amber-800 border border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800"
                                    : "bg-blue-50 text-blue-800 border border-blue-200 dark:bg-blue-950/40 dark:text-blue-300 dark:border-blue-800"
                                }`}>
                                  {isCredit ? "Credit Note" : "Debit Note"}
                                </span>
                              </td>
                              <td className="py-3 px-3 font-semibold text-foreground max-w-[200px] truncate" title={pName}>
                                {pName}
                              </td>
                              <td className="py-3 px-3 font-mono text-muted-foreground whitespace-nowrap">
                                {refNo !== "-" ? (
                                  <span className="bg-muted px-1.5 py-0.5 rounded text-[11px] font-mono">{refNo}</span>
                                ) : (
                                  <span className="text-muted-foreground/50">-</span>
                                )}
                              </td>
                              <td className="py-3 px-3 text-muted-foreground max-w-[200px] truncate" title={note.narration || ""}>
                                {note.narration || "-"}
                              </td>
                              <td className="py-3 px-4 text-right font-mono font-bold text-sm whitespace-nowrap">
                                <span className={isCredit ? "text-amber-600 dark:text-amber-400" : "text-blue-600 dark:text-blue-400"}>
                                  ₹{totAmt.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                                </span>
                              </td>
                              <td className="py-3 px-3 text-center whitespace-nowrap">
                                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800">
                                  {note.status || "POSTED"}
                                </span>
                              </td>
                              <td className="py-3 px-4 text-center whitespace-nowrap">
                                <button
                                  onClick={() => setDeleteTarget({ id: note.id, number: vNum, type: vType })}
                                  title="Delete & Reverse Note"
                                  className="p-1.5 rounded-lg text-muted-foreground hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/30 transition-colors cursor-pointer"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  {/* Mobile Card View */}
                  <div className="block md:hidden divide-y divide-border">
                    {filteredHistory.map((note) => {
                      const vType = String(note.voucherType || note.voucher_type || note.type || "").toUpperCase();
                      const vNum = note.voucherNumber || note.voucher_number || "-";
                      const vDate = note.voucherDate || note.voucher_date || note.date || "-";
                      const pName = note.partyName || note.party_name || (note.party_ledger?.name) || "-";
                      const refNo = note.referenceNumber || note.reference_number || "-";
                      const totAmt = Number(note.totalAmount ?? note.total_amount ?? 0);
                      const isCredit = vType === "CREDIT_NOTE";

                      return (
                        <div key={note.id} className="p-4 space-y-2.5">
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-mono font-bold text-foreground text-sm">{vNum}</span>
                            <div className="flex items-center gap-1.5">
                              <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                isCredit
                                  ? "bg-amber-50 text-amber-800 border border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800"
                                  : "bg-blue-50 text-blue-800 border border-blue-200 dark:bg-blue-950/40 dark:text-blue-300 dark:border-blue-800"
                              }`}>
                                {isCredit ? "Credit Note" : "Debit Note"}
                              </span>
                              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800">
                                {note.status || "POSTED"}
                              </span>
                            </div>
                          </div>

                          <div className="flex items-center justify-between text-xs">
                            <span className="font-semibold text-foreground truncate max-w-[200px]">{pName}</span>
                            <span className="font-mono text-muted-foreground">{vDate}</span>
                          </div>

                          {refNo !== "-" && (
                            <p className="text-[11px] text-muted-foreground font-mono">
                              Against: <span className="font-semibold text-foreground">{refNo}</span>
                            </p>
                          )}

                          {note.narration && (
                            <p className="text-[11px] text-muted-foreground truncate">{note.narration}</p>
                          )}

                          <div className="flex items-center justify-between pt-1 border-t border-border/50">
                            <span className={`font-mono font-bold text-base ${isCredit ? "text-amber-600 dark:text-amber-400" : "text-blue-600 dark:text-blue-400"}`}>
                              ₹{totAmt.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                            </span>
                            <button
                              onClick={() => setDeleteTarget({ id: note.id, number: vNum, type: vType })}
                              className="px-2.5 py-1 text-xs font-semibold text-rose-600 bg-rose-50 hover:bg-rose-100 dark:bg-rose-950/40 dark:text-rose-300 rounded-lg flex items-center gap-1 transition-colors cursor-pointer"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                              <span>Delete</span>
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        {/* Delete Confirmation Modal */}
        <ConfirmModal
          isOpen={!!deleteTarget}
          onClose={() => setDeleteTarget(null)}
          onConfirm={handleDeleteConfirm}
          title={`Delete ${deleteTarget?.type === "CREDIT_NOTE" ? "Credit Note" : "Debit Note"}`}
          description={
            <div className="space-y-2 text-xs">
              <p>
                Are you sure you want to delete <strong>{deleteTarget?.number}</strong>?
              </p>
              <p className="text-muted-foreground">
                This will automatically reverse the double-entry accounting entries, restore the party ledger balance, and adjust your inventory.
              </p>
            </div>
          }
          confirmText="Delete Note"
          cancelText="Cancel"
          variant="danger"
          isLoading={deleting}
        />
      </div>
    </DashboardLayout>
  );
}

export default function CreditDebitNotePage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-muted-foreground">Loading...</div>}>
      <CreditDebitNoteContent />
    </Suspense>
  );
}
