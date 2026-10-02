"use client";
import React, { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { getUser } from "@/utils/auth";

interface AccountantModeContextType {
  isAccountantMode: boolean;
  toggleAccountantMode: () => void;
  setAccountantMode: (val: boolean) => void;
}

const AccountantModeContext = createContext<AccountantModeContextType | undefined>(undefined);

export function AccountantModeProvider({ children }: { children: ReactNode }) {
  const [isAccountantMode, setIsAccountantModeState] = useState<boolean>(false);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("vouch_accountant_mode");
      if (stored !== null) {
        setIsAccountantModeState(stored === "true");
      } else {
        // Intelligent default: if user role is CA (Chartered Accountant), default to true
        const user = getUser();
        const defaultMode = user?.role === "CA";
        setIsAccountantModeState(defaultMode);
        localStorage.setItem("vouch_accountant_mode", String(defaultMode));
      }
    }
  }, []);

  const setAccountantMode = (val: boolean) => {
    setIsAccountantModeState(val);
    if (typeof window !== "undefined") {
      localStorage.setItem("vouch_accountant_mode", String(val));
      window.dispatchEvent(
        new CustomEvent("vouch:mode-changed", { detail: { isAccountantMode: val } })
      );
    }
  };

  const toggleAccountantMode = () => {
    setAccountantMode(!isAccountantMode);
  };

  useEffect(() => {
    const handleModeChange = (e: Event) => {
      const customEvent = e as CustomEvent<{ isAccountantMode: boolean }>;
      if (customEvent.detail && typeof customEvent.detail.isAccountantMode === "boolean") {
        setIsAccountantModeState(customEvent.detail.isAccountantMode);
      }
    };
    window.addEventListener("vouch:mode-changed", handleModeChange);
    return () => window.removeEventListener("vouch:mode-changed", handleModeChange);
  }, []);

  return (
    <AccountantModeContext.Provider
      value={{
        isAccountantMode,
        toggleAccountantMode,
        setAccountantMode,
      }}
    >
      {children}
    </AccountantModeContext.Provider>
  );
}

export function useAccountantMode(): AccountantModeContextType {
  const context = useContext(AccountantModeContext);
  if (!context) {
    throw new Error("useAccountantMode must be used within an AccountantModeProvider");
  }
  return context;
}
