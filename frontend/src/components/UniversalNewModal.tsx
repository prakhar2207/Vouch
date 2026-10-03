"use client";
import React, { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  FileText,
  FilePlus,
  ShoppingCart,
  ArrowUpRight,
  ArrowDownRight,
  Receipt,
  Users,
  Package,
  Scan,
  Landmark,
  X,
  Sparkles,
  Percent,
  Scale,
  ShieldAlert,
} from "lucide-react";
import { isReadOnlyUser, canPerformAccounting } from "@/utils/auth";

interface UniversalNewModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function UniversalNewModal({ isOpen, onClose }: UniversalNewModalProps) {
  const router = useRouter();
  const modalRef = useRef<HTMLDivElement>(null);
  const previousActiveElement = useRef<HTMLElement | null>(null);
  const [isReadOnly, setIsReadOnly] = useState(false);
  const [canAccounting, setCanAccounting] = useState(true);

  useEffect(() => {
    if (typeof window !== "undefined") {
      setIsReadOnly(isReadOnlyUser());
      setCanAccounting(canPerformAccounting());
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key === "Tab" && modalRef.current) {
        const focusableElements = modalRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        if (focusableElements.length > 0) {
          const first = focusableElements[0];
          const last = focusableElements[focusableElements.length - 1];
          if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
          } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    };

    if (isOpen) {
      previousActiveElement.current = document.activeElement as HTMLElement | null;
      document.addEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "hidden";
      // Auto-focus first interactive element that is not disabled
      setTimeout(() => {
        const firstBtn = modalRef.current?.querySelector<HTMLButtonElement>(
          "button:not([aria-label='Close dialog']):not([disabled])"
        ) || modalRef.current?.querySelector<HTMLButtonElement>("button:not([disabled])");
        firstBtn?.focus();
      }, 50);
    }
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "unset";
      if (previousActiveElement.current) {
        previousActiveElement.current.focus();
      }
    };
  }, [isOpen, onClose]);

  // Click outside to close
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (modalRef.current && !modalRef.current.contains(e.target as Node)) {
      onClose();
    }
  };

  if (!isOpen) return null;

  const navigateTo = (path: string) => {
    if (isReadOnly && !path.startsWith("/banking") && !path.startsWith("/parties")) {
      return;
    }
    onClose();
    router.push(path);
  };

  return (
    <div
      onClick={handleBackdropClick}
      className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-3 sm:p-4 animate-in fade-in duration-150"
    >
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="universal-new-title"
        aria-describedby="universal-new-description"
        className="w-full max-w-2xl bg-card border border-border/80 rounded-2xl shadow-2xl p-5 sm:p-6 space-y-5 animate-in zoom-in-95 duration-150 max-h-[90vh] overflow-y-auto"
      >
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-border/60">
          <div className="space-y-0.5">
            <h2 id="universal-new-title" className="text-lg sm:text-xl font-bold text-foreground flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
              <span>Create / Record</span>
            </h2>
            <p id="universal-new-description" className="text-xs text-muted-foreground">
              Quickly record transactions, create invoices, or add items & parties.
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted/80 transition-colors cursor-pointer"
            aria-label="Close dialog"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {isReadOnly && (
          <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-700 dark:text-amber-300 text-xs flex items-center gap-2.5">
            <ShieldAlert className="w-4 h-4 shrink-0 text-amber-500" />
            <span>
              <strong>View-Only Account:</strong> You have read-only access. Transaction creation and record modifications are disabled for your user role.
            </span>
          </div>
        )}

        {/* Section 1: Invoicing & Sales (DO) */}
        <div className="space-y-2.5">
          <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground/80 flex items-center gap-1.5">
            <Receipt className="w-3.5 h-3.5 text-emerald-500" />
            <span>Sales & Billing</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            <button
              type="button"
              disabled={isReadOnly}
              onClick={() => navigateTo("/sales/new")}
              aria-label="Create Sales Invoice (Shortcut: F8)"
              className={`group text-left p-3.5 rounded-xl border border-emerald-500/20 bg-emerald-500/5 hover:bg-emerald-500/10 hover:border-emerald-500/40 transition-all flex items-start gap-3 ${
                isReadOnly ? "opacity-60 cursor-not-allowed" : "cursor-pointer"
              }`}
            >
              <div className="p-2 rounded-lg bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 shrink-0 group-hover:scale-105 transition-transform">
                <FileText className="w-5 h-5" />
              </div>
              <div>
                <div className="text-sm font-bold text-foreground flex items-center gap-2">
                  <span>Sales Invoice</span>
                  <kbd className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 font-semibold">
                    F8
                  </kbd>
                </div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  Tax invoice with GST, item barcodes, & E-way bills
                </div>
              </div>
            </button>

            <button
              type="button"
              disabled={isReadOnly}
              onClick={() => navigateTo("/sales/proforma/new")}
              aria-label="Create Quotation or Estimate"
              className={`group text-left p-3.5 rounded-xl border border-blue-500/20 bg-blue-500/5 hover:bg-blue-500/10 hover:border-blue-500/40 transition-all flex items-start gap-3 ${
                isReadOnly ? "opacity-60 cursor-not-allowed" : "cursor-pointer"
              }`}
            >
              <div className="p-2 rounded-lg bg-blue-500/15 text-blue-600 dark:text-blue-400 shrink-0 group-hover:scale-105 transition-transform">
                <FilePlus className="w-5 h-5" />
              </div>
              <div>
                <div className="text-sm font-bold text-foreground flex items-center gap-2">
                  <span>Quotation / Estimate</span>
                  <span className="text-[10px] font-semibold px-1.5 py-0.2 rounded bg-blue-500/20 text-blue-600 dark:text-blue-300">
                    Proforma
                  </span>
                </div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  Send estimates & quotes; 1-click convert to invoice
                </div>
              </div>
            </button>
          </div>
        </div>

        {/* Section 2: Purchases & Money In/Out (DO) */}
        <div className="space-y-2.5">
          <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground/80 flex items-center gap-1.5">
            <ShoppingCart className="w-3.5 h-3.5 text-blue-500" />
            <span>Purchases & Payments</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
            <button
              type="button"
              disabled={isReadOnly}
              onClick={() => navigateTo("/purchases/new")}
              aria-label="Create Purchase Bill (Shortcut: F9)"
              className={`group text-left p-3 rounded-xl border border-border/70 bg-card hover:bg-muted/60 hover:border-blue-500/40 transition-all flex flex-col justify-between ${
                isReadOnly ? "opacity-60 cursor-not-allowed" : "cursor-pointer"
              }`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <div className="p-1.5 rounded-lg bg-blue-500/15 text-blue-600 dark:text-blue-400">
                  <ShoppingCart className="w-4 h-4" />
                </div>
                <kbd className="text-[10px] font-mono px-1 py-0.2 rounded bg-muted text-muted-foreground font-semibold">
                  F9
                </kbd>
              </div>
              <div>
                <div className="text-xs sm:text-sm font-bold text-foreground">Purchase Bill</div>
                <div className="text-[11px] text-muted-foreground mt-0.5">Supplier bills & ITC tax credits</div>
              </div>
            </button>

            <button
              type="button"
              disabled={isReadOnly}
              onClick={() => navigateTo("/vouchers/new?type=RECEIPT")}
              aria-label="Receive Money (Shortcut: F6)"
              className={`group text-left p-3 rounded-xl border border-border/70 bg-card hover:bg-muted/60 hover:border-teal-500/40 transition-all flex flex-col justify-between ${
                isReadOnly ? "opacity-60 cursor-not-allowed" : "cursor-pointer"
              }`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <div className="p-1.5 rounded-lg bg-teal-500/15 text-teal-600 dark:text-teal-400">
                  <ArrowDownRight className="w-4 h-4" />
                </div>
                <kbd className="text-[10px] font-mono px-1 py-0.2 rounded bg-muted text-muted-foreground font-semibold">
                  F6
                </kbd>
              </div>
              <div>
                <div className="text-xs sm:text-sm font-bold text-foreground">Receive Money</div>
                <div className="text-[11px] text-muted-foreground mt-0.5">Customer payments & receipts</div>
              </div>
            </button>

            <button
              type="button"
              disabled={isReadOnly}
              onClick={() => navigateTo("/vouchers/new?type=PAYMENT")}
              aria-label="Pay Expense (Shortcut: F5)"
              className={`group text-left p-3 rounded-xl border border-border/70 bg-card hover:bg-muted/60 hover:border-rose-500/40 transition-all flex flex-col justify-between ${
                isReadOnly ? "opacity-60 cursor-not-allowed" : "cursor-pointer"
              }`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <div className="p-1.5 rounded-lg bg-rose-500/15 text-rose-600 dark:text-rose-400">
                  <ArrowUpRight className="w-4 h-4" />
                </div>
                <kbd className="text-[10px] font-mono px-1 py-0.2 rounded bg-muted text-muted-foreground font-semibold">
                  F5
                </kbd>
              </div>
              <div>
                <div className="text-xs sm:text-sm font-bold text-foreground">Pay / Expense</div>
                <div className="text-[11px] text-muted-foreground mt-0.5">Supplier payments & overheads</div>
              </div>
            </button>

            <button
              type="button"
              disabled={isReadOnly || !canAccounting}
              onClick={() => navigateTo("/vouchers/grid?type=JOURNAL")}
              aria-label="Journal Matrix Multi-Line (Shortcut: F7)"
              title={!canAccounting ? "Restricted: Requires Owner, Admin, or CA role" : undefined}
              className={`group text-left p-3 rounded-xl border border-primary/30 bg-primary/5 hover:bg-primary/10 hover:border-primary/50 transition-all flex flex-col justify-between ${
                isReadOnly || !canAccounting ? "opacity-60 cursor-not-allowed" : "cursor-pointer"
              }`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <div className="p-1.5 rounded-lg bg-primary/20 text-primary">
                  <Scale className="w-4 h-4" />
                </div>
                <kbd className="text-[10px] font-mono px-1 py-0.2 rounded bg-primary/20 text-primary font-bold">
                  F7
                </kbd>
              </div>
              <div>
                <div className="text-xs sm:text-sm font-bold text-foreground flex items-center gap-1.5">
                  <span>Journal Matrix</span>
                  <span className="text-[9px] bg-primary/15 text-primary px-1 rounded font-bold">Dr/Cr</span>
                </div>
                <div className="text-[11px] text-muted-foreground mt-0.5">
                  {!canAccounting ? "Requires Owner or CA" : "Multi-line adjustments & transfers"}
                </div>
              </div>
            </button>

            <button
              type="button"
              disabled={isReadOnly || !canAccounting}
              onClick={() => navigateTo("/vouchers/grid?type=CONTRA")}
              aria-label="Contra Transfer (Shortcut: F4)"
              title={!canAccounting ? "Restricted: Requires Owner, Admin, or CA role" : undefined}
              className={`group text-left p-3 rounded-xl border border-border/70 bg-card hover:bg-muted/60 hover:border-sky-500/40 transition-all flex flex-col justify-between ${
                isReadOnly || !canAccounting ? "opacity-60 cursor-not-allowed" : "cursor-pointer"
              }`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <div className="p-1.5 rounded-lg bg-sky-500/15 text-sky-600 dark:text-sky-400">
                  <Landmark className="w-4 h-4" />
                </div>
                <kbd className="text-[10px] font-mono px-1 py-0.2 rounded bg-muted text-muted-foreground font-semibold">
                  F4
                </kbd>
              </div>
              <div>
                <div className="text-xs sm:text-sm font-bold text-foreground">Contra Transfer</div>
                <div className="text-[11px] text-muted-foreground mt-0.5">Cash deposit, withdrawal, bank-to-bank</div>
              </div>
            </button>
          </div>
        </div>

        {/* Section 3: Smart Automations (AUTOMATE) */}
        <div className="space-y-2.5">
          <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground/80 flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-purple-500" />
            <span>Smart Automations</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            <button
              type="button"
              disabled={isReadOnly}
              onClick={() => navigateTo("/purchases/new?scan=1")}
              aria-label="Scan Bill using AI OCR"
              className={`group text-left p-3.5 rounded-xl border border-purple-500/20 bg-purple-500/5 hover:bg-purple-500/10 hover:border-purple-500/40 transition-all flex items-start gap-3 ${
                isReadOnly ? "opacity-60 cursor-not-allowed" : "cursor-pointer"
              }`}
            >
              <div className="p-2 rounded-lg bg-purple-500/15 text-purple-600 dark:text-purple-400 shrink-0 group-hover:scale-105 transition-transform">
                <Scan className="w-5 h-5" />
              </div>
              <div>
                <div className="text-sm font-bold text-foreground flex items-center gap-2">
                  <span>Scan Bill (AI OCR)</span>
                  <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-purple-500/20 text-purple-600 dark:text-purple-300">
                    Instant
                  </span>
                </div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  Upload a photo or PDF to extract line items & taxes
                </div>
              </div>
            </button>

            <button
              type="button"
              onClick={() => navigateTo("/banking")}
              aria-label="Import Bank Statement"
              className="group text-left p-3.5 rounded-xl border border-indigo-500/20 bg-indigo-500/5 hover:bg-indigo-500/10 hover:border-indigo-500/40 transition-all flex items-start gap-3 cursor-pointer"
            >
              <div className="p-2 rounded-lg bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 shrink-0 group-hover:scale-105 transition-transform">
                <Landmark className="w-5 h-5" />
              </div>
              <div>
                <div className="text-sm font-bold text-foreground">Import Bank Statement</div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  Upload bank CSV / Excel for automatic reconciliation
                </div>
              </div>
            </button>
          </div>
        </div>

        {/* Section 4: Quick Add Masters */}
        <div className="pt-2 border-t border-border/60 flex flex-wrap items-center justify-between gap-3 text-xs">
          <span className="text-muted-foreground font-medium">Quick add to records:</span>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={isReadOnly}
              onClick={() => navigateTo("/parties")}
              aria-label="Add Party"
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border/80 bg-muted/40 hover:bg-muted text-foreground font-medium transition-colors ${
                isReadOnly ? "opacity-60 cursor-not-allowed" : "cursor-pointer"
              }`}
            >
              <Users className="w-3.5 h-3.5 text-muted-foreground" />
              <span>+ Add Party</span>
            </button>

            <button
              type="button"
              disabled={isReadOnly}
              onClick={() => navigateTo("/inventory/new")}
              aria-label="Add Product"
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border/80 bg-muted/40 hover:bg-muted text-foreground font-medium transition-colors ${
                isReadOnly ? "opacity-60 cursor-not-allowed" : "cursor-pointer"
              }`}
            >
              <Package className="w-3.5 h-3.5 text-muted-foreground" />
              <span>+ Add Product</span>
            </button>

            <button
              type="button"
              disabled={isReadOnly}
              onClick={() => navigateTo("/vouchers/credit-note")}
              aria-label="Add Credit or Debit Note"
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border/80 bg-muted/40 hover:bg-muted text-foreground font-medium transition-colors ${
                isReadOnly ? "opacity-60 cursor-not-allowed" : "cursor-pointer"
              }`}
            >
              <Percent className="w-3.5 h-3.5 text-muted-foreground" />
              <span>+ Credit / Debit Note</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
