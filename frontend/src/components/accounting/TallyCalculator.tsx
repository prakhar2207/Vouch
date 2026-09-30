"use client";
import React, { useState, useEffect, useRef } from "react";
import { useShortcuts } from "@/context/ShortcutContext";
import { Calculator, X, Copy, Check, CornerDownLeft, Sparkles, Percent } from "lucide-react";

interface HistoryItem {
  expression: string;
  result: string;
  timestamp: string;
}

export default function TallyCalculator() {
  const { isCalculatorOpen, setIsCalculatorOpen } = useShortcuts();
  const [expression, setExpression] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [copied, setCopied] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const lastActiveInputRef = useRef<HTMLInputElement | null>(null);

  // Auto-focus when opened and remember previous active input
  useEffect(() => {
    if (isCalculatorOpen) {
      if (document.activeElement instanceof HTMLInputElement) {
        lastActiveInputRef.current = document.activeElement;
      }
      setTimeout(() => {
        inputRef.current?.focus();
        inputRef.current?.select();
      }, 50);
    }
  }, [isCalculatorOpen]);

  if (!isCalculatorOpen) return null;

  const evaluateExpression = (expr: string): string | null => {
    try {
      // Sanitize: allow numbers, arithmetic operators, parentheses, decimal, and percentages
      const sanitized = expr
        .replace(/,/g, "")
        .replace(/×/g, "*")
        .replace(/÷/g, "/")
        .replace(/(\d+(\.\d+)?)%/g, "($1/100)");

      if (!sanitized.trim()) return null;

      // Safe evaluation of mathematical tokens only
      if (!/^[0-9+\-*/().\s]+$/.test(sanitized)) {
        return "Err: Invalid Input";
      }

      // eslint-disable-next-line no-new-func
      const evalFn = new Function(`"use strict"; return (${sanitized});`);
      const val = evalFn();
      if (typeof val === "number" && !isNaN(val) && isFinite(val)) {
        // Format nicely
        return Number.isInteger(val) ? val.toString() : parseFloat(val.toFixed(4)).toString();
      }
      return "Err";
    } catch {
      return "Err";
    }
  };

  const handleCalculate = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!expression.trim()) return;

    const res = evaluateExpression(expression);
    if (res && res !== "Err" && !res.startsWith("Err:")) {
      setResult(res);
      const timeStr = new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      setHistory(prev => [
        { expression, result: res, timestamp: timeStr },
        ...prev.slice(0, 9)
      ]);
    } else {
      setResult(res || "Err");
    }
  };

  const applyGst = (rate: number, isReverse: boolean = false) => {
    const base = result && result !== "Err" ? parseFloat(result) : parseFloat(expression);
    if (isNaN(base)) return;

    let newExpr = "";
    if (isReverse) {
      // Reverse GST calculation: Gross / (1 + rate/100)
      newExpr = `(${base} / (1 + ${rate}/100))`;
    } else {
      // Forward GST calculation: Base * (1 + rate/100)
      newExpr = `(${base} * (1 + ${rate}/100))`;
    }

    setExpression(newExpr);
    const res = evaluateExpression(newExpr);
    if (res && res !== "Err") {
      setResult(res);
      setHistory(prev => [
        { expression: isReverse ? `${base} - ${rate}% GST` : `${base} + ${rate}% GST`, result: res, timestamp: new Date().toLocaleTimeString("en-IN") },
        ...prev.slice(0, 9)
      ]);
    }
  };

  const handleCopyOrInsert = () => {
    const textToCopy = result || expression;
    if (!textToCopy || textToCopy === "Err") return;

    if (navigator.clipboard) {
      navigator.clipboard.writeText(textToCopy);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }

    // If an invoice or voucher input was active, insert value and close
    if (lastActiveInputRef.current) {
      const el = lastActiveInputRef.current;
      el.value = textToCopy;
      // Trigger native input event so React form updates
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      setIsCalculatorOpen(false);
      el.focus();
    }
  };

  return (
    <div className="fixed bottom-4 right-4 z-50 w-96 max-w-[calc(100vw-2rem)] bg-card border-2 border-primary/40 rounded-2xl shadow-2xl overflow-hidden flex flex-col animate-in fade-in slide-in-from-bottom-5 duration-200">
      {/* Header */}
      <div className="px-4 py-2.5 bg-muted/60 border-b border-border/80 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-primary/20 text-primary flex items-center justify-center font-bold">
            <Calculator className="w-3.5 h-3.5" />
          </div>
          <div>
            <h4 className="text-xs font-bold text-foreground flex items-center gap-1.5">
              <span>Tally Calculator</span>
              <kbd className="px-1.5 py-0.2 bg-muted text-[10px] font-mono border border-border rounded text-muted-foreground" title="Works via Alt+N or Ctrl+N">
                Alt+N / Ctrl+N
              </kbd>
            </h4>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setIsCalculatorOpen(false)}
            className="text-muted-foreground hover:text-foreground p-1 rounded-md hover:bg-muted transition-colors cursor-pointer"
            title="Close calculator (Esc or Ctrl+M)"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Live Display & Input */}
      <div className="p-3 bg-muted/30 border-b border-border/60">
        <form onSubmit={handleCalculate} className="space-y-1.5">
          <div className="text-[11px] font-mono text-muted-foreground text-right min-h-[16px]">
            {history[0] ? `${history[0].expression} = ${history[0].result}` : "Ready (e.g. 280 * 8, 1500 / 1.18)"}
          </div>
          <div className="relative">
            <input
              ref={inputRef}
              type="text"
              value={expression}
              onChange={e => {
                setExpression(e.target.value);
                const live = evaluateExpression(e.target.value);
                if (live && live !== "Err" && !live.startsWith("Err:")) {
                  setResult(live);
                }
              }}
              placeholder="e.g. 280 * 8 or 1250 * 0.95"
              className="w-full bg-background border border-border rounded-xl px-3 py-2 text-right font-mono font-bold text-base text-foreground focus:outline-none focus:ring-2 focus:ring-primary shadow-inner tabular-nums"
              autoFocus
            />
          </div>
          {result && (
            <div className="flex items-center justify-between pt-1">
              <span className="text-[11px] text-muted-foreground">Result:</span>
              <div className="flex items-center gap-2">
                <span className="font-mono font-black text-lg text-primary tabular-nums">
                  ₹{Number(result).toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}
                </span>
                <button
                  type="button"
                  onClick={handleCopyOrInsert}
                  className="px-2 py-0.5 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/30 rounded text-[11px] font-bold flex items-center gap-1 cursor-pointer transition-colors"
                  title="Insert into active form field or copy"
                >
                  {copied ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
                  <span>{copied ? "Copied!" : "Insert (Enter)"}</span>
                </button>
              </div>
            </div>
          )}
        </form>
      </div>

      {/* Quick GST & Wholesale Formula Badges */}
      <div className="p-2.5 bg-muted/10 border-b border-border/60">
        <div className="text-[10px] uppercase font-bold text-muted-foreground mb-1.5 flex items-center justify-between">
          <span>Quick Counter Tools</span>
          <span className="text-[9px] text-primary font-mono">1-Click GST</span>
        </div>
        <div className="grid grid-cols-4 gap-1.5 text-xs">
          <button
            type="button"
            onClick={() => applyGst(18, false)}
            className="px-1.5 py-1 bg-blue-500/10 hover:bg-blue-500/20 text-blue-500 dark:text-blue-400 border border-blue-500/30 rounded font-mono font-bold text-[11px] cursor-pointer text-center"
            title="Add 18% GST"
          >
            +18% GST
          </button>
          <button
            type="button"
            onClick={() => applyGst(18, true)}
            className="px-1.5 py-1 bg-amber-500/10 hover:bg-amber-500/20 text-amber-600 dark:text-amber-400 border border-amber-500/30 rounded font-mono font-bold text-[11px] cursor-pointer text-center"
            title="Remove 18% GST from Gross"
          >
            -18% Base
          </button>
          <button
            type="button"
            onClick={() => applyGst(12, false)}
            className="px-1.5 py-1 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 rounded font-mono font-bold text-[11px] cursor-pointer text-center"
            title="Add 12% GST"
          >
            +12% GST
          </button>
          <button
            type="button"
            onClick={() => applyGst(5, false)}
            className="px-1.5 py-1 bg-purple-500/10 hover:bg-purple-500/20 text-purple-600 dark:text-purple-400 border border-purple-500/30 rounded font-mono font-bold text-[11px] cursor-pointer text-center"
            title="Add 5% GST"
          >
            +5% GST
          </button>
        </div>
      </div>

      {/* Recent History Tape */}
      <div className="p-2.5 max-h-36 overflow-y-auto space-y-1 text-xs">
        <div className="text-[10px] uppercase font-bold text-muted-foreground px-1 mb-1">Calculation Tape</div>
        {history.length === 0 ? (
          <div className="text-center py-2 text-muted-foreground text-[11px] italic">
            Press Enter or type arithmetic expression
          </div>
        ) : (
          history.map((h, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => {
                setExpression(h.result);
                setResult(h.result);
                inputRef.current?.focus();
              }}
              className="w-full text-left px-2 py-1 rounded hover:bg-muted flex items-center justify-between font-mono text-[11px] cursor-pointer transition-colors group"
            >
              <span className="text-muted-foreground group-hover:text-foreground truncate">{h.expression}</span>
              <span className="font-bold text-foreground ml-2 whitespace-nowrap">= {h.result}</span>
            </button>
          ))
        )}
      </div>

      {/* Footer shortcut hint */}
      <div className="px-3 py-1.5 bg-muted/40 border-t border-border/60 text-[10px] text-muted-foreground flex items-center justify-between">
        <span><kbd className="font-mono bg-muted px-1 rounded border">Alt+N</kbd> / <kbd className="font-mono bg-muted px-1 rounded border">Esc</kbd> to close</span>
        <span><kbd className="font-mono bg-muted px-1 rounded border">Enter</kbd> to calculate</span>
      </div>
    </div>
  );
}
