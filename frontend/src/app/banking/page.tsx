"use client";

import React, { useEffect, useState, useRef, useMemo } from "react";
import axios from "axios";
import { useRouter } from "next/navigation";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import DashboardLayout from "@/components/DashboardLayout";
import { useToast } from "@/context/ToastContext";
import { useCompany } from "@/context/CompanyContext";
import ConfirmModal from "@/components/modals/ConfirmModal";
import SearchableSelect, { SearchableOption } from "@/components/SearchableSelect";
import { bankTransactionsRepository, ledgersRepository } from "@/lib/data";
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
  ledgerType?: string;
  current_balance: number;
  currentBalance?: number;
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
  status: "UNRESOLVED" | "NEEDS_REVIEW" | "MATCHED" | "RECONCILED" | "IGNORED" | "MATCHED_AUTO" | "MATCHED_SUGGESTED" | "EXCLUDED";
  is_excluded?: boolean;
  exclusion_reason?: string | null;
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
  match_notes?: string | { signals?: string[]; ignore_reason?: string; reason?: string; [key: string]: any } | null;
}

interface ReconciliationSummary {
  total_transactions: number;
  unresolved_count: number;
  needs_review_count: number;
  matched_count: number;
  reconciled_count: number;
  ignored_count: number;
  excluded_count: number;
  total_debits: string;
  total_credits: string;
  statement_closing_balance: string | null;
  book_closing_balance: string | null;
  reconciliation_gap: string | null;
  is_balanced: boolean;
  statement_cutoff_date?: string | null;
  reconciliation_state?: string;
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

const isValidId = (id: unknown): id is string =>
  typeof id === "string" && id.trim() !== "" && id !== "undefined" && id !== "null";

export default function BankingPage() {
  const router = useRouter();
  const { toast } = useToast();

  const { activeCompany, companyId: activeCompanyId } = useCompany();
  const [companyId, setCompanyId] = useState<string>(isValidId(activeCompanyId) ? activeCompanyId : "");
  const [bankLedgers, setBankLedgers] = useState<BankLedger[]>([]);
  const [selectedBankId, setSelectedBankId] = useState<string>("");
  const [allLedgers, setAllLedgers] = useState<any[]>([]);

  // Transactions & Summary State
  const [transactions, setTransactions] = useState<BankTransactionItem[]>([]);
  const [summary, setSummary] = useState<ReconciliationSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<"NEEDS_REVIEW" | "UNRESOLVED" | "MATCHED" | "EXCLUDED" | "ALL">("UNRESOLVED");
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

  // Statement History Modal State
  const [isStatementsModalOpen, setIsStatementsModalOpen] = useState<boolean>(false);
  const [statementsList, setStatementsList] = useState<any[]>([]);
  const [loadingStatements, setLoadingStatements] = useState<boolean>(false);
  const [deletingStatementId, setDeletingStatementId] = useState<string | null>(null);
  const [deletingTxId, setDeletingTxId] = useState<string | null>(null);

  // Exclusion Modal State
  const [txToExclude, setTxToExclude] = useState<BankTransactionItem | null>(null);
  const [stmtToExclude, setStmtToExclude] = useState<any | null>(null);
  const [exclusionReasonInput, setExclusionReasonInput] = useState<string>("Personal transaction");
  const [isExclusionSubmitting, setIsExclusionSubmitting] = useState<boolean>(false);

  // Action Modal State (for Match Party / Record Payment / Expense / Transfer)
  const [selectedTx, setSelectedTx] = useState<BankTransactionItem | null>(null);
  const [actionType, setActionType] = useState<"MATCH_PARTY" | "RECORD_PAYMENT" | "RECORD_EXPENSE" | "RECORD_TRANSFER" | "OWNER_DRAWING" | "IGNORE" | null>(null);
  const [actionTargetPartyId, setActionTargetPartyId] = useState<string>("");
  const [actionExpenseLedgerId, setActionExpenseLedgerId] = useState<string>("");
  const [actionTransferLedgerId, setActionTransferLedgerId] = useState<string>("");
  const [actionRemarks, setActionRemarks] = useState<string>("");
  const [actionLoading, setActionLoading] = useState<boolean>(false);

  const [confirmModalConfig, setConfirmModalConfig] = useState<{
    isOpen: boolean;
    title: string;
    description: React.ReactNode;
    confirmText: string;
    variant: "danger" | "warning" | "info";
    onConfirm: () => void | Promise<void>;
    isLoading?: boolean;
  }>({
    isOpen: false,
    title: "",
    description: null,
    confirmText: "Confirm",
    variant: "danger",
    onConfirm: () => {},
    isLoading: false,
  });

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }
    initializeData();
  }, [router, activeCompanyId]);

  useEffect(() => {
    if (isValidId(activeCompanyId) && activeCompanyId !== companyId) {
      setCompanyId(activeCompanyId);
    }
  }, [activeCompanyId]);

  useEffect(() => {
    if (isValidId(companyId)) {
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
      let cid = isValidId(activeCompanyId) ? activeCompanyId : "";
      if (!cid && typeof window !== "undefined") {
        const stored = localStorage.getItem("vouch_active_company_id");
        if (isValidId(stored)) {
          cid = stored;
        }
      }
      if (!cid) {
        const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const list = Array.isArray(compRes.data) ? compRes.data : (compRes.data.data || []);
        if (list.length > 0 && isValidId(list[0]?.id)) {
          cid = list[0].id;
        }
      }
      if (!cid) {
        toast.error("No company found", "Please create or select an active company first.");
        setLoading(false);
        return;
      }
      setCompanyId(cid);
      if (typeof window !== "undefined") {
        localStorage.setItem("vouch_active_company_id", cid);
      }

      const { data: rawLedgers } = await ledgersRepository.getLedgers(cid);
      setAllLedgers(rawLedgers as any[]);

      const banks = (rawLedgers as any[]).filter(
        (l) => l.ledger_type === "BANK" || l.ledgerType === "BANK" || (l.group && l.group.toLowerCase().includes("bank"))
      );
      setBankLedgers(banks);

      if (banks.length > 0 && isValidId(banks[0]?.id)) {
        setSelectedBankId(banks[0].id);
      }
    } catch (err: any) {
      console.error("Failed to load banking profile:", err);
      toast.error("Failed to load banking profile", err.response?.data?.error || err.message || "Network error");
    } finally {
      setLoading(false);
    }
  };

  const fetchTransactionsAndSummary = async (forceRefresh: boolean = false) => {
    if (!isValidId(companyId)) return;
    setRefreshing(true);
    try {
      const headers = getHeaders();
      const params: any = { company_id: companyId };
      if (isValidId(selectedBankId)) {
        params.bank_ledger_id = selectedBankId;
      }

      if (activeTab === "NEEDS_REVIEW") {
        params.status = "MATCHED_SUGGESTED,NEEDS_REVIEW";
      } else if (activeTab === "UNRESOLVED") {
        params.status = "UNRESOLVED,UNPROCESSED";
      } else if (activeTab === "MATCHED") {
        params.status = "MATCHED_AUTO,RECONCILED";
      } else if (activeTab === "EXCLUDED") {
        params.status = "EXCLUDED";
      } else if (activeTab === "ALL") {
        params.status = "ALL";
      }

      const [txResult, summaryRes] = await Promise.all([
        bankTransactionsRepository.getTransactions(companyId, {
          bankLedgerId: selectedBankId,
          status: params.status,
          forceRefresh,
        }),
        axios.get(`${API_BASE_URL}/api/v1/accounting/banking/summary/`, {
          headers,
          params: { company_id: companyId, ...(isValidId(selectedBankId) ? { bank_ledger_id: selectedBankId } : {}) },
        }),
      ]);

      setTransactions(txResult.data);

      const sData = summaryRes.data || null;
      if (sData) {
        setSummary({
          total_transactions: sData.total_transactions ?? 0,
          unresolved_count: sData.unresolved_count ?? sData.unresolved ?? 0,
          needs_review_count: sData.needs_review_count ?? sData.suggested ?? 0,
          matched_count: sData.matched_count ?? ((sData.auto_matched ?? 0) + (sData.reconciled ?? 0)),
          reconciled_count: sData.reconciled_count ?? sData.reconciled ?? 0,
          ignored_count: sData.ignored_count ?? sData.ignored ?? 0,
          excluded_count: sData.excluded_count ?? sData.excluded ?? 0,
          total_debits: sData.total_debits ?? sData.unreconciled_debit_amount ?? "0.00",
          total_credits: sData.total_credits ?? sData.unreconciled_credit_amount ?? "0.00",
          statement_closing_balance: sData.statement_closing_balance ?? null,
          book_closing_balance: sData.book_closing_balance ?? null,
          reconciliation_gap: sData.reconciliation_gap ?? null,
          is_balanced: Boolean(sData.is_balanced),
          statement_cutoff_date: sData.statement_cutoff_date ?? null,
          reconciliation_state: sData.reconciliation_state || (sData.is_balanced ? "BALANCE_VERIFIED" : "DISCREPANCY_DETECTED"),
        });
      } else {
        setSummary(null);
      }
    } catch (err: any) {
      console.error("Error loading bank transactions:", err);
      toast.error("Error loading bank transactions", err.response?.data?.error || err.message || "Could not fetch data.");
    } finally {
      setRefreshing(false);
    }
  };

  const fetchMappings = async () => {
    if (!isValidId(companyId)) return;
    setLoadingMappings(true);
    try {
      const headers = getHeaders();
      const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/banking/mappings/?company_id=${companyId}`, { headers });
      setMappings(Array.isArray(res.data) ? res.data : []);
    } catch (err: any) {
      toast.error("Failed to load learned rules", err.response?.data?.error || err.message);
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

  const fetchStatementsList = async () => {
    if (!isValidId(companyId)) return;
    setLoadingStatements(true);
    try {
      const headers = getHeaders();
      const params: any = { company_id: companyId };
      if (isValidId(selectedBankId)) {
        params.bank_ledger_id = selectedBankId;
      }
      const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/banking/statements/`, { headers, params });
      setStatementsList(Array.isArray(res.data) ? res.data : []);
    } catch (err: any) {
      console.error("Failed to load statements:", err);
      toast.error("Failed to load statements", err.response?.data?.error || err.message);
    } finally {
      setLoadingStatements(false);
    }
  };

  const handleDeleteStatement = (statement: any) => {
    setConfirmModalConfig({
      isOpen: true,
      title: "Delete Statement",
      description: (
        <div className="space-y-3 text-left">
          <p className="text-sm">
            Are you sure you want to permanently delete this statement and its imported records?
          </p>
          <div className="p-3.5 rounded-xl bg-muted/60 border border-border/60 text-xs space-y-1.5 font-sans">
            <div className="font-bold text-foreground truncate">{statement.source_file_name}</div>
            <div className="flex items-center gap-2 text-muted-foreground text-[11px] flex-wrap">
              <span>Format: <strong className="text-foreground">{statement.file_format}</strong></span>
              <span>•</span>
              <span>Rows: <strong className="text-foreground">{statement.successful_rows || 0} imported</strong></span>
              {statement.bank_ledger?.name && (
                <>
                  <span>•</span>
                  <span>Bank: <strong className="text-foreground">{statement.bank_ledger.name}</strong></span>
                </>
              )}
            </div>
          </div>
          <p className="text-xs text-rose-500/90 font-medium">
            This will permanently remove all associated transactions from the server and safely roll back any auto-generated reconciliation vouchers. This action cannot be undone.
          </p>
        </div>
      ),
      confirmText: "Delete Statement",
      variant: "danger",
      onConfirm: async () => {
        setDeletingStatementId(statement.id);
        setConfirmModalConfig((prev) => ({ ...prev, isLoading: true }));
        try {
          const headers = getHeaders();
          const res = await axios.delete(`${API_BASE_URL}/api/v1/accounting/banking/statements/${statement.id}/`, { headers });
          toast.success("Statement Deleted", res.data?.message || `Statement '${statement.source_file_name}' was removed from server.`);
          await fetchStatementsList();
          await fetchTransactionsAndSummary();
        } catch (err: any) {
          toast.error("Delete Failed", err.response?.data?.error || err.message || "Failed to delete statement");
        } finally {
          setDeletingStatementId(null);
          setConfirmModalConfig((prev) => ({ ...prev, isOpen: false, isLoading: false }));
        }
      },
    });
  };

  const handleExcludeTransaction = (tx: BankTransactionItem) => {
    setTxToExclude(tx);
    setExclusionReasonInput("Personal transaction");
  };

  const submitExcludeTransaction = async () => {
    if (!txToExclude) return;
    setIsExclusionSubmitting(true);
    try {
      const headers = getHeaders();
      await axios.post(
        `${API_BASE_URL}/api/v1/accounting/banking/transactions/${txToExclude.id}/exclude/`,
        { reason: exclusionReasonInput || "Excluded from business books" },
        { headers }
      );
      toast.success("Transaction Excluded", "Moved to Excluded. Any generated voucher was canonically reversed.");
      setTxToExclude(null);
      await fetchTransactionsAndSummary(true);
    } catch (err: any) {
      toast.error("Exclusion Failed", err.response?.data?.error || err.message || "Failed to exclude transaction.");
    } finally {
      setIsExclusionSubmitting(false);
    }
  };

  const handleRestoreTransaction = async (tx: BankTransactionItem) => {
    try {
      const headers = getHeaders();
      await axios.delete(
        `${API_BASE_URL}/api/v1/accounting/banking/transactions/${tx.id}/exclude/`,
        { headers }
      );
      toast.success("Transaction Restored", "Returned to active reconciliation.");
      await fetchTransactionsAndSummary(true);
    } catch (err: any) {
      toast.error("Restore Failed", err.response?.data?.error || err.message || "Failed to restore transaction.");
    }
  };

  const handleExcludeStatement = (stmt: any) => {
    setStmtToExclude(stmt);
    setExclusionReasonInput("Incorrect statement upload");
  };

  const submitExcludeStatement = async () => {
    if (!stmtToExclude) return;
    setIsExclusionSubmitting(true);
    try {
      const headers = getHeaders();
      await axios.post(
        `${API_BASE_URL}/api/v1/accounting/banking/statements/${stmtToExclude.id}/exclude/`,
        { reason: exclusionReasonInput || "Excluded from business books" },
        { headers }
      );
      toast.success("Statement Excluded", "All transactions in statement were excluded and vouchers reversed.");
      setStmtToExclude(null);
      await fetchStatementsList();
      await fetchTransactionsAndSummary(true);
    } catch (err: any) {
      toast.error("Exclusion Failed", err.response?.data?.error || err.message || "Failed to exclude statement.");
    } finally {
      setIsExclusionSubmitting(false);
    }
  };

  const handleRestoreStatement = async (stmt: any) => {
    try {
      const headers = getHeaders();
      await axios.delete(
        `${API_BASE_URL}/api/v1/accounting/banking/statements/${stmt.id}/exclude/`,
        { headers }
      );
      toast.success("Statement Restored", "Statement transactions restored to active.");
      await fetchStatementsList();
      await fetchTransactionsAndSummary(true);
    } catch (err: any) {
      toast.error("Restore Failed", err.response?.data?.error || err.message || "Failed to restore statement.");
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
        payload.target_ledger_id = actionTransferLedgerId;
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
        (tx.matched_party?.name ? tx.matched_party.name.toLowerCase().includes(q) : false) ||
        (tx.debit_amount ?? "").includes(q) ||
        (tx.credit_amount ?? "").includes(q) ||
        (tx.balance ? tx.balance.includes(q) : false) ||
        (tx.exclusion_reason ? tx.exclusion_reason.toLowerCase().includes(q) : false)
    );
  }, [transactions, searchQuery]);

  const customerAndSupplierLedgers = useMemo(() => {
    return allLedgers.filter((l) => {
      const type = l.ledgerType || l.ledger_type;
      const role = l.canonical_role;
      return (
        type === "CUSTOMER" ||
        type === "SUPPLIER" ||
        type === "BOTH" ||
        type === "PARTY" ||
        type === "CASH" ||
        (l.name && l.name.toLowerCase().includes("cash")) ||
        role === "CUSTOMER" ||
        role === "SUPPLIER" ||
        role === "BOTH" ||
        (l.group && l.group.toUpperCase().includes("DEBTOR")) ||
        (l.group && l.group.toUpperCase().includes("CREDITOR"))
      );
    });
  }, [allLedgers]);

  const expenseLedgers = useMemo(() => {
    return allLedgers.filter((l) => {
      const type = l.ledgerType || l.ledger_type;
      return (
        type === "EXPENSE" ||
        l.nature === "EXPENSE" ||
        (l.group && l.group.toLowerCase().includes("expense"))
      );
    });
  }, [allLedgers]);

  const contraLedgers = useMemo(() => {
    return allLedgers.filter((l) => {
      const type = l.ledgerType || l.ledger_type;
      return (
        (type === "BANK" || type === "CASH" || l.nature === "ASSET") &&
        l.id !== selectedBankId
      );
    });
  }, [allLedgers, selectedBankId]);

  const partyOptions: SearchableOption[] = useMemo(() => {
    return customerAndSupplierLedgers.map((p) => {
      const balance = p.currentBalance !== undefined ? p.currentBalance : p.current_balance;
      return {
        id: p.id,
        name: p.name,
        group: p.ledgerType || p.ledger_type || "PARTY",
        balance: balance !== undefined && balance !== null ? Number(balance) : undefined,
        subtitle: p.gstin ? `GSTIN: ${p.gstin}` : p.phone ? `Phone: ${p.phone}` : undefined,
      };
    });
  }, [customerAndSupplierLedgers]);

  const expenseOptions: SearchableOption[] = useMemo(() => {
    return expenseLedgers.map((exp) => {
      const balance = exp.currentBalance !== undefined ? exp.currentBalance : exp.current_balance;
      return {
        id: exp.id,
        name: exp.name,
        group: exp.group || "EXPENSE",
        balance: balance !== undefined && balance !== null ? Number(balance) : undefined,
      };
    });
  }, [expenseLedgers]);

  const contraOptions: SearchableOption[] = useMemo(() => {
    return contraLedgers.map((c) => {
      const balance = c.currentBalance !== undefined ? c.currentBalance : c.current_balance;
      return {
        id: c.id,
        name: c.name,
        group: c.ledgerType || c.ledger_type || "CONTRA",
        balance: balance !== undefined && balance !== null ? Number(balance) : undefined,
        subtitle: c.bank_account_number ? `A/c ...${c.bank_account_number.slice(-4)}` : undefined,
      };
    });
  }, [contraLedgers]);

  const bankOptions: SearchableOption[] = useMemo(() => {
    return bankLedgers.map((b) => {
      const balance = b.currentBalance !== undefined ? b.currentBalance : b.current_balance;
      return {
        id: b.id,
        name: b.name,
        group: "BANK",
        balance: balance !== undefined && balance !== null ? Number(balance) : undefined,
        subtitle: b.bank_account_number ? `A/c ...${b.bank_account_number.slice(-4)}` : undefined,
      };
    });
  }, [bankLedgers]);

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
                Banking
              </h1>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Upload bank statements and match transactions
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
              <span>Auto-match Rules ({mappings.length})</span>
            </button>

            <button
              onClick={() => {
                fetchStatementsList();
                setIsStatementsModalOpen(true);
              }}
              className="px-3.5 py-2 rounded-xl border border-border/60 bg-card hover:bg-muted text-foreground text-xs font-semibold flex items-center gap-2 cursor-pointer shadow-2xs transition-all"
            >
              <Layers className="w-3.5 h-3.5 text-blue-400" />
              <span>Upload History</span>
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
              onClick={() => fetchTransactionsAndSummary(true)}
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
                Bank Account
              </label>
              {bankLedgers.length > 1 && (
                <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
                  {bankLedgers.length} Accounts
                </span>
              )}
            </div>

            <SearchableSelect
              value={selectedBankId}
              onChange={(val) => setSelectedBankId(val)}
              options={bankOptions}
              placeholder="-- Select Bank Account --"
              searchPlaceholder="Search bank accounts..."
            />

            {(() => {
              const selectedBank = bankLedgers.find((b) => b.id === selectedBankId);
              if (!selectedBank) return null;
              const bal = selectedBank.currentBalance !== undefined ? selectedBank.currentBalance : selectedBank.current_balance;
              const hasDetails = selectedBank.bank_ifsc || selectedBank.upi_id;
              return (
                <div className="space-y-3">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center font-bold text-sm shrink-0">
                      {selectedBank.name.charAt(0).toUpperCase()}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-[11px] text-muted-foreground">Book Balance</div>
                      <div className="text-lg font-black font-mono tabular-nums text-foreground">
                        ₹{(bal ?? 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </div>
                    </div>
                  </div>
                  {hasDetails && (
                    <div className="flex items-center gap-3 text-[11px] text-muted-foreground font-mono">
                      {selectedBank.bank_ifsc && <span>IFSC: {selectedBank.bank_ifsc}</span>}
                      {selectedBank.bank_ifsc && selectedBank.upi_id && <span className="text-border">•</span>}
                      {selectedBank.upi_id && <span>UPI: {selectedBank.upi_id}</span>}
                    </div>
                  )}
                </div>
              );
            })()}
          </div>

          <div className="bg-card border border-border/40 rounded-2xl p-5 shadow-sm flex flex-col justify-between space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider block">
                  Reconciliation
                </span>
                {summary?.statement_cutoff_date && (
                  <span className="text-[11px] font-mono text-primary font-medium">
                    As of {new Date(summary.statement_cutoff_date).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}
                  </span>
                )}
              </div>
              {summary?.reconciliation_state === "FULLY_RECONCILED" ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  Reconciled
                </span>
              ) : summary?.is_balanced ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  Balanced
                </span>
              ) : summary?.reconciliation_state === "TRANSACTIONS_REVIEWED" ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-blue-500/10 text-blue-400 border border-blue-500/20">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  Reviewed
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                  <AlertCircle className="w-3.5 h-3.5" />
                  Unreconciled
                </span>
              )}
            </div>

            <div className="grid grid-cols-2 gap-0">
              <div className="p-3 bg-muted/20 rounded-l-xl border border-border/30 border-r-0">
                <div className="text-[11px] text-muted-foreground font-medium">Book</div>
                <div className="text-base font-bold font-mono tabular-nums text-foreground">
                  ₹{parseFloat(summary?.book_closing_balance || "0").toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div className="p-3 bg-muted/20 rounded-r-xl border border-border/30">
                <div className="text-[11px] text-muted-foreground font-medium">Statement</div>
                <div className="text-base font-bold font-mono tabular-nums text-foreground">
                  ₹{parseFloat(summary?.statement_closing_balance || "0").toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
              </div>
            </div>

            {!summary?.is_balanced && (summary?.reconciliation_gap || summary?.unresolved_count) ? (
              <div className="flex items-center justify-between p-2.5 rounded-xl bg-amber-500/5 border border-amber-500/15">
                <span className="text-[11px] font-medium text-amber-500">
                  Gap: ₹{parseFloat(summary?.reconciliation_gap || "0").toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </span>
                <span className="text-[11px] text-muted-foreground">
                  {summary?.unresolved_count || 0} items to review
                </span>
              </div>
            ) : (
              <p className="text-[11px] text-emerald-500/80 font-medium">
                ✓ Books match bank statement
              </p>
            )}
          </div>

          <div className="bg-card border border-border/40 rounded-2xl p-5 shadow-sm flex flex-col justify-between">
            <div className="flex items-center justify-between mb-4">
              <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
                Overview
              </span>
              <span className="text-[11px] font-mono text-muted-foreground">
                {summary?.total_transactions || 0} total
              </span>
            </div>

            <div className="space-y-3">
              <button onClick={() => setActiveTab("UNRESOLVED")} className="flex items-center justify-between w-full group cursor-pointer">
                <div className="flex items-center gap-2.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-rose-500 shrink-0" />
                  <span className="text-xs font-medium text-muted-foreground group-hover:text-foreground transition-colors">Needs Attention</span>
                </div>
                <span className="text-sm font-bold font-mono tabular-nums text-foreground">{summary?.unresolved_count || 0}</span>
              </button>

              <button onClick={() => setActiveTab("NEEDS_REVIEW")} className="flex items-center justify-between w-full group cursor-pointer">
                <div className="flex items-center gap-2.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-amber-500 shrink-0" />
                  <span className="text-xs font-medium text-muted-foreground group-hover:text-foreground transition-colors">Ready to Confirm</span>
                </div>
                <span className="text-sm font-bold font-mono tabular-nums text-foreground">{summary?.needs_review_count || 0}</span>
              </button>

              <button onClick={() => setActiveTab("MATCHED")} className="flex items-center justify-between w-full group cursor-pointer">
                <div className="flex items-center gap-2.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 shrink-0" />
                  <span className="text-xs font-medium text-muted-foreground group-hover:text-foreground transition-colors">Completed</span>
                </div>
                <span className="text-sm font-bold font-mono tabular-nums text-foreground">{(summary?.matched_count || 0) + (summary?.reconciled_count || 0)}</span>
              </button>

              {(summary?.excluded_count || 0) > 0 && (
                <button onClick={() => setActiveTab("EXCLUDED")} className="flex items-center justify-between w-full group cursor-pointer">
                  <div className="flex items-center gap-2.5">
                    <div className="w-2.5 h-2.5 rounded-full bg-muted-foreground/40 shrink-0" />
                    <span className="text-xs font-medium text-muted-foreground group-hover:text-foreground transition-colors">Excluded</span>
                  </div>
                  <span className="text-sm font-bold font-mono tabular-nums text-foreground">{summary?.excluded_count || 0}</span>
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Filter Tabs & Search Bar */}
        <div className="flex flex-col sm:flex-row justify-between items-stretch sm:items-center gap-3">
          <div className="flex items-center gap-1.5 p-1 bg-muted/30 border border-border/40 rounded-xl flex-wrap">
            <button
              onClick={() => setActiveTab("UNRESOLVED")}
              className={`px-3.5 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer flex items-center gap-2 ${
                activeTab === "UNRESOLVED"
                  ? "bg-card text-foreground shadow-sm border border-border/60"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <div className="w-2 h-2 rounded-full bg-rose-500 shrink-0" />
              <span>Attention</span>
              {(summary?.unresolved_count || 0) > 0 && (
                <span className="px-1.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-rose-500/15 text-rose-500 leading-none">
                  {summary?.unresolved_count}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab("NEEDS_REVIEW")}
              className={`px-3.5 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer flex items-center gap-2 ${
                activeTab === "NEEDS_REVIEW"
                  ? "bg-card text-foreground shadow-sm border border-border/60"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <div className="w-2 h-2 rounded-full bg-amber-500 shrink-0" />
              <span>Review</span>
              {(summary?.needs_review_count || 0) > 0 && (
                <span className="px-1.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-amber-500/15 text-amber-500 leading-none">
                  {summary?.needs_review_count}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab("MATCHED")}
              className={`px-3.5 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer flex items-center gap-2 ${
                activeTab === "MATCHED"
                  ? "bg-card text-foreground shadow-sm border border-border/60"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <div className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
              <span>Done</span>
              {((summary?.matched_count || 0) + (summary?.reconciled_count || 0)) > 0 && (
                <span className="px-1.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-emerald-500/15 text-emerald-500 leading-none">
                  {(summary?.matched_count || 0) + (summary?.reconciled_count || 0)}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab("EXCLUDED")}
              className={`px-3.5 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer flex items-center gap-2 ${
                activeTab === "EXCLUDED"
                  ? "bg-card text-foreground shadow-sm border border-border/60"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <span>Excluded</span>
              {(summary?.excluded_count || 0) > 0 && (
                <span className="px-1.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-muted text-muted-foreground leading-none">
                  {summary?.excluded_count}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab("ALL")}
              className={`px-3.5 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                activeTab === "ALL"
                  ? "bg-card text-foreground shadow-sm border border-border/60"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              All
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
            <p className="text-xs text-muted-foreground">Loading bank transactions...</p>
          </div>
        ) : filteredTransactions.length === 0 ? (
          <div className="bg-card border border-border/40 rounded-2xl p-16 text-center space-y-4 shadow-sm">
            <div className="w-14 h-14 rounded-2xl bg-muted/60 text-muted-foreground flex items-center justify-center mx-auto">
              {activeTab === "UNRESOLVED" ? (
                <AlertCircle className="w-7 h-7 text-rose-400" />
              ) : activeTab === "NEEDS_REVIEW" ? (
                <Sparkles className="w-7 h-7 text-amber-400" />
              ) : activeTab === "MATCHED" ? (
                <CheckCircle2 className="w-7 h-7 text-emerald-500" />
              ) : activeTab === "EXCLUDED" ? (
                <EyeOff className="w-7 h-7 text-muted-foreground" />
              ) : (
                <Landmark className="w-7 h-7 text-blue-400" />
              )}
            </div>
            <div>
              <h3 className="text-base font-bold text-foreground">
                {activeTab === "UNRESOLVED" ? "All Caught Up!" :
                 activeTab === "NEEDS_REVIEW" ? "No Pending Suggestions" :
                 activeTab === "MATCHED" ? "No Completed Items" :
                 activeTab === "EXCLUDED" ? "Nothing Excluded" :
                 "No Transactions Found"}
              </h3>
              <p className="text-xs text-muted-foreground max-w-xs mx-auto mt-1.5">
                {activeTab === "UNRESOLVED"
                  ? "There are no transactions requiring your attention. Upload a new statement to import more."
                  : activeTab === "NEEDS_REVIEW"
                  ? "Vouch hasn't found any AI-suggested matches. Upload another statement or check the Attention tab."
                  : activeTab === "MATCHED"
                  ? "No transactions have been matched yet. Start by reviewing items in the Attention or Review tabs."
                  : activeTab === "EXCLUDED"
                  ? "No transactions have been excluded from the books."
                  : "No transactions match your search or filter criteria."}
              </p>
            </div>
            {(activeTab === "UNRESOLVED" || activeTab === "NEEDS_REVIEW" || activeTab === "ALL") && (
              <button
                onClick={() => setIsUploadOpen(true)}
                className="px-4 py-2.5 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:bg-primary/90 transition-all cursor-pointer inline-flex items-center gap-2 shadow-sm"
              >
                <UploadCloud className="w-4 h-4" />
                <span>Upload Statement</span>
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-2">
            {filteredTransactions.map((tx, idx) => {
              const isCredit = parseFloat(tx.credit_amount) > 0;
              const amountVal = isCredit ? parseFloat(tx.credit_amount) : parseFloat(tx.debit_amount);
              const prevDate = idx > 0 ? filteredTransactions[idx - 1].transaction_date : null;
              const showDateHeader = tx.transaction_date !== prevDate;

              return (
                <React.Fragment key={tx.id}>
                  {showDateHeader && (
                    <div className={`flex items-center gap-3 ${idx > 0 ? "pt-3" : ""}`}>
                      <span className="text-[11px] font-bold text-muted-foreground font-mono whitespace-nowrap">
                        {(() => {
                          try {
                            const d = new Date(tx.transaction_date);
                            if (isNaN(d.getTime())) return tx.transaction_date;
                            return d.toLocaleDateString("en-IN", { weekday: "short", day: "2-digit", month: "short", year: "numeric" });
                          } catch { return tx.transaction_date; }
                        })()}
                      </span>
                      <div className="flex-1 h-px bg-border/40" />
                    </div>
                  )}
                <div
                  className="bg-card border border-border/40 hover:border-border/80 transition-all rounded-2xl p-4 shadow-sm space-y-2.5">
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
                          {tx.reference_number && (
                            <span className="font-mono text-[10px] px-2 py-0.5 bg-muted/60 text-muted-foreground rounded border border-border/40">
                              Ref: {tx.reference_number}
                            </span>
                          )}
                          <span
                            className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider ${
                              tx.is_excluded || tx.status === "EXCLUDED"
                                ? "bg-muted text-muted-foreground border border-border"
                                : tx.status === "MATCHED" || tx.status === "RECONCILED" || tx.status === "MATCHED_AUTO"
                                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                                : tx.status === "NEEDS_REVIEW" || tx.status === "MATCHED_SUGGESTED"
                                ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                                : tx.status === "IGNORED"
                                ? "bg-muted text-muted-foreground border border-border/50"
                                : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                            }`}
                          >
                            {tx.is_excluded || tx.status === "EXCLUDED"
                              ? "Excluded"
                              : tx.status === "MATCHED" || tx.status === "RECONCILED" || tx.status === "MATCHED_AUTO"
                              ? "Completed"
                              : tx.status === "NEEDS_REVIEW" || tx.status === "MATCHED_SUGGESTED"
                              ? "Ready to Confirm"
                              : tx.status === "IGNORED"
                              ? "Ignored"
                              : "Needs Your Attention"}
                          </span>
                        </div>

                        <div className="text-sm font-bold text-foreground leading-snug">
                          {tx.description}
                        </div>

                        {(tx.is_excluded || tx.status === "EXCLUDED") && tx.exclusion_reason && (
                          <div className="text-[11px] text-amber-500/90 font-medium flex items-center gap-1">
                            <EyeOff className="w-3 h-3" />
                            <span>Excluded: {tx.exclusion_reason}</span>
                          </div>
                        )}

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

                  {tx.matched_party && !tx.is_excluded && tx.status !== "EXCLUDED" && (
                    <div className="border-l-2 border-indigo-500/40 bg-muted/20 rounded-r-xl p-3 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                      <div className="flex items-start gap-2.5">
                        <Sparkles className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                        <div>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-xs font-semibold text-foreground">
                              {isCredit
                                ? `Receipt from ${tx.matched_party.name}`
                                : `Payment to ${tx.matched_party.name}`}
                            </span>
                            <span className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded ${
                              tx.match_confidence >= 80
                                ? "text-emerald-500"
                                : tx.match_confidence >= 50
                                ? "text-amber-500"
                                : "text-muted-foreground"
                            }`}>
                              {tx.match_confidence}%
                            </span>
                          </div>
                          {(() => {
                            if (!tx.match_notes) return null;
                            let notesObj: any = null;
                            if (typeof tx.match_notes === "object") {
                              notesObj = tx.match_notes;
                            } else if (typeof tx.match_notes === "string") {
                              try {
                                notesObj = JSON.parse(tx.match_notes);
                              } catch {
                                return <p className="text-[11px] text-muted-foreground mt-0.5">{tx.match_notes}</p>;
                              }
                            }
                            if (notesObj && typeof notesObj === "object") {
                              const signals = Array.isArray(notesObj.signals) ? notesObj.signals.filter(Boolean) : [];
                              const reason = notesObj.ignore_reason || notesObj.reason;
                              const parts = [...signals, ...(reason ? [String(reason)] : [])];
                              if (parts.length > 0) {
                                return (
                                  <div className="flex items-center gap-1.5 flex-wrap mt-1">
                                    {parts.map((p, pidx) => (
                                      <span key={pidx} className="text-[10px] px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground font-mono">
                                        {p}
                                      </span>
                                    ))}
                                  </div>
                                );
                              }
                            }
                            return null;
                          })()}
                        </div>
                      </div>

                      {tx.status !== "MATCHED" && tx.status !== "RECONCILED" && (
                        <div className="flex items-center gap-2 w-full sm:w-auto">
                          <button
                            onClick={() => openActionModal(tx, "MATCH_PARTY")}
                            className="px-3.5 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-bold transition-colors cursor-pointer flex-1 sm:flex-initial text-center"
                          >
                            {isCredit ? "Confirm" : "Confirm"}
                          </button>
                          <button
                            onClick={() => openActionModal(tx, "RECORD_PAYMENT")}
                            className="px-2.5 py-1.5 rounded-lg border border-border/60 hover:bg-muted text-foreground text-xs font-medium cursor-pointer"
                          >
                            Change
                          </button>
                          <button
                            onClick={() => openActionModal(tx, "IGNORE")}
                            className="px-2 py-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground text-xs cursor-pointer"
                          >
                            Skip
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Reconciled Voucher Link if resolved */}
                  {tx.matched_voucher && !tx.is_excluded && tx.status !== "EXCLUDED" && (
                    <div className="text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-3 py-1.5 rounded-lg flex items-center justify-between font-mono">
                      <span>✓ Reconciled to Voucher: {tx.matched_voucher.voucher_number}</span>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => router.push(`/vouchers`)}
                          className="hover:underline text-[11px] cursor-pointer"
                        >
                          View Voucher →
                        </button>
                        <button
                          onClick={() => handleExcludeTransaction(tx)}
                          className="text-amber-400/80 hover:text-amber-300 hover:underline text-[11px] cursor-pointer flex items-center gap-1 ml-2"
                          title="Exclude transaction and reverse reconciliation voucher"
                        >
                          <EyeOff className="w-3 h-3" />
                          Exclude
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Excluded state actions */}
                  {(tx.is_excluded || tx.status === "EXCLUDED") && (
                    <div className="flex items-center justify-between pt-2 border-t border-border/30">
                      <span className="text-[11px] text-muted-foreground">Excluded from business accounts and books</span>
                      <button
                        onClick={() => handleRestoreTransaction(tx)}
                        className="px-3 py-1.5 rounded-lg text-xs font-bold bg-primary text-primary-foreground hover:bg-primary/90 transition-colors cursor-pointer shadow-sm"
                      >
                        Restore to Books
                      </button>
                    </div>
                  )}

                  {/* Quick Action Toolbar — only when no AI suggestion card shown */}
                  {!tx.is_excluded && tx.status !== "EXCLUDED" && tx.status !== "MATCHED" && tx.status !== "RECONCILED" && !tx.matched_party && (
                    <div className="flex items-center gap-2 pt-2 border-t border-border/30 flex-wrap">

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

                      <button
                        onClick={() => handleExcludeTransaction(tx)}
                        className="px-2.5 py-1 rounded-lg text-xs font-semibold text-amber-500 hover:text-amber-400 hover:bg-amber-500/10 border border-amber-500/20 transition-colors cursor-pointer flex items-center gap-1"
                        title="Exclude from books without destructive deletion"
                      >
                        <EyeOff className="w-3 h-3" />
                        <span>Exclude</span>
                      </button>
                    </div>
                  )}
                </div>
                </React.Fragment>
              );
            })}
          </div>
        )}

        {/* UPLOAD STATEMENT MODAL */}
        {isUploadOpen && (
          <div 
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200"
            onClick={() => setIsUploadOpen(false)}
          >
            <div
              className="bg-card border border-border rounded-2xl shadow-2xl w-full max-w-lg overflow-visible animate-in zoom-in-95 duration-200"
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
                  <SearchableSelect
                    value={selectedBankId}
                    onChange={(val) => setSelectedBankId(val)}
                    options={bankOptions}
                    placeholder="-- Select Target Bank Account --"
                    searchPlaceholder="Search bank accounts..."
                  />
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
                    <h3 className="text-base font-bold text-foreground">Auto-match Rules</h3>
                    <p className="text-xs text-muted-foreground">Rules for your business</p>
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
          <div 
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200"
            onClick={closeActionModal}
          >
            <div
              className="bg-card border border-border rounded-2xl shadow-2xl w-full max-w-md overflow-visible animate-in zoom-in-95 duration-200"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="p-5 border-b border-border">
                <div className="flex items-center justify-between">
                  <h3 className="text-base font-bold text-foreground">
                    {actionType === "MATCH_PARTY" &&
                      (parseFloat(selectedTx.credit_amount) > 0 ? "Confirm Customer Receipt & Save Rule" : "Confirm Supplier Payment & Save Rule")}
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
                    <SearchableSelect
                      value={actionTargetPartyId}
                      onChange={(val) => setActionTargetPartyId(val)}
                      options={partyOptions}
                      placeholder="-- Choose Party --"
                      searchPlaceholder="Search party name, GSTIN, phone..."
                    />
                    {(actionType === "RECORD_PAYMENT" || actionType === "MATCH_PARTY") && (
                      <div className="p-2.5 rounded-lg bg-primary/5 border border-primary/20 text-[11px] text-muted-foreground mt-2 space-y-1">
                        <div className="font-semibold text-foreground flex items-center gap-1.5">
                          <Sparkles className="w-3.5 h-3.5 text-primary" />
                          <span>Auto-Allocation Rule</span>
                        </div>
                        <p>
                          {parseFloat(selectedTx.credit_amount) > 0
                            ? "Incoming customer receipt will be safely applied to oldest unpaid sales invoices (FIFO) or matching invoice references under concurrency locks. Any excess remains an advance balance."
                            : "Outgoing supplier payment will be safely applied to oldest unpaid purchase bills (FIFO) or matching invoice references under concurrency locks. Any excess remains an advance balance."}
                        </p>
                      </div>
                    )}
                  </div>
                )}

                {/* Expense Ledger Selector */}
                {actionType === "RECORD_EXPENSE" && (
                  <div>
                    <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider block mb-1.5">
                      Select Expense Ledger
                    </label>
                    <SearchableSelect
                      value={actionExpenseLedgerId}
                      onChange={(val) => setActionExpenseLedgerId(val)}
                      options={expenseOptions}
                      placeholder="-- Choose Expense Account --"
                      searchPlaceholder="Search expense category or ledger..."
                    />
                  </div>
                )}

                {/* Transfer Ledger Selector */}
                {actionType === "RECORD_TRANSFER" && (
                  <div>
                    <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider block mb-1.5">
                      Transfer Account (Bank / Cash)
                    </label>
                    <SearchableSelect
                      value={actionTransferLedgerId}
                      onChange={(val) => setActionTransferLedgerId(val)}
                      options={contraOptions}
                      placeholder="-- Choose Target/Source Ledger --"
                      searchPlaceholder="Search bank or cash ledger..."
                    />
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

        {/* STATEMENT HISTORY & DELETE MODAL */}
        {isStatementsModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
            <div className="bg-card border border-border/60 rounded-2xl max-w-2xl w-full shadow-2xl overflow-hidden flex flex-col max-h-[85vh]">
              <div className="px-6 py-4 border-b border-border/40 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="p-2 rounded-xl bg-blue-500/10 text-blue-400">
                    <Layers className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-foreground">Upload History</h3>
                    <p className="text-xs text-muted-foreground">
                      Manage previously uploaded statements
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setIsStatementsModalOpen(false)}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="p-6 overflow-y-auto space-y-3 flex-1">
                {loadingStatements ? (
                  <div className="py-12 flex flex-col items-center justify-center space-y-3">
                    <RefreshCw className="w-6 h-6 animate-spin text-primary" />
                    <span className="text-xs text-muted-foreground">Loading statement history...</span>
                  </div>
                ) : statementsList.length === 0 ? (
                  <div className="py-12 text-center text-muted-foreground text-xs">
                    No statements uploaded yet for this bank account.
                  </div>
                ) : (
                  statementsList.map((stmt) => (
                    <div
                      key={stmt.id}
                      className="bg-muted/30 border border-border/40 rounded-xl p-4 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 hover:border-border/60 transition-all"
                    >
                      <div className="space-y-1 min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-bold text-foreground truncate max-w-xs">
                            {stmt.source_file_name}
                          </span>
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-primary/10 text-primary border border-primary/20">
                            {stmt.file_format}
                          </span>
                          {stmt.is_excluded ? (
                            <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-muted text-muted-foreground border border-border">
                              EXCLUDED
                            </span>
                          ) : (
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${
                                stmt.status === "COMPLETED"
                                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                                  : "bg-amber-500/10 text-amber-400 border-amber-500/20"
                              }`}
                            >
                              {stmt.status}
                            </span>
                          )}
                        </div>

                        <div className="flex items-center gap-3 text-[11px] text-muted-foreground flex-wrap">
                          <span>Bank: <strong className="text-foreground">{stmt.bank_ledger?.name}</strong></span>
                          <span>•</span>
                          <span>Uploaded: {new Date(stmt.created_at).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
                          <span>•</span>
                          <span>Rows: <strong className="text-foreground">{stmt.successful_rows}/{stmt.total_rows}</strong></span>
                        </div>

                        {(stmt.opening_balance || stmt.closing_balance) && (
                          <div className="text-[11px] font-mono text-muted-foreground">
                            Bal: ₹{parseFloat(stmt.opening_balance || "0").toLocaleString("en-IN", { minimumFractionDigits: 2 })} → ₹{parseFloat(stmt.closing_balance || "0").toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                          </div>
                        )}

                        {stmt.is_excluded && stmt.exclusion_reason && (
                          <div className="text-[11px] text-amber-500 font-medium flex items-center gap-1 mt-1">
                            <EyeOff className="w-3 h-3" />
                            <span>Excluded: {stmt.exclusion_reason}</span>
                          </div>
                        )}
                      </div>

                      {stmt.is_excluded ? (
                        <button
                          onClick={() => handleRestoreStatement(stmt)}
                          className="px-3 py-2 rounded-xl text-xs font-bold text-primary hover:bg-primary/10 border border-primary/20 transition-all cursor-pointer flex items-center gap-1.5 w-full sm:w-auto justify-center"
                        >
                          Restore Statement
                        </button>
                      ) : (
                        <button
                          onClick={() => handleExcludeStatement(stmt)}
                          className="px-3 py-2 rounded-xl text-xs font-bold text-amber-500 hover:text-amber-400 hover:bg-amber-500/10 border border-amber-500/20 transition-all cursor-pointer flex items-center gap-1.5 w-full sm:w-auto justify-center"
                          title="Exclude statement from books and reverse linked vouchers"
                        >
                          <EyeOff className="w-3.5 h-3.5" />
                          <span>Exclude Statement</span>
                        </button>
                      )}
                    </div>
                  ))
                )}
              </div>

              <div className="px-6 py-3.5 border-t border-border/40 bg-muted/20 flex justify-end">
                <button
                  onClick={() => setIsStatementsModalOpen(false)}
                  className="px-4 py-2 rounded-xl text-xs font-bold text-foreground bg-muted hover:bg-muted/80 transition-colors cursor-pointer"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}

        {/* AUDITED EXCLUSION MODAL */}
        {(txToExclude || stmtToExclude) && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200"
            onClick={() => {
              setTxToExclude(null);
              setStmtToExclude(null);
            }}
          >
            <div
              className="bg-card border border-border rounded-2xl shadow-2xl w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="p-5 border-b border-border/40">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="p-2 rounded-xl bg-amber-500/10 text-amber-400">
                      <EyeOff className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-foreground">
                        {txToExclude ? "Exclude Transaction from Books" : "Exclude Statement from Books"}
                      </h3>
                      <p className="text-xs text-muted-foreground">
                        Audited financial exclusion (non-destructive)
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      setTxToExclude(null);
                      setStmtToExclude(null);
                    }}
                    className="text-muted-foreground hover:text-foreground p-1 rounded-lg cursor-pointer"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>

              <div className="p-5 space-y-4">
                <div className="p-3.5 rounded-xl bg-muted/40 border border-border/40 text-xs space-y-1.5">
                  <div className="font-bold text-foreground">
                    {txToExclude ? txToExclude.description : stmtToExclude?.source_file_name}
                  </div>
                  {txToExclude && (
                    <div className="flex items-center justify-between text-[11px] font-mono text-muted-foreground">
                      <span>Date: {txToExclude.transaction_date}</span>
                      <span className="font-bold text-foreground">
                        ₹{parseFloat(parseFloat(txToExclude.credit_amount) > 0 ? txToExclude.credit_amount : txToExclude.debit_amount).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </span>
                    </div>
                  )}
                  <p className="text-[11px] text-muted-foreground">
                    This preserves the raw banking record for audit compliance while removing it from company financial statements. Any auto-created voucher is canonically reversed with a REV- voucher.
                  </p>
                </div>

                <div>
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider block mb-1.5">
                    Reason for Exclusion
                  </label>
                  <div className="grid grid-cols-2 gap-2 mb-2">
                    {["Personal transaction", "Contra duplicate", "Non-business fee", "Wrong account"].map((preset) => (
                      <button
                        key={preset}
                        type="button"
                        onClick={() => setExclusionReasonInput(preset)}
                        className={`px-2.5 py-1.5 rounded-lg text-xs font-medium border transition-all cursor-pointer text-left truncate ${
                          exclusionReasonInput === preset
                            ? "bg-primary/10 border-primary/40 text-primary font-bold"
                            : "bg-muted/40 border-border/40 text-muted-foreground hover:text-foreground hover:bg-muted"
                        }`}
                      >
                        {preset}
                      </button>
                    ))}
                  </div>
                  <input
                    type="text"
                    value={exclusionReasonInput}
                    onChange={(e) => setExclusionReasonInput(e.target.value)}
                    placeholder="Enter custom exclusion reason..."
                    className="w-full bg-muted/40 border border-border/60 rounded-xl px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                  />
                </div>

                <div className="flex items-center gap-3 pt-2">
                  <button
                    type="button"
                    onClick={() => {
                      setTxToExclude(null);
                      setStmtToExclude(null);
                    }}
                    className="flex-1 py-2.5 rounded-xl text-xs font-bold text-muted-foreground hover:text-foreground bg-muted hover:bg-muted/80 transition-colors cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={txToExclude ? submitExcludeTransaction : submitExcludeStatement}
                    disabled={isExclusionSubmitting}
                    className="flex-1 py-2.5 rounded-xl text-xs font-bold text-white bg-amber-600 hover:bg-amber-700 transition-all cursor-pointer flex items-center justify-center gap-2 disabled:opacity-50 shadow-md shadow-amber-600/20"
                  >
                    {isExclusionSubmitting ? (
                      <>
                        <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                        <span>Excluding...</span>
                      </>
                    ) : (
                      <span>Confirm Exclusion</span>
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* REUSABLE MODERN CONFIRMATION MODAL */}
        <ConfirmModal
          isOpen={confirmModalConfig.isOpen}
          onClose={() => setConfirmModalConfig((prev) => ({ ...prev, isOpen: false }))}
          onConfirm={confirmModalConfig.onConfirm}
          title={confirmModalConfig.title}
          description={confirmModalConfig.description}
          confirmText={confirmModalConfig.confirmText}
          variant={confirmModalConfig.variant}
          isLoading={confirmModalConfig.isLoading}
        />
      </div>
    </DashboardLayout>
  );
}
