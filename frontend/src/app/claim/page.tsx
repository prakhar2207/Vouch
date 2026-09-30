"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import axios from "axios";
import { setTokens, isAuthenticated, getAccessToken } from "@/utils/auth";
import Link from "next/link";
import { API_BASE_URL } from "@/utils/api";
import {
  FileText,
  Building2,
  CheckCircle2,
  ArrowRight,
  Download,
  ShieldCheck,
  Zap,
  Lock,
  Sparkles,
  AlertCircle,
  RefreshCw,
  QrCode,
  ExternalLink,
} from "lucide-react";
import QRCode from "react-qr-code";

interface InvoicePreviewData {
  voucher_id: string;
  voucher_number: string;
  voucher_date: string;
  total_amount: number;
  seller: {
    id: string;
    name: string;
    legal_name?: string;
    gstin: string;
    state_code: string;
    city: string;
    upi_id?: string;
    bank_name?: string;
    bank_account_number?: string;
    bank_ifsc?: string;
  };
  buyer_prefill: {
    name: string;
    gstin: string;
    phone: string;
    email: string;
  };
  items: Array<{
    product_name: string;
    hsn_code: string;
    quantity: number;
    unit: string;
    rate: number;
    taxable_amount: number;
    gst_rate: number;
    total_amount: number;
  }>;
  token: string;
}

interface RecipientStatus {
  authenticated: boolean;
  is_recipient: boolean;
  is_seller?: boolean;
  already_added: boolean;
  invoice_id?: string;
  invoice_number?: string;
  invoice_date?: string;
  seller_name?: string;
  seller_gstin?: string;
  total_amount?: number;
  buyer_gstin?: string;
  buyer_name?: string;
  active_company_name?: string;
  active_company_gstin?: string;
  edi_request_id?: string;
  purchase_voucher_id?: string;
  purchase_voucher_number?: string;
  purchase_voucher_date?: string;
  error?: string;
}

function ClaimContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = searchParams.get("token") || searchParams.get("id") || "";

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<InvoicePreviewData | null>(null);

  // Recipient detection & duplicate prevention state
  const [recipientStatus, setRecipientStatus] = useState<RecipientStatus | null>(null);
  const [checkingRecipient, setCheckingRecipient] = useState(false);
  const [showAlreadyAddedModal, setShowAlreadyAddedModal] = useState(false);

  // Form state
  const [companyName, setCompanyName] = useState("");
  const [gstin, setGstin] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [showUpiModal, setShowUpiModal] = useState(false);

  useEffect(() => {
    if (!token) {
      setError("No invoice claim token provided. Please open the link sent via WhatsApp or Email.");
      setLoading(false);
      return;
    }

    const fetchPreview = async () => {
      try {
        const res = await axios.get(`${API_BASE_URL}/api/v1/accounting/vouchers/claim-preview/`, {
          params: { token },
        });
        setData(res.data);
        setCompanyName(res.data.buyer_prefill.name || "");
        setGstin(res.data.buyer_prefill.gstin || "");
        setEmail(res.data.buyer_prefill.email || "");

        // If user is logged in, check recipient match & duplicate status
        if (isAuthenticated()) {
          checkRecipientStatus(res.data.voucher_id);
        }
      } catch (err: any) {
        setError(err.response?.data?.error || "Invalid or expired invoice link.");
      } finally {
        setLoading(false);
      }
    };

    fetchPreview();
  }, [token]);

  const checkRecipientStatus = async (voucherId: string) => {
    setCheckingRecipient(true);
    try {
      const tokenStr = getAccessToken();
      const activeCompId = typeof window !== 'undefined' ? localStorage.getItem("vouch_active_company_id") || "" : "";
      const res = await axios.get(
        `${API_BASE_URL}/api/v1/accounting/vouchers/${voucherId}/recipient-status/`,
        {
          headers: {
            Authorization: `Bearer ${tokenStr}`,
            "X-Company-ID": activeCompId,
          },
        }
      );
      setRecipientStatus(res.data);
      if (res.data.already_added) {
        setShowAlreadyAddedModal(true);
      }
    } catch (err) {
      console.warn("Could not check recipient status:", err);
    } finally {
      setCheckingRecipient(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password) {
      setSubmitError("Please enter a secure password.");
      return;
    }
    if (password !== confirmPassword) {
      setSubmitError("Passwords do not match.");
      return;
    }

    setSubmitting(true);
    setSubmitError(null);

    try {
      const res = await axios.post(`${API_BASE_URL}/api/v1/accounting/vouchers/claim-register/`, {
        token,
        company_name: companyName,
        gstin,
        email,
        password,
      });

      const { access, refresh, company, redirect_url } = res.data;
      setTokens(access, refresh);

      if (company && company.id) {
        localStorage.setItem("vouch_active_company_id", company.id);
      }

      setSuccessMessage(
        "Account created! Your invoice has been linked directly to your EDI Inbox."
      );

      setTimeout(() => {
        router.push(redirect_url || "/network/inbox");
      }, 1500);
    } catch (err: any) {
      setSubmitError(err.response?.data?.error || "Registration failed. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-4">
        <div className="text-center space-y-3">
          <RefreshCw className="w-8 h-8 animate-spin text-primary mx-auto" />
          <p className="text-sm font-medium text-muted-foreground">Loading your invoice...</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-4">
        <div className="max-w-md w-full bg-card border border-border/40 rounded-2xl p-6 shadow-xl text-center space-y-4">
          <div className="w-12 h-12 rounded-full bg-rose-500/10 text-rose-500 flex items-center justify-center mx-auto">
            <AlertCircle className="w-6 h-6" />
          </div>
          <h2 className="text-lg font-bold text-foreground">Invoice Link Notice</h2>
          <p className="text-xs text-muted-foreground">{error || "Unable to load invoice preview."}</p>
          <button
            onClick={() => router.push("/login")}
            className="w-full py-2.5 px-4 text-xs font-semibold rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            Go to Vouch Sign In
          </button>
        </div>
      </div>
    );
  }

  const pdfUrl = `${API_BASE_URL}/api/v1/accounting/vouchers/${data.voucher_id}/pdf/?token=${token}`;

  return (
    <div className="min-h-screen bg-gradient-to-b from-background via-muted/20 to-background text-foreground py-8 px-4 sm:px-6 lg:px-8">
      <div className="max-w-4xl mx-auto space-y-8">
        
        {/* Brand Header */}
        <div className="text-center space-y-2">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 border border-primary/20 text-primary text-xs font-semibold">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Connected B2B Invoicing</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
            Tax Invoice from {data.seller.name}
          </h1>
          <p className="text-xs sm:text-sm text-muted-foreground max-w-xl mx-auto">
            Download your official GST invoice or import it directly into your books with zero manual data entry.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          
          {/* LEFT: INVOICE SUMMARY CARD */}
          <div className="lg:col-span-6 space-y-4">
            <div className="bg-card border border-border/40 rounded-2xl p-6 shadow-lg space-y-5">
              <div className="flex items-center justify-between border-b border-border/40 pb-4">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Tax Invoice
                  </div>
                  <div className="text-lg font-extrabold text-foreground">{data.voucher_number}</div>
                </div>
                <div className="text-right">
                  <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Total Amount
                  </div>
                  <div className="text-xl font-black text-emerald-500">
                    ₹{data.total_amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </div>
                </div>
              </div>

              {/* Seller details */}
              <div className="space-y-1 text-xs">
                <div className="text-muted-foreground font-medium">Issued by:</div>
                <div className="font-bold text-foreground">{data.seller.legal_name || data.seller.name}</div>
                <div className="text-muted-foreground font-mono">GSTIN: {data.seller.gstin || "URP"}</div>
                <div className="text-muted-foreground">Date: {data.voucher_date}</div>
              </div>

              {/* Items List */}
              <div className="border border-border/40 rounded-xl overflow-hidden text-xs">
                <div className="bg-muted/50 p-2 font-semibold text-muted-foreground flex justify-between">
                  <span>Line Items ({data.items.length})</span>
                  <span>Amount</span>
                </div>
                <div className="divide-y divide-border/20 max-h-48 overflow-y-auto">
                  {data.items.map((item, idx) => (
                    <div key={idx} className="p-2.5 flex justify-between items-center hover:bg-muted/20">
                      <div>
                        <div className="font-medium text-foreground">{item.product_name}</div>
                        <div className="text-[10px] text-muted-foreground">
                          {item.quantity} {item.unit} &bull; HSN: {item.hsn_code || "N/A"} &bull; GST {item.gst_rate}%
                        </div>
                      </div>
                      <div className="font-semibold text-foreground text-right">
                        ₹{item.total_amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Instant UPI Payment Block */}
              {data.seller?.upi_id && (
                <div className="p-3.5 bg-emerald-500/10 border border-emerald-500/20 rounded-xl space-y-2.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-600 dark:text-emerald-400">
                      <Zap className="w-4 h-4 text-emerald-500" />
                      <span>Instant UPI Payment</span>
                    </div>
                    <span className="text-[10px] font-mono text-muted-foreground">0% Gateway Fee</span>
                  </div>
                  <div className="flex flex-col sm:flex-row items-center gap-2">
                    <a
                      href={`upi://pay?pa=${encodeURIComponent(data.seller.upi_id)}&pn=${encodeURIComponent(data.seller.legal_name || data.seller.name)}&am=${data.total_amount.toFixed(2)}&cu=INR&tn=${encodeURIComponent('Invoice ' + data.voucher_number)}`}
                      className="w-full sm:flex-1 py-2 px-3 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs flex items-center justify-center gap-2 shadow-sm transition-colors text-center"
                    >
                      <span>Pay ₹{data.total_amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })} with UPI</span>
                    </a>
                    <button
                      type="button"
                      onClick={() => setShowUpiModal(!showUpiModal)}
                      className="w-full sm:w-auto px-3 py-2 border border-border/60 rounded-lg text-xs font-semibold text-muted-foreground hover:text-foreground bg-card transition-colors cursor-pointer"
                    >
                      {showUpiModal ? "Hide QR" : "Show QR"}
                    </button>
                  </div>
                  {showUpiModal && (
                    <div className="pt-2 text-center flex flex-col items-center justify-center space-y-1">
                      <div className="p-2.5 bg-white rounded-xl shadow-xs border border-border">
                        <QRCode
                          value={`upi://pay?pa=${encodeURIComponent(data.seller.upi_id)}&pn=${encodeURIComponent(data.seller.legal_name || data.seller.name)}&am=${data.total_amount.toFixed(2)}&cu=INR&tn=${encodeURIComponent('Invoice ' + data.voucher_number)}`}
                          size={130}
                        />
                      </div>
                      <span className="text-[10px] text-muted-foreground font-mono">Scan with GPay, PhonePe, Paytm, or BHIM</span>
                      <span className="text-[10px] font-mono text-foreground font-bold">UPI ID: {data.seller.upi_id}</span>
                    </div>
                  )}
                </div>
              )}

              {/* PDF Download Button */}
              <a
                href={pdfUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="w-full inline-flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl border border-border/60 bg-muted/40 hover:bg-muted text-foreground text-xs font-semibold transition-colors"
              >
                <Download className="w-4 h-4 text-primary" />
                <span>Download Official Tax Invoice PDF</span>
              </a>
            </div>

            {/* Benefit Highlights */}
            <div className="bg-primary/5 border border-primary/20 rounded-2xl p-4 space-y-2.5">
              <div className="flex items-center gap-2 text-xs font-bold text-primary">
                <Zap className="w-4 h-4" />
                <span>Why claim on Vouch?</span>
              </div>
              <ul className="text-[11px] text-muted-foreground space-y-1.5 list-disc list-inside">
                <li>Zero typing: line items and stock balances are auto-booked into your purchase register.</li>
                <li>Instant GSTR-2B matching guarantees you never lose input tax credit.</li>
                <li>Keep track of payables and supplier reconciliation in real-time.</li>
              </ul>
            </div>
          </div>

          {/* RIGHT: VIRAL ONBOARDING OR RECIPIENT ACTIONS */}
          <div className="lg:col-span-6">
            {/* 1. Loading recipient status for signed-in user */}
            {checkingRecipient ? (
              <div className="bg-card border border-border/40 rounded-2xl p-8 shadow-xl text-center space-y-3">
                <RefreshCw className="w-8 h-8 animate-spin text-primary mx-auto" />
                <p className="text-xs font-medium text-muted-foreground">Checking company books and recipient match...</p>
              </div>
            ) : recipientStatus?.authenticated && recipientStatus?.already_added ? (
              /* 2. Authenticated & Already Added into Purchase Books */
              <div className="bg-card border border-amber-500/30 rounded-2xl p-6 shadow-xl space-y-5 bg-gradient-to-b from-amber-500/5 to-transparent">
                <div className="flex items-center gap-2 text-amber-500 font-bold text-xs uppercase tracking-wider">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Invoice Already in Purchase Books</span>
                </div>

                <div>
                  <h3 className="text-lg font-black text-foreground">Purchase Voucher Recorded</h3>
                  <p className="text-xs text-muted-foreground mt-1">
                    This bill from <span className="font-semibold text-foreground">{data.seller.legal_name || data.seller.name}</span> has already been booked into your accounts. Duplicate entry is prevented.
                  </p>
                </div>

                <div className="p-4 bg-muted/40 border border-border/60 rounded-xl space-y-2.5 text-xs">
                  <div className="flex justify-between items-center">
                    <span className="text-muted-foreground">Original Invoice:</span>
                    <span className="font-mono font-bold text-foreground">#{data.voucher_number}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-muted-foreground">Recorded Voucher:</span>
                    <span className="font-mono font-bold text-emerald-500">#{recipientStatus.purchase_voucher_number || 'RECORDED'}</span>
                  </div>
                  {recipientStatus.purchase_voucher_date && (
                    <div className="flex justify-between items-center">
                      <span className="text-muted-foreground">Booking Date:</span>
                      <span className="font-mono text-foreground">{recipientStatus.purchase_voucher_date}</span>
                    </div>
                  )}
                  <div className="flex justify-between items-center pt-1.5 border-t border-border/40">
                    <span className="text-muted-foreground">Company:</span>
                    <span className="font-semibold text-foreground">{recipientStatus.active_company_name} ({recipientStatus.active_company_gstin})</span>
                  </div>
                </div>

                <div className="space-y-2 pt-2">
                  {recipientStatus.purchase_voucher_id && (
                    <Link
                      href={`/sales/${recipientStatus.purchase_voucher_id}/print`}
                      className="w-full py-2.5 px-4 rounded-xl bg-primary text-primary-foreground font-bold text-xs flex items-center justify-center gap-2 hover:bg-primary/90 transition-colors shadow-sm"
                    >
                      <FileText className="w-4 h-4" />
                      <span>View Recorded Purchase Voucher</span>
                    </Link>
                  )}
                  <Link
                    href="/network/inbox"
                    className="w-full py-2.5 px-4 rounded-xl border border-border/60 bg-muted/40 hover:bg-muted text-foreground font-bold text-xs flex items-center justify-center gap-2 transition-colors"
                  >
                    <Building2 className="w-4 h-4" />
                    <span>Open EDI Network Inbox</span>
                  </Link>
                </div>
              </div>
            ) : recipientStatus?.authenticated && recipientStatus?.is_recipient ? (
              /* 3. Authenticated & Matching Recipient (Not Yet Added -> 1-Click Accept) */
              <div className="bg-card border border-emerald-500/30 rounded-2xl p-6 shadow-xl space-y-5 bg-gradient-to-b from-emerald-500/5 to-transparent">
                <div className="flex items-center gap-2 text-emerald-500 font-bold text-xs uppercase tracking-wider">
                  <Sparkles className="w-4 h-4" />
                  <span>Verified Recipient Firm</span>
                </div>

                <div>
                  <h3 className="text-lg font-black text-foreground">Welcome back, {recipientStatus.active_company_name}!</h3>
                  <p className="text-xs text-muted-foreground mt-1">
                    You are logged in with GSTIN <span className="font-mono font-bold text-foreground">{recipientStatus.active_company_gstin}</span> matching this invoice.
                  </p>
                </div>

                <div className="p-4 bg-muted/40 border border-border/60 rounded-xl space-y-2 text-xs">
                  <div className="flex justify-between items-center">
                    <span className="text-muted-foreground">Supplier:</span>
                    <span className="font-bold text-foreground">{data.seller.legal_name || data.seller.name}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-muted-foreground">Invoice No:</span>
                    <span className="font-mono font-bold text-foreground">#{data.voucher_number}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-muted-foreground">Total Bill:</span>
                    <span className="font-mono font-bold text-emerald-500 text-sm">
                      ₹{data.total_amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => router.push(`/network/inbox?open_request=${recipientStatus.edi_request_id || ''}`)}
                  className="w-full py-3.5 px-4 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold text-xs sm:text-sm shadow-lg shadow-blue-500/25 flex items-center justify-center gap-2 transition-all cursor-pointer"
                >
                  <span>⚡ Review & Accept into Purchase Ledger</span>
                  <ArrowRight className="w-4 h-4" />
                </button>

                <p className="text-[11px] text-center text-muted-foreground">
                  Opens the EDI Inward inspection modal to review line items, tax breakdowns, and 1-click book.
                </p>
              </div>
            ) : recipientStatus?.authenticated && recipientStatus?.is_seller ? (
              /* 4. Authenticated Seller Firm */
              <div className="bg-card border border-border/60 rounded-2xl p-6 shadow-xl space-y-4">
                <div className="flex items-center gap-2 text-primary font-bold text-xs">
                  <FileText className="w-4 h-4" />
                  <span>Issuing Business View</span>
                </div>
                <h3 className="text-base font-bold text-foreground">Your Issued Sales Invoice</h3>
                <p className="text-xs text-muted-foreground">
                  You are viewing an invoice issued by your business (<span className="font-bold text-foreground">{recipientStatus.active_company_name}</span>). Counterparties open this link to download, pay via UPI, or book into their books.
                </p>
                <Link
                  href={`/sales/${data.voucher_id}/print`}
                  className="w-full py-2.5 px-4 rounded-xl bg-primary text-primary-foreground font-bold text-xs flex items-center justify-center gap-2 hover:bg-primary/90 transition-colors shadow-sm"
                >
                  <FileText className="w-4 h-4" />
                  <span>Open Full Invoice Print & Dispatch View</span>
                </Link>
              </div>
            ) : recipientStatus?.authenticated && !recipientStatus?.is_recipient ? (
              /* 5. Authenticated but GSTIN mismatch */
              <div className="bg-card border border-rose-500/30 rounded-2xl p-6 shadow-xl space-y-4 bg-gradient-to-b from-rose-500/5 to-transparent">
                <div className="flex items-center gap-2 text-rose-500 font-bold text-xs">
                  <AlertCircle className="w-4 h-4" />
                  <span>GSTIN Ownership Check</span>
                </div>
                <h3 className="text-base font-bold text-foreground">Different Company Active</h3>
                <p className="text-xs text-muted-foreground">
                  You are signed in with <span className="font-bold text-foreground">{recipientStatus.active_company_name}</span> (GSTIN: <span className="font-mono font-bold text-foreground">{recipientStatus.active_company_gstin || 'None'}</span>), but this invoice was issued to <span className="font-bold text-foreground">{data.buyer_prefill.name || 'Recipient'}</span> (GSTIN: <span className="font-mono font-bold text-foreground">{data.buyer_prefill.gstin || 'N/A'}</span>).
                </p>
                <div className="p-3 bg-muted/40 rounded-xl text-[11px] text-muted-foreground">
                  Under statutory GST rules, only the business with matching GSTIN can import this purchase bill into their accounts.
                </div>
                <div className="flex items-center gap-2 pt-2">
                  <Link
                    href="/dashboard"
                    className="flex-1 py-2 px-3 rounded-lg border border-border/60 bg-muted/30 hover:bg-muted text-center text-xs font-semibold"
                  >
                    Go to Dashboard
                  </Link>
                </div>
              </div>
            ) : (
              /* 6. Unauthenticated: Viral Onboarding Registration Form with Locked GSTIN */
              <div className="bg-card border border-border/40 rounded-2xl p-6 shadow-xl space-y-5">
                <div>
                  <h3 className="text-lg font-bold text-foreground flex items-center gap-2">
                    <Building2 className="w-5 h-5 text-primary" />
                    <span>Claim and Import This Bill</span>
                  </h3>
                  <p className="text-xs text-muted-foreground mt-1">
                    We pre-filled your company details from this invoice. Create your free password to claim.
                  </p>
                </div>

                {successMessage ? (
                  <div className="p-6 text-center space-y-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl">
                    <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto" />
                    <h4 className="font-bold text-foreground text-sm">Invoice Successfully Claimed!</h4>
                    <p className="text-xs text-muted-foreground">{successMessage}</p>
                    <p className="text-[10px] text-muted-foreground">Redirecting to your EDI Inbox...</p>
                  </div>
                ) : (
                  <form onSubmit={handleSubmit} className="space-y-4">
                    {submitError && (
                      <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-500 text-xs">
                        {submitError}
                      </div>
                    )}

                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <label className="text-xs font-semibold text-muted-foreground">
                          Company / Business GSTIN
                        </label>
                        {data.buyer_prefill.gstin && (
                          <span className="text-[10px] text-emerald-500 font-semibold flex items-center gap-1">
                            <Lock className="w-3 h-3" />
                            Statutory GSTIN (Locked to Invoice)
                          </span>
                        )}
                      </div>
                      <input
                        type="text"
                        value={gstin}
                        onChange={(e) => {
                          if (!data.buyer_prefill.gstin) {
                            setGstin(e.target.value.toUpperCase());
                          }
                        }}
                        readOnly={Boolean(data.buyer_prefill.gstin)}
                        placeholder="e.g. 07AAAAA0000A1Z5"
                        className={`w-full px-3 py-2 text-xs rounded-lg border font-mono font-bold focus:outline-none ${
                          data.buyer_prefill.gstin
                            ? "bg-muted/60 border-border text-foreground cursor-not-allowed select-none"
                            : "border-border/60 bg-muted/20 text-foreground focus:ring-1 focus:ring-primary"
                        }`}
                      />
                      {data.buyer_prefill.gstin && (
                        <p className="text-[10px] text-muted-foreground mt-1">
                          Statutory regulations require matching the recipient GSTIN specified on this tax invoice.
                        </p>
                      )}
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground mb-1">
                        Company / Trade Name
                      </label>
                      <input
                        type="text"
                        value={companyName}
                        onChange={(e) => setCompanyName(e.target.value)}
                        placeholder="e.g. Acme Enterprises"
                        required
                        className="w-full px-3 py-2 text-xs rounded-lg border border-border/60 bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground mb-1">
                        Email Address (Username)
                      </label>
                      <input
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="accounts@yourbusiness.com"
                        required
                        className="w-full px-3 py-2 text-xs rounded-lg border border-border/60 bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                      />
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-semibold text-muted-foreground mb-1">
                          Set Password
                        </label>
                        <input
                          type="password"
                          value={password}
                          onChange={(e) => setPassword(e.target.value)}
                          placeholder="••••••••"
                          required
                          className="w-full px-3 py-2 text-xs rounded-lg border border-border/60 bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-muted-foreground mb-1">
                          Confirm Password
                        </label>
                        <input
                          type="password"
                          value={confirmPassword}
                          onChange={(e) => setConfirmPassword(e.target.value)}
                          placeholder="••••••••"
                          required
                          className="w-full px-3 py-2 text-xs rounded-lg border border-border/60 bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                        />
                      </div>
                    </div>

                    <button
                      type="submit"
                      disabled={submitting}
                      className="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold text-xs sm:text-sm shadow-lg shadow-blue-500/25 flex items-center justify-center gap-2 transition-all disabled:opacity-50 cursor-pointer"
                    >
                      {submitting ? (
                        <>
                          <RefreshCw className="w-4 h-4 animate-spin" />
                          <span>Creating Account & Linking Bill...</span>
                        </>
                      ) : (
                        <>
                          <span>⚡ 1-Click Claim & Import Bill</span>
                          <ArrowRight className="w-4 h-4" />
                        </>
                      )}
                    </button>

                    <p className="text-[11px] text-center text-muted-foreground">
                      Already have a Vouch account?{" "}
                      <button
                        type="button"
                        onClick={() => router.push(`/login?redirect=/claim?token=${encodeURIComponent(token)}`)}
                        className="text-primary font-semibold hover:underline"
                      >
                        Sign In to Claim
                      </button>
                    </p>
                  </form>
                )}
              </div>
            )}
          </div>

        </div>

      </div>

      {/* Already Added Popup Notification Modal */}
      {showAlreadyAddedModal && recipientStatus && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-card border border-border w-full max-w-md rounded-2xl shadow-2xl p-6 space-y-5 animate-in zoom-in-95 duration-200">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-amber-500/10 text-amber-500 border border-amber-500/20 flex items-center justify-center shrink-0">
                <ShieldCheck className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-bold text-foreground">Purchase Invoice Already Recorded</h3>
                <p className="text-xs text-muted-foreground">Duplicate addition prevented</p>
              </div>
            </div>

            <div className="p-4 bg-muted/40 border border-border/60 rounded-xl space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Supplier Invoice:</span>
                <span className="font-mono font-bold text-foreground">#{data.voucher_number}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Supplier Firm:</span>
                <span className="font-semibold text-foreground">{data.seller.legal_name || data.seller.name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Recorded in Books as:</span>
                <span className="font-mono font-bold text-emerald-500">#{recipientStatus.purchase_voucher_number || 'RECORDED'}</span>
              </div>
              {recipientStatus.purchase_voucher_date && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Booking Date:</span>
                  <span className="font-mono text-foreground">{recipientStatus.purchase_voucher_date}</span>
                </div>
              )}
              <div className="flex justify-between pt-1 border-t border-border/40">
                <span className="text-muted-foreground">Your Company:</span>
                <span className="font-bold text-foreground">{recipientStatus.active_company_name}</span>
              </div>
            </div>

            <div className="space-y-2 pt-2">
              {recipientStatus.purchase_voucher_id && (
                <Link
                  href={`/sales/${recipientStatus.purchase_voucher_id}/print`}
                  className="w-full py-2.5 px-4 rounded-xl bg-primary text-primary-foreground font-bold text-xs flex items-center justify-center gap-2 hover:bg-primary/90 transition-colors shadow-sm"
                >
                  <FileText className="w-4 h-4" />
                  <span>View Recorded Purchase Voucher</span>
                </Link>
              )}
              <Link
                href="/network/inbox"
                className="w-full py-2.5 px-4 rounded-xl border border-border/60 bg-muted/40 hover:bg-muted text-foreground font-bold text-xs flex items-center justify-center gap-2 transition-colors"
              >
                <Building2 className="w-4 h-4" />
                <span>Open EDI Network Inbox</span>
              </Link>
              <button
                type="button"
                onClick={() => setShowAlreadyAddedModal(false)}
                className="w-full py-2 text-center text-xs text-muted-foreground hover:text-foreground font-medium cursor-pointer"
              >
                Close & View Public Invoice Copy
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ClaimInvoicePage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-background p-4">
          <RefreshCw className="w-8 h-8 animate-spin text-primary" />
        </div>
      }
    >
      <ClaimContent />
    </Suspense>
  );
}
