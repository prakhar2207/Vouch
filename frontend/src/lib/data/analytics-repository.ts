import { LocalAnalyticsEngine, LocalDashboardResult } from "../analytics/analytics-engine";
import { SyncedVoucher } from "../db/offlineDb";

export class AnalyticsRepository {
  /**
   * Reads dashboard operational KPIs and charts directly from IndexedDB.
   * Completely local-first with 0 network calls.
   */
  async getDashboardAnalytics(companyId: string): Promise<LocalDashboardResult> {
    if (!companyId) {
      return LocalAnalyticsEngine.getEmptyDashboard();
    }
    return LocalAnalyticsEngine.getDashboardAnalytics(companyId);
  }

  /**
   * Incrementally updates aggregates when vouchers are synchronized or mutated.
   */
  async updateIncremental(companyId: string, changedVouchers: SyncedVoucher[]): Promise<void> {
    return LocalAnalyticsEngine.updateIncrementalAnalytics(companyId, changedVouchers);
  }

  /**
   * Rebuilds all local aggregates for initial bootstrap.
   */
  async rebuildAll(companyId: string): Promise<void> {
    return LocalAnalyticsEngine.rebuildLocalAnalytics(companyId);
  }
}

export const analyticsRepository = new AnalyticsRepository();
