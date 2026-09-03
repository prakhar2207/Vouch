"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import { useToast } from '@/context/ToastContext';

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
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editData, setEditData] = useState<any>({});
  const [savingId, setSavingId] = useState<string | null>(null);

  // Category Edit State
  const [isCategoryEditing, setIsCategoryEditing] = useState(false);
  const [categoryEditData, setCategoryEditData] = useState<any>({});
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

  const filtered = products.filter(p =>
    p.name.toLowerCase().includes(search.toLowerCase()) ||
    (p.brand || '').toLowerCase().includes(search.toLowerCase()) ||
    p.sku.toLowerCase().includes(search.toLowerCase())
  );

  if (loading) return <DashboardLayout><div className="flex items-center justify-center py-20 text-gray-500">Loading...</div></DashboardLayout>;

  return (
    <DashboardLayout>
      <div className="space-y-6 pb-12">
        
        {/* Header */}
        <div className="flex justify-between items-start border-b border-border pb-5">
          <div className="flex items-center gap-4">
            <Link href="/inventory" className="text-gray-400 hover:text-white transition-colors mt-1">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
            </Link>
            {isCategoryEditing ? (
              <div className="flex flex-col gap-3">
                <input 
                  type="text" 
                  value={categoryEditData.name} 
                  onChange={e => setCategoryEditData({...categoryEditData, name: e.target.value})}
                  className="bg-zinc-800 border border-zinc-700 text-white px-3 py-1 rounded text-2xl font-bold max-w-sm"
                  placeholder="Category Name"
                />
                <div className="flex gap-2 items-start">
                  <input 
                    type="text" 
                    value={categoryEditData.hsn_code} 
                    onChange={e => setCategoryEditData({...categoryEditData, hsn_code: e.target.value})}
                    className="bg-zinc-800 border border-zinc-700 text-white px-2 py-1.5 rounded w-28 text-sm"
                    placeholder="HSN"
                  />
                  <div className="flex flex-col gap-1">
                    <div className="relative">
                      <input 
                        type="number" 
                        value={categoryEditData.gst_rate} 
                        onChange={e => setCategoryEditData({...categoryEditData, gst_rate: e.target.value})}
                        className="bg-zinc-800 border border-zinc-700 text-white px-2 py-1.5 rounded w-24 text-sm"
                        placeholder="GST"
                      />
                      <span className="absolute right-2 top-2 text-gray-400 text-xs">%</span>
                    </div>
                    <div className="text-[10px] text-gray-400 text-right">
                      IGST: {categoryEditData.gst_rate || 0}%<br/>
                      CGST: {(Number(categoryEditData.gst_rate || 0) / 2).toFixed(1)}% | SGST: {(Number(categoryEditData.gst_rate || 0) / 2).toFixed(1)}%
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div>
                <div className="flex items-center gap-3">
                  <h1 className="text-3xl font-bold">{category?.name || 'Category'}</h1>
                  <button onClick={startCategoryEdit} className="text-gray-400 hover:text-blue-400 transition-colors p-1" title="Edit Category">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"></path></svg>
                  </button>
                </div>
                <div className="flex items-center gap-3 mt-2">
                  <span className="bg-zinc-800 text-gray-300 text-xs px-3 py-1 rounded-full border border-zinc-700">HSN: {category?.hsn_code || '—'}</span>
                  <span className="bg-zinc-800 text-gray-300 text-xs px-3 py-1 rounded-full border border-zinc-700" title={`CGST: ${(Number(category?.gst_rate)/2).toFixed(1)}% | SGST: ${(Number(category?.gst_rate)/2).toFixed(1)}%`}>IGST: {category?.gst_rate}% (C/S: {(Number(category?.gst_rate)/2).toFixed(1)}%)</span>
                  <span className="bg-blue-500/10 text-blue-400 text-xs px-3 py-1 rounded-full border border-blue-500/20 font-medium">{products.length} item{products.length !== 1 ? 's' : ''}</span>
                </div>
              </div>
            )}
          </div>
          <div className="flex gap-3">
            {isCategoryEditing ? (
              <>
                <button onClick={() => setIsCategoryEditing(false)} className="text-gray-400 hover:text-white px-4 py-2">Cancel</button>
                <button onClick={saveCategoryEdit} disabled={savingCategory} className="bg-green-600 text-white px-5 py-2.5 rounded-lg shadow hover:bg-green-700 transition-colors font-medium">
                  {savingCategory ? 'Saving...' : 'Save Category'}
                </button>
              </>
            ) : (
              <Link href={`/inventory/categories/${categoryId}/new-item`} className="bg-blue-600 text-white px-5 py-2.5 rounded-lg shadow hover:bg-blue-700 transition-colors font-medium flex items-center gap-2">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4"></path></svg>
                Add Item
              </Link>
            )}
          </div>
        </div>

        {/* Content */}
        {products.length === 0 ? (
          <div className="flex flex-col items-center justify-center text-center p-16 bg-card rounded-xl border border-border">
            <svg className="w-20 h-20 text-gray-600 mb-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"></path>
            </svg>
            <h3 className="text-2xl font-bold mb-2">No Items in {category?.name}</h3>
            <p className="text-gray-500 max-w-md mx-auto mb-8">Add items like individual sizes, models, or variants to this category.</p>
            <Link href={`/inventory/categories/${categoryId}/new-item`} className="bg-blue-600 text-white px-6 py-2.5 rounded-lg shadow hover:bg-blue-700 transition-colors font-medium">
              + Add First Item
            </Link>
          </div>
        ) : (
          <div className="bg-card border border-border rounded-xl shadow-sm overflow-hidden">
            
            {/* Toolbar */}
            <div className="p-4 border-b border-border bg-zinc-900/50 flex justify-between items-center gap-4">
              <input
                type="text"
                placeholder="Search items by name, brand, or SKU..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="bg-zinc-800 border border-zinc-700 text-white px-4 py-2 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none w-full max-w-md text-sm"
              />
              <div className="flex items-center gap-3">
                <span className="text-gray-500 text-sm whitespace-nowrap">{filtered.length} of {products.length} items</span>
                <span className="text-xs text-gray-600 bg-zinc-800 px-2 py-1 rounded">Click ✏️ to edit</span>
              </div>
            </div>

            {/* Table */}
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead className="bg-zinc-900/80 text-gray-400 text-xs uppercase tracking-wider">
                  <tr>
                    <th className="p-4 font-medium border-b border-zinc-800">Item Name / Size</th>
                    <th className="p-4 font-medium border-b border-zinc-800">Brand</th>
                    <th className="p-4 font-medium border-b border-zinc-800">SKU / Tags</th>
                    <th className="p-4 font-medium border-b border-zinc-800 text-right">Retail Price / MRP</th>
                    <th className="p-4 font-medium border-b border-zinc-800 text-right">Wholesaler Price</th>
                    <th className="p-4 font-medium border-b border-zinc-800 text-right">Stock</th>
                    <th className="p-4 font-medium border-b border-zinc-800 text-center w-28">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {filtered.map((p: any) => (
                    <tr key={p.id} className={`transition-colors ${editingId === p.id ? 'bg-blue-500/5' : 'hover:bg-zinc-800/30'}`}>
                      
                      {/* Name */}
                      <td className="p-3">
                        {editingId === p.id ? (
                          <div className="space-y-1">
                            <input
                              type="text"
                              value={editData.name}
                              onChange={e => setEditData({ ...editData, name: e.target.value })}
                              className="bg-zinc-800 border border-zinc-600 text-white px-2 py-1.5 rounded w-full text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                            />
                            <input
                              type="text"
                              placeholder="Alias"
                              value={editData.alias}
                              onChange={e => setEditData({ ...editData, alias: e.target.value })}
                              className="bg-zinc-800 border border-zinc-600 text-gray-300 px-2 py-1 rounded w-full text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                            />
                          </div>
                        ) : (
                          <div>
                            <p className="text-white font-medium">{p.name}</p>
                            {p.alias && <p className="text-gray-500 text-xs">{p.alias}</p>}
                          </div>
                        )}
                      </td>

                      {/* Brand */}
                      <td className="p-3">
                        {editingId === p.id ? (
                          <input
                            type="text"
                            value={editData.brand}
                            onChange={e => setEditData({ ...editData, brand: e.target.value })}
                            placeholder="Brand"
                            className="bg-zinc-800 border border-zinc-600 text-white px-2 py-1.5 rounded w-full text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                          />
                        ) : p.brand ? (
                          <span className="bg-zinc-800 text-gray-300 text-xs px-2 py-1 rounded">{p.brand}</span>
                        ) : (
                          <span className="text-gray-600">—</span>
                        )}
                      </td>

                      {/* SKU & Tags */}
                      <td className="p-3">
                        <p className="text-gray-400 font-mono text-sm">{p.sku}</p>
                        <div className="flex gap-1 mt-1 flex-wrap">
                          {p.tax_override && <span className="bg-red-500/10 text-red-400 text-[10px] px-1.5 py-0.5 rounded border border-red-500/20">Tax Override</span>}
                          {p.track_batches && <span className="bg-green-500/10 text-green-400 text-[10px] px-1.5 py-0.5 rounded border border-green-500/20">Batches</span>}
                          {p.track_serial_numbers && <span className="bg-purple-500/10 text-purple-400 text-[10px] px-1.5 py-0.5 rounded border border-purple-500/20">Serial</span>}
                          {p.alternate_unit && <span className="bg-blue-500/10 text-blue-400 text-[10px] px-1.5 py-0.5 rounded border border-blue-500/20">{p.unit}/{p.alternate_unit}</span>}
                        </div>
                      </td>

                      {/* Selling Price */}
                      <td className="p-3 text-right">
                        {editingId === p.id ? (
                          <input
                            type="number"
                            step="0.01"
                            value={editData.selling_price}
                            onChange={e => setEditData({ ...editData, selling_price: parseFloat(e.target.value) || 0 })}
                            className="bg-zinc-800 border border-zinc-600 text-white px-2 py-1.5 rounded w-24 text-sm text-right focus:ring-2 focus:ring-blue-500 outline-none"
                          />
                        ) : (
                          <span className="text-green-400 font-medium">₹{parseFloat(p.selling_price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                        )}
                      </td>

                      {/* Wholesaler Price */}
                      <td className="p-3 text-right">
                        {editingId === p.id ? (
                          <input
                            type="number"
                            step="0.01"
                            value={editData.wholesaler_price}
                            onChange={e => setEditData({ ...editData, wholesaler_price: parseFloat(e.target.value) || 0 })}
                            className="bg-zinc-800 border border-zinc-600 text-white px-2 py-1.5 rounded w-24 text-sm text-right focus:ring-2 focus:ring-blue-500 outline-none"
                          />
                        ) : (
                          <span className="text-gray-400">₹{parseFloat(p.wholesaler_price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                        )}
                      </td>

                      {/* Stock */}
                      <td className="p-3 text-right">
                        <span className={`font-bold ${parseFloat(p.stock_quantity) > 0 ? 'text-green-400' : parseFloat(p.stock_quantity) < 0 ? 'text-red-400' : 'text-gray-500'}`}>
                          {parseFloat(p.stock_quantity).toLocaleString('en-IN')}
                        </span>
                        <p className="text-[10px] text-gray-500">{p.unit}</p>
                      </td>

                      {/* Actions */}
                      <td className="p-3 text-center">
                        {editingId === p.id ? (
                          <div className="flex flex-col items-center justify-center gap-1">
                            <button
                              onClick={() => saveEdit(p.id)}
                              disabled={savingId === p.id}
                              className="bg-green-600 hover:bg-green-700 w-full text-white text-xs px-2 py-1 rounded font-medium transition-colors disabled:opacity-50"
                            >
                              {savingId === p.id ? '...' : 'Save'}
                            </button>
                            <button
                              onClick={cancelEdit}
                              className="bg-zinc-700 hover:bg-zinc-600 w-full text-white text-xs px-2 py-1 rounded font-medium transition-colors"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => startEdit(p)}
                            className="text-gray-500 hover:text-blue-400 transition-colors p-1.5 rounded hover:bg-zinc-800"
                            title="Edit item"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"></path></svg>
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Footer */}
            <div className="p-4 border-t border-border bg-zinc-900/30 text-right">
              <span className="text-gray-500 text-sm">Showing {filtered.length} item{filtered.length !== 1 ? 's' : ''}</span>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
