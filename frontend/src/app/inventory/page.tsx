"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';

export default function InventoryPage() {
  const router = useRouter();
  const [categories, setCategories] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [companyId, setCompanyId] = useState('');

  const [editingCategory, setEditingCategory] = useState<any>(null);
  const [deletingCategory, setDeletingCategory] = useState<any>(null);
  const [editData, setEditData] = useState<any>({});
  const [saving, setSaving] = useState(false);

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
      }
    } catch (err: any) {
      alert('Save failed: ' + (err.response?.data?.error || err.message));
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
    } catch (err: any) {
      alert('Delete failed: ' + (err.response?.data?.error || err.message));
    } finally {
      setSaving(false);
    }
  };

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
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
            {categories.map((cat: any) => (
              <div 
                key={cat.id}
                onClick={() => router.push(`/inventory/categories/${cat.id}`)}
                className="bg-card border border-border hover:border-blue-500 cursor-pointer rounded-xl p-6 transition-all shadow-sm flex flex-col group relative overflow-hidden h-64"
              >
                {/* Top accent */}
                <div className="absolute top-0 left-0 right-0 h-1 bg-blue-500 opacity-0 group-hover:opacity-100 transition-opacity"></div>
                
                {editingCategory?.id === cat.id ? (
                  <div className="flex-1 flex flex-col justify-center gap-3" onClick={e => e.stopPropagation()}>
                    <input 
                      type="text" 
                      value={editData.name} 
                      onChange={e => setEditData({...editData, name: e.target.value})}
                      className="bg-zinc-800 border border-zinc-700 text-white px-3 py-1.5 rounded text-lg font-bold w-full"
                      placeholder="Category Name"
                    />
                    <div className="flex justify-between items-start gap-2">
                      <input 
                        type="text" 
                        value={editData.hsn_code} 
                        onChange={e => setEditData({...editData, hsn_code: e.target.value})}
                        className="bg-zinc-800 border border-zinc-700 text-white px-2 py-1.5 rounded w-full text-sm"
                        placeholder="HSN"
                      />
                      <div className="w-full flex flex-col gap-1">
                        <input 
                          type="number" 
                          value={editData.gst_rate} 
                          onChange={e => setEditData({...editData, gst_rate: e.target.value})}
                          className="bg-zinc-800 border border-zinc-700 text-white px-2 py-1.5 rounded w-full text-sm"
                          placeholder="Total GST %"
                        />
                        <div className="text-[10px] text-gray-400 text-right leading-tight">
                          IGST: {editData.gst_rate || 0}%<br/>
                          CGST: {(Number(editData.gst_rate || 0) / 2).toFixed(1)}% | SGST: {(Number(editData.gst_rate || 0) / 2).toFixed(1)}%
                        </div>
                      </div>
                    </div>
                    <div className="flex justify-end gap-2 mt-2">
                      <button onClick={() => setEditingCategory(null)} className="text-gray-400 hover:text-white text-xs px-2 py-1">Cancel</button>
                      <button onClick={handleSaveEdit} disabled={saving} className="bg-blue-600 text-white text-xs px-3 py-1 rounded hover:bg-blue-700">Save</button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="absolute top-3 right-3 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button onClick={(e) => startEdit(cat, e)} className="p-1.5 bg-zinc-800 hover:bg-blue-500 text-gray-400 hover:text-white rounded transition-colors" title="Edit Category">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"></path></svg>
                      </button>
                      <button onClick={(e) => startDelete(cat, e)} className="p-1.5 bg-zinc-800 hover:bg-red-500 text-gray-400 hover:text-white rounded transition-colors" title="Delete Category">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                      </button>
                    </div>

                    <div className="flex-1 flex flex-col items-center justify-center text-center">
                      <div className="w-14 h-14 bg-zinc-800 text-gray-300 rounded-full flex items-center justify-center mb-4 group-hover:scale-110 group-hover:bg-blue-500/10 group-hover:text-blue-400 transition-all">
                        <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
                      </div>
                      <h3 className="text-xl font-bold text-white group-hover:text-blue-400 transition-colors">{cat.name}</h3>
                      <p className="text-gray-500 text-sm mt-1">{cat.item_count} item{cat.item_count !== 1 ? 's' : ''}</p>
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
            ))}
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
