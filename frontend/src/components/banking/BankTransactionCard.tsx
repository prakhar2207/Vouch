"use client";

import React from "react";
import {
  ArrowUpRight,
  ArrowDownRight,
  Sparkles,
  EyeOff,
} from "lucide-react";
import { BankTransactionItem, BankingActionType } from "./types";

interface BankTransactionCardProps {
  tx: BankTransactionItem;
  idx: number;
  showDateHeader: boolean;
  onOpenActionModal: (tx: BankTransactionItem, type: BankingActionType) => void;
  onExclude: (tx: BankTransactionItem) => void;
  onRestore: (tx: BankTransactionItem) => void;
  onViewVouchers?: () => void;
}

export default function BankTransactionCard({
  tx,
  idx,
  showDateHeader,
  onOpenActionModal,
  onExclude,
  onRestore,
  onViewVouchers,
}: BankTransactionCardProps) {
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

  return (
    <React.Fragment>
      {showDateHeader && (
        <div className={`flex items-center gap-3 ${idx > 0 ? "pt-3" : ""}`}>
          <span className="text-[11px] font-bold text-muted-foreground font-mono whitespace-nowrap">
            {(() => {
              try {
                const d = new Date(tx.transaction_date);
                if (isNaN(d.getTime())) return tx.transaction_date;
                return d.toLocaleDateString("en-IN", { weekday: "short", day: "2-digit", month: "short", year: "numeric" });
              } catch {
                return tx.transaction_date;
              }
            })()}
          </span>
          <div className="flex-1 h-px bg-border/40" />
        </div>
      )}
      <div className="bg-card border border-border/40 hover:border-border/80 transition-all rounded-2xl p-4 shadow-sm space-y-2.5">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
          <div className="flex items-start gap-3">
            <div
              className={`p-2.5 rounded-xl shrink-0 mt-0.5 ${
                isCredit ? "bg-emerald-500/10 text-emerald-500" : "bg-rose-500/10 text-rose-500"
              }`}
            >
              {isCredit ? <ArrowDownRight className="w-5 h-5" /> : <ArrowUpRight className="w-5 h-5" />}
            </div>

            <div className="space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                {tx.reference_number && (
                  <span className="font-mono text-[10px] px-2 py-0.5 bg-muted/60 text-muted-foreground rounded border border-border/40">
                    Ref: {tx.reference_number}
                  </span>
                )}
                <span
                  className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider ${
                    tx.is_excluded || tx.status === "EXCLUDED"
                      ? "bg-muted text-muted-foreground border border-border"
                      : tx.status === "MATCHED" || tx.status === "RECONCILED" || tx.status === "MATCHED_AUTO"
                      ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                      : tx.status === "NEEDS_REVIEW" || tx.status === "MATCHED_SUGGESTED"
                      ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                      : tx.status === "IGNORED"
                      ? "bg-muted text-muted-foreground border border-border/50"
                      : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
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
                    : "Needs Your Attention"}
                </span>
              </div>

              <div className="text-sm font-bold text-foreground leading-snug">
                {tx.description}
              </div>

              {(tx.is_excluded || tx.status === "EXCLUDED") && tx.exclusion_reason && (
                <div className="text-[11px] text-amber-500/90 font-medium flex items-center gap-1">
                  <EyeOff className="w-3 h-3" />
                  <span>Excluded: {tx.exclusion_reason}</span>
                </div>
              )}
            </div>
          </div>

          <div className="text-right shrink-0 sm:self-center">
            <div
              className={`text-lg sm:text-xl font-black font-mono tabular-nums ${
                isCredit ? "text-emerald-500" : "text-rose-500"
              }`}
            >
              {isCredit ? "+" : "-"}₹{amountVal.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
            {tx.balance && (
              <div className="text-[11px] text-muted-foreground font-mono">
                Bal: ₹{parseFloat(tx.balance).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
              </div>
            )}
          </div>
        </div>

        {tx.matched_party && !tx.is_excluded && tx.status !== "EXCLUDED" && (
          <div className="border-l-2 border-indigo-500/40 bg-muted/20 rounded-r-xl p-3 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
            <div className="flex items-start gap-2.5">
              <Sparkles className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-semibold text-foreground">
                    {isExpenseMatch
                      ? `Bank Expense: ${tx.matched_party.name}`
                      : isCredit
                      ? `Receipt from ${tx.matched_party.name}`
                      : `Payment to ${tx.matched_party.name}`}
                  </span>
                  <span className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded ${
                    tx.match_confidence >= 80
                      ? "text-emerald-500"
                      : tx.match_confidence >= 50
                      ? "text-amber-500"
                      : "text-muted-foreground"
                  }`}>
                    {tx.match_confidence}%
                  </span>
                  {isLikelyExpense && !isExpenseMatch && (
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30">
                      Possible Expense
                    </span>
                  )}
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
                      return <p className="text-[11px] text-muted-foreground mt-0.5">{tx.match_notes}</p>;
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
                            <span key={pidx} className="text-[10px] px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground font-mono">
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

            {tx.status !== "MATCHED" && tx.status !== "RECONCILED" && (
              <div className="flex items-center gap-2 w-full sm:w-auto flex-wrap">
                <button
                  onClick={() => onOpenActionModal(tx, isExpenseMatch ? "RECORD_EXPENSE" : "MATCH_PARTY")}
                  className="px-3.5 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-bold transition-colors cursor-pointer flex-1 sm:flex-initial text-center"
                >
                  Confirm
                </button>
                <button
                  onClick={() => onOpenActionModal(tx, "RECORD_PAYMENT")}
                  className="px-2.5 py-1.5 rounded-lg border border-border/60 hover:bg-muted text-foreground text-xs font-medium cursor-pointer"
                >
                  Change
                </button>
                {isDebit && (
                  <button
                    onClick={() => onOpenActionModal(tx, "RECORD_EXPENSE")}
                    className={`px-2.5 py-1.5 rounded-lg border text-xs font-semibold cursor-pointer transition-colors ${
                      isLikelyExpense
                        ? "bg-amber-500/15 border-amber-500/40 text-amber-600 dark:text-amber-400 hover:bg-amber-500/25"
                        : "border-border/60 hover:bg-muted text-foreground"
                    }`}
                    title="Classify as Bank Interest, Charges, or Business Expense"
                  >
                    Expense
                  </button>
                )}
                <button
                  onClick={() => onOpenActionModal(tx, "IGNORE")}
                  className="px-2 py-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground text-xs cursor-pointer"
                >
                  Skip
                </button>
              </div>
            )}
          </div>
        )}

        {/* Reconciled Voucher Link if resolved */}
        {tx.matched_voucher && !tx.is_excluded && tx.status !== "EXCLUDED" && (
          <div className="text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-3 py-1.5 rounded-lg flex items-center justify-between font-mono">
            <span>✓ Reconciled to Voucher: {tx.matched_voucher.voucher_number}</span>
            <div className="flex items-center gap-2">
              {onViewVouchers && (
                <button
                  onClick={onViewVouchers}
                  className="hover:underline text-[11px] cursor-pointer"
                >
                  View Voucher →
                </button>
              )}
              <button
                onClick={() => onExclude(tx)}
                className="text-amber-400/80 hover:text-amber-300 hover:underline text-[11px] cursor-pointer flex items-center gap-1 ml-2"
                title="Exclude transaction and reverse reconciliation voucher"
              >
                <EyeOff className="w-3 h-3" />
                Exclude
              </button>
            </div>
          </div>
        )}

        {/* Excluded state actions */}
        {(tx.is_excluded || tx.status === "EXCLUDED") && (
          <div className="flex items-center justify-between pt-2 border-t border-border/30">
            <span className="text-[11px] text-muted-foreground">Excluded from business accounts and books</span>
            <button
              onClick={() => onRestore(tx)}
              className="px-3 py-1.5 rounded-lg text-xs font-bold bg-primary text-primary-foreground hover:bg-primary/90 transition-colors cursor-pointer shadow-sm"
            >
              Restore to Books
            </button>
          </div>
        )}

        {/* Quick Action Toolbar */}
        {!tx.is_excluded && tx.status !== "EXCLUDED" && tx.status !== "MATCHED" && tx.status !== "RECONCILED" && !tx.matched_party && (
          <div className="flex items-center gap-2 pt-2 border-t border-border/30 flex-wrap">
            <button
              onClick={() => onOpenActionModal(tx, "MATCH_PARTY")}
              className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-muted hover:bg-muted/80 text-foreground border border-border/40 transition-colors cursor-pointer"
            >
              Match Party
            </button>

            <button
              onClick={() => onOpenActionModal(tx, "RECORD_PAYMENT")}
              className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-muted hover:bg-muted/80 text-foreground border border-border/40 transition-colors cursor-pointer"
            >
              {isCredit ? "Customer Receipt" : "Supplier Payment"}
            </button>

            {!isCredit && (
              <button
                onClick={() => onOpenActionModal(tx, "RECORD_EXPENSE")}
                className={`px-2.5 py-1 rounded-lg text-xs font-semibold border transition-colors cursor-pointer ${
                  isLikelyExpense
                    ? "bg-amber-500/15 border-amber-500/40 text-amber-600 dark:text-amber-400 font-bold hover:bg-amber-500/25"
                    : "bg-muted hover:bg-muted/80 text-foreground border border-border/40"
                }`}
              >
                Record Expense {isLikelyExpense ? "★" : ""}
              </button>
            )}

            <button
              onClick={() => onOpenActionModal(tx, "RECORD_TRANSFER")}
              className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-muted hover:bg-muted/80 text-foreground border border-border/40 transition-colors cursor-pointer"
            >
              Transfer / Contra
            </button>

            {!isCredit && (
              <button
                onClick={() => onOpenActionModal(tx, "OWNER_DRAWING")}
                className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-muted hover:bg-muted/80 text-foreground border border-border/40 transition-colors cursor-pointer"
              >
                Owner Drawing
              </button>
            )}

            <button
              onClick={() => onOpenActionModal(tx, "IGNORE")}
              className="px-2.5 py-1 rounded-lg text-xs font-semibold text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer ml-auto"
            >
              Ignore
            </button>

            <button
              onClick={() => onExclude(tx)}
              className="px-2.5 py-1 rounded-lg text-xs font-semibold text-amber-500 hover:text-amber-400 hover:bg-amber-500/10 border border-amber-500/20 transition-colors cursor-pointer flex items-center gap-1"
              title="Exclude from books without destructive deletion"
            >
              <EyeOff className="w-3 h-3" />
              <span>Exclude</span>
            </button>
          </div>
        )}
      </div>
    </React.Fragment>
  );
}
