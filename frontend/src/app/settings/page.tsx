"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import { getAccessToken, isAuthenticated, removeTokens } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import StateSelect from '@/components/StateSelect';
import { getStateName } from '@/utils/gstStates';
import { useFinancialYear } from '@/context/FinancialYearContext';
import { useAccountingPeriod } from '@/context/PeriodContext';
import { useToast } from '@/context/ToastContext';
import {
  Users,
  ShieldCheck,
  UserPlus,
  Trash2,
  Wrench,
  AlertTriangle,
  RefreshCw,
  CheckCircle2,
  Lock,
  Building,
  Sliders,
  Database,
  Upload,
  X
} from 'lucide-react';

export default function SettingsPage() {
  const router = useRouter();
  const { toast } = useToast();
  const { availableFYs, activeFY, setActiveFY, setIsClosingModalOpen } = useFinancialYear();
  const { setIsSplitModalOpen } = useAccountingPeriod();
  const [company, setCompany] = useState<any>(null);
  
  // Profile State
  const [name, setName] = useState('');
  const [gstin, setGstin] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [address, setAddress] = useState('');
  const [stateCode, setStateCode] = useState('');
  const [proprietorName, setProprietorName] = useState('');
  const [proprietorPhone, setProprietorPhone] = useState('');
  const [signature, setSignature] = useState<File | null>(null);
  const [signaturePreview, setSignaturePreview] = useState<string | null>(null);
  
  const [tagline, setTagline] = useState('');
  const [bankName, setBankName] = useState('');
  const [bankAccountNumber, setBankAccountNumber] = useState('');
  const [bankIfsc, setBankIfsc] = useState('');
  const [bankBranch, setBankBranch] = useState('');
  
  // Settings State
  const [enableLedgerMapping, setEnableLedgerMapping] = useState(false);
  const [enableManualInvoice, setEnableManualInvoice] = useState(false);
  const [enableAdvancedItemCreation, setEnableAdvancedItemCreation] = useState(false);
  const [complexityLevel, setComplexityLevel] = useState(1);
  const [allowNegativeStock, setAllowNegativeStock] = useState(false);
  const [salesInvoicePrefix, setSalesInvoicePrefix] = useState('');
  const [purchaseInvoicePrefix, setPurchaseInvoicePrefix] = useState('');
  const [saving, setSaving] = useState(false);

  // Team & RBAC State
  const [members, setMembers] = useState<any[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(false);
  const [isInviteModalOpen, setIsInviteModalOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('VIEWER');
  const [inviting, setInviting] = useState(false);

  // Diagnostics State
  const [syncingTax, setSyncingTax] = useState(false);
  const [rebuildingBalances, setRebuildingBalances] = useState(false);

  // Danger Zone State
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [deleteConfirmName, setDeleteConfirmName] = useState('');
  const [deletingCompany, setDeletingCompany] = useState(false);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login');
      return;
    }
    fetchCompany();
  }, [router]);

  const fetchCompany = async () => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const comp = compRes.data.data[0];
      if (comp) {
        setCompany(comp);
        
        // Populate profile
        setName(comp.name || '');
        setGstin(comp.gstin || '');
        setEmail(comp.email || '');
        setPhone(comp.phone || '');
        setAddress(comp.address || '');
        setStateCode(comp.state_code || '');
        setProprietorName(comp.proprietor_name || '');
        setProprietorPhone(comp.proprietor_phone || '');
        if (comp.signature_data) {
          setSignaturePreview(comp.signature_data);
        } else if (comp.proprietor_signature) {
          const base = API_BASE_URL.endsWith('/') ? API_BASE_URL.slice(0, -1) : API_BASE_URL;
          const cleanPath = comp.proprietor_signature.startsWith('/') ? comp.proprietor_signature : `/${comp.proprietor_signature}`;
          setSignaturePreview(`${base}${cleanPath}`);
        } else {
          setSignaturePreview(null);
        }
        setTagline(comp.tagline || '');
        setBankName(comp.bank_name || '');
        setBankAccountNumber(comp.bank_account_number || '');
        setBankIfsc(comp.bank_ifsc || '');
        setBankBranch(comp.bank_branch || '');

        // Populate settings
        setEnableLedgerMapping(comp.settings?.enable_ledger_mapping || false);
        setEnableManualInvoice(comp.settings?.enable_manual_invoice_number || false);
        setEnableAdvancedItemCreation(comp.settings?.enable_advanced_item_creation || false);
        setComplexityLevel(comp.settings?.complexity_level || 1);
        setAllowNegativeStock(comp.settings?.allow_negative_stock || false);
        setSalesInvoicePrefix(comp.settings?.sales_invoice_prefix || '');
        setPurchaseInvoicePrefix(comp.settings?.purchase_invoice_prefix || '');

        fetchMembers(comp.id);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const fetchMembers = async (compId?: string) => {
    const cid = compId || company?.id;
    if (!cid) return;
    setLoadingMembers(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.get(`${API_BASE_URL}/api/v1/companies/${cid}/members/`, { headers });
      if (res.data?.success) {
        setMembers(res.data.data || []);
      }
    } catch (err) {
      console.error('Failed to fetch company members:', err);
    } finally {
      setLoadingMembers(false);
    }
  };

  const saveSettings = async () => {
    if (!company) return;
    setSaving(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      
      // Update Settings
      await axios.patch(`${API_BASE_URL}/api/v1/companies/${company.id}/update_settings/`, {
        enable_ledger_mapping: enableLedgerMapping,
        enable_manual_invoice_number: enableManualInvoice,
        enable_advanced_item_creation: enableAdvancedItemCreation,
        complexity_level: complexityLevel,
        allow_negative_stock: allowNegativeStock,
        sales_invoice_prefix: salesInvoicePrefix,
        purchase_invoice_prefix: purchaseInvoicePrefix
      }, { headers });

      // Update Profile
      const formData = new FormData();
      formData.append('name', name);
      formData.append('gstin', gstin);
      formData.append('email', email);
      formData.append('phone', phone);
      formData.append('address', address);
      formData.append('state_code', stateCode);
      const sName = getStateName(stateCode);
      if (sName) {
        formData.append('state_name', sName);
      }
      formData.append('proprietor_name', proprietorName);
      formData.append('proprietor_phone', proprietorPhone);
      if (signature) {
        formData.append('proprietor_signature', signature);
      }
      if (signaturePreview) {
        formData.append('signature_data', signaturePreview);
      } else {
        formData.append('signature_data', '');
      }
      formData.append('tagline', tagline);
      formData.append('bank_name', bankName);
      formData.append('bank_account_number', bankAccountNumber);
      formData.append('bank_ifsc', bankIfsc);
      formData.append('bank_branch', bankBranch);
      
      await axios.patch(`${API_BASE_URL}/api/v1/companies/${company.id}/`, formData, { 
        headers: {
          ...headers,
          'Content-Type': 'multipart/form-data'
        }
      });
      
      toast.success('Profile and Settings updated', 'Changes have been saved successfully.');
      fetchCompany();
    } catch (err: any) {
      console.error(err);
      toast.error('Failed to update profile/settings', err.response?.data?.error || err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleSignatureChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setSignature(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        if (typeof reader.result === 'string') {
          setSignaturePreview(reader.result);
        }
      };
      reader.readAsDataURL(file);
    }
  };

  // Team RBAC Handlers
  const handleInviteMember = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim() || !company?.id) return;
    setInviting(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.post(
        `${API_BASE_URL}/api/v1/companies/${company.id}/members/`,
        { email: inviteEmail.trim(), role: inviteRole },
        { headers }
      );
      if (res.data?.success) {
        toast.success('Team member invited', res.data.message);
        setIsInviteModalOpen(false);
        setInviteEmail('');
        fetchMembers(company.id);
      }
    } catch (err: any) {
      toast.error('Failed to invite member', err.response?.data?.error || err.message);
    } finally {
      setInviting(false);
    }
  };

  const handleUpdateRole = async (memberId: string, newRole: string) => {
    if (!company?.id) return;
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.patch(
        `${API_BASE_URL}/api/v1/companies/${company.id}/members/${memberId}/`,
        { role: newRole },
        { headers }
      );
      if (res.data?.success) {
        toast.success('Role updated', `Member role changed to ${newRole}`);
        fetchMembers(company.id);
      }
    } catch (err: any) {
      toast.error('Failed to update role', err.response?.data?.error || err.message);
    }
  };

  const handleRemoveMember = async (memberId: string, memberEmail: string) => {
    if (!company?.id) return;
    if (!confirm(`Are you sure you want to remove ${memberEmail} from this company?`)) return;
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.delete(
        `${API_BASE_URL}/api/v1/companies/${company.id}/members/${memberId}/`,
        { headers }
      );
      if (res.data?.success) {
        toast.success('Member removed', `${memberEmail} has been removed.`);
        fetchMembers(company.id);
      }
    } catch (err: any) {
      toast.error('Failed to remove member', err.response?.data?.error || err.message);
    }
  };

  // Diagnostics Handlers
  const handleSyncTaxLedgers = async () => {
    if (!company?.id) return;
    setSyncingTax(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.post(
        `${API_BASE_URL}/api/v1/accounting/sync-tax-ledgers/${company.id}/`,
        {},
        { headers }
      );
      if (res.data?.success) {
        toast.success('Tax ledgers aligned', res.data.message || 'CGST, SGST, IGST ledgers verified.');
      } else {
        toast.error('Tax sync failed', res.data?.error);
      }
    } catch (err: any) {
      toast.error('Tax alignment failed', err.response?.data?.error || err.message);
    } finally {
      setSyncingTax(false);
    }
  };

  const handleRebuildBalances = async () => {
    if (!company?.id) return;
    setRebuildingBalances(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.post(
        `${API_BASE_URL}/api/v1/accounting/rebuild-balances/${company.id}/`,
        {},
        { headers }
      );
      if (res.data?.success) {
        toast.success('Ledger balances rebuilt', res.data.message || 'All debit & credit balances recomputed from journals.');
      } else {
        toast.error('Rebuild failed', res.data?.error);
      }
    } catch (err: any) {
      toast.error('Rebuild failed', err.response?.data?.error || err.message);
    } finally {
      setRebuildingBalances(false);
    }
  };

  // Delete Company Handler
  const handleDeleteCompany = async () => {
    if (!company?.id) return;
    if (deleteConfirmName.trim() !== company.name.trim()) {
      toast.error('Company name does not match', 'Please type the exact company name to confirm deletion.');
      return;
    }
    setDeletingCompany(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.delete(`${API_BASE_URL}/api/v1/companies/${company.id}/`, { headers });
      if (res.data?.success || res.status === 200 || res.status === 204) {
        toast.success('Company deleted', 'Company data has been archived/deleted.');
        removeTokens();
        router.push('/login');
      }
    } catch (err: any) {
      toast.error('Deletion failed', err.response?.data?.error || err.message);
    } finally {
      setDeletingCompany(false);
    }
  };

  const getRoleBadge = (role: string) => {
    switch (role?.toUpperCase()) {
      case 'OWNER':
        return 'bg-purple-500/15 text-purple-400 border-purple-500/30';
      case 'ADMIN':
        return 'bg-blue-500/15 text-blue-400 border-blue-500/30';
      case 'ACCOUNTANT':
        return 'bg-amber-500/15 text-amber-400 border-amber-500/30';
      case 'SALES':
        return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30';
      case 'PURCHASE':
        return 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30';
      default:
        return 'bg-muted text-muted-foreground border-border/40';
    }
  };

  return (
    <DashboardLayout>
      <div className="max-w-4xl mx-auto space-y-8 pb-16">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">
            Settings & Workspace
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Manage your company profile, invoicing rules, team members, and system maintenance
          </p>
        </div>

        {company ? (
          <div className="space-y-8">
            {/* 1. Firm Details */}
            <div className="bg-card border border-border/40 rounded-xl shadow-sm p-6 space-y-6">
              <div className="flex items-center gap-2.5 border-b border-border/40 pb-3">
                <Building className="w-5 h-5 text-primary" />
                <h2 className="text-base font-bold text-foreground">Firm Details & Profile</h2>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-muted-foreground mb-1">Firm Name</label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full bg-muted/40 border border-input text-foreground text-sm p-2.5 rounded-lg outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-muted-foreground mb-1">GSTIN</label>
                  <input
                    type="text"
                    value={gstin}
                    onChange={(e) => setGstin(e.target.value.toUpperCase())}
                    className="w-full bg-muted/40 border border-input text-foreground text-sm p-2.5 rounded-lg outline-none uppercase font-mono focus:ring-1 focus:ring-primary"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-muted-foreground mb-1">Email</label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full bg-muted/40 border border-input text-foreground text-sm p-2.5 rounded-lg outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-muted-foreground mb-1">Phone</label>
                  <input
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    className="w-full bg-muted/40 border border-input text-foreground text-sm p-2.5 rounded-lg outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
                <div>
                  <StateSelect
                    value={stateCode}
                    onChange={(code) => setStateCode(code)}
                    label="State / Union Territory"
                    placeholder="Search state by name or code (e.g. 09 / Uttar Pradesh)"
                  />
                </div>
                <div className="sm:col-span-2">
                  <label className="block text-xs font-semibold text-muted-foreground mb-1">Full Billing Address</label>
                  <textarea
                    rows={2}
                    value={address}
                    onChange={(e) => setAddress(e.target.value)}
                    className="w-full bg-muted/40 border border-input text-foreground text-sm p-2.5 rounded-lg outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
              </div>

              {/* Signatory & Proprietor Details */}
              <div className="pt-4 border-t border-border/40 space-y-3">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
                      Authorized Signatory & Proprietor Details
                    </h3>
                    <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-amber-500/10 text-amber-500 border border-amber-500/20">
                      REQUIRED FOR INVOICING
                    </span>
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    Statutory seller information printed on invoice signature blocks and communication headers (GST Rule 46).
                  </p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-foreground mb-1">
                      Proprietor / Signatory Name <span className="text-rose-500">*</span>
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Rajesh Sharma"
                      value={proprietorName}
                      onChange={(e) => setProprietorName(e.target.value)}
                      className="w-full bg-muted/40 border border-input text-foreground text-sm p-2.5 rounded-lg outline-none focus:ring-1 focus:ring-primary"
                    />
                    <p className="text-[11px] text-muted-foreground mt-1">
                      Printed on invoice bottom right under &quot;Authorised Signatory&quot;.
                    </p>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-foreground mb-1">
                      Proprietor / Contact Phone <span className="text-rose-500">*</span>
                    </label>
                    <input
                      type="tel"
                      placeholder="e.g. +91 98765 43210"
                      value={proprietorPhone}
                      onChange={(e) => setProprietorPhone(e.target.value)}
                      className="w-full bg-muted/40 border border-input text-foreground text-sm p-2.5 rounded-lg outline-none focus:ring-1 focus:ring-primary"
                    />
                    <p className="text-[11px] text-muted-foreground mt-1">
                      Seller contact number displayed on invoice header.
                    </p>
                  </div>
                </div>
              </div>

              {/* Digital Signature (Strictly Optional) */}
              <div className="pt-4 border-t border-border/40 space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
                        Digital Signature Image
                      </h3>
                      <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
                        OPTIONAL
                      </span>
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      Upload an image of your signature to print above &quot;Authorised Signatory&quot;. Not required to create or post sales bills.
                    </p>
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row items-start gap-4 p-4 rounded-xl border border-border/40 bg-muted/20">
                  {signaturePreview ? (
                    <div className="space-y-2">
                      <div className="w-48 h-24 border border-border/60 rounded-lg bg-card p-2 flex items-center justify-center overflow-hidden">
                        <img
                          src={signaturePreview}
                          alt="Signature Preview"
                          className="max-h-full max-w-full object-contain filter dark:invert"
                        />
                      </div>
                      <div className="flex items-center gap-2">
                        <label className="text-xs font-medium text-primary hover:underline cursor-pointer">
                          <span>Change image</span>
                          <input
                            type="file"
                            accept="image/*"
                            onChange={handleSignatureChange}
                            className="hidden"
                          />
                        </label>
                        <span className="text-muted-foreground">•</span>
                        <button
                          type="button"
                          onClick={() => {
                            setSignature(null);
                            setSignaturePreview(null);
                          }}
                          className="text-xs font-medium text-rose-400 hover:underline cursor-pointer"
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  ) : (
                    <label className="flex flex-col items-center justify-center w-full sm:w-64 h-28 border-2 border-dashed border-border/60 hover:border-primary/50 rounded-xl cursor-pointer bg-muted/30 hover:bg-muted/50 transition-colors p-4 text-center">
                      <Upload className="w-5 h-5 text-muted-foreground mb-1.5" />
                      <span className="text-xs font-semibold text-foreground">Upload Signature Image</span>
                      <span className="text-[10px] text-muted-foreground mt-0.5">PNG, JPG up to 2MB (Optional)</span>
                      <input
                        type="file"
                        accept="image/*"
                        onChange={handleSignatureChange}
                        className="hidden"
                      />
                    </label>
                  )}
                  <div className="text-xs text-muted-foreground flex-1">
                    <p className="font-semibold text-foreground mb-1">Optional e-signature tips:</p>
                    <ul className="list-disc list-inside space-y-0.5 text-[11px]">
                      <li>Sign on a clean sheet of white paper using a dark blue or black pen</li>
                      <li>Crop the photo closely around your signature before uploading</li>
                      <li>Invoices can always be signed physically by hand after printing</li>
                    </ul>
                  </div>
                </div>
              </div>

              {/* Banking Details */}
              <div className="pt-4 border-t border-border/40">
                <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-3">
                  Bank Account (Printed on Invoices)
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
                  <div>
                    <label className="block text-xs text-muted-foreground mb-1">Bank Name</label>
                    <input
                      type="text"
                      value={bankName}
                      onChange={(e) => setBankName(e.target.value)}
                      placeholder="e.g. HDFC Bank"
                      className="w-full bg-muted/40 border border-input text-foreground text-xs p-2 rounded outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-muted-foreground mb-1">Account Number</label>
                    <input
                      type="text"
                      value={bankAccountNumber}
                      onChange={(e) => setBankAccountNumber(e.target.value)}
                      className="w-full bg-muted/40 border border-input text-foreground text-xs p-2 rounded outline-none font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-muted-foreground mb-1">IFSC Code</label>
                    <input
                      type="text"
                      value={bankIfsc}
                      onChange={(e) => setBankIfsc(e.target.value.toUpperCase())}
                      className="w-full bg-muted/40 border border-input text-foreground text-xs p-2 rounded outline-none uppercase font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-muted-foreground mb-1">Branch</label>
                    <input
                      type="text"
                      value={bankBranch}
                      onChange={(e) => setBankBranch(e.target.value)}
                      className="w-full bg-muted/40 border border-input text-foreground text-xs p-2 rounded outline-none"
                    />
                  </div>
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <button
                  onClick={saveSettings}
                  disabled={saving}
                  className="px-5 py-2 bg-primary text-primary-foreground hover:bg-primary/90 rounded-lg text-xs font-semibold shadow transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {saving ? 'Saving Profile...' : 'Save Firm Details'}
                </button>
              </div>
            </div>

            {/* 2. Invoicing, Prefixes & Stock Controls */}
            <div className="bg-card border border-border/40 rounded-xl shadow-sm p-6 space-y-6">
              <div className="flex items-center gap-2.5 border-b border-border/40 pb-3">
                <Sliders className="w-5 h-5 text-primary" />
                <h2 className="text-base font-bold text-foreground">Invoicing & Inventory Controls</h2>
              </div>

              {/* Invoice Prefixes */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-foreground mb-1">
                    Sales Invoice Prefix
                  </label>
                  <p className="text-[11px] text-muted-foreground mb-1.5">
                    Prefix for sequential sales invoices (e.g. &quot;INV/&quot; or &quot;SLS-&quot;).
                  </p>
                  <input
                    type="text"
                    maxLength={10}
                    placeholder="e.g. INV-"
                    value={salesInvoicePrefix}
                    onChange={(e) => setSalesInvoicePrefix(e.target.value)}
                    className="w-full bg-muted/40 border border-input text-foreground text-sm p-2.5 rounded-lg outline-none font-mono focus:ring-1 focus:ring-primary"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-foreground mb-1">
                    Purchase Order / Bill Prefix
                  </label>
                  <p className="text-[11px] text-muted-foreground mb-1.5">
                    Prefix for purchase vouchers (e.g. &quot;PUR/&quot; or &quot;PO-&quot;).
                  </p>
                  <input
                    type="text"
                    maxLength={10}
                    placeholder="e.g. PO-"
                    value={purchaseInvoicePrefix}
                    onChange={(e) => setPurchaseInvoicePrefix(e.target.value)}
                    className="w-full bg-muted/40 border border-input text-foreground text-sm p-2.5 rounded-lg outline-none font-mono focus:ring-1 focus:ring-primary"
                  />
                </div>
              </div>

              {/* Toggles */}
              <div className="space-y-3 pt-2">
                {/* Allow Negative Stock */}
                <div className="flex items-center justify-between bg-muted/30 p-3.5 rounded-xl border border-border/40">
                  <div>
                    <h3 className="text-foreground text-xs font-semibold flex items-center gap-2">
                      <span>Allow Negative Stock</span>
                      <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${allowNegativeStock ? 'bg-amber-500/20 text-amber-400' : 'bg-muted text-muted-foreground'}`}>
                        {allowNegativeStock ? 'PERMISSIVE' : 'STRICT'}
                      </span>
                    </h3>
                    <p className="text-muted-foreground text-xs mt-0.5">
                      When enabled, allows invoicing products even when current warehouse inventory is zero or negative.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setAllowNegativeStock(!allowNegativeStock)}
                    className={`w-11 h-6 rounded-full transition-all relative shrink-0 cursor-pointer ${allowNegativeStock ? 'bg-primary' : 'bg-muted-foreground/30'}`}
                  >
                    <div className={`w-4 h-4 bg-white rounded-full absolute top-1 transition-all ${allowNegativeStock ? 'left-6' : 'left-1'}`}></div>
                  </button>
                </div>

                {/* Manual Invoice Number (Tally-Style Auto / Manual) */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between bg-muted/30 p-4 rounded-xl border border-border/40 gap-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-foreground text-xs font-semibold">Sales Invoice Numbering Method</h3>
                      <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${
                        enableManualInvoice 
                          ? 'bg-amber-500/15 text-amber-500 border-amber-500/30' 
                          : 'bg-blue-500/15 text-blue-400 border-blue-500/30'
                      }`}>
                        {enableManualInvoice ? 'MANUAL (Custom Numbering)' : 'AUTO (GST Rule 46b Sequential)'}
                      </span>
                    </div>
                    <p className="text-muted-foreground text-xs">
                      Choose your default numbering mode. <strong>Auto</strong> generates consecutive serial numbers based on prefix and active financial year. <strong>Manual</strong> allows typing custom invoice numbers. Can also be toggled directly on the New Sales Invoice screen.
                    </p>
                  </div>
                  
                  <div className="inline-flex items-center bg-muted/80 p-0.5 rounded-lg border border-border/60 text-xs shrink-0 self-start sm:self-center">
                    <button
                      type="button"
                      onClick={() => setEnableManualInvoice(false)}
                      className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all cursor-pointer ${
                        !enableManualInvoice
                          ? 'bg-primary text-primary-foreground shadow-xs'
                          : 'text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      Auto
                    </button>
                    <button
                      type="button"
                      onClick={() => setEnableManualInvoice(true)}
                      className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all cursor-pointer ${
                        enableManualInvoice
                          ? 'bg-primary text-primary-foreground shadow-xs'
                          : 'text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      Manual
                    </button>
                  </div>
                </div>

                {/* Advanced Item Creation */}
                <div className="flex items-center justify-between bg-muted/30 p-3.5 rounded-xl border border-border/40">
                  <div>
                    <h3 className="text-foreground text-xs font-semibold">Advanced Item Options</h3>
                    <p className="text-muted-foreground text-xs mt-0.5">
                      Display pricing matrices, secondary packaging units, and batch tracking during item setup.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setEnableAdvancedItemCreation(!enableAdvancedItemCreation)}
                    className={`w-11 h-6 rounded-full transition-all relative shrink-0 cursor-pointer ${enableAdvancedItemCreation ? 'bg-primary' : 'bg-muted-foreground/30'}`}
                  >
                    <div className={`w-4 h-4 bg-white rounded-full absolute top-1 transition-all ${enableAdvancedItemCreation ? 'left-6' : 'left-1'}`}></div>
                  </button>
                </div>
              </div>

              <div className="flex justify-end pt-2 border-t border-border/40">
                <button
                  onClick={saveSettings}
                  disabled={saving}
                  className="px-5 py-2 bg-primary text-primary-foreground hover:bg-primary/90 rounded-lg text-xs font-semibold shadow transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {saving ? 'Saving...' : 'Save Invoicing Preferences'}
                </button>
              </div>
            </div>

            {/* 3. Team Members & Role Management */}
            <div className="bg-card border border-border/40 rounded-xl shadow-sm p-6 space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/40 pb-3">
                <div className="flex items-center gap-2.5">
                  <Users className="w-5 h-5 text-primary" />
                  <div>
                    <h2 className="text-base font-bold text-foreground">Team & Permissions (RBAC)</h2>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Assign Owner, Admin, Accountant, Sales, or Purchase access roles
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setIsInviteModalOpen(true)}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-semibold rounded-lg shadow-sm transition-colors cursor-pointer"
                >
                  <UserPlus className="w-3.5 h-3.5" />
                  <span>Invite Team Member</span>
                </button>
              </div>

              <div className="overflow-x-auto rounded-xl border border-border/40">
                <table className="w-full text-left text-xs min-w-[550px]">
                  <thead className="bg-muted/40 text-muted-foreground font-semibold border-b border-border/40">
                    <tr>
                      <th className="px-4 py-2.5">Member</th>
                      <th className="px-4 py-2.5">Role</th>
                      <th className="px-4 py-2.5">Joined Date</th>
                      <th className="px-4 py-2.5 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40">
                    {loadingMembers ? (
                      <tr>
                        <td colSpan={4} className="p-8 text-center text-muted-foreground">
                          Loading team members...
                        </td>
                      </tr>
                    ) : members.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="p-8 text-center text-muted-foreground">
                          No team members registered yet.
                        </td>
                      </tr>
                    ) : (
                      members.map((m) => (
                        <tr key={m.id} className="hover:bg-muted/30 transition-colors">
                          <td className="px-4 py-3">
                            <div className="font-semibold text-foreground flex items-center gap-2">
                              <span>{m.name || m.email}</span>
                              {m.is_current_user && (
                                <span className="text-[10px] font-mono bg-blue-500/10 text-blue-400 px-1.5 py-0.2 rounded border border-blue-500/20 font-bold">
                                  YOU
                                </span>
                              )}
                            </div>
                            <div className="text-[11px] text-muted-foreground font-mono">{m.email}</div>
                          </td>

                          <td className="px-4 py-3">
                            {m.role === 'OWNER' ? (
                              <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${getRoleBadge(m.role)}`}>
                                OWNER
                              </span>
                            ) : (
                              <select
                                value={m.role}
                                onChange={(e) => handleUpdateRole(m.id, e.target.value)}
                                className="text-xs bg-muted/60 border border-input rounded px-2 py-1 text-foreground font-semibold outline-none cursor-pointer"
                              >
                                <option value="ADMIN">ADMIN</option>
                                <option value="ACCOUNTANT">ACCOUNTANT</option>
                                <option value="SALES">SALES</option>
                                <option value="PURCHASE">PURCHASE</option>
                                <option value="VIEWER">VIEWER</option>
                              </select>
                            )}
                          </td>

                          <td className="px-4 py-3 text-muted-foreground font-mono">{m.created_at || 'Active'}</td>

                          <td className="px-4 py-3 text-right">
                            {m.role !== 'OWNER' && !m.is_current_user && (
                              <button
                                onClick={() => handleRemoveMember(m.id, m.email)}
                                className="p-1.5 text-rose-400 hover:bg-rose-500/10 rounded-lg transition-colors cursor-pointer"
                                title="Remove team member"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* 4. Diagnostics & Maintenance Tools */}
            <div className="bg-card border border-border/40 rounded-xl shadow-sm p-6 space-y-4">
              <div className="flex items-center gap-2.5 border-b border-border/40 pb-3">
                <Wrench className="w-5 h-5 text-primary" />
                <div>
                  <h2 className="text-base font-bold text-foreground">Data Health & Diagnostics</h2>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Self-healing automated maintenance tools for tax ledgers and ledger balance integrity
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Sync Tax Ledgers */}
                <div className="p-4 bg-muted/30 border border-border/40 rounded-xl flex flex-col justify-between space-y-3">
                  <div>
                    <h3 className="text-xs font-bold text-foreground flex items-center gap-2">
                      <span>Sync & Align Tax Ledgers</span>
                      <span className="text-[10px] font-mono px-1.5 py-0.2 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded font-semibold">
                        GST AUTO-HEAL
                      </span>
                    </h3>
                    <p className="text-xs text-muted-foreground mt-1">
                      Scans Chart of Accounts for missing standard input/output CGST, SGST, IGST tax ledgers and automatically provisions them with correct tax configurations.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleSyncTaxLedgers}
                    disabled={syncingTax}
                    className="px-3.5 py-2 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/30 rounded-lg text-xs font-bold transition-colors w-fit flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${syncingTax ? 'animate-spin' : ''}`} />
                    <span>{syncingTax ? 'Aligning...' : 'Run Tax Alignment'}</span>
                  </button>
                </div>

                {/* Rebuild Ledger Balances */}
                <div className="p-4 bg-muted/30 border border-border/40 rounded-xl flex flex-col justify-between space-y-3">
                  <div>
                    <h3 className="text-xs font-bold text-foreground flex items-center gap-2">
                      <span>Rebuild Ledger Balances</span>
                      <span className="text-[10px] font-mono px-1.5 py-0.2 bg-blue-500/10 text-blue-400 border border-blue-500/20 rounded font-semibold">
                        INTEGRITY
                      </span>
                    </h3>
                    <p className="text-xs text-muted-foreground mt-1">
                      Recalculates all running ledger closing balances from scratch using raw posted double-entry journal entries, eliminating any rounding or caching drifts.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleRebuildBalances}
                    disabled={rebuildingBalances}
                    className="px-3.5 py-2 bg-blue-600/10 hover:bg-blue-600/20 text-blue-400 border border-blue-500/30 rounded-lg text-xs font-bold transition-colors w-fit flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                  >
                    <Database className={`w-3.5 h-3.5 ${rebuildingBalances ? 'animate-spin' : ''}`} />
                    <span>{rebuildingBalances ? 'Recomputing...' : 'Recompute Ledger Balances'}</span>
                  </button>
                </div>
              </div>
            </div>

            {/* 5. Financial Years & Period Closing */}
            <div className="bg-card border border-border/40 rounded-xl p-4 sm:p-6 shadow-sm space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h2 className="text-base sm:text-lg font-bold text-foreground flex items-center gap-2 flex-wrap">
                    <span>Financial Years & Period Closing</span>
                    <span className="text-xs font-mono px-2 py-0.5 bg-blue-500/10 text-blue-400 border border-blue-500/20 rounded font-bold">
                      GST Rule 46(b)
                    </span>
                  </h2>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Year-wise sequential invoice boundaries (April 1 – March 31) and balance carry-forward engine.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setIsClosingModalOpen(true)}
                  className="w-full sm:w-auto justify-center px-4 py-2 bg-amber-600/15 hover:bg-amber-600/25 text-amber-400 border border-amber-500/30 rounded-lg text-xs font-bold transition-colors flex items-center gap-1.5 cursor-pointer"
                >
                  <Lock className="w-3.5 h-3.5" />
                  <span>Close Year & Roll-Forward</span>
                </button>
              </div>

              <div className="overflow-x-auto rounded-xl border border-border/40">
                <table className="w-full text-left text-xs min-w-[500px]">
                  <thead className="bg-muted/40 text-muted-foreground font-semibold border-b border-border/40">
                    <tr>
                      <th className="px-4 py-2.5">Financial Year</th>
                      <th className="px-4 py-2.5">Code</th>
                      <th className="px-4 py-2.5">Date Period</th>
                      <th className="px-4 py-2.5">Status</th>
                      <th className="px-4 py-2.5 text-right">Vouchers</th>
                      <th className="px-4 py-2.5 text-center">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40 font-mono">
                    {availableFYs.map((fy) => (
                      <tr key={fy.id} className={fy.id === activeFY?.id ? "bg-primary/5" : ""}>
                        <td className="px-4 py-3 font-sans font-bold text-foreground flex items-center gap-2">
                          <span>{fy.name}</span>
                          {fy.is_current && (
                            <span className="text-[9px] bg-blue-500/20 text-blue-400 px-1.5 py-0.2 rounded font-mono font-normal">Current</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">{fy.code}</td>
                        <td className="px-4 py-3 text-muted-foreground">{fy.start_date} → {fy.end_date}</td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            fy.is_closed ? "bg-muted text-amber-400 border border-amber-500/20" : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                          }`}>
                            {fy.is_closed ? "CLOSED" : "OPEN"}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right text-foreground">{fy.voucher_count ?? 0}</td>
                        <td className="px-4 py-3 text-center">
                          {fy.id === activeFY?.id ? (
                            <span className="text-[11px] font-sans font-semibold text-primary">Selected</span>
                          ) : (
                            <button
                              type="button"
                              onClick={() => setActiveFY(fy)}
                              className="px-2.5 py-1 bg-muted hover:bg-muted/80 text-foreground font-sans rounded text-[11px] transition-colors cursor-pointer"
                            >
                              Switch
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* 6. Danger Zone */}
            <div className="bg-rose-500/5 border border-rose-500/30 rounded-xl p-6 space-y-3">
              <div className="flex items-center gap-2.5">
                <AlertTriangle className="w-5 h-5 text-rose-500 shrink-0" />
                <div>
                  <h3 className="text-sm font-bold text-rose-500">Danger Zone</h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Permanently archive or delete this company entity, ledgers, vouchers, and settings.
                  </p>
                </div>
              </div>

              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-2 border-t border-rose-500/20">
                <div className="text-xs text-muted-foreground">
                  Once deleted, accounting ledgers cannot be restored. Only the company OWNER can perform this action.
                </div>
                <button
                  type="button"
                  onClick={() => setIsDeleteModalOpen(true)}
                  className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-xs font-semibold shadow transition-colors cursor-pointer shrink-0"
                >
                  Delete Company Data
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="text-muted-foreground">Loading settings...</div>
        )}

        {/* Invite Member Modal */}
        {isInviteModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in">
            <div className="bg-card border border-border rounded-2xl shadow-2xl max-w-md w-full p-6 space-y-4">
              <div className="flex items-center justify-between border-b border-border/40 pb-3">
                <h3 className="font-bold text-base text-foreground">Invite Team Member</h3>
                <button
                  onClick={() => setIsInviteModalOpen(false)}
                  className="p-1 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground cursor-pointer"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <form onSubmit={handleInviteMember} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-muted-foreground mb-1">Email Address</label>
                  <input
                    type="email"
                    required
                    placeholder="teammate@company.com"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    className="w-full bg-muted/40 border border-input text-foreground text-sm p-2.5 rounded-lg outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-muted-foreground mb-1">Access Role</label>
                  <select
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value)}
                    className="w-full bg-muted/40 border border-input text-foreground text-sm p-2.5 rounded-lg outline-none cursor-pointer"
                  >
                    <option value="ADMIN">ADMIN (Full access except owner transfer)</option>
                    <option value="ACCOUNTANT">ACCOUNTANT (Vouchers, Daybook, Ledgers, Reports)</option>
                    <option value="SALES">SALES (Create & View Sales Invoices only)</option>
                    <option value="PURCHASE">PURCHASE (Create & View Purchases only)</option>
                    <option value="VIEWER">VIEWER (Read-only access)</option>
                  </select>
                </div>

                <div className="flex justify-end gap-2 pt-2 border-t border-border/40">
                  <button
                    type="button"
                    onClick={() => setIsInviteModalOpen(false)}
                    className="px-4 py-2 rounded-lg text-xs font-semibold bg-muted hover:bg-muted/80 text-foreground transition-colors cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={inviting}
                    className="px-4 py-2 rounded-lg text-xs font-semibold bg-primary text-primary-foreground hover:bg-primary/90 transition-colors cursor-pointer disabled:opacity-50"
                  >
                    {inviting ? 'Inviting...' : 'Send Invitation'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Delete Company Modal */}
        {isDeleteModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in">
            <div className="bg-card border border-rose-500/40 rounded-2xl shadow-2xl max-w-md w-full p-6 space-y-4">
              <div className="flex items-center gap-3 text-rose-500">
                <AlertTriangle className="w-6 h-6" />
                <h3 className="font-bold text-base">Confirm Company Deletion</h3>
              </div>

              <p className="text-xs text-muted-foreground">
                This action is irreversible. To confirm deletion of <strong className="text-foreground">{company.name}</strong>, please type the company name below:
              </p>

              <input
                type="text"
                placeholder={company.name}
                value={deleteConfirmName}
                onChange={(e) => setDeleteConfirmName(e.target.value)}
                className="w-full bg-muted/40 border border-rose-500/40 text-foreground text-sm p-2.5 rounded-lg outline-none font-mono"
              />

              <div className="flex justify-end gap-2 pt-2 border-t border-border/40">
                <button
                  type="button"
                  onClick={() => {
                    setIsDeleteModalOpen(false);
                    setDeleteConfirmName('');
                  }}
                  className="px-4 py-2 rounded-lg text-xs font-semibold bg-muted hover:bg-muted/80 text-foreground transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleDeleteCompany}
                  disabled={deletingCompany || deleteConfirmName.trim() !== company.name.trim()}
                  className="px-4 py-2 rounded-lg text-xs font-semibold bg-rose-600 hover:bg-rose-700 text-white transition-colors cursor-pointer disabled:opacity-40"
                >
                  {deletingCompany ? 'Deleting...' : 'Permanently Delete'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
