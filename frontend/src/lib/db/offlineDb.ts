import Dexie, { type Table } from "dexie";

export interface OfflineVoucher {
  id?: number;
  localId: string;
  voucherType: string;
  voucherNumber?: string;
  voucherDate: string;
  payload: any;
  status: "PENDING" | "SYNCING" | "SYNCED" | "FAILED";
  errorMessage?: string;
  retryCount: number;
  createdAt: number;
  syncedAt?: number;
}

export interface MasterCache {
  key: string;
  data: any;
  updatedAt: number;
}

export interface OcrCache {
  fileHash: string;
  fileName: string;
  fileSize: number;
  result: any;
  cachedAt: number;
}

export interface SyncedVoucher {
  id: string; // server voucher UUID
  companyId: string;
  financialYearId?: string | null;
  voucherType: string; // SALES, PURCHASE, PAYMENT, RECEIPT, CONTRA, JOURNAL
  voucherNumber: string;
  voucherDate: string; // YYYY-MM-DD
  referenceNumber?: string;
  partyLedgerId?: string | null;
  partyName?: string;
  status: "DRAFT" | "POSTED" | "CANCELLED" | "REVERSED" | "SUPERSEDED" | "CORRECTED";
  totalAmount: number; // numeric float/decimal representation
  narration?: string;
  serverUpdatedAt: number;
}

export interface SyncedLedger {
  id: string; // ledger UUID
  companyId: string;
  name: string;
  ledgerType: string; // CUSTOMER, SUPPLIER, BANK, CASH, TAX, EXPENSE, GENERAL, PARTY
  gstin?: string;
  stateCode?: string;
  currentBalance: number;
  openingBalance: number;
  openingBalanceType: "DEBIT" | "CREDIT";
  phone?: string;
  serverUpdatedAt: number;
}

export interface SyncedProduct {
  id: string; // product UUID
  companyId: string;
  name: string;
  sku?: string;
  hsnCode?: string;
  unit: string;
  purchasePrice: number;
  salesPrice: number;
  gstRate: number;
  currentStock: number;
  serverUpdatedAt: number;
}

export interface SyncMeta {
  companyId: string;
  lastSyncAt: number;
  syncCursor?: string;
  oldestSyncedAt?: number;
  newestSyncedAt?: number;
  syncStatus: "IDLE" | "SYNCING" | "ERROR";
  isInitialComplete: boolean;
  pendingMutationsCount: number;
  errorMessage?: string;
}

export interface AnalyticsDaily {
  id: string; // `${companyId}_${date}`
  companyId: string;
  date: string; // YYYY-MM-DD
  sales: number;
  purchases: number;
  collections: number;
  payments: number;
  salesCount: number;
  purchaseCount: number;
}

export interface AnalyticsParty {
  id: string; // `${companyId}_${partyId}`
  companyId: string;
  partyId: string;
  partyName: string;
  sales: number;
  purchases: number;
  receipts: number;
  payments: number;
  invoiceCount: number;
  lastTransactionDate: string;
  outstanding: number;
}

export class VouchOfflineDB extends Dexie {
  vouchers!: Table<OfflineVoucher, number>;
  masters!: Table<MasterCache, string>;
  ocrCache!: Table<OcrCache, string>;
  syncedVouchers!: Table<SyncedVoucher, string>;
  syncedLedgers!: Table<SyncedLedger, string>;
  syncedProducts!: Table<SyncedProduct, string>;
  syncMeta!: Table<SyncMeta, string>;
  analyticsDaily!: Table<AnalyticsDaily, string>;
  analyticsParty!: Table<AnalyticsParty, string>;

  constructor() {
    super("VouchOfflineDB");
    this.version(1).stores({
      vouchers: "++id, localId, voucherType, status, createdAt",
      masters: "key, updatedAt",
    });
    this.version(2).stores({
      vouchers: "++id, localId, voucherType, status, createdAt",
      masters: "key, updatedAt",
      ocrCache: "fileHash, cachedAt",
    });
    this.version(3).stores({
      vouchers: "++id, localId, voucherType, status, createdAt",
      masters: "key, updatedAt",
      ocrCache: "fileHash, cachedAt",
      syncedVouchers: "id, companyId, voucherType, voucherDate, status, partyLedgerId, serverUpdatedAt, [companyId+voucherDate], [companyId+status], [companyId+voucherType]",
      syncedLedgers: "id, companyId, ledgerType, name, [companyId+ledgerType]",
      syncedProducts: "id, companyId, sku, [companyId+currentStock]",
      syncMeta: "companyId, lastSyncAt, syncStatus",
      analyticsDaily: "id, companyId, date, [companyId+date]",
      analyticsParty: "id, companyId, partyId, [companyId+partyId]",
    });
  }
}

export const offlineDb = new VouchOfflineDB();
