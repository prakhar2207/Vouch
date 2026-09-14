"use client";
import React, { useState, useEffect } from "react";
import axios from "axios";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken } from "@/utils/auth";
import { useToast } from "@/context/ToastContext";
import { offlineDb } from "@/lib/db/offlineDb";
import {
  X,
  Check,
  Calendar,
  Hash,
  FileText,
  User,
  Plus,
  Trash2,
  Receipt,
  Layers,
  Percent,
  Search,
  Package,
} from "lucide-react";

interface EditableSalesItem {
  id?: string;
  product_id?: string;
  product_name: string;
  category_id?: string;
  category_name?: string;
  brand?: string;
  hsn_code: string;
  quantity: number;
  unit: string;
  rate: number;
  discount_percent: number;
  gst_rate: number;
}

interface CategoryOption {
  id: string;
  name: string;
  hsn_code?: string;
  gst_rate?: number | string;
}

interface EditSalesInvoiceModalProps {
  isOpen: boolean;
  onClose: () => void;
  voucher: any;
  onUpdateSuccess: () => void;
}

export default function EditSalesInvoiceModal({
  isOpen,
  onClose,
  voucher,
  onUpdateSuccess,
}: EditSalesInvoiceModalProps) {
  const { toast } = useToast();

  const [loadingDetails, setLoadingDetails] = useState(false);
  const [invoiceNumber, setInvoiceNumber] = useState("");
  const [invoiceDate, setInvoiceDate] = useState("");
  const [partyLedgerId, setPartyLedgerId] = useState("");
  const [partyName, setPartyName] = useState("");
  const [isCustomParty, setIsCustomParty] = useState(false);
  const [narration, setNarration] = useState("");
  const [cartageAmount, setCartageAmount] = useState<number | string>("");
  const [items, setItems] = useState<EditableSalesItem[]>([]);
  const [categories, setCategories] = useState<CategoryOption[]>([]);
  const [ledgers, setLedgers] = useState<any[]>([]);
  const [products, setProducts] = useState<any[]>([]);
  const [activeSearchIdx, setActiveSearchIdx] = useState<number | null>(null);
  const [allocations, setAllocations] = useState<any[]>([]);
  const [paidAmount, setPaidAmount] = useState<number>(0);
  const [paymentStatus, setPaymentStatus] = useState<string>("UNPAID");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isOpen && voucher?.id) {
      loadFullVoucher();
    }
  }, [isOpen, voucher?.id]);

  const fetchMasters = async (companyId?: string) => {
    const cid = companyId || voucher?.company_id || voucher?.company?.id;

    // 1. First attempt to load cached masters from offline IndexedDB
    try {
      const [cachedCats, cachedLedgers, cachedProds] = await Promise.all([
        offlineDb.masters.get("categories"),
        offlineDb.masters.get("ledgers"),
        offlineDb.masters.get("products"),
      ]);
      if (cachedCats?.data?.length) setCategories(cachedCats.data);
      if (cachedLedgers?.data?.length) setLedgers(cachedLedgers.data);
      if (cachedProds?.data?.length) setProducts(cachedProds.data);
    } catch (cacheErr) {
      // ignore cache error
    }

    // 2. Fetch fresh masters from API
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      let targetCid = cid;
      if (!targetCid) {
        const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
        targetCid = compRes.data?.data?.[0]?.id;
      }

      if (targetCid) {
        const [catsRes, ledgersRes, prodsRes] = await Promise.all([
          axios.get(`${API_BASE_URL}/api/v1/inventory/categories/${targetCid}/`, { headers }).catch(() => ({ data: { data: [] } })),
          axios.get(`${API_BASE_URL}/api/v1/ledgers/${targetCid}/`, { headers }).catch(() => ({ data: { data: [] } })),
          axios.get(`${API_BASE_URL}/api/v1/inventory/products/${targetCid}/`, { headers }).catch(() => ({ data: { data: [] } })),
        ]);

        const catList = catsRes.data?.data || [];
        const ledgerList = ledgersRes.data?.data || [];
        const prodList = prodsRes.data?.data || [];

        if (catList.length) {
          setCategories(catList);
          offlineDb.masters.put({ key: "categories", data: catList, updatedAt: Date.now() }).catch(() => {});
        }
        if (ledgerList.length) {
          setLedgers(ledgerList);
          offlineDb.masters.put({ key: "ledgers", data: ledgerList, updatedAt: Date.now() }).catch(() => {});
        }
        if (prodList.length) {
          setProducts(prodList);
          offlineDb.masters.put({ key: "products", data: prodList, updatedAt: Date.now() }).catch(() => {});
        }
      }
    } catch (e) {
      console.error("Failed to load masters in sales edit modal", e);
    }
  };

  const loadFullVoucher = async () => {
    setLoadingDetails(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.get(`${API_BASE_URL}/api/vouchers/${voucher.id}/`, { headers });

      if (res.data.success && res.data.data) {
        const v = res.data.data;
        const targetCid = v.company?.id || v.company_id;
        fetchMasters(targetCid);

        setInvoiceNumber(v.voucher_number || "");
        setInvoiceDate(v.date || "");
        const partyId = v.party_ledger_id || v.party?.id || "";
        setPartyLedgerId(partyId);
        setPartyName(v.party?.name || v.buyer_name || "");
        setIsCustomParty(!partyId && Boolean(v.buyer_name || v.party?.name));
        setNarration(v.narration || "");
        setCartageAmount(v.cartage_amount ? Number(v.cartage_amount) : "");
        setAllocations(v.allocations || []);
        setPaidAmount(Number(v.paid_amount || 0));
        setPaymentStatus(v.payment_status || "UNPAID");

        const loadedItems: EditableSalesItem[] = (v.items || []).map((item: any) => ({
          id: item.id,
          product_id: item.product_id || undefined,
          product_name: item.product_name || "",
          category_id: item.category_id || undefined,
          category_name: item.category_name || "Unassigned",
          brand: item.brand || "",
          hsn_code: item.hsn_code || "",
          quantity: parseFloat(item.quantity) || 1,
          unit: item.unit || "PCS",
          rate: parseFloat(item.rate) || 0,
          discount_percent: item.discount_percent !== undefined && item.discount_percent !== null ? parseFloat(item.discount_percent) : 0,
          gst_rate: parseFloat(item.gst_rate) || 18,
        }));

        if (loadedItems.length === 0) {
          loadedItems.push({
            product_name: "",
            category_id: undefined,
            category_name: "Unassigned",
            brand: "",
            hsn_code: "",
            quantity: 1,
            unit: "PCS",
            rate: 0,
            discount_percent: 0,
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

  const updateItemField = (index: number, field: keyof EditableSalesItem, value: any) => {
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
        category_id: undefined,
        category_name: "Unassigned",
        brand: "",
        hsn_code: "",
        quantity: 1,
        unit: "PCS",
        rate: 0,
        discount_percent: Number(selectedParty?.discount_percent || 0),
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

  // Master Lookups & Computed
  const customerLedgers = ledgers.filter(
    (l: any) =>
      l.group?.includes("Debtor") ||
      l.group?.includes("Cash") ||
      l.group?.includes("Bank") ||
      l.ledger_type === "CUSTOMER" ||
      l.ledger_type === "PARTY" ||
      l.ledger_type === "BOTH" ||
      l.ledger_type === "CASH" ||
      l.ledger_type === "BANK" ||
      l.name?.toLowerCase().includes("cash") ||
      l.name?.toLowerCase().includes("customer")
  );
  const displayLedgers = customerLedgers.length > 0 ? customerLedgers : ledgers;
  const selectedParty = ledgers.find((l: any) => l.id === partyLedgerId);

  const handlePartyChange = (selectedId: string) => {
    setPartyLedgerId(selectedId);
    if (!selectedId) {
      setIsCustomParty(true);
      return;
    }
    setIsCustomParty(false);
    const selected = ledgers.find((l: any) => l.id === selectedId);
    if (selected) {
      setPartyName(selected.name);
      const partyDisc = Number(selected.discount_percent || 0);
      if (partyDisc > 0) {
        setItems((prev) =>
          prev.map((it) =>
            it.discount_percent === 0 ? { ...it, discount_percent: partyDisc } : it
          )
        );
      }
    }
  };

  const selectProduct = (idx: number, prod: any) => {
    setItems((prev) => {
      const copy = [...prev];
      const current = copy[idx];
      const targetCatId = prod.category_id || current.category_id;
      const matchedCat = categories.find((c) => c.id === targetCatId);
      const catName = prod.category?.name || matchedCat?.name || current.category_name || "Unassigned";
      const hsn = prod.hsn_code || matchedCat?.hsn_code || current.hsn_code || "";
      const gst =
        Number(prod.gst_rate) ||
        (matchedCat?.gst_rate ? Number(matchedCat.gst_rate) : current.gst_rate) ||
        18;
      const price = parseFloat(String(prod.selling_price || 0)) || current.rate || 0;
      const partyDisc = Number(selectedParty?.discount_percent || 0);

      copy[idx] = {
        ...current,
        product_id: prod.id,
        product_name: prod.name,
        brand: prod.brand || current.brand || "",
        category_id: targetCatId || undefined,
        category_name: catName,
        hsn_code: hsn,
        unit: prod.unit || current.unit || "PCS",
        rate: price,
        gst_rate: gst,
        discount_percent:
          current.discount_percent === 0 && partyDisc > 0
            ? partyDisc
            : current.discount_percent,
      };
      return copy;
    });
    setActiveSearchIdx(null);
  };

  const handleCategoryChange = (idx: number, selectedId: string) => {
    const selectedCat = categories.find((c) => c.id === selectedId);
    setItems((prev) => {
      const copy = [...prev];
      const current = copy[idx];
      copy[idx] = {
        ...current,
        category_id: selectedId || undefined,
        category_name: selectedCat ? selectedCat.name : "Unassigned",
        hsn_code: current.hsn_code || selectedCat?.hsn_code || "",
        gst_rate: selectedCat?.gst_rate ? Number(selectedCat.gst_rate) : current.gst_rate,
      };
      return copy;
    });
  };

  // Calculations
  const grossTotal = items.reduce((acc, item) => acc + item.quantity * item.rate, 0);
  const totalDiscount = items.reduce(
    (acc, item) => acc + item.quantity * item.rate * ((item.discount_percent || 0) / 100),
    0
  );
  const taxableTotal = items.reduce((acc, item) => {
    const gross = item.quantity * item.rate;
    const disc = gross * ((item.discount_percent || 0) / 100);
    return acc + (gross - disc);
  }, 0);

  const totalTax = items.reduce((acc, item) => {
    const gross = item.quantity * item.rate;
    const disc = gross * ((item.discount_percent || 0) / 100);
    const taxable = gross - disc;
    return acc + taxable * (item.gst_rate / 100);
  }, 0);

  const cartageVal = Number(cartageAmount) || 0;
  const unroundedGrandTotal = taxableTotal + totalTax + cartageVal;
  let grandTotal = 0;
  let roundOff = 0;
  if (unroundedGrandTotal > 0) {
    const integerPart = Math.floor(unroundedGrandTotal);
    const decimalPart = Math.round((unroundedGrandTotal - integerPart) * 100) / 100;
    grandTotal = decimalPart < 0.5 ? integerPart : integerPart + 1;
    roundOff = Math.round((grandTotal - unroundedGrandTotal) * 100) / 100;
  }

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

      const payload: any = {
        voucher_number: invoiceNumber.trim(),
        voucher_date: invoiceDate,
        party_ledger_id: isCustomParty ? null : (partyLedgerId || null),
        party_name: partyName.trim(),
        narration: narration.trim(),
        cartage_amount: cartageVal,
        items: items.map((it) => ({
          product_id: it.product_id || null,
          product_name: it.product_name.trim(),
          category_id: it.category_id || null,
          category_name: it.category_name || "",
          brand: it.brand?.trim() || "",
          hsn_code: it.hsn_code.trim(),
          quantity: it.quantity,
          rate: it.rate,
          unit: it.unit.trim().toUpperCase() || "PCS",
          discount_percent: it.discount_percent !== undefined && it.discount_percent !== null ? Number(it.discount_percent) : 0,
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
          "Sales Invoice updated successfully!",
          "Rates, discounts, ledger entries, and inventory stock have been recalculated."
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
      <div className="relative bg-card border border-border/80 w-full max-w-6xl rounded-2xl shadow-2xl overflow-hidden z-10 animate-in fade-in zoom-in-95 duration-200 flex flex-col max-h-[92vh]">
        {/* Header */}
        <div className="px-6 py-4 border-b border-border/60 bg-muted/20 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20 flex items-center justify-center">
              <Receipt className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-base font-bold text-foreground">Edit Sales Invoice</h3>
              <p className="text-xs text-muted-foreground">
                Modify line items, quantities, rates, customer discount %, and invoice metadata
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
                  Invoice No. *
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
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-semibold text-muted-foreground uppercase flex items-center gap-1.5">
                    <User className="w-3.5 h-3.5 text-blue-400" />
                    Customer / Party *
                  </label>
                  <button
                    type="button"
                    onClick={() => {
                      const nextCustom = !isCustomParty;
                      setIsCustomParty(nextCustom);
                      if (nextCustom) {
                        setPartyLedgerId("");
                      }
                    }}
                    className="text-[11px] text-blue-400 hover:text-blue-300 font-medium cursor-pointer"
                  >
                    {isCustomParty ? "← Select from List" : "+ Enter Custom Name"}
                  </button>
                </div>
                {isCustomParty ? (
                  <input
                    type="text"
                    required
                    placeholder="Enter custom buyer / customer name..."
                    value={partyName}
                    onChange={(e) => setPartyName(e.target.value)}
                    className="w-full bg-muted/40 border border-border/70 text-foreground text-xs px-3 py-1.5 rounded-lg outline-none focus:ring-1 focus:ring-blue-500 font-semibold"
                  />
                ) : (
                  <select
                    value={partyLedgerId}
                    onChange={(e) => handlePartyChange(e.target.value)}
                    className="w-full bg-muted/40 border border-border/70 text-foreground text-xs px-3 py-1.5 rounded-lg outline-none focus:ring-1 focus:ring-blue-500 font-semibold cursor-pointer"
                  >
                    <option value="" className="bg-background text-foreground">-- Select Customer / Cash / Bank --</option>
                    {displayLedgers.map((l: any) => (
                      <option key={l.id} value={l.id} className="bg-background text-foreground">
                        {l.name} {l.group ? `[${l.group}]` : ""} {Number(l.discount_percent || 0) > 0 ? `(${Number(l.discount_percent)}% Disc)` : ""}
                      </option>
                    ))}
                  </select>
                )}
                {selectedParty && Number(selectedParty.discount_percent || 0) > 0 && (
                  <div className="mt-1 text-[11px] text-blue-400 flex items-center gap-1 font-medium">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse"></span>
                    <span>Customer Discount: <strong className="font-mono">{Number(selectedParty.discount_percent)}%</strong></span>
                  </div>
                )}
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

              <div className="border border-border/70 rounded-xl overflow-visible">
                <table className="w-full text-xs text-left border-collapse">
                  <thead className="bg-muted/60 border-b border-border text-muted-foreground uppercase text-xs tracking-wider font-semibold">
                    <tr>
                      <th className="p-2.5 w-6 text-center">#</th>
                      <th className="p-2.5 min-w-[150px]">Item Name / Size</th>
                      <th className="p-2.5 w-32">Category</th>
                      <th className="p-2.5 w-24">Brand</th>
                      <th className="p-2.5 w-20">HSN Code</th>
                      <th className="p-2.5 w-18 text-right">Qty</th>
                      <th className="p-2.5 w-14 text-center">Unit</th>
                      <th className="p-2.5 w-22 text-right">Rate (₹)</th>
                      <th className="p-2.5 w-18 text-right">Disc %</th>
                      <th className="p-2.5 w-18 text-right">GST %</th>
                      <th className="p-2.5 w-24 text-right">Total (₹)</th>
                      <th className="p-2.5 w-10 text-center"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40">
                    {items.map((item, idx) => {
                      const gross = item.quantity * item.rate;
                      const disc = gross * ((item.discount_percent || 0) / 100);
                      const lineTaxable = gross - disc;
                      const lineTax = lineTaxable * (item.gst_rate / 100);
                      const lineTotal = lineTaxable + lineTax;

                      return (
                        <tr key={idx} className="hover:bg-muted/30 transition-colors">
                          <td className="p-2 text-muted-foreground font-mono tabular-nums text-center text-xs font-semibold">
                            {idx + 1}
                          </td>

                          {/* Item Name with Product Autocomplete Popover */}
                          <td className="p-2 relative">
                            <div className="relative">
                              <input
                                type="text"
                                required
                                placeholder="Search catalog or type item..."
                                value={item.product_name}
                                onChange={(e) => {
                                  updateItemField(idx, "product_name", e.target.value);
                                  setActiveSearchIdx(idx);
                                }}
                                onFocus={() => setActiveSearchIdx(idx)}
                                onBlur={() => setTimeout(() => setActiveSearchIdx(null), 250)}
                                className="w-full min-h-[32px] bg-background/50 border border-border/60 text-foreground font-medium px-2.5 py-1 rounded-md outline-none focus:border-primary focus:bg-background"
                              />

                              {/* Autocomplete Dropdown Popover */}
                              {activeSearchIdx === idx && (
                                <div
                                  className="absolute left-0 top-full mt-1 z-50 w-full min-w-[340px] max-w-[480px] bg-card border border-border rounded-xl shadow-2xl overflow-hidden max-h-64 overflow-y-auto"
                                  onMouseDown={(e) => e.preventDefault()}
                                >
                                  {(() => {
                                    const query = String(item.product_name || "").trim().toLowerCase();
                                    const queryAlpha = query.replace(/[\s\-_/.]/g, "");
                                    const filteredProds = products.filter((p: any) => {
                                      if (item.category_id && p.category_id && p.category_id !== item.category_id) {
                                        if (!query) return false;
                                      }
                                      if (!query) return true;
                                      const pName = (p.name || "").toLowerCase();
                                      const pAlpha = pName.replace(/[\s\-_/.]/g, "");
                                      const pBrand = (p.brand || "").toLowerCase();
                                      const pAlias = (p.alias || "").toLowerCase();
                                      const pSku = (p.sku || "").toLowerCase();
                                      return (
                                        pName.includes(query) ||
                                        pAlpha.includes(queryAlpha) ||
                                        pBrand.includes(query) ||
                                        pAlias.includes(query) ||
                                        pSku.includes(query)
                                      );
                                    });

                                    if (filteredProds.length === 0) {
                                      return (
                                        <div className="p-3 text-xs text-muted-foreground italic">
                                          No catalog product found. Enter details manually.
                                        </div>
                                      );
                                    }

                                    return (
                                      <div className="divide-y divide-border/60">
                                        <div className="bg-muted/80 px-3 py-1.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider flex justify-between">
                                          <span>Catalog Products</span>
                                          <span>{filteredProds.length} match{filteredProds.length > 1 ? "es" : ""}</span>
                                        </div>
                                        {filteredProds.slice(0, 30).map((p: any) => {
                                          const isSelected = item.product_id === p.id;
                                          const price = parseFloat(p.selling_price) || 0;
                                          const stock = Number(p.stock_quantity ?? 0);
                                          return (
                                            <button
                                              key={p.id}
                                              type="button"
                                              onClick={() => selectProduct(idx, p)}
                                              className={`w-full text-left p-2.5 hover:bg-muted/60 flex items-center justify-between gap-3 cursor-pointer transition-colors ${
                                                isSelected ? "bg-blue-500/10 border-l-2 border-blue-500" : ""
                                              }`}
                                            >
                                              <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 flex-wrap">
                                                  <span className="font-semibold text-foreground text-xs truncate">
                                                    {p.name}
                                                  </span>
                                                  {p.brand && (
                                                    <span className="text-[10px] bg-blue-500/10 text-blue-400 border border-blue-500/20 px-1.5 py-0.5 rounded font-medium">
                                                      {p.brand}
                                                    </span>
                                                  )}
                                                  {p.category?.name && (
                                                    <span className="text-[10px] bg-muted text-muted-foreground px-1.5 py-0.5 rounded">
                                                      {p.category.name}
                                                    </span>
                                                  )}
                                                </div>
                                                <div className="text-[11px] text-muted-foreground flex items-center gap-3 mt-0.5">
                                                  {p.hsn_code && <span>HSN: {p.hsn_code}</span>}
                                                  <span>GST: {Number(p.gst_rate || 18)}%</span>
                                                  <span className={stock > 0 ? "text-emerald-400" : "text-amber-400"}>
                                                    Stock: {stock} {p.unit || "PCS"}
                                                  </span>
                                                </div>
                                              </div>
                                              <div className="text-right whitespace-nowrap">
                                                <div className="font-bold text-foreground text-xs">
                                                  ₹{price.toFixed(2)}
                                                </div>
                                                <div className="text-[10px] text-muted-foreground">
                                                  per {p.unit || "PCS"}
                                                </div>
                                              </div>
                                            </button>
                                          );
                                        })}
                                      </div>
                                    );
                                  })()}
                                </div>
                              )}
                            </div>
                          </td>

                          {/* Category */}
                          <td className="p-2">
                            <select
                              value={item.category_id || ""}
                              onChange={(e) => handleCategoryChange(idx, e.target.value)}
                              className="w-full min-h-[32px] bg-background/50 border border-border/60 text-foreground text-xs px-2 py-1 rounded-md outline-none focus:border-primary focus:bg-background font-medium cursor-pointer"
                            >
                              <option value="" className="bg-background text-foreground">Unassigned</option>
                              {categories.map((cat) => (
                                <option key={cat.id} value={cat.id} className="bg-background text-foreground">
                                  {cat.name}
                                </option>
                              ))}
                            </select>
                          </td>

                          {/* Brand */}
                          <td className="p-2">
                            <input
                              type="text"
                              placeholder="e.g. Modicord"
                              value={item.brand || ""}
                              onChange={(e) => updateItemField(idx, "brand", e.target.value)}
                              className="w-full min-h-[32px] bg-background/50 border border-border/60 text-foreground text-xs px-2.5 py-1 rounded-md outline-none focus:border-primary focus:bg-background font-medium"
                            />
                          </td>

                          {/* HSN */}
                          <td className="p-2">
                            <input
                              type="text"
                              placeholder="4010"
                              value={item.hsn_code}
                              onChange={(e) => updateItemField(idx, "hsn_code", e.target.value)}
                              className="w-full min-h-[32px] bg-background/50 border border-border/60 text-foreground font-mono tabular-nums px-2 py-1 rounded-md outline-none focus:border-primary focus:bg-background text-center text-xs font-medium"
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
                              onChange={(e) =>
                                updateItemField(idx, "quantity", parseFloat(e.target.value) || 0)
                              }
                              className="w-full min-h-[32px] bg-background/50 border border-border/60 text-foreground font-mono tabular-nums px-2 py-1 rounded-md outline-none focus:border-primary focus:bg-background text-right font-bold text-xs"
                            />
                          </td>

                          {/* Unit */}
                          <td className="p-2">
                            <input
                              type="text"
                              value={item.unit}
                              onChange={(e) =>
                                updateItemField(idx, "unit", e.target.value.toUpperCase())
                              }
                              className="w-full min-h-[32px] bg-background/50 border border-border/60 text-muted-foreground font-mono text-xs px-1.5 py-1 rounded-md outline-none text-center font-medium"
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
                              onChange={(e) =>
                                updateItemField(idx, "rate", parseFloat(e.target.value) || 0)
                              }
                              className="w-full min-h-[32px] bg-background/50 border border-border/60 text-foreground font-mono tabular-nums px-2 py-1 rounded-md outline-none focus:border-primary focus:bg-background text-right font-bold text-xs"
                            />
                          </td>

                          {/* Discount % */}
                          <td className="p-2 text-right">
                            <input
                              type="number"
                              step="0.01"
                              min="0"
                              max="100"
                              value={item.discount_percent}
                              onChange={(e) =>
                                updateItemField(
                                  idx,
                                  "discount_percent",
                                  parseFloat(e.target.value) || 0
                                )
                              }
                              className="w-full min-h-[32px] bg-background/50 border border-border/60 text-amber-500 font-mono tabular-nums text-xs px-1.5 py-1 rounded-md outline-none text-right font-bold focus:border-primary focus:bg-background"
                            />
                          </td>

                          {/* GST Rate */}
                          <td className="p-2 text-right">
                            <select
                              value={item.gst_rate}
                              onChange={(e) =>
                                updateItemField(idx, "gst_rate", parseFloat(e.target.value) || 0)
                              }
                              className="w-full min-h-[32px] bg-background border border-border text-foreground font-mono tabular-nums text-xs px-1.5 py-1 rounded-md outline-none text-right cursor-pointer"
                            >
                              <option value={0} className="bg-background text-foreground">
                                0%
                              </option>
                              <option value={5} className="bg-background text-foreground">
                                5%
                              </option>
                              <option value={12} className="bg-background text-foreground">
                                12%
                              </option>
                              <option value={18} className="bg-background text-foreground">
                                18%
                              </option>
                              <option value={28} className="bg-background text-foreground">
                                28%
                              </option>
                            </select>
                          </td>

                          {/* Line Total */}
                          <td className="p-2 text-right font-mono tabular-nums font-bold text-emerald-500 whitespace-nowrap text-xs">
                            ₹
                            {lineTotal.toLocaleString("en-IN", {
                              minimumFractionDigits: 2,
                              maximumFractionDigits: 2,
                            })}
                          </td>

                          {/* Action */}
                          <td className="p-2 text-center">
                            <button
                              type="button"
                              onClick={() => handleRemoveItem(idx)}
                              className="p-1.5 min-w-[30px] min-h-[30px] inline-flex items-center justify-center text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded transition-colors cursor-pointer"
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
                  placeholder="Payment terms, delivery notes, or remarks..."
                  className="w-full bg-muted/30 border border-border/70 text-foreground text-xs px-3.5 py-2 rounded-xl outline-none focus:ring-1 focus:ring-blue-500 resize-none"
                />
              </div>

              {/* Live Totals Card */}
              <div className="bg-muted/30 p-4 rounded-xl border border-border/70 space-y-2 text-xs">
                <div className="flex justify-between text-muted-foreground">
                  <span>Gross Amount:</span>
                  <span className="font-mono tabular-nums font-semibold text-foreground">
                    ₹{grossTotal.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </span>
                </div>
                {totalDiscount > 0 && (
                  <div className="flex justify-between text-amber-500 font-medium">
                    <span>Discount:</span>
                    <span className="font-mono tabular-nums font-semibold">
                      -₹{totalDiscount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                )}
                <div className="flex justify-between text-muted-foreground">
                  <span>Taxable Subtotal:</span>
                  <span className="font-mono tabular-nums font-semibold text-foreground">
                    ₹{taxableTotal.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </span>
                </div>
                <div className="flex justify-between text-muted-foreground">
                  <span>Total Taxes (GST):</span>
                  <span className="font-mono tabular-nums font-semibold text-foreground">
                    ₹{totalTax.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </span>
                </div>
                <div className="flex justify-between items-center text-muted-foreground">
                  <span>Cartage / Freight Outward:</span>
                  <div className="flex items-center gap-1.5">
                    <span className="text-muted-foreground font-mono">₹</span>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={cartageAmount}
                      onChange={(e) => setCartageAmount(e.target.value)}
                      placeholder="0.00"
                      className="w-28 bg-background border border-border text-foreground text-right px-2.5 py-1 rounded font-mono tabular-nums text-xs font-semibold focus:border-primary outline-none"
                    />
                  </div>
                </div>
                <div className="flex justify-between text-muted-foreground">
                  <span>Round Off:</span>
                  <span
                    className={
                      roundOff < 0
                        ? "text-emerald-500 font-mono tabular-nums font-semibold"
                        : roundOff > 0
                        ? "text-amber-500 font-mono tabular-nums font-semibold"
                        : "text-muted-foreground font-mono tabular-nums"
                    }
                  >
                    {roundOff > 0
                      ? `+₹${roundOff.toFixed(2)}`
                      : roundOff < 0
                      ? `-₹${Math.abs(roundOff).toFixed(2)}`
                      : `₹0.00`}
                  </span>
                </div>
                <div className="flex justify-between border-t border-border pt-2.5 font-bold text-sm">
                  <span>Net Invoice Amount:</span>
                  <span className="font-mono tabular-nums text-primary text-base font-black">
                    ₹{grandTotal.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </span>
                </div>
              </div>
            </div>

            {/* Payment Settlements & Bill Allocations Breakdown */}
            <div className="bg-muted/30 p-4 rounded-xl border border-border/70 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Receipt className="w-4 h-4 text-primary" />
                  <h4 className="text-xs font-bold text-foreground">Linked Payments & Bill Allocations</h4>
                </div>
                <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold font-mono border ${
                  paymentStatus === 'PAID'
                    ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                    : paymentStatus === 'PARTIAL'
                    ? 'bg-amber-500/15 text-amber-400 border-amber-500/30'
                    : 'bg-rose-500/15 text-rose-400 border-rose-500/30'
                }`}>
                  {paymentStatus} (₹{paidAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })} Settled)
                </span>
              </div>

              {allocations.length > 0 ? (
                <div className="overflow-x-auto rounded-lg border border-border/50">
                  <table className="w-full text-left text-xs font-mono">
                    <thead className="bg-muted/60 text-muted-foreground text-[10px] uppercase">
                      <tr>
                        <th className="p-2">Receipt Voucher</th>
                        <th className="p-2">Date</th>
                        <th className="p-2 text-right">Allocated Amount</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/40">
                      {allocations.map((alloc: any, i: number) => (
                        <tr key={alloc.id || i} className="hover:bg-muted/20">
                          <td className="p-2 text-foreground font-semibold">{alloc.voucher_number || `Voucher #${alloc.voucher_id?.slice(0, 8)}`}</td>
                          <td className="p-2 text-muted-foreground">{alloc.voucher_date || '-'}</td>
                          <td className="p-2 text-right font-bold text-emerald-500">₹{Number(alloc.amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">
                  No payment receipts allocated against this invoice yet. Outstanding balance: ₹{Math.max(0, grandTotal - paidAmount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}.
                </p>
              )}
            </div>

            {/* Modal Footer */}
            <div className="pt-4 border-t border-border/60 flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                Saving will update customer ledger balance, GST liabilities, and stock deductions.
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
