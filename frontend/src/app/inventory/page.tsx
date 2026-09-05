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

export default function InventoryPage() {
  const router = useRouter();
  const { toast } = useToast();
  const [categories, setCategories] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [companyId, setCompanyId] = useState('');

  const [editingCategory, setEditingCategory] = useState<any>(null);
  const [deletingCategory, setDeletingCategory] = useState<any>(null);
  const [editData, setEditData] = useState<any>({});
  const [saving, setSaving] = useState(false);
  const [retailDiscount, setRetailDiscount] = useState<number>(0);

  useEffect(() => {
    if (!isAuthenticated()) { router.push('/login'); return; }
    fetchCategories();
  }, [router]);

  const fetchCategories = async () => {
    setLoading(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const cid = compRes.data.data[0]?.id;
      if (!cid) return;
      setCompanyId(cid);

      const res = await axios.get(`${API_BASE_URL}/api/v1/inventory/categories/${cid}/`, { headers });
      setCategories(res.data.data || []);
      setSummary(res.data.summary || null);
    } catch (err) {
      console.error(err);
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
        <div className="flex justify-between items-center border-b border-border pb-4">
          <div>
            <h1 className="text-3xl font-bold">Inventory</h1>
            <p className="text-sm text-gray-400 mt-1">Manage product categories and items</p>
          </div>
          <Link href="/inventory/categories/new" className="bg-blue-600 text-white px-5 py-2.5 rounded-lg shadow hover:bg-blue-700 transition-colors font-medium flex items-center gap-2">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4"></path></svg>
            New Category
          </Link>
        </div>

        {/* Stock Valuation Summary Banner */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="p-4 rounded-xl border border-border bg-card/70 backdrop-blur shadow-xs flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20 flex items-center justify-center shrink-0">
              <Boxes className="w-6 h-6" />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Total Stock Value</p>
              <h3 className="text-xl font-bold text-foreground truncate">
                ₹{(summary?.total_stock_value || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </h3>
              <p className="text-[11px] text-blue-400 font-medium mt-0.5">
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
                <div className="p-4 rounded-xl border border-border bg-card/70 backdrop-blur shadow-xs flex flex-col justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20 flex items-center justify-center shrink-0">
                      <Tag className="w-6 h-6" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Total MRP (List Price)</p>
                      <h3 className="text-xl font-bold text-foreground truncate">
                        ₹{listPriceValue.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </h3>
                      <p className="text-[11px] text-muted-foreground mt-0.5">
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
                  <div className="mt-2.5 pt-2 border-t border-border/40 flex items-center justify-between text-[11px]">
                    <span className="text-muted-foreground">Est. Retail Discount:</span>
                    <div className="flex items-center gap-1">
                      <input
                        type="number"
                        min="0"
                        max="99"
                        placeholder="0"
                        value={retailDiscount || ''}
                        onChange={e => setRetailDiscount(Math.max(0, Math.min(99, parseFloat(e.target.value) || 0)))}
                        className="w-12 bg-zinc-800/80 border border-zinc-700/80 rounded px-1.5 py-0.5 text-xs text-white font-mono font-bold text-right outline-none focus:border-purple-500"
                      />
                      <span className="text-muted-foreground font-semibold">%</span>
                      {retailDiscount > 0 && (
                        <button
                          onClick={() => setRetailDiscount(0)}
                          className="text-[10px] text-zinc-400 hover:text-white ml-1 px-1 py-0.5 rounded bg-zinc-800"
                          title="Reset to 0%"
                        >
                          ✕
                        </button>
                      )}
                    </div>
                  </div>
                </div>

                <div className="p-4 rounded-xl border border-border bg-card/70 backdrop-blur shadow-xs flex flex-col justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center justify-center shrink-0">
                      <TrendingUp className="w-6 h-6" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                        {retailDiscount > 0 ? 'Realized Margin' : 'Gross Margin (At MRP)'}
                      </p>
                      <h3 className="text-xl font-bold text-emerald-400 truncate">
                        ₹{effectiveMargin.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </h3>
                      <p className="text-[11px] text-muted-foreground mt-0.5">
                        {marginMarkupPct}% {retailDiscount > 0 ? `markup after ${retailDiscount}% retail discount` : 'markup over cost at list price'}
                      </p>
                    </div>
                  </div>
                  <div className="mt-2.5 pt-2 border-t border-border/40 text-[11px] text-muted-foreground flex items-center justify-between">
                    <span>Retail vs Purchase Cost</span>
                    <span className="font-medium text-foreground">
                      ₹{stockCostValue > 0 ? ((effectiveRetailValue / stockCostValue)).toFixed(2) : '1.00'}x cost
                    </span>
                  </div>
                </div>
              </>
            );
          })()}

          <div className="p-4 rounded-xl border border-border bg-card/70 backdrop-blur shadow-xs flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20 flex items-center justify-center shrink-0">
              <Layers className="w-6 h-6" />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Catalog Scope</p>
              <h3 className="text-xl font-bold text-foreground truncate">
                {summary?.total_items ?? categories.reduce((acc: number, c: any) => acc + (c.item_count || 0), 0)} Items
              </h3>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                Across {categories.length} product {categories.length === 1 ? 'category' : 'categories'}
              </p>
            </div>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20 text-gray-500">Loading...</div>
        ) : categories.length === 0 ? (
          <div className="flex flex-col items-center justify-center text-center p-16 bg-card rounded-xl border border-border">
            <svg className="w-20 h-20 text-gray-600 mb-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
            </svg>
            <h3 className="text-2xl font-bold mb-2">No Categories Yet</h3>
            <p className="text-gray-500 max-w-md mx-auto mb-8">Start by creating a product category (e.g. V-Belt, Bearings, Phones). Each category carries its own HSN code and GST rate.</p>
            <Link href="/inventory/categories/new" className="bg-blue-600 text-white px-6 py-2.5 rounded-lg shadow hover:bg-blue-700 transition-colors font-medium">
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
                    className={`border cursor-pointer rounded-xl p-5 transition-all shadow-sm flex flex-col group relative overflow-hidden min-h-[17.5rem] ${
                      isFocused 
                        ? 'bg-card border-blue-500 ring-2 ring-blue-500/60 shadow-lg shadow-blue-500/15 scale-[1.01]' 
                        : 'bg-card border-border hover:border-blue-500'
                    }`}
                  >
                    {/* Top accent */}
                    <div className={`absolute top-0 left-0 right-0 h-1 bg-blue-500 transition-opacity ${isFocused ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}></div>

                    {isFocused && (
                      <div className="absolute top-2.5 left-2.5 z-10 px-2 py-0.5 rounded text-[10px] font-mono bg-blue-500/20 text-blue-400 border border-blue-500/30">
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
                          className="bg-zinc-900 border border-zinc-700 rounded p-1.5 text-white text-sm"
                          autoFocus
                        />
                        <input 
                          type="text" 
                          value={editData.hsn_code} 
                          onChange={e => setEditData({...editData, hsn_code: e.target.value})}
                          placeholder="HSN Code"
                          className="bg-zinc-900 border border-zinc-700 rounded p-1.5 text-white text-sm"
                        />
                        <input 
                          type="number" 
                          value={editData.gst_rate} 
                          onChange={e => setEditData({...editData, gst_rate: e.target.value})}
                          placeholder="GST Rate %"
                          className="bg-zinc-900 border border-zinc-700 rounded p-1.5 text-white text-sm"
                        />
                        <div className="flex justify-end gap-2 mt-2">
                          <button onClick={() => setEditingCategory(null)} className="text-gray-400 hover:text-white text-xs px-2 py-1">Cancel (Esc)</button>
                          <button onClick={handleSaveEdit} disabled={saving} className="bg-blue-600 text-white text-xs px-3 py-1 rounded hover:bg-blue-700">Save (Ctrl+Enter / Ctrl+A)</button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div className="absolute top-3 right-3 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button onClick={(e) => startEdit(cat, e)} className="p-1.5 bg-zinc-800 hover:bg-blue-500 text-gray-400 hover:text-white rounded transition-colors" title="Edit Category (Ctrl+Enter)">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"></path></svg>
                          </button>
                          <button onClick={(e) => startDelete(cat, e)} className="p-1.5 bg-zinc-800 hover:bg-red-500 text-gray-400 hover:text-white rounded transition-colors" title="Delete Category (Alt+D)">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                          </button>
                        </div>

                        <div className="flex-1 flex flex-col items-center justify-center text-center">
                          <div className="w-12 h-12 bg-zinc-800 text-gray-300 rounded-full flex items-center justify-center mb-2.5 group-hover:scale-110 group-hover:bg-blue-500/10 group-hover:text-blue-400 transition-all">
                            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
                          </div>
                          <h3 className="text-lg font-bold text-white group-hover:text-blue-400 transition-colors truncate max-w-full px-1">{cat.name}</h3>
                          <div className="flex items-center gap-1.5 text-xs text-gray-400 mt-0.5">
                            <span>{cat.item_count} item{cat.item_count !== 1 ? 's' : ''}</span>
                            {cat.stock_quantity > 0 && (
                              <>
                                <span>•</span>
                                <span className="text-blue-400 font-medium">{cat.stock_quantity} units</span>
                              </>
                            )}
                          </div>
                          
                          {/* Stock Value Badge */}
                          <div className="mt-2.5 px-2.5 py-1 rounded-md bg-emerald-950/40 border border-emerald-500/20 text-emerald-400 text-xs font-semibold flex items-center gap-1">
                            <span className="text-[10px] text-emerald-500/70 uppercase">Stock Val:</span>
                            <span>₹{(cat.stock_value || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                          </div>
                        </div>

                        <div className="border-t border-zinc-800 pt-3 mt-auto flex flex-col text-xs text-gray-500 gap-1">
                          <div className="flex justify-between">
                            <span>HSN: <span className="text-gray-300 font-medium">{cat.hsn_code || '—'}</span></span>
                            <span>IGST: <span className="text-gray-300 font-medium">{cat.gst_rate}%</span></span>
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
            <div className="p-3 border border-border bg-card/60 backdrop-blur rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs text-muted-foreground mt-4">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="flex items-center gap-1 font-semibold text-foreground">
                  <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></span>
                  Tally Shortcuts:
                </span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded border border-zinc-700 font-mono text-[10px] text-white font-bold">↑</kbd>
                  <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded border border-zinc-700 font-mono text-[10px] text-white font-bold">↓</kbd>
                  <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded border border-zinc-700 font-mono text-[10px] text-white font-bold">←</kbd>
                  <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded border border-zinc-700 font-mono text-[10px] text-white font-bold">→</kbd>
                  <span className="text-[11px]">Navigate</span>
                </span>
                <span>•</span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded border border-zinc-700 font-mono text-[10px] text-white font-bold">Enter</kbd>
                  <span className="text-[11px]">Open Category</span>
                </span>
                <span>•</span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded border border-zinc-700 font-mono text-[10px] text-white font-bold">Ctrl + Enter</kbd>
                  <span className="text-[11px]">Alter / Edit</span>
                </span>
                <span>•</span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded border border-zinc-700 font-mono text-[10px] text-white font-bold">Alt + D</kbd>
                  <span className="text-[11px]">Delete</span>
                </span>
                <span>•</span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded border border-zinc-700 font-mono text-[10px] text-white font-bold">Esc</kbd>
                  <span className="text-[11px]">Deselect</span>
                </span>
              </div>
              {focusedIndex >= 0 && categories[focusedIndex] && (
                <span className="font-mono text-blue-400 font-semibold text-[11px]">
                  {categories[focusedIndex].name} ({focusedIndex + 1}/{categories.length})
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Delete Confirmation Modal */}
      {deletingCategory && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl max-w-md w-full p-6 text-center">
            <div className="w-16 h-16 bg-red-500/10 text-red-500 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
            </div>
            <h3 className="text-xl font-bold text-white mb-2">Delete Category?</h3>
            <p className="text-gray-400 mb-6 text-sm">
              Are you sure you want to delete <strong className="text-white">{deletingCategory.name}</strong>? 
              <br/><br/>
              <span className="text-red-400 font-medium">Warning: Deleting this category of item would lose all data related to it.</span>
            </p>
            <div className="flex gap-3 justify-center">
              <button 
                onClick={() => setDeletingCategory(null)} 
                className="px-5 py-2.5 bg-zinc-800 text-white rounded-lg hover:bg-zinc-700 transition-colors font-medium"
                disabled={saving}
              >
                Cancel
              </button>
              <button 
                onClick={handleDelete} 
                className="px-5 py-2.5 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors font-medium flex items-center justify-center min-w-[120px]"
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
