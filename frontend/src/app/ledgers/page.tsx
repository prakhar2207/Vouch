"use client";
import React, { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { API_BASE_URL } from '@/utils/api';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import { useToast } from '@/context/ToastContext';
import { useCompany } from '@/context/CompanyContext';
import { useFinancialYear } from '@/context/FinancialYearContext';
import SemanticBalance from '@/components/accounting/SemanticBalance';
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
  ArrowRight,
  Calendar,
  Filter
} from 'lucide-react';
import { ledgersRepository } from '@/lib/data';
import { offlineDb, SyncedLedger } from '@/lib/db/offlineDb';
import { PeriodPreset, computePeriodDateRange, formatFriendlyDate } from '@/utils/periodRanges';
import { gstApi } from '@/lib/api/gst';

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
  balance_state?: string;
  display_amount?: number;
  normal_balance?: string;
  balance_direction?: string;
  canonical_role?: string;
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
  const { companyId: activeCompanyId } = useCompany();
  const { activeFY } = useFinancialYear();

  const [companyId, setCompanyId] = useState('');
  const [ledgers, setLedgers] = useState<LedgerItem[]>([]);
  const [groups, setGroups] = useState<LedgerGroupItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeTab, setActiveTab] = useState<'ALL' | 'ASSET' | 'LIABILITY' | 'INCOME' | 'EXPENSE' | 'TAX'>('ALL');
  const [isGstWidgetExpanded, setIsGstWidgetExpanded] = useState(true);

  // GST Tax Summary Period Filtering
  const [gstPeriodPreset, setGstPeriodPreset] = useState<PeriodPreset>('ALL');
  const [gstCustomStart, setGstCustomStart] = useState('');
  const [gstCustomEnd, setGstCustomEnd] = useState('');
  const [filterLedgersByGstPeriod, setFilterLedgersByGstPeriod] = useState(false);
  const [loadingGstPeriod, setLoadingGstPeriod] = useState(false);
  const [gstPeriodSummary, setGstPeriodSummary] = useState<{
    totalInput: number;
    inputCgst: number;
    inputSgst: number;
    inputIgst: number;
    otherInput: number;
    totalOutput: number;
    outputCgst: number;
    outputSgst: number;
    outputIgst: number;
    otherOutput: number;
    netPayable: number;
    netItcCarryForward: number;
    statusHeadline?: string;
    statusBadge?: string;
    statusExplanation?: string;
  } | null>(null);

  const activeGstDateRange = useMemo(() => {
    return computePeriodDateRange(gstPeriodPreset, activeFY, gstCustomStart, gstCustomEnd);
  }, [gstPeriodPreset, activeFY, gstCustomStart, gstCustomEnd]);

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
  }, [router, activeCompanyId, activeFY?.id, filterLedgersByGstPeriod, activeGstDateRange.startDate, activeGstDateRange.endDate]);

  // Fetch period-specific GSTR-3B summary when a period preset is active
  useEffect(() => {
    let isCancelled = false;

    const loadGstPeriodData = async () => {
      if (gstPeriodPreset === 'ALL') {
        setGstPeriodSummary(null);
        setLoadingGstPeriod(false);
        return;
      }

      const { startDate, endDate } = activeGstDateRange;
      if (!startDate || !endDate) return;

      const cid = companyId || activeCompanyId;
      if (!cid) return;

      setLoadingGstPeriod(true);
      try {
        const res = await gstApi.getGSTR3BSummary(cid, startDate, endDate);
        if (isCancelled) return;

        if (res && res.summary) {
          const sum = res.summary || {};
          const t31 = res.table_3_1_outward_supplies || {};
          const t4 = res.table_4_eligible_itc || {};
          const net = res.net_tax_payable || {};

          setGstPeriodSummary({
            totalInput: Number(sum.itc_total ?? t4.total ?? 0),
            inputCgst: Number(t4.cgst ?? 0),
            inputSgst: Number(t4.sgst ?? 0),
            inputIgst: Number(t4.igst ?? 0),
            otherInput: 0,
            totalOutput: Number(sum.outward_tax_total ?? t31.total_tax ?? 0),
            outputCgst: Number(t31.cgst ?? 0),
            outputSgst: Number(t31.sgst ?? 0),
            outputIgst: Number(t31.igst ?? 0),
            otherOutput: 0,
            netPayable: Number(sum.net_cash_payable ?? net.total ?? 0),
            netItcCarryForward: Number(sum.excess_itc_claimable ?? 0),
            statusHeadline: sum.status_headline,
            statusBadge: sum.status_badge,
            statusExplanation: sum.status_explanation,
          });
        }
      } catch (err) {
        console.warn('[Ledgers] Failed to fetch GSTR-3B summary for period:', err);
      } finally {
        if (!isCancelled) {
          setLoadingGstPeriod(false);
        }
      }
    };

    loadGstPeriodData();
    return () => {
      isCancelled = true;
    };
  }, [gstPeriodPreset, activeGstDateRange.startDate, activeGstDateRange.endDate, companyId, activeCompanyId]);

  const fetchLedgers = async () => {
    setLoading(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      let cid = activeCompanyId;
      if (!cid) {
        const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
        cid = compRes.data?.data?.[0]?.id || compRes.data?.[0]?.id;
      }
      if (!cid) return;
      setCompanyId(cid);

      // 1. Fetch groups locally or from server first
      let grpList: LedgerGroupItem[] = [];
      const cachedGroups = await offlineDb.masters.get('ledger_groups').catch(() => null);
      if (cachedGroups?.data?.length) {
        grpList = cachedGroups.data;
        setGroups(grpList);
      } else {
        const groupsRes = await axios.get(`${API_BASE_URL}/api/v1/ledgers/${cid}/groups/`, { headers }).catch(() => ({ data: { data: [] } }));
        grpList = groupsRes.data?.data || [];
        setGroups(grpList);
        if (grpList.length > 0) {
          offlineDb.masters.put({ key: 'ledger_groups', data: grpList, updatedAt: Date.now() }).catch(() => {});
        }
      }

      const shouldUsePeriod = filterLedgersByGstPeriod && gstPeriodPreset !== 'ALL';
      const sDate = shouldUsePeriod ? activeGstDateRange.startDate : activeFY?.start_date;
      const eDate = shouldUsePeriod ? activeGstDateRange.endDate : activeFY?.end_date;

      // 2. Read ledgers locally first for instant UI response (scoped to active FY or selected period)
      const { data: localLedgers } = await ledgersRepository.getLedgers(cid, {
        financialYearId: shouldUsePeriod ? undefined : activeFY?.id,
        startDate: sDate,
        endDate: eDate,
        scopeTaxes: shouldUsePeriod,
      });
      if (localLedgers && localLedgers.length > 0) {
        const mappedLocal: LedgerItem[] = localLedgers.map((l: any) => {
          const grp = grpList.find(g => g.id === (l.group_id || l.groupId) || g.name === l.group);
          return {
            id: String(l.id),
            name: l.name,
            group_id: l.group_id ? String(l.group_id) : (grp?.id || undefined),
            group: l.group || grp?.name || 'General',
            nature: ((l.nature || grp?.nature || 'ASSET') as string).toUpperCase() as any,
            ledger_type: l.ledgerType || l.ledger_type || 'GENERAL',
            gstin: l.gstin || '',
            state_code: l.stateCode || l.state_code || '',
            phone: l.phone || '',
            email: l.email || '',
            address: l.address || '',
            current_balance: Number(l.currentBalance ?? l.current_balance) || 0,
            opening_balance: Number(l.openingBalance ?? l.opening_balance) || 0,
            opening_balance_type: l.openingBalanceType || l.opening_balance_type || 'DEBIT',
            discount_percent: Number(l.discount_percent) || 0,
            is_active: l.is_active ?? true,
            canonical_role: l.canonical_role || l.canonicalRole,
            balance_state: l.balance_state || l.balanceState,
            display_amount: (l.display_amount ?? l.displayAmount) !== undefined ? Number(l.display_amount ?? l.displayAmount) : undefined,
            normal_balance: l.normal_balance || l.normalBalance,
            balance_direction: l.balance_direction || l.balanceDirection,
          };
        });
        setLedgers(mappedLocal);
      }

      // 3. Fetch authoritative fresh ledgers with full nature & group from server
      const params: Record<string, string> = {};
      if (shouldUsePeriod) {
        if (sDate) params.start_date = sDate;
        if (eDate) params.end_date = eDate;
        params.scope_taxes = 'true';
      } else {
        if (activeFY?.id) params.financial_year_id = activeFY.id;
        if (activeFY?.start_date) params.start_date = activeFY.start_date;
        if (activeFY?.end_date) params.end_date = activeFY.end_date;
      }

      const res = await axios.get(`${API_BASE_URL}/api/v1/ledgers/${cid}/`, { headers, params }).catch((err) => {
        console.warn("[Ledgers] Server fetch error:", err);
        return null;
      });

      if (res?.data?.data && Array.isArray(res.data.data)) {
        const serverLedgers: LedgerItem[] = res.data.data.map((l: any) => {
          const grp = grpList.find(g => g.id === l.group_id || g.name === l.group);
          return {
            id: String(l.id),
            name: l.name,
            group_id: l.group_id ? String(l.group_id) : (grp?.id || undefined),
            group: l.group || grp?.name || 'General',
            nature: ((l.nature || grp?.nature || 'ASSET') as string).toUpperCase() as any,
            ledger_type: l.ledger_type || 'GENERAL',
            gstin: l.gstin || '',
            state_code: l.state_code || '',
            phone: l.phone || '',
            email: l.email || '',
            address: l.address || '',
            current_balance: Number(l.current_balance) || 0,
            opening_balance: Number(l.opening_balance) || 0,
            opening_balance_type: l.opening_balance_type || 'DEBIT',
            discount_percent: Number(l.discount_percent) || 0,
            is_active: l.is_active ?? true,
            canonical_role: l.canonical_role,
            balance_state: l.balance_state,
            display_amount: l.display_amount !== undefined ? Number(l.display_amount) : undefined,
            normal_balance: l.normal_balance,
            balance_direction: l.balance_direction,
          };
        });
        setLedgers(serverLedgers);

        // Update local Dexie cache with full nature & group & balances
        const toPut: SyncedLedger[] = serverLedgers.map((l) => ({
          id: l.id,
          companyId: cid!,
          name: l.name,
          ledgerType: l.ledger_type,
          group: l.group,
          group_id: l.group_id,
          nature: l.nature,
          gstin: l.gstin,
          stateCode: l.state_code,
          currentBalance: l.current_balance || 0,
          openingBalance: l.opening_balance || 0,
          openingBalanceType: l.opening_balance_type || 'DEBIT',
          phone: l.phone,
          canonical_role: l.canonical_role,
          balanceState: l.balance_state,
          displayAmount: l.display_amount,
          normalBalance: l.normal_balance,
          balanceDirection: l.balance_direction,
          serverUpdatedAt: Date.now(),
        }));
        await offlineDb.syncedLedgers.bulkPut(toPut).catch(() => {});
      }
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
    const assets = ledgers.filter(l => (l.nature || '').toUpperCase() === 'ASSET').length;
    const liabilities = ledgers.filter(l => (l.nature || '').toUpperCase() === 'LIABILITY').length;
    const income = ledgers.filter(l => (l.nature || '').toUpperCase() === 'INCOME').length;
    const expenses = ledgers.filter(l => (l.nature || '').toUpperCase() === 'EXPENSE').length;
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

      const raw = Number(l.current_balance || 0);
      const name = l.name.toLowerCase();
      const isInputName = name.includes('input');
      const isOutputName = name.includes('output');

      // Determine true net debit and net credit balance based on normal_balance / nature or balance_direction
      const isNormalCredit = l.normal_balance
        ? l.normal_balance === 'CREDIT'
        : (l.nature === 'LIABILITY' || l.nature === 'INCOME' || l.nature === 'EQUITY');

      // On a credit account: positive raw is credit (sales tax liability), negative raw is debit (ITC).
      // On a debit account: positive raw is debit (ITC), negative raw is credit.
      let netDebit = 0;
      let netCredit = 0;

      if (l.balance_direction === 'DEBIT') {
        netDebit = Math.abs(raw);
        netCredit = -netDebit;
      } else if (l.balance_direction === 'CREDIT') {
        netCredit = Math.abs(raw);
        netDebit = -netCredit;
      } else {
        netCredit = isNormalCredit ? raw : -raw;
        netDebit = -netCredit;
      }

      if (isInputName) {
        // Explicit input tax ledger (Input CGST, Input SGST, Input IGST)
        const val = netDebit > 0 ? netDebit : Math.abs(raw);
        if (name.includes('cgst')) inputCgst += val;
        else if (name.includes('sgst') || name.includes('utgst')) inputSgst += val;
        else if (name.includes('igst')) inputIgst += val;
        else otherInput += val;
      } else if (isOutputName) {
        // Explicit output tax ledger (Output CGST, Output SGST, Output IGST)
        const val = netCredit > 0 ? netCredit : Math.abs(raw);
        if (name.includes('cgst')) outputCgst += val;
        else if (name.includes('sgst') || name.includes('utgst')) outputSgst += val;
        else if (name.includes('igst')) outputIgst += val;
        else otherOutput += val;
      } else {
        // Generic tax account without 'input' or 'output' in name
        if (netCredit > 0) {
          const val = netCredit;
          if (name.includes('cgst')) outputCgst += val;
          else if (name.includes('sgst') || name.includes('utgst')) outputSgst += val;
          else if (name.includes('igst')) outputIgst += val;
          else otherOutput += val;
        } else if (netDebit > 0) {
          const val = netDebit;
          if (name.includes('cgst')) inputCgst += val;
          else if (name.includes('sgst') || name.includes('utgst')) inputSgst += val;
          else if (name.includes('igst')) inputIgst += val;
          else otherInput += val;
        }
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
      statusHeadline: undefined as string | undefined,
      statusBadge: undefined as string | undefined,
      statusExplanation: undefined as string | undefined,
    };
  }, [ledgers]);

  // If a specific period is selected, use period-scoped GSTR-3B summary when available; otherwise fallback to full FY ledger summary
  const effectiveGst = useMemo(() => {
    if (gstPeriodPreset !== 'ALL' && gstPeriodSummary) {
      return {
        ...gstPeriodSummary,
        taxLedgersCount: taxSummary.taxLedgersCount,
      };
    }
    return taxSummary;
  }, [gstPeriodPreset, gstPeriodSummary, taxSummary]);

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
      } else if (activeTab !== 'ALL' && (l.nature || '').toUpperCase() !== activeTab) {
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
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-card border border-border/40 p-6 rounded-2xl shadow-sm">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
              <BookOpen className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-2xl font-extrabold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">Accounts</h1>
                {activeFY && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-primary/10 text-primary border border-primary/20">
                    <span>FY {activeFY.code}</span>
                    <span className="text-muted-foreground font-normal text-[11px]">({activeFY.start_date} to {activeFY.end_date})</span>
                  </span>
                )}
              </div>
              <p className="text-sm text-muted-foreground">
                Manage your account heads and ledgers
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 w-full sm:w-auto">
            <button
              onClick={fetchLedgers}
              className="p-2.5 rounded-xl border border-border/40 hover:bg-muted text-muted-foreground hover:text-foreground transition-all cursor-pointer"
              title="Refresh Accounts"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={handleOpenAddModal}
              className="flex-1 sm:flex-initial flex items-center justify-center gap-2 px-4 py-2.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl text-sm font-medium transition-all shadow-md shadow-primary/20 cursor-pointer"
            >
              <Plus className="w-4 h-4" />
              <span>New Account Head</span>
            </button>
          </div>
        </div>

        {/* KPI Metrics */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <div className="bg-card border border-border/40 p-4 rounded-xl shadow-sm">
            <div className="text-xs text-muted-foreground font-medium">Total Ledgers</div>
            <div className="text-2xl font-bold text-foreground mt-1">{metrics.total}</div>
          </div>
          <div className="bg-card border border-border/40 p-4 rounded-xl shadow-sm">
            <div className="text-xs text-blue-400 font-medium flex items-center gap-1">
              <Wallet className="w-3.5 h-3.5" /> Assets
            </div>
            <div className="text-2xl font-bold text-blue-400 mt-1">{metrics.assets}</div>
          </div>
          <div className="bg-card border border-border/40 p-4 rounded-xl shadow-sm">
            <div className="text-xs text-amber-400 font-medium flex items-center gap-1">
              <Building2 className="w-3.5 h-3.5" /> Liabilities
            </div>
            <div className="text-2xl font-bold text-amber-400 mt-1">{metrics.liabilities}</div>
          </div>
          <div className="bg-card border border-border/40 p-4 rounded-xl shadow-sm">
            <div className="text-xs text-emerald-400 font-medium flex items-center gap-1">
              <ArrowDownLeft className="w-3.5 h-3.5" /> Incomes
            </div>
            <div className="text-2xl font-bold text-emerald-400 mt-1">{metrics.income}</div>
          </div>
          <div className="bg-card border border-border/40 p-4 rounded-xl shadow-sm">
            <div className="text-xs text-rose-400 font-medium flex items-center gap-1">
              <ArrowUpRight className="w-3.5 h-3.5" /> Expenses
            </div>
            <div className="text-2xl font-bold text-rose-400 mt-1">{metrics.expenses}</div>
          </div>
        </div>

        {/* GST Tax Position (Input vs. Output Summary) */}
        <div className="bg-card border border-border/40 rounded-2xl p-5 shadow-sm space-y-4">
          <div className="flex flex-col xl:flex-row items-start xl:items-center justify-between gap-3 border-b border-border/40 pb-3">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400 shrink-0">
                <Receipt className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <h2 className="text-base font-bold text-foreground">GST Tax Summary</h2>
                  <span className="text-[11px] bg-purple-500/10 text-purple-400 border border-purple-500/20 px-2 py-0.5 rounded-full font-medium">
                    Input Tax Credit vs. Output Liability
                  </span>
                  {activeGstDateRange.startDate && activeGstDateRange.endDate && (
                    <span className="text-[11px] bg-muted/80 text-foreground/80 border border-border/60 px-2 py-0.5 rounded-full font-mono font-medium flex items-center gap-1">
                      <Calendar className="w-3 h-3 text-purple-400" />
                      <span>{formatFriendlyDate(activeGstDateRange.startDate)} – {formatFriendlyDate(activeGstDateRange.endDate)}</span>
                    </span>
                  )}
                  {loadingGstPeriod && (
                    <span className="text-[10px] text-muted-foreground flex items-center gap-1 font-mono">
                      <RefreshCw className="w-3 h-3 animate-spin text-purple-400" />
                      <span>Calculating period...</span>
                    </span>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  Statutory tax liability &amp; eligible input credit aggregated for the selected period
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 w-full xl:w-auto">
              {/* Period Preset Pills */}
              <div className="flex items-center gap-1 bg-muted/70 p-1 rounded-xl border border-border/50 text-xs overflow-x-auto">
                <button
                  type="button"
                  onClick={() => setGstPeriodPreset('ALL')}
                  className={`px-2.5 py-1 rounded-lg font-semibold transition-all cursor-pointer whitespace-nowrap text-xs ${
                    gstPeriodPreset === 'ALL'
                      ? 'bg-background text-foreground shadow-xs'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  Full FY
                </button>
                <button
                  type="button"
                  onClick={() => setGstPeriodPreset('THIS_MONTH')}
                  className={`px-2.5 py-1 rounded-lg font-semibold transition-all cursor-pointer whitespace-nowrap text-xs ${
                    gstPeriodPreset === 'THIS_MONTH'
                      ? 'bg-background text-foreground shadow-xs'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  This Month
                </button>
                <button
                  type="button"
                  onClick={() => setGstPeriodPreset('LAST_MONTH')}
                  className={`px-2.5 py-1 rounded-lg font-semibold transition-all cursor-pointer whitespace-nowrap text-xs ${
                    gstPeriodPreset === 'LAST_MONTH'
                      ? 'bg-background text-foreground shadow-xs'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  Last Month
                </button>
                <button
                  type="button"
                  onClick={() => setGstPeriodPreset('THIS_QUARTER')}
                  className={`px-2.5 py-1 rounded-lg font-semibold transition-all cursor-pointer whitespace-nowrap text-xs ${
                    gstPeriodPreset === 'THIS_QUARTER'
                      ? 'bg-background text-foreground shadow-xs'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  This Quarter
                </button>
                <button
                  type="button"
                  onClick={() => setGstPeriodPreset('TODAY')}
                  className={`px-2.5 py-1 rounded-lg font-semibold transition-all cursor-pointer whitespace-nowrap text-xs ${
                    gstPeriodPreset === 'TODAY'
                      ? 'bg-background text-foreground shadow-xs'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  Today
                </button>
                <button
                  type="button"
                  onClick={() => setGstPeriodPreset('CUSTOM')}
                  className={`px-2.5 py-1 rounded-lg font-semibold transition-all cursor-pointer whitespace-nowrap text-xs ${
                    gstPeriodPreset === 'CUSTOM'
                      ? 'bg-background text-foreground shadow-xs'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  Custom
                </button>
              </div>

              {/* Table filter sync switch */}
              <button
                type="button"
                onClick={() => setFilterLedgersByGstPeriod(!filterLedgersByGstPeriod)}
                className={`px-2.5 py-1.5 rounded-xl border text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
                  filterLedgersByGstPeriod
                    ? 'bg-purple-500/10 text-purple-400 border-purple-500/30 shadow-xs'
                    : 'bg-muted/40 text-muted-foreground border-border/60 hover:text-foreground'
                }`}
                title="When enabled, the account heads table below will strictly show balances scoped to this period"
              >
                <Filter className="w-3.5 h-3.5" />
                <span>Filter Accounts</span>
                <span className={`w-2 h-2 rounded-full ${filterLedgersByGstPeriod ? 'bg-purple-500' : 'bg-muted-foreground/40'}`} />
              </button>

              <button
                onClick={() => {
                  setActiveTab('TAX');
                  setSearchTerm('');
                }}
                className={`px-3 py-1.5 rounded-lg border text-xs font-medium transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
                  activeTab === 'TAX'
                    ? 'bg-purple-600 text-foreground border-purple-600 shadow-sm'
                    : 'border-purple-500/30 bg-purple-500/10 hover:bg-purple-500/20 text-purple-300'
                }`}
                title="Jump to tax ledgers tab"
              >
                <span>Tax Ledgers</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>

              <button
                onClick={() => setIsGstWidgetExpanded(!isGstWidgetExpanded)}
                className="p-1.5 rounded-lg border border-border/40 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                title={isGstWidgetExpanded ? 'Collapse GST Summary' : 'Expand GST Summary'}
              >
                {isGstWidgetExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Custom Date Picker row if CUSTOM selected */}
          {gstPeriodPreset === 'CUSTOM' && (
            <div className="flex flex-wrap items-center gap-3 bg-muted/30 p-3 rounded-xl border border-border/40 text-xs">
              <span className="font-semibold text-muted-foreground">Select Date Range:</span>
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">From</span>
                <input
                  type="date"
                  value={gstCustomStart}
                  onChange={(e) => setGstCustomStart(e.target.value)}
                  className="bg-background border border-border rounded-lg px-2.5 py-1 text-xs text-foreground focus:outline-hidden focus:ring-1 focus:ring-purple-500"
                />
              </div>
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">To</span>
                <input
                  type="date"
                  value={gstCustomEnd}
                  onChange={(e) => setGstCustomEnd(e.target.value)}
                  className="bg-background border border-border rounded-lg px-2.5 py-1 text-xs text-foreground focus:outline-hidden focus:ring-1 focus:ring-purple-500"
                />
              </div>
              {(gstCustomStart || gstCustomEnd) && (
                <button
                  type="button"
                  onClick={() => {
                    setGstCustomStart('');
                    setGstCustomEnd('');
                  }}
                  className="text-xs text-muted-foreground hover:text-foreground underline cursor-pointer"
                >
                  Reset
                </button>
              )}
            </div>
          )}

          {isGstWidgetExpanded && (
            <div className={`grid grid-cols-1 md:grid-cols-3 gap-4 pt-1 transition-opacity ${loadingGstPeriod ? 'opacity-70' : 'opacity-100'}`}>
              {/* Total Input Tax Credit (ITC) */}
              <div className="bg-muted/30 border border-border/40 rounded-xl p-4 flex flex-col justify-between">
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
                    ₹{effectiveGst.totalInput.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    {gstPeriodPreset === 'ALL'
                      ? 'Total tax paid on purchases eligible for input credit'
                      : 'Eligible input credit from purchases in selected period'}
                  </p>
                </div>
                <div className="grid grid-cols-3 gap-2 mt-4 pt-3 border-t border-border/40 text-center font-mono">
                  <div className="bg-background/50 rounded p-1.5 border border-border/40">
                    <div className="text-[10px] text-muted-foreground font-sans">Input CGST</div>
                    <div className="text-xs font-semibold text-foreground mt-0.5">
                      ₹{effectiveGst.inputCgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div className="bg-background/50 rounded p-1.5 border border-border/40">
                    <div className="text-[10px] text-muted-foreground font-sans">Input SGST</div>
                    <div className="text-xs font-semibold text-foreground mt-0.5">
                      ₹{effectiveGst.inputSgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div className="bg-background/50 rounded p-1.5 border border-border/40">
                    <div className="text-[10px] text-muted-foreground font-sans">Input IGST</div>
                    <div className="text-xs font-semibold text-foreground mt-0.5">
                      ₹{effectiveGst.inputIgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                </div>
              </div>

              {/* Total Output Tax Liability */}
              <div className="bg-muted/30 border border-border/40 rounded-xl p-4 flex flex-col justify-between">
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
                    ₹{effectiveGst.totalOutput.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    {gstPeriodPreset === 'ALL'
                      ? 'Total tax collected on sales invoices payable to gov'
                      : 'Total tax collected on sales invoices in selected period'}
                  </p>
                </div>
                <div className="grid grid-cols-3 gap-2 mt-4 pt-3 border-t border-border/40 text-center font-mono">
                  <div className="bg-background/50 rounded p-1.5 border border-border/40">
                    <div className="text-[10px] text-muted-foreground font-sans">Output CGST</div>
                    <div className="text-xs font-semibold text-foreground mt-0.5">
                      ₹{effectiveGst.outputCgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div className="bg-background/50 rounded p-1.5 border border-border/40">
                    <div className="text-[10px] text-muted-foreground font-sans">Output SGST</div>
                    <div className="text-xs font-semibold text-foreground mt-0.5">
                      ₹{effectiveGst.outputSgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div className="bg-background/50 rounded p-1.5 border border-border/40">
                    <div className="text-[10px] text-muted-foreground font-sans">Output IGST</div>
                    <div className="text-xs font-semibold text-foreground mt-0.5">
                      ₹{effectiveGst.outputIgst.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                </div>
              </div>

              {/* Net GST Position */}
              <div
                className={`rounded-xl p-4 flex flex-col justify-between border ${
                  effectiveGst.netPayable > 0
                    ? 'bg-rose-500/5 border-rose-500/20'
                    : effectiveGst.netItcCarryForward > 0
                    ? 'bg-emerald-500/5 border-emerald-500/20'
                    : 'bg-muted/30 border-border/40'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-foreground uppercase tracking-wide flex items-center gap-1">
                      <Scale className="w-3.5 h-3.5 text-blue-400" /> Net GST Position
                    </span>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-medium ${
                        effectiveGst.statusBadge
                          ? (effectiveGst.statusBadge === 'CASH_PAYMENT_REQUIRED' ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20' : effectiveGst.statusBadge === 'EXCESS_ITC_AVAILABLE' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-zinc-500/10 text-zinc-400 border border-zinc-500/20')
                          : effectiveGst.netPayable > 0
                          ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                          : effectiveGst.netItcCarryForward > 0
                          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                          : 'bg-zinc-500/10 text-zinc-400 border border-zinc-500/20'
                      }`}
                    >
                      {effectiveGst.statusBadge
                        ? (effectiveGst.statusBadge === 'CASH_PAYMENT_REQUIRED' ? 'Net Payable' : effectiveGst.statusBadge === 'EXCESS_ITC_AVAILABLE' ? 'ITC Surplus' : 'Reconciled')
                        : effectiveGst.netPayable > 0
                        ? 'Net Payable'
                        : effectiveGst.netItcCarryForward > 0
                        ? 'ITC Surplus'
                        : 'Reconciled'}
                    </span>
                  </div>
                  <div
                    className={`text-2xl font-bold font-mono mt-2 ${
                      effectiveGst.netPayable > 0
                        ? 'text-rose-400'
                        : effectiveGst.netItcCarryForward > 0
                        ? 'text-emerald-400'
                        : 'text-foreground'
                    }`}
                  >
                    ₹{(effectiveGst.netPayable || effectiveGst.netItcCarryForward || 0).toLocaleString('en-IN', {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    {effectiveGst.statusExplanation ||
                      (effectiveGst.netPayable > 0
                        ? 'Net statutory liability to be paid after setting off input credit'
                        : effectiveGst.netItcCarryForward > 0
                        ? 'Unutilized ITC surplus available to offset future sales liability'
                        : 'All input and output tax balances are completely balanced')}
                  </p>
                </div>

                <div className="mt-4 pt-3 border-t border-border/40 flex items-center justify-between text-xs flex-wrap gap-2">
                  <span className="text-muted-foreground">Filing Action:</span>
                  <div className="flex items-center gap-2">
                    <span
                      className={`font-semibold ${
                        effectiveGst.netPayable > 0
                          ? 'text-rose-400'
                          : effectiveGst.netItcCarryForward > 0
                          ? 'text-emerald-400'
                          : 'text-zinc-400'
                      }`}
                    >
                      {effectiveGst.statusHeadline ||
                        (effectiveGst.netPayable > 0
                          ? `Deposit ₹${effectiveGst.netPayable.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
                          : effectiveGst.netItcCarryForward > 0
                          ? `Carry forward ₹${effectiveGst.netItcCarryForward.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
                          : 'Zero Tax Due')}
                    </span>
                    <Link
                      href="/gst/returns"
                      className="text-purple-400 hover:text-purple-300 hover:underline flex items-center gap-0.5 font-medium ml-1"
                      title="Open GST Returns Center"
                    >
                      <span>Returns</span>
                      <ExternalLink className="w-3 h-3" />
                    </Link>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Search & Tabs Toolbar */}
        <div className="bg-card border border-border/40 p-4 rounded-2xl shadow-sm space-y-3">
          <div className="flex flex-col md:flex-row items-center justify-between gap-3">
            {/* Tabs */}
            <div className="flex items-center gap-1 bg-muted/60 p-1 rounded-xl border border-border/40 w-full md:w-auto overflow-x-auto">
              {(['ALL', 'ASSET', 'LIABILITY', 'INCOME', 'EXPENSE', 'TAX'] as const).map(tab => {
                const isTaxTab = tab === 'TAX';
                return (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 ${
                      activeTab === tab
                        ? isTaxTab
                          ? 'bg-purple-600 text-foreground shadow-2xs font-semibold'
                          : 'bg-card text-foreground shadow-2xs font-semibold'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    {isTaxTab ? (
                      <>
                        <Receipt className="w-3.5 h-3.5" />
                        <span>Duties & Taxes (GST)</span>
                        <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono ${
                          activeTab === 'TAX' ? 'bg-purple-700 text-foreground' : 'bg-purple-500/15 text-purple-300'
                        }`}>
                          {taxSummary.taxLedgersCount}
                        </span>
                      </>
                    ) : tab === 'ALL' ? (
                      'All Heads'
                    ) : tab === 'LIABILITY' ? (
                      'Liabilities'
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
                className="w-full pl-9 pr-3 py-2 bg-muted/40 border border-border/40 rounded-xl text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
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
        <div className="bg-card border border-border/40 rounded-2xl shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-muted/30 text-muted-foreground border-b border-border/40 uppercase tracking-wider font-semibold">
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
              <tbody className="divide-y divide-border/40 text-foreground">
                {loading ? (
                  <tr>
                    <td colSpan={8} className="text-center py-12 text-muted-foreground">
                      <div className="flex flex-col items-center justify-center gap-2">
                        <RefreshCw className="w-5 h-5 animate-spin text-blue-500" />
                        <span>Loading accounts...</span>
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
                      <td className="py-3.5 px-4 text-muted-foreground font-mono text-xs">
                        {l.ledger_type}
                      </td>
                      <td className="py-3.5 px-4 text-muted-foreground">
                        {l.gstin ? (
                          <div className="font-mono text-foreground/80 font-medium text-xs">{l.gstin}</div>
                        ) : l.phone ? (
                          <div className="text-xs">{l.phone}</div>
                        ) : (
                          <span className="text-muted-foreground/60">—</span>
                        )}
                      </td>
                      <td className="py-3.5 px-4 text-right">
                        <SemanticBalance
                          balanceState={l.balance_state}
                          displayAmount={l.display_amount}
                          currentBalance={l.current_balance}
                          normalBalance={l.normal_balance}
                          balanceDirection={l.balance_direction}
                          size="sm"
                        />
                      </td>
                      <td className="py-3.5 px-4 text-center">
                        <span
                          className={`inline-block w-2.5 h-2.5 rounded-full ${
                            l.is_active !== false ? 'bg-emerald-400' : 'bg-zinc-500'
                          }`}
                          title={l.is_active !== false ? 'Active' : 'Archived'}
                        />
                      </td>
                      <td className="py-3.5 px-4 text-right" onClick={e => e.stopPropagation()}>
                        <div className="flex items-center justify-end gap-2">
                          <Link
                            href={`/ledgers/${l.id}/statement`}
                            className="p-2 rounded-lg border border-border/60 hover:bg-blue-500/10 text-muted-foreground hover:text-blue-400 transition-colors cursor-pointer min-h-[36px] min-w-[36px] flex items-center justify-center"
                            title="View Account Statement & Invoices"
                          >
                            <FileText className="w-4 h-4" />
                          </Link>
                          <button
                            onClick={e => {
                              e.stopPropagation();
                              handleOpenEditModal(l);
                            }}
                            className="p-2 rounded-lg border border-border/60 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer min-h-[36px] min-w-[36px] flex items-center justify-center"
                            title="Edit Account Head"
                          >
                            <Edit2 className="w-4 h-4" />
                          </button>
                          <button
                            onClick={e => {
                              e.stopPropagation();
                              setDeleteError('');
                              setDeletingLedger(l);
                            }}
                            className="p-2 rounded-lg border border-border/60 hover:bg-rose-500/10 text-muted-foreground hover:text-rose-400 transition-colors cursor-pointer min-h-[36px] min-w-[36px] flex items-center justify-center"
                            title="Delete Account Head"
                          >
                            <Trash2 className="w-4 h-4" />
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
            <div className="bg-card border border-border/40 rounded-2xl max-w-xl w-full p-6 shadow-2xl space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-border/40">
                <div className="flex items-center gap-2">
                  <BookOpen className="w-5 h-5 text-primary" />
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
                      className="w-full bg-muted/30 border border-border/60 text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-primary/40 outline-none"
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
                      className="w-full bg-muted/30 border border-border/60 text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-primary/40 outline-none"
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
                      className="w-full bg-muted/30 border border-border/60 text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-primary/40 outline-none"
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
                      className="w-full bg-muted/30 border border-border/60 text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-primary/40 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-muted-foreground font-medium mb-1">Balance Type</label>
                    <select
                      value={formData.opening_balance_type}
                      onChange={e => setFormData({ ...formData, opening_balance_type: e.target.value as any })}
                      className="w-full bg-muted/30 border border-border/60 text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-primary/40 outline-none"
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
                      className="w-full bg-muted/30 border border-border/60 text-foreground p-2.5 rounded-lg text-xs font-mono uppercase focus:ring-2 focus:ring-primary/40 outline-none"
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
                      className="w-full bg-muted/30 border border-border/60 text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-primary/40 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-muted-foreground font-medium mb-1">Phone / Mobile</label>
                    <input
                      type="text"
                      value={formData.phone}
                      onChange={e => setFormData({ ...formData, phone: e.target.value })}
                      placeholder="e.g. 9876543210"
                      className="w-full bg-muted/30 border border-border/60 text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-primary/40 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-muted-foreground font-medium mb-1">Email</label>
                    <input
                      type="email"
                      value={formData.email}
                      onChange={e => setFormData({ ...formData, email: e.target.value })}
                      placeholder="account@company.com"
                      className="w-full bg-muted/30 border border-border/60 text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-primary/40 outline-none"
                    />
                  </div>

                  <div className="sm:col-span-2">
                    <label className="block text-muted-foreground font-medium mb-1">Address</label>
                    <textarea
                      rows={2}
                      value={formData.address}
                      onChange={e => setFormData({ ...formData, address: e.target.value })}
                      placeholder="Street, City, State, PIN"
                      className="w-full bg-muted/30 border border-border/60 text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-primary/40 outline-none"
                    />
                  </div>
                </div>

                <div className="flex items-center justify-end gap-2 pt-3 border-t border-border/40">
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
                    className="px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-medium transition-all shadow-md shadow-primary/20 cursor-pointer"
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
            <div className="bg-card border border-border/40 rounded-2xl max-w-xl w-full p-6 shadow-2xl space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-border/40">
                <div className="flex items-center gap-2">
                  <Edit2 className="w-5 h-5 text-primary" />
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
                      className="w-full bg-muted/30 border border-border/60 text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-primary/40 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-muted-foreground font-medium mb-1">Parent Group</label>
                    <select
                      value={formData.group_id}
                      onChange={e => setFormData({ ...formData, group_id: e.target.value })}
                      className="w-full bg-muted/30 border border-border/60 text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-primary/40 outline-none"
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
                      className="w-full bg-muted/30 border border-border/60 text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-primary/40 outline-none"
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
                      className="w-full bg-muted/30 border border-border/60 text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-primary/40 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-muted-foreground font-medium mb-1">Default Discount %</label>
                    <input
                      type="number"
                      step="0.01"
                      value={formData.discount_percent}
                      onChange={e => setFormData({ ...formData, discount_percent: e.target.value })}
                      className="w-full bg-muted/30 border border-border/60 text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-primary/40 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-muted-foreground font-medium mb-1">GSTIN</label>
                    <input
                      type="text"
                      value={formData.gstin}
                      onChange={e => setFormData({ ...formData, gstin: e.target.value.toUpperCase() })}
                      className="w-full bg-muted/30 border border-border/60 text-foreground p-2.5 rounded-lg text-xs font-mono uppercase focus:ring-2 focus:ring-primary/40 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-muted-foreground font-medium mb-1">Phone</label>
                    <input
                      type="text"
                      value={formData.phone}
                      onChange={e => setFormData({ ...formData, phone: e.target.value })}
                      className="w-full bg-muted/30 border border-border/60 text-foreground p-2.5 rounded-lg text-xs focus:ring-2 focus:ring-primary/40 outline-none"
                    />
                  </div>

                  <div className="sm:col-span-2 flex items-center gap-2 pt-2">
                    <input
                      type="checkbox"
                      id="is_active_chk"
                      checked={formData.is_active}
                      onChange={e => setFormData({ ...formData, is_active: e.target.checked })}
                      className="rounded border-border text-primary focus:ring-primary"
                    />
                    <label htmlFor="is_active_chk" className="text-foreground font-medium cursor-pointer">
                      Active (uncheck to archive this ledger from invoice pickers)
                    </label>
                  </div>
                </div>

                <div className="flex items-center justify-end gap-2 pt-3 border-t border-border/40">
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
                    className="px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-medium transition-all shadow-md shadow-primary/20 cursor-pointer"
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
            <div className="bg-card border border-border/40 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4">
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
                  <div className="text-[11px] text-muted-foreground mt-1">
                    Tip: Instead of deleting, edit this ledger and uncheck "Active" to safely archive it.
                  </div>
                </div>
              ) : (
                <div className="text-[11px] text-muted-foreground bg-muted/40 p-3 rounded-lg border border-border/40">
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
                    className="px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-700 text-foreground text-xs font-medium transition-all shadow-md shadow-rose-600/20 cursor-pointer"
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
