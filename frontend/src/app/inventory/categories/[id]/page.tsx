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
import ConfirmModal from '@/components/modals/ConfirmModal';
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
  Info
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
  
  // Sort and Brand Filter state
  const [sortBy, setSortBy] = useState<SortOption>('NAME_ASC');
  const [selectedBrands, setSelectedBrands] = useState<string[]>([]);
  
  // Modals state
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [deleteConfirmParams, setDeleteConfirmParams] = useState<{ id: string, name: string } | null>(null);

  // Edit state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editData, setEditData] = useState<any>({});
  const [savingId, setSavingId] = useState<string | null>(null);

  // Category Edit State
  const [isCategoryEditing, setIsCategoryEditing] = useState(false);
  const [categoryEditData, setCategoryEditData] = useState({ name: '', hsn_code: '', gst_rate: 18 });
  const [savingCategory, setSavingCategory] = useState(false);

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

  const startEdit = (p: any) => {
    setEditingId(p.id);
    setEditData({
      name: p.name,
      alias: p.alias || '',
      brand: p.brand || '',
      selling_price: p.selling_price,
      wholesaler_price: p.wholesaler_price,
      purchase_price: p.purchase_price,
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditData({});
  };

  const saveEdit = async (productId: string) => {
    setSavingId(productId);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.patch(
        `${API_BASE_URL}/api/v1/inventory/products/${companyId}/${productId}/`,
        editData,
        { headers }
      );
      if (res.data.success) {
        setProducts(prev => prev.map(p => p.id === productId ? { ...p, ...editData } : p));
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
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/60 pb-5">
          <div className="flex items-center gap-3">
            <Link 
              href="/inventory" 
              className="p-2 rounded-xl bg-muted/40 hover:bg-muted/80 text-muted-foreground hover:text-foreground transition-colors border border-border/50"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
            </Link>

            <div>
              <div className="flex items-center gap-3">
                {isCategoryEditing ? (
                  <input
                    type="text"
                    value={categoryEditData.name}
                    onChange={e => setCategoryEditData({ ...categoryEditData, name: e.target.value })}
                    className="text-2xl font-bold bg-muted/40 border border-border px-3 py-1 rounded-lg text-foreground focus:ring-2 focus:ring-blue-500 outline-none"
                  />
                ) : (
                  <h1 className="text-2xl font-black tracking-tight text-foreground flex items-center gap-2">
                    {category?.name || 'Loading Category...'}
                    <button onClick={startCategoryEdit} className="text-muted-foreground hover:text-blue-400 p-1">
                      <Edit2 className="w-4 h-4" />
                    </button>
                  </h1>
                )}

                <span className="text-xs font-mono bg-blue-500/10 text-blue-400 border border-blue-500/20 px-2 py-0.5 rounded-md font-semibold">
                  {products.length} {products.length === 1 ? 'item' : 'items'}
                </span>
              </div>

              {/* Category Meta Badges */}
              <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                <span className="font-mono bg-muted/40 px-2 py-0.5 rounded border border-border/50">
                  HSN: {category?.hsn_code || 'None'}
                </span>
                <span>•</span>
                <span className="font-mono bg-muted/40 px-2 py-0.5 rounded border border-border/50">
                  GST: {category?.gst_rate || 0}%
                </span>
              </div>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2.5 flex-wrap">
            {isCategoryEditing ? (
              <>
                <button onClick={() => setIsCategoryEditing(false)} className="text-muted-foreground hover:text-foreground px-4 py-2 text-xs font-bold">
                  Cancel
                </button>
                <button 
                  onClick={saveCategoryEdit} 
                  disabled={savingCategory} 
                  className="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-xl text-xs font-bold shadow transition-all"
                >
                  {savingCategory ? 'Saving...' : 'Save Category'}
                </button>
              </>
            ) : (
              <>
                {/* Import Price List Trigger */}
                <button
                  onClick={() => setIsImportModalOpen(true)}
                  className="bg-muted/60 hover:bg-muted text-foreground border border-border/80 px-3.5 py-2 rounded-xl text-xs font-bold shadow-xs transition-all flex items-center gap-2 cursor-pointer"
                >
                  <FileSpreadsheet className="w-4 h-4 text-emerald-400" />
                  <span>Import Price List</span>
                </button>

                {/* Add Item Trigger */}
                <Link 
                  href={`/inventory/categories/${categoryId}/new-item`} 
                  className="bg-primary hover:bg-primary/90 text-primary-foreground px-4 py-2 rounded-xl text-xs font-bold shadow transition-all flex items-center gap-1.5"
                >
                  <Plus className="w-4 h-4" />
                  <span>Add Item</span>
                </Link>
              </>
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
            <div className="p-4 border-b border-border/60 bg-muted/15 flex flex-col md:flex-row md:items-center justify-between gap-3.5">
              
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

              {/* Sort By Dropdown */}
              <div className="flex items-center gap-3 self-end md:self-auto">
                <div className="flex items-center gap-2">
                  <ArrowUpDown className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                  <span className="text-xs text-muted-foreground whitespace-nowrap font-medium">Sort by:</span>
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

                <div className="text-xs text-muted-foreground whitespace-nowrap font-mono bg-muted/40 px-2.5 py-1.5 rounded-lg border border-border/40">
                  {groupedItemBlocks.length} items ({filteredProducts.length} variants)
                </div>
              </div>
            </div>

            {/* Brand Filter Pill Bar */}
            {existingBrandList.length > 0 && (
              <div className="px-4 py-2.5 border-b border-border/40 bg-muted/10 flex items-center gap-2 overflow-x-auto">
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

            {/* Multi-Brand Unified Items Table */}
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead className="bg-muted/40 text-muted-foreground text-[11px] uppercase tracking-wider font-semibold border-b border-border/70">
                  <tr>
                    <th className="p-3.5 w-60">Item Name / Size</th>
                    <th className="p-3.5 w-32">Brand</th>
                    <th className="p-3.5">SKU / Tags</th>
                    <th className="p-3.5 text-right w-36">Retail Price / MRP</th>
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

                    // If single variant for this item block
                    if (!isMultiBrand) {
                      const p = block.variants[0];
                      const isEditing = editingId === p.id;
                      const isFocused = focusedRowIndex >= 0 && navigableRows[focusedRowIndex]?.productId === p.id;
                      return (
                        <tr
                          id={`row-product-${p.id}`}
                          key={p.id}
                          onClick={() => setFocusedRowIndex(navigableRows.findIndex(r => r.productId === p.id))}
                          className={`transition-all duration-150 cursor-pointer ${
                            isEditing 
                              ? 'bg-blue-500/10 border-l-4 border-l-blue-500' 
                              : isFocused 
                              ? 'bg-blue-500/10 ring-2 ring-inset ring-blue-500/60 border-l-4 border-l-blue-500' 
                              : 'hover:bg-muted/20'
                          }`}
                        >
                          {/* Item Name */}
                          <td className="p-3.5">
                            {isEditing ? (
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
                              <div>
                                <p className="text-foreground font-bold text-sm">{block.baseName}</p>
                                {block.alias && <p className="text-muted-foreground text-xs">{block.alias}</p>}
                              </div>
                            )}
                          </td>

                          {/* Brand */}
                          <td className="p-3.5">
                            {isEditing ? (
                              <input
                                type="text"
                                value={editData.brand}
                                onChange={e => setEditData({ ...editData, brand: e.target.value })}
                                placeholder="Brand"
                                className="bg-muted/40 border border-border text-foreground px-2 py-1 rounded w-full text-xs outline-none"
                              />
                            ) : p.brand ? (
                              <span className="bg-muted/60 text-foreground border border-border/60 text-xs px-2 py-0.5 rounded-md font-semibold font-mono">
                                {p.brand}
                              </span>
                            ) : (
                              <span className="bg-zinc-800/80 text-zinc-300 border border-zinc-700/80 text-xs px-2 py-0.5 rounded-md font-medium">
                                Unbranded
                              </span>
                            )}
                          </td>

                          {/* SKU & Tags */}
                          <td className="p-3.5">
                            <p className="text-muted-foreground font-mono text-xs">{p.sku}</p>
                            <div className="flex gap-1 mt-1 flex-wrap">
                              {p.tax_override && <span className="bg-red-500/10 text-red-400 text-[9px] px-1.5 py-0.5 rounded border border-red-500/20">Tax Override</span>}
                              {p.track_batches && <span className="bg-green-500/10 text-green-400 text-[9px] px-1.5 py-0.5 rounded border border-green-500/20">Batches</span>}
                              {p.track_serial_numbers && <span className="bg-purple-500/10 text-purple-400 text-[9px] px-1.5 py-0.5 rounded border border-purple-500/20">Serial</span>}
                            </div>
                          </td>

                          {/* Retail Price / MRP */}
                          <td className="p-3.5 text-right">
                            {isEditing ? (
                              <input
                                type="number"
                                step="0.01"
                                value={editData.selling_price}
                                onChange={e => setEditData({ ...editData, selling_price: parseFloat(e.target.value) || 0 })}
                                className="bg-muted/40 border border-border text-emerald-400 px-2 py-1 rounded w-24 text-xs text-right font-mono font-bold outline-none"
                              />
                            ) : (
                              <span className="text-emerald-400 font-bold text-sm">
                                ₹{parseFloat(p.selling_price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                              </span>
                            )}
                          </td>

                          {/* Purchase Price */}
                          <td className="p-3.5 text-right">
                            {isEditing ? (
                              <input
                                type="number"
                                step="0.01"
                                value={editData.purchase_price}
                                onChange={e => setEditData({ ...editData, purchase_price: parseFloat(e.target.value) || 0 })}
                                className="bg-muted/40 border border-border text-foreground px-2 py-1 rounded w-24 text-xs text-right font-mono outline-none"
                              />
                            ) : (
                              <div className="flex items-center justify-end gap-1.5">
                                <span className="text-muted-foreground font-medium text-xs">
                                  {parseFloat(p.purchase_price) > 0 ? `₹${parseFloat(p.purchase_price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : '—'}
                                </span>
                                {p.purchase_price_from_invoice && (
                                  <span title="Purchase price set from Purchase Invoice" className="text-[10px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-1 rounded font-mono font-bold">
                                    Invoice
                                  </span>
                                )}
                              </div>
                            )}
                          </td>

                          {/* Stock */}
                          <td className="p-3.5 text-right">
                            <span className={`font-bold text-sm ${parseFloat(p.stock_quantity) > 0 ? 'text-emerald-400' : 'text-muted-foreground'}`}>
                              {parseFloat(p.stock_quantity).toLocaleString('en-IN')}
                            </span>
                            <span className="text-[10px] text-muted-foreground ml-1">{p.unit}</span>
                          </td>

                          {/* Actions */}
                          <td className="p-3.5 text-center">
                            {isEditing ? (
                              <div className="flex items-center justify-center gap-1">
                                <button
                                  onClick={() => saveEdit(p.id)}
                                  disabled={savingId === p.id}
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
                                  onClick={() => startEdit(p)}
                                  className="text-muted-foreground hover:text-blue-400 p-1.5 rounded hover:bg-muted/60 transition-colors"
                                  title="Edit item"
                                >
                                  <Edit2 className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={() => deleteProduct(p.id, p.name)}
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
                    }

                    // Multi-Brand Unified Item Block:
                    // Render single master item block with stacked brand rows
                    return (
                      <tr key={block.baseName} className="border-b border-border/60 hover:bg-muted/5 transition-colors">
                        {/* Master Item Name Column */}
                        <td className="p-3.5 align-top border-r border-border/40 bg-muted/5">
                          <div className="space-y-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="text-foreground font-extrabold text-sm">{block.baseName}</span>
                              <span className="text-[10px] bg-blue-500/10 text-blue-400 border border-blue-500/20 px-1.5 py-0.2 rounded font-semibold whitespace-nowrap">
                                {block.variants.length} Brands
                              </span>
                            </div>
                            {block.alias && <p className="text-muted-foreground text-xs">{block.alias}</p>}
                            <p className="text-[11px] text-muted-foreground">
                              {block.variants.map(v => v.brand).filter(Boolean).join(', ')}
                            </p>
                          </div>
                        </td>

                        {/* Multi-Brand Nested Details Columns */}
                        <td colSpan={6} className="p-0 align-top">
                          <div className="divide-y divide-border/30">
                            {block.variants.map((v) => {
                              const isEditing = editingId === v.id;
                              const isFocused = focusedRowIndex >= 0 && navigableRows[focusedRowIndex]?.productId === v.id;
                              return (
                                <div
                                  id={`row-product-${v.id}`}
                                  key={v.id}
                                  onClick={() => setFocusedRowIndex(navigableRows.findIndex(r => r.productId === v.id))}
                                  className={`grid grid-cols-6 items-center p-3 text-xs transition-all duration-150 cursor-pointer ${
                                    isEditing 
                                      ? 'bg-blue-500/10 border-l-4 border-l-blue-500' 
                                      : isFocused 
                                      ? 'bg-blue-500/10 ring-2 ring-inset ring-blue-500/60 border-l-4 border-l-blue-500' 
                                      : 'hover:bg-muted/15'
                                  }`}
                                >
                                  {/* Brand */}
                                  <div>
                                    {isEditing ? (
                                      <input
                                        type="text"
                                        value={editData.brand}
                                        onChange={e => setEditData({ ...editData, brand: e.target.value })}
                                        className="bg-muted/40 border border-border text-foreground px-1.5 py-1 rounded text-xs w-full outline-none"
                                      />
                                    ) : v.brand ? (
                                      <span className="bg-zinc-800 text-blue-400 border border-blue-500/20 text-xs px-2 py-0.5 rounded font-bold font-mono">
                                        {v.brand}
                                      </span>
                                    ) : (
                                      <span className="bg-zinc-800/80 text-zinc-300 border border-zinc-700 text-xs px-2 py-0.5 rounded font-medium">
                                        Unbranded
                                      </span>
                                    )}
                                  </div>

                                  {/* SKU */}
                                  <div className="font-mono text-muted-foreground text-xs truncate pr-2">
                                    {v.sku}
                                  </div>

                                  {/* Retail Price / MRP */}
                                  <div className="text-right">
                                    {isEditing ? (
                                      <input
                                        type="number"
                                        step="0.01"
                                        value={editData.selling_price}
                                        onChange={e => setEditData({ ...editData, selling_price: parseFloat(e.target.value) || 0 })}
                                        className="bg-muted/40 border border-border text-emerald-400 px-1.5 py-1 rounded text-xs text-right font-mono font-bold w-20 outline-none"
                                      />
                                    ) : (
                                      <span className="text-emerald-400 font-bold">
                                        ₹{parseFloat(v.selling_price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                                      </span>
                                    )}
                                  </div>

                                  {/* Purchase Price */}
                                  <div className="text-right">
                                    {isEditing ? (
                                      <input
                                        type="number"
                                        step="0.01"
                                        value={editData.purchase_price}
                                        onChange={e => setEditData({ ...editData, purchase_price: parseFloat(e.target.value) || 0 })}
                                        className="bg-muted/40 border border-border text-foreground px-1.5 py-1 rounded text-xs text-right font-mono w-20 outline-none"
                                      />
                                    ) : (
                                      <div className="flex items-center justify-end gap-1">
                                        <span className="text-muted-foreground font-medium">
                                          {parseFloat(v.purchase_price) > 0 ? `₹${parseFloat(v.purchase_price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : '—'}
                                        </span>
                                        {v.purchase_price_from_invoice && (
                                          <span title="Purchase price set from Purchase Invoice" className="text-[9px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-1 rounded font-mono font-bold">
                                            Invoice
                                          </span>
                                        )}
                                      </div>
                                    )}
                                  </div>

                                  {/* Stock */}
                                  <div className="text-right">
                                    <span className={`font-bold ${parseFloat(v.stock_quantity) > 0 ? 'text-emerald-400' : 'text-muted-foreground'}`}>
                                      {parseFloat(v.stock_quantity).toLocaleString('en-IN')}
                                    </span>
                                    <span className="text-[10px] text-muted-foreground ml-1">{v.unit}</span>
                                  </div>

                                  {/* Action */}
                                  <div className="text-center">
                                    {isEditing ? (
                                      <div className="flex items-center justify-center gap-1">
                                        <button
                                          onClick={() => saveEdit(v.id)}
                                          disabled={savingId === v.id}
                                          className="p-1 rounded bg-emerald-600 text-white hover:bg-emerald-700"
                                          title="Save"
                                        >
                                          <Check className="w-3 h-3" />
                                        </button>
                                        <button
                                          onClick={cancelEdit}
                                          className="p-1 rounded bg-muted text-muted-foreground hover:text-foreground"
                                          title="Cancel"
                                        >
                                          <X className="w-3 h-3" />
                                        </button>
                                      </div>
                                    ) : (
                                      <div className="flex items-center justify-center gap-1">
                                        <button
                                          onClick={() => startEdit(v)}
                                          className="text-muted-foreground hover:text-blue-400 p-1 rounded hover:bg-muted/60 transition-colors"
                                          title="Edit this brand variant"
                                        >
                                          <Edit2 className="w-3 h-3" />
                                        </button>
                                        <button
                                          onClick={() => deleteProduct(v.id, v.name)}
                                          className="text-muted-foreground hover:text-rose-400 p-1 rounded hover:bg-muted/60 transition-colors"
                                          title="Delete item (Alt+D)"
                                        >
                                          <Trash2 className="w-3 h-3" />
                                        </button>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Table Footer */}
            <div className="p-3.5 border-t border-border/60 bg-muted/20 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs text-muted-foreground">
              <div className="flex items-center gap-2 flex-wrap">
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
              <div className="flex items-center gap-2 font-mono text-[11px]">
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
      </div>
    </DashboardLayout>
  );
}
