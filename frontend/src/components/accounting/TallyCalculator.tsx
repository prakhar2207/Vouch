"use client";
import React, { useState, useEffect, useRef } from "react";
import { useShortcuts } from "@/context/ShortcutContext";
import { 
  Calculator, 
  X, 
  Copy, 
  Check, 
  Delete, 
  ArrowDownToLine, 
  History, 
  RotateCcw,
  Sparkles,
  ChevronDown,
  ChevronUp
} from "lucide-react";

interface HistoryItem {
  expression: string;
  result: string;
  timestamp: string;
}

export default function TallyCalculator() {
  const { isCalculatorOpen, setIsCalculatorOpen } = useShortcuts();
  const [expression, setExpression] = useState("");
  const [result, setResult] = useState<number | null>(null);
  const [breakdown, setBreakdown] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [showHistory, setShowHistory] = useState(false);
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

  // Commercial / Accounting Mathematical Evaluator
  const evaluateAccountingExpr = (raw: string): { val: number | null; breakdownText: string | null } => {
    if (!raw) return { val: null, breakdownText: null };
    let expr = raw.toString().replace(/,/g, "").replace(/×/g, "*").replace(/÷/g, "/").trim();
    if (!expr) return { val: null, breakdownText: null };

    let detectedBreakdown: string | null = null;

    // Handle commercial percentages:
    // A + B% = A + (A * B / 100)
    // A - B% = A - (A * B / 100)
    // A * B% = A * (B / 100)
    // A / B% = A / (B / 100)
    let safety = 0;
    while (expr.includes("%") && safety < 10) {
      safety++;
      const match = expr.match(/(.+?)\s*([+\-*/])\s*(\d+(?:\.\d+)?)\s*%/);
      if (match) {
        const fullMatch = match[0];
        const leftPart = match[1].trim();
        const op = match[2];
        const pct = parseFloat(match[3]);

        if (op === "+" || op === "-") {
          try {
            // eslint-disable-next-line no-new-func
            const leftVal = Function(`"use strict"; return (${leftPart})`)();
            if (typeof leftVal === "number" && !isNaN(leftVal)) {
              const pctAmount = (leftVal * pct) / 100;
              const formattedBase = leftVal.toLocaleString("en-IN", { maximumFractionDigits: 2 });
              const formattedPct = pctAmount.toLocaleString("en-IN", { maximumFractionDigits: 2 });

              if (op === "+") {
                detectedBreakdown = `Base: ₹${formattedBase} | +${pct}%: ₹${formattedPct}`;
                expr = expr.replace(fullMatch, `(${leftPart} + ${pctAmount})`);
              } else {
                detectedBreakdown = `Gross: ₹${formattedBase} | -${pct}%: -₹${formattedPct}`;
                expr = expr.replace(fullMatch, `(${leftPart} - ${pctAmount})`);
              }
              continue;
            }
          } catch {
            expr = expr.replace(fullMatch, `(${leftPart} ${op} ((${leftPart}) * ${pct} / 100))`);
            continue;
          }
        } else if (op === "*") {
          expr = expr.replace(fullMatch, `(${leftPart} * (${pct} / 100))`);
          continue;
        } else if (op === "/") {
          expr = expr.replace(fullMatch, `(${leftPart} / (${pct} / 100))`);
          continue;
        }
      }

      // Standalone percentage, e.g. "15%"
      expr = expr.replace(/(\d+(?:\.\d+)?)\s*%/g, "($1 / 100)");
      break;
    }

    // Check for reverse GST division, e.g. [amount] / 1.18
    const reverseGstMatch = expr.match(/(.+?)\s*\/\s*1\.(18|12|05|28)\b/);
    if (reverseGstMatch && !detectedBreakdown) {
      try {
        // eslint-disable-next-line no-new-func
        const grossVal = Function(`"use strict"; return (${reverseGstMatch[1].trim()})`)();
        const rate = parseInt(reverseGstMatch[2], 10);
        if (typeof grossVal === "number" && !isNaN(grossVal)) {
          const baseVal = grossVal / (1 + rate / 100);
          const taxVal = grossVal - baseVal;
          detectedBreakdown = `Gross: ₹${grossVal.toLocaleString("en-IN", { maximumFractionDigits: 2 })} | Base: ₹${baseVal.toLocaleString("en-IN", { maximumFractionDigits: 2 })} | Tax: ₹${taxVal.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
        }
      } catch {
        // ignore
      }
    }

    // Sanitize math tokens: only allow numbers, operators, parentheses, dot, space
    if (!/^[0-9+\-*/().\s]+$/.test(expr)) {
      return { val: null, breakdownText: null };
    }

    try {
      // eslint-disable-next-line no-new-func
      const val = Function(`"use strict"; return (${expr})`)();
      if (typeof val === "number" && !isNaN(val) && isFinite(val)) {
        return { val, breakdownText: detectedBreakdown };
      }
      return { val: null, breakdownText: null };
    } catch {
      return { val: null, breakdownText: null };
    }
  };

  const handleInputChange = (newVal: string) => {
    setExpression(newVal);
    const { val, breakdownText } = evaluateAccountingExpr(newVal);
    setResult(val);
    setBreakdown(breakdownText);
  };

  const handleCalculate = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!expression.trim()) return;

    const { val } = evaluateAccountingExpr(expression);
    if (val !== null) {
      setResult(val);
      const formattedRes = val.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      const timeStr = new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
      setHistory(prev => [
        { expression, result: formattedRes, timestamp: timeStr },
        ...prev.slice(0, 9)
      ]);
    }
  };

  // Append key or operator
  const appendKey = (key: string) => {
    let nextExpr = expression;
    if (result !== null && (key === "+" || key === "-" || key === "×" || key === "÷" || key === "%")) {
      // Continue from previous calculated result
      if (!expression.trim() || expression === result.toString()) {
        nextExpr = result.toString();
      }
    }
    const updated = nextExpr + key;
    handleInputChange(updated);
    inputRef.current?.focus();
  };

  const handleClear = () => {
    setExpression("");
    setResult(null);
    setBreakdown(null);
    inputRef.current?.focus();
  };

  const handleBackspace = () => {
    const updated = expression.slice(0, -1);
    handleInputChange(updated);
    inputRef.current?.focus();
  };

  // Wholesale quick GST formulas: Clean expressions without raw math code!
  const applyWholesaleTool = (action: string) => {
    const currentBase = result !== null ? result.toString() : (expression.trim() || "0");
    if (!currentBase || currentBase === "0") {
      inputRef.current?.focus();
      return;
    }

    let updated = "";
    if (action === "+18") {
      updated = `${currentBase} + 18%`;
    } else if (action === "-18_base") {
      // Reverse GST calculation: Gross / 1.18
      updated = `${currentBase} / 1.18`;
    } else if (action === "+12") {
      updated = `${currentBase} + 12%`;
    } else if (action === "+5") {
      updated = `${currentBase} + 5%`;
    } else if (action === "+28") {
      updated = `${currentBase} + 28%`;
    } else if (action === "-5_disc") {
      updated = `${currentBase} - 5%`;
    } else if (action === "+25_margin") {
      updated = `${currentBase} + 25%`;
    } else if (action === "round") {
      const curNum = result !== null ? result : parseFloat(currentBase);
      if (!isNaN(curNum)) {
        updated = Math.round(curNum).toString();
      }
    }

    if (updated) {
      handleInputChange(updated);
      const { val } = evaluateAccountingExpr(updated);
      if (val !== null) {
        setResult(val);
        const formattedRes = val.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        const timeStr = new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
        setHistory(prev => [
          { expression: updated, result: formattedRes, timestamp: timeStr },
          ...prev.slice(0, 9)
        ]);
      }
      inputRef.current?.focus();
    }
  };

  const handleCopyOrInsert = () => {
    if (result === null) return;
    const finalVal = parseFloat(result.toFixed(2)).toString();

    if (navigator.clipboard) {
      navigator.clipboard.writeText(finalVal);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }

    // Insert directly into the focused invoice/voucher input if one was active
    if (lastActiveInputRef.current) {
      const el = lastActiveInputRef.current;
      el.value = finalVal;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      setIsCalculatorOpen(false);
      el.focus();
    }
  };

  const formattedResult = result !== null
    ? `₹${result.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : null;

  return (
    <div className="fixed bottom-5 right-5 z-50 w-[380px] max-w-[calc(100vw-1.5rem)] bg-zinc-900/95 dark:bg-zinc-950/95 backdrop-blur-2xl border border-zinc-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col text-zinc-100 ring-1 ring-white/10 animate-in fade-in slide-in-from-bottom-5 duration-200">
      
      {/* Header Bar */}
      <div className="px-4 py-2.5 bg-zinc-950/80 border-b border-zinc-800/80 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center justify-center font-bold">
            <Calculator className="w-3.5 h-3.5" />
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-bold text-zinc-100 tracking-wide">Tally Calculator</span>
            <kbd className="px-1.5 py-0.2 bg-zinc-800 text-[10px] font-mono border border-zinc-700 rounded text-zinc-300">
              Alt+N
            </kbd>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setShowHistory(!showHistory)}
            className={`p-1.5 rounded-lg text-xs transition-colors cursor-pointer ${
              showHistory ? "bg-zinc-800 text-emerald-400" : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60"
            }`}
            title="Toggle Calculation Tape"
          >
            <History className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={() => setIsCalculatorOpen(false)}
            className="text-zinc-400 hover:text-zinc-100 p-1.5 rounded-lg hover:bg-zinc-800/80 transition-colors cursor-pointer"
            title="Close (Esc or Alt+N)"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* OLED Screen & Primary Display */}
      <div className="p-3.5 bg-black/60 border-b border-zinc-800/80">
        <form onSubmit={handleCalculate} className="space-y-1">
          {/* Top tape preview */}
          <div className="text-[11px] font-mono text-zinc-400 text-right min-h-[16px] truncate">
            {history[0] ? `${history[0].expression} = ₹${history[0].result}` : "Ready • Supports +, -, *, /, % (e.g. 15220 + 18%)"}
          </div>

          {/* Active Expression Input */}
          <div className="relative">
            <input
              ref={inputRef}
              type="text"
              value={expression}
              onChange={e => handleInputChange(e.target.value)}
              placeholder="0.00"
              className="w-full bg-transparent border-b border-zinc-700/60 focus:border-emerald-500 py-1.5 text-right font-mono font-bold text-2xl text-zinc-100 focus:outline-none tracking-tight tabular-nums"
              autoFocus
            />
          </div>

          {/* Live Result & Smart Breakdown */}
          <div className="pt-1.5 flex flex-col gap-1">
            {formattedResult ? (
              <div className="flex items-baseline justify-between">
                <span className="text-[11px] uppercase font-bold tracking-wider text-zinc-400">Total:</span>
                <span className="font-mono font-extrabold text-2xl text-emerald-400 tabular-nums tracking-tight">
                  {formattedResult}
                </span>
              </div>
            ) : (
              <div className="flex items-baseline justify-between text-zinc-500">
                <span className="text-[11px] uppercase font-bold tracking-wider">Result:</span>
                <span className="font-mono font-bold text-xl tabular-nums">₹0.00</span>
              </div>
            )}

            {/* Smart GST / Percentage Breakdown */}
            {breakdown && (
              <div className="px-2 py-1 bg-emerald-950/40 border border-emerald-500/20 rounded-md text-[11px] font-mono text-emerald-300 text-right truncate">
                {breakdown}
              </div>
            )}
          </div>
        </form>
      </div>

      {/* Primary Action Buttons */}
      <div className="p-2.5 bg-zinc-950/60 border-b border-zinc-800/60 flex items-center gap-2">
        <button
          type="button"
          onClick={handleCopyOrInsert}
          disabled={result === null}
          className={`flex-1 py-2 px-3 rounded-xl font-semibold text-xs flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
            result !== null
              ? "bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/30"
              : "bg-zinc-800 text-zinc-500 cursor-not-allowed"
          }`}
          title="Insert into currently focused voucher field"
        >
          <ArrowDownToLine className="w-3.5 h-3.5" />
          <span>Insert into Voucher</span>
          <kbd className="text-[9px] bg-black/30 px-1 py-0.2 rounded font-mono">↵ Enter</kbd>
        </button>

        <button
          type="button"
          onClick={handleCopyOrInsert}
          disabled={result === null}
          className="py-2 px-3 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer border border-zinc-700/60"
          title="Copy to clipboard"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          <span>{copied ? "Copied" : "Copy"}</span>
        </button>
      </div>

      {/* Wholesale Counter GST Tools */}
      <div className="p-2.5 bg-zinc-900/90 border-b border-zinc-800/60">
        <div className="text-[10px] uppercase font-bold tracking-wider text-zinc-400 mb-1.5 flex items-center justify-between">
          <span>⚡ Wholesale Counter Shortcuts</span>
          <span className="text-[9px] text-emerald-400 font-mono">Auto-Formulas</span>
        </div>
        <div className="grid grid-cols-4 gap-1.5 text-xs font-mono">
          <button
            type="button"
            onClick={() => applyWholesaleTool("+18")}
            className="px-1.5 py-1.5 bg-blue-950/40 hover:bg-blue-900/50 text-blue-300 border border-blue-700/50 rounded-lg font-bold text-[11px] cursor-pointer text-center transition-colors"
            title="Add 18% GST (Base + 18%)"
          >
            +18% GST
          </button>
          <button
            type="button"
            onClick={() => applyWholesaleTool("-18_base")}
            className="px-1.5 py-1.5 bg-amber-950/40 hover:bg-amber-900/50 text-amber-300 border border-amber-700/50 rounded-lg font-bold text-[11px] cursor-pointer text-center transition-colors"
            title="Reverse GST: Extract base from gross (Gross ÷ 1.18)"
          >
            -18% Base
          </button>
          <button
            type="button"
            onClick={() => applyWholesaleTool("+12")}
            className="px-1.5 py-1.5 bg-emerald-950/40 hover:bg-emerald-900/50 text-emerald-300 border border-emerald-700/50 rounded-lg font-bold text-[11px] cursor-pointer text-center transition-colors"
            title="Add 12% GST"
          >
            +12% GST
          </button>
          <button
            type="button"
            onClick={() => applyWholesaleTool("+5")}
            className="px-1.5 py-1.5 bg-purple-950/40 hover:bg-purple-900/50 text-purple-300 border border-purple-700/50 rounded-lg font-bold text-[11px] cursor-pointer text-center transition-colors"
            title="Add 5% GST"
          >
            +5% GST
          </button>

          <button
            type="button"
            onClick={() => applyWholesaleTool("+28")}
            className="px-1.5 py-1.5 bg-rose-950/40 hover:bg-rose-900/50 text-rose-300 border border-rose-700/50 rounded-lg font-bold text-[11px] cursor-pointer text-center transition-colors"
            title="Add 28% GST (Automotive / High Tax)"
          >
            +28% GST
          </button>
          <button
            type="button"
            onClick={() => applyWholesaleTool("-5_disc")}
            className="px-1.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 rounded-lg font-bold text-[11px] cursor-pointer text-center transition-colors"
            title="Subtract 5% Cash Discount (-5%)"
          >
            -5% Disc
          </button>
          <button
            type="button"
            onClick={() => applyWholesaleTool("+25_margin")}
            className="px-1.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 rounded-lg font-bold text-[11px] cursor-pointer text-center transition-colors"
            title="Add standard 25% wholesale margin"
          >
            +25% Margin
          </button>
          <button
            type="button"
            onClick={() => applyWholesaleTool("round")}
            className="px-1.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 rounded-lg font-bold text-[11px] cursor-pointer text-center transition-colors"
            title="Round to nearest Rupee (₹1.00)"
          >
            Round ₹
          </button>
        </div>
      </div>

      {/* Interactive Keypad (Compact Numpad) */}
      <div className="p-2.5 bg-zinc-950/40 border-b border-zinc-800/60">
        <div className="grid grid-cols-4 gap-1.5 font-mono text-sm font-semibold">
          <button
            type="button"
            onClick={handleClear}
            className="py-2 rounded-lg bg-zinc-800/80 hover:bg-zinc-700 text-rose-400 font-bold cursor-pointer transition-colors"
          >
            AC
          </button>
          <button
            type="button"
            onClick={handleBackspace}
            className="py-2 rounded-lg bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 flex items-center justify-center cursor-pointer transition-colors"
          >
            <Delete className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => appendKey("%")}
            className="py-2 rounded-lg bg-zinc-800/80 hover:bg-zinc-700 text-emerald-400 font-bold cursor-pointer transition-colors"
          >
            %
          </button>
          <button
            type="button"
            onClick={() => appendKey("÷")}
            className="py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-blue-400 font-bold cursor-pointer transition-colors text-base"
          >
            ÷
          </button>

          <button
            type="button"
            onClick={() => appendKey("7")}
            className="py-2 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-200 border border-zinc-800 cursor-pointer transition-colors"
          >
            7
          </button>
          <button
            type="button"
            onClick={() => appendKey("8")}
            className="py-2 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-200 border border-zinc-800 cursor-pointer transition-colors"
          >
            8
          </button>
          <button
            type="button"
            onClick={() => appendKey("9")}
            className="py-2 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-200 border border-zinc-800 cursor-pointer transition-colors"
          >
            9
          </button>
          <button
            type="button"
            onClick={() => appendKey("×")}
            className="py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-blue-400 font-bold cursor-pointer transition-colors text-base"
          >
            ×
          </button>

          <button
            type="button"
            onClick={() => appendKey("4")}
            className="py-2 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-200 border border-zinc-800 cursor-pointer transition-colors"
          >
            4
          </button>
          <button
            type="button"
            onClick={() => appendKey("5")}
            className="py-2 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-200 border border-zinc-800 cursor-pointer transition-colors"
          >
            5
          </button>
          <button
            type="button"
            onClick={() => appendKey("6")}
            className="py-2 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-200 border border-zinc-800 cursor-pointer transition-colors"
          >
            6
          </button>
          <button
            type="button"
            onClick={() => appendKey("-")}
            className="py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-blue-400 font-bold cursor-pointer transition-colors text-base"
          >
            -
          </button>

          <button
            type="button"
            onClick={() => appendKey("1")}
            className="py-2 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-200 border border-zinc-800 cursor-pointer transition-colors"
          >
            1
          </button>
          <button
            type="button"
            onClick={() => appendKey("2")}
            className="py-2 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-200 border border-zinc-800 cursor-pointer transition-colors"
          >
            2
          </button>
          <button
            type="button"
            onClick={() => appendKey("3")}
            className="py-2 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-200 border border-zinc-800 cursor-pointer transition-colors"
          >
            3
          </button>
          <button
            type="button"
            onClick={() => appendKey("+")}
            className="py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-blue-400 font-bold cursor-pointer transition-colors text-base"
          >
            +
          </button>

          <button
            type="button"
            onClick={() => appendKey("0")}
            className="py-2 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-200 border border-zinc-800 cursor-pointer transition-colors"
          >
            0
          </button>
          <button
            type="button"
            onClick={() => appendKey(".")}
            className="py-2 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-200 border border-zinc-800 cursor-pointer transition-colors"
          >
            .
          </button>
          <button
            type="button"
            onClick={() => appendKey("00")}
            className="py-2 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-400 border border-zinc-800 cursor-pointer transition-colors text-xs"
          >
            00
          </button>
          <button
            type="button"
            onClick={() => handleCalculate()}
            className="py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold cursor-pointer transition-colors text-base"
          >
            =
          </button>
        </div>
      </div>

      {/* Calculation Tape (Drawer) */}
      {showHistory && (
        <div className="p-3 bg-zinc-950 max-h-44 overflow-y-auto space-y-1.5 border-b border-zinc-800">
          <div className="text-[10px] uppercase font-bold tracking-wider text-zinc-400 mb-1 flex items-center justify-between">
            <span>Calculation Tape</span>
            <button 
              type="button"
              onClick={() => setHistory([])}
              className="text-[10px] text-zinc-500 hover:text-rose-400 cursor-pointer"
            >
              Clear Tape
            </button>
          </div>
          {history.length === 0 ? (
            <div className="text-center py-3 text-zinc-500 text-xs italic">
              No previous calculations recorded
            </div>
          ) : (
            history.map((h, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => {
                  setExpression(h.result.replace(/,/g, ""));
                  handleInputChange(h.result.replace(/,/g, ""));
                }}
                className="w-full text-left px-2.5 py-1.5 rounded-lg hover:bg-zinc-900 flex items-center justify-between font-mono text-xs cursor-pointer transition-colors group border border-transparent hover:border-zinc-800"
              >
                <span className="text-zinc-400 group-hover:text-zinc-200 truncate">{h.expression}</span>
                <span className="font-bold text-emerald-400 ml-2 whitespace-nowrap">₹{h.result}</span>
              </button>
            ))
          )}
        </div>
      )}

      {/* Footer shortcut hint */}
      <div className="px-3.5 py-2 bg-zinc-950/80 border-t border-zinc-800/80 text-[10px] text-zinc-400 flex items-center justify-between">
        <span><kbd className="font-mono bg-zinc-800 text-zinc-300 px-1 py-0.5 rounded border border-zinc-700">Alt+N</kbd> or <kbd className="font-mono bg-zinc-800 text-zinc-300 px-1 py-0.5 rounded border border-zinc-700">Esc</kbd> to toggle</span>
        <span><kbd className="font-mono bg-zinc-800 text-zinc-300 px-1 py-0.5 rounded border border-zinc-700">Enter</kbd> to insert</span>
      </div>
    </div>
  );
}
