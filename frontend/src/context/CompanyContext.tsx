"use client";
import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import axios from "axios";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken, isAuthenticated } from "@/utils/auth";

export interface Company {
  id: string;
  name: string;
  legal_name?: string;
  gstin?: string;
  state_code?: string;
  email?: string;
  phone?: string;
  address?: string;
  city?: string;
  pincode?: string;
  state?: string;
  is_active?: boolean;
  [key: string]: any;
}

interface CompanyContextType {
  activeCompany: Company | null;
  availableCompanies: Company[];
  companyId: string | null;
  loading: boolean;
  setActiveCompany: (company: Company) => void;
  refreshCompanies: () => Promise<Company | null>;
}

const CompanyContext = createContext<CompanyContextType | null>(null);

const STORAGE_KEY = "vouch_active_company_id";

export function CompanyProvider({ children }: { children: React.ReactNode }) {
  const [availableCompanies, setAvailableCompanies] = useState<Company[]>([]);
  const [activeCompany, setActiveCompanyState] = useState<Company | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const refreshCompanies = useCallback(async (): Promise<Company | null> => {
    if (!isAuthenticated()) {
      setLoading(false);
      return null;
    }

    try {
      const token = getAccessToken();
      const res = await axios.get(`${API_BASE_URL}/api/v1/companies/`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      const list: Company[] = Array.isArray(res.data)
        ? res.data
        : (res.data?.data && Array.isArray(res.data.data) ? res.data.data : []);

      setAvailableCompanies(list);

      if (list.length === 0) {
        setActiveCompanyState(null);
        setLoading(false);
        return null;
      }

      const savedId = typeof window !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null;
      let selected = list.find((c) => c.id === savedId);

      if (!selected) {
        selected = list[0];
      }

      setActiveCompanyState(selected);
      if (typeof window !== "undefined" && selected) {
        localStorage.setItem(STORAGE_KEY, selected.id);
      }
      setLoading(false);
      return selected;
    } catch (err) {
      console.error("Failed to load companies in CompanyProvider:", err);
      setLoading(false);
      return null;
    }
  }, []);

  const setActiveCompany = (company: Company) => {
    setActiveCompanyState(company);
    if (typeof window !== "undefined" && company) {
      localStorage.setItem(STORAGE_KEY, company.id);
    }
  };

  useEffect(() => {
    refreshCompanies();
  }, [refreshCompanies]);

  return (
    <CompanyContext.Provider
      value={{
        activeCompany,
        availableCompanies,
        companyId: activeCompany?.id || null,
        loading,
        setActiveCompany,
        refreshCompanies,
      }}
    >
      {children}
    </CompanyContext.Provider>
  );
}

export function useCompany() {
  const context = useContext(CompanyContext);
  if (!context) {
    throw new Error("useCompany must be used within a CompanyProvider");
  }
  return context;
}
