"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import ConfirmModal from '@/components/modals/ConfirmModal';
import { useToast } from '@/context/ToastContext';
import { 
  Search, 
  Trash2, 
  Edit2, 
  Users, 
  Building2, 
  UserCheck, 
  ArrowUpRight,
  Plus,
  RefreshCw
} from 'lucide-react';

export default function PartiesPage() {
  const router = useRouter();
  const { toast } = useToast();

  const [parties, setParties] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [companyId, setCompanyId] = useState('');

  // Filtering: 'ALL' | 'SUPPLIER' | 'CUSTOMER'
  const [activeFilter, setActiveFilter] = useState<'ALL' | 'SUPPLIER' | 'CUSTOMER'>('ALL');

  // Keyboard Navigation state
  const [focusedIndex, setFocusedIndex] = useState<number>(-1);

  // Deletion state
  const [deletingParty, setDeletingParty] = useState<any | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login');
      return;
    }
    fetchParties();
  }, [router]);

  const fetchParties = async () => {
    setLoading(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      
      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const cid = compRes.data.data[0]?.id;
      if (!cid) return;
      setCompanyId(cid);

      const ledgersRes = await axios.get(`${API_BASE_URL}/api/v1/ledgers/${cid}/`, { headers });
      
      const rawLedgers = ledgersRes.data.data || [];
      const filteredParties = rawLedgers.filter((l: any) => 
        l.group.includes('Debtor') || 
        l.group.includes('Creditor') || 
        l.name.includes('Customer') || 
        l.name.includes('Supplier') ||
        l.ledger_type === 'CUSTOMER' ||
        l.ledger_type === 'SUPPLIER'
      ).map((l: any) => ({
        ...l,
        type: (l.group.includes('Debtor') || l.ledger_type === 'CUSTOMER') ? 'Customer' : 'Supplier'
      }));

      setParties(filteredParties);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const [isCleaning, setIsCleaning] = useState(false);

  const handleCleanDuplicates = async () => {
    if (!companyId) return;
    setIsCleaning(true);
    try {
      const token = getAccessToken();
      const res = await axios.post(
        `${API_BASE_URL}/api/v1/ledgers/${companyId}/cleanup-duplicates/`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success("Parties Consolidated", res.data.message || "Duplicates merged successfully.");
      await fetchParties();
    } catch (err: any) {
      toast.error("Cleanup Failed", err.response?.data?.error || err.message);
    } finally {
      setIsCleaning(false);
    }
  };


  // Counts for tabs
  const counts = useMemo(() => {
    const suppliers = parties.filter(p => p.type === 'Supplier').length;
    const customers = parties.filter(p => p.type === 'Customer').length;
    return { all: parties.length, suppliers, customers };
  }, [parties]);

  // Filtered and Searched parties
  const filteredParties = useMemo(() => {
    return parties.filter(p => {
      // 1. Filter tab
      if (activeFilter === 'SUPPLIER' && p.type !== 'Supplier') return false;
      if (activeFilter === 'CUSTOMER' && p.type !== 'Customer') return false;

      // 2. Search query
      if (searchTerm.trim()) {
        const q = searchTerm.toLowerCase();
        const matchName = p.name?.toLowerCase().includes(q);
        const matchGstin = p.gstin?.toLowerCase().includes(q);
        const matchPhone = p.phone?.toLowerCase().includes(q);
        const matchGroup = p.group?.toLowerCase().includes(q);
        return matchName || matchGstin || matchPhone || matchGroup;
      }
      return true;
    });
  }, [parties, activeFilter, searchTerm]);

  // Scroll focused card into view
  useEffect(() => {
    if (focusedIndex >= 0 && focusedIndex < filteredParties.length) {
      const el = document.getElementById(`party-card-${filteredParties[focusedIndex].id}`);
      if (el) {
        el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
  }, [focusedIndex, filteredParties]);

  // Keyboard navigation & Tally shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // 1. If Delete Confirmation Modal is open
      if (deletingParty) {
        if (e.key === 'Escape') {
          e.preventDefault();
          setDeletingParty(null);
        } else if (e.key === 'Enter') {
          e.preventDefault();
          handleDeleteParty();
        }
        return;
      }

      // 2. If typing inside an input or textarea
      const activeEl = document.activeElement;
      const isInput = activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA');
      if (isInput) {
        if (e.key === 'Escape') {
          (activeEl as HTMLElement).blur();
        }
        return;
      }

      // 3. Arrow Keys to Navigate Cards
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault();
        setFocusedIndex(prev => (prev < filteredParties.length - 1 ? prev + 1 : prev));
      } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault();
        setFocusedIndex(prev => Math.max(0, prev - 1));
      } else if (e.key === 'Enter') {
        // Enter opens Statement
        if (focusedIndex >= 0 && focusedIndex < filteredParties.length) {
          e.preventDefault();
          router.push(`/parties/${filteredParties[focusedIndex].id}/statement`);
        }
      } else if (e.key.toLowerCase() === 'e' && !e.ctrlKey && !e.metaKey) {
        // 'e' shortcut to edit
        if (focusedIndex >= 0 && focusedIndex < filteredParties.length) {
          e.preventDefault();
          router.push(`/parties/${filteredParties[focusedIndex].id}/edit`);
        }
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        // Ctrl+Enter edit shortcut
        if (focusedIndex >= 0 && focusedIndex < filteredParties.length) {
          e.preventDefault();
          router.push(`/parties/${filteredParties[focusedIndex].id}/edit`);
        }
      } else if ((e.altKey && e.key.toLowerCase() === 'd') || e.key === 'Delete') {
        // Tally Delete shortcut: Alt + D or Delete
        if (focusedIndex >= 0 && focusedIndex < filteredParties.length) {
          e.preventDefault();
          setDeletingParty(filteredParties[focusedIndex]);
        }
      } else if (e.key === 'Escape') {
        setFocusedIndex(-1);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [deletingParty, focusedIndex, filteredParties, router]);

  const handleDeleteParty = async () => {
    if (!deletingParty || !companyId) return;
    setIsDeleting(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.delete(
        `${API_BASE_URL}/api/v1/ledgers/${companyId}/${deletingParty.id}/`,
        { headers }
      );
      if (res.data.success) {
        toast.success(res.data.message || `Party '${deletingParty.name}' deleted.`);
        setParties(prev => prev.filter(p => p.id !== deletingParty.id));
        setDeletingParty(null);
      } else {
        toast.error(res.data.error || 'Failed to delete party.');
      }
    } catch (err: any) {
      toast.error(err.response?.data?.error || err.message || 'Failed to delete party.');
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6 max-w-7xl mx-auto pb-16">
        {/* Header */}
        <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4 border-b border-border pb-6">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Parties</h1>
            <p className="text-gray-400 mt-1 text-sm">Manage your Customers and Suppliers accounts</p>
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 w-full lg:w-auto">
            {/* Search Input */}
            <div className="relative flex-1 sm:w-72">
              <Search className="w-4 h-4 text-muted-foreground absolute left-3.5 top-3" />
              <input 
                type="text" 
                placeholder="Search name, GSTIN, phone..." 
                value={searchTerm}
                onChange={e => {
                  setSearchTerm(e.target.value);
                  setFocusedIndex(-1);
                }}
                className="bg-zinc-900 border border-zinc-700 text-white pl-10 pr-4 py-2 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none w-full text-sm"
              />
              {searchTerm && (
                <button 
                  onClick={() => setSearchTerm('')} 
                  className="absolute right-3 top-2.5 text-xs text-muted-foreground hover:text-white"
                >
                  ✕
                </button>
              )}
            </div>

            {/* Create Buttons */}
            <div className="flex items-center gap-2">
              <Link 
                href="/purchases/suppliers/new" 
                className="bg-red-600/90 hover:bg-red-600 text-white px-3.5 py-2 rounded-xl shadow transition-colors text-xs font-bold whitespace-nowrap flex items-center gap-1.5"
              >
                <Plus className="w-4 h-4" />
                <span>Supplier</span>
              </Link>
              <Link 
                href="/sales/customers/new" 
                className="bg-blue-600 hover:bg-blue-700 text-white px-3.5 py-2 rounded-xl shadow transition-colors text-xs font-bold whitespace-nowrap flex items-center gap-1.5"
              >
                <Plus className="w-4 h-4" />
                <span>Customer</span>
              </Link>
            </div>
          </div>
        </div>

        {/* Filter Toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-3 bg-card/60 border border-border/70 p-2 rounded-2xl backdrop-blur">
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => { setActiveFilter('ALL'); setFocusedIndex(-1); }}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
                activeFilter === 'ALL'
                  ? 'bg-zinc-800 text-white border border-zinc-700 shadow-xs'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted/40'
              }`}
            >
              <Users className="w-3.5 h-3.5" />
              <span>All Parties</span>
              <span className="px-1.5 py-0.2 rounded-md bg-zinc-700/60 text-[10px] font-mono font-bold">
                {counts.all}
              </span>
            </button>

            <button
              type="button"
              onClick={() => { setActiveFilter('SUPPLIER'); setFocusedIndex(-1); }}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
                activeFilter === 'SUPPLIER'
                  ? 'bg-red-500/20 text-red-400 border border-red-500/40 shadow-xs'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted/40'
              }`}
            >
              <Building2 className="w-3.5 h-3.5 text-red-400" />
              <span>Suppliers</span>
              <span className="px-1.5 py-0.2 rounded-md bg-red-500/20 text-red-300 text-[10px] font-mono font-bold">
                {counts.suppliers}
              </span>
            </button>

            <button
              type="button"
              onClick={() => { setActiveFilter('CUSTOMER'); setFocusedIndex(-1); }}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
                activeFilter === 'CUSTOMER'
                  ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40 shadow-xs'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted/40'
              }`}
            >
              <UserCheck className="w-3.5 h-3.5 text-blue-400" />
              <span>Customers</span>
              <span className="px-1.5 py-0.2 rounded-md bg-blue-500/20 text-blue-300 text-[10px] font-mono font-bold">
                {counts.customers}
              </span>
            </button>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleCleanDuplicates}
              disabled={isCleaning}
              title="Consolidate duplicate parties and merge purchases"
              className="px-3 py-1.5 rounded-xl text-xs font-semibold bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 border border-zinc-700/60 transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
            >
              <RefreshCw className={`w-3 h-3 ${isCleaning ? 'animate-spin text-blue-400' : 'text-zinc-400'}`} />
              <span>{isCleaning ? 'Consolidating...' : 'Consolidate Duplicates'}</span>
            </button>
            <div className="text-xs text-muted-foreground px-1">
              Showing <span className="text-foreground font-bold">{filteredParties.length}</span> of {parties.length} accounts
            </div>
          </div>
        </div>
        
        {loading ? (
          <div className="flex items-center justify-center py-20 text-gray-500">Loading parties...</div>
        ) : filteredParties.length === 0 ? (
          <div className="flex flex-col items-center justify-center text-center p-16 bg-card rounded-2xl border border-border mt-4">
            <svg className="w-16 h-16 text-muted-foreground mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path>
            </svg>
            <h3 className="text-xl font-bold mb-1">No Parties Found</h3>
            <p className="text-gray-500 text-sm max-w-md mx-auto mb-6">
              {searchTerm 
                ? `No ${activeFilter !== 'ALL' ? activeFilter.toLowerCase() + 's' : 'parties'} match "${searchTerm}".`
                : `No ${activeFilter !== 'ALL' ? activeFilter.toLowerCase() + 's' : 'parties'} recorded yet.`}
            </p>
            <div className="flex gap-3">
              <Link href="/purchases/suppliers/new" className="bg-red-600 text-white px-5 py-2 rounded-xl shadow hover:bg-red-700 transition-colors text-xs font-bold">
                + Add Supplier
              </Link>
              <Link href="/sales/customers/new" className="bg-blue-600 text-white px-5 py-2 rounded-xl shadow hover:bg-blue-700 transition-colors text-xs font-bold">
                + Add Customer
              </Link>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            {filteredParties.map((party: any, idx: number) => {
              const isFocused = focusedIndex === idx;
              const isCustomer = party.type === 'Customer';
              const balanceNum = parseFloat(party.current_balance) || 0;
              const hasZeroBalance = balanceNum === 0;

              return (
                <div 
                  id={`party-card-${party.id}`}
                  key={party.id}
                  onClick={() => setFocusedIndex(idx)}
                  className={`bg-card border transition-all rounded-2xl p-5 flex flex-col group relative overflow-hidden cursor-pointer ${
                    isFocused 
                      ? 'border-blue-500 ring-2 ring-blue-500/60 shadow-lg shadow-blue-500/10 scale-[1.01]' 
                      : 'border-border hover:border-zinc-500'
                  }`}
                >
                  {/* Decorative Top Bar based on Type */}
                  <div className={`absolute top-0 left-0 right-0 h-1 ${isCustomer ? 'bg-blue-500' : 'bg-red-500'}`}></div>

                  {/* Selected Tag */}
                  {isFocused && (
                    <div className="absolute top-2.5 left-2.5 z-10 px-2 py-0.5 rounded text-[10px] font-mono bg-blue-500/20 text-blue-400 border border-blue-500/30">
                      Selected
                    </div>
                  )}

                  {/* Card Header */}
                  <div className="flex justify-between items-start mb-3 mt-1">
                    <div className="min-w-0 flex-1 pr-2">
                      <h3 className="text-lg font-bold text-white truncate group-hover:text-blue-400 transition-colors" title={party.name}>
                        {party.name}
                      </h3>
                      <div className="flex items-center gap-2 mt-1">
                        <span className={`text-[11px] px-2.5 py-0.5 rounded-full border font-semibold ${
                          isCustomer 
                            ? 'text-blue-400 bg-blue-500/10 border-blue-500/20' 
                            : 'text-red-400 bg-red-500/10 border-red-500/20'
                        }`}>
                          {party.type}
                        </span>
                        {party.gstin && (
                          <span className="text-[10px] font-mono text-muted-foreground bg-muted/40 px-2 py-0.5 rounded border border-border/40">
                            {party.gstin}
                          </span>
                        )}
                        {Number(party.discount_percent || 0) > 0 && (
                          <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded font-semibold">
                            {Number(party.discount_percent)}% Disc
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Top Action Buttons */}
                    <div className="flex items-center gap-1 opacity-75 group-hover:opacity-100 transition-opacity">
                      <Link 
                        href={`/parties/${party.id}/edit`} 
                        onClick={e => e.stopPropagation()}
                        className="p-1.5 rounded-lg bg-zinc-800/80 hover:bg-blue-600 text-gray-400 hover:text-white transition-colors"
                        title="Edit Party (Ctrl+Enter / E)"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </Link>
                      <button 
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeletingParty(party);
                        }}
                        className="p-1.5 rounded-lg bg-zinc-800/80 hover:bg-rose-600 text-gray-400 hover:text-white transition-colors"
                        title="Delete Party (Alt+D / Del)"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* Card Details */}
                  <div className="space-y-2.5 flex-1 text-xs">
                    <div className="flex justify-between items-center text-muted-foreground">
                      <span>Ledger Group</span>
                      <span className="text-zinc-300 font-medium font-mono">{party.group}</span>
                    </div>

                    {party.phone && (
                      <div className="flex justify-between items-center text-muted-foreground">
                        <span>Phone</span>
                        <span className="text-zinc-300 font-medium">{party.phone}</span>
                      </div>
                    )}
                    
                    <div className="flex justify-between items-baseline pt-1 border-t border-zinc-800/80">
                      <span className="text-muted-foreground text-xs">Current Balance</span>
                      <div className="text-right">
                        <span className={`font-bold text-base font-mono ${
                          hasZeroBalance 
                            ? 'text-zinc-400' 
                            : balanceNum > 0 
                            ? 'text-emerald-400' 
                            : 'text-rose-400'
                        }`}>
                          ₹{Math.abs(balanceNum).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                        <span className="text-[10px] text-muted-foreground ml-1 uppercase font-semibold">
                          {party.opening_balance_type || 'DEBIT'}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Card Footer */}
                  <div className="mt-4 pt-3 border-t border-zinc-800 flex justify-between items-center text-xs">
                    <div className="flex items-center gap-2">
                      <Link 
                        href={`/parties/${party.id}/edit`} 
                        onClick={e => e.stopPropagation()}
                        className="text-muted-foreground hover:text-white flex items-center gap-1 transition-colors font-medium"
                      >
                        <Edit2 className="w-3 h-3" />
                        <span>Edit</span>
                      </Link>
                      <span className="text-zinc-700">•</span>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeletingParty(party);
                        }}
                        className="text-muted-foreground hover:text-rose-400 flex items-center gap-1 transition-colors font-medium"
                      >
                        <Trash2 className="w-3 h-3" />
                        <span>Delete</span>
                      </button>
                    </div>

                    <Link 
                      href={`/parties/${party.id}/statement`} 
                      onClick={e => e.stopPropagation()}
                      className="text-blue-400 hover:text-blue-300 font-semibold flex items-center gap-1 group-hover:translate-x-0.5 transition-transform"
                    >
                      <span>Statement</span>
                      <ArrowUpRight className="w-3.5 h-3.5" />
                    </Link>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Keyboard Shortcuts Hint Bar */}
        <div className="p-3 border border-border bg-card/60 backdrop-blur rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs text-muted-foreground mt-6">
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
              <span className="text-[11px]">Statement</span>
            </span>
            <span>•</span>
            <span className="flex items-center gap-1">
              <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded border border-zinc-700 font-mono text-[10px] text-white font-bold">Ctrl + Enter / E</kbd>
              <span className="text-[11px]">Edit Party</span>
            </span>
            <span>•</span>
            <span className="flex items-center gap-1">
              <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded border border-zinc-700 font-mono text-[10px] text-white font-bold">Alt + D / Del</kbd>
              <span className="text-[11px]">Delete Party</span>
            </span>
            <span>•</span>
            <span className="flex items-center gap-1">
              <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded border border-zinc-700 font-mono text-[10px] text-white font-bold">Esc</kbd>
              <span className="text-[11px]">Deselect</span>
            </span>
          </div>
        </div>

        {/* Delete Confirmation Modal */}
        {deletingParty && (
          <ConfirmModal
            isOpen={!!deletingParty}
            onClose={() => setDeletingParty(null)}
            onConfirm={handleDeleteParty}
            title={`Delete Party "${deletingParty.name}"?`}
            variant="danger"
            confirmText={isDeleting ? "Deleting..." : "Delete Party"}
            description={
              <div className="space-y-2 text-xs text-muted-foreground">
                <p>
                  Are you sure you want to delete <span className="font-bold text-foreground">{deletingParty.name}</span> ({deletingParty.type})?
                </p>
                {parseFloat(deletingParty.current_balance) === 0 ? (
                  <p className="text-emerald-400 bg-emerald-500/10 p-2 rounded-lg border border-emerald-500/20">
                    This account has a ₹0.00 balance and no active transactions. It can be safely deleted.
                  </p>
                ) : (
                  <p className="text-amber-400 bg-amber-500/10 p-2 rounded-lg border border-amber-500/20">
                    Notice: This account currently has a balance of ₹{Math.abs(parseFloat(deletingParty.current_balance)).toLocaleString('en-IN', { minimumFractionDigits: 2 })}. If it has associated vouchers, deletion will be blocked to preserve accounting history.
                  </p>
                )}
              </div>
            }
          />
        )}
      </div>
    </DashboardLayout>
  );
}
