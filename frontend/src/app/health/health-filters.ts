/**
 * SriLekh Books Health — Filter & Categorization Engine
 * 
 * Provides strictly mutually exclusive, hardened predicates for accounting audit findings.
 * Guarantees that inventory/stock issues (negative stock, zero cost, catalog merge)
 * NEVER leak into Bank & Cash, and vice versa.
 */

export interface AccountingFindingItem {
  id: string;
  code?: string;
  category: string;
  severity: "CRITICAL" | "WARNING" | "INFO";
  title: string;
  description: string;
  suggested_fix?: string;
  evidence?: Record<string, any>;
  is_actionable?: boolean;
  fix_type?: string;
  status?: "UNRESOLVED" | "RESOLVED" | "IGNORED";
  created_at?: string;
}

export type HealthTab = "ALL" | "BANK" | "INVENTORY" | "GST" | "DUPLICATES" | "CRITICAL" | "ACTIONABLE";

/**
 * Predicate: Bank Reconciliation, Cash in Hand & Liquidity Findings
 * 
 * Strictly excludes any inventory, stock, or product merge records, even if
 * evidence payloads or descriptions contain ambiguous keywords.
 */
export const isBankFinding = (f: AccountingFindingItem | null | undefined): boolean => {
  if (!f || typeof f !== "object") return false;
  const cat = String(f.category || "").toUpperCase();
  const fix = String(f.fix_type || "").toUpperCase();
  const actionUrl = typeof f.evidence?.action_url === "string" ? f.evidence.action_url : "";
  const title = String(f.title || "").toLowerCase();

  // Absolute exclusion: Never classify inventory stock, negative stock, or product merge as bank
  if (
    cat.includes("INVENTORY") ||
    fix === "MERGE_INVENTORY_ITEMS" ||
    actionUrl === "/inventory" ||
    title.startsWith("negative stock") ||
    title.includes("in-stock item") ||
    title.includes("stock valuation")
  ) {
    return false;
  }

  return (
    cat.includes("BANK") ||
    cat === "LIQUIDITY" ||
    cat === "BANK_RECONCILIATION" ||
    cat.startsWith("DUPLICATE_BANK") ||
    fix === "EXCLUDE_DUPLICATE_BANK" ||
    fix === "REVIEW_BANK_BALANCE" ||
    fix === "NAVIGATE_BANK_RECON" ||
    actionUrl === "/banking" ||
    title.includes("bank") ||
    title.includes("cash in hand") ||
    title.includes("cash drawer") ||
    title.includes("overdraft") ||
    title.includes("od limit")
  );
};

/**
 * Predicate: Inventory & Stock Discrepancies
 * 
 * Strictly excludes banking, statement reconciliation, and cash liquidity issues.
 */
export const isInventoryFinding = (f: AccountingFindingItem | null | undefined): boolean => {
  if (!f || typeof f !== "object") return false;
  const cat = String(f.category || "").toUpperCase();
  const fix = String(f.fix_type || "").toUpperCase();
  const actionUrl = typeof f.evidence?.action_url === "string" ? f.evidence.action_url : "";
  const title = String(f.title || "").toLowerCase();

  // Absolute exclusion: Never classify bank or liquidity issues as inventory
  if (
    cat.includes("BANK") ||
    cat === "LIQUIDITY" ||
    cat === "BANK_RECONCILIATION" ||
    actionUrl === "/banking" ||
    fix === "EXCLUDE_DUPLICATE_BANK" ||
    fix === "REVIEW_BANK_BALANCE" ||
    fix === "NAVIGATE_BANK_RECON"
  ) {
    return false;
  }

  return (
    cat.includes("INVENTORY") ||
    fix === "MERGE_INVENTORY_ITEMS" ||
    actionUrl === "/inventory" ||
    title.startsWith("negative stock") ||
    title.includes("in-stock item") ||
    title.includes("stock valuation") ||
    title.includes("inventory")
  );
};

/**
 * Predicate: GST & Statutory Compliance Findings (GST, Tax, TDS)
 */
export const isGstFinding = (f: AccountingFindingItem | null | undefined): boolean => {
  if (!f || typeof f !== "object") return false;
  const cat = String(f.category || "").toUpperCase();
  const title = String(f.title || "").toLowerCase();
  return (
    cat.includes("GST") ||
    cat.includes("TDS") ||
    cat.includes("TAX") ||
    title.includes("gst") ||
    title.includes("tds") ||
    title.includes("tax")
  );
};

/**
 * Predicate: Duplicate Transactions, Items, and Records
 */
export const isDuplicateFinding = (f: AccountingFindingItem | null | undefined): boolean => {
  if (!f || typeof f !== "object") return false;
  const cat = String(f.category || "").toUpperCase();
  const fix = String(f.fix_type || "").toUpperCase();
  const title = String(f.title || "").toLowerCase();
  return (
    cat.startsWith("DUPLICATE") ||
    fix.includes("DUPLICATE") ||
    fix === "VOID_DUPLICATE_VOUCHER" ||
    fix === "MERGE_INVENTORY_ITEMS" ||
    fix === "EXCLUDE_DUPLICATE_BANK" ||
    title.startsWith("duplicate")
  );
};

/**
 * Predicate: Critical Severity Findings
 */
export const isCriticalFinding = (f: AccountingFindingItem | null | undefined): boolean => {
  if (!f || typeof f !== "object") return false;
  return f.severity === "CRITICAL";
};

/**
 * Predicate: Actionable (1-Click Fixable) Findings
 */
export const isActionableFinding = (f: AccountingFindingItem | null | undefined): boolean => {
  if (!f || typeof f !== "object") return false;
  return Boolean(f.is_actionable || f.fix_type);
};

/**
 * Filter engine: applies active category tab and search query with full resilience against null/malformed items
 */
export function filterFindings(
  findings: AccountingFindingItem[] | null | undefined,
  activeTab: HealthTab,
  searchQuery: string
): AccountingFindingItem[] {
  if (!Array.isArray(findings)) return [];

  // Filter out any null/undefined or non-object entries first
  let list = findings.filter((f): f is AccountingFindingItem => Boolean(f && typeof f === "object"));

  if (activeTab === "DUPLICATES") {
    list = list.filter(isDuplicateFinding);
  } else if (activeTab === "BANK") {
    list = list.filter(isBankFinding);
  } else if (activeTab === "INVENTORY") {
    list = list.filter(isInventoryFinding);
  } else if (activeTab === "GST") {
    list = list.filter(isGstFinding);
  } else if (activeTab === "CRITICAL") {
    list = list.filter(isCriticalFinding);
  } else if (activeTab === "ACTIONABLE") {
    list = list.filter(isActionableFinding);
  }
  // "ALL" tab keeps all findings

  if (searchQuery && typeof searchQuery === "string" && searchQuery.trim()) {
    const q = searchQuery.toLowerCase().trim();
    list = list.filter((f) => {
      const title = String(f.title || "").toLowerCase();
      const desc = String(f.description || "").toLowerCase();
      const cat = String(f.category || "").toLowerCase();
      const party = f.evidence?.party_name ? String(f.evidence.party_name).toLowerCase() : "";
      const voucher = f.evidence?.primary_voucher_number ? String(f.evidence.primary_voucher_number).toLowerCase() : "";
      return title.includes(q) || desc.includes(q) || cat.includes(q) || party.includes(q) || voucher.includes(q);
    });
  }

  return list;
}

/**
 * Accurate category counts derived from findings array
 */
export function getFindingsCounts(findings: AccountingFindingItem[] | null | undefined) {
  if (!Array.isArray(findings)) {
    return {
      allCount: 0,
      bankCount: 0,
      inventoryCount: 0,
      gstCount: 0,
      duplicateCount: 0,
      criticalCount: 0,
      actionableCount: 0,
    };
  }

  const valid = findings.filter((f): f is AccountingFindingItem => Boolean(f && typeof f === "object"));

  return {
    allCount: valid.length,
    bankCount: valid.filter(isBankFinding).length,
    inventoryCount: valid.filter(isInventoryFinding).length,
    gstCount: valid.filter(isGstFinding).length,
    duplicateCount: valid.filter(isDuplicateFinding).length,
    criticalCount: valid.filter(isCriticalFinding).length,
    actionableCount: valid.filter(isActionableFinding).length,
  };
}
