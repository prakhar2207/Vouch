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

export class VouchOfflineDB extends Dexie {
  vouchers!: Table<OfflineVoucher, number>;
  masters!: Table<MasterCache, string>;
  ocrCache!: Table<OcrCache, string>;

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
  }
}

export const offlineDb = new VouchOfflineDB();
