"use client";

import React, { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import DashboardLayout from "@/components/DashboardLayout";
import { api } from "@/utils/api";
import { isAuthenticated } from "@/utils/auth";
import { useToast } from "@/context/ToastContext";
import { useCompany } from "@/context/CompanyContext";
import {
  CreditCard,
  QrCode,
  ArrowRight,
  ArrowLeft,
  Building,
  CheckCircle2,
  Copy,
  ExternalLink,
  RefreshCw,
  ShieldCheck,
  AlertCircle
} from "lucide-react";

function NewPaymentContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { toast } = useToast();
  const { companyId: activeCompanyId } = useCompany();

  const [companyId, setCompanyId] = useState<string>(activeCompanyId || "");
  const [amount, setAmount] = useState<string>("");
  const [paymentMethod, setPaymentMethod] = useState<string>("UPI");
  const [recipientName, setRecipientName] = useState<string>("");
  const [recipientVpa, setRecipientVpa] = useState<string>("");
  const [recipientAccount, setRecipientAccount] = useState<string>("");
  const [recipientIfsc, setRecipientIfsc] = useState<string>("");
  const [payerPartyId, setPayerPartyId] = useState<string>("");
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<string>("");
  const [notes, setNotes] = useState<string>("");

  const [parties, setParties] = useState<any[]>([]);
  const [invoices, setInvoices] = useState<any[]>([]);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [createdPayment, setCreatedPayment] = useState<any | null>(null);

  // Manual UTR Confirmation State
  const [utrInput, setUtrInput] = useState<string>("");
  const [confirmingUtr, setConfirmingUtr] = useState<boolean>(false);

  // Query Param Prefill
  useEffect(() => {
    const qInvoiceId = searchParams.get("invoice_id");
    const qPartyId = searchParams.get("party_id");
    const qAmount = searchParams.get("amount");
    const qPartyName = searchParams.get("party_name");

    if (qInvoiceId) setSelectedInvoiceId(qInvoiceId);
    if (qPartyId) setPayerPartyId(qPartyId);
    if (qAmount && !isNaN(parseFloat(qAmount))) setAmount(qAmount);
    if (qPartyName) setRecipientName(qPartyName);
  }, [searchParams]);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }
    const cid = activeCompanyId || (typeof window !== "undefined" ? localStorage.getItem("vouch_active_company_id") : "");
    if (cid) {
      setCompanyId(cid);
      loadPartiesAndInvoices(cid);
    }
  }, [activeCompanyId, router]);

  const loadPartiesAndInvoices = async (cid: string) => {
    try {
      const [partiesRes, invRes] = await Promise.all([
        api.get(`/api/v1/ledgers/?company_id=${cid}&ledger_type=SUPPLIER`, { headers: { "X-Company-ID": cid } }),
        api.get(`/api/v1/vouchers/?company_id=${cid}&voucher_type=PURCHASE&status=POSTED`, { headers: { "X-Company-ID": cid } })
      ]);
      setParties(Array.isArray(partiesRes.data) ? partiesRes.data : (partiesRes.data?.results || []));
      setInvoices(Array.isArray(invRes.data) ? invRes.data : (invRes.data?.results || []));
    } catch (err) {
      console.error(err);
    }
  };

  const handlePartySelect = (partyId: string) => {
    setPayerPartyId(partyId);
    const p = parties.find((item) => String(item.id) === String(partyId));
    if (p) {
      setRecipientName(p.name);
      if (p.metadata?.vpa || p.upi_id) setRecipientVpa(p.metadata?.vpa || p.upi_id);
      if (p.bank_account_number) setRecipientAccount(p.bank_account_number);
      if (p.ifsc_code) setRecipientIfsc(p.ifsc_code);
    }
  };

  const handleInvoiceSelect = (invId: string) => {
    setSelectedInvoiceId(invId);
    const inv = invoices.find((item) => String(item.id) === String(invId));
    if (inv) {
      setAmount(String(inv.total_amount));
      if (inv.party_ledger) {
        handlePartySelect(inv.party_ledger.id || inv.party_ledger);
      }
    }
  };

  const handleInitiate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!amount || parseFloat(amount) <= 0) {
      toast.error("Invalid amount", "Payment amount must be greater than zero.");
      return;
    }
    if (!recipientName.trim()) {
      toast.error("Recipient required", "Please enter or select a recipient name.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await api.post(
        `/api/v1/payments/requests/?company_id=${companyId}`,
        {
          amount: parseFloat(amount),
          payment_method: paymentMethod,
          payer_party_id: payerPartyId || null,
          recipient_name: recipientName,
          recipient_vpa: recipientVpa || null,
          recipient_account_number: recipientAccount || null,
          recipient_ifsc: recipientIfsc || null,
          invoice_id: selectedInvoiceId || null,
          notes: notes,
          idempotency_key: `IDEM-${Date.now()}`
        },
        { headers: { "X-Company-ID": companyId } }
      );

      setCreatedPayment(res.data);
      toast.success("Payment Initiated", `Reference ${res.data.srilekh_pay_id} generated.`);
    } catch (err: any) {
      console.error(err);
      toast.error("Payment initiation failed", err.response?.data?.error || err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleConfirmUtr = async () => {
    if (!utrInput.trim() || !createdPayment) {
      toast.error("UTR Required", "Please enter the bank UTR or transaction reference number.");
      return;
    }
    setConfirmingUtr(true);
    try {
      const res = await api.post(
        `/api/v1/payments/requests/${createdPayment.id}/confirm/?company_id=${companyId}`,
        { utr: utrInput.trim() },
        { headers: { "X-Company-ID": companyId } }
      );
      toast.success("Payment Confirmed!", "Double-entry accounting voucher posted.");
      router.push(`/pay/${createdPayment.id}`);
    } catch (err: any) {
      toast.error("Confirmation error", err.response?.data?.error || err.message);
    } finally {
      setConfirmingUtr(false);
    }
  };

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast.success("Copied", `${label} copied to clipboard.`);
  };

  return (
    <DashboardLayout>
      <div className="space-y-6 pb-12 max-w-3xl mx-auto">
        
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border/40 pb-4">
          <div className="flex items-center gap-3">
            <Link
              href="/pay"
              className="p-2 rounded-xl border border-border/60 bg-card hover:bg-muted text-foreground transition-colors cursor-pointer"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-foreground">
                Make Payment
              </h1>
              <p className="text-xs text-muted-foreground">
                Pay suppliers via UPI, NEFT, RTGS or IMPS with automatic voucher posting
              </p>
            </div>
          </div>
        </div>

        {!createdPayment ? (
          /* Payment Setup Form */
          <form onSubmit={handleInitiate} className="bg-card border border-border/50 rounded-2xl p-6 shadow-2xs space-y-5">
            
            {/* Amount */}
            <div>
              <label className="block text-xs font-semibold text-foreground mb-1.5">
                Amount to Pay (INR) *
              </label>
              <div className="relative">
                <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-base font-bold text-muted-foreground">
                  ₹
                </span>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  required
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  placeholder="0.00"
                  className="w-full bg-muted/20 border border-border/60 rounded-xl pl-8 pr-4 py-2.5 text-lg font-bold font-mono text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>
            </div>

            {/* Payment Method Selector */}
            <div>
              <label className="block text-xs font-semibold text-foreground mb-1.5">
                Payment Method *
              </label>
              <div className="grid grid-cols-3 gap-2.5">
                <button
                  type="button"
                  onClick={() => setPaymentMethod("UPI")}
                  className={`p-3 rounded-xl border text-center transition-all cursor-pointer ${
                    paymentMethod === "UPI"
                      ? "border-primary bg-primary/10 text-primary font-bold shadow-xs ring-1 ring-primary/30"
                      : "border-border/60 bg-muted/20 text-muted-foreground hover:bg-muted/40 font-medium"
                  }`}
                >
                  <QrCode className="w-4 h-4 mx-auto mb-1 text-primary" />
                  <div className="text-xs">UPI (Instant)</div>
                  <div className="text-[10px] text-muted-foreground">Dynamic QR & App Link</div>
                </button>

                <button
                  type="button"
                  onClick={() => setPaymentMethod("NEFT")}
                  className={`p-3 rounded-xl border text-center transition-all cursor-pointer ${
                    paymentMethod === "NEFT"
                      ? "border-primary bg-primary/10 text-primary font-bold shadow-xs ring-1 ring-primary/30"
                      : "border-border/60 bg-muted/20 text-muted-foreground hover:bg-muted/40 font-medium"
                  }`}
                >
                  <Building className="w-4 h-4 mx-auto mb-1 text-primary" />
                  <div className="text-xs">NEFT / RTGS</div>
                  <div className="text-[10px] text-muted-foreground">Virtual Account</div>
                </button>

                <button
                  type="button"
                  onClick={() => setPaymentMethod("IMPS")}
                  className={`p-3 rounded-xl border text-center transition-all cursor-pointer ${
                    paymentMethod === "IMPS"
                      ? "border-primary bg-primary/10 text-primary font-bold shadow-xs ring-1 ring-primary/30"
                      : "border-border/60 bg-muted/20 text-muted-foreground hover:bg-muted/40 font-medium"
                  }`}
                >
                  <CreditCard className="w-4 h-4 mx-auto mb-1 text-primary" />
                  <div className="text-xs">IMPS Transfer</div>
                  <div className="text-[10px] text-muted-foreground">24x7 Direct Bank</div>
                </button>
              </div>
            </div>

            {/* Quick Bill / Invoice Selector */}
            {invoices.length > 0 && (
              <div>
                <label className="block text-xs font-semibold text-foreground mb-1.5">
                  Link to Purchase Bill (Optional - Auto Allocates via FIFO)
                </label>
                <select
                  value={selectedInvoiceId}
                  onChange={(e) => handleInvoiceSelect(e.target.value)}
                  className="w-full bg-muted/20 border border-border/60 rounded-xl px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 cursor-pointer"
                >
                  <option value="">-- No specific bill (General supplier payment) --</option>
                  {invoices.map((inv) => (
                    <option key={inv.id} value={inv.id}>
                      #{inv.voucher_number} — ₹{inv.total_amount} ({inv.party_ledger?.name || "Supplier"})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Recipient Details */}
            <div className="space-y-3 pt-2 border-t border-border/40">
              <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Recipient Information
              </h3>

              {parties.length > 0 && (
                <div>
                  <label className="block text-[11px] font-semibold text-foreground mb-1">
                    Select from Registered Suppliers
                  </label>
                  <select
                    value={payerPartyId}
                    onChange={(e) => handlePartySelect(e.target.value)}
                    className="w-full bg-muted/20 border border-border/60 rounded-xl px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 cursor-pointer"
                  >
                    <option value="">-- Enter recipient manually below --</option>
                    {parties.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name} {p.gstin ? `(${p.gstin})` : ""}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label className="block text-[11px] font-semibold text-foreground mb-1">
                  Recipient Name / Business *
                </label>
                <input
                  type="text"
                  required
                  value={recipientName}
                  onChange={(e) => setRecipientName(e.target.value)}
                  placeholder="e.g. Annapurna Belting Suppliers"
                  className="w-full bg-muted/20 border border-border/60 rounded-xl px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>

              {paymentMethod === "UPI" ? (
                <div>
                  <label className="block text-[11px] font-semibold text-foreground mb-1">
                    Recipient UPI VPA (Optional - for direct QR generation)
                  </label>
                  <input
                    type="text"
                    value={recipientVpa}
                    onChange={(e) => setRecipientVpa(e.target.value)}
                    placeholder="e.g. merchant@icici or 9876543210@paytm"
                    className="w-full bg-muted/20 border border-border/60 rounded-xl px-3 py-2 text-xs text-foreground font-mono focus:outline-none focus:ring-2 focus:ring-primary/40"
                  />
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] font-semibold text-foreground mb-1">
                      Bank Account Number
                    </label>
                    <input
                      type="text"
                      value={recipientAccount}
                      onChange={(e) => setRecipientAccount(e.target.value)}
                      placeholder="Account number"
                      className="w-full bg-muted/20 border border-border/60 rounded-xl px-3 py-2 text-xs text-foreground font-mono focus:outline-none focus:ring-2 focus:ring-primary/40"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-semibold text-foreground mb-1">
                      Bank IFSC Code
                    </label>
                    <input
                      type="text"
                      value={recipientIfsc}
                      onChange={(e) => setRecipientIfsc(e.target.value)}
                      placeholder="e.g. HDFC0001234"
                      className="w-full bg-muted/20 border border-border/60 rounded-xl px-3 py-2 text-xs text-foreground font-mono focus:outline-none focus:ring-2 focus:ring-primary/40"
                    />
                  </div>
                </div>
              )}

              <div>
                <label className="block text-[11px] font-semibold text-foreground mb-1">
                  Payment Notes / Reference
                </label>
                <input
                  type="text"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="e.g. Clearing October Bill #INV-1092"
                  className="w-full bg-muted/20 border border-border/60 rounded-xl px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>
            </div>

            {/* Submit Button */}
            <div className="pt-3">
              <button
                type="submit"
                disabled={submitting}
                className="w-full py-3 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:bg-primary/90 transition-all flex items-center justify-center gap-2 cursor-pointer shadow-md disabled:opacity-50"
              >
                {submitting ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Initiating Payment...</span>
                  </>
                ) : (
                  <>
                    <span>Generate Payment Intent</span>
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </div>
          </form>
        ) : (
          /* Payment Intent Generated Display */
          <div className="bg-card border border-border/50 rounded-2xl p-6 shadow-2xs space-y-6">
            
            <div className="flex items-center justify-between pb-4 border-b border-border/40">
              <div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground font-mono">
                  Traceable Reference: {createdPayment.srilekh_pay_id}
                </span>
                <h2 className="text-xl font-black text-foreground">
                  ₹{parseFloat(createdPayment.amount).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </h2>
                <p className="text-xs text-muted-foreground">
                  Pay to: <span className="font-semibold text-foreground">{createdPayment.recipient_name}</span>
                </p>
              </div>

              <span className="px-2.5 py-1 rounded-full text-xs font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400">
                Awaiting Confirmation
              </span>
            </div>

            {/* QR Code / DeepLink Box for UPI */}
            {createdPayment.payment_method === "UPI" && (
              <div className="flex flex-col items-center justify-center p-6 bg-muted/20 border border-border/50 rounded-2xl space-y-4">
                <div className="p-4 bg-white rounded-2xl shadow-sm border border-border/40">
                  <QrCode className="w-40 h-40 text-black mx-auto" />
                </div>
                <div className="text-center space-y-1">
                  <p className="text-xs font-semibold text-foreground">Scan with any UPI App</p>
                  <p className="text-[11px] text-muted-foreground">Google Pay, PhonePe, Paytm, BHIM, Cred</p>
                </div>

                {createdPayment.qr_data && (
                  <div className="flex items-center gap-2">
                    <a
                      href={createdPayment.qr_data}
                      className="px-4 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:bg-primary/90 flex items-center gap-1.5 shadow-sm"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                      <span>Open UPI App on Device</span>
                    </a>
                    <button
                      onClick={() => copyToClipboard(createdPayment.qr_data, "UPI URI")}
                      className="p-2 rounded-xl border border-border/60 bg-card hover:bg-muted text-foreground"
                      title="Copy UPI Intent URI"
                    >
                      <Copy className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Bank Transfer Instructions for NEFT / IMPS */}
            {createdPayment.payment_method !== "UPI" && (
              <div className="p-5 bg-muted/20 border border-border/50 rounded-2xl space-y-3">
                <h3 className="text-xs font-bold text-foreground flex items-center gap-2">
                  <Building className="w-4 h-4 text-primary" />
                  <span>Beneficiary Bank Transfer Details</span>
                </h3>
                
                <div className="space-y-2 text-xs">
                  <div className="flex justify-between items-center py-1 border-b border-border/20">
                    <span className="text-muted-foreground">Beneficiary Name</span>
                    <span className="font-semibold text-foreground">{createdPayment.recipient_name}</span>
                  </div>
                  <div className="flex justify-between items-center py-1 border-b border-border/20">
                    <span className="text-muted-foreground">Account Number</span>
                    <span className="font-mono font-bold text-foreground">
                      {createdPayment.recipient_account_number || `VOUCH${createdPayment.srilekh_pay_id.slice(-6)}`}
                    </span>
                  </div>
                  <div className="flex justify-between items-center py-1 border-b border-border/20">
                    <span className="text-muted-foreground">IFSC Code</span>
                    <span className="font-mono font-bold text-foreground">
                      {createdPayment.recipient_ifsc || "ICIC0000011"}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* UTR Confirmation Box */}
            <div className="p-5 bg-primary/5 border border-primary/20 rounded-2xl space-y-3">
              <div>
                <h3 className="text-xs font-bold text-primary flex items-center gap-1.5">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Verify Payment with Bank UTR</span>
                </h3>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Enter the 12-digit UTR/RRN from your bank or UPI app to instantly post the double-entry voucher.
                </p>
              </div>

              <div className="flex flex-col sm:flex-row gap-2">
                <input
                  type="text"
                  value={utrInput}
                  onChange={(e) => setUtrInput(e.target.value)}
                  placeholder="e.g. 412345678901 or ICICN2611..."
                  className="flex-1 bg-card border border-border/60 rounded-xl px-3 py-2 text-xs font-mono font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 min-h-[38px]"
                />
                <button
                  onClick={handleConfirmUtr}
                  disabled={confirmingUtr}
                  className="px-4 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:bg-primary/90 transition-all flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50 min-h-[38px]"
                >
                  {confirmingUtr ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <ShieldCheck className="w-3.5 h-3.5" />
                  )}
                  <span>Confirm & Post Voucher</span>
                </button>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <Link
                href="/pay"
                className="px-4 py-2 rounded-xl border border-border text-xs font-semibold text-foreground hover:bg-muted"
              >
                Return to Payments Dashboard
              </Link>
            </div>

          </div>
        )}

      </div>
    </DashboardLayout>
  );
}

export default function NewPaymentPage() {
  return (
    <Suspense
      fallback={
        <DashboardLayout>
          <div className="flex flex-col items-center justify-center min-h-[400px] space-y-3">
            <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            <div className="text-xs text-muted-foreground font-medium">Loading SriLekh Pay...</div>
          </div>
        </DashboardLayout>
      }
    >
      <NewPaymentContent />
    </Suspense>
  );
}
