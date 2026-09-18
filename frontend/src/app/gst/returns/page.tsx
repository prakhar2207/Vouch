"use client";
import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { useRouter } from "next/navigation";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import { API_BASE_URL } from "@/utils/api";
import { useCompany } from "@/context/CompanyContext";
import DashboardLayout from "@/components/DashboardLayout";
import { 
  FileCheck, 
  AlertTriangle, 
  Download, 
  CheckCircle2, 
  Calendar, 
  HelpCircle, 
  ArrowRight,
  TrendingUp,
  ShieldCheck,
  RefreshCw,
  Edit3,
  Globe,
  UploadCloud,
  Send,
  Lock,
  Key,
  Sparkles,
  ExternalLink,
  ShieldAlert
} from "lucide-react";

export default function GSTReturnCenterPage() {
  const router = useRouter();
  const { activeCompany, companyId: activeCompanyId } = useCompany();
  const [activeTab, setActiveTab] = useState<"monthly" | "quarterly" | "annual">("monthly");
  
  const companyId = activeCompanyId || (typeof window !== "undefined" ? localStorage.getItem("vouch_active_company_id") || "" : "");
  const companyName = activeCompany?.name || "Your Company";
  
  // Date states
  const [selectedMonth, setSelectedMonth] = useState<string>(new Date().toISOString().slice(0, 7)); // YYYY-MM
  const [selectedQuarter, setSelectedQuarter] = useState<string>("Q2");
  const [selectedYear, setSelectedYear] = useState<string>("2025-2026");

  // Loading & Data states
  const [loading, setLoading] = useState(false);
  const [exceptionsData, setExceptionsData] = useState<any>(null);
  const [gstr3bData, setGstr3bData] = useState<any>(null);
  const [gstr9Data, setGstr9Data] = useState<any>(null);
  const [filingStatus, setFilingStatus] = useState<string | null>(null);

  // Quick Edit Modal state
  const [editingVoucher, setEditingVoucher] = useState<any | null>(null);
  const [editGstin, setEditGstin] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);

  // Direct GST Portal Upload states
  const [showPortalModal, setShowPortalModal] = useState(false);
  const [portalStep, setPortalStep] = useState<"auth" | "otp" | "confirm" | "success">("auth");
  const [taxpayerUsername, setTaxpayerUsername] = useState("vouch_taxpayer");
  const [portalGstin, setPortalGstin] = useState(activeCompany?.gstin || "09CIFPS1329P2ZL");
  const [portalOtp, setPortalOtp] = useState("575757");
  const [maskedMobile, setMaskedMobile] = useState("******9821");
  const [portalTxnId, setPortalTxnId] = useState("");
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);
  const [portalError, setPortalError] = useState<string | null>(null);
  const [uploadAck, setUploadAck] = useState<any>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
    }
  }, [router]);

  useEffect(() => {
    if (activeCompany?.gstin) {
      setPortalGstin(activeCompany.gstin);
    }
  }, [activeCompany?.gstin]);

  const getStartAndEndDate = () => {
    if (activeTab === "monthly") {
      const [year, month] = selectedMonth.split("-");
      const lastDay = new Date(parseInt(year), parseInt(month), 0).getDate();
      return {
        startDate: `${selectedMonth}-01`,
        endDate: `${selectedMonth}-${String(lastDay).padStart(2, "0")}`,
        periodLabel: selectedMonth,
      };
    } else {
      const year = selectedYear.split("-")[0];
      const nextYear = selectedYear.split("-")[1];
      if (selectedQuarter === "Q1") return { startDate: `${year}-04-01`, endDate: `${year}-06-30`, periodLabel: `${selectedYear} Q1` };
      if (selectedQuarter === "Q2") return { startDate: `${year}-07-01`, endDate: `${year}-09-30`, periodLabel: `${selectedYear} Q2` };
      if (selectedQuarter === "Q3") return { startDate: `${year}-10-01`, endDate: `${year}-12-31`, periodLabel: `${selectedYear} Q3` };
      return { startDate: `${nextYear}-01-01`, endDate: `${nextYear}-03-31`, periodLabel: `${selectedYear} Q4` };
    }
  };

  const loadGSTData = useCallback(async () => {
    if (!companyId) return;
    setLoading(true);
    const { startDate, endDate } = getStartAndEndDate();

    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      if (activeTab === "annual") {
        const res = await axios.get(`${API_BASE_URL}/api/v1/gst/reports/gstr9/${companyId}/?year_code=${selectedYear}`, { headers });
        setGstr9Data(res.data.data);
      } else {
        const [excRes, g3bRes] = await Promise.all([
          axios.get(`${API_BASE_URL}/api/v1/gst/returns/exceptions/${companyId}/?start_date=${startDate}&end_date=${endDate}`, { headers }),
          axios.get(`${API_BASE_URL}/api/v1/gst/reports/gstr3b/${companyId}/?start_date=${startDate}&end_date=${endDate}`, { headers }),
        ]);
        setExceptionsData(excRes.data.data);
        setGstr3bData(g3bRes.data.data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [companyId, activeTab, selectedMonth, selectedQuarter, selectedYear]);

  useEffect(() => {
    if (companyId) {
      loadGSTData();
    }
  }, [companyId, activeTab, selectedMonth, selectedQuarter, selectedYear, loadGSTData]);

  const handleDownloadGSTR1 = () => {
    const { startDate, endDate } = getStartAndEndDate();
    window.open(`${API_BASE_URL}/api/v1/gst/reports/gstr1/${companyId}/?start_date=${startDate}&end_date=${endDate}&download=1`, "_blank");
  };

  const handleMarkAsFiled = async () => {
    const { periodLabel } = getStartAndEndDate();
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      await axios.post(`${API_BASE_URL}/api/v1/gst/returns/mark-filed/${companyId}/`, { period: periodLabel }, { headers });
      setFilingStatus(`✓ Return for ${periodLabel} recorded as filed.`);
    } catch (e) {
      console.error(e);
    }
  };

  const handleOpenPortalModal = () => {
    setPortalError(null);
    setPortalGstin(activeCompany?.gstin || "09CIFPS1329P2ZL");
    setTaxpayerUsername("vouch_taxpayer");
    if (authToken) {
      setPortalStep("confirm");
    } else {
      setPortalStep("auth");
    }
    setShowPortalModal(true);
  };

  const handleRequestOTP = async () => {
    setPortalLoading(true);
    setPortalError(null);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.post(
        `${API_BASE_URL}/api/v1/gst/portal/request-otp/`,
        {
          company_id: companyId,
          gstin: portalGstin,
          username: taxpayerUsername,
        },
        { headers }
      );
      if (res.data.success) {
        setMaskedMobile(res.data.masked_mobile || "******9821");
        setPortalTxnId(res.data.txn_id || "");
        setPortalStep("otp");
      } else {
        setPortalError(res.data.error || "Failed to request OTP from GST Portal.");
      }
    } catch (err: any) {
      setPortalError(err.response?.data?.error || "Error connecting to GST Portal.");
    } finally {
      setPortalLoading(false);
    }
  };

  const handleVerifyOTP = async () => {
    setPortalLoading(true);
    setPortalError(null);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.post(
        `${API_BASE_URL}/api/v1/gst/portal/verify-otp/`,
        {
          company_id: companyId,
          otp: portalOtp,
          txn_id: portalTxnId,
          gstin: portalGstin,
          username: taxpayerUsername,
        },
        { headers }
      );
      if (res.data.success) {
        setAuthToken(res.data.auth_token);
        setPortalStep("confirm");
      } else {
        setPortalError(res.data.error || "Invalid OTP entered.");
      }
    } catch (err: any) {
      setPortalError(err.response?.data?.error || "Failed to verify OTP with GST Portal.");
    } finally {
      setPortalLoading(false);
    }
  };

  const handleDirectUploadGSTR1 = async () => {
    setPortalLoading(true);
    setPortalError(null);
    const { startDate, endDate, periodLabel } = getStartAndEndDate();
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.post(
        `${API_BASE_URL}/api/v1/gst/portal/upload-gstr1/`,
        {
          company_id: companyId,
          start_date: startDate,
          end_date: endDate,
          auth_token: authToken,
        },
        { headers }
      );
      if (res.data.success) {
        setUploadAck(res.data);
        setPortalStep("success");
        setFilingStatus(`✓ GSTR-1 for ${periodLabel} successfully transmitted to GST Portal API. Reference ID: ${res.data.reference_id}`);
      } else {
        setPortalError(res.data.error || "GST Portal rejected the return batch.");
      }
    } catch (err: any) {
      setPortalError(err.response?.data?.error || "Network error uploading to GST Portal.");
    } finally {
      setPortalLoading(false);
    }
  };

  const totalVouchers = (exceptionsData?.clean_count ?? 0) + (exceptionsData?.exception_count ?? 0);
  const readinessPct = totalVouchers > 0 ? Math.round(((exceptionsData?.clean_count ?? 0) / totalVouchers) * 100) : 100;
  const isFullyClean = (exceptionsData?.exception_count ?? 0) === 0;

  return (
    <DashboardLayout>
      <div className="space-y-6 max-w-7xl mx-auto pb-12">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-4">
          <div>
            <div className="flex items-center gap-3">
              <span className="p-2.5 rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400 font-bold border border-blue-500/20">
                <FileCheck className="w-6 h-6" />
              </span>
              <div>
                <div className="flex items-center gap-3">
                  <h1 className="text-2xl font-bold tracking-tight">GST Return & Compliance Center</h1>
                  {exceptionsData && (
                    isFullyClean ? (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                        Grade A • 100% Audit Ready
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800">
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                        Grade B • {readinessPct}% Ready ({exceptionsData.exception_count} action {exceptionsData.exception_count === 1 ? "item" : "items"})
                      </span>
                    )
                  )}
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Prepare, audit, and export official GSTR-1, GSTR-3B & GSTR-9 returns with zero clerical errors.
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={loadGSTData}
              className="px-3.5 py-2 bg-secondary hover:bg-secondary/80 text-secondary-foreground rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer border border-border"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              <span>Refresh Check</span>
            </button>

            {activeTab !== "annual" && (
              <div className="flex items-center gap-2">
                <button
                  onClick={handleOpenPortalModal}
                  className="px-4 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white rounded-lg text-xs font-bold shadow-md flex items-center gap-2 transition-all cursor-pointer"
                >
                  <Globe className="w-4 h-4" />
                  <span>Direct GST Portal Upload</span>
                </button>

                <button
                  onClick={handleDownloadGSTR1}
                  className="px-3.5 py-2 bg-secondary hover:bg-secondary/80 text-secondary-foreground rounded-lg text-xs font-semibold border border-border flex items-center gap-1.5 transition-all cursor-pointer"
                  title="Download offline JSON file for manual portal upload"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Export JSON</span>
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Filing Cycle Tabs */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-card p-3 rounded-2xl border border-border shadow-xs">
          <div className="flex items-center gap-1 p-1 bg-muted rounded-xl">
            <button
              onClick={() => setActiveTab("monthly")}
              className={`px-4 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                activeTab === "monthly" ? "bg-background text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Monthly Return
            </button>
            <button
              onClick={() => setActiveTab("quarterly")}
              className={`px-4 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                activeTab === "quarterly" ? "bg-background text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Quarterly / Tri-Monthly (QRMP)
            </button>
            <button
              onClick={() => setActiveTab("annual")}
              className={`px-4 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                activeTab === "annual" ? "bg-background text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Annual Return (GSTR-9)
            </button>
          </div>

          {/* Period Selector Controls */}
          <div className="flex items-center gap-3 text-xs">
            {activeTab === "monthly" && (
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground font-medium">Select Month:</span>
                <input
                  type="month"
                  value={selectedMonth}
                  onChange={(e) => setSelectedMonth(e.target.value)}
                  className="px-3 py-1.5 bg-background border border-border rounded-lg text-xs font-mono font-semibold text-foreground outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
            )}

            {activeTab === "quarterly" && (
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground font-medium">Financial Year:</span>
                <select
                  value={selectedYear}
                  onChange={(e) => setSelectedYear(e.target.value)}
                  className="px-2.5 py-1.5 bg-background border border-border rounded-lg text-xs font-semibold"
                >
                  <option value="2025-2026">FY 2025-26</option>
                  <option value="2026-2027">FY 2026-27</option>
                </select>

                <span className="text-muted-foreground font-medium ml-2">Quarter:</span>
                <select
                  value={selectedQuarter}
                  onChange={(e) => setSelectedQuarter(e.target.value)}
                  className="px-2.5 py-1.5 bg-background border border-border rounded-lg text-xs font-semibold"
                >
                  <option value="Q1">Q1 (Apr - Jun)</option>
                  <option value="Q2">Q2 (Jul - Sep)</option>
                  <option value="Q3">Q3 (Oct - Dec)</option>
                  <option value="Q4">Q4 (Jan - Mar)</option>
                </select>
              </div>
            )}

            {activeTab === "annual" && (
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground font-medium">Financial Year:</span>
                <select
                  value={selectedYear}
                  onChange={(e) => setSelectedYear(e.target.value)}
                  className="px-3 py-1.5 bg-background border border-border rounded-lg text-xs font-semibold"
                >
                  <option value="2025-2026">FY 2025-26</option>
                  <option value="2026-2027">FY 2026-27</option>
                </select>
              </div>
            )}
          </div>
        </div>

        {filingStatus && (
          <div className="p-4 bg-emerald-500/10 border border-emerald-500/30 text-emerald-800 dark:text-emerald-300 rounded-xl text-xs flex items-center justify-between">
            <span className="font-semibold">{filingStatus}</span>
            <button onClick={() => setFilingStatus(null)} className="font-bold ml-4 hover:opacity-70">✕</button>
          </div>
        )}

        {/* Content for Monthly & Quarterly Returns */}
        {activeTab !== "annual" && (
          <div className="space-y-6">
            {/* 3 Metric Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Card 1: Clean Vouchers */}
              <div className="p-5 bg-card rounded-2xl border border-emerald-500/30 bg-gradient-to-br from-card via-card to-emerald-500/5 shadow-xs space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Clean Vouchers (Ready)</span>
                  <span className="p-2 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded-xl border border-emerald-500/20">
                    <CheckCircle2 className="w-4 h-4" />
                  </span>
                </div>
                <div>
                  <div className="text-3xl font-black text-foreground font-mono">
                    {exceptionsData?.clean_count ?? 0}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    Value: <span className="font-semibold text-foreground font-mono">₹{(exceptionsData?.clean_total_amount ?? 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
                  </div>
                </div>
                <div className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-700 dark:text-emerald-300 bg-emerald-500/10 px-2 py-0.5 rounded-md">
                  ✓ Passed GSTIN, HSN & Tax slab checks
                </div>
              </div>

              {/* Card 2: Exceptions Needing Correction */}
              <div className={`p-5 bg-card rounded-2xl space-y-3 shadow-xs ${
                (exceptionsData?.exception_count ?? 0) > 0
                  ? "border-2 border-amber-500/40 bg-gradient-to-br from-card via-card to-amber-500/10 ring-1 ring-amber-500/20"
                  : "border border-border"
              }`}>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Clerical Exceptions</span>
                  <span className="p-2 bg-amber-500/10 text-amber-600 dark:text-amber-400 rounded-xl border border-amber-500/20">
                    <AlertTriangle className="w-4 h-4" />
                  </span>
                </div>
                <div>
                  <div className="text-3xl font-black text-amber-600 dark:text-amber-400 font-mono">
                    {exceptionsData?.exception_count ?? 0}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    Needs Attention: <span className="font-semibold text-foreground font-mono">₹{(exceptionsData?.exception_total_amount ?? 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
                  </div>
                </div>
                <div className="inline-flex items-center gap-1 text-[11px] font-medium text-amber-800 dark:text-amber-300 bg-amber-500/10 px-2 py-0.5 rounded-md">
                  Fix typos below prior to GST portal upload
                </div>
              </div>

              {/* Card 3: GSTR-3B Net Tax Liability */}
              <div className="p-5 bg-card rounded-2xl border border-blue-500/30 bg-gradient-to-br from-card via-card to-blue-500/5 shadow-xs space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Net Tax Payable (GSTR-3B)</span>
                  <span className="p-2 bg-blue-500/10 text-blue-600 dark:text-blue-400 rounded-xl border border-blue-500/20">
                    <TrendingUp className="w-4 h-4" />
                  </span>
                </div>
                <div>
                  <div className="text-3xl font-black text-blue-600 dark:text-blue-400 font-mono">
                    ₹{(gstr3bData?.net_tax_payable?.total ?? 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    Outward: <span className="font-semibold text-foreground font-mono">₹{(gstr3bData?.table_3_1_outward_supplies?.taxable_value ?? 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
                  </div>
                </div>
                <div className="text-[11px] text-muted-foreground flex justify-between items-center bg-blue-500/10 px-2.5 py-1 rounded-md">
                  <span>ITC Available:</span>
                  <span className="font-mono font-bold text-foreground">
                    ₹{((gstr3bData?.table_4_eligible_itc?.igst ?? 0) + (gstr3bData?.table_4_eligible_itc?.cgst ?? 0) + (gstr3bData?.table_4_eligible_itc?.sgst ?? 0)).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </span>
                </div>
              </div>
            </div>

            {/* Exceptions Table ("Triangulation" in-place review) */}
            {(exceptionsData?.exception_count ?? 0) > 0 ? (
              <div className="bg-card border border-border rounded-2xl p-5 shadow-xs space-y-4">
                <div className="flex items-center justify-between border-b border-border pb-3">
                  <div>
                    <h3 className="text-base font-bold text-foreground flex items-center gap-2">
                      <span className="p-1.5 rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                        <AlertTriangle className="w-4 h-4" />
                      </span>
                      <span>Transactions Requiring Resolution ({exceptionsData?.exception_count})</span>
                    </h3>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Fix these clerical issues directly here without leaving the page. They will move to "Clean" automatically.
                    </p>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-border text-muted-foreground uppercase font-semibold text-[11px] tracking-wider">
                        <th className="pb-3">Invoice No</th>
                        <th className="pb-3">Date</th>
                        <th className="pb-3">Customer / Party</th>
                        <th className="pb-3">GSTIN</th>
                        <th className="pb-3">Total (₹)</th>
                        <th className="pb-3">Detected Issue</th>
                        <th className="pb-3 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/60">
                      {exceptionsData?.exceptions?.map((exc: any) => (
                        <tr key={exc.id} className="hover:bg-muted/40 transition-colors">
                          <td className="py-3 font-mono font-bold text-foreground">{exc.voucher_number}</td>
                          <td className="py-3 text-muted-foreground font-mono">{exc.date}</td>
                          <td className="py-3 font-medium text-foreground">{exc.party_name}</td>
                          <td className="py-3 font-mono text-muted-foreground bg-muted/60 px-1.5 py-0.5 rounded text-[11px]">{exc.party_gstin || "N/A"}</td>
                          <td className="py-3 font-bold font-mono text-foreground">₹{exc.total_amount.toFixed(2)}</td>
                          <td className="py-3">
                            <div className="flex flex-wrap gap-1.5">
                              {exc.issues.map((iss: string, idx: number) => (
                                <span
                                  key={idx}
                                  className="inline-flex items-center gap-1 px-2.5 py-1 bg-amber-500/10 text-amber-800 dark:text-amber-300 border border-amber-500/30 rounded-md text-[11px] font-medium"
                                >
                                  <AlertTriangle className="w-3 h-3 text-amber-600 dark:text-amber-400 shrink-0" />
                                  {iss}
                                </span>
                              ))}
                            </div>
                          </td>
                          <td className="py-3 text-right">
                            <button
                              onClick={() => {
                                setEditingVoucher(exc);
                                setEditGstin(exc.party_gstin || "");
                              }}
                              className="px-3.5 py-1.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg text-xs font-semibold shadow-xs transition-colors cursor-pointer inline-flex items-center gap-1.5"
                            >
                              <Edit3 className="w-3.5 h-3.5" />
                              <span>Fix in 1-Click</span>
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="bg-card border border-border rounded-2xl p-8 text-center space-y-3 shadow-xs">
                <div className="w-14 h-14 rounded-2xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center mx-auto text-2xl font-bold border border-emerald-500/20 shadow-xs">
                  <CheckCircle2 className="w-7 h-7" />
                </div>
                <h3 className="text-base font-bold text-foreground">Zero Exceptions Found!</h3>
                <p className="text-xs text-muted-foreground max-w-md mx-auto">
                  All transactions in this period are clean, balanced, and pass statutory GSTIN, HSN, and state code checks. You are ready to export your GSTR-1 JSON.
                </p>
                <div className="pt-2 flex flex-wrap items-center justify-center gap-3">
                  <button
                    onClick={handleOpenPortalModal}
                    className="px-5 py-2.5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white rounded-xl text-xs font-bold shadow-md cursor-pointer flex items-center gap-2 transition-all"
                  >
                    <Globe className="w-4 h-4" />
                    <span>Upload Directly to GST Portal (API)</span>
                  </button>
                  <button
                    onClick={handleDownloadGSTR1}
                    className="px-4 py-2.5 bg-secondary hover:bg-secondary/80 text-secondary-foreground rounded-xl text-xs font-semibold border border-border cursor-pointer flex items-center gap-2"
                  >
                    <Download className="w-4 h-4" />
                    <span>Export JSON File</span>
                  </button>
                  <button
                    onClick={handleMarkAsFiled}
                    className="px-4 py-2.5 bg-secondary hover:bg-secondary/80 text-secondary-foreground rounded-xl text-xs font-semibold border border-border cursor-pointer transition-colors"
                  >
                    Mark Period as Filed
                  </button>
                </div>
              </div>
            )}

            {/* Clean Vouchers Ready for Return Table */}
            {exceptionsData?.clean_vouchers && exceptionsData.clean_vouchers.length > 0 && (
              <div className="bg-card border border-border rounded-2xl p-5 shadow-xs space-y-4">
                <div className="flex items-center justify-between border-b border-border pb-3">
                  <div>
                    <h3 className="text-base font-bold text-foreground flex items-center gap-2">
                      <span className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                        <CheckCircle2 className="w-4 h-4" />
                      </span>
                      <span>Clean & Audit-Ready Invoices ({exceptionsData.clean_count})</span>
                    </h3>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      These invoices have passed statutory checks (GSTIN, HSN, Tax Rate) and will be included in the GSTR-1 & GSTR-3B filings.
                    </p>
                  </div>
                  <div className="text-xs font-mono font-bold text-emerald-600 dark:text-emerald-400">
                    Total: ₹{(exceptionsData.clean_total_amount ?? 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-border text-muted-foreground uppercase font-semibold text-[11px] tracking-wider">
                        <th className="pb-3">Invoice No</th>
                        <th className="pb-3">Date</th>
                        <th className="pb-3">Customer / Party</th>
                        <th className="pb-3">GSTIN</th>
                        <th className="pb-3">Place of Supply</th>
                        <th className="pb-3 text-right">Total (₹)</th>
                        <th className="pb-3 text-center">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/60">
                      {exceptionsData.clean_vouchers.map((v: any) => (
                        <tr key={v.id} className="hover:bg-muted/40 transition-colors">
                          <td className="py-3 font-mono font-bold text-foreground">{v.voucher_number}</td>
                          <td className="py-3 text-muted-foreground font-mono">{v.date}</td>
                          <td className="py-3 font-medium text-foreground">{v.party_name}</td>
                          <td className="py-3 font-mono text-muted-foreground bg-muted/60 px-1.5 py-0.5 rounded text-[11px]">{v.party_gstin || "B2C / Unregistered"}</td>
                          <td className="py-3 font-mono text-muted-foreground">{v.pos || "09"}</td>
                          <td className="py-3 font-bold font-mono text-foreground text-right">₹{Number(v.total_amount).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</td>
                          <td className="py-3 text-center">
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800 rounded-full text-[10px] font-semibold">
                              <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                              Audit Ready
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Content for Annual Return (GSTR-9) */}
        {activeTab === "annual" && (
          <div className="space-y-6">
            <div className="bg-card border border-border rounded-2xl p-6 shadow-sm space-y-6">
              <div className="border-b border-border pb-3">
                <h3 className="text-lg font-bold text-foreground">Annual Return (GSTR-9) Summary: {selectedYear}</h3>
                <p className="text-xs text-muted-foreground">
                  Consolidated turnover and ITC comparison across all 4 quarters for year-end statutory audit.
                </p>
              </div>

              {/* Quarterly Breakdown Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {gstr9Data?.quarterly_breakdown?.map((q: any, idx: number) => (
                  <div key={idx} className="p-4 bg-muted/40 rounded-xl border border-border space-y-2 text-xs">
                    <div className="font-bold text-foreground">{q.quarter}</div>
                    <div className="flex justify-between text-muted-foreground">
                      <span>Sales ({q.sales_count} bills):</span>
                      <span className="font-mono font-bold text-foreground">₹{q.sales_total.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between text-muted-foreground">
                      <span>Purchases ({q.purchase_count} bills):</span>
                      <span className="font-mono font-bold text-foreground">₹{q.purchase_total.toFixed(2)}</span>
                    </div>
                  </div>
                ))}
              </div>

              {/* Annual Totals Summary */}
              <div className="p-5 bg-background border border-border rounded-xl grid grid-cols-1 md:grid-cols-2 gap-6 text-xs font-mono">
                <div>
                  <div className="font-sans font-bold text-foreground text-sm mb-2">Table 4: Outward Supplies</div>
                  <div className="flex justify-between text-muted-foreground py-1 border-b border-border/50">
                    <span>Total Taxable Turnover:</span>
                    <span className="text-foreground font-bold">₹{(gstr9Data?.table_4_outward_annual?.total_turnover ?? 0).toFixed(2)}</span>
                  </div>
                </div>
                <div>
                  <div className="font-sans font-bold text-foreground text-sm mb-2">Table 6: ITC Availed</div>
                  <div className="flex justify-between text-muted-foreground py-1 border-b border-border/50">
                    <span>Total Input Tax Credit:</span>
                    <span className="text-foreground font-bold">₹{(gstr9Data?.table_6_itc_annual?.total_itc_availed ?? 0).toFixed(2)}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 1-Click In-place Resolution Modal */}
        {editingVoucher && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-150">
            <div className="bg-card border border-border rounded-2xl max-w-lg w-full p-6 space-y-4 shadow-2xl text-foreground">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <h3 className="text-base font-bold">Fix Invoice Clerical Error</h3>
                <button onClick={() => setEditingVoucher(null)} className="text-muted-foreground hover:text-foreground cursor-pointer">✕</button>
              </div>

              <div className="space-y-3 text-xs">
                <div>
                  <span className="text-muted-foreground">Invoice:</span>
                  <span className="font-mono font-bold text-foreground ml-2">{editingVoucher.voucher_number}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Customer:</span>
                  <span className="font-bold text-foreground ml-2">{editingVoucher.party_name}</span>
                </div>

                <div className="space-y-1 pt-2">
                  <label className="block text-muted-foreground font-semibold">Correct 15-Digit GSTIN:</label>
                  <input
                    type="text"
                    value={editGstin}
                    onChange={(e) => setEditGstin(e.target.value.toUpperCase())}
                    placeholder="e.g. 09ACHFS9225Q1Z7"
                    className="w-full p-2.5 bg-background border border-border rounded-lg font-mono uppercase text-sm font-semibold text-foreground outline-none focus:ring-2 focus:ring-primary"
                  />
                  <p className="text-[11px] text-muted-foreground">
                    Tip: Enter 15 characters matching customer state code.
                  </p>
                </div>
              </div>

              <div className="pt-3 border-t border-border flex justify-end gap-3">
                <button
                  onClick={() => setEditingVoucher(null)}
                  className="px-4 py-2 bg-secondary hover:bg-secondary/80 text-secondary-foreground rounded-lg text-xs font-semibold cursor-pointer border border-border transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={async () => {
                    setSavingEdit(true);
                    try {
                      const token = getAccessToken();
                      const headers = { Authorization: `Bearer ${token}` };
                      // Update party gstin or voucher
                      await axios.post(
                        `${API_BASE_URL}/api/v1/accounting/vouchers/`,
                        {
                          id: editingVoucher.id,
                          buyer_gstin: editGstin,
                          correction_reason: "Clerical GSTIN fix in GST Center",
                          correction_type: "CLERICAL"
                        },
                        { headers }
                      ).catch(() => {});
                      setEditingVoucher(null);
                      loadGSTData();
                    } catch (e) {
                      console.error(e);
                    } finally {
                      setSavingEdit(false);
                    }
                  }}
                  className="px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg text-xs font-bold shadow-md cursor-pointer transition-all"
                >
                  {savingEdit ? "Saving..." : "Save & Re-validate"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Direct GST Portal Upload Modal */}
        {showPortalModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-150">
            <div className="bg-card border border-border rounded-2xl max-w-lg w-full p-6 space-y-5 shadow-2xl text-foreground">
              {/* Header */}
              <div className="flex items-center justify-between border-b border-border pb-3">
                <div className="flex items-center gap-2.5">
                  <span className="p-2 rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400 font-bold border border-blue-500/20">
                    <Globe className="w-5 h-5" />
                  </span>
                  <div>
                    <h3 className="text-base font-bold">Direct GST Portal Return Upload</h3>
                    <p className="text-xs text-muted-foreground">
                      GSTN Developer Sandbox API • Direct Return Submission
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setShowPortalModal(false)}
                  className="text-muted-foreground hover:text-foreground cursor-pointer"
                >
                  ✕
                </button>
              </div>

              {/* Progress Indicator */}
              <div className="grid grid-cols-3 gap-2 text-[11px] font-semibold">
                <div className={`p-2 rounded-lg text-center border ${
                  portalStep === "auth"
                    ? "bg-primary/10 border-primary text-primary"
                    : "bg-muted/40 border-border text-muted-foreground"
                }`}>
                  1. Credentials
                </div>
                <div className={`p-2 rounded-lg text-center border ${
                  portalStep === "otp"
                    ? "bg-primary/10 border-primary text-primary"
                    : portalStep === "confirm" || portalStep === "success"
                    ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800"
                    : "bg-muted/40 border-border text-muted-foreground"
                }`}>
                  2. OTP Verify
                </div>
                <div className={`p-2 rounded-lg text-center border ${
                  portalStep === "confirm" || portalStep === "success"
                    ? "bg-primary/10 border-primary text-primary"
                    : "bg-muted/40 border-border text-muted-foreground"
                }`}>
                  3. Upload & ARN
                </div>
              </div>

              {portalError && (
                <div className="p-3 bg-red-500/10 border border-red-500/30 text-red-600 dark:text-red-400 rounded-xl text-xs flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  <span>{portalError}</span>
                </div>
              )}

              {/* Step 1: Credentials */}
              {portalStep === "auth" && (
                <div className="space-y-4 text-xs">
                  <div className="p-3.5 bg-blue-500/10 border border-blue-500/20 text-blue-800 dark:text-blue-300 rounded-xl space-y-1">
                    <div className="font-bold flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5" />
                      <span>Zero JSON Exporting Required</span>
                    </div>
                    <p className="text-[11px] leading-relaxed">
                      Your return data will be validated against statutory schema rules and pushed directly to the GSTN Gateway API.
                    </p>
                  </div>

                  <div className="space-y-3">
                    <div>
                      <label className="block font-semibold text-muted-foreground mb-1">Taxpayer GSTIN:</label>
                      <input
                        type="text"
                        value={portalGstin}
                        onChange={(e) => setPortalGstin(e.target.value.toUpperCase())}
                        placeholder="e.g. 09ACHFS9225Q1Z7"
                        className="w-full p-2.5 bg-background border border-border rounded-xl font-mono uppercase text-xs font-semibold text-foreground outline-none focus:ring-2 focus:ring-primary"
                      />
                    </div>

                    <div>
                      <label className="block font-semibold text-muted-foreground mb-1">GST Portal Username / ID:</label>
                      <input
                        type="text"
                        value={taxpayerUsername}
                        onChange={(e) => setTaxpayerUsername(e.target.value)}
                        placeholder="e.g. taxpayer_username"
                        className="w-full p-2.5 bg-background border border-border rounded-xl font-mono text-xs font-semibold text-foreground outline-none focus:ring-2 focus:ring-primary"
                      />
                    </div>
                  </div>

                  <div className="pt-3 border-t border-border flex justify-end gap-3">
                    <button
                      onClick={() => setShowPortalModal(false)}
                      className="px-4 py-2 bg-secondary hover:bg-secondary/80 text-secondary-foreground rounded-lg text-xs font-semibold cursor-pointer border border-border transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleRequestOTP}
                      disabled={portalLoading}
                      className="px-5 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg text-xs font-bold shadow-md cursor-pointer transition-all flex items-center gap-2"
                    >
                      <Send className="w-3.5 h-3.5" />
                      <span>{portalLoading ? "Connecting..." : "Request GST Portal OTP"}</span>
                    </button>
                  </div>
                </div>
              )}

              {/* Step 2: OTP Verification */}
              {portalStep === "otp" && (
                <div className="space-y-4 text-xs">
                  <div className="p-3.5 bg-emerald-50 border border-emerald-200 dark:bg-emerald-950/40 dark:border-emerald-800 text-emerald-900 dark:text-emerald-300 rounded-xl space-y-1">
                    <div className="font-bold flex items-center gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>OTP Dispatched by GST Portal</span>
                    </div>
                    <p className="text-[11px]">
                      A 6-digit OTP has been sent to the registered mobile ({maskedMobile}) for GSTIN <strong>{portalGstin}</strong>.
                    </p>
                  </div>

                  <div className="space-y-1.5">
                    <label className="block font-semibold text-muted-foreground">Enter 6-Digit OTP:</label>
                    <input
                      type="text"
                      maxLength={6}
                      value={portalOtp}
                      onChange={(e) => setPortalOtp(e.target.value)}
                      placeholder="e.g. 575757"
                      className="w-full p-3 bg-background border border-border rounded-xl font-mono text-center tracking-[0.5em] text-lg font-bold text-foreground outline-none focus:ring-2 focus:ring-primary"
                    />
                    <div className="flex items-center justify-between text-[11px] text-muted-foreground pt-1">
                      <span>Sandbox Demo OTP: <strong className="text-foreground">575757</strong></span>
                      <button onClick={handleRequestOTP} className="text-primary hover:underline cursor-pointer">Resend OTP</button>
                    </div>
                  </div>

                  <div className="pt-3 border-t border-border flex justify-end gap-3">
                    <button
                      onClick={() => setPortalStep("auth")}
                      className="px-4 py-2 bg-secondary hover:bg-secondary/80 text-secondary-foreground rounded-lg text-xs font-semibold cursor-pointer border border-border transition-colors"
                    >
                      Back
                    </button>
                    <button
                      onClick={handleVerifyOTP}
                      disabled={portalLoading}
                      className="px-5 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg text-xs font-bold shadow-md cursor-pointer transition-all flex items-center gap-2"
                    >
                      <Key className="w-3.5 h-3.5" />
                      <span>{portalLoading ? "Verifying..." : "Verify & Activate Session"}</span>
                    </button>
                  </div>
                </div>
              )}

              {/* Step 3: Confirm & Upload */}
              {portalStep === "confirm" && (
                <div className="space-y-4 text-xs">
                  <div className="p-4 bg-muted/40 border border-border rounded-xl space-y-2.5 font-mono">
                    <div className="flex justify-between text-muted-foreground font-sans text-xs">
                      <span>Filing Period:</span>
                      <span className="font-bold text-foreground">{getStartAndEndDate().periodLabel}</span>
                    </div>
                    <div className="flex justify-between text-muted-foreground">
                      <span>Clean Vouchers Ready:</span>
                      <span className="font-bold text-foreground">{exceptionsData?.clean_count ?? 0} Invoices</span>
                    </div>
                    <div className="flex justify-between text-muted-foreground">
                      <span>Total Return Value:</span>
                      <span className="font-bold text-foreground">₹{(exceptionsData?.clean_total_amount ?? 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
                    </div>
                    <div className="flex justify-between text-muted-foreground">
                      <span>Portal Gateway:</span>
                      <span className="font-bold text-emerald-700 dark:text-emerald-400">GSTN Developer Sandbox</span>
                    </div>
                  </div>

                  {(exceptionsData?.exception_count ?? 0) > 0 && (
                    <div className="p-3 bg-amber-500/10 border border-amber-500/30 text-amber-800 dark:text-amber-300 rounded-xl text-xs flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4 shrink-0 text-amber-600 dark:text-amber-400" />
                      <span>
                        Note: You have {exceptionsData.exception_count} pending clerical exceptions. The clean vouchers ({exceptionsData.clean_count}) will be uploaded.
                      </span>
                    </div>
                  )}

                  <div className="pt-3 border-t border-border flex justify-end gap-3">
                    <button
                      onClick={() => setShowPortalModal(false)}
                      className="px-4 py-2 bg-secondary hover:bg-secondary/80 text-secondary-foreground rounded-lg text-xs font-semibold cursor-pointer border border-border transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleDirectUploadGSTR1}
                      disabled={portalLoading}
                      className="px-6 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white rounded-lg text-xs font-bold shadow-md cursor-pointer transition-all flex items-center gap-2"
                    >
                      <UploadCloud className="w-4 h-4" />
                      <span>{portalLoading ? "Transmitting to GSTN..." : "Confirm & Upload GSTR-1 to Portal"}</span>
                    </button>
                  </div>
                </div>
              )}

              {/* Step 4: Success Acknowledgement */}
              {portalStep === "success" && uploadAck && (
                <div className="space-y-4 text-xs text-center">
                  <div className="w-14 h-14 rounded-2xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center mx-auto text-2xl font-bold border border-emerald-500/20 shadow-xs">
                    <CheckCircle2 className="w-7 h-7" />
                  </div>
                  <div>
                    <h4 className="text-base font-bold text-foreground">Return Transmitted Successfully!</h4>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Your GSTR-1 return was accepted and verified by the GST Portal API.
                    </p>
                  </div>

                  <div className="p-4 bg-muted/40 border border-border rounded-xl space-y-2 text-left font-mono">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Reference ID / ARN:</span>
                      <span className="font-bold text-foreground">{uploadAck.reference_id}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Portal Status:</span>
                      <span className="font-bold text-emerald-700 dark:text-emerald-400">{uploadAck.status}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Invoices Processed:</span>
                      <span className="font-bold text-foreground">{uploadAck.b2b_invoices_uploaded} B2B Invoices</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">HSN Summary Lines:</span>
                      <span className="font-bold text-foreground">{uploadAck.hsn_entries_uploaded} Codes</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Ack Timestamp:</span>
                      <span className="text-muted-foreground">{uploadAck.ack_timestamp}</span>
                    </div>
                  </div>

                  <div className="pt-2 flex justify-center">
                    <button
                      onClick={() => {
                        setShowPortalModal(false);
                        loadGSTData();
                      }}
                      className="px-6 py-2.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl text-xs font-bold shadow-md cursor-pointer transition-all"
                    >
                      Done & Close
                    </button>
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
