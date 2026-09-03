"use client";
import React, { useState, useEffect, useRef } from "react";
import { useAccountingPeriod } from "@/context/PeriodContext";
import { Calendar, ArrowRight, X, Sparkles } from "lucide-react";

export default function PeriodModal() {
  const { fromDate, toDate, setPeriod, isPeriodModalOpen, setIsPeriodModalOpen } = useAccountingPeriod();
  const [tempFrom, setTempFrom] = useState(fromDate);
  const [tempTo, setTempTo] = useState(toDate);

  const fromInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isPeriodModalOpen) {
      setTempFrom(fromDate);
      setTempTo(toDate);
      setTimeout(() => {
        fromInputRef.current?.focus();
      }, 50);
    }
  }, [isPeriodModalOpen, fromDate, toDate]);

  if (!isPeriodModalOpen) return null;

  const handleApply = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (tempFrom && tempTo) {
      setPeriod(tempFrom, tempTo);
      setIsPeriodModalOpen(false);
    }
  };

  const applyPreset = (from: string, to: string) => {
    setTempFrom(from);
    setTempTo(to);
    setPeriod(from, to);
    setIsPeriodModalOpen(false);
  };

  const today = new Date();
  const year = today.getFullYear();
  const month = today.getMonth() + 1;
  const currentStartYear = month >= 4 ? year : year - 1;

  // Presets
  const curFYFrom = `${currentStartYear}-04-01`;
  const curFYTo = `${currentStartYear + 1}-03-31`;

  const prevFYFrom = `${currentStartYear - 1}-04-01`;
  const prevFYTo = `${currentStartYear}-03-31`;

  const curMonthStart = `${year}-${String(month).padStart(2, '0')}-01`;
  const nextMonthDate = new Date(year, month, 0);
  const curMonthEnd = `${year}-${String(month).padStart(2, '0')}-${String(nextMonthDate.getDate()).padStart(2, '0')}`;

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl max-w-md w-full p-5 shadow-2xl relative animate-in fade-in zoom-in-95">
        
        {/* Close Button */}
        <button
          onClick={() => setIsPeriodModalOpen(false)}
          className="absolute top-4 right-4 text-zinc-400 hover:text-white p-1 rounded-lg hover:bg-zinc-800 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>

        {/* Header */}
        <div className="flex items-center gap-2.5 mb-4">
          <div className="w-9 h-9 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400 flex items-center justify-center">
            <Calendar className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-white">Change Period</h2>
              <kbd className="px-1.5 py-0.5 bg-zinc-800 text-zinc-300 rounded border border-zinc-700 font-mono text-[10px]">
                Alt+F2
              </kbd>
            </div>
            <p className="text-xs text-zinc-400">Continuous ledger range for reports & accounts</p>
          </div>
        </div>

        {/* Date Inputs Form */}
        <form onSubmit={handleApply} className="space-y-4">
          <div className="grid grid-cols-2 gap-3 bg-zinc-950 p-3.5 rounded-xl border border-zinc-800">
            <div>
              <label className="block text-[10px] font-bold text-zinc-400 uppercase tracking-wider mb-1">
                From Date
              </label>
              <input
                ref={fromInputRef}
                type="date"
                value={tempFrom}
                onChange={(e) => setTempFrom(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-700 text-white px-2.5 py-2 rounded-lg text-xs font-mono outline-none focus:ring-1 focus:ring-blue-500"
                required
              />
            </div>
            <div>
              <label className="block text-[10px] font-bold text-zinc-400 uppercase tracking-wider mb-1">
                To Date
              </label>
              <input
                type="date"
                value={tempTo}
                onChange={(e) => setTempTo(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-700 text-white px-2.5 py-2 rounded-lg text-xs font-mono outline-none focus:ring-1 focus:ring-blue-500"
                required
              />
            </div>
          </div>

          {/* Quick Presets */}
          <div>
            <div className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider mb-1.5">
              Quick Period Presets
            </div>
            <div className="grid grid-cols-2 gap-1.5 text-xs">
              <button
                type="button"
                onClick={() => applyPreset(curFYFrom, curFYTo)}
                className="px-2.5 py-1.5 bg-zinc-950 hover:bg-zinc-800 text-zinc-300 hover:text-white rounded-lg border border-zinc-800 text-left flex items-center justify-between transition-colors cursor-pointer"
              >
                <span>Current Financial Year</span>
                <span className="text-[10px] text-zinc-500 font-mono">FY {currentStartYear}-{String(currentStartYear + 1).slice(-2)}</span>
              </button>

              <button
                type="button"
                onClick={() => applyPreset(prevFYFrom, prevFYTo)}
                className="px-2.5 py-1.5 bg-zinc-950 hover:bg-zinc-800 text-zinc-300 hover:text-white rounded-lg border border-zinc-800 text-left flex items-center justify-between transition-colors cursor-pointer"
              >
                <span>Previous Financial Year</span>
                <span className="text-[10px] text-zinc-500 font-mono">FY {currentStartYear - 1}-{String(currentStartYear).slice(-2)}</span>
              </button>

              <button
                type="button"
                onClick={() => applyPreset(curMonthStart, curMonthEnd)}
                className="px-2.5 py-1.5 bg-zinc-950 hover:bg-zinc-800 text-zinc-300 hover:text-white rounded-lg border border-zinc-800 text-left flex items-center justify-between transition-colors cursor-pointer"
              >
                <span>Current Month</span>
                <span className="text-[10px] text-zinc-500 font-mono">30 Days</span>
              </button>

              <button
                type="button"
                onClick={() => applyPreset("2020-04-01", "2030-03-31")}
                className="px-2.5 py-1.5 bg-zinc-950 hover:bg-zinc-800 text-zinc-300 hover:text-white rounded-lg border border-zinc-800 text-left flex items-center justify-between transition-colors cursor-pointer"
              >
                <span>All-Time (Continuous)</span>
                <span className="text-[10px] text-zinc-500 font-mono">Multi-Year</span>
              </button>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2 pt-2">
            <button
              type="button"
              onClick={() => setIsPeriodModalOpen(false)}
              className="flex-1 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-xl font-bold text-xs transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex-1 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-bold text-xs shadow-md shadow-blue-600/20 transition-all flex items-center justify-center gap-1.5 cursor-pointer"
            >
              <span>Apply Period</span>
              <kbd className="px-1 py-0.2 bg-black/20 text-white/80 rounded font-mono text-[9px]">Enter</kbd>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
