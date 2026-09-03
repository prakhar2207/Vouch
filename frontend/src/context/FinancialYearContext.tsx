"use client";
import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import axios from "axios";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken, isAuthenticated } from "@/utils/auth";

export interface FinancialYear {
  id: string;
  name: string;
  code: string;
  start_date: string;
  end_date: string;
  is_closed: boolean;
  voucher_count?: number;
  is_current?: boolean;
}

interface FinancialYearContextType {
  activeFY: FinancialYear | null;
  availableFYs: FinancialYear[];
  loading: boolean;
  isReadOnly: boolean;
  setActiveFY: (fy: FinancialYear) => void;
  refreshFYs: () => Promise<void>;
  isClosingModalOpen: boolean;
  setIsClosingModalOpen: (open: boolean) => void;
}

const FinancialYearContext = createContext<FinancialYearContextType | null>(null);

export function FinancialYearProvider({ children }: { children: React.ReactNode }) {
  const [availableFYs, setAvailableFYs] = useState<FinancialYear[]>([]);
  const [activeFY, setActiveFYState] = useState<FinancialYear | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [isClosingModalOpen, setIsClosingModalOpen] = useState<boolean>(false);

  const refreshFYs = useCallback(async () => {
    if (!isAuthenticated()) {
      setLoading(false);
      return;
    }

    try {
      const token = getAccessToken();
      const res = await axios.get(`${API_BASE_URL}/api/v1/financial-years/`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (res.data?.success && Array.isArray(res.data.data)) {
        const list: FinancialYear[] = res.data.data;
        setAvailableFYs(list);

        const savedId = typeof window !== "undefined" ? localStorage.getItem("vouch_active_fy_id") : null;
        let selected = list.find((fy) => fy.id === savedId);

        if (!selected) {
          selected = list.find((fy) => fy.is_current && !fy.is_closed) || list.find((fy) => !fy.is_closed) || list[0];
        }

        if (selected) {
          setActiveFYState(selected);
          if (typeof window !== "undefined") {
            localStorage.setItem("vouch_active_fy_id", selected.id);
          }
        }
      }
    } catch (err) {
      console.error("Failed to load financial years", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshFYs();
  }, [refreshFYs]);

  const setActiveFY = (fy: FinancialYear) => {
    setActiveFYState(fy);
    if (typeof window !== "undefined") {
      localStorage.setItem("vouch_active_fy_id", fy.id);
    }
  };

  const isReadOnly = Boolean(activeFY?.is_closed);

  return (
    <FinancialYearContext.Provider
      value={{
        activeFY,
        availableFYs,
        loading,
        isReadOnly,
        setActiveFY,
        refreshFYs,
        isClosingModalOpen,
        setIsClosingModalOpen
      }}
    >
      {children}
    </FinancialYearContext.Provider>
  );
}

export function useFinancialYear() {
  const context = useContext(FinancialYearContext);
  if (!context) {
    throw new Error("useFinancialYear must be used within a FinancialYearProvider");
  }
  return context;
}
