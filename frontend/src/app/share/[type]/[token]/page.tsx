"use client";

import React, { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import axios from "axios";
import { API_BASE_URL, api } from "@/utils/api";
import { getAccessToken, setTokens } from "@/utils/auth";
import {
  FileText,
  Building2,
  CheckCircle2,
  Download,
  Zap,
  ArrowRight,
  ShieldCheck,
  AlertCircle,
  RefreshCw,
  Printer,
  Lock,
  ExternalLink,
} from "lucide-react";

interface ShareData {
  share_type: string;
  document_type: string;
  document_number: string;
  document_date: string;
  total_amount: number | null;
  expires_at: string | null;
  capabilities: {
    pdf: boolean;
    preview: boolean;
    share: boolean;
    email: boolean;
    whatsapp: boolean;
    edi: boolean;
  };
  dto: any;
}

export default function PublicSharePage() {
  const params = useParams();
  const router = useRouter();
  const token = (params?.token as string) || "";
  const shareType = (params?.type as string) || "i";

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<ShareData | null>(null);

  // EDI Import state
  const [importing, setImporting] = useState(false);
  const [importSuccess, setImportSuccess] = useState<any | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  // Auth modal for unauthenticated users clicking "Add to my Vouch"
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "register">("register");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authCompanyName, setAuthCompanyName] = useState("");
  const [authGstin, setAuthGstin] = useState("");
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setError("No document share token provided.");
      setLoading(false);
      return;
    }

    const fetchShare = async () => {
      try {
        const res = await axios.get(`${API_BASE_URL}/api/v1/documents/share/resolve/${token}/`);
        setData(res.data);
        if (res.data?.dto?.buyer) {
          setAuthCompanyName(res.data.dto.buyer.name || "");
          setAuthGstin(res.data.dto.buyer.gstin || "");
          setAuthEmail(res.data.dto.buyer.email || "");
        }
      } catch (err: any) {
        setError(err.response?.data?.error || "This document link is invalid, revoked, or has expired.");
      } finally {
        setLoading(false);
      }
    };

    fetchShare();
  }, [token]);

  const handleDownloadPdf = () => {
    window.open(`${API_BASE_URL}/api/v1/documents/share/download/${token}/`, "_blank");
  };

  const handleExecuteImport = async () => {
    setImportError(null);
    setImporting(true);

    try {
      const activeCompanyId = localStorage.getItem("current_company_id");
      const headers: Record<string, string> = {};
      if (activeCompanyId) {
        headers["X-Company-ID"] = activeCompanyId;
      }

      const res = await api.post(
        `/api/v1/documents/share/import/${token}/`,
        {},
        { headers }
      );
      setImportSuccess(res.data);
    } catch (err: any) {
      setImportError(err.response?.data?.error || "Failed to auto-import invoice.");
    } finally {
      setImporting(false);
    }
  };

  const handleAddToVouchClick = () => {
    const accessToken = getAccessToken();
    if (!accessToken) {
      setShowAuthModal(true);
    } else {
      handleExecuteImport();
    }
  };

  const handleAuthSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError(null);
    setAuthSubmitting(true);

    try {
      if (authMode === "login") {
        const res = await axios.post(`${API_BASE_URL}/api/v1/auth/login/`, {
          email: authEmail,
          password: authPassword,
        });
        setTokens(res.data.access, res.data.refresh);
        if (res.data.user?.companies?.[0]?.company_id) {
          localStorage.setItem("current_company_id", res.data.user.companies[0].company_id);
        }
      } else {
        const res = await axios.post(`${API_BASE_URL}/api/v1/accounting/vouchers/claim-register/`, {
          token: token,
          company_name: authCompanyName,
          buyer_gstin: authGstin,
          email: authEmail,
          password: authPassword,
        });
        setTokens(res.data.access, res.data.refresh);
        if (res.data.company?.id) {
          localStorage.setItem("current_company_id", res.data.company.id);
        }
      }

      setShowAuthModal(false);
      // Immediately run import after auth
      await handleExecuteImport();
    } catch (err: any) {
      setAuthError(err.response?.data?.error || "Authentication failed. Please check credentials.");
    } finally {
      setAuthSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <div className="text-center space-y-3">
          <RefreshCw className="w-8 h-8 animate-spin text-blue-600 mx-auto" />
          <p className="text-sm font-medium text-slate-600">Loading verified document...</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-white rounded-2xl p-6 sm:p-8 shadow-sm border border-slate-200 text-center space-y-4">
          <div className="w-12 h-12 rounded-full bg-red-50 text-red-600 flex items-center justify-center mx-auto">
            <AlertCircle className="w-6 h-6" />
          </div>
          <h2 className="text-lg font-bold text-slate-900">Document Unavailable</h2>
          <p className="text-sm text-slate-600 leading-relaxed">{error || "Document could not be loaded."}</p>
        </div>
      </div>
    );
  }

  const dto = data.dto || {};
  const isInvoice = data.capabilities.edi;
  const seller = dto.seller || dto.company || {};
  const buyer = dto.buyer || dto.party || {};
  const docMeta = dto.document || {};
  const subtotals = dto.subtotals || {};
  const items = dto.items || [];
  const transactions = dto.transactions || [];

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900 font-sans pb-16">
      {/* Top Banner */}
      <header className="bg-white border-b border-slate-200 px-4 py-3 sticky top-0 z-30 shadow-xs">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <div className="w-8 h-8 rounded-lg bg-blue-600 text-white flex items-center justify-center font-bold text-sm tracking-wider">
              V
            </div>
            <div>
              <span className="font-bold text-slate-900 text-base">VOUCH</span>
              <span className="hidden sm:inline-block ml-2 text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                ✓ Verified Document
              </span>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={handleDownloadPdf}
              className="inline-flex items-center px-3 py-1.5 text-xs font-semibold rounded-lg bg-blue-600 hover:bg-blue-700 text-white transition-colors shadow-xs"
            >
              <Download className="w-3.5 h-3.5 mr-1.5" />
              Download PDF
            </button>
            <button
              onClick={() => window.print()}
              className="hidden sm:inline-flex items-center px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors"
            >
              <Printer className="w-3.5 h-3.5 mr-1.5" />
              Print
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto p-4 sm:p-6 space-y-6">
        {/* Success / Warning Alerts */}
        {importSuccess && (
          <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 flex items-start space-x-3">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
            <div className="text-sm">
              <p className="font-bold text-emerald-900">{importSuccess.message}</p>
              {importSuccess.warning && (
                <p className="text-amber-800 text-xs mt-1 font-medium">{importSuccess.warning}</p>
              )}
              <div className="mt-2">
                <button
                  onClick={() => router.push("/purchases")}
                  className="inline-flex items-center font-bold text-xs text-emerald-700 hover:underline"
                >
                  View in Purchases <ArrowRight className="w-3.5 h-3.5 ml-1" />
                </button>
              </div>
            </div>
          </div>
        )}

        {importError && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-start space-x-3">
            <AlertCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
            <div className="text-sm">
              <p className="font-bold text-red-900">Import Failed</p>
              <p className="text-red-700 text-xs mt-0.5">{importError}</p>
            </div>
          </div>
        )}

        {/* Primary Action Card for Invoices (EDI) */}
        {isInvoice && !importSuccess && (
          <div className="bg-linear-to-r from-blue-700 to-indigo-800 text-white rounded-2xl p-5 sm:p-6 shadow-md flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full bg-blue-500/30 text-blue-100 text-xs font-semibold">
                <Zap className="w-3.5 h-3.5 text-amber-300" />
                <span>Instant B2B Handshake</span>
              </div>
              <h2 className="text-lg sm:text-xl font-bold">Auto-Book This Bill Into Your Vouch</h2>
              <p className="text-xs sm:text-sm text-blue-100/90 max-w-xl">
                Avoid typing line items manually. 1-Click imports this invoice directly into your Vouch books as a verified Draft Purchase Bill.
              </p>
            </div>

            <button
              onClick={handleAddToVouchClick}
              disabled={importing}
              className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-amber-400 hover:bg-amber-300 text-slate-950 font-bold text-sm transition-all shadow-md flex items-center justify-center shrink-0 disabled:opacity-50"
            >
              {importing ? (
                <>
                  <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                  Importing...
                </>
              ) : (
                <>
                  <Zap className="w-4 h-4 mr-2 text-slate-950" />
                  Add to my Vouch
                </>
              )}
            </button>
          </div>
        )}

        {/* Document Overview Box */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5 sm:p-6 shadow-xs space-y-6">
          {/* Header Row */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-5">
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                {data.document_type.replace(/_/g, " ")}
              </span>
              <h1 className="text-xl sm:text-2xl font-black text-slate-900 mt-0.5">
                {data.document_number || "Document"}
              </h1>
              <p className="text-xs text-slate-500 mt-0.5">
                Date: <span className="font-semibold text-slate-700">{data.document_date || "N/A"}</span>
              </p>
            </div>

            <div className="sm:text-right bg-slate-50 sm:bg-transparent p-3 sm:p-0 rounded-xl">
              <span className="text-xs text-slate-500 block">Total Amount</span>
              <span className="text-2xl font-black text-blue-700">
                ₹{Number(data.total_amount || subtotals.grand_total || 0).toLocaleString("en-IN", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </span>
              {dto.amount_in_words && (
                <span className="text-[11px] text-slate-500 block italic max-w-xs sm:ml-auto">
                  {dto.amount_in_words}
                </span>
              )}
            </div>
          </div>

          {/* Party Details Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-100 space-y-1">
              <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block">
                Issued By (Seller)
              </span>
              <p className="font-bold text-sm text-slate-900">{seller.name || "Company"}</p>
              <p className="text-xs text-slate-600">{seller.address || ""}</p>
              <p className="text-xs text-slate-700 font-medium">
                GSTIN: <span className="font-bold">{seller.gstin || "Unregistered"}</span>
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-50 border border-slate-100 space-y-1">
              <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block">
                Billed To (Buyer)
              </span>
              <p className="font-bold text-sm text-slate-900">{buyer.name || "Customer"}</p>
              <p className="text-xs text-slate-600">{buyer.address || ""}</p>
              <p className="text-xs text-slate-700 font-medium">
                GSTIN: <span className="font-bold">{buyer.gstin || "Unregistered"}</span>
              </p>
            </div>
          </div>

          {/* Items Table (For Invoices) */}
          {items.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-bold text-slate-800">Items &amp; Goods Breakdown</h3>
              <div className="overflow-x-auto rounded-xl border border-slate-200">
                <table className="w-full text-left border-collapse text-xs">
                  <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                    <tr>
                      <th className="p-2.5">S.N.</th>
                      <th className="p-2.5">Description</th>
                      <th className="p-2.5">HSN</th>
                      <th className="p-2.5 text-right">Qty</th>
                      <th className="p-2.5 text-right">Rate (₹)</th>
                      <th className="p-2.5 text-right">Taxable (₹)</th>
                      <th className="p-2.5 text-right">GST</th>
                      <th className="p-2.5 text-right">Total (₹)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {items.map((itm: any, idx: number) => (
                      <tr key={idx} className="hover:bg-slate-50/60">
                        <td className="p-2.5 text-slate-400">{itm.sn || idx + 1}</td>
                        <td className="p-2.5 font-medium text-slate-900">{itm.name}</td>
                        <td className="p-2.5 text-slate-500">{itm.hsn_code || "-"}</td>
                        <td className="p-2.5 text-right font-medium">
                          {itm.quantity} {itm.unit || ""}
                        </td>
                        <td className="p-2.5 text-right">{Number(itm.rate).toFixed(2)}</td>
                        <td className="p-2.5 text-right font-medium">{Number(itm.taxable_amount).toFixed(2)}</td>
                        <td className="p-2.5 text-right text-slate-500">{itm.gst_rate}%</td>
                        <td className="p-2.5 text-right font-bold text-slate-900">
                          {Number(itm.total_amount).toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Statement Transactions (For Statements) */}
          {transactions.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-bold text-slate-800">Transaction History</h3>
              <div className="overflow-x-auto rounded-xl border border-slate-200">
                <table className="w-full text-left border-collapse text-xs">
                  <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                    <tr>
                      <th className="p-2.5">Date</th>
                      <th className="p-2.5">Voucher No</th>
                      <th className="p-2.5">Type</th>
                      <th className="p-2.5">Narration</th>
                      <th className="p-2.5 text-right">Debit (₹)</th>
                      <th className="p-2.5 text-right">Credit (₹)</th>
                      <th className="p-2.5 text-right">Balance (₹)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {transactions.map((tx: any, idx: number) => (
                      <tr key={idx} className="hover:bg-slate-50/60">
                        <td className="p-2.5 text-slate-500">{tx.date}</td>
                        <td className="p-2.5 font-semibold text-slate-900">{tx.voucher_number}</td>
                        <td className="p-2.5 text-slate-500">{tx.voucher_type}</td>
                        <td className="p-2.5 text-slate-600">{tx.narration || "-"}</td>
                        <td className="p-2.5 text-right font-medium text-slate-800">
                          {tx.debit > 0 ? Number(tx.debit).toFixed(2) : "-"}
                        </td>
                        <td className="p-2.5 text-right font-medium text-slate-800">
                          {tx.credit > 0 ? Number(tx.credit).toFixed(2) : "-"}
                        </td>
                        <td className="p-2.5 text-right font-bold text-blue-700">
                          {Number(tx.running_balance).toFixed(2)} {tx.running_type}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Footer Note */}
          <div className="pt-4 border-t border-slate-100 text-center text-xs text-slate-400">
            Official B2B Document generated and secured via Vouch ERP Infrastructure.
          </div>
        </div>
      </main>

      {/* Auth Modal for Unauthenticated Clickers */}
      {showAuthModal && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl border border-slate-100 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-slate-900 text-lg">
                {authMode === "register" ? "Auto-Book into Vouch" : "Log In to Import"}
              </h3>
              <button
                onClick={() => setShowAuthModal(false)}
                className="text-slate-400 hover:text-slate-600 text-sm font-bold"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-slate-500">
              {authMode === "register"
                ? "Set a password to register your business. We will create your Vouch tenant and import this invoice as a draft purchase bill instantly."
                : "Enter your Vouch account credentials to import this bill."}
            </p>

            {authError && (
              <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-xs rounded-lg">
                {authError}
              </div>
            )}

            <form onSubmit={handleAuthSubmit} className="space-y-3">
              {authMode === "register" && (
                <>
                  <div>
                    <label className="text-[11px] font-bold text-slate-600 block mb-1">Company Name</label>
                    <input
                      type="text"
                      required
                      value={authCompanyName}
                      onChange={(e) => setAuthCompanyName(e.target.value)}
                      className="w-full text-xs p-2.5 border border-slate-200 rounded-lg focus:outline-blue-600"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] font-bold text-slate-600 block mb-1">GSTIN</label>
                    <input
                      type="text"
                      value={authGstin}
                      onChange={(e) => setAuthGstin(e.target.value.toUpperCase())}
                      className="w-full text-xs p-2.5 border border-slate-200 rounded-lg focus:outline-blue-600 uppercase"
                    />
                  </div>
                </>
              )}

              <div>
                <label className="text-[11px] font-bold text-slate-600 block mb-1">Email</label>
                <input
                  type="email"
                  required
                  value={authEmail}
                  onChange={(e) => setAuthEmail(e.target.value)}
                  className="w-full text-xs p-2.5 border border-slate-200 rounded-lg focus:outline-blue-600"
                />
              </div>

              <div>
                <label className="text-[11px] font-bold text-slate-600 block mb-1">Password</label>
                <input
                  type="password"
                  required
                  value={authPassword}
                  onChange={(e) => setAuthPassword(e.target.value)}
                  className="w-full text-xs p-2.5 border border-slate-200 rounded-lg focus:outline-blue-600"
                />
              </div>

              <button
                type="submit"
                disabled={authSubmitting}
                className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs rounded-xl shadow-xs transition-colors disabled:opacity-50"
              >
                {authSubmitting ? "Processing..." : authMode === "register" ? "Create Account & Auto-Book" : "Log In & Auto-Book"}
              </button>
            </form>

            <div className="text-center pt-2">
              <button
                type="button"
                onClick={() => setAuthMode(authMode === "register" ? "login" : "register")}
                className="text-xs text-blue-600 hover:underline font-medium"
              >
                {authMode === "register"
                  ? "Already have a Vouch account? Log in instead"
                  : "Need an account? Quick register your company"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
