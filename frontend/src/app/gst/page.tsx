"use client";
import React, { useState, useEffect, useCallback } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { useCompany } from "@/context/CompanyContext";
import { useFinancialYear } from "@/context/FinancialYearContext";
import { useToast } from "@/context/ToastContext";
import { gstApi, GSTRegistration, GSTR2BRecordItem, GSTAuditLogItem } from "@/lib/api/gst";
import { 
  ShieldCheck, 
  Building2, 
  FileText, 
  CheckCircle2, 
  AlertTriangle, 
  RefreshCw, 
  Download, 
  Send, 
  Search, 
  Truck, 
  History, 
  ExternalLink, 
  Plus, 
  Filter, 
  Clock, 
  Check, 
  X,
  Layers,
  ChevronRight,
  ArrowUpRight
} from "lucide-react";
import GSTINVerifyDialog from "@/components/gst/GSTINVerifyDialog";

export default function GSTWorkspacePage() {
  const { activeCompany, companyId } = useCompany();
  const { activeFY } = useFinancialYear();
  const { toast } = useToast();

  const [activeTab, setActiveTab] = useState<
    "overview" | "gstr1" | "gstr3b" | "reconciliation" | "einvoice" | "lookup" | "audit"
  >("overview");

  // Multi-GSTIN Registrations
  const [registrations, setRegistrations] = useState<GSTRegistration[]>([]);
  const [selectedRegId, setSelectedRegId] = useState<string>("");
  const [loadingRegs, setLoadingRegs] = useState(false);

  // Overview data
  const [overviewData, setOverviewData] = useState<any>(null);
  const [loadingOverview, setLoadingOverview] = useState(false);

  // Period state (YYYY-MM)
  const [period, setPeriod] = useState<string>(() => {
    const d = new Date();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    return `${d.getFullYear()}-${m}`;
  });

  // GSTR-1 state
  const [gstr1Data, setGstr1Data] = useState<any>(null);
  const [loadingGstr1, setLoadingGstr1] = useState(false);
  const [submittingGstr1, setSubmittingGstr1] = useState(false);

  // GSTR-3B state
  const [gstr3bData, setGstr3bData] = useState<any>(null);
  const [loadingGstr3b, setLoadingGstr3b] = useState(false);

  // GSTR-2B Reconciliation state
  const [reconData, setReconData] = useState<any>(null);
  const [selectedCategory, setSelectedCategory] = useState<string>("ALL");
  const [loadingRecon, setLoadingRecon] = useState(false);
  const [syncing2B, setSyncing2B] = useState(false);

  // Lookup Tool state
  const [searchGstin, setSearchGstin] = useState("");
  const [lookupResult, setLookupResult] = useState<any>(null);
  const [lookingUp, setLookingUp] = useState(false);

  // Audit Log state
  const [auditLogs, setAuditLogs] = useState<GSTAuditLogItem[]>([]);
  const [loadingAudit, setLoadingAudit] = useState(false);

  // 1. Fetch Registrations
  const fetchRegistrations = useCallback(async () => {
    if (!companyId) return;
    setLoadingRegs(true);
    try {
      const list = await gstApi.getRegistrations(companyId);
      setRegistrations(list);
      if (list.length > 0 && !selectedRegId) {
        const primary = list.find((r) => r.is_primary) || list[0];
        setSelectedRegId(primary.id);
      }
    } catch (err: any) {
      console.error("Failed to load GST registrations", err);
    } finally {
      setLoadingRegs(false);
    }
  }, [companyId, selectedRegId]);

  // 2. Fetch Overview
  const fetchOverview = useCallback(async () => {
    if (!companyId) return;
    setLoadingOverview(true);
    try {
      const data = await gstApi.getOverview(selectedRegId || undefined, companyId);
      setOverviewData(data);
    } catch (err: any) {
      console.error("Failed to load GST overview", err);
    } finally {
      setLoadingOverview(false);
    }
  }, [companyId, selectedRegId]);

  // 3. Fetch GSTR-1
  const fetchGSTR1 = useCallback(async () => {
    if (!companyId) return;
    setLoadingGstr1(true);
    try {
      const data = await gstApi.getGSTR1Workspace(period, selectedRegId || undefined, companyId);
      setGstr1Data(data);
    } catch (err: any) {
      toast.error("Failed to load GSTR-1", err.response?.data?.message || err.message);
    } finally {
      setLoadingGstr1(false);
    }
  }, [companyId, period, selectedRegId, toast]);

  // 4. Fetch GSTR-3B
  const fetchGSTR3B = useCallback(async () => {
    if (!companyId) return;
    setLoadingGstr3b(true);
    try {
      const data = await gstApi.getGSTR3BWorkspace(period, selectedRegId || undefined, companyId);
      setGstr3bData(data);
    } catch (err: any) {
      toast.error("Failed to load GSTR-3B", err.response?.data?.message || err.message);
    } finally {
      setLoadingGstr3b(false);
    }
  }, [companyId, period, selectedRegId, toast]);

  // 5. Fetch Reconciliation
  const fetchReconciliation = useCallback(async () => {
    if (!companyId) return;
    setLoadingRecon(true);
    try {
      const params: any = {
        return_period: period,
      };
      if (selectedRegId) params.registration_id = selectedRegId;
      if (selectedCategory && selectedCategory !== "ALL") {
        params.match_category = selectedCategory;
      }
      const data = await gstApi.getGSTR2BReconciliation(params, companyId);
      setReconData(data);
    } catch (err: any) {
      console.error("Reconciliation error", err);
    } finally {
      setLoadingRecon(false);
    }
  }, [companyId, period, selectedRegId, selectedCategory]);

  // 6. Fetch Audit Logs
  const fetchAuditLogs = useCallback(async () => {
    if (!companyId) return;
    setLoadingAudit(true);
    try {
      const data = await gstApi.getAuditLogs(undefined, companyId);
      setAuditLogs(data?.results || data || []);
    } catch (err: any) {
      console.error("Failed to load audit logs", err);
    } finally {
      setLoadingAudit(false);
    }
  }, [companyId]);

  useEffect(() => {
    fetchRegistrations();
  }, [fetchRegistrations]);

  useEffect(() => {
    if (activeTab === "overview") fetchOverview();
    if (activeTab === "gstr1") fetchGSTR1();
    if (activeTab === "gstr3b") fetchGSTR3B();
    if (activeTab === "reconciliation") fetchReconciliation();
    if (activeTab === "audit") fetchAuditLogs();
  }, [activeTab, fetchOverview, fetchGSTR1, fetchGSTR3B, fetchReconciliation, fetchAuditLogs]);

  // Actions
  const handleSync2B = async () => {
    if (!companyId) return;
    const [y, m] = period.split("-");
    setSyncing2B(true);
    try {
      const res = await gstApi.syncGSTR2BFromSandbox({
        year: parseInt(y),
        month: parseInt(m),
        registration_id: selectedRegId || undefined,
      }, companyId);
      toast.success("GSTR-2B Synced", `Processed ${res.records_imported || 0} records from Sandbox.`);
      fetchReconciliation();
    } catch (err: any) {
      toast.error("GSTR-2B Sync Failed", err.response?.data?.message || err.message);
    } finally {
      setSyncing2B(false);
    }
  };

  const handleDownloadGSTR1JSON = () => {
    if (!gstr1Data?.gstr1_payload) return;
    const blob = new Blob([JSON.stringify(gstr1Data.gstr1_payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `GSTR1_${period}_${selectedReg?.gstin || "ALL"}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("JSON Downloaded", "Ready for offline GST portal tool or API upload.");
  };

  const handleSubmitGSTR1 = async () => {
    if (!gstr1Data?.gstr1_payload?.tables) return;
    setSubmittingGstr1(true);
    try {
      const res = await gstApi.submitGSTR1({
        period,
        registration_id: selectedRegId || undefined,
        tables: gstr1Data.gstr1_payload.tables,
      }, companyId || undefined);
      toast.success("GSTR-1 Submitted", res.message || "Submitted to GST Sandbox successfully.");
      fetchGSTR1();
    } catch (err: any) {
      toast.error("Submission Failed", err.response?.data?.message || err.message);
    } finally {
      setSubmittingGstr1(false);
    }
  };

  const handleReviewRecord = async (recordId: string, action: string) => {
    try {
      await gstApi.reviewGSTR2BRecord(recordId, action, undefined, companyId || undefined);
      toast.success("Record Reviewed", `Marked as ${action}`);
      fetchReconciliation();
    } catch (err: any) {
      toast.error("Review Failed", err.response?.data?.message || err.message);
    }
  };

  const handleStandaloneLookup = async () => {
    const clean = searchGstin.trim().toUpperCase();
    if (clean.length !== 15) {
      toast.warning("GSTIN must be 15 alphanumeric characters.");
      return;
    }
    setLookingUp(true);
    try {
      const res = await gstApi.verifyGSTIN(clean, undefined, companyId || undefined);
      if (res.success && res.data) {
        setLookupResult(res.data);
      } else {
        toast.error("Not Found", res.error || "Taxpayer not found.");
      }
    } catch (err: any) {
      toast.error("Lookup Error", err.response?.data?.message || err.message);
    } finally {
      setLookingUp(false);
    }
  };

  const selectedReg = registrations.find((r) => r.id === selectedRegId);

  return (
    <DashboardLayout>
      <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-6">
        {/* Top Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-xl bg-primary/10 text-primary">
                <ShieldCheck className="w-6 h-6" />
              </div>
              <div>
                <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground">
                  GST Compliance Center
                </h1>
                <p className="text-xs text-muted-foreground">
                  Powered by Sandbox (Quicko) • e-Invoice, e-Way Bill, GSTR-1, & GSTR-2B
                </p>
              </div>
            </div>
          </div>

          {/* Controls: Multi-GSTIN & Period Selector */}
          <div className="flex flex-wrap items-center gap-3">
            {/* Multi-GSTIN Registration Switcher */}
            <div className="flex items-center gap-2 bg-card border border-border px-3 py-1.5 rounded-xl text-xs">
              <Building2 className="w-4 h-4 text-muted-foreground" />
              <select
                value={selectedRegId}
                onChange={(e) => setSelectedRegId(e.target.value)}
                className="bg-transparent font-semibold text-foreground outline-none cursor-pointer"
              >
                {registrations.length === 0 ? (
                  <option value="">{activeCompany?.gstin ? `${activeCompany.gstin} (Company)` : "No GSTIN Registered"}</option>
                ) : (
                  registrations.map((reg) => (
                    <option key={reg.id} value={reg.id}>
                      {reg.gstin} ({reg.state_code}) {reg.is_primary ? "★ Primary" : ""}
                    </option>
                  ))
                )}
              </select>
            </div>

            {/* Period Selector */}
            <div className="flex items-center gap-2 bg-card border border-border px-3 py-1.5 rounded-xl text-xs">
              <span className="text-muted-foreground font-medium">Period:</span>
              <input
                type="month"
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
                className="bg-transparent font-semibold text-foreground outline-none cursor-pointer"
              />
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto border-b border-border/60 pb-2 text-xs font-semibold">
          {[
            { id: "overview", label: "Compliance Overview", icon: Layers },
            { id: "gstr1", label: "GSTR-1 Returns", icon: FileText },
            { id: "gstr3b", label: "GSTR-3B Summary", icon: CheckCircle2 },
            { id: "reconciliation", label: "GSTR-2B Reconciliation", icon: RefreshCw },
            { id: "lookup", label: "GSTIN Verifier", icon: Search },
            { id: "audit", label: "Audit Trail", icon: History },
          ].map((tab) => {
            const Icon = tab.icon;
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl transition-all cursor-pointer whitespace-nowrap ${
                  active
                    ? "bg-primary text-primary-foreground shadow-xs font-bold"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* TAB 1: OVERVIEW */}
        {activeTab === "overview" && (
          <div className="space-y-6">
            {/* Stat Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="p-5 rounded-2xl bg-card border border-border/80 shadow-xs space-y-2">
                <div className="flex items-center justify-between text-muted-foreground text-xs">
                  <span>Registered GSTIN</span>
                  <Building2 className="w-4 h-4 text-primary" />
                </div>
                <div className="text-lg font-mono font-bold text-foreground">
                  {selectedReg?.gstin || activeCompany?.gstin || "Not Configured"}
                </div>
                <div className="text-[11px] text-emerald-500 font-semibold flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>State {selectedReg?.state_code || "Active"}</span>
                </div>
              </div>

              <div className="p-5 rounded-2xl bg-card border border-border/80 shadow-xs space-y-2">
                <div className="flex items-center justify-between text-muted-foreground text-xs">
                  <span>Next GSTR-1 Deadline</span>
                  <Clock className="w-4 h-4 text-blue-500" />
                </div>
                <div className="text-lg font-bold text-foreground">11th of Next Month</div>
                <div className="text-[11px] text-muted-foreground">Monthly Outward Supplies</div>
              </div>

              <div className="p-5 rounded-2xl bg-card border border-border/80 shadow-xs space-y-2">
                <div className="flex items-center justify-between text-muted-foreground text-xs">
                  <span>Next GSTR-3B Deadline</span>
                  <Clock className="w-4 h-4 text-purple-500" />
                </div>
                <div className="text-lg font-bold text-foreground">20th of Next Month</div>
                <div className="text-[11px] text-muted-foreground">Summary & Tax Payment</div>
              </div>

              <div className="p-5 rounded-2xl bg-card border border-border/80 shadow-xs space-y-2">
                <div className="flex items-center justify-between text-muted-foreground text-xs">
                  <span>API Integration</span>
                  <ShieldCheck className="w-4 h-4 text-emerald-500" />
                </div>
                <div className="text-lg font-bold text-foreground">Sandbox (Quicko)</div>
                <div className="text-[11px] text-emerald-500 font-semibold">Test Environment Active</div>
              </div>
            </div>

            {/* Quick Actions Card */}
            <div className="p-6 rounded-2xl bg-gradient-to-r from-primary/10 via-card to-card border border-border/80 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
              <div className="space-y-1">
                <h3 className="text-base font-bold text-foreground">Need to prepare your returns?</h3>
                <p className="text-xs text-muted-foreground max-w-xl">
                  Review calculated B2B, B2C, HSN, and Taxable values computed automatically from your double-entry posted vouchers.
                </p>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setActiveTab("gstr1")}
                  className="px-4 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:bg-primary/90 transition-all flex items-center gap-1.5"
                >
                  <span>Review GSTR-1</span>
                  <ChevronRight className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setActiveTab("reconciliation")}
                  className="px-4 py-2 rounded-xl bg-card border border-border text-foreground text-xs font-bold hover:bg-muted/40 transition-all flex items-center gap-1.5"
                >
                  <RefreshCw className="w-4 h-4 text-primary" />
                  <span>2B Reconciliation</span>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: GSTR-1 */}
        {activeTab === "gstr1" && (
          <div className="space-y-5">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div>
                <h2 className="text-lg font-bold text-foreground">GSTR-1 Return Preparation</h2>
                <p className="text-xs text-muted-foreground">Period: {period} • Real-time outward supplies from posted sales</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={fetchGSTR1}
                  disabled={loadingGstr1}
                  className="p-2 rounded-xl border border-border bg-card hover:bg-muted text-foreground"
                >
                  <RefreshCw className={`w-4 h-4 ${loadingGstr1 ? "animate-spin" : ""}`} />
                </button>
                <button
                  onClick={handleDownloadGSTR1JSON}
                  disabled={!gstr1Data}
                  className="px-3.5 py-2 rounded-xl border border-border bg-card hover:bg-muted text-foreground text-xs font-semibold flex items-center gap-1.5"
                >
                  <Download className="w-4 h-4" />
                  <span>Download JSON</span>
                </button>
                <button
                  onClick={handleSubmitGSTR1}
                  disabled={submittingGstr1 || !gstr1Data}
                  className="px-4 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:bg-primary/90 flex items-center gap-1.5"
                >
                  <Send className={`w-4 h-4 ${submittingGstr1 ? "animate-spin" : ""}`} />
                  <span>Submit to Sandbox</span>
                </button>
              </div>
            </div>

            {loadingGstr1 ? (
              <div className="p-12 text-center text-muted-foreground text-xs">Computing GSTR-1 tables...</div>
            ) : gstr1Data ? (
              <div className="space-y-4">
                {/* Tables Grid */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {Object.entries(gstr1Data.tables_summary || {}).map(([key, val]: any) => (
                    <div key={key} className="p-4 rounded-xl border border-border bg-card space-y-1.5">
                      <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{key}</div>
                      <div className="text-xl font-bold text-foreground">₹ {Number(val.taxable_value || 0).toLocaleString()}</div>
                      <div className="text-xs text-muted-foreground flex justify-between">
                        <span>Records: {val.record_count || 0}</span>
                        <span>Tax: ₹ {Number(val.total_tax || 0).toLocaleString()}</span>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Validation Warnings */}
                {gstr1Data.validation_errors?.length > 0 && (
                  <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-500 text-xs space-y-1">
                    <div className="font-bold flex items-center gap-1.5">
                      <AlertTriangle className="w-4 h-4" />
                      <span>Pre-filing Warnings ({gstr1Data.validation_errors.length})</span>
                    </div>
                    <ul className="list-disc list-inside space-y-0.5">
                      {gstr1Data.validation_errors.map((err: string, i: number) => (
                        <li key={i}>{err}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <div className="p-12 text-center text-muted-foreground text-xs">No data for selected period.</div>
            )}
          </div>
        )}

        {/* TAB 3: GSTR-3B */}
        {activeTab === "gstr3b" && (
          <div className="space-y-5">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-foreground">GSTR-3B Monthly Tax Summary</h2>
                <p className="text-xs text-muted-foreground">Period: {period} • Tax liability vs eligible ITC</p>
              </div>
              <button
                onClick={fetchGSTR3B}
                disabled={loadingGstr3b}
                className="p-2 rounded-xl border border-border bg-card hover:bg-muted text-foreground"
              >
                <RefreshCw className={`w-4 h-4 ${loadingGstr3b ? "animate-spin" : ""}`} />
              </button>
            </div>

            {loadingGstr3b ? (
              <div className="p-12 text-center text-muted-foreground text-xs">Loading GSTR-3B...</div>
            ) : gstr3bData ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {/* Outward Tax Liability */}
                <div className="p-5 rounded-2xl bg-card border border-border space-y-4">
                  <div className="font-bold text-sm text-foreground">Table 3.1: Tax on Outward Supplies</div>
                  <div className="space-y-2 text-xs">
                    <div className="flex justify-between py-1 border-b border-border/40">
                      <span className="text-muted-foreground">Taxable Value</span>
                      <span className="font-bold">₹ {Number(gstr3bData.outward_supplies?.taxable_value || 0).toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-border/40">
                      <span className="text-muted-foreground">IGST</span>
                      <span className="font-bold">₹ {Number(gstr3bData.outward_supplies?.igst || 0).toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-border/40">
                      <span className="text-muted-foreground">CGST</span>
                      <span className="font-bold">₹ {Number(gstr3bData.outward_supplies?.cgst || 0).toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-border/40">
                      <span className="text-muted-foreground">SGST</span>
                      <span className="font-bold">₹ {Number(gstr3bData.outward_supplies?.sgst || 0).toLocaleString()}</span>
                    </div>
                  </div>
                </div>

                {/* Eligible ITC */}
                <div className="p-5 rounded-2xl bg-card border border-border space-y-4">
                  <div className="font-bold text-sm text-foreground">Table 4: Eligible Input Tax Credit (ITC)</div>
                  <div className="space-y-2 text-xs">
                    <div className="flex justify-between py-1 border-b border-border/40">
                      <span className="text-muted-foreground">All other ITC (IGST)</span>
                      <span className="font-bold text-emerald-500">₹ {Number(gstr3bData.itc_eligible?.igst || 0).toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-border/40">
                      <span className="text-muted-foreground">All other ITC (CGST)</span>
                      <span className="font-bold text-emerald-500">₹ {Number(gstr3bData.itc_eligible?.cgst || 0).toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-border/40">
                      <span className="text-muted-foreground">All other ITC (SGST)</span>
                      <span className="font-bold text-emerald-500">₹ {Number(gstr3bData.itc_eligible?.sgst || 0).toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-border/40">
                      <span className="text-muted-foreground">Net Tax Payable (Cash)</span>
                      <span className="font-bold text-primary">₹ {Number(gstr3bData.net_tax_payable || 0).toLocaleString()}</span>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="p-12 text-center text-muted-foreground text-xs">No data available.</div>
            )}
          </div>
        )}

        {/* TAB 4: RECONCILIATION */}
        {activeTab === "reconciliation" && (
          <div className="space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold text-foreground">GSTR-2B ITC Reconciliation</h2>
                <p className="text-xs text-muted-foreground">Compare supplier GSTR-2B feeds with your purchase vouchers</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleSync2B}
                  disabled={syncing2B}
                  className="px-3.5 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:bg-primary/90 flex items-center gap-1.5"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${syncing2B ? "animate-spin" : ""}`} />
                  <span>{syncing2B ? "Syncing 2B..." : "Sync from Sandbox"}</span>
                </button>
              </div>
            </div>

            {/* Mismatch Category Filter Pills */}
            <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs">
              <span className="text-muted-foreground font-semibold flex items-center gap-1">
                <Filter className="w-3.5 h-3.5" /> Filter:
              </span>
              {[
                "ALL",
                "MATCHED",
                "PARTIAL_MATCH",
                "MISSING_IN_BOOKS",
                "MISSING_IN_2B",
                "TAX_MISMATCH",
                "DOC_NUM_MISMATCH",
                "DATE_MISMATCH",
                "INELIGIBLE_ITC",
              ].map((cat) => (
                <button
                  key={cat}
                  onClick={() => setSelectedCategory(cat)}
                  className={`px-3 py-1 rounded-lg text-xs font-semibold cursor-pointer transition-all ${
                    selectedCategory === cat
                      ? "bg-foreground text-background"
                      : "bg-muted/40 text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {cat.replace(/_/g, " ")}
                </button>
              ))}
            </div>

            {/* Records List */}
            {loadingRecon ? (
              <div className="p-12 text-center text-muted-foreground text-xs">Reconciling records...</div>
            ) : reconData?.records?.length > 0 ? (
              <div className="rounded-2xl border border-border overflow-hidden bg-card divide-y divide-border/60">
                {reconData.records.map((rec: GSTR2BRecordItem) => (
                  <div key={rec.id} className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-foreground">{rec.supplier_trade_name || rec.supplier_gstin}</span>
                        <span className="font-mono text-muted-foreground">({rec.supplier_gstin})</span>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          rec.match_category === "MATCHED"
                            ? "bg-emerald-500/10 text-emerald-500"
                            : "bg-amber-500/10 text-amber-500"
                        }`}>
                          {rec.match_category}
                        </span>
                      </div>
                      <div className="text-muted-foreground">
                        Inv #{rec.invoice_number} • Date: {rec.invoice_date} • Value: ₹{rec.invoice_value} • Tax: ₹{(Number(rec.igst_amount) + Number(rec.cgst_amount) + Number(rec.sgst_amount)).toFixed(2)}
                      </div>
                      {rec.mismatch_explanation && (
                        <div className="text-[11px] text-amber-500/90 font-medium">
                          {rec.mismatch_explanation}
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleReviewRecord(rec.id, "ACCEPT")}
                        className="px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20 font-bold"
                      >
                        Accept ITC
                      </button>
                      <button
                        onClick={() => handleReviewRecord(rec.id, "DISPUTE")}
                        className="px-3 py-1.5 rounded-lg bg-amber-500/10 text-amber-500 hover:bg-amber-500/20 font-bold"
                      >
                        Dispute
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-12 text-center text-muted-foreground text-xs">
                No reconciliation records found for category: {selectedCategory}
              </div>
            )}
          </div>
        )}

        {/* TAB 5: GSTIN VERIFIER */}
        {activeTab === "lookup" && (
          <div className="max-w-2xl mx-auto space-y-6">
            <div>
              <h2 className="text-lg font-bold text-foreground">GSTIN Search & Verification Tool</h2>
              <p className="text-xs text-muted-foreground">
                Verify any taxpayer GSTIN with Indian Luhn MOD-36 checksum and Sandbox portal lookup.
              </p>
            </div>

            <div className="flex gap-2">
              <input
                type="text"
                maxLength={15}
                placeholder="Enter 15-character GSTIN (e.g. 27AADCB2230M1ZT)"
                value={searchGstin}
                onChange={(e) => setSearchGstin(e.target.value.toUpperCase())}
                className="flex-1 bg-card border border-input rounded-xl px-4 py-2.5 text-xs font-mono uppercase focus:ring-2 focus:ring-primary outline-none"
              />
              <button
                onClick={handleStandaloneLookup}
                disabled={lookingUp || searchGstin.length !== 15}
                className="px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
              >
                {lookingUp ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                <span>Verify</span>
              </button>
            </div>

            {lookupResult && (
              <div className="p-6 rounded-2xl bg-card border border-border space-y-4 text-xs animate-in fade-in">
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <div className="font-bold text-base text-foreground">{lookupResult.legal_name || "Taxpayer"}</div>
                    <div className="font-mono text-muted-foreground">{lookupResult.gstin}</div>
                  </div>
                  <span className={`px-2.5 py-1 rounded-full font-bold uppercase text-[11px] ${
                    lookupResult.status === "ACTIVE"
                      ? "bg-emerald-500/10 text-emerald-500"
                      : "bg-red-500/10 text-red-500"
                  }`}>
                    {lookupResult.status}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3 text-muted-foreground pt-2 border-t border-border/60">
                  <div>
                    <span className="font-semibold block text-foreground">Trade Name:</span>
                    <span>{lookupResult.trade_name || "—"}</span>
                  </div>
                  <div>
                    <span className="font-semibold block text-foreground">Taxpayer Type:</span>
                    <span>{lookupResult.taxpayer_type || "Regular"}</span>
                  </div>
                  <div className="col-span-2">
                    <span className="font-semibold block text-foreground">Address:</span>
                    <span>{lookupResult.address || "—"}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 6: AUDIT TRAIL */}
        {activeTab === "audit" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-foreground">Compliance Audit Trail</h2>
                <p className="text-xs text-muted-foreground">Tamper-evident log of all GST compliance operations (passwords/tokens redacted)</p>
              </div>
              <button
                onClick={fetchAuditLogs}
                disabled={loadingAudit}
                className="p-2 rounded-xl border border-border bg-card hover:bg-muted text-foreground"
              >
                <RefreshCw className={`w-4 h-4 ${loadingAudit ? "animate-spin" : ""}`} />
              </button>
            </div>

            {loadingAudit ? (
              <div className="p-12 text-center text-muted-foreground text-xs">Loading audit logs...</div>
            ) : auditLogs.length > 0 ? (
              <div className="rounded-2xl border border-border overflow-hidden bg-card divide-y divide-border/60">
                {auditLogs.map((log) => (
                  <div key={log.id} className="p-4 flex items-center justify-between text-xs">
                    <div className="space-y-0.5">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-foreground">{log.action}</span>
                        <span className="font-mono text-muted-foreground">{log.gstin || "—"}</span>
                      </div>
                      <div className="text-[11px] text-muted-foreground">
                        {new Date(log.created_at).toLocaleString()}
                      </div>
                    </div>
                    <span className={`px-2.5 py-0.5 rounded text-[10px] font-bold uppercase ${
                      log.status === "SUCCESS"
                        ? "bg-emerald-500/10 text-emerald-500"
                        : "bg-red-500/10 text-red-500"
                    }`}>
                      {log.status}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-12 text-center text-muted-foreground text-xs">No audit logs recorded yet.</div>
            )}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
