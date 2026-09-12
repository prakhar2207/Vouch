import { offlineDb, SyncedLedger } from "../db/offlineDb";
import axios from "axios";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken } from "@/utils/auth";

export interface LedgerQueryOptions {
  ledgerType?: string;
  search?: string;
}

export interface PartyQueryOptions {
  role?: "CUSTOMER" | "SUPPLIER" | "BOTH";
  search?: string;
}

export class LedgersRepository {
  /**
   * Reads ledgers locally from IndexedDB.
   * If not yet populated, fetches once from server and caches locally.
   */
  async getLedgers(companyId: string, options: LedgerQueryOptions = {}): Promise<{ data: SyncedLedger[]; isLocal: boolean }> {
    if (!companyId) return { data: [], isLocal: true };

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

    if (process.env.NODE_ENV === "development") {
      console.log(`[LOCAL] ledgers query (count=${filtered.length})`);
    }

    return { data: filtered, isLocal: true };
  }

  /**
   * Returns parties (Customers, Suppliers, Both) formatted for party screens.
   */
  async getParties(companyId: string, options: PartyQueryOptions = {}): Promise<{ data: any[]; isLocal: boolean }> {
    const { data: allLedgers } = await this.getLedgers(companyId);

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

  async saveLedgers(companyId: string, ledgers: SyncedLedger[]): Promise<void> {
    if (!ledgers || ledgers.length === 0) return;
    await offlineDb.syncedLedgers.bulkPut(ledgers);
  }
}

export const ledgersRepository = new LedgersRepository();
