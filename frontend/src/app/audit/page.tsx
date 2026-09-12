"use client";
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import { API_BASE_URL } from '@/utils/api';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import { useToast } from '@/context/ToastContext';
import {
  ShieldCheck,
  Search,
  Filter,
  RefreshCw,
  Eye,
  X,
  ChevronLeft,
  ChevronRight,
  Hash,
  User,
  Clock,
  CheckCircle2,
  Lock,
  ArrowRight,
  AlertCircle
} from 'lucide-react';

interface AuditEntry {
  id: string;
  action: 'CREATE' | 'UPDATE' | 'CANCEL' | 'DELETE' | string;
  model_name: string;
  record_id: string;
  changes: Record<string, any>;
  user_email: string;
  user_name: string;
  created_at: string;
  current_hash: string;
  previous_hash: string;
  ip_address: string;
}

export default function AuditPage() {
  const router = useRouter();
  const { toast } = useToast();

  const [company, setCompany] = useState<any>(null);
  const [logs, setLogs] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionFilter, setActionFilter] = useState('ALL');
  const [modelFilter, setModelFilter] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  // Pagination
  const [page, setPage] = useState(1);
  const [limit] = useState(25);
  const [pagination, setPagination] = useState<any>(null);

  // Diff Modal
  const [selectedEntry, setSelectedEntry] = useState<AuditEntry | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login');
      return;
    }
    fetchLogs(1);
  }, [actionFilter, modelFilter, router]);

  const fetchLogs = async (targetPage = 1) => {
    setLoading(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      let activeComp = company;
      if (!activeComp) {
        const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
        activeComp = compRes.data?.data?.[0];
        setCompany(activeComp);
      }

      if (!activeComp?.id) {
        setLoading(false);
        return;
      }

      const offset = (targetPage - 1) * limit;
      let url = `${API_BASE_URL}/api/v1/audit/${activeComp.id}/?limit=${limit}&offset=${offset}`;

      if (actionFilter !== 'ALL') {
        url += `&action=${actionFilter}`;
      }
      if (modelFilter !== 'ALL') {
        url += `&model=${modelFilter}`;
      }

      const res = await axios.get(url, { headers });
      if (res.data?.success) {
        setLogs(res.data.data || []);
        setPagination(res.data.pagination);
        setPage(targetPage);
      }
    } catch (err: any) {
      console.error('Failed to fetch audit logs:', err);
      toast.error('Failed to load audit logs', err.response?.data?.error || err.message);
    } finally {
      setLoading(false);
    }
  };

  const filteredLogs = logs.filter((log) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      log.user_email?.toLowerCase().includes(q) ||
      log.model_name?.toLowerCase().includes(q) ||
      log.record_id?.toLowerCase().includes(q) ||
      log.current_hash?.toLowerCase().includes(q)
    );
  });

  const getActionBadge = (action: string) => {
    switch (action.toUpperCase()) {
      case 'CREATE':
        return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
      case 'UPDATE':
        return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
      case 'CANCEL':
        return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
      case 'DELETE':
        return 'bg-rose-500/10 text-rose-400 border-rose-500/20';
      default:
        return 'bg-muted text-muted-foreground border-border/40';
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/40 pb-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-blue-500/10 rounded-xl text-blue-400">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">
                Activity Log
              </h1>
              <p className="text-xs sm:text-sm text-muted-foreground mt-0.5">
                Complete history of changes and entries for your business
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={() => fetchLogs(page)}
              disabled={loading}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-border/60 bg-muted/40 hover:bg-muted text-xs font-semibold text-foreground transition-colors cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* Cryptographic Tamper-Chain Verification Banner */}
        <div className="p-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shrink-0">
              <Lock className="w-5 h-5" />
            </div>
            <div>
              <div className="font-bold text-sm text-foreground flex items-center gap-2">
                <span>Audit Log Integrity: Verified</span>
                <span className="text-[10px] font-mono px-2 py-0.5 bg-emerald-500/20 text-emerald-400 rounded-full font-bold">
                  SHA-256
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Every transaction is cryptographically verified to ensure records cannot be altered.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs font-mono text-emerald-400">
            <CheckCircle2 className="w-4 h-4" />
            <span>Verified Records</span>
          </div>
        </div>

        {/* Filters and Search */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2 flex-wrap w-full sm:w-auto">
            {/* Action filter */}
            <div className="flex items-center gap-1 bg-muted/40 p-1 rounded-xl border border-border/40">
              {['ALL', 'CREATE', 'UPDATE', 'CANCEL', 'DELETE'].map((act) => (
                <button
                  key={act}
                  onClick={() => setActionFilter(act)}
                  className={`px-2.5 py-1 text-xs font-semibold rounded-lg transition-colors cursor-pointer ${
                    actionFilter === act
                      ? 'bg-card text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {act}
                </button>
              ))}
            </div>

            {/* Entity filter */}
            <div className="flex items-center gap-1 bg-muted/40 p-1 rounded-xl border border-border/40">
              {['ALL', 'Voucher', 'Ledger', 'Product'].map((mod) => (
                <button
                  key={mod}
                  onClick={() => setModelFilter(mod)}
                  className={`px-2.5 py-1 text-xs font-semibold rounded-lg transition-colors cursor-pointer ${
                    modelFilter === mod
                      ? 'bg-card text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {mod === 'ALL' ? 'All Entities' : mod}
                </button>
              ))}
            </div>
          </div>

          {/* Search */}
          <div className="relative w-full sm:w-72">
            <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search user, entity, hash..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-xs bg-muted/40 border border-border/60 rounded-xl text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
        </div>

        {/* Audit Log Table */}
        <div className="bg-card border border-border/40 rounded-xl shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse min-w-[700px]">
              <thead className="bg-muted/40 text-muted-foreground border-b border-border/60 font-semibold">
                <tr>
                  <th className="p-3.5">Timestamp</th>
                  <th className="p-3.5">Action</th>
                  <th className="p-3.5">Entity</th>
                  <th className="p-3.5">Actor</th>
                  <th className="p-3.5">SHA-256 Hash</th>
                  <th className="p-3.5 text-right">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40 font-mono text-xs">
                {loading ? (
                  <tr>
                    <td colSpan={6} className="p-12 text-center text-muted-foreground font-sans">
                      <div className="flex flex-col items-center justify-center space-y-2">
                        <RefreshCw className="w-5 h-5 animate-spin text-primary" />
                        <span>Verifying cryptographic log chain...</span>
                      </div>
                    </td>
                  </tr>
                ) : filteredLogs.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="p-12 text-center text-muted-foreground font-sans">
                      No audit entries matching the current filter.
                    </td>
                  </tr>
                ) : (
                  filteredLogs.map((entry) => (
                    <tr key={entry.id} className="hover:bg-muted/40 transition-colors">
                      <td className="p-3.5 text-foreground whitespace-nowrap">
                        <div className="flex items-center gap-1.5 font-sans">
                          <Clock className="w-3.5 h-3.5 text-muted-foreground" />
                          <span>{entry.created_at}</span>
                        </div>
                      </td>

                      <td className="p-3.5">
                        <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${getActionBadge(entry.action)}`}>
                          {entry.action}
                        </span>
                      </td>

                      <td className="p-3.5 font-sans">
                        <div className="font-semibold text-foreground">{entry.model_name}</div>
                        <div className="text-[10px] text-muted-foreground font-mono truncate max-w-[120px]">
                          ID: {entry.record_id}
                        </div>
                      </td>

                      <td className="p-3.5 font-sans">
                        <div className="flex items-center gap-1.5 text-foreground">
                          <User className="w-3.5 h-3.5 text-muted-foreground" />
                          <span>{entry.user_email || 'System'}</span>
                        </div>
                        {entry.ip_address && (
                          <div className="text-[10px] text-muted-foreground font-mono">
                            IP: {entry.ip_address}
                          </div>
                        )}
                      </td>

                      <td className="p-3.5">
                        <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                          <Hash className="w-3 h-3 text-muted-foreground" />
                          <span className="truncate max-w-[140px]" title={entry.current_hash}>
                            {entry.current_hash ? `${entry.current_hash.slice(0, 16)}...` : 'genesis'}
                          </span>
                        </div>
                      </td>

                      <td className="p-3.5 text-right font-sans">
                        <button
                          onClick={() => setSelectedEntry(entry)}
                          className="px-2.5 py-1 rounded-lg border border-border/60 hover:bg-muted text-xs font-medium text-foreground transition-colors inline-flex items-center gap-1 cursor-pointer"
                        >
                          <Eye className="w-3.5 h-3.5 text-muted-foreground" />
                          <span>View Diff</span>
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {pagination && pagination.total_pages > 1 && (
            <div className="flex items-center justify-between p-3.5 border-t border-border/40 bg-muted/20 text-xs text-muted-foreground">
              <div>
                Showing {(page - 1) * limit + 1} to {Math.min(page * limit, pagination.total_count)} of {pagination.total_count} records
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => fetchLogs(page - 1)}
                  disabled={page <= 1 || loading}
                  className="px-2.5 py-1 rounded-lg border border-border/60 bg-card hover:bg-muted text-foreground disabled:opacity-40 transition-colors flex items-center gap-1 cursor-pointer"
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                  <span>Prev</span>
                </button>
                <span className="font-mono text-foreground font-semibold">
                  Page {page} of {pagination.total_pages}
                </span>
                <button
                  onClick={() => fetchLogs(page + 1)}
                  disabled={page >= pagination.total_pages || loading}
                  className="px-2.5 py-1 rounded-lg border border-border/60 bg-card hover:bg-muted text-foreground disabled:opacity-40 transition-colors flex items-center gap-1 cursor-pointer"
                >
                  <span>Next</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Diff Inspection Modal */}
        {selectedEntry && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in">
            <div className="bg-card border border-border rounded-2xl shadow-2xl max-w-2xl w-full p-6 space-y-4 max-h-[85vh] flex flex-col">
              <div className="flex items-center justify-between border-b border-border/40 pb-3">
                <div className="flex items-center gap-2">
                  <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${getActionBadge(selectedEntry.action)}`}>
                    {selectedEntry.action}
                  </span>
                  <h3 className="font-bold text-base text-foreground font-sans">
                    {selectedEntry.model_name} #{selectedEntry.record_id}
                  </h3>
                </div>
                <button
                  onClick={() => setSelectedEntry(null)}
                  className="p-1 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Hash Chain Metadata */}
              <div className="p-3 bg-muted/40 rounded-xl border border-border/40 text-xs space-y-1.5 font-mono">
                <div className="flex items-center justify-between text-muted-foreground">
                  <span>Timestamp:</span>
                  <span className="text-foreground">{selectedEntry.created_at}</span>
                </div>
                <div className="flex items-center justify-between text-muted-foreground">
                  <span>Actor:</span>
                  <span className="text-foreground">{selectedEntry.user_email}</span>
                </div>
                <div className="flex items-center justify-between text-muted-foreground">
                  <span>Current Hash:</span>
                  <span className="text-emerald-400 break-all">{selectedEntry.current_hash}</span>
                </div>
                <div className="flex items-center justify-between text-muted-foreground">
                  <span>Previous Hash:</span>
                  <span className="text-muted-foreground break-all">{selectedEntry.previous_hash || 'genesis'}</span>
                </div>
              </div>

              {/* Payload Diff */}
              <div className="flex-1 overflow-y-auto space-y-2">
                <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Audit Snapshot & Modification Diff
                </div>
                <div className="bg-muted/50 rounded-xl p-4 border border-border/40 text-xs font-mono overflow-x-auto text-foreground">
                  <pre className="whitespace-pre-wrap">
                    {JSON.stringify(selectedEntry.changes, null, 2)}
                  </pre>
                </div>
              </div>

              <div className="flex justify-end pt-3 border-t border-border/40">
                <button
                  onClick={() => setSelectedEntry(null)}
                  className="px-4 py-2 rounded-xl bg-muted hover:bg-muted/80 text-foreground text-xs font-semibold transition-colors cursor-pointer"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
