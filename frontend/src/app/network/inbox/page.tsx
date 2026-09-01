"use client";

import React, { useState, useEffect } from "react";
import axios from "axios";
import Link from "next/link";
import { 
  Network, 
  ArrowDownLeft, 
  CheckCircle2, 
  XCircle, 
  Clock, 
  ShieldCheck, 
  FileText, 
  Search, 
  RefreshCw, 
  ChevronRight, 
  PackageCheck, 
  Building2, 
  Hash, 
  Calendar,
  AlertCircle,
  ExternalLink,
  Layers,
  Sparkles,
  Key
} from "lucide-react";
import DashboardLayout from "@/components/DashboardLayout";
import { getAccessToken } from "@/utils/auth";
import { API_BASE_URL } from "@/utils/api";

interface InwardRequest {
  id: string;
  source_company: {
    id: string;
    name: string;
    legal_name: string;
    gstin: string;
    state_code: string;
    city: string;
    address?: string;
    email: string;
    phone: string;
  };
  status: "PENDING" | "ACCEPTED" | "REJECTED" | "DISPUTED";
  payload: {
    source_company_name: string;
    source_company_gstin: string;
    voucher_number: string;
    voucher_date: string;
    reference_number?: string;
    narration?: string;
    total_amount: number;
    items: Array<{
      source_product_id: string;
      product_name: string;
      brand?: string;
      sku: string;
      hsn_code: string;
      unit: string;
      quantity: number;
      rate: number;
      discount_percent: number;
      discount_amount: number;
      taxable_amount: number;
      gst_rate: number;
      total_amount: number;
    }>;
  };
  digital_signature_hash?: string;
  signed_at?: string;
  created_purchase_voucher?: {
    id: string;
    voucher_number: string;
    total_amount: number;
    status: string;
  };
  rejection_reason?: string;
  created_at: string;
}

export default function B2BInboxPage() {
  const [requests, setRequests] = useState<InwardRequest[]>([]);
  const [counts, setCounts] = useState({ all: 0, pending: 0, accepted: 0, rejected: 0 });
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedReq, setSelectedReq] = useState<InwardRequest | null>(null);
  const [isSignModalOpen, setIsSignModalOpen] = useState(false);
  const [isRejectModalOpen, setIsRejectModalOpen] = useState(false);
  const [rejectionReason, setRejectionReason] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const fetchInbox = async () => {
    setLoading(true);
    setError("");
    try {
      const token = getAccessToken();
      const res = await axios.get(`${API_BASE_URL}/api/b2b/inbox/`, {
        headers: { Authorization: `Bearer ${token}` },
        params: { status: statusFilter }
      });
      setRequests(res.data.data || []);
      setCounts(res.data.counts || { all: 0, pending: 0, accepted: 0, rejected: 0 });
    } catch (err: any) {
      setError(err.response?.data?.error || "Failed to load B2B Inward network requests.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInbox();
  }, [statusFilter]);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 5000);
  };

  const handleAccept = async () => {
    if (!selectedReq) return;
    setActionLoading(true);
    try {
      const token = getAccessToken();
      const res = await axios.post(
        `${API_BASE_URL}/api/b2b/inbox/${selectedReq.id}/accept/`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.data.success) {
        showToast(`🎉 Success! Purchase Voucher #${res.data.voucher_number} created and inventory updated instantly.`);
        setIsSignModalOpen(false);
        setSelectedReq(null);
        fetchInbox();
      }
    } catch (err: any) {
      alert(err.response?.data?.error || "Failed to accept and sign inward voucher.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async () => {
    if (!selectedReq) return;
    setActionLoading(true);
    try {
      const token = getAccessToken();
      const res = await axios.post(
        `${API_BASE_URL}/api/b2b/inbox/${selectedReq.id}/reject/`,
        { reason: rejectionReason },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.data.success) {
        showToast("Inward voucher request has been rejected.");
        setIsRejectModalOpen(false);
        setSelectedReq(null);
        setRejectionReason("");
        fetchInbox();
      }
    } catch (err: any) {
      alert(err.response?.data?.error || "Failed to reject inward voucher.");
    } finally {
      setActionLoading(false);
    }
  };

  const filteredRequests = requests.filter(r => {
    const q = searchQuery.toLowerCase();
    return (
      r.source_company.name.toLowerCase().includes(q) ||
      r.source_company.gstin.toLowerCase().includes(q) ||
      r.payload.voucher_number.toLowerCase().includes(q)
    );
  });

  return (
    <DashboardLayout>
      <div className="space-y-6 animate-in fade-in duration-300">
        
        {/* Toast Banner */}
        {toastMessage && (
          <div className="p-4 bg-green-500/10 border border-green-500/30 text-green-400 rounded-xl flex items-center justify-between shadow-lg">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <CheckCircle2 className="w-5 h-5 text-green-400" />
              <span>{toastMessage}</span>
            </div>
            <button onClick={() => setToastMessage(null)} className="text-gray-400 hover:text-white text-xs">✕</button>
          </div>
        )}

        {/* Page Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/60 pb-5">
          <div>
            <div className="flex items-center gap-2">
              <div className="w-9 h-9 rounded-xl bg-blue-600/10 text-blue-500 flex items-center justify-center border border-blue-500/20">
                <Network className="w-5 h-5" />
              </div>
              <h1 className="text-2xl font-black tracking-tight">B2B Network Interchange (EDI)</h1>
              <span className="px-2 py-0.5 text-[10px] font-mono bg-blue-500/10 text-blue-400 border border-blue-500/20 rounded font-bold">
                AUTO-HANDSHAKE
              </span>
            </div>
            <p className="text-xs text-gray-400 mt-1">
              Cross-tenant verified invoice stream. When registered suppliers issue a sales invoice to your GSTIN, bills arrive here for 1-click cryptographic receipt.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={fetchInbox}
              disabled={loading}
              className="px-3.5 py-2 bg-zinc-800 hover:bg-zinc-700 text-gray-200 text-xs font-semibold rounded-lg border border-zinc-700 transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              <span>Refresh Inbox</span>
            </button>
            <Link
              href="/export/tally"
              className="px-3.5 py-2 bg-blue-600/10 hover:bg-blue-600/20 text-blue-400 border border-blue-500/30 text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5"
            >
              <FileText className="w-3.5 h-3.5" />
              <span>Tally Export</span>
            </Link>
          </div>
        </div>

        {/* Stats & Filter Bar */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <button
            onClick={() => setStatusFilter("ALL")}
            className={`p-3 rounded-xl border text-left transition-all ${
              statusFilter === "ALL"
                ? "bg-blue-600/10 border-blue-500/50 text-white"
                : "bg-card border-border hover:bg-zinc-900/60 text-gray-300"
            }`}
          >
            <div className="text-[10px] uppercase font-bold text-gray-400">All Inward Bills</div>
            <div className="text-xl font-extrabold mt-0.5">{counts.all}</div>
          </button>

          <button
            onClick={() => setStatusFilter("PENDING")}
            className={`p-3 rounded-xl border text-left transition-all ${
              statusFilter === "PENDING"
                ? "bg-amber-500/10 border-amber-500/50 text-amber-300"
                : "bg-card border-border hover:bg-zinc-900/60 text-gray-300"
            }`}
          >
            <div className="flex items-center justify-between text-[10px] uppercase font-bold text-amber-400">
              <span>Pending Sign</span>
              <Clock className="w-3.5 h-3.5" />
            </div>
            <div className="text-xl font-extrabold mt-0.5 text-amber-400">{counts.pending}</div>
          </button>

          <button
            onClick={() => setStatusFilter("ACCEPTED")}
            className={`p-3 rounded-xl border text-left transition-all ${
              statusFilter === "ACCEPTED"
                ? "bg-green-500/10 border-green-500/50 text-green-300"
                : "bg-card border-border hover:bg-zinc-900/60 text-gray-300"
            }`}
          >
            <div className="flex items-center justify-between text-[10px] uppercase font-bold text-green-400">
              <span>Accepted & Signed</span>
              <CheckCircle2 className="w-3.5 h-3.5" />
            </div>
            <div className="text-xl font-extrabold mt-0.5 text-green-400">{counts.accepted}</div>
          </button>

          <button
            onClick={() => setStatusFilter("REJECTED")}
            className={`p-3 rounded-xl border text-left transition-all ${
              statusFilter === "REJECTED"
                ? "bg-red-500/10 border-red-500/50 text-red-300"
                : "bg-card border-border hover:bg-zinc-900/60 text-gray-300"
            }`}
          >
            <div className="flex items-center justify-between text-[10px] uppercase font-bold text-red-400">
              <span>Rejected</span>
              <XCircle className="w-3.5 h-3.5" />
            </div>
            <div className="text-xl font-extrabold mt-0.5 text-red-400">{counts.rejected}</div>
          </button>
        </div>

        {/* Search Input */}
        <div className="relative">
          <Search className="w-4 h-4 text-gray-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search by supplier name, GSTIN, or invoice number..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-card border border-border rounded-xl pl-10 pr-4 py-2.5 text-xs text-foreground placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* Inward Invoices Table */}
        <div className="bg-card border border-border rounded-2xl overflow-hidden shadow-sm">
          {loading ? (
            <div className="p-12 text-center text-gray-400 text-xs flex flex-col items-center justify-center gap-2">
              <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
              <span>Scanning network ledger handshake...</span>
            </div>
          ) : error ? (
            <div className="p-8 text-center text-red-400 text-xs">
              <AlertCircle className="w-6 h-6 mx-auto mb-2 text-red-400" />
              <span>{error}</span>
            </div>
          ) : filteredRequests.length === 0 ? (
            <div className="p-12 text-center text-gray-500 space-y-2">
              <Network className="w-8 h-8 mx-auto text-zinc-600 stroke-[1.5]" />
              <div className="text-sm font-semibold text-gray-300">No B2B Inward Invoices Found</div>
              <p className="text-xs text-gray-500 max-w-md mx-auto">
                When registered suppliers on Vouch generate a Sales Invoice for your company GSTIN, the invoice automatically appears here for 1-click inspection and digital signing.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-border bg-zinc-950/40 text-gray-400 uppercase text-[10px] font-bold tracking-wider">
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Supplier Firm</th>
                    <th className="py-3 px-4 font-mono">Supplier GSTIN</th>
                    <th className="py-3 px-4 font-mono">Invoice #</th>
                    <th className="py-3 px-4 text-center">Items</th>
                    <th className="py-3 px-4 text-right">Taxable</th>
                    <th className="py-3 px-4 text-right">Grand Total</th>
                    <th className="py-3 px-4">Date</th>
                    <th className="py-3 px-4 text-center">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {filteredRequests.map((req) => {
                    const taxable = req.payload.items?.reduce((acc, i) => acc + (i.taxable_amount || 0), 0) || 0;
                    return (
                      <tr key={req.id} className="hover:bg-zinc-900/40 transition-colors">
                        <td className="py-3.5 px-4 whitespace-nowrap">
                          {req.status === "PENDING" && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20 animate-pulse">
                              <Clock className="w-3 h-3" />
                              <span>PENDING</span>
                            </span>
                          )}
                          {req.status === "ACCEPTED" && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-green-500/10 text-green-400 border border-green-500/20">
                              <CheckCircle2 className="w-3 h-3" />
                              <span>ACCEPTED</span>
                            </span>
                          )}
                          {req.status === "REJECTED" && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-500/10 text-red-400 border border-red-500/20">
                              <XCircle className="w-3 h-3" />
                              <span>REJECTED</span>
                            </span>
                          )}
                        </td>
                        <td className="py-3.5 px-4 font-semibold text-foreground whitespace-nowrap">
                          <div>{req.source_company.name}</div>
                          <div className="text-[10px] text-gray-500">{req.source_company.city || "India"}</div>
                        </td>
                        <td className="py-3.5 px-4 font-mono text-blue-400 whitespace-nowrap">
                          {req.source_company.gstin}
                        </td>
                        <td className="py-3.5 px-4 font-mono font-bold text-gray-200 whitespace-nowrap">
                          {req.payload.voucher_number}
                        </td>
                        <td className="py-3.5 px-4 text-center whitespace-nowrap">
                          <span className="px-2 py-0.5 bg-zinc-800 rounded font-mono text-gray-300 text-[11px]">
                            {req.payload.items?.length || 0}
                          </span>
                        </td>
                        <td className="py-3.5 px-4 text-right font-mono text-gray-300 whitespace-nowrap">
                          ₹{taxable.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </td>
                        <td className="py-3.5 px-4 text-right font-mono font-bold text-green-400 whitespace-nowrap">
                          ₹{(req.payload.total_amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </td>
                        <td className="py-3.5 px-4 text-gray-400 whitespace-nowrap">
                          {req.payload.voucher_date}
                        </td>
                        <td className="py-3.5 px-4 text-center whitespace-nowrap">
                          <button
                            onClick={() => {
                              setSelectedReq(req);
                              setIsSignModalOpen(true);
                            }}
                            className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-bold text-xs transition-colors shadow-sm inline-flex items-center gap-1 cursor-pointer"
                          >
                            <span>Inspect & Sign</span>
                            <ChevronRight className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Inspection & Digital Sign Modal */}
        {isSignModalOpen && selectedReq && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
            <div className="bg-card border border-border w-full max-w-4xl rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
              
              {/* Modal Header */}
              <div className="px-6 py-4 border-b border-border bg-zinc-950 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-blue-600/20 text-blue-400 flex items-center justify-center border border-blue-500/30">
                    <ShieldCheck className="w-4 h-4" />
                  </div>
                  <div>
                    <h2 className="text-sm font-bold text-white">Inspect B2B Inward Invoice</h2>
                    <div className="text-[11px] text-gray-400 font-mono">
                      Invoice #{selectedReq.payload.voucher_number} • Dated {selectedReq.payload.voucher_date}
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => {
                    setIsSignModalOpen(false);
                    setSelectedReq(null);
                  }}
                  className="p-1 text-gray-400 hover:text-white rounded-lg hover:bg-zinc-800"
                >
                  ✕
                </button>
              </div>

              {/* Modal Body - Two Column Layout */}
              <div className="p-6 overflow-y-auto space-y-6 flex-1 text-xs">
                
                {/* Header Information Grid */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 p-4 bg-zinc-950/60 rounded-xl border border-zinc-800">
                  <div>
                    <span className="text-[10px] text-gray-400 uppercase font-bold">Seller Firm</span>
                    <div className="font-bold text-white text-sm truncate">{selectedReq.source_company.name}</div>
                    <div className="text-gray-400 text-[11px] font-mono">{selectedReq.source_company.gstin}</div>
                  </div>
                  <div>
                    <span className="text-[10px] text-gray-400 uppercase font-bold">Seller Location</span>
                    <div className="text-gray-200">{selectedReq.source_company.address || "Main Street"}</div>
                    <div className="text-gray-400">State Code: {selectedReq.source_company.state_code}</div>
                  </div>
                  <div>
                    <span className="text-[10px] text-gray-400 uppercase font-bold">Total Inward Value</span>
                    <div className="text-green-400 font-mono text-base font-extrabold">
                      ₹{(selectedReq.payload.total_amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </div>
                    <div className="text-[10px] text-gray-400 font-mono">
                      {selectedReq.payload.items?.length} Line Items
                    </div>
                  </div>
                </div>

                {/* Line Items Breakdown */}
                <div className="space-y-2">
                  <h3 className="font-bold text-gray-300 text-xs flex items-center gap-1.5">
                    <PackageCheck className="w-4 h-4 text-blue-400" />
                    <span>Inward Line Items & Tax Breakdown</span>
                  </h3>

                  <div className="border border-border rounded-xl overflow-hidden">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="bg-zinc-950/80 text-gray-400 uppercase text-[10px] font-bold border-b border-border">
                          <th className="py-2.5 px-3">Item Name</th>
                          <th className="py-2.5 px-3 font-mono">HSN</th>
                          <th className="py-2.5 px-3 text-right">Qty</th>
                          <th className="py-2.5 px-3 text-right">Rate</th>
                          <th className="py-2.5 px-3 text-right">GST %</th>
                          <th className="py-2.5 px-3 text-right">Taxable</th>
                          <th className="py-2.5 px-3 text-right">Total</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/60">
                        {selectedReq.payload.items?.map((item, idx) => (
                          <tr key={idx} className="hover:bg-zinc-900/30">
                            <td className="py-2.5 px-3 font-medium text-white">
                              <div>{item.product_name}</div>
                              <div className="text-[10px] font-mono text-gray-500">SKU: {item.sku}</div>
                            </td>
                            <td className="py-2.5 px-3 font-mono text-gray-400">{item.hsn_code || "—"}</td>
                            <td className="py-2.5 px-3 text-right font-mono text-gray-200">
                              {item.quantity} {item.unit}
                            </td>
                            <td className="py-2.5 px-3 text-right font-mono text-gray-300">
                              ₹{item.rate.toFixed(2)}
                            </td>
                            <td className="py-2.5 px-3 text-right font-mono text-gray-300">
                              {item.gst_rate}%
                            </td>
                            <td className="py-2.5 px-3 text-right font-mono text-gray-300">
                              ₹{item.taxable_amount.toFixed(2)}
                            </td>
                            <td className="py-2.5 px-3 text-right font-mono font-bold text-green-400">
                              ₹{item.total_amount.toFixed(2)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Cryptographic Signature Info Box */}
                <div className="p-4 bg-blue-950/20 border border-blue-500/30 rounded-xl space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-blue-300 flex items-center gap-1.5 text-xs">
                      <Key className="w-3.5 h-3.5" />
                      <span>Cryptographic Handshake & Audit Hash</span>
                    </span>
                    <span className="text-[10px] font-mono bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded border border-blue-500/20">
                      SHA-256 Verified
                    </span>
                  </div>
                  {selectedReq.digital_signature_hash ? (
                    <div className="space-y-1">
                      <div className="text-[11px] font-mono text-green-400 break-all bg-zinc-950 p-2 rounded border border-green-500/30">
                        {selectedReq.digital_signature_hash}
                      </div>
                      <div className="text-[10px] text-gray-400">
                        Signed at: {selectedReq.signed_at} • Linked Purchase Voucher: #{selectedReq.created_purchase_voucher?.voucher_number}
                      </div>
                    </div>
                  ) : (
                    <p className="text-[11px] text-gray-400 leading-relaxed">
                      Accepting this voucher computes a permanent SHA-256 cryptographic seal over the supplier payload, creates an official <strong>PURCHASE Voucher</strong> in your books, debits Input GST credit, and increments your inventory stock automatically.
                    </p>
                  )}
                </div>

                {selectedReq.status === "REJECTED" && (
                  <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-xs">
                    <strong>Rejection Reason:</strong> {selectedReq.rejection_reason || "None specified"}
                  </div>
                )}
              </div>

              {/* Modal Footer Controls */}
              <div className="px-6 py-4 border-t border-border bg-zinc-950 flex items-center justify-between">
                <button
                  onClick={() => setIsSignModalOpen(false)}
                  className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-gray-300 rounded-lg text-xs font-semibold transition-colors"
                >
                  Close
                </button>

                {selectedReq.status === "PENDING" && (
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setIsRejectModalOpen(true)}
                      disabled={actionLoading}
                      className="px-4 py-2 bg-red-600/10 hover:bg-red-600/20 text-red-400 border border-red-500/30 rounded-lg text-xs font-bold transition-colors cursor-pointer"
                    >
                      Reject Invoice
                    </button>
                    <button
                      onClick={handleAccept}
                      disabled={actionLoading}
                      className="px-5 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg text-xs font-bold transition-colors shadow-lg flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                    >
                      {actionLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                      <span>Accept & Digitally Sign Receipt</span>
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Rejection Prompt Modal */}
        {isRejectModalOpen && selectedReq && (
          <div className="fixed inset-0 z-60 flex items-center justify-center p-4 bg-black/85 animate-in fade-in duration-200">
            <div className="bg-card border border-border w-full max-w-md rounded-2xl p-6 space-y-4 shadow-2xl">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <XCircle className="w-5 h-5 text-red-500" />
                <span>Reject Inward EDI Invoice</span>
              </h3>
              <p className="text-xs text-gray-400">
                Please specify a reason for rejecting invoice #{selectedReq.payload.voucher_number} from {selectedReq.source_company.name}.
              </p>
              <textarea
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                placeholder="e.g. Rate discrepancy, wrong quantity, or unexpected bill..."
                rows={3}
                className="w-full bg-zinc-900 border border-zinc-700 rounded-xl p-3 text-xs text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-red-500"
              />
              <div className="flex justify-end gap-2 pt-2">
                <button
                  onClick={() => setIsRejectModalOpen(false)}
                  className="px-3.5 py-2 bg-zinc-800 hover:bg-zinc-700 text-gray-300 rounded-lg text-xs font-semibold"
                >
                  Cancel
                </button>
                <button
                  onClick={handleReject}
                  disabled={actionLoading}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-bold shadow-lg"
                >
                  Confirm Rejection
                </button>
              </div>
            </div>
          </div>
        )}

      </div>
    </DashboardLayout>
  );
}
