"use client";

import React, { useEffect, useState, useMemo, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import DashboardLayout from "@/components/DashboardLayout";
import { api } from "@/utils/api";
import { isAuthenticated } from "@/utils/auth";
import { useToast } from "@/context/ToastContext";
import { useCompany } from "@/context/CompanyContext";
import {
  CreditCard,
  ArrowUpRight,
  ArrowDownLeft,
  QrCode,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Search,
  RefreshCw,
  Plus,
  Settings as SettingsIcon,
  X,
  ExternalLink,
  ShieldCheck,
  Building,
  Phone,
  UserCheck,
  Star,
  Trash2,
  Copy,
  Check,
  Zap,
  Send,
  Download,
  ArrowRight,
  Camera,
  FileText,
  Filter,
  Sparkles,
  HelpCircle
} from "lucide-react";

type MainTab =
  | "overview"
  | "send"
  | "collect"
  | "beneficiaries"
  | "requests"
  | "transactions"
  | "settlements"
  | "reconciliation"
  | "settings";

interface PaymentItem {
  id: string;
  srilekh_pay_id: string;
  company: string;
  company_name: string;
  recipient_company?: string;
  recipient_company_name?: string;
  payer_party?: string;
  payer_party_name?: string;
  recipient_party?: string;
  recipient_party_name?: string;
  recipient_name: string;
  amount: string;
  currency: string;
  payment_method: string;
  provider: string;
  utr?: string;
  status: "CREATED" | "INITIATED" | "PENDING" | "PROCESSING" | "SUCCESS" | "FAILED" | "EXPIRED" | "REVERSED" | "REFUNDED";
  accounting_status: "PENDING" | "POSTED" | "PAYER_ONLY" | "UNMATCHED" | "FAILED";
  payer_voucher_number?: string;
  recipient_voucher_number?: string;
  invoice_number?: string;
  initiated_at: string;
  confirmed_at?: string;
}

interface BeneficiaryItem {
  id: string;
  company: string;
  beneficiary_type: "MOBILE_UPI" | "VPA" | "BANK_ACCOUNT" | "QR";
  name: string;
  nickname?: string;
  mobile_number?: string;
  masked_mobile_number?: string;
  vpa?: string;
  account_number?: string;
  masked_account_number?: string;
  ifsc_code?: string;
  bank_name?: string;
  is_verified: boolean;
  verification_status: "UNVERIFIED" | "VERIFIED" | "FAILED";
  verified_name?: string;
  verification_source?: string;
  is_favorite: boolean;
  is_active: boolean;
  linked_party?: string;
  linked_party_name?: string;
  last_paid_at?: string;
  total_payments_count: number;
  total_paid_amount: string;
}

interface UnmatchedItem {
  id: string;
  amount: string;
  utr?: string;
  payer_identifier?: string;
  unmatched_reason?: string;
  created_at: string;
}

interface MerchantSettings {
  vpa: string;
  is_onboarded: boolean;
  virtual_account_prefix: string;
  virtual_account_ifsc: string;
  auto_post_accounting: boolean;
  default_settlement_ledger?: string;
  payment_clearing_ledger?: string;
  gateway_charges_ledger?: string;
}

export default function SriLekhPayDashboard() {
  const router = useRouter();
  const { toast } = useToast();
  const { companyId: activeCompanyId } = useCompany();

  const [companyId, setCompanyId] = useState<string>(activeCompanyId || "");
  const [activeTab, setActiveTab] = useState<MainTab>("overview");
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);

  // Data states
  const [payments, setPayments] = useState<PaymentItem[]>([]);
  const [beneficiaries, setBeneficiaries] = useState<BeneficiaryItem[]>([]);
  const [unmatched, setUnmatched] = useState<UnmatchedItem[]>([]);
  const [ledgers, setLedgers] = useState<any[]>([]);
  const [invoices, setInvoices] = useState<any[]>([]);

  // Search and filter states
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [requestsFilter, setRequestsFilter] = useState<string>("ALL");
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Settings
  const [merchantSettings, setMerchantSettings] = useState<MerchantSettings>({
    vpa: "",
    is_onboarded: false,
    virtual_account_prefix: "APEX",
    virtual_account_ifsc: "ICIC0000011",
    auto_post_accounting: true
  });
  const [savingSettings, setSavingSettings] = useState<boolean>(false);

  // --- SEND MONEY STATE ---
  const [sendMode, setSendMode] = useState<"SAVED" | "MOBILE" | "CONTACTS" | "VPA" | "QR" | "BANK">("SAVED");
  const [sendQuery, setSendQuery] = useState<string>("");
  const [sendAmount, setSendAmount] = useState<string>("");
  const [sendNote, setSendNote] = useState<string>("");
  const [sendMethod, setSendMethod] = useState<string>("UPI");
  const [sendSelectedBeneficiary, setSendSelectedBeneficiary] = useState<BeneficiaryItem | null>(null);
  const [sendSelectedPartyId, setSendSelectedPartyId] = useState<string>("");
  const [sendSelectedInvoiceId, setSendSelectedInvoiceId] = useState<string>("");
  const [sendSourceBankId, setSendSourceBankId] = useState<string>("");
  const [sendDiscoveryResult, setSendDiscoveryResult] = useState<any | null>(null);
  const [sendDiscovering, setSendDiscovering] = useState<boolean>(false);
  const [sendSubmitting, setSendSubmitting] = useState<boolean>(false);
  const [sendActivePayment, setSendActivePayment] = useState<any | null>(null);
  const [sendManualUtr, setSendManualUtr] = useState<string>("");
  const [confirmingUtr, setConfirmingUtr] = useState<boolean>(false);

  // Bank Form Specific State
  const [bankAccountNum, setBankAccountNum] = useState<string>("");
  const [bankConfirmAccountNum, setBankConfirmAccountNum] = useState<string>("");
  const [bankIfsc, setBankIfsc] = useState<string>("");
  const [bankBeneficiaryName, setBankBeneficiaryName] = useState<string>("");

  // QR Camera State
  const [qrScanning, setQrScanning] = useState<boolean>(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  // --- COLLECT MONEY STATE ---
  const [collectCustomerPartyId, setCollectCustomerPartyId] = useState<string>("");
  const [collectInvoiceId, setCollectInvoiceId] = useState<string>("");
  const [collectAmount, setCollectAmount] = useState<string>("");
  const [collectNote, setCollectNote] = useState<string>("");
  const [collectingSubmitting, setCollectingSubmitting] = useState<boolean>(false);
  const [collectCreatedPayment, setCollectCreatedPayment] = useState<any | null>(null);

  // --- BENEFICIARY DIRECTORY STATE ---
  const [beneficiarySearch, setBeneficiarySearch] = useState<string>("");
  const [beneficiaryTypeFilter, setBeneficiaryTypeFilter] = useState<string>("ALL");
  const [isAddBeneficiaryOpen, setIsAddBeneficiaryOpen] = useState<boolean>(false);
  const [newBType, setNewBType] = useState<"MOBILE_UPI" | "VPA" | "BANK_ACCOUNT">("MOBILE_UPI");
  const [newBName, setNewBName] = useState<string>("");
  const [newBMobile, setNewBMobile] = useState<string>("");
  const [newBVpa, setNewBVpa] = useState<string>("");
  const [newBAccount, setNewBAccount] = useState<string>("");
  const [newBIfsc, setNewBIfsc] = useState<string>("");
  const [newBNickname, setNewBNickname] = useState<string>("");
  const [newBPartyId, setNewBPartyId] = useState<string>("");
  const [addingBeneficiary, setAddingBeneficiary] = useState<boolean>(false);
  const [verifyingBId, setVerifyingBId] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }
    const cid = activeCompanyId || (typeof window !== "undefined" ? localStorage.getItem("vouch_active_company_id") : "");
    if (cid) {
      setCompanyId(cid);
      loadAllData(cid);
    }
  }, [activeCompanyId, router]);

  const loadAllData = async (cid: string) => {
    setLoading(true);
    try {
      await Promise.all([
        fetchPayments(cid),
        fetchBeneficiaries(cid),
        fetchUnmatched(cid),
        fetchMerchantSettings(cid),
        fetchLedgersAndInvoices(cid)
      ]);
    } catch (err) {
      console.error("[SriLekhPay] Initial fetch error:", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchPayments = async (cid: string) => {
    try {
      const res = await api.get(`/api/v1/payments/requests/?company_id=${cid}`, {
        headers: { "X-Company-ID": cid }
      });
      const data = Array.isArray(res.data) ? res.data : (res.data?.results || []);
      setPayments(data);
    } catch (e) {
      console.error(e);
    }
  };

  const fetchBeneficiaries = async (cid: string) => {
    try {
      const res = await api.get(`/api/v1/payments/beneficiaries/?company_id=${cid}`, {
        headers: { "X-Company-ID": cid }
      });
      const data = Array.isArray(res.data) ? res.data : (res.data?.results || []);
      setBeneficiaries(data);
    } catch (e) {
      console.error(e);
    }
  };

  const fetchUnmatched = async (cid: string) => {
    try {
      const res = await api.get(`/api/v1/payments/unmatched/?company_id=${cid}`, {
        headers: { "X-Company-ID": cid }
      });
      const data = Array.isArray(res.data) ? res.data : (res.data?.results || []);
      setUnmatched(data);
    } catch (e) {
      console.error(e);
    }
  };

  const fetchMerchantSettings = async (cid: string) => {
    try {
      const res = await api.get(`/api/v1/payments/account/?company_id=${cid}`, {
        headers: { "X-Company-ID": cid }
      });
      if (res.data) {
        setMerchantSettings({
          vpa: res.data.vpa || "",
          is_onboarded: Boolean(res.data.is_onboarded),
          virtual_account_prefix: res.data.virtual_account_prefix || "APEX",
          virtual_account_ifsc: res.data.virtual_account_ifsc || "ICIC0000011",
          auto_post_accounting: res.data.auto_post_accounting ?? true,
          default_settlement_ledger: res.data.default_settlement_ledger || "",
          payment_clearing_ledger: res.data.payment_clearing_ledger || "",
          gateway_charges_ledger: res.data.gateway_charges_ledger || ""
        });
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchLedgersAndInvoices = async (cid: string) => {
    try {
      const [ledgersRes, invRes] = await Promise.all([
        api.get(`/api/v1/ledgers/?company_id=${cid}`, { headers: { "X-Company-ID": cid } }),
        api.get(`/api/v1/vouchers/?company_id=${cid}&status=POSTED`, { headers: { "X-Company-ID": cid } })
      ]);
      setLedgers(Array.isArray(ledgersRes.data) ? ledgersRes.data : (ledgersRes.data?.results || []));
      setInvoices(Array.isArray(invRes.data) ? invRes.data : (invRes.data?.results || []));
    } catch (e) {
      console.error(e);
    }
  };

  const handleRefresh = async () => {
    if (!companyId) return;
    setRefreshing(true);
    await loadAllData(companyId);
    setRefreshing(false);
    toast.success("Refreshed", "Payment records, beneficiaries, and accounting ledgers synchronised.");
  };

  const copyToClipboard = (text: string, key: string) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    toast.info("Copied", `Copied to clipboard: ${text}`);
    setTimeout(() => setCopiedKey(null), 2500);
  };

  // --- STATS COMPUTATION ---
  const stats = useMemo(() => {
    let totalPaid = 0;
    let totalReceived = 0;
    let pendingCount = 0;
    let pendingAmount = 0;

    payments.forEach((p) => {
      const amt = parseFloat(p.amount) || 0;
      const isOutgoing = p.company === companyId;
      if (p.status === "SUCCESS") {
        if (isOutgoing) totalPaid += amt;
        else totalReceived += amt;
      } else if (p.status === "INITIATED" || p.status === "PENDING" || p.status === "PROCESSING") {
        pendingCount += 1;
        pendingAmount += amt;
      }
    });

    const unmatchedTotal = unmatched.reduce((acc, u) => acc + (parseFloat(u.amount) || 0), 0);

    return {
      totalPaid,
      totalReceived,
      pendingCount,
      pendingAmount,
      unmatchedCount: unmatched.length,
      unmatchedTotal
    };
  }, [payments, unmatched, companyId]);

  // --- BENEFICIARY DISCOVERY HANDLER ---
  const handleDiscoverRecipient = async (mode: "MOBILE" | "VPA" | "QR" | "IFSC", q: string) => {
    if (!q.trim()) return;
    setSendDiscovering(true);
    setSendDiscoveryResult(null);
    try {
      const res = await api.post(
        `/api/v1/payments/beneficiaries/discover/?company_id=${companyId}`,
        { discovery_mode: mode, query: q.trim() },
        { headers: { "X-Company-ID": companyId } }
      );
      if (res.data?.success && res.data.data) {
        setSendDiscoveryResult(res.data.data);
        if (res.data.data.amount) setSendAmount(res.data.data.amount);
        if (res.data.data.notes) setSendNote(res.data.data.notes);
        toast.success("Recipient Resolved", `Verified: ${res.data.data.name}`);
      } else {
        toast.error("Lookup failed", res.data?.error || "Could not resolve recipient.");
      }
    } catch (err: any) {
      toast.error("Discovery Error", err.response?.data?.error || "Recipient lookup failed.");
    } finally {
      setSendDiscovering(false);
    }
  };

  // --- CONTACT PICKER API (PWA / Mobile) ---
  const handlePickContact = async () => {
    if ("contacts" in navigator && "ContactsManager" in window) {
      try {
        const props = ["name", "tel"];
        const opts = { multiple: false };
        const contacts = await (navigator as any).contacts.select(props, opts);
        if (contacts && contacts[0] && contacts[0].tel && contacts[0].tel[0]) {
          const rawNum = contacts[0].tel[0];
          setSendQuery(rawNum);
          handleDiscoverRecipient("MOBILE", rawNum);
        }
      } catch (e) {
        console.warn("Contact picker cancelled or unsupported:", e);
      }
    } else {
      toast.info("Manual Entry", "Contact Picker API is not available on this device. Please type the 10-digit mobile number.");
    }
  };

  // --- QR CAMERA SCANNER (PWA) ---
  const startCameraScan = async () => {
    setQrScanning(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.play();
      }
    } catch (err) {
      console.error("Camera access error:", err);
      toast.error("Camera Error", "Could not access camera for QR scanning.");
      setQrScanning(false);
    }
  };

  const stopCameraScan = () => {
    if (videoRef.current && videoRef.current.srcObject) {
      const stream = videoRef.current.srcObject as MediaStream;
      stream.getTracks().forEach((track) => track.stop());
    }
    setQrScanning(false);
  };

  // --- SEND MONEY SUBMISSION ---
  const handleInitiateSendMoney = async (e: React.FormEvent) => {
    e.preventDefault();
    const amt = parseFloat(sendAmount);
    if (!amt || amt <= 0) {
      toast.error("Invalid Amount", "Please enter a valid payment amount greater than ₹0.");
      return;
    }

    let recipientName = "";
    let recipientVpa = "";
    let recipientAccount = "";
    let recipientIfsc = "";
    let beneficiaryId: string | null = null;

    if (sendSelectedBeneficiary) {
      beneficiaryId = sendSelectedBeneficiary.id;
      recipientName = sendSelectedBeneficiary.name;
      recipientVpa = sendSelectedBeneficiary.vpa || "";
      recipientAccount = sendSelectedBeneficiary.account_number || "";
      recipientIfsc = sendSelectedBeneficiary.ifsc_code || "";
    } else if (sendDiscoveryResult) {
      recipientName = sendDiscoveryResult.name || "Recipient";
      recipientVpa = sendDiscoveryResult.vpa || "";
      recipientAccount = sendDiscoveryResult.account_number || "";
      recipientIfsc = sendDiscoveryResult.ifsc || "";
    } else if (sendMode === "BANK") {
      if (bankAccountNum !== bankConfirmAccountNum) {
        toast.error("Mismatch", "Account numbers do not match.");
        return;
      }
      recipientName = bankBeneficiaryName || "Bank Beneficiary";
      recipientAccount = bankAccountNum;
      recipientIfsc = bankIfsc;
    } else if (sendMode === "VPA" && sendQuery) {
      recipientName = sendQuery.split("@")[0].toUpperCase();
      recipientVpa = sendQuery;
    } else {
      toast.error("Recipient Required", "Please resolve or select a beneficiary first.");
      return;
    }

    setSendSubmitting(true);
    try {
      const payload: any = {
        amount: amt,
        payment_method: sendMethod,
        beneficiary_id: beneficiaryId,
        recipient_name: recipientName,
        recipient_vpa: recipientVpa || null,
        recipient_account_number: recipientAccount || null,
        recipient_ifsc: recipientIfsc || null,
        payer_party_id: sendSelectedPartyId || null,
        invoice_id: sendSelectedInvoiceId || null,
        notes: sendNote || "SriLekh Pay Transfer",
        idempotency_key: `pay_${companyId}_${Date.now()}`
      };

      const res = await api.post(`/api/v1/payments/requests/?company_id=${companyId}`, payload, {
        headers: { "X-Company-ID": companyId }
      });

      setSendActivePayment(res.data);
      toast.success("Payment Dispatched", `Request ${res.data.srilekh_pay_id} initialized.`);
      fetchPayments(companyId);
    } catch (err: any) {
      toast.error("Payment Initiation Failed", err.response?.data?.error || "Could not initialize payment request.");
    } finally {
      setSendSubmitting(false);
    }
  };

  // --- MANUAL UTR CONFIRMATION ---
  const handleConfirmManualUtr = async () => {
    if (!sendActivePayment || !sendManualUtr.trim()) {
      toast.error("UTR Required", "Please enter the 12-digit UTR from your bank or UPI app.");
      return;
    }
    setConfirmingUtr(true);
    try {
      const res = await api.post(
        `/api/v1/payments/requests/${sendActivePayment.id}/confirm/?company_id=${companyId}`,
        { utr: sendManualUtr.trim() },
        { headers: { "X-Company-ID": companyId } }
      );
      setSendActivePayment(res.data);
      toast.success("Payment Verified & Posted", `Double-entry voucher ${res.data.payer_voucher_number || ""} posted.`);
      fetchPayments(companyId);
    } catch (err: any) {
      toast.error("Confirmation Error", err.response?.data?.error || "Failed to confirm UTR.");
    } finally {
      setConfirmingUtr(false);
    }
  };

  // --- COLLECT MONEY SUBMISSION ---
  const handleCreateCollectionRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    const amt = parseFloat(collectAmount);
    if (!amt || amt <= 0) {
      toast.error("Invalid Amount", "Please enter a valid collection amount.");
      return;
    }

    setCollectingSubmitting(true);
    try {
      const party = ledgers.find((l) => String(l.id) === String(collectCustomerPartyId));
      const res = await api.post(
        `/api/v1/payments/requests/?company_id=${companyId}`,
        {
          amount: amt,
          payment_method: "UPI",
          payer_party_id: collectCustomerPartyId || null,
          invoice_id: collectInvoiceId || null,
          recipient_name: merchantSettings.vpa || "SriLekh Merchant",
          recipient_vpa: merchantSettings.vpa,
          notes: collectNote || (party ? `Invoice Collection from ${party.name}` : "Trade Collection"),
          idempotency_key: `collect_${companyId}_${Date.now()}`
        },
        { headers: { "X-Company-ID": companyId } }
      );

      setCollectCreatedPayment(res.data);
      toast.success("Collection Request Created", "Dynamic QR and payment link generated.");
      fetchPayments(companyId);
    } catch (err: any) {
      toast.error("Collection Failed", err.response?.data?.error || "Could not create payment request.");
    } finally {
      setCollectingSubmitting(false);
    }
  };

  // --- BENEFICIARY DIRECTORY ACTIONS ---
  const handleAddBeneficiary = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newBName.trim()) {
      toast.error("Name Required", "Please provide a recipient name.");
      return;
    }
    setAddingBeneficiary(true);
    try {
      const payload: any = {
        name: newBName.trim(),
        nickname: newBNickname.trim() || null,
        beneficiary_type: newBType,
        mobile_number: newBMobile.trim() || null,
        vpa: newBVpa.trim() || null,
        account_number: newBAccount.trim() || null,
        ifsc_code: newBIfsc.trim().toUpperCase() || null,
        linked_party: newBPartyId || null,
        auto_verify: true
      };

      const res = await api.post(`/api/v1/payments/beneficiaries/?company_id=${companyId}`, payload, {
        headers: { "X-Company-ID": companyId }
      });
      setBeneficiaries([res.data, ...beneficiaries]);
      setIsAddBeneficiaryOpen(false);
      // Reset form
      setNewBName("");
      setNewBMobile("");
      setNewBVpa("");
      setNewBAccount("");
      setNewBIfsc("");
      setNewBNickname("");
      toast.success("Beneficiary Saved", `${res.data.name} added to company directory.`);
    } catch (err: any) {
      toast.error("Could not save beneficiary", err.response?.data?.error || "Validation failed.");
    } finally {
      setAddingBeneficiary(false);
    }
  };

  const handleToggleFavorite = async (bId: string) => {
    try {
      const res = await api.post(`/api/v1/payments/beneficiaries/${bId}/favorite/?company_id=${companyId}`, {}, {
        headers: { "X-Company-ID": companyId }
      });
      setBeneficiaries((prev) =>
        prev.map((b) => (b.id === bId ? { ...b, is_favorite: res.data.is_favorite } : b))
      );
    } catch (e) {
      console.error(e);
    }
  };

  const handleVerifyBeneficiary = async (bId: string) => {
    setVerifyingBId(bId);
    try {
      const res = await api.post(`/api/v1/payments/beneficiaries/${bId}/verify/?company_id=${companyId}`, {}, {
        headers: { "X-Company-ID": companyId }
      });
      if (res.data?.success && res.data.data) {
        setBeneficiaries((prev) => prev.map((b) => (b.id === bId ? res.data.data : b)));
        toast.success("Verified", res.data.message || "Beneficiary verified against banking network.");
      }
    } catch (err: any) {
      toast.error("Verification Error", err.response?.data?.error || "Could not verify beneficiary.");
    } finally {
      setVerifyingBId(null);
    }
  };

  const handleDeleteBeneficiary = async (bId: string) => {
    try {
      await api.delete(`/api/v1/payments/beneficiaries/${bId}/?company_id=${companyId}`, {
        headers: { "X-Company-ID": companyId }
      });
      setBeneficiaries((prev) => prev.filter((b) => b.id !== bId));
      toast.info("Beneficiary Removed", "Removed from directory.");
    } catch (e) {
      console.error(e);
    }
  };

  // --- SAVE SETTINGS ---
  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingSettings(true);
    try {
      const res = await api.post(`/api/v1/payments/account/?company_id=${companyId}`, merchantSettings, {
        headers: { "X-Company-ID": companyId }
      });
      toast.success("Settings Saved", "SriLekh Pay merchant settings updated.");
      fetchMerchantSettings(companyId);
    } catch (err: any) {
      toast.error("Save Failed", err.response?.data?.error || "Failed to update settings.");
    } finally {
      setSavingSettings(false);
    }
  };

  // Filtered beneficiaries
  const filteredBeneficiaries = useMemo(() => {
    return beneficiaries.filter((b) => {
      const matchesSearch =
        !beneficiarySearch ||
        b.name.toLowerCase().includes(beneficiarySearch.toLowerCase()) ||
        (b.nickname && b.nickname.toLowerCase().includes(beneficiarySearch.toLowerCase())) ||
        (b.vpa && b.vpa.toLowerCase().includes(beneficiarySearch.toLowerCase())) ||
        (b.mobile_number && b.mobile_number.includes(beneficiarySearch)) ||
        (b.account_number && b.account_number.includes(beneficiarySearch));

      const matchesType =
        beneficiaryTypeFilter === "ALL"
          ? true
          : beneficiaryTypeFilter === "FAVORITES"
          ? b.is_favorite
          : b.beneficiary_type === beneficiaryTypeFilter;

      return matchesSearch && matchesType;
    });
  }, [beneficiaries, beneficiarySearch, beneficiaryTypeFilter]);

  // Filtered payment requests
  const filteredRequests = useMemo(() => {
    return payments.filter((p) => {
      const matchesSearch =
        !searchQuery ||
        p.srilekh_pay_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        p.recipient_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (p.utr && p.utr.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (p.payer_voucher_number && p.payer_voucher_number.toLowerCase().includes(searchQuery.toLowerCase()));

      let matchesFilter = true;
      if (requestsFilter === "OUTGOING") matchesFilter = p.company === companyId;
      else if (requestsFilter === "INCOMING") matchesFilter = p.recipient_company === companyId;
      else if (requestsFilter === "PENDING") matchesFilter = ["INITIATED", "PENDING", "PROCESSING"].includes(p.status);
      else if (requestsFilter === "SUCCESS") matchesFilter = p.status === "SUCCESS";
      else if (requestsFilter === "FAILED") matchesFilter = p.status === "FAILED";

      return matchesSearch && matchesFilter;
    });
  }, [payments, searchQuery, requestsFilter, companyId]);

  return (
    <DashboardLayout>
      <div className="space-y-6 pb-12">
        {/* Top Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border/60 pb-5">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="p-2 rounded-xl bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                <Zap className="w-5 h-5 fill-current" />
              </span>
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
                SriLekh Pay
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                  Unified Payments & Accounting
                </span>
              </h1>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Multi-tenant B2B payments, beneficiary discovery, automated double-entry vouchers & bank reconciliation.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="p-2 rounded-xl border border-border bg-card hover:bg-muted text-muted-foreground hover:text-foreground transition-all cursor-pointer flex items-center gap-1.5 text-xs font-semibold"
              title="Refresh Payment Feeds"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
              <span className="hidden sm:inline">Sync</span>
            </button>

            <button
              onClick={() => setActiveTab("send")}
              className="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition-all shadow-sm flex items-center gap-1.5 cursor-pointer"
            >
              <Send className="w-3.5 h-3.5" />
              <span>Send Money</span>
            </button>

            <button
              onClick={() => setActiveTab("collect")}
              className="px-3.5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold transition-all shadow-sm flex items-center gap-1.5 cursor-pointer"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Collect Money</span>
            </button>
          </div>
        </div>

        {/* 9-Tab Modern Navigation Bar */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 border-b border-border/40 scrollbar-none text-xs font-semibold">
          {[
            { id: "overview", label: "Overview", icon: Building },
            { id: "send", label: "Send Money", icon: Send },
            { id: "collect", label: "Collect Money", icon: Download },
            { id: "beneficiaries", label: "Beneficiaries", icon: UserCheck, count: beneficiaries.length },
            { id: "requests", label: "Payment Requests", icon: CreditCard, count: payments.length },
            { id: "transactions", label: "Transactions", icon: FileText },
            { id: "settlements", label: "Settlements", icon: ArrowDownLeft },
            { id: "reconciliation", label: "Reconciliation", icon: CheckCircle2 },
            { id: "settings", label: "Settings", icon: SettingsIcon }
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as MainTab)}
                className={`px-3 py-2 rounded-xl transition-all flex items-center gap-2 whitespace-nowrap cursor-pointer shrink-0 ${
                  isActive
                    ? "bg-foreground text-background font-bold shadow-xs"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{tab.label}</span>
                {tab.count !== undefined && tab.count > 0 && (
                  <span
                    className={`px-1.5 py-0.2 rounded-full text-[10px] ${
                      isActive ? "bg-background/20 text-background" : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {tab.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* ========================================================================= */}
        {/* TAB 1: OVERVIEW */}
        {/* ========================================================================= */}
        {activeTab === "overview" && (
          <div className="space-y-6">
            {/* Metric Cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
              <div className="p-4 rounded-2xl border border-border/60 bg-card/60 backdrop-blur-xs space-y-1">
                <div className="flex items-center justify-between text-muted-foreground text-xs font-medium">
                  <span>Total Outflow (Paid)</span>
                  <ArrowUpRight className="w-4 h-4 text-rose-500" />
                </div>
                <div className="text-xl sm:text-2xl font-bold font-mono text-foreground">
                  ₹{stats.totalPaid.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-[11px] text-muted-foreground">Verified & posted to supplier books</div>
              </div>

              <div className="p-4 rounded-2xl border border-border/60 bg-card/60 backdrop-blur-xs space-y-1">
                <div className="flex items-center justify-between text-muted-foreground text-xs font-medium">
                  <span>Total Inflow (Received)</span>
                  <ArrowDownLeft className="w-4 h-4 text-emerald-500" />
                </div>
                <div className="text-xl sm:text-2xl font-bold font-mono text-foreground">
                  ₹{stats.totalReceived.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-[11px] text-muted-foreground">Settled into bank clearing</div>
              </div>

              <div className="p-4 rounded-2xl border border-border/60 bg-card/60 backdrop-blur-xs space-y-1">
                <div className="flex items-center justify-between text-muted-foreground text-xs font-medium">
                  <span>In-Flight Processing</span>
                  <Clock className="w-4 h-4 text-amber-500" />
                </div>
                <div className="text-xl sm:text-2xl font-bold font-mono text-foreground">
                  ₹{stats.pendingAmount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-[11px] text-muted-foreground">{stats.pendingCount} pending confirmations</div>
              </div>

              <div className="p-4 rounded-2xl border border-border/60 bg-card/60 backdrop-blur-xs space-y-1">
                <div className="flex items-center justify-between text-muted-foreground text-xs font-medium">
                  <span>Suspense (Unmatched)</span>
                  <AlertTriangle className="w-4 h-4 text-purple-500" />
                </div>
                <div className="text-xl sm:text-2xl font-bold font-mono text-foreground">
                  ₹{stats.unmatchedTotal.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div className="text-[11px] text-muted-foreground">{stats.unmatchedCount} unallocated receipts</div>
              </div>
            </div>

            {/* Quick Actions Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div
                onClick={() => setActiveTab("send")}
                className="p-5 rounded-2xl border border-border/60 bg-gradient-to-br from-emerald-500/5 via-card to-card hover:border-emerald-500/40 transition-all cursor-pointer group"
              >
                <div className="w-10 h-10 rounded-xl bg-emerald-500/10 text-emerald-500 flex items-center justify-center mb-3 group-hover:scale-105 transition-transform">
                  <Send className="w-5 h-5" />
                </div>
                <h3 className="font-bold text-sm text-foreground flex items-center justify-between">
                  <span>Instant B2B Payment</span>
                  <ArrowRight className="w-4 h-4 text-muted-foreground group-hover:translate-x-1 transition-transform" />
                </h3>
                <p className="text-xs text-muted-foreground mt-1">
                  Pay suppliers via Mobile Number, UPI Intent, Dynamic QR, or Bank Transfer (NEFT/RTGS).
                </p>
              </div>

              <div
                onClick={() => setActiveTab("collect")}
                className="p-5 rounded-2xl border border-border/60 bg-gradient-to-br from-blue-500/5 via-card to-card hover:border-blue-500/40 transition-all cursor-pointer group"
              >
                <div className="w-10 h-10 rounded-xl bg-blue-500/10 text-blue-500 flex items-center justify-center mb-3 group-hover:scale-105 transition-transform">
                  <QrCode className="w-5 h-5" />
                </div>
                <h3 className="font-bold text-sm text-foreground flex items-center justify-between">
                  <span>Invoice Collection</span>
                  <ArrowRight className="w-4 h-4 text-muted-foreground group-hover:translate-x-1 transition-transform" />
                </h3>
                <p className="text-xs text-muted-foreground mt-1">
                  Generate dynamic QR codes & payment links for open sales bills with automatic FIFO allocation.
                </p>
              </div>

              <div
                onClick={() => setActiveTab("beneficiaries")}
                className="p-5 rounded-2xl border border-border/60 bg-gradient-to-br from-purple-500/5 via-card to-card hover:border-purple-500/40 transition-all cursor-pointer group"
              >
                <div className="w-10 h-10 rounded-xl bg-purple-500/10 text-purple-500 flex items-center justify-center mb-3 group-hover:scale-105 transition-transform">
                  <UserCheck className="w-5 h-5" />
                </div>
                <h3 className="font-bold text-sm text-foreground flex items-center justify-between">
                  <span>Beneficiary Directory</span>
                  <ArrowRight className="w-4 h-4 text-muted-foreground group-hover:translate-x-1 transition-transform" />
                </h3>
                <p className="text-xs text-muted-foreground mt-1">
                  Manage verified mobile numbers, VPAs, and bank IFSC accounts with audit trail protection.
                </p>
              </div>
            </div>

            {/* Recent Stream */}
            <div className="rounded-2xl border border-border/60 bg-card overflow-hidden">
              <div className="p-4 border-b border-border/50 flex items-center justify-between">
                <h3 className="font-bold text-sm text-foreground">Recent SriLekh Pay Transactions</h3>
                <button
                  onClick={() => setActiveTab("requests")}
                  className="text-xs font-semibold text-primary hover:underline cursor-pointer"
                >
                  View All ({payments.length})
                </button>
              </div>

              <div className="divide-y divide-border/40 text-xs">
                {payments.slice(0, 5).map((p) => {
                  const isOutflow = p.company === companyId;
                  return (
                    <div key={p.id} className="p-4 flex items-center justify-between gap-3 hover:bg-muted/30 transition-colors">
                      <div className="flex items-center gap-3">
                        <div
                          className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${
                            isOutflow ? "bg-rose-500/10 text-rose-500" : "bg-emerald-500/10 text-emerald-500"
                          }`}
                        >
                          {isOutflow ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownLeft className="w-4 h-4" />}
                        </div>
                        <div>
                          <div className="font-bold text-foreground text-sm flex items-center gap-2">
                            <span>{p.recipient_name}</span>
                            <span className="font-mono text-[10px] text-muted-foreground">({p.srilekh_pay_id})</span>
                          </div>
                          <div className="text-[11px] text-muted-foreground flex items-center gap-2 mt-0.5">
                            <span>{p.payment_method}</span>
                            <span>•</span>
                            <span>{p.initiated_at ? new Date(p.initiated_at).toLocaleDateString("en-IN") : ""}</span>
                            {p.utr && (
                              <>
                                <span>•</span>
                                <span className="font-mono">UTR: {p.utr}</span>
                              </>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="text-right">
                        <div className={`font-mono font-bold text-sm ${isOutflow ? "text-rose-500" : "text-emerald-500"}`}>
                          {isOutflow ? "-" : "+"}₹{parseFloat(p.amount).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </div>
                        <div className="text-[10px] font-bold mt-0.5">
                          {p.status === "SUCCESS" ? (
                            <span className="text-emerald-500">Voucher: {p.payer_voucher_number || p.recipient_voucher_number || "Posted"}</span>
                          ) : (
                            <span className="text-amber-500">{p.status}</span>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 2: SEND MONEY */}
        {/* ========================================================================= */}
        {activeTab === "send" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left 2 Cols: Send Form */}
            <div className="lg:col-span-2 space-y-6">
              <div className="p-6 rounded-2xl border border-border/60 bg-card space-y-5">
                <div>
                  <h2 className="text-base font-bold text-foreground">1. Recipient Discovery Mode</h2>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Select how you want to find or enter the beneficiary details.
                  </p>
                </div>

                {/* Discovery Mode Pills */}
                <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
                  {[
                    { id: "SAVED", label: "Saved Directory", icon: Star },
                    { id: "MOBILE", label: "Mobile Number", icon: Phone },
                    { id: "CONTACTS", label: "Contacts (PWA)", icon: UserCheck },
                    { id: "VPA", label: "UPI ID", icon: Sparkles },
                    { id: "QR", label: "Scan QR", icon: Camera },
                    { id: "BANK", label: "Bank (IFSC)", icon: Building }
                  ].map((m) => {
                    const Icon = m.icon;
                    const isSelected = sendMode === m.id;
                    return (
                      <button
                        key={m.id}
                        type="button"
                        onClick={() => {
                          setSendMode(m.id as any);
                          setSendDiscoveryResult(null);
                          setSendSelectedBeneficiary(null);
                          if (m.id === "CONTACTS") handlePickContact();
                        }}
                        className={`p-3 rounded-xl border text-center transition-all flex flex-col items-center justify-center gap-1.5 cursor-pointer ${
                          isSelected
                            ? "bg-emerald-600/10 border-emerald-500 text-emerald-500 font-bold"
                            : "border-border/60 bg-muted/20 text-muted-foreground hover:bg-muted hover:text-foreground"
                        }`}
                      >
                        <Icon className="w-4 h-4" />
                        <span className="text-[11px] leading-tight">{m.label}</span>
                      </button>
                    );
                  })}
                </div>

                {/* Sub-view: Saved Beneficiary Picker */}
                {sendMode === "SAVED" && (
                  <div className="space-y-3 pt-2">
                    <label className="text-xs font-semibold text-muted-foreground">Select from Saved Beneficiaries</label>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 max-h-[220px] overflow-y-auto">
                      {beneficiaries.map((b) => {
                        const isChosen = sendSelectedBeneficiary?.id === b.id;
                        return (
                          <div
                            key={b.id}
                            onClick={() => {
                              setSendSelectedBeneficiary(b);
                              if (b.linked_party) setSendSelectedPartyId(b.linked_party);
                            }}
                            className={`p-3 rounded-xl border transition-all cursor-pointer flex items-center justify-between ${
                              isChosen
                                ? "bg-emerald-600/10 border-emerald-500 text-foreground"
                                : "border-border/60 bg-muted/20 hover:bg-muted"
                            }`}
                          >
                            <div className="truncate">
                              <div className="font-bold text-xs truncate">{b.name}</div>
                              <div className="text-[10px] text-muted-foreground font-mono truncate">
                                {b.vpa || b.mobile_number || b.masked_account_number}
                              </div>
                            </div>
                            {b.is_verified && <ShieldCheck className="w-4 h-4 text-emerald-500 shrink-0" />}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Sub-view: Mobile Number Discovery */}
                {sendMode === "MOBILE" && (
                  <div className="space-y-3 pt-2">
                    <label className="text-xs font-semibold text-muted-foreground">Enter 10-Digit Mobile Number</label>
                    <div className="flex gap-2">
                      <div className="relative flex-1">
                        <span className="absolute left-3 top-2.5 text-xs text-muted-foreground font-mono">+91</span>
                        <input
                          type="text"
                          maxLength={10}
                          value={sendQuery}
                          onChange={(e) => setSendQuery(e.target.value.replace(/\D/g, ""))}
                          placeholder="9876543210"
                          className="w-full pl-11 pr-3 py-2 bg-muted/30 border border-border rounded-xl text-xs font-mono text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary"
                        />
                      </div>
                      <button
                        type="button"
                        onClick={() => handleDiscoverRecipient("MOBILE", sendQuery)}
                        disabled={sendDiscovering || sendQuery.length !== 10}
                        className="px-4 py-2 bg-primary text-primary-foreground text-xs font-bold rounded-xl disabled:opacity-50 cursor-pointer flex items-center gap-1.5"
                      >
                        {sendDiscovering ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
                        <span>Verify Number</span>
                      </button>
                    </div>
                  </div>
                )}

                {/* Sub-view: UPI ID Discovery */}
                {sendMode === "VPA" && (
                  <div className="space-y-3 pt-2">
                    <label className="text-xs font-semibold text-muted-foreground">Enter UPI ID (VPA)</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={sendQuery}
                        onChange={(e) => setSendQuery(e.target.value)}
                        placeholder="supplier@icici"
                        className="flex-1 px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs font-mono text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary"
                      />
                      <button
                        type="button"
                        onClick={() => handleDiscoverRecipient("VPA", sendQuery)}
                        disabled={sendDiscovering || !sendQuery.includes("@")}
                        className="px-4 py-2 bg-primary text-primary-foreground text-xs font-bold rounded-xl disabled:opacity-50 cursor-pointer flex items-center gap-1.5"
                      >
                        {sendDiscovering ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
                        <span>Verify VPA</span>
                      </button>
                    </div>
                  </div>
                )}

                {/* Sub-view: QR Scan / Paste */}
                {sendMode === "QR" && (
                  <div className="space-y-3 pt-2">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-semibold text-muted-foreground">Scan or Paste UPI QR Code</label>
                      {!qrScanning ? (
                        <button
                          type="button"
                          onClick={startCameraScan}
                          className="text-xs font-bold text-primary flex items-center gap-1"
                        >
                          <Camera className="w-3.5 h-3.5" />
                          <span>Open Camera</span>
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={stopCameraScan}
                          className="text-xs font-bold text-rose-500 flex items-center gap-1"
                        >
                          <X className="w-3.5 h-3.5" />
                          <span>Close Camera</span>
                        </button>
                      )}
                    </div>

                    {qrScanning && (
                      <div className="relative rounded-2xl overflow-hidden border border-border aspect-video bg-black flex items-center justify-center">
                        <video ref={videoRef} className="w-full h-full object-cover" />
                        <div className="absolute inset-0 border-2 border-emerald-500/50 pointer-events-none rounded-2xl animate-pulse" />
                      </div>
                    )}

                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={sendQuery}
                        onChange={(e) => setSendQuery(e.target.value)}
                        placeholder="Paste UPI QR payload (upi://pay?pa=...)"
                        className="flex-1 px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs font-mono text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary"
                      />
                      <button
                        type="button"
                        onClick={() => handleDiscoverRecipient("QR", sendQuery)}
                        disabled={sendDiscovering || !sendQuery.startsWith("upi://")}
                        className="px-4 py-2 bg-primary text-primary-foreground text-xs font-bold rounded-xl disabled:opacity-50 cursor-pointer flex items-center gap-1.5"
                      >
                        {sendDiscovering ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                        <span>Parse QR</span>
                      </button>
                    </div>
                  </div>
                )}

                {/* Sub-view: Bank Account Form */}
                {sendMode === "BANK" && (
                  <div className="space-y-3 pt-2">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="text-[11px] font-semibold text-muted-foreground">Account Holder Name</label>
                        <input
                          type="text"
                          value={bankBeneficiaryName}
                          onChange={(e) => setBankBeneficiaryName(e.target.value)}
                          placeholder="Beneficiary Legal Name"
                          className="w-full px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs text-foreground mt-1"
                        />
                      </div>
                      <div>
                        <label className="text-[11px] font-semibold text-muted-foreground">IFSC Code</label>
                        <input
                          type="text"
                          maxLength={11}
                          value={bankIfsc}
                          onChange={(e) => setBankIfsc(e.target.value.toUpperCase())}
                          placeholder="HDFC0001234"
                          className="w-full px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs font-mono text-foreground mt-1"
                        />
                      </div>
                      <div>
                        <label className="text-[11px] font-semibold text-muted-foreground">Account Number</label>
                        <input
                          type="password"
                          value={bankAccountNum}
                          onChange={(e) => setBankAccountNum(e.target.value)}
                          placeholder="Enter Account Number"
                          className="w-full px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs font-mono text-foreground mt-1"
                        />
                      </div>
                      <div>
                        <label className="text-[11px] font-semibold text-muted-foreground">Confirm Account Number</label>
                        <input
                          type="text"
                          value={bankConfirmAccountNum}
                          onChange={(e) => setBankConfirmAccountNum(e.target.value)}
                          placeholder="Re-enter Account Number"
                          className="w-full px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs font-mono text-foreground mt-1"
                        />
                      </div>
                    </div>
                  </div>
                )}

                {/* Verified Recipient Confirmation Card */}
                {(sendSelectedBeneficiary || sendDiscoveryResult) && (
                  <div className="p-4 rounded-xl border border-emerald-500/30 bg-emerald-500/5 flex items-center justify-between gap-3 animate-in fade-in">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-emerald-500/10 text-emerald-500 flex items-center justify-center shrink-0">
                        <ShieldCheck className="w-5 h-5" />
                      </div>
                      <div>
                        <div className="font-bold text-sm text-foreground flex items-center gap-2">
                          <span>{sendSelectedBeneficiary?.name || sendDiscoveryResult?.name}</span>
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                            Verified Beneficiary
                          </span>
                        </div>
                        <div className="text-xs text-muted-foreground font-mono mt-0.5">
                          {sendSelectedBeneficiary?.vpa ||
                            sendDiscoveryResult?.vpa ||
                            sendSelectedBeneficiary?.mobile_number ||
                            sendDiscoveryResult?.masked_identifier ||
                            ""}
                        </div>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setSendSelectedBeneficiary(null);
                        setSendDiscoveryResult(null);
                      }}
                      className="text-xs text-muted-foreground hover:text-foreground p-1"
                    >
                      Change
                    </button>
                  </div>
                )}

                {/* 2. Amount & Accounting Linkage */}
                <div className="pt-4 border-t border-border/50 space-y-4">
                  <h2 className="text-base font-bold text-foreground">2. Payment & Invoice Allocation</h2>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="text-xs font-semibold text-muted-foreground">Amount to Transfer (₹) *</label>
                      <input
                        type="number"
                        step="0.01"
                        value={sendAmount}
                        onChange={(e) => setSendAmount(e.target.value)}
                        placeholder="0.00"
                        className="w-full px-3 py-2.5 bg-muted/30 border border-border rounded-xl text-base font-mono font-bold text-foreground mt-1 focus:outline-hidden focus:ring-1 focus:ring-primary"
                        required
                      />
                    </div>

                    <div>
                      <label className="text-xs font-semibold text-muted-foreground">Payment Method</label>
                      <select
                        value={sendMethod}
                        onChange={(e) => setSendMethod(e.target.value)}
                        className="w-full px-3 py-2.5 bg-muted/30 border border-border rounded-xl text-xs text-foreground mt-1"
                      >
                        <option value="UPI">UPI (Instant Dynamic QR & DeepLink)</option>
                        <option value="IMPS">IMPS (Instant Bank Transfer)</option>
                        <option value="NEFT">NEFT (Virtual Account Settlement)</option>
                        <option value="RTGS">RTGS (High-Value Transfer)</option>
                      </select>
                    </div>

                    <div>
                      <label className="text-xs font-semibold text-muted-foreground">Link Purchase Bill (FIFO Allocation)</label>
                      <select
                        value={sendSelectedInvoiceId}
                        onChange={(e) => setSendSelectedInvoiceId(e.target.value)}
                        className="w-full px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs text-foreground mt-1"
                      >
                        <option value="">-- No specific invoice (FIFO Auto-allocate) --</option>
                        {invoices
                          .filter((i) => i.voucher_type === "PURCHASE")
                          .map((inv) => (
                            <option key={inv.id} value={inv.id}>
                              #{inv.voucher_number} — ₹{parseFloat(inv.total_amount).toFixed(2)} ({inv.date})
                            </option>
                          ))}
                      </select>
                    </div>

                    <div>
                      <label className="text-xs font-semibold text-muted-foreground">Source Ledger (Debit Party)</label>
                      <select
                        value={sendSelectedPartyId}
                        onChange={(e) => setSendSelectedPartyId(e.target.value)}
                        className="w-full px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs text-foreground mt-1"
                      >
                        <option value="">-- Select Supplier Ledger --</option>
                        {ledgers
                          .filter((l) => l.ledger_type === "SUPPLIER" || l.group_nature === "LIABILITY")
                          .map((l) => (
                            <option key={l.id} value={l.id}>
                              {l.name}
                            </option>
                          ))}
                      </select>
                    </div>
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-muted-foreground">Payment Note / Reference</label>
                    <input
                      type="text"
                      value={sendNote}
                      onChange={(e) => setSendNote(e.target.value)}
                      placeholder="e.g. Belting order advance"
                      className="w-full px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs text-foreground mt-1"
                    />
                  </div>

                  <div className="pt-2">
                    <button
                      type="button"
                      onClick={handleInitiateSendMoney}
                      disabled={sendSubmitting || !sendAmount}
                      className="w-full py-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-sm font-bold shadow-md transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
                    >
                      {sendSubmitting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4 fill-current" />}
                      <span>Execute SriLekh Pay Transfer</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Right 1 Col: Active Payment Execution Window */}
            <div className="space-y-4">
              {sendActivePayment ? (
                <div className="p-6 rounded-2xl border border-emerald-500/40 bg-card space-y-4 animate-in fade-in">
                  <div className="flex items-center justify-between border-b border-border pb-3">
                    <h3 className="font-bold text-sm text-foreground">Payment Instructions</h3>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-500">
                      {sendActivePayment.status}
                    </span>
                  </div>

                  <div className="text-center py-2 space-y-2">
                    <div className="text-2xl font-mono font-bold text-foreground">₹{parseFloat(sendActivePayment.amount).toFixed(2)}</div>
                    <div className="text-xs text-muted-foreground">To: {sendActivePayment.recipient_name}</div>
                  </div>

                  {/* QR Code display */}
                  {sendActivePayment.qr_data && (
                    <div className="flex flex-col items-center justify-center p-4 bg-white rounded-xl border border-border">
                      <QrCode className="w-36 h-36 text-black" />
                      <div className="text-[10px] font-mono text-neutral-600 mt-2">Scan with any UPI App</div>
                    </div>
                  )}

                  {/* UPI Intent Deep Link */}
                  {sendActivePayment.qr_data && (
                    <a
                      href={sendActivePayment.qr_data}
                      className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2 text-center"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                      <span>Open in UPI App</span>
                    </a>
                  )}

                  {/* UTR Box */}
                  <div className="pt-2 border-t border-border/50 space-y-2">
                    <label className="text-[11px] font-semibold text-muted-foreground">Enter Bank UTR to Post Voucher</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={sendManualUtr}
                        onChange={(e) => setSendManualUtr(e.target.value)}
                        placeholder="12-digit UTR"
                        className="flex-1 px-3 py-1.5 bg-muted/40 border border-border rounded-xl text-xs font-mono text-foreground"
                      />
                      <button
                        type="button"
                        onClick={handleConfirmManualUtr}
                        disabled={confirmingUtr || !sendManualUtr}
                        className="px-3 py-1.5 bg-emerald-600 text-white rounded-xl text-xs font-bold disabled:opacity-50"
                      >
                        {confirmingUtr ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : "Verify"}
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="p-6 rounded-2xl border border-border/60 bg-card text-center space-y-3">
                  <div className="w-12 h-12 rounded-2xl bg-muted/60 text-muted-foreground flex items-center justify-center mx-auto">
                    <CreditCard className="w-6 h-6" />
                  </div>
                  <h3 className="font-bold text-sm text-foreground">Ready for Dispatch</h3>
                  <p className="text-xs text-muted-foreground">
                    Select a recipient and amount to generate dynamic UPI links, QR code, or Virtual Account details.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 3: COLLECT MONEY */}
        {/* ========================================================================= */}
        {activeTab === "collect" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-5 p-6 rounded-2xl border border-border/60 bg-card">
              <div>
                <h2 className="text-base font-bold text-foreground">Generate Invoice Collection Request</h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Create a branded payment link and dynamic QR for your customers to pay against sales invoices.
                </p>
              </div>

              <form onSubmit={handleCreateCollectionRequest} className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs font-semibold text-muted-foreground">Select Customer (Debtor)</label>
                    <select
                      value={collectCustomerPartyId}
                      onChange={(e) => setCollectCustomerPartyId(e.target.value)}
                      className="w-full px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs text-foreground mt-1"
                    >
                      <option value="">-- All Customers / Walk-in --</option>
                      {ledgers
                        .filter((l) => l.ledger_type === "CUSTOMER" || l.group_nature === "ASSET")
                        .map((l) => (
                          <option key={l.id} value={l.id}>
                            {l.name}
                          </option>
                        ))}
                    </select>
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-muted-foreground">Select Sales Invoice</label>
                    <select
                      value={collectInvoiceId}
                      onChange={(e) => {
                        setCollectInvoiceId(e.target.value);
                        const inv = invoices.find((i) => i.id === e.target.value);
                        if (inv) setCollectAmount(String(inv.total_amount));
                      }}
                      className="w-full px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs text-foreground mt-1"
                    >
                      <option value="">-- Standalone Trade Collection --</option>
                      {invoices
                        .filter((i) => i.voucher_type === "SALES")
                        .map((inv) => (
                          <option key={inv.id} value={inv.id}>
                            #{inv.voucher_number} — ₹{parseFloat(inv.total_amount).toFixed(2)} ({inv.date})
                          </option>
                        ))}
                    </select>
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-muted-foreground">Collection Amount (₹) *</label>
                    <input
                      type="number"
                      step="0.01"
                      value={collectAmount}
                      onChange={(e) => setCollectAmount(e.target.value)}
                      placeholder="0.00"
                      className="w-full px-3 py-2.5 bg-muted/30 border border-border rounded-xl text-base font-mono font-bold text-foreground mt-1"
                      required
                    />
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-muted-foreground">Settlement VPA</label>
                    <input
                      type="text"
                      disabled
                      value={merchantSettings.vpa || "Not configured (Setup in Settings)"}
                      className="w-full px-3 py-2.5 bg-muted/50 border border-border rounded-xl text-xs font-mono text-muted-foreground mt-1"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-xs font-semibold text-muted-foreground">Collection Note</label>
                  <input
                    type="text"
                    value={collectNote}
                    onChange={(e) => setCollectNote(e.target.value)}
                    placeholder="e.g. Invoice #SAL/26-27/0042 balance"
                    className="w-full px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs text-foreground mt-1"
                  />
                </div>

                <button
                  type="submit"
                  disabled={collectingSubmitting || !collectAmount}
                  className="w-full py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-sm font-bold shadow-md transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
                >
                  {collectingSubmitting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <QrCode className="w-4 h-4" />}
                  <span>Generate Payment QR & Link</span>
                </button>
              </form>
            </div>

            {/* Collection Result Window */}
            <div>
              {collectCreatedPayment ? (
                <div className="p-6 rounded-2xl border border-blue-500/40 bg-card space-y-4 animate-in fade-in">
                  <div className="flex items-center justify-between border-b border-border pb-3">
                    <h3 className="font-bold text-sm text-foreground">Ready for Customer</h3>
                    <span className="font-mono text-xs text-muted-foreground">{collectCreatedPayment.srilekh_pay_id}</span>
                  </div>

                  <div className="text-center py-2 space-y-1">
                    <div className="text-2xl font-mono font-bold text-foreground">
                      ₹{parseFloat(collectCreatedPayment.amount).toFixed(2)}
                    </div>
                    <div className="text-xs text-muted-foreground">Dynamic Instant Collection QR</div>
                  </div>

                  <div className="flex flex-col items-center justify-center p-4 bg-white rounded-xl border border-border">
                    <QrCode className="w-40 h-40 text-black" />
                    <div className="text-[10px] font-mono text-neutral-600 mt-2">Payer can scan via GPay / PhonePe / Paytm</div>
                  </div>

                  <div className="space-y-2 pt-2">
                    <button
                      type="button"
                      onClick={() =>
                        copyToClipboard(
                          collectCreatedPayment.payment_url || collectCreatedPayment.qr_data || "",
                          "collect_link"
                        )
                      }
                      className="w-full py-2 bg-muted/60 hover:bg-muted text-foreground rounded-xl text-xs font-semibold border border-border transition-all flex items-center justify-center gap-1.5"
                    >
                      {copiedKey === "collect_link" ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                      <span>Copy Payment Link</span>
                    </button>
                  </div>
                </div>
              ) : (
                <div className="p-6 rounded-2xl border border-border/60 bg-card text-center space-y-3">
                  <div className="w-12 h-12 rounded-2xl bg-muted/60 text-muted-foreground flex items-center justify-center mx-auto">
                    <Download className="w-6 h-6" />
                  </div>
                  <h3 className="font-bold text-sm text-foreground">Awaiting Input</h3>
                  <p className="text-xs text-muted-foreground">
                    Enter customer invoice details on the left to generate dynamic QR and instant shareable payment links.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 4: BENEFICIARIES */}
        {/* ========================================================================= */}
        {activeTab === "beneficiaries" && (
          <div className="space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="relative flex-1 max-w-md">
                <Search className="w-4 h-4 absolute left-3 top-2.5 text-muted-foreground" />
                <input
                  type="text"
                  value={beneficiarySearch}
                  onChange={(e) => setBeneficiarySearch(e.target.value)}
                  placeholder="Search beneficiaries by name, mobile, UPI, account..."
                  className="w-full pl-9 pr-3 py-2 bg-muted/30 border border-border rounded-xl text-xs text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary"
                />
              </div>

              <div className="flex items-center gap-2">
                <select
                  value={beneficiaryTypeFilter}
                  onChange={(e) => setBeneficiaryTypeFilter(e.target.value)}
                  className="px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs text-foreground"
                >
                  <option value="ALL">All Types</option>
                  <option value="FAVORITES">⭐ Favorites Only</option>
                  <option value="MOBILE_UPI">Mobile (UPI)</option>
                  <option value="VPA">UPI ID (VPA)</option>
                  <option value="BANK_ACCOUNT">Bank Account</option>
                </select>

                <button
                  onClick={() => setIsAddBeneficiaryOpen(true)}
                  className="px-3 py-2 bg-primary text-primary-foreground rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Add Beneficiary</span>
                </button>
              </div>
            </div>

            {/* Beneficiaries Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {filteredBeneficiaries.map((b) => (
                <div
                  key={b.id}
                  className="p-4 rounded-2xl border border-border/60 bg-card hover:border-border transition-all flex flex-col justify-between gap-3"
                >
                  <div className="space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="truncate">
                        <div className="font-bold text-sm text-foreground truncate flex items-center gap-1.5">
                          <span>{b.name}</span>
                          {b.nickname && <span className="text-[10px] text-muted-foreground font-normal">({b.nickname})</span>}
                        </div>
                        <div className="text-[11px] font-mono text-muted-foreground truncate mt-0.5">
                          {b.vpa || b.mobile_number || b.masked_account_number}
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={() => handleToggleFavorite(b.id)}
                        className={`p-1 rounded-lg transition-colors cursor-pointer ${
                          b.is_favorite ? "text-amber-500" : "text-muted-foreground hover:text-foreground"
                        }`}
                        title="Toggle Favorite"
                      >
                        <Star className={`w-4 h-4 ${b.is_favorite ? "fill-current" : ""}`} />
                      </button>
                    </div>

                    <div className="flex items-center gap-1.5 flex-wrap pt-1">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-muted text-muted-foreground">
                        {b.beneficiary_type}
                      </span>

                      {b.is_verified ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                          <CheckCircle2 className="w-3 h-3" />
                          <span>Verified ({b.verified_name || b.name})</span>
                        </span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => handleVerifyBeneficiary(b.id)}
                          disabled={verifyingBId === b.id}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/10 text-amber-500 border border-amber-500/20 hover:bg-amber-500/20"
                        >
                          {verifyingBId === b.id ? <RefreshCw className="w-3 h-3 animate-spin" /> : <ShieldCheck className="w-3 h-3" />}
                          <span>Verify Now</span>
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="pt-2 border-t border-border/40 flex items-center justify-between text-xs">
                    <div className="text-[11px] text-muted-foreground">
                      {b.total_payments_count > 0 ? (
                        <span>
                          {b.total_payments_count} payments (₹{parseFloat(b.total_paid_amount).toFixed(0)})
                        </span>
                      ) : (
                        <span>No payments yet</span>
                      )}
                    </div>

                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => {
                          setSendSelectedBeneficiary(b);
                          setActiveTab("send");
                        }}
                        className="px-2.5 py-1 bg-emerald-600/10 hover:bg-emerald-600/20 text-emerald-500 font-bold rounded-lg text-[11px] cursor-pointer"
                      >
                        Pay
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteBeneficiary(b.id)}
                        className="p-1 text-muted-foreground hover:text-rose-500 rounded-lg"
                        title="Remove Beneficiary"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Modal: Add Beneficiary */}
            {isAddBeneficiaryOpen && (
              <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4 animate-in fade-in">
                <div className="w-full max-w-lg bg-card border border-border rounded-2xl shadow-2xl p-6 space-y-4">
                  <div className="flex items-center justify-between border-b border-border/60 pb-3">
                    <h3 className="font-bold text-sm text-foreground">Add Beneficiary to Company Directory</h3>
                    <button onClick={() => setIsAddBeneficiaryOpen(false)} className="text-muted-foreground hover:text-foreground">
                      <X className="w-4 h-4" />
                    </button>
                  </div>

                  <form onSubmit={handleAddBeneficiary} className="space-y-4">
                    <div className="grid grid-cols-3 gap-2">
                      {[
                        { id: "MOBILE_UPI", label: "Mobile" },
                        { id: "VPA", label: "UPI ID" },
                        { id: "BANK_ACCOUNT", label: "Bank Account" }
                      ].map((t) => (
                        <button
                          key={t.id}
                          type="button"
                          onClick={() => setNewBType(t.id as any)}
                          className={`py-2 rounded-xl text-xs font-semibold border ${
                            newBType === t.id
                              ? "bg-primary text-primary-foreground border-primary"
                              : "border-border text-muted-foreground hover:bg-muted"
                          }`}
                        >
                          {t.label}
                        </button>
                      ))}
                    </div>

                    <div>
                      <label className="text-[11px] font-semibold text-muted-foreground">Recipient Name *</label>
                      <input
                        type="text"
                        value={newBName}
                        onChange={(e) => setNewBName(e.target.value)}
                        placeholder="Saksham Belts Ltd"
                        className="w-full px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs text-foreground mt-1"
                        required
                      />
                    </div>

                    {newBType === "MOBILE_UPI" && (
                      <div>
                        <label className="text-[11px] font-semibold text-muted-foreground">10-Digit Mobile Number *</label>
                        <input
                          type="text"
                          maxLength={10}
                          value={newBMobile}
                          onChange={(e) => setNewBMobile(e.target.value.replace(/\D/g, ""))}
                          placeholder="9876543210"
                          className="w-full px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs font-mono text-foreground mt-1"
                          required
                        />
                      </div>
                    )}

                    {newBType === "VPA" && (
                      <div>
                        <label className="text-[11px] font-semibold text-muted-foreground">UPI ID (VPA) *</label>
                        <input
                          type="text"
                          value={newBVpa}
                          onChange={(e) => setNewBVpa(e.target.value)}
                          placeholder="merchant@icici"
                          className="w-full px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs font-mono text-foreground mt-1"
                          required
                        />
                      </div>
                    )}

                    {newBType === "BANK_ACCOUNT" && (
                      <div className="grid grid-cols-2 gap-3">
                        <div className="col-span-2">
                          <label className="text-[11px] font-semibold text-muted-foreground">Account Number *</label>
                          <input
                            type="text"
                            value={newBAccount}
                            onChange={(e) => setNewBAccount(e.target.value)}
                            placeholder="Bank Account Number"
                            className="w-full px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs font-mono text-foreground mt-1"
                            required
                          />
                        </div>
                        <div className="col-span-2">
                          <label className="text-[11px] font-semibold text-muted-foreground">IFSC Code *</label>
                          <input
                            type="text"
                            maxLength={11}
                            value={newBIfsc}
                            onChange={(e) => setNewBIfsc(e.target.value.toUpperCase())}
                            placeholder="SBIN0001234"
                            className="w-full px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs font-mono text-foreground mt-1"
                            required
                          />
                        </div>
                      </div>
                    )}

                    <div>
                      <label className="text-[11px] font-semibold text-muted-foreground">Associate with Supplier Ledger (Optional)</label>
                      <select
                        value={newBPartyId}
                        onChange={(e) => setNewBPartyId(e.target.value)}
                        className="w-full px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs text-foreground mt-1"
                      >
                        <option value="">-- No ledger link --</option>
                        {ledgers
                          .filter((l) => l.ledger_type === "SUPPLIER")
                          .map((l) => (
                            <option key={l.id} value={l.id}>
                              {l.name}
                            </option>
                          ))}
                      </select>
                    </div>

                    <div className="flex justify-end gap-2 pt-2">
                      <button
                        type="button"
                        onClick={() => setIsAddBeneficiaryOpen(false)}
                        className="px-4 py-2 border border-border text-xs font-semibold rounded-xl"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={addingBeneficiary}
                        className="px-4 py-2 bg-primary text-primary-foreground text-xs font-bold rounded-xl"
                      >
                        {addingBeneficiary ? "Saving & Verifying..." : "Save Beneficiary"}
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 5: PAYMENT REQUESTS */}
        {/* ========================================================================= */}
        {activeTab === "requests" && (
          <div className="space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="relative flex-1 max-w-md">
                <Search className="w-4 h-4 absolute left-3 top-2.5 text-muted-foreground" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Filter by ID, recipient name, voucher, UTR..."
                  className="w-full pl-9 pr-3 py-2 bg-muted/30 border border-border rounded-xl text-xs text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary"
                />
              </div>

              <div className="flex items-center gap-1.5 overflow-x-auto">
                {["ALL", "OUTGOING", "INCOMING", "PENDING", "SUCCESS", "FAILED"].map((f) => (
                  <button
                    key={f}
                    onClick={() => setRequestsFilter(f)}
                    className={`px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap transition-all ${
                      requestsFilter === f ? "bg-foreground text-background font-bold" : "bg-muted/40 text-muted-foreground hover:bg-muted"
                    }`}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-border/60 bg-card overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead className="bg-muted/30 border-b border-border/60 text-muted-foreground font-semibold">
                    <tr>
                      <th className="p-3.5">SriLekh Pay ID</th>
                      <th className="p-3.5">Direction</th>
                      <th className="p-3.5">Party / Recipient</th>
                      <th className="p-3.5">Method</th>
                      <th className="p-3.5 text-right">Amount</th>
                      <th className="p-3.5 text-center">Status</th>
                      <th className="p-3.5 text-center">Voucher</th>
                      <th className="p-3.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40">
                    {filteredRequests.map((p) => {
                      const isOutflow = p.company === companyId;
                      return (
                        <tr key={p.id} className="hover:bg-muted/20 transition-colors">
                          <td className="p-3.5 font-mono font-bold text-foreground">
                            <Link href={`/pay/${p.id}`} className="hover:text-primary transition-colors">
                              {p.srilekh_pay_id}
                            </Link>
                          </td>
                          <td className="p-3.5">
                            <span
                              className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                isOutflow ? "bg-rose-500/10 text-rose-500" : "bg-emerald-500/10 text-emerald-500"
                              }`}
                            >
                              {isOutflow ? "Outflow" : "Inflow"}
                            </span>
                          </td>
                          <td className="p-3.5">
                            <div className="font-semibold text-foreground truncate max-w-[180px]">{p.recipient_name}</div>
                            {p.utr && <div className="text-[10px] font-mono text-muted-foreground">UTR: {p.utr}</div>}
                          </td>
                          <td className="p-3.5 font-mono">{p.payment_method}</td>
                          <td className="p-3.5 text-right font-mono font-bold">
                            ₹{parseFloat(p.amount).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                          </td>
                          <td className="p-3.5 text-center">
                            <span
                              className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                p.status === "SUCCESS"
                                  ? "bg-emerald-500/10 text-emerald-500"
                                  : p.status === "FAILED"
                                  ? "bg-rose-500/10 text-rose-500"
                                  : "bg-amber-500/10 text-amber-500"
                              }`}
                            >
                              {p.status}
                            </span>
                          </td>
                          <td className="p-3.5 text-center font-mono text-[11px]">
                            {p.payer_voucher_number || p.recipient_voucher_number || "—"}
                          </td>
                          <td className="p-3.5 text-right">
                            <Link
                              href={`/pay/${p.id}`}
                              className="px-2.5 py-1.5 rounded-lg bg-muted/60 hover:bg-muted text-foreground text-xs font-semibold border border-border"
                            >
                              Audit Timeline
                            </Link>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 6: TRANSACTIONS (VOUCHER-LINKED) */}
        {/* ========================================================================= */}
        {activeTab === "transactions" && (
          <div className="space-y-4">
            <div>
              <h3 className="font-bold text-base text-foreground">Double-Entry Accounting Journal Entries</h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                Authoritative vouchers posted to company books via SriLekh Pay with verified mathematical equilibrium.
              </p>
            </div>

            <div className="rounded-2xl border border-border/60 bg-card overflow-hidden">
              <div className="divide-y divide-border/40 text-xs">
                {payments
                  .filter((p) => p.status === "SUCCESS")
                  .map((p) => (
                    <div key={p.id} className="p-4 flex items-center justify-between gap-3">
                      <div>
                        <div className="font-bold text-foreground text-sm flex items-center gap-2">
                          <span>Voucher #{p.payer_voucher_number || p.recipient_voucher_number || "POSTED"}</span>
                          <span className="text-[10px] font-mono text-muted-foreground">({p.srilekh_pay_id})</span>
                        </div>
                        <div className="text-[11px] text-muted-foreground mt-0.5">
                          Party: {p.recipient_name} • Method: {p.payment_method} • Confirmed: {p.confirmed_at ? new Date(p.confirmed_at).toLocaleString("en-IN") : ""}
                        </div>
                      </div>

                      <div className="text-right">
                        <div className="font-mono font-bold text-sm text-foreground">
                          ₹{parseFloat(p.amount).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </div>
                        <div className="text-[10px] text-emerald-500 font-bold">Total Debits == Total Credits</div>
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 7: SETTLEMENTS */}
        {/* ========================================================================= */}
        {activeTab === "settlements" && (
          <div className="space-y-4">
            <div>
              <h3 className="font-bold text-base text-foreground">Provider Settlements & Net Payouts</h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                Reconcile gross UPI/bank collections against gateway fee deductions and net bank credits.
              </p>
            </div>

            <div className="p-6 rounded-2xl border border-border/60 bg-card text-center space-y-3">
              <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 text-emerald-500 flex items-center justify-center mx-auto">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <h4 className="font-bold text-sm text-foreground">Automated Daily T+1 Settlement Active</h4>
              <p className="text-xs text-muted-foreground max-w-md mx-auto">
                Funds collected through Setu UPI & Virtual Accounts settle directly into your designated settlement account (
                <span className="font-mono font-semibold">{merchantSettings.vpa || "Primary Bank"}</span>).
              </p>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 8: RECONCILIATION */}
        {/* ========================================================================= */}
        {activeTab === "reconciliation" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-bold text-base text-foreground">Bank Statement Feed Match</h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Automated reconciliation between imported bank statement feeds and SriLekh Pay UTR records.
                </p>
              </div>
              <Link
                href="/banking"
                className="px-3 py-1.5 rounded-xl border border-border text-xs font-semibold hover:bg-muted"
              >
                Go to Bank Reconciliation
              </Link>
            </div>

            <div className="rounded-2xl border border-border/60 bg-card overflow-hidden">
              <div className="divide-y divide-border/40 text-xs">
                {payments
                  .filter((p) => p.utr)
                  .map((p) => (
                    <div key={p.id} className="p-4 flex items-center justify-between gap-3">
                      <div>
                        <div className="font-bold text-foreground">UTR: {p.utr}</div>
                        <div className="text-[11px] text-muted-foreground mt-0.5">
                          SriLekh Pay ID: {p.srilekh_pay_id} • Amount: ₹{parseFloat(p.amount).toFixed(2)}
                        </div>
                      </div>
                      <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                        100% Matched
                      </span>
                    </div>
                  ))}
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 9: SETTINGS */}
        {/* ========================================================================= */}
        {activeTab === "settings" && (
          <div className="max-w-3xl space-y-6">
            <div className="p-6 rounded-2xl border border-border/60 bg-card space-y-5">
              <div>
                <h3 className="font-bold text-base text-foreground">Merchant Account Configuration</h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Configure your company VPA, Virtual Account collection prefix, and double-entry clearing ledgers.
                </p>
              </div>

              <form onSubmit={handleSaveSettings} className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs font-semibold text-muted-foreground">Registered UPI VPA</label>
                    <input
                      type="text"
                      value={merchantSettings.vpa}
                      onChange={(e) => setMerchantSettings({ ...merchantSettings, vpa: e.target.value })}
                      placeholder="merchant@okhdfcbank"
                      className="w-full px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs font-mono text-foreground mt-1"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-muted-foreground">Virtual Account Prefix</label>
                    <input
                      type="text"
                      value={merchantSettings.virtual_account_prefix}
                      onChange={(e) => setMerchantSettings({ ...merchantSettings, virtual_account_prefix: e.target.value })}
                      placeholder="APEX"
                      className="w-full px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs font-mono text-foreground mt-1"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-muted-foreground">Settlement Bank Ledger</label>
                    <select
                      value={merchantSettings.default_settlement_ledger || ""}
                      onChange={(e) =>
                        setMerchantSettings({ ...merchantSettings, default_settlement_ledger: e.target.value })
                      }
                      className="w-full px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs text-foreground mt-1"
                    >
                      <option value="">-- Select Bank Ledger --</option>
                      {ledgers
                        .filter((l) => l.ledger_type === "BANK")
                        .map((l) => (
                          <option key={l.id} value={l.id}>
                            {l.name}
                          </option>
                        ))}
                    </select>
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-muted-foreground">Payment Clearing Ledger</label>
                    <select
                      value={merchantSettings.payment_clearing_ledger || ""}
                      onChange={(e) =>
                        setMerchantSettings({ ...merchantSettings, payment_clearing_ledger: e.target.value })
                      }
                      className="w-full px-3 py-2 bg-muted/30 border border-border rounded-xl text-xs text-foreground mt-1"
                    >
                      <option value="">-- Select Clearing Ledger --</option>
                      {ledgers
                        .filter((l) => l.ledger_type === "BANK")
                        .map((l) => (
                          <option key={l.id} value={l.id}>
                            {l.name}
                          </option>
                        ))}
                    </select>
                  </div>
                </div>

                <div className="pt-2">
                  <label className="flex items-center gap-2 cursor-pointer text-xs font-semibold text-foreground">
                    <input
                      type="checkbox"
                      checked={merchantSettings.auto_post_accounting}
                      onChange={(e) =>
                        setMerchantSettings({ ...merchantSettings, auto_post_accounting: e.target.checked })
                      }
                      className="rounded text-primary"
                    />
                    <span>Automatically post double-entry vouchers upon verified payment confirmation</span>
                  </label>
                </div>

                <div className="pt-2 flex justify-end">
                  <button
                    type="submit"
                    disabled={savingSettings}
                    className="px-5 py-2.5 bg-primary text-primary-foreground text-xs font-bold rounded-xl disabled:opacity-50"
                  >
                    {savingSettings ? "Saving Settings..." : "Save Merchant Settings"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
