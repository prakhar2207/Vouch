"use client";
import React, { useState, useRef, useEffect } from "react";
import { Search, ChevronDown, Check, Plus, X } from "lucide-react";

export interface SearchableOption {
  id: string;
  name: string;
  group?: string;
  balance?: string | number;
  balanceType?: string;
  subtitle?: string;
}

interface SearchableSelectProps {
  value: string;
  onChange: (value: string, selectedOption?: SearchableOption) => void;
  options: SearchableOption[];
  placeholder?: string;
  searchPlaceholder?: string;
  disabled?: boolean;
  required?: boolean;
  className?: string;
  onAddNew?: () => void;
  addNewText?: string;
  id?: string;
}

export default function SearchableSelect({
  value,
  onChange,
  options,
  placeholder = "-- Select --",
  searchPlaceholder = "Type to search...",
  disabled = false,
  required = false,
  className = "",
  onAddNew,
  addNewText = "+ Add New",
  id,
}: SearchableSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [highlightedIndex, setHighlightedIndex] = useState(0);

  const containerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const selectedOption = options.find((opt) => opt.id === value);

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Focus search input and reset highlight when opened
  useEffect(() => {
    if (isOpen) {
      setSearch("");
      setHighlightedIndex(0);
      setTimeout(() => {
        searchInputRef.current?.focus();
      }, 50);
    }
  }, [isOpen]);

  const filteredOptions = options.filter((opt) => {
    if (!search.trim()) return true;
    const query = search.toLowerCase();
    const nameMatch = opt.name.toLowerCase().includes(query);
    const groupMatch = opt.group ? opt.group.toLowerCase().includes(query) : false;
    const subMatch = opt.subtitle ? opt.subtitle.toLowerCase().includes(query) : false;
    return nameMatch || groupMatch || subMatch;
  });

  // Handle keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen) {
      if (e.key === "Enter" || e.key === "ArrowDown" || e.key === " ") {
        e.preventDefault();
        setIsOpen(true);
      }
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightedIndex((prev) => (prev + 1 < filteredOptions.length ? prev + 1 : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightedIndex((prev) => (prev - 1 >= 0 ? prev - 1 : filteredOptions.length - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (filteredOptions[highlightedIndex]) {
        handleSelect(filteredOptions[highlightedIndex]);
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      setIsOpen(false);
    }
  };

  const handleSelect = (option: SearchableOption) => {
    onChange(option.id, option);
    setIsOpen(false);
  };

  return (
    <div ref={containerRef} className={`relative ${className}`} id={id}>
      {/* Hidden input for HTML5 form validation if required */}
      {required && (
        <input
          type="text"
          value={value}
          onChange={() => {}}
          required
          className="sr-only"
          tabIndex={-1}
          aria-hidden="true"
        />
      )}

      {/* Trigger Button */}
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen(!isOpen)}
        onKeyDown={handleKeyDown}
        className={`w-full bg-muted/50 hover:bg-muted/80 border border-input text-foreground px-3.5 py-2.5 rounded-lg text-left flex items-center justify-between transition-all min-h-[44px] focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer ${
          disabled ? "opacity-50 cursor-not-allowed" : ""
        } ${isOpen ? "ring-2 ring-blue-500 border-blue-500" : ""}`}
      >
        <div className="flex items-center gap-2 truncate pr-2">
          {selectedOption ? (
            <div className="flex items-center gap-2 truncate">
              <span className="font-semibold text-foreground text-sm truncate">
                {selectedOption.name}
              </span>
              {selectedOption.group && (
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-muted border border-border text-muted-foreground shrink-0 font-medium">
                  {selectedOption.group}
                </span>
              )}
            </div>
          ) : (
            <span className="text-muted-foreground text-sm font-normal">
              {placeholder}
            </span>
          )}
        </div>

        <div className="flex items-center gap-1.5 shrink-0 text-muted-foreground">
          {value && !disabled && (
            <span
              onClick={(e) => {
                e.stopPropagation();
                onChange("");
              }}
              className="p-1 hover:text-foreground rounded-full hover:bg-muted transition-colors cursor-pointer"
              title="Clear selection"
            >
              <X className="w-3.5 h-3.5" />
            </span>
          )}
          <ChevronDown
            className={`w-4 h-4 transition-transform duration-200 ${
              isOpen ? "rotate-180 text-foreground" : ""
            }`}
          />
        </div>
      </button>

      {/* Elevated Dropdown Menu */}
      {isOpen && (
        <div className="absolute left-0 right-0 top-full mt-1.5 z-50 bg-card border border-border rounded-xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
          {/* Search Bar */}
          <div className="p-2 border-b border-border bg-muted/30">
            <div className="relative flex items-center">
              <Search className="w-4 h-4 absolute left-3 text-muted-foreground pointer-events-none" />
              <input
                ref={searchInputRef}
                type="text"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setHighlightedIndex(0);
                }}
                onKeyDown={handleKeyDown}
                placeholder={searchPlaceholder}
                className="w-full bg-muted/60 text-foreground placeholder:text-muted-foreground text-sm pl-9 pr-8 py-2 rounded-lg border border-input focus:outline-none focus:ring-1 focus:ring-blue-500 font-normal"
              />
              {search && (
                <button
                  type="button"
                  onClick={() => setSearch("")}
                  className="absolute right-2.5 text-muted-foreground hover:text-foreground p-1"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>

          {/* Options List */}
          <div
            ref={listRef}
            className="max-h-64 overflow-y-auto divide-y divide-border/30 p-1"
          >
            {filteredOptions.length === 0 ? (
              <div className="p-6 text-center text-muted-foreground space-y-2">
                <p className="text-sm font-medium">No matches found</p>
                {search && (
                  <p className="text-xs">
                    No items matching &ldquo;<span className="text-foreground">{search}</span>&rdquo;
                  </p>
                )}
                {onAddNew && (
                  <div className="pt-2">
                    <button
                      type="button"
                      onClick={() => {
                        setIsOpen(false);
                        onAddNew();
                      }}
                      className="inline-flex items-center gap-1.5 text-xs text-blue-500 hover:text-blue-400 font-semibold px-3 py-1.5 rounded-lg bg-blue-500/10 border border-blue-500/20 transition-all cursor-pointer"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      <span>{addNewText}</span>
                    </button>
                  </div>
                )}
              </div>
            ) : (
              filteredOptions.map((opt, idx) => {
                const isSelected = opt.id === value;
                const isHighlighted = idx === highlightedIndex;

                return (
                  <div
                    key={opt.id}
                    onClick={() => handleSelect(opt)}
                    onMouseEnter={() => setHighlightedIndex(idx)}
                    className={`px-3.5 py-2.5 rounded-lg flex items-center justify-between cursor-pointer transition-colors text-sm ${
                      isSelected
                        ? "bg-blue-600/15 text-blue-400 font-semibold"
                        : isHighlighted
                        ? "bg-muted text-foreground"
                        : "text-foreground/90 hover:bg-muted/70"
                    }`}
                  >
                    <div className="min-w-0 pr-2">
                      <div className="flex items-center gap-2">
                        <span className="truncate">{opt.name}</span>
                        {opt.group && (
                          <span
                            className={`text-[10px] px-2 py-0.5 rounded-full font-medium shrink-0 ${
                              isSelected
                                ? "bg-blue-500/20 text-blue-300 border border-blue-500/30"
                                : "bg-muted border border-border text-muted-foreground"
                            }`}
                          >
                            {opt.group}
                          </span>
                        )}
                      </div>
                      {opt.subtitle && (
                        <p className="text-xs text-muted-foreground truncate mt-0.5">
                          {opt.subtitle}
                        </p>
                      )}
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {opt.balance !== undefined && (
                        <span className="text-xs font-mono tabular-nums text-muted-foreground font-medium">
                          ₹{Number(opt.balance).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                          {opt.balanceType ? ` ${opt.balanceType}` : ""}
                        </span>
                      )}
                      {isSelected && (
                        <Check className="w-4 h-4 text-blue-400" />
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Quick Footer Action if onAddNew is provided */}
          {onAddNew && (
            <div className="p-2 border-t border-border bg-muted/20 flex justify-between items-center text-xs">
              <span className="text-muted-foreground">
                {filteredOptions.length} option{filteredOptions.length !== 1 ? "s" : ""}
              </span>
              <button
                type="button"
                onClick={() => {
                  setIsOpen(false);
                  onAddNew();
                }}
                className="inline-flex items-center gap-1 text-blue-500 hover:text-blue-400 font-semibold px-2.5 py-1 rounded hover:bg-blue-500/10 transition-colors cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>{addNewText}</span>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
