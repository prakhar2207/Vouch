"use client";
import React, { createContext, useContext, useState, useCallback } from "react";
import { CheckCircle2, AlertTriangle, XCircle, Info, X } from "lucide-react";

export interface ToastMessage {
  id: string;
  type: "success" | "error" | "warning" | "info";
  message: string;
  description?: string;
  duration?: number;
}

interface ToastContextValue {
  toast: {
    success: (message: string, description?: string) => void;
    error: (message: string, description?: string) => void;
    warning: (message: string, description?: string) => void;
    info: (message: string, description?: string) => void;
  };
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const addToast = useCallback(
    (type: ToastMessage["type"], message: string, description?: string) => {
      const id = `${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
      setToasts((prev) => [...prev, { id, type, message, description }]);

      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 4000);
    },
    []
  );

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = {
    success: (msg: string, desc?: string) => addToast("success", msg, desc),
    error: (msg: string, desc?: string) => addToast("error", msg, desc),
    warning: (msg: string, desc?: string) => addToast("warning", msg, desc),
    info: (msg: string, desc?: string) => addToast("info", msg, desc),
  };

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      {/* Sleek In-App Toast Container (top-right) */}
      <div className="fixed top-5 right-5 z-[9999] flex flex-col gap-2.5 max-w-sm w-full pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`pointer-events-auto p-3.5 rounded-xl border shadow-2xl backdrop-blur-md flex items-start justify-between gap-3 animate-in slide-in-from-top-3 fade-in duration-200 ${
              t.type === "success"
                ? "bg-zinc-900/95 border-emerald-500/40 text-white"
                : t.type === "error"
                ? "bg-zinc-900/95 border-rose-500/40 text-white"
                : t.type === "warning"
                ? "bg-zinc-900/95 border-amber-500/40 text-white"
                : "bg-zinc-900/95 border-blue-500/40 text-white"
            }`}
          >
            <div className="flex items-start gap-3 min-w-0">
              {t.type === "success" && (
                <div className="w-6 h-6 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center shrink-0 mt-0.5">
                  <CheckCircle2 className="w-4 h-4" />
                </div>
              )}
              {t.type === "error" && (
                <div className="w-6 h-6 rounded-full bg-rose-500/20 text-rose-400 flex items-center justify-center shrink-0 mt-0.5">
                  <XCircle className="w-4 h-4" />
                </div>
              )}
              {t.type === "warning" && (
                <div className="w-6 h-6 rounded-full bg-amber-500/20 text-amber-400 flex items-center justify-center shrink-0 mt-0.5">
                  <AlertTriangle className="w-4 h-4" />
                </div>
              )}
              {t.type === "info" && (
                <div className="w-6 h-6 rounded-full bg-blue-500/20 text-blue-400 flex items-center justify-center shrink-0 mt-0.5">
                  <Info className="w-4 h-4" />
                </div>
              )}
              <div className="min-w-0">
                <p className="text-xs font-bold leading-snug break-words">{t.message}</p>
                {t.description && (
                  <p className="text-[11px] text-zinc-400 mt-0.5 break-words">{t.description}</p>
                )}
              </div>
            </div>
            <button
              onClick={() => removeToast(t.id)}
              className="p-1 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors shrink-0 cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    return {
      toast: {
        success: (m: string) => console.log("[Success]", m),
        error: (m: string) => console.error("[Error]", m),
        warning: (m: string) => console.warn("[Warning]", m),
        info: (m: string) => console.info("[Info]", m),
      },
    };
  }
  return context;
}
