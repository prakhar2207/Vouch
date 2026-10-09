"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  ArrowUpRight,
  ArrowDownRight,
  ArrowLeftRight,
  Sparkles,
  EyeOff,
  MoreHorizontal,
  Check,
  CreditCard,
  Receipt,
  UserCheck,
  Building2,
  Wallet,
  CornerDownRight,
  ExternalLink,
  ChevronDown,
  Maximize2,
} from "lucide-react";
import { BankTransactionItem, BankingActionType } from "./types";
import { SearchableOption } from "@/components/SearchableSelect";
import InlineMatchTray from "./InlineMatchTray";

interface BankTransactionCardProps {
  tx: BankTransactionItem;
  idx: number;
  showDateHeader: boolean;
  onOpenActionModal: (tx: BankTransactionItem, type: BankingActionType) => void;
  onToggleDirection?: (tx: BankTransactionItem) => void;
  isTogglingDirection?: boolean;
  onExclude: (tx: BankTransactionItem) => void;
  onRestore: (tx: BankTransactionItem) => void;
  onViewVouchers?: () => void;
  partyOptions?: SearchableOption[];
  expenseOptions?: SearchableOption[];
  contraOptions?: SearchableOption[];
  sisterCompanies?: { id: string; name: string }[];
  onOneClickConfirm?: (tx: BankTransactionItem) => Promise<void> | void;
  onInlineResolve?: (tx: BankTransactionItem, actionType: BankingActionType, payload: any) => Promise<void> | void;
  isResolving?: boolean;
}

export default function BankTransactionCard({
  tx,
  idx,
  showDateHeader,
  onOpenActionModal,
  onToggleDirection,
  isTogglingDirection = false,
  onExclude,
  onRestore,
  onViewVouchers,
  partyOptions = [],
  expenseOptions = [],
  contraOptions = [],
  sisterCompanies = [],
  onOneClickConfirm,
  onInlineResolve,
  isResolving = false,
}: BankTransactionCardProps) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isTrayOpen, setIsTrayOpen] = useState(false);
  const [trayActionType, setTrayActionType] = useState<BankingActionType>("RECORD_PAYMENT");
  const menuRef = useRef<HTMLDivElement>(null);

  // Close dropdown menu on outside click
  useEffect(() => {
    if (!isMenuOpen) return;
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isMenuOpen]);

  const isCredit = parseFloat(tx.credit_amount) > 0;
  const isDebit = !isCredit;
  const amountVal = isCredit ? parseFloat(tx.credit_amount) : parseFloat(tx.debit_amount);
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

  const handleMenuAction = (actionFn: () => void) => {
    setIsMenuOpen(false);
    actionFn();
  };

  const openTrayWith = (actionType: BankingActionType) => {
    setTrayActionType(actionType);
    setIsTrayOpen(true);
  };

  const handleConfirmClick = () => {
    if (onOneClickConfirm) {
      onOneClickConfirm(tx);
    } else {
      onOpenActionModal(tx, isExpenseMatch ? "RECORD_EXPENSE" : "MATCH_PARTY");
    }
  };

  const handleChangeClick = () => {
    if (isTrayOpen && trayActionType === "RECORD_PAYMENT") {
      setIsTrayOpen(false);
    } else {
      openTrayWith("RECORD_PAYMENT");
    }
  };

  const handleExpenseClick = () => {
    if (isTrayOpen && trayActionType === "RECORD_EXPENSE") {
      setIsTrayOpen(false);
    } else {
      openTrayWith("RECORD_EXPENSE");
    }
  };

  return (
    <React.Fragment>
      {showDateHeader && (
        <div className={`flex items-center gap-3 ${idx > 0 ? "pt-3.5" : ""}`}>
          <span className="text-[11px] font-bold text-muted-foreground font-mono whitespace-nowrap">
            {(() => {
              try {
                const d = new Date(tx.transaction_date);
                if (isNaN(d.getTime())) return tx.transaction_date;
                return d.toLocaleDateString("en-IN", {
                  weekday: "short",
                  day: "2-digit",
                  month: "short",
                  year: "numeric",
                });
              } catch {
                return tx.transaction_date;
              }
            })()}
          </span>
          <div className="flex-1 h-px bg-border/40" />
        </div>
      )}

      <div
        className={`bg-card border transition-all rounded-2xl p-4 shadow-xs space-y-3 relative ${
          isTrayOpen
            ? "border-primary/50 shadow-md ring-1 ring-primary/20"
            : "border-border/50 hover:border-border/90 hover:shadow-md"
        }`}
      >
        {/* Main Header Row: Direction icon, Badges, Narration & Clean Amount */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <div
              className={`p-2.5 rounded-xl shrink-0 mt-0.5 shadow-2xs ${
                isCredit
                  ? "bg-emerald-500/10 text-emerald-500 border border-emerald-500/20"
                  : "bg-rose-500/10 text-rose-500 border border-rose-500/20"
              }`}
              title={isCredit ? "Deposit / Inward Credit" : "Withdrawal / Outward Debit"}
            >
              {isCredit ? <ArrowDownRight className="w-5 h-5" /> : <ArrowUpRight className="w-5 h-5" />}
            </div>

            <div className="space-y-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                {tx.reference_number && (
                  <span className="font-mono text-[10px] font-medium px-2 py-0.5 bg-muted/60 text-muted-foreground rounded-md border border-border/50">
                    Ref: {tx.reference_number}
                  </span>
                )}

                <span
                  className={`text-[10px] font-bold px-2 py-0.5 rounded-md uppercase tracking-wider ${
                    tx.is_excluded || tx.status === "EXCLUDED"
                      ? "bg-muted text-muted-foreground border border-border"
                      : tx.status === "MATCHED" || tx.status === "RECONCILED" || tx.status === "MATCHED_AUTO"
                      ? "bg-emerald-500/10 text-emerald-500 border border-emerald-500/25"
                      : tx.status === "NEEDS_REVIEW" || tx.status === "MATCHED_SUGGESTED"
                      ? "bg-amber-500/10 text-amber-500 border border-amber-500/25"
                      : tx.status === "IGNORED"
                      ? "bg-muted text-muted-foreground border border-border/50"
                      : "bg-rose-500/10 text-rose-500 border border-rose-500/25"
                  }`}
                >
                  {tx.is_excluded || tx.status === "EXCLUDED"
                    ? "Excluded"
                    : tx.status === "MATCHED" || tx.status === "RECONCILED" || tx.status === "MATCHED_AUTO"
                    ? "Completed"
                    : tx.status === "NEEDS_REVIEW" || tx.status === "MATCHED_SUGGESTED"
                    ? "Ready to Confirm"
                    : tx.status === "IGNORED"
                    ? "Ignored"
                    : "Needs Attention"}
                </span>

                {isLikelyExpense && !tx.matched_party && (
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/25">
                    Likely Bank Charge
                  </span>
                )}
              </div>

              <div className="text-sm font-bold text-foreground leading-snug break-words">
                {tx.description}
              </div>

              {(tx.is_excluded || tx.status === "EXCLUDED") && tx.exclusion_reason && (
                <div className="text-[11px] text-amber-500/90 font-medium flex items-center gap-1.5 pt-0.5">
                  <EyeOff className="w-3.5 h-3.5" />
                  <span>Excluded: {tx.exclusion_reason}</span>
                </div>
              )}
            </div>
          </div>

          {/* Amount Display & Running Balance */}
          <div className="text-right shrink-0 sm:self-center pl-2">
            <div
              className={`text-lg sm:text-xl font-black font-mono tabular-nums leading-tight ${
                isCredit ? "text-emerald-500" : "text-rose-500"
              }`}
            >
              {isCredit ? "+" : "-"}₹{amountVal.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
            {tx.balance && (
              <div className="text-[11px] text-muted-foreground font-mono mt-0.5">
                Bal: ₹{parseFloat(tx.balance).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
              </div>
            )}
          </div>
        </div>

        {/* ------------------------------------------------------------- */}
        {/* Tier A: AI / Suggested Match Banner (Streamlined Hierarchy)     */}
        {/* ------------------------------------------------------------- */}
        {tx.matched_party && !tx.is_excluded && tx.status !== "EXCLUDED" && (
          <div className="border border-indigo-500/20 bg-indigo-500/5 dark:bg-indigo-500/10 rounded-xl p-3 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
            <div className="flex items-start gap-2.5 min-w-0">
              <div className="p-1 rounded-lg bg-indigo-500/15 text-indigo-400 shrink-0 mt-0.5">
                <Sparkles className="w-4 h-4" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-bold text-foreground truncate">
                    {isExpenseMatch
                      ? `Bank Expense: ${tx.matched_party.name}`
                      : isCredit
                      ? `Receipt from: ${tx.matched_party.name}`
                      : `Payment to: ${tx.matched_party.name}`}
                  </span>
                  <span
                    className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded ${
                      tx.match_confidence >= 80
                        ? "bg-emerald-500/15 text-emerald-500 border border-emerald-500/20"
                        : tx.match_confidence >= 50
                        ? "bg-amber-500/15 text-amber-500 border border-amber-500/20"
                        : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {tx.match_confidence}% Match
                  </span>
                </div>

                {(() => {
                  if (!tx.match_notes) return null;
                  let notesObj: any = null;
                  if (typeof tx.match_notes === "object") {
                    notesObj = tx.match_notes;
                  } else if (typeof tx.match_notes === "string") {
                    try {
                      notesObj = JSON.parse(tx.match_notes);
                    } catch {
                      return <p className="text-[11px] text-muted-foreground mt-0.5 truncate">{tx.match_notes}</p>;
                    }
                  }
                  if (notesObj && typeof notesObj === "object") {
                    const signals = Array.isArray(notesObj.signals) ? notesObj.signals.filter(Boolean) : [];
                    const reason = notesObj.ignore_reason || notesObj.reason;
                    const parts = [...signals, ...(reason ? [String(reason)] : [])];
                    if (parts.length > 0) {
                      return (
                        <div className="flex items-center gap-1.5 flex-wrap mt-1">
                          {parts.map((p, pidx) => (
                            <span key={pidx} className="text-[10px] px-1.5 py-0.5 rounded bg-card/80 text-muted-foreground font-mono border border-border/40">
                              {p}
                            </span>
                          ))}
                        </div>
                      );
                    }
                  }
                  return null;
                })()}
              </div>
            </div>

            {/* Clean 2-tier buttons + dropdown */}
            {tx.status !== "MATCHED" && tx.status !== "RECONCILED" && (
              <div className="flex items-center gap-2 w-full sm:w-auto shrink-0 justify-end">
                {/* 1. Primary One-Click Confirm (Instant, Zero Popups) */}
                <button
                  type="button"
                  onClick={handleConfirmClick}
                  disabled={isResolving}
                  className="px-3.5 py-1.5 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-bold transition-all shadow-xs flex items-center justify-center gap-1.5 cursor-pointer active:scale-95 disabled:opacity-50"
                  title="Instantly reconcile and create balanced voucher"
                >
                  {isResolving ? (
                    <div className="w-3.5 h-3.5 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <Check className="w-3.5 h-3.5 stroke-[2.5]" />
                  )}
                  <span>{isResolving ? "Confirming..." : "Confirm"}</span>
                </button>

                {/* 2. Secondary: Change Party (Opens Inline Accordion Tray) */}
                <button
                  type="button"
                  onClick={handleChangeClick}
                  className={`px-3 py-1.5 rounded-xl border text-xs font-semibold transition-all cursor-pointer flex items-center gap-1 ${
                    isTrayOpen && (trayActionType === "RECORD_PAYMENT" || trayActionType === "MATCH_PARTY")
                      ? "bg-primary/10 border-primary/40 text-primary"
                      : "border-border/80 bg-card hover:bg-muted text-foreground"
                  }`}
                  title="Expand inline drawer to change party or search bills"
                >
                  <span>Change</span>
                  <ChevronDown
                    className={`w-3 h-3 transition-transform duration-200 ${
                      isTrayOpen && (trayActionType === "RECORD_PAYMENT" || trayActionType === "MATCH_PARTY")
                        ? "rotate-180"
                        : ""
                    }`}
                  />
                </button>

                {/* Contextual Expense Shortcut if applicable */}
                {isDebit && !isExpenseMatch && isLikelyExpense && (
                  <button
                    type="button"
                    onClick={handleExpenseClick}
                    className={`px-2.5 py-1.5 rounded-xl border text-xs font-semibold cursor-pointer transition-all flex items-center gap-1 ${
                      isTrayOpen && trayActionType === "RECORD_EXPENSE"
                        ? "bg-amber-500/20 border-amber-500/50 text-amber-500"
                        : "bg-amber-500/10 border-amber-500/30 hover:bg-amber-500/20 text-amber-600 dark:text-amber-400"
                    }`}
                    title="Classify as Bank Expense inline"
                  >
                    <Receipt className="w-3 h-3" />
                    <span>Expense</span>
                  </button>
                )}

                {/* 3. Overflow Dropdown Button */}
                <div className="relative" ref={menuRef}>
                  <button
                    type="button"
                    onClick={() => setIsMenuOpen(!isMenuOpen)}
                    className="p-1.5 rounded-xl border border-border/80 bg-card hover:bg-muted text-muted-foreground hover:text-foreground cursor-pointer transition-all shadow-2xs"
                    title="More options"
                  >
                    <MoreHorizontal className="w-4 h-4" />
                  </button>

                  {/* Dropdown Menu */}
                  {isMenuOpen && (
                    <div className="absolute right-0 top-full mt-1.5 w-56 bg-card border border-border rounded-2xl shadow-xl z-30 p-1 divide-y divide-border/40 animate-in fade-in zoom-in-95 duration-100">
                      <div className="p-1 space-y-0.5">
                        <button
                          type="button"
                          onClick={() => handleMenuAction(() => openTrayWith("RECORD_TRANSFER"))}
                          className="w-full px-2.5 py-2 text-xs font-medium rounded-lg flex items-center gap-2.5 hover:bg-muted text-foreground transition-colors cursor-pointer text-left"
                        >
                          <Wallet className="w-3.5 h-3.5 text-muted-foreground" />
                          <span>Transfer / Contra</span>
                        </button>
                        {sisterCompanies.length > 0 && (
                          <button
                            type="button"
                            onClick={() => handleMenuAction(() => openTrayWith("TRIANGULAR_SETTLEMENT"))}
                            className="w-full px-2.5 py-2 text-xs font-medium rounded-lg flex items-center gap-2.5 hover:bg-muted text-foreground transition-colors cursor-pointer text-left"
                          >
                            <Building2 className="w-3.5 h-3.5 text-muted-foreground" />
                            <span>Sister Entity Settlement</span>
                          </button>
                        )}
                        {isDebit && (
                          <button
                            type="button"
                            onClick={() => handleMenuAction(() => openTrayWith("OWNER_DRAWING"))}
                            className="w-full px-2.5 py-2 text-xs font-medium rounded-lg flex items-center gap-2.5 hover:bg-muted text-foreground transition-colors cursor-pointer text-left"
                          >
                            <CornerDownRight className="w-3.5 h-3.5 text-muted-foreground" />
                            <span>Owner / Partner Drawing</span>
                          </button>
                        )}
                        {onToggleDirection && (
                          <button
                            type="button"
                            onClick={() => handleMenuAction(() => onToggleDirection(tx))}
                            disabled={isTogglingDirection}
                            className="w-full px-2.5 py-2 text-xs font-medium rounded-lg flex items-center gap-2.5 hover:bg-muted text-foreground transition-colors cursor-pointer text-left disabled:opacity-50"
                          >
                            <ArrowLeftRight className="w-3.5 h-3.5 text-primary" />
                            <span>{isCredit ? "Switch to Debit (-)" : "Switch to Credit (+)"}</span>
                          </button>
                        )}
                      </div>

                      <div className="p-1 space-y-0.5">
                        <button
                          type="button"
                          onClick={() => handleMenuAction(() => openTrayWith("IGNORE"))}
                          className="w-full px-2.5 py-2 text-xs font-medium rounded-lg flex items-center gap-2.5 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer text-left"
                        >
                          <span>Skip for Now (Ignore)</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleMenuAction(() => onOpenActionModal(tx, "MATCH_PARTY"))}
                          className="w-full px-2.5 py-2 text-xs font-medium rounded-lg flex items-center gap-2.5 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer text-left"
                        >
                          <Maximize2 className="w-3.5 h-3.5 text-muted-foreground" />
                          <span>Open Advanced Modal...</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleMenuAction(() => onExclude(tx))}
                          className="w-full px-2.5 py-2 text-xs font-semibold rounded-lg flex items-center gap-2.5 hover:bg-amber-500/10 text-amber-500 transition-colors cursor-pointer text-left"
                        >
                          <EyeOff className="w-3.5 h-3.5" />
                          <span>Exclude (Personal)</span>
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ------------------------------------------------------------- */}
        {/* Tier B: Reconciled / Done State                                 */}
        {/* ------------------------------------------------------------- */}
        {tx.matched_voucher && !tx.is_excluded && tx.status !== "EXCLUDED" && (
          <div className="text-xs text-emerald-500 bg-emerald-500/10 border border-emerald-500/20 px-3.5 py-2 rounded-xl flex items-center justify-between font-mono">
            <span className="font-semibold">✓ Reconciled: Voucher #{tx.matched_voucher.voucher_number}</span>
            <div className="flex items-center gap-2.5">
              {onViewVouchers && (
                <button
                  onClick={onViewVouchers}
                  className="hover:underline text-[11px] font-sans font-semibold cursor-pointer flex items-center gap-1 text-primary"
                >
                  <span>View Voucher</span>
                  <ExternalLink className="w-3 h-3" />
                </button>
              )}
              <button
                onClick={() => onExclude(tx)}
                className="text-amber-500/80 hover:text-amber-400 hover:underline text-[11px] font-sans cursor-pointer flex items-center gap-1 ml-1"
                title="Exclude transaction and reverse reconciliation"
              >
                <EyeOff className="w-3 h-3" />
                <span>Exclude</span>
              </button>
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------- */}
        {/* Tier C: Excluded State                                          */}
        {/* ------------------------------------------------------------- */}
        {(tx.is_excluded || tx.status === "EXCLUDED") && (
          <div className="flex items-center justify-between pt-2 border-t border-border/30">
            <span className="text-[11px] text-muted-foreground font-medium">
              Excluded from financial statements & tax books
            </span>
            <button
              onClick={() => onRestore(tx)}
              className="px-3 py-1.5 rounded-xl text-xs font-bold bg-primary text-primary-foreground hover:bg-primary/90 transition-all cursor-pointer shadow-xs"
            >
              Restore to Books
            </button>
          </div>
        )}

        {/* ------------------------------------------------------------- */}
        {/* Tier D: Unmatched / Needs Attention (Streamlined 2-Tier Bar)    */}
        {/* ------------------------------------------------------------- */}
        {!tx.is_excluded && tx.status !== "EXCLUDED" && tx.status !== "MATCHED" && tx.status !== "RECONCILED" && !tx.matched_party && (
          <div className="flex items-center justify-between gap-2 pt-2.5 border-t border-border/40 flex-wrap">
            <div className="text-xs text-muted-foreground flex items-center gap-1.5 font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse" />
              <span>Select classification:</span>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              {/* Primary Action Button (Opens Inline Tray directly) */}
              {isLikelyExpense ? (
                <button
                  type="button"
                  onClick={() => openTrayWith("RECORD_EXPENSE")}
                  className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer shadow-xs flex items-center gap-1.5 active:scale-95 ${
                    isTrayOpen && trayActionType === "RECORD_EXPENSE"
                      ? "bg-amber-600 text-white ring-2 ring-amber-500/30"
                      : "bg-amber-500 text-white hover:bg-amber-600"
                  }`}
                >
                  <Receipt className="w-3.5 h-3.5" />
                  <span>Record Expense</span>
                  <ChevronDown
                    className={`w-3 h-3 transition-transform duration-200 ${
                      isTrayOpen && trayActionType === "RECORD_EXPENSE" ? "rotate-180" : ""
                    }`}
                  />
                </button>
              ) : isCredit ? (
                <button
                  type="button"
                  onClick={() => openTrayWith("RECORD_PAYMENT")}
                  className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer shadow-xs flex items-center gap-1.5 active:scale-95 ${
                    isTrayOpen && trayActionType === "RECORD_PAYMENT"
                      ? "bg-emerald-700 text-white ring-2 ring-emerald-500/30"
                      : "bg-emerald-600 hover:bg-emerald-700 text-white"
                  }`}
                >
                  <Receipt className="w-3.5 h-3.5" />
                  <span>Customer Receipt</span>
                  <ChevronDown
                    className={`w-3 h-3 transition-transform duration-200 ${
                      isTrayOpen && trayActionType === "RECORD_PAYMENT" ? "rotate-180" : ""
                    }`}
                  />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => openTrayWith("RECORD_PAYMENT")}
                  className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer shadow-xs flex items-center gap-1.5 active:scale-95 ${
                    isTrayOpen && trayActionType === "RECORD_PAYMENT"
                      ? "bg-primary/90 text-primary-foreground ring-2 ring-primary/30"
                      : "bg-primary text-primary-foreground hover:bg-primary/90"
                  }`}
                >
                  <CreditCard className="w-3.5 h-3.5" />
                  <span>Supplier Payment</span>
                  <ChevronDown
                    className={`w-3 h-3 transition-transform duration-200 ${
                      isTrayOpen && trayActionType === "RECORD_PAYMENT" ? "rotate-180" : ""
                    }`}
                  />
                </button>
              )}

              {/* Secondary Action Button */}
              {isLikelyExpense ? (
                <button
                  type="button"
                  onClick={() => openTrayWith("MATCH_PARTY")}
                  className={`px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all cursor-pointer flex items-center gap-1.5 ${
                    isTrayOpen && trayActionType === "MATCH_PARTY"
                      ? "bg-muted border-primary/40 text-foreground"
                      : "border-border/80 bg-card hover:bg-muted text-foreground"
                  }`}
                >
                  <UserCheck className="w-3.5 h-3.5 text-muted-foreground" />
                  <span>Match Party</span>
                </button>
              ) : isCredit ? (
                <button
                  type="button"
                  onClick={() => openTrayWith("MATCH_PARTY")}
                  className={`px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all cursor-pointer flex items-center gap-1.5 ${
                    isTrayOpen && trayActionType === "MATCH_PARTY"
                      ? "bg-muted border-primary/40 text-foreground"
                      : "border-border/80 bg-card hover:bg-muted text-foreground"
                  }`}
                >
                  <UserCheck className="w-3.5 h-3.5 text-muted-foreground" />
                  <span>Match Party</span>
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => openTrayWith("RECORD_EXPENSE")}
                  className={`px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all cursor-pointer flex items-center gap-1.5 ${
                    isTrayOpen && trayActionType === "RECORD_EXPENSE"
                      ? "bg-muted border-primary/40 text-foreground"
                      : "border-border/80 bg-card hover:bg-muted text-foreground"
                  }`}
                >
                  <Receipt className="w-3.5 h-3.5 text-muted-foreground" />
                  <span>Record Expense</span>
                </button>
              )}

              {/* 3. Overflow Dropdown Button for Niche / Advanced Actions */}
              <div className="relative" ref={menuRef}>
                <button
                  type="button"
                  onClick={() => setIsMenuOpen(!isMenuOpen)}
                  className="px-2.5 py-1.5 rounded-xl text-xs font-semibold border border-border/80 bg-card hover:bg-muted text-muted-foreground hover:text-foreground cursor-pointer transition-all flex items-center gap-1 shadow-2xs"
                  title="More actions"
                >
                  <MoreHorizontal className="w-4 h-4" />
                  <span className="hidden sm:inline">More</span>
                </button>

                {/* Dropdown Menu */}
                {isMenuOpen && (
                  <div className="absolute right-0 bottom-full sm:bottom-auto sm:top-full mb-1.5 sm:mb-0 sm:mt-1.5 w-56 bg-card border border-border rounded-2xl shadow-xl z-30 p-1 divide-y divide-border/40 animate-in fade-in zoom-in-95 duration-100">
                    <div className="p-1 space-y-0.5">
                      <button
                        type="button"
                        onClick={() => handleMenuAction(() => openTrayWith("RECORD_TRANSFER"))}
                        className="w-full px-2.5 py-2 text-xs font-medium rounded-lg flex items-center gap-2.5 hover:bg-muted text-foreground transition-colors cursor-pointer text-left"
                      >
                        <Wallet className="w-3.5 h-3.5 text-muted-foreground" />
                        <span>Transfer / Contra</span>
                      </button>
                      {sisterCompanies.length > 0 && (
                        <button
                          type="button"
                          onClick={() => handleMenuAction(() => openTrayWith("TRIANGULAR_SETTLEMENT"))}
                          className="w-full px-2.5 py-2 text-xs font-medium rounded-lg flex items-center gap-2.5 hover:bg-muted text-foreground transition-colors cursor-pointer text-left"
                        >
                          <Building2 className="w-3.5 h-3.5 text-muted-foreground" />
                          <span>Sister Entity Settlement</span>
                        </button>
                      )}
                      {isDebit && (
                        <button
                          type="button"
                          onClick={() => handleMenuAction(() => openTrayWith("OWNER_DRAWING"))}
                          className="w-full px-2.5 py-2 text-xs font-medium rounded-lg flex items-center gap-2.5 hover:bg-muted text-foreground transition-colors cursor-pointer text-left"
                        >
                          <CornerDownRight className="w-3.5 h-3.5 text-muted-foreground" />
                          <span>Owner / Partner Drawing</span>
                        </button>
                      )}
                      {onToggleDirection && (
                        <button
                          type="button"
                          onClick={() => handleMenuAction(() => onToggleDirection(tx))}
                          disabled={isTogglingDirection}
                          className="w-full px-2.5 py-2 text-xs font-medium rounded-lg flex items-center gap-2.5 hover:bg-muted text-foreground transition-colors cursor-pointer text-left disabled:opacity-50"
                        >
                          <ArrowLeftRight className="w-3.5 h-3.5 text-primary" />
                          <span>{isCredit ? "Switch to Debit (-)" : "Switch to Credit (+)"}</span>
                        </button>
                      )}
                    </div>

                    <div className="p-1 space-y-0.5">
                      <button
                        type="button"
                        onClick={() => handleMenuAction(() => openTrayWith("IGNORE"))}
                        className="w-full px-2.5 py-2 text-xs font-medium rounded-lg flex items-center gap-2.5 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer text-left"
                      >
                        <span>Skip for Now (Ignore)</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => handleMenuAction(() => onOpenActionModal(tx, "RECORD_PAYMENT"))}
                        className="w-full px-2.5 py-2 text-xs font-medium rounded-lg flex items-center gap-2.5 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer text-left"
                      >
                        <Maximize2 className="w-3.5 h-3.5 text-muted-foreground" />
                        <span>Open Advanced Modal...</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => handleMenuAction(() => onExclude(tx))}
                        className="w-full px-2.5 py-2 text-xs font-semibold rounded-lg flex items-center gap-2.5 hover:bg-amber-500/10 text-amber-500 transition-colors cursor-pointer text-left"
                      >
                        <EyeOff className="w-3.5 h-3.5" />
                        <span>Exclude (Personal)</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Phase 3 Inline Accordion Match Tray */}
        {isTrayOpen && (
          <InlineMatchTray
            tx={tx}
            isOpen={isTrayOpen}
            onClose={() => setIsTrayOpen(false)}
            partyOptions={partyOptions}
            expenseOptions={expenseOptions}
            contraOptions={contraOptions}
            sisterCompanies={sisterCompanies}
            initialActionType={trayActionType}
            isResolving={isResolving}
            onResolve={async (actionType, payload) => {
              if (onInlineResolve) {
                await onInlineResolve(tx, actionType, payload);
                setIsTrayOpen(false);
              } else {
                onOpenActionModal(tx, actionType);
              }
            }}
            onOpenAdvancedModal={() => {
              setIsTrayOpen(false);
              onOpenActionModal(tx, trayActionType);
            }}
          />
        )}
      </div>
    </React.Fragment>
  );
}
