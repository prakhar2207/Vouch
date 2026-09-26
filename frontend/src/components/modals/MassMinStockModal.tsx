"use client";

import React from "react";
import { X, Sliders, Check, ShieldAlert, Sparkles, Layers, CheckSquare, Globe } from "lucide-react";

interface MassMinStockModalProps {
  isOpen: boolean;
  onClose: () => void;
  scope: "selected" | "category" | "all";
  onScopeChange: (scope: "selected" | "category" | "all") => void;
  minStockInput: number;
  onMinStockInputChange: (val: number) => void;
  onApply: () => void;
  loading: boolean;
  selectedCount: number;
  currentCategoryName: string;
  hasCategoryFilter: boolean;
}

export default function MassMinStockModal({
  isOpen,
  onClose,
  scope,
  onScopeChange,
  minStockInput,
  onMinStockInputChange,
  onApply,
  loading,
  selectedCount,
  currentCategoryName,
  hasCategoryFilter,
}: MassMinStockModalProps) {
  if (!isOpen) return null;

  const presets = [5, 10, 15, 20, 25, 50];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-3 sm:p-4 overflow-y-auto animate-in fade-in duration-150">
      <div className="relative w-full max-w-lg bg-card border border-border/80 rounded-2xl shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border/60 bg-muted/30">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-500/10 text-blue-600 dark:text-blue-400 flex items-center justify-center font-bold">
              <Sliders className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm sm:text-base font-bold text-foreground">
                Set Minimum Required Stock (Mass-Wise)
              </h2>
              <p className="text-[11px] text-muted-foreground">
                Configure reorder threshold across selected items, category, or catalog
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={loading}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4">
          {/* Info Tip */}
          <div className="p-3 rounded-xl bg-blue-500/5 border border-blue-500/20 text-xs text-blue-600 dark:text-blue-400 flex items-start gap-2.5">
            <Sparkles className="w-4 h-4 shrink-0 mt-0.5" />
            <div>
              Any item with stock at or below this minimum quantity will automatically be flagged for urgent reorder, provided it has verified sales demand.
            </div>
          </div>

          {/* Scope Selector */}
          <div className="space-y-2">
            <label className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
              Select Scope
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              {/* Option 1: Selected Items */}
              <button
                type="button"
                onClick={() => onScopeChange("selected")}
                className={`p-3 rounded-xl border text-left transition-all cursor-pointer flex flex-col justify-between ${
                  scope === "selected"
                    ? "bg-primary/10 border-primary text-foreground shadow-2xs"
                    : "bg-muted/30 hover:bg-muted/50 border-border/60 text-muted-foreground"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <CheckSquare className="w-4 h-4 text-blue-500" />
                  {scope === "selected" && <Check className="w-3.5 h-3.5 text-primary" />}
                </div>
                <div className="font-bold text-xs text-foreground">Selected Items</div>
                <div className="text-[10px] text-muted-foreground mt-0.5">
                  {selectedCount} item(s) selected
                </div>
              </button>

              {/* Option 2: Current Category */}
              <button
                type="button"
                onClick={() => onScopeChange("category")}
                disabled={!hasCategoryFilter}
                className={`p-3 rounded-xl border text-left transition-all cursor-pointer flex flex-col justify-between ${
                  !hasCategoryFilter
                    ? "opacity-50 pointer-events-none bg-muted/20 border-border/30"
                    : scope === "category"
                    ? "bg-primary/10 border-primary text-foreground shadow-2xs"
                    : "bg-muted/30 hover:bg-muted/50 border-border/60 text-muted-foreground"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <Layers className="w-4 h-4 text-emerald-500" />
                  {scope === "category" && <Check className="w-3.5 h-3.5 text-primary" />}
                </div>
                <div className="font-bold text-xs text-foreground truncate">{currentCategoryName}</div>
                <div className="text-[10px] text-muted-foreground mt-0.5">
                  Category items
                </div>
              </button>

              {/* Option 3: Entire Catalog */}
              <button
                type="button"
                onClick={() => onScopeChange("all")}
                className={`p-3 rounded-xl border text-left transition-all cursor-pointer flex flex-col justify-between ${
                  scope === "all"
                    ? "bg-primary/10 border-primary text-foreground shadow-2xs"
                    : "bg-muted/30 hover:bg-muted/50 border-border/60 text-muted-foreground"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <Globe className="w-4 h-4 text-purple-500" />
                  {scope === "all" && <Check className="w-3.5 h-3.5 text-primary" />}
                </div>
                <div className="font-bold text-xs text-foreground">Entire Catalog</div>
                <div className="text-[10px] text-muted-foreground mt-0.5">
                  All active items
                </div>
              </button>
            </div>
          </div>

          {/* Minimum Quantity Input & Quick Presets */}
          <div className="space-y-2 pt-1">
            <label className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground flex items-center justify-between">
              <span>Minimum Required Quantity (Min Stock)</span>
              <span className="text-[10px] font-mono text-muted-foreground">Units</span>
            </label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min="0"
                value={minStockInput}
                onChange={(e) => onMinStockInputChange(Math.max(0, parseInt(e.target.value) || 0))}
                className="w-full bg-card border border-border/80 rounded-xl px-3 py-2 text-base font-mono font-bold text-foreground outline-none focus:ring-2 focus:ring-primary/40 text-center"
                placeholder="e.g. 10"
              />
            </div>

            {/* Quick Presets */}
            <div className="flex items-center gap-1.5 flex-wrap pt-1">
              <span className="text-[10px] text-muted-foreground mr-1">Quick Presets:</span>
              {presets.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => onMinStockInputChange(p)}
                  className={`px-2 py-0.5 rounded text-[11px] font-mono font-bold border transition-colors cursor-pointer ${
                    minStockInput === p
                      ? "bg-primary text-primary-foreground border-primary"
                      : "bg-muted/60 hover:bg-muted text-foreground border-border/60"
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-end gap-2.5 px-5 py-3.5 border-t border-border/60 bg-muted/20">
          <button
            type="button"
            onClick={onClose}
            disabled={loading}
            className="px-4 py-2 rounded-xl text-xs font-semibold bg-muted hover:bg-muted/80 text-foreground transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onApply}
            disabled={loading || (scope === "selected" && selectedCount === 0)}
            className="px-5 py-2 rounded-xl text-xs font-bold bg-primary hover:bg-primary/90 text-primary-foreground transition-all shadow-sm cursor-pointer disabled:opacity-50 disabled:pointer-events-none flex items-center gap-2"
          >
            {loading ? (
              <>
                <div className="w-3.5 h-3.5 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin"></div>
                <span>Applying...</span>
              </>
            ) : (
              <>
                <Check className="w-4 h-4" />
                <span>
                  Apply Min Stock ({minStockInput})
                </span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
