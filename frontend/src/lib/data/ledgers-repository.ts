import { offlineDb, SyncedLedger } from "../db/offlineDb";
import axios from "axios";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken } from "@/utils/auth";

export interface LedgerQueryOptions {
  ledgerType?: string;
  search?: string;
  financialYearId?: string;
  startDate?: string;
  endDate?: string;
  asOfDate?: string;
  forceRemote?: boolean;
}

export interface PartyQueryOptions {
  role?: "CUSTOMER" | "SUPPLIER" | "BOTH";
  search?: string;
  financialYearId?: string;
  startDate?: string;
  endDate?: string;
  asOfDate?: string;
  forceRemote?: boolean;
}

export class LedgersRepository {
  private _applyFilters(ledgers: SyncedLedger[], options: LedgerQueryOptions): SyncedLedger[] {
    let filtered = ledgers;
    if (options.ledgerType && options.ledgerType !== "ALL") {
      filtered = filtered.filter((l) => l.ledgerType === options.ledgerType);
    }
    if (options.search) {
      const q = options.search.trim().toLowerCase();
      filtered = filtered.filter(
        (l) =>
          l.name.toLowerCase().includes(q) ||
          (l.gstin && l.gstin.toLowerCase().includes(q)) ||
          (l.phone && l.phone.includes(q))
      );
    }
    return filtered;
  }

  /**
   * Reads ledgers locally from IndexedDB, or fetches from server if scoped or empty.
   */
  async getLedgers(companyId: string, options: LedgerQueryOptions = {}): Promise<{ data: SyncedLedger[]; isLocal: boolean }> {
    if (!companyId) return { data: [], isLocal: true };

    const requiresRemote = Boolean(
      options.financialYearId || options.startDate || options.endDate || options.asOfDate || options.forceRemote
    );

    if (requiresRemote) {
      try {
        const token = getAccessToken();
        if (token) {
          const headers = { Authorization: `Bearer ${token}`, "X-Company-ID": companyId };
          const params: Record<string, string> = {};
          if (options.financialYearId) params.financial_year_id = options.financialYearId;
          if (options.startDate) params.start_date = options.startDate;
          if (options.endDate) params.end_date = options.endDate;
          if (options.asOfDate) params.as_of_date = options.asOfDate;
          const res = await axios.get(`${API_BASE_URL}/api/v1/ledgers/${companyId}/`, { headers, params, timeout: 6000 });
          const raw = res.data?.data || (Array.isArray(res.data) ? res.data : []);
          if (raw.length > 0) {
            const mapped: SyncedLedger[] = raw.map((l: any) => ({
              id: String(l.id),
              companyId,
              name: l.name,
              ledgerType: l.ledger_type || l.canonical_role || "GENERAL",
              group: l.group || l.group_name || "",
              group_id: l.group_id || "",
              nature: l.nature || "ASSET",
              gstin: l.gstin || "",
              stateCode: l.state_code || "",
              currentBalance: Number(l.current_balance) || 0,
              openingBalance: Number(l.opening_balance) || 0,
              openingBalanceType: l.opening_balance_type || "DEBIT",
              phone: l.phone || "",
              balanceState: l.balance_state,
              displayAmount: Number(l.display_amount) || 0,
              normalBalance: l.normal_balance,
              balanceDirection: l.balance_direction,
              serverUpdatedAt: Date.now(),
            }));
            return { data: this._applyFilters(mapped, options), isLocal: false };
          }
        }
      } catch (err) {
        console.warn("[LedgersRepo] Scoped fetch failed, falling back to local:", err);
      }
    }

    let ledgers = await offlineDb.syncedLedgers
      .where("companyId")
      .equals(companyId)
      .toArray();

    // Server fallback if local read model is empty
    if (ledgers.length === 0) {
      try {
        const token = getAccessToken();
        if (token) {
          const headers = { Authorization: `Bearer ${token}`, "X-Company-ID": companyId };
          const res = await axios.get(`${API_BASE_URL}/api/v1/ledgers/${companyId}/`, { headers, timeout: 5000 });
          const raw = res.data?.data || (Array.isArray(res.data) ? res.data : []);
          if (raw.length > 0) {
            const toPut: SyncedLedger[] = raw.map((l: any) => ({
              id: String(l.id),
              companyId,
              name: l.name,
              ledgerType: l.ledger_type || l.canonical_role || "GENERAL",
              group: l.group || l.group_name || "",
              group_id: l.group_id || "",
              nature: l.nature || "ASSET",
              gstin: l.gstin || "",
              stateCode: l.state_code || "",
              currentBalance: Number(l.current_balance) || 0,
              openingBalance: Number(l.opening_balance) || 0,
              openingBalanceType: l.opening_balance_type || "DEBIT",
              phone: l.phone || "",
              balanceState: l.balance_state,
              displayAmount: Number(l.display_amount) || 0,
              normalBalance: l.normal_balance,
              balanceDirection: l.balance_direction,
              serverUpdatedAt: Date.now(),
            }));
            await offlineDb.syncedLedgers.bulkPut(toPut);
            ledgers = toPut;
          }
        }
      } catch (err) {
        console.warn("[LedgersRepo] Fallback fetch failed:", err);
      }
    }

    const filtered = this._applyFilters(ledgers, options);

    if (process.env.NODE_ENV === "development") {
      console.log(`[LOCAL] ledgers query (count=${filtered.length})`);
    }

    return { data: filtered, isLocal: true };
  }

  /**
   * Returns parties (Customers, Suppliers, Both) formatted for party screens.
   */
  async getParties(companyId: string, options: PartyQueryOptions = {}): Promise<{ data: any[]; isLocal: boolean }> {
    const { data: allLedgers } = await this.getLedgers(companyId, options);

    const partyLedgers = allLedgers.filter((l) => {
      const t = (l.ledgerType || "").toUpperCase();
      return (
        t === "CUSTOMER" ||
        t === "SUPPLIER" ||
        t === "PARTY" ||
        t === "BOTH" ||
        t.includes("DEBTOR") ||
        t.includes("CREDITOR")
      );
    });

    const formatted = partyLedgers.map((l) => {
      const t = (l.ledgerType || "").toUpperCase();
      const isCust = t === "CUSTOMER" || t.includes("DEBTOR");
      const isSupp = t === "SUPPLIER" || t.includes("CREDITOR");
      const isBoth = t === "BOTH" || (isCust && isSupp);
      const role = isBoth ? "BOTH" : isCust ? "CUSTOMER" : "SUPPLIER";

      return {
        id: l.id,
        name: l.name,
        ledger_type: l.ledgerType,
        canonical_role: role,
        role,
        type: role === "BOTH" ? "Both" : role === "CUSTOMER" ? "Customer" : "Supplier",
        gstin: l.gstin || "",
        state_code: l.stateCode || "",
        phone: l.phone || "",
        current_balance: l.currentBalance,
        opening_balance: l.openingBalance,
        opening_balance_type: l.openingBalanceType,
        balance_state: l.balanceState,
        display_amount: l.displayAmount,
        normal_balance: l.normalBalance,
        balance_direction: l.balanceDirection,
      };
    });

    let result = formatted;
    if (options.role && options.role !== "BOTH") {
      result = result.filter((p) => p.role === options.role || p.role === "BOTH");
    }
    if (options.search) {
      const q = options.search.trim().toLowerCase();
      result = result.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          (p.gstin && p.gstin.toLowerCase().includes(q)) ||
          (p.phone && p.phone.includes(q))
      );
    }

    return { data: result, isLocal: true };
  }

  async refreshLedgers(companyId: string): Promise<SyncedLedger[]> {
    if (!companyId) return [];
    try {
      const token = getAccessToken();
      if (!token) return [];
      const headers = { Authorization: `Bearer ${token}`, "X-Company-ID": companyId };
      const res = await axios.get(`${API_BASE_URL}/api/v1/ledgers/${companyId}/`, { headers, timeout: 5000 });
      const raw = res.data?.data || (Array.isArray(res.data) ? res.data : []);
      if (raw.length > 0) {
        const toPut: SyncedLedger[] = raw.map((l: any) => ({
          id: String(l.id),
          companyId,
          name: l.name,
          ledgerType: l.ledger_type || l.canonical_role || "GENERAL",
          group: l.group || l.group_name || "",
          group_id: l.group_id || "",
          nature: l.nature || "ASSET",
          gstin: l.gstin || "",
          stateCode: l.state_code || "",
          currentBalance: Number(l.current_balance) || 0,
          openingBalance: Number(l.opening_balance) || 0,
          openingBalanceType: l.opening_balance_type || "DEBIT",
          phone: l.phone || "",
          balanceState: l.balance_state,
          displayAmount: Number(l.display_amount) || 0,
          normalBalance: l.normal_balance,
          balanceDirection: l.balance_direction,
          serverUpdatedAt: Date.now(),
        }));
        await offlineDb.syncedLedgers.bulkPut(toPut);
        return toPut;
      }
    } catch (err) {
      console.warn("[LedgersRepo] Refresh failed:", err);
    }
    return [];
  }

  async saveLedgers(companyId: string, ledgers: SyncedLedger[]): Promise<void> {
    if (!ledgers || ledgers.length === 0) return;
    await offlineDb.syncedLedgers.bulkPut(ledgers);
  }
}

export const ledgersRepository = new LedgersRepository();
