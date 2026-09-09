"use client";
import React, { useState, useEffect } from "react";
import axios from "axios";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken } from "@/utils/auth";
import { useToast } from "@/context/ToastContext";
import SearchableSelect, { SearchableOption } from "@/components/SearchableSelect";
import AddBankModal from "@/components/modals/AddBankModal";
import AddExpenseModal from "@/components/modals/AddExpenseModal";
import { 
  X, 
  Check, 
  ArrowDownLeft, 
  ArrowUpRight, 
  Banknote, 
  Landmark, 
  FileText, 
  QrCode, 
  CreditCard, 
  Zap, 
  Send,
  Plus,
  Hash
} from "lucide-react";

type PaymentMode = 'CASH' | 'CHEQUE' | 'NEFT' | 'RTGS' | 'IMPS' | 'UPI' | 'BANK_TRANSFER';

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
  const [companyId, setCompanyId] = useState("");
  const [ledgers, setLedgers] = useState<any[]>([]);

  const [partyLedgerId, setPartyLedgerId] = useState("");
  const [paymentLedgerId, setPaymentLedgerId] = useState("");
  const [amount, setAmount] = useState("");
  const [voucherDate, setVoucherDate] = useState("");
  const [narration, setNarration] = useState("");
  const [referenceNumber, setReferenceNumber] = useState("");

  const [paymentMode, setPaymentMode] = useState<PaymentMode>("CASH");
  const [isAddBankModalOpen, setIsAddBankModalOpen] = useState(false);
  const [isAddExpenseModalOpen, setIsAddExpenseModalOpen] = useState(false);

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
        setCompanyId(cid);
        const ledgersRes = await axios.get(`${API_BASE_URL}/api/v1/ledgers/${cid}/`, { headers });
        setLedgers(ledgersRes.data.data || []);
      }

      // 2. Fetch specific voucher details
      const vRes = await axios.get(`${API_BASE_URL}/api/vouchers/${voucher.id}/`, { headers });
      if (vRes.data.success && vRes.data.data) {
        const d = vRes.data.data;
        setVoucherDate(d.date || voucher.date || "");
        setAmount(String(d.total_amount || voucher.total_amount || ""));
        setNarration(d.narration || voucher.narration || "");
        setReferenceNumber(d.reference_number || voucher.reference_number || "");
        setPartyLedgerId(d.party_ledger_id || "");
        setPaymentLedgerId(d.payment_ledger_id || "");

        // Determine initial payment mode based on reference or payment ledger
        const ref = (d.reference_number || voucher.reference_number || "").toUpperCase();
        if (ref.startsWith("CHQ") || ref.startsWith("CHEQUE")) {
          setPaymentMode("CHEQUE");
        } else if (ref.startsWith("NEFT")) {
          setPaymentMode("NEFT");
        } else if (ref.startsWith("RTGS")) {
          setPaymentMode("RTGS");
        } else if (ref.startsWith("IMPS")) {
          setPaymentMode("IMPS");
        } else if (ref.startsWith("UPI")) {
          setPaymentMode("UPI");
        } else if (d.payment_ledger_name?.toLowerCase().includes("bank")) {
          setPaymentMode("BANK_TRANSFER");
        } else {
          setPaymentMode("CASH");
        }
      } else {
        setVoucherDate(voucher.date || "");
        setAmount(String(voucher.total_amount || ""));
        setNarration(voucher.narration || "");
        setReferenceNumber(voucher.reference_number || "");
      }
    } catch (err: any) {
      console.error(err);
      toast.error("Failed to load voucher details", err.response?.data?.error || err.message);
    } finally {
      setLoading(false);
    }
  };

  // Parties & Expenses
  const partyLedgers = ledgers.filter((l: any) => {
    const grp = (l.group || "").toLowerCase();
    const ltype = (l.ledger_type || "").toUpperCase();
    const nature = (l.nature || "").toUpperCase();
    if (voucherType === "RECEIPT") {
      return grp.includes("debtor") || ltype === "CUSTOMER" || grp.includes("customer") || grp.includes("income") || nature === "INCOME";
    } else {
      return grp.includes("creditor") || ltype === "SUPPLIER" || grp.includes("supplier") || grp.includes("expense") || nature === "EXPENSE" || ltype === "EXPENSE";
    }
  });

  const effectivePartyLedgers = partyLedgers.length > 0
    ? partyLedgers
    : ledgers.filter((l: any) => (l.group || "").includes("Debtor") || (l.group || "").includes("Creditor") || (l.group || "").includes("Expense"));

  const partyOptions: SearchableOption[] = effectivePartyLedgers.map((l: any) => {
    const isExp = (l.group || "").toLowerCase().includes("expense") || (l.nature || "").toUpperCase() === "EXPENSE";
    return {
      id: l.id,
      name: l.name,
      group: l.group,
      balance: l.current_balance,
      balanceType: l.opening_balance_type === "DEBIT" ? "Dr" : "Cr",
      subtitle: isExp ? (l.group || "Expense Account") : (l.gstin ? `GSTIN: ${l.gstin}` : undefined),
    };
  });

  const handleExpenseCreated = (newExpense: any) => {
    setLedgers((prev) => [...prev, newExpense]);
    setPartyLedgerId(newExpense.id);
  };

  // Cash vs Bank Ledgers
  const cashLedgers = ledgers.filter((l: any) =>
    l.group === "Cash-in-Hand" || l.ledger_type === "CASH" || l.name.toLowerCase().includes("cash")
  );

  const bankLedgers = ledgers.filter((l: any) =>
    (l.group || "").toLowerCase().includes("bank") || l.ledger_type === "BANK"
  );

  const currentAccounts = paymentMode === "CASH" ? cashLedgers : bankLedgers;

  const accountOptions: SearchableOption[] = currentAccounts.map((l: any) => ({
    id: l.id,
    name: l.name,
    group: l.group,
    balance: l.current_balance,
    balanceType: l.opening_balance_type === "DEBIT" ? "Dr" : "Cr",
  }));

  const handlePaymentModeChange = (mode: PaymentMode) => {
    setPaymentMode(mode);
    if (mode === "CASH") {
      const defaultCash = cashLedgers[0];
      if (defaultCash) setPaymentLedgerId(defaultCash.id);
    } else {
      const isCurrentCash = cashLedgers.some((l: any) => l.id === paymentLedgerId);
      if (isCurrentCash || !paymentLedgerId) {
        if (bankLedgers.length > 0) {
          setPaymentLedgerId(bankLedgers[0].id);
        } else {
          setPaymentLedgerId("");
        }
      }
    }
  };

  const handleBankCreated = (newBank: any) => {
    setLedgers((prev) => [...prev, newBank]);
    setPaymentLedgerId(newBank.id);
  };

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
        reference_number: referenceNumber.trim(),
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
        className="bg-card text-card-foreground border border-border rounded-2xl shadow-2xl w-full max-w-xl overflow-hidden animate-in zoom-in-95 duration-200 flex flex-col max-h-[90vh]"
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
          <form onSubmit={handleSave} className="p-5 space-y-4 overflow-y-auto">
            {/* Party Selection */}
            <div>
              <div className="flex justify-between items-center mb-1.5">
                <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {voucherType === "RECEIPT" ? "Customer / Income (Received From) *" : "Paid To / Account (Supplier or Expense) *"}
                </label>
                {voucherType === "PAYMENT" && (
                  <button
                    type="button"
                    onClick={() => setIsAddExpenseModalOpen(true)}
                    className="text-amber-500 hover:text-amber-400 text-xs font-semibold flex items-center gap-1 cursor-pointer"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Add Expense</span>
                  </button>
                )}
              </div>
              <SearchableSelect
                value={partyLedgerId}
                onChange={(val) => setPartyLedgerId(val)}
                options={partyOptions}
                placeholder={voucherType === "RECEIPT" ? "-- Select Customer or Income --" : "-- Select Supplier or Expense Account --"}
                searchPlaceholder="Search supplier or expense (e.g. Rent, Freight)..."
                required
                onAddNew={voucherType === "PAYMENT" ? () => setIsAddExpenseModalOpen(true) : undefined}
                addNewText="+ Add Expense Account"
              />
            </div>

            {/* Payment Mode Selector */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                Mode of Payment *
              </label>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5">
                {[
                  { mode: "CASH" as PaymentMode, label: "Cash", icon: Banknote },
                  { mode: "CHEQUE" as PaymentMode, label: "Cheque / DD", icon: FileText },
                  { mode: "NEFT" as PaymentMode, label: "NEFT", icon: Landmark },
                  { mode: "RTGS" as PaymentMode, label: "RTGS", icon: Zap },
                  { mode: "IMPS" as PaymentMode, label: "IMPS", icon: Send },
                  { mode: "UPI" as PaymentMode, label: "UPI / QR", icon: QrCode },
                  { mode: "BANK_TRANSFER" as PaymentMode, label: "NetBanking", icon: CreditCard },
                ].map(({ mode, label, icon: Icon }) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => handlePaymentModeChange(mode)}
                    className={`px-2.5 py-2 rounded-lg border text-xs font-semibold flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
                      paymentMode === mode
                        ? "bg-blue-600 text-foreground border-blue-500 shadow-sm ring-1 ring-blue-500"
                        : "bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground border-input"
                    }`}
                  >
                    <Icon className="w-3.5 h-3.5 shrink-0" />
                    <span className="truncate">{label}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Cash / Bank Account Selection */}
            <div>
              <div className="flex justify-between items-center mb-1.5">
                <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {paymentMode === "CASH"
                    ? (voucherType === "RECEIPT" ? "Received Into (Cash Account) *" : "Paid From (Cash Account) *")
                    : (voucherType === "RECEIPT" ? "Received Into (Bank Account) *" : "Paid From (Bank Account) *")}
                </label>
                {paymentMode !== "CASH" && (
                  <button
                    type="button"
                    onClick={() => setIsAddBankModalOpen(true)}
                    className="text-blue-500 hover:text-blue-400 text-xs font-semibold flex items-center gap-1 cursor-pointer"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Add Bank</span>
                  </button>
                )}
              </div>

              {paymentMode !== "CASH" && bankLedgers.length === 0 ? (
                <div className="p-3 rounded-lg border border-dashed border-border bg-muted/20 text-center space-y-1.5">
                  <p className="text-xs font-medium text-foreground">No Bank Account ledger found</p>
                  <button
                    type="button"
                    onClick={() => setIsAddBankModalOpen(true)}
                    className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold rounded bg-blue-600 text-foreground hover:bg-blue-700 transition-colors cursor-pointer"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Create Bank Account</span>
                  </button>
                </div>
              ) : (
                <SearchableSelect
                  value={paymentLedgerId}
                  onChange={(val) => setPaymentLedgerId(val)}
                  options={accountOptions}
                  placeholder={paymentMode === "CASH" ? "-- Select Cash Account --" : "-- Select Bank Account --"}
                  searchPlaceholder="Search cash or bank ledger..."
                  required
                  onAddNew={paymentMode !== "CASH" ? () => setIsAddBankModalOpen(true) : undefined}
                  addNewText="+ Add Bank Account"
                />
              )}
            </div>

            {/* Reference / Transaction Number */}
            {paymentMode !== "CASH" && (
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5 flex items-center gap-1">
                  <Hash className="w-3.5 h-3.5 text-blue-400" />
                  <span>
                    {paymentMode === "CHEQUE"
                      ? "Cheque / DD Number *"
                      : paymentMode === "UPI"
                      ? "UPI Ref / UTR No. *"
                      : `${paymentMode} UTR / Transaction No. *`}
                  </span>
                </label>
                <input
                  type="text"
                  value={referenceNumber}
                  onChange={(e) => setReferenceNumber(e.target.value)}
                  placeholder={
                    paymentMode === "CHEQUE"
                      ? "e.g. Chq# 004521"
                      : paymentMode === "UPI"
                      ? "e.g. UPI: 425189201928"
                      : "e.g. UTRB260909123456"
                  }
                  className="w-full bg-background border border-border text-foreground px-3 py-2 rounded-xl focus:border-primary focus:ring-1 focus:ring-primary outline-none font-mono text-sm"
                />
              </div>
            )}

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
                <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                  Voucher Date *
                </label>
                <input
                  required
                  type="date"
                  value={voucherDate}
                  onChange={(e) => setVoucherDate(e.target.value)}
                  className="w-full bg-background border border-border text-foreground p-2.5 rounded-xl focus:border-primary focus:ring-1 focus:ring-primary outline-none font-mono text-sm min-h-[44px]"
                />
              </div>
            </div>

            {/* Narration */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                Narration / Reference Notes
              </label>
              <textarea
                rows={2}
                value={narration}
                onChange={(e) => setNarration(e.target.value)}
                placeholder="Optional notes or reference..."
                className="w-full bg-background border border-border text-foreground p-2.5 rounded-xl focus:border-primary focus:ring-1 focus:ring-primary outline-none text-sm resize-none"
              />
            </div>

            {/* Impact Preview */}
            <div
              className={`p-3.5 rounded-xl border ${
                voucherType === "RECEIPT"
                  ? "bg-green-500/5 border-green-500/20"
                  : "bg-red-500/5 border-red-500/20"
              }`}
            >
              <p className="text-xs font-medium text-foreground">Accounting Impact Preview:</p>
              <div className="mt-1 text-xs font-mono flex flex-col gap-0.5 text-muted-foreground">
                {voucherType === "RECEIPT" ? (
                  <>
                    <p>
                      <span className="text-green-500 font-bold">Dr</span> {paymentMode === "CASH" ? "Cash" : "Bank Account"} (+₹{amount || "0.00"})
                    </p>
                    <p>
                      <span className="text-blue-400 font-bold">Cr</span> Customer Ledger (-₹{amount || "0.00"})
                    </p>
                  </>
                ) : (
                  <>
                    <p>
                      <span className="text-blue-400 font-bold">Dr</span> Supplier Ledger (-₹{amount || "0.00"})
                    </p>
                    <p>
                      <span className="text-red-500 font-bold">Cr</span> {paymentMode === "CASH" ? "Cash" : "Bank Account"} (-₹{amount || "0.00"})
                    </p>
                  </>
                )}
              </div>
            </div>

            {/* Footer Buttons */}
            <div className="flex items-center justify-end gap-3 pt-3 border-t border-border">
              <button
                type="button"
                onClick={onClose}
                disabled={saving}
                className="px-4 py-2 text-sm rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer min-h-[38px]"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className={`px-5 py-2 text-sm font-semibold rounded-xl text-foreground flex items-center gap-2 shadow-md transition-all cursor-pointer min-h-[38px] ${
                  voucherType === "RECEIPT"
                    ? "bg-green-600 hover:bg-green-700"
                    : "bg-red-600 hover:bg-red-700"
                } disabled:opacity-50`}
              >
                {saving ? (
                  "Updating..."
                ) : (
                  <>
                    <Check className="w-4 h-4" />
                    <span>Update & Recalculate</span>
                  </>
                )}
              </button>
            </div>
          </form>
        )}

        {/* Add Bank Modal */}
        <AddBankModal
          isOpen={isAddBankModalOpen}
          onClose={() => setIsAddBankModalOpen(false)}
          companyId={companyId}
          onSuccess={handleBankCreated}
        />

        {/* Add Expense Modal */}
        <AddExpenseModal
          isOpen={isAddExpenseModalOpen}
          onClose={() => setIsAddExpenseModalOpen(false)}
          companyId={companyId}
          onSuccess={handleExpenseCreated}
        />
      </div>
    </div>
  );
}
