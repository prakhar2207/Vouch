"use client";
import React, { useEffect, useState } from "react";
import axios from "axios";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import DashboardLayout from "@/components/DashboardLayout";

export default function PurchaseInvoiceList() {
  const router = useRouter();
  const [invoices, setInvoices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedVoucher, setSelectedVoucher] = useState<any | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [zoomLevel, setZoomLevel] = useState<number>(100);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }
    fetchInvoices();
  }, [router]);

  const fetchInvoices = async () => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const compRes = await axios.get("http://localhost:8000/api/v1/companies/", { headers });
      const companyId = compRes.data.data[0]?.id;
      if (!companyId) return;

      const res = await axios.get(`http://localhost:8000/api/v1/accounting/vouchers/${companyId}/`, { headers });
      const purchaseVouchers = (res.data.data || []).filter((v: any) => v.type === "PURCHASE");
      setInvoices(purchaseVouchers);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenVoucherDetail = async (voucherId: string) => {
    setLoadingDetail(true);
    setSelectedVoucher(null);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const res = await axios.get(`http://localhost:8000/api/vouchers/${voucherId}/`, { headers });
      if (res.data.success) {
        setSelectedVoucher(res.data.data);
      }
    } catch (err) {
      console.error("Failed to load voucher detail:", err);
    } finally {
      setLoadingDetail(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6 flex flex-col h-full">
        {/* Header */}
        <div className="flex justify-between items-center border-b border-border pb-4">
          <div>
            <h1 className="text-3xl font-bold text-white">Purchase Invoices</h1>
            <p className="text-xs text-gray-400 mt-1">Inward supplier bills and attached documents</p>
          </div>
          <Link
            href="/purchases/new"
            className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg text-xs font-bold shadow-md transition-colors flex items-center gap-1.5"
          >
            <span>+ Create / Scan Invoice</span>
            <kbd className="bg-purple-800 px-1.5 py-0.5 rounded text-[10px]">F9</kbd>
          </Link>
        </div>

        {/* Invoices Table Card */}
        <div className="bg-card text-card-foreground p-2 rounded-xl shadow-sm border border-border flex-1 h-[600px] overflow-hidden flex flex-col">
          <div className="px-4 py-3 border-b border-border bg-gray-50 dark:bg-zinc-800/50 flex items-center justify-between">
            <span className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Previous Invoices</span>
            <span className="text-xs text-gray-400">Click any row or "View Document" to inspect original bill</span>
          </div>

          {loading ? (
            <div className="flex items-center justify-center h-full text-gray-500">Loading invoices...</div>
          ) : invoices.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center p-12 bg-card">
              <div className="text-4xl mb-3">📄</div>
              <h3 className="text-2xl font-bold mb-2">No Purchase Invoices Yet</h3>
              <p className="text-gray-500 max-w-md mx-auto mb-6 text-sm">
                Upload your first supplier bill to automatically extract data and store attached documents.
              </p>
              <Link
                href="/purchases/new"
                className="bg-purple-600 hover:bg-purple-700 text-white px-6 py-2.5 rounded-lg shadow font-bold text-xs"
              >
                + Scan First Invoice
              </Link>
            </div>
          ) : (
            <div className="flex-1 w-full overflow-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-zinc-800 bg-zinc-900/40 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                    <th className="p-4 rounded-tl-lg">Invoice No.</th>
                    <th className="p-4">Date</th>
                    <th className="p-4">Supplier Party</th>
                    <th className="p-4">Total Amount</th>
                    <th className="p-4">Status</th>
                    <th className="p-4 rounded-tr-lg text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/50 text-xs">
                  {invoices.map((inv) => (
                    <tr
                      key={inv.id}
                      onClick={() => handleOpenVoucherDetail(inv.id)}
                      className="hover:bg-zinc-800/40 transition-colors cursor-pointer group"
                    >
                      <td className="p-4 font-mono font-medium text-white flex items-center gap-2">
                        <span>{inv.voucher_number}</span>
                        {inv.has_attachment && (
                          <span className="px-1.5 py-0.5 bg-blue-500/20 text-blue-400 rounded text-[10px] font-bold border border-blue-500/30">
                            📎 Doc
                          </span>
                        )}
                      </td>
                      <td className="p-4 text-gray-400">{inv.date}</td>
                      <td className="p-4 text-gray-300 font-medium">{inv.party_name}</td>
                      <td className="p-4 font-bold text-white font-mono">
                        ₹ {parseFloat(inv.total_amount).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </td>
                      <td className="p-4">
                        <span className={`px-2.5 py-1 text-[10px] font-bold rounded-full ${
                          inv.status === "POSTED"
                            ? "bg-green-500/10 text-green-400 border border-green-500/20"
                            : "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                        }`}>
                          {inv.status}
                        </span>
                      </td>
                      <td className="p-4 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleOpenVoucherDetail(inv.id);
                          }}
                          className="px-3 py-1 bg-zinc-800 hover:bg-zinc-700 text-gray-200 rounded-md text-xs font-semibold border border-zinc-700 transition-colors"
                        >
                          👁️ View Bill & Doc
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Voucher Detail & Document Viewer Modal */}
        {(selectedVoucher || loadingDetail) && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 animate-in fade-in">
            <div className="w-full max-w-5xl bg-zinc-900 border border-zinc-700 rounded-2xl shadow-2xl overflow-hidden flex flex-col text-white max-h-[90vh]">
              {/* Modal Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 bg-zinc-950">
                <div className="flex items-center gap-3">
                  <span className="text-xl">🧾</span>
                  <div>
                    <h3 className="text-lg font-bold text-white">
                      Purchase Invoice #{selectedVoucher?.voucher_number || "Loading..."}
                    </h3>
                    <p className="text-xs text-gray-400">
                      Date: {selectedVoucher?.date} • Supplier: {selectedVoucher?.party?.name}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => setSelectedVoucher(null)}
                    className="text-gray-400 hover:text-white text-sm font-bold px-2 py-1 cursor-pointer"
                  >
                    ✕
                  </button>
                </div>
              </div>

              {/* Modal Body */}
              <div className="p-6 overflow-y-auto space-y-6 flex-1">
                {loadingDetail ? (
                  <div className="p-12 flex flex-col items-center justify-center space-y-3">
                    <div className="w-8 h-8 border-4 border-purple-500 border-t-transparent rounded-full animate-spin"></div>
                    <div className="text-xs text-gray-400">Loading invoice details & document...</div>
                  </div>
                ) : selectedVoucher ? (
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Left Column: Original Document Viewer */}
                    <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-4 flex flex-col h-[520px]">
                      <div className="flex items-center justify-between border-b border-zinc-800 pb-2 mb-3 text-xs">
                        <span className="font-bold text-gray-300">Attached Original Document</span>
                        <div className="flex items-center gap-2">
                          <button onClick={() => setZoomLevel((z) => Math.max(50, z - 25))} className="px-2 py-0.5 bg-zinc-800 rounded text-xs">-</button>
                          <span className="font-mono text-gray-300 text-[11px]">{zoomLevel}%</span>
                          <button onClick={() => setZoomLevel((z) => Math.min(200, z + 25))} className="px-2 py-0.5 bg-zinc-800 rounded text-xs">+</button>
                          {selectedVoucher.attachment_data && (
                            <a
                              href={selectedVoucher.attachment_data}
                              target="_blank"
                              rel="noreferrer"
                              className="px-2 py-0.5 bg-blue-600/20 text-blue-400 rounded text-[11px] font-bold"
                            >
                              ↗ Pop Out
                            </a>
                          )}
                        </div>
                      </div>

                      <div className="flex-1 bg-zinc-900 rounded-lg overflow-auto flex items-center justify-center p-2">
                        {selectedVoucher.attachment_data ? (
                          selectedVoucher.attachment_mime?.includes("pdf") || selectedVoucher.attachment_data.startsWith("data:application/pdf") ? (
                            <object
                              data={selectedVoucher.attachment_data}
                              type="application/pdf"
                              className="w-full h-full rounded border-0"
                            >
                              <embed src={selectedVoucher.attachment_data} type="application/pdf" className="w-full h-full" />
                              <div className="text-center p-4 text-xs text-gray-400">
                                <a href={selectedVoucher.attachment_data} target="_blank" rel="noreferrer" className="text-blue-400 underline">
                                  Click here to open and view the PDF
                                </a>
                              </div>
                            </object>
                          ) : (
                            <div className="w-full h-full overflow-auto flex items-center justify-center">
                              <img
                                src={selectedVoucher.attachment_data}
                                alt="Original Document"
                                style={{ transform: `scale(${zoomLevel / 100})`, transformOrigin: "center center" }}
                                className="max-w-full max-h-full object-contain rounded transition-transform"
                              />
                            </div>
                          )
                        ) : (
                          <div className="text-center p-8 text-gray-500 text-xs">
                            No document was attached to this purchase invoice.
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Right Column: Invoice Details & Items Breakdown */}
                    <div className="space-y-4 text-xs">
                      {/* Supplier Card */}
                      <div className="p-4 bg-zinc-950 border border-zinc-800 rounded-xl space-y-2">
                        <div className="font-bold text-gray-300 border-b border-zinc-800 pb-1">Supplier Details</div>
                        <div className="flex justify-between"><span className="text-gray-400">Supplier:</span><span className="font-semibold text-white">{selectedVoucher.party?.name}</span></div>
                        <div className="flex justify-between"><span className="text-gray-400">GSTIN:</span><span className="font-mono text-white">{selectedVoucher.party?.gstin || "N/A"}</span></div>
                        <div className="flex justify-between"><span className="text-gray-400">Place of Supply:</span><span className="text-white">State {selectedVoucher.party?.state_code || "N/A"}</span></div>
                      </div>

                      {/* Items List */}
                      <div className="p-4 bg-zinc-950 border border-zinc-800 rounded-xl space-y-3">
                        <div className="font-bold text-gray-300 border-b border-zinc-800 pb-1">Invoiced Products</div>
                        <div className="space-y-2 max-h-40 overflow-y-auto">
                          {(selectedVoucher.items || []).map((item: any, idx: number) => (
                            <div key={idx} className="p-2.5 bg-zinc-900 rounded-lg space-y-1">
                              <div className="flex justify-between font-medium text-white">
                                <span>{item.product_name}</span>
                                <span className="font-mono">₹{Number(item.total_amount || item.taxable_amount).toFixed(2)}</span>
                              </div>
                              <div className="flex justify-between text-[11px] text-gray-400 font-mono">
                                <span>HSN: {item.hsn_code || "40103999"}</span>
                                <span>{item.quantity} {item.unit || "PCS"} × ₹{Number(item.rate).toFixed(2)}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Financials & Totals */}
                      <div className="p-4 bg-zinc-950 border border-zinc-800 rounded-xl space-y-2 font-mono text-xs">
                        <div className="flex justify-between text-gray-400">
                          <span>Accounting Status:</span>
                          <span className="text-green-400 font-bold">{selectedVoucher.status}</span>
                        </div>
                        <div className="flex justify-between text-sm font-bold text-white border-t border-zinc-800 pt-2">
                          <span>Grand Total:</span>
                          <span className="text-green-400">₹{Number(selectedVoucher.total_amount).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>

              {/* Footer */}
              <div className="px-6 py-3 bg-zinc-950 border-t border-zinc-800 text-xs text-gray-400 flex items-center justify-between">
                <span>Press <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded font-mono text-zinc-300">Esc</kbd> or ✕ to close</span>
                <button
                  onClick={() => setSelectedVoucher(null)}
                  className="px-4 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-white rounded-lg text-xs font-semibold"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
