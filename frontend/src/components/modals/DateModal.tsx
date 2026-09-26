"use client";
import React, { useState, useEffect, useRef } from "react";
import { useShortcuts } from "@/context/ShortcutContext";

export default function DateModal() {
  const { isDateOpen, setIsDateOpen, workingDate, setWorkingDate } = useShortcuts();
  const [selectedDate, setSelectedDate] = useState(workingDate);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isDateOpen) {
      setSelectedDate(workingDate);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isDateOpen, workingDate]);

  if (!isDateOpen) return null;

  const handleSave = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (selectedDate) {
      setWorkingDate(selectedDate);
    }
    setIsDateOpen(false);
  };

  const setPreset = (offsetDays: number) => {
    const d = new Date();
    d.setDate(d.getDate() + offsetDays);
    const dateStr = d.toISOString().split("T")[0];
    setSelectedDate(dateStr);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="w-full max-w-md bg-card border border-border/80 rounded-2xl shadow-2xl p-6 text-foreground space-y-5 animate-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between border-b border-border/60 pb-3">
          <div className="flex items-center gap-2.5">
            <span className="px-2 py-0.5 bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/25 rounded text-xs font-mono font-bold">
              F2
            </span>
            <h3 className="text-lg font-bold text-foreground">Change Voucher / Working Date</h3>
          </div>
          <button
            onClick={() => setIsDateOpen(false)}
            className="text-muted-foreground hover:text-foreground text-sm font-bold p-1 rounded-lg hover:bg-muted/70 transition-colors cursor-pointer"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSave} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-muted-foreground uppercase mb-1.5">
              Current Working Date
            </label>
            <input
              ref={inputRef}
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="w-full bg-background border border-border text-foreground p-3 rounded-xl text-base font-semibold outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
            />
          </div>

          <div className="grid grid-cols-3 gap-2 text-xs">
            <button
              type="button"
              onClick={() => setPreset(0)}
              className="p-2 bg-muted/60 hover:bg-muted text-foreground rounded-xl border border-border/60 font-semibold transition-colors cursor-pointer"
            >
              Today
            </button>
            <button
              type="button"
              onClick={() => setPreset(-1)}
              className="p-2 bg-muted/60 hover:bg-muted text-foreground rounded-xl border border-border/60 font-semibold transition-colors cursor-pointer"
            >
              Yesterday
            </button>
            <button
              type="button"
              onClick={() => {
                const now = new Date();
                const firstDay = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().split("T")[0];
                setSelectedDate(firstDay);
              }}
              className="p-2 bg-muted/60 hover:bg-muted text-foreground rounded-xl border border-border/60 font-semibold transition-colors cursor-pointer"
            >
              1st of Month
            </button>
          </div>

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={() => setIsDateOpen(false)}
              className="px-4 py-2 bg-muted hover:bg-muted/80 text-foreground border border-border/60 rounded-xl text-sm font-semibold transition-colors cursor-pointer"
            >
              Cancel (Esc)
            </button>
            <button
              type="submit"
              className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-sm font-bold shadow-md shadow-blue-600/20 transition-all cursor-pointer"
            >
              Apply Date (Enter)
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
