"use client";
import React, { useState, useRef, useEffect } from "react";
import { GST_STATES, GSTState, getStateByCode } from "@/utils/gstStates";

interface StateSelectProps {
  value: string;
  onChange: (code: string, stateName?: string) => void;
  label?: string;
  placeholder?: string;
  required?: boolean;
  className?: string;
  disabled?: boolean;
}

export default function StateSelect({
  value,
  onChange,
  label = "State / UT (GST Code)",
  placeholder = "Search by state name or code...",
  required = false,
  className = "",
  disabled = false,
}: StateSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Sync search input with value prop when not open
  const selectedState = getStateByCode(value);

  useEffect(() => {
    if (selectedState) {
      setSearch(`${selectedState.name} (${selectedState.code})`);
    } else if (value) {
      setSearch(value);
    } else {
      setSearch("");
    }
  }, [value]);

  // Click outside to close dropdown
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        // Reset search to selected state text if not confirmed
        if (selectedState) {
          setSearch(`${selectedState.name} (${selectedState.code})`);
        } else if (value) {
          setSearch(value);
        } else {
          setSearch("");
        }
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [selectedState, value]);

  const filteredStates = GST_STATES.filter((s) => {
    const q = search.toLowerCase().trim();
    if (!q) return true;
    return (
      s.name.toLowerCase().includes(q) ||
      s.code.includes(q) ||
      `${s.name} (${s.code})`.toLowerCase().includes(q)
    );
  });

  const handleSelect = (state: GSTState) => {
    onChange(state.code, state.name);
    setSearch(`${state.name} (${state.code})`);
    setIsOpen(false);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setSearch(val);
    setIsOpen(true);

    // If exact 2-digit code entered, auto-select
    const exact = getStateByCode(val);
    if (exact) {
      onChange(exact.code, exact.name);
    } else if (!val) {
      onChange("", "");
    }
  };

  return (
    <div className={`relative ${className}`} ref={dropdownRef}>
      {label && (
        <label className="block text-sm font-medium text-gray-700 dark:text-foreground/80 mb-1">
          {label} {required && <span className="text-red-500">*</span>}
        </label>
      )}

      <div className="relative">
        <input
          type="text"
          value={search}
          onChange={handleInputChange}
          onFocus={() => setIsOpen(true)}
          placeholder={placeholder}
          disabled={disabled}
          required={required}
          className="w-full px-3 py-2 border rounded-lg shadow-xs text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 border-input bg-background text-foreground disabled:bg-muted disabled:cursor-not-allowed pr-8 transition-colors"
        />

        {value && !disabled && (
          <button
            type="button"
            onClick={() => {
              onChange("", "");
              setSearch("");
            }}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground text-xs font-bold p-1 cursor-pointer"
            title="Clear"
          >
            ✕
          </button>
        )}
      </div>

      {isOpen && !disabled && (
        <ul className="absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-xl bg-card py-1 text-sm shadow-xl border border-border focus:outline-none">
          {filteredStates.length === 0 ? (
            <li className="relative cursor-default select-none py-2 px-3 text-muted-foreground text-xs">
              No matching states or codes found.
            </li>
          ) : (
            filteredStates.map((s) => {
              const isSelected = s.code === value;
              return (
                <li
                  key={s.code}
                  onClick={() => handleSelect(s)}
                  className={`relative cursor-pointer select-none py-2 px-3 flex items-center justify-between transition-colors ${
                    isSelected ? "bg-primary/10 text-primary font-semibold" : "text-foreground hover:bg-accent hover:text-accent-foreground"
                  }`}
                >
                  <span>{s.name}</span>
                  <span className="text-xs px-2 py-0.5 rounded bg-muted font-mono text-muted-foreground border border-border">
                    Code: {s.code}
                  </span>
                </li>
              );
            })
          )}
        </ul>
      )}
    </div>
  );
}
