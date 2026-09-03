"use client";
import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { useHotkeys } from "react-hotkeys-hook";

interface PeriodContextType {
  fromDate: string;
  toDate: string;
  setPeriod: (from: string, to: string) => void;
  resetToCurrentFY: () => void;
  isPeriodModalOpen: boolean;
  setIsPeriodModalOpen: (open: boolean) => void;
  isSplitModalOpen: boolean;
  setIsSplitModalOpen: (open: boolean) => void;
  displayPeriod: string;
}

const PeriodContext = createContext<PeriodContextType | null>(null);

function getDefaultFYDates() {
  const today = new Date();
  const year = today.getFullYear();
  const month = today.getMonth() + 1;
  const startYear = month >= 4 ? year : year - 1;
  const endYear = startYear + 1;
  return {
    from: `${startYear}-04-01`,
    to: `${endYear}-03-31`
  };
}

export function PeriodProvider({ children }: { children: React.ReactNode }) {
  const defaults = getDefaultFYDates();
  const [fromDate, setFromDateState] = useState<string>(defaults.from);
  const [toDate, setToDateState] = useState<string>(defaults.to);
  const [isPeriodModalOpen, setIsPeriodModalOpen] = useState(false);
  const [isSplitModalOpen, setIsSplitModalOpen] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const savedFrom = localStorage.getItem("vouch_period_from");
      const savedTo = localStorage.getItem("vouch_period_to");
      if (savedFrom && savedTo) {
        setFromDateState(savedFrom);
        setToDateState(savedTo);
      }
    }
  }, []);

  const setPeriod = useCallback((from: string, to: string) => {
    setFromDateState(from);
    setToDateState(to);
    if (typeof window !== "undefined") {
      localStorage.setItem("vouch_period_from", from);
      localStorage.setItem("vouch_period_to", to);
    }
  }, []);

  const resetToCurrentFY = useCallback(() => {
    const d = getDefaultFYDates();
    setPeriod(d.from, d.to);
  }, [setPeriod]);

  // Global Alt + F2 Shortcut to Change Period (Tally-Style)
  useHotkeys(['alt+f2'], (e) => {
    e.preventDefault();
    setIsPeriodModalOpen(true);
  }, { enableOnFormTags: true });

  const formatDisplayDate = (dStr: string) => {
    if (!dStr) return "";
    try {
      const d = new Date(dStr);
      return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
    } catch {
      return dStr;
    }
  };

  const displayPeriod = `${formatDisplayDate(fromDate)} to ${formatDisplayDate(toDate)}`;

  return (
    <PeriodContext.Provider
      value={{
        fromDate,
        toDate,
        setPeriod,
        resetToCurrentFY,
        isPeriodModalOpen,
        setIsPeriodModalOpen,
        isSplitModalOpen,
        setIsSplitModalOpen,
        displayPeriod
      }}
    >
      {children}
    </PeriodContext.Provider>
  );
}

export function useAccountingPeriod() {
  const context = useContext(PeriodContext);
  if (!context) {
    throw new Error("useAccountingPeriod must be used within a PeriodProvider");
  }
  return context;
}
