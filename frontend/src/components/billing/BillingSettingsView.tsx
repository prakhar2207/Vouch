"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  CreditCard,
  ShieldCheck,
  Zap,
  ArrowUpRight,
  Download,
  AlertCircle,
  CheckCircle2,
  Clock,
  Loader2,
  XCircle,
  FileText,
  RefreshCw,
} from "lucide-react";
import api, { API_BASE_URL } from "@/utils/api";
import { useCompany } from "@/context/CompanyContext";
import { getAccessToken } from "@/utils/auth";

interface SubscriptionInfo {
  id: string;
  plan: {
    id: string;
    name: string;
    tagline: string;
    description: string;
    base_amount_rupees: string;
    total_amount_rupees: string;
    billing_interval: string;
    limits: {
      ocr_fast_daily: number;
      ocr_deep_daily: number;
    };
    features: Record<string, boolean>;
  };
  status: string;
  billing_interval: string;
  current_period_start: string;
  current_period_end: string;
  next_billing_at: string | null;
  cancelled_at: string | null;
  is_currently_active: boolean;
}

interface Invoice {
  id: string;
  invoice_number: string;
  customer_name: string;
  plan_name: string;
  billing_period_start: string;
  billing_period_end: string;
  taxable_amount_rupees: string;
  cgst_amount_rupees: string;
  sgst_amount_rupees: string;
  igst_amount_rupees: string;
  total_amount_rupees: string;
  status: string;
  invoice_date: string;
  pdf_path: string;
}

interface Transaction {
  id: string;
  transaction_number: string;
  razorpay_order_id: string;
  razorpay_payment_id: string;
  amount_rupees: string;
  status: string;
  signature_verified: boolean;
  created_at: string;
}

export function BillingSettingsView() {
  const { activeCompany } = useCompany();
  const [subInfo, setSubInfo] = useState<SubscriptionInfo | null>(null);
  const [dailyUsage, setDailyUsage] = useState<{ ocr_fast_scans: number; ocr_deep_scans: number }>({
    ocr_fast_scans: 0,
    ocr_deep_scans: 0,
  });
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [cancelling, setCancelling] = useState(false);
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const fetchData = async () => {
    if (!activeCompany?.id) return;
    setLoading(true);
    setFeedback(null);
    try {
      const [subRes, invRes, txnRes] = await Promise.all([
        api.get(`/api/v1/billing/subscription/?company_id=${activeCompany.id}`),
        api.get(`/api/v1/billing/invoices/?company_id=${activeCompany.id}`),
        api.get(`/api/v1/billing/payments/?company_id=${activeCompany.id}`),
      ]);

      if (subRes.data?.subscription) {
        setSubInfo(subRes.data.subscription);
      } else {
        setSubInfo(null);
      }

      if (subRes.data?.daily_usage) {
        setDailyUsage(subRes.data.daily_usage);
      }

      if (invRes.data?.invoices) {
        setInvoices(invRes.data.invoices);
      }

      if (txnRes.data?.transactions) {
        setTransactions(txnRes.data.transactions);
      }
    } catch (err: any) {
      console.warn("Failed to load billing details:", err);
      setFeedback({
        type: "error",
        message: err.response?.data?.error || "Could not load subscription details.",
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [activeCompany?.id]);

  const handleCancelSubscription = async () => {
    if (!activeCompany?.id) return;
    setCancelling(true);
    try {
      const res = await api.post("/api/v1/billing/subscription/cancel/", {
        company_id: activeCompany.id,
        reason: cancelReason || "Customer cancelled from settings dashboard",
      });

      if (res.data?.success) {
        setFeedback({
          type: "success",
          message: "Subscription cancelled. Access remains active until the end of your billing cycle.",
        });
        setShowCancelModal(false);
        fetchData();
      }
    } catch (err: any) {
      setFeedback({
        type: "error",
        message: err.response?.data?.error || "Failed to cancel subscription.",
      });
    } finally {
      setCancelling(false);
    }
  };

  const handleDownloadInvoice = async (invoiceId: string, invoiceNumber: string) => {
    if (!activeCompany?.id) return;
    try {
      const token = getAccessToken();
      const res = await fetch(
        `${API_BASE_URL}/api/v1/billing/invoices/${invoiceId}/download/?company_id=${activeCompany.id}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
            "X-Company-ID": activeCompany.id,
          },
        }
      );

      if (!res.ok) {
        throw new Error("Failed to download invoice PDF");
      }

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${invoiceNumber}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: any) {
      alert("Could not download invoice PDF: " + (err.message || "Unknown error"));
    }
  };

  if (!activeCompany) {
    return (
      <div className="p-8 text-center text-muted-foreground text-sm">
        Please select an active company workspace to view billing details.
      </div>
    );
  }

  if (loading) {
    return (
      <div className="p-12 flex flex-col items-center justify-center gap-3 text-muted-foreground text-xs">
        <Loader2 className="w-6 h-6 animate-spin text-primary" />
        <span>Loading subscription &amp; billing data...</span>
      </div>
    );
  }

  const fastDailyLimit = subInfo?.plan?.limits?.ocr_fast_daily ?? 2;
  const deepDailyLimit = subInfo?.plan?.limits?.ocr_deep_daily ?? 0;
  const fastScansPercent = Math.min(100, Math.round((dailyUsage.ocr_fast_scans / (fastDailyLimit || 1)) * 100));
  const deepScansPercent = Math.min(100, Math.round((dailyUsage.ocr_deep_scans / (deepDailyLimit || 1)) * 100));

  return (
    <div className="space-y-8 max-w-5xl">
      {/* Feedback Alert */}
      {feedback && (
        <div
          className={`p-4 rounded-xl text-xs flex items-center justify-between gap-3 ${
            feedback.type === "success"
              ? "bg-emerald-50 dark:bg-emerald-950/50 border border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-300"
              : "bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-900 text-red-800 dark:text-red-300"
          }`}
        >
          <div className="flex items-center gap-2">
            {feedback.type === "success" ? (
              <CheckCircle2 className="w-4 h-4 shrink-0" />
            ) : (
              <AlertCircle className="w-4 h-4 shrink-0" />
            )}
            <span>{feedback.message}</span>
          </div>
          <button
            onClick={() => setFeedback(null)}
            className="text-muted-foreground hover:text-foreground text-xs font-bold"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* 1. Subscription Overview Card */}
      <div className="rounded-2xl border border-border bg-card p-6 shadow-xs space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-6">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold text-foreground">
                {subInfo ? subInfo.plan.name : "Free Starter Access"}
              </h2>
              <span
                className={`text-[11px] font-bold px-2.5 py-0.5 rounded-full ${
                  subInfo?.status === "active"
                    ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20"
                    : subInfo?.status === "cancelled"
                    ? "bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/20"
                    : "bg-slate-500/10 text-slate-700 dark:text-slate-400 border border-slate-500/20"
                }`}
              >
                {subInfo?.status ? subInfo.status.toUpperCase() : "FREE TIER"}
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              {subInfo
                ? `${subInfo.plan.tagline} • Annual billing interval`
                : "Basic accounting & invoicing enabled for MSMEs"}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Link
              href="/pricing"
              className="px-4 py-2 bg-[#162C5B] hover:bg-[#0F1E3D] dark:bg-[#E28123] dark:hover:bg-[#c86815] text-white rounded-xl text-xs font-bold transition-all shadow-xs inline-flex items-center gap-1.5"
            >
              <span>{subInfo ? "Upgrade / Change Plan" : "Upgrade to Pro"}</span>
              <ArrowUpRight className="w-3.5 h-3.5" />
            </Link>

            {subInfo && subInfo.status === "active" && (
              <button
                onClick={() => setShowCancelModal(true)}
                className="px-3 py-2 bg-card hover:bg-muted border border-border rounded-xl text-xs font-semibold text-rose-600 dark:text-rose-400 transition-colors"
              >
                Cancel Subscription
              </button>
            )}
          </div>
        </div>

        {/* Subscription Meta Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
          <div className="p-3 bg-muted/30 rounded-xl border border-border/60">
            <span className="text-muted-foreground block text-[11px]">Current Plan Amount</span>
            <span className="text-sm font-bold text-foreground mt-0.5 block">
              {subInfo ? `₹${subInfo.plan.total_amount_rupees}` : "₹0.00"}
            </span>
          </div>

          <div className="p-3 bg-muted/30 rounded-xl border border-border/60">
            <span className="text-muted-foreground block text-[11px]">Billing Cycle</span>
            <span className="text-sm font-bold text-foreground mt-0.5 block capitalize">
              {subInfo ? subInfo.billing_interval : "Free"}
            </span>
          </div>

          <div className="p-3 bg-muted/30 rounded-xl border border-border/60">
            <span className="text-muted-foreground block text-[11px]">Current Period End</span>
            <span className="text-sm font-bold text-foreground mt-0.5 block">
              {subInfo?.current_period_end
                ? new Date(subInfo.current_period_end).toLocaleDateString("en-IN")
                : "Lifetime Basic"}
            </span>
          </div>

          <div className="p-3 bg-muted/30 rounded-xl border border-border/60">
            <span className="text-muted-foreground block text-[11px]">Payment Gateway</span>
            <span className="text-sm font-bold text-foreground mt-0.5 block">
              Razorpay Secured
            </span>
          </div>
        </div>
      </div>

      {/* 2. Daily Usage & Operational Quotas */}
      <div className="rounded-2xl border border-border bg-card p-6 shadow-xs space-y-4">
        <div className="space-y-1">
          <h3 className="text-base font-bold text-foreground flex items-center gap-2">
            <Zap className="w-4 h-4 text-amber-500" />
            <span>Today&apos;s AI OCR Automation Usage</span>
          </h3>
          <p className="text-xs text-muted-foreground">
            Daily scan limits reset every night at 00:00 IST. Core double-entry accounting is never rate-limited.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
          {/* Fast Model */}
          <div className="p-4 rounded-xl border border-border bg-muted/20 space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-foreground">Printed Bill &amp; Bank OCR (Fast Model)</span>
              <span className="text-muted-foreground font-mono">
                {dailyUsage.ocr_fast_scans} / {fastDailyLimit} scans
              </span>
            </div>
            <div className="w-full h-2 rounded-full bg-border overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${
                  fastScansPercent >= 100 ? "bg-red-500" : fastScansPercent >= 80 ? "bg-amber-500" : "bg-emerald-500"
                }`}
                style={{ width: `${fastScansPercent}%` }}
              />
            </div>
          </div>

          {/* Deep Model */}
          <div className="p-4 rounded-xl border border-border bg-muted/20 space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-foreground">Handwritten Bill OCR (Deep Model)</span>
              <span className="text-muted-foreground font-mono">
                {dailyUsage.ocr_deep_scans} / {deepDailyLimit} scans
              </span>
            </div>
            <div className="w-full h-2 rounded-full bg-border overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${
                  deepScansPercent >= 100 ? "bg-red-500" : deepScansPercent >= 80 ? "bg-amber-500" : "bg-emerald-500"
                }`}
                style={{ width: `${deepScansPercent}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* 3. Billing Invoices & Receipts Table */}
      <div className="rounded-2xl border border-border bg-card shadow-xs overflow-hidden">
        <div className="p-6 border-b border-border flex items-center justify-between">
          <div className="space-y-1">
            <h3 className="text-base font-bold text-foreground flex items-center gap-2">
              <FileText className="w-4 h-4 text-blue-600" />
              <span>Tax Invoices &amp; Receipts</span>
            </h3>
            <p className="text-xs text-muted-foreground">
              Official computer-generated tax invoices for subscription purchases.
            </p>
          </div>
          <button
            onClick={fetchData}
            className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            title="Refresh Invoices"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        {invoices.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground text-xs">
            No subscription invoices have been generated for this company yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-muted/40 text-muted-foreground border-b border-border">
                <tr>
                  <th className="py-3 px-4 font-semibold">Invoice No</th>
                  <th className="py-3 px-4 font-semibold">Date</th>
                  <th className="py-3 px-4 font-semibold">Plan Description</th>
                  <th className="py-3 px-4 font-semibold text-right">Taxable</th>
                  <th className="py-3 px-4 font-semibold text-right">Total (INR)</th>
                  <th className="py-3 px-4 font-semibold text-center">Status</th>
                  <th className="py-3 px-4 font-semibold text-center">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {invoices.map((inv) => (
                  <tr key={inv.id} className="hover:bg-muted/20">
                    <td className="py-3 px-4 font-mono font-bold text-foreground">
                      {inv.invoice_number}
                    </td>
                    <td className="py-3 px-4 text-muted-foreground">
                      {new Date(inv.invoice_date).toLocaleDateString("en-IN")}
                    </td>
                    <td className="py-3 px-4 text-foreground font-medium">
                      {inv.plan_name}
                    </td>
                    <td className="py-3 px-4 text-right text-muted-foreground font-mono">
                      ₹{inv.taxable_amount_rupees}
                    </td>
                    <td className="py-3 px-4 text-right font-bold text-foreground font-mono">
                      ₹{inv.total_amount_rupees}
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-700 dark:text-emerald-400">
                        PAID
                      </span>
                    </td>
                    <td className="py-3 px-4 text-center">
                      <button
                        onClick={() => handleDownloadInvoice(inv.id, inv.invoice_number)}
                        className="p-1.5 rounded-lg hover:bg-muted text-primary inline-flex items-center gap-1 text-xs font-semibold"
                        title="Download PDF"
                      >
                        <Download className="w-3.5 h-3.5" />
                        <span>PDF</span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 4. Payment Transactions Log */}
      <div className="rounded-2xl border border-border bg-card shadow-xs overflow-hidden">
        <div className="p-6 border-b border-border">
          <h3 className="text-base font-bold text-foreground flex items-center gap-2">
            <CreditCard className="w-4 h-4 text-emerald-600" />
            <span>Razorpay Transaction Log</span>
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            Authoritative transaction history recorded from Razorpay gateway.
          </p>
        </div>

        {transactions.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground text-xs">
            No payment transactions recorded for this workspace.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-muted/40 text-muted-foreground border-b border-border">
                <tr>
                  <th className="py-3 px-4 font-semibold">Transaction ID</th>
                  <th className="py-3 px-4 font-semibold">Payment ID</th>
                  <th className="py-3 px-4 font-semibold">Date</th>
                  <th className="py-3 px-4 font-semibold text-right">Amount</th>
                  <th className="py-3 px-4 font-semibold text-center">Verified</th>
                  <th className="py-3 px-4 font-semibold text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {transactions.map((txn) => (
                  <tr key={txn.id} className="hover:bg-muted/20">
                    <td className="py-3 px-4 font-mono text-foreground font-semibold">
                      {txn.transaction_number}
                    </td>
                    <td className="py-3 px-4 font-mono text-muted-foreground">
                      {txn.razorpay_payment_id || "Pending"}
                    </td>
                    <td className="py-3 px-4 text-muted-foreground">
                      {new Date(txn.created_at).toLocaleDateString("en-IN")}
                    </td>
                    <td className="py-3 px-4 text-right font-bold text-foreground font-mono">
                      ₹{txn.amount_rupees}
                    </td>
                    <td className="py-3 px-4 text-center">
                      {txn.signature_verified ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-600 inline-block" />
                      ) : (
                        <Clock className="w-4 h-4 text-amber-500 inline-block" />
                      )}
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                          txn.status === "captured"
                            ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                            : txn.status === "failed"
                            ? "bg-red-500/10 text-red-700 dark:text-red-400"
                            : "bg-slate-500/10 text-slate-700 dark:text-slate-400"
                        }`}
                      >
                        {txn.status.toUpperCase()}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Cancellation Confirmation Modal */}
      {showCancelModal && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <h4 className="text-base font-bold text-foreground">Cancel Subscription</h4>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Are you sure you want to cancel your subscription? Your access to plan features will
              remain active until{" "}
              <strong>
                {subInfo?.current_period_end
                  ? new Date(subInfo.current_period_end).toLocaleDateString("en-IN")
                  : "the end of your billing cycle"}
              </strong>
              . Your historical financial records will remain completely intact.
            </p>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-foreground">Reason for cancellation (optional):</label>
              <textarea
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder="Let us know how we can improve SriLekh..."
                className="w-full text-xs p-2.5 rounded-xl border border-border bg-muted/20 outline-none focus:ring-1 focus:ring-primary min-h-[70px]"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => setShowCancelModal(false)}
                disabled={cancelling}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-muted-foreground hover:bg-muted"
              >
                Keep Subscription
              </button>
              <button
                onClick={handleCancelSubscription}
                disabled={cancelling}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-bold flex items-center gap-1.5"
              >
                {cancelling ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                <span>Confirm Cancellation</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
