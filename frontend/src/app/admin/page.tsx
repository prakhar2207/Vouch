"use client";
import { API_BASE_URL } from "@/utils/api";
import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import DashboardLayout from "@/components/DashboardLayout";
import { useToast } from "@/context/ToastContext";
import {
  ShieldAlert,
  Building2,
  Users,
  Receipt,
  TrendingUp,
  Activity,
  CheckCircle2,
  XCircle,
  Search,
  RefreshCw,
  ExternalLink,
  ArrowRight,
  ShieldCheck,
  Calendar,
  Layers,
  FileText,
  Lock,
  Unlock,
  UserCheck,
  UserX,
  Database,
  Server,
  Zap,
  LogIn
} from "lucide-react";

interface MetricsData {
  companies: {
    total: number;
    active: number;
    inactive: number;
    new_last_30_days: number;
  };
  users: {
    total: number;
    active: number;
    staff: number;
    new_last_30_days: number;
  };
  vouchers: {
    total: number;
    sales: number;
    purchases: number;
    other: number;
    new_last_30_days: number;
    gross_volume: number;
    sales_volume: number;
  };
  catalog: {
    total_products: number;
    total_ledgers: number;
    total_proformas: number;
  };
  chart_data: Array<{
    date: string;
    count: number;
    amount: number;
  }>;
  system: {
    status: string;
    django_version: string;
    server_time: string;
    environment: string;
  };
}

export default function SuperadminPortalPage() {
  const router = useRouter();
  const { toast } = useToast();

  const [activeTab, setActiveTab] = useState<"companies" | "users" | "audit" | "diagnostics">("companies");
  const [currentUser, setCurrentUser] = useState<any>(null);
  const [isAuthorized, setIsAuthorized] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Data states
  const [metrics, setMetrics] = useState<MetricsData | null>(null);
  const [companies, setCompanies] = useState<any[]>([]);
  const [companiesCount, setCompaniesCount] = useState(0);
  const [companySearch, setCompanySearch] = useState("");
  const [companyStatusFilter, setCompanyStatusFilter] = useState("all");

  const [users, setUsers] = useState<any[]>([]);
  const [usersCount, setUsersCount] = useState(0);
  const [userSearch, setUserSearch] = useState("");
  const [userStaffFilter, setUserStaffFilter] = useState("all");

  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // 1. Authenticate and check permissions
  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }

    const checkAdmin = async () => {
      try {
        const token = getAccessToken();
        const headers = { Authorization: `Bearer ${token}` };
        const meRes = await axios.get(`${API_BASE_URL}/api/v1/auth/me/`, { headers });
        const user = meRes.data?.data;
        setCurrentUser(user);

        if (user?.is_staff || user?.is_superuser) {
          setIsAuthorized(true);
        } else {
          setIsAuthorized(false);
        }
      } catch (err) {
        setIsAuthorized(false);
      } finally {
        setLoading(false);
      }
    };

    checkAdmin();
  }, [router]);

  // 2. Fetch metrics
  const fetchMetrics = useCallback(async () => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.get(`${API_BASE_URL}/api/v1/superadmin/metrics/`, { headers });
      if (res.data?.success) {
        setMetrics(res.data.data);
      }
    } catch (err) {
      console.error("Failed to load metrics", err);
    }
  }, []);

  // 3. Fetch companies
  const fetchCompanies = useCallback(async () => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      let url = `${API_BASE_URL}/api/v1/superadmin/companies/?limit=100`;
      if (companySearch.trim()) url += `&search=${encodeURIComponent(companySearch.trim())}`;
      if (companyStatusFilter !== "all") url += `&status=${companyStatusFilter}`;

      const res = await axios.get(url, { headers });
      if (res.data?.success) {
        setCompanies(res.data.data || []);
        setCompaniesCount(res.data.total_count || 0);
      }
    } catch (err) {
      console.error("Failed to load companies", err);
    }
  }, [companySearch, companyStatusFilter]);

  // 4. Fetch users
  const fetchUsers = useCallback(async () => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      let url = `${API_BASE_URL}/api/v1/superadmin/users/?limit=100`;
      if (userSearch.trim()) url += `&search=${encodeURIComponent(userSearch.trim())}`;
      if (userStaffFilter === "staff") url += `&is_staff=true`;
      else if (userStaffFilter === "non_staff") url += `&is_staff=false`;

      const res = await axios.get(url, { headers });
      if (res.data?.success) {
        setUsers(res.data.data || []);
        setUsersCount(res.data.total_count || 0);
      }
    } catch (err) {
      console.error("Failed to load users", err);
    }
  }, [userSearch, userStaffFilter]);

  // 5. Fetch audit logs
  const fetchAuditLogs = useCallback(async () => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.get(`${API_BASE_URL}/api/v1/superadmin/audit/?limit=50`, { headers });
      if (res.data?.success) {
        setAuditLogs(res.data.data || []);
      }
    } catch (err) {
      console.error("Failed to load audit logs", err);
    }
  }, []);

  // Load all initial data once authorized
  useEffect(() => {
    if (isAuthorized) {
      fetchMetrics();
      fetchCompanies();
      fetchUsers();
      fetchAuditLogs();
    }
  }, [isAuthorized, fetchMetrics, fetchCompanies, fetchUsers, fetchAuditLogs]);

  // Global manual refresh
  const handleRefresh = async () => {
    setRefreshing(true);
    await Promise.all([
      fetchMetrics(),
      fetchCompanies(),
      fetchUsers(),
      fetchAuditLogs()
    ]);
    setRefreshing(false);
    toast.success("Refreshed", "Platform metrics and directories updated.");
  };

  // Actions: Toggle Company Status
  const handleToggleCompanyStatus = async (compId: string) => {
    setActionLoading(`company-${compId}`);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.post(`${API_BASE_URL}/api/v1/superadmin/companies/${compId}/toggle-status/`, {}, { headers });
      if (res.data?.success) {
        toast.success("Status Updated", res.data.message);
        fetchCompanies();
        fetchMetrics();
      }
    } catch (err: any) {
      toast.error("Action Failed", err.response?.data?.error || err.message);
    } finally {
      setActionLoading(null);
    }
  };

  // Actions: Impersonate / Switch Workspace
  const handleImpersonateCompany = async (compId: string) => {
    setActionLoading(`impersonate-${compId}`);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.post(`${API_BASE_URL}/api/v1/superadmin/companies/${compId}/impersonate/`, {}, { headers });
      if (res.data?.success && res.data.company) {
        localStorage.setItem("vouch_active_company_id", res.data.company.id);
        toast.success("Workspace Switched", `Switched to ${res.data.company.name}`);
        router.push("/dashboard");
      }
    } catch (err: any) {
      toast.error("Switch Failed", err.response?.data?.error || err.message);
    } finally {
      setActionLoading(null);
    }
  };

  // Actions: Toggle User Staff
  const handleToggleUserStaff = async (userId: string) => {
    setActionLoading(`user-staff-${userId}`);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.post(`${API_BASE_URL}/api/v1/superadmin/users/${userId}/toggle-staff/`, {}, { headers });
      if (res.data?.success) {
        toast.success("Privilege Updated", res.data.message);
        fetchUsers();
        fetchMetrics();
      }
    } catch (err: any) {
      toast.error("Action Failed", err.response?.data?.error || err.message);
    } finally {
      setActionLoading(null);
    }
  };

  // Actions: Toggle User Active
  const handleToggleUserActive = async (userId: string) => {
    setActionLoading(`user-active-${userId}`);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.post(`${API_BASE_URL}/api/v1/superadmin/users/${userId}/toggle-active/`, {}, { headers });
      if (res.data?.success) {
        toast.success("Account Updated", res.data.message);
        fetchUsers();
        fetchMetrics();
      }
    } catch (err: any) {
      toast.error("Action Failed", err.response?.data?.error || err.message);
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex flex-col items-center justify-center min-h-[60vh] gap-3">
          <div className="w-8 h-8 border-3 border-primary border-t-transparent rounded-full animate-spin"></div>
          <p className="text-xs text-muted-foreground font-medium">Verifying superadmin credentials...</p>
        </div>
      </DashboardLayout>
    );
  }

  if (isAuthorized === false) {
    return (
      <DashboardLayout>
        <div className="max-w-md mx-auto my-16 p-8 bg-card border border-border rounded-2xl shadow-xl text-center space-y-4">
          <div className="w-12 h-12 rounded-full bg-rose-500/10 text-rose-500 flex items-center justify-center mx-auto border border-rose-500/20">
            <ShieldAlert className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-foreground">Access Restricted</h1>
            <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
              This area is reserved strictly for Vouch platform administrators and superusers.
              Your account <span className="font-mono text-foreground">{currentUser?.email}</span> does not have staff privileges.
            </p>
          </div>
          <Link
            href="/dashboard"
            className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-primary text-primary-foreground text-xs font-semibold rounded-xl hover:bg-primary/90 transition-colors shadow-xs"
          >
            <span>Return to Business Dashboard</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="max-w-7xl mx-auto space-y-6 pb-20">
        {/* Top Header */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-border pb-5">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <div className="px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 font-mono text-[10px] font-bold tracking-wider uppercase border border-amber-500/20 flex items-center gap-1.5">
                <ShieldCheck className="w-3 h-3 text-amber-500" />
                <span>Superadmin Command Center</span>
              </div>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
              <span className="text-[11px] font-mono text-emerald-600 dark:text-emerald-400 font-semibold">
                Telemetry Active
              </span>
            </div>
            <h1 className="text-2xl font-black text-foreground tracking-tight">
              Platform Administration
            </h1>
            <p className="text-xs text-muted-foreground">
              Fleet management across all companies, tenants, platform users, and transaction volumes.
            </p>
          </div>

          <div className="flex items-center gap-2.5 flex-wrap">
            <button
              type="button"
              onClick={handleRefresh}
              disabled={refreshing}
              className="px-3 py-2 bg-card hover:bg-muted text-foreground border border-border rounded-xl text-xs font-semibold transition-colors flex items-center gap-1.5 cursor-pointer shadow-2xs disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>

            <a
              href={`${API_BASE_URL}/admin/`}
              target="_blank"
              rel="noopener noreferrer"
              className="px-3 py-2 bg-muted hover:bg-muted/80 text-foreground border border-border rounded-xl text-xs font-semibold transition-colors flex items-center gap-1.5 cursor-pointer shadow-2xs"
            >
              <Database className="w-3.5 h-3.5 text-primary" />
              <span>Django Admin (/admin/)</span>
              <ExternalLink className="w-3 h-3 text-muted-foreground ml-0.5" />
            </a>

            <Link
              href="/dashboard"
              className="px-3.5 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl text-xs font-bold transition-all shadow-xs flex items-center gap-1.5 cursor-pointer"
            >
              <span>Back to ERP</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>

        {/* Top KPI Metrics Cards */}
        {metrics && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Total Companies */}
            <div className="bg-card border border-border rounded-2xl p-4 shadow-xs space-y-2">
              <div className="flex items-center justify-between text-muted-foreground text-xs">
                <span className="font-semibold uppercase tracking-wider text-[11px]">Tenants &amp; Companies</span>
                <Building2 className="w-4 h-4 text-blue-500" />
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-black text-foreground font-mono">
                  {metrics.companies.total}
                </span>
                <span className="text-[11px] text-emerald-600 dark:text-emerald-400 font-semibold font-mono">
                  {metrics.companies.active} active
                </span>
              </div>
              <div className="text-[11px] text-muted-foreground flex items-center justify-between pt-1 border-t border-border/40">
                <span>+ {metrics.companies.new_last_30_days} in last 30d</span>
                <span className="text-rose-500 font-mono">{metrics.companies.inactive} inactive</span>
              </div>
            </div>

            {/* Total Users */}
            <div className="bg-card border border-border rounded-2xl p-4 shadow-xs space-y-2">
              <div className="flex items-center justify-between text-muted-foreground text-xs">
                <span className="font-semibold uppercase tracking-wider text-[11px]">Platform Users</span>
                <Users className="w-4 h-4 text-purple-500" />
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-black text-foreground font-mono">
                  {metrics.users.total}
                </span>
                <span className="text-[11px] text-purple-600 dark:text-purple-400 font-semibold font-mono">
                  {metrics.users.staff} staff/admin
                </span>
              </div>
              <div className="text-[11px] text-muted-foreground flex items-center justify-between pt-1 border-t border-border/40">
                <span>+ {metrics.users.new_last_30_days} new users (30d)</span>
                <span className="text-emerald-500 font-mono">{metrics.users.active} active</span>
              </div>
            </div>

            {/* Total Vouchers */}
            <div className="bg-card border border-border rounded-2xl p-4 shadow-xs space-y-2">
              <div className="flex items-center justify-between text-muted-foreground text-xs">
                <span className="font-semibold uppercase tracking-wider text-[11px]">Vouchers / Records</span>
                <Receipt className="w-4 h-4 text-emerald-500" />
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-black text-foreground font-mono">
                  {metrics.vouchers.total}
                </span>
                <span className="text-[11px] text-blue-600 dark:text-blue-400 font-semibold font-mono">
                  {metrics.vouchers.sales} sales
                </span>
              </div>
              <div className="text-[11px] text-muted-foreground flex items-center justify-between pt-1 border-t border-border/40">
                <span>{metrics.vouchers.purchases} purchases</span>
                <span className="font-mono text-foreground font-semibold">+{metrics.vouchers.new_last_30_days} (30d)</span>
              </div>
            </div>

            {/* Platform Gross Volume */}
            <div className="bg-card border border-border rounded-2xl p-4 shadow-xs space-y-2">
              <div className="flex items-center justify-between text-muted-foreground text-xs">
                <span className="font-semibold uppercase tracking-wider text-[11px]">Gross Transaction Vol</span>
                <TrendingUp className="w-4 h-4 text-amber-500" />
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-black text-foreground font-mono">
                  ₹{metrics.vouchers.gross_volume >= 100000 
                    ? `${(metrics.vouchers.gross_volume / 100000).toFixed(2)}L`
                    : metrics.vouchers.gross_volume.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                </span>
                <span className="text-[10px] text-muted-foreground">across platform</span>
              </div>
              <div className="text-[11px] text-muted-foreground flex items-center justify-between pt-1 border-t border-border/40">
                <span>Sales: ₹{metrics.vouchers.sales_volume >= 100000 
                  ? `${(metrics.vouchers.sales_volume / 100000).toFixed(2)}L` 
                  : metrics.vouchers.sales_volume.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</span>
                <span className="text-emerald-500 font-semibold font-mono">100% Audit Safe</span>
              </div>
            </div>
          </div>
        )}

        {/* Tab Navigation */}
        <div className="flex items-center gap-1.5 border-b border-border text-xs font-bold">
          <button
            type="button"
            onClick={() => setActiveTab("companies")}
            className={`px-4 py-2.5 border-b-2 transition-all cursor-pointer flex items-center gap-2 ${
              activeTab === "companies"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <Building2 className="w-4 h-4" />
            <span>Companies Directory ({companiesCount})</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("users")}
            className={`px-4 py-2.5 border-b-2 transition-all cursor-pointer flex items-center gap-2 ${
              activeTab === "users"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <Users className="w-4 h-4" />
            <span>Platform Users ({usersCount})</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("audit")}
            className={`px-4 py-2.5 border-b-2 transition-all cursor-pointer flex items-center gap-2 ${
              activeTab === "audit"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <Activity className="w-4 h-4" />
            <span>System Audit Trail</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("diagnostics")}
            className={`px-4 py-2.5 border-b-2 transition-all cursor-pointer flex items-center gap-2 ${
              activeTab === "diagnostics"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <Zap className="w-4 h-4" />
            <span>Engine &amp; Telemetry</span>
          </button>
        </div>

        {/* TAB 1: COMPANIES DIRECTORY */}
        {activeTab === "companies" && (
          <div className="space-y-4">
            {/* Filter bar */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-card border border-border p-3 rounded-2xl shadow-2xs">
              <div className="relative w-full sm:w-80">
                <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Search company name, GSTIN, email..."
                  value={companySearch}
                  onChange={(e) => setCompanySearch(e.target.value)}
                  className="w-full pl-9 pr-3 py-1.5 bg-background border border-border rounded-xl text-xs text-foreground focus:outline-hidden"
                />
              </div>

              <div className="flex items-center gap-2 w-full sm:w-auto">
                <select
                  value={companyStatusFilter}
                  onChange={(e) => setCompanyStatusFilter(e.target.value)}
                  className="px-3 py-1.5 bg-background border border-border rounded-xl text-xs text-foreground focus:outline-hidden"
                >
                  <option value="all">All Statuses</option>
                  <option value="active">Active Only</option>
                  <option value="inactive">Suspended Only</option>
                </select>
              </div>
            </div>

            {/* Companies Table */}
            <div className="bg-card border border-border rounded-2xl overflow-hidden shadow-xs">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-muted/50 border-b border-border text-muted-foreground uppercase text-[10px] tracking-wider">
                    <tr>
                      <th className="p-3.5 font-bold">Company / Firm Name</th>
                      <th className="p-3.5 font-bold">GSTIN &amp; State</th>
                      <th className="p-3.5 font-bold">Owner / Contact</th>
                      <th className="p-3.5 font-bold text-center">Vouchers</th>
                      <th className="p-3.5 font-bold text-right">Sales Turnover</th>
                      <th className="p-3.5 font-bold text-center">Status</th>
                      <th className="p-3.5 font-bold text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {companies.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="p-8 text-center text-muted-foreground italic">
                          No companies found matching criteria.
                        </td>
                      </tr>
                    ) : (
                      companies.map((c) => (
                        <tr key={c.id} className="hover:bg-muted/30 transition-colors">
                          <td className="p-3.5">
                            <div className="font-bold text-foreground text-sm">{c.name}</div>
                            <div className="text-[11px] text-muted-foreground font-mono">
                              ID: {c.id.substring(0, 8)}... | {c.members_count} member{c.members_count > 1 ? "s" : ""} | {c.products_count} SKU{c.products_count > 1 ? "s" : ""}
                            </div>
                          </td>
                          <td className="p-3.5 font-mono">
                            <div className="font-semibold text-foreground">{c.gstin || "Unregistered"}</div>
                            <div className="text-[11px] text-muted-foreground">State Code: {c.state_code || "—"}</div>
                          </td>
                          <td className="p-3.5">
                            <div className="font-medium text-foreground">{c.owner?.name || c.email || "—"}</div>
                            <div className="text-[11px] text-muted-foreground font-mono">{c.owner?.email || c.phone || "—"}</div>
                          </td>
                          <td className="p-3.5 text-center font-mono font-bold text-foreground">
                            {c.vouchers_count}
                          </td>
                          <td className="p-3.5 text-right font-mono font-bold text-emerald-600 dark:text-emerald-400">
                            ₹{c.sales_volume.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                          </td>
                          <td className="p-3.5 text-center">
                            <span
                              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                c.is_active
                                  ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                                  : "bg-rose-500/10 text-rose-500 border border-rose-500/20"
                              }`}
                            >
                              {c.is_active ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                              <span>{c.is_active ? "Active" : "Suspended"}</span>
                            </span>
                          </td>
                          <td className="p-3.5 text-right whitespace-nowrap">
                            <div className="flex items-center justify-end gap-1.5">
                              {/* Impersonate Button */}
                              <button
                                type="button"
                                onClick={() => handleImpersonateCompany(c.id)}
                                disabled={actionLoading === `impersonate-${c.id}`}
                                className="px-2.5 py-1 bg-primary/10 hover:bg-primary/20 text-primary rounded-lg text-xs font-bold transition-colors flex items-center gap-1 cursor-pointer disabled:opacity-50"
                                title="Open this company's workspace directly"
                              >
                                <LogIn className="w-3 h-3" />
                                <span>Switch In</span>
                              </button>

                              {/* Toggle Active Button */}
                              <button
                                type="button"
                                onClick={() => handleToggleCompanyStatus(c.id)}
                                disabled={actionLoading === `company-${c.id}`}
                                className={`px-2 py-1 rounded-lg text-xs font-semibold border transition-colors cursor-pointer ${
                                  c.is_active
                                    ? "bg-rose-500/10 hover:bg-rose-500/20 text-rose-600 border-rose-500/20"
                                    : "bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-600 border-emerald-500/20"
                                }`}
                              >
                                {c.is_active ? "Suspend" : "Activate"}
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: PLATFORM USERS */}
        {activeTab === "users" && (
          <div className="space-y-4">
            {/* Filter bar */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-card border border-border p-3 rounded-2xl shadow-2xs">
              <div className="relative w-full sm:w-80">
                <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Search user email, name..."
                  value={userSearch}
                  onChange={(e) => setUserSearch(e.target.value)}
                  className="w-full pl-9 pr-3 py-1.5 bg-background border border-border rounded-xl text-xs text-foreground focus:outline-hidden"
                />
              </div>

              <div className="flex items-center gap-2 w-full sm:w-auto">
                <select
                  value={userStaffFilter}
                  onChange={(e) => setUserStaffFilter(e.target.value)}
                  className="px-3 py-1.5 bg-background border border-border rounded-xl text-xs text-foreground focus:outline-hidden"
                >
                  <option value="all">All Users</option>
                  <option value="staff">Staff / Superusers Only</option>
                  <option value="non_staff">Regular Users Only</option>
                </select>
              </div>
            </div>

            {/* Users Table */}
            <div className="bg-card border border-border rounded-2xl overflow-hidden shadow-xs">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-muted/50 border-b border-border text-muted-foreground uppercase text-[10px] tracking-wider">
                    <tr>
                      <th className="p-3.5 font-bold">User Identity</th>
                      <th className="p-3.5 font-bold">Privileges</th>
                      <th className="p-3.5 font-bold">Company Memberships</th>
                      <th className="p-3.5 font-bold">Joined Date</th>
                      <th className="p-3.5 font-bold text-center">Status</th>
                      <th className="p-3.5 font-bold text-right">Admin Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {users.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="p-8 text-center text-muted-foreground italic">
                          No users found matching criteria.
                        </td>
                      </tr>
                    ) : (
                      users.map((u) => (
                        <tr key={u.id} className="hover:bg-muted/30 transition-colors">
                          <td className="p-3.5">
                            <div className="font-bold text-foreground text-sm">{u.full_name}</div>
                            <div className="text-[11px] text-muted-foreground font-mono">{u.email}</div>
                          </td>
                          <td className="p-3.5">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              {u.is_superuser && (
                                <span className="px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400 font-bold text-[10px] border border-amber-500/30">
                                  SUPERUSER
                                </span>
                              )}
                              {u.is_staff && !u.is_superuser && (
                                <span className="px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-600 dark:text-blue-400 font-bold text-[10px] border border-blue-500/30">
                                  STAFF
                                </span>
                              )}
                              {!u.is_staff && !u.is_superuser && (
                                <span className="px-2 py-0.5 rounded-full bg-muted text-muted-foreground text-[10px] font-medium border border-border">
                                  {u.role || "User"}
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="p-3.5">
                            {u.companies.length === 0 ? (
                              <span className="text-muted-foreground italic text-[11px]">No affiliated firms</span>
                            ) : (
                              <div className="flex flex-col gap-1 max-w-xs">
                                {u.companies.map((c: any) => (
                                  <div key={c.id} className="text-[11px] truncate flex items-center gap-1">
                                    <span className="font-semibold text-foreground">{c.name}</span>
                                    <span className="text-[10px] text-muted-foreground font-mono">({c.role})</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </td>
                          <td className="p-3.5 font-mono text-muted-foreground text-[11px]">
                            {u.created_at ? new Date(u.created_at).toLocaleDateString("en-IN") : "—"}
                          </td>
                          <td className="p-3.5 text-center">
                            <span
                              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                u.is_active
                                  ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                                  : "bg-rose-500/10 text-rose-500 border border-rose-500/20"
                              }`}
                            >
                              {u.is_active ? "Active" : "Deactivated"}
                            </span>
                          </td>
                          <td className="p-3.5 text-right whitespace-nowrap">
                            <div className="flex items-center justify-end gap-1.5">
                              {/* Toggle Staff */}
                              <button
                                type="button"
                                onClick={() => handleToggleUserStaff(u.id)}
                                disabled={actionLoading === `user-staff-${u.id}`}
                                className={`px-2 py-1 rounded-lg text-xs font-semibold border transition-colors cursor-pointer ${
                                  u.is_staff
                                    ? "bg-amber-500/10 hover:bg-amber-500/20 text-amber-600 border-amber-500/20"
                                    : "bg-muted hover:bg-muted/80 text-foreground border-border"
                                }`}
                                title={u.is_staff ? "Revoke staff privileges" : "Grant staff privileges"}
                              >
                                {u.is_staff ? "Revoke Staff" : "Make Staff"}
                              </button>

                              {/* Toggle Active */}
                              <button
                                type="button"
                                onClick={() => handleToggleUserActive(u.id)}
                                disabled={actionLoading === `user-active-${u.id}`}
                                className={`px-2 py-1 rounded-lg text-xs font-semibold border transition-colors cursor-pointer ${
                                  u.is_active
                                    ? "bg-rose-500/10 hover:bg-rose-500/20 text-rose-600 border-rose-500/20"
                                    : "bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-600 border-emerald-500/20"
                                }`}
                              >
                                {u.is_active ? "Deactivate" : "Activate"}
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: SYSTEM AUDIT TRAIL */}
        {activeTab === "audit" && (
          <div className="space-y-4">
            <div className="bg-card border border-border rounded-2xl overflow-hidden shadow-xs">
              <div className="p-4 border-b border-border flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-foreground">Immutable Audit Trail</h3>
                  <p className="text-xs text-muted-foreground">Recent critical record changes across all tenants.</p>
                </div>
                <span className="text-xs font-mono text-muted-foreground">{auditLogs.length} events logged</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-muted/50 border-b border-border text-muted-foreground uppercase text-[10px] tracking-wider">
                    <tr>
                      <th className="p-3.5 font-bold">Timestamp</th>
                      <th className="p-3.5 font-bold">Action</th>
                      <th className="p-3.5 font-bold">Target Model</th>
                      <th className="p-3.5 font-bold">Tenant / Firm</th>
                      <th className="p-3.5 font-bold">User</th>
                      <th className="p-3.5 font-bold">Change Delta</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {auditLogs.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="p-8 text-center text-muted-foreground italic">
                          No audit log entries recorded yet.
                        </td>
                      </tr>
                    ) : (
                      auditLogs.map((log) => (
                        <tr key={log.id} className="hover:bg-muted/30 transition-colors">
                          <td className="p-3.5 font-mono text-muted-foreground text-[11px] whitespace-nowrap">
                            {log.timestamp ? new Date(log.timestamp).toLocaleString("en-IN") : "—"}
                          </td>
                          <td className="p-3.5">
                            <span className="px-2 py-0.5 rounded font-mono font-bold text-[10px] bg-primary/10 text-primary border border-primary/20">
                              {log.action}
                            </span>
                          </td>
                          <td className="p-3.5 font-mono font-semibold text-foreground">
                            {log.model_name}
                            <span className="text-[10px] text-muted-foreground block font-normal truncate max-w-xs">
                              ID: {log.record_id}
                            </span>
                          </td>
                          <td className="p-3.5 font-semibold text-foreground">
                            {log.company_name}
                          </td>
                          <td className="p-3.5 text-muted-foreground font-mono text-[11px]">
                            {log.user_email}
                          </td>
                          <td className="p-3.5 font-mono text-[10px] text-muted-foreground max-w-sm truncate">
                            {log.changes ? JSON.stringify(log.changes) : "—"}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: ENGINE & TELEMETRY */}
        {activeTab === "diagnostics" && metrics && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* 7-Day Activity Trend */}
            <div className="bg-card border border-border rounded-2xl p-5 shadow-xs space-y-4">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <div className="flex items-center gap-2">
                  <Activity className="w-4 h-4 text-primary" />
                  <h3 className="text-sm font-bold text-foreground">Last 7 Days Activity Trend</h3>
                </div>
                <span className="text-[11px] font-mono text-muted-foreground">Platform-wide</span>
              </div>

              <div className="space-y-3">
                {metrics.chart_data.map((day) => (
                  <div key={day.date} className="flex items-center justify-between text-xs p-2.5 rounded-xl bg-muted/30 border border-border/50">
                    <span className="font-mono font-semibold text-foreground w-20">{day.date}</span>
                    <span className="text-muted-foreground font-mono">{day.count} vouchers</span>
                    <span className="font-mono font-bold text-foreground">
                      ₹{day.amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* System Status & Direct Links */}
            <div className="space-y-6">
              <div className="bg-card border border-border rounded-2xl p-5 shadow-xs space-y-4">
                <div className="flex items-center gap-2 border-b border-border pb-3">
                  <Server className="w-4 h-4 text-emerald-500" />
                  <h3 className="text-sm font-bold text-foreground">System Health &amp; Diagnostics</h3>
                </div>

                <div className="space-y-2.5 text-xs font-mono divide-y divide-border/40">
                  <div className="flex justify-between pt-1">
                    <span className="text-muted-foreground font-sans">Database Status:</span>
                    <span className="text-emerald-600 dark:text-emerald-400 font-bold">CONNECTED &amp; HEALTHY</span>
                  </div>
                  <div className="flex justify-between pt-2">
                    <span className="text-muted-foreground font-sans">Django Engine:</span>
                    <span className="text-foreground">{metrics.system.django_version}</span>
                  </div>
                  <div className="flex justify-between pt-2">
                    <span className="text-muted-foreground font-sans">Server Environment:</span>
                    <span className="text-foreground uppercase">{metrics.system.environment}</span>
                  </div>
                  <div className="flex justify-between pt-2">
                    <span className="text-muted-foreground font-sans">Catalog SKUs:</span>
                    <span className="text-foreground">{metrics.catalog.total_products} items</span>
                  </div>
                  <div className="flex justify-between pt-2">
                    <span className="text-muted-foreground font-sans">Total Double-Entry Ledgers:</span>
                    <span className="text-foreground">{metrics.catalog.total_ledgers} ledgers</span>
                  </div>
                </div>
              </div>

              {/* Django Admin Direct Deep Links */}
              <div className="bg-card border border-border rounded-2xl p-5 shadow-xs space-y-3">
                <div className="flex items-center gap-2 border-b border-border pb-2">
                  <Database className="w-4 h-4 text-primary" />
                  <h3 className="text-sm font-bold text-foreground">Direct Database Admin Links</h3>
                </div>
                <p className="text-xs text-muted-foreground">
                  Access raw Django Admin tables for manual maintenance or raw database inspection.
                </p>

                <div className="grid grid-cols-2 gap-2 pt-1">
                  <a
                    href={`${API_BASE_URL}/admin/companies/company/`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-2.5 rounded-xl bg-muted/40 hover:bg-muted/80 text-foreground border border-border text-xs font-semibold flex items-center justify-between"
                  >
                    <span>Companies Admin</span>
                    <ExternalLink className="w-3 h-3 text-muted-foreground" />
                  </a>
                  <a
                    href={`${API_BASE_URL}/admin/accounts/user/`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-2.5 rounded-xl bg-muted/40 hover:bg-muted/80 text-foreground border border-border text-xs font-semibold flex items-center justify-between"
                  >
                    <span>Users Admin</span>
                    <ExternalLink className="w-3 h-3 text-muted-foreground" />
                  </a>
                  <a
                    href={`${API_BASE_URL}/admin/accounting/voucher/`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-2.5 rounded-xl bg-muted/40 hover:bg-muted/80 text-foreground border border-border text-xs font-semibold flex items-center justify-between"
                  >
                    <span>Vouchers Admin</span>
                    <ExternalLink className="w-3 h-3 text-muted-foreground" />
                  </a>
                  <a
                    href={`${API_BASE_URL}/admin/inventory/product/`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-2.5 rounded-xl bg-muted/40 hover:bg-muted/80 text-foreground border border-border text-xs font-semibold flex items-center justify-between"
                  >
                    <span>Products Admin</span>
                    <ExternalLink className="w-3 h-3 text-muted-foreground" />
                  </a>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
