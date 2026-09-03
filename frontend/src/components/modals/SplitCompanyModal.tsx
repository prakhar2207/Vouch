"use client";
import React, { useState, useEffect } from "react";
import axios from "axios";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken } from "@/utils/auth";
import { useAccountingPeriod } from "@/context/PeriodContext";
import {
  Scissors,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  TrendingUp,
  TrendingDown,
  Building2,
  Sparkles,
  X,
} from "lucide-react";

export default function SplitCompanyModal() {
  const { isSplitModalOpen, setIsSplitModalOpen } = useAccountingPeriod();
  
  // Default to upcoming April 1st
  const today = new Date();
  const defaultSplitYear = today.getMonth() >= 3 ? today.getFullYear() + 1 : today.getFullYear();
  const defaultSplitDate = `${defaultSplitYear}-04-01`;

  const [splitDate, setSplitDate] = useState(defaultSplitDate);
  const [customName, setCustomName] = useState("");
  const [auditData, setAuditData] = useState<any>(null);
  const [loadingAudit, setLoadingAudit] = useState(false);
  const [splitting, setSplitting] = useState(false);
  const [splitResult, setSplitResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isSplitModalOpen) {
      fetchAudit();
      setSplitResult(null);
      setError(null);
    }
  }, [isSplitModalOpen, splitDate]);

  const fetchAudit = async () => {
    setLoadingAudit(true);
    setError(null);
    try {
      const token = getAccessToken();
      const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/split-company/audit/?split_date=${splitDate}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.data?.success) {
        setAuditData(res.data.data);
        if (!customName) {
          setCustomName(res.data.data.suggested_company_name);
        }
      }
    } catch (err: any) {
      setError(err.response?.data?.error || "Failed to load pre-split audit.");
    } finally {
      setLoadingAudit(false);
    }
  };

  const handleExecuteSplit = async () => {
    setSplitting(true);
    setError(null);
    try {
      const token = getAccessToken();
      const res = await axios.post(
        `${API_BASE_URL}/api/v1/accounting/split-company/`,
        {
          split_date: splitDate,
          new_company_name: customName || undefined
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.data?.success) {
        setSplitResult(res.data);
      }
    } catch (err: any) {
      setError(err.response?.data?.error || "Failed to execute company split.");
    } finally {
      setSplitting(false);
    }
  };

  if (!isSplitModalOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl max-w-xl w-full p-6 shadow-2xl relative animate-in fade-in zoom-in-95">
        
        {/* Close Button */}
        <button
          onClick={() => setIsSplitModalOpen(false)}
          className="absolute top-4 right-4 text-zinc-400 hover:text-white p-1 rounded-lg hover:bg-zinc-800 transition-colors"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Modal Header */}
        <div className="flex items-center gap-3 mb-5">
          <div className="w-10 h-10 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400 flex items-center justify-center shadow-sm">
            <Scissors className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-white">Split Company Data</h2>
              <span className="text-[10px] font-mono px-2 py-0.5 bg-purple-500/15 text-purple-400 border border-purple-500/30 rounded font-bold">
                Tally Paradigm
              </span>
            </div>
            <p className="text-xs text-zinc-400">
              Spawns a new standalone entity starting at Split Date and archives historical periods
            </p>
          </div>
        </div>

        {/* Post-Split Success Screen */}
        {splitResult ? (
          <div className="space-y-4">
            <div className="p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-emerald-400 text-sm flex items-start gap-3">
              <CheckCircle2 className="w-5 h-5 shrink-0 mt-0.5" />
              <div>
                <div className="font-bold">{splitResult.message}</div>
                <div className="text-xs text-emerald-500/80 mt-1">
                  New Entity ID: <span className="font-mono">{splitResult.new_company_id}</span>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 bg-zinc-950 rounded-xl border border-zinc-800">
                <div className="text-xs text-zinc-400">Real & Personal Accounts Initialized</div>
                <div className="text-xl font-mono font-bold text-white mt-1">
                  {splitResult.carried_accounts_count} Ledgers
                </div>
              </div>
              <div className="p-3 bg-zinc-950 rounded-xl border border-zinc-800">
                <div className="text-xs text-zinc-400">Prior Net P&L Settled in Capital</div>
                <div className="text-xl font-mono font-bold text-emerald-400 mt-1">
                  ₹{Number(splitResult.net_profit_loss).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
              </div>
            </div>

            <button
              onClick={() => {
                setIsSplitModalOpen(false);
                window.location.reload();
              }}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-bold text-sm transition-colors cursor-pointer"
            >
              Done & Reload Companies
            </button>
          </div>
        ) : (
          /* Pre-Split Configuration & Audit */
          <div className="space-y-4">
            {error && (
              <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-400 text-xs flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {/* Split Date & Target Name Inputs */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 bg-zinc-950 p-3.5 rounded-xl border border-zinc-800">
              <div>
                <label className="block text-[10px] font-bold text-zinc-400 uppercase tracking-wider mb-1">
                  Split Date (Commencement)
                </label>
                <input
                  type="date"
                  value={splitDate}
                  onChange={(e) => setSplitDate(e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-700 text-white px-2.5 py-1.5 rounded-lg text-xs font-mono outline-none focus:ring-1 focus:ring-purple-500"
                  required
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-zinc-400 uppercase tracking-wider mb-1">
                  New Company Name
                </label>
                <input
                  type="text"
                  value={customName}
                  onChange={(e) => setCustomName(e.target.value)}
                  placeholder="Target company name..."
                  className="w-full bg-zinc-900 border border-zinc-700 text-white px-2.5 py-1.5 rounded-lg text-xs outline-none focus:ring-1 focus:ring-purple-500 font-semibold"
                />
              </div>
            </div>

            {loadingAudit ? (
              <div className="py-8 text-center text-zinc-400 text-sm">
                <div className="w-6 h-6 border-2 border-purple-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
                Verifying trial balance and transaction records...
              </div>
            ) : auditData ? (
              <>
                {/* Audit Checklist */}
                <div className="space-y-2.5">
                  <div className={`p-3 rounded-xl border flex items-center justify-between text-xs ${
                    auditData.unposted_vouchers_count === 0
                      ? "bg-emerald-500/5 border-emerald-500/20 text-emerald-300"
                      : "bg-rose-500/10 border-rose-500/30 text-rose-300"
                  }`}>
                    <div className="flex items-center gap-2">
                      {auditData.unposted_vouchers_count === 0 ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                      ) : (
                        <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                      )}
                      <div>
                        <div className="font-bold">Unposted Vouchers Before Split Date</div>
                        <div className="text-[11px] text-zinc-400">
                          {auditData.unposted_vouchers_count === 0
                            ? "All prior transactions are posted cleanly."
                            : `${auditData.unposted_vouchers_count} draft vouchers found before ${splitDate}. Must post or cancel.`}
                        </div>
                      </div>
                    </div>
                    <span className="font-mono font-bold text-sm">
                      {auditData.unposted_vouchers_count}
                    </span>
                  </div>

                  <div className={`p-3 rounded-xl border flex items-center justify-between text-xs ${
                    auditData.is_trial_balance_balanced
                      ? "bg-emerald-500/5 border-emerald-500/20 text-emerald-300"
                      : "bg-rose-500/10 border-rose-500/30 text-rose-300"
                  }`}>
                    <div className="flex items-center gap-2">
                      {auditData.is_trial_balance_balanced ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                      ) : (
                        <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                      )}
                      <div>
                        <div className="font-bold">Prior Trial Balance Equilibrium</div>
                        <div className="text-[11px] text-zinc-400">
                          Net Debits equal Credits as of {auditData.closing_date}
                        </div>
                      </div>
                    </div>
                    <span className="font-mono font-bold text-xs">
                      {auditData.is_trial_balance_balanced ? "Equilibrium OK" : `Diff: ₹${auditData.trial_balance_difference}`}
                    </span>
                  </div>

                  {/* Net Profit Transfer Preview */}
                  <div className="p-3 bg-zinc-950 rounded-xl border border-zinc-800 flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-purple-400 shrink-0" />
                      <div>
                        <div className="font-bold text-white">Prior Period Net Profit to Retained Earnings</div>
                        <div className="text-[11px] text-zinc-400">
                          Income ₹{Number(auditData.total_income).toLocaleString("en-IN")} − Expense ₹{Number(auditData.total_expense).toLocaleString("en-IN")}
                        </div>
                      </div>
                    </div>
                    <span className="font-mono font-bold text-emerald-400">
                      ₹{Number(auditData.net_profit_loss).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                </div>

                {/* Information Callout */}
                <div className="p-3 bg-zinc-950/80 rounded-xl border border-zinc-800/80 text-[11px] text-zinc-400 space-y-1">
                  <div className="font-semibold text-zinc-300">Tally Split Behavior:</div>
                  <ul className="list-disc pl-4 space-y-0.5">
                    <li>The source company remains unchanged and its historical periods are archived.</li>
                    <li>A new standalone company is created with books commencing on {splitDate}.</li>
                    <li>Real & Personal account closing balances become new opening balances.</li>
                    <li>Nominal P&L accounts start fresh with ₹0.00.</li>
                  </ul>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setIsSplitModalOpen(false)}
                    className="flex-1 py-2.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-xl font-bold text-xs transition-colors cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleExecuteSplit}
                    disabled={!auditData.can_split || splitting}
                    className={`flex-1 py-2.5 rounded-xl font-bold text-xs transition-all flex items-center justify-center gap-2 cursor-pointer ${
                      auditData.can_split && !splitting
                        ? "bg-purple-600 hover:bg-purple-500 text-white shadow-lg shadow-purple-600/20"
                        : "bg-zinc-800 text-zinc-500 cursor-not-allowed opacity-60"
                    }`}
                  >
                    {splitting ? (
                      <>
                        <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                        <span>Splitting Company...</span>
                      </>
                    ) : (
                      <>
                        <Scissors className="w-3.5 h-3.5" />
                        <span>Confirm & Execute Split</span>
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
