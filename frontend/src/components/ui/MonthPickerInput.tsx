"use client";

import React, { useState, useEffect, useRef } from "react";
import { Calendar, ChevronLeft, ChevronRight, X } from "lucide-react";

const MONTH_NAMES_FULL = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"
];

const MONTH_NAMES_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
];

export interface MonthPickerInputProps {
  label?: string;
  value: string; // Normalized MMYYYY (e.g. "042026")
  onChange: (normalizedPeriod: string, displayLabel: string) => void;
  minYear?: number;
  maxYear?: number;
  maxPeriod?: string; // Optional maximum allowed normalized MMYYYY
  error?: string | null;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

export function parsePeriodToDisplay(norm: string): string {
  if (!norm || norm.length !== 6 || !/^\d{6}$/.test(norm)) return "";
  const month = parseInt(norm.slice(0, 2), 10);
  const year = parseInt(norm.slice(2), 10);
  if (month >= 1 && month <= 12) {
    return `${MONTH_NAMES_FULL[month - 1]} ${year}`;
  }
  return norm;
}

export function parseUserInputToPeriod(input: string): { normalized: string; display: string } | null {
  if (!input) return null;
  const s = input.trim();

  // Pattern 1: Pure 6 digits MMYYYY (e.g. "042026")
  if (/^\d{6}$/.test(s)) {
    const m = parseInt(s.slice(0, 2), 10);
    const y = parseInt(s.slice(2), 10);
    if (m >= 1 && m <= 12 && y >= 2017 && y <= 2040) {
      const norm = `${String(m).padStart(2, '0')}${y}`;
      return { normalized: norm, display: `${MONTH_NAMES_FULL[m - 1]} ${y}` };
    }
  }

  // Pattern 2: Pure 6 digits YYYYMM (e.g. "202604")
  if (/^\d{6}$/.test(s)) {
    const y = parseInt(s.slice(0, 4), 10);
    const m = parseInt(s.slice(4), 10);
    if (y >= 2017 && y <= 2040 && m >= 1 && m <= 12) {
      const norm = `${String(m).padStart(2, '0')}${y}`;
      return { normalized: norm, display: `${MONTH_NAMES_FULL[m - 1]} ${y}` };
    }
  }

  // Pattern 3: Slashed or Hyphenated "MM/YYYY", "MM-YYYY", "YYYY-MM", "YYYY/MM"
  const sepMatch = s.match(/^(\d{1,4})[-/](\d{1,4})$/);
  if (sepMatch) {
    const p1 = parseInt(sepMatch[1], 10);
    const p2 = parseInt(sepMatch[2], 10);
    let m = 0;
    let y = 0;
    if (p1 >= 1 && p1 <= 12 && p2 >= 2017 && p2 <= 2040) {
      m = p1;
      y = p2;
    } else if (p1 >= 2017 && p1 <= 2040 && p2 >= 1 && p2 <= 12) {
      y = p1;
      m = p2;
    }
    if (m && y) {
      const norm = `${String(m).padStart(2, '0')}${y}`;
      return { normalized: norm, display: `${MONTH_NAMES_FULL[m - 1]} ${y}` };
    }
  }

  // Pattern 4: Named month + Year (e.g. "April 2026", "Apr 2026", "April, 2026")
  const namedMatch = s.match(/^([a-zA-Z]+)[,\s]+(\d{4})$/);
  if (namedMatch) {
    const monthWord = namedMatch[1].toLowerCase();
    const y = parseInt(namedMatch[2], 10);
    if (y >= 2017 && y <= 2040) {
      const mIdx = MONTH_NAMES_FULL.findIndex(
        (nm, idx) => nm.toLowerCase().startsWith(monthWord) || MONTH_NAMES_SHORT[idx].toLowerCase() === monthWord
      );
      if (mIdx !== -1) {
        const m = mIdx + 1;
        const norm = `${String(m).padStart(2, '0')}${y}`;
        return { normalized: norm, display: `${MONTH_NAMES_FULL[m - 1]} ${y}` };
      }
    }
  }

  return null;
}

export default function MonthPickerInput({
  label,
  value,
  onChange,
  minYear = 2020,
  maxYear = 2030,
  maxPeriod,
  error,
  placeholder = "e.g. April 2026",
  disabled = false,
  className = "",
}: MonthPickerInputProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [inputText, setInputText] = useState("");
  const [inputError, setInputError] = useState<string | null>(null);

  // Derive initial picker year from value or current date
  const initialYear = value && value.length === 6 ? parseInt(value.slice(2), 10) : new Date().getFullYear();
  const [pickerYear, setPickerYear] = useState(initialYear);

  const containerRef = useRef<HTMLDivElement>(null);

  // Sync internal display text when value prop changes
  useEffect(() => {
    if (value && value.length === 6) {
      setInputText(parsePeriodToDisplay(value));
      const y = parseInt(value.slice(2), 10);
      if (!isNaN(y)) setPickerYear(y);
    } else {
      setInputText("");
    }
    setInputError(null);
  }, [value]);

  // Click outside listener to close popover
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        if (isOpen) {
          setIsOpen(false);
          // On close, re-normalize input text
          if (value && value.length === 6) {
            setInputText(parsePeriodToDisplay(value));
            setInputError(null);
          }
        }
      }
    }
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen, value]);

  // Keyboard navigation inside popover
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      setIsOpen(false);
    } else if (e.key === "Enter") {
      commitDirectInput();
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setInputText(e.target.value);
    setInputError(null);
  };

  const commitDirectInput = () => {
    if (!inputText.trim()) {
      return;
    }
    const parsed = parseUserInputToPeriod(inputText);
    if (parsed) {
      // Check maxPeriod constraint if provided
      if (maxPeriod && maxPeriod.length === 6) {
        const pMonth = parseInt(parsed.normalized.slice(0, 2), 10);
        const pYear = parseInt(parsed.normalized.slice(2), 10);
        const maxM = parseInt(maxPeriod.slice(0, 2), 10);
        const maxY = parseInt(maxPeriod.slice(2), 10);
        if (pYear > maxY || (pYear === maxY && pMonth > maxM)) {
          setInputError(`Period cannot be in the future (max: ${parsePeriodToDisplay(maxPeriod)})`);
          return;
        }
      }
      setInputText(parsed.display);
      setInputError(null);
      setPickerYear(parseInt(parsed.normalized.slice(2), 10));
      onChange(parsed.normalized, parsed.display);
    } else {
      setInputError("Invalid format. Use 'April 2026', '04/2026', or '042026'.");
    }
  };

  const handleMonthSelect = (monthIndex: number) => {
    const monthNum = monthIndex + 1;
    const norm = `${String(monthNum).padStart(2, '0')}${pickerYear}`;
    const display = `${MONTH_NAMES_FULL[monthIndex]} ${pickerYear}`;

    // Validate future period if maxPeriod is set
    if (maxPeriod && maxPeriod.length === 6) {
      const maxM = parseInt(maxPeriod.slice(0, 2), 10);
      const maxY = parseInt(maxPeriod.slice(2), 10);
      if (pickerYear > maxY || (pickerYear === maxY && monthNum > maxM)) {
        setInputError(`Period cannot be in the future (max: ${parsePeriodToDisplay(maxPeriod)})`);
        return;
      }
    }

    setInputText(display);
    setInputError(null);
    setIsOpen(false);
    onChange(norm, display);
  };

  const isMonthSelected = (monthIndex: number) => {
    if (!value || value.length !== 6) return false;
    const vMonth = parseInt(value.slice(0, 2), 10) - 1;
    const vYear = parseInt(value.slice(2), 10);
    return vMonth === monthIndex && vYear === pickerYear;
  };

  const isMonthDisabled = (monthIndex: number) => {
    if (pickerYear < minYear || pickerYear > maxYear) return true;
    if (maxPeriod && maxPeriod.length === 6) {
      const maxM = parseInt(maxPeriod.slice(0, 2), 10);
      const maxY = parseInt(maxPeriod.slice(2), 10);
      const monthNum = monthIndex + 1;
      if (pickerYear > maxY || (pickerYear === maxY && monthNum > maxM)) {
        return true;
      }
    }
    return false;
  };

  return (
    <div ref={containerRef} className={`relative space-y-1 ${className}`}>
      {label && (
        <label className="block text-[11px] font-semibold text-muted-foreground">
          {label}
        </label>
      )}

      <div className="relative flex items-center">
        <input
          type="text"
          value={inputText}
          onChange={handleInputChange}
          onBlur={commitDirectInput}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={placeholder}
          aria-label={label || "Select Month and Year"}
          className={`w-full pl-3 pr-9 py-2 text-xs rounded-lg border bg-background text-foreground transition-all focus:outline-none focus:ring-1 focus:ring-primary ${
            error || inputError
              ? "border-rose-500/80 focus:border-rose-500 focus:ring-rose-500/30"
              : "border-border/60 hover:border-border"
          } ${disabled ? "opacity-60 cursor-not-allowed" : "cursor-text font-medium"}`}
        />

        <button
          type="button"
          onClick={() => !disabled && setIsOpen(!isOpen)}
          disabled={disabled}
          aria-label={`Open calendar month picker for ${label || "period"}`}
          title="Open month picker"
          className="absolute right-1.5 p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer"
        >
          <Calendar className="w-4 h-4 text-primary/80" />
        </button>
      </div>

      {(error || inputError) && (
        <p className="text-[10px] text-rose-500 font-medium tracking-tight">
          {error || inputError}
        </p>
      )}

      {/* Popover Month Picker Grid */}
      {isOpen && (
        <div className="absolute top-full left-0 z-50 mt-1 w-64 p-3 bg-card border border-border/60 rounded-xl shadow-xl animate-in fade-in zoom-in-95 backdrop-blur-md">
          {/* Year Navigation Header */}
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-border/40">
            <button
              type="button"
              onClick={() => setPickerYear((y) => Math.max(minYear, y - 1))}
              disabled={pickerYear <= minYear}
              className="p-1 rounded-lg hover:bg-muted/70 text-muted-foreground hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer"
              title="Previous Year"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>

            <span className="text-xs font-bold text-foreground font-mono">
              {pickerYear}
            </span>

            <button
              type="button"
              onClick={() => setPickerYear((y) => Math.min(maxYear, y + 1))}
              disabled={pickerYear >= maxYear}
              className="p-1 rounded-lg hover:bg-muted/70 text-muted-foreground hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer"
              title="Next Year"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          {/* 12 Months Grid */}
          <div className="grid grid-cols-3 gap-1.5">
            {MONTH_NAMES_SHORT.map((mName, idx) => {
              const selected = isMonthSelected(idx);
              const disabledMonth = isMonthDisabled(idx);
              return (
                <button
                  key={mName}
                  type="button"
                  onClick={() => !disabledMonth && handleMonthSelect(idx)}
                  disabled={disabledMonth}
                  className={`py-1.5 px-2 text-xs rounded-lg font-medium transition-all text-center cursor-pointer ${
                    selected
                      ? "bg-primary text-primary-foreground font-bold shadow-sm"
                      : disabledMonth
                      ? "opacity-30 cursor-not-allowed text-muted-foreground"
                      : "text-foreground hover:bg-muted hover:text-foreground"
                  }`}
                >
                  {mName}
                </button>
              );
            })}
          </div>

          <div className="mt-2.5 pt-2 border-t border-border/30 flex items-center justify-between text-[10px] text-muted-foreground">
            <span>Direct typing supported</span>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              className="text-primary hover:underline font-semibold cursor-pointer"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
