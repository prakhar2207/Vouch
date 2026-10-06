"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated, removeTokens } from '@/utils/auth';
import { useRole } from '@/hooks/useRole';
import { useCompany, Company } from '@/context/CompanyContext';
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
  Monitor,
  Key,
  Send,
  User as UserIcon,
  Briefcase,
  Plus,
  Save,
  ChevronRight,
  ChevronDown,
  Calendar,
  CreditCard,
  Package,
  CheckCircle,
  ExternalLink,
  Shield,
  Landmark
} from 'lucide-react';

export default function SettingsPage() {
  const router = useRouter();
  const { toast } = useToast();
  const { user, role: currentUserRole, isAdmin, canManageSettings, isReadOnly, refreshUser } = useRole();
  const { activeCompany, availableCompanies, setActiveCompany, refreshCompanies } = useCompany();
  const { availableFYs, activeFY, setActiveFY, setIsClosingModalOpen } = useFinancialYear();
  const { setIsSplitModalOpen } = useAccountingPeriod();

  // Active Navigation Tab
  // Options: 'account-profile' | 'account-companies' | 'firm-profile' | 'branding' | 'invoicing-inventory' | 'gst-portal' | 'team' | 'financial-years' | 'maintenance' | 'danger-zone'
  const [activeTab, setActiveTab] = useState<string>('account-profile');

  // Currently Selected Company for Company Settings
  const [selectedCompanyId, setSelectedCompanyId] = useState<string>('');
  const [company, setCompany] = useState<any>(null);

  // User Profile State (Account Settings)
  const [userFirstName, setUserFirstName] = useState('');
  const [userLastName, setUserLastName] = useState('');
  const [userPassword, setUserPassword] = useState('');
  const [userConfirmPassword, setUserConfirmPassword] = useState('');
  const [savingUser, setSavingUser] = useState(false);

  // Add Company Modal State
  const [isAddCompanyModalOpen, setIsAddCompanyModalOpen] = useState(false);
  const [newCompName, setNewCompName] = useState('');
  const [newCompGstin, setNewCompGstin] = useState('');
  const [newCompStateCode, setNewCompStateCode] = useState('');
  const [newCompPhone, setNewCompPhone] = useState('');
  const [newCompEmail, setNewCompEmail] = useState('');
  const [newCompAddress, setNewCompAddress] = useState('');
  const [newCompProprietor, setNewCompProprietor] = useState('');
  const [creatingCompany, setCreatingCompany] = useState(false);

  // Company Profile State
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
  const [upiId, setUpiId] = useState('');

  // GST Portal OTP Direct Connect State
  const [portalConnected, setPortalConnected] = useState(false);
  const [portalUsername, setPortalUsername] = useState('');
  const [portalExpiresAt, setPortalExpiresAt] = useState<string | null>(null);
  const [portalOtp, setPortalOtp] = useState('');
  const [portalTxnId, setPortalTxnId] = useState('');
  const [portalStep, setPortalStep] = useState<'idle' | 'otp' | 'connected'>('idle');
  const [portalLoading, setPortalLoading] = useState(false);
  const [portalError, setPortalError] = useState<string | null>(null);
  const [portalSuccess, setPortalSuccess] = useState<string | null>(null);

  // Branding State
  const [accentColor, setAccentColor] = useState('#0f172a');
  const [logoPosition, setLogoPosition] = useState<'left' | 'center'>('left');
  const [logoHeight, setLogoHeight] = useState<number>(52);
  const [showLogo, setShowLogo] = useState(true);
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

  // Controls & Settings State
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

  // Read URL query params on load (supports ?tab=... and ?action=new)
  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login');
      return;
    }
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      const tabParam = params.get('tab');
      if (tabParam) {
        setActiveTab(tabParam);
      }
      if (params.get('action') === 'new' || params.get('new') === '1') {
        setIsAddCompanyModalOpen(true);
      }
    }
  }, [router]);

  // Synchronize User state
  useEffect(() => {
    if (user) {
      setUserFirstName(user.first_name || '');
      setUserLastName(user.last_name || '');
    }
  }, [user]);

  // Synchronize company list and active selection
  useEffect(() => {
    if (availableCompanies && availableCompanies.length > 0) {
      const currentCid = selectedCompanyId || activeCompany?.id || availableCompanies[0].id;
      if (!selectedCompanyId || selectedCompanyId !== currentCid) {
        setSelectedCompanyId(currentCid);
        loadCompanyData(currentCid);
      }
    }
  }, [availableCompanies, activeCompany]);

  const loadCompanyData = async (compId: string) => {
    if (!compId) return;
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/${compId}/`, { headers });
      const comp = compRes.data?.data || compRes.data;
      if (comp) {
        setCompany(comp);
        populateCompanyFields(comp);
        fetchGSTConfig(comp.id);
        fetchMembers(comp.id);
      }
    } catch (err) {
      console.error('Failed to load company details:', err);
    }
  };

  const populateCompanyFields = (comp: any) => {
    setName(comp.name || '');
    setGstin(comp.gstin || '');
    setEmail(comp.email || '');
    setPhone(comp.phone || '');
    setAddress(comp.address || '');
    setStateCode(comp.state_code || '');
    setProprietorName(comp.proprietor_name || '');
    setProprietorPhone(comp.proprietor_phone || '');
    setWebsite(comp.website || '');
    setTagline(comp.tagline || '');
    setBankName(comp.bank_name || '');
    setBankAccountNumber(comp.bank_account_number || '');
    setBankIfsc(comp.bank_ifsc || '');
    setBankBranch(comp.bank_branch || '');
    setUpiId(comp.upi_id || '');

    if (comp.signature_data) {
      setSignaturePreview(comp.signature_data);
    } else if (comp.proprietor_signature) {
      const base = API_BASE_URL.endsWith('/') ? API_BASE_URL.slice(0, -1) : API_BASE_URL;
      const cleanPath = comp.proprietor_signature.startsWith('/') ? comp.proprietor_signature : `/${comp.proprietor_signature}`;
      setSignaturePreview(`${base}${cleanPath}`);
    } else {
      setSignaturePreview(null);
    }

    if (comp.stamp_data) {
      setStampPreview(comp.stamp_data);
    } else if (comp.stamp) {
      const base = API_BASE_URL.endsWith('/') ? API_BASE_URL.slice(0, -1) : API_BASE_URL;
      const cleanPath = comp.stamp.startsWith('/') ? comp.stamp : `/${comp.stamp}`;
      setStampPreview(`${base}${cleanPath}`);
    } else {
      setStampPreview(null);
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

    // Populate document branding
    const branding = comp.settings?.document_branding || {};
    setAccentColor(branding.accent_color || '#0f172a');
    setLogoPosition(branding.logo_position || 'left');
    setLogoHeight(branding.logo_height || 52);
    setShowLogo(branding.show_logo !== false);
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
  };

  const handleTabChange = (newTab: string) => {
    setActiveTab(newTab);
    if (typeof window !== 'undefined') {
      const url = new URL(window.location.href);
      url.searchParams.set('tab', newTab);
      window.history.replaceState({}, '', url.toString());
    }
  };

  const fetchMembers = async (compId?: string) => {
    const cid = compId || company?.id || selectedCompanyId;
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

  const fetchGSTConfig = async (companyId: string) => {
    try {
      const token = getAccessToken();
      const res = await axios.get(`${API_BASE_URL}/api/v1/gst/config/${companyId}/`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.data?.success && res.data.config) {
        setPortalConnected(Boolean(res.data.config.is_portal_connected));
        setPortalUsername(res.data.config.portal_username || res.data.config.eway_username || '');
        setPortalExpiresAt(res.data.config.token_expires_at || null);
        if (res.data.config.is_portal_connected) {
          setPortalStep('connected');
        } else {
          setPortalStep('idle');
        }
      }
    } catch (e) {
      console.warn("Could not fetch GST config", e);
    }
  };

  // User Profile Update (Account Settings)
  const handleSaveUserProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingUser(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const payload: any = {
        first_name: userFirstName.trim(),
        last_name: userLastName.trim()
      };
      if (userPassword.trim()) {
        if (userPassword !== userConfirmPassword) {
          toast.error("Passwords do not match", "Please make sure password confirmation matches.");
          setSavingUser(false);
          return;
        }
        payload.password = userPassword;
      }
      const res = await axios.patch(`${API_BASE_URL}/api/v1/auth/me/`, payload, { headers });
      if (res.data?.success) {
        toast.success("Profile Updated", "Your personal details have been saved.");
        setUserPassword('');
        setUserConfirmPassword('');
        await refreshUser();
      }
    } catch (err: any) {
      toast.error("Failed to update profile", err.response?.data?.error || err.message);
    } finally {
      setSavingUser(false);
    }
  };

  // Create New Company Handler
  const handleCreateCompany = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCompName.trim()) {
      toast.error("Company Name is required");
      return;
    }
    setCreatingCompany(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const payload = {
        name: newCompName.trim(),
        legal_name: newCompName.trim(),
        gstin: newCompGstin.trim().toUpperCase(),
        state_code: newCompStateCode.trim(),
        phone: newCompPhone.trim(),
        email: newCompEmail.trim(),
        address: newCompAddress.trim(),
        proprietor_name: newCompProprietor.trim()
      };
      const res = await axios.post(`${API_BASE_URL}/api/v1/companies/`, payload, { headers });
      const created = res.data?.data || res.data;
      if (created && created.id) {
        toast.success("Company Created Successfully!", `${created.name} is now ready with pre-configured accounts.`);
        setIsAddCompanyModalOpen(false);
        setNewCompName('');
        setNewCompGstin('');
        setNewCompStateCode('');
        setNewCompPhone('');
        setNewCompEmail('');
        setNewCompAddress('');
        setNewCompProprietor('');
        await refreshCompanies();
        setActiveCompany(created);
        setSelectedCompanyId(created.id);
        await loadCompanyData(created.id);
        handleTabChange('firm-profile');
      }
    } catch (err: any) {
      toast.error("Failed to create company", err.response?.data?.error || err.message);
    } finally {
      setCreatingCompany(false);
    }
  };

  // Save Company Settings & Branding
  const saveCompanySettings = async () => {
    if (!company) return;
    setSaving(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      
      // 1. Update Settings & Document Branding
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
          show_logo: showLogo,
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

      // 2. Update Profile & Legal Info
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
      formData.append('upi_id', upiId);
      
      await axios.patch(`${API_BASE_URL}/api/v1/companies/${company.id}/`, formData, { 
        headers: {
          ...headers,
          'Content-Type': 'multipart/form-data'
        }
      });
      
      toast.success('Settings Saved Successfully', `Changes saved for ${name || company.name}.`);
      await refreshCompanies();
      loadCompanyData(company.id);
    } catch (err: any) {
      console.error(err);
      toast.error('Failed to update settings', err.response?.data?.error || err.message);
    } finally {
      setSaving(false);
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
        toast.success('Ledger balances rebuilt', res.data.message || 'All balances recomputed from entries.');
      } else {
        toast.error('Rebuild failed', res.data?.error);
      }
    } catch (err: any) {
      toast.error('Rebuild failed', err.response?.data?.error || err.message);
    } finally {
      setRebuildingBalances(false);
    }
  };

  // GST Portal OTP Handlers
  const handleRequestPortalOTP = async () => {
    if (!company?.id) return;
    setPortalLoading(true);
    setPortalError(null);
    setPortalSuccess(null);
    try {
      const token = getAccessToken();
      const res = await axios.post(`${API_BASE_URL}/api/v1/gst/portal/request-otp/`, {
        company_id: company.id,
        gstin: gstin,
        username: portalUsername || gstin,
      }, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.data?.success) {
        setPortalTxnId(res.data.txn_id || '');
        setPortalStep('otp');
        setPortalSuccess(res.data.message || `OTP sent to mobile registered with GST Portal.`);
        toast.success("GST Portal OTP Sent", res.data.message || "Check your registered mobile number.");
      } else {
        setPortalError(res.data?.error || "Failed to request OTP from GST Portal.");
      }
    } catch (err: any) {
      setPortalError(err.response?.data?.error || "Error contacting GST Portal gateway.");
    } finally {
      setPortalLoading(false);
    }
  };

  const handleVerifyPortalOTP = async () => {
    if (!company?.id) return;
    setPortalLoading(true);
    setPortalError(null);
    try {
      const token = getAccessToken();
      const res = await axios.post(`${API_BASE_URL}/api/v1/gst/portal/verify-otp/`, {
        company_id: company.id,
        otp: portalOtp,
        txn_id: portalTxnId,
        gstin: gstin,
        username: portalUsername || gstin,
      }, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.data?.success) {
        setPortalConnected(true);
        setPortalStep('connected');
        setPortalSuccess("GST Portal connected successfully! 30-day session active.");
        toast.success("GST Connected", "Your business is now directly connected to the GST Portal.");
        fetchGSTConfig(company.id);
      } else {
        setPortalError(res.data?.error || "Invalid OTP entered.");
      }
    } catch (err: any) {
      setPortalError(err.response?.data?.error || "Failed to verify OTP.");
    } finally {
      setPortalLoading(false);
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
        await refreshCompanies();
        if (availableCompanies.length > 1) {
          const next = availableCompanies.find(c => c.id !== company.id) || availableCompanies[0];
          setActiveCompany(next);
          setSelectedCompanyId(next.id);
          loadCompanyData(next.id);
          setIsDeleteModalOpen(false);
        } else {
          removeTokens();
          router.push('/login');
        }
      }
    } catch (err: any) {
      toast.error('Deletion failed', err.response?.data?.error || err.message);
    } finally {
      setDeletingCompany(false);
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
        item_name: 'Industrial Transmission Belts (Size 42)',
        description: 'Heavy-duty synthetic rubber transmission belt with polyester cord.',
        hsn_code: '40103990',
        quantity: 100,
        unit: 'PCS',
        rate: 1000,
        discount_percent: 0,
        taxable_amount: 100000,
        gst_rate: 18,
        total_amount: 118000,
      },
      {
        item_name: 'High-Temperature Industrial Conveyor Belt',
        description: 'Multi-ply heat resistant conveyor belt with vulcanized edges.',
        hsn_code: '40101290',
        quantity: 1,
        unit: 'MTR',
        rate: 25000,
        discount_percent: 0,
        taxable_amount: 25000,
        gst_rate: 18,
        total_amount: 29500,
      }
    ]
  }), [defaultTermsConditions, defaultNotes]);

  // Is current tab an editable company form tab?
  const isCompanyFormTab = ['firm-profile', 'branding', 'invoicing-inventory'].includes(activeTab);

  return (
    <DashboardLayout>
      <div className="pb-16 max-w-7xl mx-auto space-y-6">
        
        {/* HEADER BREADCRUMB & TITLE */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 border-b border-border/40 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider bg-primary/10 text-primary border border-primary/20 rounded-md">
                Settings & Workspaces
              </span>
            </div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground mt-1">
              Settings
            </h1>
            <p className="text-xs text-muted-foreground mt-0.5">
              Manage your personal user account, multi-company workspaces, and entity billing rules
            </p>
          </div>

          {/* Top Actions: Save button or Add Company button */}
          <div className="flex items-center gap-2">
            {isCompanyFormTab && !isReadOnly && (
              <button
                onClick={saveCompanySettings}
                disabled={saving}
                className="px-4 py-2 bg-primary text-primary-foreground hover:bg-primary/90 rounded-xl text-xs font-bold shadow-sm transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
              >
                <Save className={`w-3.5 h-3.5 ${saving ? 'animate-spin' : ''}`} />
                <span>{saving ? 'Saving Changes...' : 'Save Settings'}</span>
              </button>
            )}
            <button
              onClick={() => setIsAddCompanyModalOpen(true)}
              className="px-3.5 py-2 rounded-xl border border-primary/30 bg-primary/10 hover:bg-primary/20 text-primary text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer shadow-2xs"
            >
              <Plus className="w-3.5 h-3.5 stroke-[2.5]" />
              <span>Add New Company</span>
            </button>
          </div>
        </div>

        {/* READ ONLY NOTIFICATION IF VIEWER */}
        {isReadOnly && (
          <div className="bg-amber-500/10 border border-amber-500/30 text-amber-500 p-3.5 rounded-xl text-xs flex items-center gap-2">
            <Lock className="w-4 h-4 shrink-0" />
            <span>You are currently viewing settings in read-only mode with the Viewer role. Changes cannot be saved.</span>
          </div>
        )}

        {/* TWO-COLUMN LAYOUT: SIDEBAR NAVIGATION + CONTENT PANE */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          
          {/* ================= LEFT COLUMN: SETTINGS SIDEBAR ================= */}
          <div className="lg:col-span-4 xl:col-span-3 space-y-5">
            
            {/* GROUP 1: ACCOUNT SETTINGS */}
            <div className="bg-card border border-border/50 rounded-2xl p-3 shadow-2xs space-y-1">
              <div className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70 flex items-center gap-1.5">
                <UserIcon className="w-3 h-3 text-primary" />
                <span>Account Settings</span>
              </div>

              <button
                onClick={() => handleTabChange('account-profile')}
                className={`w-full text-left px-3 py-2 rounded-xl text-xs transition-all flex items-center justify-between cursor-pointer ${
                  activeTab === 'account-profile'
                    ? 'bg-primary/10 text-primary font-bold border border-primary/20 shadow-2xs'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted/60 font-medium'
                }`}
              >
                <div className="flex items-center gap-2.5 truncate">
                  <ShieldCheck className="w-4 h-4 shrink-0" />
                  <span className="truncate">My Profile & Security</span>
                </div>
                <ChevronRight className="w-3 h-3 text-muted-foreground/60 shrink-0" />
              </button>

              <button
                onClick={() => handleTabChange('account-companies')}
                className={`w-full text-left px-3 py-2 rounded-xl text-xs transition-all flex items-center justify-between cursor-pointer ${
                  activeTab === 'account-companies'
                    ? 'bg-primary/10 text-primary font-bold border border-primary/20 shadow-2xs'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted/60 font-medium'
                }`}
              >
                <div className="flex items-center gap-2.5 truncate">
                  <Briefcase className="w-4 h-4 shrink-0" />
                  <span className="truncate">Companies & Entities</span>
                </div>
                <span className="px-1.5 py-0.5 rounded-full text-[10px] font-mono font-bold bg-muted text-foreground">
                  {availableCompanies.length}
                </span>
              </button>
            </div>

            {/* GROUP 2: COMPANY SETTINGS (WITH INLINE ENTITY PICKER) */}
            <div className="bg-card border border-border/50 rounded-2xl p-3 shadow-2xs space-y-2">
              <div className="px-3 py-1.5 flex items-center justify-between">
                <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70 flex items-center gap-1.5">
                  <Building className="w-3 h-3 text-blue-500" />
                  <span>Company Settings</span>
                </span>
              </div>

              {/* Entity Context Switcher Box */}
              <div className="p-2.5 rounded-xl bg-muted/40 border border-border/40 space-y-1">
                <div className="text-[10px] text-muted-foreground font-semibold flex items-center justify-between">
                  <span>Selected Firm:</span>
                  <span className="font-mono text-[9px] uppercase px-1.5 py-0.2 rounded bg-primary/10 text-primary">
                    {company?.gstin ? 'GST Registered' : 'Active'}
                  </span>
                </div>
                <select
                  value={selectedCompanyId}
                  onChange={(e) => {
                    const cid = e.target.value;
                    setSelectedCompanyId(cid);
                    const found = availableCompanies.find(c => c.id === cid);
                    if (found) {
                      setActiveCompany(found);
                    }
                    loadCompanyData(cid);
                  }}
                  className="w-full text-xs font-bold text-foreground bg-card border border-border/60 rounded-lg p-2 outline-none focus:ring-1 focus:ring-primary cursor-pointer truncate"
                >
                  {availableCompanies.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} {activeCompany?.id === c.id ? '(Active)' : ''}
                    </option>
                  ))}
                </select>
              </div>

              {/* Company Sub-Navigation Items */}
              <div className="space-y-0.5 pt-1">
                {[
                  { id: 'firm-profile', label: 'Firm Details & Profile', icon: Building },
                  { id: 'branding', label: 'Document Branding', icon: Palette },
                  { id: 'invoicing-inventory', label: 'Invoicing & Inventory', icon: Sliders },
                  { id: 'gst-portal', label: 'GST Portal Direct Connect', icon: Globe },
                  { id: 'team', label: 'Team & Roles (RBAC)', icon: Users },
                  { id: 'financial-years', label: 'Financial Year & Period', icon: Calendar },
                  { id: 'maintenance', label: 'Diagnostics & Balancing', icon: Wrench },
                  { id: 'danger-zone', label: 'Danger Zone', icon: AlertTriangle, danger: true },
                ].map((item) => {
                  const Icon = item.icon;
                  const isActive = activeTab === item.id;
                  return (
                    <button
                      key={item.id}
                      onClick={() => handleTabChange(item.id)}
                      className={`w-full text-left px-3 py-2 rounded-xl text-xs transition-all flex items-center justify-between cursor-pointer ${
                        isActive
                          ? item.danger
                            ? 'bg-rose-500/10 text-rose-500 font-bold border border-rose-500/30'
                            : 'bg-primary/10 text-primary font-bold border border-primary/20 shadow-2xs'
                          : item.danger
                          ? 'text-rose-500/80 hover:text-rose-500 hover:bg-rose-500/5 font-medium'
                          : 'text-muted-foreground hover:text-foreground hover:bg-muted/60 font-medium'
                      }`}
                    >
                      <div className="flex items-center gap-2.5 truncate">
                        <Icon className={`w-4 h-4 shrink-0 ${item.danger ? 'text-rose-500' : ''}`} />
                        <span className="truncate">{item.label}</span>
                      </div>
                      <ChevronRight className="w-3 h-3 text-muted-foreground/60 shrink-0" />
                    </button>
                  );
                })}
              </div>
            </div>

          </div>

          {/* ================= RIGHT COLUMN: SETTINGS CONTENT PANE ================= */}
          <div className="lg:col-span-8 xl:col-span-9 space-y-6">

            {/* TAB 1: MY PROFILE & SECURITY (ACCOUNT SETTINGS) */}
            {activeTab === 'account-profile' && (
              <div className="space-y-6 animate-in fade-in duration-200">
                <div className="bg-card border border-border/50 rounded-2xl p-6 shadow-2xs space-y-6">
                  <div className="flex items-center gap-3 border-b border-border/40 pb-4">
                    <div className="p-2.5 rounded-xl bg-primary/10 text-primary">
                      <UserIcon className="w-5 h-5" />
                    </div>
                    <div>
                      <h2 className="text-base font-bold text-foreground">User Profile & Account</h2>
                      <p className="text-xs text-muted-foreground">Manage your personal details and authentication credentials</p>
                    </div>
                  </div>

                  <form onSubmit={handleSaveUserProfile} className="space-y-5">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-semibold text-muted-foreground mb-1">First Name</label>
                        <input
                          type="text"
                          value={userFirstName}
                          onChange={(e) => setUserFirstName(e.target.value)}
                          placeholder="Your first name"
                          className="w-full bg-muted/30 border border-input text-foreground text-sm p-2.5 rounded-xl outline-none focus:ring-1 focus:ring-primary"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-muted-foreground mb-1">Last Name</label>
                        <input
                          type="text"
                          value={userLastName}
                          onChange={(e) => setUserLastName(e.target.value)}
                          placeholder="Your last name"
                          className="w-full bg-muted/30 border border-input text-foreground text-sm p-2.5 rounded-xl outline-none focus:ring-1 focus:ring-primary"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-muted-foreground mb-1">Registered Email</label>
                        <input
                          type="email"
                          value={user?.email || ''}
                          disabled
                          className="w-full bg-muted/60 border border-input text-muted-foreground text-sm p-2.5 rounded-xl outline-none cursor-not-allowed font-mono"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-muted-foreground mb-1">Global System Role</label>
                        <div className="flex items-center gap-2 h-[42px] px-3 bg-muted/30 border border-input rounded-xl">
                          <Shield className="w-4 h-4 text-primary" />
                          <span className="text-xs font-mono font-bold text-foreground uppercase">{currentUserRole || 'OWNER'}</span>
                        </div>
                      </div>
                    </div>

                    {/* Change Password Block */}
                    <div className="pt-4 border-t border-border/40 space-y-4">
                      <div>
                        <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Change Password</h3>
                        <p className="text-[11px] text-muted-foreground mt-0.5">Leave blank if you do not wish to update your login password.</p>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div>
                          <label className="block text-xs font-semibold text-muted-foreground mb-1">New Password</label>
                          <input
                            type="password"
                            value={userPassword}
                            onChange={(e) => setUserPassword(e.target.value)}
                            placeholder="••••••••••••"
                            className="w-full bg-muted/30 border border-input text-foreground text-sm p-2.5 rounded-xl outline-none focus:ring-1 focus:ring-primary"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-semibold text-muted-foreground mb-1">Confirm New Password</label>
                          <input
                            type="password"
                            value={userConfirmPassword}
                            onChange={(e) => setUserConfirmPassword(e.target.value)}
                            placeholder="••••••••••••"
                            className="w-full bg-muted/30 border border-input text-foreground text-sm p-2.5 rounded-xl outline-none focus:ring-1 focus:ring-primary"
                          />
                        </div>
                      </div>
                    </div>

                    <div className="flex justify-end pt-2">
                      <button
                        type="submit"
                        disabled={savingUser}
                        className="px-5 py-2.5 bg-primary text-primary-foreground hover:bg-primary/90 rounded-xl text-xs font-bold shadow-sm transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
                      >
                        <Save className={`w-3.5 h-3.5 ${savingUser ? 'animate-spin' : ''}`} />
                        <span>{savingUser ? 'Updating Profile...' : 'Update Account Profile'}</span>
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            )}

            {/* TAB 2: COMPANIES & ENTITIES HUB (ACCOUNT SETTINGS) */}
            {activeTab === 'account-companies' && (
              <div className="space-y-6 animate-in fade-in duration-200">
                <div className="bg-card border border-border/50 rounded-2xl p-6 shadow-2xs space-y-5">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/40 pb-4">
                    <div className="flex items-center gap-3">
                      <div className="p-2.5 rounded-xl bg-blue-500/10 text-blue-500">
                        <Briefcase className="w-5 h-5" />
                      </div>
                      <div>
                        <h2 className="text-base font-bold text-foreground">Companies & Workspaces Hub</h2>
                        <p className="text-xs text-muted-foreground">Manage multi-entity businesses, switch active workspace, or register a new firm</p>
                      </div>
                    </div>

                    <button
                      onClick={() => setIsAddCompanyModalOpen(true)}
                      className="px-3.5 py-2 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-bold flex items-center gap-1.5 cursor-pointer shadow-sm transition-all shrink-0"
                    >
                      <Plus className="w-3.5 h-3.5 stroke-[2.5]" />
                      <span>Add New Company</span>
                    </button>
                  </div>

                  {/* List of Companies */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {availableCompanies.map((comp) => {
                      const isCurrentActive = activeCompany?.id === comp.id;
                      const isBeingEdited = selectedCompanyId === comp.id;
                      return (
                        <div
                          key={comp.id}
                          className={`p-4 rounded-2xl border transition-all space-y-3 ${
                            isCurrentActive
                              ? 'bg-primary/5 border-primary/40 shadow-xs'
                              : 'bg-card border-border/60 hover:border-border'
                          }`}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="flex items-center gap-2.5 min-w-0">
                              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary/20 to-primary/5 border border-primary/20 flex items-center justify-center text-sm font-bold text-primary shrink-0 uppercase">
                                {comp.name[0]}
                              </div>
                              <div className="min-w-0">
                                <h3 className="font-bold text-sm text-foreground truncate">{comp.name}</h3>
                                <p className="text-[11px] font-mono text-muted-foreground truncate">
                                  {comp.gstin || 'Unregistered / Composition'}
                                </p>
                              </div>
                            </div>

                            {isCurrentActive && (
                              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/25 shrink-0 flex items-center gap-1">
                                <CheckCircle className="w-2.5 h-2.5" />
                                <span>Active</span>
                              </span>
                            )}
                          </div>

                          <div className="text-[11px] text-muted-foreground space-y-1 pt-1 border-t border-border/30">
                            <div className="truncate"><strong>State:</strong> {comp.state_code ? `${comp.state_code} (${getStateName(comp.state_code)})` : 'N/A'}</div>
                            {comp.address && <div className="truncate"><strong>Address:</strong> {comp.address}</div>}
                          </div>

                          <div className="flex items-center gap-2 pt-2">
                            {!isCurrentActive ? (
                              <button
                                onClick={() => {
                                  setActiveCompany(comp);
                                  setSelectedCompanyId(comp.id);
                                  loadCompanyData(comp.id);
                                  toast.success(`Switched to ${comp.name}`);
                                }}
                                className="flex-1 py-1.5 px-3 rounded-xl border border-border/60 bg-muted/30 hover:bg-muted text-xs font-semibold text-foreground transition-all cursor-pointer text-center"
                              >
                                Switch Workspace
                              </button>
                            ) : (
                              <div className="flex-1 py-1.5 px-3 rounded-xl bg-emerald-500/10 text-emerald-600 text-xs font-semibold text-center">
                                Current Workspace
                              </div>
                            )}

                            <button
                              onClick={() => {
                                setSelectedCompanyId(comp.id);
                                loadCompanyData(comp.id);
                                handleTabChange('firm-profile');
                              }}
                              className="py-1.5 px-3 rounded-xl bg-primary/10 hover:bg-primary/20 text-primary text-xs font-semibold transition-all cursor-pointer flex items-center gap-1"
                              title="Edit this company's profile & settings"
                            >
                              <span>Configure</span>
                              <ChevronRight className="w-3 h-3" />
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}

            {/* TAB 3: FIRM PROFILE & DETAILS (COMPANY SETTINGS) */}
            {activeTab === 'firm-profile' && company && (
              <div className="space-y-6 animate-in fade-in duration-200">
                <div className="bg-card border border-border/50 rounded-2xl p-6 shadow-2xs space-y-6">
                  <div className="flex items-center gap-3 border-b border-border/40 pb-4">
                    <div className="p-2.5 rounded-xl bg-primary/10 text-primary">
                      <Building className="w-5 h-5" />
                    </div>
                    <div>
                      <h2 className="text-base font-bold text-foreground">Firm Details & Profile</h2>
                      <p className="text-xs text-muted-foreground">Statutory business registration, address, and settlement bank accounts</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground mb-1">Firm Name</label>
                      <input
                        type="text"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        className="w-full bg-muted/30 border border-input text-foreground text-sm p-2.5 rounded-xl outline-none focus:ring-1 focus:ring-primary"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground mb-1">GSTIN</label>
                      <input
                        type="text"
                        value={gstin}
                        onChange={(e) => setGstin(e.target.value.toUpperCase())}
                        className="w-full bg-muted/30 border border-input text-foreground text-sm p-2.5 rounded-xl outline-none uppercase font-mono focus:ring-1 focus:ring-primary"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground mb-1">Email</label>
                      <input
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        className="w-full bg-muted/30 border border-input text-foreground text-sm p-2.5 rounded-xl outline-none focus:ring-1 focus:ring-primary"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground mb-1">Phone</label>
                      <input
                        type="tel"
                        value={phone}
                        onChange={(e) => setPhone(e.target.value)}
                        className="w-full bg-muted/30 border border-input text-foreground text-sm p-2.5 rounded-xl outline-none focus:ring-1 focus:ring-primary"
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
                        className="w-full bg-muted/30 border border-input text-foreground text-sm p-2.5 rounded-xl outline-none focus:ring-1 focus:ring-primary"
                      />
                    </div>
                    <div className="sm:col-span-2">
                      <label className="block text-xs font-semibold text-muted-foreground mb-1">Full Billing Address</label>
                      <textarea
                        rows={2}
                        value={address}
                        onChange={(e) => setAddress(e.target.value)}
                        className="w-full bg-muted/30 border border-input text-foreground text-sm p-2.5 rounded-xl outline-none focus:ring-1 focus:ring-primary"
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
                          className="w-full bg-muted/30 border border-input text-foreground text-sm p-2.5 rounded-xl outline-none focus:ring-1 focus:ring-primary"
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
                          className="w-full bg-muted/30 border border-input text-foreground text-sm p-2.5 rounded-xl outline-none focus:ring-1 focus:ring-primary"
                        />
                        <p className="text-[11px] text-muted-foreground mt-1">
                          Seller contact number displayed on invoice header.
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Banking Details */}
                  <div className="pt-4 border-t border-border/40 space-y-3">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div>
                        <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                          <Landmark className="w-3.5 h-3.5 text-blue-500" />
                          <span>Bank Account & Settlement Details (Printed on Invoices)</span>
                        </h3>
                        <p className="text-[11px] text-muted-foreground mt-0.5">
                          Saving these bank details automatically creates & syncs your <strong>Bank Account Ledger</strong> for statement reconciliation and dynamic invoice QR codes.
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        {((company as any)?.linked_bank_ledger_name || (company as any)?.bank_account_number) && (
                          <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 shrink-0 flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                            <span>Auto-Linked to Ledger</span>
                          </span>
                        )}
                        <Link
                          href="/banking"
                          className="text-[11px] font-semibold text-blue-400 hover:text-blue-300 flex items-center gap-1 shrink-0 hover:underline"
                        >
                          <span>Reconciliation</span>
                          <ArrowRight className="w-3 h-3" />
                        </Link>
                      </div>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">Bank Name</label>
                        <input
                          type="text"
                          value={bankName}
                          onChange={(e) => setBankName(e.target.value)}
                          placeholder="e.g. HDFC Bank"
                          className="w-full bg-muted/30 border border-input text-foreground text-xs p-2.5 rounded-xl outline-none"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">Account Number</label>
                        <input
                          type="text"
                          value={bankAccountNumber}
                          onChange={(e) => setBankAccountNumber(e.target.value)}
                          className="w-full bg-muted/30 border border-input text-foreground text-xs p-2.5 rounded-xl outline-none font-mono"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">IFSC Code</label>
                        <input
                          type="text"
                          value={bankIfsc}
                          onChange={(e) => setBankIfsc(e.target.value.toUpperCase())}
                          className="w-full bg-muted/30 border border-input text-foreground text-xs p-2.5 rounded-xl outline-none uppercase font-mono"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">Branch Name</label>
                        <input
                          type="text"
                          value={bankBranch}
                          onChange={(e) => setBankBranch(e.target.value)}
                          className="w-full bg-muted/30 border border-input text-foreground text-xs p-2.5 rounded-xl outline-none"
                        />
                      </div>
                      <div className="sm:col-span-2">
                        <label className="block text-xs text-muted-foreground mb-1">UPI ID / VPA (For Dynamic QR Code)</label>
                        <input
                          type="text"
                          value={upiId}
                          onChange={(e) => setUpiId(e.target.value)}
                          placeholder="e.g. business@okhdfcbank"
                          className="w-full bg-muted/30 border border-input text-foreground text-xs p-2.5 rounded-xl outline-none font-mono"
                        />
                      </div>
                    </div>
                  </div>

                  <div className="flex justify-end pt-2">
                    <button
                      onClick={saveCompanySettings}
                      disabled={saving || isReadOnly}
                      className="px-5 py-2.5 bg-primary text-primary-foreground hover:bg-primary/90 rounded-xl text-xs font-bold shadow-sm transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
                    >
                      <Save className={`w-3.5 h-3.5 ${saving ? 'animate-spin' : ''}`} />
                      <span>{saving ? 'Saving...' : 'Save Firm Details'}</span>
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 4: BRANDING & DOCUMENT DESIGN (COMPANY SETTINGS) */}
            {activeTab === 'branding' && company && (
              <div className="space-y-6 animate-in fade-in duration-200">
                <div className="bg-card border border-border/50 rounded-2xl p-6 shadow-2xs space-y-6">
                  <div className="flex items-center gap-3 border-b border-border/40 pb-4">
                    <div className="p-2.5 rounded-xl bg-purple-500/10 text-purple-500">
                      <Palette className="w-5 h-5" />
                    </div>
                    <div>
                      <h2 className="text-base font-bold text-foreground">Document Branding & Invoicing Design</h2>
                      <p className="text-xs text-muted-foreground">Configure company logo, authorized signatures, stamp, color theme, and proforma preview</p>
                    </div>
                  </div>

                  {/* Logo, Signature & Stamp Upload Row */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {/* Brand Logo */}
                    <div className="p-4 rounded-xl border border-border/50 bg-muted/20 space-y-3">
                      <div className="text-xs font-bold text-foreground flex items-center gap-2">
                        <ImageIcon className="w-4 h-4 text-primary" />
                        <span>Company Logo</span>
                      </div>
                      <div className="flex items-center justify-center h-28 border border-dashed border-border/60 rounded-xl overflow-hidden bg-card">
                        {logoPreview ? (
                          <img src={logoPreview} alt="Logo" className="max-h-full max-w-full object-contain p-2" />
                        ) : (
                          <span className="text-xs text-muted-foreground">No logo uploaded</span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <label className="flex-1 py-1.5 px-3 bg-muted hover:bg-muted/80 text-foreground text-xs font-semibold rounded-lg text-center cursor-pointer transition-colors">
                          <span>{logoPreview ? 'Change' : 'Upload'}</span>
                          <input type="file" accept="image/*" onChange={handleLogoChange} className="hidden" />
                        </label>
                        {logoPreview && (
                          <button
                            type="button"
                            onClick={() => { setLogo(null); setLogoPreview(null); }}
                            className="p-1.5 text-rose-500 hover:bg-rose-500/10 rounded-lg cursor-pointer"
                            title="Remove logo"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Digital Signature */}
                    <div className="p-4 rounded-xl border border-border/50 bg-muted/20 space-y-3">
                      <div className="text-xs font-bold text-foreground flex items-center gap-2">
                        <Sparkles className="w-4 h-4 text-amber-500" />
                        <span>Proprietor Signature</span>
                      </div>
                      <div className="flex items-center justify-center h-28 border border-dashed border-border/60 rounded-xl overflow-hidden bg-card">
                        {signaturePreview ? (
                          <img src={signaturePreview} alt="Signature" className="max-h-full max-w-full object-contain p-2" />
                        ) : (
                          <span className="text-xs text-muted-foreground">No signature uploaded</span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <label className="flex-1 py-1.5 px-3 bg-muted hover:bg-muted/80 text-foreground text-xs font-semibold rounded-lg text-center cursor-pointer transition-colors">
                          <span>{signaturePreview ? 'Change' : 'Upload'}</span>
                          <input type="file" accept="image/*" onChange={handleSignatureChange} className="hidden" />
                        </label>
                        {signaturePreview && (
                          <button
                            type="button"
                            onClick={() => { setSignature(null); setSignaturePreview(null); }}
                            className="p-1.5 text-rose-500 hover:bg-rose-500/10 rounded-lg cursor-pointer"
                            title="Remove signature"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Official Stamp */}
                    <div className="p-4 rounded-xl border border-border/50 bg-muted/20 space-y-3">
                      <div className="text-xs font-bold text-foreground flex items-center gap-2">
                        <Stamp className="w-4 h-4 text-blue-500" />
                        <span>Official Seal / Stamp</span>
                      </div>
                      <div className="flex items-center justify-center h-28 border border-dashed border-border/60 rounded-xl overflow-hidden bg-card">
                        {stampPreview ? (
                          <img src={stampPreview} alt="Stamp" className="max-h-full max-w-full object-contain p-2" />
                        ) : (
                          <span className="text-xs text-muted-foreground">No stamp uploaded</span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <label className="flex-1 py-1.5 px-3 bg-muted hover:bg-muted/80 text-foreground text-xs font-semibold rounded-lg text-center cursor-pointer transition-colors">
                          <span>{stampPreview ? 'Change' : 'Upload'}</span>
                          <input type="file" accept="image/*" onChange={handleStampChange} className="hidden" />
                        </label>
                        {stampPreview && (
                          <button
                            type="button"
                            onClick={() => { setStamp(null); setStampPreview(null); }}
                            className="p-1.5 text-rose-500 hover:bg-rose-500/10 rounded-lg cursor-pointer"
                            title="Remove stamp"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Theme Accent Color & Sizing Controls */}
                  <div className="pt-4 border-t border-border/40 grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground mb-1">Document Accent Color</label>
                      <div className="flex items-center gap-2">
                        <input
                          type="color"
                          value={accentColor}
                          onChange={(e) => setAccentColor(e.target.value)}
                          className="w-10 h-10 rounded-xl cursor-pointer bg-transparent border border-border/60 p-0.5"
                        />
                        <input
                          type="text"
                          value={accentColor}
                          onChange={(e) => setAccentColor(e.target.value)}
                          className="flex-1 bg-muted/30 border border-input text-foreground text-xs p-2 rounded-xl font-mono uppercase"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground mb-1">Logo Placement</label>
                      <select
                        value={logoPosition}
                        onChange={(e: any) => setLogoPosition(e.target.value)}
                        className="w-full bg-muted/30 border border-input text-foreground text-xs p-2.5 rounded-xl outline-none"
                      >
                        <option value="left">Left Aligned</option>
                        <option value="center">Centered Header</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground mb-1">Logo Print Height ({logoHeight}px)</label>
                      <input
                        type="range"
                        min="30"
                        max="90"
                        value={logoHeight}
                        onChange={(e) => setLogoHeight(Number(e.target.value))}
                        className="w-full mt-2 accent-primary cursor-pointer"
                      />
                    </div>
                  </div>

                  {/* Document Visibility Checkboxes */}
                  <div className="pt-4 border-t border-border/40 space-y-3">
                    <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Document Visibility Controls</h3>
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 text-xs">
                      {[
                        { label: 'Show Brand Logo', val: showLogo, set: setShowLogo },
                        { label: 'Watermark Background', val: watermarkEnabled, set: setWatermarkEnabled },
                        { label: 'Bank Settlement Box', val: showBankDetails, set: setShowBankDetails },
                        { label: 'UPI Payment QR', val: showUpiQr, set: setShowUpiQr },
                        { label: 'Terms & Conditions', val: showTerms, set: setShowTerms },
                        { label: 'Amount in Words', val: showAmountInWords, set: setShowAmountInWords },
                        { label: 'HSN Tax Summary Table', val: showHsnSummary, set: setShowHsnSummary },
                        { label: 'Promotional Footer', val: showPromoFooter, set: setShowPromoFooter },
                      ].map((item, idx) => (
                        <label key={idx} className="flex items-center gap-2 p-2 rounded-xl bg-muted/20 border border-border/40 cursor-pointer hover:bg-muted/40">
                          <input
                            type="checkbox"
                            checked={item.val}
                            onChange={(e) => item.set(e.target.checked)}
                            className="rounded text-primary focus:ring-primary w-4 h-4"
                          />
                          <span className="font-medium text-foreground">{item.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* Terms & Notes Textareas */}
                  <div className="pt-4 border-t border-border/40 grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground mb-1">Default Terms & Conditions</label>
                      <textarea
                        rows={3}
                        value={defaultTermsConditions}
                        onChange={(e) => setDefaultTermsConditions(e.target.value)}
                        className="w-full bg-muted/30 border border-input text-foreground text-xs p-2.5 rounded-xl outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground mb-1">Default Document Notes</label>
                      <textarea
                        rows={3}
                        value={defaultNotes}
                        onChange={(e) => setDefaultNotes(e.target.value)}
                        className="w-full bg-muted/30 border border-input text-foreground text-xs p-2.5 rounded-xl outline-none"
                      />
                    </div>
                  </div>

                  {/* Promo Footer Fields (if enabled) */}
                  {showPromoFooter && (
                    <div className="pt-4 border-t border-border/40 space-y-3">
                      <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Promotional Footer Banner Details</h3>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <input
                          type="text"
                          placeholder="Promo Tagline (e.g. Leading Belting Specialists)"
                          value={promoTagline}
                          onChange={(e) => setPromoTagline(e.target.value)}
                          className="bg-muted/30 border border-input text-foreground text-xs p-2.5 rounded-xl outline-none"
                        />
                        <input
                          type="text"
                          placeholder="Website or Catalog Link"
                          value={promoWebsite}
                          onChange={(e) => setPromoWebsite(e.target.value)}
                          className="bg-muted/30 border border-input text-foreground text-xs p-2.5 rounded-xl outline-none"
                        />
                        <input
                          type="text"
                          placeholder="Support Phone / WhatsApp"
                          value={promoSupportPhone}
                          onChange={(e) => setPromoSupportPhone(e.target.value)}
                          className="bg-muted/30 border border-input text-foreground text-xs p-2.5 rounded-xl outline-none"
                        />
                      </div>
                    </div>
                  )}

                  {/* Interactive Proforma Document Live Preview */}
                  <div className="pt-6 border-t border-border/40 space-y-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Live Document Preview</h3>
                        <p className="text-[11px] text-muted-foreground">Interactive preview of official proforma invoice rendered with your active branding settings.</p>
                      </div>
                      <div className="flex items-center gap-1.5 bg-muted/40 p-1 rounded-xl border border-border/40">
                        <button
                          type="button"
                          onClick={() => setPreviewDevice('desktop')}
                          className={`p-1.5 rounded-lg text-xs flex items-center gap-1 cursor-pointer ${
                            previewDevice === 'desktop' ? 'bg-card text-foreground font-bold shadow-2xs' : 'text-muted-foreground'
                          }`}
                        >
                          <Monitor className="w-3.5 h-3.5" />
                          <span>Desktop</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => setPreviewDevice('mobile')}
                          className={`p-1.5 rounded-lg text-xs flex items-center gap-1 cursor-pointer ${
                            previewDevice === 'mobile' ? 'bg-card text-foreground font-bold shadow-2xs' : 'text-muted-foreground'
                          }`}
                        >
                          <Smartphone className="w-3.5 h-3.5" />
                          <span>Mobile</span>
                        </button>
                      </div>
                    </div>

                    <div className="border border-border/60 rounded-2xl p-4 bg-muted/10 overflow-x-auto flex justify-center">
                      <div className={previewDevice === 'mobile' ? 'w-[380px]' : 'w-full max-w-[850px]'}>
                        <ProformaDocumentSheet
                          doc={sampleDoc as any}
                          company={{
                            ...company,
                            name,
                            gstin,
                            email,
                            phone,
                            address,
                            state_code: stateCode,
                            proprietor_name: proprietorName,
                            proprietor_phone: proprietorPhone,
                            bank_name: bankName,
                            bank_account_number: bankAccountNumber,
                            bank_ifsc: bankIfsc,
                            bank_branch: bankBranch,
                            upi_id: upiId,
                            logo_data: logoPreview,
                            signature_data: signaturePreview,
                            stamp_data: stampPreview,
                            settings: {
                              document_branding: {
                                accent_color: accentColor,
                                logo_position: logoPosition,
                                logo_height: logoHeight,
                                show_logo: showLogo,
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
                                promo_support_phone: promoSupportPhone,
                              }
                            }
                          }}
                        />
                      </div>
                    </div>
                  </div>

                  <div className="flex justify-end pt-2">
                    <button
                      onClick={saveCompanySettings}
                      disabled={saving || isReadOnly}
                      className="px-5 py-2.5 bg-primary text-primary-foreground hover:bg-primary/90 rounded-xl text-xs font-bold shadow-sm transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
                    >
                      <Save className={`w-3.5 h-3.5 ${saving ? 'animate-spin' : ''}`} />
                      <span>{saving ? 'Saving...' : 'Save Branding'}</span>
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 5: INVOICING & INVENTORY CONTROLS (COMPANY SETTINGS) */}
            {activeTab === 'invoicing-inventory' && company && (
              <div className="space-y-6 animate-in fade-in duration-200">
                <div className="bg-card border border-border/50 rounded-2xl p-6 shadow-2xs space-y-6">
                  <div className="flex items-center gap-3 border-b border-border/40 pb-4">
                    <div className="p-2.5 rounded-xl bg-emerald-500/10 text-emerald-500">
                      <Sliders className="w-5 h-5" />
                    </div>
                    <div>
                      <h2 className="text-base font-bold text-foreground">Invoicing & Inventory Controls</h2>
                      <p className="text-xs text-muted-foreground">Invoice sequence prefixes, numbering methods, stock safety limits, and item master complexity</p>
                    </div>
                  </div>

                  {/* Invoicing Controls */}
                  <div className="space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-semibold text-muted-foreground mb-1">Sales Invoice Prefix</label>
                        <input
                          type="text"
                          value={salesInvoicePrefix}
                          onChange={(e) => setSalesInvoicePrefix(e.target.value)}
                          placeholder="e.g. INV/26-27/ or MAP/"
                          className="w-full bg-muted/30 border border-input text-foreground text-xs p-2.5 rounded-xl font-mono"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-muted-foreground mb-1">Purchase Invoice Prefix</label>
                        <input
                          type="text"
                          value={purchaseInvoicePrefix}
                          onChange={(e) => setPurchaseInvoicePrefix(e.target.value)}
                          placeholder="e.g. BILL/ or PUR/"
                          className="w-full bg-muted/30 border border-input text-foreground text-xs p-2.5 rounded-xl font-mono"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                      <label className="flex items-start gap-3 p-3 rounded-xl bg-muted/20 border border-border/40 cursor-pointer hover:bg-muted/40">
                        <input
                          type="checkbox"
                          checked={allowNegativeStock}
                          onChange={(e) => setAllowNegativeStock(e.target.checked)}
                          className="mt-0.5 rounded text-primary focus:ring-primary w-4 h-4"
                        />
                        <div>
                          <div className="font-semibold text-xs text-foreground">Allow Negative Stock</div>
                          <div className="text-[11px] text-muted-foreground">Permit recording sales invoices even when recorded warehouse stock is zero</div>
                        </div>
                      </label>

                      <label className="flex items-start gap-3 p-3 rounded-xl bg-muted/20 border border-border/40 cursor-pointer hover:bg-muted/40">
                        <input
                          type="checkbox"
                          checked={enableManualInvoice}
                          onChange={(e) => setEnableManualInvoice(e.target.checked)}
                          className="mt-0.5 rounded text-primary focus:ring-primary w-4 h-4"
                        />
                        <div>
                          <div className="font-semibold text-xs text-foreground">Manual Invoice Numbering</div>
                          <div className="text-[11px] text-muted-foreground">Allow users to enter custom voucher numbers instead of automated sequence</div>
                        </div>
                      </label>

                      <label className="flex items-start gap-3 p-3 rounded-xl bg-muted/20 border border-border/40 cursor-pointer hover:bg-muted/40">
                        <input
                          type="checkbox"
                          checked={enableLedgerMapping}
                          onChange={(e) => setEnableLedgerMapping(e.target.checked)}
                          className="mt-0.5 rounded text-primary focus:ring-primary w-4 h-4"
                        />
                        <div>
                          <div className="font-semibold text-xs text-foreground">Enable Ledger Mapping</div>
                          <div className="text-[11px] text-muted-foreground">Advanced accounts mapping for automated sales & purchase ledger routing</div>
                        </div>
                      </label>

                      <label className="flex items-start gap-3 p-3 rounded-xl bg-muted/20 border border-border/40 cursor-pointer hover:bg-muted/40">
                        <input
                          type="checkbox"
                          checked={enableAdvancedItemCreation}
                          onChange={(e) => setEnableAdvancedItemCreation(e.target.checked)}
                          className="mt-0.5 rounded text-primary focus:ring-primary w-4 h-4"
                        />
                        <div>
                          <div className="font-semibold text-xs text-foreground">Advanced Item Options</div>
                          <div className="text-[11px] text-muted-foreground">Enable custom product attributes, batch tracking, and multi-warehouse selection</div>
                        </div>
                      </label>
                    </div>

                    <div className="pt-2">
                      <label className="block text-xs font-semibold text-muted-foreground mb-1">Inventory Master Complexity Level ({complexityLevel})</label>
                      <input
                        type="range"
                        min="1"
                        max="3"
                        value={complexityLevel}
                        onChange={(e) => setComplexityLevel(Number(e.target.value))}
                        className="w-full max-w-xs accent-primary cursor-pointer"
                      />
                      <div className="text-[11px] text-muted-foreground mt-1">Level 1: Simple SKU & Pricing • Level 2: Multi-Category & HSN • Level 3: Full Multi-Unit & Batch</div>
                    </div>
                  </div>

                  <div className="flex justify-end pt-2">
                    <button
                      onClick={saveCompanySettings}
                      disabled={saving || isReadOnly}
                      className="px-5 py-2.5 bg-primary text-primary-foreground hover:bg-primary/90 rounded-xl text-xs font-bold shadow-sm transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
                    >
                      <Save className={`w-3.5 h-3.5 ${saving ? 'animate-spin' : ''}`} />
                      <span>{saving ? 'Saving...' : 'Save Invoicing Controls'}</span>
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 6: GOVERNMENT GST PORTAL INTEGRATION (COMPANY SETTINGS) */}
            {activeTab === 'gst-portal' && company && (
              <div className="space-y-6 animate-in fade-in duration-200">
                <div className="bg-card border border-border/50 rounded-2xl p-6 shadow-2xs space-y-5">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-border/40 gap-3">
                    <div className="flex items-center gap-3">
                      <div className="p-2.5 rounded-xl bg-emerald-500/10 text-emerald-500">
                        <Globe className="w-5 h-5" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h2 className="text-base font-bold text-foreground">Government GST Portal Integration</h2>
                          {portalConnected ? (
                            <span className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                              <CheckCircle2 className="w-3 h-3" />
                              <span>Live Connected</span>
                            </span>
                          ) : (
                            <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-muted text-muted-foreground border border-border/40">
                              Not Connected
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          Authenticate via OTP with the GST Common Portal for GSTR-1, GSTR-3B, and 2B ITC verification
                        </p>
                      </div>
                    </div>
                  </div>

                  {portalConnected ? (
                    <div className="p-4 rounded-xl bg-emerald-500/5 border border-emerald-500/20 space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="text-xs text-foreground font-semibold">
                          Active API Gateway Session Connected for GSTIN: <strong className="font-mono">{gstin || company.gstin}</strong>
                        </div>
                        <button
                          onClick={() => setPortalStep('idle')}
                          className="text-xs text-muted-foreground hover:text-foreground underline cursor-pointer"
                        >
                          Reconnect / Refresh Session
                        </button>
                      </div>
                      {portalExpiresAt && (
                        <div className="text-[11px] text-muted-foreground font-mono">
                          Session token valid until: {new Date(portalExpiresAt).toLocaleString()}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {portalStep === 'idle' ? (
                        <div className="p-4 rounded-xl bg-muted/20 border border-border/40 space-y-4">
                          <div className="text-xs text-foreground">
                            Enter your registered GST Portal username. We will request a one-time OTP directly to your registered mobile number:
                          </div>
                          <div className="flex flex-col sm:flex-row items-center gap-3">
                            <input
                              type="text"
                              value={portalUsername}
                              onChange={(e) => setPortalUsername(e.target.value)}
                              placeholder={`GST Portal Username (Default: ${gstin || 'GSTIN'})`}
                              className="flex-1 bg-muted/30 border border-input text-foreground text-xs p-2.5 rounded-xl outline-none"
                            />
                            <button
                              onClick={handleRequestPortalOTP}
                              disabled={portalLoading}
                              className="px-4 py-2.5 bg-primary text-primary-foreground hover:bg-primary/90 rounded-xl text-xs font-bold transition-all disabled:opacity-50 cursor-pointer flex items-center gap-1.5 shrink-0"
                            >
                              <Key className="w-3.5 h-3.5" />
                              <span>{portalLoading ? 'Requesting OTP...' : 'Request Portal OTP'}</span>
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="p-4 rounded-xl bg-blue-500/5 border border-blue-500/20 space-y-4">
                          <div className="text-xs text-foreground">
                            {portalSuccess || 'Enter the 6-digit OTP sent to your GST portal registered phone:'}
                          </div>
                          <div className="flex flex-col sm:flex-row items-center gap-3">
                            <input
                              type="text"
                              maxLength={6}
                              value={portalOtp}
                              onChange={(e) => setPortalOtp(e.target.value)}
                              placeholder="6-digit OTP"
                              className="w-40 bg-card border border-input text-foreground text-center font-mono tracking-widest text-sm p-2.5 rounded-xl outline-none"
                            />
                            <button
                              onClick={handleVerifyPortalOTP}
                              disabled={portalLoading || portalOtp.length < 4}
                              className="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold transition-all disabled:opacity-50 cursor-pointer flex items-center gap-1.5"
                            >
                              <ShieldCheck className="w-3.5 h-3.5" />
                              <span>{portalLoading ? 'Verifying...' : 'Verify & Connect Session'}</span>
                            </button>
                            <button
                              onClick={() => setPortalStep('idle')}
                              className="px-3 py-2 text-xs text-muted-foreground hover:text-foreground cursor-pointer"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      )}

                      {portalError && (
                        <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-500 text-xs flex items-center gap-2">
                          <AlertTriangle className="w-4 h-4 shrink-0" />
                          <span>{portalError}</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* TAB 7: TEAM & ROLES (RBAC) (COMPANY SETTINGS) */}
            {activeTab === 'team' && company && (
              <div className="space-y-6 animate-in fade-in duration-200">
                <div className="bg-card border border-border/50 rounded-2xl p-6 shadow-2xs space-y-5">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-border/40 gap-3">
                    <div className="flex items-center gap-3">
                      <div className="p-2.5 rounded-xl bg-blue-500/10 text-blue-500">
                        <Users className="w-5 h-5" />
                      </div>
                      <div>
                        <h2 className="text-base font-bold text-foreground">Team & Permissions (RBAC)</h2>
                        <p className="text-xs text-muted-foreground">Manage user roles, CA accountants, and employee access controls for this company</p>
                      </div>
                    </div>

                    {!isReadOnly && (
                      <button
                        onClick={() => setIsInviteModalOpen(true)}
                        className="px-3.5 py-2 bg-primary text-primary-foreground hover:bg-primary/90 rounded-xl text-xs font-bold transition-all shadow-sm flex items-center gap-1.5 cursor-pointer"
                      >
                        <UserPlus className="w-3.5 h-3.5" />
                        <span>Invite Member</span>
                      </button>
                    )}
                  </div>

                  {/* Members Table */}
                  <div className="border border-border/60 rounded-xl overflow-hidden">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-muted/40 border-b border-border/40 text-muted-foreground">
                        <tr>
                          <th className="p-3">User / Email</th>
                          <th className="p-3">Role</th>
                          <th className="p-3">Joined Date</th>
                          <th className="p-3 text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/30">
                        {loadingMembers ? (
                          <tr><td colSpan={4} className="p-4 text-center text-muted-foreground">Loading members...</td></tr>
                        ) : members.length === 0 ? (
                          <tr><td colSpan={4} className="p-4 text-center text-muted-foreground">No members found.</td></tr>
                        ) : (
                          members.map((m: any) => (
                            <tr key={m.id} className="hover:bg-muted/20">
                              <td className="p-3 font-semibold text-foreground">
                                <div>{m.user?.email || m.email}</div>
                                {m.user?.first_name && <div className="text-[11px] text-muted-foreground font-normal">{m.user.first_name} {m.user.last_name}</div>}
                              </td>
                              <td className="p-3">
                                <span className={`px-2 py-0.5 rounded-md font-mono text-[10px] font-bold border ${
                                  m.role === 'OWNER' ? 'bg-amber-500/10 text-amber-500 border-amber-500/20' :
                                  m.role === 'ADMIN' ? 'bg-purple-500/10 text-purple-500 border-purple-500/20' :
                                  m.role === 'CA' ? 'bg-blue-500/10 text-blue-500 border-blue-500/20' :
                                  'bg-muted text-muted-foreground border-border/40'
                                }`}>
                                  {m.role}
                                </span>
                              </td>
                              <td className="p-3 text-muted-foreground font-mono">
                                {m.created_at ? new Date(m.created_at).toLocaleDateString() : 'N/A'}
                              </td>
                              <td className="p-3 text-right space-x-2">
                                {m.role !== 'OWNER' && !isReadOnly && (
                                  <>
                                    <select
                                      value={m.role}
                                      onChange={(e) => handleUpdateRole(m.id, e.target.value)}
                                      className="bg-muted/40 border border-border/60 text-foreground text-[11px] p-1 rounded-lg outline-none cursor-pointer"
                                    >
                                      <option value="ADMIN">ADMIN</option>
                                      <option value="CA">CA</option>
                                      <option value="EMPLOYEE">EMPLOYEE</option>
                                      <option value="VIEWER">VIEWER</option>
                                    </select>
                                    <button
                                      onClick={() => handleRemoveMember(m.id, m.user?.email || m.email)}
                                      className="p-1 text-rose-500 hover:bg-rose-500/10 rounded-lg cursor-pointer"
                                      title="Remove member"
                                    >
                                      <Trash2 className="w-3.5 h-3.5" />
                                    </button>
                                  </>
                                )}
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 8: FINANCIAL YEARS & PERIOD LOCKS (COMPANY SETTINGS) */}
            {activeTab === 'financial-years' && company && (
              <div className="space-y-6 animate-in fade-in duration-200">
                <div className="bg-card border border-border/50 rounded-2xl p-6 shadow-2xs space-y-5">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-border/40 gap-3">
                    <div className="flex items-center gap-3">
                      <div className="p-2.5 rounded-xl bg-amber-500/10 text-amber-500">
                        <Calendar className="w-5 h-5" />
                      </div>
                      <div>
                        <h2 className="text-base font-bold text-foreground">Financial Year & Period Closing</h2>
                        <p className="text-xs text-muted-foreground">Manage fiscal periods, lock historical transactions, and close books</p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setIsSplitModalOpen(true)}
                        className="px-3 py-1.5 border border-border/60 rounded-xl text-xs font-semibold hover:bg-muted cursor-pointer"
                      >
                        Split Company
                      </button>
                      <button
                        onClick={() => setIsClosingModalOpen(true)}
                        className="px-3.5 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-xl text-xs font-bold cursor-pointer shadow-xs"
                      >
                        Close Financial Year
                      </button>
                    </div>
                  </div>

                  <div className="border border-border/60 rounded-xl overflow-hidden">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-muted/40 border-b border-border/40 text-muted-foreground">
                        <tr>
                          <th className="p-3">FY Code</th>
                          <th className="p-3">Fiscal Range</th>
                          <th className="p-3">Status</th>
                          <th className="p-3 text-right">Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/30">
                        {availableFYs.map((fy) => (
                          <tr key={fy.id} className="hover:bg-muted/20">
                            <td className="p-3 font-mono font-bold text-foreground">
                              {fy.code || fy.name}
                            </td>
                            <td className="p-3 text-muted-foreground font-mono">
                              {fy.start_date} → {fy.end_date}
                            </td>
                            <td className="p-3">
                              <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                fy.is_closed ? 'bg-amber-500/15 text-amber-500' : 'bg-emerald-500/15 text-emerald-500'
                              }`}>
                                {fy.is_closed ? 'Closed' : 'Active Open'}
                              </span>
                            </td>
                            <td className="p-3 text-right">
                              {activeFY?.id === fy.id ? (
                                <span className="text-primary font-bold text-[11px]">Currently Active</span>
                              ) : (
                                <button
                                  onClick={() => {
                                    setActiveFY(fy);
                                    toast.success(`Active FY changed to ${fy.code || fy.name}`);
                                  }}
                                  className="text-xs text-primary hover:underline font-semibold cursor-pointer"
                                >
                                  Make Active
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 9: SYSTEM MAINTENANCE & BALANCING (COMPANY SETTINGS) */}
            {activeTab === 'maintenance' && company && (
              <div className="space-y-6 animate-in fade-in duration-200">
                <div className="bg-card border border-border/50 rounded-2xl p-6 shadow-2xs space-y-5">
                  <div className="flex items-center gap-3 border-b border-border/40 pb-4">
                    <div className="p-2.5 rounded-xl bg-cyan-500/10 text-cyan-500">
                      <Wrench className="w-5 h-5" />
                    </div>
                    <div>
                      <h2 className="text-base font-bold text-foreground">Diagnostics & Balancing Maintenance</h2>
                      <p className="text-xs text-muted-foreground">Recompute double-entry ledger balances and align GST tax heads</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="p-4 rounded-xl border border-border/50 bg-muted/20 space-y-3">
                      <div className="font-bold text-xs text-foreground flex items-center gap-2">
                        <RefreshCw className="w-4 h-4 text-primary" />
                        <span>Recompute Ledger Balances</span>
                      </div>
                      <p className="text-[11px] text-muted-foreground">
                        Re-aggregates all historical debit and credit journal entries to ensure 100% mathematical precision with zero balance drift.
                      </p>
                      <button
                        onClick={handleRebuildBalances}
                        disabled={rebuildingBalances}
                        className="px-4 py-2 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 rounded-xl text-xs font-semibold transition-all cursor-pointer disabled:opacity-50 flex items-center gap-2"
                      >
                        <Database className={`w-3.5 h-3.5 ${rebuildingBalances ? 'animate-spin' : ''}`} />
                        <span>{rebuildingBalances ? 'Rebuilding Balances...' : 'Rebuild Balances'}</span>
                      </button>
                    </div>

                    <div className="p-4 rounded-xl border border-border/50 bg-muted/20 space-y-3">
                      <div className="font-bold text-xs text-foreground flex items-center gap-2">
                        <ShieldCheck className="w-4 h-4 text-emerald-500" />
                        <span>Sync Tax Ledgers</span>
                      </div>
                      <p className="text-[11px] text-muted-foreground">
                        Verifies Output & Input CGST, SGST, IGST account heads and aligns chart of accounts for GST compliance.
                      </p>
                      <button
                        onClick={handleSyncTaxLedgers}
                        disabled={syncingTax}
                        className="px-4 py-2 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-600 border border-emerald-500/20 rounded-xl text-xs font-semibold transition-all cursor-pointer disabled:opacity-50 flex items-center gap-2"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${syncingTax ? 'animate-spin' : ''}`} />
                        <span>{syncingTax ? 'Aligning...' : 'Align Tax Ledgers'}</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 10: DANGER ZONE (COMPANY SETTINGS) */}
            {activeTab === 'danger-zone' && company && (
              <div className="space-y-6 animate-in fade-in duration-200">
                <div className="bg-rose-500/5 border border-rose-500/20 rounded-2xl p-6 shadow-2xs space-y-5">
                  <div className="flex items-center gap-3 border-b border-rose-500/20 pb-4">
                    <div className="p-2.5 rounded-xl bg-rose-500/10 text-rose-500">
                      <AlertTriangle className="w-5 h-5" />
                    </div>
                    <div>
                      <h2 className="text-base font-bold text-rose-500">Danger Zone: {company.name}</h2>
                      <p className="text-xs text-muted-foreground">Irreversible actions that affect company data and accounting books</p>
                    </div>
                  </div>

                  <div className="p-4 rounded-xl bg-card border border-rose-500/20 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div>
                      <div className="font-bold text-xs text-foreground">Archive or Delete Company</div>
                      <p className="text-[11px] text-muted-foreground mt-0.5">
                        Permanently delete this business entity, all vouchers, ledgers, and inventory. This action cannot be undone.
                      </p>
                    </div>
                    <button
                      onClick={() => setIsDeleteModalOpen(true)}
                      className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-bold transition-all shadow-xs shrink-0 cursor-pointer"
                    >
                      Delete Company
                    </button>
                  </div>
                </div>
              </div>
            )}

          </div>

        </div>

      </div>

      {/* MODAL: ADD NEW COMPANY */}
      {isAddCompanyModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-200">
          <div className="bg-card border border-border rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between p-5 border-b border-border">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-primary/10 text-primary">
                  <Building className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-foreground">Register New Company</h3>
                  <p className="text-xs text-muted-foreground">Add a new business entity to your multi-company workspace</p>
                </div>
              </div>
              <button
                onClick={() => setIsAddCompanyModalOpen(false)}
                className="text-muted-foreground hover:text-foreground p-1 rounded-lg cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateCompany} className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-foreground mb-1">
                  Company / Firm Name <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Annapurna Rubber Products"
                  value={newCompName}
                  onChange={(e) => setNewCompName(e.target.value)}
                  className="w-full bg-muted/30 border border-input text-foreground text-sm p-2.5 rounded-xl outline-none focus:ring-1 focus:ring-primary"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-muted-foreground mb-1">GSTIN (Optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. 09CIFPS1329P2ZL"
                    value={newCompGstin}
                    onChange={(e) => {
                      const val = e.target.value.toUpperCase();
                      setNewCompGstin(val);
                      if (val.length >= 2 && !newCompStateCode) {
                        setNewCompStateCode(val.slice(0, 2));
                      }
                    }}
                    className="w-full bg-muted/30 border border-input text-foreground text-xs p-2.5 rounded-xl font-mono uppercase"
                  />
                </div>
                <div>
                  <StateSelect
                    value={newCompStateCode}
                    onChange={(code) => setNewCompStateCode(code)}
                    label="State / Union Territory"
                    placeholder="Select State"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-muted-foreground mb-1">Phone Number</label>
                  <input
                    type="tel"
                    placeholder="e.g. 9876543210"
                    value={newCompPhone}
                    onChange={(e) => setNewCompPhone(e.target.value)}
                    className="w-full bg-muted/30 border border-input text-foreground text-xs p-2.5 rounded-xl outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-muted-foreground mb-1">Proprietor Name</label>
                  <input
                    type="text"
                    placeholder="e.g. Ranjana Shukla"
                    value={newCompProprietor}
                    onChange={(e) => setNewCompProprietor(e.target.value)}
                    className="w-full bg-muted/30 border border-input text-foreground text-xs p-2.5 rounded-xl outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-muted-foreground mb-1">Billing Address</label>
                <textarea
                  rows={2}
                  placeholder="Address, Industrial Area, City, Pincode"
                  value={newCompAddress}
                  onChange={(e) => setNewCompAddress(e.target.value)}
                  className="w-full bg-muted/30 border border-input text-foreground text-xs p-2.5 rounded-xl outline-none"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-border/40">
                <button
                  type="button"
                  onClick={() => setIsAddCompanyModalOpen(false)}
                  className="px-4 py-2 border border-border/60 rounded-xl text-xs font-semibold text-muted-foreground hover:bg-muted cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creatingCompany}
                  className="px-5 py-2 bg-primary text-primary-foreground hover:bg-primary/90 rounded-xl text-xs font-bold transition-all disabled:opacity-50 cursor-pointer flex items-center gap-1.5"
                >
                  <Plus className="w-3.5 h-3.5 stroke-[2.5]" />
                  <span>{creatingCompany ? 'Registering Company...' : 'Create Company Workspace'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: INVITE TEAM MEMBER */}
      {isInviteModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-200">
          <div className="bg-card border border-border rounded-2xl shadow-2xl w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between p-5 border-b border-border">
              <div className="flex items-center gap-2">
                <UserPlus className="w-5 h-5 text-primary" />
                <h3 className="text-base font-bold text-foreground">Invite Team Member</h3>
              </div>
              <button onClick={() => setIsInviteModalOpen(false)} className="text-muted-foreground hover:text-foreground p-1 rounded-lg cursor-pointer">
                <X className="w-4 h-4" />
              </button>
            </div>
            <form onSubmit={handleInviteMember} className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-foreground mb-1">Email Address</label>
                <input
                  type="email"
                  required
                  placeholder="colleague@yourcompany.com"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  className="w-full bg-muted/30 border border-input text-foreground text-sm p-2.5 rounded-xl outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-foreground mb-1">Role & Access Level</label>
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value)}
                  className="w-full bg-muted/30 border border-input text-foreground text-xs p-2.5 rounded-xl outline-none cursor-pointer"
                >
                  <option value="ADMIN">ADMIN (Full administrative access & settings)</option>
                  <option value="CA">CA (Chartered Accountant: journal, contra, and tax audits)</option>
                  <option value="EMPLOYEE">EMPLOYEE (Sales, Purchases & Payments creation)</option>
                  <option value="VIEWER">VIEWER (Read-only reports access)</option>
                </select>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsInviteModalOpen(false)}
                  className="px-4 py-2 border border-border/60 rounded-xl text-xs font-semibold text-muted-foreground hover:bg-muted cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={inviting}
                  className="px-4 py-2 bg-primary text-primary-foreground hover:bg-primary/90 rounded-xl text-xs font-bold transition-all disabled:opacity-50 cursor-pointer flex items-center gap-1.5"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>{inviting ? 'Inviting...' : 'Send Invitation'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: DELETE COMPANY CONFIRMATION */}
      {isDeleteModalOpen && company && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-200">
          <div className="bg-card border border-rose-500/40 rounded-2xl shadow-2xl w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between p-5 border-b border-border bg-rose-500/10">
              <div className="flex items-center gap-2 text-rose-500">
                <AlertTriangle className="w-5 h-5" />
                <h3 className="text-base font-bold">Delete {company.name}?</h3>
              </div>
              <button onClick={() => setIsDeleteModalOpen(false)} className="text-muted-foreground hover:text-foreground p-1 rounded-lg cursor-pointer">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <p className="text-xs text-foreground leading-relaxed">
                This will permanently delete <strong>{company.name}</strong>, all transactions, invoices, customer balances, and vouchers.
              </p>
              <div>
                <label className="block text-xs font-semibold text-muted-foreground mb-1">
                  Type <strong>{company.name}</strong> to confirm:
                </label>
                <input
                  type="text"
                  value={deleteConfirmName}
                  onChange={(e) => setDeleteConfirmName(e.target.value)}
                  placeholder={company.name}
                  className="w-full bg-muted/30 border border-input text-foreground text-sm p-2.5 rounded-xl outline-none"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsDeleteModalOpen(false)}
                  className="px-4 py-2 border border-border/60 rounded-xl text-xs font-semibold text-muted-foreground hover:bg-muted cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleDeleteCompany}
                  disabled={deletingCompany || deleteConfirmName.trim() !== company.name.trim()}
                  className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-bold transition-all disabled:opacity-50 cursor-pointer"
                >
                  {deletingCompany ? 'Deleting Company...' : 'Permanently Delete'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

    </DashboardLayout>
  );
}
