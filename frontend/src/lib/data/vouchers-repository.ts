import { offlineDb, SyncedVoucher, OfflineVoucher } from "../db/offlineDb";
import axios from "axios";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken } from "@/utils/auth";

export interface VoucherQueryOptions {
  type?: string | string[];
  status?: string;
  search?: string;
  startDate?: string;
  endDate?: string;
  page?: number;
  pageSize?: number;
}

export interface VoucherQueryResult {
  data: any[];
  totalCount: number;
  page: number;
  pageSize: number;
  totalPages: number;
  offset: number;
  hasMore: boolean;
  isLocal: boolean;
  totalPayments?: number;
  totalReceipts?: number;
}

export class VouchersRepository {
  /**
   * Retrieves vouchers using local IndexedDB read model with outbox merge.
   * Falls back to server only if local read model is unpopulated.
   */
  async getVouchers(companyId: string, options: VoucherQueryOptions = {}): Promise<VoucherQueryResult> {
    if (!companyId) {
      return { data: [], totalCount: 0, page: 1, pageSize: options.pageSize || 50, totalPages: 0, offset: 0, hasMore: false, isLocal: true };
    }

    const page = Math.max(1, options.page || 1);
    const pageSize = Math.max(1, options.pageSize || 50);

    // 1. Query local synced vouchers
    let localVouchers = await offlineDb.syncedVouchers
      .where("companyId")
      .equals(companyId)
      .toArray();

    // If local storage is empty, attempt initial fallback fetch
    if (localVouchers.length === 0) {
      try {
        const token = getAccessToken();
        if (token) {
          const headers = { Authorization: `Bearer ${token}`, "X-Company-ID": companyId };
          const typeParam = Array.isArray(options.type) ? options.type.join(",") : (options.type || "");
          const url = `${API_BASE_URL}/api/v1/accounting/vouchers/${companyId}/?limit=100${typeParam ? `&type=${typeParam}` : ""}`;
          const res = await axios.get(url, { headers, timeout: 5000 });
          const serverList = res.data?.data || [];
          if (serverList.length > 0) {
            const toPut: SyncedVoucher[] = serverList.map((v: any) => ({
              id: v.id,
              companyId,
              financialYearId: v.financial_year_id || null,
              voucherType: v.type || v.voucher_type,
              voucherNumber: v.voucher_number,
              voucherDate: v.date || v.voucher_date,
              referenceNumber: v.reference_number || "",
              partyLedgerId: v.party_ledger_id || null,
              partyName: v.party_name || v.party_ledger?.name || "",
              status: v.status || "POSTED",
              totalAmount: Number(v.total_amount) || 0,
              paymentStatus: v.payment_status || "UNPAID",
              paidAmount: Number(v.paid_amount) || 0,
              narration: v.narration || "",
              serverUpdatedAt: Date.now(),
            }));
            await offlineDb.syncedVouchers.bulkPut(toPut);
            localVouchers = toPut;
          }
        }
      } catch (err) {
        console.warn("[VouchersRepo] Server fallback fetch skipped/failed:", err);
      }
    }

    // 2. Query offline outbox for pending/syncing/failed mutations
    const outboxItems = await offlineDb.vouchers
      .where("status")
      .anyOf(["PENDING", "SYNCING", "FAILED"])
      .toArray();

    const offlineMerged: any[] = outboxItems
      .filter((o) => {
        const p = o.payload || {};
        const matchesCompany = !p.company_id || p.company_id === companyId;
        if (!matchesCompany) return false;
        if (options.type) {
          const types = Array.isArray(options.type) ? options.type : [options.type];
          return types.includes(o.voucherType);
        }
        return true;
      })
      .map((o) => {
        const p = o.payload || {};
        return {
          id: `offline_${o.localId}`,
          localId: o.localId,
          isOffline: true,
          syncStatus: o.status,
          voucher_number: o.voucherNumber || "PENDING SYNC",
          voucherNumber: o.voucherNumber || "PENDING SYNC",
          type: o.voucherType,
          voucherType: o.voucherType,
          date: o.voucherDate,
          voucherDate: o.voucherDate,
          party_name: p.buyer_name || p.party_name || "Counter Party",
          partyName: p.buyer_name || p.party_name || "Counter Party",
          total_amount: Number(p.total_amount || p.round_off_total || 0),
          totalAmount: Number(p.total_amount || p.round_off_total || 0),
          status: o.status === "FAILED" ? "FAILED" : "PENDING",
          payment_status: "UNPAID",
          paid_amount: 0,
          errorMessage: o.errorMessage,
          items: p.items || [],
          serverUpdatedAt: o.createdAt,
        };
      });

    // 3. Filter local vouchers
    let filtered = localVouchers;

    if (options.type) {
      const types = Array.isArray(options.type) ? options.type : [options.type];
      filtered = filtered.filter((v) => types.includes(v.voucherType));
    }

    if (options.status && options.status !== "ALL") {
      filtered = filtered.filter((v) => v.status === options.status);
    } else if (!options.status) {
      // By default hide cancelled/reversed/superseded from regular active views
      filtered = filtered.filter((v) => v.status !== "CANCELLED" && v.status !== "REVERSED" && v.status !== "SUPERSEDED");
    }

    if (options.startDate) {
      filtered = filtered.filter((v) => v.voucherDate >= options.startDate!);
    }
    if (options.endDate) {
      filtered = filtered.filter((v) => v.voucherDate <= options.endDate!);
    }

    if (options.search) {
      const q = options.search.trim().toLowerCase();
      filtered = filtered.filter((v) =>
        (v.voucherNumber && v.voucherNumber.toLowerCase().includes(q)) ||
        (v.partyName && v.partyName.toLowerCase().includes(q)) ||
        (v.referenceNumber && v.referenceNumber.toLowerCase().includes(q)) ||
        (v.narration && v.narration.toLowerCase().includes(q))
      );
    }

    // 3b. Query local payment allocations to calculate accurate payment/settlement status
    const allocByInv: Record<string, number> = {};
    const allocByPmt: Record<string, number> = {};
    try {
      const allocations = await offlineDb.syncedPaymentAllocations
        .where("companyId")
        .equals(companyId)
        .toArray();
      for (const a of allocations) {
        if (a.invoiceVoucherId) {
          allocByInv[a.invoiceVoucherId] = (allocByInv[a.invoiceVoucherId] || 0) + Number(a.allocatedAmount || 0);
        }
        if (a.paymentVoucherId) {
          allocByPmt[a.paymentVoucherId] = (allocByPmt[a.paymentVoucherId] || 0) + Number(a.allocatedAmount || 0);
        }
      }
    } catch {
      // Non-fatal if table not yet populated
    }

    // Map SyncedVoucher to common frontend item schema (supporting both camelCase and snake_case)
    const normalizedLocal = filtered.map((v) => {
      let pStatus = v.paymentStatus || "UNPAID";
      let paidAmt = v.paidAmount || 0;

      if (v.voucherType === "SALES" || v.voucherType === "PURCHASE") {
        if (allocByInv[v.id] !== undefined) {
          paidAmt = allocByInv[v.id];
          if (paidAmt >= v.totalAmount && v.totalAmount > 0) {
            pStatus = "PAID";
          } else if (paidAmt > 0) {
            pStatus = "PARTIAL";
          } else {
            pStatus = "UNPAID";
          }
        }
      } else if (v.voucherType === "PAYMENT" || v.voucherType === "RECEIPT") {
        if (allocByPmt[v.id] !== undefined) {
          paidAmt = allocByPmt[v.id];
          if (paidAmt >= v.totalAmount && v.totalAmount > 0) {
            pStatus = "ALLOCATED";
          } else if (paidAmt > 0) {
            pStatus = "PARTIAL";
          } else {
            pStatus = "UNALLOCATED";
          }
        }
      }

      return {
        ...v,
        type: v.voucherType,
        voucher_number: v.voucherNumber,
        voucher_date: v.voucherDate,
        party_name: v.partyName,
        total_amount: v.totalAmount,
        payment_status: pStatus,
        paid_amount: paidAmt,
        syncStatus: "SYNCED",
      };
    });

    // 4. Sort: newest date first, then serverUpdatedAt descending
    normalizedLocal.sort((a, b) => {
      if (a.voucherDate !== b.voucherDate) {
        return b.voucherDate.localeCompare(a.voucherDate);
      }
      return (b.serverUpdatedAt || 0) - (a.serverUpdatedAt || 0);
    });

    // Merge offline items on top
    const combined = [...offlineMerged, ...normalizedLocal];
    const totalCount = combined.length;
    const totalPages = Math.ceil(totalCount / pageSize);
    const offset = (page - 1) * pageSize;
    const pagedData = combined.slice(offset, offset + pageSize);

    if (process.env.NODE_ENV === "development") {
      console.log(`[LOCAL] vouchers query (count=${pagedData.length}, total=${totalCount})`);
    }

    // Compute aggregates across ALL combined items (unpaged dataset)
    const totalPayments = combined
      .filter((v) => v.type === "PAYMENT" || v.voucherType === "PAYMENT")
      .reduce((sum, v) => sum + (Number(v.total_amount || v.totalAmount) || 0), 0);

    const totalReceipts = combined
      .filter((v) => v.type === "RECEIPT" || v.voucherType === "RECEIPT")
      .reduce((sum, v) => sum + (Number(v.total_amount || v.totalAmount) || 0), 0);

    const hasMore = page < totalPages;

    return {
      data: pagedData,
      totalCount,
      page,
      pageSize,
      totalPages,
      offset,
      hasMore,
      isLocal: true,
      totalPayments,
      totalReceipts,
    };
  }

  async getSalesInvoices(companyId: string, options: Omit<VoucherQueryOptions, "type"> = {}): Promise<VoucherQueryResult> {
    return this.getVouchers(companyId, { ...options, type: "SALES" });
  }

  async getPurchaseInvoices(companyId: string, options: Omit<VoucherQueryOptions, "type"> = {}): Promise<VoucherQueryResult> {
    return this.getVouchers(companyId, { ...options, type: "PURCHASE" });
  }

  async getPaymentReceipts(companyId: string, options: VoucherQueryOptions = {}): Promise<VoucherQueryResult> {
    const type = options.type || ["PAYMENT", "RECEIPT"];
    return this.getVouchers(companyId, { ...options, type });
  }

  async deleteVoucher(voucherId: string): Promise<void> {
    try {
      await offlineDb.syncedVouchers.delete(voucherId);
    } catch (e) {
      console.warn("[VouchersRepo] Failed to delete local voucher:", e);
    }
  }
}

export const vouchersRepository = new VouchersRepository();
