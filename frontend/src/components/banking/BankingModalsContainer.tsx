"use client";

import React, { RefObject } from "react";
import {
  X,
  UploadCloud,
  FileSpreadsheet,
  BookOpen,
  Layers,
  Trash2,
  Sparkles,
  RefreshCw,
  EyeOff,
} from "lucide-react";
import SearchableSelect, { SearchableOption } from "@/components/SearchableSelect";
import ConfirmModal from "@/components/modals/ConfirmModal";
import {
  BankTransactionItem,
  PartyMappingItem,
  BankingActionType,
} from "./types";

interface BankingModalsContainerProps {
  isUploadOpen: boolean;
  onCloseUpload: () => void;
  selectedBankId: string;
  onSelectBankId: (id: string) => void;
  bankOptions: SearchableOption[];
  uploadFile: File | null;
  onFileChange: (file: File | null) => void;
  isUploading: boolean;
  uploadResult: any;
  onUploadSubmit: (e: React.FormEvent) => void;
  fileInputRef: RefObject<HTMLInputElement | null>;

  isMappingsOpen: boolean;
  onCloseMappings: () => void;
  mappings: PartyMappingItem[];
  loadingMappings: boolean;
  onDeleteMapping: (id: string) => void;

  selectedTx: BankTransactionItem | null;
  actionType: BankingActionType | null;
  onCloseAction: () => void;
  actionTargetPartyId: string;
  onTargetPartyChange: (id: string) => void;
  partyOptions: SearchableOption[];
  actionExpenseLedgerId: string;
  onExpenseLedgerChange: (id: string) => void;
  expenseOptions: SearchableOption[];
  actionTransferLedgerId: string;
  onTransferLedgerChange: (id: string) => void;
  contraOptions: SearchableOption[];
  actionRemarks: string;
  onRemarksChange: (remarks: string) => void;
  actionLoading: boolean;
  onSubmitAction: () => void;

  isStatementsModalOpen: boolean;
  onCloseStatements: () => void;
  statementsList: any[];
  loadingStatements: boolean;
  onExcludeStatement: (stmt: any) => void;
  onRestoreStatement: (stmt: any) => void;

  txToExclude: BankTransactionItem | null;
  stmtToExclude: any | null;
  onCloseExclusion: () => void;
  exclusionReasonInput: string;
  onExclusionReasonChange: (reason: string) => void;
  isExclusionSubmitting: boolean;
  onSubmitExcludeTransaction: () => void;
  onSubmitExcludeStatement: () => void;

  confirmModalConfig: {
    isOpen: boolean;
    title: string;
    description: React.ReactNode;
    confirmText: string;
    variant: "danger" | "warning" | "info";
    onConfirm: () => void | Promise<void>;
    isLoading?: boolean;
  };
  onCloseConfirm: () => void;
}

export default function BankingModalsContainer({
  isUploadOpen,
  onCloseUpload,
  selectedBankId,
  onSelectBankId,
  bankOptions,
  uploadFile,
  onFileChange,
  isUploading,
  uploadResult,
  onUploadSubmit,
  fileInputRef,
  isMappingsOpen,
  onCloseMappings,
  mappings,
  loadingMappings,
  onDeleteMapping,
  selectedTx,
  actionType,
  onCloseAction,
  actionTargetPartyId,
  onTargetPartyChange,
  partyOptions,
  actionExpenseLedgerId,
  onExpenseLedgerChange,
  expenseOptions,
  actionTransferLedgerId,
  onTransferLedgerChange,
  contraOptions,
  actionRemarks,
  onRemarksChange,
  actionLoading,
  onSubmitAction,
  isStatementsModalOpen,
  onCloseStatements,
  statementsList,
  loadingStatements,
  onExcludeStatement,
  onRestoreStatement,
  txToExclude,
  stmtToExclude,
  onCloseExclusion,
  exclusionReasonInput,
  onExclusionReasonChange,
  isExclusionSubmitting,
  onSubmitExcludeTransaction,
  onSubmitExcludeStatement,
  confirmModalConfig,
  onCloseConfirm,
}: BankingModalsContainerProps) {
  return (
    <>
      {/* UPLOAD STATEMENT MODAL */}
      {isUploadOpen && (
        <div 
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200"
          onClick={onCloseUpload}
        >
          <div
            className="bg-card border border-border rounded-2xl shadow-2xl w-full max-w-lg overflow-visible animate-in zoom-in-95 duration-200"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-5 border-b border-border">
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-xl bg-primary/10 text-primary">
                  <FileSpreadsheet className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-foreground">Upload Bank Statement</h3>
                  <p className="text-xs text-muted-foreground">CSV, Excel (.xlsx, .xls), or PDF statements</p>
                </div>
              </div>
              <button
                onClick={onCloseUpload}
                className="text-muted-foreground hover:text-foreground p-1 rounded-lg cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={onUploadSubmit} className="p-5 space-y-4">
              <div>
                <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider block mb-1.5">
                  Target Bank Ledger
                </label>
                <SearchableSelect
                  value={selectedBankId}
                  onChange={onSelectBankId}
                  options={bankOptions}
                  placeholder="-- Select Target Bank Account --"
                  searchPlaceholder="Search bank accounts..."
                />
              </div>

              <div
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-border/80 hover:border-primary/60 transition-all rounded-2xl p-6 text-center cursor-pointer bg-muted/20 hover:bg-muted/40 space-y-2"
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv,.xlsx,.xls,.pdf,image/png,image/jpeg"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files && e.target.files[0]) {
                      onFileChange(e.target.files[0]);
                    }
                  }}
                />
                <div className="w-12 h-12 rounded-full bg-primary/10 text-primary flex items-center justify-center mx-auto">
                  <UploadCloud className="w-6 h-6" />
                </div>
                <div className="text-xs font-bold text-foreground">
                  {uploadFile ? uploadFile.name : "Click or drag bank statement file here"}
                </div>
                <div className="text-[11px] text-muted-foreground">
                  Supports HDFC, ICICI, SBI, Axis, Kotak CSV/Excel & scanned statements
                </div>
              </div>

              {uploadResult && (
                <div className={`p-3.5 rounded-xl border text-xs space-y-1.5 text-foreground ${
                  uploadResult.is_duplicate_file
                    ? "bg-blue-500/10 border-blue-500/30"
                    : uploadResult.balance_chain_valid
                    ? "bg-emerald-500/10 border-emerald-500/20"
                    : "bg-amber-500/10 border-amber-500/30"
                }`}>
                  <div className="font-bold flex items-center justify-between">
                    <span className={uploadResult.is_duplicate_file ? "text-blue-400" : uploadResult.balance_chain_valid ? "text-emerald-400" : "text-amber-400"}>
                      {uploadResult.is_duplicate_file ? "Duplicate Statement Detected" : "Statement Ingestion Summary"}
                    </span>
                    {uploadResult.balance_chain_valid ? (
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400">
                        ✓ Balance Chain Verified
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-400">
                        ⚠️ Balance Discrepancy (₹{uploadResult.discrepancy_amount?.toFixed(2)})
                      </span>
                    )}
                  </div>
                  {uploadResult.message && (
                    <div className="text-[11px] text-muted-foreground">{uploadResult.message}</div>
                  )}
                  <div>• Total detected rows: {uploadResult.total_detected || uploadResult.total_rows}</div>
                  <div>• Verified automatic matches: {uploadResult.auto_matched_count}</div>
                  <div>• Suggestions for review: {uploadResult.needs_review_count}</div>
                  <div>• Duplicates skipped: {uploadResult.duplicates_detected ?? uploadResult.duplicate_count ?? 0}</div>
                </div>
              )}

              <div className="flex items-center gap-3 pt-2">
                <button
                  type="button"
                  onClick={onCloseUpload}
                  className="flex-1 py-2.5 rounded-xl text-xs font-bold text-muted-foreground hover:text-foreground bg-muted hover:bg-muted/80 transition-colors cursor-pointer"
                >
                  Close
                </button>
                <button
                  type="submit"
                  disabled={isUploading || !uploadFile}
                  className="flex-1 py-2.5 rounded-xl text-xs font-bold text-primary-foreground bg-primary hover:bg-primary/90 transition-all cursor-pointer flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  {isUploading ? (
                    <>
                      <div className="w-4 h-4 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin"></div>
                      <span>Parsing Statement...</span>
                    </>
                  ) : (
                    <span>Upload & Ingest</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* LEARNED MAPPINGS DRAWER */}
      {isMappingsOpen && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div
            className="bg-card border-l border-border w-full max-w-md h-full flex flex-col p-6 shadow-2xl animate-in slide-in-from-right duration-200"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-4 border-b border-border">
              <div className="flex items-center gap-2">
                <BookOpen className="w-5 h-5 text-indigo-400" />
                <div>
                  <h3 className="text-base font-bold text-foreground">Auto-match Rules</h3>
                  <p className="text-xs text-muted-foreground">Rules for your business</p>
                </div>
              </div>
              <button
                onClick={onCloseMappings}
                className="text-muted-foreground hover:text-foreground p-1 rounded-lg cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto py-4 space-y-3">
              {loadingMappings ? (
                <div className="flex items-center justify-center p-8">
                  <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
                </div>
              ) : mappings.length === 0 ? (
                <div className="text-center p-8 space-y-2 text-muted-foreground">
                  <p className="text-xs">No learned rules yet.</p>
                  <p className="text-[11px]">
                    When you match a party in bank reconciliation, Vouch remembers the UPI ID, IFSC, or narration pattern automatically.
                  </p>
                </div>
              ) : (
                mappings.map((m) => (
                  <div
                    key={m.id}
                    className="p-3 rounded-xl bg-muted/30 border border-border/40 space-y-1.5 relative group"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-foreground">{m.party.name}</span>
                      <button
                        onClick={() => onDeleteMapping(m.id)}
                        className="text-muted-foreground hover:text-rose-400 p-1 cursor-pointer transition-colors"
                        title="Delete learned rule"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    <div className="text-[11px] font-mono text-muted-foreground break-all">
                      Pattern: {m.pattern}
                    </div>

                    <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                      <span className="px-1.5 py-0.2 rounded bg-muted font-mono">{m.mapping_type}</span>
                      <span>Used {m.usage_count} times</span>
                      <span className="text-emerald-400 font-bold">{m.confidence}% confidence</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* TRANSACTION ACTION MODAL */}
      {selectedTx && actionType && (
        <div 
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200"
          onClick={onCloseAction}
        >
          <div
            className="bg-card border border-border rounded-2xl shadow-2xl w-full max-w-md overflow-visible animate-in zoom-in-95 duration-200"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-5 border-b border-border">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-bold text-foreground">
                  {actionType === "MATCH_PARTY" &&
                    (parseFloat(selectedTx.credit_amount) > 0 ? "Confirm Customer Receipt & Save Rule" : "Confirm Supplier Payment & Save Rule")}
                  {actionType === "RECORD_PAYMENT" &&
                    (parseFloat(selectedTx.credit_amount) > 0 ? "Record Customer Receipt" : "Record Supplier Payment")}
                  {actionType === "RECORD_EXPENSE" && "Record Bank Expense"}
                  {actionType === "RECORD_TRANSFER" && "Contra Transfer (Bank / Cash)"}
                  {actionType === "OWNER_DRAWING" && "Record Owner Drawing"}
                  {actionType === "IGNORE" && "Ignore Transaction"}
                </h3>
                <button
                  onClick={onCloseAction}
                  className="text-muted-foreground hover:text-foreground p-1 rounded-lg cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <p className="text-xs text-muted-foreground mt-1 line-clamp-1">{selectedTx.description}</p>
            </div>

            <div className="p-5 space-y-4">
              {(actionType === "MATCH_PARTY" || actionType === "RECORD_PAYMENT") && (
                <div>
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider block mb-1.5">
                    Select Party
                  </label>
                  <SearchableSelect
                    value={actionTargetPartyId}
                    onChange={onTargetPartyChange}
                    options={partyOptions}
                    placeholder="-- Choose Party --"
                    searchPlaceholder="Search party name, GSTIN, phone..."
                  />
                  <div className="p-2.5 rounded-lg bg-primary/5 border border-primary/20 text-[11px] text-muted-foreground mt-2 space-y-1">
                    <div className="font-semibold text-foreground flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-primary" />
                      <span>Auto-Allocation Rule</span>
                    </div>
                    <p>
                      {parseFloat(selectedTx.credit_amount) > 0
                        ? "Incoming customer receipt will be safely applied to oldest unpaid sales invoices (FIFO) or matching invoice references under concurrency locks. Any excess remains an advance balance."
                        : "Outgoing supplier payment will be safely applied to oldest unpaid purchase bills (FIFO) or matching invoice references under concurrency locks. Any excess remains an advance balance."}
                    </p>
                  </div>
                </div>
              )}

              {actionType === "RECORD_EXPENSE" && (
                <div>
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider block mb-1.5">
                    Select Expense Ledger
                  </label>
                  <SearchableSelect
                    value={actionExpenseLedgerId}
                    onChange={onExpenseLedgerChange}
                    options={expenseOptions}
                    placeholder="-- Choose Expense Account --"
                    searchPlaceholder="Search expense category or ledger..."
                  />
                </div>
              )}

              {actionType === "RECORD_TRANSFER" && (
                <div>
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider block mb-1.5">
                    Transfer Account (Bank / Cash)
                  </label>
                  <SearchableSelect
                    value={actionTransferLedgerId}
                    onChange={onTransferLedgerChange}
                    options={contraOptions}
                    placeholder="-- Choose Target/Source Ledger --"
                    searchPlaceholder="Search bank or cash ledger..."
                  />
                </div>
              )}

              <div>
                <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider block mb-1.5">
                  {actionType === "IGNORE" ? "Reason for Ignoring" : "Remarks / Narration"}
                </label>
                <input
                  type="text"
                  value={actionRemarks}
                  onChange={(e) => onRemarksChange(e.target.value)}
                  placeholder={
                    actionType === "IGNORE"
                      ? "e.g. Personal transfer, reversal duplicate"
                      : "Optional remarks for accounting ledger"
                  }
                  className="w-full bg-muted/40 border border-border/60 rounded-xl px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>

              <div className="flex items-center gap-3 pt-2">
                <button
                  onClick={onCloseAction}
                  className="flex-1 py-2.5 rounded-xl text-xs font-bold text-muted-foreground hover:text-foreground bg-muted hover:bg-muted/80 transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  onClick={onSubmitAction}
                  disabled={actionLoading}
                  className="flex-1 py-2.5 rounded-xl text-xs font-bold text-primary-foreground bg-primary hover:bg-primary/90 transition-all cursor-pointer flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  {actionLoading ? (
                    <>
                      <div className="w-4 h-4 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin"></div>
                      <span>Processing...</span>
                    </>
                  ) : (
                    <span>Confirm & Reconcile</span>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* STATEMENT HISTORY & DELETE MODAL */}
      {isStatementsModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-card border border-border/60 rounded-2xl max-w-2xl w-full shadow-2xl overflow-hidden flex flex-col max-h-[85vh]">
            <div className="px-6 py-4 border-b border-border/40 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-blue-500/10 text-blue-400">
                  <Layers className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-foreground">Upload History</h3>
                  <p className="text-xs text-muted-foreground">
                    Manage previously uploaded statements
                  </p>
                </div>
              </div>
              <button
                onClick={onCloseStatements}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-3 flex-1">
              {loadingStatements ? (
                <div className="py-12 flex flex-col items-center justify-center space-y-3">
                  <RefreshCw className="w-6 h-6 animate-spin text-primary" />
                  <span className="text-xs text-muted-foreground">Loading statement history...</span>
                </div>
              ) : statementsList.length === 0 ? (
                <div className="py-12 text-center text-muted-foreground text-xs">
                  No statements uploaded yet for this bank account.
                </div>
              ) : (
                statementsList.map((stmt) => (
                  <div
                    key={stmt.id}
                    className="bg-muted/30 border border-border/40 rounded-xl p-4 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 hover:border-border/60 transition-all"
                  >
                    <div className="space-y-1 min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-bold text-foreground truncate max-w-xs">
                          {stmt.source_file_name}
                        </span>
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-primary/10 text-primary border border-primary/20">
                          {stmt.file_format}
                        </span>
                        {stmt.is_excluded ? (
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-muted text-muted-foreground border border-border">
                            EXCLUDED
                          </span>
                        ) : (
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${
                              stmt.status === "COMPLETED"
                                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                                : "bg-amber-500/10 text-amber-400 border-amber-500/20"
                            }`}
                          >
                            {stmt.status}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-3 text-[11px] text-muted-foreground flex-wrap">
                        <span>Bank: <strong className="text-foreground">{stmt.bank_ledger?.name}</strong></span>
                        <span>•</span>
                        <span>Uploaded: {new Date(stmt.created_at).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
                        <span>•</span>
                        <span>Rows: <strong className="text-foreground">{stmt.successful_rows}/{stmt.total_rows}</strong></span>
                      </div>

                      {(stmt.opening_balance || stmt.closing_balance) && (
                        <div className="text-[11px] font-mono text-muted-foreground">
                          Bal: ₹{parseFloat(stmt.opening_balance || "0").toLocaleString("en-IN", { minimumFractionDigits: 2 })} → ₹{parseFloat(stmt.closing_balance || "0").toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </div>
                      )}

                      {stmt.is_excluded && stmt.exclusion_reason && (
                        <div className="text-[11px] text-amber-500 font-medium flex items-center gap-1 mt-1">
                          <EyeOff className="w-3 h-3" />
                          <span>Excluded: {stmt.exclusion_reason}</span>
                        </div>
                      )}
                    </div>

                    {stmt.is_excluded ? (
                      <button
                        onClick={() => onRestoreStatement(stmt)}
                        className="px-3 py-2 rounded-xl text-xs font-bold text-primary hover:bg-primary/10 border border-primary/20 transition-all cursor-pointer flex items-center gap-1.5 w-full sm:w-auto justify-center"
                      >
                        Restore Statement
                      </button>
                    ) : (
                      <button
                        onClick={() => onExcludeStatement(stmt)}
                        className="px-3 py-2 rounded-xl text-xs font-bold text-amber-500 hover:text-amber-400 hover:bg-amber-500/10 border border-amber-500/20 transition-all cursor-pointer flex items-center gap-1.5 w-full sm:w-auto justify-center"
                        title="Exclude statement from books and reverse linked vouchers"
                      >
                        <EyeOff className="w-3.5 h-3.5" />
                        <span>Exclude Statement</span>
                      </button>
                    )}
                  </div>
                ))
              )}
            </div>

            <div className="px-6 py-3.5 border-t border-border/40 bg-muted/20 flex justify-end">
              <button
                onClick={onCloseStatements}
                className="px-4 py-2 rounded-xl text-xs font-bold text-foreground bg-muted hover:bg-muted/80 transition-colors cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* AUDITED EXCLUSION MODAL */}
      {(txToExclude || stmtToExclude) && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200"
          onClick={onCloseExclusion}
        >
          <div
            className="bg-card border border-border rounded-2xl shadow-2xl w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-5 border-b border-border/40">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="p-2 rounded-xl bg-amber-500/10 text-amber-400">
                    <EyeOff className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-foreground">
                      {txToExclude ? "Exclude Transaction from Books" : "Exclude Statement from Books"}
                    </h3>
                    <p className="text-xs text-muted-foreground">
                      Audited financial exclusion (non-destructive)
                    </p>
                  </div>
                </div>
                <button
                  onClick={onCloseExclusion}
                  className="text-muted-foreground hover:text-foreground p-1 rounded-lg cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="p-5 space-y-4">
              <div className="p-3.5 rounded-xl bg-muted/40 border border-border/40 text-xs space-y-1.5">
                <div className="font-bold text-foreground">
                  {txToExclude ? txToExclude.description : stmtToExclude?.source_file_name}
                </div>
                {txToExclude && (
                  <div className="flex items-center justify-between text-[11px] font-mono text-muted-foreground">
                    <span>Date: {txToExclude.transaction_date}</span>
                    <span className="font-bold text-foreground">
                      ₹{parseFloat(parseFloat(txToExclude.credit_amount) > 0 ? txToExclude.credit_amount : txToExclude.debit_amount).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                )}
                <p className="text-[11px] text-muted-foreground">
                  This preserves the raw banking record for audit compliance while removing it from company financial statements. Any auto-created voucher is canonically reversed with a REV- voucher.
                </p>
              </div>

              <div>
                <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider block mb-1.5">
                  Reason for Exclusion
                </label>
                <div className="grid grid-cols-2 gap-2 mb-2">
                  {["Personal transaction", "Contra duplicate", "Non-business fee", "Wrong account"].map((preset) => (
                    <button
                      key={preset}
                      type="button"
                      onClick={() => onExclusionReasonChange(preset)}
                      className={`px-2.5 py-1.5 rounded-lg text-xs font-medium border transition-all cursor-pointer text-left truncate ${
                        exclusionReasonInput === preset
                          ? "bg-primary/10 border-primary/40 text-primary font-bold"
                          : "bg-muted/40 border-border/40 text-muted-foreground hover:text-foreground hover:bg-muted"
                      }`}
                    >
                      {preset}
                    </button>
                  ))}
                </div>
                <input
                  type="text"
                  value={exclusionReasonInput}
                  onChange={(e) => onExclusionReasonChange(e.target.value)}
                  placeholder="Enter custom exclusion reason..."
                  className="w-full bg-muted/40 border border-border/60 rounded-xl px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>

              <div className="flex items-center gap-3 pt-2">
                <button
                  type="button"
                  onClick={onCloseExclusion}
                  className="flex-1 py-2.5 rounded-xl text-xs font-bold text-muted-foreground hover:text-foreground bg-muted hover:bg-muted/80 transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={txToExclude ? onSubmitExcludeTransaction : onSubmitExcludeStatement}
                  disabled={isExclusionSubmitting}
                  className="flex-1 py-2.5 rounded-xl text-xs font-bold text-white bg-amber-600 hover:bg-amber-700 transition-all cursor-pointer flex items-center justify-center gap-2 disabled:opacity-50 shadow-md shadow-amber-600/20"
                >
                  {isExclusionSubmitting ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                      <span>Excluding...</span>
                    </>
                  ) : (
                    <span>Confirm Exclusion</span>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* CONFIRMATION MODAL */}
      <ConfirmModal
        isOpen={confirmModalConfig.isOpen}
        onClose={onCloseConfirm}
        onConfirm={confirmModalConfig.onConfirm}
        title={confirmModalConfig.title}
        description={confirmModalConfig.description}
        confirmText={confirmModalConfig.confirmText}
        variant={confirmModalConfig.variant}
        isLoading={confirmModalConfig.isLoading}
      />
    </>
  );
}
