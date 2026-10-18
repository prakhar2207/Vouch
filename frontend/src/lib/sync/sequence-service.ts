import { offlineDb } from '../db/offlineDb';

/**
 * Calculates current Indian Financial Year code (e.g., "26-27") for a given date.
 * Financial Year starts April 1 and ends March 31.
 */
export function getFinancialYearCode(dateStr?: string): string {
  const d = dateStr ? new Date(dateStr) : new Date();
  const year = isNaN(d.getTime()) ? new Date().getFullYear() : d.getFullYear();
  const month = isNaN(d.getTime()) ? new Date().getMonth() + 1 : d.getMonth() + 1; // 1-12
  const startYear = month >= 4 ? year : year - 1;
  const endYear = startYear + 1;
  const startYY = String(startYear).slice(-2);
  const endYY = String(endYear).slice(-2);
  return `${startYY}-${endYY}`;
}

export interface ParsedSequencePattern {
  prefix: string;
  fyCode: string;
  maxNumber: number;
  padLength: number;
  patternType: 'SLASH_FY' | 'DASH' | 'NUMERIC' | 'GENERIC';
}

/**
 * Inspects local IndexedDB cached vouchers, outbox queue, and localStorage to determine
 * the highest existing invoice number and the company's numbering format (e.g. INV/26-27/0144 -> 144).
 */
export async function getOfflineNextSequence(
  companyId: string,
  voucherType: string = 'SALES',
  invoiceDate?: string
): Promise<string> {
  const vTypeUpper = (voucherType || 'SALES').toUpperCase();
  const currentFyCode = getFinancialYearCode(invoiceDate);

  let maxNum = 0;
  let detectedPrefix = 'INV';
  let detectedFy = currentFyCode;
  let padLength = 4;
  let detectedPattern: 'SLASH_FY' | 'DASH' | 'NUMERIC' | 'GENERIC' = 'SLASH_FY';

  const inspectNumber = (numStr: string | null | undefined) => {
    if (!numStr) return;
    const clean = String(numStr).trim();
    // Exclude internal client transaction placeholders like OFF- or TX-
    if (/^OFF-/i.test(clean) || /^TX-/i.test(clean) || /^PENDING/i.test(clean)) return;

    // 1. Standard Indian GST format: PREFIX/YY-YY/0001 (e.g. INV/26-27/0144)
    const slashMatch = clean.match(/^([A-Za-z0-9_-]+)\/(\d{2}-\d{2}|\d{4}-\d{2})\/(\d+)$/);
    if (slashMatch) {
      const pfx = slashMatch[1];
      const fy = slashMatch[2];
      const nStr = slashMatch[3];
      const n = parseInt(nStr, 10);
      if (!isNaN(n) && n > maxNum) {
        maxNum = n;
        detectedPrefix = pfx;
        detectedFy = fy;
        padLength = Math.max(padLength, nStr.length);
        detectedPattern = 'SLASH_FY';
      }
      return;
    }

    // 2. Dash format: PREFIX-0001 (e.g. INV-144 or SAL-0144)
    const dashMatch = clean.match(/^([A-Za-z0-9_]+)-(\d+)$/);
    if (dashMatch) {
      const pfx = dashMatch[1];
      const nStr = dashMatch[2];
      const n = parseInt(nStr, 10);
      if (!isNaN(n) && n > maxNum) {
        maxNum = n;
        detectedPrefix = pfx;
        padLength = Math.max(padLength, nStr.length);
        detectedPattern = 'DASH';
      }
      return;
    }

    // 3. Pure numeric integer: 144
    if (/^\d+$/.test(clean)) {
      const n = parseInt(clean, 10);
      if (!isNaN(n) && n > maxNum) {
        maxNum = n;
        padLength = Math.max(padLength, clean.length);
        detectedPattern = 'NUMERIC';
      }
      return;
    }

    // 4. Generic trailing numeric extraction
    const genericMatch = clean.match(/(\d+)$/);
    if (genericMatch) {
      const nStr = genericMatch[1];
      const n = parseInt(nStr, 10);
      if (!isNaN(n) && n > maxNum) {
        maxNum = n;
        padLength = Math.max(padLength, nStr.length);
      }
    }
  };

  try {
    // 1. Check local synced vouchers in IndexedDB
    if (companyId) {
      const cached = await offlineDb.syncedVouchers
        .where('companyId')
        .equals(companyId)
        .filter((v) => v.voucherType === vTypeUpper)
        .toArray();

      for (const v of cached) {
        inspectNumber(v.voucherNumber);
      }
    }

    // 2. Check operations queued in operationLog
    const pendingOps = await offlineDb.operationLog
      .filter((op) => {
        const p = op.payload || {};
        return (!companyId || p.company_id === companyId) && String(p.voucher_type || 'SALES').toUpperCase() === vTypeUpper;
      })
      .toArray();

    for (const op of pendingOps) {
      inspectNumber(op.payload?.voucher_number);
    }

    // 3. Check legacy vouchers table
    const legacy = await offlineDb.vouchers
      .filter((v) => {
        return (!companyId || v.payload?.company_id === companyId) && String(v.voucherType || 'SALES').toUpperCase() === vTypeUpper;
      })
      .toArray();

    for (const v of legacy) {
      inspectNumber(v.voucherNumber);
      inspectNumber(v.payload?.voucher_number);
    }
  } catch (err) {
    console.warn('[SequenceService] Error inspecting offlineDb:', err);
  }

  // 4. Check cached values from localStorage
  if (typeof localStorage !== 'undefined' && companyId) {
    const lastNumKey = `vouch_last_sales_seq_${companyId}`;
    const storedLast = localStorage.getItem(lastNumKey);
    if (storedLast) {
      const n = parseInt(storedLast, 10);
      if (!isNaN(n) && n > maxNum) {
        maxNum = n;
      }
    }

    // Also inspect any online next sequence pre-cached before disconnecting
    const nextSeqKey = `vouch_next_seq_${companyId}_${vTypeUpper}`;
    const preCachedNext = localStorage.getItem(nextSeqKey);
    if (preCachedNext) {
      inspectNumber(preCachedNext);
    }
  }

  const nextNumber = maxNum + 1;

  // Format into official, continuous invoice number compliant with GST Rule 46(b)
  if (detectedPattern === 'SLASH_FY') {
    return `${detectedPrefix}/${detectedFy || currentFyCode}/${String(nextNumber).padStart(padLength, '0')}`;
  } else if (detectedPattern === 'DASH') {
    return `${detectedPrefix}-${String(nextNumber).padStart(padLength, '0')}`;
  } else if (detectedPattern === 'NUMERIC') {
    return String(nextNumber).padStart(padLength, '0');
  } else {
    // Default fallback format
    return `${detectedPrefix}/${currentFyCode}/${String(nextNumber).padStart(4, '0')}`;
  }
}

/**
 * Updates localStorage so the immediate next offline bill created in the same session
 * monotonically advances (e.g. 145 -> 146 -> 147).
 */
export function advanceOfflineSequence(companyId: string, assignedVoucherNumber: string): void {
  if (typeof localStorage === 'undefined' || !companyId || !assignedVoucherNumber) return;
  const match = String(assignedVoucherNumber).trim().match(/(\d+)$/);
  if (match) {
    const num = parseInt(match[1], 10);
    if (!isNaN(num) && num > 0) {
      const lastKey = `vouch_last_sales_seq_${companyId}`;
      const current = parseInt(localStorage.getItem(lastKey) || '0', 10);
      if (num > current) {
        localStorage.setItem(lastKey, String(num));
      }
    }
  }
}
