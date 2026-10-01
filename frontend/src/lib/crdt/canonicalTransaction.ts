import { canonicalJsonStringify, computeCanonicalSha256 } from "./canonicalJson";

export interface CanonicalEntity {
  type: string;
  value: string;
  name: string;
  state_code?: string | null;
}

export interface CanonicalLineItem {
  line_id: string;
  sku: string;
  name: string;
  hsn_code: string;
  quantity: string;
  unit: string;
  unit_price: string;
  discount_amount: string;
  taxable_amount: string;
  tax_rate_percent: string;
}

export interface CanonicalTaxSummary {
  cgst: string;
  sgst: string;
  igst: string;
  cess: string;
  total_tax: string;
}

export interface CanonicalTotals {
  subtotal: string;
  total_tax: string;
  shipping: string;
  discount: string;
  grand_total: string;
}

export interface CanonicalTransactionEnvelope {
  protocol_version: string;
  transaction_id: string;
  transaction_type: string;
  state_version: number;
  issued_at: string;
  source_entity: CanonicalEntity;
  destination_entity: CanonicalEntity;
  items: CanonicalLineItem[];
  tax_summary: CanonicalTaxSummary;
  totals: CanonicalTotals;
  causal_dependencies: string[];
}

export function buildCanonicalTransaction(params: {
  transaction_id: string;
  transaction_type: string;
  issued_at: string;
  source_entity: CanonicalEntity;
  destination_entity: CanonicalEntity;
  items: Array<{
    line_id?: string;
    sku?: string;
    name?: string;
    hsn_code?: string;
    quantity: number | string;
    unit?: string;
    unit_price: number | string;
    discount_amount?: number | string;
    taxable_amount?: number | string;
    tax_rate_percent?: number | string;
  }>;
  tax_summary?: {
    cgst?: number | string;
    sgst?: number | string;
    igst?: number | string;
    cess?: number | string;
    total_tax?: number | string;
  };
  totals: {
    subtotal: number | string;
    total_tax?: number | string;
    shipping?: number | string;
    discount?: number | string;
    grand_total: number | string;
  };
  causal_dependencies?: string[];
}): CanonicalTransactionEnvelope {
  const toDecStr = (val: any) => {
    const num = Number(val || 0);
    return isNaN(num) ? "0.00" : num.toFixed(2);
  };

  const formattedItems: CanonicalLineItem[] = params.items.map((it, idx) => ({
    line_id: String(it.line_id || `L${idx + 1}`),
    sku: String(it.sku || ""),
    name: String(it.name || "Item"),
    hsn_code: String(it.hsn_code || "0000"),
    quantity: toDecStr(it.quantity),
    unit: String(it.unit || "PCS"),
    unit_price: toDecStr(it.unit_price),
    discount_amount: toDecStr(it.discount_amount),
    taxable_amount: toDecStr(it.taxable_amount),
    tax_rate_percent: toDecStr(it.tax_rate_percent)
  }));

  const totalTaxStr = toDecStr(params.totals.total_tax || params.tax_summary?.total_tax || 0);

  const formattedTax: CanonicalTaxSummary = {
    cgst: toDecStr(params.tax_summary?.cgst),
    sgst: toDecStr(params.tax_summary?.sgst),
    igst: toDecStr(params.tax_summary?.igst),
    cess: toDecStr(params.tax_summary?.cess),
    total_tax: totalTaxStr
  };

  const formattedTotals: CanonicalTotals = {
    subtotal: toDecStr(params.totals.subtotal),
    total_tax: totalTaxStr,
    shipping: toDecStr(params.totals.shipping),
    discount: toDecStr(params.totals.discount),
    grand_total: toDecStr(params.totals.grand_total)
  };

  return {
    protocol_version: "1.0",
    transaction_id: params.transaction_id,
    transaction_type: params.transaction_type.toUpperCase(),
    state_version: 1,
    issued_at: params.issued_at,
    source_entity: {
      type: params.source_entity.type || "GSTIN",
      value: String(params.source_entity.value || ""),
      name: String(params.source_entity.name || ""),
      state_code: params.source_entity.state_code || null
    },
    destination_entity: {
      type: params.destination_entity.type || "GSTIN",
      value: String(params.destination_entity.value || ""),
      name: String(params.destination_entity.name || ""),
      state_code: params.destination_entity.state_code || null
    },
    items: formattedItems,
    tax_summary: formattedTax,
    totals: formattedTotals,
    causal_dependencies: params.causal_dependencies || []
  };
}

export async function hashCanonicalTransaction(tx: CanonicalTransactionEnvelope): Promise<string> {
  return await computeCanonicalSha256(tx);
}
