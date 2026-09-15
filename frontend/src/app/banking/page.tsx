"use client";

import React, { useEffect, useState, useRef, useMemo } from "react";
import axios from "axios";
import { useRouter } from "next/navigation";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import DashboardLayout from "@/components/DashboardLayout";
import { useToast } from "@/context/ToastContext";
import { useCompany } from "@/context/CompanyContext";
import { SearchableOption } from "@/components/SearchableSelect";
import { bankTransactionsRepository, ledgersRepository } from "@/lib/data";
import {
  Landmark,
  UploadCloud,
  BookOpen,
  RefreshCw,
  Layers,
  AlertCircle,
  Sparkles,
  CheckCircle2,
  EyeOff,
} from "lucide-react";
import {
  BankLedger,
  BankTransactionItem,
  ReconciliationSummary,
  PartyMappingItem,
  BankingActiveTab,
  BankingActionType,
  BankAccountSummaryCard,
  ReconciliationComparisonCard,
  ReconciliationOverviewCard,
  ReconciliationStatsBar,
  BankTransactionCard,
  BankingModalsContainer,
} from "@/components/banking";

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
  const [activeTab, setActiveTab] = useState<BankingActiveTab>("UNRESOLVED");
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
  const [actionType, setActionType] = useState<BankingActionType | null>(null);
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
        (l: any) => l.ledgerType === "BANK" || l.ledger_type === "BANK"
      );
      setBankLedgers(banks);

      if (banks.length > 0 && !selectedBankId) {
        setSelectedBankId(banks[0].id);
      }

      // Background fresh sync from server to ensure latest expense accounts and groups
      ledgersRepository.refreshLedgers(cid).then((refreshed) => {
        if (refreshed && refreshed.length > 0) {
          setAllLedgers(refreshed as any[]);
          const freshBanks = (refreshed as any[]).filter(
            (l: any) => l.ledgerType === "BANK" || l.ledger_type === "BANK"
          );
          if (freshBanks.length > 0) {
            setBankLedgers(freshBanks as any[]);
          }
        }
      });
    } catch (err: any) {
      console.error(err);
      toast.error("Initialization Failed", err.message || "Failed to load bank accounts.");
    } finally {
      setLoading(false);
    }
  };

  const fetchTransactionsAndSummary = async (isManualRefresh = false) => {
    if (!isValidId(companyId)) return;
    if (isManualRefresh) setRefreshing(true);
    try {
      const headers = getHeaders();
      const params: any = { company_id: companyId };
      if (selectedBankId) {
        params.bank_ledger_id = selectedBankId;
      }
      if (activeTab !== "ALL") {
        params.status = activeTab;
      }

      if (typeof window !== "undefined" && !navigator.onLine && selectedBankId) {
        const cachedTxs = await bankTransactionsRepository.getByBankLedger(selectedBankId);
        if (cachedTxs && cachedTxs.length > 0) {
          setTransactions(cachedTxs as any[]);
          setLoading(false);
          if (isManualRefresh) setRefreshing(false);
          return;
        }
      }

      const [txRes, sumRes] = await Promise.all([
        axios.get(`${API_BASE_URL}/api/v1/accounting/banking/transactions/`, {
          headers,
          params,
        }),
        axios.get(`${API_BASE_URL}/api/v1/accounting/banking/summary/`, {
          headers,
          params: selectedBankId ? { company_id: companyId, bank_ledger_id: selectedBankId } : { company_id: companyId },
        }),
      ]);

      const fetchedTxs = Array.isArray(txRes.data) ? txRes.data : txRes.data.results || [];
      setTransactions(fetchedTxs);
      setSummary(sumRes.data);

      if (selectedBankId && fetchedTxs.length > 0) {
        bankTransactionsRepository.bulkUpsert(
          fetchedTxs.map((t: any) => ({
            id: t.id,
            bank_ledger: t.bank_ledger?.id || selectedBankId,
            transaction_date: t.transaction_date,
            description: t.description,
            normalized_narration: t.normalized_narration,
            reference_number: t.reference_number,
            debit_amount: t.debit_amount,
            credit_amount: t.credit_amount,
            balance: t.balance,
            status: t.status,
            is_excluded: t.is_excluded,
            exclusion_reason: t.exclusion_reason,
            matched_party: t.matched_party,
            matched_voucher: t.matched_voucher,
            match_confidence: t.match_confidence,
            match_notes: t.match_notes,
            created_at: t.created_at || new Date().toISOString(),
            updated_at: t.updated_at || new Date().toISOString(),
          }))
        ).catch((e: any) => console.warn("Failed to cache bank transactions offline:", e));
      }
    } catch (err: any) {
      console.error(err);
      if (selectedBankId) {
        const cached = await bankTransactionsRepository.getByBankLedger(selectedBankId);
        if (cached && cached.length > 0) {
          setTransactions(cached as any[]);
          toast.info("Offline Mode", "Displaying locally cached bank transactions.");
        }
      }
    } finally {
      setLoading(false);
      if (isManualRefresh) setRefreshing(false);
    }
  };

  const fetchMappings = async () => {
    setLoadingMappings(true);
    try {
      const headers = getHeaders();
      const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/banking/mappings/`, {
        headers,
        params: { company_id: companyId },
      });
      setMappings(Array.isArray(res.data) ? res.data : res.data.results || []);
    } catch (err: any) {
      toast.error("Failed to load mappings", err.message);
    } finally {
      setLoadingMappings(false);
    }
  };

  const deleteMapping = async (mappingId: string) => {
    try {
      const headers = getHeaders();
      await axios.delete(`${API_BASE_URL}/api/v1/accounting/banking/mappings/${mappingId}/`, {
        headers,
      });
      setMappings((prev) => prev.filter((m) => m.id !== mappingId));
      toast.success("Rule Deleted", "The auto-match rule has been removed.");
    } catch (err: any) {
      toast.error("Delete Failed", err.message);
    }
  };

  const fetchStatementsList = async () => {
    setLoadingStatements(true);
    try {
      const headers = getHeaders();
      const params: any = { company_id: companyId };
      if (selectedBankId) params.bank_ledger_id = selectedBankId;
      const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/banking/statements/`, {
        headers,
        params,
      });
      setStatementsList(Array.isArray(res.data) ? res.data : res.data.results || []);
    } catch (err: any) {
      toast.error("Failed to load upload history", err.message);
    } finally {
      setLoadingStatements(false);
    }
  };

  const handleExcludeTransaction = (tx: BankTransactionItem) => {
    setTxToExclude(tx);
    setStmtToExclude(null);
    setExclusionReasonInput("Personal transaction");
  };

  const submitExcludeTransaction = async () => {
    if (!txToExclude) return;
    setIsExclusionSubmitting(true);
    try {
      const headers = getHeaders();
      const res = await axios.post(
        `${API_BASE_URL}/api/v1/accounting/banking/transactions/${txToExclude.id}/exclude/`,
        { reason: exclusionReasonInput || "Personal transaction" },
        { headers }
      );
      toast.success("Transaction Excluded", res.data.message || "Transaction excluded from books.");
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
      const res = await axios.post(
        `${API_BASE_URL}/api/v1/accounting/banking/transactions/${tx.id}/restore/`,
        {},
        { headers }
      );
      toast.success("Transaction Restored", res.data.message || "Transaction restored to books.");
      await fetchTransactionsAndSummary(true);
    } catch (err: any) {
      toast.error("Restore Failed", err.response?.data?.error || err.message || "Failed to restore transaction.");
    }
  };

  const handleExcludeStatement = (stmt: any) => {
    setStmtToExclude(stmt);
    setTxToExclude(null);
    setExclusionReasonInput("Wrong account upload");
  };

  const submitExcludeStatement = async () => {
    if (!stmtToExclude) return;
    setIsExclusionSubmitting(true);
    try {
      const headers = getHeaders();
      const res = await axios.post(
        `${API_BASE_URL}/api/v1/accounting/banking/statements/${stmtToExclude.id}/exclude/`,
        { reason: exclusionReasonInput || "Excluded by user" },
        { headers }
      );
      toast.success("Statement Excluded", res.data.message || "All statement transactions safely excluded.");
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
      const res = await axios.post(
        `${API_BASE_URL}/api/v1/accounting/banking/statements/${stmt.id}/restore/`,
        {},
        { headers }
      );
      toast.success("Statement Restored", res.data.message || "Statement transactions restored to books.");
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
    type: BankingActionType
  ) => {
    setSelectedTx(tx);
    setActionRemarks("");

    const isDebit = parseFloat(tx.debit_amount) > 0;
    const desc = (tx.description || tx.normalized_narration || "").toLowerCase();
    const isExpenseCue = isDebit && (
      desc.includes("interest") ||
      desc.includes("charge") ||
      desc.includes("chg") ||
      desc.includes("fee") ||
      desc.includes("sms") ||
      desc.includes("amc") ||
      desc.includes("tax") ||
      desc.includes("gst") ||
      desc.includes("capitalized")
    );
    const isExpenseMatch =
      tx.matched_party?.ledger_type === "EXPENSE" ||
      (typeof tx.match_notes === "object" && (tx.match_notes as any)?.is_bank_expense);

    let effectiveType = type;
    if (isExpenseMatch || (isExpenseCue && (type === "RECORD_PAYMENT" || (type === "MATCH_PARTY" && (tx.match_confidence || 0) < 85)))) {
      effectiveType = "RECORD_EXPENSE";
    }

    setActionType(effectiveType);

    if (tx.matched_party && !isExpenseMatch && effectiveType !== "RECORD_EXPENSE") {
      setActionTargetPartyId(tx.matched_party.id);
    } else {
      setActionTargetPartyId("");
    }

    // Auto-select smart expense ledger if applicable
    let matchedExpId = "";
    if (isExpenseMatch && tx.matched_party) {
      matchedExpId = tx.matched_party.id;
    } else if (effectiveType === "RECORD_EXPENSE" || isExpenseCue) {
      if (desc.includes("interest")) {
        const intLedger = expenseLedgers.find((l) => l.name.toLowerCase().includes("interest"));
        if (intLedger) matchedExpId = intLedger.id;
      }
      if (!matchedExpId && (desc.includes("charge") || desc.includes("chg") || desc.includes("fee") || desc.includes("sms"))) {
        const chgLedger = expenseLedgers.find((l) =>
          l.name.toLowerCase().includes("charge") || l.name.toLowerCase().includes("fee")
        );
        if (chgLedger) matchedExpId = chgLedger.id;
      }
      if (!matchedExpId && expenseLedgers.length > 0) {
        matchedExpId = expenseLedgers[0].id;
      }
    }
    setActionExpenseLedgerId(matchedExpId);
    setActionTransferLedgerId("");
  };

  const handleActionTypeChange = (newType: BankingActionType) => {
    setActionType(newType);
    if (newType === "RECORD_EXPENSE" && !actionExpenseLedgerId && selectedTx) {
      const desc = (selectedTx.description || selectedTx.normalized_narration || "").toLowerCase();
      let matchedExpId = "";
      if (desc.includes("interest")) {
        const intLedger = expenseLedgers.find((l) => l.name.toLowerCase().includes("interest"));
        if (intLedger) matchedExpId = intLedger.id;
      }
      if (!matchedExpId && (desc.includes("charge") || desc.includes("chg") || desc.includes("fee") || desc.includes("sms"))) {
        const chgLedger = expenseLedgers.find((l) =>
          l.name.toLowerCase().includes("charge") || l.name.toLowerCase().includes("fee")
        );
        if (chgLedger) matchedExpId = chgLedger.id;
      }
      if (!matchedExpId && expenseLedgers.length > 0) {
        matchedExpId = expenseLedgers[0].id;
      }
      if (matchedExpId) setActionExpenseLedgerId(matchedExpId);
    }
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
      const type = (l.ledgerType || l.ledger_type || "").toUpperCase();
      const role = (l.canonical_role || "").toUpperCase();
      const nature = (l.nature || "").toUpperCase();
      if (nature === "EXPENSE") return false;
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
      const type = (l.ledgerType || l.ledger_type || "").toUpperCase();
      const nature = (l.nature || "").toUpperCase();
      const group = (l.group || l.group_name || "").toLowerCase();
      const name = (l.name || "").toLowerCase();

      if (type === "EXPENSE" || nature === "EXPENSE") return true;
      if (group.includes("expense") || group.includes("exp")) return true;
      if (group.includes("indirect") || group.includes("direct")) return true;

      // Common business expense keywords if not explicitly a customer, supplier, bank, or cash
      const isLiquidOrParty =
        type === "CUSTOMER" ||
        type === "SUPPLIER" ||
        type === "BANK" ||
        type === "CASH" ||
        (l.canonical_role && (l.canonical_role === "CUSTOMER" || l.canonical_role === "SUPPLIER"));

      if (!isLiquidOrParty) {
        if (
          name.includes("interest") ||
          name.includes("charge") ||
          name.includes("fee") ||
          name.includes("tax") ||
          name.includes("rent") ||
          name.includes("salary") ||
          name.includes("commission") ||
          name.includes("cartage") ||
          name.includes("freight") ||
          name.includes("amc") ||
          name.includes("depreciation")
        ) {
          return true;
        }
      }

      return false;
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
          <BankAccountSummaryCard
            selectedBankId={selectedBankId}
            onSelectBankId={setSelectedBankId}
            bankLedgers={bankLedgers}
            bankOptions={bankOptions}
          />
          <ReconciliationComparisonCard summary={summary} />
          <ReconciliationOverviewCard
            summary={summary}
            onSelectTab={setActiveTab}
          />
        </div>

        {/* Filter Tabs & Search Bar */}
        <ReconciliationStatsBar
          summary={summary}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
        />

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
              const prevDate = idx > 0 ? filteredTransactions[idx - 1].transaction_date : null;
              const showDateHeader = tx.transaction_date !== prevDate;
              return (
                <BankTransactionCard
                  key={tx.id}
                  tx={tx}
                  idx={idx}
                  showDateHeader={showDateHeader}
                  onOpenActionModal={openActionModal}
                  onExclude={handleExcludeTransaction}
                  onRestore={handleRestoreTransaction}
                  onViewVouchers={() => router.push("/vouchers")}
                />
              );
            })}
          </div>
        )}

        {/* Modular Modals & Drawers Container */}
        <BankingModalsContainer
          isUploadOpen={isUploadOpen}
          onCloseUpload={() => setIsUploadOpen(false)}
          selectedBankId={selectedBankId}
          onSelectBankId={setSelectedBankId}
          bankOptions={bankOptions}
          uploadFile={uploadFile}
          onFileChange={setUploadFile}
          isUploading={isUploading}
          uploadResult={uploadResult}
          onUploadSubmit={handleFileUpload}
          fileInputRef={fileInputRef}
          isMappingsOpen={isMappingsOpen}
          onCloseMappings={() => setIsMappingsOpen(false)}
          mappings={mappings}
          loadingMappings={loadingMappings}
          onDeleteMapping={deleteMapping}
          selectedTx={selectedTx}
          actionType={actionType}
          onActionTypeChange={handleActionTypeChange}
          onCloseAction={closeActionModal}
          actionTargetPartyId={actionTargetPartyId}
          onTargetPartyChange={setActionTargetPartyId}
          partyOptions={partyOptions}
          actionExpenseLedgerId={actionExpenseLedgerId}
          onExpenseLedgerChange={setActionExpenseLedgerId}
          expenseOptions={expenseOptions}
          actionTransferLedgerId={actionTransferLedgerId}
          onTransferLedgerChange={setActionTransferLedgerId}
          contraOptions={contraOptions}
          actionRemarks={actionRemarks}
          onRemarksChange={setActionRemarks}
          actionLoading={actionLoading}
          onSubmitAction={submitResolveAction}
          isStatementsModalOpen={isStatementsModalOpen}
          onCloseStatements={() => setIsStatementsModalOpen(false)}
          statementsList={statementsList}
          loadingStatements={loadingStatements}
          onExcludeStatement={handleExcludeStatement}
          onRestoreStatement={handleRestoreStatement}
          txToExclude={txToExclude}
          stmtToExclude={stmtToExclude}
          onCloseExclusion={() => {
            setTxToExclude(null);
            setStmtToExclude(null);
          }}
          exclusionReasonInput={exclusionReasonInput}
          onExclusionReasonChange={setExclusionReasonInput}
          isExclusionSubmitting={isExclusionSubmitting}
          onSubmitExcludeTransaction={submitExcludeTransaction}
          onSubmitExcludeStatement={submitExcludeStatement}
          confirmModalConfig={confirmModalConfig}
          onCloseConfirm={() => setConfirmModalConfig((prev) => ({ ...prev, isOpen: false }))}
        />
      </div>
    </DashboardLayout>
  );
}
