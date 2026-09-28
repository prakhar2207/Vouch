"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated, removeTokens } from '@/utils/auth';
import { useRole } from '@/hooks/useRole';
import DashboardLayout from '@/components/DashboardLayout';
import StateSelect from '@/components/StateSelect';
import { getStateName } from '@/utils/gstStates';
import { useFinancialYear } from '@/context/FinancialYearContext';
import { useAccountingPeriod } from '@/context/PeriodContext';
import { useToast } from '@/context/ToastContext';
import ProformaDocumentSheet from '@/components/documents/ProformaDocumentSheet';
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
  ArrowRight,
  X,
  ImageIcon,
  Palette,
  Stamp,
  Globe,
  Eye,
  FileText,
  Check,
  Sparkles,
  QrCode,
  Smartphone,
  Monitor
} from 'lucide-react';

export default function SettingsPage() {
  const router = useRouter();
  const { toast } = useToast();
  const { role: currentUserRole, isAdmin, canManageSettings, isReadOnly } = useRole();
  const { availableFYs, activeFY, setActiveFY, setIsClosingModalOpen } = useFinancialYear();
  const { setIsSplitModalOpen } = useAccountingPeriod();
  const [company, setCompany] = useState<any>(null);
  
  // Profile State
  const [name, setName] = useState('');
  const [gstin, setGstin] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [website, setWebsite] = useState('');
  const [address, setAddress] = useState('');
  const [stateCode, setStateCode] = useState('');
  const [proprietorName, setProprietorName] = useState('');
  const [proprietorPhone, setProprietorPhone] = useState('');
  const [signature, setSignature] = useState<File | null>(null);
  const [signaturePreview, setSignaturePreview] = useState<string | null>(null);
  const [stamp, setStamp] = useState<File | null>(null);
  const [stampPreview, setStampPreview] = useState<string | null>(null);
  const [logo, setLogo] = useState<File | null>(null);
  const [logoPreview, setLogoPreview] = useState<string | null>(null);
  
  const [tagline, setTagline] = useState('');
  const [bankName, setBankName] = useState('');
  const [bankAccountNumber, setBankAccountNumber] = useState('');
  const [bankIfsc, setBankIfsc] = useState('');
  const [bankBranch, setBankBranch] = useState('');
  
  // Document Branding & Invoicing Design State
  const [accentColor, setAccentColor] = useState('#0f172a');
  const [logoPosition, setLogoPosition] = useState<'left' | 'center'>('left');
  const [logoHeight, setLogoHeight] = useState<number>(52);
  const [watermarkEnabled, setWatermarkEnabled] = useState(true);
  const [showBankDetails, setShowBankDetails] = useState(true);
  const [showUpiQr, setShowUpiQr] = useState(true);
  const [showTerms, setShowTerms] = useState(true);
  const [showAmountInWords, setShowAmountInWords] = useState(true);
  const [showHsnSummary, setShowHsnSummary] = useState(true);
  const [defaultTermsConditions, setDefaultTermsConditions] = useState(
    "1. Goods once sold will not be taken back or exchanged.\n2. Payment terms: 100% advance or as agreed.\n3. Quotation / Proforma valid for 30 days from date of issue."
  );
  const [defaultNotes, setDefaultNotes] = useState(
    "Thank you for considering our commercial proposal. Please reach out for any clarifications."
  );
  const [showPromoFooter, setShowPromoFooter] = useState(false);
  const [promoTagline, setPromoTagline] = useState('');
  const [promoWebsite, setPromoWebsite] = useState('');
  const [promoSocial, setPromoSocial] = useState('');
  const [promoSupportPhone, setPromoSupportPhone] = useState('');
  const [promoSupportEmail, setPromoSupportEmail] = useState('');
  const [promoMessage, setPromoMessage] = useState('');
  const [promoQrUrl, setPromoQrUrl] = useState('');
  const [previewDevice, setPreviewDevice] = useState<'desktop' | 'mobile'>('desktop');

  
  // Settings State
  const [enableLedgerMapping, setEnableLedgerMapping] = useState(false);
  const [enableManualInvoice, setEnableManualInvoice] = useState(false);
  const [enableAdvancedItemCreation, setEnableAdvancedItemCreation] = useState(false);
  const [complexityLevel, setComplexityLevel] = useState(1);
  const [allowNegativeStock, setAllowNegativeStock] = useState(true);
  const [salesInvoicePrefix, setSalesInvoicePrefix] = useState('');
  const [purchaseInvoicePrefix, setPurchaseInvoicePrefix] = useState('');
  const [saving, setSaving] = useState(false);

  // Team & RBAC State
  const [members, setMembers] = useState<any[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(false);
  const [isInviteModalOpen, setIsInviteModalOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('EMPLOYEE');
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

        if (comp.logo_data) {
          setLogoPreview(comp.logo_data);
        } else if (comp.logo) {
          const base = API_BASE_URL.endsWith('/') ? API_BASE_URL.slice(0, -1) : API_BASE_URL;
          const cleanPath = comp.logo.startsWith('/') ? comp.logo : `/${comp.logo}`;
          setLogoPreview(`${base}${cleanPath}`);
        } else {
          setLogoPreview(null);
        }
        setTagline(comp.tagline || '');
        setBankName(comp.bank_name || '');
        setBankAccountNumber(comp.bank_account_number || '');
        setBankIfsc(comp.bank_ifsc || '');
        setBankBranch(comp.bank_branch || '');
        setWebsite(comp.website || '');

        if (comp.stamp_data) {
          setStampPreview(comp.stamp_data);
        } else if (comp.stamp) {
          const base = API_BASE_URL.endsWith('/') ? API_BASE_URL.slice(0, -1) : API_BASE_URL;
          const cleanPath = comp.stamp.startsWith('/') ? comp.stamp : `/${comp.stamp}`;
          setStampPreview(`${base}${cleanPath}`);
        } else {
          setStampPreview(null);
        }

        // Populate document branding
        const branding = comp.settings?.document_branding || {};
        setAccentColor(branding.accent_color || '#0f172a');
        setLogoPosition(branding.logo_position || 'left');
        setLogoHeight(branding.logo_height || 52);
        setWatermarkEnabled(branding.watermark_enabled !== false);
        setShowBankDetails(branding.show_bank_details !== false);
        setShowUpiQr(branding.show_upi_qr !== false);
        setShowTerms(branding.show_terms !== false);
        setShowAmountInWords(branding.show_amount_in_words !== false);
        setShowHsnSummary(branding.show_hsn_summary !== false);
        setDefaultTermsConditions(branding.default_terms_conditions || "1. Goods once sold will not be taken back or exchanged.\n2. Payment terms: 100% advance or as agreed.\n3. Quotation / Proforma valid for 30 days from date of issue.");
        setDefaultNotes(branding.default_notes || "Thank you for considering our commercial proposal. Please reach out for any clarifications.");
        setShowPromoFooter(Boolean(branding.show_promo_footer));
        setPromoTagline(branding.promo_tagline || '');
        setPromoWebsite(branding.promo_website || '');
        setPromoSocial(branding.promo_social || '');
        setPromoSupportPhone(branding.promo_support_phone || '');
        setPromoSupportEmail(branding.promo_support_email || '');
        setPromoMessage(branding.promo_message || '');
        setPromoQrUrl(branding.promo_qr_url || '');

        // Populate settings
        setEnableLedgerMapping(comp.settings?.enable_ledger_mapping || false);
        setEnableManualInvoice(comp.settings?.enable_manual_invoice_number || false);
        setEnableAdvancedItemCreation(comp.settings?.enable_advanced_item_creation || false);
        setComplexityLevel(comp.settings?.complexity_level || 1);
        setAllowNegativeStock(comp.settings?.allow_negative_stock !== false);
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
      
      // Update Settings & Document Branding
      await axios.patch(`${API_BASE_URL}/api/v1/companies/${company.id}/update_settings/`, {
        enable_ledger_mapping: enableLedgerMapping,
        enable_manual_invoice_number: enableManualInvoice,
        enable_advanced_item_creation: enableAdvancedItemCreation,
        complexity_level: complexityLevel,
        allow_negative_stock: allowNegativeStock,
        sales_invoice_prefix: salesInvoicePrefix,
        purchase_invoice_prefix: purchaseInvoicePrefix,
        document_branding: {
          accent_color: accentColor,
          logo_position: logoPosition,
          logo_height: Number(logoHeight),
          watermark_enabled: watermarkEnabled,
          show_bank_details: showBankDetails,
          show_upi_qr: showUpiQr,
          show_terms: showTerms,
          show_amount_in_words: showAmountInWords,
          show_hsn_summary: showHsnSummary,
          default_terms_conditions: defaultTermsConditions,
          default_notes: defaultNotes,
          show_promo_footer: showPromoFooter,
          promo_tagline: promoTagline,
          promo_website: promoWebsite,
          promo_social: promoSocial,
          promo_support_phone: promoSupportPhone,
          promo_support_email: promoSupportEmail,
          promo_message: promoMessage,
          promo_qr_url: promoQrUrl,
        }
      }, { headers });

      // Update Profile
      const formData = new FormData();
      formData.append('name', name);
      formData.append('gstin', gstin);
      formData.append('email', email);
      formData.append('phone', phone);
      formData.append('website', website);
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

      if (stamp) {
        formData.append('stamp', stamp);
      }
      if (stampPreview) {
        formData.append('stamp_data', stampPreview);
      } else {
        formData.append('remove_stamp', 'true');
        formData.append('stamp_data', '');
      }

      if (logo) {
        formData.append('logo', logo);
      }
      if (logoPreview) {
        formData.append('logo_data', logoPreview);
      } else {
        formData.append('remove_logo', 'true');
        formData.append('logo_data', '');
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
      
      toast.success('Settings & Branding Saved', 'Your changes are now live across proforma invoices and exports.');
      fetchCompany();
    } catch (err: any) {
      console.error(err);
      toast.error('Failed to update profile/settings', err.response?.data?.error || err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleStampChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setStamp(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        if (typeof reader.result === 'string') {
          setStampPreview(reader.result);
        }
      };
      reader.readAsDataURL(file);
    }
  };


  const handleLogoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setLogo(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        if (typeof reader.result === 'string') {
          setLogoPreview(reader.result);
        }
      };
      reader.readAsDataURL(file);
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
      case 'ADMIN':
        return 'bg-purple-500/15 text-purple-400 border-purple-500/30';
      case 'OWNER':
        return 'bg-amber-500/15 text-amber-400 border-amber-500/30';
      case 'CA':
        return 'bg-blue-500/15 text-blue-400 border-blue-500/30';
      case 'EMPLOYEE':
        return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30';
      case 'VIEWER':
      default:
        return 'bg-zinc-500/15 text-zinc-400 border-zinc-500/30';
    }
  };

  const sampleDoc = useMemo(() => ({
    id: 'preview-sample',
    proforma_number: 'PI-26-27-0042',
    date: new Date().toISOString().split('T')[0],
    valid_until: new Date(Date.now() + 30 * 86400000).toISOString().split('T')[0],
    proforma_type: 'PROFORMA',
    status: 'SENT',
    buyer_name: 'Acme Technologies Pvt Ltd',
    buyer_address: '402 Cyber City, DLF Phase 2, Gurugram, Haryana - 122002',
    buyer_gstin: '06AAACA1234A1Z5',
    buyer_state_code: '06',
    buyer_phone: '+91 98765 43210',
    buyer_email: 'accounts@acmetech.com',
    subtotal: 125000,
    taxable_amount: 125000,
    cgst_amount: 11250,
    sgst_amount: 11250,
    igst_amount: 0,
    total_tax: 22500,
    cartage_amount: 500,
    round_off: 0,
    total_amount: 148000,
    terms_and_conditions: defaultTermsConditions,
    customer_notes: defaultNotes,
    items: [
      {
        item_name: 'Enterprise Cloud ERP Subscription',
        description: 'Annual enterprise license with multi-tenant accounting and GST compliance.',
        hsn_code: '998313',
        quantity: 1,
        unit: 'YR',
        rate: 100000,
        discount_percent: 0,
        taxable_amount: 100000,
        gst_rate: 18,
        total_amount: 118000,
      },
      {
        item_name: 'Implementation & CA Setup Services',
        description: 'Chart of accounts configuration, tax ledgers setup, and team onboarding.',
        hsn_code: '998311',
        quantity: 1,
        unit: 'JOB',
        rate: 25000,
        discount_percent: 0,
        taxable_amount: 25000,
        gst_rate: 18,
        total_amount: 29500,
      }
    ]
  }), [defaultTermsConditions, defaultNotes]);

  return (

    <DashboardLayout>
      <div className="max-w-4xl mx-auto space-y-8 pb-16">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">
            Settings
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Manage your business settings
          </p>
        </div>

        {isReadOnly && (
          <div className="bg-amber-500/10 border border-amber-500/30 text-amber-400 p-4 rounded-xl text-xs flex items-center gap-2">
            <Lock className="w-4 h-4 shrink-0" />
            <span>You are currently viewing settings in read-only mode with the Viewer role. Changes cannot be saved.</span>
          </div>
        )}

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
                <div>
                  <label className="block text-xs font-semibold text-muted-foreground mb-1">Company Website</label>
                  <input
                    type="text"
                    value={website}
                    onChange={(e) => setWebsite(e.target.value)}
                    placeholder="e.g. https://www.yourcompany.com"
                    className="w-full bg-muted/40 border border-input text-foreground text-sm p-2.5 rounded-lg outline-none focus:ring-1 focus:ring-primary"
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

              {/* Company Brand Logo (Compressed & Stored in DB) */}
              <div className="pt-4 border-t border-border/40 space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
                        Company Brand Logo
                      </h3>
                      <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
                        OPTIONAL
                      </span>
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      Upload your brand logo for official proforma invoices, quotations, and tax invoices. Auto-compressed and stored in the database.
                    </p>
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row items-start gap-4 p-4 rounded-xl border border-border/40 bg-muted/20">
                  {logoPreview ? (
                    <div className="space-y-2">
                      <div className="w-56 h-24 border border-border/60 rounded-lg bg-card p-2 flex items-center justify-center overflow-hidden">
                        <img
                          src={logoPreview}
                          alt="Company Logo Preview"
                          className="max-h-full max-w-full object-contain"
                        />
                      </div>
                      <div className="flex items-center gap-2">
                        <label className="text-xs font-medium text-primary hover:underline cursor-pointer">
                          <span>Change logo</span>
                          <input
                            type="file"
                            accept="image/*"
                            onChange={handleLogoChange}
                            className="hidden"
                          />
                        </label>
                        <span className="text-muted-foreground">•</span>
                        <button
                          type="button"
                          onClick={() => {
                            setLogo(null);
                            setLogoPreview(null);
                          }}
                          className="text-xs font-medium text-rose-400 hover:underline cursor-pointer"
                        >
                          Delete logo
                        </button>
                      </div>
                    </div>
                  ) : (
                    <label className="flex flex-col items-center justify-center w-full sm:w-64 h-28 border-2 border-dashed border-border/60 hover:border-primary/50 rounded-xl cursor-pointer bg-muted/30 hover:bg-muted/50 transition-colors p-4 text-center">
                      <Upload className="w-5 h-5 text-muted-foreground mb-1.5" />
                      <span className="text-xs font-semibold text-foreground">Upload Company Logo</span>
                      <span className="text-[10px] text-muted-foreground mt-0.5">PNG, JPG, WebP up to 3MB</span>
                      <input
                        type="file"
                        accept="image/*"
                        onChange={handleLogoChange}
                        className="hidden"
                      />
                    </label>
                  )}
                  <div className="text-xs text-muted-foreground flex-1">
                    <p className="font-semibold text-foreground mb-1">Company logo guidelines:</p>
                    <ul className="list-disc list-inside space-y-0.5 text-[11px]">
                      <li>A landscape aspect ratio logo with transparent background works best (e.g. 2:1 or 3:1)</li>
                      <li>Image is compressed automatically and saved in the database</li>
                      <li>Loads dynamically on proforma invoices, sales bills, and PDF downloads</li>
                    </ul>
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

              {/* Official Stamp / Seal (Optional) */}
              <div className="pt-4 border-t border-border/40 space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
                        Official Company Stamp / Seal
                      </h3>
                      <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
                        OPTIONAL
                      </span>
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      Upload an image of your round or rectangular company stamp to render alongside the signature block on proforma invoices.
                    </p>
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row items-start gap-4 p-4 rounded-xl border border-border/40 bg-muted/20">
                  {stampPreview ? (
                    <div className="space-y-2">
                      <div className="w-48 h-24 border border-border/60 rounded-lg bg-card p-2 flex items-center justify-center overflow-hidden">
                        <img
                          src={stampPreview}
                          alt="Official Stamp Preview"
                          className="max-h-full max-w-full object-contain"
                        />
                      </div>
                      <div className="flex items-center gap-2">
                        <label className="text-xs font-medium text-primary hover:underline cursor-pointer">
                          <span>Change stamp</span>
                          <input
                            type="file"
                            accept="image/*"
                            onChange={handleStampChange}
                            className="hidden"
                          />
                        </label>
                        <span className="text-muted-foreground">•</span>
                        <button
                          type="button"
                          onClick={() => {
                            setStamp(null);
                            setStampPreview(null);
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
                      <span className="text-xs font-semibold text-foreground">Upload Stamp / Seal</span>
                      <span className="text-[10px] text-muted-foreground mt-0.5">PNG, JPG up to 2MB (Optional)</span>
                      <input
                        type="file"
                        accept="image/*"
                        onChange={handleStampChange}
                        className="hidden"
                      />
                    </label>
                  )}
                  <div className="text-xs text-muted-foreground flex-1">
                    <p className="font-semibold text-foreground mb-1">Company stamp guidelines:</p>
                    <ul className="list-disc list-inside space-y-0.5 text-[11px]">
                      <li>Stamp onto clean white paper and crop closely</li>
                      <li>Transparent PNG or high-contrast scan works best</li>
                      <li>Prints in the bottom-right signature area</li>
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

            {/* 2. Document Branding & Invoicing Design */}
            <div className="bg-card border border-border/40 rounded-xl shadow-sm p-6 space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-border/40 gap-2">
                <div className="flex items-center gap-2.5">
                  <Palette className="w-5 h-5 text-primary" />
                  <div>
                    <h2 className="text-base font-bold text-foreground">Document Branding & Invoicing Design</h2>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Configure company logo sizing, watermark, brand color, and printable document options for Proforma Invoices and Exports.
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={saveSettings}
                  disabled={saving}
                  className="px-4 py-1.5 bg-primary text-primary-foreground hover:bg-primary/90 rounded-lg text-xs font-semibold shadow transition-colors cursor-pointer disabled:opacity-50 self-start sm:self-auto"
                >
                  {saving ? 'Saving...' : 'Save Branding'}
                </button>
              </div>

              {/* Grid: Left Controls (7 cols) + Right Live Preview (5 cols) */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
                
                {/* Left 6 Columns: Form Controls */}
                <div className="lg:col-span-6 space-y-6">
                  
                  {/* Brand Accent Color Picker */}
                  <div className="space-y-2">
                    <label className="block text-xs font-bold text-foreground uppercase tracking-wider">
                      Brand Accent Color
                    </label>
                    <p className="text-[11px] text-muted-foreground">
                      Applied to document titles, totals, and table headers.
                    </p>
                    <div className="flex items-center gap-2 flex-wrap pt-1">
                      {[
                        { name: 'Navy', hex: '#0f172a' },
                        { name: 'Royal Blue', hex: '#2563eb' },
                        { name: 'Indigo', hex: '#4f46e5' },
                        { name: 'Emerald', hex: '#059669' },
                        { name: 'Crimson', hex: '#dc2626' },
                        { name: 'Slate', hex: '#334155' },
                        { name: 'Amber', hex: '#d97706' },
                      ].map((c) => (
                        <button
                          key={c.hex}
                          type="button"
                          onClick={() => setAccentColor(c.hex)}
                          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-semibold transition-all cursor-pointer ${
                            accentColor.toLowerCase() === c.hex.toLowerCase()
                              ? 'border-primary ring-2 ring-primary/20 bg-primary/10 text-foreground font-bold'
                              : 'border-border/60 bg-muted/40 text-muted-foreground hover:text-foreground'
                          }`}
                        >
                          <span className="w-3.5 h-3.5 rounded-full border border-black/10 shrink-0" style={{ backgroundColor: c.hex }} />
                          <span>{c.name}</span>
                        </button>
                      ))}

                      {/* Custom Color Input */}
                      <div className="flex items-center gap-1.5 px-2 py-1 bg-muted/40 border border-border/60 rounded-lg">
                        <input
                          type="color"
                          value={accentColor}
                          onChange={(e) => setAccentColor(e.target.value)}
                          className="w-5 h-5 rounded cursor-pointer border-none bg-transparent"
                          title="Custom Color Picker"
                        />
                        <input
                          type="text"
                          value={accentColor}
                          onChange={(e) => setAccentColor(e.target.value)}
                          placeholder="#0f172a"
                          maxLength={7}
                          className="w-16 bg-transparent text-xs font-mono outline-none uppercase"
                        />
                      </div>
                    </div>
                  </div>

                  {/* Logo Positioning & Sizing */}
                  <div className="space-y-3 pt-3 border-t border-border/40">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-bold text-foreground uppercase tracking-wider">
                        Logo Position & Sizing
                      </label>
                      <span className="text-[11px] font-mono text-muted-foreground">
                        {logoHeight}px height
                      </span>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-[11px] text-muted-foreground mb-1">Position on Header</label>
                        <div className="inline-flex bg-muted/80 p-0.5 rounded-lg border border-border/60 text-xs w-full">
                          <button
                            type="button"
                            onClick={() => setLogoPosition('left')}
                            className={`flex-1 py-1.5 rounded-md text-xs font-semibold transition-all cursor-pointer text-center ${
                              logoPosition === 'left' ? 'bg-primary text-primary-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground'
                            }`}
                          >
                            Left-Aligned
                          </button>
                          <button
                            type="button"
                            onClick={() => setLogoPosition('center')}
                            className={`flex-1 py-1.5 rounded-md text-xs font-semibold transition-all cursor-pointer text-center ${
                              logoPosition === 'center' ? 'bg-primary text-primary-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground'
                            }`}
                          >
                            Centered
                          </button>
                        </div>
                      </div>

                      <div>
                        <label className="block text-[11px] text-muted-foreground mb-1">Logo Height</label>
                        <input
                          type="range"
                          min={36}
                          max={84}
                          value={logoHeight}
                          onChange={(e) => setLogoHeight(Number(e.target.value))}
                          className="w-full cursor-pointer mt-2"
                        />
                      </div>
                    </div>
                  </div>

                  {/* Document Elements Toggles */}
                  <div className="space-y-2 pt-3 border-t border-border/40">
                    <label className="block text-xs font-bold text-foreground uppercase tracking-wider mb-1">
                      Document Visibility Controls
                    </label>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                      {[
                        { label: 'Company Logo Watermark', state: watermarkEnabled, setter: setWatermarkEnabled, desc: 'Subtle logo centered on each sheet' },
                        { label: 'Bank Details Block', state: showBankDetails, setter: setShowBankDetails, desc: 'A/C number, IFSC, Branch' },
                        { label: 'UPI Payment QR Code', state: showUpiQr, setter: setShowUpiQr, desc: 'Instant mobile UPI scan & pay' },
                        { label: 'Terms & Conditions', state: showTerms, setter: setShowTerms, desc: 'Commercial agreement clauses' },
                        { label: 'Amount in Words', state: showAmountInWords, setter: setShowAmountInWords, desc: 'Indian currency word format' },
                        { label: 'HSN Tax Summary Table', state: showHsnSummary, setter: setShowHsnSummary, desc: 'GST rate-wise tax breakdown' },
                      ].map((item, idx) => (
                        <div key={idx} className="flex items-center justify-between p-2.5 rounded-lg border border-border/40 bg-muted/20">
                          <div className="min-w-0 pr-2">
                            <span className="font-semibold text-foreground text-xs block truncate">{item.label}</span>
                            <span className="text-[10px] text-muted-foreground">{item.desc}</span>
                          </div>
                          <button
                            type="button"
                            onClick={() => item.setter(!item.state)}
                            className={`w-9 h-5 rounded-full transition-all relative shrink-0 cursor-pointer ${
                              item.state ? 'bg-primary' : 'bg-muted-foreground/30'
                            }`}
                          >
                            <div className={`w-3.5 h-3.5 bg-white rounded-full absolute top-0.75 transition-all ${
                              item.state ? 'left-4.5' : 'left-0.75'
                            }`} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Default Terms & Notes */}
                  <div className="space-y-3 pt-3 border-t border-border/40">
                    <label className="block text-xs font-bold text-foreground uppercase tracking-wider">
                      Default Terms & Conditions & Customer Notes
                    </label>
                    <div className="space-y-2">
                      <div>
                        <label className="block text-[11px] text-muted-foreground mb-1">Standard Terms & Conditions</label>
                        <textarea
                          rows={3}
                          value={defaultTermsConditions}
                          onChange={(e) => setDefaultTermsConditions(e.target.value)}
                          className="w-full bg-muted/40 border border-input text-foreground text-xs p-2 rounded-lg outline-none font-mono focus:ring-1 focus:ring-primary"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] text-muted-foreground mb-1">Default Document Remarks / Customer Notes</label>
                        <textarea
                          rows={2}
                          value={defaultNotes}
                          onChange={(e) => setDefaultNotes(e.target.value)}
                          className="w-full bg-muted/40 border border-input text-foreground text-xs p-2 rounded-lg outline-none focus:ring-1 focus:ring-primary"
                        />
                      </div>
                    </div>
                  </div>

                  {/* Promotional Footer Strip (Step 4) */}
                  <div className="space-y-3 pt-3 border-t border-border/40">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="text-xs font-bold text-foreground uppercase tracking-wider flex items-center gap-2">
                          <span>Promotional Footer Strip</span>
                          <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${showPromoFooter ? 'bg-emerald-500/20 text-emerald-400' : 'bg-muted text-muted-foreground'}`}>
                            {showPromoFooter ? 'ENABLED' : 'DISABLED'}
                          </span>
                        </h3>
                        <p className="text-[11px] text-muted-foreground mt-0.5">
                          Adds an optional marketing and brand strip above page numbers on every exported sheet.
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => setShowPromoFooter(!showPromoFooter)}
                        className={`w-11 h-6 rounded-full transition-all relative shrink-0 cursor-pointer ${
                          showPromoFooter ? 'bg-primary' : 'bg-muted-foreground/30'
                        }`}
                      >
                        <div className={`w-4 h-4 bg-white rounded-full absolute top-1 transition-all ${
                          showPromoFooter ? 'left-6' : 'left-1'
                        }`} />
                      </button>
                    </div>

                    {showPromoFooter && (
                      <div className="space-y-3 p-3.5 rounded-xl border border-primary/20 bg-primary/5 text-xs">
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          <div>
                            <label className="block text-[11px] text-muted-foreground mb-1">Promo Tagline</label>
                            <input
                              type="text"
                              placeholder="e.g. INDIA'S FASTEST GROWING B2B HUB"
                              value={promoTagline}
                              onChange={(e) => setPromoTagline(e.target.value)}
                              className="w-full bg-background border border-input text-foreground text-xs p-2 rounded outline-none"
                            />
                          </div>
                          <div>
                            <label className="block text-[11px] text-muted-foreground mb-1">Promo Website URL</label>
                            <input
                              type="text"
                              placeholder="e.g. www.yourdomain.com"
                              value={promoWebsite}
                              onChange={(e) => setPromoWebsite(e.target.value)}
                              className="w-full bg-background border border-input text-foreground text-xs p-2 rounded outline-none"
                            />
                          </div>
                          <div>
                            <label className="block text-[11px] text-muted-foreground mb-1">Social Handles</label>
                            <input
                              type="text"
                              placeholder="e.g. @yourcompany on LinkedIn / X"
                              value={promoSocial}
                              onChange={(e) => setPromoSocial(e.target.value)}
                              className="w-full bg-background border border-input text-foreground text-xs p-2 rounded outline-none"
                            />
                          </div>
                          <div>
                            <label className="block text-[11px] text-muted-foreground mb-1">Support Phone</label>
                            <input
                              type="text"
                              placeholder="e.g. +91 80000 12345"
                              value={promoSupportPhone}
                              onChange={(e) => setPromoSupportPhone(e.target.value)}
                              className="w-full bg-background border border-input text-foreground text-xs p-2 rounded outline-none"
                            />
                          </div>
                          <div>
                            <label className="block text-[11px] text-muted-foreground mb-1">Support Email</label>
                            <input
                              type="email"
                              placeholder="e.g. care@yourcompany.com"
                              value={promoSupportEmail}
                              onChange={(e) => setPromoSupportEmail(e.target.value)}
                              className="w-full bg-background border border-input text-foreground text-xs p-2 rounded outline-none"
                            />
                          </div>
                          <div>
                            <label className="block text-[11px] text-muted-foreground mb-1">Promo QR Code URL</label>
                            <input
                              type="text"
                              placeholder="e.g. https://yourdomain.com/offers"
                              value={promoQrUrl}
                              onChange={(e) => setPromoQrUrl(e.target.value)}
                              className="w-full bg-background border border-input text-foreground text-xs p-2 rounded outline-none"
                            />
                          </div>
                        </div>

                        <div>
                          <div className="flex justify-between items-center mb-1">
                            <label className="text-[11px] text-muted-foreground">Short Promotional Pitch (max 200 chars)</label>
                            <span className="text-[10px] text-muted-foreground">{promoMessage.length}/200</span>
                          </div>
                          <input
                            type="text"
                            maxLength={200}
                            placeholder="e.g. Celebrating 10 years of reliable manufacturing. Ask your account manager about volume discounts!"
                            value={promoMessage}
                            onChange={(e) => setPromoMessage(e.target.value)}
                            className="w-full bg-background border border-input text-foreground text-xs p-2 rounded outline-none"
                          />
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Right 6 Columns: Interactive Live Document Preview Card */}
                <div className="lg:col-span-6 bg-slate-900/5 dark:bg-slate-900/50 border border-border/60 rounded-2xl p-4 flex flex-col items-center">
                  <div className="w-full flex items-center justify-between pb-3 border-b border-border/40 mb-3">
                    <div className="flex items-center gap-2">
                      <Eye className="w-4 h-4 text-primary" />
                      <span className="text-xs font-bold text-foreground">Live Document Preview</span>
                    </div>
                    <span className="text-[10.5px] font-mono text-muted-foreground">
                      Real-time A4 rendering
                    </span>
                  </div>

                  {/* Scaled Preview Frame */}
                  <div className="w-full overflow-hidden flex justify-center bg-slate-200/50 dark:bg-slate-950/70 p-2 sm:p-4 rounded-xl border border-slate-300 dark:border-slate-800">
                    <div className="scale-[0.52] sm:scale-[0.62] origin-top transition-transform duration-200 shadow-xl rounded-sm -mb-[260px] sm:-mb-[200px]">
                      <ProformaDocumentSheet
                        doc={sampleDoc}
                        company={{
                          name: name || 'Your Company Name',
                          legal_name: name || 'Your Legal Entity Name',
                          gstin: gstin || '07AAAAA0000A1Z5',
                          pan: gstin && gstin.length >= 12 ? gstin.slice(2, 12) : 'AAAAA0000A',
                          address: address || '123 Business Boulevard, Commercial District',
                          city: 'New Delhi',
                          state_code: stateCode || '07',
                          state_name: getStateName(stateCode) || 'Delhi',
                          email: email || 'contact@example.com',
                          phone: phone || '+91 98765 00000',
                          website: website || 'www.example.com',
                          tagline: tagline,
                          bank_name: bankName || 'HDFC Bank Ltd',
                          bank_account_number: bankAccountNumber || '50200012345678',
                          bank_ifsc: bankIfsc || 'HDFC0001234',
                          bank_branch: bankBranch || 'Connaught Place',
                          logo_data: logoPreview,
                          signature_data: signaturePreview,
                          stamp_data: stampPreview,
                        }}
                        branding={{
                          accent_color: accentColor,
                          logo_position: logoPosition,
                          logo_height: Number(logoHeight),
                          watermark_enabled: watermarkEnabled,
                          show_bank_details: showBankDetails,
                          show_upi_qr: showUpiQr,
                          show_terms: showTerms,
                          show_amount_in_words: showAmountInWords,
                          show_hsn_summary: showHsnSummary,
                          default_terms_conditions: defaultTermsConditions,
                          default_notes: defaultNotes,
                          show_promo_footer: showPromoFooter,
                          promo_tagline: promoTagline,
                          promo_website: promoWebsite,
                          promo_social: promoSocial,
                          promo_support_phone: promoSupportPhone,
                          promo_support_email: promoSupportEmail,
                          promo_message: promoMessage,
                          promo_qr_url: promoQrUrl,
                        }}
                        isPreviewMode={true}
                      />
                    </div>
                  </div>

                  <p className="text-[11px] text-muted-foreground text-center mt-4">
                    This live preview reflects exactly how proforma invoices, quotations, and official vector PDFs are rendered.
                  </p>
                </div>
              </div>

              <div className="flex justify-end pt-3 border-t border-border/40">
                <button
                  type="button"
                  onClick={saveSettings}
                  disabled={saving}
                  className="px-6 py-2 bg-primary text-primary-foreground hover:bg-primary/90 rounded-xl text-xs font-bold shadow transition-colors cursor-pointer disabled:opacity-50"
                >
                  {saving ? 'Saving Branding...' : 'Save Document Branding'}
                </button>
              </div>
            </div>

            {/* 3. Invoicing, Prefixes & Stock Controls */}
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
                      Assign Owner, CA (Chartered Accountant), Employee, or Viewer access roles
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
                            {m.role === 'OWNER' || m.role === 'ADMIN' ? (
                              <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${getRoleBadge(m.role)}`}>
                                {m.role}
                              </span>
                            ) : (
                              <select
                                value={m.role}
                                onChange={(e) => handleUpdateRole(m.id, e.target.value)}
                                className="text-xs bg-muted/60 border border-input rounded px-2 py-1 text-foreground font-semibold outline-none cursor-pointer"
                              >
                                <option value="ADMIN">ADMIN</option>
                                <option value="CA">CA</option>
                                <option value="EMPLOYEE">EMPLOYEE</option>
                                <option value="VIEWER">VIEWER</option>
                              </select>
                            )}
                          </td>

                          <td className="px-4 py-3 text-muted-foreground font-mono">{m.created_at || 'Active'}</td>

                          <td className="px-4 py-3 text-right">
                            {m.role !== 'OWNER' && (m.role !== 'ADMIN' || currentUserRole === 'OWNER') && !m.is_current_user && (
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
                  <h2 className="text-base font-bold text-foreground">Maintenance</h2>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Tools to keep your books in order
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Sync Tax Ledgers */}
                <div className="p-4 bg-muted/30 border border-border/40 rounded-xl flex flex-col justify-between space-y-3">
                  <div>
                    <h3 className="text-xs font-bold text-foreground flex items-center gap-2">
                      <span>Fix Tax Accounts</span>
                      <span className="text-[10px] font-mono px-1.5 py-0.2 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded font-semibold">
                        TAX
                      </span>
                    </h3>
                    <p className="text-xs text-muted-foreground mt-1">
                      Checks for missing tax accounts and creates them automatically
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleSyncTaxLedgers}
                    disabled={syncingTax}
                    className="px-3.5 py-2 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/30 rounded-lg text-xs font-bold transition-colors w-fit flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${syncingTax ? 'animate-spin' : ''}`} />
                    <span>{syncingTax ? 'Fixing...' : 'Fix Tax Accounts'}</span>
                  </button>
                </div>

                {/* Rebuild Ledger Balances */}
                <div className="p-4 bg-muted/30 border border-border/40 rounded-xl flex flex-col justify-between space-y-3">
                  <div>
                    <h3 className="text-xs font-bold text-foreground flex items-center gap-2">
                      <span>Recalculate Balances</span>
                      <span className="text-[10px] font-mono px-1.5 py-0.2 bg-blue-500/10 text-blue-400 border border-blue-500/20 rounded font-semibold">
                        BALANCES
                      </span>
                    </h3>
                    <p className="text-xs text-muted-foreground mt-1">
                      Recalculates all account balances from your transaction history to fix any discrepancies
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleRebuildBalances}
                    disabled={rebuildingBalances}
                    className="px-3.5 py-2 bg-blue-600/10 hover:bg-blue-600/20 text-blue-400 border border-blue-500/30 rounded-lg text-xs font-bold transition-colors w-fit flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                  >
                    <Database className={`w-3.5 h-3.5 ${rebuildingBalances ? 'animate-spin' : ''}`} />
                    <span>{rebuildingBalances ? 'Recalculating...' : 'Recalculate Balances'}</span>
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
                              onClick={() => {
                                setActiveFY(fy);
                                toast.success("Switched Financial Year", `Active year changed to ${fy.name || fy.code}`);
                              }}
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
                    <option value="ADMIN">ADMIN (Full administrative access, company settings, team management)</option>
                    <option value="CA">CA (Full Accounting: Ledgers, Daybook, Vouchers, Reports)</option>
                    <option value="EMPLOYEE">EMPLOYEE (Operational: Sales, Purchases, Stock, Parties)</option>
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
