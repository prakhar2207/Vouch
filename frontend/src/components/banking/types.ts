export interface BankLedger {
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

export interface BankTransactionItem {
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

export interface ReconciliationSummary {
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

export interface PartyMappingItem {
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

export type BankingActiveTab = "NEEDS_REVIEW" | "UNRESOLVED" | "MATCHED" | "EXCLUDED" | "ALL";

export type BankingActionType = "MATCH_PARTY" | "RECORD_PAYMENT" | "RECORD_EXPENSE" | "RECORD_TRANSFER" | "OWNER_DRAWING" | "IGNORE";
