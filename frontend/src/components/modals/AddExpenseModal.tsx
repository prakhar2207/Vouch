"use client";
import React, { useState } from "react";
import axios from "axios";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken } from "@/utils/auth";
import { useToast } from "@/context/ToastContext";
import { X, Receipt, Check, Sparkles } from "lucide-react";

interface AddExpenseModalProps {
  isOpen: boolean;
  onClose: () => void;
  companyId: string;
  onSuccess: (newLedger: any) => void;
}

const COMMON_EXPENSES = [
  { name: "Freight & Cartage", group: "Direct Expenses" },
  { name: "Shop / Office Rent", group: "Indirect Expenses" },
  { name: "Electricity & Utilities", group: "Indirect Expenses" },
  { name: "Salaries & Wages", group: "Indirect Expenses" },
  { name: "Tea & Refreshments", group: "Indirect Expenses" },
  { name: "Printing & Stationery", group: "Indirect Expenses" },
  { name: "Repairs & Maintenance", group: "Indirect Expenses" },
  { name: "Bank Charges", group: "Indirect Expenses" },
];

export default function AddExpenseModal({
  isOpen,
  onClose,
  companyId,
  onSuccess,
}: AddExpenseModalProps) {
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);

  const [expenseName, setExpenseName] = useState("");
  const [expenseGroup, setExpenseGroup] = useState("Indirect Expenses");

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!expenseName.trim()) {
      toast.warning("Expense name is required.");
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

      const payload = {
        name: expenseName.trim(),
        group_name: expenseGroup,
        ledger_type: "EXPENSE",
        opening_balance: 0,
        opening_balance_type: "DEBIT",
      };

      const res = await axios.post(`${API_BASE_URL}/api/v1/ledgers/${companyId}/`, payload, { headers });

      if (res.data.success) {
        toast.success(`Expense '${expenseName.trim()}' added successfully!`);
        onSuccess(res.data.data);
        handleClose();
      } else {
        toast.error("Failed to create expense ledger", res.data.error);
      }
    } catch (err: any) {
      toast.error("Error creating expense ledger", err.response?.data?.error || err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleSelectPreset = (preset: { name: string; group: string }) => {
    setExpenseName(preset.name);
    setExpenseGroup(preset.group);
  };

  const handleClose = () => {
    setExpenseName("");
    setExpenseGroup("Indirect Expenses");
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="bg-card border border-border w-full max-w-md rounded-2xl shadow-2xl overflow-hidden animate-in zoom-in-95 duration-150">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-muted/30">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-amber-500/10 text-amber-400 flex items-center justify-center">
              <Receipt className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-foreground text-base">Add New Expense Account</h3>
              <p className="text-xs text-muted-foreground">Creates an Expense ledger for payments (Rent, Freight, etc.)</p>
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
          
          {/* Quick Presets */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-amber-400" />
              <span>Quick Suggestions</span>
            </label>
            <div className="flex flex-wrap gap-1.5">
              {COMMON_EXPENSES.map((p) => (
                <button
                  key={p.name}
                  type="button"
                  onClick={() => handleSelectPreset(p)}
                  className={`text-xs px-2.5 py-1 rounded-lg border transition-all cursor-pointer ${
                    expenseName === p.name
                      ? "bg-amber-500/20 text-amber-300 border-amber-500/40 font-semibold"
                      : "bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground border-input"
                  }`}
                >
                  {p.name}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
              Expense Account Name *
            </label>
            <input
              type="text"
              required
              autoFocus
              value={expenseName}
              onChange={(e) => setExpenseName(e.target.value)}
              placeholder="e.g. Shop Rent, Freight Charges, Courier"
              className="w-full bg-muted/50 border border-input text-foreground px-3.5 py-2.5 rounded-lg text-sm focus:ring-2 focus:ring-amber-500 outline-none transition-all"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
              Expense Classification *
            </label>
            <div className="grid grid-cols-2 gap-2">
              {[
                { id: "Indirect Expenses", title: "Indirect Expense", desc: "Rent, Electricity, Office, Salary" },
                { id: "Direct Expenses", title: "Direct Expense", desc: "Freight, Cartage, Factory, Carriage" },
              ].map((g) => {
                const isSelected = expenseGroup === g.id;
                return (
                  <button
                    key={g.id}
                    type="button"
                    onClick={() => setExpenseGroup(g.id)}
                    className={`p-3 rounded-xl border text-left transition-all cursor-pointer ${
                      isSelected
                        ? "bg-amber-500/10 border-amber-500 ring-1 ring-amber-500 text-foreground"
                        : "bg-muted/30 border-input text-muted-foreground hover:bg-muted/60"
                    }`}
                  >
                    <p className="text-xs font-bold">{g.title}</p>
                    <p className="text-[10px] text-muted-foreground mt-0.5">{g.desc}</p>
                  </button>
                );
              })}
            </div>
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
              disabled={saving || !expenseName.trim()}
              className="px-5 py-2 text-sm font-semibold rounded-lg bg-amber-600 hover:bg-amber-700 text-foreground transition-all flex items-center gap-1.5 shadow cursor-pointer disabled:opacity-50"
            >
              {saving ? "Saving..." : (
                <>
                  <Check className="w-4 h-4" />
                  <span>Create Expense</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
