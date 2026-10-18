"use client";
import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import api from "@/utils/api";
import { isAuthenticated } from "@/utils/auth";
import { offlineDb } from "@/lib/db/offlineDb";

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
const CACHED_COMPANIES_KEY = "vouch_cached_companies_list";

export function CompanyProvider({ children }: { children: React.ReactNode }) {
  const [availableCompanies, setAvailableCompanies] = useState<Company[]>([]);
  const [activeCompany, setActiveCompanyState] = useState<Company | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  // Safe client-side rehydration preventing React #418 SSR mismatch
  useEffect(() => {
    try {
      const cached = localStorage.getItem(CACHED_COMPANIES_KEY);
      if (cached) {
        const list: Company[] = JSON.parse(cached);
        if (Array.isArray(list) && list.length > 0) {
          setAvailableCompanies(list);
          const savedId = localStorage.getItem(STORAGE_KEY);
          const found = list.find((c) => c.id === savedId) || list[0] || null;
          if (found) {
            setActiveCompanyState(found);
            setLoading(false);
          }
        }
      }
    } catch {}

    // Fallback: load companies from IndexedDB
    offlineDb.masters.get('all_companies').then((entry) => {
      if (entry?.data && Array.isArray(entry.data) && entry.data.length > 0) {
        setAvailableCompanies((prev) => (prev.length > 0 ? prev : entry.data));
        const savedId = typeof window !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null;
        const found = entry.data.find((c: any) => c.id === savedId) || entry.data[0];
        if (found) {
          setActiveCompanyState((prev) => prev || found);
          setLoading(false);
        }
      }
    }).catch(() => {});
  }, []);

  const refreshCompanies = useCallback(async (): Promise<Company | null> => {
    // If offline: skip network call immediately and use local cache
    if (typeof navigator !== "undefined" && !navigator.onLine) {
      if (typeof window !== "undefined") {
        try {
          const cached = localStorage.getItem(CACHED_COMPANIES_KEY);
          if (cached) {
            const list: Company[] = JSON.parse(cached);
            if (Array.isArray(list) && list.length > 0) {
              setAvailableCompanies(list);
              const savedId = localStorage.getItem(STORAGE_KEY) || localStorage.getItem("activeCompanyId");
              const selected = list.find((c) => c.id === savedId) || list[0];
              setActiveCompanyState(selected);
              setLoading(false);
              return selected;
            }
          }
        } catch {}
      }
      try {
        const entry = await offlineDb.masters.get('all_companies');
        if (entry?.data && Array.isArray(entry.data) && entry.data.length > 0) {
          setAvailableCompanies(entry.data);
          const savedId = typeof window !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null;
          const selected = entry.data.find((c: any) => c.id === savedId) || entry.data[0];
          setActiveCompanyState(selected);
          setLoading(false);
          return selected;
        }
      } catch {}
      setLoading(false);
      return null;
    }

    if (!isAuthenticated()) {
      setLoading(false);
      return null;
    }

    try {
      const res = await api.get('/api/v1/companies/');

      const list: Company[] = Array.isArray(res.data)
        ? res.data
        : (res.data?.data && Array.isArray(res.data.data) ? res.data.data : []);

      setAvailableCompanies(list);
      if (typeof window !== "undefined") {
        try {
          localStorage.setItem(CACHED_COMPANIES_KEY, JSON.stringify(list));
        } catch {}
      }
      // Persist in IndexedDB for resilient offline cold starts
      offlineDb.masters.put({ key: 'all_companies', data: list, updatedAt: Date.now() }).catch(() => {});

      if (list.length === 0) {
        setActiveCompanyState(null);
        if (typeof window !== "undefined") {
          localStorage.removeItem(CACHED_COMPANIES_KEY);
        }
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
        localStorage.setItem("activeCompanyId", selected.id);
        localStorage.setItem("vouch_active_company", selected.id);
        localStorage.setItem("vouch_active_company_name", selected.name || "");
      }
      setLoading(false);
      return selected;
    } catch (err) {
      console.warn("Failed to fetch companies from cloud, falling back to local storage:", err);
      if (typeof window !== "undefined") {
        try {
          const cached = localStorage.getItem(CACHED_COMPANIES_KEY);
          if (cached) {
            const list: Company[] = JSON.parse(cached);
            if (Array.isArray(list) && list.length > 0) {
              setAvailableCompanies(list);
              const savedId = localStorage.getItem(STORAGE_KEY) || localStorage.getItem("activeCompanyId");
              const selected = list.find((c) => c.id === savedId) || list[0];
              setActiveCompanyState(selected);
              setLoading(false);
              return selected;
            }
          }
        } catch {}
      }
      try {
        const entry = await offlineDb.masters.get('all_companies');
        if (entry?.data && Array.isArray(entry.data) && entry.data.length > 0) {
          setAvailableCompanies(entry.data);
          const savedId = typeof window !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null;
          const selected = entry.data.find((c: any) => c.id === savedId) || entry.data[0];
          setActiveCompanyState(selected);
          setLoading(false);
          return selected;
        }
      } catch {}
      setLoading(false);
      return null;
    }
  }, []);

  const setActiveCompany = (company: Company) => {
    setActiveCompanyState(company);
    if (typeof window !== "undefined" && company) {
      localStorage.setItem(STORAGE_KEY, company.id);
      localStorage.setItem("activeCompanyId", company.id);
      localStorage.setItem("vouch_active_company", company.id);
      localStorage.setItem("vouch_active_company_name", company.name || "");
      // Sync to Capacitor native Preferences if available
      try {
        const cap = (window as any).Capacitor;
        if (cap?.Plugins?.Preferences) {
          cap.Plugins.Preferences.set({ key: 'vouch_active_company_id', value: company.id });
          cap.Plugins.Preferences.set({ key: 'vouch_active_company_name', value: company.name || '' });
          if (company.state_code) {
            cap.Plugins.Preferences.set({ key: 'vouch_active_company_state_code', value: company.state_code });
          }
          if (company.gstin) {
            cap.Plugins.Preferences.set({ key: 'vouch_active_company_gstin', value: company.gstin });
          }
        }
      } catch {}
      // Retain company in IndexedDB
      offlineDb.masters.put({ key: `company_${company.id}`, data: company, updatedAt: Date.now() }).catch(() => {});
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
