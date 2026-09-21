"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import axios from "axios";
import { setTokens } from "@/utils/auth";
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
} from "lucide-react";

interface InvoicePreviewData {
  voucher_id: string;
  voucher_number: string;
  voucher_date: string;
  total_amount: number;
  seller: {
    id: string;
    name: string;
    legal_name: string;
    gstin: string;
    state_code: string;
    city: string;
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

function ClaimContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = searchParams.get("token") || searchParams.get("id") || "";

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<InvoicePreviewData | null>(null);

  // Form state
  const [companyName, setCompanyName] = useState("");
  const [gstin, setGstin] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

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
      } catch (err: any) {
        setError(err.response?.data?.error || "Invalid or expired invoice link.");
      } finally {
        setLoading(false);
      }
    };

    fetchPreview();
  }, [token]);

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

          {/* RIGHT: VIRAL ONBOARDING FORM */}
          <div className="lg:col-span-6">
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
                    <label className="block text-xs font-semibold text-muted-foreground mb-1">
                      Company / Business GSTIN
                    </label>
                    <input
                      type="text"
                      value={gstin}
                      onChange={(e) => setGstin(e.target.value.toUpperCase())}
                      placeholder="e.g. 07AAAAA0000A1Z5"
                      className="w-full px-3 py-2 text-xs rounded-lg border border-border/60 bg-muted/20 font-mono font-bold focus:outline-none focus:ring-1 focus:ring-primary"
                    />
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
          </div>

        </div>

      </div>
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
