"use client";
import React, { useEffect, useState, useMemo } from "react";
import axios from "axios";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import DashboardLayout from "@/components/DashboardLayout";
import { useCompany } from "@/context/CompanyContext";
import { useFinancialYear } from "@/context/FinancialYearContext";
import { LocalAnalyticsEngine } from "@/lib/analytics/analytics-engine";
import { useToast } from "@/context/ToastContext";
import PurchaseOrderDraftModal, { POOrderItem } from "@/components/modals/PurchaseOrderDraftModal";
import ItemHistoryModal from "@/components/modals/ItemHistoryModal";
import MassMinStockModal from "@/components/modals/MassMinStockModal";
import {
  TrendingUp,
  Sparkles,
  Boxes,
  Users,
  Calendar,
  Layers,
  Tag,
  ShieldCheck,
  RefreshCw,
  Clock,
  Landmark,
  FileText,
  AlertCircle,
  ShoppingCart,
  CheckSquare,
  Square,
  PackageCheck,
  AlertTriangle,
  Search,
  Filter,
  Plus,
  Minus,
  Check,
  ExternalLink,
  ChevronRight,
  TrendingDown,
  Sliders,
  Download,
  Archive,
  Activity,
} from "lucide-react";

function formatCurrencyShort(val: number): string {
  if (val >= 10000000) return `₹${(val / 10000000).toFixed(1)}Cr`;
  if (val >= 100000) return `₹${(val / 100000).toFixed(1)}L`;
  if (val >= 1000) return `₹${(val / 1000).toFixed(0)}k`;
  return `₹${Math.round(val)}`;
}

function formatChartDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  } catch {
    return dateStr;
  }
}

function AnalyticsHubContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialTab = searchParams.get("tab") || "sales";

  const [activeTab, setActiveTab] = useState<"sales" | "monthly" | "rfm" | "inventory" | "cashflow">(
    (initialTab as any) || "sales"
  );
  const [forecastDays, setForecastDays] = useState<number>(30);
  const [forecast, setForecast] = useState<any>(null);
  const [rfmData, setRfmData] = useState<any[]>([]);
  const [insights, setInsights] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [retailDiscount, setRetailDiscount] = useState<number>(0);

  const { toast } = useToast();

  // Inventory Analytics & Smart Reorder Hub State
  const [effectiveCompanyId, setEffectiveCompanyId] = useState<string>("");
  const [inventoryAnalytics, setInventoryAnalytics] = useState<any>(null);
  const initialCategory = searchParams.get("category_id") || "ALL";
  const [inventoryCategoryFilter, setInventoryCategoryFilter] = useState<string>(initialCategory);
  const [loadingInventoryAnalytics, setLoadingInventoryAnalytics] = useState<boolean>(false);
  const [inventorySearch, setInventorySearch] = useState<string>("");
  const [selectedReorderIds, setSelectedReorderIds] = useState<Set<string>>(new Set());
  const [orderQuantities, setOrderQuantities] = useState<Record<string, number>>({});
  const [bulkQuantityInput, setBulkQuantityInput] = useState<number>(10);
  const [selectedHistoryItem, setSelectedHistoryItem] = useState<any>(null);
  const [isPoModalOpen, setIsPoModalOpen] = useState<boolean>(false);

  // Brand & Sub-View Filter States (Mention Brand & Deadstock / Sitting on Benches)
  const [inventoryBrandFilter, setInventoryBrandFilter] = useState<string>("ALL");
  const [inventorySubView, setInventorySubView] = useState<"reorder" | "deadstock">("reorder");
  const [deadstockAgingFilter, setDeadstockAgingFilter] = useState<"all" | "dormant" | "90" | "60" | "30">("all");

  // Mass-Wise Minimum Required Stock State
  const [massMinStockInput, setMassMinStockInput] = useState<number>(10);
  const [isMassMinStockModalOpen, setIsMassMinStockModalOpen] = useState<boolean>(false);
  const [massMinStockScope, setMassMinStockScope] = useState<"selected" | "category" | "all">("selected");
  const [updatingMinStock, setUpdatingMinStock] = useState<boolean>(false);

  const fetchInventoryAnalytics = async (cid?: string, catId?: string) => {
    const targetCid = cid || effectiveCompanyId || activeCompanyId;
    if (!targetCid) return;
    setLoadingInventoryAnalytics(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const categoryParam = catId !== undefined ? catId : inventoryCategoryFilter;
      const catQuery = categoryParam && categoryParam !== "ALL" ? `&category_id=${categoryParam}` : "";
      const url = `${API_BASE_URL}/api/v1/inventory/analytics/${targetCid}/?limit=15&reorder_limit=150${catQuery}`;
      const res = await axios.get(url, { headers });
      if (res.data?.success) {
        setInventoryAnalytics(res.data.data);

        // Pre-populate suggested order quantities for items if not already customized
        if (res.data.data?.reorder_items) {
          setOrderQuantities((prev) => {
            const next = { ...prev };
            res.data.data.reorder_items.forEach((it: any) => {
              if (next[it.product_id] === undefined) {
                next[it.product_id] = it.suggested_qty || 5;
              }
            });
            return next;
          });
        }
      }
    } catch (err) {
      console.error("Failed to load inventory analytics:", err);
    } finally {
      setLoadingInventoryAnalytics(false);
    }
  };

  const { activeCompany, companyId: activeCompanyId } = useCompany();
  const { activeFY } = useFinancialYear();

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }

    let isMounted = true;
    async function loadAnalytics() {
      setLoading(true);
      try {
        let cid = activeCompanyId;
        if (!cid && typeof window !== "undefined") {
          cid = localStorage.getItem("vouch_active_company_id");
        }
        if (!cid) {
          const token = getAccessToken();
          const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          const companies = Array.isArray(compRes.data) ? compRes.data : compRes.data.data || [];
          if (companies.length > 0) {
            cid = companies[0].id;
          }
        }

        if (!cid) {
          if (isMounted) setLoading(false);
          return;
        }

        const validCid = cid;
        setEffectiveCompanyId(validCid);
        fetchInventoryAnalytics(validCid, inventoryCategoryFilter);
        const fyOptions = {
          startDate: activeFY?.start_date,
          endDate: activeFY?.end_date,
          financialYearId: activeFY?.id,
        };

        // 1. Instant local read from IndexedDB (<15ms)
        const local = await LocalAnalyticsEngine.getDashboardAnalytics(validCid, fyOptions);
        if (isMounted && local) {
          setInsights(local);
          if (local.forecast) {
            setForecast(local.forecast);
          }
          if (local.rfm_clusters && local.rfm_clusters.length > 0) {
            setRfmData(local.rfm_clusters);
          }
          setLoading(false);
        }

        // 2. Refresh from remote API if online
        if (typeof navigator !== "undefined" && navigator.onLine) {
          const token = getAccessToken();
          const headers = { Authorization: `Bearer ${token}`, "X-Company-ID": validCid };

          const [forecastRes, rfmRes, insightsRes] = await Promise.allSettled([
            axios.get(`${API_BASE_URL}/api/v1/analytics/forecast/${validCid}/?days=${forecastDays}&company_id=${validCid}`, { headers }),
            axios.get(`${API_BASE_URL}/api/v1/analytics/rfm/${validCid}/`, { headers }),
            axios.get(`${API_BASE_URL}/api/v1/analytics/insights/${validCid}/`, { headers }),
          ]);

          if (isMounted) {
            if (forecastRes.status === "fulfilled" && forecastRes.value.data?.success) {
              setForecast(forecastRes.value.data.data);
            }
            if (rfmRes.status === "fulfilled" && rfmRes.value.data?.success) {
              setRfmData(rfmRes.value.data.data || []);
            }
            if (insightsRes.status === "fulfilled" && insightsRes.value.data?.success) {
              const remote = insightsRes.value.data.data;
              setInsights((prev: any) => ({
                ...prev,
                ...remote,
                kpis: {
                  ...(prev?.kpis || {}),
                  ...(remote?.kpis || {}),
                }
              }));
            }
          }
        }
      } catch (err) {
        console.error("Failed loading analytics hub data:", err);
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    loadAnalytics();
    return () => {
      isMounted = false;
    };
  }, [activeCompanyId, activeFY?.id, forecastDays, router]);

  // Sync tab and category with URL search parameters if changed
  useEffect(() => {
    const tab = searchParams.get("tab");
    if (tab && ["sales", "monthly", "rfm", "inventory", "cashflow"].includes(tab)) {
      setActiveTab(tab as any);
    }
    const cat = searchParams.get("category_id");
    if (cat && cat !== inventoryCategoryFilter) {
      setInventoryCategoryFilter(cat);
      if (effectiveCompanyId) {
        fetchInventoryAnalytics(effectiveCompanyId, cat);
      }
    }
  }, [searchParams, effectiveCompanyId, inventoryCategoryFilter]);

  // Category & Reorder Hub Filters
  const handleCategoryFilterChange = (newCatId: string) => {
    setInventoryCategoryFilter(newCatId);
    if (effectiveCompanyId) {
      fetchInventoryAnalytics(effectiveCompanyId, newCatId);
    }
  };

  // Unique brand options across both reorder items and deadstock items
  const availableBrands = useMemo(() => {
    const brandsSet = new Set<string>();
    inventoryAnalytics?.reorder_items?.forEach((it: any) => {
      if (it.brand && it.brand.trim()) brandsSet.add(it.brand.trim());
    });
    inventoryAnalytics?.deadstock_items?.forEach((it: any) => {
      if (it.brand && it.brand.trim()) brandsSet.add(it.brand.trim());
    });
    return Array.from(brandsSet).sort();
  }, [inventoryAnalytics?.reorder_items, inventoryAnalytics?.deadstock_items]);

  const currentCategoryName = useMemo(() => {
    if (!inventoryCategoryFilter || inventoryCategoryFilter === "ALL") return "All Categories";
    const cat = inventoryAnalytics?.categories?.find((c: any) => c.id === inventoryCategoryFilter);
    return cat ? cat.name : "Category";
  }, [inventoryAnalytics?.categories, inventoryCategoryFilter]);

  const filteredReorderItems = useMemo(() => {
    if (!inventoryAnalytics?.reorder_items) return [];
    let list: any[] = inventoryAnalytics.reorder_items;
    if (inventoryBrandFilter && inventoryBrandFilter !== "ALL") {
      list = list.filter(
        (it: any) => (it.brand || "").trim().toLowerCase() === inventoryBrandFilter.trim().toLowerCase()
      );
    }
    if (inventorySearch.trim()) {
      const q = inventorySearch.toLowerCase();
      list = list.filter(
        (it: any) =>
          it.name?.toLowerCase().includes(q) ||
          it.brand?.toLowerCase().includes(q) ||
          it.sku?.toLowerCase().includes(q) ||
          it.category_name?.toLowerCase().includes(q) ||
          it.last_supplier?.toLowerCase().includes(q)
      );
    }
    return list;
  }, [inventoryAnalytics?.reorder_items, inventoryBrandFilter, inventorySearch]);

  // Filtered Sitting on Benches / Slow-Moving (Deadstock) Items
  const filteredDeadstockItems = useMemo(() => {
    if (!inventoryAnalytics?.deadstock_items) return [];
    let list: any[] = inventoryAnalytics.deadstock_items;
    if (inventoryBrandFilter && inventoryBrandFilter !== "ALL") {
      list = list.filter(
        (it: any) => (it.brand || "").trim().toLowerCase() === inventoryBrandFilter.trim().toLowerCase()
      );
    }
    if (deadstockAgingFilter !== "all") {
      if (deadstockAgingFilter === "dormant") {
        list = list.filter((it: any) => it.status === "DORMANT");
      } else if (deadstockAgingFilter === "90") {
        list = list.filter((it: any) => it.status === "CRITICAL_DEADSTOCK" || it.days_idle >= 90);
      } else if (deadstockAgingFilter === "60") {
        list = list.filter((it: any) => it.days_idle >= 60);
      } else if (deadstockAgingFilter === "30") {
        list = list.filter((it: any) => it.days_idle >= 30);
      }
    }
    if (inventorySearch.trim()) {
      const q = inventorySearch.toLowerCase();
      list = list.filter(
        (it: any) =>
          it.name?.toLowerCase().includes(q) ||
          it.brand?.toLowerCase().includes(q) ||
          it.sku?.toLowerCase().includes(q) ||
          it.category_name?.toLowerCase().includes(q)
      );
    }
    return list;
  }, [inventoryAnalytics?.deadstock_items, inventoryBrandFilter, deadstockAgingFilter, inventorySearch]);

  // Mass Min Stock Update Handler
  const handleApplyMassMinStock = async () => {
    const targetCid = effectiveCompanyId || activeCompanyId;
    if (!targetCid) {
      toast.error("Company not identified");
      return;
    }
    const val = Number(massMinStockInput);
    if (isNaN(val) || val < 0) {
      toast.error("Please enter a valid minimum required quantity (0 or greater)");
      return;
    }

    if (massMinStockScope === "selected" && selectedReorderIds.size === 0) {
      toast.error("No items selected. Select items from the table or choose category/catalog scope.");
      return;
    }

    setUpdatingMinStock(true);
    try {
      const token = getAccessToken();
      const payload: any = {
        min_stock_level: val,
      };

      if (massMinStockScope === "selected") {
        payload.product_ids = Array.from(selectedReorderIds);
      } else if (massMinStockScope === "category") {
        payload.category_id = inventoryCategoryFilter !== "ALL" ? inventoryCategoryFilter : null;
        if (!payload.category_id) {
          payload.apply_all = true;
        }
      } else {
        payload.apply_all = true;
      }

      const res = await axios.post(
        `${API_BASE_URL}/api/v1/inventory/bulk-min-stock/${targetCid}/`,
        payload,
        { headers: { Authorization: `Bearer ${token}` } }
      );

      if (res.data?.success) {
        toast.success(res.data.message || `Updated minimum stock to ${val} successfully`);
        setIsMassMinStockModalOpen(false);
        fetchInventoryAnalytics(targetCid, inventoryCategoryFilter);
      } else {
        toast.error(res.data?.error || "Failed to update minimum stock");
      }
    } catch (err: any) {
      console.error("Bulk min stock update error:", err);
      toast.error(err.response?.data?.error || "Error applying minimum stock mass-wise");
    } finally {
      setUpdatingMinStock(false);
    }
  };

  // Export Deadstock Report CSV
  const handleExportDeadstockCsv = () => {
    const list = filteredDeadstockItems;
    if (list.length === 0) {
      toast.error("No deadstock items to export");
      return;
    }
    const headers = [
      "S.No",
      "Item Name",
      "Brand",
      "SKU",
      "Category",
      "Units On Bench",
      "Unit Cost (INR)",
      "Locked Capital (INR)",
      "MRP (INR)",
      "Days Idle",
      "Last Activity",
      "Status"
    ];
    const rows = list.map((it: any, idx: number) => [
      idx + 1,
      `"${(it.name || "").replace(/"/g, '""')}"`,
      `"${(it.brand || "").replace(/"/g, '""')}"`,
      `"${(it.sku || "").replace(/"/g, '""')}"`,
      `"${(it.category_name || "").replace(/"/g, '""')}"`,
      it.current_stock,
      (it.purchase_price || 0).toFixed(2),
      (it.locked_capital || 0).toFixed(2),
      (it.selling_price || 0).toFixed(2),
      it.days_idle,
      `"${it.last_sale_date ? `Last Sold: ${it.last_sale_date}` : (it.last_purchase_date ? `Purchased: ${it.last_purchase_date}` : 'None')}"`,
      `"${it.status_label || it.status}"`
    ]);
    const csvContent = "data:text/csv;charset=utf-8," +
      [`# SLOW-MOVING & DEADSTOCK INVENTORY REPORT (SITTING ON BENCHES)`, `# Company: ${activeCompany?.name || 'Company'}`, `# Date: ${new Date().toISOString().split('T')[0]}`].join("\n") +
      "\n\n" + [headers.join(","), ...rows.map((r: any) => r.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `Deadstock_Sitting_On_Benches_${new Date().toISOString().split('T')[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success("Deadstock inventory report downloaded successfully");
  };

  const handleToggleSelect = (productId: string) => {
    setSelectedReorderIds((prev) => {
      const next = new Set(prev);
      if (next.has(productId)) {
        next.delete(productId);
      } else {
        next.add(productId);
      }
      return next;
    });
  };

  const isAllSelected = useMemo(() => {
    if (filteredReorderItems.length === 0) return false;
    return filteredReorderItems.every((it: any) => selectedReorderIds.has(it.product_id));
  }, [filteredReorderItems, selectedReorderIds]);

  const handleSelectAllToggle = () => {
    if (isAllSelected) {
      setSelectedReorderIds((prev) => {
        const next = new Set(prev);
        filteredReorderItems.forEach((it: any) => next.delete(it.product_id));
        return next;
      });
    } else {
      setSelectedReorderIds((prev) => {
        const next = new Set(prev);
        filteredReorderItems.forEach((it: any) => next.add(it.product_id));
        return next;
      });
    }
  };

  const handleApplyBulkQuantity = () => {
    if (selectedReorderIds.size === 0) {
      toast.error("Please select items first to apply bulk quantity");
      return;
    }
    const qty = Math.max(1, bulkQuantityInput || 1);
    setOrderQuantities((prev) => {
      const next = { ...prev };
      selectedReorderIds.forEach((pid) => {
        next[pid] = qty;
      });
      return next;
    });
    toast.success(`Set order quantity to ${qty} for ${selectedReorderIds.size} selected item(s)`);
  };

  const handleItemQuantityChange = (productId: string, newQty: number) => {
    const qty = Math.max(1, newQty || 1);
    setOrderQuantities((prev) => ({
      ...prev,
      [productId]: qty,
    }));
  };

  const handleRemoveFromDraft = (productId: string) => {
    setSelectedReorderIds((prev) => {
      const next = new Set(prev);
      next.delete(productId);
      return next;
    });
  };

  const selectedItemsData = useMemo(() => {
    const items = (inventoryAnalytics?.reorder_items || []).filter((it: any) =>
      selectedReorderIds.has(it.product_id)
    );
    const count = items.length;
    const units = items.reduce(
      (acc: number, it: any) => acc + (orderQuantities[it.product_id] ?? it.suggested_qty ?? 5),
      0
    );
    const cost = items.reduce(
      (acc: number, it: any) =>
        acc + (orderQuantities[it.product_id] ?? it.suggested_qty ?? 5) * (it.purchase_price || 0),
      0
    );
    return { count, units, cost };
  }, [inventoryAnalytics?.reorder_items, selectedReorderIds, orderQuantities]);

  const poDraftItems: POOrderItem[] = useMemo(() => {
    const list = inventoryAnalytics?.reorder_items || [];
    return list
      .filter((it: any) => selectedReorderIds.has(it.product_id))
      .map((it: any) => ({
        product_id: it.product_id,
        name: it.name,
        brand: it.brand || "",
        sku: it.sku || "",
        unit: it.unit || "PCS",
        category_name: it.category_name || "General",
        current_stock: it.current_stock || 0,
        order_quantity: orderQuantities[it.product_id] ?? it.suggested_qty ?? 5,
        purchase_price: it.purchase_price || 0,
        last_supplier: it.last_supplier,
        urgency: it.urgency,
        urgency_label: it.urgency_label,
      }));
  }, [inventoryAnalytics?.reorder_items, selectedReorderIds, orderQuantities]);

  const handleOpenPoModal = () => {
    if (selectedReorderIds.size === 0) {
      toast.error("Please select at least one item to draft a purchase order");
      return;
    }
    setIsPoModalOpen(true);
  };

  // Inventory discount calculation
  const stockValuation = useMemo(() => {
    const k = insights?.kpis || insights || {};
    const stockCost = Number(k.total_stock_value ?? k.stock_valuation ?? 0);
    const retailCost = Number(k.total_retail_value ?? k.retail_valuation ?? (stockCost > 0 ? stockCost * 1.3 : 0));
    const effectiveRetail = retailDiscount > 0 ? retailCost * (1 - retailDiscount / 100) : retailCost;
    const margin = Math.max(0, effectiveRetail - stockCost);
    const markupPct = stockCost > 0 ? ((margin / stockCost) * 100).toFixed(1) : "0";
    const costMultiple = stockCost > 0 ? (effectiveRetail / stockCost).toFixed(2) : "1.00";
    return { stockCost, retailCost, effectiveRetail, margin, markupPct, costMultiple };
  }, [insights, retailDiscount]);

  const kpis = insights?.kpis || insights || {};

  return (
    <DashboardLayout>
      <div className="space-y-6 pb-16 max-w-7xl mx-auto px-1 sm:px-2">
        {/* Header Banner */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border/40 pb-5">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl sm:text-2xl font-extrabold text-foreground tracking-tight">
                Analytics & Business Intelligence
              </h1>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
                AI Engine
              </span>
            </div>
            <p className="text-xs sm:text-sm text-muted-foreground mt-1">
              Multi-factor sales forecasting, monthly trajectory benchmarks, customer RFM tiers & inventory valuation.
            </p>
          </div>

          {/* Quick Info & Horizon Select */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-muted-foreground font-medium">Horizon:</span>
            <div className="flex items-center bg-muted/60 p-0.5 rounded-lg border border-border/40 text-xs">
              {[14, 30, 60, 90].map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setForecastDays(d)}
                  className={`px-2.5 py-1 rounded font-medium transition-colors cursor-pointer ${
                    forecastDays === d ? "bg-card text-foreground font-bold shadow-2xs" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {d}d
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Executive Tab Navigation */}
        <div className="flex items-center gap-1.5 border-b border-border/40 pb-2 overflow-x-auto no-scrollbar">
          <button
            type="button"
            onClick={() => setActiveTab("sales")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all flex items-center gap-1.5 cursor-pointer ${
              activeTab === "sales"
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5" />
            <span>Sales Forecast</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("monthly")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all flex items-center gap-1.5 cursor-pointer ${
              activeTab === "monthly"
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
            }`}
          >
            <Calendar className="w-3.5 h-3.5" />
            <span>Monthly Benchmark (MoM/YoY)</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("rfm")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all flex items-center gap-1.5 cursor-pointer ${
              activeTab === "rfm"
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
            }`}
          >
            <Users className="w-3.5 h-3.5" />
            <span>Customer RFM Tiers</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("inventory")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all flex items-center gap-1.5 cursor-pointer ${
              activeTab === "inventory"
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
            }`}
          >
            <Boxes className="w-3.5 h-3.5" />
            <span>Inventory & Reorder Hub</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("cashflow")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all flex items-center gap-1.5 cursor-pointer ${
              activeTab === "cashflow"
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
            }`}
          >
            <Landmark className="w-3.5 h-3.5" />
            <span>Cash Flow & Working Capital</span>
          </button>
        </div>

        {/* Tab 1: Sales & Predictive Forecast */}
        {activeTab === "sales" && (
          <div className="space-y-5 animate-in fade-in duration-200">
            {/* KPI Summary Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Projected {forecastDays}-Day Revenue
                </span>
                <div className="text-xl sm:text-2xl font-bold font-mono text-foreground">
                  ₹{(forecast?.projected_total || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                {forecast?.p10_total && forecast?.p90_total && (
                  <div className="text-[11px] text-muted-foreground font-mono">
                    Range: ₹{formatCurrencyShort(forecast.p10_total)} - ₹{formatCurrencyShort(forecast.p90_total)} (P10-P90)
                  </div>
                )}
              </div>

              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Projected Daily Average
                </span>
                <div className="text-xl sm:text-2xl font-bold font-mono text-foreground">
                  ₹{(forecast?.projected_daily_average || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-[11px] text-muted-foreground">
                  Historical Mean: ₹{(forecast?.historical_daily_average || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}/day
                </div>
              </div>

              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Growth Trajectory
                </span>
                <div className="flex items-center gap-2">
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-xs font-mono font-bold border ${
                      forecast?.trend_status === "Booming"
                        ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20"
                        : forecast?.trend_status === "Declining"
                        ? "bg-amber-500/10 text-amber-500 border-amber-500/20"
                        : "bg-blue-500/10 text-blue-500 border-blue-500/20"
                    }`}
                  >
                    {forecast?.trend_status || "Stable"}
                  </span>
                  <span className="text-xs text-muted-foreground font-medium">Confidence: {forecast?.confidence || "HIGH"}</span>
                </div>
                <div className="text-[11px] text-muted-foreground">
                  Based on {forecast?.sample_size_days || 0} active selling days
                </div>
              </div>

              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Realization Pipeline
                </span>
                <div className="text-xl sm:text-2xl font-bold font-mono text-purple-600 dark:text-purple-400">
                  ₹{(forecast?.factors_analyzed?.open_proforma_pipeline || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-[11px] text-muted-foreground">
                  Open proforma quotes converting in next 14 days
                </div>
              </div>
            </div>

            {/* Main Area Chart */}
            <div className="bg-card border border-border/50 rounded-xl p-5 shadow-2xs space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                    <span>Multi-Factor Sales Trajectory & Confidence Band</span>
                    <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Synthesizes day-of-week dispatch patterns, month-end GST rush, customer replenishment cadence, and physical stock guards.
                  </p>
                </div>
              </div>

              <div className="h-64 sm:h-72 w-full pt-2">
                {forecast?.daily_forecast && forecast.daily_forecast.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={forecast.daily_forecast} margin={{ top: 10, right: 15, left: -10, bottom: 0 }}>
                      <defs>
                        <linearGradient id="forecastHubGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.35} />
                          <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-border/40" vertical={false} />
                      <XAxis
                        dataKey="date"
                        stroke="currentColor"
                        className="text-muted-foreground"
                        fontSize={11}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={formatChartDate}
                      />
                      <YAxis
                        stroke="currentColor"
                        className="text-muted-foreground"
                        fontSize={11}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={formatCurrencyShort}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "var(--card)",
                          borderColor: "var(--border)",
                          borderRadius: "12px",
                          boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.3)",
                          fontSize: "12px",
                        }}
                        labelFormatter={(label: any) => {
                          try {
                            const d = new Date(label);
                            if (!isNaN(d.getTime())) {
                              return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
                            }
                          } catch {}
                          return label;
                        }}
                        formatter={(val: any) => [`₹${Number(val).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`, "Projected Sales"]}
                      />
                      <Area
                        type="monotone"
                        dataKey="projected_sales"
                        stroke="#8b5cf6"
                        strokeWidth={2.5}
                        fillOpacity={1}
                        fill="url(#forecastHubGrad)"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
                    No sales history available to project forecast.
                  </div>
                )}
              </div>

              {/* Factors Analyzed Breakdown */}
              <div className="pt-2 border-t border-border/40">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-2">
                  Active B2B Factors Evaluated:
                </span>
                <div className="flex flex-wrap gap-2">
                  <span
                    className={`text-xs px-2.5 py-1 rounded-full border font-medium ${
                      forecast?.factors_analyzed?.yoy_seasonality_applied
                        ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20"
                        : "bg-muted text-muted-foreground border-border/40"
                    }`}
                  >
                    {forecast?.factors_analyzed?.yoy_seasonality_applied
                      ? "✓ YoY Seasonality Active (From Past Records)"
                      : "YoY Seasonality Excluded (< 1 yr data)"}
                  </span>
                  <span className="text-xs px-2.5 py-1 rounded-full border font-medium bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20">
                    Day-of-Week Dispatch Pattern (Mon-Fri Peak)
                  </span>
                  <span className="text-xs px-2.5 py-1 rounded-full border font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20">
                    Month-End GST Surge ({forecast?.factors_analyzed?.month_end_surge_multiplier || 1.2}x)
                  </span>
                  {(forecast?.factors_analyzed?.repeat_buyers_modeled || 0) > 0 && (
                    <span className="text-xs px-2.5 py-1 rounded-full border font-medium bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/20">
                      {forecast.factors_analyzed.repeat_buyers_modeled} Repeat Customer Cycles Scheduled
                    </span>
                  )}
                  {forecast?.factors_analyzed?.stock_constraint_applied && (
                    <span className="text-xs px-2.5 py-1 rounded-full border font-medium bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20">
                      Physical Stock Fulfillment Constraint Active
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 2: Monthly Performance & Forecast Benchmark */}
        {activeTab === "monthly" && (
          <div className="space-y-5 animate-in fade-in duration-200">
            {/* Monthly Benchmark KPI Cards */}
            {forecast?.monthly_comparison && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Present Month Card */}
                <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-2">
                  <div className="flex items-center justify-between text-xs text-muted-foreground font-medium">
                    <span>{forecast.monthly_comparison.current_month.month_name} (Current)</span>
                    <span className="font-mono text-purple-600 dark:text-purple-400 font-bold">
                      {forecast.monthly_comparison.current_month.completion_pct}% Achieved
                    </span>
                  </div>
                  <div className="text-2xl font-bold font-mono text-foreground">
                    ₹{forecast.monthly_comparison.current_month.projected_month_total.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </div>
                  <div className="text-xs text-muted-foreground flex items-center justify-between">
                    <span>MTD Achieved: <strong className="text-foreground">₹{formatCurrencyShort(forecast.monthly_comparison.current_month.mtd_actual_sales)}</strong></span>
                    <span>+ Forecast: <strong className="text-purple-500">₹{formatCurrencyShort(forecast.monthly_comparison.current_month.remaining_projected_sales)}</strong></span>
                  </div>
                  {/* Progress Bar */}
                  <div className="w-full bg-muted h-2 rounded-full overflow-hidden flex">
                    <div
                      className="bg-blue-500 h-full transition-all duration-300"
                      style={{ width: `${Math.min(100, forecast.monthly_comparison.current_month.completion_pct)}%` }}
                    />
                    <div
                      className="bg-purple-500/60 h-full transition-all duration-300"
                      style={{ width: `${Math.max(0, 100 - forecast.monthly_comparison.current_month.completion_pct)}%` }}
                    />
                  </div>
                  <div className="text-[11px] text-muted-foreground pt-1">
                    {forecast.monthly_comparison.current_month.days_remaining} calendar days remaining in current month.
                  </div>
                </div>

                {/* vs Last Month Card */}
                <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-2">
                  <div className="flex items-center justify-between text-xs text-muted-foreground font-medium">
                    <span>vs Last Month ({forecast.monthly_comparison.previous_month.short_name || "M-1"})</span>
                    <span
                      className={`text-xs font-mono px-2 py-0.5 rounded-full font-bold ${
                        forecast.monthly_comparison.mom_comparison.pace_status === "BEATING_LAST_MONTH"
                          ? "bg-emerald-500/10 text-emerald-500 border border-emerald-500/20"
                          : forecast.monthly_comparison.mom_comparison.pace_status === "PACING_BEHIND"
                          ? "bg-amber-500/10 text-amber-500 border border-amber-500/20"
                          : "bg-muted text-muted-foreground border border-border/40"
                      }`}
                    >
                      {forecast.monthly_comparison.mom_comparison.percentage_change >= 0 ? "+" : ""}
                      {forecast.monthly_comparison.mom_comparison.percentage_change}%
                    </span>
                  </div>
                  <div className="text-2xl font-bold font-mono text-foreground">
                    Last: ₹{(forecast.monthly_comparison.previous_month.total_sales || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {forecast.monthly_comparison.mom_comparison.summary}
                  </div>
                  {forecast.monthly_comparison.mom_comparison.required_daily_to_match_last_month > 0 && (
                    <div className="text-xs text-purple-600 dark:text-purple-400 font-medium">
                      Target Run-Rate: ₹{formatCurrencyShort(forecast.monthly_comparison.mom_comparison.required_daily_to_match_last_month)}/day needed to surpass
                    </div>
                  )}
                </div>

                {/* Annual YoY Benchmark */}
                <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-2">
                  <div className="text-xs text-muted-foreground font-medium">
                    Annual Year-over-Year (YoY) Benchmark
                  </div>
                  {forecast.monthly_comparison.yoy_comparison?.available ? (
                    <>
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold text-foreground">
                          {forecast.monthly_comparison.yoy_comparison.prior_year_month_name}
                        </span>
                        <span
                          className={`text-xs font-mono px-2 py-0.5 rounded-full font-bold ${
                            forecast.monthly_comparison.yoy_comparison.percentage_change >= 0
                              ? "bg-emerald-500/10 text-emerald-500"
                              : "bg-rose-500/10 text-rose-500"
                          }`}
                        >
                          {forecast.monthly_comparison.yoy_comparison.percentage_change >= 0 ? "+" : ""}
                          {forecast.monthly_comparison.yoy_comparison.percentage_change}%
                        </span>
                      </div>
                      <div className="text-xl font-bold font-mono text-foreground">
                        Prior: ₹{(forecast.monthly_comparison.yoy_comparison.prior_year_sales || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </div>
                      <div className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                        {forecast.monthly_comparison.yoy_comparison.summary}
                      </div>
                    </>
                  ) : (
                    <div className="space-y-1.5 pt-2">
                      <span className="inline-block px-2.5 py-0.5 bg-muted rounded border border-border/40 text-xs text-muted-foreground font-medium">
                        YoY Excluded (&lt; 1 yr history)
                      </span>
                      <p className="text-xs text-muted-foreground">
                        Following strict business modeling rules, annual seasonal multipliers are only applied when verified prior-year historical records exist.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Comparative Multi-Month Stacked Bar Chart */}
            <div className="bg-card border border-border/50 rounded-xl p-5 shadow-2xs space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-foreground">
                    Historical Completed Months vs Present In-Progress & Forecast
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Blue bars represent confirmed historical actual sales. Purple stacked segments represent forecasted sales.
                  </p>
                </div>
              </div>

              <div className="h-64 sm:h-72 w-full pt-2">
                {forecast?.monthly_comparison?.historical_months_series && forecast.monthly_comparison.historical_months_series.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={forecast.monthly_comparison.historical_months_series}
                      margin={{ top: 10, right: 15, left: -10, bottom: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-border/40" vertical={false} />
                      <XAxis
                        dataKey="short_name"
                        stroke="currentColor"
                        className="text-muted-foreground"
                        fontSize={11}
                        tickLine={false}
                        axisLine={false}
                      />
                      <YAxis
                        stroke="currentColor"
                        className="text-muted-foreground"
                        fontSize={11}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={formatCurrencyShort}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "var(--card)",
                          borderColor: "var(--border)",
                          borderRadius: "12px",
                          boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.3)",
                          fontSize: "12px",
                        }}
                        formatter={(val: any, name?: any) => [
                          `₹${Number(val).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`,
                          name === "actual_sales" ? "Actual Sales" : "Forecasted Sales",
                        ]}
                        labelFormatter={(label: any, items?: any) => {
                          const item = (items as any)?.[0]?.payload;
                          return item ? item.month_label : label;
                        }}
                      />
                      <Legend
                        wrapperStyle={{ fontSize: "11px", paddingTop: "4px" }}
                        formatter={(value) => (value === "actual_sales" ? "Actual Sales" : "Forecasted Sales")}
                      />
                      <Bar dataKey="actual_sales" stackId="monthStack" fill="#3b82f6" radius={[0, 0, 0, 0]} />
                      <Bar dataKey="projected_sales" stackId="monthStack" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
                    No multi-month historical records available.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: Customer RFM Segmentation */}
        {activeTab === "rfm" && (
          <div className="space-y-5 animate-in fade-in duration-200">
            <div className="bg-card border border-border/50 rounded-xl p-5 shadow-2xs space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border/40 pb-3">
                <div>
                  <h3 className="text-base font-semibold text-foreground">
                    Customer Recency, Frequency & Monetary (RFM) Segmentation
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Clustered via scikit-learn machine learning based on purchase frequency, invoice spend, and recency of last order.
                  </p>
                </div>
                <span className="text-xs text-muted-foreground font-mono">
                  {rfmData.length} Active Customers Analyzed
                </span>
              </div>

              {rfmData.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-border/60 text-muted-foreground uppercase text-[10px] tracking-wider font-semibold">
                        <th className="py-2.5 px-3">Customer Party</th>
                        <th className="py-2.5 px-3 text-center">Tier Segment</th>
                        <th className="py-2.5 px-3 text-right">Recency (Days)</th>
                        <th className="py-2.5 px-3 text-right">Frequency (Orders)</th>
                        <th className="py-2.5 px-3 text-right">Total Revenue</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/30">
                      {rfmData.slice(0, 30).map((c: any, idx: number) => (
                        <tr key={idx} className="hover:bg-muted/40 transition-colors">
                          <td className="py-2.5 px-3 font-medium text-foreground">
                            {c.party_ledger__name || "Unknown Customer"}
                          </td>
                          <td className="py-2.5 px-3 text-center">
                            <span
                              className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                c.segment?.includes("High Value") || c.segment?.includes("VIP")
                                  ? "bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20"
                                  : c.segment?.includes("Medium")
                                  ? "bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20"
                                  : "bg-muted text-muted-foreground border border-border/40"
                              }`}
                            >
                              {c.segment || "Standard"}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono text-muted-foreground">
                            {c.recency}d ago
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono font-medium text-foreground">
                            {c.frequency} orders
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono font-bold text-foreground">
                            ₹{(c.monetary || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="py-12 text-center text-xs text-muted-foreground">
                  No sales invoices recorded yet for customer clustering.
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tab 4: Inventory Valuation & Margin Simulation */}
        {activeTab === "inventory" && (
          <div className="space-y-5 animate-in fade-in duration-200">
            {/* Inventory Valuation Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Total Stock Value (At Cost)
                </span>
                <div className="text-xl sm:text-2xl font-bold font-mono text-foreground">
                  ₹{stockValuation.stockCost.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-xs text-blue-600 dark:text-blue-400 font-medium">
                  {Number(kpis.total_stock_qty || 0).toLocaleString("en-IN")} physical units on hand
                </div>
              </div>

              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Catalog List Price (MRP)
                </span>
                <div className="text-xl sm:text-2xl font-bold font-mono text-foreground">
                  ₹{stockValuation.retailCost.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-xs text-muted-foreground">
                  Maximum potential revenue at full MRP
                </div>
              </div>

              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider">
                  Gross Profit Margin
                </span>
                <div className="text-xl sm:text-2xl font-bold font-mono text-emerald-600 dark:text-emerald-400">
                  ₹{stockValuation.margin.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-xs text-muted-foreground">
                  {stockValuation.markupPct}% markup over cost
                </div>
              </div>

              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Stock Health & Fulfillment
                </span>
                <div className="text-xl sm:text-2xl font-bold font-mono text-purple-600 dark:text-purple-400">
                  {Number(kpis.total_in_stock_items || 0)} / {Number(kpis.total_catalog_items || kpis.total_in_stock_items || 0)} Active
                </div>
                <div className="text-xs text-muted-foreground">
                  Items ready for immediate dispatch
                </div>
              </div>
            </div>

            {/* Interactive Margin & Discount Simulator */}
            <div className="bg-card border border-border/50 rounded-xl p-5 shadow-2xs space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/40 pb-3">
                <div>
                  <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                    <Tag className="w-4 h-4 text-purple-500" />
                    <span>Interactive Wholesale Retail Discount & Margin Simulator</span>
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Simulate how trade discounts impact gross margins across the inventory catalog.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-muted-foreground">Discount Rate:</span>
                  <input
                    type="number"
                    min="0"
                    max="90"
                    value={retailDiscount || ""}
                    placeholder="0"
                    onChange={(e) => setRetailDiscount(Math.max(0, Math.min(90, parseFloat(e.target.value) || 0)))}
                    className="w-16 bg-muted border border-border/60 rounded-lg px-2.5 py-1 text-sm font-mono font-bold text-right outline-none focus:border-purple-500"
                  />
                  <span className="text-xs font-bold text-muted-foreground">%</span>
                  {retailDiscount > 0 && (
                    <button
                      onClick={() => setRetailDiscount(0)}
                      className="text-xs text-muted-foreground hover:text-foreground px-2 py-1 bg-muted rounded cursor-pointer"
                    >
                      Reset
                    </button>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-1">
                <div className="p-3.5 bg-muted/40 rounded-xl border border-border/40 space-y-1">
                  <span className="text-[11px] text-muted-foreground font-semibold uppercase">Effective Realizable Value</span>
                  <div className="text-lg font-bold font-mono text-foreground">
                    ₹{stockValuation.effectiveRetail.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    After {retailDiscount}% simulated discount
                  </div>
                </div>

                <div className="p-3.5 bg-muted/40 rounded-xl border border-border/40 space-y-1">
                  <span className="text-[11px] text-emerald-600 dark:text-emerald-400 font-semibold uppercase">Simulated Profit Margin</span>
                  <div className="text-lg font-bold font-mono text-emerald-600 dark:text-emerald-400">
                    ₹{stockValuation.margin.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    {stockValuation.markupPct}% markup over cost
                  </div>
                </div>

                <div className="p-3.5 bg-muted/40 rounded-xl border border-border/40 space-y-1">
                  <span className="text-[11px] text-purple-600 dark:text-purple-400 font-semibold uppercase">Cost Recovery Multiple</span>
                  <div className="text-lg font-bold font-mono text-purple-600 dark:text-purple-400">
                    {stockValuation.costMultiple}x
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    Returns per ₹1 invested in stock
                  </div>
                </div>
              </div>
            </div>

            {/* 3. Inventory Intelligence Hub: Low-Stock Reorders & Sitting on Benches (Deadstock) */}
            <div className="bg-card border border-border/50 rounded-xl p-4 sm:p-5 shadow-2xs space-y-4">
              {/* Header with Sub-View Switcher & Filter Controls */}
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 border-b border-border/40 pb-4">
                {/* Left: View Switcher (Reorder vs Sitting on Benches) */}
                <div className="flex flex-wrap items-center gap-1.5 p-1 bg-muted/60 rounded-xl border border-border/70">
                  <button
                    type="button"
                    onClick={() => setInventorySubView("reorder")}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
                      inventorySubView === "reorder"
                        ? "bg-card text-foreground shadow-xs border border-border/60"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
                    <span>Low-Stock Reorders</span>
                    <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-blue-500/10 text-blue-600 dark:text-blue-400 font-mono font-bold">
                      {filteredReorderItems.length}
                    </span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setInventorySubView("deadstock")}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
                      inventorySubView === "deadstock"
                        ? "bg-card text-foreground shadow-xs border border-border/60"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <Clock className="w-3.5 h-3.5 text-rose-500" />
                    <span>Sitting on Benches / Slow-Moving</span>
                    <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-rose-500/10 text-rose-600 dark:text-rose-400 font-mono font-bold">
                      {filteredDeadstockItems.length}
                    </span>
                  </button>
                </div>

                {/* Right: Category, Brand & Search Filters */}
                <div className="flex flex-wrap sm:flex-nowrap items-center gap-2">
                  {/* Category Dropdown */}
                  <div className="relative w-full sm:w-auto">
                    <select
                      value={inventoryCategoryFilter}
                      onChange={(e) => handleCategoryFilterChange(e.target.value)}
                      className="w-full sm:w-40 bg-muted/60 border border-border/70 rounded-xl px-2.5 py-1.5 text-xs font-semibold text-foreground outline-none focus:ring-2 focus:ring-primary/40 cursor-pointer"
                    >
                      <option value="ALL">All Categories</option>
                      {inventoryAnalytics?.categories?.map((cat: any) => (
                        <option key={cat.id} value={cat.id}>
                          {cat.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Brand Dropdown (Mention Brand Here As Well!) */}
                  <div className="relative w-full sm:w-auto">
                    <select
                      value={inventoryBrandFilter}
                      onChange={(e) => setInventoryBrandFilter(e.target.value)}
                      className="w-full sm:w-36 bg-muted/60 border border-border/70 rounded-xl px-2.5 py-1.5 text-xs font-semibold text-foreground outline-none focus:ring-2 focus:ring-primary/40 cursor-pointer"
                    >
                      <option value="ALL">All Brands ({availableBrands.length})</option>
                      {availableBrands.map((b) => (
                        <option key={b} value={b}>
                          {b}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Search Input */}
                  <div className="relative w-full sm:w-48">
                    <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-3 top-2.5" />
                    <input
                      type="text"
                      placeholder="Search item, brand, SKU..."
                      value={inventorySearch}
                      onChange={(e) => setInventorySearch(e.target.value)}
                      className="w-full bg-muted/60 border border-border/70 text-foreground pl-8 pr-3 py-1.5 rounded-xl outline-none focus:ring-2 focus:ring-primary/40 text-xs"
                    />
                  </div>

                  {/* Refresh Button */}
                  <button
                    type="button"
                    onClick={() => fetchInventoryAnalytics(effectiveCompanyId, inventoryCategoryFilter)}
                    disabled={loadingInventoryAnalytics}
                    className="p-2 rounded-xl bg-muted/60 hover:bg-muted text-muted-foreground hover:text-foreground border border-border/70 transition-colors cursor-pointer shrink-0"
                    title="Refresh Inventory Intelligence"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${loadingInventoryAnalytics ? "animate-spin text-blue-500" : ""}`} />
                  </button>
                </div>
              </div>

              {/* ============================================================ */}
              {/* SUBVIEW 1: SMART LOW-STOCK REORDER INTELLIGENCE & PO HUB     */}
              {/* ============================================================ */}
              {inventorySubView === "reorder" && (
                <div className="space-y-4 animate-in fade-in duration-150">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                    <p className="text-muted-foreground">
                      Only shows items with <strong>verified sales demand</strong> that are critically short or below minimum required stock (Min Stock). Deadstock is automatically filtered out.
                    </p>
                    {inventoryBrandFilter !== "ALL" && (
                      <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 text-[11px] font-semibold self-start sm:self-auto">
                        <span>Brand Filter:</span>
                        <span className="font-bold">{inventoryBrandFilter}</span>
                        <button
                          type="button"
                          onClick={() => setInventoryBrandFilter("ALL")}
                          className="hover:opacity-75 cursor-pointer ml-0.5"
                          title="Clear brand filter"
                        >
                          ✕
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Action Toolbar: Select All, Bulk Quantity, Mass Min Stock & Draft PO Trigger */}
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 p-3 bg-muted/30 border border-border/40 rounded-xl">
                    {/* Left: Select All, Bulk Order Qty & Mass Min Stock */}
                    <div className="flex flex-wrap items-center gap-2.5">
                      {/* Select All Toggle */}
                      <button
                        type="button"
                        onClick={handleSelectAllToggle}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-card hover:bg-muted text-foreground border border-border/60 transition-colors cursor-pointer shadow-2xs"
                      >
                        {isAllSelected ? (
                          <CheckSquare className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
                        ) : (
                          <Square className="w-3.5 h-3.5 text-muted-foreground" />
                        )}
                        <span>{isAllSelected ? "Deselect All" : `Select All (${filteredReorderItems.length})`}</span>
                      </button>

                      {/* Bulk Quantity Setter */}
                      <div className="flex items-center gap-1.5 bg-card px-2.5 py-1 rounded-lg border border-border/60 shadow-2xs">
                        <span className="text-[11px] font-medium text-muted-foreground whitespace-nowrap">
                          Set order qty:
                        </span>
                        <input
                          type="number"
                          min="1"
                          value={bulkQuantityInput}
                          onChange={(e) => setBulkQuantityInput(Math.max(1, parseInt(e.target.value) || 1))}
                          className="w-12 bg-muted border border-border/70 rounded px-1.5 py-0.5 text-xs font-mono font-bold text-center text-foreground outline-none focus:ring-1 focus:ring-primary"
                        />
                        <button
                          type="button"
                          onClick={handleApplyBulkQuantity}
                          className="px-2 py-0.5 rounded text-[11px] font-bold bg-primary text-primary-foreground hover:bg-primary/90 transition-colors cursor-pointer"
                        >
                          Apply
                        </button>
                      </div>

                      {/* Mass-Wise Minimum Required Stock Button */}
                      <button
                        type="button"
                        onClick={() => setIsMassMinStockModalOpen(true)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-card hover:bg-muted text-foreground border border-border/60 transition-colors cursor-pointer shadow-2xs"
                        title="Configure minimum required quantity mass-wise across selected items, category, or catalog"
                      >
                        <Sliders className="w-3.5 h-3.5 text-blue-500" />
                        <span>Set Min Stock (Mass)</span>
                      </button>
                    </div>

                    {/* Right: Selected Counter & Draft PO Trigger */}
                    <div className="flex items-center justify-between md:justify-end gap-3 w-full md:w-auto">
                      <div className="text-right text-xs">
                        <div className="font-semibold text-foreground">
                          <span className="text-blue-600 dark:text-blue-400 font-bold">{selectedItemsData.count}</span> items ({selectedItemsData.units} units)
                        </div>
                        <div className="text-[11px] text-muted-foreground font-mono">
                          Est. ₹{selectedItemsData.cost.toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={handleOpenPoModal}
                        disabled={selectedReorderIds.size === 0}
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 disabled:pointer-events-none text-white transition-all shadow-sm cursor-pointer whitespace-nowrap"
                      >
                        <ShoppingCart className="w-4 h-4" />
                        <span>Draft Purchase Order ({selectedItemsData.count})</span>
                      </button>
                    </div>
                  </div>

                  {/* Responsive Reorder Items Table */}
                  {loadingInventoryAnalytics ? (
                    <div className="py-12 text-center text-xs text-muted-foreground space-y-2">
                      <RefreshCw className="w-5 h-5 animate-spin mx-auto text-blue-500" />
                      <div>Analyzing item velocity and stock levels...</div>
                    </div>
                  ) : filteredReorderItems.length === 0 ? (
                    <div className="py-12 text-center text-xs text-muted-foreground space-y-1 bg-muted/10 rounded-xl border border-dashed border-border/60">
                      <PackageCheck className="w-8 h-8 mx-auto text-emerald-500/70" />
                      <div className="font-bold text-foreground text-sm">No Urgent Reorders Needed!</div>
                      <p className="max-w-md mx-auto text-[11px]">
                        All high-velocity fast-moving items currently have sufficient stock on hand. Low-priority deadstock is excluded.
                      </p>
                    </div>
                  ) : (
                    <div className="rounded-xl border border-border/60 overflow-hidden">
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs">
                          <thead>
                            <tr className="bg-muted/40 border-b border-border/60 text-muted-foreground uppercase text-[10px] tracking-wider font-semibold">
                              <th className="py-2.5 px-3 w-10 text-center">
                                <input
                                  type="checkbox"
                                  checked={isAllSelected}
                                  onChange={handleSelectAllToggle}
                                  className="rounded border-border cursor-pointer"
                                />
                              </th>
                              <th className="py-2.5 px-2 text-center">Urgency</th>
                              <th className="py-2.5 px-3">Item / Size</th>
                              <th className="py-2.5 px-3">Brand</th>
                              <th className="py-2.5 px-3">Category</th>
                              <th className="py-2.5 px-3 text-right">Min Req</th>
                              <th className="py-2.5 px-3 text-right">Current Stock</th>
                              <th className="py-2.5 px-3 text-right">Sales Demand</th>
                              <th className="py-2.5 px-3 text-right">Last Purchase</th>
                              <th className="py-2.5 px-3 text-center w-36">Order Qty</th>
                              <th className="py-2.5 px-3 text-right">Est. Total</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border/30">
                            {filteredReorderItems.map((it: any) => {
                              const isSelected = selectedReorderIds.has(it.product_id);
                              const qty = orderQuantities[it.product_id] ?? it.suggested_qty ?? 5;
                              const lineTotal = qty * (it.purchase_price || 0);

                              return (
                                <tr
                                  key={it.product_id}
                                  className={`transition-colors ${
                                    isSelected ? "bg-blue-500/5 dark:bg-blue-500/10" : "hover:bg-muted/30"
                                  }`}
                                >
                                  {/* Checkbox */}
                                  <td className="py-2.5 px-3 text-center">
                                    <input
                                      type="checkbox"
                                      checked={isSelected}
                                      onChange={() => handleToggleSelect(it.product_id)}
                                      className="rounded border-border cursor-pointer"
                                    />
                                  </td>

                                  {/* Urgency Badge */}
                                  <td className="py-2.5 px-2 text-center">
                                    {it.urgency === "OUT_OF_STOCK" ? (
                                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20 whitespace-nowrap">
                                        Out of Stock
                                      </span>
                                    ) : it.urgency === "CRITICAL" ? (
                                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 whitespace-nowrap">
                                        Critical
                                      </span>
                                    ) : (
                                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 border border-yellow-500/20 whitespace-nowrap">
                                        Low Stock
                                      </span>
                                    )}
                                  </td>

                                  {/* Item Description (Clickable to view history) */}
                                  <td className="py-2.5 px-3">
                                    <button
                                      type="button"
                                      onClick={() => setSelectedHistoryItem(it)}
                                      className="text-left font-semibold text-foreground hover:text-blue-500 transition-colors cursor-pointer group flex items-center gap-1.5"
                                      title="Click to view transaction history"
                                    >
                                      <span>{it.name}</span>
                                      <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 text-blue-500 transition-opacity" />
                                    </button>
                                    <div className="text-[10px] text-muted-foreground font-mono flex items-center gap-2 mt-0.5">
                                      {it.sku && <span>SKU: {it.sku}</span>}
                                    </div>
                                  </td>

                                  {/* Brand Column (Dedicated & Prominent) */}
                                  <td className="py-2.5 px-3">
                                    {it.brand ? (
                                      <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold bg-primary/10 text-primary border border-primary/20 whitespace-nowrap">
                                        {it.brand}
                                      </span>
                                    ) : (
                                      <span className="text-muted-foreground/50 italic font-mono text-[11px]">—</span>
                                    )}
                                  </td>

                                  {/* Category */}
                                  <td className="py-2.5 px-3 text-muted-foreground">
                                    {it.category_name || "General"}
                                  </td>

                                  {/* Minimum Required Stock (Threshold) */}
                                  <td className="py-2.5 px-3 text-right font-mono text-xs">
                                    <span className="font-semibold text-foreground">
                                      {it.min_required_qty ?? it.reorder_level ?? 10}
                                    </span>
                                    {it.has_custom_reorder && (
                                      <span className="ml-1 text-[9px] font-bold px-1 py-0.2 rounded bg-blue-500/10 text-blue-600 dark:text-blue-400">
                                        Set
                                      </span>
                                    )}
                                  </td>

                                  {/* Current Stock */}
                                  <td className="py-2.5 px-3 text-right font-mono">
                                    <span
                                      className={`font-bold ${
                                        it.current_stock <= 0
                                          ? "text-rose-600 dark:text-rose-400"
                                          : it.current_stock <= 3
                                          ? "text-amber-600 dark:text-amber-400"
                                          : "text-foreground"
                                      }`}
                                    >
                                      {it.current_stock}
                                    </span>{" "}
                                    <span className="text-[10px] text-muted-foreground">{it.unit}</span>
                                  </td>

                                  {/* Sales Demand */}
                                  <td className="py-2.5 px-3 text-right font-mono text-muted-foreground">
                                    <span className="font-semibold text-blue-600 dark:text-blue-400">
                                      {it.invoices_count} inv
                                    </span>{" "}
                                    <span className="text-[10px]">({it.total_sold_qty} sold)</span>
                                  </td>

                                  {/* Last Purchase Rate & Supplier */}
                                  <td className="py-2.5 px-3 text-right font-mono">
                                    <div className="font-semibold text-foreground">
                                      ₹{(it.purchase_price || 0).toLocaleString("en-IN", {
                                        minimumFractionDigits: 2,
                                        maximumFractionDigits: 2,
                                      })}
                                    </div>
                                    <div className="text-[10px] text-muted-foreground truncate max-w-[120px] ml-auto">
                                      {it.last_supplier || "Catalog"}
                                    </div>
                                  </td>

                                  {/* Order Quantity Editor (Editable individual row and bulk) */}
                                  <td className="py-2.5 px-3 text-center">
                                    <div className="inline-flex items-center justify-center gap-1">
                                      <button
                                        type="button"
                                        onClick={() => handleItemQuantityChange(it.product_id, Math.max(1, qty - 1))}
                                        className="w-5 h-5 rounded bg-muted hover:bg-muted/80 text-foreground flex items-center justify-center cursor-pointer transition-colors"
                                        title="Decrease quantity"
                                      >
                                        <Minus className="w-2.5 h-2.5" />
                                      </button>
                                      <input
                                        type="number"
                                        min="1"
                                        value={qty}
                                        onChange={(e) =>
                                          handleItemQuantityChange(it.product_id, Math.max(1, parseInt(e.target.value) || 1))
                                        }
                                        className="w-14 bg-card border border-border/80 rounded py-0.5 text-center font-mono font-bold text-xs text-foreground outline-none focus:ring-1 focus:ring-primary"
                                      />
                                      <span className="text-[10px] text-muted-foreground font-mono">{it.unit}</span>
                                      <button
                                        type="button"
                                        onClick={() => handleItemQuantityChange(it.product_id, qty + 1)}
                                        className="w-5 h-5 rounded bg-muted hover:bg-muted/80 text-foreground flex items-center justify-center cursor-pointer transition-colors"
                                        title="Increase quantity"
                                      >
                                        <Plus className="w-2.5 h-2.5" />
                                      </button>
                                    </div>
                                  </td>

                                  {/* Line Total */}
                                  <td className="py-2.5 px-3 text-right font-mono font-bold text-foreground">
                                    ₹{lineTotal.toLocaleString("en-IN", {
                                      minimumFractionDigits: 2,
                                      maximumFractionDigits: 2,
                                    })}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* ========================================================================= */}
              {/* SUBVIEW 2: SITTING ON BENCHES / SLOW-MOVING (DEADSTOCK) INTELLIGENCE      */}
              {/* ========================================================================= */}
              {inventorySubView === "deadstock" && (
                <div className="space-y-4 animate-in fade-in duration-150">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                    <p className="text-muted-foreground">
                      Identifies items with <strong>physical stock on hand</strong> that have zero or low sales activity and have been sitting idle on benches/shelves. Pinpoints trapped working capital.
                    </p>
                    {inventoryBrandFilter !== "ALL" && (
                      <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 text-[11px] font-semibold self-start sm:self-auto">
                        <span>Brand Filter:</span>
                        <span className="font-bold">{inventoryBrandFilter}</span>
                        <button
                          type="button"
                          onClick={() => setInventoryBrandFilter("ALL")}
                          className="hover:opacity-75 cursor-pointer ml-0.5"
                          title="Clear brand filter"
                        >
                          ✕
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Summary Metric Cards for Deadstock on Benches */}
                  <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 p-3.5 bg-muted/20 border border-border/50 rounded-xl">
                    <div className="space-y-0.5">
                      <div className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">
                        Trapped Working Capital
                      </div>
                      <div className="text-lg sm:text-xl font-bold font-mono text-rose-600 dark:text-rose-400">
                        ₹{(inventoryAnalytics?.deadstock_summary?.locked_capital || 0).toLocaleString("en-IN", {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}
                      </div>
                      <div className="text-[10px] text-muted-foreground">
                        Tied up on benches at purchase cost
                      </div>
                    </div>

                    <div className="space-y-0.5">
                      <div className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">
                        Idle Physical Units
                      </div>
                      <div className="text-lg sm:text-xl font-bold font-mono text-foreground">
                        {(inventoryAnalytics?.deadstock_summary?.total_units || 0).toLocaleString("en-IN")} units
                      </div>
                      <div className="text-[10px] text-muted-foreground">
                        Across {inventoryAnalytics?.deadstock_summary?.total_items || 0} slow-moving products
                      </div>
                    </div>

                    <div className="space-y-0.5">
                      <div className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">
                        Never Sold (Dormant)
                      </div>
                      <div className="text-lg sm:text-xl font-bold font-mono text-purple-600 dark:text-purple-400">
                        {inventoryAnalytics?.deadstock_summary?.dormant_count || 0} items
                      </div>
                      <div className="text-[10px] text-muted-foreground">
                        Zero sales invoices ever recorded
                      </div>
                    </div>

                    <div className="space-y-0.5">
                      <div className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">
                        Critical Inactive (60d+)
                      </div>
                      <div className="text-lg sm:text-xl font-bold font-mono text-amber-600 dark:text-amber-400">
                        {(inventoryAnalytics?.deadstock_summary?.critical_90_count || 0) +
                          (inventoryAnalytics?.deadstock_summary?.stagnant_60_count || 0)}{" "}
                        items
                      </div>
                      <div className="text-[10px] text-muted-foreground">
                        No movement in over 60 days
                      </div>
                    </div>
                  </div>

                  {/* Top Brands on Benches Quick Bar */}
                  {inventoryAnalytics?.deadstock_summary?.by_brand &&
                    inventoryAnalytics.deadstock_summary.by_brand.length > 0 && (
                      <div className="flex flex-wrap items-center gap-2 p-2.5 bg-muted/15 border border-border/40 rounded-xl text-xs">
                        <span className="text-[11px] font-semibold text-muted-foreground whitespace-nowrap">
                          Top Brands on Benches:
                        </span>
                        {inventoryAnalytics.deadstock_summary.by_brand.map((b: any) => (
                          <button
                            key={b.brand}
                            type="button"
                            onClick={() =>
                              setInventoryBrandFilter(inventoryBrandFilter === b.brand ? "ALL" : b.brand)
                            }
                            className={`px-2.5 py-1 rounded-lg font-mono text-[11px] border transition-all cursor-pointer ${
                              inventoryBrandFilter === b.brand
                                ? "bg-primary text-primary-foreground border-primary font-bold shadow-2xs"
                                : "bg-card hover:bg-muted text-foreground border-border/60 font-medium"
                            }`}
                          >
                            <span>{b.brand}</span>: <span className="font-bold">₹{formatCurrencyShort(b.locked_capital)}</span>
                          </button>
                        ))}
                        {inventoryBrandFilter !== "ALL" && (
                          <button
                            type="button"
                            onClick={() => setInventoryBrandFilter("ALL")}
                            className="text-[11px] text-muted-foreground hover:text-foreground underline ml-1 cursor-pointer font-medium"
                          >
                            Show All
                          </button>
                        )}
                      </div>
                    )}

                  {/* Filter Toolbar: Aging Periods & Export CSV */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 bg-muted/30 border border-border/40 rounded-xl">
                    {/* Left: Aging Filters */}
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-[11px] font-semibold text-muted-foreground mr-1">
                        Idle Period:
                      </span>
                      {[
                        { key: "all", label: "All Idle (>30d)" },
                        { key: "60", label: "60+ Days" },
                        { key: "90", label: "90+ Days (Critical)" },
                        { key: "dormant", label: "Never Sold (Dormant)" },
                      ].map((f) => (
                        <button
                          key={f.key}
                          type="button"
                          onClick={() => setDeadstockAgingFilter(f.key as any)}
                          className={`px-2.5 py-1 rounded-lg text-xs font-semibold border transition-all cursor-pointer ${
                            deadstockAgingFilter === f.key
                              ? "bg-primary text-primary-foreground border-primary shadow-2xs"
                              : "bg-card hover:bg-muted text-muted-foreground hover:text-foreground border-border/60"
                          }`}
                        >
                          {f.label}
                        </button>
                      ))}
                    </div>

                    {/* Right: Item Count & Export CSV */}
                    <div className="flex items-center gap-3">
                      <div className="text-xs font-mono text-muted-foreground">
                        Showing <span className="font-bold text-foreground">{filteredDeadstockItems.length}</span> items
                      </div>
                      <button
                        type="button"
                        onClick={handleExportDeadstockCsv}
                        disabled={filteredDeadstockItems.length === 0}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-card hover:bg-muted text-foreground border border-border/60 transition-colors cursor-pointer shadow-2xs"
                        title="Download deadstock report in clean CSV spreadsheet"
                      >
                        <Download className="w-3.5 h-3.5 text-blue-500" />
                        <span>Export CSV</span>
                      </button>
                    </div>
                  </div>

                  {/* Sitting on Benches Table */}
                  {loadingInventoryAnalytics ? (
                    <div className="py-12 text-center text-xs text-muted-foreground space-y-2">
                      <RefreshCw className="w-5 h-5 animate-spin mx-auto text-blue-500" />
                      <div>Scanning catalog for idle inventory on benches...</div>
                    </div>
                  ) : filteredDeadstockItems.length === 0 ? (
                    <div className="py-12 text-center text-xs text-muted-foreground space-y-1 bg-muted/10 rounded-xl border border-dashed border-border/60">
                      <PackageCheck className="w-8 h-8 mx-auto text-emerald-500/70" />
                      <div className="font-bold text-foreground text-sm">No Deadstock Found!</div>
                      <p className="max-w-md mx-auto text-[11px]">
                        No stocked items match the selected idle period or brand criteria. All stocked items have active sales.
                      </p>
                    </div>
                  ) : (
                    <div className="rounded-xl border border-border/60 overflow-hidden">
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs">
                          <thead>
                            <tr className="bg-muted/40 border-b border-border/60 text-muted-foreground uppercase text-[10px] tracking-wider font-semibold">
                              <th className="py-2.5 px-3 w-10 text-center">#</th>
                              <th className="py-2.5 px-2 text-center">Status</th>
                              <th className="py-2.5 px-3">Item / Size</th>
                              <th className="py-2.5 px-3">Brand</th>
                              <th className="py-2.5 px-3">Category</th>
                              <th className="py-2.5 px-3 text-right">Units on Bench</th>
                              <th className="py-2.5 px-3 text-right">Cost Rate</th>
                              <th className="py-2.5 px-3 text-right">Locked Capital</th>
                              <th className="py-2.5 px-3 text-right">Catalog MRP</th>
                              <th className="py-2.5 px-3 text-center">Days Idle</th>
                              <th className="py-2.5 px-3 text-right">Last Activity</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border/30">
                            {filteredDeadstockItems.map((it: any, idx: number) => (
                              <tr
                                key={it.product_id}
                                className="hover:bg-muted/30 transition-colors"
                              >
                                <td className="py-2.5 px-3 text-center font-mono text-[11px] text-muted-foreground">
                                  {idx + 1}
                                </td>

                                {/* Status Badge */}
                                <td className="py-2.5 px-2 text-center">
                                  {it.status === "DORMANT" ? (
                                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20 whitespace-nowrap">
                                      Never Sold
                                    </span>
                                  ) : it.status === "CRITICAL_DEADSTOCK" ? (
                                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20 whitespace-nowrap">
                                      90+ Days
                                    </span>
                                  ) : it.status === "STAGNANT" ? (
                                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 whitespace-nowrap">
                                      60-90 Days
                                    </span>
                                  ) : (
                                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 border border-yellow-500/20 whitespace-nowrap">
                                      30-60 Days
                                    </span>
                                  )}
                                </td>

                                {/* Item Description */}
                                <td className="py-2.5 px-3">
                                  <button
                                    type="button"
                                    onClick={() => setSelectedHistoryItem(it)}
                                    className="text-left font-semibold text-foreground hover:text-blue-500 transition-colors cursor-pointer group flex items-center gap-1.5"
                                    title="Click to view transaction history"
                                  >
                                    <span>{it.name}</span>
                                    <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 text-blue-500 transition-opacity" />
                                  </button>
                                  <div className="text-[10px] text-muted-foreground font-mono flex items-center gap-2 mt-0.5">
                                    {it.sku && <span>SKU: {it.sku}</span>}
                                  </div>
                                </td>

                                {/* Brand Column */}
                                <td className="py-2.5 px-3">
                                  {it.brand ? (
                                    <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold bg-primary/10 text-primary border border-primary/20 whitespace-nowrap">
                                      {it.brand}
                                    </span>
                                  ) : (
                                    <span className="text-muted-foreground/50 italic font-mono text-[11px]">—</span>
                                  )}
                                </td>

                                {/* Category */}
                                <td className="py-2.5 px-3 text-muted-foreground">
                                  {it.category_name || "General"}
                                </td>

                                {/* Physical Units on Bench */}
                                <td className="py-2.5 px-3 text-right font-mono">
                                  <span className="font-bold text-foreground">
                                    {it.current_stock}
                                  </span>{" "}
                                  <span className="text-[10px] text-muted-foreground">{it.unit}</span>
                                </td>

                                {/* Purchase Cost */}
                                <td className="py-2.5 px-3 text-right font-mono text-muted-foreground">
                                  ₹{(it.purchase_price || 0).toLocaleString("en-IN", {
                                    minimumFractionDigits: 2,
                                    maximumFractionDigits: 2,
                                  })}
                                </td>

                                {/* Locked Working Capital */}
                                <td className="py-2.5 px-3 text-right font-mono font-bold text-rose-600 dark:text-rose-400">
                                  ₹{(it.locked_capital || 0).toLocaleString("en-IN", {
                                    minimumFractionDigits: 2,
                                    maximumFractionDigits: 2,
                                  })}
                                </td>

                                {/* Potential Revenue (Selling Price) */}
                                <td className="py-2.5 px-3 text-right font-mono text-muted-foreground">
                                  ₹{(it.potential_revenue || 0).toLocaleString("en-IN", {
                                    minimumFractionDigits: 2,
                                    maximumFractionDigits: 2,
                                  })}
                                </td>

                                {/* Days Idle */}
                                <td className="py-2.5 px-3 text-center font-mono">
                                  {it.status === "DORMANT" ? (
                                    <span className="text-[11px] text-purple-600 dark:text-purple-400 font-bold">
                                      Never
                                    </span>
                                  ) : (
                                    <span
                                      className={`text-xs font-semibold ${
                                        it.days_idle >= 90
                                          ? "text-rose-600 dark:text-rose-400 font-bold"
                                          : it.days_idle >= 60
                                          ? "text-amber-600 dark:text-amber-400"
                                          : "text-muted-foreground"
                                      }`}
                                    >
                                      {it.days_idle}d
                                    </span>
                                  )}
                                </td>

                                {/* Last Activity */}
                                <td className="py-2.5 px-3 text-right font-mono text-[10px] text-muted-foreground">
                                  {it.last_sale_date ? (
                                    <div>
                                      <span className="text-blue-500 font-medium">Sold:</span> {it.last_sale_date}
                                    </div>
                                  ) : it.last_purchase_date ? (
                                    <div>
                                      <span className="text-emerald-500 font-medium">Stocked:</span> {it.last_purchase_date}
                                    </div>
                                  ) : (
                                    <span>No activity</span>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* 4. Item Velocity & Most Frequent Movement Section */}
            <div className="bg-card border border-border/50 rounded-xl p-4 sm:p-5 shadow-2xs space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border/40 pb-3">
                <div>
                  <h3 className="text-sm sm:text-base font-bold text-foreground flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-blue-500" />
                    <span>Item Velocity & Most Frequent Movement</span>
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Top recurring items sold and purchased across posted invoices and vendor bills.
                  </p>
                </div>
                <div className="text-xs text-muted-foreground font-mono">
                  {inventoryCategoryFilter === "ALL"
                    ? "All Categories"
                    : inventoryAnalytics?.categories?.find((c: any) => c.id === inventoryCategoryFilter)?.name || "Category Filtered"}
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Most Frequent Sold */}
                <div className="bg-muted/20 border border-border/60 rounded-xl p-4 space-y-3">
                  <div className="flex items-center justify-between border-b border-border/40 pb-2">
                    <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-blue-500"></span>
                      Most Frequent Items Sold
                    </span>
                    <span className="text-[10px] text-muted-foreground font-mono">By Invoice Count</span>
                  </div>

                  {(!inventoryAnalytics?.top_sold || inventoryAnalytics.top_sold.length === 0) ? (
                    <div className="py-6 text-center text-xs text-muted-foreground">
                      No sales transactions recorded for this selection.
                    </div>
                  ) : (
                    <div className="space-y-1.5">
                      {inventoryAnalytics.top_sold.map((it: any, idx: number) => (
                        <div
                          key={idx}
                          onClick={() => setSelectedHistoryItem(it)}
                          className="flex items-center justify-between p-2.5 rounded-lg bg-card/60 hover:bg-muted/40 border border-border/30 text-xs transition-colors cursor-pointer group"
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="font-mono text-[10px] text-muted-foreground w-4">#{idx + 1}</span>
                            <div className="truncate">
                              <div className="font-semibold text-foreground group-hover:text-blue-500 transition-colors truncate">
                                {it.name}
                              </div>
                              <div className="text-[10px] text-muted-foreground font-mono">
                                {it.brand || "Unbranded"} • Stock: {it.current_stock} {it.unit}
                              </div>
                            </div>
                          </div>
                          <div className="text-right font-mono shrink-0 ml-2">
                            <div className="font-bold text-blue-600 dark:text-blue-400">
                              {it.invoices_count} inv ({it.total_qty} {it.unit})
                            </div>
                            <div className="text-[10px] text-muted-foreground">
                              ₹{it.total_revenue?.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Most Frequent Purchased */}
                <div className="bg-muted/20 border border-border/60 rounded-xl p-4 space-y-3">
                  <div className="flex items-center justify-between border-b border-border/40 pb-2">
                    <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                      Most Frequent Items Purchased
                    </span>
                    <span className="text-[10px] text-muted-foreground font-mono">By Bill Count</span>
                  </div>

                  {(!inventoryAnalytics?.top_purchased || inventoryAnalytics.top_purchased.length === 0) ? (
                    <div className="py-6 text-center text-xs text-muted-foreground">
                      No purchase transactions recorded for this selection.
                    </div>
                  ) : (
                    <div className="space-y-1.5">
                      {inventoryAnalytics.top_purchased.map((it: any, idx: number) => (
                        <div
                          key={idx}
                          onClick={() => setSelectedHistoryItem(it)}
                          className="flex items-center justify-between p-2.5 rounded-lg bg-card/60 hover:bg-muted/40 border border-border/30 text-xs transition-colors cursor-pointer group"
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="font-mono text-[10px] text-muted-foreground w-4">#{idx + 1}</span>
                            <div className="truncate">
                              <div className="font-semibold text-foreground group-hover:text-emerald-500 transition-colors truncate">
                                {it.name}
                              </div>
                              <div className="text-[10px] text-muted-foreground font-mono">
                                {it.brand || "Unbranded"} • Stock: {it.current_stock} {it.unit}
                              </div>
                            </div>
                          </div>
                          <div className="text-right font-mono shrink-0 ml-2">
                            <div className="font-bold text-emerald-600 dark:text-emerald-400">
                              {it.bills_count} bills ({it.total_qty} {it.unit})
                            </div>
                            <div className="text-[10px] text-muted-foreground">
                              ₹{it.total_spend?.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 5: Cash Flow & Working Capital */}
        {activeTab === "cashflow" && (
          <div className="space-y-5 animate-in fade-in duration-200">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Money to Collect (Debtors)
                </span>
                <div className="text-xl sm:text-2xl font-bold font-mono text-emerald-600 dark:text-emerald-400">
                  ₹{Number(kpis.money_to_collect || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-xs text-muted-foreground">
                  Pending customer receivables
                </div>
              </div>

              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Bills to Pay (Creditors)
                </span>
                <div className="text-xl sm:text-2xl font-bold font-mono text-rose-600 dark:text-rose-400">
                  ₹{Number(kpis.bills_to_pay || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-xs text-muted-foreground">
                  Vendor payables due
                </div>
              </div>

              <div className="bg-card border border-border/50 rounded-xl p-4 shadow-2xs space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Available Liquid Cash & Bank
                </span>
                <div className="text-xl sm:text-2xl font-bold font-mono text-blue-600 dark:text-blue-400">
                  ₹{Number(kpis.cash_and_bank || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-xs text-muted-foreground">
                  Current bank balances + physical cash in hand
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Mass-Wise Minimum Required Stock Configuration Modal */}
        <MassMinStockModal
          isOpen={isMassMinStockModalOpen}
          onClose={() => setIsMassMinStockModalOpen(false)}
          scope={massMinStockScope}
          onScopeChange={setMassMinStockScope}
          minStockInput={massMinStockInput}
          onMinStockInputChange={setMassMinStockInput}
          onApply={handleApplyMassMinStock}
          loading={updatingMinStock}
          selectedCount={selectedReorderIds.size}
          currentCategoryName={currentCategoryName}
          hasCategoryFilter={inventoryCategoryFilter !== "ALL"}
        />

        {/* Purchase Order Draft Modal */}
        <PurchaseOrderDraftModal
          isOpen={isPoModalOpen}
          onClose={() => setIsPoModalOpen(false)}
          items={poDraftItems}
          companyName={activeCompany?.name || "Company"}
          companyGstin={activeCompany?.gstin || ""}
          companyAddress={
            activeCompany?.address
              ? `${activeCompany.address}${activeCompany.city ? `, ${activeCompany.city}` : ""}`
              : ""
          }
          onUpdateQuantity={handleItemQuantityChange}
          onRemoveItem={handleRemoveFromDraft}
        />

        {/* Item Invoice & Bill History Inspection Modal */}
        <ItemHistoryModal
          isOpen={!!selectedHistoryItem}
          onClose={() => setSelectedHistoryItem(null)}
          productId={selectedHistoryItem?.product_id || selectedHistoryItem?.id || null}
          productName={selectedHistoryItem?.name || ""}
          companyId={effectiveCompanyId || activeCompanyId || ""}
        />
      </div>
    </DashboardLayout>
  );
}

export default function AnalyticsHubPage() {
  return (
    <React.Suspense
      fallback={
        <DashboardLayout>
          <div className="flex flex-col items-center justify-center min-h-[400px] space-y-3">
            <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
            <div className="text-xs text-muted-foreground font-medium">Loading analytics hub...</div>
          </div>
        </DashboardLayout>
      }
    >
      <AnalyticsHubContent />
    </React.Suspense>
  );
}
