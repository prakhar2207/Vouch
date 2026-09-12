"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import { Boxes, Tag, Layers, TrendingUp, Plus } from 'lucide-react';
import { useToast } from '@/context/ToastContext';
import { offlineDb } from '@/lib/db/offlineDb';
import { useCompany } from '@/context/CompanyContext';

export default function InventoryPage() {
  const router = useRouter();
  const { toast } = useToast();
  const [categories, setCategories] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const { activeCompany, companyId: activeCompanyId } = useCompany();
  const [companyId, setCompanyId] = useState(activeCompanyId || '');

  const [editingCategory, setEditingCategory] = useState<any>(null);
  const [deletingCategory, setDeletingCategory] = useState<any>(null);
  const [editData, setEditData] = useState<any>({});
  const [saving, setSaving] = useState(false);
  const [retailDiscount, setRetailDiscount] = useState<number>(0);

  useEffect(() => {
    if (!isAuthenticated()) { router.push('/login'); return; }
    fetchCategories();
  }, [router, activeCompanyId]);

  useEffect(() => {
    if (activeCompanyId && activeCompanyId !== companyId) {
      setCompanyId(activeCompanyId);
    }
  }, [activeCompanyId]);

  const fetchCategories = async () => {
    setLoading(true);
    try {
      // 1. Try local offline cache first
      try {
        const cachedComp = await offlineDb.masters.get('company');
        if (cachedComp?.data?.id) setCompanyId(cachedComp.data.id);

        const cachedCats = await offlineDb.masters.get('categories');
        const cachedSummary = await offlineDb.masters.get('inventory_summary');
        if (cachedCats?.data?.length) {
          setCategories(cachedCats.data);
          if (cachedSummary?.data) setSummary(cachedSummary.data);
          setLoading(false);
          // If cached within the last 5 minutes, do not make repeated network requests
          if (cachedCats.updatedAt && Date.now() - cachedCats.updatedAt < 5 * 60 * 1000) {
            return;
          }
        }
      } catch (cacheErr) {
        console.warn('Could not read categories from offline cache', cacheErr);
      }

      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      
      let cid = activeCompanyId;
      if (!cid && typeof window !== 'undefined') {
        cid = localStorage.getItem('vouch_active_company_id');
      }
      if (!cid) {
        const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
        const list = Array.isArray(compRes.data) ? compRes.data : (compRes.data.data || []);
        cid = list[0]?.id;
      }
      if (!cid) return;
      setCompanyId(cid);
      offlineDb.masters.put({ key: 'company', data: activeCompany || { id: cid }, updatedAt: Date.now() }).catch(() => {});

      const res = await axios.get(`${API_BASE_URL}/api/v1/inventory/categories/${cid}/`, { headers });
      const catList = res.data.data || [];
      const sumData = res.data.summary || null;
      setCategories(catList);
      setSummary(sumData);
      offlineDb.masters.put({ key: 'categories', data: catList, updatedAt: Date.now() }).catch(() => {});
      if (sumData) {
        offlineDb.masters.put({ key: 'inventory_summary', data: sumData, updatedAt: Date.now() }).catch(() => {});
      }
    } catch (err) {
      console.error('Network fetch failed in inventory, using offline cache if available:', err);
    } finally {
      setLoading(false);
    }
  };

  const startEdit = (cat: any, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setEditingCategory(cat);
    setEditData({ name: cat.name, hsn_code: cat.hsn_code, gst_rate: cat.gst_rate });
  };

  const handleSaveEdit = async () => {
    setSaving(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.patch(
        `${API_BASE_URL}/api/v1/inventory/categories/${companyId}/${editingCategory.id}/`,
        editData,
        { headers }
      );
      if (res.data.success) {
        setCategories(cats => cats.map(c => c.id === editingCategory.id ? { ...c, ...editData } : c));
        setEditingCategory(null);
        toast.success('Category updated successfully');
      }
    } catch (err: any) {
      toast.error('Save failed', err.response?.data?.error || err.message);
    } finally {
      setSaving(false);
    }
  };

  const startDelete = (cat: any, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDeletingCategory(cat);
  };

  const handleDelete = async () => {
    setSaving(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      await axios.delete(
        `${API_BASE_URL}/api/v1/inventory/categories/${companyId}/${deletingCategory.id}/`,
        { headers }
      );
      setCategories(cats => cats.filter(c => c.id !== deletingCategory.id));
      setDeletingCategory(null);
      toast.success('Category deleted successfully');
    } catch (err: any) {
      toast.error('Delete failed', err.response?.data?.error || err.message);
    } finally {
      setSaving(false);
    }
  };

  const [focusedIndex, setFocusedIndex] = useState<number>(-1);

  const scrollToCategory = (index: number) => {
    if (index >= 0 && index < categories.length) {
      const catId = categories[index].id;
      const el = document.getElementById(`cat-card-${catId}`);
      if (el) {
        el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // 1. If Category Inline Edit is active
      if (editingCategory) {
        if ((e.ctrlKey || e.metaKey) && (e.key === 'Enter' || e.key.toLowerCase() === 'a')) {
          e.preventDefault();
          handleSaveEdit();
        } else if (e.key === 'Escape') {
          e.preventDefault();
          setEditingCategory(null);
        }
        return;
      }

      // 2. If Delete Confirmation Modal is open
      if (deletingCategory) {
        if (e.key === 'Enter') {
          e.preventDefault();
          handleDelete();
        } else if (e.key === 'Escape') {
          e.preventDefault();
          setDeletingCategory(null);
        }
        return;
      }

      // 3. Skip if user is actively typing in an input
      const activeElement = document.activeElement;
      const isInputFocused = activeElement && (
        activeElement.tagName === 'INPUT' ||
        activeElement.tagName === 'TEXTAREA' ||
        activeElement.tagName === 'SELECT'
      );
      if (isInputFocused) return;

      if (categories.length === 0) return;

      // 4. Arrow navigation
      if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
        e.preventDefault();
        setFocusedIndex(prev => {
          const next = prev < categories.length - 1 ? prev + 1 : 0;
          scrollToCategory(next);
          return next;
        });
      } else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
        e.preventDefault();
        setFocusedIndex(prev => {
          const next = prev > 0 ? prev - 1 : categories.length - 1;
          scrollToCategory(next);
          return next;
        });
      } else if (e.key === 'Home') {
        e.preventDefault();
        setFocusedIndex(0);
        scrollToCategory(0);
      } else if (e.key === 'End') {
        e.preventDefault();
        setFocusedIndex(categories.length - 1);
        scrollToCategory(categories.length - 1);
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        // TALLY ALTER SHORTCUT: Ctrl + Enter edits the selected category
        if (focusedIndex >= 0 && focusedIndex < categories.length) {
          e.preventDefault();
          const target = categories[focusedIndex];
          setEditingCategory(target);
          setEditData({ name: target.name, hsn_code: target.hsn_code, gst_rate: target.gst_rate });
        }
      } else if (e.key.toLowerCase() === 'e' && !e.ctrlKey && !e.metaKey) {
        // 'e' shortcut to edit
        if (focusedIndex >= 0 && focusedIndex < categories.length) {
          e.preventDefault();
          const target = categories[focusedIndex];
          setEditingCategory(target);
          setEditData({ name: target.name, hsn_code: target.hsn_code, gst_rate: target.gst_rate });
        }
      } else if (e.key === 'Enter') {
        // Enter drills down into category items
        if (focusedIndex >= 0 && focusedIndex < categories.length) {
          e.preventDefault();
          router.push(`/inventory/categories/${categories[focusedIndex].id}`);
        }
      } else if ((e.altKey && e.key.toLowerCase() === 'd') || e.key === 'Delete') {
        // TALLY DELETE SHORTCUT: Alt + D deletes selected category
        if (focusedIndex >= 0 && focusedIndex < categories.length) {
          e.preventDefault();
          setDeletingCategory(categories[focusedIndex]);
        }
      } else if (e.key === 'Escape') {
        setFocusedIndex(-1);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [categories, focusedIndex, editingCategory, deletingCategory, editData, saving, router]);

  return (
    <DashboardLayout>
      <div className="space-y-6 pb-12">
        
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/40 pb-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">Inventory</h1>
            <p className="text-xs sm:text-sm text-muted-foreground mt-0.5">Manage your products and stock</p>
          </div>
          <Link href="/inventory/categories/new" className="bg-primary text-primary-foreground px-4 sm:px-5 py-2 sm:py-2.5 rounded-xl shadow-md shadow-primary/20 hover:bg-primary/90 transition-all font-medium flex items-center justify-center gap-2 text-xs sm:text-sm">
            <svg className="w-4 h-4 sm:w-5 sm:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4"></path></svg>
            <span>New Category</span>
          </Link>
        </div>

        {/* Stock Valuation Summary Banner */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="p-4 rounded-2xl border border-border/40 bg-card/70 backdrop-blur shadow-sm flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20 flex items-center justify-center shrink-0">
              <Boxes className="w-6 h-6" />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Total Stock Value</p>
              <h3 className="text-xl font-bold font-mono tabular-nums text-foreground truncate">
                ₹{(summary?.total_stock_value || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </h3>
              <p className="text-xs text-blue-400 font-medium mt-0.5">
                {(summary?.total_stock_quantity || 0).toLocaleString('en-IN')} units at cost
              </p>
            </div>
          </div>

          {(() => {
            const listPriceValue = summary?.total_retail_value || 0;
            const stockCostValue = summary?.total_stock_value || 0;
            const effectiveRetailValue = retailDiscount > 0 
              ? listPriceValue * (1 - retailDiscount / 100) 
              : listPriceValue;
            const effectiveMargin = Math.max(0, effectiveRetailValue - stockCostValue);
            const marginMarkupPct = stockCostValue > 0 ? ((effectiveMargin / stockCostValue) * 100).toFixed(1) : '0';

            return (
              <>
                <div className="p-4 rounded-2xl border border-border/40 bg-card/70 backdrop-blur shadow-sm flex flex-col justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20 flex items-center justify-center shrink-0">
                      <Tag className="w-6 h-6" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Total MRP (List Price)</p>
                      <h3 className="text-xl font-bold font-mono tabular-nums text-foreground truncate">
                        ₹{listPriceValue.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </h3>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {retailDiscount > 0 ? (
                          <span className="text-purple-400 font-medium">
                            At {retailDiscount}% disc: ₹{effectiveRetailValue.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </span>
                        ) : (
                          'Valuation at catalog list price'
                        )}
                      </p>
                    </div>
                  </div>
                  <div className="mt-2.5 pt-2 border-t border-border/40 flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">Est. Retail Discount:</span>
                    <div className="flex items-center gap-1">
                      <input
                        type="number"
                        min="0"
                        max="99"
                        placeholder="0"
                        value={retailDiscount || ''}
                        onChange={e => setRetailDiscount(Math.max(0, Math.min(99, parseFloat(e.target.value) || 0)))}
                        className="w-14 bg-muted border border-border/60 rounded-lg px-2 py-1 text-sm text-foreground font-mono font-bold text-right outline-none focus:border-purple-500 min-h-[30px]"
                      />
                      <span className="text-muted-foreground font-semibold">%</span>
                      {retailDiscount > 0 && (
                        <button
                          onClick={() => setRetailDiscount(0)}
                          className="text-xs text-muted-foreground hover:text-foreground ml-1 px-1.5 py-0.5 rounded bg-muted cursor-pointer"
                          title="Reset to 0%"
                        >
                          ✕
                        </button>
                      )}
                    </div>
                  </div>
                </div>

                <div className="p-4 rounded-2xl border border-border/40 bg-card/70 backdrop-blur shadow-sm flex flex-col justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center justify-center shrink-0">
                      <TrendingUp className="w-6 h-6" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-emerald-400 uppercase tracking-wider">
                        {retailDiscount > 0 ? 'Profit Margin' : 'Profit Margin (At MRP)'}
                      </p>
                      <h3 className="text-xl font-bold font-mono tabular-nums text-emerald-400 truncate">
                        ₹{effectiveMargin.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </h3>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {marginMarkupPct}% {retailDiscount > 0 ? `markup after ${retailDiscount}% retail discount` : 'markup over cost at list price'}
                      </p>
                    </div>
                  </div>
                  <div className="mt-2.5 pt-2 border-t border-border/40 text-xs text-muted-foreground flex items-center justify-between">
                    <span>Retail vs Purchase Cost</span>
                    <span className="font-semibold text-foreground font-mono tabular-nums">
                      ₹{stockCostValue > 0 ? ((effectiveRetailValue / stockCostValue)).toFixed(2) : '1.00'}x cost
                    </span>
                  </div>
                </div>
              </>
            );
          })()}

          <div className="p-4 rounded-2xl border border-border/40 bg-card/70 backdrop-blur shadow-sm flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20 flex items-center justify-center shrink-0">
              <Layers className="w-6 h-6" />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Products</p>
              <h3 className="text-xl font-bold text-foreground truncate">
                {summary?.total_items ?? categories.reduce((acc: number, c: any) => acc + (c.item_count || 0), 0)} Items
              </h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                Across {categories.length} product {categories.length === 1 ? 'category' : 'categories'}
              </p>
            </div>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20 text-muted-foreground">Loading...</div>
        ) : categories.length === 0 ? (
          <div className="flex flex-col items-center justify-center text-center p-16 bg-card rounded-2xl border border-border/40 shadow-sm">
            <svg className="w-20 h-20 text-muted-foreground/60 mb-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
            </svg>
            <h3 className="text-2xl font-bold mb-2">No Categories Yet</h3>
            <p className="text-muted-foreground max-w-md mx-auto mb-8">Start by creating a product category (e.g. V-Belt, Bearings, Phones). Each category carries its own HSN code and GST rate.</p>
            <Link href="/inventory/categories/new" className="bg-primary text-primary-foreground px-6 py-2.5 rounded-xl shadow-md shadow-primary/20 hover:bg-primary/90 transition-all font-medium">
              + Create First Category
            </Link>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
              {categories.map((cat: any, idx: number) => {
                const isFocused = focusedIndex === idx;
                return (
                  <div 
                    id={`cat-card-${cat.id}`}
                    key={cat.id}
                    onClick={() => {
                      setFocusedIndex(idx);
                      router.push(`/inventory/categories/${cat.id}`);
                    }}
                    className={`border cursor-pointer rounded-2xl p-5 transition-all shadow-sm flex flex-col group relative overflow-hidden min-h-[17.5rem] ${
                      isFocused 
                        ? 'bg-card border-primary ring-2 ring-primary/60 shadow-lg shadow-primary/15 scale-[1.01]' 
                        : 'bg-card border-border/40 hover:border-border'
                    }`}
                  >
                    {/* Top accent */}
                    <div className={`absolute top-0 left-0 right-0 h-1 bg-primary transition-opacity ${isFocused ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}></div>

                    {isFocused && (
                      <div className="absolute top-2.5 left-2.5 z-10 px-2 py-0.5 rounded text-[10px] font-mono bg-primary/20 text-primary border border-primary/30">
                        Selected
                      </div>
                    )}
                    
                    {editingCategory?.id === cat.id ? (
                      <div className="flex-1 flex flex-col justify-center gap-3" onClick={e => e.stopPropagation()}>
                        <input 
                          type="text" 
                          value={editData.name} 
                          onChange={e => setEditData({...editData, name: e.target.value})}
                          placeholder="Category Name"
                          className="bg-muted/40 border border-border/60 rounded-lg p-1.5 text-foreground text-sm outline-none focus:ring-2 focus:ring-primary/40"
                          autoFocus
                        />
                        <input 
                          type="text" 
                          value={editData.hsn_code} 
                          onChange={e => setEditData({...editData, hsn_code: e.target.value})}
                          placeholder="HSN Code"
                          className="bg-muted/40 border border-border/60 rounded-lg p-1.5 text-foreground text-sm outline-none focus:ring-2 focus:ring-primary/40"
                        />
                        <input 
                          type="number" 
                          value={editData.gst_rate} 
                          onChange={e => setEditData({...editData, gst_rate: e.target.value})}
                          placeholder="GST Rate %"
                          className="bg-muted/40 border border-border/60 rounded-lg p-1.5 text-foreground text-sm outline-none focus:ring-2 focus:ring-primary/40"
                        />
                        <div className="flex justify-end gap-2 mt-2">
                          <button onClick={() => setEditingCategory(null)} className="text-muted-foreground hover:text-foreground text-xs px-2 py-1">Cancel (Esc)</button>
                          <button onClick={handleSaveEdit} disabled={saving} className="bg-primary text-primary-foreground text-xs px-3 py-1 rounded-lg hover:bg-primary/90 shadow-md shadow-primary/20">Save (Ctrl+Enter / Ctrl+A)</button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div className="absolute top-3 right-3 flex gap-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
                          <button onClick={(e) => startEdit(cat, e)} className="p-1.5 bg-muted/80 hover:bg-primary text-muted-foreground hover:text-primary-foreground rounded-lg transition-colors" title="Edit Category (Ctrl+Enter)">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"></path></svg>
                          </button>
                          <button onClick={(e) => startDelete(cat, e)} className="p-1.5 bg-muted/80 hover:bg-rose-500 text-muted-foreground hover:text-foreground rounded-lg transition-colors" title="Delete Category (Alt+D)">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                          </button>
                        </div>

                        <div className="flex-1 flex flex-col items-center justify-center text-center">
                          <div className="w-12 h-12 bg-muted text-muted-foreground rounded-full flex items-center justify-center mb-2.5 group-hover:scale-110 group-hover:bg-primary/10 group-hover:text-primary transition-all">
                            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
                          </div>
                          <h3 className="text-lg font-bold text-foreground group-hover:text-primary transition-colors truncate max-w-full px-1">{cat.name}</h3>
                          <div className="flex items-center gap-1.5 text-xs text-muted-foreground mt-0.5">
                            <span>{cat.item_count} item{cat.item_count !== 1 ? 's' : ''}</span>
                            {cat.stock_quantity > 0 && (
                              <>
                                <span>•</span>
                                <span className="text-primary font-medium">{cat.stock_quantity} units</span>
                              </>
                            )}
                          </div>
                          
                          {/* Stock Value Badge */}
                          <div className="mt-2.5 px-2.5 py-1 rounded-md bg-emerald-950/40 border border-emerald-500/20 text-emerald-400 text-xs font-semibold flex items-center gap-1">
                            <span className="text-[10px] text-emerald-500/70 uppercase">Stock Val:</span>
                            <span>₹{(cat.stock_value || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                          </div>
                        </div>

                        <div className="border-t border-border/40 pt-3 mt-auto flex flex-col text-xs text-muted-foreground gap-1">
                          <div className="flex justify-between">
                            <span>HSN: <span className="text-foreground font-medium">{cat.hsn_code || '—'}</span></span>
                            <span>IGST: <span className="text-foreground font-medium">{cat.gst_rate}%</span></span>
                          </div>
                          <div className="flex justify-between text-[10px]">
                            <span></span>
                            <span>CGST: {(Number(cat.gst_rate)/2).toFixed(1)}% | SGST: {(Number(cat.gst_rate)/2).toFixed(1)}%</span>
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Keyboard Shortcuts Hint Bar */}
            <div className="p-3 border border-border/40 bg-card/60 backdrop-blur rounded-xl shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs text-muted-foreground mt-4">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="flex items-center gap-1 font-semibold text-foreground">
                  <span className="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
                  Shortcuts:
                </span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/60 font-mono text-[10px] text-foreground font-bold">↑</kbd>
                  <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/60 font-mono text-[10px] text-foreground font-bold">↓</kbd>
                  <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/60 font-mono text-[10px] text-foreground font-bold">←</kbd>
                  <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/60 font-mono text-[10px] text-foreground font-bold">→</kbd>
                  <span className="text-[11px]">Navigate</span>
                </span>
                <span>•</span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/60 font-mono text-[10px] text-foreground font-bold">Enter</kbd>
                  <span className="text-[11px]">Open Category</span>
                </span>
                <span>•</span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/60 font-mono text-[10px] text-foreground font-bold">Ctrl + Enter</kbd>
                  <span className="text-[11px]">Alter / Edit</span>
                </span>
                <span>•</span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/60 font-mono text-[10px] text-foreground font-bold">Alt + D</kbd>
                  <span className="text-[11px]">Delete</span>
                </span>
                <span>•</span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-muted rounded border border-border/60 font-mono text-[10px] text-foreground font-bold">Esc</kbd>
                  <span className="text-[11px]">Deselect</span>
                </span>
              </div>
              {focusedIndex >= 0 && categories[focusedIndex] && (
                <span className="font-mono text-primary font-semibold text-[11px]">
                  {categories[focusedIndex].name} ({focusedIndex + 1}/{categories.length})
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Delete Confirmation Modal */}
      {deletingCategory && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-card border border-border/40 rounded-2xl shadow-2xl max-w-md w-full p-6 text-center">
            <div className="w-16 h-16 bg-rose-500/10 text-rose-500 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
            </div>
            <h3 className="text-xl font-bold text-foreground mb-2">Delete Category?</h3>
            <p className="text-muted-foreground mb-6 text-sm">
              Are you sure you want to delete <strong className="text-foreground">{deletingCategory.name}</strong>? 
              <br/><br/>
              <span className="text-rose-400 font-medium">Warning: Deleting this category of item would lose all data related to it.</span>
            </p>
            <div className="flex gap-3 justify-center">
              <button 
                onClick={() => setDeletingCategory(null)} 
                className="px-5 py-2.5 bg-muted text-foreground rounded-xl hover:bg-muted/80 border border-border/40 transition-colors font-medium cursor-pointer"
                disabled={saving}
              >
                Cancel
              </button>
              <button 
                onClick={handleDelete} 
                className="px-5 py-2.5 bg-rose-600 text-foreground rounded-xl hover:bg-rose-700 shadow-md shadow-rose-600/20 transition-all font-medium flex items-center justify-center min-w-[120px] cursor-pointer"
                disabled={saving}
              >
                {saving ? 'Deleting...' : 'Yes, Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
