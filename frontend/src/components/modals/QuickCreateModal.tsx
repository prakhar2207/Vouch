"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import { useShortcuts } from "@/context/ShortcutContext";
import { getAccessToken } from "@/utils/auth";
import StateSelect from "@/components/StateSelect";

export default function QuickCreateModal() {
  const { isAltCOpen, setIsAltCOpen, altCEntityType, notifyAltCCreated } = useShortcuts();

  const [activeTab, setActiveTab] = useState<"LEDGER" | "PRODUCT">("LEDGER");
  const [companyId, setCompanyId] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Ledger Form
  const [ledgerName, setLedgerName] = useState("");
  const [ledgerGroup, setLedgerGroup] = useState("Sundry Debtors");
  const [ledgerType, setLedgerType] = useState("CUSTOMER");
  const [gstin, setGstin] = useState("");
  const [stateCode, setStateCode] = useState("09");

  // Product Form
  const [productName, setProductName] = useState("");
  const [sku, setSku] = useState("");
  const [hsnCode, setHsnCode] = useState("");
  const [gstRate, setGstRate] = useState(18);
  const [unit, setUnit] = useState("PCS");
  const [price, setPrice] = useState(0);

  const firstInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isAltCOpen) {
      setActiveTab(altCEntityType);
      setError(null);
      fetchCompany();
      setTimeout(() => firstInputRef.current?.focus(), 50);
    }
  }, [isAltCOpen, altCEntityType]);

  const fetchCompany = async () => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const cid = compRes.data.data?.[0]?.id;
      if (cid) setCompanyId(cid);
    } catch (e) {
      console.error(e);
    }
  };

  if (!isAltCOpen) return null;

  const handleSaveLedger = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ledgerName || !companyId) return;

    setSaving(true);
    setError(null);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      const payload = {
        name: ledgerName,
        group_name: ledgerGroup,
        ledger_type: ledgerType,
        gstin: gstin.toUpperCase(),
        state_code: stateCode,
      };

      const res = await axios.post(`${API_BASE_URL}/api/v1/ledgers/${companyId}/`, payload, { headers });
      const created = res.data.data;
      notifyAltCCreated(created);
      setIsAltCOpen(false);

      // Reset form
      setLedgerName("");
      setGstin("");
    } catch (err: any) {
      setError(err.response?.data?.error || err.message || "Failed to create ledger.");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveProduct = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!productName || !companyId) return;

    setSaving(true);
    setError(null);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      const payload = {
        name: productName,
        sku: sku || productName.toUpperCase().slice(0, 4) + "-" + Math.floor(Math.random() * 1000),
        hsn_code: hsnCode,
        gst_rate: Number(gstRate),
        unit: unit,
        selling_price: Number(price),
        purchase_price: Number(price),
      };

      const res = await axios.post(`${API_BASE_URL}/api/v1/inventory/products/${companyId}/`, payload, { headers });
      const created = res.data.data;
      notifyAltCCreated(created);
      setIsAltCOpen(false);

      // Reset form
      setProductName("");
      setSku("");
      setHsnCode("");
    } catch (err: any) {
      setError(err.response?.data?.error || err.message || "Failed to create product.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm animate-in fade-in duration-150 p-4">
      <div className="w-full max-w-lg bg-zinc-900 border border-zinc-700 rounded-2xl shadow-2xl overflow-hidden text-white space-y-5 p-6">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
          <div className="flex items-center gap-2.5">
            <span className="px-2 py-0.5 bg-purple-600/20 text-purple-400 border border-purple-500/30 rounded text-xs font-mono font-bold">
              Alt + C
            </span>
            <h3 className="text-lg font-bold text-white">Create Master on the Fly</h3>
          </div>
          <button onClick={() => setIsAltCOpen(false)} className="text-gray-400 hover:text-white font-bold text-sm">
            ✕
          </button>
        </div>

        {/* Tab Switcher */}
        <div className="flex bg-zinc-950 p-1 rounded-xl border border-zinc-800">
          <button
            onClick={() => setActiveTab("LEDGER")}
            type="button"
            className={`flex-1 py-1.5 rounded-lg text-xs font-bold transition-all ${
              activeTab === "LEDGER" ? "bg-blue-600 text-white shadow" : "text-gray-400 hover:text-white"
            }`}
          >
            Party / Ledger Master
          </button>
          <button
            onClick={() => setActiveTab("PRODUCT")}
            type="button"
            className={`flex-1 py-1.5 rounded-lg text-xs font-bold transition-all ${
              activeTab === "PRODUCT" ? "bg-blue-600 text-white shadow" : "text-gray-400 hover:text-white"
            }`}
          >
            Product / Item Master
          </button>
        </div>

        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-xs font-medium">
            {error}
          </div>
        )}

        {/* Ledger Form */}
        {activeTab === "LEDGER" && (
          <form onSubmit={handleSaveLedger} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Ledger / Party Name</label>
              <input
                ref={firstInputRef}
                type="text"
                value={ledgerName}
                onChange={(e) => setLedgerName(e.target.value)}
                placeholder="e.g. Shyam Traders"
                required
                className="w-full bg-zinc-950 border border-zinc-700 text-white p-2.5 rounded-lg text-sm font-semibold outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Account Group</label>
                <select
                  value={ledgerGroup}
                  onChange={(e) => {
                    setLedgerGroup(e.target.value);
                    if (e.target.value === "Sundry Debtors") setLedgerType("CUSTOMER");
                    else if (e.target.value === "Sundry Creditors") setLedgerType("SUPPLIER");
                    else setLedgerType("GENERAL");
                  }}
                  className="w-full bg-zinc-950 border border-zinc-700 text-white p-2.5 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500 font-medium"
                >
                  <option value="Sundry Debtors">Sundry Debtors (Customer)</option>
                  <option value="Sundry Creditors">Sundry Creditors (Supplier)</option>
                  <option value="Bank Accounts">Bank Accounts</option>
                  <option value="Cash-in-Hand">Cash-in-Hand</option>
                  <option value="Sales Accounts">Sales Accounts</option>
                  <option value="Purchase Accounts">Purchase Accounts</option>
                  <option value="Duties & Taxes">Duties & Taxes</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">GSTIN (Optional)</label>
                <input
                  type="text"
                  value={gstin}
                  onChange={(e) => setGstin(e.target.value.toUpperCase())}
                  placeholder="2-Digit State + PAN..."
                  className="w-full bg-zinc-950 border border-zinc-700 text-white p-2.5 rounded-lg text-sm font-mono uppercase outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            <div>
              <StateSelect value={stateCode} onChange={setStateCode} label="State Code / Place of Supply" />
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setIsAltCOpen(false)}
                className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-gray-300 rounded-lg text-xs font-medium transition-colors"
              >
                Cancel (Esc)
              </button>
              <button
                type="submit"
                disabled={saving}
                className="px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold shadow-md transition-colors"
              >
                {saving ? "Creating..." : "Save & Auto-Select (Ctrl+A)"}
              </button>
            </div>
          </form>
        )}

        {/* Product Form */}
        {activeTab === "PRODUCT" && (
          <form onSubmit={handleSaveProduct} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Product / Item Name</label>
              <input
                ref={firstInputRef}
                type="text"
                value={productName}
                onChange={(e) => setProductName(e.target.value)}
                placeholder="e.g. Precision Industrial Bearing"
                required
                className="w-full bg-zinc-950 border border-zinc-700 text-white p-2.5 rounded-lg text-sm font-semibold outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">HSN / SAC Code</label>
                <input
                  type="text"
                  value={hsnCode}
                  onChange={(e) => setHsnCode(e.target.value)}
                  placeholder="e.g. 84821010"
                  className="w-full bg-zinc-950 border border-zinc-700 text-white p-2.5 rounded-lg text-sm font-mono outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">GST Rate (%)</label>
                <select
                  value={gstRate}
                  onChange={(e) => setGstRate(Number(e.target.value))}
                  className="w-full bg-zinc-950 border border-zinc-700 text-white p-2.5 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500 font-medium"
                >
                  <option value={0}>0%</option>
                  <option value={5}>5%</option>
                  <option value={12}>12%</option>
                  <option value={18}>18%</option>
                  <option value={28}>28%</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Unit of Measurement</label>
                <input
                  type="text"
                  value={unit}
                  onChange={(e) => setUnit(e.target.value.toUpperCase())}
                  placeholder="PCS, KG, NOS"
                  className="w-full bg-zinc-950 border border-zinc-700 text-white p-2.5 rounded-lg text-sm font-mono outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Standard Rate (₹)</label>
                <input
                  type="number"
                  value={price}
                  onChange={(e) => setPrice(Number(e.target.value))}
                  placeholder="0.00"
                  className="w-full bg-zinc-950 border border-zinc-700 text-white p-2.5 rounded-lg text-sm font-mono outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setIsAltCOpen(false)}
                className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-gray-300 rounded-lg text-xs font-medium transition-colors"
              >
                Cancel (Esc)
              </button>
              <button
                type="submit"
                disabled={saving}
                className="px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold shadow-md transition-colors"
              >
                {saving ? "Creating..." : "Save & Auto-Select (Ctrl+A)"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
