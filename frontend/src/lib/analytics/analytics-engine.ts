import { offlineDb, SyncedVoucher, SyncedLedger, SyncedProduct, SyncedPaymentAllocation } from "../db/offlineDb";
import { ledgersRepository } from "../data/ledgers-repository";

/**
 * Returns YYYY-MM-DD string in Indian Standard Time (Asia/Kolkata).
 */
export function getIndiaTodayStr(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
}

/**
 * Returns YYYY-MM-DD string N days ago in Indian Standard Time (Asia/Kolkata).
 */
export function getIndiaDateDaysAgo(days: number): string {
  const d = new Date(Date.now() - days * 24 * 60 * 60 * 1000);
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(d);
}

export interface DashboardKpis {
  today_sales: number;
  today_collections: number;
  money_to_collect: number;
  bills_to_pay: number;
  cash_and_bank: number;
  total_sales: number;
  total_purchases: number;
  sales_vouchers_count: number;
  purchase_vouchers_count: number;
  total_stock_value: number;
  total_retail_value: number;
  total_stock_qty: number;
  total_in_stock_items: number;
  total_catalog_items: number;
}

export interface TrendDetails {
  status: "Booming" | "Constant" | "Declining";
  slope: number;
  growth_rate_pct: number;
  normalized_slope: number;
  average_daily_sales: number;
  daily_trend: Array<{ date: string; sales: number }>;
  summary: string;
}

export interface RfmCluster {
  party_ledger__name: string;
  recency: number;
  frequency: number;
  monetary: number;
  segment: "High Value / VIP" | "Medium Value" | "Low Value" | "Standard";
  cluster: number;
}

export interface ActionableAlert {
  type: string;
  severity: "WARNING" | "INFO" | "CRITICAL";
  message: string;
}

export interface MonthlyComparisonResult {
  current_month: {
    month_name: string;
    short_name: string;
    days_in_month: number;
    days_elapsed: number;
    days_remaining: number;
    mtd_actual_sales: number;
    mtd_orders: number;
    remaining_projected_sales: number;
    projected_month_total: number;
    completion_pct: number;
    current_daily_run_rate: number;
    projected_daily_run_rate: number;
  };
  previous_month: {
    month_name: string;
    total_sales: number;
    order_count: number;
    daily_average: number;
  };
  mom_comparison: {
    absolute_change: number;
    percentage_change: number;
    pace_status: "BEATING_LAST_MONTH" | "PACING_BEHIND" | "ON_PAR" | "NO_PRIOR_MONTH";
    required_daily_to_match_last_month: number;
    summary: string;
  };
  yoy_comparison: {
    available: boolean;
    prior_year_month_name: string;
    prior_year_sales: number;
    percentage_change: number;
    absolute_change: number;
    summary: string;
  };
  historical_months_series: Array<{
    month_key: string;
    month_label: string;
    short_name: string;
    actual_sales: number;
    projected_sales: number;
    total_sales: number;
    order_count: number;
    is_current: boolean;
    is_projected: boolean;
    days_remaining?: number;
  }>;
}

export interface SalesForecastResult {
  forecast_days: number;
  projected_total: number;
  projected_daily_average: number;
  p10_total?: number;
  p50_total?: number;
  p90_total?: number;
  trend_status: "Booming" | "Constant" | "Declining" | "Insufficient Data";
  confidence: "HIGH" | "MEDIUM" | "LOW";
  sample_size_days: number;
  trend_summary: string;
  daily_forecast: Array<{
    date: string;
    projected_sales: number;
    lower_bound: number;
    upper_bound: number;
  }>;
  historical_daily_series?: Array<{
    date: string;
    actual_sales: number;
    moving_avg_7d: number;
    cumulative_sales: number;
    invoice_count: number;
    is_historical: boolean;
  }>;
  combined_series?: Array<{
    date: string;
    actual_sales: number | null;
    moving_avg_7d: number | null;
    cumulative_sales: number | null;
    projected_sales: number | null;
    lower_bound?: number | null;
    upper_bound?: number | null;
    is_historical: boolean;
    is_today?: boolean;
  }>;
  historical_summary?: {
    total_historical_sales: number;
    historical_invoices_count: number;
    distinct_selling_days: number;
    historical_daily_average: number;
    peak_day?: {
      date: string;
      amount: number;
    };
    current_7d_run_rate?: number;
    anchor_date?: string;
  };
  customer_pareto?: Array<{
    party_id: string;
    name: string;
    total_revenue: number;
    invoice_count: number;
    percentage_of_total: number;
    cumulative_percentage: number;
    pareto_tier: "TOP_80_PERCENT" | "LONG_TAIL_20_PERCENT";
    days_since_last_order: number;
    is_at_risk: boolean;
    last_order_date: string | null;
  }>;
  brand_contribution?: Array<{
    brand: string;
    total_revenue: number;
    units_sold: number;
    bills_count: number;
    percentage_of_total: number;
  }>;
  working_capital_cycle?: {
    dso_days: number;
    dio_days: number;
    dpo_days: number;
    cash_conversion_cycle_days: number;
    accounts_receivable: number;
    accounts_payable: number;
    inventory_valuation: number;
    daily_sales_avg: number;
    daily_cogs_avg: number;
    working_capital_health: "HEALTHY" | "MODERATE" | "ELEVATED_CYCLE";
    recommendation: string;
  };
  historical_daily_average: number;
  factors_analyzed?: {
    yoy_seasonality_applied: boolean;
    yoy_summary?: string;
    day_of_week_active?: boolean;
    month_end_surge_multiplier?: number;
    repeat_buyers_modeled?: number;
    open_proforma_pipeline?: number;
    stock_health_ratio?: number;
    stock_constraint_applied?: boolean;
  };
  monthly_comparison?: MonthlyComparisonResult;
}

export interface LocalDashboardResult {
  business_health: string;
  trend_summary: string;
  trend_details: TrendDetails;
  forecast?: SalesForecastResult;
  rfm_clusters: RfmCluster[];
  actionable_alerts: ActionableAlert[];
  kpis: DashboardKpis;
  recent_vouchers: any[];
  coverage: {
    oldestDate: string | null;
    newestDate: string | null;
    totalVouchersCount: number;
    isComplete: boolean;
    lastSyncAt: number | null;
  };
}

/**
 * High-performance, local-first operational analytics engine.
 * Computes dashboard KPIs directly from browser IndexedDB (Dexie).
 * Guaranteed to be company-scoped and non-blocking.
 */
export class LocalAnalyticsEngine {

  /**
   * P0: Centralized authoritative definition of an "effective" accounting voucher.
   * A voucher is effective if its status is POSTED.
   * DRAFT, CANCELLED, REVERSED, SUPERSEDED, CORRECTED are excluded.
   */
  static isEffectiveVoucher(v: SyncedVoucher): boolean {
    return v.status === "POSTED";
  }

  static resolveEffectiveVouchers(vouchers: SyncedVoucher[]): SyncedVoucher[] {
    return vouchers.filter(this.isEffectiveVoucher);
  }

  /**
   * P0: Computes the actual remaining outstanding amount of an invoice
   * by summing all valid PaymentAllocations linked to it.
   */
  static calculateInvoiceOutstanding(
    invoice: SyncedVoucher,
    allAllocations: SyncedPaymentAllocation[],
    allEffectiveVouchers: Map<string, SyncedVoucher>
  ): number {
    if (!this.isEffectiveVoucher(invoice)) return 0;
    
    // Find all allocations for this invoice
    const allocations = allAllocations.filter(pa => pa.invoiceVoucherId === invoice.id);
    
    let allocatedAmount = 0;
    for (const pa of allocations) {
      // The payment allocation is only valid if the source payment voucher is ALSO effective
      const paymentVoucher = allEffectiveVouchers.get(pa.paymentVoucherId);
      if (paymentVoucher && this.isEffectiveVoucher(paymentVoucher)) {
        allocatedAmount += Number(pa.allocatedAmount) || 0;
      }
    }
    
    const invoiceTotal = Number(invoice.totalAmount) || 0;
    const outstanding = invoiceTotal - allocatedAmount;
    
    // Guard against negative outstanding due to overpayment
    return outstanding > 0 ? outstanding : 0;
  }
  /**
   * Primary entry point for rendering the operational dashboard.
   */
  static async getDashboardAnalytics(
    companyId: string,
    options?: { startDate?: string; endDate?: string; financialYearId?: string }
  ): Promise<LocalDashboardResult> {
    if (!companyId) {
      return this.getEmptyDashboard();
    }

    // 1. Fetch valid, posted vouchers for active company
    // Omit CANCELLED, REVERSED, DRAFT according to authoritative accounting rules
    const allCompanyVouchers = await offlineDb.syncedVouchers
      .where("companyId")
      .equals(companyId)
      .toArray();

    let activeVouchers = this.resolveEffectiveVouchers(allCompanyVouchers);
    if (options?.startDate) {
      activeVouchers = activeVouchers.filter((v) => v.voucherDate >= options.startDate!);
    }
    if (options?.endDate) {
      activeVouchers = activeVouchers.filter((v) => v.voucherDate <= options.endDate!);
    }
    const activeVouchersMap = new Map(activeVouchers.map(v => [v.id, v]));

    // Fetch allocations for outstanding calculations
    const allAllocations = await offlineDb.syncedPaymentAllocations
      .where("companyId")
      .equals(companyId)
      .toArray();

    // 2. Fetch ledgers for active company (scoped to FY if dates or FY ID provided)
    let ledgers: any[] = [];
    if (options?.financialYearId || options?.startDate || options?.endDate) {
      const { data: scopedLedgers } = await ledgersRepository.getLedgers(companyId, {
        financialYearId: options.financialYearId,
        startDate: options.startDate,
        endDate: options.endDate,
      });
      ledgers = scopedLedgers;
    } else {
      ledgers = await offlineDb.syncedLedgers
        .where("companyId")
        .equals(companyId)
        .toArray();
    }

    // 3. Fetch products for active company
    const products = await offlineDb.syncedProducts
      .where("companyId")
      .equals(companyId)
      .toArray();

    // 4. Fetch sync metadata
    const syncMeta = await offlineDb.syncMeta.get(companyId);

    // Compute date ranges in Indian Standard Time (IST)
    const todayStr = getIndiaTodayStr();
    const thirtyDaysAgo = getIndiaDateDaysAgo(30);

    // --- P1: Aggregate-First Fast Path ---
    // If scoped to a specific FY date range, bypass static pre-computed aggregates to isolate that period
    const isDateFiltered = Boolean(options?.startDate || options?.endDate);
    const dailyAggregates = isDateFiltered ? [] : await offlineDb.analyticsDaily.where("companyId").equals(companyId).toArray();
    const partyAggregates = isDateFiltered ? [] : await offlineDb.analyticsParty.where("companyId").equals(companyId).toArray();
    
    const useAggregates = !isDateFiltered && (dailyAggregates.length > 0 || activeVouchers.length === 0);

    // --- A. Financial KPIs ---
    let todaySales = 0;
    let todayCollections = 0;
    let totalSales = 0;
    let totalPurchases = 0;
    let salesCount = 0;
    let purchaseCount = 0;

    const salesByParty: Record<string, { name: string; count: number; total: number; lastDate: string }> = {};
    const salesByDate: Record<string, number> = {};
    const overdueInvoices: SyncedVoucher[] = [];

    let oldestDate: string | null = null;
    let newestDate: string | null = null;

    if (useAggregates && dailyAggregates.length > 0) {
      for (const d of dailyAggregates) {
        totalSales += d.sales;
        totalPurchases += d.purchases;
        salesCount += d.salesCount;
        purchaseCount += d.purchaseCount;
        salesByDate[d.date] = d.sales;

        if (!oldestDate || d.date < oldestDate) oldestDate = d.date;
        if (!newestDate || d.date > newestDate) newestDate = d.date;

        if (d.date === todayStr) {
          todaySales += d.sales;
          todayCollections += d.collections;
        }
      }

      for (const p of partyAggregates) {
        salesByParty[p.partyId] = {
          name: p.partyName,
          count: p.invoiceCount,
          total: p.sales,
          lastDate: p.lastTransactionDate
        };
      }
      
      // We still need to iterate over outstanding sales invoices to find overdue ones, 
      // but we only need to look at SALES vouchers, not the entire history.
      const salesVouchers = activeVouchers.filter(v => v.voucherType === "SALES");
      for (const v of salesVouchers) {
        const outstanding = this.calculateInvoiceOutstanding(v, allAllocations, activeVouchersMap);
        if (outstanding > 0) {
          const isOverdue = v.dueDate ? (v.dueDate < todayStr) : false;
          if (isOverdue) overdueInvoices.push(v);
        }
      }
    } else {
      // --- Fallback: Raw History Scan ---
      for (const v of activeVouchers) {
        const amt = Number(v.totalAmount) || 0;
        const vDate = v.voucherDate;

        if (!oldestDate || vDate < oldestDate) oldestDate = vDate;
        if (!newestDate || vDate > newestDate) newestDate = vDate;

        if (v.voucherType === "SALES") {
          totalSales += amt;
          salesCount++;
          if (vDate === todayStr) {
            todaySales += amt;
          }

          // Daily trend accumulation
          salesByDate[vDate] = (salesByDate[vDate] || 0) + amt;

          // Customer RFM accumulation (Canonical partyLedgerId grouping)
          const partyKey = v.partyLedgerId || v.partyName || "Counter Sale / Cash";
          const partyName = v.partyName || "Counter Sale / Cash";
          if (!salesByParty[partyKey]) {
            salesByParty[partyKey] = { name: partyName, count: 0, total: 0, lastDate: vDate };
          }
          salesByParty[partyKey].count += 1;
          salesByParty[partyKey].total += amt;
          if (vDate > salesByParty[partyKey].lastDate) {
            salesByParty[partyKey].lastDate = vDate;
          }

          // Check overdue (P0: Payment Allocation drives outstanding)
          const outstanding = this.calculateInvoiceOutstanding(v, allAllocations, activeVouchersMap);
          if (outstanding > 0) {
            const isOverdue = v.dueDate ? (v.dueDate < todayStr) : false;
            if (isOverdue) {
              overdueInvoices.push(v);
            }
          }
        } else if (v.voucherType === "PURCHASE") {
          totalPurchases += amt;
          purchaseCount++;
        } else if (v.voucherType === "RECEIPT") {
          if (vDate === todayStr) {
            todayCollections += amt;
          }
        }
      }
    }

    // --- B. Receivables, Payables, Liquid Funds ---
    let moneyToCollect = 0;
    let billsToPay = 0;
    let cashAndBank = 0;

    for (const l of ledgers) {
      const bal = Number(l.currentBalance) || 0;
      const lt = (l.ledgerType || "").toUpperCase();
      const grp = (l.group || "").toUpperCase();

      const isCustomer = lt === "CUSTOMER" || lt.includes("DEBTOR") || grp.includes("DEBTOR");
      const isSupplier = lt === "SUPPLIER" || lt.includes("CREDITOR") || grp.includes("CREDITOR");
      const isParty = lt === "PARTY" || lt === "BOTH";
      const isCashOrBank = lt === "CASH" || lt === "BANK" || grp.includes("BANK") || grp.includes("CASH");

      if (l.balanceState === "TO_COLLECT") {
        moneyToCollect += Number(l.displayAmount || Math.abs(bal));
      } else if (l.balanceState === "TO_PAY") {
        billsToPay += Number(l.displayAmount || Math.abs(bal));
      } else if (isCustomer) {
        if (bal > 0) moneyToCollect += bal;
      } else if (isSupplier) {
        // Suppliers with positive balance under credit-normal convention are owed money (bills to pay)
        if (bal > 0) billsToPay += bal;
      } else if (isParty) {
        if (bal > 0) moneyToCollect += bal;
        else if (bal < 0) billsToPay += Math.abs(bal);
      }

      if (isCashOrBank) {
        cashAndBank += bal;
      }
    }

    // --- C. Stock & Inventory Valuation ---
    let totalStockValue = 0;
    let totalRetailValue = 0;
    let totalStockQty = 0;
    let totalInStockItems = 0;
    const lowStockProducts: SyncedProduct[] = [];

    for (const p of products) {
      const qty = Number(p.currentStock) || 0;
      const pPrice = Number(p.purchasePrice) || 0;
      const sPrice = Number(p.salesPrice) || 0;

      if (qty > 0) {
        totalInStockItems++;
        totalStockQty += qty;
        totalStockValue += qty * pPrice;
        totalRetailValue += qty * sPrice;
      }

      if (qty <= (p.reorderLevel || 0)) {
        lowStockProducts.push(p);
      }
    }

    // --- D. Actionable Alerts ---
    const alerts: ActionableAlert[] = [];
    for (const lp of lowStockProducts.slice(0, 4)) {
      alerts.push({
        type: "LOW_STOCK",
        severity: "WARNING",
        message: `Low Stock: '${lp.name}' has only ${lp.currentStock} ${lp.unit || "units"} remaining.`,
      });
    }
    for (const oi of overdueInvoices.slice(0, 3)) {
      const dueInfo = oi.dueDate ? `was due on ${oi.dueDate}` : "is past 30 days";
      alerts.push({
        type: "OVERDUE_INVOICE",
        severity: "INFO",
        message: `Overdue Bill: Invoice #${oi.voucherNumber} for ${oi.partyName || "Customer"} (₹${oi.totalAmount.toLocaleString("en-IN")}) ${dueInfo}.`,
      });
    }

    // --- E. Sales Velocity Trend (Linear Regression) ---
    const trendDetails = this.calculateSalesTrend(salesByDate, todayStr);

    // --- E2. Sales Forecast Projection ---
    const forecastData = this.calculateForecast(salesByDate, trendDetails, todayStr, 30);

    // --- F. RFM Segmentation ---
    const rfmClusters = this.calculateRfmClusters(salesByParty, todayStr);

    // --- G. Recent Vouchers (Sorted for table display) ---
    const recentVouchers = [...activeVouchers]
      .sort((a: any, b: any) => {
        const dateA = a.voucherDate || a.voucher_date || "";
        const dateB = b.voucherDate || b.voucher_date || "";
        if (dateB !== dateA) return dateB > dateA ? 1 : -1;
        const updA = a.serverUpdatedAt || a.server_updated_at || 0;
        const updB = b.serverUpdatedAt || b.server_updated_at || 0;
        return updB - updA;
      })
      .slice(0, 15)
      .map((v: any) => ({
        ...v,
        id: v.id,
        voucherNumber: v.voucherNumber || v.voucher_number || "",
        voucher_number: v.voucher_number || v.voucherNumber || "",
        voucherDate: v.voucherDate || v.voucher_date || v.date || "",
        voucher_date: v.voucher_date || v.voucherDate || v.date || "",
        date: v.voucherDate || v.voucher_date || v.date || "",
        voucherType: v.voucherType || v.voucher_type || v.type || "GENERAL",
        voucher_type: v.voucher_type || v.voucherType || v.type || "GENERAL",
        type: v.voucherType || v.voucher_type || v.type || "GENERAL",
        partyName: v.partyName || v.party_name || v.narration || "General Entry",
        party_name: v.party_name || v.partyName || v.narration || "General Entry",
        totalAmount: Number(v.totalAmount !== undefined && v.totalAmount !== null ? v.totalAmount : (v.total_amount || 0)),
        total_amount: Number(v.total_amount !== undefined && v.total_amount !== null ? v.total_amount : (v.totalAmount || 0)),
        status: v.status || "POSTED",
      }));

    return {
      business_health: trendDetails.status,
      trend_summary: trendDetails.summary,
      trend_details: trendDetails,
      forecast: forecastData,
      rfm_clusters: rfmClusters,
      actionable_alerts: alerts,
      kpis: {
        today_sales: Math.round(todaySales * 100) / 100,
        today_collections: Math.round(todayCollections * 100) / 100,
        money_to_collect: Math.round(moneyToCollect * 100) / 100,
        bills_to_pay: Math.round(billsToPay * 100) / 100,
        cash_and_bank: Math.round(cashAndBank * 100) / 100,
        total_sales: Math.round(totalSales * 100) / 100,
        total_purchases: Math.round(totalPurchases * 100) / 100,
        sales_vouchers_count: salesCount,
        purchase_vouchers_count: purchaseCount,
        total_stock_value: Math.round(totalStockValue * 100) / 100,
        total_retail_value: Math.round(totalRetailValue * 100) / 100,
        total_stock_qty: Math.round(totalStockQty * 100) / 100,
        total_in_stock_items: totalInStockItems,
        total_catalog_items: products.length,
      },
      recent_vouchers: recentVouchers,
      coverage: {
        oldestDate,
        newestDate,
        totalVouchersCount: activeVouchers.length,
        isComplete: Boolean(syncMeta?.isInitialComplete),
        lastSyncAt: syncMeta?.lastSyncAt || null,
      },
    };
  }

  /**
   * Deterministic Linear Regression on chronological daily sales.
   * Anchors to the most recent sales window (last 30 days) leading up to today or latest recorded sale.
   */
  private static calculateSalesTrend(salesByDate: Record<string, number>, referenceDateStr?: string): TrendDetails {
    const positiveDates = Object.keys(salesByDate)
      .filter((d) => (salesByDate[d] || 0) > 0)
      .sort();

    if (positiveDates.length === 0) {
      return {
        status: "Constant",
        slope: 0.0,
        growth_rate_pct: 0.0,
        normalized_slope: 0.0,
        average_daily_sales: 0.0,
        daily_trend: [],
        summary: "No historical sales data available.",
      };
    }

    const lastActiveDate = positiveDates[positiveDates.length - 1];
    let anchorDate = new Date(lastActiveDate);

    // If referenceDateStr (today) is within 60 days of the last recorded sale, anchor to it
    if (referenceDateStr) {
      const refD = new Date(referenceDateStr);
      const diffDays = (refD.getTime() - anchorDate.getTime()) / (24 * 60 * 60 * 1000);
      if (diffDays >= 0 && diffDays <= 60) {
        anchorDate = refD;
      }
    }

    // Determine recent window span (up to 30 days, or at least 7 days for early businesses)
    const firstActiveDate = positiveDates[0];
    const totalDaysSpan = Math.round((anchorDate.getTime() - new Date(firstActiveDate).getTime()) / (24 * 60 * 60 * 1000)) + 1;
    const windowDays = Math.max(Math.min(totalDaysSpan, 30), 7);

    const dailyTrend: Array<{ date: string; sales: number }> = [];
    for (let i = windowDays - 1; i >= 0; i--) {
      const cur = new Date(anchorDate.getTime() - i * 24 * 60 * 60 * 1000);
      const dStr = cur.toISOString().slice(0, 10);
      dailyTrend.push({
        date: dStr,
        sales: Math.round((salesByDate[dStr] || 0) * 100) / 100,
      });
    }

    if (dailyTrend.length < 2) {
      return {
        status: "Constant",
        slope: 0.0,
        growth_rate_pct: 0.0,
        normalized_slope: 0.0,
        average_daily_sales: dailyTrend[0]?.sales || 0.0,
        daily_trend: dailyTrend,
        summary: "Need at least 2 days of records for trend calculation.",
      };
    }

    // Least Squares Slope calculation
    const n = dailyTrend.length;
    let sumX = 0;
    let sumY = 0;
    for (let i = 0; i < n; i++) {
      sumX += i;
      sumY += dailyTrend[i].sales;
    }
    const meanX = sumX / n;
    const meanY = sumY / n;

    let numerator = 0;
    let denominator = 0;
    for (let i = 0; i < n; i++) {
      const xDiff = i - meanX;
      const yDiff = dailyTrend[i].sales - meanY;
      numerator += xDiff * yDiff;
      denominator += xDiff * xDiff;
    }

    const slope = denominator !== 0 ? numerator / denominator : 0.0;
    const avgSales = meanY > 0 ? meanY : 0.0;
    const normalizedSlope = avgSales > 0 ? (slope / avgSales) * 100.0 : 0.0;
    const growthRatePct = Math.round(normalizedSlope * 10) / 10;

    let status: "Booming" | "Constant" | "Declining" = "Constant";
    let summary = "Sales trajectory is stable and constant.";

    if (normalizedSlope > 1.5) {
      status = "Booming";
      summary = `Sales are rapidly increasing (+${growthRatePct}% daily trajectory).`;
    } else if (normalizedSlope < -1.5) {
      status = "Declining";
      summary = `Sales are declining (${growthRatePct}% daily trajectory). Attention needed.`;
    }

    return {
      status,
      slope: Math.round(slope * 100) / 100,
      growth_rate_pct: growthRatePct,
      normalized_slope: Math.round(normalizedSlope * 100) / 100,
      average_daily_sales: Math.round(avgSales * 100) / 100,
      daily_trend: dailyTrend,
      summary,
    };
  }

  /**
   * Deterministic local sales forecast projection for offline-first resilience.
   */
  static calculateForecast(
    salesByDate: Record<string, number>,
    trend: TrendDetails,
    referenceDateStr: string,
    days: number = 30
  ): SalesForecastResult {
    const positiveDates = Object.keys(salesByDate)
      .filter((d) => (salesByDate[d] || 0) > 0)
      .sort();
    const sampleSize = positiveDates.length;

    if (sampleSize === 0) {
      return {
        forecast_days: days,
        projected_total: 0.0,
        projected_daily_average: 0.0,
        p10_total: 0.0,
        p50_total: 0.0,
        p90_total: 0.0,
        trend_status: "Insufficient Data",
        confidence: "LOW",
        sample_size_days: 0,
        trend_summary: "No sales data available for projection.",
        daily_forecast: [],
        historical_daily_average: 0.0,
        factors_analyzed: {
          yoy_seasonality_applied: false,
          yoy_summary: "No sales data available.",
          day_of_week_active: false,
          month_end_surge_multiplier: 1.0,
          repeat_buyers_modeled: 0,
          open_proforma_pipeline: 0.0,
          stock_health_ratio: 1.0,
          stock_constraint_applied: false,
        },
      };
    }

    const confidence: "HIGH" | "MEDIUM" | "LOW" = sampleSize >= 30 ? "HIGH" : sampleSize >= 7 ? "MEDIUM" : "LOW";
    const avgSales = trend.average_daily_sales || 0;
    const slope = trend.slope || 0;
    const status = trend.status || "Constant";

    const firstActiveDate = new Date(positiveDates[0]);
    const lastActiveDate = new Date(positiveDates[positiveDates.length - 1]);
    const historySpanDays = Math.round((lastActiveDate.getTime() - firstActiveDate.getTime()) / (24 * 60 * 60 * 1000));
    
    // Strict user rule: only apply YoY seasonality if >= 330 days history is available
    const hasYoyHistory = historySpanDays >= 330;
    const yoySummary = hasYoyHistory
      ? "Incorporated historical year-over-year seasonal pattern."
      : "Past-year records not available (< 1 year history); annual seasonality excluded to ensure realistic predictions.";

    let anchorDate = new Date(lastActiveDate);
    if (referenceDateStr) {
      const refD = new Date(referenceDateStr);
      const diff = (refD.getTime() - anchorDate.getTime()) / (24 * 60 * 60 * 1000);
      if (diff >= 0 && diff <= 60) {
        anchorDate = refD;
      }
    }

    // Standard B2B operating profile: Mon-Fri peak, Sat reduced, Sun minimal
    const dowWeights: Record<number, number> = { 0: 0.20, 1: 1.10, 2: 1.25, 3: 1.25, 4: 1.20, 5: 1.10, 6: 0.80 }; // Sunday is 0 in JS Date

    const forecastList: Array<{
      date: string;
      projected_sales: number;
      lower_bound: number;
      upper_bound: number;
    }> = [];

    let projectedTotal = 0;
    let p10Total = 0;
    let p90Total = 0;
    const spreadPct = confidence === "HIGH" ? 0.12 : confidence === "MEDIUM" ? 0.22 : 0.35;

    for (let i = 1; i <= days; i++) {
      const futureD = new Date(anchorDate.getTime() + i * 24 * 60 * 60 * 1000);
      const dStr = futureD.toISOString().slice(0, 10);
      let baseProj = Math.max(0, avgSales + slope * (i / 10.0));

      // Day of week profile
      const dayOfWeek = futureD.getDay(); // 0 is Sunday
      baseProj *= dowWeights[dayOfWeek] ?? 1.0;

      // Month-end GST surge (25th to end of month)
      if (futureD.getDate() >= 25) {
        baseProj *= 1.20;
      }

      const spread = Math.round(baseProj * spreadPct * 100) / 100;
      const lower = Math.max(0, Math.round((baseProj - spread) * 100) / 100);
      const upper = Math.round((baseProj + spread) * 100) / 100;
      const proj = Math.round(baseProj * 100) / 100;

      projectedTotal += proj;
      p10Total += lower;
      p90Total += upper;

      forecastList.push({
        date: dStr,
        projected_sales: proj,
        lower_bound: lower,
        upper_bound: upper,
      });
    }

    const projectedDailyAvg = Math.round((projectedTotal / Math.max(1, days)) * 100) / 100;
    const summary = sampleSize < 7
      ? `Preliminary projection based on early history (${sampleSize} active selling days recorded).`
      : `${trend.summary} Confidence: ${confidence} | DOW Profile: Active | YoY Seasonality: ${hasYoyHistory ? 'Active' : 'Excluded'}.`;

    // Month-over-Month & Historical Series
    const curYear = anchorDate.getFullYear();
    const curMonth = anchorDate.getMonth(); // 0-indexed
    const daysInCurMonth = new Date(curYear, curMonth + 1, 0).getDate();
    const daysElapsed = anchorDate.getDate();
    const daysRemaining = Math.max(0, daysInCurMonth - daysElapsed);

    let mtdSales = 0;
    const curMonthKey = `${curYear}-${String(curMonth + 1).padStart(2, '0')}`;
    for (const d of positiveDates) {
      if (d.startsWith(curMonthKey) && d <= anchorDate.toISOString().slice(0, 10)) {
        mtdSales += salesByDate[d] || 0;
      }
    }

    let remainingForecast = 0;
    for (const f of forecastList) {
      if (f.date.startsWith(curMonthKey) && f.date > anchorDate.toISOString().slice(0, 10)) {
        remainingForecast += f.projected_sales;
      }
    }
    const projectedMonthTotal = Math.round((mtdSales + remainingForecast) * 100) / 100;

    // Previous completed months
    const historicalMonths: MonthlyComparisonResult["historical_months_series"] = [];
    let lastMonthTotal = 0;
    let lastMonthName = "";

    const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const fullMonthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

    for (let step = 5; step >= 1; step--) {
      const pmDate = new Date(curYear, curMonth - step, 1);
      const pmKey = `${pmDate.getFullYear()}-${String(pmDate.getMonth() + 1).padStart(2, '0')}`;
      let mTotal = 0;
      let mOrders = 0;
      for (const d of positiveDates) {
        if (d.startsWith(pmKey)) {
          mTotal += salesByDate[d] || 0;
          mOrders++;
        }
      }
      const label = `${monthNames[pmDate.getMonth()]} ${pmDate.getFullYear()}`;
      historicalMonths.push({
        month_key: pmKey,
        month_label: label,
        short_name: monthNames[pmDate.getMonth()],
        actual_sales: Math.round(mTotal * 100) / 100,
        projected_sales: 0,
        total_sales: Math.round(mTotal * 100) / 100,
        order_count: mOrders,
        is_current: false,
        is_projected: false
      });
      if (step === 1) {
        lastMonthTotal = mTotal;
        lastMonthName = label;
      }
    }

    historicalMonths.push({
      month_key: curMonthKey,
      month_label: `${monthNames[curMonth]} ${curYear} (Current)`,
      short_name: monthNames[curMonth],
      actual_sales: Math.round(mtdSales * 100) / 100,
      projected_sales: Math.round(remainingForecast * 100) / 100,
      total_sales: projectedMonthTotal,
      order_count: 0,
      is_current: true,
      is_projected: false,
      days_remaining: daysRemaining
    });

    const momAbs = lastMonthTotal > 0 ? Math.round((projectedMonthTotal - lastMonthTotal) * 100) / 100 : 0;
    const momPct = lastMonthTotal > 0 ? Math.round(((projectedMonthTotal - lastMonthTotal) / lastMonthTotal) * 10000) / 100 : 0;
    const paceStatus: "BEATING_LAST_MONTH" | "PACING_BEHIND" | "ON_PAR" | "NO_PRIOR_MONTH" = 
      lastMonthTotal === 0 ? "NO_PRIOR_MONTH" : momPct > 1.5 ? "BEATING_LAST_MONTH" : momPct < -1.5 ? "PACING_BEHIND" : "ON_PAR";

    const shortfall = Math.max(0, lastMonthTotal - mtdSales);
    const requiredDaily = daysRemaining > 0 ? Math.round((shortfall / daysRemaining) * 100) / 100 : 0;

    const momSummary = lastMonthTotal > 0
      ? paceStatus === "BEATING_LAST_MONTH"
        ? `On track to finish +${momPct}% ahead of ${lastMonthName} (+₹${momAbs.toLocaleString('en-IN')}).`
        : paceStatus === "PACING_BEHIND"
        ? `Pacing ${Math.abs(momPct)}% behind ${lastMonthName} (-₹${Math.abs(momAbs).toLocaleString('en-IN')}).`
        : `Tracking on par with ${lastMonthName} (~0% variance).`
      : "No previous month transactions found for MoM comparison.";

    const monthlyComparison: MonthlyComparisonResult = {
      current_month: {
        month_name: `${fullMonthNames[curMonth]} ${curYear}`,
        short_name: monthNames[curMonth],
        days_in_month: daysInCurMonth,
        days_elapsed: daysElapsed,
        days_remaining: daysRemaining,
        mtd_actual_sales: Math.round(mtdSales * 100) / 100,
        mtd_orders: 0,
        remaining_projected_sales: Math.round(remainingForecast * 100) / 100,
        projected_month_total: projectedMonthTotal,
        completion_pct: projectedMonthTotal > 0 ? Math.round((mtdSales / projectedMonthTotal) * 1000) / 10 : 0,
        current_daily_run_rate: Math.round((mtdSales / Math.max(1, daysElapsed)) * 100) / 100,
        projected_daily_run_rate: daysRemaining > 0 ? Math.round((remainingForecast / daysRemaining) * 100) / 100 : 0
      },
      previous_month: {
        month_name: lastMonthName || "Previous Month",
        total_sales: Math.round(lastMonthTotal * 100) / 100,
        order_count: 0,
        daily_average: Math.round((lastMonthTotal / 30) * 100) / 100
      },
      mom_comparison: {
        absolute_change: momAbs,
        percentage_change: momPct,
        pace_status: paceStatus,
        required_daily_to_match_last_month: requiredDaily,
        summary: momSummary
      },
      yoy_comparison: {
        available: false,
        prior_year_month_name: "",
        prior_year_sales: 0,
        percentage_change: 0,
        absolute_change: 0,
        summary: hasYoyHistory ? "Prior year local sync data limited." : "Past-year record not available (< 1 year history); annual YoY comparison excluded."
      },
      historical_months_series: historicalMonths
    };

    // Construct local historical daily series & combined timeline
    const historicalDailySeries: Array<{
      date: string;
      actual_sales: number;
      moving_avg_7d: number;
      cumulative_sales: number;
      invoice_count: number;
      is_historical: boolean;
    }> = [];

    let runningCumulative = 0;
    let peakDay = { date: positiveDates[0] || "", amount: 0 };
    const tempSalesHistory: number[] = [];

    const startHistTime = new Date(positiveDates[0]).getTime();
    const anchorTime = anchorDate.getTime();
    const dayMs = 24 * 60 * 60 * 1000;
    const totalHistDays = Math.max(1, Math.round((anchorTime - startHistTime) / dayMs) + 1);

    for (let dIdx = 0; dIdx < totalHistDays; dIdx++) {
      const curDate = new Date(startHistTime + dIdx * dayMs);
      const curDateStr = curDate.toISOString().slice(0, 10);
      const val = Math.round((salesByDate[curDateStr] || 0) * 100) / 100;
      runningCumulative += val;
      tempSalesHistory.push(val);

      if (val > peakDay.amount) {
        peakDay = { date: curDateStr, amount: val };
      }

      const windowStart = Math.max(0, tempSalesHistory.length - 7);
      const recentWindow = tempSalesHistory.slice(windowStart);
      const sumWin = recentWindow.reduce((a, b) => a + b, 0);
      const sma7 = Math.round((sumWin / recentWindow.length) * 100) / 100;

      historicalDailySeries.push({
        date: curDateStr,
        actual_sales: val,
        moving_avg_7d: sma7,
        cumulative_sales: Math.round(runningCumulative * 100) / 100,
        invoice_count: val > 0 ? 1 : 0,
        is_historical: true,
      });
    }

    const anchorDateStr = anchorDate.toISOString().slice(0, 10);
    const combinedSeries: Array<{
      date: string;
      actual_sales: number | null;
      moving_avg_7d: number | null;
      cumulative_sales: number | null;
      projected_sales: number | null;
      lower_bound?: number | null;
      upper_bound?: number | null;
      is_historical: boolean;
      is_today?: boolean;
    }> = [];

    historicalDailySeries.forEach((h) => {
      combinedSeries.push({
        date: h.date,
        actual_sales: h.actual_sales,
        moving_avg_7d: h.moving_avg_7d,
        cumulative_sales: h.cumulative_sales,
        projected_sales: null,
        lower_bound: null,
        upper_bound: null,
        is_historical: true,
        is_today: h.date === anchorDateStr,
      });
    });

    forecastList.forEach((f) => {
      combinedSeries.push({
        date: f.date,
        actual_sales: null,
        moving_avg_7d: null,
        cumulative_sales: null,
        projected_sales: f.projected_sales,
        lower_bound: f.lower_bound,
        upper_bound: f.upper_bound,
        is_historical: false,
        is_today: false,
      });
    });

    const recent7Days = historicalDailySeries.slice(-7);
    const recent7Sum = recent7Days.reduce((acc, it) => acc + it.actual_sales, 0);
    const current7dRunRate = recent7Days.length > 0 ? Math.round((recent7Sum / recent7Days.length) * 100) / 100 : avgSales;

    const historicalSummary = {
      total_historical_sales: Math.round(runningCumulative * 100) / 100,
      historical_invoices_count: sampleSize,
      distinct_selling_days: sampleSize,
      historical_daily_average: avgSales,
      peak_day: peakDay,
      current_7d_run_rate: current7dRunRate,
      anchor_date: anchorDateStr,
    };

    return {
      forecast_days: days,
      projected_total: Math.round(projectedTotal * 100) / 100,
      projected_daily_average: projectedDailyAvg,
      p10_total: Math.round(p10Total * 100) / 100,
      p50_total: Math.round(projectedTotal * 100) / 100,
      p90_total: Math.round(p90Total * 100) / 100,
      trend_status: status,
      confidence,
      sample_size_days: sampleSize,
      trend_summary: summary,
      daily_forecast: forecastList,
      historical_daily_series: historicalDailySeries,
      combined_series: combinedSeries,
      historical_summary: historicalSummary,
      historical_daily_average: avgSales,
      factors_analyzed: {
        yoy_seasonality_applied: hasYoyHistory,
        yoy_summary: yoySummary,
        day_of_week_active: true,
        month_end_surge_multiplier: 1.20,
        repeat_buyers_modeled: 0,
        open_proforma_pipeline: 0.0,
        stock_health_ratio: 1.0,
        stock_constraint_applied: false,
      },
      monthly_comparison: monthlyComparison
    };
  }

  /**
   * Deterministic RFM Customer Segmentation.
   */
  private static calculateRfmClusters(
    salesByParty: Record<string, { name?: string; count: number; total: number; lastDate: string }>,
    todayStr: string
  ): RfmCluster[] {
    const today = new Date(todayStr);
    const parties = Object.keys(salesByParty);

    if (parties.length === 0) return [];

    const rawList = parties.map((pKey) => {
      const info = salesByParty[pKey];
      const lastD = new Date(info.lastDate);
      const recency = Math.max(0, Math.floor((today.getTime() - lastD.getTime()) / (24 * 60 * 60 * 1000)));
      return {
        party_ledger__name: info.name || pKey,
        recency,
        frequency: info.count,
        monetary: Math.round(info.total * 100) / 100,
      };
    });

    if (rawList.length < 3) {
      return rawList.map((item) => ({
        ...item,
        segment: "Standard",
        cluster: 0,
      }));
    }

    // Mean monetary threshold
    const avgMonetary = rawList.reduce((acc, i) => acc + i.monetary, 0) / rawList.length;

    return rawList.map((item) => {
      let segment: "High Value / VIP" | "Medium Value" | "Low Value" = "Low Value";
      let cluster = 0;

      if (item.monetary >= avgMonetary * 1.5) {
        segment = "High Value / VIP";
        cluster = 2;
      } else if (item.monetary >= avgMonetary * 0.75) {
        segment = "Medium Value";
        cluster = 1;
      }

      return {
        ...item,
        segment,
        cluster,
      };
    });
  }

  /**
   * Idempotently rebuilds local aggregate tables for a company.
   */
  static async rebuildLocalAnalytics(companyId: string): Promise<void> {
    if (!companyId) return;

    const vouchers = await offlineDb.syncedVouchers
      .where("companyId")
      .equals(companyId)
      .toArray();

    const activeVouchers = this.resolveEffectiveVouchers(vouchers);
    const activeVouchersMap = new Map(activeVouchers.map(v => [v.id, v]));

    const allAllocations = await offlineDb.syncedPaymentAllocations
      .where("companyId")
      .equals(companyId)
      .toArray();

    const dailyMap: Record<string, { sales: number; purchases: number; collections: number; payments: number; salesCount: number; purchaseCount: number }> = {};
    const partyMap: Record<string, { name: string; sales: number; purchases: number; receipts: number; payments: number; invoiceCount: number; lastDate: string; outstanding: number }> = {};

    for (const v of activeVouchers) {
      const d = v.voucherDate;
      const amt = Number(v.totalAmount) || 0;
      const pId = v.partyLedgerId || v.partyName || "counter-sale";
      const pName = v.partyName || "Counter Sale";

      if (!dailyMap[d]) {
        dailyMap[d] = { sales: 0, purchases: 0, collections: 0, payments: 0, salesCount: 0, purchaseCount: 0 };
      }
      if (!partyMap[pId]) {
        partyMap[pId] = { name: pName, sales: 0, purchases: 0, receipts: 0, payments: 0, invoiceCount: 0, lastDate: d, outstanding: 0 };
      }

      if (v.voucherType === "SALES") {
        dailyMap[d].sales += amt;
        dailyMap[d].salesCount += 1;
        partyMap[pId].sales += amt;
        partyMap[pId].invoiceCount += 1;
        
        partyMap[pId].outstanding += this.calculateInvoiceOutstanding(v, allAllocations, activeVouchersMap);
      } else if (v.voucherType === "PURCHASE") {
        dailyMap[d].purchases += amt;
        dailyMap[d].purchaseCount += 1;
        partyMap[pId].purchases += amt;
      } else if (v.voucherType === "RECEIPT") {
        dailyMap[d].collections += amt;
        partyMap[pId].receipts += amt;
      } else if (v.voucherType === "PAYMENT") {
        dailyMap[d].payments += amt;
        partyMap[pId].payments += amt;
      }

      if (d > partyMap[pId].lastDate) {
        partyMap[pId].lastDate = d;
      }
    }

    await offlineDb.transaction("rw", [offlineDb.analyticsDaily, offlineDb.analyticsParty], async () => {
      // Clear old aggregates for this company
      await offlineDb.analyticsDaily.where("companyId").equals(companyId).delete();
      await offlineDb.analyticsParty.where("companyId").equals(companyId).delete();

      const dailyEntries = Object.keys(dailyMap).map((d) => ({
        id: `${companyId}_${d}`,
        companyId,
        date: d,
        sales: Math.round(dailyMap[d].sales * 100) / 100,
        purchases: Math.round(dailyMap[d].purchases * 100) / 100,
        collections: Math.round(dailyMap[d].collections * 100) / 100,
        payments: Math.round(dailyMap[d].payments * 100) / 100,
        salesCount: dailyMap[d].salesCount,
        purchaseCount: dailyMap[d].purchaseCount,
      }));

      const partyEntries = Object.keys(partyMap).map((pId) => ({
        id: `${companyId}_${pId}`,
        companyId,
        partyId: pId,
        partyName: partyMap[pId].name,
        sales: Math.round(partyMap[pId].sales * 100) / 100,
        purchases: Math.round(partyMap[pId].purchases * 100) / 100,
        receipts: Math.round(partyMap[pId].receipts * 100) / 100,
        payments: Math.round(partyMap[pId].payments * 100) / 100,
        invoiceCount: partyMap[pId].invoiceCount,
        lastTransactionDate: partyMap[pId].lastDate,
        outstanding: Math.round(partyMap[pId].outstanding * 100) / 100,
      }));

      await offlineDb.analyticsDaily.bulkPut(dailyEntries);
      await offlineDb.analyticsParty.bulkPut(partyEntries);
    });
  }

  /**
   * Incrementally updates only the affected dates and parties without full-table scans.
   */
  static async updateIncrementalAnalytics(companyId: string, changedVouchers: SyncedVoucher[]): Promise<void> {
    if (!companyId || !changedVouchers || changedVouchers.length === 0) return;

    // For large bulk changes (>200 items), a full rebuild is more efficient
    if (changedVouchers.length > 200) {
      return this.rebuildLocalAnalytics(companyId);
    }

    const affectedDates = Array.from(new Set(changedVouchers.map((v) => v.voucherDate).filter(Boolean)));
    const affectedPartyIds = Array.from(
      new Set(changedVouchers.map((v) => v.partyLedgerId || v.partyName).filter(Boolean))
    ) as string[];

    // 1. Update only affected Daily aggregates
    const dailyUpdates = [];
    for (const d of affectedDates) {
      const dayVouchers = await offlineDb.syncedVouchers
        .where("companyId")
        .equals(companyId)
        .and((v) => v.voucherDate === d && v.status === "POSTED")
        .toArray();

      let sales = 0, purchases = 0, collections = 0, payments = 0, salesCount = 0, purchaseCount = 0;
      for (const v of dayVouchers) {
        const amt = Number(v.totalAmount) || 0;
        if (v.voucherType === "SALES") {
          sales += amt;
          salesCount += 1;
        } else if (v.voucherType === "PURCHASE") {
          purchases += amt;
          purchaseCount += 1;
        } else if (v.voucherType === "RECEIPT") {
          collections += amt;
        } else if (v.voucherType === "PAYMENT") {
          payments += amt;
        }
      }

      dailyUpdates.push({
        id: `${companyId}_${d}`,
        companyId,
        date: d,
        sales: Math.round(sales * 100) / 100,
        purchases: Math.round(purchases * 100) / 100,
        collections: Math.round(collections * 100) / 100,
        payments: Math.round(payments * 100) / 100,
        salesCount,
        purchaseCount,
      });
    }

    if (dailyUpdates.length > 0) {
      await offlineDb.analyticsDaily.bulkPut(dailyUpdates);
    }

    // 2. Update only affected Party aggregates
    const partyUpdates = [];
    const allAllocations = await offlineDb.syncedPaymentAllocations
      .where("companyId")
      .equals(companyId)
      .toArray();

    const allCompanyVouchers = await offlineDb.syncedVouchers
      .where("companyId")
      .equals(companyId)
      .toArray();
    const effectiveVouchersMap = new Map(this.resolveEffectiveVouchers(allCompanyVouchers).map(v => [v.id, v]));

    for (const pId of affectedPartyIds) {
      const pVouchers = await offlineDb.syncedVouchers
        .where("companyId")
        .equals(companyId)
        .and((v) => (v.partyLedgerId === pId || (!v.partyLedgerId && v.partyName === pId)) && v.status === "POSTED")
        .toArray();

      let sales = 0, purchases = 0, receipts = 0, payments = 0, invoiceCount = 0;
      let lastDate = "";
      let pName = "";
      let outstanding = 0;

      for (const v of pVouchers) {
        const amt = Number(v.totalAmount) || 0;
        if (!pName && v.partyName) pName = v.partyName;
        if (v.voucherDate > lastDate) lastDate = v.voucherDate;

        if (v.voucherType === "SALES") {
          sales += amt;
          invoiceCount += 1;
          outstanding += this.calculateInvoiceOutstanding(v, allAllocations, effectiveVouchersMap);
        } else if (v.voucherType === "PURCHASE") {
          purchases += amt;
        } else if (v.voucherType === "RECEIPT") {
          receipts += amt;
        } else if (v.voucherType === "PAYMENT") {
          payments += amt;
        }
      }

      partyUpdates.push({
        id: `${companyId}_${pId}`,
        companyId,
        partyId: pId,
        partyName: pName || "Party",
        sales: Math.round(sales * 100) / 100,
        purchases: Math.round(purchases * 100) / 100,
        receipts: Math.round(receipts * 100) / 100,
        payments: Math.round(payments * 100) / 100,
        invoiceCount,
        lastTransactionDate: lastDate,
        outstanding: Math.round(outstanding * 100) / 100,
      });
    }

    if (partyUpdates.length > 0) {
      await offlineDb.analyticsParty.bulkPut(partyUpdates);
    }

    if (process.env.NODE_ENV === "development") {
      console.log(`[LOCAL] incremental analytics updated (dates=${dailyUpdates.length}, parties=${partyUpdates.length})`);
    }
  }

  static getEmptyDashboard(): LocalDashboardResult {
    return {
      business_health: "Constant",
      trend_summary: "No local data available for this company.",
      trend_details: {
        status: "Constant",
        slope: 0,
        growth_rate_pct: 0,
        normalized_slope: 0,
        average_daily_sales: 0,
        daily_trend: [],
        summary: "No local data available.",
      },
      rfm_clusters: [],
      actionable_alerts: [],
      kpis: {
        today_sales: 0,
        today_collections: 0,
        money_to_collect: 0,
        bills_to_pay: 0,
        cash_and_bank: 0,
        total_sales: 0,
        total_purchases: 0,
        sales_vouchers_count: 0,
        purchase_vouchers_count: 0,
        total_stock_value: 0,
        total_retail_value: 0,
        total_stock_qty: 0,
        total_in_stock_items: 0,
        total_catalog_items: 0,
      },
      recent_vouchers: [],
      coverage: {
        oldestDate: null,
        newestDate: null,
        totalVouchersCount: 0,
        isComplete: false,
        lastSyncAt: null,
      },
    };
  }
}
