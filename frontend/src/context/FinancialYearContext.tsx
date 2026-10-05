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

const STORAGE_FY_KEY = "vouch_active_fy_id";
const CACHED_FYS_KEY = "vouch_cached_fys_list";

export function FinancialYearProvider({ children }: { children: React.ReactNode }) {
  const [availableFYs, setAvailableFYs] = useState<FinancialYear[]>(() => {
    if (typeof window !== "undefined") {
      try {
        const cached = localStorage.getItem(CACHED_FYS_KEY);
        if (cached) return JSON.parse(cached);
      } catch {}
    }
    return [];
  });

  const [activeFY, setActiveFYState] = useState<FinancialYear | null>(() => {
    if (typeof window !== "undefined") {
      try {
        const savedId = localStorage.getItem(STORAGE_FY_KEY);
        const cached = localStorage.getItem(CACHED_FYS_KEY);
        if (cached) {
          const list: FinancialYear[] = JSON.parse(cached);
          const found = list.find((fy) => fy.id === savedId) || list.find((fy) => !fy.is_closed) || list[0] || null;
          if (found) return found;
        }
      } catch {}
    }
    return null;
  });

  const [loading, setLoading] = useState<boolean>(() => {
    if (typeof window !== "undefined") {
      try {
        const cached = localStorage.getItem(CACHED_FYS_KEY);
        if (cached && JSON.parse(cached).length > 0) return false;
      } catch {}
    }
    return true;
  });

  const [isClosingModalOpen, setIsClosingModalOpen] = useState<boolean>(false);

  const refreshFYs = useCallback(async () => {
    if (!isAuthenticated()) {
      setLoading(false);
      return;
    }

    try {
      const token = getAccessToken();
      const activeCo = typeof window !== "undefined"
        ? (localStorage.getItem("vouch_active_company_id") || localStorage.getItem("active_company_id"))
        : null;

      const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
      if (activeCo) {
        headers["X-Company-ID"] = activeCo;
      }

      const res = await axios.get(`${API_BASE_URL}/api/v1/financial-years/`, {
        headers,
        params: activeCo ? { company_id: activeCo } : undefined
      });

      if (res.data?.success && Array.isArray(res.data.data)) {
        const list: FinancialYear[] = res.data.data;
        setAvailableFYs(list);
        if (typeof window !== "undefined") {
          try {
            localStorage.setItem(CACHED_FYS_KEY, JSON.stringify(list));
          } catch {}
        }

        const todayStr = new Date().toISOString().slice(0, 10);
        const currentByDate = list.find((fy) => !fy.is_closed && fy.start_date <= todayStr && fy.end_date >= todayStr);

        const savedId = typeof window !== "undefined" ? localStorage.getItem("vouch_active_fy_id") : null;
        let selected = list.find((fy) => fy.id === savedId);

        if (!selected) {
          selected = currentByDate || list.find((fy) => !fy.is_closed) || list[0];
        }

        if (selected) {
          setActiveFYState(selected);
          if (typeof window !== "undefined") {
            localStorage.setItem("vouch_active_fy_id", selected.id);
          }
        }
      }
    } catch (err) {
      // Graceful fallback for initial load without active company selected yet
      console.warn("Financial years not yet provisioned for active context");
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
