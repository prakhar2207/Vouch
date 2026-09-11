"use client";

import React, { useEffect, useState, useRef, useMemo } from "react";
import axios from "axios";
import { useRouter } from "next/navigation";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import DashboardLayout from "@/components/DashboardLayout";
import { useToast } from "@/context/ToastContext";
import { useCompany } from "@/context/CompanyContext";
import {
  Landmark,
  UploadCloud,
  FileSpreadsheet,
  FileText,
  CheckCircle2,
  AlertCircle,
  Clock,
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
  Search,
  BookOpen,
  UserCheck,
  CreditCard,
  Building2,
  Trash2,
  X,
  ChevronRight,
  Sparkles,
  HelpCircle,
  EyeOff,
  Filter,
  Layers,
  Percent,
} from "lucide-react";

interface BankLedger {
  id: string;
  name: string;
  ledger_type: string;
  current_balance: number;
  bank_account_number?: string;
  bank_ifsc?: string;
  upi_id?: string;
}

interface BankTransactionItem {
  id: string;
  transaction_date: string;
  value_date?: string | null;
  description: string;
  normalized_narration: string;
  reference_number?: string;
  debit_amount: string;
  credit_amount: string;
  balance?: string | null;
  status: "UNRESOLVED" | "NEEDS_REVIEW" | "MATCHED" | "RECONCILED" | "IGNORED";
  bank_ledger: {
    id: string;
    name: string;
  };
  matched_party?: {
    id: string;
    name: string;
    ledger_type: string;
  } | null;
  matched_voucher?: {
    id: string;
    voucher_number: string;
  } | null;
  match_confidence: number;
  match_notes: string;
}

interface ReconciliationSummary {
  total_transactions: number;
  unresolved_count: number;
  needs_review_count: number;
  matched_count: number;
  reconciled_count: number;
  ignored_count: number;
  total_debits: string;
  total_credits: string;
  statement_closing_balance: string | null;
  book_closing_balance: string | null;
  reconciliation_gap: string | null;
  is_balanced: boolean;
}

interface PartyMappingItem {
  id: string;
  pattern: string;
  normalized_pattern: string;
  mapping_type: string;
  party: {
    id: string;
    name: string;
    ledger_type: string;
  };
  confirmed_by_user: boolean;
  confidence: number;
  usage_count: number;
  last_used: string;
}

export default function BankingPage() {
  const router = useRouter();
  const { toast } = useToast();

  const { activeCompany, companyId: activeCompanyId } = useCompany();
  const [companyId, setCompanyId] = useState<string>(activeCompanyId || "");
  const [bankLedgers, setBankLedgers] = useState<BankLedger[]>([]);
  const [selectedBankId, setSelectedBankId] = useState<string>("");
  const [allLedgers, setAllLedgers] = useState<any[]>([]);

  // Transactions & Summary State
  const [transactions, setTransactions] = useState<BankTransactionItem[]>([]);
  const [summary, setSummary] = useState<ReconciliationSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<"NEEDS_REVIEW" | "UNRESOLVED" | "MATCHED" | "ALL">("NEEDS_REVIEW");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Upload Modal State
  const [isUploadOpen, setIsUploadOpen] = useState<boolean>(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [uploadResult, setUploadResult] = useState<any | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Mappings Drawer State
  const [isMappingsOpen, setIsMappingsOpen] = useState<boolean>(false);
  const [mappings, setMappings] = useState<PartyMappingItem[]>([]);
  const [loadingMappings, setLoadingMappings] = useState<boolean>(false);

  // Action Modal State (for Match Party / Record Payment / Expense / Transfer)
  const [selectedTx, setSelectedTx] = useState<BankTransactionItem | null>(null);
  const [actionType, setActionType] = useState<"MATCH_PARTY" | "RECORD_PAYMENT" | "RECORD_EXPENSE" | "RECORD_TRANSFER" | "OWNER_DRAWING" | "IGNORE" | null>(null);
  const [actionTargetPartyId, setActionTargetPartyId] = useState<string>("");
  const [actionExpenseLedgerId, setActionExpenseLedgerId] = useState<string>("");
  const [actionTransferLedgerId, setActionTransferLedgerId] = useState<string>("");
  const [actionRemarks, setActionRemarks] = useState<string>("");
  const [actionLoading, setActionLoading] = useState<boolean>(false);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }
    initializeData();
  }, [router, activeCompanyId]);

  useEffect(() => {
    if (activeCompanyId && activeCompanyId !== companyId) {
      setCompanyId(activeCompanyId);
    }
  }, [activeCompanyId]);

  useEffect(() => {
    if (companyId) {
      fetchTransactionsAndSummary();
    }
  }, [companyId, selectedBankId, activeTab]);

  const getHeaders = () => {
    const token = getAccessToken();
    return {
      Authorization: `Bearer ${token}`,
      "X-Company-ID": companyId,
    };
  };

  const initializeData = async () => {
    setLoading(true);
    try {
      const token = getAccessToken();
      let cid = activeCompanyId;
      if (!cid && typeof window !== "undefined") {
        cid = localStorage.getItem("vouch_active_company_id");
      }
      if (!cid) {
        const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const list = Array.isArray(compRes.data) ? compRes.data : (compRes.data.data || []);
        cid = list[0]?.id;
      }
      if (!cid) {
        toast.error("No company found", "Please create or select an active company first.");
        setLoading(false);
        return;
      }
      setCompanyId(cid);

      const ledgersRes = await axios.get(`${API_BASE_URL}/api/v1/ledgers/${cid}/`, {
        headers: { Authorization: `Bearer ${token}`, "X-Company-ID": cid },
      });
      const rawLedgers: any[] = ledgersRes.data.data || [];
      setAllLedgers(rawLedgers);

      const banks = rawLedgers.filter(
        (l) => l.ledger_type === "BANK" || (l.group && l.group.toLowerCase().includes("bank"))
      );
      setBankLedgers(banks);

      if (banks.length > 0) {
        setSelectedBankId(banks[0].id);
      }
    } catch (err: any) {
      console.error(err);
      toast.error("Failed to load banking profile", err.message || "Network error");
    } finally {
      setLoading(false);
    }
  };

  const fetchTransactionsAndSummary = async () => {
    if (!companyId) return;
    setRefreshing(true);
    try {
      const headers = getHeaders();
      const params: any = { company_id: companyId };
      if (selectedBankId) {
        params.bank_ledger_id = selectedBankId;
      }

      if (activeTab === "NEEDS_REVIEW") {
        params.status = "NEEDS_REVIEW";
      } else if (activeTab === "UNRESOLVED") {
        params.status = "UNRESOLVED";
      } else if (activeTab === "MATCHED") {
        params.status = "MATCHED,RECONCILED";
      }

      const [txRes, summaryRes] = await Promise.all([
        axios.get(`${API_BASE_URL}/api/v1/accounting/banking/transactions/`, { headers, params }),
        axios.get(`${API_BASE_URL}/api/v1/accounting/banking/summary/`, {
          headers,
          params: { company_id: companyId, ...(selectedBankId ? { bank_ledger_id: selectedBankId } : {}) },
        }),
      ]);

      setTransactions(txRes.data.results || []);
      setSummary(summaryRes.data || null);
    } catch (err: any) {
      console.error(err);
      toast.error("Error loading bank transactions", err.message || "Could not fetch data.");
    } finally {
      setRefreshing(false);
    }
  };

  const fetchMappings = async () => {
    if (!companyId) return;
    setLoadingMappings(true);
    try {
      const headers = getHeaders();
      const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/banking/mappings/?company_id=${companyId}`, { headers });
      setMappings(res.data || []);
    } catch (err: any) {
      toast.error("Failed to load learned rules", err.message);
    } finally {
      setLoadingMappings(false);
    }
  };

  const deleteMapping = async (id: string) => {
    try {
      const headers = getHeaders();
      await axios.delete(`${API_BASE_URL}/api/v1/accounting/banking/mappings/${id}/`, { headers });
      toast.success("Rule removed", "The learned pattern has been forgotten.");
      fetchMappings();
    } catch (err: any) {
      toast.error("Failed to delete rule", err.message);
    }
  };

  const handleFileUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile) {
      toast.warning("Select statement", "Please select a CSV, Excel, or PDF bank statement.");
      return;
    }
    if (!selectedBankId) {
      toast.warning("Select bank account", "Please pick the target bank ledger.");
      return;
    }

    if (typeof window !== "undefined" && !navigator.onLine) {
      toast.error("Offline", "Internet connection required to upload and parse new bank statements.");
      return;
    }

    setIsUploading(true);
    try {
      const headers: Record<string, string> = { ...getHeaders() };
      const geminiKey = typeof window !== "undefined" ? localStorage.getItem("vouch_gemini_key") : null;
      if (geminiKey) {
        headers["X-Gemini-Key"] = geminiKey;
      }
      const formData = new FormData();
      formData.append("file", uploadFile);
      formData.append("bank_ledger_id", selectedBankId);
      formData.append("company_id", companyId);

      const res = await axios.post(`${API_BASE_URL}/api/v1/accounting/banking/upload/`, formData, {
        headers,
      });

      setUploadResult(res.data);
      if (res.data.is_duplicate_file) {
        toast.info(
          "Statement already imported",
          res.data.message || "This exact statement was already uploaded previously."
        );
      } else {
        toast.success(
          "Statement ingested successfully",
          `Parsed ${res.data.total_detected || res.data.total_rows} rows: ${res.data.auto_matched_count} verified matches, ${res.data.needs_review_count} suggestions.`
        );
      }
      fetchTransactionsAndSummary();
    } catch (err: any) {
      console.error(err);
      toast.error(
        "Upload failed",
        err.response?.data?.error || err.message || "Invalid or unparseable statement file."
      );
    } finally {
      setIsUploading(false);
    }
  };

  const openActionModal = (
    tx: BankTransactionItem,
    type: "MATCH_PARTY" | "RECORD_PAYMENT" | "RECORD_EXPENSE" | "RECORD_TRANSFER" | "OWNER_DRAWING" | "IGNORE"
  ) => {
    setSelectedTx(tx);
    setActionType(type);
    setActionRemarks("");
    if (tx.matched_party) {
      setActionTargetPartyId(tx.matched_party.id);
    } else {
      setActionTargetPartyId("");
    }
    setActionExpenseLedgerId("");
    setActionTransferLedgerId("");
  };

  const closeActionModal = () => {
    setSelectedTx(null);
    setActionType(null);
    setActionLoading(false);
  };

  const submitResolveAction = async () => {
    if (!selectedTx || !actionType) return;
    setActionLoading(true);

    try {
      const headers = getHeaders();
      const payload: any = {};

      if (actionType === "MATCH_PARTY") {
        if (!actionTargetPartyId) {
          toast.warning("Missing Party", "Please select a party ledger to match.");
          setActionLoading(false);
          return;
        }
        payload.party_id = actionTargetPartyId;
      } else if (actionType === "RECORD_PAYMENT") {
        if (!actionTargetPartyId) {
          toast.warning("Missing Party", "Select a customer or supplier party to record payment.");
          setActionLoading(false);
          return;
        }
        payload.party_id = actionTargetPartyId;
        payload.narration = actionRemarks || selectedTx.description;
      } else if (actionType === "RECORD_EXPENSE") {
        if (!actionExpenseLedgerId) {
          toast.warning("Missing Expense Ledger", "Select an expense ledger (e.g. Bank Charges, Rent, Utilities).");
          setActionLoading(false);
          return;
        }
        payload.expense_ledger_id = actionExpenseLedgerId;
        payload.narration = actionRemarks || selectedTx.description;
      } else if (actionType === "RECORD_TRANSFER") {
        if (!actionTransferLedgerId) {
          toast.warning("Missing Transfer Ledger", "Select the destination or source Bank/Cash account.");
          setActionLoading(false);
          return;
        }
        payload.transfer_ledger_id = actionTransferLedgerId;
        payload.narration = actionRemarks || selectedTx.description;
      } else if (actionType === "OWNER_DRAWING") {
        payload.narration = actionRemarks || "Proprietor / Partner Drawings";
      } else if (actionType === "IGNORE") {
        payload.reason = actionRemarks || "Ignored by user";
      }

      const res = await axios.post(
        `${API_BASE_URL}/api/v1/accounting/banking/transactions/${selectedTx.id}/resolve/`,
        { action: actionType, payload },
        { headers }
      );

      toast.success(
        "Transaction Resolved",
        res.data.voucher_number
          ? `Balanced Voucher ${res.data.voucher_number} created and applied to oldest unpaid invoices.`
          : res.data.message || "Updated successfully."
      );

      closeActionModal();
      fetchTransactionsAndSummary();
    } catch (err: any) {
      console.error(err);
      toast.error(
        "Resolution Failed",
        err.response?.data?.error || err.message || "Could not complete resolution action."
      );
    } finally {
      setActionLoading(false);
    }
  };

  const filteredTransactions = useMemo(() => {
    if (!searchQuery.trim()) return transactions;
    const q = searchQuery.toLowerCase();
    return transactions.filter(
      (tx) =>
        (tx.description ?? "").toLowerCase().includes(q) ||
        (tx.normalized_narration ?? "").toLowerCase().includes(q) ||
        ((tx.reference_number ?? "").toLowerCase().includes(q)) ||
        (tx.matched_party?.name ? tx.matched_party.name.toLowerCase().includes(q) : false)
    );
  }, [transactions, searchQuery]);

  const customerAndSupplierLedgers = useMemo(() => {
    return allLedgers.filter(
      (l) =>
        l.ledger_type === "CUSTOMER" ||
        l.ledger_type === "SUPPLIER" ||
        l.ledger_type === "BOTH" ||
        l.canonical_role === "CUSTOMER" ||
        l.canonical_role === "SUPPLIER" ||
        l.canonical_role === "BOTH"
    );
  }, [allLedgers]);

  const expenseLedgers = useMemo(() => {
    return allLedgers.filter(
      (l) =>
        l.ledger_type === "EXPENSE" ||
        l.nature === "EXPENSE" ||
        (l.group && l.group.toLowerCase().includes("expense"))
    );
  }, [allLedgers]);

  const contraLedgers = useMemo(() => {
    return allLedgers.filter(
      (l) =>
        (l.ledger_type === "BANK" || l.ledger_type === "CASH" || l.nature === "ASSET") &&
        l.id !== selectedBankId
    );
  }, [allLedgers, selectedBankId]);

  return (
    <DashboardLayout>
      <div className="space-y-6 pb-12">
        {/* Top Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-border/40 pb-5">
          <div>
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-xl bg-blue-500/10 text-blue-500">
                <Landmark className="w-5 h-5" />
              </div>
              <h1 className="text-xl sm:text-2xl font-extrabold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">
                Bank Intelligence & Reconciliation
              </h1>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Ingest statements, multi-signal party learning, and continuous audit reconciliation without manual data entry.
            </p>
          </div>

          <div className="flex items-center gap-2.5 flex-wrap">
            <button
              onClick={() => {
                fetchMappings();
                setIsMappingsOpen(true);
              }}
              className="px-3.5 py-2 rounded-xl border border-border/60 bg-card hover:bg-muted text-foreground text-xs font-semibold flex items-center gap-2 cursor-pointer shadow-2xs transition-all"
            >
              <BookOpen className="w-3.5 h-3.5 text-indigo-400" />
              <span>Learned Rules ({mappings.length})</span>
            </button>

            <button
              onClick={() => {
                setUploadFile(null);
                setUploadResult(null);
                setIsUploadOpen(true);
              }}
              className="px-4 py-2 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-bold flex items-center gap-2 cursor-pointer shadow-md shadow-primary/20 transition-all"
            >
              <UploadCloud className="w-4 h-4" />
              <span>Upload Statement</span>
            </button>

            <button
              onClick={fetchTransactionsAndSummary}
              disabled={refreshing}
              className="p-2 rounded-xl border border-border/60 bg-card hover:bg-muted text-muted-foreground hover:text-foreground cursor-pointer transition-colors"
              title="Refresh Transactions"
            >
              <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin text-primary" : ""}`} />
            </button>
          </div>
        </div>

        {/* Bank Account Selector & Status Bar */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="bg-card border border-border/40 rounded-2xl p-5 shadow-sm space-y-4">
            <div className="flex items-center justify-between">
              <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
                Select Bank Account
              </label>
              <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
                {bankLedgers.length} Accounts
              </span>
            </div>

            <select
              value={selectedBankId}
              onChange={(e) => setSelectedBankId(e.target.value)}
              className="w-full bg-muted/40 border border-border/60 rounded-xl px-3.5 py-2.5 text-sm font-semibold text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 cursor-pointer"
            >
              {bankLedgers.map((bank) => (
                <option key={bank.id} value={bank.id} className="bg-card text-foreground">
                  {bank.name} {bank.bank_account_number ? `(A/c: ...${bank.bank_account_number.slice(-4)})` : ""}
                </option>
              ))}
            </select>

            {bankLedgers.find((b) => b.id === selectedBankId) && (
              <div className="text-xs space-y-1 text-muted-foreground bg-muted/20 p-3 rounded-xl border border-border/30 font-mono">
                <div>IFSC: {bankLedgers.find((b) => b.id === selectedBankId)?.bank_ifsc || "Not Set"}</div>
                <div>UPI: {bankLedgers.find((b) => b.id === selectedBankId)?.upi_id || "Not Set"}</div>
              </div>
            )}
          </div>

          {/* Balance Comparison & Gap Card */}
          <div className="bg-card border border-border/40 rounded-2xl p-5 shadow-sm flex flex-col justify-between space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
                Book vs Bank Equilibrium
              </span>
              {summary?.is_balanced ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  In Sync
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                  <AlertCircle className="w-3.5 h-3.5" />
                  Gap: ₹{parseFloat(summary?.reconciliation_gap || "0").toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </span>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 bg-muted/30 rounded-xl border border-border/30">
                <div className="text-[11px] text-muted-foreground">Book Balance</div>
                <div className="text-base sm:text-lg font-bold font-mono tabular-nums text-foreground">
                  ₹{parseFloat(summary?.book_closing_balance || "0").toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div className="p-3 bg-muted/30 rounded-xl border border-border/30">
                <div className="text-[11px] text-muted-foreground">Statement Balance</div>
                <div className="text-base sm:text-lg font-bold font-mono tabular-nums text-foreground">
                  ₹{parseFloat(summary?.statement_closing_balance || "0").toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
              </div>
            </div>

            <p className="text-[11px] text-muted-foreground">
              {summary?.unresolved_count || 0} unresolved items awaiting classification to reach zero gap.
            </p>
          </div>

          {/* Quick Stats Grid */}
          <div className="bg-card border border-border/40 rounded-2xl p-5 shadow-sm grid grid-cols-2 gap-3">
            <div className="p-3 bg-amber-500/5 rounded-xl border border-amber-500/20 space-y-1">
              <div className="text-[11px] font-semibold text-amber-500 flex items-center gap-1">
                <Sparkles className="w-3 h-3" />
                Needs Review
              </div>
              <div className="text-2xl font-black font-mono text-foreground">
                {summary?.needs_review_count || 0}
              </div>
              <div className="text-[10px] text-muted-foreground">AI match candidate</div>
            </div>

            <div className="p-3 bg-rose-500/5 rounded-xl border border-rose-500/20 space-y-1">
              <div className="text-[11px] font-semibold text-rose-500 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                Unresolved
              </div>
              <div className="text-2xl font-black font-mono text-foreground">
                {summary?.unresolved_count || 0}
              </div>
              <div className="text-[10px] text-muted-foreground">Requires attention</div>
            </div>

            <div className="p-3 bg-emerald-500/5 rounded-xl border border-emerald-500/20 space-y-1">
              <div className="text-[11px] font-semibold text-emerald-500 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" />
                Auto-Matched
              </div>
              <div className="text-2xl font-black font-mono text-foreground">
                {(summary?.matched_count || 0) + (summary?.reconciled_count || 0)}
              </div>
              <div className="text-[10px] text-muted-foreground">Verified & reconciled</div>
            </div>

            <div className="p-3 bg-muted/40 rounded-xl border border-border/40 space-y-1">
              <div className="text-[11px] font-semibold text-muted-foreground flex items-center gap-1">
                <Layers className="w-3 h-3" />
                Total Entries
              </div>
              <div className="text-2xl font-black font-mono text-foreground">
                {summary?.total_transactions || 0}
              </div>
              <div className="text-[10px] text-muted-foreground">Ingested rows</div>
            </div>
          </div>
        </div>

        {/* Filter Tabs & Search Bar */}
        <div className="flex flex-col sm:flex-row justify-between items-stretch sm:items-center gap-3">
          <div className="flex items-center gap-1 p-1 bg-muted/40 border border-border/40 rounded-xl">
            <button
              onClick={() => setActiveTab("NEEDS_REVIEW")}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                activeTab === "NEEDS_REVIEW"
                  ? "bg-card text-foreground shadow-sm border border-border/60"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <span>Needs Review</span>
              {(summary?.needs_review_count || 0) > 0 && (
                <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono font-bold bg-amber-500/20 text-amber-500">
                  {summary?.needs_review_count}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab("UNRESOLVED")}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                activeTab === "UNRESOLVED"
                  ? "bg-card text-foreground shadow-sm border border-border/60"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <span>Unresolved</span>
              {(summary?.unresolved_count || 0) > 0 && (
                <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono font-bold bg-rose-500/20 text-rose-500">
                  {summary?.unresolved_count}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab("MATCHED")}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                activeTab === "MATCHED"
                  ? "bg-card text-foreground shadow-sm border border-border/60"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Matched & Reconciled
            </button>

            <button
              onClick={() => setActiveTab("ALL")}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                activeTab === "ALL"
                  ? "bg-card text-foreground shadow-sm border border-border/60"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              All Ingested
            </button>
          </div>

          <div className="relative min-w-[260px]">
            <Search className="w-4 h-4 text-muted-foreground absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search narration, ref #, or party..."
              className="w-full bg-card border border-border/60 rounded-xl pl-10 pr-4 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
          </div>
        </div>

        {/* Transactions Card List */}
        {loading ? (
          <div className="flex flex-col items-center justify-center p-16 space-y-3">
            <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
            <p className="text-xs text-muted-foreground">Loading bank intelligence feed...</p>
          </div>
        ) : filteredTransactions.length === 0 ? (
          <div className="bg-card border border-border/40 rounded-2xl p-12 text-center space-y-3 shadow-sm">
            <div className="w-12 h-12 rounded-full bg-muted/60 text-muted-foreground flex items-center justify-center mx-auto">
              <CheckCircle2 className="w-6 h-6 text-emerald-500" />
            </div>
            <h3 className="text-base font-bold text-foreground">No Transactions In This Category</h3>
            <p className="text-xs text-muted-foreground max-w-sm mx-auto">
              {activeTab === "NEEDS_REVIEW"
                ? "No pending AI suggestions. Upload another bank statement or view all transactions."
                : "No matching records found for current filters."}
            </p>
            <button
              onClick={() => setIsUploadOpen(true)}
              className="px-4 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:bg-primary/90 transition-all cursor-pointer inline-flex items-center gap-2"
            >
              <UploadCloud className="w-4 h-4" />
              <span>Upload Statement Now</span>
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredTransactions.map((tx) => {
              const isCredit = parseFloat(tx.credit_amount) > 0;
              const amountVal = isCredit ? parseFloat(tx.credit_amount) : parseFloat(tx.debit_amount);

              return (
                <div
                  key={tx.id}
                  className="bg-card border border-border/40 hover:border-border/80 transition-all rounded-2xl p-4 sm:p-5 shadow-sm space-y-3"
                >
                  <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                    <div className="flex items-start gap-3">
                      <div
                        className={`p-2.5 rounded-xl shrink-0 mt-0.5 ${
                          isCredit ? "bg-emerald-500/10 text-emerald-500" : "bg-rose-500/10 text-rose-500"
                        }`}
                      >
                        {isCredit ? <ArrowDownRight className="w-5 h-5" /> : <ArrowUpRight className="w-5 h-5" />}
                      </div>

                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-mono text-xs font-bold text-muted-foreground">
                            {tx.transaction_date}
                          </span>
                          {tx.reference_number && (
                            <span className="font-mono text-[10px] px-2 py-0.5 bg-muted/60 text-muted-foreground rounded border border-border/40">
                              Ref: {tx.reference_number}
                            </span>
                          )}
                          <span
                            className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider ${
                              tx.status === "MATCHED" || tx.status === "RECONCILED"
                                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                                : tx.status === "NEEDS_REVIEW"
                                ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                                : tx.status === "IGNORED"
                                ? "bg-muted text-muted-foreground border border-border/50"
                                : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                            }`}
                          >
                            {tx.status.replace("_", " ")}
                          </span>
                        </div>

                        <div className="text-sm font-bold text-foreground leading-snug">
                          {tx.description}
                        </div>

                        <div className="text-[11px] text-muted-foreground font-mono">
                          Normalized: {tx.normalized_narration}
                        </div>
                      </div>
                    </div>

                    <div className="text-right shrink-0 sm:self-center">
                      <div
                        className={`text-lg sm:text-xl font-black font-mono tabular-nums ${
                          isCredit ? "text-emerald-500" : "text-rose-500"
                        }`}
                      >
                        {isCredit ? "+" : "-"}₹{amountVal.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </div>
                      {tx.balance && (
                        <div className="text-[11px] text-muted-foreground font-mono">
                          Bal: ₹{parseFloat(tx.balance).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* AI Suggestion Card if match found */}
                  {tx.matched_party && (
                    <div className="bg-muted/30 border border-border/50 rounded-xl p-3 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                      <div className="flex items-center gap-2.5">
                        <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400">
                          <Sparkles className="w-4 h-4" />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-bold text-foreground">
                              Suggested Party: {tx.matched_party.name}
                            </span>
                            <span
                              className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-full border ${
                                tx.match_confidence >= 80
                                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                                  : tx.match_confidence >= 50
                                  ? "bg-amber-500/10 text-amber-400 border-amber-500/30"
                                  : "bg-muted text-muted-foreground border-border"
                              }`}
                            >
                              {tx.match_confidence >= 80 ? "Verified Match" : tx.match_confidence >= 50 ? "Suggested Match" : "Needs Review"}
                            </span>
                          </div>
                          <p className="text-[11px] text-muted-foreground">{tx.match_notes}</p>
                        </div>
                      </div>

                      {tx.status !== "MATCHED" && tx.status !== "RECONCILED" && (
                        <div className="flex items-center gap-2 w-full sm:w-auto">
                          <button
                            onClick={() => openActionModal(tx, "RECORD_PAYMENT")}
                            className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-bold transition-colors cursor-pointer w-full sm:w-auto text-center"
                          >
                            {isCredit ? "Record Receipt" : "Record Payment"}
                          </button>
                          <button
                            onClick={() => openActionModal(tx, "MATCH_PARTY")}
                            className="px-2.5 py-1.5 rounded-lg border border-border/60 hover:bg-card text-foreground text-xs font-semibold cursor-pointer"
                          >
                            Confirm Match
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Reconciled Voucher Link if resolved */}
                  {tx.matched_voucher && (
                    <div className="text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-3 py-1.5 rounded-lg flex items-center justify-between font-mono">
                      <span>✓ Reconciled to Voucher: {tx.matched_voucher.voucher_number}</span>
                      <button
                        onClick={() => router.push(`/vouchers`)}
                        className="hover:underline text-[11px] cursor-pointer"
                      >
                        View Voucher →
                      </button>
                    </div>
                  )}

                  {/* Quick Action Toolbar (Unresolved / Review) */}
                  {tx.status !== "MATCHED" && tx.status !== "RECONCILED" && (
                    <div className="flex items-center gap-2 pt-2 border-t border-border/30 flex-wrap">
                      <span className="text-[11px] font-bold text-muted-foreground mr-1">Actions:</span>

                      <button
                        onClick={() => openActionModal(tx, "MATCH_PARTY")}
                        className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-muted hover:bg-muted/80 text-foreground border border-border/40 transition-colors cursor-pointer"
                      >
                        Match Party
                      </button>

                      <button
                        onClick={() => openActionModal(tx, "RECORD_PAYMENT")}
                        className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-muted hover:bg-muted/80 text-foreground border border-border/40 transition-colors cursor-pointer"
                      >
                        {isCredit ? "Customer Receipt" : "Supplier Payment"}
                      </button>

                      {!isCredit && (
                        <button
                          onClick={() => openActionModal(tx, "RECORD_EXPENSE")}
                          className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-muted hover:bg-muted/80 text-foreground border border-border/40 transition-colors cursor-pointer"
                        >
                          Record Expense
                        </button>
                      )}

                      <button
                        onClick={() => openActionModal(tx, "RECORD_TRANSFER")}
                        className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-muted hover:bg-muted/80 text-foreground border border-border/40 transition-colors cursor-pointer"
                      >
                        Transfer / Contra
                      </button>

                      {!isCredit && (
                        <button
                          onClick={() => openActionModal(tx, "OWNER_DRAWING")}
                          className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-muted hover:bg-muted/80 text-foreground border border-border/40 transition-colors cursor-pointer"
                        >
                          Owner Drawing
                        </button>
                      )}

                      <button
                        onClick={() => openActionModal(tx, "IGNORE")}
                        className="px-2.5 py-1 rounded-lg text-xs font-semibold text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer ml-auto"
                      >
                        Ignore
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* UPLOAD STATEMENT MODAL */}
        {isUploadOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
            <div
              className="bg-card border border-border rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden animate-in zoom-in-95 duration-200"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between p-5 border-b border-border">
                <div className="flex items-center gap-2">
                  <div className="p-2 rounded-xl bg-primary/10 text-primary">
                    <FileSpreadsheet className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-foreground">Upload Bank Statement</h3>
                    <p className="text-xs text-muted-foreground">CSV, Excel (.xlsx, .xls), or PDF statements</p>
                  </div>
                </div>
                <button
                  onClick={() => setIsUploadOpen(false)}
                  className="text-muted-foreground hover:text-foreground p-1 rounded-lg cursor-pointer"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <form onSubmit={handleFileUpload} className="p-5 space-y-4">
                <div>
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider block mb-1.5">
                    Target Bank Ledger
                  </label>
                  <select
                    value={selectedBankId}
                    onChange={(e) => setSelectedBankId(e.target.value)}
                    className="w-full bg-muted/40 border border-border/60 rounded-xl px-3 py-2.5 text-xs font-semibold text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 cursor-pointer"
                  >
                    {bankLedgers.map((bank) => (
                      <option key={bank.id} value={bank.id}>
                        {bank.name} {bank.bank_account_number ? `(${bank.bank_account_number})` : ""}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Drag and Drop Zone */}
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="border-2 border-dashed border-border/80 hover:border-primary/60 transition-all rounded-2xl p-6 text-center cursor-pointer bg-muted/20 hover:bg-muted/40 space-y-2"
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv,.xlsx,.xls,.pdf,image/png,image/jpeg"
                    className="hidden"
                    onChange={(e) => {
                      if (e.target.files && e.target.files[0]) {
                        setUploadFile(e.target.files[0]);
                      }
                    }}
                  />
                  <div className="w-12 h-12 rounded-full bg-primary/10 text-primary flex items-center justify-center mx-auto">
                    <UploadCloud className="w-6 h-6" />
                  </div>
                  <div className="text-xs font-bold text-foreground">
                    {uploadFile ? uploadFile.name : "Click or drag bank statement file here"}
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    Supports HDFC, ICICI, SBI, Axis, Kotak CSV/Excel & scanned statements
                  </div>
                </div>

                {/* Upload Feedback */}
                {uploadResult && (
                  <div className={`p-3.5 rounded-xl border text-xs space-y-1.5 text-foreground ${
                    uploadResult.is_duplicate_file
                      ? "bg-blue-500/10 border-blue-500/30"
                      : uploadResult.balance_chain_valid
                      ? "bg-emerald-500/10 border-emerald-500/20"
                      : "bg-amber-500/10 border-amber-500/30"
                  }`}>
                    <div className="font-bold flex items-center justify-between">
                      <span className={uploadResult.is_duplicate_file ? "text-blue-400" : uploadResult.balance_chain_valid ? "text-emerald-400" : "text-amber-400"}>
                        {uploadResult.is_duplicate_file ? "Duplicate Statement Detected" : "Statement Ingestion Summary"}
                      </span>
                      {uploadResult.balance_chain_valid ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400">
                          ✓ Balance Chain Verified
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-400">
                          ⚠️ Balance Discrepancy (₹{uploadResult.discrepancy_amount?.toFixed(2)})
                        </span>
                      )}
                    </div>
                    {uploadResult.message && (
                      <div className="text-[11px] text-muted-foreground">{uploadResult.message}</div>
                    )}
                    <div>• Total detected rows: {uploadResult.total_detected || uploadResult.total_rows}</div>
                    <div>• Verified automatic matches: {uploadResult.auto_matched_count}</div>
                    <div>• Suggestions for review: {uploadResult.needs_review_count}</div>
                    <div>• Duplicates skipped: {uploadResult.duplicates_detected ?? uploadResult.duplicate_count ?? 0}</div>
                  </div>
                )}

                <div className="flex items-center gap-3 pt-2">
                  <button
                    type="button"
                    onClick={() => setIsUploadOpen(false)}
                    className="flex-1 py-2.5 rounded-xl text-xs font-bold text-muted-foreground hover:text-foreground bg-muted hover:bg-muted/80 transition-colors cursor-pointer"
                  >
                    Close
                  </button>
                  <button
                    type="submit"
                    disabled={isUploading || !uploadFile}
                    className="flex-1 py-2.5 rounded-xl text-xs font-bold text-primary-foreground bg-primary hover:bg-primary/90 transition-all cursor-pointer flex items-center justify-center gap-2 disabled:opacity-50"
                  >
                    {isUploading ? (
                      <>
                        <div className="w-4 h-4 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin"></div>
                        <span>Parsing Statement...</span>
                      </>
                    ) : (
                      <span>Upload & Ingest</span>
                    )}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* LEARNED MAPPINGS DRAWER */}
        {isMappingsOpen && (
          <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
            <div
              className="bg-card border-l border-border w-full max-w-md h-full flex flex-col p-6 shadow-2xl animate-in slide-in-from-right duration-200"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between pb-4 border-b border-border">
                <div className="flex items-center gap-2">
                  <BookOpen className="w-5 h-5 text-indigo-400" />
                  <div>
                    <h3 className="text-base font-bold text-foreground">Learned Party Rules</h3>
                    <p className="text-xs text-muted-foreground">Isolated to your company</p>
                  </div>
                </div>
                <button
                  onClick={() => setIsMappingsOpen(false)}
                  className="text-muted-foreground hover:text-foreground p-1 rounded-lg cursor-pointer"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto py-4 space-y-3">
                {loadingMappings ? (
                  <div className="flex items-center justify-center p-8">
                    <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
                  </div>
                ) : mappings.length === 0 ? (
                  <div className="text-center p-8 space-y-2 text-muted-foreground">
                    <p className="text-xs">No learned rules yet.</p>
                    <p className="text-[11px]">
                      When you match a party in bank reconciliation, Vouch remembers the UPI ID, IFSC, or narration pattern automatically.
                    </p>
                  </div>
                ) : (
                  mappings.map((m) => (
                    <div
                      key={m.id}
                      className="p-3 rounded-xl bg-muted/30 border border-border/40 space-y-1.5 relative group"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-foreground">{m.party.name}</span>
                        <button
                          onClick={() => deleteMapping(m.id)}
                          className="text-muted-foreground hover:text-rose-400 p-1 cursor-pointer transition-colors"
                          title="Delete learned rule"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>

                      <div className="text-[11px] font-mono text-muted-foreground break-all">
                        Pattern: {m.pattern}
                      </div>

                      <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                        <span className="px-1.5 py-0.2 rounded bg-muted font-mono">{m.mapping_type}</span>
                        <span>Used {m.usage_count} times</span>
                        <span className="text-emerald-400 font-bold">{m.confidence}% confidence</span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}

        {/* TRANSACTION ACTION MODAL (Match / Payment / Expense / Transfer / Drawing) */}
        {selectedTx && actionType && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
            <div
              className="bg-card border border-border rounded-2xl shadow-2xl w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="p-5 border-b border-border">
                <div className="flex items-center justify-between">
                  <h3 className="text-base font-bold text-foreground">
                    {actionType === "MATCH_PARTY" && "Match Party & Learn Rule"}
                    {actionType === "RECORD_PAYMENT" &&
                      (parseFloat(selectedTx.credit_amount) > 0 ? "Record Customer Receipt" : "Record Supplier Payment")}
                    {actionType === "RECORD_EXPENSE" && "Record Bank Expense"}
                    {actionType === "RECORD_TRANSFER" && "Contra Transfer (Bank / Cash)"}
                    {actionType === "OWNER_DRAWING" && "Record Owner Drawing"}
                    {actionType === "IGNORE" && "Ignore Transaction"}
                  </h3>
                  <button
                    onClick={closeActionModal}
                    className="text-muted-foreground hover:text-foreground p-1 rounded-lg cursor-pointer"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
                <p className="text-xs text-muted-foreground mt-1 line-clamp-1">{selectedTx.description}</p>
              </div>

              <div className="p-5 space-y-4">
                {/* Party Selection for Match Party / Payment */}
                {(actionType === "MATCH_PARTY" || actionType === "RECORD_PAYMENT") && (
                  <div>
                    <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider block mb-1.5">
                      Select Party
                    </label>
                    <select
                      value={actionTargetPartyId}
                      onChange={(e) => setActionTargetPartyId(e.target.value)}
                      className="w-full bg-muted/40 border border-border/60 rounded-xl px-3 py-2.5 text-xs font-semibold text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 cursor-pointer"
                    >
                      <option value="">-- Choose Party --</option>
                      {customerAndSupplierLedgers.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name} ({p.ledger_type}) • Bal: ₹{p.current_balance}
                        </option>
                      ))}
                    </select>
                    {actionType === "RECORD_PAYMENT" && (
                      <p className="text-[11px] text-muted-foreground mt-1.5">
                        Payment will be automatically applied to the oldest unpaid invoices.
                      </p>
                    )}
                  </div>
                )}

                {/* Expense Ledger Selector */}
                {actionType === "RECORD_EXPENSE" && (
                  <div>
                    <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider block mb-1.5">
                      Select Expense Ledger
                    </label>
                    <select
                      value={actionExpenseLedgerId}
                      onChange={(e) => setActionExpenseLedgerId(e.target.value)}
                      className="w-full bg-muted/40 border border-border/60 rounded-xl px-3 py-2.5 text-xs font-semibold text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 cursor-pointer"
                    >
                      <option value="">-- Choose Expense Account --</option>
                      {expenseLedgers.map((exp) => (
                        <option key={exp.id} value={exp.id}>
                          {exp.name} ({exp.group || "Expense"})
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {/* Transfer Ledger Selector */}
                {actionType === "RECORD_TRANSFER" && (
                  <div>
                    <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider block mb-1.5">
                      Transfer Account (Bank / Cash)
                    </label>
                    <select
                      value={actionTransferLedgerId}
                      onChange={(e) => setActionTransferLedgerId(e.target.value)}
                      className="w-full bg-muted/40 border border-border/60 rounded-xl px-3 py-2.5 text-xs font-semibold text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 cursor-pointer"
                    >
                      <option value="">-- Choose Target/Source Ledger --</option>
                      {contraLedgers.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name} ({c.ledger_type})
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {/* Remarks / Narration */}
                <div>
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider block mb-1.5">
                    {actionType === "IGNORE" ? "Reason for Ignoring" : "Remarks / Narration"}
                  </label>
                  <input
                    type="text"
                    value={actionRemarks}
                    onChange={(e) => setActionRemarks(e.target.value)}
                    placeholder={
                      actionType === "IGNORE"
                        ? "e.g. Personal transfer, reversal duplicate"
                        : "Optional remarks for accounting ledger"
                    }
                    className="w-full bg-muted/40 border border-border/60 rounded-xl px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                  />
                </div>

                <div className="flex items-center gap-3 pt-2">
                  <button
                    onClick={closeActionModal}
                    className="flex-1 py-2.5 rounded-xl text-xs font-bold text-muted-foreground hover:text-foreground bg-muted hover:bg-muted/80 transition-colors cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={submitResolveAction}
                    disabled={actionLoading}
                    className="flex-1 py-2.5 rounded-xl text-xs font-bold text-primary-foreground bg-primary hover:bg-primary/90 transition-all cursor-pointer flex items-center justify-center gap-2 disabled:opacity-50"
                  >
                    {actionLoading ? (
                      <>
                        <div className="w-4 h-4 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin"></div>
                        <span>Processing...</span>
                      </>
                    ) : (
                      <span>Confirm & Reconcile</span>
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
