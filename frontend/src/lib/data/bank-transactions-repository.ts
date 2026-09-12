import { offlineDb, SyncedBankTransaction } from "../db/offlineDb";
import axios from "axios";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken } from "@/utils/auth";

export interface BankTransactionQueryOptions {
  bankLedgerId?: string;
  status?: string;
  search?: string;
  page?: number;
  pageSize?: number;
  forceRefresh?: boolean;
}

export interface BankTransactionQueryResult {
  data: any[];
  totalCount: number;
  page: number;
  pageSize: number;
  isLocal: boolean;
}

export class BankTransactionsRepository {
  /**
   * Reads bank transactions locally from IndexedDB.
   * If not yet populated or forceRefresh is true, fetches from server and stores in IndexedDB.
   */
  async getTransactions(companyId: string, options: BankTransactionQueryOptions = {}): Promise<BankTransactionQueryResult> {
    if (!companyId) {
      return { data: [], totalCount: 0, page: 1, pageSize: options.pageSize || 50, isLocal: true };
    }

    const page = Math.max(1, options.page || 1);
    const pageSize = Math.max(1, options.pageSize || 50);

    let txs = await offlineDb.syncedBankTransactions
      .where("companyId")
      .equals(companyId)
      .toArray();

    // Server fallback if local bank transactions store is unpopulated or forceRefresh requested
    if (txs.length === 0 || options.forceRefresh) {
      try {
        const token = getAccessToken();
        if (token) {
          const headers = { Authorization: `Bearer ${token}`, "X-Company-ID": companyId };
          const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/banking/transactions/`, {
            headers,
            params: { company_id: companyId, page_size: 100 },
            timeout: 6000,
          });
          const raw = res.data?.results || (Array.isArray(res.data) ? res.data : []);
          if (raw.length > 0) {
            const toPut: SyncedBankTransaction[] = raw.map((t: any) => ({
              id: String(t.id),
              companyId,
              bankLedgerId: t.bank_ledger?.id || "",
              bankLedgerName: t.bank_ledger?.name || "",
              transactionDate: t.transaction_date,
              valueDate: t.value_date || null,
              description: t.description || "",
              normalizedNarration: t.normalized_narration || "",
              referenceNumber: t.reference_number || "",
              debitAmount: Number(t.debit_amount) || 0,
              creditAmount: Number(t.credit_amount) || 0,
              balance: t.balance !== null && t.balance !== undefined ? Number(t.balance) : null,
              status: t.status || "UNRESOLVED",
              matchedPartyId: t.matched_party?.id || null,
              matchedPartyName: t.matched_party?.name || null,
              matchedPartyType: t.matched_party?.ledger_type || null,
              matchedVoucherId: t.matched_voucher?.id || null,
              matchedVoucherNumber: t.matched_voucher?.voucher_number || null,
              matchConfidence: t.match_confidence || 0,
              matchNotes: t.match_notes || "",
              serverUpdatedAt: Date.now(),
            }));
            await offlineDb.syncedBankTransactions.bulkPut(toPut);
            txs = await offlineDb.syncedBankTransactions
              .where("companyId")
              .equals(companyId)
              .toArray();
          }
        }
      } catch (err) {
        console.warn("[BankRepo] Server fallback fetch failed:", err);
      }
    }

    let filtered = txs;

    if (options.bankLedgerId && options.bankLedgerId !== "ALL" && options.bankLedgerId !== "") {
      filtered = filtered.filter((t) => t.bankLedgerId === options.bankLedgerId);
    }

    if (options.status && options.status !== "ALL") {
      const rawStatuses = options.status.split(",").map((s) => s.trim().toUpperCase());
      const resolvedStatuses: string[] = [];
      for (const s of rawStatuses) {
        if (s === "NEEDS_REVIEW") {
          resolvedStatuses.push("MATCHED_SUGGESTED", "NEEDS_REVIEW");
        } else if (s === "MATCHED") {
          resolvedStatuses.push("MATCHED_AUTO", "RECONCILED");
        } else if (s === "UNRESOLVED") {
          resolvedStatuses.push("UNRESOLVED", "UNPROCESSED");
        } else {
          resolvedStatuses.push(s);
        }
      }
      filtered = filtered.filter((t) => resolvedStatuses.includes(t.status));
    }

    if (options.search) {
      const q = options.search.trim().toUpperCase();
      filtered = filtered.filter(
        (t) =>
          (t.normalizedNarration && t.normalizedNarration.toUpperCase().includes(q)) ||
          (t.description && t.description.toUpperCase().includes(q)) ||
          (t.referenceNumber && t.referenceNumber.toUpperCase().includes(q))
      );
    }

    // Sort newest transaction date first
    filtered.sort((a, b) => b.transactionDate.localeCompare(a.transactionDate));

    // Map to the shape expected by BankingPage
    const mapped = filtered.map((t) => ({
      id: t.id,
      transaction_date: t.transactionDate,
      value_date: t.valueDate,
      description: t.description,
      normalized_narration: t.normalizedNarration,
      reference_number: t.referenceNumber,
      debit_amount: String(t.debitAmount),
      credit_amount: String(t.creditAmount),
      balance: t.balance !== null ? String(t.balance) : null,
      status: t.status,
      bank_ledger: { id: t.bankLedgerId, name: t.bankLedgerName || "Bank" },
      matched_party: t.matchedPartyId
        ? { id: t.matchedPartyId, name: t.matchedPartyName, ledger_type: t.matchedPartyType || "CUSTOMER" }
        : null,
      matched_voucher: t.matchedVoucherId
        ? { id: t.matchedVoucherId, voucher_number: t.matchedVoucherNumber }
        : null,
      match_confidence: t.matchConfidence,
      match_notes: t.matchNotes,
    }));

    const totalCount = mapped.length;
    const offset = (page - 1) * pageSize;
    const pagedData = mapped.slice(offset, offset + pageSize);

    if (process.env.NODE_ENV === "development") {
      console.log(`[LOCAL] bank transactions query (count=${pagedData.length}, total=${totalCount})`);
    }

    return {
      data: pagedData,
      totalCount,
      page,
      pageSize,
      isLocal: true,
    };
  }

  async saveTransactions(companyId: string, transactions: SyncedBankTransaction[]): Promise<void> {
    if (!transactions || transactions.length === 0) return;
    await offlineDb.syncedBankTransactions.bulkPut(transactions);
  }

  async updateTransactionStatus(id: string, updates: Partial<SyncedBankTransaction>): Promise<void> {
    const existing = await offlineDb.syncedBankTransactions.get(id);
    if (existing) {
      await offlineDb.syncedBankTransactions.put({
        ...existing,
        ...updates,
        serverUpdatedAt: Date.now(),
      });
    }
  }
}

export const bankTransactionsRepository = new BankTransactionsRepository();
