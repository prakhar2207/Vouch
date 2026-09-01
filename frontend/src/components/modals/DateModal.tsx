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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="w-full max-w-md bg-zinc-900 border border-zinc-700 rounded-2xl shadow-2xl p-6 text-white space-y-5">
        <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
          <div className="flex items-center gap-2.5">
            <span className="px-2 py-0.5 bg-blue-600/20 text-blue-400 border border-blue-500/30 rounded text-xs font-mono font-bold">
              F2
            </span>
            <h3 className="text-lg font-bold text-white">Change Voucher / Working Date</h3>
          </div>
          <button
            onClick={() => setIsDateOpen(false)}
            className="text-gray-400 hover:text-white text-sm font-bold px-2 py-1"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSave} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-gray-400 uppercase mb-1.5">
              Current Working Date
            </label>
            <input
              ref={inputRef}
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-700 text-white p-3 rounded-xl text-base font-semibold outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="grid grid-cols-3 gap-2 text-xs">
            <button
              type="button"
              onClick={() => setPreset(0)}
              className="p-2 bg-zinc-800 hover:bg-zinc-700 text-gray-200 rounded-lg border border-zinc-700 font-medium transition-colors"
            >
              Today
            </button>
            <button
              type="button"
              onClick={() => setPreset(-1)}
              className="p-2 bg-zinc-800 hover:bg-zinc-700 text-gray-200 rounded-lg border border-zinc-700 font-medium transition-colors"
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
              className="p-2 bg-zinc-800 hover:bg-zinc-700 text-gray-200 rounded-lg border border-zinc-700 font-medium transition-colors"
            >
              1st of Month
            </button>
          </div>

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={() => setIsDateOpen(false)}
              className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-gray-300 rounded-lg text-sm font-medium transition-colors"
            >
              Cancel (Esc)
            </button>
            <button
              type="submit"
              className="px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-bold shadow-md transition-colors"
            >
              Apply Date (Enter)
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
