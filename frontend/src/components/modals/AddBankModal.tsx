"use client";
import React, { useState } from "react";
import axios from "axios";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken } from "@/utils/auth";
import { useToast } from "@/context/ToastContext";
import { X, Landmark, Check } from "lucide-react";

interface AddBankModalProps {
  isOpen: boolean;
  onClose: () => void;
  companyId: string;
  onSuccess: (newLedger: any) => void;
}

export default function AddBankModal({
  isOpen,
  onClose,
  companyId,
  onSuccess,
}: AddBankModalProps) {
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);

  const [bankName, setBankName] = useState("");
  const [accountNumber, setAccountNumber] = useState("");
  const [ifscCode, setIfscCode] = useState("");
  const [openingBalance, setOpeningBalance] = useState("");

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!bankName.trim()) {
      toast.warning("Bank account name is required.");
      return;
    }
    if (!companyId) {
      toast.error("Company information missing.");
      return;
    }

    setSaving(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      // Compile helpful name if account number is provided (e.g., "HDFC Bank - A/c 5020001234")
      let ledgerDisplayName = bankName.trim();
      if (accountNumber.trim() && !ledgerDisplayName.includes(accountNumber.trim().slice(-4))) {
        ledgerDisplayName += ` (A/c ...${accountNumber.trim().slice(-4)})`;
      }

      const payload = {
        name: ledgerDisplayName,
        group_name: "Bank Accounts",
        ledger_type: "BANK",
        opening_balance: parseFloat(openingBalance || "0") || 0,
        opening_balance_type: "DEBIT",
      };

      const res = await axios.post(`${API_BASE_URL}/api/v1/ledgers/${companyId}/`, payload, { headers });

      if (res.data.success) {
        toast.success(`Bank Account '${ledgerDisplayName}' created successfully!`);
        onSuccess(res.data.data);
        handleClose();
      } else {
        toast.error("Failed to create bank ledger", res.data.error);
      }
    } catch (err: any) {
      toast.error("Error creating bank ledger", err.response?.data?.error || err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleClose = () => {
    setBankName("");
    setAccountNumber("");
    setIfscCode("");
    setOpeningBalance("");
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="bg-card border border-border w-full max-w-md rounded-2xl shadow-2xl overflow-hidden animate-in zoom-in-95 duration-150">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-muted/30">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-500/10 text-blue-400 flex items-center justify-center">
              <Landmark className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-foreground text-base">Add New Bank Account</h3>
              <p className="text-xs text-muted-foreground">Creates a Bank Account ledger in Chart of Accounts</p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
              Bank / Account Name *
            </label>
            <input
              type="text"
              required
              autoFocus
              value={bankName}
              onChange={(e) => setBankName(e.target.value)}
              placeholder="e.g. HDFC Bank Current A/c, State Bank of India"
              className="w-full bg-muted/50 border border-input text-foreground px-3.5 py-2.5 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none transition-all"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                Account Number
              </label>
              <input
                type="text"
                value={accountNumber}
                onChange={(e) => setAccountNumber(e.target.value)}
                placeholder="e.g. 50200012345678"
                className="w-full bg-muted/50 border border-input text-foreground px-3 py-2 rounded-lg text-sm font-mono focus:ring-2 focus:ring-blue-500 outline-none transition-all"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                IFSC Code
              </label>
              <input
                type="text"
                value={ifscCode}
                onChange={(e) => setIfscCode(e.target.value.toUpperCase())}
                placeholder="e.g. HDFC0001234"
                className="w-full bg-muted/50 border border-input text-foreground px-3 py-2 rounded-lg text-sm font-mono uppercase focus:ring-2 focus:ring-blue-500 outline-none transition-all"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
              Opening Balance (₹)
            </label>
            <input
              type="number"
              step="0.01"
              value={openingBalance}
              onChange={(e) => setOpeningBalance(e.target.value)}
              placeholder="0.00"
              className="w-full bg-muted/50 border border-input text-foreground px-3.5 py-2.5 rounded-lg text-sm font-mono tabular-nums focus:ring-2 focus:ring-blue-500 outline-none transition-all"
            />
            <span className="text-[11px] text-muted-foreground mt-1 block">
              Leave blank or 0.00 if opening balance will be set later
            </span>
          </div>

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-border">
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-2 text-sm rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving || !bankName.trim()}
              className="px-5 py-2 text-sm font-semibold rounded-lg bg-blue-600 hover:bg-blue-700 text-foreground transition-all flex items-center gap-1.5 shadow cursor-pointer disabled:opacity-50"
            >
              {saving ? "Saving..." : (
                <>
                  <Check className="w-4 h-4" />
                  <span>Create Bank Account</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
