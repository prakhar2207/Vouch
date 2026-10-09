"use client";

import React, { useState, useEffect } from "react";
import SearchableSelect, { SearchableOption } from "@/components/SearchableSelect";
import {
  X,
  Check,
  Sparkles,
  Receipt,
  CreditCard,
  Wallet,
  Building2,
  CornerDownRight,
  Maximize2,
  ShieldCheck,
} from "lucide-react";
import { BankTransactionItem, BankingActionType } from "./types";

interface InlineMatchTrayProps {
  tx: BankTransactionItem;
  isOpen: boolean;
  onClose: () => void;
  partyOptions: SearchableOption[];
  expenseOptions: SearchableOption[];
  contraOptions: SearchableOption[];
  sisterCompanies?: { id: string; name: string }[];
  onResolve: (actionType: BankingActionType, payload: any) => Promise<void>;
  isResolving: boolean;
  onOpenAdvancedModal?: () => void;
  initialActionType?: BankingActionType;
}

export default function InlineMatchTray({
  tx,
  isOpen,
  onClose,
  partyOptions,
  expenseOptions,
  contraOptions,
  sisterCompanies = [],
  onResolve,
  isResolving,
  onOpenAdvancedModal,
  initialActionType,
}: InlineMatchTrayProps) {
  const isCredit = parseFloat(tx.credit_amount) > 0;
  const isDebit = !isCredit;
  const descLower = (tx.description || tx.normalized_narration || "").toLowerCase();

  const isLikelyExpense = isDebit && (
    descLower.includes("interest") ||
    descLower.includes("charge") ||
    descLower.includes("chg") ||
    descLower.includes("fee") ||
    descLower.includes("sms") ||
    descLower.includes("amc") ||
    descLower.includes("tax") ||
    descLower.includes("gst") ||
    descLower.includes("capitalized")
  );

  const isExpenseMatch =
    tx.matched_party?.ledger_type === "EXPENSE" ||
    (typeof tx.match_notes === "object" && (tx.match_notes as any)?.is_bank_expense);

  // Determine starting tab
  const defaultTab: BankingActionType = initialActionType
    ? initialActionType
    : isExpenseMatch || isLikelyExpense
    ? "RECORD_EXPENSE"
    : "RECORD_PAYMENT";

  const [activeAction, setActiveAction] = useState<BankingActionType>(defaultTab);
  const [selectedPartyId, setSelectedPartyId] = useState<string>(
    tx.matched_party && !isExpenseMatch ? tx.matched_party.id : ""
  );
  const [selectedExpenseId, setSelectedExpenseId] = useState<string>("");
  const [selectedTransferId, setSelectedTransferId] = useState<string>("");
  const [selectedSisterCoId, setSelectedSisterCoId] = useState<string>(
    sisterCompanies.length > 0 ? sisterCompanies[0].id : ""
  );
  const [remarks, setRemarks] = useState<string>(tx.description || "");

  // Auto-populate smart expense account if likely expense
  useEffect(() => {
    if (isExpenseMatch && tx.matched_party) {
      setSelectedExpenseId(tx.matched_party.id);
    } else if (expenseOptions.length > 0 && !selectedExpenseId) {
      let matchedExpId = "";
      if (descLower.includes("interest")) {
        const intOpt = expenseOptions.find((l) => l.name.toLowerCase().includes("interest"));
        if (intOpt) matchedExpId = intOpt.id;
      }
      if (!matchedExpId && (descLower.includes("charge") || descLower.includes("chg") || descLower.includes("fee") || descLower.includes("sms"))) {
        const chgOpt = expenseOptions.find((l) =>
          l.name.toLowerCase().includes("charge") || l.name.toLowerCase().includes("fee")
        );
        if (chgOpt) matchedExpId = chgOpt.id;
      }
      if (!matchedExpId && expenseOptions.length > 0) {
        matchedExpId = expenseOptions[0].id;
      }
      if (matchedExpId) setSelectedExpenseId(matchedExpId);
    }
  }, [tx, expenseOptions, isExpenseMatch, descLower]);

  // Handle escape key to close tray
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const payload: any = {};

    if (activeAction === "RECORD_PAYMENT" || activeAction === "MATCH_PARTY") {
      if (!selectedPartyId) return;
      payload.party_id = selectedPartyId;
      payload.narration = remarks || tx.description;
    } else if (activeAction === "RECORD_EXPENSE") {
      if (!selectedExpenseId) return;
      payload.expense_ledger_id = selectedExpenseId;
      payload.narration = remarks || tx.description;
    } else if (activeAction === "RECORD_TRANSFER") {
      if (!selectedTransferId) return;
      payload.target_ledger_id = selectedTransferId;
      payload.transfer_ledger_id = selectedTransferId;
      payload.narration = remarks || tx.description;
    } else if (activeAction === "TRIANGULAR_SETTLEMENT") {
      if (!selectedSisterCoId) return;
      payload.target_company_id = selectedSisterCoId;
      if (selectedPartyId) payload.target_party_id = selectedPartyId;
      payload.narration = remarks || tx.description;
    } else if (activeAction === "OWNER_DRAWING") {
      payload.narration = remarks || "Proprietor / Partner Drawings";
    } else if (activeAction === "IGNORE") {
      payload.reason = remarks || "Ignored by user";
    }

    await onResolve(activeAction, payload);
  };

  // Quick pick expense options
  const quickPickExpenses = expenseOptions.filter((opt) => {
    const n = opt.name.toLowerCase();
    return (
      n.includes("charge") ||
      n.includes("interest") ||
      n.includes("fee") ||
      n.includes("sms") ||
      n.includes("tax") ||
      n.includes("gst") ||
      n.includes("rent")
    );
  }).slice(0, 6);

  return (
    <div className="border-t border-border/60 bg-muted/25 dark:bg-muted/15 rounded-b-2xl p-4 sm:p-5 mt-3 space-y-4 animate-in slide-in-from-top-2 duration-200">
      {/* Top Bar of the Tray: Mode Switcher Tabs + Close & Advanced Modal Actions */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2.5">
        <div className="flex items-center gap-1.5 p-1 bg-muted/60 dark:bg-muted/30 border border-border/50 rounded-xl overflow-x-auto">
          <button
            type="button"
            onClick={() => setActiveAction("RECORD_PAYMENT")}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 ${
              activeAction === "RECORD_PAYMENT" || activeAction === "MATCH_PARTY"
                ? "bg-card text-foreground shadow-xs border border-border/60"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {isCredit ? <Receipt className="w-3.5 h-3.5 text-emerald-500" /> : <CreditCard className="w-3.5 h-3.5 text-primary" />}
            <span>{isCredit ? "Customer Receipt" : "Supplier Payment"}</span>
          </button>

          {isDebit && (
            <button
              type="button"
              onClick={() => setActiveAction("RECORD_EXPENSE")}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 ${
                activeAction === "RECORD_EXPENSE"
                  ? "bg-card text-foreground shadow-xs border border-border/60"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Receipt className="w-3.5 h-3.5 text-amber-500" />
              <span>Expense / Bank Charges</span>
            </button>
          )}

          <button
            type="button"
            onClick={() => setActiveAction("RECORD_TRANSFER")}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 ${
              activeAction === "RECORD_TRANSFER"
                ? "bg-card text-foreground shadow-xs border border-border/60"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Wallet className="w-3.5 h-3.5 text-blue-500" />
            <span>Transfer / Contra</span>
          </button>

          {sisterCompanies.length > 0 && (
            <button
              type="button"
              onClick={() => setActiveAction("TRIANGULAR_SETTLEMENT")}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 ${
                activeAction === "TRIANGULAR_SETTLEMENT"
                  ? "bg-card text-indigo-500 shadow-xs border border-indigo-500/30"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Building2 className="w-3.5 h-3.5 text-indigo-400" />
              <span>Sister Entity</span>
            </button>
          )}

          {isDebit && (
            <button
              type="button"
              onClick={() => setActiveAction("OWNER_DRAWING")}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 ${
                activeAction === "OWNER_DRAWING"
                  ? "bg-card text-foreground shadow-xs border border-border/60"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <CornerDownRight className="w-3.5 h-3.5 text-rose-400" />
              <span>Drawing</span>
            </button>
          )}

          <button
            type="button"
            onClick={() => setActiveAction("IGNORE")}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer whitespace-nowrap ${
              activeAction === "IGNORE"
                ? "bg-card text-foreground shadow-xs border border-border/60"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <span>Skip</span>
          </button>
        </div>

        {/* Action controls: open in modal & close */}
        <div className="flex items-center gap-1.5 justify-end shrink-0">
          {onOpenAdvancedModal && (
            <button
              type="button"
              onClick={onOpenAdvancedModal}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
              title="Open full-screen modal"
            >
              <Maximize2 className="w-4 h-4" />
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
            title="Close tray (Esc)"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Main Drawer Form Body */}
      <form onSubmit={handleSubmit} className="space-y-3.5">
        {/* CASE 1: Party Payment / Receipt */}
        {(activeAction === "RECORD_PAYMENT" || activeAction === "MATCH_PARTY") && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-bold text-foreground">
                {isCredit ? "Select Customer Party:" : "Select Supplier Party:"}
              </label>
              <span className="text-[11px] text-muted-foreground">
                {partyOptions.length} registered parties
              </span>
            </div>

            <SearchableSelect
              value={selectedPartyId}
              onChange={setSelectedPartyId}
              options={partyOptions}
              placeholder={isCredit ? "-- Search Customer Name, Phone, GSTIN --" : "-- Search Supplier Name, Phone, GSTIN --"}
              searchPlaceholder="Type party name..."
            />

            <div className="flex items-start gap-2 p-2.5 rounded-xl bg-card border border-border/40 text-[11px] text-muted-foreground mt-2">
              <ShieldCheck className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-foreground">Automatic Double-Entry Allocation: </span>
                {isCredit
                  ? "Applies to oldest unpaid sales invoices (FIFO) with atomic concurrency row-locking. Any surplus remains as unadjusted customer advance credit."
                  : "Applies to oldest unpaid purchase bills (FIFO) with atomic concurrency row-locking. Any surplus remains as supplier advance debit."}
              </div>
            </div>
          </div>
        )}

        {/* CASE 2: Business Expense */}
        {activeAction === "RECORD_EXPENSE" && (
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-bold text-foreground">
                Select Expense Account (Bank Charges, Interest, Utilities):
              </label>
              <span className="text-[11px] text-muted-foreground">
                {expenseOptions.length} expense ledgers
              </span>
            </div>

            <SearchableSelect
              value={selectedExpenseId}
              onChange={setSelectedExpenseId}
              options={expenseOptions}
              placeholder="-- Select Expense Ledger --"
              searchPlaceholder="Search expense category..."
            />

            {/* Instant Quick-Pick Chips */}
            {quickPickExpenses.length > 0 && (
              <div className="space-y-1.5 pt-1">
                <div className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">
                  Quick Pick Frequent Charges:
                </div>
                <div className="flex items-center gap-1.5 flex-wrap">
                  {quickPickExpenses.map((opt) => (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => setSelectedExpenseId(opt.id)}
                      className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition-all cursor-pointer ${
                        selectedExpenseId === opt.id
                          ? "bg-primary text-primary-foreground border-primary font-bold shadow-xs scale-102"
                          : "bg-card border-border/60 text-foreground hover:bg-muted"
                      }`}
                    >
                      {opt.name}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* CASE 3: Transfer / Contra */}
        {activeAction === "RECORD_TRANSFER" && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-bold text-foreground">
                Target / Source Account (Bank or Cash):
              </label>
              <span className="text-[11px] text-muted-foreground">
                {contraOptions.length} available accounts
              </span>
            </div>

            <SearchableSelect
              value={selectedTransferId}
              onChange={setSelectedTransferId}
              options={contraOptions}
              placeholder="-- Select Destination / Source Bank or Cash --"
              searchPlaceholder="Search cash or bank ledger..."
            />
          </div>
        )}

        {/* CASE 4: Sister Entity Settlement */}
        {activeAction === "TRIANGULAR_SETTLEMENT" && (
          <div className="space-y-2.5">
            <label className="text-xs font-bold text-foreground block">
              Sister Entity (Cross-Entity Settlement):
            </label>
            <select
              value={selectedSisterCoId}
              onChange={(e) => setSelectedSisterCoId(e.target.value)}
              className="w-full px-3 py-2 bg-card border border-border/80 rounded-xl text-xs font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500/40 text-foreground"
            >
              {sisterCompanies.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>

            <div className="p-2.5 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-xs text-indigo-950 dark:text-indigo-200">
              <div className="font-semibold flex items-center gap-1.5 text-indigo-600 dark:text-indigo-400">
                <Sparkles className="w-3.5 h-3.5 shrink-0" />
                <span>Zero Drift Cross-Entity Voucher</span>
              </div>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                Automatically posts a voucher in this entity and a mirroring counter-voucher in {sisterCompanies.find((c) => c.id === selectedSisterCoId)?.name || "the sister business"}.
              </p>
            </div>
          </div>
        )}

        {/* CASE 5: Drawing */}
        {activeAction === "OWNER_DRAWING" && (
          <div className="p-3 rounded-xl bg-muted/40 border border-border/60 text-xs space-y-1">
            <div className="font-bold text-foreground">Proprietor / Partner Personal Drawing</div>
            <p className="text-[11px] text-muted-foreground">
              Debits Partner Capital / Drawings Account and credits Bank Account with no GST impact.
            </p>
          </div>
        )}

        {/* CASE 6: Ignore / Skip */}
        {activeAction === "IGNORE" && (
          <div className="space-y-2">
            <label className="text-xs font-bold text-foreground">Reason for Skipping:</label>
            <input
              type="text"
              value={remarks}
              onChange={(e) => setRemarks(e.target.value)}
              placeholder="e.g. Duplicate reversal, personal expense, unverified"
              className="w-full bg-card border border-border/70 rounded-xl px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
          </div>
        )}

        {/* Common Remarks Field (for all actions except ignore) */}
        {activeAction !== "IGNORE" && (
          <div className="space-y-1">
            <label className="text-[11px] font-medium text-muted-foreground">
              Narration / Voucher Remarks (Optional):
            </label>
            <input
              type="text"
              value={remarks}
              onChange={(e) => setRemarks(e.target.value)}
              placeholder="Remarks for accounting journal..."
              className="w-full bg-card border border-border/70 rounded-xl px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
          </div>
        )}

        {/* Drawer Action Footer Buttons */}
        <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-border/40">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-muted-foreground hover:text-foreground bg-card hover:bg-muted border border-border/60 transition-colors cursor-pointer"
          >
            Cancel
          </button>

          <button
            type="submit"
            disabled={
              isResolving ||
              ((activeAction === "RECORD_PAYMENT" || activeAction === "MATCH_PARTY") && !selectedPartyId) ||
              (activeAction === "RECORD_EXPENSE" && !selectedExpenseId) ||
              (activeAction === "RECORD_TRANSFER" && !selectedTransferId) ||
              (activeAction === "TRIANGULAR_SETTLEMENT" && !selectedSisterCoId)
            }
            className="px-5 py-2 rounded-xl text-xs font-bold text-primary-foreground bg-primary hover:bg-primary/90 transition-all cursor-pointer flex items-center gap-1.5 shadow-sm disabled:opacity-50 active:scale-98"
          >
            {isResolving ? (
              <>
                <div className="w-3.5 h-3.5 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin" />
                <span>Reconciling...</span>
              </>
            ) : (
              <>
                <Check className="w-3.5 h-3.5 stroke-[2.5]" />
                <span>Confirm & Reconcile</span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
