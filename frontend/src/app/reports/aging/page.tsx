"use client";
import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { useRouter } from "next/navigation";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import { API_BASE_URL } from "@/utils/api";
import { useCompany } from "@/context/CompanyContext";
import { useFinancialYear } from "@/context/FinancialYearContext";
import DashboardLayout from "@/components/DashboardLayout";
import { 
  Clock, 
  AlertCircle, 
  ArrowRight, 
  RefreshCw, 
  CheckCircle2, 
  Zap, 
  Filter, 
  Building2, 
  Phone,
  ShieldAlert
} from "lucide-react";

export default function AgingReportPage() {
  const router = useRouter();
  const { activeCompany, companyId: activeCompanyId } = useCompany();
  const { activeFY } = useFinancialYear();
  const [partyType, setPartyType] = useState<"CUSTOMER" | "SUPPLIER">("CUSTOMER");
  const [loading, setLoading] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [reportData, setReportData] = useState<any>(null);
  const [notification, setNotification] = useState<string | null>(null);

  const companyId = activeCompanyId || (typeof window !== "undefined" ? localStorage.getItem("vouch_active_company_id") || "" : "");

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
    }
  }, [router]);

  const loadAgingData = useCallback(async () => {
    if (!companyId) return;
    setLoading(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const params = new URLSearchParams();
      params.append('type', partyType);
      if (activeFY?.id) params.append('financial_year_id', activeFY.id);
      if (activeFY?.start_date) params.append('start_date', activeFY.start_date);
      if (activeFY?.end_date) {
        params.append('end_date', activeFY.end_date);
        params.append('as_of_date', activeFY.end_date);
      }
      const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/reports/aging/${companyId}/?${params.toString()}`, { headers });
      setReportData(res.data.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [companyId, partyType, activeFY?.id]);

  useEffect(() => {
    if (companyId) {
      loadAgingData();
    }
  }, [companyId, partyType, loadAgingData, activeFY?.id]);

  const handleAutoFIFO = async () => {
    if (!companyId) return;
    setReconciling(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.post(`${API_BASE_URL}/api/v1/accounting/allocation/auto-fifo/${companyId}/`, {}, { headers });
      setNotification(res.data.message || "Auto-reconciliation finished.");
      loadAgingData();
    } catch (e) {
      console.error(e);
      alert("Failed to run auto-FIFO reconciliation.");
    } finally {
      setReconciling(false);
    }
  };

  const summary = reportData?.summary || {};
  const parties = reportData?.parties || [];

  return (
    <DashboardLayout>
      <div className="space-y-6 max-w-7xl mx-auto pb-12">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="p-2 rounded-xl bg-purple-600/10 text-purple-500 font-bold">
                <Clock className="w-6 h-6" />
              </span>
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <h1 className="text-2xl font-bold tracking-tight">Outstanding Aging Analysis</h1>
                  {activeFY && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-purple-600/10 text-purple-500 border border-purple-500/20">
                      <span>FY {activeFY.code}</span>
                      <span className="text-muted-foreground font-normal text-[11px]">({activeFY.start_date} to {activeFY.end_date})</span>
                    </span>
                  )}
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Track overdue bills by age buckets (0–30, 31–60, 61–90, &gt;90 days) with MSME 45-day statutory compliance.
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleAutoFIFO}
              disabled={reconciling}
              className="px-3.5 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-xs font-bold shadow-md flex items-center gap-1.5 transition-all cursor-pointer"
            >
              <Zap className={`w-3.5 h-3.5 ${reconciling ? "animate-spin" : ""}`} />
              <span>{reconciling ? "Reconciling..." : "⚡ Auto-Settle Payments (FIFO)"}</span>
            </button>

            <button
              onClick={loadAgingData}
              className="px-3 py-2 bg-muted hover:bg-muted/80 text-foreground rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* Toggle: Receivables vs Payables */}
        <div className="flex items-center justify-between gap-4 bg-card p-3 rounded-2xl border border-border">
          <div className="flex items-center gap-1 p-1 bg-muted rounded-xl">
            <button
              onClick={() => setPartyType("CUSTOMER")}
              className={`px-4 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                partyType === "CUSTOMER" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Receivables (Customers / Debtors)
            </button>
            <button
              onClick={() => setPartyType("SUPPLIER")}
              className={`px-4 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                partyType === "SUPPLIER" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Payables (Suppliers / Creditors)
            </button>
          </div>

          <div className="text-xs text-muted-foreground">
            Showing all outstanding <span className="font-semibold text-foreground">{partyType === "CUSTOMER" ? "sales invoices" : "purchase bills"}</span>
          </div>
        </div>

        {notification && (
          <div className="p-4 bg-emerald-50 border border-emerald-200 text-emerald-900 dark:bg-emerald-950/40 dark:border-emerald-800 dark:text-emerald-300 rounded-xl text-xs flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
              <span>{notification}</span>
            </div>
            <button onClick={() => setNotification(null)} className="font-bold hover:opacity-70">✕</button>
          </div>
        )}

        {/* 5 Aging Bucket Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {/* Total */}
          <div className="p-4 bg-card border border-border rounded-xl space-y-1 shadow-xs">
            <div className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">Total Outstanding</div>
            <div className="text-xl font-black text-foreground font-mono">
              ₹{(reportData?.total_outstanding ?? 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
          </div>

          {/* Current (Not Due) */}
          <div className="p-4 bg-card border border-emerald-500/20 bg-gradient-to-br from-card to-emerald-500/5 rounded-xl space-y-1 shadow-xs">
            <div className="text-[11px] font-bold text-emerald-700 dark:text-emerald-400 uppercase tracking-wider">Not Due Yet</div>
            <div className="text-xl font-bold text-foreground font-mono">
              ₹{(summary?.current ?? 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
          </div>

          {/* 1-30 Days */}
          <div className="p-4 bg-card border border-blue-500/20 bg-gradient-to-br from-card to-blue-500/5 rounded-xl space-y-1 shadow-xs">
            <div className="text-[11px] font-bold text-blue-700 dark:text-blue-400 uppercase tracking-wider">1–30 Days</div>
            <div className="text-xl font-bold text-foreground font-mono">
              ₹{(summary?.days_1_30 ?? 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
          </div>

          {/* 31-60 Days */}
          <div className="p-4 bg-card border border-amber-500/20 bg-gradient-to-br from-card to-amber-500/5 rounded-xl space-y-1 shadow-xs">
            <div className="text-[11px] font-bold text-amber-700 dark:text-amber-400 uppercase tracking-wider">31–60 Days</div>
            <div className="text-xl font-bold text-foreground font-mono">
              ₹{(summary?.days_31_60 ?? 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
          </div>

          {/* 61-90 Days */}
          <div className="p-4 bg-card border border-orange-500/20 bg-gradient-to-br from-card to-orange-500/5 rounded-xl space-y-1 shadow-xs">
            <div className="text-[11px] font-bold text-orange-700 dark:text-orange-400 uppercase tracking-wider">61–90 Days</div>
            <div className="text-xl font-bold text-foreground font-mono">
              ₹{(summary?.days_61_90 ?? 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
          </div>

          {/* >90 Days */}
          <div className="p-4 bg-card border border-red-500/30 bg-gradient-to-br from-card to-red-500/10 rounded-xl space-y-1 shadow-xs">
            <div className="text-[11px] font-bold text-red-700 dark:text-red-400 uppercase tracking-wider">&gt;90 Days (Critical)</div>
            <div className="text-xl font-black text-red-600 dark:text-red-400 font-mono">
              ₹{(summary?.above_90 ?? 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
          </div>
        </div>

        {/* MSME Alert Banner */}
        {(summary?.msme_overdue_count ?? 0) > 0 && (
          <div className="p-4 bg-amber-50 border border-amber-200 dark:bg-amber-950/40 dark:border-amber-800 rounded-2xl flex items-center justify-between text-xs text-amber-900 dark:text-amber-300">
            <div className="flex items-center gap-2.5">
              <ShieldAlert className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0" />
              <span>
                <strong>MSME Section 43B(h) Warning:</strong> You have{" "}
                <strong>{summary.msme_overdue_count} overdue invoice(s)</strong> exceeding 45 days. In India, payments to MSME registered suppliers must be settled within 45 days to claim tax deductions.
              </span>
            </div>
          </div>
        )}

        {/* Aging Details Table */}
        <div className="bg-card border border-border rounded-2xl p-5 shadow-xs space-y-4 text-xs">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <h3 className="font-bold text-foreground flex items-center gap-2">
              <Building2 className="w-4 h-4 text-muted-foreground" />
              <span>Party-wise Aging Breakdown ({parties.length})</span>
            </h3>
          </div>

          {parties.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground space-y-2">
              <div className="text-3xl">🎉</div>
              <div className="font-bold text-foreground">Zero Outstanding Overdue Bills!</div>
              <p className="text-xs max-w-sm mx-auto">
                All bills have been settled or allocated. Keep entering sales and purchases freely.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-border text-muted-foreground uppercase font-semibold text-[11px] tracking-wider">
                    <th className="pb-3">Party Name</th>
                    <th className="pb-3 text-center">Bills</th>
                    <th className="pb-3 text-right">Total O/S (₹)</th>
                    <th className="pb-3 text-right">Not Due (₹)</th>
                    <th className="pb-3 text-right">1–30d (₹)</th>
                    <th className="pb-3 text-right">31–60d (₹)</th>
                    <th className="pb-3 text-right">61–90d (₹)</th>
                    <th className="pb-3 text-right">&gt;90d (₹)</th>
                    <th className="pb-3 text-center">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {parties.map((p: any) => (
                    <tr key={p.party_id} className="hover:bg-muted/40 transition-colors">
                      <td className="py-3">
                        <div className="font-bold text-foreground">{p.party_name}</div>
                        <div className="text-[11px] text-muted-foreground font-mono">
                          {p.gstin || (p.phone ? `Ph: ${p.phone}` : "No GSTIN")}
                        </div>
                      </td>

                      <td className="py-3 text-center font-mono font-bold text-muted-foreground">
                        {p.bills_count}
                      </td>

                      <td className="py-3 text-right font-mono font-black text-foreground">
                        ₹{p.total_outstanding.toFixed(2)}
                      </td>

                      <td className="py-3 text-right font-mono text-muted-foreground">
                        {p.current > 0 ? `₹${p.current.toFixed(2)}` : "—"}
                      </td>

                      <td className="py-3 text-right font-mono font-semibold text-blue-600 dark:text-blue-400">
                        {p.days_1_30 > 0 ? `₹${p.days_1_30.toFixed(2)}` : "—"}
                      </td>

                      <td className="py-3 text-right font-mono font-semibold text-amber-700 dark:text-amber-400">
                        {p.days_31_60 > 0 ? `₹${p.days_31_60.toFixed(2)}` : "—"}
                      </td>

                      <td className="py-3 text-right font-mono font-semibold text-orange-700 dark:text-orange-400">
                        {p.days_61_90 > 0 ? `₹${p.days_61_90.toFixed(2)}` : "—"}
                      </td>

                      <td className="py-3 text-right font-mono font-bold text-red-600 dark:text-red-400">
                        {p.above_90 > 0 ? `₹${p.above_90.toFixed(2)}` : "—"}
                      </td>

                      <td className="py-3 text-center">
                        {p.msme_overdue ? (
                          <span className="px-2 py-0.5 bg-amber-50 text-amber-800 border border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800 rounded text-[10px] font-bold">
                            &gt;45d Overdue
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 bg-emerald-50 text-emerald-800 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800 rounded text-[10px] font-semibold">
                            Compliant
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
