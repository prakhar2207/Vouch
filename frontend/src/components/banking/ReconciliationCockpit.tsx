"use client";

import React from "react";
import Link from "next/link";
import SearchableSelect, { SearchableOption } from "@/components/SearchableSelect";
import {
  Landmark,
  Plus,
  CheckCircle2,
  AlertCircle,
  Sparkles,
  Layers,
  ArrowRight,
  ShieldCheck,
  Scale,
} from "lucide-react";
import { BankLedger, ReconciliationSummary, BankingActiveTab } from "./types";

interface ReconciliationCockpitProps {
  selectedBankId: string;
  onSelectBankId: (id: string) => void;
  bankLedgers: BankLedger[];
  bankOptions: SearchableOption[];
  onAddNewBank?: () => void;
  summary: ReconciliationSummary | null;
  activeTab: BankingActiveTab;
  onSelectTab: (tab: BankingActiveTab) => void;
}

export default function ReconciliationCockpit({
  selectedBankId,
  onSelectBankId,
  bankLedgers,
  bankOptions,
  onAddNewBank,
  summary,
  activeTab,
  onSelectTab,
}: ReconciliationCockpitProps) {
  const selectedBank = bankLedgers.find((b) => b.id === selectedBankId);
  const bal = selectedBank
    ? (selectedBank.currentBalance !== undefined ? selectedBank.currentBalance : selectedBank.current_balance)
    : 0;

  const hasDetails = selectedBank && (selectedBank.bank_ifsc || selectedBank.upi_id || selectedBank.bank_account_number);

  const maskAccountNumber = (acc?: string) => {
    if (!acc) return null;
    const clean = acc.trim();
    if (clean.length <= 4) return clean;
    return `•••• ${clean.slice(-4)}`;
  };

  const formattedCutoff = summary?.statement_cutoff_date
    ? new Date(summary.statement_cutoff_date).toLocaleDateString("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      })
    : null;

  const statementBal = parseFloat(summary?.statement_closing_balance || "0");
  const bookBal = parseFloat(summary?.book_closing_balance || "0");
  const rawGap = summary?.reconciliation_gap !== null && summary?.reconciliation_gap !== undefined
    ? parseFloat(summary.reconciliation_gap)
    : Math.abs(statementBal - bookBal);
  const gap = Math.abs(rawGap);

  const isBalanced = summary?.is_balanced || gap < 0.01;
  const isFullyReconciled = summary?.reconciliation_state === "FULLY_RECONCILED" || (isBalanced && (summary?.unresolved_count || 0) === 0);

  const total = summary?.total_transactions || 0;
  const completedCount = (summary?.matched_count || 0) + (summary?.reconciled_count || 0);
  const progressPercent = total > 0 ? Math.min(100, Math.max(0, Math.round((completedCount / total) * 100))) : (isBalanced ? 100 : 0);

  return (
    <div className="relative overflow-hidden bg-card border border-border/60 rounded-3xl p-5 md:p-6 shadow-sm transition-all space-y-6">
      {/* Background ambient decorative glow */}
      <div className="pointer-events-none absolute -right-20 -top-20 w-80 h-80 rounded-full bg-primary/5 blur-3xl" />
      <div className="pointer-events-none absolute -left-20 -bottom-20 w-80 h-80 rounded-full bg-emerald-500/5 blur-3xl" />

      {/* TOP TIER: Bank Account Identity & Reconcilation Formula */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        {/* LEFT COLUMN: Bank Selector & Bank Details (4 cols on desktop) */}
        <div className="lg:col-span-4 flex flex-col justify-between border-b lg:border-b-0 lg:border-r border-border/50 pb-6 lg:pb-0 lg:pr-6 space-y-4">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Landmark className="w-4 h-4 text-primary" />
                <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
                  Active Bank
                </label>
              </div>
              <div className="flex items-center gap-2">
                {bankLedgers.length > 1 && (
                  <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-500 dark:text-blue-400 border border-blue-500/20 font-semibold">
                    {bankLedgers.length} Accounts
                  </span>
                )}
                {onAddNewBank && (
                  <button
                    type="button"
                    onClick={onAddNewBank}
                    className="text-xs text-primary hover:text-primary/80 font-bold flex items-center gap-1 cursor-pointer transition-colors"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Add Bank</span>
                  </button>
                )}
              </div>
            </div>

            <SearchableSelect
              value={selectedBankId}
              onChange={onSelectBankId}
              options={bankOptions}
              placeholder="-- Select Bank Account --"
              searchPlaceholder="Search bank accounts..."
            />

            {bankLedgers.length === 0 && (
              <div className="p-3.5 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-xs text-foreground space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <p className="font-bold text-amber-500">No bank accounts configured</p>
                    <p className="text-[11px] text-muted-foreground">Add your bank account to reconcile statements & match transactions.</p>
                  </div>
                  {onAddNewBank && (
                    <button
                      type="button"
                      onClick={onAddNewBank}
                      className="px-2.5 py-1 bg-primary text-primary-foreground text-xs font-bold rounded-lg shrink-0 cursor-pointer shadow-xs hover:bg-primary/90 transition-all"
                    >
                      + Add
                    </button>
                  )}
                </div>
                <div className="pt-2 border-t border-amber-500/10 flex items-center justify-between text-[11px]">
                  <span className="text-muted-foreground">Or setup bank on sales invoices:</span>
                  <Link
                    href="/settings?tab=firm-profile"
                    className="text-primary hover:underline font-semibold"
                  >
                    Firm Settings &rarr;
                  </Link>
                </div>
              </div>
            )}
          </div>

          {selectedBank && (
            <div className="p-3.5 rounded-2xl bg-muted/20 border border-border/40 space-y-2.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5 min-w-0">
                  <div className="w-8 h-8 rounded-xl bg-primary/15 text-primary flex items-center justify-center font-black text-xs shrink-0">
                    {selectedBank.name.charAt(0).toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <div className="text-xs font-bold text-foreground truncate" title={selectedBank.name}>
                      {selectedBank.name}
                    </div>
                    {selectedBank.bank_account_number && (
                      <div className="text-[11px] text-muted-foreground font-mono">
                        A/C {maskAccountNumber(selectedBank.bank_account_number)}
                      </div>
                    )}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className="text-[10px] uppercase font-bold text-muted-foreground">Ledger Bal</div>
                  <div className="text-xs font-black font-mono tabular-nums text-foreground">
                    ₹{(bal ?? 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </div>
                </div>
              </div>

              {hasDetails && (
                <div className="pt-2 border-t border-border/30 flex items-center gap-2 text-[10px] text-muted-foreground font-mono flex-wrap">
                  {selectedBank.bank_ifsc && (
                    <span className="px-1.5 py-0.5 rounded bg-card border border-border/40">
                      IFSC: {selectedBank.bank_ifsc}
                    </span>
                  )}
                  {selectedBank.upi_id && (
                    <span className="px-1.5 py-0.5 rounded bg-card border border-border/40">
                      UPI: {selectedBank.upi_id}
                    </span>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* RIGHT COLUMN: Reconciliation Equation Cockpit (8 cols on desktop) */}
        <div className="lg:col-span-8 flex flex-col justify-between space-y-4">
          {/* Header Row: Title & High-level Status */}
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-2.5">
              <Scale className="w-4 h-4 text-primary" />
              <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
                Reconciliation Balance Formula
              </span>
              {formattedCutoff && (
                <span className="text-[11px] font-mono font-medium px-2 py-0.5 rounded bg-muted/40 text-muted-foreground border border-border/40">
                  As of {formattedCutoff}
                </span>
              )}
            </div>

            {isFullyReconciled ? (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 shadow-xs">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Reconciled</span>
              </span>
            ) : isBalanced ? (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 shadow-xs">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Balanced</span>
              </span>
            ) : summary?.reconciliation_state === "TRANSACTIONS_REVIEWED" ? (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 shadow-xs">
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>Reviewed</span>
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 shadow-xs">
                <AlertCircle className="w-3.5 h-3.5" />
                <span>Unreconciled</span>
              </span>
            )}
          </div>

          {/* Equation Cards: Statement - Book = Gap */}
          <div className="grid grid-cols-1 sm:grid-cols-11 gap-2 items-center">
            {/* Box 1: Statement Balance */}
            <div className="sm:col-span-3 p-3.5 rounded-2xl bg-muted/20 border border-border/40 flex flex-col justify-between space-y-1">
              <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">
                Statement Balance
              </span>
              <div className="text-base sm:text-lg font-black font-mono tabular-nums text-foreground tracking-tight">
                ₹{statementBal.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <span className="text-[10px] text-muted-foreground/80 font-medium">
                Bank Passbook closing
              </span>
            </div>

            {/* Minus Operator */}
            <div className="sm:col-span-1 flex justify-center py-1 sm:py-0">
              <div className="w-7 h-7 rounded-full bg-muted/40 border border-border/50 flex items-center justify-center text-sm font-black text-muted-foreground select-none">
                −
              </div>
            </div>

            {/* Box 2: Book Balance */}
            <div className="sm:col-span-3 p-3.5 rounded-2xl bg-muted/20 border border-border/40 flex flex-col justify-between space-y-1">
              <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">
                Book Balance
              </span>
              <div className="text-base sm:text-lg font-black font-mono tabular-nums text-foreground tracking-tight">
                ₹{bookBal.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <span className="text-[10px] text-muted-foreground/80 font-medium">
                Recorded in Vouch
              </span>
            </div>

            {/* Equals Operator */}
            <div className="sm:col-span-1 flex justify-center py-1 sm:py-0">
              <div className="w-7 h-7 rounded-full bg-muted/40 border border-border/50 flex items-center justify-center text-sm font-black text-muted-foreground select-none">
                =
              </div>
            </div>

            {/* Box 3: Reconciliation Gap */}
            <div
              className={`sm:col-span-3 p-3.5 rounded-2xl border transition-all flex flex-col justify-between space-y-1 ${
                isBalanced
                  ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-500"
                  : "bg-amber-500/10 border-amber-500/30 text-amber-500"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                  {isBalanced ? "Balance Gap" : "Difference (Gap)"}
                </span>
                {isBalanced ? (
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                ) : (
                  <AlertCircle className="w-3.5 h-3.5 text-amber-500" />
                )}
              </div>
              <div
                className={`text-base sm:text-lg font-black font-mono tabular-nums tracking-tight ${
                  isBalanced ? "text-emerald-500" : "text-amber-500"
                }`}
              >
                ₹{gap.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <div className="text-[10px] font-semibold truncate">
                {isBalanced ? (
                  <span className="text-emerald-600 dark:text-emerald-400">✓ Perfectly Reconciled</span>
                ) : (
                  <span className="text-amber-600 dark:text-amber-400">
                    {summary?.unresolved_count || 0} items to resolve
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* BOTTOM TIER: Live Progress Bar & Clickable Interactive Status Chips */}
      <div className="border-t border-border/50 pt-4 space-y-3.5">
        {/* Progress Bar & Stat Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 text-xs">
          <div className="flex items-center gap-2">
            <span className="font-bold text-foreground">Reconciliation Progress</span>
            <span className="text-muted-foreground text-[11px] font-medium font-mono">
              ({completedCount} of {total} transactions reconciled)
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`text-xs font-mono font-black ${
                progressPercent === 100 ? "text-emerald-500" : "text-primary"
              }`}
            >
              {progressPercent}% Complete
            </span>
          </div>
        </div>

        {/* The Progress Bar Track */}
        <div className="h-2.5 w-full bg-muted/40 rounded-full overflow-hidden p-0.5 border border-border/40">
          <div
            className={`h-full rounded-full transition-all duration-500 ease-out ${
              progressPercent === 100
                ? "bg-emerald-500"
                : "bg-gradient-to-r from-primary to-emerald-500"
            }`}
            style={{ width: `${progressPercent}%` }}
          />
        </div>

        {/* Interactive Clickable Filter Chips */}
        <div className="flex items-center gap-2 flex-wrap pt-1">
          <button
            type="button"
            onClick={() => onSelectTab("UNRESOLVED")}
            className={`group px-3 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer flex items-center gap-2 border ${
              activeTab === "UNRESOLVED"
                ? "bg-rose-500/15 border-rose-500/40 text-foreground shadow-xs ring-1 ring-rose-500/20"
                : "bg-muted/30 border-border/40 text-muted-foreground hover:text-foreground hover:bg-muted/50"
            }`}
            title="Filter by transactions needing attention"
          >
            <div className="w-2 h-2 rounded-full bg-rose-500 shrink-0" />
            <span>Needs Attention</span>
            <span className="px-1.5 py-0.5 rounded-full text-[10px] font-mono font-black bg-rose-500/15 text-rose-500 leading-none">
              {summary?.unresolved_count || 0}
            </span>
          </button>

          <button
            type="button"
            onClick={() => onSelectTab("NEEDS_REVIEW")}
            className={`group px-3 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer flex items-center gap-2 border ${
              activeTab === "NEEDS_REVIEW"
                ? "bg-amber-500/15 border-amber-500/40 text-foreground shadow-xs ring-1 ring-amber-500/20"
                : "bg-muted/30 border-border/40 text-muted-foreground hover:text-foreground hover:bg-muted/50"
            }`}
            title="Filter by suggested matches ready to confirm"
          >
            <div className="w-2 h-2 rounded-full bg-amber-500 shrink-0" />
            <span>Ready to Confirm</span>
            <span className="px-1.5 py-0.5 rounded-full text-[10px] font-mono font-black bg-amber-500/15 text-amber-500 leading-none">
              {summary?.needs_review_count || 0}
            </span>
          </button>

          <button
            type="button"
            onClick={() => onSelectTab("MATCHED")}
            className={`group px-3 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer flex items-center gap-2 border ${
              activeTab === "MATCHED"
                ? "bg-emerald-500/15 border-emerald-500/40 text-foreground shadow-xs ring-1 ring-emerald-500/20"
                : "bg-muted/30 border-border/40 text-muted-foreground hover:text-foreground hover:bg-muted/50"
            }`}
            title="Filter by reconciled transactions"
          >
            <div className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
            <span>Completed</span>
            <span className="px-1.5 py-0.5 rounded-full text-[10px] font-mono font-black bg-emerald-500/15 text-emerald-500 leading-none">
              {completedCount}
            </span>
          </button>

          {(summary?.excluded_count || 0) > 0 && (
            <button
              type="button"
              onClick={() => onSelectTab("EXCLUDED")}
              className={`group px-3 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer flex items-center gap-2 border ${
                activeTab === "EXCLUDED"
                  ? "bg-card border-border/80 text-foreground shadow-xs ring-1 ring-border/50"
                  : "bg-muted/30 border-border/40 text-muted-foreground hover:text-foreground hover:bg-muted/50"
              }`}
              title="Filter by excluded transactions"
            >
              <div className="w-2 h-2 rounded-full bg-muted-foreground/40 shrink-0" />
              <span>Excluded</span>
              <span className="px-1.5 py-0.5 rounded-full text-[10px] font-mono font-black bg-muted text-muted-foreground leading-none">
                {summary?.excluded_count || 0}
              </span>
            </button>
          )}

          <button
            type="button"
            onClick={() => onSelectTab("ALL")}
            className={`group px-3 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer flex items-center gap-2 border ${
              activeTab === "ALL"
                ? "bg-card border-primary/50 text-foreground shadow-xs ring-1 ring-primary/20"
                : "bg-muted/30 border-border/40 text-muted-foreground hover:text-foreground hover:bg-muted/50"
            }`}
            title="View all transactions"
          >
            <span>All Transactions</span>
            <span className="px-1.5 py-0.5 rounded-full text-[10px] font-mono font-black bg-muted text-muted-foreground leading-none">
              {total}
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}
