/**
 * Domain Type Definitions for SriLekh Accounting System
 * 
 * Centralizes the canonical domain representations for:
 * - Vouchers and Double-Entry Ledger Transactions
 * - Multi-tenant Company and Role-Based Permissions
 * - Offline-First Sync & Change Feed Contracts
 */

export type VoucherType =
  | "SALES"
  | "PURCHASE"
  | "PAYMENT"
  | "RECEIPT"
  | "CONTRA"
  | "JOURNAL"
  | "CREDIT_NOTE"
  | "DEBIT_NOTE";

export type VoucherStatus =
  | "DRAFT"
  | "POSTED"
  | "CANCELLED"
  | "REVERSED"
  | "SUPERSEDED"
  | "CORRECTED";

export type PaymentStatus =
  | "PAID"
  | "PARTIAL"
  | "UNPAID"
  | "ALLOCATED"
  | "UNALLOCATED"
  | "N/A";

export type LedgerNature = "ASSET" | "LIABILITY" | "INCOME" | "EXPENSE" | "EQUITY";

export type LedgerType =
  | "CUSTOMER"
  | "SUPPLIER"
  | "BANK"
  | "CASH"
  | "TAX"
  | "EXPENSE"
  | "GENERAL"
  | "PARTY";

export type AccountingRole =
  | "OWNER"
  | "ADMIN"
  | "CA"
  | "EMPLOYEE"
  | "VIEWER";

export interface CompanyReference {
  id: string;
  name: string;
  gstin?: string;
  stateCode?: string;
  pan?: string;
  currency?: string;
}

export interface FinancialYearReference {
  id: string;
  companyId: string;
  name?: string;
  code?: string;
  startDate: string;
  endDate: string;
  isClosed: boolean;
}

export interface VoucherLineItem {
  id?: string;
  productId: string;
  productName?: string;
  quantity: number;
  unit: string;
  rate: number;
  discountPercent?: number;
  discountAmount?: number;
  taxableAmount: number;
  gstRate: number;
  cgstAmount?: number;
  sgstAmount?: number;
  igstAmount?: number;
  totalAmount: number;
  hsnCode?: string;
}

export interface DoubleEntryRow {
  id?: string;
  ledgerId: string;
  ledgerName?: string;
  debit: number;
  credit: number;
  narration?: string;
}

export interface CanonicalVoucher {
  id: string;
  companyId: string;
  financialYearId?: string | null;
  voucherType: VoucherType;
  voucherNumber: string;
  voucherDate: string;
  dueDate?: string | null;
  referenceNumber?: string;
  partyLedgerId?: string | null;
  partyName?: string;
  status: VoucherStatus;
  totalAmount: number;
  roundOff?: number;
  paidAmount?: number;
  paymentStatus?: PaymentStatus;
  narration?: string;
  items?: VoucherLineItem[];
  entries?: DoubleEntryRow[];
  createdAt?: string | number;
  updatedAt?: string | number;
}

/**
 * Sync Protocol Change Feed Types
 */
export interface SyncBatchChanges<TRecord = unknown> {
  created: TRecord[];
  updated: TRecord[];
  deleted: { id: string }[];
}

export interface SyncFeedResponse {
  next_cursor: string;
  has_more: boolean;
  snapshot_cursor?: string;
  changes: {
    ledgers?: SyncBatchChanges;
    products?: SyncBatchChanges;
    vouchers?: SyncBatchChanges;
    bank_transactions?: SyncBatchChanges;
    payment_allocations?: SyncBatchChanges;
  };
}

/**
 * Role Permission Matrix Definitions
 */
export interface RoleCapabilities {
  canCreateSales: boolean;
  canCreatePurchases: boolean;
  canCreateJournals: boolean;
  canCreateContras: boolean;
  canCancelVouchers: boolean;
  canManageLedgers: boolean;
  canManageSettings: boolean;
  isReadOnly: boolean;
}

export const ROLE_CAPABILITY_MAP: Record<AccountingRole, RoleCapabilities> = {
  OWNER: {
    canCreateSales: true,
    canCreatePurchases: true,
    canCreateJournals: true,
    canCreateContras: true,
    canCancelVouchers: true,
    canManageLedgers: true,
    canManageSettings: true,
    isReadOnly: false,
  },
  ADMIN: {
    canCreateSales: true,
    canCreatePurchases: true,
    canCreateJournals: true,
    canCreateContras: true,
    canCancelVouchers: true,
    canManageLedgers: true,
    canManageSettings: true,
    isReadOnly: false,
  },
  CA: {
    canCreateSales: true,
    canCreatePurchases: true,
    canCreateJournals: true,
    canCreateContras: true,
    canCancelVouchers: true,
    canManageLedgers: true,
    canManageSettings: false,
    isReadOnly: false,
  },
  EMPLOYEE: {
    canCreateSales: true,
    canCreatePurchases: true,
    canCreateJournals: false,
    canCreateContras: false,
    canCancelVouchers: false,
    canManageLedgers: false,
    canManageSettings: false,
    isReadOnly: false,
  },
  VIEWER: {
    canCreateSales: false,
    canCreatePurchases: false,
    canCreateJournals: false,
    canCreateContras: false,
    canCancelVouchers: false,
    canManageLedgers: false,
    canManageSettings: false,
    isReadOnly: true,
  },
};
