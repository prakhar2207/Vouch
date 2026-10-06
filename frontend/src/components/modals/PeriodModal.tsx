"use client";
import React, { useState, useEffect, useRef } from "react";
import { useAccountingPeriod } from "@/context/PeriodContext";
import { useFinancialYear } from "@/context/FinancialYearContext";
import { Calendar, ArrowRight, X, Sparkles, Check } from "lucide-react";

export default function PeriodModal() {
  const { fromDate, toDate, setPeriod, isPeriodModalOpen, setIsPeriodModalOpen } = useAccountingPeriod();
  const { availableFYs, activeFY, setActiveFY } = useFinancialYear();
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
      // Two-way sync with Financial Year
      const exactFY = availableFYs.find(fy => fy.start_date === tempFrom && fy.end_date === tempTo);
      if (exactFY) {
        setActiveFY(exactFY);
      } else {
        const containingFY = availableFYs.find(fy => fy.start_date <= tempFrom && fy.end_date >= tempTo);
        if (containingFY) {
          setActiveFY(containingFY);
        }
      }
      setIsPeriodModalOpen(false);
    }
  };

  const applyFYPreset = (fy: any) => {
    setTempFrom(fy.start_date);
    setTempTo(fy.end_date);
    setPeriod(fy.start_date, fy.end_date);
    setActiveFY(fy);
    setIsPeriodModalOpen(false);
  };

  const applyCustomPreset = (from: string, to: string) => {
    setTempFrom(from);
    setTempTo(to);
    setPeriod(from, to);
    const exactFY = availableFYs.find(fy => fy.start_date === from && fy.end_date === to);
    if (exactFY) {
      setActiveFY(exactFY);
    } else {
      const containingFY = availableFYs.find(fy => fy.start_date <= from && fy.end_date >= to);
      if (containingFY) {
        setActiveFY(containingFY);
      }
    }
    setIsPeriodModalOpen(false);
  };

  const today = new Date();
  const todayStr = today.toISOString().slice(0, 10);
  const year = today.getFullYear();
  const month = today.getMonth() + 1;
  const curMonthStart = `${year}-${String(month).padStart(2, '0')}-01`;
  const nextMonthDate = new Date(year, month, 0);
  const curMonthEnd = `${year}-${String(month).padStart(2, '0')}-${String(nextMonthDate.getDate()).padStart(2, '0')}`;

  const fyStartYear = activeFY?.start_date ? parseInt(activeFY.start_date.slice(0, 4)) : (month >= 4 ? year : year - 1);
  const q1Start = `${fyStartYear}-04-01`;
  const q1End = `${fyStartYear}-06-30`;
  const q2Start = `${fyStartYear}-07-01`;
  const q2End = `${fyStartYear}-09-30`;
  const q3Start = `${fyStartYear}-10-01`;
  const q3End = `${fyStartYear}-12-31`;
  const q4Start = `${fyStartYear + 1}-01-01`;
  const q4End = `${fyStartYear + 1}-03-31`;

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-2xl max-w-md w-full p-5 shadow-2xl relative animate-in fade-in zoom-in-95">
        
        {/* Close Button */}
        <button
          onClick={() => setIsPeriodModalOpen(false)}
          className="absolute top-4 right-4 text-muted-foreground hover:text-foreground p-1 rounded-lg hover:bg-muted transition-colors cursor-pointer"
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
              <h2 className="text-base font-bold text-foreground">Change Period</h2>
              <kbd className="px-1.5 py-0.5 bg-muted text-muted-foreground rounded border border-border font-mono text-[10px]">
                Alt+F2
              </kbd>
            </div>
            <p className="text-xs text-muted-foreground">Select a financial year or custom date range</p>
          </div>
        </div>

        {/* Date Inputs Form */}
        <form onSubmit={handleApply} className="space-y-4">
          <div className="grid grid-cols-2 gap-3 bg-muted/40 p-3.5 rounded-xl border border-border">
            <div>
              <label className="block text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-1">
                From Date
              </label>
              <input
                ref={fromInputRef}
                type="date"
                value={tempFrom}
                onChange={(e) => setTempFrom(e.target.value)}
                className="w-full bg-background border border-input text-foreground px-2.5 py-2 rounded-lg text-xs font-mono outline-none focus:ring-1 focus:ring-primary"
                required
              />
            </div>
            <div>
              <label className="block text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-1">
                To Date
              </label>
              <input
                type="date"
                value={tempTo}
                onChange={(e) => setTempTo(e.target.value)}
                className="w-full bg-background border border-input text-foreground px-2.5 py-2 rounded-lg text-xs font-mono outline-none focus:ring-1 focus:ring-primary"
                required
              />
            </div>
          </div>

          {/* Quick Presets */}
          <div>
            <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-1.5">
              Financial Years & Presets
            </div>
            <div className="grid grid-cols-2 gap-1.5 text-xs max-h-48 overflow-y-auto">
              {availableFYs.map((fy) => {
                const isCurrent = activeFY?.id === fy.id;
                return (
                  <button
                    key={fy.id}
                    type="button"
                    onClick={() => applyFYPreset(fy)}
                    className={`px-2.5 py-2 rounded-lg border text-left flex items-center justify-between transition-colors cursor-pointer ${
                      isCurrent
                        ? "bg-primary/15 border-primary/40 text-primary font-semibold"
                        : "bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground border-border"
                    }`}
                  >
                    <div className="flex flex-col">
                      <span className="text-xs">{fy.name || `FY ${fy.code}`}</span>
                      <span className="text-[9px] text-muted-foreground font-mono">{fy.code}</span>
                    </div>
                    {isCurrent && <Check className="w-3.5 h-3.5 text-primary shrink-0" />}
                  </button>
                );
              })}

              <button
                type="button"
                onClick={() => applyCustomPreset(todayStr, todayStr)}
                className="px-2.5 py-2 bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground rounded-lg border border-border text-left flex items-center justify-between transition-colors cursor-pointer"
              >
                <span>Today</span>
                <span className="text-[10px] text-muted-foreground font-mono">1 Day</span>
              </button>

              <button
                type="button"
                onClick={() => applyCustomPreset(curMonthStart, curMonthEnd)}
                className="px-2.5 py-2 bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground rounded-lg border border-border text-left flex items-center justify-between transition-colors cursor-pointer"
              >
                <span>Current Month</span>
                <span className="text-[10px] text-muted-foreground font-mono">Month</span>
              </button>

              <button
                type="button"
                onClick={() => applyCustomPreset(q1Start, q1End)}
                className="px-2.5 py-2 bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground rounded-lg border border-border text-left flex items-center justify-between transition-colors cursor-pointer"
              >
                <span>Q1 (Apr–Jun)</span>
                <span className="text-[10px] text-muted-foreground font-mono">Apr-Jun</span>
              </button>

              <button
                type="button"
                onClick={() => applyCustomPreset(q2Start, q2End)}
                className="px-2.5 py-2 bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground rounded-lg border border-border text-left flex items-center justify-between transition-colors cursor-pointer"
              >
                <span>Q2 (Jul–Sep)</span>
                <span className="text-[10px] text-muted-foreground font-mono">Jul-Sep</span>
              </button>

              <button
                type="button"
                onClick={() => applyCustomPreset(q3Start, q3End)}
                className="px-2.5 py-2 bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground rounded-lg border border-border text-left flex items-center justify-between transition-colors cursor-pointer"
              >
                <span>Q3 (Oct–Dec)</span>
                <span className="text-[10px] text-muted-foreground font-mono">Oct-Dec</span>
              </button>

              <button
                type="button"
                onClick={() => applyCustomPreset(q4Start, q4End)}
                className="px-2.5 py-2 bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground rounded-lg border border-border text-left flex items-center justify-between transition-colors cursor-pointer"
              >
                <span>Q4 (Jan–Mar)</span>
                <span className="text-[10px] text-muted-foreground font-mono">Jan-Mar</span>
              </button>

              <button
                type="button"
                onClick={() => applyCustomPreset("2020-04-01", "2030-03-31")}
                className="px-2.5 py-2 bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground rounded-lg border border-border text-left flex items-center justify-between transition-colors cursor-pointer"
              >
                <span>All-Time (Continuous)</span>
                <span className="text-[10px] text-muted-foreground font-mono">Multi-Year</span>
              </button>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2 pt-2">
            <button
              type="button"
              onClick={() => setIsPeriodModalOpen(false)}
              className="flex-1 py-2 bg-muted hover:bg-zinc-700 text-zinc-300 rounded-xl font-bold text-xs transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex-1 py-2 bg-blue-600 hover:bg-blue-500 text-foreground rounded-xl font-bold text-xs shadow-md shadow-blue-600/20 transition-all flex items-center justify-center gap-1.5 cursor-pointer"
            >
              <span>Apply Period</span>
              <kbd className="px-1 py-0.2 bg-black/20 text-foreground/80 rounded font-mono text-[9px]">Enter</kbd>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
