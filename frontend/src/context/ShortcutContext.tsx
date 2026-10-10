"use client";
import React, { createContext, useContext, useState, useRef, useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useHotkeys } from "react-hotkeys-hook";

interface ShortcutContextType {
  isHelpOpen: boolean;
  setIsHelpOpen: (open: boolean) => void;
  isDateOpen: boolean;
  setIsDateOpen: (open: boolean) => void;
  isAltCOpen: boolean;
  setIsAltCOpen: (open: boolean) => void;
  isCalculatorOpen: boolean;
  setIsCalculatorOpen: (open: boolean) => void;
  altCEntityType: "LEDGER" | "PRODUCT";
  setAltCEntityType: (type: "LEDGER" | "PRODUCT") => void;
  workingDate: string;
  setWorkingDate: (date: string) => void;
  registerSaveHandler: (fn: () => void) => () => void;
  triggerSave: () => void;
  registerDeleteLineHandler: (fn: () => void) => () => void;
  triggerDeleteLine: () => void;
  registerExportHandler: (fn: () => void) => () => void;
  triggerExport: () => void;
  registerEditMasterHandler: (fn: () => void) => () => void;
  triggerEditMaster: () => void;
  registerAltCCallback: (cb: (entity: any) => void) => void;
  notifyAltCCreated: (entity: any) => void;
  startTour: () => void;
  setTourStarter: (fn: () => void) => void;
}

const ShortcutContext = createContext<ShortcutContextType | null>(null);

export function ShortcutProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();

  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const [isDateOpen, setIsDateOpen] = useState(false);
  const [isAltCOpen, setIsAltCOpen] = useState(false);
  const [isCalculatorOpen, setIsCalculatorOpen] = useState(false);
  const [altCEntityType, setAltCEntityType] = useState<"LEDGER" | "PRODUCT">("LEDGER");
  const [workingDate, setWorkingDate] = useState<string>(() => new Date().toISOString().split("T")[0]);

  const saveHandlerRef = useRef<(() => void) | null>(null);
  const deleteLineHandlerRef = useRef<(() => void) | null>(null);
  const exportHandlerRef = useRef<(() => void) | null>(null);
  const editMasterHandlerRef = useRef<(() => void) | null>(null);
  const altCCallbackRef = useRef<((entity: any) => void) | null>(null);
  const tourStarterRef = useRef<(() => void) | null>(null);

  const registerSaveHandler = useCallback((fn: () => void) => {
    saveHandlerRef.current = fn;
    return () => {
      if (saveHandlerRef.current === fn) {
        saveHandlerRef.current = null;
      }
    };
  }, []);

  const triggerSave = useCallback(() => {
    if (saveHandlerRef.current) {
      saveHandlerRef.current();
    }
  }, []);

  const registerDeleteLineHandler = useCallback((fn: () => void) => {
    deleteLineHandlerRef.current = fn;
    return () => {
      if (deleteLineHandlerRef.current === fn) {
        deleteLineHandlerRef.current = null;
      }
    };
  }, []);

  const triggerDeleteLine = useCallback(() => {
    if (deleteLineHandlerRef.current) {
      deleteLineHandlerRef.current();
    } else if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("shrilekh:delete-line"));
    }
  }, []);

  const registerExportHandler = useCallback((fn: () => void) => {
    exportHandlerRef.current = fn;
    return () => {
      if (exportHandlerRef.current === fn) {
        exportHandlerRef.current = null;
      }
    };
  }, []);

  const triggerExport = useCallback(() => {
    if (exportHandlerRef.current) {
      exportHandlerRef.current();
    } else {
      router.push("/export/tally");
    }
  }, [router]);

  const registerEditMasterHandler = useCallback((fn: () => void) => {
    editMasterHandlerRef.current = fn;
    return () => {
      if (editMasterHandlerRef.current === fn) {
        editMasterHandlerRef.current = null;
      }
    };
  }, []);

  const triggerEditMaster = useCallback(() => {
    if (editMasterHandlerRef.current) {
      editMasterHandlerRef.current();
    } else if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("shrilekh:edit-master"));
    }
  }, []);

  const registerAltCCallback = useCallback((cb: (entity: any) => void) => {
    altCCallbackRef.current = cb;
  }, []);

  const notifyAltCCreated = useCallback((entity: any) => {
    if (altCCallbackRef.current) {
      altCCallbackRef.current(entity);
      altCCallbackRef.current = null;
    }
  }, []);

  const setTourStarter = useCallback((fn: () => void) => {
    tourStarterRef.current = fn;
  }, []);

  const startTour = useCallback(() => {
    if (tourStarterRef.current) {
      tourStarterRef.current();
    }
  }, []);

  // F1: Help Cheat Sheet
  useHotkeys("f1", (e) => {
    e.preventDefault();
    setIsHelpOpen((prev) => !prev);
  }, { enableOnFormTags: true });

  // F2: Date / Period Modal
  useHotkeys("f2", (e) => {
    e.preventDefault();
    setIsDateOpen((prev) => !prev);
  }, { enableOnFormTags: true });

  // F4: Contra Voucher
  useHotkeys("f4", (e) => {
    e.preventDefault();
    router.push("/vouchers/new?type=CONTRA");
  }, { enableOnFormTags: true });

  // F5: Payment Voucher
  useHotkeys("f5", (e) => {
    e.preventDefault();
    router.push("/vouchers/new?type=PAYMENT");
  }, { enableOnFormTags: true });

  // F6: Receipt Voucher
  useHotkeys("f6", (e) => {
    e.preventDefault();
    router.push("/vouchers/new?type=RECEIPT");
  }, { enableOnFormTags: true });

  // F7: Journal Voucher
  useHotkeys("f7", (e) => {
    e.preventDefault();
    router.push("/vouchers/new?type=JOURNAL");
  }, { enableOnFormTags: true });

  // F8: Sales Voucher
  useHotkeys("f8", (e) => {
    e.preventDefault();
    router.push("/sales/new");
  }, { enableOnFormTags: true });

  // F9: Purchase Voucher
  useHotkeys("f9", (e) => {
    e.preventDefault();
    router.push("/purchases/new");
  }, { enableOnFormTags: true });

  // Alt + F6: Credit Note (Sales Return)
  useHotkeys("alt+f6, option+f6", (e) => {
    e.preventDefault();
    router.push("/vouchers/credit-note?type=CREDIT_NOTE");
  }, { enableOnFormTags: true });

  // Alt + F5: Debit Note (Purchase Return)
  useHotkeys("alt+f5, option+f5", (e) => {
    e.preventDefault();
    router.push("/vouchers/credit-note?type=DEBIT_NOTE");
  }, { enableOnFormTags: true });

  // Alt + N or Ctrl + N or Alt + K: Tally Calculator (Alt+N avoids browser Ctrl+N "New Window" conflict)
  useHotkeys(["alt+n", "option+n", "alt+k", "ctrl+n", "meta+n"], (e) => {
    e.preventDefault();
    setIsCalculatorOpen((prev) => !prev);
  }, { enableOnFormTags: true });

  // Ctrl + M: Close Calculator / Return to Voucher Entry
  useHotkeys(["ctrl+m", "meta+m"], (e) => {
    if (isCalculatorOpen) {
      e.preventDefault();
      setIsCalculatorOpen(false);
    }
  }, { enableOnFormTags: true });

  // Alt + D: Delete Line Item or Voucher
  useHotkeys(["alt+d", "option+d"], (e) => {
    e.preventDefault();
    triggerDeleteLine();
  }, { enableOnFormTags: true });

  // Alt + E: Export to Excel / CSV / Tally
  useHotkeys(["alt+e", "option+e"], (e) => {
    e.preventDefault();
    triggerExport();
  }, { enableOnFormTags: true });

  // Ctrl + Enter: Alter / Edit Master Inline
  useHotkeys(["ctrl+enter", "meta+enter"], (e) => {
    e.preventDefault();
    triggerEditMaster();
  }, { enableOnFormTags: true });

  // Esc: Close open modal / calculator or Go Back
  useHotkeys("escape", (e) => {
    if (isCalculatorOpen) {
      e.preventDefault();
      setIsCalculatorOpen(false);
    } else if (isHelpOpen || isDateOpen || isAltCOpen) {
      e.preventDefault();
      setIsHelpOpen(false);
      setIsDateOpen(false);
      setIsAltCOpen(false);
    } else if (pathname !== "/" && pathname !== "/login") {
      e.preventDefault();
      router.back();
    }
  }, { enableOnFormTags: true });

  // Alt + P: Print Active Invoice
  useHotkeys("alt+p, option+p", (e) => {
    e.preventDefault();
    if (typeof window !== "undefined") {
      window.print();
    }
  }, { enableOnFormTags: true });

  // Alt + C: Create on the Fly
  useHotkeys("alt+c, option+c", (e) => {
    e.preventDefault();
    const activeEl = document.activeElement;
    const isProductContext =
      activeEl?.getAttribute("data-entity") === "product" ||
      activeEl?.closest("[data-entity='product']") !== null;

    setAltCEntityType(isProductContext ? "PRODUCT" : "LEDGER");
    setIsAltCOpen(true);
  }, { enableOnFormTags: true });

  // Ctrl + A / Cmd + A: Save / Accept Active Form (intercepted ONLY if a save handler is registered)
  useHotkeys(["ctrl+a", "meta+a"], (e) => {
    if (saveHandlerRef.current) {
      e.preventDefault();
      saveHandlerRef.current();
    }
  }, { enableOnFormTags: true });

  return (
    <ShortcutContext.Provider
      value={{
        isHelpOpen,
        setIsHelpOpen,
        isDateOpen,
        setIsDateOpen,
        isAltCOpen,
        setIsAltCOpen,
        isCalculatorOpen,
        setIsCalculatorOpen,
        altCEntityType,
        setAltCEntityType,
        workingDate,
        setWorkingDate,
        registerSaveHandler,
        triggerSave,
        registerDeleteLineHandler,
        triggerDeleteLine,
        registerExportHandler,
        triggerExport,
        registerEditMasterHandler,
        triggerEditMaster,
        registerAltCCallback,
        notifyAltCCreated,
        startTour,
        setTourStarter,
      }}
    >
      {children}
    </ShortcutContext.Provider>
  );
}

export function useShortcuts() {
  const context = useContext(ShortcutContext);
  if (!context) {
    throw new Error("useShortcuts must be used within a ShortcutProvider");
  }
  return context;
}
