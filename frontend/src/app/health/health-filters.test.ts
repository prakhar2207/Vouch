import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  isBankFinding,
  isInventoryFinding,
  isDuplicateFinding,
  isGstFinding,
  isCriticalFinding,
  isActionableFinding,
  filterFindings,
  getFindingsCounts,
  AccountingFindingItem,
} from "./health-filters";

describe("SriLekh Books Health — Filter & Categorization Suite", () => {
  // Test Data Fixtures
  const negativeStockFinding: AccountingFindingItem = {
    id: "f-inv-1",
    category: "INVENTORY",
    severity: "WARNING",
    title: "Negative stock for B 65",
    description: "B 65 has a recorded stock of -9.00 PCS. Sales exceeded recorded purchases.",
    evidence: {
      action_url: "/inventory",
      action_label: "View Inventory",
      product_name: "B 65",
      current_stock: "-9.00",
    },
    is_actionable: false,
  };

  const inventoryMergeFinding: AccountingFindingItem = {
    id: "f-inv-dup",
    category: "DUPLICATE_INVENTORY",
    severity: "WARNING",
    title: "Duplicate Product: B 65 Belts",
    description: "Potential duplicate inventory item found in master catalog.",
    evidence: {
      action_url: "/inventory",
      primary_item_id: "inv-1",
      duplicate_item_id: "inv-2",
    },
    fix_type: "MERGE_INVENTORY_ITEMS",
    is_actionable: true,
  };

  const bankReconFinding: AccountingFindingItem = {
    id: "f-bank-1",
    category: "BANK",
    severity: "WARNING",
    title: "Unreconciled Bank Feed Transactions: HDFC Bank",
    description: "3 transactions imported from statement are pending book voucher reconciliation.",
    evidence: {
      action_url: "/banking",
      bank_name: "HDFC Bank",
      unreconciled_count: 3,
    },
    fix_type: "NAVIGATE_BANK_RECON",
    is_actionable: false,
  };

  const cashLiquidityFinding: AccountingFindingItem = {
    id: "f-liq-1",
    category: "LIQUIDITY",
    severity: "CRITICAL",
    title: "Cash drawer deficit detected",
    description: "Physical cash in hand ledger is negative ₹14,250.00.",
    evidence: {
      action_url: "/banking",
      ledger_name: "Cash in Hand",
      current_balance: "-14250.00",
    },
    fix_type: "REVIEW_BANK_BALANCE",
    is_actionable: false,
  };

  const duplicateBankFinding: AccountingFindingItem = {
    id: "f-bank-dup",
    category: "DUPLICATE_BANK",
    severity: "WARNING",
    title: "Duplicate Bank Feed Transaction: UTR #AXIS982341",
    description: "Identical transaction detected twice in imported bank feed.",
    evidence: {
      action_url: "/banking",
      utr: "AXIS982341",
      amount: "5000.00",
    },
    fix_type: "EXCLUDE_DUPLICATE_BANK",
    is_actionable: true,
  };

  const gstMismatchFinding: AccountingFindingItem = {
    id: "f-gst-1",
    category: "GST",
    severity: "CRITICAL",
    title: "Interstate Supply IGST Rate Mismatch",
    description: "Invoice #INV/26-27/0019 applies CGST/SGST to an out-of-state party.",
    evidence: {
      primary_voucher_number: "INV/26-27/0019",
      party_name: "Apex Maharashtra Depot",
    },
    is_actionable: false,
  };

  const tdsFinding: AccountingFindingItem = {
    id: "f-tds-1",
    category: "GST",
    severity: "WARNING",
    title: "Missing payee PAN on TDS deduction: Bill #PUR/26-27/0011",
    description: "Voucher has TDS deducted without valid 10-digit PAN.",
    evidence: {
      voucher_number: "PUR/26-27/0011",
      party_name: "Raw Materials Ltd",
    },
    fix_type: "UPDATE_PARTY_PAN",
    is_actionable: true,
  };

  const duplicateVoucherFinding: AccountingFindingItem = {
    id: "f-vouch-dup",
    category: "DUPLICATE",
    severity: "CRITICAL",
    title: "Duplicate Voucher: RCP/26-27/0004",
    description: "Receipt voucher created twice with identical reference.",
    evidence: {
      primary_voucher_number: "RCP/26-27/0004",
      party_name: "Apex Logistics",
    },
    fix_type: "VOID_DUPLICATE_VOUCHER",
    is_actionable: true,
  };

  const allFindings = [
    negativeStockFinding,
    inventoryMergeFinding,
    bankReconFinding,
    cashLiquidityFinding,
    duplicateBankFinding,
    gstMismatchFinding,
    tdsFinding,
    duplicateVoucherFinding,
  ];

  // 1. Negative stock findings appear only under Inventory
  it("1. Negative stock findings appear only under Inventory and never under Bank & Cash", () => {
    assert.equal(isInventoryFinding(negativeStockFinding), true);
    assert.equal(isBankFinding(negativeStockFinding), false);
    assert.equal(isDuplicateFinding(negativeStockFinding), false);

    const bankResults = filterFindings([negativeStockFinding], "BANK", "");
    assert.equal(bankResults.length, 0);

    const invResults = filterFindings([negativeStockFinding], "INVENTORY", "");
    assert.equal(invResults.length, 1);
    assert.equal(invResults[0].id, "f-inv-1");
  });

  // 2. Inventory merge findings never appear under Bank & Cash
  it("2. Inventory merge findings never appear under Bank & Cash", () => {
    assert.equal(isBankFinding(inventoryMergeFinding), false);
    assert.equal(isInventoryFinding(inventoryMergeFinding), true);
    assert.equal(isDuplicateFinding(inventoryMergeFinding), true);

    const bankResults = filterFindings([inventoryMergeFinding], "BANK", "");
    assert.equal(bankResults.length, 0);

    const dupResults = filterFindings([inventoryMergeFinding], "DUPLICATES", "");
    assert.equal(dupResults.length, 1);
  });

  // 3. Bank reconciliation findings appear under Bank & Cash
  it("3. Bank reconciliation findings appear under Bank & Cash and not Inventory", () => {
    assert.equal(isBankFinding(bankReconFinding), true);
    assert.equal(isInventoryFinding(bankReconFinding), false);

    const bankResults = filterFindings([bankReconFinding], "BANK", "");
    assert.equal(bankResults.length, 1);
    assert.equal(bankResults[0].id, "f-bank-1");

    const invResults = filterFindings([bankReconFinding], "INVENTORY", "");
    assert.equal(invResults.length, 0);
  });

  // 4. Cash-in-hand liquidity findings appear under Bank & Cash
  it("4. Cash-in-hand liquidity findings appear under Bank & Cash", () => {
    assert.equal(isBankFinding(cashLiquidityFinding), true);
    assert.equal(isInventoryFinding(cashLiquidityFinding), false);

    const bankResults = filterFindings([cashLiquidityFinding], "BANK", "");
    assert.equal(bankResults.length, 1);
    assert.equal(bankResults[0].id, "f-liq-1");
  });

  // 5. Duplicate bank transactions appear in the appropriate duplicate category & bank category
  it("5. Duplicate bank transactions appear under Duplicates and Bank & Cash, never Inventory", () => {
    assert.equal(isDuplicateFinding(duplicateBankFinding), true);
    assert.equal(isBankFinding(duplicateBankFinding), true);
    assert.equal(isInventoryFinding(duplicateBankFinding), false);

    const dupResults = filterFindings([duplicateBankFinding], "DUPLICATES", "");
    assert.equal(dupResults.length, 1);

    const bankResults = filterFindings([duplicateBankFinding], "BANK", "");
    assert.equal(bankResults.length, 1);

    const invResults = filterFindings([duplicateBankFinding], "INVENTORY", "");
    assert.equal(invResults.length, 0);
  });

  // 6. Duplicate inventory records appear in the appropriate duplicate category
  it("6. Duplicate inventory records appear in Duplicates and Inventory, never Bank & Cash", () => {
    assert.equal(isDuplicateFinding(inventoryMergeFinding), true);
    assert.equal(isInventoryFinding(inventoryMergeFinding), true);
    assert.equal(isBankFinding(inventoryMergeFinding), false);

    const dupResults = filterFindings([inventoryMergeFinding], "DUPLICATES", "");
    assert.equal(dupResults.length, 1);

    const invResults = filterFindings([inventoryMergeFinding], "INVENTORY", "");
    assert.equal(invResults.length, 1);

    const bankResults = filterFindings([inventoryMergeFinding], "BANK", "");
    assert.equal(bankResults.length, 0);
  });

  // 7. All Issues displays every eligible finding
  it("7. All Issues tab displays every single finding without omission", () => {
    const allResults = filterFindings(allFindings, "ALL", "");
    assert.equal(allResults.length, allFindings.length);
  });

  // 8. Search and category filters work together correctly
  it("8. Search and category filters work together conjunctively", () => {
    // Search for "HDFC" under ALL -> 1 result
    const searchAll = filterFindings(allFindings, "ALL", "HDFC");
    assert.equal(searchAll.length, 1);
    assert.equal(searchAll[0].id, "f-bank-1");

    // Search for "HDFC" under BANK -> 1 result
    const searchBank = filterFindings(allFindings, "BANK", "HDFC");
    assert.equal(searchBank.length, 1);

    // Search for "HDFC" under INVENTORY -> 0 results
    const searchInv = filterFindings(allFindings, "INVENTORY", "HDFC");
    assert.equal(searchInv.length, 0);

    // Search for "B 65" under INVENTORY -> 2 results (negative stock + duplicate product)
    const searchB65 = filterFindings(allFindings, "INVENTORY", "B 65");
    assert.equal(searchB65.length, 2);

    // Search for "B 65" under BANK -> 0 results
    const searchB65Bank = filterFindings(allFindings, "BANK", "B 65");
    assert.equal(searchB65Bank.length, 0);

    // Search by party name in evidence
    const searchParty = filterFindings(allFindings, "GST", "Maharashtra");
    assert.equal(searchParty.length, 1);
    assert.equal(searchParty[0].id, "f-gst-1");

    // Search by voucher number in evidence
    const searchVoucher = filterFindings(allFindings, "DUPLICATES", "RCP/26-27/0004");
    assert.equal(searchVoucher.length, 1);
    assert.equal(searchVoucher[0].id, "f-vouch-dup");
  });

  // 9. Counts match rendered results
  it("9. Counts calculated by getFindingsCounts match rendered results exactly", () => {
    const counts = getFindingsCounts(allFindings);

    const renderedAll = filterFindings(allFindings, "ALL", "");
    const renderedBank = filterFindings(allFindings, "BANK", "");
    const renderedInv = filterFindings(allFindings, "INVENTORY", "");
    const renderedGst = filterFindings(allFindings, "GST", "");
    const renderedDup = filterFindings(allFindings, "DUPLICATES", "");
    const renderedCrit = filterFindings(allFindings, "CRITICAL", "");
    const renderedAct = filterFindings(allFindings, "ACTIONABLE", "");

    assert.equal(counts.allCount, renderedAll.length);
    assert.equal(counts.bankCount, renderedBank.length);
    assert.equal(counts.inventoryCount, renderedInv.length);
    assert.equal(counts.gstCount, renderedGst.length);
    assert.equal(counts.duplicateCount, renderedDup.length);
    assert.equal(counts.criticalCount, renderedCrit.length);
    assert.equal(counts.actionableCount, renderedAct.length);
  });

  // 10. Malformed, missing, and inconsistent evidence payloads
  it("10. Handles malformed, null, undefined, and inconsistent evidence payloads without throwing", () => {
    const malformedFindings: any[] = [
      null,
      undefined,
      {},
      { id: "bad-1" },
      { id: "bad-2", category: null, title: null, evidence: null },
      { id: "bad-3", category: 12345, title: true, evidence: "not an object" },
      { id: "bad-4", category: "INVENTORY", evidence: { action_url: null } },
      { id: "bad-5", category: "BANK", evidence: undefined },
    ];

    // Predicates should not throw
    for (const item of malformedFindings) {
      assert.doesNotThrow(() => isBankFinding(item));
      assert.doesNotThrow(() => isInventoryFinding(item));
      assert.doesNotThrow(() => isGstFinding(item));
      assert.doesNotThrow(() => isDuplicateFinding(item));
      assert.doesNotThrow(() => isCriticalFinding(item));
      assert.doesNotThrow(() => isActionableFinding(item));
    }

    // Filter engine should handle null array or malformed elements gracefully
    assert.doesNotThrow(() => filterFindings(null, "BANK", ""));
    assert.doesNotThrow(() => filterFindings(undefined, "INVENTORY", "test"));
    assert.doesNotThrow(() => filterFindings(malformedFindings, "ALL", ""));
    assert.doesNotThrow(() => filterFindings(malformedFindings, "BANK", ""));
    assert.doesNotThrow(() => filterFindings(malformedFindings, "INVENTORY", ""));
    assert.doesNotThrow(() => getFindingsCounts(null));
    assert.doesNotThrow(() => getFindingsCounts(undefined));
    assert.doesNotThrow(() => getFindingsCounts(malformedFindings));

    // Verify valid items among malformed items are still correctly identified
    const mixedList: any[] = [null, negativeStockFinding, undefined, bankReconFinding];
    const bankFiltered = filterFindings(mixedList, "BANK", "");
    assert.equal(bankFiltered.length, 1);
    assert.equal(bankFiltered[0].id, "f-bank-1");

    const invFiltered = filterFindings(mixedList, "INVENTORY", "");
    assert.equal(invFiltered.length, 1);
    assert.equal(invFiltered[0].id, "f-inv-1");
  });

  // 11. Empty categories return empty arrays
  it("11. Empty categories return clean empty lists for empty states", () => {
    const onlyBank = [bankReconFinding];
    const invResults = filterFindings(onlyBank, "INVENTORY", "");
    assert.equal(invResults.length, 0);

    const gstResults = filterFindings(onlyBank, "GST", "");
    assert.equal(gstResults.length, 0);

    const dupResults = filterFindings(onlyBank, "DUPLICATES", "");
    assert.equal(dupResults.length, 0);
  });

  // 12. Edge Case: Product with "Bank" in product title
  it("12. Product with 'Bank' in its name (e.g. 'Power Bank 10000mAh') never leaks into Bank & Cash", () => {
    const powerBankFinding: AccountingFindingItem = {
      id: "f-power-bank",
      category: "INVENTORY",
      severity: "WARNING",
      title: "Negative stock for Power Bank 10000mAh",
      description: "Stock is -4.00 PCS.",
      evidence: { action_url: "/inventory", product_name: "Power Bank 10000mAh" },
    };

    assert.equal(isBankFinding(powerBankFinding), false);
    assert.equal(isInventoryFinding(powerBankFinding), true);

    const bankResults = filterFindings([powerBankFinding], "BANK", "");
    assert.equal(bankResults.length, 0);

    const invResults = filterFindings([powerBankFinding], "INVENTORY", "");
    assert.equal(invResults.length, 1);
  });
});
