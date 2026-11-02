"use client";

import React, { useEffect, useState, useRef, useMemo } from "react";

import { useRouter } from "next/navigation";
import { api, API_BASE_URL } from "@/utils/api";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import DashboardLayout from "@/components/DashboardLayout";
import { useToast } from "@/context/ToastContext";
import { useCompany } from "@/context/CompanyContext";
import { useFinancialYear } from "@/context/FinancialYearContext";
import { useAccountingPeriod } from "@/context/PeriodContext";
import AddBankModal from "@/components/modals/AddBankModal";
import { SearchableOption } from "@/components/SearchableSelect";
import { bankTransactionsRepository, ledgersRepository } from "@/lib/data";
import { offlineDb } from "@/lib/db/offlineDb";
import { parseStatementOnDevice } from "@/lib/banking/clientStatementParser";
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
  ReconciliationCockpit,
  ReconciliationStatsBar,
  BankTransactionCard,
  BankingModalsContainer,
} from "@/components/banking";

const isValidId = (id: unknown): id is string =>
  typeof id === "string" && id.trim() !== "" && id !== "undefined" && id !== "null";

export default function BankingPage() {
  const router = useRouter();
  const { toast } = useToast();

  const { activeCompany, companyId: activeCompanyId, availableCompanies } = useCompany();
  const { activeFY } = useFinancialYear();
  const { fromDate, toDate, displayPeriod, isCustomPeriod } = useAccountingPeriod();
  const [companyId, setCompanyId] = useState<string>(isValidId(activeCompanyId) ? activeCompanyId : "");

  const sisterCompanies = useMemo(() => {
    if (!availableCompanies) return [];
    return availableCompanies.filter((c) => c.id !== companyId);
  }, [availableCompanies, companyId]);

  const [bankLedgers, setBankLedgers] = useState<BankLedger[]>([]);
  const [selectedBankId, setSelectedBankId] = useState<string>("");
  const [allLedgers, setAllLedgers] = useState<any[]>([]);
  const [isAddBankOpen, setIsAddBankOpen] = useState<boolean>(false);

  const effectiveStartDate = fromDate || activeFY?.start_date;
  const effectiveEndDate = toDate || activeFY?.end_date;

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
  const [isCachedLocally, setIsCachedLocally] = useState<boolean>(false);
  const [uploadProgress, setUploadProgress] = useState<{
    current: number;
    total: number;
    phase: "idle" | "parsing" | "ingesting";
  }>({ current: 0, total: 0, phase: "idle" });
  const fileInputRef = useRef<HTMLInputElement>(null);

  const computeStatementHash = async (file: File, bankId: string, compId: string): Promise<string> => {
    try {
      const buffer = await file.arrayBuffer();
      const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
      const hashArray = Array.from(new Uint8Array(hashBuffer));
      const rawHex = hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
      return `stmt_v2_${compId}_${bankId}_${rawHex}`;
    } catch (err) {
      console.warn("[Banking] Web Crypto SHA-256 unavailable, falling back to name/size hash:", err);
      return `stmt_v2_${compId}_${bankId}_${file.name}_${file.size}_${file.lastModified}`;
    }
  };

  useEffect(() => {
    let active = true;
    if (uploadFile && selectedBankId && isValidId(companyId)) {
      computeStatementHash(uploadFile, selectedBankId, companyId).then((key) => {
        offlineDb.ocrCache.get(key).then((cached) => {
          if (active) {
            setIsCachedLocally(Boolean(cached && cached.result));
          }
        }).catch(() => {
          if (active) setIsCachedLocally(false);
        });
      });
    } else {
      setIsCachedLocally(false);
    }
    return () => { active = false; };
  }, [uploadFile, selectedBankId, companyId]);

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
  const [actionTargetCompanyId, setActionTargetCompanyId] = useState<string>("");
  const [actionExpenseLedgerId, setActionExpenseLedgerId] = useState<string>("");
  const [actionTransferLedgerId, setActionTransferLedgerId] = useState<string>("");
  const [actionRemarks, setActionRemarks] = useState<string>("");
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [directionTogglingId, setDirectionTogglingId] = useState<string | null>(null);
  const [resolvingTxId, setResolvingTxId] = useState<string | null>(null);
  const [isBulkResolving, setIsBulkResolving] = useState<boolean>(false);

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

  const fetchTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (isValidId(companyId)) {
      if (fetchTimeoutRef.current) {
        clearTimeout(fetchTimeoutRef.current);
      }
      fetchTimeoutRef.current = setTimeout(() => {
        fetchTransactionsAndSummary();
      }, 150);
    }
    return () => {
      if (fetchTimeoutRef.current) {
        clearTimeout(fetchTimeoutRef.current);
      }
    };
  }, [companyId, selectedBankId, activeTab, activeFY?.id, fromDate, toDate]);

  const getHeaders = () => {
    const token = getAccessToken();
    const headers: Record<string, string> = {
      "X-Company-ID": companyId,
    };
    if (activeFY?.id) {
      headers["X-Financial-Year-ID"] = activeFY.id;
    }
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    return headers;
  };

  const isBankLedger = (l: any) => {
    const type = String(l.ledgerType || l.ledger_type || "").toUpperCase();
    if (type === "BANK" || type === "BANK_OD" || type === "BANK_OCC") return true;
    const groupName = String(l.group?.name || l.group_name || l.group || "").toLowerCase();
    if (groupName.includes("bank") && !groupName.includes("loan") && !groupName.includes("borrowing")) return true;
    return false;
  };

  const handleBankAdded = (newLedger: any) => {
    setAllLedgers((prev) => [newLedger, ...prev]);
    const formattedBank: BankLedger = {
      id: String(newLedger.id),
      name: newLedger.name,
      ledger_type: newLedger.ledger_type || "BANK",
      ledgerType: newLedger.ledger_type || "BANK",
      currentBalance: Number(newLedger.current_balance ?? newLedger.opening_balance ?? 0),
      current_balance: Number(newLedger.current_balance ?? newLedger.opening_balance ?? 0),
      group: newLedger.group_name || "Bank Accounts",
    };
    setBankLedgers((prev) => {
      const exists = prev.some((b) => b.id === formattedBank.id);
      return exists ? prev : [formattedBank, ...prev];
    });
    setSelectedBankId(String(newLedger.id));
    ledgersRepository.refreshLedgers(companyId);
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
        const compRes = await api.get(`${API_BASE_URL}/api/v1/companies/`, {
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

      const banks = (rawLedgers as any[]).filter(isBankLedger);
      setBankLedgers(banks);

      if (banks.length > 0 && !selectedBankId) {
        setSelectedBankId(banks[0].id);
      }

      // Background fresh sync from server to ensure latest expense accounts and groups
      ledgersRepository.refreshLedgers(cid).then((refreshed) => {
        if (refreshed && refreshed.length > 0) {
          setAllLedgers(refreshed as any[]);
          const freshBanks = (refreshed as any[]).filter(isBankLedger);
          if (freshBanks.length > 0) {
            setBankLedgers(freshBanks as any[]);
            setSelectedBankId((prev) => prev || freshBanks[0].id);
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
      if (activeFY?.id) {
        params.financial_year_id = activeFY.id;
      }
      if (effectiveStartDate) {
        params.start_date = effectiveStartDate;
      }
      if (effectiveEndDate) {
        params.end_date = effectiveEndDate;
      }

      if (typeof window !== "undefined" && !navigator.onLine && selectedBankId) {
        const cachedTxs = await bankTransactionsRepository.getByBankLedger(selectedBankId);
        if (cachedTxs && cachedTxs.length > 0) {
          const filteredByPeriod = cachedTxs.filter((t: any) => {
            if (effectiveStartDate && t.transaction_date < effectiveStartDate) return false;
            if (effectiveEndDate && t.transaction_date > effectiveEndDate) return false;
            return true;
          });
          setTransactions(filteredByPeriod as any[]);
          setLoading(false);
          if (isManualRefresh) setRefreshing(false);
          return;
        }
      }

      const summaryParams: any = { company_id: companyId };
      if (selectedBankId) {
        summaryParams.bank_ledger_id = selectedBankId;
      }
      if (activeFY?.id) {
        summaryParams.financial_year_id = activeFY.id;
      }
      if (effectiveStartDate) {
        summaryParams.start_date = effectiveStartDate;
      }
      if (effectiveEndDate) {
        summaryParams.end_date = effectiveEndDate;
      }

      const [txRes, sumRes] = await Promise.all([
        api.get(`${API_BASE_URL}/api/v1/accounting/banking/transactions/`, {
          headers,
          params,
        }),
        api.get(`${API_BASE_URL}/api/v1/accounting/banking/summary/`, {
          headers,
          params: summaryParams,
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
    } catch (err: unknown) {
      console.error(err);
      let loadedFromCache = false;
      if (selectedBankId) {
        const cached = await bankTransactionsRepository.getByBankLedger(selectedBankId);
        if (cached && cached.length > 0) {
          setTransactions(cached as any[]);
          toast.info("Offline Mode", "Displaying locally cached bank transactions.");
          loadedFromCache = true;
        }
      }
      if (!loadedFromCache) {
        const errMsg = err instanceof Error ? err.message : "Failed to load bank transactions";
        toast.error("Banking Load Error", errMsg);
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
      const res = await api.get(`${API_BASE_URL}/api/v1/accounting/banking/mappings/`, {
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
      await api.delete(`${API_BASE_URL}/api/v1/accounting/banking/mappings/${mappingId}/`, {
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
      const res = await api.get(`${API_BASE_URL}/api/v1/accounting/banking/statements/`, {
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
      const res = await api.post(
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
      const res = await api.post(
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

  const handleToggleDirection = async (tx: BankTransactionItem) => {
    if (directionTogglingId) return;
    setDirectionTogglingId(tx.id);
    try {
      const headers = getHeaders();
      const res = await api.post(
        `${API_BASE_URL}/api/v1/accounting/banking/transactions/${tx.id}/toggle-direction/`,
        {},
        { headers }
      );

      const updatedTx = res.data.transaction;
      if (updatedTx) {
        setTransactions((prev) =>
          prev.map((t) => (t.id === tx.id ? { ...t, ...updatedTx } : t))
        );
        if (selectedTx && selectedTx.id === tx.id) {
          setSelectedTx((prev) => (prev ? { ...prev, ...updatedTx } : null));
          if (updatedTx.matched_party) {
            if (updatedTx.matched_party.ledger_type === "EXPENSE") {
              setActionType("RECORD_EXPENSE");
              setActionExpenseLedgerId(updatedTx.matched_party.id);
            } else {
              setActionTargetPartyId(updatedTx.matched_party.id);
            }
          } else {
            const newIsCredit = parseFloat(updatedTx.credit_amount) > 0;
            const desc = (updatedTx.description || updatedTx.normalized_narration || "").toLowerCase();
            const isExp = !newIsCredit && (
              desc.includes("interest") || desc.includes("charge") || desc.includes("chg") || desc.includes("fee") || desc.includes("sms") || desc.includes("folio")
            );
            if (isExp) {
              setActionType("RECORD_EXPENSE");
              let matchedExpId = "";
              if (desc.includes("interest")) {
                const intLedger = expenseLedgers.find((l) => l.name.toLowerCase().includes("interest"));
                if (intLedger) matchedExpId = intLedger.id;
              }
              if (!matchedExpId) {
                const chgLedger = expenseLedgers.find((l) =>
                  l.name.toLowerCase().includes("charge") || l.name.toLowerCase().includes("fee")
                );
                if (chgLedger) matchedExpId = chgLedger.id;
              }
              if (matchedExpId) setActionExpenseLedgerId(matchedExpId);
            }
          }
        }
        // Update local offline IndexedDB cache
        bankTransactionsRepository.bulkUpsert([{
          id: updatedTx.id,
          bank_ledger: updatedTx.bank_ledger?.id || selectedBankId,
          transaction_date: updatedTx.transaction_date,
          description: updatedTx.description,
          normalized_narration: updatedTx.normalized_narration,
          reference_number: updatedTx.reference_number,
          debit_amount: updatedTx.debit_amount,
          credit_amount: updatedTx.credit_amount,
          balance: updatedTx.balance,
          status: updatedTx.status,
          is_excluded: updatedTx.is_excluded,
          exclusion_reason: updatedTx.exclusion_reason,
          matched_party: updatedTx.matched_party,
          matched_voucher: updatedTx.matched_voucher,
          match_confidence: updatedTx.match_confidence,
          match_notes: updatedTx.match_notes,
          created_at: updatedTx.created_at || new Date().toISOString(),
          updated_at: updatedTx.updated_at || new Date().toISOString(),
        }]).catch((e: any) => console.warn("Failed to update cached bank transaction offline:", e));
      }

      toast.success(
        res.data.is_credit ? "Switched to Deposit (Credit)" : "Switched to Withdrawal (Debit)",
        res.data.message || "Transaction direction updated."
      );
      fetchTransactionsAndSummary(false);
    } catch (err: any) {
      console.error(err);
      toast.error(
        "Failed to change direction",
        err.response?.data?.error || err.message || "Could not toggle transaction direction."
      );
    } finally {
      setDirectionTogglingId(null);
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
      const res = await api.post(
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
      const res = await api.post(
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

    setIsUploading(true);
    setUploadProgress({ current: 0, total: 0, phase: "parsing" });
    try {
      const cacheKey = await computeStatementHash(uploadFile, selectedBankId, companyId);

      // Check if transactions were previously parsed and cached locally
      let allParsedTxs: any[] = [];
      let clientParsed: any = null;

      const cached = await offlineDb.ocrCache.get(cacheKey).catch(() => null);
      if (cached && Array.isArray(cached.transactions) && cached.transactions.length > 0) {
        console.log(`[PWA Cache] Reusing ${cached.transactions.length} pre-parsed transactions from local cache.`);
        allParsedTxs = cached.transactions;
        clientParsed = {
          transactions: cached.transactions,
          openingBalance: cached.openingBalance,
          closingBalance: cached.closingBalance,
          fileHash: cacheKey,
        };
      } else {
        // Step 1: Parse statement directly on client device (sub-second, 0 MB server load!)
        setUploadProgress({ current: 0, total: 0, phase: "parsing" });
        try {
          clientParsed = await parseStatementOnDevice(uploadFile);
          allParsedTxs = clientParsed?.transactions || [];
        } catch (parseErr) {
          console.warn("[Banking] Client-side parsing failed, falling back to server ingestion:", parseErr);
        }
      }

      // Step 2: Stream/push to backend in lightweight batches
      // This completely eliminates Gunicorn 30-second timeouts and Render 512MB RAM exhaustion!
      if (allParsedTxs.length > 0) {
        const BATCH_SIZE = 10;
        let totalImported = 0;
        let totalDuplicates = 0;
        let totalAutoMatched = 0;
        let lastBatchError: any = null;
        let successfulBatches = 0;
        const headers: Record<string, string> = { ...getHeaders() };

        setUploadProgress({ current: 0, total: allParsedTxs.length, phase: "ingesting" });

        for (let i = 0; i < allParsedTxs.length; i += BATCH_SIZE) {
          const chunk = allParsedTxs.slice(i, i + BATCH_SIZE);
          try {
            const res = await api.post(
              `/api/v1/accounting/banking/ingest-batch/`,
              {
                bank_ledger_id: selectedBankId,
                company_id: companyId,
                statement_info: {
                  filename: uploadFile.name,
                  file_hash: clientParsed?.fileHash || cacheKey,
                  total_rows: allParsedTxs.length,
                  opening_balance: clientParsed?.openingBalance,
                  closing_balance: clientParsed?.closingBalance,
                },
                transactions: chunk,
              },
              {
                headers,
                timeout: 30000,
              }
            );
            if (res.data) {
              totalImported += res.data.imported_count || 0;
              totalDuplicates += res.data.duplicates_count || 0;
              totalAutoMatched += res.data.auto_matched_count || 0;
              successfulBatches++;
            }
          } catch (batchErr: any) {
            lastBatchError = batchErr;
            console.warn(`[Banking] Batch ${Math.floor(i / BATCH_SIZE) + 1} push error:`, batchErr);
          }

          setUploadProgress({
            current: Math.min(i + BATCH_SIZE, allParsedTxs.length),
            total: allParsedTxs.length,
            phase: "ingesting",
          });
        }

        if (successfulBatches === 0 && lastBatchError) {
          // If server push failed, delete stale cache entry so un-synced state doesn't block future attempts
          await offlineDb.ocrCache.delete(cacheKey).catch(() => {});
          throw lastBatchError;
        }

        const finalSummary = {
          import_id: `stmt_${cacheKey}`,
          source_file: uploadFile.name,
          file_hash: cacheKey,
          status: "COMPLETED",
          total_detected: allParsedTxs.length,
          total_rows: allParsedTxs.length,
          successful_rows: allParsedTxs.length,
          imported_count: totalImported,
          duplicates_detected: totalDuplicates,
          auto_matched_count: totalAutoMatched,
          opening_balance: clientParsed?.openingBalance,
          closing_balance: clientParsed?.closingBalance,
        };
        setUploadResult(finalSummary);

        // Update local cache with verified transactions and server sync state
        await offlineDb.ocrCache.put({
          fileHash: cacheKey,
          fileName: uploadFile.name,
          fileSize: uploadFile.size,
          transactions: allParsedTxs,
          openingBalance: clientParsed?.openingBalance,
          closingBalance: clientParsed?.closingBalance,
          result: finalSummary,
          is_synced: true,
          cachedAt: Date.now(),
        }).catch(() => {});

        toast.success(
          "Statement ingested successfully",
          `Parsed ${allParsedTxs.length} rows on device: ${totalImported} imported to books, ${totalDuplicates} duplicates skipped.`
        );
        fetchTransactionsAndSummary();
        setIsUploading(false);
        setUploadProgress({ current: 0, total: 0, phase: "idle" });
        return;
      }

      // Step 3: Fallback path for scanned/image PDFs (server vision OCR)
      if (typeof window !== "undefined" && !navigator.onLine) {
        toast.error("Offline", "Internet connection required to upload new (uncached) bank statements.");
        setIsUploading(false);
        setUploadProgress({ current: 0, total: 0, phase: "idle" });
        return;
      }

      const headers: Record<string, string> = { ...getHeaders() };
      let res;
      try {
        const formData = new FormData();
        formData.append("file", uploadFile);
        formData.append("bank_ledger_id", selectedBankId);
        formData.append("company_id", companyId);

        res = await api.post(`/api/v1/accounting/banking/upload/`, formData, {
          headers,
          timeout: 90000,
        });
      } catch (uploadErr: any) {
        const isNetworkErr = !uploadErr.response && (uploadErr.code === "ERR_NETWORK" || uploadErr.message?.toLowerCase().includes("network"));
        if (isNetworkErr && uploadFile.size < 12 * 1024 * 1024) {
          console.warn("[Banking] Multipart upload network interrupted, retrying via JSON base64 channel...");
          const b64 = await new Promise<string>((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result as string);
            reader.onerror = reject;
            reader.readAsDataURL(uploadFile);
          });
          res = await api.post(
            `/api/v1/accounting/banking/upload/`,
            {
              file_base64: b64,
              filename: uploadFile.name,
              bank_ledger_id: selectedBankId,
              company_id: companyId,
            },
            {
              headers: {
                ...headers,
                "Content-Type": "application/json",
              },
              timeout: 90000,
            }
          );
        } else {
          throw uploadErr;
        }
      }

      if (cacheKey && res.data) {
        await offlineDb.ocrCache.put({
          fileHash: cacheKey,
          fileName: uploadFile.name,
          fileSize: uploadFile.size,
          result: res.data,
          cachedAt: Date.now(),
        }).catch((cacheErr) => console.warn("[PWA Cache] Failed to persist statement cache:", cacheErr));
      }

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
      const isNetworkErr = !err.response && (err.code === "ERR_NETWORK" || err.message?.toLowerCase().includes("network"));
      const errMsg = isNetworkErr
        ? "Network connection interrupted while uploading. The server may be processing or restarting. Please verify your connection and retry in a few moments."
        : (err.response?.data?.error || err.response?.data?.detail || err.message || "Invalid or unparseable statement file.");
      toast.error(
        "Upload failed",
        errMsg
      );
    } finally {
      setIsUploading(false);
      setUploadProgress({ current: 0, total: 0, phase: "idle" });
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
    setActionTargetCompanyId(sisterCompanies.length > 0 ? sisterCompanies[0].id : "");
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
    if (newType === "TRIANGULAR_SETTLEMENT" && !actionTargetCompanyId && sisterCompanies.length > 0) {
      setActionTargetCompanyId(sisterCompanies[0].id);
    }
  };

  const closeActionModal = () => {
    setSelectedTx(null);
    setActionType(null);
    setActionTargetCompanyId("");
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
      } else if (actionType === "TRIANGULAR_SETTLEMENT") {
        if (!actionTargetCompanyId) {
          toast.warning("Missing Sister Company", "Please select the sister entity for this transaction.");
          setActionLoading(false);
          return;
        }
        payload.target_company_id = actionTargetCompanyId;
        if (actionTargetPartyId) {
          payload.target_party_id = actionTargetPartyId;
        }
        payload.narration = actionRemarks || selectedTx.description;
      } else if (actionType === "OWNER_DRAWING") {
        payload.narration = actionRemarks || "Proprietor / Partner Drawings";
      } else if (actionType === "IGNORE") {
        payload.reason = actionRemarks || "Ignored by user";
      }

      const res = await api.post(
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

  const handleOneClickConfirm = async (tx: BankTransactionItem) => {
    if (resolvingTxId) return;
    setResolvingTxId(tx.id);
    try {
      const headers = getHeaders();
      const isExpenseMatch =
        tx.matched_party?.ledger_type === "EXPENSE" ||
        (typeof tx.match_notes === "object" && (tx.match_notes as any)?.is_bank_expense);

      const actionType = isExpenseMatch ? "RECORD_EXPENSE" : "MATCH_PARTY";
      const payload: any = isExpenseMatch
        ? { expense_ledger_id: tx.matched_party?.id, narration: tx.description }
        : { party_id: tx.matched_party?.id, narration: tx.description };

      const res = await api.post(
        `${API_BASE_URL}/api/v1/accounting/banking/transactions/${tx.id}/resolve/`,
        { action: actionType, payload },
        { headers }
      );

      toast.success(
        "Transaction Reconciled",
        res.data.voucher_number
          ? `Balanced Voucher ${res.data.voucher_number} created and reconciled.`
          : res.data.message || "Reconciled successfully."
      );
      await fetchTransactionsAndSummary();
    } catch (err: any) {
      console.error(err);
      toast.error(
        "Resolution Failed",
        err.response?.data?.error || err.message || "Could not reconcile transaction."
      );
    } finally {
      setResolvingTxId(null);
    }
  };

  const handleInlineResolve = async (
    tx: BankTransactionItem,
    actionType: BankingActionType,
    payload: any
  ) => {
    if (resolvingTxId) return;
    setResolvingTxId(tx.id);
    try {
      const headers = getHeaders();
      const res = await api.post(
        `${API_BASE_URL}/api/v1/accounting/banking/transactions/${tx.id}/resolve/`,
        { action: actionType, payload },
        { headers }
      );

      toast.success(
        "Transaction Reconciled",
        res.data.voucher_number
          ? `Balanced Voucher ${res.data.voucher_number} created and applied.`
          : res.data.message || "Reconciled successfully."
      );
      await fetchTransactionsAndSummary();
    } catch (err: any) {
      console.error(err);
      toast.error(
        "Resolution Failed",
        err.response?.data?.error || err.message || "Could not complete resolution action."
      );
    } finally {
      setResolvingTxId(null);
    }
  };

  const handleBulkResolve = async () => {
    if (!summary?.needs_review_count || summary.needs_review_count === 0) {
      toast.info("No Transactions", "There are no suggested transactions pending review.");
      return;
    }

    if (!window.confirm(`Auto-confirm and reconcile all ${summary.needs_review_count} suggested bank matches?`)) {
      return;
    }

    setIsBulkResolving(true);
    try {
      const headers = getHeaders();
      const res = await api.post(
        `${API_BASE_URL}/api/v1/accounting/banking/transactions/bulk-resolve/`,
        { company_id: companyId, min_confidence: 75 },
        { headers }
      );

      if (res.data?.success) {
        toast.success(
          "Bulk Reconciliation Complete",
          `Successfully auto-confirmed ${res.data.resolved_count} transactions (Total: ₹${res.data.total_amount}).`
        );
        fetchTransactionsAndSummary();
      } else {
        toast.error("Bulk Reconciliation", res.data?.message || "No transactions resolved.");
      }
    } catch (err: any) {
      console.error("Bulk resolve error:", err);
      toast.error(
        "Bulk Reconciliation Failed",
        err.response?.data?.error || err.message || "Could not bulk-resolve transactions."
      );
    } finally {
      setIsBulkResolving(false);
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
            <div className="flex items-center gap-2.5 flex-wrap">
              <div className="p-2 rounded-xl bg-blue-500/10 text-blue-500">
                <Landmark className="w-5 h-5" />
              </div>
              <h1 className="text-xl sm:text-2xl font-extrabold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">
                Banking
              </h1>
              {isCustomPeriod ? (
                <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20">
                  {displayPeriod}
                </span>
              ) : activeFY ? (
                <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-primary/10 text-primary border border-primary/20">
                  FY {activeFY.code} ({activeFY.start_date} to {activeFY.end_date})
                </span>
              ) : null}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Upload bank statements and match transactions for {isCustomPeriod ? displayPeriod : activeFY ? `FY ${activeFY.code}` : "the selected period"}
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

        {/* Hero Reconciliation Cockpit */}
        <ReconciliationCockpit
          selectedBankId={selectedBankId}
          onSelectBankId={setSelectedBankId}
          bankLedgers={bankLedgers}
          bankOptions={bankOptions}
          onAddNewBank={() => setIsAddBankOpen(true)}
          summary={summary}
          activeTab={activeTab}
          onSelectTab={setActiveTab}
        />

        {/* Filter Tabs & Search Bar */}
        <ReconciliationStatsBar
          summary={summary}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          onBulkResolve={handleBulkResolve}
          isBulkResolving={isBulkResolving}
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
                {transactions.length === 0 && activeFY
                  ? `No bank transactions recorded for FY ${activeFY.code} (${activeFY.start_date} to ${activeFY.end_date}). Upload a statement or switch financial years.`
                  : activeTab === "UNRESOLVED"
                  ? "There are no transactions requiring your attention. Upload a new statement to import more."
                  : activeTab === "NEEDS_REVIEW"
                  ? "SriLekh hasn't found any AI-suggested matches. Upload another statement or check the Attention tab."
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
                  onToggleDirection={handleToggleDirection}
                  isTogglingDirection={directionTogglingId === tx.id}
                  onExclude={handleExcludeTransaction}
                  onRestore={handleRestoreTransaction}
                  onViewVouchers={() => router.push("/vouchers")}
                  partyOptions={partyOptions}
                  expenseOptions={expenseOptions}
                  contraOptions={contraOptions}
                  sisterCompanies={sisterCompanies}
                  onOneClickConfirm={handleOneClickConfirm}
                  onInlineResolve={handleInlineResolve}
                  isResolving={resolvingTxId === tx.id}
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
          isCachedLocally={isCachedLocally}
          uploadProgress={uploadProgress}
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
          onToggleDirection={handleToggleDirection}
          isTogglingDirection={directionTogglingId === selectedTx?.id}
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
          sisterCompanies={sisterCompanies}
          actionTargetCompanyId={actionTargetCompanyId}
          onTargetCompanyChange={setActionTargetCompanyId}
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

        <AddBankModal
          isOpen={isAddBankOpen}
          onClose={() => setIsAddBankOpen(false)}
          companyId={companyId}
          onSuccess={handleBankAdded}
        />
      </div>
    </DashboardLayout>
  );
}
