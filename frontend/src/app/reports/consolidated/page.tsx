"use client";

import React, { useState, useEffect } from "react";
import axios from "axios";
import Link from "next/link";
import { 
  Building2, 
  Landmark, 
  TrendingUp, 
  TrendingDown, 
  CheckCircle2, 
  AlertCircle, 
  RefreshCw, 
  Layers, 
  ArrowRight, 
  Check, 
  X, 
  ShieldCheck, 
  ArrowLeftRight, 
  Sliders, 
  FileText,
  DollarSign,
  Sparkles,
  ExternalLink
} from "lucide-react";
import DashboardLayout from "@/components/DashboardLayout";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import { API_BASE_URL } from "@/utils/api";
import { useToast } from "@/context/ToastContext";
import { useCompany } from "@/context/CompanyContext";

export default function ConsolidatedReportsPage() {
  const { toast } = useToast();
  const { activeCompany, setActiveCompany, availableCompanies } = useCompany();

  const [activeTab, setActiveTab] = useState<"mis" | "inter-company">("mis");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Consolidated MIS Data
  const [misData, setMisData] = useState<any>(null);

  // Inter-Company Data
  const [inboxEntries, setInboxEntries] = useState<any[]>([]);
  const [selectedSisterId, setSelectedSisterId] = useState<string>("");
  const [matrixData, setMatrixData] = useState<any>(null);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);

  useEffect(() => {
    fetchConsolidatedData();
  }, []);

  useEffect(() => {
    if (activeTab === "inter-company") {
      fetchInterCompanyInbox();
      if (selectedSisterId) {
        fetchReconciliationMatrix(selectedSisterId);
      }
    }
  }, [activeTab, selectedSisterId]);

  const fetchConsolidatedData = async () => {
    setLoading(true);
    try {
      const token = getAccessToken();
      const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/consolidated-financials/`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.data.success) {
        setMisData(res.data.data);
        const sisterList = (res.data.data.entities || []).filter(
          (e: any) => e.company_id !== activeCompany?.id
        );
        if (sisterList.length > 0 && !selectedSisterId) {
          setSelectedSisterId(sisterList[0].company_id);
        }
      }
    } catch (err: any) {
      toast.error("Failed to load consolidated financials", err.message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const fetchInterCompanyInbox = async () => {
    try {
      const token = getAccessToken();
      const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/inter-company/inbox/`, {
        headers: { 
          Authorization: `Bearer ${token}`,
          "X-Company-ID": activeCompany?.id || ""
        }
      });
      if (res.data.success) {
        setInboxEntries(res.data.results || []);
      }
    } catch (err: any) {
      console.error(err);
    }
  };

  const fetchReconciliationMatrix = async (sisterId: string) => {
    try {
      const token = getAccessToken();
      const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/inter-company/reconcile/?sister_company_id=${sisterId}`, {
        headers: { 
          Authorization: `Bearer ${token}`,
          "X-Company-ID": activeCompany?.id || ""
        }
      });
      if (res.data.success) {
        setMatrixData(res.data.matrix);
      }
    } catch (err: any) {
      console.error(err);
    }
  };

  const handleAcceptMirror = async (entryId: string) => {
    setActionLoadingId(entryId);
    try {
      const token = getAccessToken();
      const res = await axios.post(
        `${API_BASE_URL}/api/v1/accounting/inter-company/${entryId}/accept/`,
        {},
        {
          headers: { 
            Authorization: `Bearer ${token}`,
            "X-Company-ID": activeCompany?.id || ""
          }
        }
      );
      toast.success("Mirror Voucher Posted", res.data.message || "Counter-voucher generated.");
      fetchInterCompanyInbox();
      if (selectedSisterId) fetchReconciliationMatrix(selectedSisterId);
      fetchConsolidatedData();
    } catch (err: any) {
      toast.error("Acceptance Failed", err.response?.data?.error || err.message);
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleRejectMirror = async (entryId: string) => {
    setActionLoadingId(entryId);
    try {
      const token = getAccessToken();
      const res = await axios.post(
        `${API_BASE_URL}/api/v1/accounting/inter-company/${entryId}/reject/`,
        { reason: "Rejected by accountant" },
        {
          headers: { 
            Authorization: `Bearer ${token}`,
            "X-Company-ID": activeCompany?.id || ""
          }
        }
      );
      toast.info("Mirror Entry Rejected", res.data.message);
      fetchInterCompanyInbox();
    } catch (err: any) {
      toast.error("Rejection Failed", err.response?.data?.error || err.message);
    } finally {
      setActionLoadingId(null);
    }
  };

  const summary = misData?.summary;
  const entities = misData?.entities || [];
  const eliminations = misData?.eliminations || [];

  return (
    <DashboardLayout>
      <div className="space-y-6 pb-16">
        {/* Top Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-border/40 pb-5">
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <div className="p-2 rounded-xl bg-purple-500/10 text-purple-500">
                <Layers className="w-5 h-5" />
              </div>
              <h1 className="text-xl sm:text-2xl font-extrabold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">
                Consolidated Group Financials
              </h1>
              {summary && (
                <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-purple-500/10 text-purple-400 border border-purple-500/20">
                  {summary.total_companies} Sister Entities
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Automated inter-company eliminations, group cash & bank aggregation, and mirror ledger reconciliation.
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              onClick={() => {
                setRefreshing(true);
                fetchConsolidatedData();
                if (activeTab === "inter-company") {
                  fetchInterCompanyInbox();
                  if (selectedSisterId) fetchReconciliationMatrix(selectedSisterId);
                }
              }}
              disabled={refreshing}
              className="p-2 rounded-xl border border-border/60 bg-card hover:bg-muted text-foreground cursor-pointer shadow-2xs transition-all disabled:opacity-50"
              title="Refresh Financials"
            >
              <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin text-primary" : ""}`} />
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-2 border-b border-border/40 pb-2">
          <button
            onClick={() => setActiveTab("mis")}
            className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center gap-2 ${
              activeTab === "mis"
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5" />
            <span>Group MIS & Financials</span>
          </button>
          <button
            onClick={() => setActiveTab("inter-company")}
            className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center gap-2 ${
              activeTab === "inter-company"
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
            }`}
          >
            <ArrowLeftRight className="w-3.5 h-3.5" />
            <span>Inter-Company Mirroring</span>
            {inboxEntries.filter((e) => e.status === "PENDING").length > 0 && (
              <span className="w-4 h-4 rounded-full bg-amber-500 text-black text-[10px] font-bold flex items-center justify-center">
                {inboxEntries.filter((e) => e.status === "PENDING").length}
              </span>
            )}
          </button>
        </div>

        {loading ? (
          <div className="flex flex-col items-center justify-center p-20 space-y-3">
            <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
            <p className="text-xs text-muted-foreground">Consolidating books across sister companies...</p>
          </div>
        ) : activeTab === "mis" ? (
          <div className="space-y-6">
            {/* 4 Master KPI Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Liquid Cash & Bank */}
              <div className="p-4 rounded-2xl bg-card border border-border/50 shadow-xs space-y-2">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span className="font-semibold uppercase tracking-wider">Group Cash & Bank</span>
                  <Landmark className="w-4 h-4 text-blue-400" />
                </div>
                <div className="text-2xl font-black font-mono tabular-nums text-foreground">
                  ₹{(summary?.total_liquid_cash_and_bank || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Total liquid treasury across all {summary?.total_companies} business entities
                </p>
              </div>

              {/* Net Debtors */}
              <div className="p-4 rounded-2xl bg-card border border-border/50 shadow-xs space-y-2">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span className="font-semibold uppercase tracking-wider">External Receivables</span>
                  <TrendingUp className="w-4 h-4 text-emerald-400" />
                </div>
                <div className="text-2xl font-black font-mono tabular-nums text-foreground">
                  ₹{(summary?.net_consolidated_debtors || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-[11px] text-muted-foreground flex items-center justify-between">
                  <span>Gross: ₹{(summary?.gross_debtors || 0).toLocaleString("en-IN", { minimumFractionDigits: 0 })}</span>
                  <span className="text-emerald-500 font-semibold font-mono">
                    -₹{(summary?.intercompany_debtors_eliminated || 0).toLocaleString("en-IN", { minimumFractionDigits: 0 })} elim
                  </span>
                </div>
              </div>

              {/* Net Creditors */}
              <div className="p-4 rounded-2xl bg-card border border-border/50 shadow-xs space-y-2">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span className="font-semibold uppercase tracking-wider">External Payables</span>
                  <TrendingDown className="w-4 h-4 text-rose-400" />
                </div>
                <div className="text-2xl font-black font-mono tabular-nums text-foreground">
                  ₹{(summary?.net_consolidated_creditors || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-[11px] text-muted-foreground flex items-center justify-between">
                  <span>Gross: ₹{(summary?.gross_creditors || 0).toLocaleString("en-IN", { minimumFractionDigits: 0 })}</span>
                  <span className="text-rose-400 font-semibold font-mono">
                    -₹{(summary?.intercompany_creditors_eliminated || 0).toLocaleString("en-IN", { minimumFractionDigits: 0 })} elim
                  </span>
                </div>
              </div>

              {/* Consolidated Revenue */}
              <div className="p-4 rounded-2xl bg-card border border-border/50 shadow-xs space-y-2">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span className="font-semibold uppercase tracking-wider">Net Group Turnover</span>
                  <Building2 className="w-4 h-4 text-purple-400" />
                </div>
                <div className="text-2xl font-black font-mono tabular-nums text-foreground">
                  ₹{(summary?.net_consolidated_revenue || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <p className="text-[11px] text-muted-foreground">
                  True external revenue (eliminates ₹{(summary?.intercompany_turnover_eliminated || 0).toLocaleString("en-IN")} internal sales)
                </p>
              </div>
            </div>

            {/* Entity Comparison Matrix Table */}
            <div className="bg-card border border-border/60 rounded-2xl p-5 shadow-xs space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-foreground">Sister Companies Breakdown</h3>
                  <p className="text-xs text-muted-foreground">
                    Side-by-side performance metrics across all group businesses
                  </p>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead>
                    <tr className="border-b border-border/60 text-muted-foreground font-semibold">
                      <th className="py-2.5 px-3">Company Name</th>
                      <th className="py-2.5 px-3">GSTIN</th>
                      <th className="py-2.5 px-3 text-right">Cash & Bank</th>
                      <th className="py-2.5 px-3 text-right">Receivables (Debtors)</th>
                      <th className="py-2.5 px-3 text-right">Payables (Creditors)</th>
                      <th className="py-2.5 px-3 text-right">Turnover</th>
                      <th className="py-2.5 px-3 text-right">Net Profit</th>
                      <th className="py-2.5 px-3 text-center">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/30">
                    {entities.map((ent: any) => (
                      <tr key={ent.company_id} className="hover:bg-muted/30 transition-colors">
                        <td className="py-3 px-3 font-semibold text-foreground flex items-center gap-2">
                          <Building2 className="w-3.5 h-3.5 text-muted-foreground" />
                          <span>{ent.company_name}</span>
                          {ent.company_id === activeCompany?.id && (
                            <span className="text-[10px] bg-primary/10 text-primary font-bold px-1.5 py-0.5 rounded">Active</span>
                          )}
                        </td>
                        <td className="py-3 px-3 font-mono text-muted-foreground">{ent.gstin || "—"}</td>
                        <td className="py-3 px-3 text-right font-mono font-semibold text-foreground">
                          ₹{ent.liquid_cash_and_bank.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </td>
                        <td className="py-3 px-3 text-right font-mono text-foreground">
                          ₹{ent.external_debtors.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </td>
                        <td className="py-3 px-3 text-right font-mono text-foreground">
                          ₹{ent.external_creditors.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </td>
                        <td className="py-3 px-3 text-right font-mono text-foreground">
                          ₹{ent.external_revenue.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </td>
                        <td className={`py-3 px-3 text-right font-mono font-bold ${ent.net_profit >= 0 ? "text-emerald-500" : "text-rose-400"}`}>
                          ₹{ent.net_profit.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </td>
                        <td className="py-3 px-3 text-center">
                          {ent.company_id !== activeCompany?.id && (
                            <button
                              onClick={() => {
                                const target = availableCompanies.find((c) => c.id === ent.company_id);
                                if (target) {
                                  setActiveCompany(target);
                                  window.location.reload();
                                }
                              }}
                              className="px-2.5 py-1 text-[11px] font-semibold bg-muted hover:bg-muted/80 rounded-lg text-foreground cursor-pointer transition-colors"
                            >
                              Switch
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Elimination Ledger Audit Log */}
            {eliminations.length > 0 && (
              <div className="bg-card border border-border/60 rounded-2xl p-5 shadow-xs space-y-3">
                <div className="flex items-center gap-2 text-amber-500">
                  <ShieldCheck className="w-4 h-4" />
                  <h3 className="text-xs font-bold uppercase tracking-wider">
                    Statutory Inter-Company Eliminations Audit Log ({eliminations.length} Holdings Removed)
                  </h3>
                </div>
                <p className="text-xs text-muted-foreground">
                  Under Indian Accounting Standards (Ind AS 110), transactions and balances between sister companies are automatically eliminated to prevent artificial revenue and asset inflation.
                </p>
                <div className="space-y-2 pt-2">
                  {eliminations.map((el: any, idx: number) => (
                    <div key={idx} className="p-3 rounded-xl bg-muted/40 border border-border/40 text-xs flex items-center justify-between gap-4">
                      <div>
                        <div className="font-semibold text-foreground flex items-center gap-2">
                          <span className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-500 font-mono text-[10px] uppercase font-bold">
                            {el.type}
                          </span>
                          <span>{el.holding_company} &rarr; {el.counterpart}</span>
                        </div>
                        <p className="text-muted-foreground text-[11px] mt-0.5">{el.rationale}</p>
                      </div>
                      <div className="font-mono font-bold text-rose-400 text-sm shrink-0">
                        -₹{el.amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          /* Inter-Company Mirror Ledgers & Reconciliation Tab */
          <div className="space-y-6">
            {/* Pending Inbound Approvals Card */}
            <div className="bg-card border border-border/60 rounded-2xl p-5 shadow-xs space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
                    <span>Inbound Mirror Entries Approval Queue</span>
                    <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-amber-500/10 text-amber-500 border border-amber-500/20">
                      {inboxEntries.filter((e) => e.status === "PENDING").length} Pending
                    </span>
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    When a sister company creates a transfer or expense voucher, it appears here for 1-click counter-voucher generation.
                  </p>
                </div>
              </div>

              {inboxEntries.length === 0 ? (
                <div className="p-8 text-center text-xs text-muted-foreground bg-muted/20 rounded-xl border border-dashed border-border/60">
                  <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto mb-2 opacity-60" />
                  <p className="font-semibold text-foreground">All Caught Up!</p>
                  <p>No unconfirmed cross-company entries pending for {activeCompany?.name}.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {inboxEntries.map((item: any) => (
                    <div
                      key={item.id}
                      className="p-4 rounded-xl border border-border/60 bg-muted/30 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 text-[10px] font-bold uppercase font-mono">
                            {item.entry_type}
                          </span>
                          <span className="text-xs font-bold text-foreground">
                            From: {item.source_company_name} (#{item.source_voucher_number})
                          </span>
                          <span className="text-[11px] text-muted-foreground font-mono">
                            {item.entry_date}
                          </span>
                        </div>
                        <p className="text-xs text-muted-foreground">{item.narration}</p>
                        {item.suggested_debit && (
                          <div className="text-[11px] text-muted-foreground flex items-center gap-1 font-mono">
                            <span>Suggest: Dr {item.suggested_debit.name}</span>
                            <span>•</span>
                            <span>Cr {item.suggested_credit?.name || "Sister Co Current A/c"}</span>
                          </div>
                        )}
                      </div>

                      <div className="flex items-center gap-3 shrink-0">
                        <div className="text-base font-black font-mono tabular-nums text-foreground">
                          ₹{item.amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </div>
                        {item.status === "PENDING" ? (
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => handleAcceptMirror(item.id)}
                              disabled={actionLoadingId === item.id}
                              className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-foreground text-xs font-semibold flex items-center gap-1 cursor-pointer transition-all disabled:opacity-50"
                            >
                              <Check className="w-3.5 h-3.5" />
                              <span>{actionLoadingId === item.id ? "Posting..." : "Accept & Post"}</span>
                            </button>
                            <button
                              onClick={() => handleRejectMirror(item.id)}
                              disabled={actionLoadingId === item.id}
                              className="px-2.5 py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-xs font-semibold flex items-center gap-1 cursor-pointer transition-all"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ) : (
                          <span className="text-[11px] font-bold px-2.5 py-1 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                            {item.status} (#{item.target_voucher_number})
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Sister Company Selector & Matrix Reconciliation */}
            <div className="bg-card border border-border/60 rounded-2xl p-5 shadow-xs space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-bold text-foreground">
                    Sister Company Matrix Reconciler
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Side-by-side ledger comparison ensuring Entity A Debit = Entity B Credit to the paisa
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-xs text-muted-foreground font-semibold">Sister Entity:</label>
                  <select
                    value={selectedSisterId}
                    onChange={(e) => {
                      setSelectedSisterId(e.target.value);
                      fetchReconciliationMatrix(e.target.value);
                    }}
                    className="bg-muted border border-input rounded-xl px-3 py-1.5 text-xs text-foreground outline-none"
                  >
                    {entities
                      .filter((e: any) => e.company_id !== activeCompany?.id)
                      .map((e: any) => (
                        <option key={e.company_id} value={e.company_id}>
                          {e.company_name}
                        </option>
                      ))}
                  </select>
                </div>
              </div>

              {matrixData && (
                <div className="space-y-4 pt-2">
                  {/* Status Banner */}
                  <div
                    className={`p-4 rounded-xl border flex items-center justify-between gap-3 text-xs ${
                      matrixData.is_reconciled
                        ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                        : "bg-rose-500/10 border-rose-500/30 text-rose-400"
                    }`}
                  >
                    <div className="flex items-center gap-2.5">
                      {matrixData.is_reconciled ? (
                        <CheckCircle2 className="w-5 h-5 shrink-0" />
                      ) : (
                        <AlertCircle className="w-5 h-5 shrink-0" />
                      )}
                      <div>
                        <span className="font-bold text-sm block">{matrixData.status_headline}</span>
                        <span className="text-[11px] opacity-90">
                          {matrixData.is_reconciled
                            ? "All inter-company entries are symmetrically matched across both sets of statutory books."
                            : `Variance of ₹${matrixData.net_variance.toLocaleString("en-IN", { minimumFractionDigits: 2 })} found between entities.`}
                        </span>
                      </div>
                    </div>
                    <div className="text-right font-mono shrink-0">
                      <span className="text-[11px] block opacity-80">Net Variance</span>
                      <span className="text-lg font-black">
                        ₹{matrixData.net_variance.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </span>
                    </div>
                  </div>

                  {/* Side-by-Side Balance Cards */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Entity A */}
                    <div className="p-4 rounded-xl border border-border/50 bg-muted/20 space-y-2">
                      <div className="text-xs font-bold text-foreground flex items-center justify-between">
                        <span>{matrixData.company_a.name}</span>
                        <span className="font-mono text-[11px] text-muted-foreground">{matrixData.company_a.ledger_name}</span>
                      </div>
                      <div className="flex items-center justify-between pt-1">
                        <span className="text-xs text-muted-foreground">Book Balance:</span>
                        <span className="text-base font-black font-mono text-foreground">
                          ₹{Math.abs(matrixData.company_a.net_balance).toLocaleString("en-IN", { minimumFractionDigits: 2 })} {matrixData.company_a.balance_type}
                        </span>
                      </div>
                    </div>

                    {/* Entity B */}
                    <div className="p-4 rounded-xl border border-border/50 bg-muted/20 space-y-2">
                      <div className="text-xs font-bold text-foreground flex items-center justify-between">
                        <span>{matrixData.company_b.name}</span>
                        <span className="font-mono text-[11px] text-muted-foreground">{matrixData.company_b.ledger_name}</span>
                      </div>
                      <div className="flex items-center justify-between pt-1">
                        <span className="text-xs text-muted-foreground">Book Balance:</span>
                        <span className="text-base font-black font-mono text-foreground">
                          ₹{Math.abs(matrixData.company_b.net_balance).toLocaleString("en-IN", { minimumFractionDigits: 2 })} {matrixData.company_b.balance_type}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
