"use client";
import React, { useState, useEffect } from "react";
import axios from "axios";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken } from "@/utils/auth";
import { useToast } from "@/context/ToastContext";
import { X, Check, Calendar, ArrowDownLeft, ArrowUpRight, FileText } from "lucide-react";

interface EditPaymentReceiptModalProps {
  isOpen: boolean;
  onClose: () => void;
  voucher: any;
  onUpdateSuccess: () => void;
}

export default function EditPaymentReceiptModal({
  isOpen,
  onClose,
  voucher,
  onUpdateSuccess,
}: EditPaymentReceiptModalProps) {
  const { toast } = useToast();

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [ledgers, setLedgers] = useState<any[]>([]);

  const [partyLedgerId, setPartyLedgerId] = useState("");
  const [paymentLedgerId, setPaymentLedgerId] = useState("");
  const [amount, setAmount] = useState("");
  const [voucherDate, setVoucherDate] = useState("");
  const [narration, setNarration] = useState("");

  const voucherType: "RECEIPT" | "PAYMENT" = voucher?.type || "RECEIPT";
  const voucherNumber = voucher?.voucher_number || "";

  useEffect(() => {
    if (isOpen && voucher?.id) {
      loadDetailsAndLedgers();
    }
  }, [isOpen, voucher?.id]);

  const loadDetailsAndLedgers = async () => {
    setLoading(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      // 1. Fetch company and ledgers
      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const cid = compRes.data.data[0]?.id;
      if (cid) {
        const ledgersRes = await axios.get(`${API_BASE_URL}/api/v1/ledgers/${cid}/`, { headers });
        setLedgers(ledgersRes.data.data || []);
      }

      // 2. Fetch specific voucher details to get payment_ledger_id
      const vRes = await axios.get(`${API_BASE_URL}/api/vouchers/${voucher.id}/`, { headers });
      if (vRes.data.success && vRes.data.data) {
        const d = vRes.data.data;
        setVoucherDate(d.date || voucher.date || "");
        setAmount(String(d.total_amount || voucher.total_amount || ""));
        setNarration(d.narration || voucher.narration || "");
        setPartyLedgerId(d.party_ledger_id || "");
        setPaymentLedgerId(d.payment_ledger_id || "");
      } else {
        setVoucherDate(voucher.date || "");
        setAmount(String(voucher.total_amount || ""));
        setNarration(voucher.narration || "");
      }
    } catch (err: any) {
      console.error(err);
      toast.error("Failed to load voucher details", err.response?.data?.error || err.message);
    } finally {
      setLoading(false);
    }
  };

  const partyLedgers = ledgers.filter((l) => {
    const grp = l.group_name || l.group || "";
    return grp.includes("Debtor") || grp.includes("Creditor");
  });

  const cashBankLedgers = ledgers.filter((l) => {
    const grp = l.group_name || l.group || "";
    return grp.includes("Cash") || grp.includes("Bank");
  });

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!partyLedgerId || !paymentLedgerId || !amount || parseFloat(amount) <= 0) {
      toast.warning("Please fill all required fields with a valid amount.");
      return;
    }

    setSaving(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      const payload = {
        voucher_date: voucherDate,
        amount: parseFloat(amount),
        party_ledger_id: partyLedgerId,
        payment_ledger_id: paymentLedgerId,
        narration: narration.trim(),
      };

      const res = await axios.patch(`${API_BASE_URL}/api/vouchers/${voucher.id}/`, payload, { headers });

      if (res.data.success) {
        toast.success(
          `${voucherType === "RECEIPT" ? "Receipt" : "Payment"} Updated`,
          `Voucher #${voucherNumber} updated and ledger balances recalculated.`
        );
        onUpdateSuccess();
        onClose();
      } else {
        toast.error("Update failed", res.data.error);
      }
    } catch (err: any) {
      toast.error("Error updating voucher", err.response?.data?.error || err.message);
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div
        className="bg-card text-card-foreground border border-border rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden animate-in zoom-in-95 duration-200 flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-5 border-b border-border flex items-center justify-between bg-muted/40">
          <div className="flex items-center gap-3">
            <div
              className={`w-10 h-10 rounded-xl flex items-center justify-center font-bold shadow-sm ${
                voucherType === "RECEIPT"
                  ? "bg-green-500/15 text-green-500 border border-green-500/30"
                  : "bg-red-500/15 text-red-500 border border-red-500/30"
              }`}
            >
              {voucherType === "RECEIPT" ? (
                <ArrowDownLeft className="w-5 h-5" />
              ) : (
                <ArrowUpRight className="w-5 h-5" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base sm:text-lg font-bold text-foreground">
                  Edit {voucherType === "RECEIPT" ? "Receipt" : "Payment"}
                </h2>
                <span className="font-mono text-xs px-2 py-0.5 rounded-md bg-muted text-muted-foreground border border-border font-semibold">
                  {voucherNumber}
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Modifications will automatically roll back and recalculate ledger balances.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content / Form */}
        {loading ? (
          <div className="p-12 text-center text-sm text-muted-foreground">
            Loading voucher details...
          </div>
        ) : (
          <form onSubmit={handleSave} className="p-5 space-y-4">
            {/* Party Selection */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                {voucherType === "RECEIPT" ? "Customer (Received From) *" : "Supplier (Paid To) *"}
              </label>
              <select
                required
                value={partyLedgerId}
                onChange={(e) => setPartyLedgerId(e.target.value)}
                className="w-full bg-background border border-border text-foreground text-sm p-2.5 rounded-xl focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all font-medium"
              >
                <option value="">-- Select Party --</option>
                {partyLedgers.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name} {l.group ? `(${l.group})` : ""}
                  </option>
                ))}
              </select>
            </div>

            {/* Cash / Bank Selection */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                {voucherType === "RECEIPT" ? "Received Into (Cash / Bank) *" : "Paid From (Cash / Bank) *"}
              </label>
              <select
                required
                value={paymentLedgerId}
                onChange={(e) => setPaymentLedgerId(e.target.value)}
                className="w-full bg-background border border-border text-foreground text-sm p-2.5 rounded-xl focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all font-medium"
              >
                <option value="">-- Select Cash / Bank Account --</option>
                {cashBankLedgers.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Amount & Date Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                  Amount (₹) *
                </label>
                <input
                  required
                  type="number"
                  step="0.01"
                  min="0.01"
                  placeholder="0.00"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  className="w-full bg-background border border-border text-foreground p-2.5 rounded-xl focus:border-primary focus:ring-1 focus:ring-primary outline-none font-mono tabular-nums text-lg font-bold text-right"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5 flex items-center gap-1">
                  <Calendar className="w-3.5 h-3.5" />
                  <span>Voucher Date *</span>
                </label>
                <input
                  required
                  type="date"
                  value={voucherDate}
                  onChange={(e) => setVoucherDate(e.target.value)}
                  className="w-full bg-background border border-border text-foreground p-2.5 rounded-xl focus:border-primary focus:ring-1 focus:ring-primary outline-none font-mono text-sm font-semibold"
                />
              </div>
            </div>

            {/* Narration */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5 flex items-center gap-1">
                <FileText className="w-3.5 h-3.5" />
                <span>Narration / Notes</span>
              </label>
              <textarea
                rows={2}
                placeholder="Remarks, check/ref number, payment notes..."
                value={narration}
                onChange={(e) => setNarration(e.target.value)}
                className="w-full bg-background border border-border text-foreground text-xs p-2.5 rounded-xl focus:border-primary focus:ring-1 focus:ring-primary outline-none resize-none"
              />
            </div>

            {/* Realtime Impact Preview Card */}
            {amount && parseFloat(amount) > 0 && (
              <div
                className={`rounded-xl p-3.5 border ${
                  voucherType === "RECEIPT"
                    ? "bg-green-500/10 border-green-500/20 text-green-400"
                    : "bg-red-500/10 border-red-500/20 text-red-400"
                }`}
              >
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold uppercase tracking-wider">
                    {voucherType === "RECEIPT" ? "Debit Cash/Bank → Credit Party" : "Debit Party → Credit Cash/Bank"}
                  </span>
                  <span className="font-mono tabular-nums font-bold text-sm">
                    ₹{parseFloat(amount).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </span>
                </div>
              </div>
            )}

            {/* Modal Footer */}
            <div className="pt-3 border-t border-border flex items-center justify-end gap-2.5">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground hover:bg-muted rounded-xl transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className="px-5 py-2.5 bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 rounded-xl text-xs font-bold shadow-md shadow-primary/20 transition-all flex items-center gap-1.5 cursor-pointer"
              >
                <Check className="w-4 h-4" />
                <span>{saving ? "Updating..." : "Save Changes"}</span>
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
