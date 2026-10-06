"use client";

import React from "react";
import SearchableSelect, { SearchableOption } from "@/components/SearchableSelect";
import { Plus } from "lucide-react";
import { BankLedger } from "./types";

interface BankAccountSummaryCardProps {
  selectedBankId: string;
  onSelectBankId: (id: string) => void;
  bankLedgers: BankLedger[];
  bankOptions: SearchableOption[];
  onAddNewBank?: () => void;
}

export default function BankAccountSummaryCard({
  selectedBankId,
  onSelectBankId,
  bankLedgers,
  bankOptions,
  onAddNewBank,
}: BankAccountSummaryCardProps) {
  const selectedBank = bankLedgers.find((b) => b.id === selectedBankId);
  const bal = selectedBank
    ? (selectedBank.currentBalance !== undefined ? selectedBank.currentBalance : selectedBank.current_balance)
    : 0;
  const hasDetails = selectedBank && (selectedBank.bank_ifsc || selectedBank.upi_id);

  return (
    <div className="bg-card border border-border/40 rounded-2xl p-5 shadow-sm space-y-4">
      <div className="flex items-center justify-between">
        <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
          Bank Account
        </label>
        <div className="flex items-center gap-2">
          {bankLedgers.length > 1 && (
            <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
              {bankLedgers.length} Accounts
            </span>
          )}
          {onAddNewBank && (
            <button
              type="button"
              onClick={onAddNewBank}
              className="text-xs text-primary hover:text-primary/80 font-semibold flex items-center gap-1 cursor-pointer hover:underline"
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
        <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs text-foreground flex items-center justify-between gap-2">
          <div>
            <p className="font-semibold text-amber-500">No bank accounts configured</p>
            <p className="text-[11px] text-muted-foreground">Add your bank account to reconcile statements.</p>
          </div>
          {onAddNewBank && (
            <button
              type="button"
              onClick={onAddNewBank}
              className="px-2.5 py-1 bg-primary text-primary-foreground text-xs font-bold rounded-lg shrink-0 cursor-pointer shadow-xs"
            >
              + Add
            </button>
          )}
        </div>
      )}

      {selectedBank && (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center font-bold text-sm shrink-0">
              {selectedBank.name.charAt(0).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[11px] text-muted-foreground">Book Balance</div>
              <div className="text-lg font-black font-mono tabular-nums text-foreground">
                ₹{(bal ?? 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
              </div>
            </div>
          </div>
          {hasDetails && (
            <div className="flex items-center gap-3 text-[11px] text-muted-foreground font-mono">
              {selectedBank.bank_ifsc && <span>IFSC: {selectedBank.bank_ifsc}</span>}
              {selectedBank.bank_ifsc && selectedBank.upi_id && <span className="text-border">•</span>}
              {selectedBank.upi_id && <span>UPI: {selectedBank.upi_id}</span>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
