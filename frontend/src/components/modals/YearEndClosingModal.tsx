"use client";
import React, { useState, useEffect } from "react";
import axios from "axios";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken } from "@/utils/auth";
import { useFinancialYear } from "@/context/FinancialYearContext";
import {
  Calendar,
  AlertTriangle,
  CheckCircle2,
  Lock,
  ArrowRight,
  TrendingUp,
  TrendingDown,
  Layers,
  Sparkles,
  X,
} from "lucide-react";

export default function YearEndClosingModal() {
  const { activeFY, isClosingModalOpen, setIsClosingModalOpen, refreshFYs } = useFinancialYear();
  const [auditData, setAuditData] = useState<any>(null);
  const [loadingAudit, setLoadingAudit] = useState(false);
  const [closing, setClosing] = useState(false);
  const [closeResult, setCloseResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isClosingModalOpen && activeFY) {
      fetchAudit();
      setCloseResult(null);
      setError(null);
    }
  }, [isClosingModalOpen, activeFY]);

  const fetchAudit = async () => {
    if (!activeFY) return;
    setLoadingAudit(true);
    setError(null);
    try {
      const token = getAccessToken();
      const res = await axios.get(`${API_BASE_URL}/api/v1/financial-years/${activeFY.id}/audit/`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.data?.success) {
        setAuditData(res.data.data);
      }
    } catch (err: any) {
      setError(err.response?.data?.error || "Failed to load pre-closing audit.");
    } finally {
      setLoadingAudit(false);
    }
  };

  const handleConfirmClose = async () => {
    if (!activeFY) return;
    setClosing(true);
    setError(null);
    try {
      const token = getAccessToken();
      const res = await axios.post(
        `${API_BASE_URL}/api/v1/financial-years/${activeFY.id}/close/`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.data?.success) {
        setCloseResult(res.data);
        await refreshFYs();
      }
    } catch (err: any) {
      setError(err.response?.data?.error || "Failed to close financial year.");
    } finally {
      setClosing(false);
    }
  };

  if (!isClosingModalOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl max-w-xl w-full p-6 shadow-2xl relative animate-in fade-in zoom-in-95">
        
        {/* Close Button */}
        <button
          onClick={() => setIsClosingModalOpen(false)}
          className="absolute top-4 right-4 text-zinc-400 hover:text-white p-1 rounded-lg hover:bg-zinc-800 transition-colors"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Modal Header */}
        <div className="flex items-center gap-3 mb-5">
          <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center justify-center">
            <Lock className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              Financial Year-End Close & Roll-Forward
            </h2>
            <p className="text-xs text-zinc-400">
              Period Closing for <span className="font-semibold text-white">{activeFY?.name}</span> ({activeFY?.start_date} to {activeFY?.end_date})
            </p>
          </div>
        </div>

        {/* Result Screen after closing */}
        {closeResult ? (
          <div className="space-y-4">
            <div className="p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-emerald-400 text-sm flex items-start gap-3">
              <CheckCircle2 className="w-5 h-5 shrink-0 mt-0.5" />
              <div>
                <div className="font-bold">{closeResult.message}</div>
                <div className="text-xs text-emerald-500/80 mt-1">
                  Closed Period: {closeResult.closed_financial_year} · Active Target: {closeResult.next_financial_year}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 bg-zinc-950 rounded-xl border border-zinc-800">
                <div className="text-xs text-zinc-400">Real & Personal Accounts Carried</div>
                <div className="text-xl font-mono font-bold text-white mt-1">
                  {closeResult.carried_accounts_count} Accounts
                </div>
              </div>
              <div className="p-3 bg-zinc-950 rounded-xl border border-zinc-800">
                <div className="text-xs text-zinc-400">
                  {closeResult.profit_loss_type === "PROFIT" ? "Net Profit Credited to Equity" : "Net Loss Debited to Equity"}
                </div>
                <div className={`text-xl font-mono font-bold mt-1 flex items-center gap-1 ${
                  closeResult.profit_loss_type === "PROFIT" ? "text-emerald-400" : "text-rose-400"
                }`}>
                  {closeResult.profit_loss_type === "PROFIT" ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                  ₹{Number(closeResult.net_profit_loss).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
              </div>
            </div>

            <button
              onClick={() => setIsClosingModalOpen(false)}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-bold text-sm transition-colors cursor-pointer"
            >
              Done
            </button>
          </div>
        ) : (
          /* Pre-Closing Audit & Confirmation */
          <div className="space-y-4">
            {error && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-400 text-xs flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {loadingAudit ? (
              <div className="py-8 text-center text-zinc-400 text-sm">
                <div className="w-6 h-6 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
                Running pre-closing audit verification...
              </div>
            ) : auditData ? (
              <>
                {/* Audit Checklist Cards */}
                <div className="space-y-2.5">
                  {/* Item 1: Unposted Vouchers */}
                  <div className={`p-3 rounded-xl border flex items-center justify-between text-xs ${
                    auditData.unposted_vouchers_count === 0
                      ? "bg-emerald-500/5 border-emerald-500/20 text-emerald-300"
                      : "bg-rose-500/10 border-rose-500/30 text-rose-300"
                  }`}>
                    <div className="flex items-center gap-2.5">
                      {auditData.unposted_vouchers_count === 0 ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                      ) : (
                        <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                      )}
                      <div>
                        <div className="font-bold">Draft / Unposted Vouchers Check</div>
                        <div className="text-[11px] text-zinc-400">
                          {auditData.unposted_vouchers_count === 0
                            ? "All vouchers are posted. Zero pending drafts."
                            : `${auditData.unposted_vouchers_count} unposted vouchers found. Must post or delete before closing.`}
                        </div>
                      </div>
                    </div>
                    <span className="font-mono font-bold text-sm">
                      {auditData.unposted_vouchers_count}
                    </span>
                  </div>

                  {/* Item 2: Trial Balance Equilibrium */}
                  <div className={`p-3 rounded-xl border flex items-center justify-between text-xs ${
                    auditData.is_trial_balance_balanced
                      ? "bg-emerald-500/5 border-emerald-500/20 text-emerald-300"
                      : "bg-rose-500/10 border-rose-500/30 text-rose-300"
                  }`}>
                    <div className="flex items-center gap-2.5">
                      {auditData.is_trial_balance_balanced ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                      ) : (
                        <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                      )}
                      <div>
                        <div className="font-bold">Trial Balance Equilibrium Check</div>
                        <div className="text-[11px] text-zinc-400">
                          Total Dr: ₹{Number(auditData.total_debits).toLocaleString("en-IN", { minimumFractionDigits: 2 })} · Total Cr: ₹{Number(auditData.total_credits).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </div>
                      </div>
                    </div>
                    <span className="font-mono font-bold text-xs">
                      {auditData.is_trial_balance_balanced ? "Equilibrium OK" : `Diff: ₹${auditData.trial_balance_difference}`}
                    </span>
                  </div>

                  {/* Item 3: Roll-Forward Target Preview */}
                  <div className="p-3 bg-zinc-950 rounded-xl border border-zinc-800 flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2.5">
                      <Sparkles className="w-4 h-4 text-blue-400 shrink-0" />
                      <div>
                        <div className="font-bold text-white">Target New Financial Year</div>
                        <div className="text-[11px] text-zinc-400">
                          Asset, Liability & Party closing balances will become new opening balances
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 font-mono text-blue-400 font-bold bg-blue-500/10 px-2.5 py-1 rounded-lg border border-blue-500/20">
                      <span>{activeFY?.code}</span>
                      <ArrowRight className="w-3 h-3" />
                      <span>Next FY</span>
                    </div>
                  </div>
                </div>

                {/* Information Callout */}
                <div className="p-3 bg-zinc-950/80 rounded-xl border border-zinc-800/80 text-[11px] text-zinc-400 space-y-1">
                  <div className="font-semibold text-zinc-300">Accounting Rules Applied:</div>
                  <ul className="list-disc pl-4 space-y-0.5">
                    <li>Balance sheet accounts (Cash, Bank, Debtors, Creditors) roll forward intact.</li>
                    <li>Nominal P&L accounts (Sales, Purchases, Expenses) reset to ₹0.00.</li>
                    <li>Net Profit / Loss transfers directly to Retained Earnings (Capital).</li>
                    <li>Financial Year {activeFY?.name} will be marked as read-only.</li>
                  </ul>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setIsClosingModalOpen(false)}
                    className="flex-1 py-2.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-xl font-bold text-xs transition-colors cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleConfirmClose}
                    disabled={!auditData.can_close || closing}
                    className={`flex-1 py-2.5 rounded-xl font-bold text-xs transition-all flex items-center justify-center gap-2 cursor-pointer ${
                      auditData.can_close && !closing
                        ? "bg-amber-600 hover:bg-amber-500 text-white shadow-lg shadow-amber-600/20"
                        : "bg-zinc-800 text-zinc-500 cursor-not-allowed opacity-60"
                    }`}
                  >
                    {closing ? (
                      <>
                        <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                        <span>Closing Period...</span>
                      </>
                    ) : (
                      <>
                        <Lock className="w-3.5 h-3.5" />
                        <span>Confirm Year-End Closing & Carry Balances</span>
                      </>
                    )}
                  </button>
                </div>
              </>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
