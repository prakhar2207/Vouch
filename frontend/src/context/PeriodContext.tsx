"use client";
import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from "react";
import { useHotkeys } from "react-hotkeys-hook";
import { useFinancialYear, FinancialYear } from "./FinancialYearContext";

export interface PeriodContextType {
  fromDate: string;
  toDate: string;
  activeFY: FinancialYear | null;
  periodKey: string;
  isCustomPeriod: boolean;
  setPeriod: (from: string, to: string) => void;
  resetToCurrentFY: () => void;
  isPeriodModalOpen: boolean;
  setIsPeriodModalOpen: (open: boolean) => void;
  isSplitModalOpen: boolean;
  setIsSplitModalOpen: (open: boolean) => void;
  displayPeriod: string;
  shortDisplayPeriod: string;
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
  const { activeFY, availableFYs, setActiveFY } = useFinancialYear();

  const [fromDate, setFromDateState] = useState<string>(() => {
    if (typeof window !== "undefined") {
      const savedFrom = localStorage.getItem("vouch_period_from");
      if (savedFrom) return savedFrom;
    }
    return activeFY?.start_date || defaults.from;
  });

  const [toDate, setToDateState] = useState<string>(() => {
    if (typeof window !== "undefined") {
      const savedTo = localStorage.getItem("vouch_period_to");
      if (savedTo) return savedTo;
    }
    return activeFY?.end_date || defaults.to;
  });

  const [isPeriodModalOpen, setIsPeriodModalOpen] = useState(false);
  const [isSplitModalOpen, setIsSplitModalOpen] = useState(false);

  // Sync with activeFY when activeFY changes
  useEffect(() => {
    if (activeFY?.start_date && activeFY?.end_date) {
      if (typeof window !== "undefined") {
        const isCustom = localStorage.getItem("vouch_period_is_custom") === "true";
        const savedFrom = localStorage.getItem("vouch_period_from");
        const savedTo = localStorage.getItem("vouch_period_to");
        // If user already had a custom sub-period inside this FY, preserve it
        if (isCustom && savedFrom && savedTo && savedFrom >= activeFY.start_date && savedTo <= activeFY.end_date) {
          setFromDateState(savedFrom);
          setToDateState(savedTo);
          return;
        }
      }
      setFromDateState(activeFY.start_date);
      setToDateState(activeFY.end_date);
      if (typeof window !== "undefined") {
        localStorage.setItem("vouch_period_from", activeFY.start_date);
        localStorage.setItem("vouch_period_to", activeFY.end_date);
        localStorage.setItem("vouch_period_is_custom", "false");
      }
    }
  }, [activeFY?.id, activeFY?.start_date, activeFY?.end_date]);

  const setPeriod = useCallback((from: string, to: string) => {
    setFromDateState(from);
    setToDateState(to);

    const exactFY = availableFYs.find((fy) => fy.start_date === from && fy.end_date === to);
    if (exactFY) {
      if (activeFY?.id !== exactFY.id) {
        setActiveFY(exactFY);
      }
      if (typeof window !== "undefined") {
        localStorage.setItem("vouch_period_is_custom", "false");
      }
    } else {
      const containingFY = availableFYs.find((fy) => fy.start_date <= from && fy.end_date >= to);
      if (containingFY && activeFY?.id !== containingFY.id) {
        setActiveFY(containingFY);
      }
      if (typeof window !== "undefined") {
        localStorage.setItem("vouch_period_is_custom", "true");
      }
    }

    if (typeof window !== "undefined") {
      localStorage.setItem("vouch_period_from", from);
      localStorage.setItem("vouch_period_to", to);
      window.dispatchEvent(new CustomEvent("vouch_period_changed", { detail: { from, to } }));
    }
  }, [availableFYs, activeFY?.id, setActiveFY]);

  const resetToCurrentFY = useCallback(() => {
    if (activeFY?.start_date && activeFY?.end_date) {
      setPeriod(activeFY.start_date, activeFY.end_date);
    } else {
      const d = getDefaultFYDates();
      setPeriod(d.from, d.to);
    }
  }, [activeFY, setPeriod]);

  // Global Alt + F2 Shortcut to Change Period (Tally-Style)
  useHotkeys(['alt+f2'], (e) => {
    e.preventDefault();
    setIsPeriodModalOpen(true);
  }, { enableOnFormTags: true });

  const isCustomPeriod = useMemo(() => {
    if (!activeFY?.start_date || !activeFY?.end_date) return false;
    return fromDate !== activeFY.start_date || toDate !== activeFY.end_date;
  }, [fromDate, toDate, activeFY?.start_date, activeFY?.end_date]);

  const formatDisplayDate = (dStr: string) => {
    if (!dStr) return "";
    try {
      const d = new Date(dStr);
      return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
    } catch {
      return dStr;
    }
  };

  const formatShortDate = (dStr: string) => {
    if (!dStr) return "";
    try {
      const d = new Date(dStr);
      return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
    } catch {
      return dStr;
    }
  };

  const displayPeriod = `${formatDisplayDate(fromDate)} to ${formatDisplayDate(toDate)}`;
  const shortDisplayPeriod = `${formatShortDate(fromDate)} – ${formatShortDate(toDate)}`;
  const periodKey = `${fromDate}_${toDate}_${activeFY?.id || ""}`;

  return (
    <PeriodContext.Provider
      value={{
        fromDate,
        toDate,
        activeFY,
        periodKey,
        isCustomPeriod,
        setPeriod,
        resetToCurrentFY,
        isPeriodModalOpen,
        setIsPeriodModalOpen,
        isSplitModalOpen,
        setIsSplitModalOpen,
        displayPeriod,
        shortDisplayPeriod,
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

export const usePeriod = useAccountingPeriod;
