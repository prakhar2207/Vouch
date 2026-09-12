import { offlineDb, SyncedVoucher, SyncedLedger, SyncedProduct } from "../db/offlineDb";

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

export interface LocalDashboardResult {
  business_health: string;
  trend_summary: string;
  trend_details: TrendDetails;
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
   * Primary entry point for rendering the operational dashboard.
   */
  static async getDashboardAnalytics(companyId: string): Promise<LocalDashboardResult> {
    if (!companyId) {
      return this.getEmptyDashboard();
    }

    // 1. Fetch valid, posted vouchers for active company
    // Omit CANCELLED, REVERSED, DRAFT according to authoritative accounting rules
    const allCompanyVouchers = await offlineDb.syncedVouchers
      .where("companyId")
      .equals(companyId)
      .toArray();

    const activeVouchers = allCompanyVouchers.filter(
      (v) => v.status === "POSTED"
    );

    // 2. Fetch ledgers for active company
    const ledgers = await offlineDb.syncedLedgers
      .where("companyId")
      .equals(companyId)
      .toArray();

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

        // Check overdue (P0-6: Canonical due-date calculation)
        const isOverdue = v.dueDate ? (v.dueDate < todayStr) : (vDate < thirtyDaysAgo);
        if (isOverdue) {
          overdueInvoices.push(v);
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

    // --- B. Receivables, Payables, Liquid Funds ---
    let moneyToCollect = 0;
    let billsToPay = 0;
    let cashAndBank = 0;

    for (const l of ledgers) {
      const bal = Number(l.currentBalance) || 0;
      const lt = (l.ledgerType || "").toUpperCase();

      if (lt === "CUSTOMER") {
        if (bal > 0) moneyToCollect += bal;
      } else if (lt === "SUPPLIER") {
        if (bal > 0) billsToPay += bal;
      } else if (lt === "PARTY") {
        if (bal > 0) moneyToCollect += bal;
        else if (bal < 0) billsToPay += Math.abs(bal);
      } else if (lt === "CASH" || lt === "BANK") {
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
    const trendDetails = this.calculateSalesTrend(salesByDate);

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
   */
  private static calculateSalesTrend(salesByDate: Record<string, number>): TrendDetails {
    const dates = Object.keys(salesByDate).sort();

    if (dates.length === 0) {
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

    // Fill continuous calendar date series between minDate and maxDate (up to 30 days)
    const dailyTrend: Array<{ date: string; sales: number }> = [];
    const minD = new Date(dates[0]);
    const maxD = new Date(dates[dates.length - 1]);
    const diffDays = Math.min(Math.round((maxD.getTime() - minD.getTime()) / (24 * 60 * 60 * 1000)), 60);

    const seriesDates: string[] = [];
    for (let i = 0; i <= diffDays; i++) {
      const cur = new Date(minD.getTime() + i * 24 * 60 * 60 * 1000);
      const dStr = cur.toISOString().slice(0, 10);
      seriesDates.push(dStr);
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
    const avgSales = meanY > 0 ? meanY : 1.0;
    const normalizedSlope = (slope / avgSales) * 100.0;
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

    const activeVouchers = vouchers.filter(
      (v) => v.status === "POSTED"
    );

    const dailyMap: Record<string, { sales: number; purchases: number; collections: number; payments: number; salesCount: number; purchaseCount: number }> = {};
    const partyMap: Record<string, { name: string; sales: number; purchases: number; receipts: number; payments: number; invoiceCount: number; lastDate: string }> = {};

    for (const v of activeVouchers) {
      const d = v.voucherDate;
      const amt = Number(v.totalAmount) || 0;
      const pId = v.partyLedgerId || "counter-sale";
      const pName = v.partyName || "Counter Sale";

      if (!dailyMap[d]) {
        dailyMap[d] = { sales: 0, purchases: 0, collections: 0, payments: 0, salesCount: 0, purchaseCount: 0 };
      }
      if (!partyMap[pId]) {
        partyMap[pId] = { name: pName, sales: 0, purchases: 0, receipts: 0, payments: 0, invoiceCount: 0, lastDate: d };
      }

      if (v.voucherType === "SALES") {
        dailyMap[d].sales += amt;
        dailyMap[d].salesCount += 1;
        partyMap[pId].sales += amt;
        partyMap[pId].invoiceCount += 1;
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
        outstanding: Math.round((partyMap[pId].sales - partyMap[pId].receipts) * 100) / 100,
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
    for (const pId of affectedPartyIds) {
      const pVouchers = await offlineDb.syncedVouchers
        .where("companyId")
        .equals(companyId)
        .and((v) => (v.partyLedgerId === pId || (!v.partyLedgerId && v.partyName === pId)) && v.status === "POSTED")
        .toArray();

      let sales = 0, purchases = 0, receipts = 0, payments = 0, invoiceCount = 0;
      let lastDate = "";
      let pName = "";

      for (const v of pVouchers) {
        const amt = Number(v.totalAmount) || 0;
        if (!pName && v.partyName) pName = v.partyName;
        if (v.voucherDate > lastDate) lastDate = v.voucherDate;

        if (v.voucherType === "SALES") {
          sales += amt;
          invoiceCount += 1;
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
        outstanding: Math.round((sales - receipts) * 100) / 100,
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
