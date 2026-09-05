"use client";

import React, { useState } from "react";
import axios from "axios";
import Link from "next/link";
import { 
  FileCode2, 
  Download, 
  BookOpen, 
  CheckCircle2, 
  HelpCircle, 
  Calendar, 
  Layers, 
  FileSpreadsheet, 
  Copy, 
  Check, 
  ExternalLink,
  ShieldAlert,
  ArrowRight,
  Info,
  Sparkles,
  Database
} from "lucide-react";
import DashboardLayout from "@/components/DashboardLayout";
import { getAccessToken } from "@/utils/auth";
import { API_BASE_URL } from "@/utils/api";
import { useToast } from "@/context/ToastContext";

export default function TallyExportPage() {
  const { toast } = useToast();
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [exportType, setExportType] = useState<"all" | "vouchers" | "masters">("all");
  const [selectedVchTypes, setSelectedVchTypes] = useState<string[]>([
    "SALES", "PURCHASE", "PAYMENT", "RECEIPT", "JOURNAL", "CONTRA"
  ]);
  const [downloading, setDownloading] = useState(false);
  const [isGuideOpen, setIsGuideOpen] = useState(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [downloadSuccess, setDownloadSuccess] = useState(false);

  const toggleVoucherType = (type: string) => {
    setSelectedVchTypes(prev => 
      prev.includes(type) ? prev.filter(t => t !== type) : [...prev, type]
    );
  };

  const handleDownload = async () => {
    setDownloading(true);
    setDownloadSuccess(false);
    try {
      const token = getAccessToken();
      const params: any = {
        type: exportType,
        voucher_types: selectedVchTypes.join(",")
      };
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;

      const res = await axios.get(`${API_BASE_URL}/api/export/tally/xml/`, {
        headers: { Authorization: `Bearer ${token}` },
        params,
        responseType: "blob"
      });

      // Extract filename or fallback
      const blob = new Blob([res.data], { type: "application/xml" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `Vouch_Tally_Export_${new Date().toISOString().slice(0, 10)}.xml`);
      document.body.appendChild(link);
      link.click();
      link.parentNode?.removeChild(link);
      window.URL.revokeObjectURL(url);

      setDownloadSuccess(true);
      toast.success("Export generated successfully", "Your Tally XML file has downloaded.");
      setTimeout(() => setDownloadSuccess(false), 6000);
    } catch (err: any) {
      toast.error("Export Failed", "Failed to export Tally XML. Please verify your date filters.");
    } finally {
      setDownloading(false);
    }
  };

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(id);
    setTimeout(() => setCopiedKey(null), 2500);
  };

  const setPreset = (preset: "this_month" | "last_month" | "fy" | "all") => {
    const now = new Date();
    if (preset === "all") {
      setFromDate("");
      setToDate("");
    } else if (preset === "this_month") {
      const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
      setFromDate(firstDay.toISOString().slice(0, 10));
      setToDate(now.toISOString().slice(0, 10));
    } else if (preset === "last_month") {
      const firstDay = new Date(now.getFullYear(), now.getMonth() - 1, 1);
      const lastDay = new Date(now.getFullYear(), now.getMonth(), 0);
      setFromDate(firstDay.toISOString().slice(0, 10));
      setToDate(lastDay.toISOString().slice(0, 10));
    } else if (preset === "fy") {
      const currentYear = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
      setFromDate(`${currentYear}-04-01`);
      setToDate(`${currentYear + 1}-03-31`);
    }
  };

  const tallyVoucherOptions = [
    { type: "SALES", label: "Sales (F8)", desc: "Customer Invoices & Outward GST" },
    { type: "PURCHASE", label: "Purchase (F9)", desc: "Vendor Bills & Input ITC" },
    { type: "RECEIPT", label: "Receipt (F6)", desc: "Bank & Cash Inflow" },
    { type: "PAYMENT", label: "Payment (F5)", desc: "Vendor & Expense Payouts" },
    { type: "CONTRA", label: "Contra (F4)", desc: "Cash-to-Bank Transfers" },
    { type: "JOURNAL", label: "Journal (F7)", desc: "Adjustments & Depreciation" },
  ];

  const guideSteps = [
    {
      step: "1",
      title: "Download the Tally XML Export",
      desc: "Configure your date range on this page and click 'Generate & Download Tally XML'. Keep the .xml file saved on your computer.",
      shortcut: null
    },
    {
      step: "2",
      title: "Open TallyPrime & Load Company",
      desc: "Launch TallyPrime or Tally.ERP 9 and select the company you wish to import data into.",
      shortcut: "F1 / Select Company"
    },
    {
      step: "3",
      title: "Trigger the Import Menu",
      desc: "Press Alt + O on your keyboard or click 'Import' from the top application header.",
      shortcut: "Alt + O"
    },
    {
      step: "4",
      title: "Select Data Type (Masters vs Transactions)",
      desc: "If importing for the first time, select 'Masters' to create all Chart of Accounts and Stock Items. Then select 'Transactions' to import vouchers.",
      shortcut: "Transactions / Masters"
    },
    {
      step: "5",
      title: "Select Downloaded XML File",
      desc: "Provide the file path to the downloaded XML file (e.g. C:\\Downloads\\Vouch_Tally_Export.xml).",
      shortcut: "File Path (.xml)"
    },
    {
      step: "6",
      title: "Set Import Behavior",
      desc: "Set treatment of existing records to 'Modify with New Data' to update balances seamlessly.",
      shortcut: "Modify with New Data"
    },
    {
      step: "7",
      title: "Verify in Day Book",
      desc: "Press Enter to execute the import. Once complete, open Day Book to review all double-entry vouchers.",
      shortcut: "Alt + G > Day Book"
    },
  ];

  return (
    <DashboardLayout>
      <div className="space-y-6 animate-in fade-in duration-300 max-w-5xl mx-auto">
        
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/60 pb-5">
          <div>
            <div className="flex items-center gap-2">
              <div className="w-9 h-9 rounded-xl bg-purple-600/10 text-purple-400 flex items-center justify-center border border-purple-500/20">
                <FileCode2 className="w-5 h-5" />
              </div>
              <h1 className="text-2xl font-black tracking-tight">Tally XML Export & Bridge</h1>
              <span className="px-2 py-0.5 text-[10px] font-mono bg-purple-500/10 text-purple-400 border border-purple-500/20 rounded font-bold">
                TallyPrime & ERP 9
              </span>
            </div>
            <p className="text-xs text-gray-400 mt-1">
              Export ledgers, product inventory items, and balanced double-entry vouchers in standard Tally &lt;ENVELOPE&gt; schema for seamless CA audits.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsGuideOpen(true)}
              className="px-4 py-2 bg-blue-600/10 hover:bg-blue-600/20 text-blue-400 border border-blue-500/30 text-xs font-bold rounded-lg transition-colors flex items-center gap-1.5 cursor-pointer shadow-sm"
            >
              <BookOpen className="w-4 h-4" />
              <span>CA Import Guide (Alt+O)</span>
            </button>
          </div>
        </div>

        {/* Download Success Banner */}
        {downloadSuccess && (
          <div className="p-4 bg-green-500/10 border border-green-500/30 text-green-400 rounded-xl flex items-center justify-between shadow-lg animate-in fade-in">
            <div className="flex items-center gap-2 text-xs font-semibold">
              <CheckCircle2 className="w-5 h-5 text-green-400 shrink-0" />
              <span>XML file exported successfully! Open TallyPrime and press <kbd className="px-1.5 py-0.5 bg-green-950 rounded font-mono text-green-300">Alt + O</kbd> to import.</span>
            </div>
            <button onClick={() => setDownloadSuccess(false)} className="text-gray-400 hover:text-white text-xs">✕</button>
          </div>
        )}

        {/* Main Export Settings Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          
          {/* Left Column: Scope & Date Settings (2 Cols) */}
          <div className="lg:col-span-2 space-y-6">
            
            {/* Scope Selection */}
            <div className="bg-card border border-border rounded-2xl p-5 space-y-4">
              <h2 className="text-sm font-bold text-white flex items-center gap-2">
                <Database className="w-4 h-4 text-purple-400" />
                <span>1. Select Export Scope</span>
              </h2>

              <div className="grid grid-cols-3 gap-3">
                <button
                  type="button"
                  onClick={() => setExportType("all")}
                  className={`p-3 rounded-xl border text-left transition-all ${
                    exportType === "all"
                      ? "bg-purple-600/10 border-purple-500/50 text-white shadow-sm font-bold"
                      : "bg-zinc-950/60 border-zinc-800 hover:bg-zinc-900 text-gray-400"
                  }`}
                >
                  <div className="text-xs font-bold text-white">Full Package</div>
                  <div className="text-[10px] text-gray-400 mt-1">Masters + Vouchers</div>
                </button>

                <button
                  type="button"
                  onClick={() => setExportType("vouchers")}
                  className={`p-3 rounded-xl border text-left transition-all ${
                    exportType === "vouchers"
                      ? "bg-purple-600/10 border-purple-500/50 text-white shadow-sm font-bold"
                      : "bg-zinc-950/60 border-zinc-800 hover:bg-zinc-900 text-gray-400"
                  }`}
                >
                  <div className="text-xs font-bold text-white">Vouchers Only</div>
                  <div className="text-[10px] text-gray-400 mt-1">Transactions & GST</div>
                </button>

                <button
                  type="button"
                  onClick={() => setExportType("masters")}
                  className={`p-3 rounded-xl border text-left transition-all ${
                    exportType === "masters"
                      ? "bg-purple-600/10 border-purple-500/50 text-white shadow-sm font-bold"
                      : "bg-zinc-950/60 border-zinc-800 hover:bg-zinc-900 text-gray-400"
                  }`}
                >
                  <div className="text-xs font-bold text-white">Masters Only</div>
                  <div className="text-[10px] text-gray-400 mt-1">Ledgers & Products</div>
                </button>
              </div>
            </div>

            {/* Date Range Selection */}
            <div className="bg-card border border-border rounded-2xl p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-bold text-white flex items-center gap-2">
                  <Calendar className="w-4 h-4 text-blue-400" />
                  <span>2. Accounting Date Period</span>
                </h2>
                <div className="flex gap-1">
                  <button
                    onClick={() => setPreset("this_month")}
                    className="px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-gray-300 rounded text-[10px] font-semibold"
                  >
                    This Month
                  </button>
                  <button
                    onClick={() => setPreset("last_month")}
                    className="px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-gray-300 rounded text-[10px] font-semibold"
                  >
                    Last Month
                  </button>
                  <button
                    onClick={() => setPreset("fy")}
                    className="px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-gray-300 rounded text-[10px] font-semibold"
                  >
                    Current FY
                  </button>
                  <button
                    onClick={() => setPreset("all")}
                    className="px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-gray-300 rounded text-[10px] font-semibold"
                  >
                    All Time
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 text-xs">
                <div>
                  <label className="block text-gray-400 font-semibold mb-1">From Date</label>
                  <input
                    type="date"
                    value={fromDate}
                    onChange={(e) => setFromDate(e.target.value)}
                    className="w-full bg-zinc-900 border border-zinc-700 p-2.5 rounded-xl text-white focus:ring-2 focus:ring-purple-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-gray-400 font-semibold mb-1">To Date</label>
                  <input
                    type="date"
                    value={toDate}
                    onChange={(e) => setToDate(e.target.value)}
                    className="w-full bg-zinc-900 border border-zinc-700 p-2.5 rounded-xl text-white focus:ring-2 focus:ring-purple-500 focus:outline-none"
                  />
                </div>
              </div>
            </div>

            {/* Voucher Types Filter */}
            {exportType !== "masters" && (
              <div className="bg-card border border-border rounded-2xl p-5 space-y-3">
                <h2 className="text-sm font-bold text-white flex items-center gap-2">
                  <Layers className="w-4 h-4 text-green-400" />
                  <span>3. Filter Voucher Types</span>
                </h2>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {tallyVoucherOptions.map((opt) => {
                    const isSelected = selectedVchTypes.includes(opt.type);
                    return (
                      <div
                        key={opt.type}
                        onClick={() => toggleVoucherType(opt.type)}
                        className={`p-3 rounded-xl border flex items-center justify-between cursor-pointer transition-all ${
                          isSelected
                            ? "bg-zinc-900 border-purple-500/40 text-white"
                            : "bg-zinc-950/40 border-zinc-800/80 text-gray-500 hover:bg-zinc-900/40"
                        }`}
                      >
                        <div>
                          <div className={`text-xs font-bold ${isSelected ? "text-white" : "text-gray-400"}`}>
                            {opt.label}
                          </div>
                          <div className="text-[10px] text-gray-500">{opt.desc}</div>
                        </div>
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => {}}
                          className="w-4 h-4 rounded text-purple-600 bg-zinc-800 border-zinc-700"
                        />
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Right Column: Execution & Preview Box */}
          <div className="space-y-6">
            
            {/* Download Execution Card */}
            <div className="bg-card border border-border rounded-2xl p-5 space-y-5 shadow-xl">
              <div className="space-y-1">
                <h3 className="text-base font-bold text-white">Generate Tally XML</h3>
                <p className="text-xs text-gray-400">
                  Ready to compile your accounting records into standard &lt;ENVELOPE&gt; Tally schema.
                </p>
              </div>

              <div className="space-y-2.5 p-3.5 bg-zinc-950/80 rounded-xl border border-zinc-800 text-xs">
                <div className="flex justify-between text-gray-400">
                  <span>Export Scope:</span>
                  <span className="font-bold text-white uppercase font-mono">{exportType}</span>
                </div>
                <div className="flex justify-between text-gray-400">
                  <span>Date Range:</span>
                  <span className="font-mono text-gray-200">
                    {fromDate || "Start"} → {toDate || "Present"}
                  </span>
                </div>
                <div className="flex justify-between text-gray-400">
                  <span>Selected Vouchers:</span>
                  <span className="font-mono text-purple-400 font-bold">{selectedVchTypes.length} Types</span>
                </div>
                <div className="flex justify-between text-gray-400">
                  <span>Format:</span>
                  <span className="font-mono text-green-400 font-bold">XML (Tally XML 9.0)</span>
                </div>
              </div>

              <button
                onClick={handleDownload}
                disabled={downloading}
                className="w-full py-3.5 bg-purple-600 hover:bg-purple-700 text-white rounded-xl text-xs font-bold transition-all shadow-xl shadow-purple-600/20 flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
              >
                {downloading ? (
                  <>
                    <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                    <span>Compiling Tally XML...</span>
                  </>
                ) : (
                  <>
                    <Download className="w-4 h-4" />
                    <span>Download Tally XML (.xml)</span>
                  </>
                )}
              </button>

              <div className="text-[11px] text-gray-500 text-center leading-relaxed">
                Compatible with all versions of <strong>TallyPrime</strong>, <strong>Tally.ERP 9</strong>, and third-party CA audit tools.
              </div>
            </div>

            {/* Quick CA Guide Teaser Card */}
            <div className="p-4 bg-blue-950/20 border border-blue-500/30 rounded-2xl space-y-3">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-blue-400" />
                <span className="text-xs font-bold text-blue-300">Fast 2-Minute CA Import</span>
              </div>
              <p className="text-[11px] text-gray-300 leading-relaxed">
                Need to hand over books to your Chartered Accountant? Share this XML file alongside our step-by-step Tally import guide.
              </p>
              <button
                onClick={() => setIsGuideOpen(true)}
                className="text-xs font-bold text-blue-400 hover:text-blue-300 underline flex items-center gap-1 cursor-pointer"
              >
                <span>Read Step-by-Step Guide →</span>
              </button>
            </div>
          </div>
        </div>

        {/* Interactive CA Import Guide Modal */}
        {isGuideOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
            <div className="bg-card border border-border w-full max-w-2xl rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
              
              <div className="px-6 py-4 border-b border-border bg-zinc-950 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-blue-600/20 text-blue-400 flex items-center justify-center border border-blue-500/30">
                    <BookOpen className="w-4 h-4" />
                  </div>
                  <div>
                    <h2 className="text-sm font-bold text-white">How to Import into TallyPrime (CA Guide)</h2>
                    <div className="text-[11px] text-gray-400">Official Step-by-Step Checklist for Auditors & Accountants</div>
                  </div>
                </div>
                <button
                  onClick={() => setIsGuideOpen(false)}
                  className="p-1 text-gray-400 hover:text-white rounded-lg hover:bg-zinc-800"
                >
                  ✕
                </button>
              </div>

              <div className="p-6 overflow-y-auto space-y-4 text-xs">
                
                <div className="space-y-3">
                  {guideSteps.map((s) => (
                    <div key={s.step} className="p-3.5 bg-zinc-950/60 rounded-xl border border-zinc-800 flex gap-3.5 items-start">
                      <div className="w-6 h-6 rounded-full bg-blue-600/20 text-blue-400 font-bold flex items-center justify-center shrink-0 text-xs border border-blue-500/30">
                        {s.step}
                      </div>
                      <div className="flex-1 space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-white text-xs">{s.title}</span>
                          {s.shortcut && (
                            <button
                              onClick={() => copyToClipboard(s.shortcut!, s.step)}
                              className="px-2 py-0.5 bg-zinc-800 hover:bg-zinc-700 text-blue-400 rounded font-mono text-[10px] flex items-center gap-1 border border-zinc-700 transition-colors"
                              title="Copy shortcut"
                            >
                              <span>{s.shortcut}</span>
                              {copiedKey === s.step ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3 text-gray-400" />}
                            </button>
                          )}
                        </div>
                        <p className="text-[11px] text-gray-400 leading-relaxed">
                          {s.desc}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl text-amber-300 text-[11px] leading-relaxed flex items-start gap-2">
                  <Info className="w-4 h-4 shrink-0 mt-0.5 text-amber-400" />
                  <div>
                    <strong>Pro Tip for Auditors:</strong> If your Tally company already contains existing ledgers with differing names, import <em>Masters</em> first or map the ledger names to avoid duplicate ledger creation in Tally.
                  </div>
                </div>
              </div>

              <div className="px-6 py-4 border-t border-border bg-zinc-950 flex items-center justify-between">
                <button
                  onClick={() => setIsGuideOpen(false)}
                  className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-gray-300 rounded-lg text-xs font-semibold"
                >
                  Close Guide
                </button>
                <button
                  onClick={() => {
                    setIsGuideOpen(false);
                    handleDownload();
                  }}
                  className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-xs font-bold shadow-md flex items-center gap-1.5"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Download XML Now</span>
                </button>
              </div>
            </div>
          </div>
        )}

      </div>
    </DashboardLayout>
  );
}
