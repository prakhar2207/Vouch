"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import { useToast } from '@/context/ToastContext';
import PriceListImportModal from '@/components/modals/PriceListImportModal';
import BulkBrandDiscountModal from '@/components/modals/BulkBrandDiscountModal';
import ConfirmModal from '@/components/modals/ConfirmModal';
import ItemHistoryModal from '@/components/modals/ItemHistoryModal';
import { 
  ArrowUpDown, 
  FileSpreadsheet, 
  Plus, 
  Search, 
  Tag, 
  Layers, 
  Edit2, 
  Trash2,
  Check, 
  X,
  Info,
  Percent,
  Boxes,
  Sparkles,
  History,
  BarChart2,
  FileText,
  RefreshCw
} from 'lucide-react';

type SortOption = 
  | 'NAME_ASC' 
  | 'NAME_DESC' 
  | 'MRP_DESC' 
  | 'MRP_ASC' 
  | 'PURCHASE_DESC' 
  | 'PURCHASE_ASC' 
  | 'STOCK_DESC' 
  | 'STOCK_ASC';

const isIntegerUnit = (unit?: string) => {
  if (!unit) return true; // Default unit is PCS
  const u = unit.trim().toUpperCase();
  const fractionalUnits = ['KG', 'KGS', 'KILOGRAM', 'KILOGRAMS', 'LTR', 'LTRS', 'LITRE', 'LITRES', 'LITER', 'LITERS', 'MTR', 'MTRS', 'METER', 'METERS', 'METRE', 'METRES'];
  return !fractionalUnits.includes(u);
};

const formatStockQuantity = (qty: any, unit?: string) => {
  const num = parseFloat(qty) || 0;
  if (isIntegerUnit(unit)) {
    return Math.round(num).toLocaleString('en-IN');
  }
  return num.toLocaleString('en-IN', { maximumFractionDigits: 2 });
};

export default function CategoryDetailPage() {
  const router = useRouter();
  const params = useParams();
  const categoryId = params.id as string;
  const { toast } = useToast();

  const [category, setCategory] = useState<any>(null);
  const [products, setProducts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [companyId, setCompanyId] = useState('');
  
  const categoryStockValue = useMemo(() => {
    return products.reduce((acc, p) => acc + ((parseFloat(p.stock_quantity) || 0) * (parseFloat(p.purchase_price) || 0)), 0);
  }, [products]);

  const categoryStockQty = useMemo(() => {
    return products.reduce((acc, p) => acc + (parseFloat(p.stock_quantity) || 0), 0);
  }, [products]);
  // Sort and Brand Filter state
  const [sortBy, setSortBy] = useState<SortOption>('NAME_ASC');
  const [selectedBrands, setSelectedBrands] = useState<string[]>([]);
  
  // Modals state
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [isBulkDiscountModalOpen, setIsBulkDiscountModalOpen] = useState(false);
  const [isMergeModalOpen, setIsMergeModalOpen] = useState(false);
  const [isMerging, setIsMerging] = useState(false);
  const [deleteConfirmParams, setDeleteConfirmParams] = useState<{ id: string, name: string } | null>(null);

  // Edit state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editData, setEditData] = useState<any>({});
  const [savingId, setSavingId] = useState<string | null>(null);

  // Category Edit State
  const [isCategoryEditing, setIsCategoryEditing] = useState(false);
  const [categoryEditData, setCategoryEditData] = useState({ name: '', hsn_code: '', gst_rate: 18 });
  const [savingCategory, setSavingCategory] = useState(false);

  // Item Bill History & Category Analytics State
  const [selectedHistoryItem, setSelectedHistoryItem] = useState<any>(null);
  const [analyticsOpen, setAnalyticsOpen] = useState(false);
  const [topAnalytics, setTopAnalytics] = useState<any>(null);
  const [loadingAnalytics, setLoadingAnalytics] = useState(false);

  const fetchAnalytics = async (cid?: string) => {
    const targetCompanyId = cid || companyId;
    if (!targetCompanyId) return;
    setLoadingAnalytics(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.get(
        `${API_BASE_URL}/api/v1/inventory/analytics/${targetCompanyId}/?category_id=${categoryId}&limit=6`,
        { headers }
      );
      if (res.data.success) {
        setTopAnalytics(res.data.data);
      }
    } catch (err) {
      console.error("Failed to fetch inventory analytics:", err);
    } finally {
      setLoadingAnalytics(false);
    }
  };

  useEffect(() => {
    if (!isAuthenticated()) { router.push('/login'); return; }
    fetchData();
  }, [router, categoryId]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const cid = compRes.data.data[0]?.id;
      if (!cid) return;
      setCompanyId(cid);

      const catRes = await axios.get(`${API_BASE_URL}/api/v1/inventory/categories/${cid}/`, { headers });
      const cat = (catRes.data.data || []).find((c: any) => c.id === categoryId);
      setCategory(cat);

      const prodRes = await axios.get(`${API_BASE_URL}/api/v1/inventory/products/${cid}/?category=${categoryId}`, { headers });
      setProducts(prodRes.data.data || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleMergeDuplicates = async () => {
    if (!companyId) return;
    setIsMerging(true);
    try {
      const token = getAccessToken();
      const res = await axios.post(
        `${API_BASE_URL}/api/v1/inventory/combine-items/${companyId}/`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.data.success) {
        toast.success(
          "Items Combined Successfully",
          `Cleaned & merged ${res.data.total_merged_groups} duplicate groups and normalized ${res.data.total_renamed_items} item names to standard single-space format.`
        );
        fetchData();
      }
    } catch (err: any) {
      toast.error("Combine Failed", err.response?.data?.error || "Failed to combine duplicate items.");
    } finally {
      setIsMerging(false);
      setIsMergeModalOpen(false);
    }
  };

  const startEdit = (p: any) => {
    setEditingId(p.id);
    const sp = parseFloat(p.selling_price) || 0;
    const pp = parseFloat(p.purchase_price) || 0;
    const dp = sp > 0 ? ((sp - pp) / sp) * 100 : 0;
    const isInt = isIntegerUnit(p.unit);
    const sq = parseFloat(p.stock_quantity) || 0;
    setEditData({
      name: p.name,
      alias: p.alias || '',
      brand: p.brand || '',
      selling_price: sp,
      wholesaler_price: p.wholesaler_price,
      purchase_price: pp,
      stock_quantity: isInt ? Math.round(sq) : sq,
      discount_percent: dp.toFixed(2),
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditData({});
  };

  const saveEdit = async (productId: string) => {
    setSavingId(productId);
    try {
      const product = products.find(p => p.id === productId) || products.flatMap(p => p.variants || []).find((v: any) => v.id === productId);
      const isInt = isIntegerUnit(product?.unit);
      const payload = {
        ...editData,
        stock_quantity: editData.stock_quantity !== undefined 
          ? (isInt ? Math.round(parseFloat(editData.stock_quantity) || 0) : parseFloat(editData.stock_quantity) || 0)
          : undefined
      };

      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.patch(
        `${API_BASE_URL}/api/v1/inventory/products/${companyId}/${productId}/`,
        payload,
        { headers }
      );
      if (res.data.success) {
        setProducts(prev => prev.map(p => {
          if (p.id === productId) return { ...p, ...payload };
          if (p.variants) {
            return {
              ...p,
              variants: p.variants.map((v: any) => v.id === productId ? { ...v, ...payload } : v)
            };
          }
          return p;
        }));
        setEditingId(null);
        setEditData({});
        toast.success("Item updated successfully!");
      }
    } catch (err: any) {
      toast.error('Save failed', err.response?.data?.error || err.message);
    } finally {
      setSavingId(null);
    }
  };

  const executeDelete = async (productId: string) => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.delete(
        `${API_BASE_URL}/api/v1/inventory/products/${companyId}/${productId}/`,
        { headers }
      );
      if (res.data.success) {
        toast.success("Item deleted successfully!");
        setProducts(prev => prev.filter(p => p.id !== productId));
        if (editingId === productId) cancelEdit();
      }
    } catch (err: any) {
      toast.error('Delete failed', err.response?.data?.error || err.message);
    }
  };

  const deleteProduct = (productId: string, productName: string) => {
    setDeleteConfirmParams({ id: productId, name: productName });
  };

  const startCategoryEdit = () => {
    setCategoryEditData({
      name: category?.name || '',
      hsn_code: category?.hsn_code || '',
      gst_rate: category?.gst_rate || 18,
    });
    setIsCategoryEditing(true);
  };

  const saveCategoryEdit = async () => {
    setSavingCategory(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.patch(
        `${API_BASE_URL}/api/v1/inventory/categories/${companyId}/${categoryId}/`,
        categoryEditData,
        { headers }
      );
      if (res.data.success) {
        setCategory({ ...category, ...categoryEditData });
        setIsCategoryEditing(false);
        toast.success("Category updated successfully!");
      }
    } catch (err: any) {
      toast.error('Save failed', err.response?.data?.error || err.message);
    } finally {
      setSavingCategory(false);
    }
  };

  // Compute available brands with counts (including Unbranded)
  const availableBrands = useMemo(() => {
    const counts: Record<string, number> = {};
    products.forEach((p) => {
      const b = (p.brand || '').trim();
      const key = b || 'Unbranded';
      counts[key] = (counts[key] || 0) + 1;
    });
    return counts;
  }, [products]);

  const existingBrandList = useMemo(() => Object.keys(availableBrands).sort((a, b) => {
    if (a === 'Unbranded') return 1;
    if (b === 'Unbranded') return -1;
    return a.localeCompare(b);
  }), [availableBrands]);

  const toggleBrand = (b: string) => {
    setSelectedBrands(prev => 
      prev.includes(b) ? prev.filter(x => x !== b) : [...prev, b]
    );
  };

  const clearBrandFilter = () => {
    setSelectedBrands([]);
  };

  // Filter items based on search and selected brands
  const filteredProducts = useMemo(() => {
    return products.filter(p => {
      const matchesSearch = 
        p.name.toLowerCase().includes(search.toLowerCase()) ||
        (p.brand || '').toLowerCase().includes(search.toLowerCase()) ||
        p.sku.toLowerCase().includes(search.toLowerCase());
      
      if (!matchesSearch) return false;

      if (selectedBrands.length > 0) {
        const brandClean = (p.brand || '').trim();
        const isUnbranded = !brandClean || brandClean.toLowerCase() === 'unbranded' || brandClean.toLowerCase() === 'generic';
        if (selectedBrands.includes('Unbranded') && isUnbranded) return true;
        return selectedBrands.includes(brandClean);
      }
      return true;
    });
  }, [products, search, selectedBrands]);

  // Group items by base item name into unified item blocks
  interface ItemBlock {
    baseName: string;
    alias?: string;
    variants: any[];
  }

  const groupedItemBlocks = useMemo(() => {
    const groups: Record<string, ItemBlock> = {};

    filteredProducts.forEach(p => {
      const key = p.name.trim().toLowerCase();
      if (!groups[key]) {
        groups[key] = {
          baseName: p.name.trim(),
          alias: p.alias,
          variants: []
        };
      }
      groups[key].variants.push(p);
    });

    const list = Object.values(groups);

    // Sort variants within each item block: Branded first (alphabetical), Unbranded at the bottom
    list.forEach((block) => {
      block.variants.sort((a, b) => {
        const aBrand = (a.brand || '').trim();
        const bBrand = (b.brand || '').trim();
        const aIsUnbranded = !aBrand || aBrand.toLowerCase() === 'unbranded' || aBrand.toLowerCase() === 'generic';
        const bIsUnbranded = !bBrand || bBrand.toLowerCase() === 'unbranded' || bBrand.toLowerCase() === 'generic';
        if (aIsUnbranded && !bIsUnbranded) return 1;
        if (!aIsUnbranded && bIsUnbranded) return -1;
        return aBrand.localeCompare(bBrand);
      });
    });

    // Sort blocks
    list.sort((a, b) => {
      if (sortBy === 'NAME_ASC') {
        return a.baseName.localeCompare(b.baseName, undefined, { numeric: true, sensitivity: 'base' });
      }
      if (sortBy === 'NAME_DESC') {
        return b.baseName.localeCompare(a.baseName, undefined, { numeric: true, sensitivity: 'base' });
      }

      const aMaxMrp = Math.max(...a.variants.map(v => parseFloat(v.selling_price) || 0));
      const bMaxMrp = Math.max(...b.variants.map(v => parseFloat(v.selling_price) || 0));
      const aMinMrp = Math.min(...a.variants.map(v => parseFloat(v.selling_price) || 0));
      const bMinMrp = Math.min(...b.variants.map(v => parseFloat(v.selling_price) || 0));

      if (sortBy === 'MRP_DESC') return bMaxMrp - aMaxMrp;
      if (sortBy === 'MRP_ASC') return aMinMrp - bMinMrp;

      const aMaxPurch = Math.max(...a.variants.map(v => parseFloat(v.purchase_price) || 0));
      const bMaxPurch = Math.max(...b.variants.map(v => parseFloat(v.purchase_price) || 0));
      const aMinPurch = Math.min(...a.variants.map(v => parseFloat(v.purchase_price) || 0));
      const bMinPurch = Math.min(...b.variants.map(v => parseFloat(v.purchase_price) || 0));

      if (sortBy === 'PURCHASE_DESC') return bMaxPurch - aMaxPurch;
      if (sortBy === 'PURCHASE_ASC') return aMinPurch - bMinPurch;

      const aStock = a.variants.reduce((acc, v) => acc + (parseFloat(v.stock_quantity) || 0), 0);
      const bStock = b.variants.reduce((acc, v) => acc + (parseFloat(v.stock_quantity) || 0), 0);

      if (sortBy === 'STOCK_DESC') return bStock - aStock;
      if (sortBy === 'STOCK_ASC') return aStock - bStock;

      return 0;
    });

    return list;
  }, [filteredProducts, sortBy]);

  // Flat list of all navigable product variant rows in the table
  const navigableRows = useMemo(() => {
    const list: { productId: string; product: any; blockBaseName: string }[] = [];
    groupedItemBlocks.forEach(block => {
      block.variants.forEach(v => {
        list.push({ productId: v.id, product: v, blockBaseName: block.baseName });
      });
    });
    return list;
  }, [groupedItemBlocks]);

  const [focusedRowIndex, setFocusedRowIndex] = useState<number>(-1);

  // Auto-scroll focused row into view smoothly
  const scrollToRow = (index: number) => {
    if (index >= 0 && index < navigableRows.length) {
      const pid = navigableRows[index].productId;
      const el = document.getElementById(`row-product-${pid}`);
      if (el) {
        el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (isImportModalOpen || deleteConfirmParams !== null) return;

      const activeElement = document.activeElement;
      const isInputFocused = activeElement && (
        activeElement.tagName === 'INPUT' ||
        activeElement.tagName === 'TEXTAREA' ||
        activeElement.tagName === 'SELECT'
      );

      // If currently editing an item inline
      if (editingId) {
        if (e.key === 'Escape') {
          e.preventDefault();
          cancelEdit();
        } else if ((e.ctrlKey || e.metaKey) && (e.key === 'Enter' || e.key.toLowerCase() === 'a')) {
          // Tally shortcut: Ctrl + Enter or Ctrl + A to accept/save
          e.preventDefault();
          saveEdit(editingId);
        } else if (e.key === 'Enter' && isInputFocused && !e.shiftKey) {
          e.preventDefault();
          saveEdit(editingId);
        }
        return;
      }

      // If user is focused on the search bar or category edit
      if (isInputFocused) {
        if (e.key === 'Escape') {
          (activeElement as HTMLElement).blur();
        }
        return;
      }

      if (navigableRows.length === 0) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setFocusedRowIndex(prev => {
          const next = prev < navigableRows.length - 1 ? prev + 1 : 0;
          scrollToRow(next);
          return next;
        });
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setFocusedRowIndex(prev => {
          const next = prev > 0 ? prev - 1 : navigableRows.length - 1;
          scrollToRow(next);
          return next;
        });
      } else if (e.key === 'Home') {
        e.preventDefault();
        setFocusedRowIndex(0);
        scrollToRow(0);
      } else if (e.key === 'End') {
        e.preventDefault();
        setFocusedRowIndex(navigableRows.length - 1);
        scrollToRow(navigableRows.length - 1);
      } else if (e.key === 'PageDown') {
        e.preventDefault();
        setFocusedRowIndex(prev => {
          const next = Math.min(navigableRows.length - 1, Math.max(0, prev) + 10);
          scrollToRow(next);
          return next;
        });
      } else if (e.key === 'PageUp') {
        e.preventDefault();
        setFocusedRowIndex(prev => {
          const next = Math.max(0, prev - 10);
          scrollToRow(next);
          return next;
        });
      } else if (e.key === 'Enter' || ((e.ctrlKey || e.metaKey) && e.key === 'Enter')) {
        // TALLY SHORTCUT: Ctrl + Enter or Enter to alter/edit the selected item!
        if (focusedRowIndex >= 0 && focusedRowIndex < navigableRows.length) {
          e.preventDefault();
          const target = navigableRows[focusedRowIndex];
          if (target) {
            startEdit(target.product);
          }
        }
      } else if ((e.altKey && e.key.toLowerCase() === "d") || e.key === "Delete") {
        if (focusedRowIndex >= 0 && focusedRowIndex < navigableRows.length) {
          e.preventDefault();
          const target = navigableRows[focusedRowIndex];
          if (target) {
            deleteProduct(target.product.id, target.product.name);
          }
        }
      } else if (e.key === 'Escape') {
        setFocusedRowIndex(-1);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [navigableRows, focusedRowIndex, editingId, editData, isImportModalOpen]);

  return (
    <DashboardLayout>
      <div className="space-y-6 pb-16">
        
        {/* Header Bar */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-border/60 pb-5">
          <div className="flex items-start gap-3 min-w-0">
            <Link 
              href="/inventory" 
              className="p-2 rounded-xl bg-muted/40 hover:bg-muted/80 text-muted-foreground hover:text-foreground transition-colors border border-border/50 shrink-0 mt-0.5"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
            </Link>

            <div className="min-w-0 flex-1">
              {/* Category Title */}
              {isCategoryEditing ? (
                <input
                  type="text"
                  value={categoryEditData.name}
                  onChange={e => setCategoryEditData({ ...categoryEditData, name: e.target.value })}
                  className="text-xl sm:text-2xl font-bold bg-muted/40 border border-border px-3 py-1 rounded-lg text-foreground focus:ring-2 focus:ring-blue-500 outline-none w-full max-w-md"
                />
              ) : (
                <h1 className="text-xl sm:text-2xl font-black tracking-tight text-foreground flex items-center gap-2">
                  <span className="truncate">{category?.name || 'Loading Category...'}</span>
                  <button onClick={startCategoryEdit} className="text-muted-foreground hover:text-blue-400 p-1 shrink-0" title="Edit Category Name">
                    <Edit2 className="w-4 h-4" />
                  </button>
                </h1>
              )}

              {/* Category Meta Badges */}
              <div className="flex items-center gap-2 mt-2 flex-wrap text-xs">
                <span className="font-mono bg-blue-500/10 text-blue-400 border border-blue-500/20 px-2 py-0.5 rounded-md font-semibold">
                  {products.length} {products.length === 1 ? 'item' : 'items'}
                </span>

                <span className="font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2.5 py-0.5 rounded-md font-semibold flex items-center gap-1.5">
                  <Boxes className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                  <span>Stock Value: ₹{categoryStockValue.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                  {categoryStockQty > 0 && (
                    <span className="text-emerald-400/70 font-normal">({categoryStockQty.toLocaleString('en-IN')} units)</span>
                  )}
                </span>

                <span className="font-mono bg-muted/40 px-2 py-0.5 rounded border border-border/50 text-muted-foreground">
                  HSN: {category?.hsn_code || 'None'}
                </span>
                <span className="font-mono bg-muted/40 px-2 py-0.5 rounded border border-border/50 text-muted-foreground">
                  GST: {category?.gst_rate || 0}%
                </span>
              </div>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2 sm:gap-2.5 w-full lg:w-auto">
            {isCategoryEditing ? (
              <div className="flex items-center gap-2 w-full lg:w-auto">
                <button onClick={() => setIsCategoryEditing(false)} className="flex-1 lg:flex-none text-muted-foreground hover:text-foreground px-4 py-2 text-xs font-bold bg-muted/40 rounded-xl">
                  Cancel
                </button>
                <button 
                  onClick={saveCategoryEdit} 
                  disabled={savingCategory} 
                  className="flex-1 lg:flex-none bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-xl text-xs font-bold shadow transition-all"
                >
                  {savingCategory ? 'Saving...' : 'Save Category'}
                </button>
              </div>
            ) : (
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 w-full lg:w-auto">
                <div className="grid grid-cols-2 sm:grid-cols-4 md:flex gap-2 w-full sm:w-auto">
                  {/* Bulk Discount Trigger */}
                  <button
                    onClick={() => setIsBulkDiscountModalOpen(true)}
                    className="justify-center bg-muted/60 hover:bg-muted text-foreground border border-border/80 px-2.5 sm:px-3 py-2 rounded-xl text-xs font-bold shadow-xs transition-all flex items-center gap-1.5 cursor-pointer"
                  >
                    <Percent className="w-3.5 h-3.5 text-blue-400" />
                    <span>Brand Disc.</span>
                  </button>
                  
                  {/* Import Price List Trigger */}
                  <button
                    onClick={() => setIsImportModalOpen(true)}
                    className="justify-center bg-muted/60 hover:bg-muted text-foreground border border-border/80 px-2.5 sm:px-3 py-2 rounded-xl text-xs font-bold shadow-xs transition-all flex items-center gap-1.5 cursor-pointer"
                  >
                    <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Import List</span>
                  </button>

                  {/* Combine Duplicates Trigger */}
                  <button
                    onClick={() => setIsMergeModalOpen(true)}
                    disabled={isMerging}
                    className="justify-center bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30 px-2.5 sm:px-3 py-2 rounded-xl text-xs font-bold shadow-xs transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                    title="Clean and combine duplicate sizes (e.g. A-31 and A 31 -> A 31, B92 -> B 92) and preserve invoice tags"
                  >
                    <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                    <span>{isMerging ? 'Combining...' : 'Combine'}</span>
                  </button>

                  {/* Top Items & Analytics Trigger */}
                  <button
                    onClick={() => {
                      const next = !analyticsOpen;
                      setAnalyticsOpen(next);
                      if (next && !topAnalytics) fetchAnalytics();
                    }}
                    className={`justify-center px-2.5 sm:px-3 py-2 rounded-xl text-xs font-bold shadow-xs transition-all flex items-center gap-1.5 cursor-pointer border ${
                      analyticsOpen
                        ? "bg-blue-500/20 text-blue-400 border-blue-500/40 shadow-xs"
                        : "bg-muted/60 hover:bg-muted text-foreground border-border/80"
                    }`}
                    title="View top sold and purchased items & movement analytics"
                  >
                    <BarChart2 className="w-3.5 h-3.5 text-blue-400" />
                    <span>Analytics</span>
                  </button>
                </div>

                {/* Add Item Trigger */}
                <Link 
                  href={`/inventory/categories/${categoryId}/new-item`} 
                  className="justify-center bg-primary hover:bg-primary/90 text-primary-foreground px-4 py-2 rounded-xl text-xs font-bold shadow transition-all flex items-center gap-1.5 w-full sm:w-auto"
                >
                  <Plus className="w-4 h-4" />
                  <span>Add Item</span>
                </Link>
              </div>
            )}
          </div>
        </div>

        {/* Content Section */}
        {products.length === 0 ? (
          <div className="flex flex-col items-center justify-center text-center p-16 bg-card rounded-2xl border border-border/70 shadow-sm">
            <div className="w-16 h-16 rounded-2xl bg-blue-500/10 text-blue-400 flex items-center justify-center mb-4">
              <Layers className="w-8 h-8" />
            </div>
            <h3 className="text-xl font-bold mb-1">No Items in {category?.name}</h3>
            <p className="text-sm text-muted-foreground max-w-md mx-auto mb-6">
              Create individual items manually or import a distributor price list (CSV, Excel, PDF) to populate items and MRPs in bulk.
            </p>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setIsImportModalOpen(true)}
                className="bg-muted/80 hover:bg-muted text-foreground border border-border px-4 py-2 rounded-xl text-xs font-bold shadow-xs transition-all flex items-center gap-1.5 cursor-pointer"
              >
                <FileSpreadsheet className="w-4 h-4 text-emerald-400" />
                <span>Import Price List</span>
              </button>
              <Link 
                href={`/inventory/categories/${categoryId}/new-item`} 
                className="bg-primary hover:bg-primary/90 text-primary-foreground px-4 py-2 rounded-xl text-xs font-bold shadow transition-all flex items-center gap-1.5"
              >
                <Plus className="w-4 h-4" />
                <span>Add First Item</span>
              </Link>
            </div>
          </div>
        ) : (
          <div className="bg-card border border-border/80 rounded-2xl shadow-sm overflow-hidden space-y-0">
            
            {/* Filter & Sort Controls Toolbar */}
            <div className="p-3 sm:p-4 border-b border-border/60 bg-muted/15 flex flex-col md:flex-row md:items-center justify-between gap-3">
              
              {/* Search Bar */}
              <div className="relative w-full md:max-w-xs">
                <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-2.5" />
                <input
                  type="text"
                  placeholder="Search item, size, brand, SKU..."
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  className="bg-muted/30 border border-border/70 text-foreground pl-9 pr-3.5 py-1.5 rounded-xl outline-none focus:ring-2 focus:ring-blue-500/50 w-full text-xs transition-all"
                />
              </div>

              {/* Sort By Dropdown & Count */}
              <div className="flex items-center justify-between md:justify-end gap-2.5 w-full md:w-auto">
                <div className="flex items-center gap-1.5 sm:gap-2">
                  <ArrowUpDown className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                  <span className="text-xs text-muted-foreground whitespace-nowrap font-medium hidden sm:inline">Sort by:</span>
                  <select
                    value={sortBy}
                    onChange={(e) => setSortBy(e.target.value as SortOption)}
                    className="bg-zinc-900 border border-zinc-700 text-white text-xs font-medium rounded-xl px-2.5 py-1.5 outline-none focus:ring-2 focus:ring-blue-500/50 cursor-pointer"
                  >
                    <option value="NAME_ASC" className="bg-zinc-900 text-white py-1">Name (A → Z)</option>
                    <option value="NAME_DESC" className="bg-zinc-900 text-white py-1">Name (Z → A)</option>
                    <option value="MRP_DESC" className="bg-zinc-900 text-white py-1">MRP: High → Low</option>
                    <option value="MRP_ASC" className="bg-zinc-900 text-white py-1">MRP: Low → High</option>
                    <option value="PURCHASE_DESC" className="bg-zinc-900 text-white py-1">Purchase Price: High → Low</option>
                    <option value="PURCHASE_ASC" className="bg-zinc-900 text-white py-1">Purchase Price: Low → High</option>
                    <option value="STOCK_DESC" className="bg-zinc-900 text-white py-1">Stock: High → Low</option>
                    <option value="STOCK_ASC" className="bg-zinc-900 text-white py-1">Stock: Low → High</option>
                  </select>
                </div>

                <div className="text-[11px] sm:text-xs text-muted-foreground whitespace-nowrap font-mono bg-muted/40 px-2 sm:px-2.5 py-1.5 rounded-lg border border-border/40">
                  {groupedItemBlocks.length} items ({filteredProducts.length} var)
                </div>
              </div>
            </div>

            {/* Collapsible Top Items & Movement Analytics Panel */}
            {analyticsOpen && (
              <div className="p-4 sm:p-5 border-b border-border/60 bg-muted/10 space-y-4 animate-in fade-in slide-in-from-top-2 duration-200">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <BarChart2 className="w-4 h-4 text-blue-400" />
                    <h4 className="text-xs font-bold uppercase tracking-wider text-foreground">
                      Item Velocity & Most Frequent Items ({category?.name || "Category"})
                    </h4>
                  </div>
                  <button
                    onClick={() => fetchAnalytics()}
                    disabled={loadingAnalytics}
                    className="p-1 text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                    title="Refresh Analytics"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${loadingAnalytics ? 'animate-spin text-blue-400' : ''}`} />
                  </button>
                </div>

                {loadingAnalytics ? (
                  <div className="py-8 text-center text-xs text-muted-foreground">
                    Analyzing sales and purchase transactions...
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Top Sold Items */}
                    <div className="bg-muted/20 border border-border/60 rounded-xl p-3.5 space-y-2.5">
                      <div className="flex items-center justify-between border-b border-border/40 pb-2">
                        <span className="text-[11px] font-bold text-foreground flex items-center gap-1.5">
                          <span className="w-2 h-2 rounded-full bg-blue-400"></span>
                          Most Frequent Items Sold
                        </span>
                        <span className="text-[10px] text-muted-foreground font-mono">By Invoice Count</span>
                      </div>

                      {(!topAnalytics?.top_sold || topAnalytics.top_sold.length === 0) ? (
                        <div className="py-4 text-center text-xs text-muted-foreground">
                          No sales recorded for this category yet.
                        </div>
                      ) : (
                        <div className="space-y-1.5">
                          {topAnalytics.top_sold.map((it: any, idx: number) => (
                            <div
                              key={idx}
                              onClick={() => {
                                const prod = products.find(p => p.id === it.product_id) || it;
                                setSelectedHistoryItem(prod);
                              }}
                              className="flex items-center justify-between p-2 rounded-lg bg-card/60 hover:bg-muted/40 border border-border/30 text-xs transition-colors cursor-pointer group"
                            >
                              <div className="flex items-center gap-2 min-w-0">
                                <span className="font-mono text-[10px] text-muted-foreground w-4">#{idx + 1}</span>
                                <div className="truncate">
                                  <div className="font-semibold text-foreground group-hover:text-blue-400 transition-colors truncate">
                                    {it.name}
                                  </div>
                                  <div className="text-[10px] text-muted-foreground font-mono">
                                    {it.brand || "Unbranded"} • Stock: {it.current_stock} {it.unit}
                                  </div>
                                </div>
                              </div>
                              <div className="text-right font-mono shrink-0 ml-2">
                                <div className="font-bold text-blue-400">
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

                    {/* Top Purchased Items */}
                    <div className="bg-muted/20 border border-border/60 rounded-xl p-3.5 space-y-2.5">
                      <div className="flex items-center justify-between border-b border-border/40 pb-2">
                        <span className="text-[11px] font-bold text-foreground flex items-center gap-1.5">
                          <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                          Most Frequent Items Purchased
                        </span>
                        <span className="text-[10px] text-muted-foreground font-mono">By Bill Count</span>
                      </div>

                      {(!topAnalytics?.top_purchased || topAnalytics.top_purchased.length === 0) ? (
                        <div className="py-4 text-center text-xs text-muted-foreground">
                          No purchases recorded for this category yet.
                        </div>
                      ) : (
                        <div className="space-y-1.5">
                          {topAnalytics.top_purchased.map((it: any, idx: number) => (
                            <div
                              key={idx}
                              onClick={() => {
                                const prod = products.find(p => p.id === it.product_id) || it;
                                setSelectedHistoryItem(prod);
                              }}
                              className="flex items-center justify-between p-2 rounded-lg bg-card/60 hover:bg-muted/40 border border-border/30 text-xs transition-colors cursor-pointer group"
                            >
                              <div className="flex items-center gap-2 min-w-0">
                                <span className="font-mono text-[10px] text-muted-foreground w-4">#{idx + 1}</span>
                                <div className="truncate">
                                  <div className="font-semibold text-foreground group-hover:text-emerald-400 transition-colors truncate">
                                    {it.name}
                                  </div>
                                  <div className="text-[10px] text-muted-foreground font-mono">
                                    {it.brand || "Unbranded"} • Stock: {it.current_stock} {it.unit}
                                  </div>
                                </div>
                              </div>
                              <div className="text-right font-mono shrink-0 ml-2">
                                <div className="font-bold text-emerald-400">
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
                )}
              </div>
            )}

            {/* Brand Filter Pill Bar */}
            {existingBrandList.length > 0 && (
              <div className="px-3 sm:px-4 py-2 border-b border-border/40 bg-muted/10 flex items-center gap-1.5 sm:gap-2 overflow-x-auto no-scrollbar">
                <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider shrink-0 flex items-center gap-1">
                  <Tag className="w-3 h-3" />
                  Brands:
                </span>

                <button
                  type="button"
                  onClick={clearBrandFilter}
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all shrink-0 cursor-pointer ${
                    selectedBrands.length === 0
                      ? "bg-primary text-primary-foreground font-bold shadow-xs"
                      : "bg-muted/40 text-muted-foreground hover:text-foreground border border-border/50"
                  }`}
                >
                  All Brands ({products.length})
                </button>

                {existingBrandList.map((b) => {
                  const count = availableBrands[b] || 0;
                  const isSelected = selectedBrands.includes(b);
                  return (
                    <button
                      key={b}
                      type="button"
                      onClick={() => toggleBrand(b)}
                      className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all shrink-0 flex items-center gap-1.5 cursor-pointer border ${
                        isSelected
                          ? "bg-blue-600 text-white border-blue-500 font-bold shadow-xs"
                          : "bg-muted/40 text-muted-foreground hover:text-foreground border-border/50"
                      }`}
                    >
                      <span>{b}</span>
                      <span className={`text-[10px] font-mono px-1 rounded ${isSelected ? 'bg-blue-800 text-blue-100' : 'bg-muted text-muted-foreground'}`}>
                        {count}
                      </span>
                    </button>
                  );
                })}

                {selectedBrands.length > 0 && (
                  <button
                    type="button"
                    onClick={clearBrandFilter}
                    className="text-[11px] text-muted-foreground hover:text-rose-400 ml-1 underline cursor-pointer shrink-0"
                  >
                    Reset
                  </button>
                )}
              </div>
            )}

            {/* Mobile Product Cards (visible on < md) */}
            <div className="block md:hidden divide-y divide-border/60">
              {groupedItemBlocks.map((block) => {
                const isMultiBrand = block.variants.length > 1;

                return (
                  <div key={block.baseName} className="p-3.5 space-y-2.5 bg-card">
                    {/* Item Name Header */}
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="font-bold text-foreground text-sm">{block.baseName}</span>
                          {isMultiBrand && (
                            <span className="text-[10px] bg-blue-500/10 text-blue-400 border border-blue-500/20 px-1.5 py-0.2 rounded font-semibold whitespace-nowrap">
                              {block.variants.length} Brands
                            </span>
                          )}
                        </div>
                        {block.alias && <p className="text-[11px] text-muted-foreground">{block.alias}</p>}
                      </div>
                    </div>

                    {/* Variant Cards */}
                    <div className="space-y-2">
                      {block.variants.map((v) => {
                        const isEditing = editingId === v.id;

                        if (isEditing) {
                          return (
                            <div key={v.id} className="p-3 rounded-xl bg-blue-500/5 border border-blue-500/30 space-y-3 animate-in fade-in">
                              <div className="flex items-center justify-between border-b border-border/40 pb-2">
                                <span className="text-xs font-bold text-blue-400">Edit Item Details</span>
                                <div className="flex items-center gap-1.5">
                                  <button
                                    onClick={() => saveEdit(v.id)}
                                    disabled={savingId === v.id}
                                    className="px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold flex items-center gap-1"
                                  >
                                    <Check className="w-3.5 h-3.5" />
                                    <span>{savingId === v.id ? 'Saving...' : 'Save'}</span>
                                  </button>
                                  <button
                                    onClick={cancelEdit}
                                    className="px-2 py-1 rounded-lg bg-muted text-muted-foreground hover:text-foreground text-xs"
                                  >
                                    <X className="w-3.5 h-3.5" />
                                  </button>
                                </div>
                              </div>

                              <div className="grid grid-cols-2 gap-2 text-xs">
                                <div>
                                  <label className="text-[10px] uppercase font-semibold text-muted-foreground block mb-0.5">Brand</label>
                                  <input
                                    type="text"
                                    value={editData.brand}
                                    onChange={e => setEditData({ ...editData, brand: e.target.value })}
                                    className="bg-muted/40 border border-border text-foreground px-2 py-1.5 rounded-lg w-full text-xs outline-none focus:ring-1 focus:ring-blue-500"
                                  />
                                </div>
                                <div>
                                  <label className="text-[10px] uppercase font-semibold text-muted-foreground block mb-0.5">Stock Qty ({v.unit})</label>
                                  <input
                                    type="number"
                                    step={isIntegerUnit(v.unit) ? "1" : "0.01"}
                                    min="0"
                                    value={
                                      isIntegerUnit(v.unit)
                                        ? Math.round(parseFloat(editData.stock_quantity !== undefined ? editData.stock_quantity : v.stock_quantity) || 0)
                                        : (editData.stock_quantity !== undefined ? editData.stock_quantity : v.stock_quantity)
                                    }
                                    onChange={e => {
                                      const val = parseFloat(e.target.value) || 0;
                                      setEditData({ ...editData, stock_quantity: isIntegerUnit(v.unit) ? Math.round(val) : val });
                                    }}
                                    className="bg-muted/40 border border-border text-emerald-400 font-mono font-bold px-2 py-1.5 rounded-lg w-full text-xs outline-none focus:ring-1 focus:ring-blue-500"
                                  />
                                </div>
                              </div>

                              <div className="grid grid-cols-3 gap-2 text-xs">
                                <div>
                                  <label className="text-[10px] uppercase font-semibold text-muted-foreground block mb-0.5">MRP (₹)</label>
                                  <input
                                    type="number"
                                    step="0.01"
                                    value={editData.selling_price}
                                    onChange={e => {
                                      const sp = parseFloat(e.target.value) || 0;
                                      const d = parseFloat(editData.discount_percent) || 0;
                                      const pp = sp * (1 - d/100);
                                      setEditData({ ...editData, selling_price: sp, purchase_price: parseFloat(pp.toFixed(2)) });
                                    }}
                                    className="bg-muted/40 border border-border text-emerald-400 font-mono font-bold px-2 py-1.5 rounded-lg w-full text-xs outline-none focus:ring-1 focus:ring-blue-500"
                                  />
                                </div>
                                <div>
                                  <label className="text-[10px] uppercase font-semibold text-muted-foreground block mb-0.5">Disc %</label>
                                  <input
                                    type="number"
                                    step="0.01"
                                    value={editData.discount_percent}
                                    onChange={e => {
                                      const d = parseFloat(e.target.value) || 0;
                                      const p = (editData.selling_price * (1 - d/100)).toFixed(2);
                                      setEditData({ ...editData, discount_percent: e.target.value, purchase_price: parseFloat(p) });
                                    }}
                                    className="bg-muted/40 border border-border text-blue-400 font-mono font-bold px-2 py-1.5 rounded-lg w-full text-xs outline-none focus:ring-1 focus:ring-blue-500"
                                  />
                                </div>
                                <div>
                                  <label className="text-[10px] uppercase font-semibold text-muted-foreground block mb-0.5">Cost (₹)</label>
                                  <input
                                    type="number"
                                    step="0.01"
                                    value={editData.purchase_price}
                                    onChange={e => {
                                      const p = parseFloat(e.target.value) || 0;
                                      const sp = editData.selling_price || 1;
                                      const d = sp > 0 ? ((sp - p) / sp * 100).toFixed(2) : 0;
                                      setEditData({ ...editData, purchase_price: p, discount_percent: d });
                                    }}
                                    className="bg-muted/40 border border-border text-foreground font-mono px-2 py-1.5 rounded-lg w-full text-xs outline-none focus:ring-1 focus:ring-blue-500"
                                  />
                                </div>
                              </div>
                            </div>
                          );
                        }

                        return (
                          <div 
                            key={v.id} 
                            className="p-2.5 rounded-xl border border-border/50 bg-muted/10 hover:bg-muted/20 transition-colors space-y-2"
                          >
                            {/* Brand, SKU & Actions Line */}
                            <div className="flex items-center justify-between gap-2">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                {v.brand ? (
                                  <span className="bg-zinc-800 text-blue-400 border border-blue-500/20 text-[11px] px-2 py-0.5 rounded font-bold font-mono">
                                    {v.brand}
                                  </span>
                                ) : (
                                  <span className="bg-zinc-800/80 text-zinc-400 border border-zinc-700/80 text-[11px] px-2 py-0.5 rounded font-medium">
                                    Unbranded
                                  </span>
                                )}
                                {v.sku && (
                                  <span className="text-[10px] font-mono text-muted-foreground">
                                    {v.sku}
                                  </span>
                                )}
                                {(v.purchase_price_from_invoice || v.has_invoice_stock) && (
                                  <button
                                    onClick={() => setSelectedHistoryItem(v)}
                                    className="text-[9px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-1.5 py-0.5 rounded font-mono font-bold flex items-center gap-1 hover:bg-emerald-500/25 transition-colors cursor-pointer"
                                    title="Purchased via bill - click to inspect invoice history"
                                  >
                                    <FileText className="w-2.5 h-2.5" />
                                    Invoice
                                  </button>
                                )}
                              </div>

                              <div className="flex items-center gap-1 shrink-0">
                                <button
                                  onClick={() => setSelectedHistoryItem(v)}
                                  className="p-1.5 text-muted-foreground hover:text-emerald-400 rounded-lg hover:bg-muted/60 transition-colors"
                                  title="View Bill History & Analytics"
                                >
                                  <History className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={() => startEdit(v)}
                                  className="p-1.5 text-muted-foreground hover:text-blue-400 rounded-lg hover:bg-muted/60 transition-colors"
                                  title="Edit item"
                                >
                                  <Edit2 className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={() => deleteProduct(v.id, v.name)}
                                  className="p-1.5 text-muted-foreground hover:text-rose-400 rounded-lg hover:bg-muted/60 transition-colors"
                                  title="Delete item"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            </div>

                            {/* 3-Column Financial & Stock Metrics Grid */}
                            <div className="grid grid-cols-3 gap-2 pt-1 border-t border-border/30">
                              <div className="bg-muted/20 rounded-lg p-1.5 text-center">
                                <div className="text-[9px] uppercase font-semibold text-muted-foreground">MRP</div>
                                <div className="text-xs font-bold text-emerald-400 font-mono">
                                  ₹{parseFloat(v.selling_price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                                </div>
                              </div>
                              <div className="bg-muted/20 rounded-lg p-1.5 text-center">
                                <div className="text-[9px] uppercase font-semibold text-muted-foreground">Purchase</div>
                                <div className="text-xs font-mono text-muted-foreground font-medium">
                                  {parseFloat(v.purchase_price) > 0 ? `₹${parseFloat(v.purchase_price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : '—'}
                                </div>
                              </div>
                              <div className="bg-muted/20 rounded-lg p-1.5 text-center">
                                <div className="text-[9px] uppercase font-semibold text-muted-foreground">Stock</div>
                                <div className={`text-xs font-mono font-bold ${parseFloat(v.stock_quantity) > 0 ? 'text-emerald-400' : 'text-muted-foreground'}`}>
                                  {formatStockQuantity(v.stock_quantity, v.unit)} <span className="text-[10px] font-normal text-muted-foreground">{v.unit}</span>
                                </div>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Multi-Brand Unified Items Table (Desktop) */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead className="bg-muted/40 text-muted-foreground text-[11px] uppercase tracking-wider font-semibold border-b border-border/70">
                  <tr>
                    <th className="p-3.5 w-60">Item Name / Size</th>
                    <th className="p-3.5 w-32">Brand</th>
                    <th className="p-3.5">SKU / Tags</th>
                    <th className="p-3.5 text-right w-36">MRP / List Price</th>
                    <th className="p-3.5 text-right w-36">
                      <div className="flex items-center justify-end gap-1">
                        <span>Purchase Price</span>
                        <span title="Updated automatically via Purchase Invoices">
                          <Info className="w-3 h-3 text-muted-foreground" />
                        </span>
                      </div>
                    </th>
                    <th className="p-3.5 text-right w-28">Stock</th>
                    <th className="p-3.5 text-center w-24">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {groupedItemBlocks.map((block) => {
                    const isMultiBrand = block.variants.length > 1;

                    return block.variants.map((v, vIndex) => {
                      const isFirst = vIndex === 0;
                      const isEditing = editingId === v.id;
                      const isFocused = focusedRowIndex >= 0 && navigableRows[focusedRowIndex]?.productId === v.id;

                      return (
                        <tr
                          id={`row-product-${v.id}`}
                          key={v.id}
                          onClick={() => setFocusedRowIndex(navigableRows.findIndex(r => r.productId === v.id))}
                          className={`transition-all duration-150 cursor-pointer ${
                            isEditing 
                              ? 'bg-blue-500/10 border-l-4 border-l-blue-500' 
                              : isFocused 
                              ? 'bg-blue-500/10 ring-2 ring-inset ring-blue-500/60 border-l-4 border-l-blue-500' 
                              : 'hover:bg-muted/20'
                          } ${isMultiBrand && !isFirst ? 'border-t-0' : 'border-t border-border/40'}`}
                        >
                          {/* Item Name / Size */}
                          {isFirst && (
                            <td 
                              rowSpan={isMultiBrand ? block.variants.length : 1} 
                              className={`p-3.5 align-top ${isMultiBrand ? 'border-r border-border/40 bg-muted/5' : ''}`}
                            >
                              {isEditing && !isMultiBrand ? (
                                <div className="space-y-1">
                                  <input
                                    type="text"
                                    value={editData.name}
                                    onChange={e => setEditData({ ...editData, name: e.target.value })}
                                    className="bg-muted/40 border border-border text-foreground px-2 py-1 rounded w-full text-xs font-semibold outline-none focus:ring-1 focus:ring-blue-500"
                                  />
                                  <input
                                    type="text"
                                    placeholder="Alias"
                                    value={editData.alias}
                                    onChange={e => setEditData({ ...editData, alias: e.target.value })}
                                    className="bg-muted/40 border border-border text-muted-foreground px-2 py-0.5 rounded w-full text-[11px] outline-none"
                                  />
                                </div>
                              ) : (
                                <div className="space-y-1">
                                  <div className="flex items-center gap-2 flex-wrap">
                                    <span className="text-foreground font-extrabold text-sm">{block.baseName}</span>
                                    {isMultiBrand && (
                                      <span className="text-[10px] bg-blue-500/10 text-blue-400 border border-blue-500/20 px-1.5 py-0.2 rounded font-semibold whitespace-nowrap">
                                        {block.variants.length} Brands
                                      </span>
                                    )}
                                  </div>
                                  {block.alias && <p className="text-muted-foreground text-xs">{block.alias}</p>}
                                  {isMultiBrand && (
                                    <p className="text-[11px] text-muted-foreground">
                                      {block.variants.map(varItem => varItem.brand).filter(Boolean).join(', ')}
                                    </p>
                                  )}
                                </div>
                              )}
                            </td>
                          )}

                          {/* Brand */}
                          <td className="p-3.5 align-middle">
                            {isEditing ? (
                              <input
                                type="text"
                                value={editData.brand}
                                onChange={e => setEditData({ ...editData, brand: e.target.value })}
                                placeholder="Brand"
                                className="bg-muted/40 border border-border text-foreground px-2 py-1 rounded w-full text-xs outline-none"
                              />
                            ) : v.brand ? (
                              <span className="bg-zinc-800 text-blue-400 border border-blue-500/20 text-xs px-2 py-0.5 rounded font-bold font-mono">
                                {v.brand}
                              </span>
                            ) : (
                              <span className="bg-zinc-800/80 text-zinc-300 border border-zinc-700/80 text-xs px-2 py-0.5 rounded-md font-medium">
                                Unbranded
                              </span>
                            )}
                          </td>

                          {/* SKU & Tags */}
                          <td className="p-3.5 align-middle">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              {v.sku && <p className="text-muted-foreground font-mono text-xs">{v.sku}</p>}
                              {(v.purchase_price_from_invoice || v.has_invoice_stock) && (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setSelectedHistoryItem(v);
                                  }}
                                  className="text-[9px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-1.5 py-0.5 rounded font-mono font-bold flex items-center gap-1 cursor-pointer hover:bg-emerald-500/25 transition-colors"
                                  title="Purchased via bill - click to inspect invoice history"
                                >
                                  <FileText className="w-2.5 h-2.5" />
                                  Invoice
                                </button>
                              )}
                            </div>
                            <div className="flex gap-1 mt-1 flex-wrap">
                              {v.tax_override && <span className="bg-red-500/10 text-red-400 text-[9px] px-1.5 py-0.5 rounded border border-red-500/20">Tax Override</span>}
                              {v.track_batches && <span className="bg-green-500/10 text-green-400 text-[9px] px-1.5 py-0.5 rounded border border-green-500/20">Batches</span>}
                              {v.track_serial_numbers && <span className="bg-purple-500/10 text-purple-400 text-[9px] px-1.5 py-0.5 rounded border border-purple-500/20">Serial</span>}
                            </div>
                          </td>

                          {/* Retail Price / MRP */}
                          <td className="p-3.5 text-right align-middle font-mono">
                            {isEditing ? (
                              <input
                                type="number"
                                step="0.01"
                                value={editData.selling_price}
                                onChange={e => {
                                  const sp = parseFloat(e.target.value) || 0;
                                  const d = parseFloat(editData.discount_percent) || 0;
                                  const pp = sp * (1 - d/100);
                                  setEditData({ ...editData, selling_price: sp, purchase_price: parseFloat(pp.toFixed(2)) });
                                }}
                                className="bg-muted/40 border border-border text-emerald-400 px-2 py-1 rounded w-24 text-xs text-right font-mono font-bold outline-none"
                              />
                            ) : (
                              <span className="text-emerald-400 font-bold text-sm">
                                ₹{parseFloat(v.selling_price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                              </span>
                            )}
                          </td>

                          {/* Purchase Price */}
                          <td className="p-3.5 text-right align-middle">
                            {isEditing ? (
                              <div className="flex items-center justify-end gap-1.5">
                                <div className="flex items-center gap-1 bg-muted/30 px-1 py-0.5 rounded border border-border/40">
                                  <span className="text-[9px] text-muted-foreground font-semibold">DISC%</span>
                                  <input
                                    type="number"
                                    step="0.01"
                                    value={editData.discount_percent}
                                    onChange={e => {
                                      const d = parseFloat(e.target.value) || 0;
                                      const p = (editData.selling_price * (1 - d/100)).toFixed(2);
                                      setEditData({ ...editData, discount_percent: e.target.value, purchase_price: parseFloat(p) });
                                    }}
                                    className="bg-transparent text-blue-400 w-14 text-xs text-right font-mono font-bold outline-none"
                                  />
                                </div>
                                <input
                                  type="number"
                                  step="0.01"
                                  value={editData.purchase_price}
                                  onChange={e => {
                                    const p = parseFloat(e.target.value) || 0;
                                    const sp = editData.selling_price || 1;
                                    const d = sp > 0 ? ((sp - p) / sp * 100).toFixed(2) : 0;
                                    setEditData({ ...editData, purchase_price: p, discount_percent: d });
                                  }}
                                  className="bg-muted/40 border border-border text-foreground px-2 py-1 rounded w-20 text-xs text-right font-mono outline-none"
                                />
                              </div>
                            ) : (
                              <div className="flex items-center justify-end gap-1.5 font-mono">
                                <span className="text-muted-foreground font-medium text-xs">
                                  {parseFloat(v.purchase_price) > 0 ? `₹${parseFloat(v.purchase_price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : '—'}
                                </span>
                                {(v.purchase_price_from_invoice || v.has_invoice_stock) && (
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setSelectedHistoryItem(v);
                                    }}
                                    title="Purchase price set from Purchase Invoice - click to inspect bills"
                                    className="text-[10px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-1.5 py-0.5 rounded font-mono font-bold hover:bg-emerald-500/25 transition-colors cursor-pointer"
                                  >
                                    Invoice
                                  </button>
                                )}
                              </div>
                            )}
                          </td>

                          {/* Stock */}
                          <td className="p-3.5 text-right align-middle font-mono">
                            {isEditing && !v.has_invoice_stock ? (
                              <div className="flex items-center justify-end gap-1">
                                <input
                                  type="number"
                                  step={isIntegerUnit(v.unit) ? "1" : "0.01"}
                                  min="0"
                                  value={
                                    isIntegerUnit(v.unit)
                                      ? Math.round(parseFloat(editData.stock_quantity !== undefined ? editData.stock_quantity : v.stock_quantity) || 0)
                                      : (editData.stock_quantity !== undefined ? editData.stock_quantity : v.stock_quantity)
                                  }
                                  onKeyDown={e => {
                                    if (isIntegerUnit(v.unit)) {
                                      if (e.key === 'ArrowUp') {
                                        e.preventDefault();
                                        const current = Math.round(parseFloat(editData.stock_quantity !== undefined ? editData.stock_quantity : v.stock_quantity) || 0);
                                        setEditData({ ...editData, stock_quantity: current + 1 });
                                      } else if (e.key === 'ArrowDown') {
                                        e.preventDefault();
                                        const current = Math.round(parseFloat(editData.stock_quantity !== undefined ? editData.stock_quantity : v.stock_quantity) || 0);
                                        setEditData({ ...editData, stock_quantity: Math.max(0, current - 1) });
                                      }
                                    }
                                  }}
                                  onChange={e => {
                                    const val = parseFloat(e.target.value) || 0;
                                    setEditData({ ...editData, stock_quantity: isIntegerUnit(v.unit) ? Math.round(val) : val });
                                  }}
                                  className="bg-muted/40 border border-border text-emerald-400 px-1.5 py-1 rounded text-xs text-right font-mono font-bold w-16 outline-none"
                                />
                                <span className="text-[10px] text-muted-foreground">{v.unit}</span>
                              </div>
                            ) : (
                              <>
                                <span className={`font-bold text-sm ${parseFloat(v.stock_quantity) > 0 ? 'text-emerald-400' : 'text-muted-foreground'}`}>
                                  {formatStockQuantity(v.stock_quantity, v.unit)}
                                </span>
                                <span className="text-[10px] text-muted-foreground ml-1">{v.unit}</span>
                              </>
                            )}
                          </td>

                          {/* Actions */}
                          <td className="p-3.5 text-center align-middle">
                            {isEditing ? (
                              <div className="flex items-center justify-center gap-1">
                                <button
                                  onClick={() => saveEdit(v.id)}
                                  disabled={savingId === v.id}
                                  className="p-1 rounded bg-emerald-600 text-white hover:bg-emerald-700"
                                  title="Save"
                                >
                                  <Check className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={cancelEdit}
                                  className="p-1 rounded bg-muted text-muted-foreground hover:text-foreground"
                                  title="Cancel"
                                >
                                  <X className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            ) : (
                              <div className="flex items-center justify-center gap-1">
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setSelectedHistoryItem(v);
                                  }}
                                  className="text-muted-foreground hover:text-emerald-400 p-1.5 rounded hover:bg-muted/60 transition-colors"
                                  title="View Bill History & Analytics"
                                >
                                  <History className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={() => startEdit(v)}
                                  className="text-muted-foreground hover:text-blue-400 p-1.5 rounded hover:bg-muted/60 transition-colors"
                                  title="Edit item"
                                >
                                  <Edit2 className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={() => deleteProduct(v.id, v.name)}
                                  className="text-muted-foreground hover:text-rose-400 p-1.5 rounded hover:bg-muted/60 transition-colors"
                                  title="Delete item (Alt+D)"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            )}
                          </td>
                        </tr>
                      );
                    });
                  })}
                </tbody>
              </table>
            </div>

            {/* Table Footer */}
            <div className="p-3.5 border-t border-border/60 bg-muted/20 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs text-muted-foreground">
              <div className="hidden sm:flex items-center gap-2 flex-wrap">
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">↑</kbd>
                  <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">↓</kbd>
                  <span className="text-[11px]">Navigate</span>
                </span>
                <span>•</span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">Ctrl</kbd>
                  <span>+</span>
                  <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">Enter</kbd>
                  <span className="text-[11px]">Edit (Tally Alter)</span>
                </span>
                <span>•</span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">Ctrl</kbd>
                  <span>+</span>
                  <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">A</kbd>
                  <span>/</span>
                  <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">Enter</kbd>
                  <span className="text-[11px]">Save</span>
                </span>
                <span>•</span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">Alt</kbd>
                  <span>+</span>
                  <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">D</kbd>
                  <span className="text-[11px]">Delete</span>
                </span>
                <span>•</span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/70 font-mono text-[10px] text-foreground font-bold">Esc</kbd>
                  <span className="text-[11px]">Cancel</span>
                </span>
              </div>
              <div className="flex items-center justify-between sm:justify-end gap-2 font-mono text-[11px] w-full sm:w-auto">
                {focusedRowIndex >= 0 ? (
                  <span className="text-blue-400 font-semibold bg-blue-500/10 px-2 py-0.5 rounded border border-blue-500/20">
                    Row {focusedRowIndex + 1} of {navigableRows.length}
                  </span>
                ) : (
                  <span>Showing {groupedItemBlocks.length} items ({filteredProducts.length} variants)</span>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Price List Import Modal */}
        <PriceListImportModal
          isOpen={isImportModalOpen}
          onClose={() => setIsImportModalOpen(false)}
          categoryId={categoryId}
          categoryName={category?.name || 'Category'}
          companyId={companyId}
          existingBrands={existingBrandList}
          onImportSuccess={fetchData}
        />

        {/* Bulk Brand Discount Modal */}
        <BulkBrandDiscountModal
          isOpen={isBulkDiscountModalOpen}
          onClose={() => setIsBulkDiscountModalOpen(false)}
          categoryId={categoryId}
          companyId={companyId}
          existingBrands={existingBrandList}
          onSuccess={fetchData}
        />

        <ConfirmModal
          isOpen={deleteConfirmParams !== null}
          onClose={() => setDeleteConfirmParams(null)}
          onConfirm={() => deleteConfirmParams && executeDelete(deleteConfirmParams.id)}
          title="Delete Item"
          description={
            <>
              Are you sure you want to delete <span className="text-white font-semibold">{deleteConfirmParams?.name}</span>? 
              This action cannot be undone.
            </>
          }
          confirmText="Delete"
          cancelText="Cancel"
          variant="danger"
        />

        {/* Combine Duplicates Confirmation Modal */}
        <ConfirmModal
          isOpen={isMergeModalOpen}
          onClose={() => setIsMergeModalOpen(false)}
          onConfirm={handleMergeDuplicates}
          title="Combine Duplicate Inventory Items?"
          description={
            <span>
              This will scan your inventory, combine all duplicate sizes with hyphens or spaces (e.g. <strong className="text-white">A-31</strong> & <strong className="text-white">A 31</strong> into <strong className="text-emerald-400">A 31</strong>, <strong className="text-white">B92</strong> into <strong className="text-emerald-400">B 92</strong>), sum their stock quantities, re-link all purchase & sales vouchers, and ensure the green <strong className="text-emerald-400">Invoice</strong> tag is preserved on items uploaded from invoices.
            </span>
          }
          confirmText={isMerging ? "Combining..." : "Combine & Clean Items"}
          cancelText="Cancel"
          variant="info"
        />

        {/* Item Invoice History & Analytics Modal */}
        <ItemHistoryModal
          isOpen={selectedHistoryItem !== null}
          onClose={() => setSelectedHistoryItem(null)}
          productId={selectedHistoryItem?.id || null}
          productName={selectedHistoryItem ? `${selectedHistoryItem.name}${selectedHistoryItem.brand ? ` (${selectedHistoryItem.brand})` : ''}` : ''}
          companyId={companyId}
        />
      </div>
    </DashboardLayout>
  );
}
