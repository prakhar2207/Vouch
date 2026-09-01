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
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
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
          className="w-full px-3 py-2 border rounded-lg shadow-sm text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white disabled:bg-gray-100 dark:disabled:bg-gray-900 disabled:cursor-not-allowed pr-8"
        />

        {value && !disabled && (
          <button
            type="button"
            onClick={() => {
              onChange("", "");
              setSearch("");
            }}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 text-xs font-bold"
            title="Clear"
          >
            ✕
          </button>
        )}
      </div>

      {isOpen && !disabled && (
        <ul className="absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-md bg-white dark:bg-gray-800 py-1 text-sm shadow-lg ring-1 ring-black ring-opacity-5 border border-gray-200 dark:border-gray-700 focus:outline-none">
          {filteredStates.length === 0 ? (
            <li className="relative cursor-default select-none py-2 px-3 text-gray-500 dark:text-gray-400">
              No matching states or codes found.
            </li>
          ) : (
            filteredStates.map((s) => {
              const isSelected = s.code === value;
              return (
                <li
                  key={s.code}
                  onClick={() => handleSelect(s)}
                  className={`relative cursor-pointer select-none py-2 px-3 flex items-center justify-between hover:bg-blue-50 dark:hover:bg-gray-700 ${
                    isSelected ? "bg-blue-100 dark:bg-blue-900/40 font-semibold text-blue-900 dark:text-blue-200" : "text-gray-900 dark:text-gray-100"
                  }`}
                >
                  <span>{s.name}</span>
                  <span className="text-xs px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-700 font-mono text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-600">
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
