import { offlineDb, SyncedProduct } from "../db/offlineDb";
import axios from "axios";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken } from "@/utils/auth";

export interface ProductQueryOptions {
  search?: string;
  lowStockOnly?: boolean;
}

export class ProductsRepository {
  /**
   * Reads products locally from IndexedDB.
   * Falls back to server only when local catalog is empty.
   */
  async getProducts(companyId: string, options: ProductQueryOptions = {}): Promise<{ data: SyncedProduct[]; isLocal: boolean }> {
    if (!companyId) return { data: [], isLocal: true };

    let products = await offlineDb.syncedProducts
      .where("companyId")
      .equals(companyId)
      .toArray();

    // Fallback if local product catalog is unpopulated
    if (products.length === 0) {
      try {
        const token = getAccessToken();
        if (token) {
          const headers = { Authorization: `Bearer ${token}`, "X-Company-ID": companyId };
          const res = await axios.get(`${API_BASE_URL}/api/v1/inventory/products/${companyId}/`, { headers, timeout: 5000 });
          const raw = res.data?.data || (Array.isArray(res.data) ? res.data : []);
          if (raw.length > 0) {
            const toPut: SyncedProduct[] = raw.map((p: any) => ({
              id: String(p.id),
              companyId,
              name: p.name,
              sku: p.sku || "",
              hsnCode: p.hsn_code || "",
              unit: p.unit || "PCS",
              purchasePrice: Number(p.purchase_price) || 0,
              salesPrice: Number(p.selling_price || p.sales_price) || 0,
              gstRate: Number(p.gst_rate) || 0,
              currentStock: Number(p.stock_quantity || p.current_stock) || 0,
              serverUpdatedAt: Date.now(),
            }));
            await offlineDb.syncedProducts.bulkPut(toPut);
            products = toPut;
          }
        }
      } catch (err) {
        console.warn("[ProductsRepo] Fallback fetch failed:", err);
      }
    }

    let filtered = products;
    if (options.lowStockOnly) {
      filtered = filtered.filter((p) => p.currentStock <= 5);
    }
    if (options.search) {
      const q = options.search.trim().toLowerCase();
      filtered = filtered.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          (p.sku && p.sku.toLowerCase().includes(q)) ||
          (p.hsnCode && p.hsnCode.toLowerCase().includes(q))
      );
    }

    if (process.env.NODE_ENV === "development") {
      console.log(`[LOCAL] products query (count=${filtered.length})`);
    }

    return { data: filtered, isLocal: true };
  }

  async getProductById(id: string): Promise<SyncedProduct | undefined> {
    return offlineDb.syncedProducts.get(id);
  }

  async saveProducts(companyId: string, products: SyncedProduct[]): Promise<void> {
    if (!products || products.length === 0) return;
    await offlineDb.syncedProducts.bulkPut(products);
  }
}

export const productsRepository = new ProductsRepository();
