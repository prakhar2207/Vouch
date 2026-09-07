"use client";
import React, { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { API_BASE_URL } from '@/utils/api';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import { useToast } from '@/context/ToastContext';
import {
  Search,
  Plus,
  Edit2,
  Trash2,
  BookOpen,
  Layers,
  ArrowDownLeft,
  ArrowUpRight,
  ShieldAlert,
  Building2,
  Wallet,
  X,
  RefreshCw,
  Lock,
  Receipt,
  FileText,
  Scale,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  ArrowRight
} from 'lucide-react';

interface LedgerItem {
  id: string;
  name: string;
  group_id?: string;
  group: string;
  nature: 'ASSET' | 'LIABILITY' | 'INCOME' | 'EXPENSE' | 'EQUITY';
  ledger_type: string;
  gstin?: string;
  state_code?: string;
  phone?: string;
  email?: string;
  address?: string;
  current_balance?: number;
  opening_balance?: number;
  opening_balance_type?: 'DEBIT' | 'CREDIT';
  discount_percent?: number;
  is_active?: boolean;
}

interface LedgerGroupItem {
  id: string;
  name: string;
  nature: string;
  parent_group_id?: string;
  parent_group_name?: string;
}

export default function LedgersPage() {
  const router = useRouter();
  const { toast } = useToast();

  const [companyId, setCompanyId] = useState('');
  const [ledgers, setLedgers] = useState<LedgerItem[]>([]);
  const [groups, setGroups] = useState<LedgerGroupItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeTab, setActiveTab] = useState<'ALL' | 'ASSET' | 'LIABILITY' | 'INCOME' | 'EXPENSE' | 'TAX'>('ALL');
  const [isGstWidgetExpanded, setIsGstWidgetExpanded] = useState(true);

  // Modals
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingLedger, setEditingLedger] = useState<LedgerItem | null>(null);
  const [deletingLedger, setDeletingLedger] = useState<LedgerItem | null>(null);
  const [deleteError, setDeleteError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Form State for Add / Edit
  const [formData, setFormData] = useState({
    name: '',
    group_id: '',
    group_name: '',
    nature: 'ASSET',
    ledger_type: 'GENERAL',
    gstin: '',
    state_code: '',
    phone: '',
    email: '',
    address: '',
    opening_balance: '',
    opening_balance_type: 'DEBIT',
    discount_percent: '',
    is_active: true,
  });

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login');
      return;
    }
    fetchLedgers();
  }, [router]);

  const fetchLedgers = async () => {
    setLoading(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const cid = compRes.data.data[0]?.id;
      if (!cid) return;
      setCompanyId(cid);

      const [ledgersRes, groupsRes] = await Promise.all([
        axios.get(`${API_BASE_URL}/api/v1/ledgers/${cid}/`, { headers }),
        axios.get(`${API_BASE_URL}/api/v1/ledgers/${cid}/groups/`, { headers }).catch(() => ({ data: { data: [] } }))
      ]);

      setLedgers(ledgersRes.data.data || []);
      setGroups(groupsRes.data?.data || []);
    } catch (err: any) {
      console.error(err);
      toast.error('Failed to load accounts', err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenAddModal = () => {
    setFormData({
      name: '',
      group_id: groups[0]?.id || '',
      group_name: '',
      nature: groups[0]?.nature || 'ASSET',
      ledger_type: 'GENERAL',
      gstin: '',
      state_code: '',
      phone: '',
      email: '',
      address: '',
      opening_balance: '',
      opening_balance_type: 'DEBIT',
      discount_percent: '',
      is_active: true,
    });
    setIsAddModalOpen(true);
  };

  const handleOpenEditModal = (ledger: LedgerItem) => {
    setEditingLedger(ledger);
    setFormData({
      name: ledger.name || '',
      group_id: ledger.group_id || '',
      group_name: ledger.group || '',
      nature: ledger.nature || 'ASSET',
      ledger_type: ledger.ledger_type || 'GENERAL',
      gstin: ledger.gstin || '',
      state_code: ledger.state_code || '',
      phone: ledger.phone || '',
      email: ledger.email || '',
      address: ledger.address || '',
      opening_balance: ledger.opening_balance ? String(ledger.opening_balance) : '',
      opening_balance_type: ledger.opening_balance_type || 'DEBIT',
      discount_percent: ledger.discount_percent ? String(ledger.discount_percent) : '',
      is_active: ledger.is_active ?? true,
    });
  };

  const handleCreateLedger = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name.trim()) {
      toast.error('Name required', 'Please provide an account head name.');
      return;
    }
    setIsSubmitting(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      const selectedGrp = groups.find(g => g.id === formData.group_id);
      const payload = {
        name: formData.name.trim(),
        group_id: formData.group_id || undefined,
        group_name: selectedGrp?.name || formData.group_name || 'General',
        ledger_type: formData.ledger_type,
        gstin: formData.gstin.trim().toUpperCase(),
        state_code: formData.state_code.trim(),
        phone: formData.phone.trim(),
        email: formData.email.trim(),
        address: formData.address.trim(),
        opening_balance: formData.opening_balance ? parseFloat(formData.opening_balance) : 0,
        opening_balance_type: formData.opening_balance_type,
        discount_percent: formData.discount_percent ? parseFloat(formData.discount_percent) : 0,
      };

      const res = await axios.post(`${API_BASE_URL}/api/v1/ledgers/${companyId}/`, payload, { headers });
      if (res.data.success) {
        toast.success('Account Created', `Account "${formData.name}" added successfully.`);
        setIsAddModalOpen(false);
        await fetchLedgers();
      }
    } catch (err: any) {
      toast.error('Creation Failed', err.response?.data?.error || err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleUpdateLedger = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingLedger) return;
    setIsSubmitting(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      const payload = {
        name: formData.name.trim(),
        group_id: formData.group_id || undefined,
        ledger_type: formData.ledger_type,
        gstin: formData.gstin.trim().toUpperCase(),
        state_code: formData.state_code.trim(),
        phone: formData.phone.trim(),
        email: formData.email.trim(),
        address: formData.address.trim(),
        opening_balance: formData.opening_balance ? parseFloat(formData.opening_balance) : 0,
        opening_balance_type: formData.opening_balance_type,
        discount_percent: formData.discount_percent ? parseFloat(formData.discount_percent) : 0,
        is_active: formData.is_active,
      };

      const res = await axios.patch(
        `${API_BASE_URL}/api/v1/ledgers/${companyId}/${editingLedger.id}/`,
        payload,
        { headers }
      );
      if (res.data.success) {
        toast.success('Account Updated', `Account "${formData.name}" updated successfully.`);
        setEditingLedger(null);
        await fetchLedgers();
      }
    } catch (err: any) {
      toast.error('Update Failed', err.response?.data?.error || err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteLedger = async () => {
    if (!deletingLedger) return;
    setIsSubmitting(true);
    setDeleteError('');
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      const res = await axios.delete(
        `${API_BASE_URL}/api/v1/ledgers/${companyId}/${deletingLedger.id}/`,
        { headers }
      );
      if (res.data.success) {
        toast.success('Account Deleted', res.data.message || `Deleted "${deletingLedger.name}".`);
        setDeletingLedger(null);
        await fetchLedgers();
      }
    } catch (err: any) {
      const msg = err.response?.data?.error || err.message;
      setDeleteError(msg);
      toast.error('Cannot Delete Account', msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Metrics
  const metrics = useMemo(() => {
    const assets = ledgers.filter(l => l.nature === 'ASSET').length;
    const liabilities = ledgers.filter(l => l.nature === 'LIABILITY').length;
    const income = ledgers.filter(l => l.nature === 'INCOME').length;
    const expenses = ledgers.filter(l => l.nature === 'EXPENSE').length;
    return { total: ledgers.length, assets, liabilities, income, expenses };
  }, [ledgers]);

  // Tax Summary Calculation (Input Tax Credit vs Output Tax Liability)
  const taxSummary = useMemo(() => {
    let inputCgst = 0;
    let inputSgst = 0;
    let inputIgst = 0;
    let otherInput = 0;

    let outputCgst = 0;
    let outputSgst = 0;
    let outputIgst = 0;
    let otherOutput = 0;

    let taxLedgersCount = 0;

    ledgers.forEach(l => {
      const isTax =
        l.ledger_type === 'TAX' ||
        l.group?.toLowerCase().includes('duties') ||
        l.group?.toLowerCase().includes('tax') ||
        /^(input|output)\s+(cgst|sgst|igst|tax)/i.test(l.name) ||
        /^(cgst|sgst|igst)$/i.test(l.name);

      if (!isTax) return;
      taxLedgersCount++;

      const isCreditType = l.opening_balance_type === 'CREDIT';
      const raw = Number(l.current_balance || 0);
      const netDebit = isCreditType ? -raw : raw;
      const netCredit = isCreditType ? raw : -raw;
      const name = l.name.toLowerCase();

      if (name.includes('input') || (!name.includes('output') && netDebit > 0)) {
        const val = Math.max(0, netDebit);
        if (name.includes('cgst')) inputCgst += val;
        else if (name.includes('sgst') || name.includes('utgst')) inputSgst += val;
        else if (name.includes('igst')) inputIgst += val;
        else otherInput += val;
      } else if (name.includes('output') || (!name.includes('input') && netCredit > 0)) {
        const val = Math.max(0, netCredit);
        if (name.includes('cgst')) outputCgst += val;
        else if (name.includes('sgst') || name.includes('utgst')) outputSgst += val;
        else if (name.includes('igst')) outputIgst += val;
        else otherOutput += val;
      }
    });

    const totalInput = inputCgst + inputSgst + inputIgst + otherInput;
    const totalOutput = outputCgst + outputSgst + outputIgst + otherOutput;
    const netDiff = totalOutput - totalInput;

    return {
      inputCgst,
      inputSgst,
      inputIgst,
      otherInput,
      totalInput,
      outputCgst,
      outputSgst,
      outputIgst,
      otherOutput,
      totalOutput,
      netPayable: netDiff > 0 ? netDiff : 0,
      netItcCarryForward: netDiff < 0 ? Math.abs(netDiff) : 0,
      taxLedgersCount,
    };
  }, [ledgers]);

  // Filtering
  const filteredLedgers = useMemo(() => {
    return ledgers.filter(l => {
      if (activeTab === 'TAX') {
        const isTax =
          l.ledger_type === 'TAX' ||
          l.group?.toLowerCase().includes('duties') ||
          l.group?.toLowerCase().includes('tax') ||
          /^(input|output)\s+(cgst|sgst|igst|tax)/i.test(l.name) ||
          /^(cgst|sgst|igst)$/i.test(l.name);
        if (!isTax) return false;
      } else if (activeTab !== 'ALL' && l.nature !== activeTab) {
        return false;
      }
      if (searchTerm.trim()) {
        const q = searchTerm.toLowerCase();
        const matchName = l.name?.toLowerCase().includes(q);
        const matchGroup = l.group?.toLowerCase().includes(q);
        const matchGstin = l.gstin?.toLowerCase().includes(q);
        const matchType = l.ledger_type?.toLowerCase().includes(q);
        return matchName || matchGroup || matchGstin || matchType;
      }
      return true;
    });
  }, [ledgers, activeTab, searchTerm]);

  return (
    <DashboardLayout>
      <div className="max-w-[1600px] mx-auto p-4 sm:p-6 space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-card border border-border p-6 rounded-2xl shadow-sm">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
              <BookOpen className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-foreground tracking-tight">Chart of Accounts</h1>
              <p className="text-sm text-muted-foreground">
                Manage financial ledgers, primary group hierarchies, and double-entry safeguards
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 w-full sm:w-auto">
            <button
              onClick={fetchLedgers}
              className="p-2.5 rounded-xl border border-border hover:bg-muted text-muted-foreground hover:text-foreground transition-all cursor-pointer"
              title="Refresh Accounts"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={handleOpenAddModal}
              className="flex-1 sm:flex-initial flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-sm font-medium transition-all shadow-md shadow-blue-500/10 cursor-pointer"
            >
              <Plus className="w-4 h-4" />
              <span>New Account Head</span>
            </button>
          </div>
        </div>

        {/* KPI Metrics */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <div className="bg-card border border-border p-4 rounded-xl shadow-2xs">
            <div className="text-xs text-muted-foreground font-medium">Total Ledgers</div>
            <div className="text-2xl font-bold text-foreground mt-1">{metrics.total}</div>
          </div>
          <div className="bg-card border border-border p-4 rounded-xl shadow-2xs">
            <div className="text-xs text-blue-400 font-medium flex items-center gap-1">
              <Wallet className="w-3.5 h-3.5" /> Assets
            </div>
            <div className="text-2xl font-bold text-blue-400 mt-1">{metrics.assets}</div>
          </div>
          <div className="bg-card border border-border p-4 rounded-xl shadow-2xs">
            <div className="text-xs text-amber-400 font-medium flex items-center gap-1">
              <Building2 className="w-3.5 h-3.5" /> Liabilities
            </div>
            <div className="text-2xl font-bold text-amber-400 mt-1">{metrics.liabilities}</div>
          </div>
          <div className="bg-card border border-border p-4 rounded-xl shadow-2xs">
            <div className="text-xs text-emerald-400 font-medium flex items-center gap-1">
              <ArrowDownLeft className="w-3.5 h-3.5" /> Incomes
            </div>
            <div className="text-2xl font-bold text-emerald-400 mt-1">{metrics.income}</div>
          </div>
          <div className="bg-card border border-border p-4 rounded-xl shadow-2xs">
            <div className="text-xs text-rose-400 font-medium flex items-center gap-1">
              <ArrowUpRight className="w-3.5 h-3.5" /> Expenses
            </div>
            <div className="text-2xl font-bold text-rose-400 mt-1">{metrics.expenses}</div>
          </div>
        </div>

        {/* GST Tax Position (Input vs. Output Summary) */}
        <div className="bg-card border border-border rounded-2xl p-5 shadow-sm space-y-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-border/60 pb-3">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
                <Receipt className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-bold text-foreground">GST Tax Summary</h2>
                  <span className="text-[11px] bg-purple-500/10 text-purple-400 border border-purple-500/20 px-2 py-0.5 rounded-full font-medium">
                    Input Tax Credit vs. Output Liability
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">
                  Live statutory balance aggregated across all Duties &amp; Taxes ledgers
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 w-full sm:w-auto">
              <button
                onClick={() => {
                  setActiveTab('TAX');
                  setSearchTerm('');
                }}
                className={`px-3 py-1.5 rounded-lg border text-xs font-medium transition-all flex items-center justify-center gap-1.5 cursor-pointer w-full sm:w-auto ${
                  activeTab === 'TAX'
                    ? 'bg-purple-600 text-white border-purple-600 shadow-sm'
                    : 'border-purple-500/30 bg-purple-500/10 hover:bg-purple-500/20 text-purple-300'
                }`}
              >
                <span>Filter Tax Ledgers</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => setIsGstWidgetExpanded(!isGstWidgetExpanded)}
                className="p-1.5 rounded-lg border border-border/60 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                title={isGstWidgetExpanded ? 'Collapse GST Summary' : 'Expand GST Summary'}
              >
                {isGstWidgetExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {isGstWidgetExpanded && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-1">
              {/* Total Input Tax Credit (ITC) */}
              <div className="bg-muted/30 border border-border/80 rounded-xl p-4 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wide flex items-center gap-1">
                      <ArrowDownLeft className="w-3.5 h-3.5" /> Total Input Tax (ITC)
                    </span>
                    <span className="text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-1.5 py-0.5 rounded font-mono">
                      Purchases (Dr)
                    </span>
                  </div>
                  <div className="text-2xl font-bold font-mono text-emerald-400 mt-2">
                    ₹{taxSummary.totalInput.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    Total tax paid on purchases eligible for input credit
                  </p>
                </div>
                <div className="grid grid-cols-3 gap-2 mt-4 pt-3 border-t border-border/50 text-center font-mono">
                  <div className="bg-background/50 rounded p-1.5 border border-border/40">
                    <div className="text-[10px] text-muted-foreground font-sans">Input CGST</div>
                    <div className="text-xs font-semibold text-foreground mt-0.5">
                      ₹{taxSummary.inputCgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div className="bg-background/50 rounded p-1.5 border border-border/40">
                    <div className="text-[10px] text-muted-foreground font-sans">Input SGST</div>
                    <div className="text-xs font-semibold text-foreground mt-0.5">
                      ₹{taxSummary.inputSgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div className="bg-background/50 rounded p-1.5 border border-border/40">
                    <div className="text-[10px] text-muted-foreground font-sans">Input IGST</div>
                    <div className="text-xs font-semibold text-foreground mt-0.5">
                      ₹{taxSummary.inputIgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                </div>
              </div>

              {/* Total Output Tax Liability */}
              <div className="bg-muted/30 border border-border/80 rounded-xl p-4 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-amber-400 uppercase tracking-wide flex items-center gap-1">
                      <ArrowUpRight className="w-3.5 h-3.5" /> Total Output Tax
                    </span>
                    <span className="text-[10px] bg-amber-500/10 text-amber-400 border border-amber-500/20 px-1.5 py-0.5 rounded font-mono">
                      Sales (Cr)
                    </span>
                  </div>
                  <div className="text-2xl font-bold font-mono text-amber-400 mt-2">
                    ₹{taxSummary.totalOutput.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    Total tax collected on sales invoices payable to gov
                  </p>
                </div>
                <div className="grid grid-cols-3 gap-2 mt-4 pt-3 border-t border-border/50 text-center font-mono">
                  <div className="bg-background/50 rounded p-1.5 border border-border/40">
                    <div className="text-[10px] text-muted-foreground font-sans">Output CGST</div>
                    <div className="text-xs font-semibold text-foreground mt-0.5">
                      ₹{taxSummary.outputCgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div className="bg-background/50 rounded p-1.5 border border-border/40">
                    <div className="text-[10px] text-muted-foreground font-sans">Output SGST</div>
                    <div className="text-xs font-semibold text-foreground mt-0.5">
                      ₹{taxSummary.outputSgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div className="bg-background/50 rounded p-1.5 border border-border/40">
                    <div className="text-[10px] text-muted-foreground font-sans">Output IGST</div>
                    <div className="text-xs font-semibold text-foreground mt-0.5">
                      ₹{taxSummary.outputIgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                </div>
              </div>

              {/* Net GST Position */}
              <div
                className={`rounded-xl p-4 flex flex-col justify-between border ${
                  taxSummary.netPayable > 0
                    ? 'bg-rose-500/5 border-rose-500/20'
                    : taxSummary.netItcCarryForward > 0
                    ? 'bg-emerald-500/5 border-emerald-500/20'
                    : 'bg-muted/30 border-border/80'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-foreground uppercase tracking-wide flex items-center gap-1">
                      <Scale className="w-3.5 h-3.5 text-blue-400" /> Net GST Position
                    </span>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-medium ${
                        taxSummary.netPayable > 0
                          ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                          : taxSummary.netItcCarryForward > 0
                          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                          : 'bg-zinc-500/10 text-zinc-400 border border-zinc-500/20'
                      }`}
                    >
                      {taxSummary.netPayable > 0
                        ? 'Net Payable'
                        : taxSummary.netItcCarryForward > 0
                        ? 'ITC Surplus'
                        : 'Reconciled'}
                    </span>
                  </div>
                  <div
                    className={`text-2xl font-bold font-mono mt-2 ${
                      taxSummary.netPayable > 0
                        ? 'text-rose-400'
                        : taxSummary.netItcCarryForward > 0
                        ? 'text-emerald-400'
                        : 'text-foreground'
                    }`}
                  >
                    ₹{(taxSummary.netPayable || taxSummary.netItcCarryForward || 0).toLocaleString('en-IN', {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    {taxSummary.netPayable > 0
                      ? 'Net statutory liability to be paid after setting off input credit'
                      : taxSummary.netItcCarryForward > 0
                      ? 'Unutilized ITC surplus available to offset future sales liability'
                      : 'All input and output tax balances are completely balanced'}
                  </p>
                </div>

                <div className="mt-4 pt-3 border-t border-border/50 flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">Filing Action:</span>
                  <span
                    className={`font-semibold ${
                      taxSummary.netPayable > 0
                        ? 'text-rose-400'
                        : taxSummary.netItcCarryForward > 0
                        ? 'text-emerald-400'
                        : 'text-zinc-400'
                    }`}
                  >
                    {taxSummary.netPayable > 0
                      ? `Deposit ₹${taxSummary.netPayable.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
                      : taxSummary.netItcCarryForward > 0
                      ? `Carry forward ₹${taxSummary.netItcCarryForward.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
                      : 'Zero Tax Due'}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Search & Tabs Toolbar */}
        <div className="bg-card border border-border p-4 rounded-2xl shadow-sm space-y-3">
          <div className="flex flex-col md:flex-row items-center justify-between gap-3">
            {/* Tabs */}
            <div className="flex items-center gap-1 bg-muted/60 p-1 rounded-xl border border-border/60 w-full md:w-auto overflow-x-auto">
              {(['ALL', 'ASSET', 'LIABILITY', 'INCOME', 'EXPENSE', 'TAX'] as const).map(tab => {
                const isTaxTab = tab === 'TAX';
                return (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 ${
                      activeTab === tab
                        ? isTaxTab
                          ? 'bg-purple-600 text-white shadow-2xs font-semibold'
                          : 'bg-card text-foreground shadow-2xs font-semibold'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    {isTaxTab ? (
                      <>
                        <Receipt className="w-3.5 h-3.5" />
                        <span>Duties & Taxes (GST)</span>
                        <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono ${
                          activeTab === 'TAX' ? 'bg-purple-700 text-white' : 'bg-purple-500/15 text-purple-300'
                        }`}>
                          {taxSummary.taxLedgersCount}
                        </span>
                      </>
                    ) : tab === 'ALL' ? (
                      'All Heads'
                    ) : (
                      tab.charAt(0) + tab.slice(1).toLowerCase() + 's'
                    )}
                  </button>
                );
              })}
            </div>

            {/* Search Input */}
            <div className="relative w-full md:w-80">
              <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                placeholder="Search ledger, group, GSTIN..."
                className="w-full pl-9 pr-3 py-2 bg-muted/40 border border-border rounded-xl text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-blue-500/50"
              />
              {searchTerm && (
                <button
                  onClick={() => setSearchTerm('')}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground text-xs cursor-pointer"
                >
                  ✕
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Table View */}
        <div className="bg-card border border-border rounded-2xl shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-muted/40 text-muted-foreground border-b border-border uppercase tracking-wider font-semibold">
                <tr>
                  <th className="py-3 px-4">Account Head (Ledger)</th>
                  <th className="py-3 px-4">Parent Group</th>
                  <th className="py-3 px-4">Nature</th>
                  <th className="py-3 px-4">Type</th>
                  <th className="py-3 px-4">GSTIN / Contact</th>
                  <th className="py-3 px-4 text-right">Current Balance</th>
                  <th className="py-3 px-4 text-center">Status</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60 text-foreground">
                {loading ? (
                  <tr>
                    <td colSpan={8} className="text-center py-12 text-muted-foreground">
                      <div className="flex flex-col items-center justify-center gap-2">
                        <RefreshCw className="w-5 h-5 animate-spin text-blue-500" />
                        <span>Loading Chart of Accounts...</span>
                      </div>
                    </td>
                  </tr>
                ) : filteredLedgers.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="text-center py-12 text-muted-foreground">
                      <div className="flex flex-col items-center justify-center gap-2">
                        <BookOpen className="w-8 h-8 text-zinc-600" />
                        <span>No account heads found matching your filter.</span>
                      </div>
                    </td>
                  </tr>
                ) : (
                  filteredLedgers.map(l => (
                    <tr
                      key={l.id}
                      onClick={() => router.push(`/ledgers/${l.id}/statement`)}
                      className="hover:bg-muted/30 transition-colors cursor-pointer group"
                    >
                      <td className="py-3 px-4 font-medium">
                        <div className="flex items-center gap-2">
                          <Link
                            href={`/ledgers/${l.id}/statement`}
                            onClick={e => e.stopPropagation()}
                            className="font-semibold text-sm group-hover:text-blue-400 group-hover:underline transition-colors flex items-center gap-1"
                            title="View Account Statement & Invoices"
                          >
                            <span>{l.name}</span>
                            <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 text-blue-400 transition-opacity" />
                          </Link>
                          {Number(l.discount_percent || 0) > 0 && (
                            <span className="text-[10px] bg-blue-500/10 text-blue-400 border border-blue-500/20 px-1.5 py-0.2 rounded font-mono">
                              {Number(l.discount_percent)}% Disc
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-3 px-4 text-muted-foreground">
                        <span className="inline-flex items-center gap-1 font-medium text-foreground">
                          <Layers className="w-3 h-3 text-zinc-500" />
                          {l.group}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase ${
                            l.nature === 'ASSET'
                              ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                              : l.nature === 'LIABILITY'
                              ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                              : l.nature === 'INCOME'
                              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                              : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                          }`}
                        >
                          {l.nature}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-muted-foreground font-mono text-[11px]">
                        {l.ledger_type}
                      </td>
                      <td className="py-3 px-4 text-muted-foreground">
                        {l.gstin ? (
                          <div className="font-mono text-zinc-300">{l.gstin}</div>
                        ) : l.phone ? (
                          <div>{l.phone}</div>
                        ) : (
                          <span className="text-zinc-600">—</span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right font-mono font-medium">
                        {(() => {
                          const isCreditType = l.opening_balance_type === 'CREDIT';
                          const raw = Number(l.current_balance || 0);
                          const isDr = isCreditType ? raw < 0 : raw >= 0;
                          const absVal = Math.abs(raw);
                          return (
                            <div className="inline-flex items-center justify-end gap-1">
                              <span className={isDr ? 'text-foreground' : 'text-amber-400'}>
                                ₹{absVal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                              </span>
                              <span
                                className={`text-[10px] font-semibold px-1 py-0.2 rounded ${
                                  isDr
                                    ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                                    : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                                }`}
                              >
                                {isDr ? 'Dr' : 'Cr'}
                              </span>
                            </div>
                          );
                        })()}
                      </td>
                      <td className="py-3 px-4 text-center">
                        <span
                          className={`inline-block w-2 h-2 rounded-full ${
                            l.is_active !== false ? 'bg-emerald-400' : 'bg-zinc-500'
                          }`}
                          title={l.is_active !== false ? 'Active' : 'Archived'}
                        />
                      </td>
                      <td className="py-3 px-4 text-right" onClick={e => e.stopPropagation()}>
                        <div className="flex items-center justify-end gap-1.5">
                          <Link
                            href={`/ledgers/${l.id}/statement`}
                            className="p-1.5 rounded-lg border border-border/60 hover:bg-blue-500/10 text-muted-foreground hover:text-blue-400 transition-colors cursor-pointer"
                            title="View Account Statement & Invoices"
                          >
                            <FileText className="w-3.5 h-3.5" />
                          </Link>
                          <button
                            onClick={e => {
                              e.stopPropagation();
                              handleOpenEditModal(l);
                            }}
                            className="p-1.5 rounded-lg border border-border/60 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                            title="Edit Account Head"
                          >
                            <Edit2 className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={e => {
                              e.stopPropagation();
                              setDeleteError('');
                              setDeletingLedger(l);
                            }}
                            className="p-1.5 rounded-lg border border-border/60 hover:bg-rose-500/10 text-muted-foreground hover:text-rose-400 transition-colors cursor-pointer"
                            title="Delete Account Head"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* ───── ADD ACCOUNT HEAD MODAL ───── */}
        {isAddModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in">
            <div className="bg-card border border-border rounded-2xl max-w-xl w-full p-6 shadow-2xl space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-border">
                <div className="flex items-center gap-2">
                  <BookOpen className="w-5 h-5 text-blue-400" />
                  <h3 className="text-lg font-bold text-foreground">Create Account Head</h3>
                </div>
                <button
                  onClick={() => setIsAddModalOpen(false)}
                  className="text-muted-foreground hover:text-foreground p-1 rounded-lg cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <form onSubmit={handleCreateLedger} className="space-y-4 text-xs">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="sm:col-span-2">
                    <label className="block text-muted-foreground font-medium mb-1">Account Head Name *</label>
                    <input
                      required
                      type="text"
                      value={formData.name}
                      onChange={e => setFormData({ ...formData, name: e.target.value })}
                      placeholder="e.g. HDFC Bank Ltd, Freight Inward, Ramesh & Co"
                      className="w-full bg-muted/30 border border-border text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-muted-foreground font-medium mb-1">Parent Group *</label>
                    <select
                      value={formData.group_id}
                      onChange={e => {
                        const sel = groups.find(g => g.id === e.target.value);
                        setFormData({
                          ...formData,
                          group_id: e.target.value,
                          nature: (sel?.nature as any) || 'ASSET',
                        });
                      }}
                      className="w-full bg-muted/30 border border-border text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                    >
                      {groups.map(g => (
                        <option key={g.id} value={g.id}>
                          {g.name} ({g.nature})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-muted-foreground font-medium mb-1">Ledger Type</label>
                    <select
                      value={formData.ledger_type}
                      onChange={e => setFormData({ ...formData, ledger_type: e.target.value })}
                      className="w-full bg-muted/30 border border-border text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                    >
                      <option value="GENERAL">GENERAL</option>
                      <option value="BANK">BANK</option>
                      <option value="CASH">CASH</option>
                      <option value="CUSTOMER">CUSTOMER (Debtor)</option>
                      <option value="SUPPLIER">SUPPLIER (Creditor)</option>
                      <option value="TAX">TAX (Duties)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-muted-foreground font-medium mb-1">Opening Balance (₹)</label>
                    <input
                      type="number"
                      step="0.01"
                      value={formData.opening_balance}
                      onChange={e => setFormData({ ...formData, opening_balance: e.target.value })}
                      placeholder="0.00"
                      className="w-full bg-muted/30 border border-border text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-muted-foreground font-medium mb-1">Balance Type</label>
                    <select
                      value={formData.opening_balance_type}
                      onChange={e => setFormData({ ...formData, opening_balance_type: e.target.value as any })}
                      className="w-full bg-muted/30 border border-border text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                    >
                      <option value="DEBIT">Debit (Asset / Expense)</option>
                      <option value="CREDIT">Credit (Liability / Income)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-muted-foreground font-medium mb-1">GSTIN (Optional)</label>
                    <input
                      type="text"
                      value={formData.gstin}
                      onChange={e => setFormData({ ...formData, gstin: e.target.value.toUpperCase() })}
                      placeholder="27AAAAA0000A1Z5"
                      className="w-full bg-muted/30 border border-border text-foreground p-2.5 rounded-lg text-xs font-mono uppercase focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-muted-foreground font-medium mb-1">Default Discount %</label>
                    <input
                      type="number"
                      step="0.01"
                      value={formData.discount_percent}
                      onChange={e => setFormData({ ...formData, discount_percent: e.target.value })}
                      placeholder="0.00"
                      className="w-full bg-muted/30 border border-border text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-muted-foreground font-medium mb-1">Phone / Mobile</label>
                    <input
                      type="text"
                      value={formData.phone}
                      onChange={e => setFormData({ ...formData, phone: e.target.value })}
                      placeholder="e.g. 9876543210"
                      className="w-full bg-muted/30 border border-border text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-muted-foreground font-medium mb-1">Email</label>
                    <input
                      type="email"
                      value={formData.email}
                      onChange={e => setFormData({ ...formData, email: e.target.value })}
                      placeholder="account@company.com"
                      className="w-full bg-muted/30 border border-border text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </div>

                  <div className="sm:col-span-2">
                    <label className="block text-muted-foreground font-medium mb-1">Address</label>
                    <textarea
                      rows={2}
                      value={formData.address}
                      onChange={e => setFormData({ ...formData, address: e.target.value })}
                      placeholder="Street, City, State, PIN"
                      className="w-full bg-muted/30 border border-border text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </div>
                </div>

                <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
                  <button
                    type="button"
                    onClick={() => setIsAddModalOpen(false)}
                    className="px-4 py-2 rounded-lg border border-border hover:bg-muted text-muted-foreground text-xs font-medium cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium transition-all cursor-pointer"
                  >
                    {isSubmitting ? 'Creating...' : 'Create Account'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* ───── EDIT ACCOUNT HEAD MODAL ───── */}
        {editingLedger && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in">
            <div className="bg-card border border-border rounded-2xl max-w-xl w-full p-6 shadow-2xl space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-border">
                <div className="flex items-center gap-2">
                  <Edit2 className="w-5 h-5 text-blue-400" />
                  <h3 className="text-lg font-bold text-foreground">Edit Account Head</h3>
                </div>
                <button
                  onClick={() => setEditingLedger(null)}
                  className="text-muted-foreground hover:text-foreground p-1 rounded-lg cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <form onSubmit={handleUpdateLedger} className="space-y-4 text-xs">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="sm:col-span-2">
                    <label className="block text-muted-foreground font-medium mb-1">Account Head Name *</label>
                    <input
                      required
                      type="text"
                      value={formData.name}
                      onChange={e => setFormData({ ...formData, name: e.target.value })}
                      className="w-full bg-muted/30 border border-border text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-muted-foreground font-medium mb-1">Parent Group</label>
                    <select
                      value={formData.group_id}
                      onChange={e => setFormData({ ...formData, group_id: e.target.value })}
                      className="w-full bg-muted/30 border border-border text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                    >
                      {groups.map(g => (
                        <option key={g.id} value={g.id}>
                          {g.name} ({g.nature})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-muted-foreground font-medium mb-1">Ledger Type</label>
                    <select
                      value={formData.ledger_type}
                      onChange={e => setFormData({ ...formData, ledger_type: e.target.value })}
                      className="w-full bg-muted/30 border border-border text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                    >
                      <option value="GENERAL">GENERAL</option>
                      <option value="BANK">BANK</option>
                      <option value="CASH">CASH</option>
                      <option value="CUSTOMER">CUSTOMER (Debtor)</option>
                      <option value="SUPPLIER">SUPPLIER (Creditor)</option>
                      <option value="TAX">TAX (Duties)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-muted-foreground font-medium mb-1">Opening Balance (₹)</label>
                    <input
                      type="number"
                      step="0.01"
                      value={formData.opening_balance}
                      onChange={e => setFormData({ ...formData, opening_balance: e.target.value })}
                      className="w-full bg-muted/30 border border-border text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-muted-foreground font-medium mb-1">Default Discount %</label>
                    <input
                      type="number"
                      step="0.01"
                      value={formData.discount_percent}
                      onChange={e => setFormData({ ...formData, discount_percent: e.target.value })}
                      className="w-full bg-muted/30 border border-border text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-muted-foreground font-medium mb-1">GSTIN</label>
                    <input
                      type="text"
                      value={formData.gstin}
                      onChange={e => setFormData({ ...formData, gstin: e.target.value.toUpperCase() })}
                      className="w-full bg-muted/30 border border-border text-foreground p-2.5 rounded-lg text-xs font-mono uppercase focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-muted-foreground font-medium mb-1">Phone</label>
                    <input
                      type="text"
                      value={formData.phone}
                      onChange={e => setFormData({ ...formData, phone: e.target.value })}
                      className="w-full bg-muted/30 border border-border text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </div>

                  <div className="sm:col-span-2 flex items-center gap-2 pt-2">
                    <input
                      type="checkbox"
                      id="is_active_chk"
                      checked={formData.is_active}
                      onChange={e => setFormData({ ...formData, is_active: e.target.checked })}
                      className="rounded border-border text-blue-600 focus:ring-blue-500"
                    />
                    <label htmlFor="is_active_chk" className="text-foreground font-medium cursor-pointer">
                      Active (uncheck to archive this ledger from invoice pickers)
                    </label>
                  </div>
                </div>

                <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
                  <button
                    type="button"
                    onClick={() => setEditingLedger(null)}
                    className="px-4 py-2 rounded-lg border border-border hover:bg-muted text-muted-foreground text-xs font-medium cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium transition-all cursor-pointer"
                  >
                    {isSubmitting ? 'Saving...' : 'Save Changes'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* ───── DELETE SAFETY CONFIRMATION MODAL ───── */}
        {deletingLedger && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in">
            <div className="bg-card border border-border rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4">
              <div className="flex items-center gap-3 text-rose-400">
                <ShieldAlert className="w-6 h-6 shrink-0" />
                <h3 className="text-lg font-bold text-foreground">Delete Account Head?</h3>
              </div>

              <p className="text-xs text-muted-foreground">
                You are about to delete <strong className="text-foreground">"{deletingLedger.name}"</strong> ({deletingLedger.group}).
              </p>

              {deleteError ? (
                <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-rose-400 text-xs space-y-1">
                  <div className="font-semibold flex items-center gap-1.5">
                    <Lock className="w-3.5 h-3.5" /> Double-Entry Integrity Protection
                  </div>
                  <div>{deleteError}</div>
                  <div className="text-[11px] text-zinc-400 mt-1">
                    Tip: Instead of deleting, edit this ledger and uncheck "Active" to safely archive it.
                  </div>
                </div>
              ) : (
                <div className="text-[11px] text-zinc-500 bg-muted/40 p-3 rounded-lg border border-border/60">
                  ⚠️ Double-entry constraint: Ledgers with posted transactions cannot be deleted to preserve financial history and audit trails.
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setDeletingLedger(null)}
                  className="px-4 py-2 rounded-lg border border-border hover:bg-muted text-muted-foreground text-xs font-medium cursor-pointer"
                >
                  Close
                </button>
                {!deleteError && (
                  <button
                    type="button"
                    onClick={handleDeleteLedger}
                    disabled={isSubmitting}
                    className="px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-xs font-medium transition-all cursor-pointer"
                  >
                    {isSubmitting ? 'Verifying & Deleting...' : 'Confirm Delete'}
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
