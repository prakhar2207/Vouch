"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import DashboardLayout from "@/components/DashboardLayout";
import { api } from "@/utils/api";
import { isAuthenticated } from "@/utils/auth";
import { useToast } from "@/context/ToastContext";
import { useCompany } from "@/context/CompanyContext";
import {
  CreditCard,
  CheckCircle2,
  Clock,
  AlertTriangle,
  ArrowLeft,
  ArrowUpRight,
  ArrowDownLeft,
  ShieldCheck,
  RefreshCw,
  ExternalLink,
  FileText,
  Building,
  Check,
  Copy
} from "lucide-react";

export default function PaymentDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { toast } = useToast();
  const { companyId: activeCompanyId } = useCompany();

  const [payment, setPayment] = useState<any | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [verifying, setVerifying] = useState<boolean>(false);
  const [utrInput, setUtrInput] = useState<string>("");
  const [confirmingUtr, setConfirmingUtr] = useState<boolean>(false);

  const paymentId = params?.id as string;

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }
    const cid = activeCompanyId || (typeof window !== "undefined" ? localStorage.getItem("vouch_active_company_id") : "");
    if (cid && paymentId) {
      fetchPaymentDetail(cid, paymentId);
    }
  }, [activeCompanyId, paymentId, router]);

  const fetchPaymentDetail = async (cid: string, id: string) => {
    setLoading(true);
    try {
      const res = await api.get(`/api/v1/payments/requests/${id}/?company_id=${cid}`, {
        headers: { "X-Company-ID": cid }
      });
      setPayment(res.data);
      if (res.data.utr) setUtrInput(res.data.utr);
    } catch (err: any) {
      console.error(err);
      toast.error("Could not load payment", err.message || "Network error");
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyStatus = async () => {
    if (!payment) return;
    setVerifying(true);
    try {
      const res = await api.post(
        `/api/v1/payments/requests/${payment.id}/verify/?company_id=${activeCompanyId}`,
        {},
        { headers: { "X-Company-ID": activeCompanyId } }
      );
      setPayment(res.data);
      toast.success("Status Updated", res.data.message || "Payment status synchronized.");
    } catch (err: any) {
      toast.error("Verification failed", err.response?.data?.error || err.message);
    } finally {
      setVerifying(false);
    }
  };

  const handleConfirmUtr = async () => {
    if (!utrInput.trim() || !payment) {
      toast.error("UTR Required", "Please enter the bank UTR reference number.");
      return;
    }
    setConfirmingUtr(true);
    try {
      const res = await api.post(
        `/api/v1/payments/requests/${payment.id}/confirm/?company_id=${activeCompanyId}`,
        { utr: utrInput.trim() },
        { headers: { "X-Company-ID": activeCompanyId } }
      );
      setPayment(res.data);
      toast.success("Payment Confirmed", "Double-entry accounting voucher posted.");
    } catch (err: any) {
      toast.error("Failed to confirm", err.response?.data?.error || err.message);
    } finally {
      setConfirmingUtr(false);
    }
  };

  const formatAmount = (val: any) => {
    const num = parseFloat(String(val || "0").replace(/,/g, ""));
    return `₹${num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return "--";
    try {
      return new Date(dateStr).toLocaleDateString("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit"
      });
    } catch {
      return dateStr;
    }
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex flex-col items-center justify-center p-20 space-y-2">
          <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
          <p className="text-xs text-muted-foreground">Loading payment details...</p>
        </div>
      </DashboardLayout>
    );
  }

  if (!payment) {
    return (
      <DashboardLayout>
        <div className="max-w-xl mx-auto p-12 text-center space-y-3">
          <AlertTriangle className="w-8 h-8 text-amber-500 mx-auto" />
          <h2 className="text-sm font-bold text-foreground">Payment record not found</h2>
          <Link href="/pay" className="inline-block text-xs font-semibold text-primary hover:underline">
            Return to SriLekh Pay
          </Link>
        </div>
      </DashboardLayout>
    );
  }

  const isSuccess = payment.status === "SUCCESS";
  const isPayer = payment.company === activeCompanyId;

  return (
    <DashboardLayout>
      <div className="space-y-6 pb-12 max-w-4xl mx-auto">
        
        {/* Navigation & Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 border-b border-border/40 pb-4">
          <div className="flex items-center gap-3">
            <Link
              href="/pay"
              className="p-2 rounded-xl border border-border/60 bg-card hover:bg-muted text-foreground transition-colors cursor-pointer"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs font-bold px-2 py-0.5 rounded bg-muted text-muted-foreground">
                  {payment.srilekh_pay_id}
                </span>
                <span
                  className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                    isSuccess
                      ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                      : "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                  }`}
                >
                  {payment.status}
                </span>
              </div>
              <h1 className="text-2xl font-black tracking-tight text-foreground mt-0.5">
                {formatAmount(payment.amount)}
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {!isSuccess && (
              <button
                onClick={handleVerifyStatus}
                disabled={verifying}
                className="px-3.5 py-1.5 rounded-xl border border-border/60 bg-card hover:bg-muted text-foreground text-xs font-semibold flex items-center gap-2 cursor-pointer shadow-2xs disabled:opacity-50 min-h-[36px]"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${verifying ? "animate-spin" : ""}`} />
                <span>Verify with Bank</span>
              </button>
            )}

            <Link
              href="/pay/new"
              className="px-3.5 py-1.5 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-bold flex items-center gap-2 cursor-pointer shadow-sm min-h-[36px]"
            >
              <span>Make Another Payment</span>
            </Link>
          </div>
        </div>

        {/* 5-Stage Traceable Timeline */}
        <div className="bg-card border border-border/50 rounded-2xl p-6 shadow-2xs space-y-6">
          <h2 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
            Transaction & Accounting Audit Trail
          </h2>

          <div className="relative border-l-2 border-border/60 ml-4 space-y-6 pl-6">
            
            {/* Step 1: Initiated */}
            <div className="relative">
              <span className="absolute -left-[33px] top-0.5 w-4 h-4 rounded-full bg-emerald-500 text-white flex items-center justify-center text-[10px]">
                <Check className="w-2.5 h-2.5" />
              </span>
              <div>
                <h3 className="text-xs font-bold text-foreground">1. Payment Initiated</h3>
                <p className="text-[11px] text-muted-foreground">
                  Created by {payment.company_name} for recipient {payment.recipient_name} via {payment.payment_method}.
                </p>
                <span className="text-[10px] text-muted-foreground/80 font-mono">
                  {formatDate(payment.initiated_at)}
                </span>
              </div>
            </div>

            {/* Step 2: Provider Dispatched */}
            <div className="relative">
              <span className="absolute -left-[33px] top-0.5 w-4 h-4 rounded-full bg-emerald-500 text-white flex items-center justify-center text-[10px]">
                <Check className="w-2.5 h-2.5" />
              </span>
              <div>
                <h3 className="text-xs font-bold text-foreground">2. Dispatched to {payment.provider}</h3>
                <p className="text-[11px] text-muted-foreground font-mono">
                  Reference: {payment.provider_reference || "N/A"}
                </p>
              </div>
            </div>

            {/* Step 3: Bank Confirmation & UTR */}
            <div className="relative">
              <span
                className={`absolute -left-[33px] top-0.5 w-4 h-4 rounded-full flex items-center justify-center text-[10px] ${
                  payment.utr ? "bg-emerald-500 text-white" : "bg-amber-500 text-white"
                }`}
              >
                {payment.utr ? <Check className="w-2.5 h-2.5" /> : <Clock className="w-2.5 h-2.5" />}
              </span>
              <div>
                <h3 className="text-xs font-bold text-foreground">3. Bank Confirmation & UTR</h3>
                {payment.utr ? (
                  <p className="text-[11px] text-emerald-600 dark:text-emerald-400 font-mono font-bold">
                    UTR / RRN: {payment.utr} (Confirmed {formatDate(payment.confirmed_at)})
                  </p>
                ) : (
                  <div className="space-y-2 pt-1">
                    <p className="text-[11px] text-muted-foreground">
                      Awaiting confirmation from bank partner webhook or manual UTR entry.
                    </p>
                    <div className="flex gap-2 max-w-sm">
                      <input
                        type="text"
                        value={utrInput}
                        onChange={(e) => setUtrInput(e.target.value)}
                        placeholder="Enter 12-digit UTR"
                        className="flex-1 bg-muted/20 border border-border/60 rounded-xl px-3 py-1.5 text-xs font-mono font-bold text-foreground"
                      />
                      <button
                        onClick={handleConfirmUtr}
                        disabled={confirmingUtr}
                        className="px-3 py-1.5 rounded-xl bg-primary text-primary-foreground text-xs font-bold cursor-pointer disabled:opacity-50"
                      >
                        {confirmingUtr ? "Posting..." : "Confirm"}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Step 4: Double-Entry Vouchers Posted */}
            <div className="relative">
              <span
                className={`absolute -left-[33px] top-0.5 w-4 h-4 rounded-full flex items-center justify-center text-[10px] ${
                  payment.payer_voucher_number ? "bg-emerald-500 text-white" : "bg-muted text-muted-foreground"
                }`}
              >
                {payment.payer_voucher_number ? <Check className="w-2.5 h-2.5" /> : <Clock className="w-2.5 h-2.5" />}
              </span>
              <div className="space-y-1.5">
                <h3 className="text-xs font-bold text-foreground">4. Double-Entry Vouchers Posted</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                  
                  {/* Payer Voucher */}
                  <div className="p-3 bg-muted/20 border border-border/40 rounded-xl space-y-1">
                    <span className="text-[10px] uppercase font-bold text-rose-600 dark:text-rose-400">
                      Payer Books (Outflow)
                    </span>
                    <div className="text-xs font-bold font-mono text-foreground flex items-center gap-1.5">
                      <FileText className="w-3.5 h-3.5 text-primary" />
                      <span>{payment.payer_voucher_number ? `Payment #${payment.payer_voucher_number}` : "Pending"}</span>
                    </div>
                    <p className="text-[10px] text-muted-foreground">
                      Dr {payment.payer_party_name || "Supplier"}, Cr Bank / SriLekh Pay Clearing
                    </p>
                  </div>

                  {/* Recipient Voucher */}
                  <div className="p-3 bg-muted/20 border border-border/40 rounded-xl space-y-1">
                    <span className="text-[10px] uppercase font-bold text-emerald-600 dark:text-emerald-400">
                      Recipient Books (Inflow)
                    </span>
                    <div className="text-xs font-bold font-mono text-foreground flex items-center gap-1.5">
                      <FileText className="w-3.5 h-3.5 text-primary" />
                      <span>{payment.recipient_voucher_number ? `Receipt #${payment.recipient_voucher_number}` : (payment.recipient_company ? "Pending Match" : "External Business")}</span>
                    </div>
                    <p className="text-[10px] text-muted-foreground">
                      {payment.recipient_company ? "Dr Bank / Clearing, Cr Customer Receivable" : "External Recipient (Off-Platform)"}
                    </p>
                  </div>

                </div>
              </div>
            </div>

            {/* Step 5: FIFO Allocation */}
            <div className="relative">
              <span className="absolute -left-[33px] top-0.5 w-4 h-4 rounded-full bg-emerald-500 text-white flex items-center justify-center text-[10px]">
                <Check className="w-2.5 h-2.5" />
              </span>
              <div>
                <h3 className="text-xs font-bold text-foreground">5. Invoice Allocation Status</h3>
                <p className="text-[11px] text-muted-foreground">
                  {payment.invoice_number ? (
                    <span>Allocated against Bill <strong className="text-foreground">#{payment.invoice_number}</strong></span>
                  ) : (
                    <span>FIFO Auto-allocation applied to outstanding balances</span>
                  )}
                </p>
              </div>
            </div>

          </div>
        </div>

      </div>
    </DashboardLayout>
  );
}
