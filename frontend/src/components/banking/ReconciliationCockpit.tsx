"use client";

import React, { useState, useEffect } from "react";
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
  FileText,
  SlidersHorizontal,
  HelpCircle,
  Check,
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
  // Simple Mode (default for small business owners) vs Advanced / Accountant Mode
  const [viewMode, setViewMode] = useState<"simple" | "advanced">("simple");

  useEffect(() => {
    try {
      const saved = localStorage.getItem("srilekh_recon_mode");
      if (saved === "advanced" || saved === "simple") {
        setViewMode(saved);
      }
    } catch {
      // Local storage not accessible
    }
  }, []);

  const toggleViewMode = (newMode: "simple" | "advanced") => {
    setViewMode(newMode);
    try {
      localStorage.setItem("srilekh_recon_mode", newMode);
    } catch {
      // Local storage not accessible
    }
  };

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

  // Evidence validation: Missing statement evidence is NOT zero!
  const hasStatementEvidence = summary?.statement_closing_balance !== null && summary?.statement_closing_balance !== undefined;
  const statementBal = hasStatementEvidence ? parseFloat(summary!.statement_closing_balance!) : null;
  const bookBal = summary?.book_closing_balance !== null && summary?.book_closing_balance !== undefined
    ? parseFloat(summary.book_closing_balance)
    : 0;

  const rawGap = summary?.reconciliation_gap !== null && summary?.reconciliation_gap !== undefined
    ? parseFloat(summary.reconciliation_gap)
    : null;
  const gap = rawGap !== null ? Math.abs(rawGap) : null;

  // Trust validated backend reconciliation state
  const reconState = summary?.reconciliation_state || (hasStatementEvidence ? (summary?.is_balanced ? "BALANCE_MATCHED" : "IN_PROGRESS") : "NOT_VERIFIABLE");
  const isFullyReconciled = reconState === "FULLY_RECONCILED";
  const isBalanced = reconState === "FULLY_RECONCILED" || reconState === "BALANCE_MATCHED";
  const isNotVerifiable = reconState === "NOT_VERIFIABLE" || !hasStatementEvidence;

  const total = summary?.total_transactions || 0;
  const completedCount = summary?.completed_count ?? summary?.reconciled_count ?? 0;
  const progressPercent = total > 0 ? Math.min(100, Math.max(0, Math.round((completedCount / total) * 100))) : (isFullyReconciled ? 100 : 0);

  return (
    <div className="relative overflow-hidden bg-card border border-border/60 rounded-3xl p-5 md:p-6 shadow-sm transition-all space-y-6">
      {/* Background ambient decorative glow */}
      <div className="pointer-events-none absolute -right-20 -top-20 w-80 h-80 rounded-full bg-primary/5 blur-3xl" />
      <div className="pointer-events-none absolute -left-20 -bottom-20 w-80 h-80 rounded-full bg-emerald-500/5 blur-3xl" />

      {/* TOP TIER: Bank Account Identity & Reconciliation Dashboard */}
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

        {/* RIGHT COLUMN: Reconciliation Cockpit (8 cols on desktop) */}
        <div className="lg:col-span-8 flex flex-col justify-between space-y-4">
          {/* Header Row: Title, Mode Toggle & State Pill */}
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-2.5">
              {viewMode === "simple" ? (
                <Sparkles className="w-4 h-4 text-primary" />
              ) : (
                <Scale className="w-4 h-4 text-primary" />
              )}
              <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
                {viewMode === "simple" ? "Reconciliation Summary" : "Reconciliation Balance Formula"}
              </span>
              {formattedCutoff && (
                <span className="text-[11px] font-mono font-medium px-2 py-0.5 rounded bg-muted/40 text-muted-foreground border border-border/40">
                  As of {formattedCutoff}
                </span>
              )}
            </div>

            <div className="flex items-center gap-2">
              {/* Progressive Disclosure Mode Toggle */}
              <div className="inline-flex items-center p-0.5 rounded-lg bg-muted/40 border border-border/40 text-[11px] font-medium">
                <button
                  type="button"
                  onClick={() => toggleViewMode("simple")}
                  className={`px-2 py-0.5 rounded-md transition-all cursor-pointer ${
                    viewMode === "simple"
                      ? "bg-card text-foreground shadow-xs font-bold"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                  title="Simplified view for business owners"
                >
                  Simple View
                </button>
                <button
                  type="button"
                  onClick={() => toggleViewMode("advanced")}
                  className={`px-2 py-0.5 rounded-md transition-all cursor-pointer ${
                    viewMode === "advanced"
                      ? "bg-card text-foreground shadow-xs font-bold"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                  title="Full accounting formula & BRS bridge"
                >
                  Accountant View
                </button>
              </div>

              {/* Status Badge */}
              {isFullyReconciled ? (
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 shadow-xs">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>Fully Reconciled</span>
                </span>
              ) : isBalanced ? (
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 shadow-xs">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>Balances Match</span>
                </span>
              ) : isNotVerifiable ? (
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-muted text-muted-foreground border border-border/60 shadow-xs">
                  <HelpCircle className="w-3.5 h-3.5 text-muted-foreground" />
                  <span>Awaiting Statement</span>
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 shadow-xs">
                  <AlertCircle className="w-3.5 h-3.5" />
                  <span>Needs Attention</span>
                </span>
              )}
            </div>
          </div>

          {/* VIEW MODE 1: SIMPLE MODE (For Non-Accountant Business Owners) */}
          {viewMode === "simple" ? (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-stretch">
              {/* Card 1: Bank Balance */}
              <div className="p-4 rounded-2xl bg-muted/20 border border-border/40 flex flex-col justify-between space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">
                    Bank Passbook
                  </span>
                  <Landmark className="w-3.5 h-3.5 text-muted-foreground/60" />
                </div>
                <div className="text-lg font-black font-mono tabular-nums text-foreground tracking-tight">
                  {hasStatementEvidence && statementBal !== null
                    ? `₹${statementBal.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                    : <span className="text-xs font-medium text-muted-foreground italic">No Statement Uploaded</span>}
                </div>
                <span className="text-[10px] text-muted-foreground font-medium">
                  {hasStatementEvidence ? "Closing balance from statement" : "Upload a PDF/Excel statement"}
                </span>
              </div>

              {/* Card 2: SriLekh Balance */}
              <div className="p-4 rounded-2xl bg-muted/20 border border-border/40 flex flex-col justify-between space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">
                    SriLekh Books
                  </span>
                  <FileText className="w-3.5 h-3.5 text-muted-foreground/60" />
                </div>
                <div className="text-lg font-black font-mono tabular-nums text-foreground tracking-tight">
                  ₹{bookBal.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
                <span className="text-[10px] text-muted-foreground font-medium">
                  Recorded in your books
                </span>
              </div>

              {/* Card 3: Status & Action Needed */}
              <div
                className={`p-4 rounded-2xl border transition-all flex flex-col justify-between space-y-1.5 ${
                  isFullyReconciled
                    ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
                    : isBalanced
                    ? "bg-blue-500/10 border-blue-500/30 text-blue-600 dark:text-blue-400"
                    : isNotVerifiable
                    ? "bg-muted/30 border-border/60 text-muted-foreground"
                    : "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold uppercase tracking-wider">
                    {isFullyReconciled
                      ? "Match Status"
                      : isBalanced
                      ? "Balance Status"
                      : isNotVerifiable
                      ? "Status"
                      : "Difference"}
                  </span>
                  {isFullyReconciled ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                  ) : isBalanced ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-blue-500" />
                  ) : isNotVerifiable ? (
                    <HelpCircle className="w-3.5 h-3.5 text-muted-foreground" />
                  ) : (
                    <AlertCircle className="w-3.5 h-3.5 text-amber-500" />
                  )}
                </div>

                <div className="text-lg font-black font-mono tabular-nums tracking-tight">
                  {gap !== null ? (
                    gap < 0.01 ? (
                      "₹0.00"
                    ) : (
                      `₹${gap.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                    )
                  ) : (
                    "Pending Check"
                  )}
                </div>

                <div className="text-[10px] font-semibold truncate">
                  {isFullyReconciled ? (
                    <span>All matched & verified</span>
                  ) : isBalanced ? (
                    <span>Balances match • Verify pending</span>
                  ) : isNotVerifiable ? (
                    <span>Upload statement to verify balance</span>
                  ) : (
                    <span>{summary?.unresolved_count || 0} items need your review</span>
                  )}
                </div>
              </div>
            </div>
          ) : (
            /* VIEW MODE 2: ADVANCED ACCOUNTANT VIEW (Formal Equation & BRS) */
            <div className="space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-11 gap-2 items-center">
                {/* Box 1: Statement Balance */}
                <div className="sm:col-span-3 p-3.5 rounded-2xl bg-muted/20 border border-border/40 flex flex-col justify-between space-y-1">
                  <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">
                    Statement Balance
                  </span>
                  <div className="text-base sm:text-lg font-black font-mono tabular-nums text-foreground tracking-tight">
                    {hasStatementEvidence && statementBal !== null
                      ? `₹${statementBal.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                      : <span className="text-xs font-semibold text-muted-foreground">Not Available</span>}
                  </div>
                  <span className="text-[10px] text-muted-foreground/80 font-medium">
                    Passbook closing evidence
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
                    SriLekh General Ledger
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
                    isFullyReconciled || isBalanced
                      ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-500"
                      : isNotVerifiable
                      ? "bg-muted/30 border-border/60 text-muted-foreground"
                      : "bg-amber-500/10 border-amber-500/30 text-amber-500"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                      {isBalanced ? "Balance Gap" : isNotVerifiable ? "Verification" : "Reconciliation Gap"}
                    </span>
                    {isBalanced ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                    ) : isNotVerifiable ? (
                      <HelpCircle className="w-3.5 h-3.5 text-muted-foreground" />
                    ) : (
                      <AlertCircle className="w-3.5 h-3.5 text-amber-500" />
                    )}
                  </div>
                  <div
                    className={`text-base sm:text-lg font-black font-mono tabular-nums tracking-tight ${
                      isBalanced ? "text-emerald-500" : isNotVerifiable ? "text-muted-foreground" : "text-amber-500"
                    }`}
                  >
                    {gap !== null ? `₹${gap.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "NOT_VERIFIABLE"}
                  </div>
                  <div className="text-[10px] font-semibold truncate">
                    {isFullyReconciled ? (
                      <span className="text-emerald-600 dark:text-emerald-400">✓ Fully Reconciled</span>
                    ) : isBalanced ? (
                      <span className="text-emerald-600 dark:text-emerald-400">✓ Mathematically Balanced</span>
                    ) : isNotVerifiable ? (
                      <span className="text-muted-foreground">Missing statement closing balance</span>
                    ) : (
                      <span className="text-amber-600 dark:text-amber-400">
                        {summary?.unresolved_count || 0} items to resolve
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {selectedBankId && (
                <div className="flex justify-end pt-1">
                  <Link
                    href={`/reports/brs?bank_id=${selectedBankId}`}
                    className="text-xs text-primary hover:underline font-semibold flex items-center gap-1"
                  >
                    <span>View Statutory BRS Bridge Report</span>
                    <ArrowRight className="w-3 h-3" />
                  </Link>
                </div>
              )}
            </div>
          )}
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
            <div className="w-2 h-2 rounded-full bg-purple-500 shrink-0" />
            <span>Suggested Matches</span>
            <span className="px-1.5 py-0.5 rounded-full text-[10px] font-mono font-black bg-purple-500/15 text-purple-600 dark:text-purple-400 leading-none">
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
            <span>Reconciled</span>
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
