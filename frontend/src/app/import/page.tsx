"use client";

import React, { useState, useRef, useEffect } from "react";
import axios from "axios";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import * as XLSX from "xlsx";
import DashboardLayout from "@/components/DashboardLayout";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken } from "@/utils/auth";
import { useToast } from "@/context/ToastContext";
import { useCompany } from "@/context/CompanyContext";
import {
  UploadCloud,
  FileSpreadsheet,
  FileCode2,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Sparkles,
  ArrowRight,
  Download,
  Users,
  Boxes,
  Scale,
  ShieldCheck,
  Building2,
  Check,
  ChevronRight,
  HelpCircle,
  Database,
  Sliders,
  Layers,
  Info,
  X,
} from "lucide-react";

interface PreviewData {
  platform: string;
  entity_type: string;
  total_detected: number;
  valid_records: number;
  duplicate_records: number;
  preview_samples: any[];
  equilibrium?: {
    total_debits: number;
    total_credits: number;
    difference: number;
    is_balanced: boolean;
  };
  summary_text?: string;
  status: string;
}

function UniversalImportContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const isWelcome = searchParams.get("welcome") === "1";
  const entityParam = searchParams.get("entity") || searchParams.get("type");

  const { toast } = useToast();
  const { activeCompany } = useCompany();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [importing, setImporting] = useState(false);

  const [parsedInfo, setParsedInfo] = useState<any>(null);
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [customMappings, setCustomMappings] = useState<Record<string, string>>({});
  const [duplicateStrategy, setDuplicateStrategy] = useState<"MERGE" | "SKIP">("MERGE");
  const [importSuccess, setImportSuccess] = useState<any>(null);

  // Clear states when file is removed
  const resetUpload = () => {
    setSelectedFile(null);
    setParsedInfo(null);
    setPreview(null);
    setCustomMappings({});
    setImportSuccess(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFileSelected(e.target.files[0]);
    }
  };

  const handleFileSelected = async (file: File) => {
    setSelectedFile(file);
    setAnalyzing(true);
    setImportSuccess(null);

    const token = getAccessToken();
    const formData = new FormData();
    formData.append("file", file);
    if (activeCompany?.id) {
      formData.append("company_id", activeCompany.id);
    }

    try {
      const res = await axios.post(`${API_BASE_URL}/api/v1/accounting/import/preview/`, formData, {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "multipart/form-data",
        },
      });

      if (res.data.success) {
        setParsedInfo(res.data.parsed_info);
        setPreview(res.data.preview);
        setCustomMappings(res.data.parsed_info?.mapped_columns || {});
        toast.success(
          "File Analyzed Successfully",
          res.data.parsed_info?.summary_text || `Detected ${res.data.parsed_info?.platform} format`
        );
      } else {
        toast.error("Analysis Failed", res.data.error || "Unable to parse file.");
        resetUpload();
      }
    } catch (err: any) {
      console.error(err);
      toast.error(
        "File Error",
        err.response?.data?.error || "Could not read this file format. Please check the template."
      );
      resetUpload();
    } finally {
      setAnalyzing(false);
    }
  };

  const handleExecuteImport = async () => {
    if (!selectedFile) return;
    setImporting(true);

    const token = getAccessToken();
    const formData = new FormData();
    formData.append("file", selectedFile);
    if (activeCompany?.id) {
      formData.append("company_id", activeCompany.id);
    }
    formData.append("duplicate_strategy", duplicateStrategy);
    if (Object.keys(customMappings).length > 0) {
      formData.append("custom_mappings", JSON.stringify(customMappings));
    }

    try {
      const res = await axios.post(`${API_BASE_URL}/api/v1/accounting/import/execute/`, formData, {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "multipart/form-data",
        },
      });

      if (res.data.success) {
        setImportSuccess(res.data);
        toast.success("Import Complete!", res.data.message || `Imported ${res.data.created_count} records.`);
      } else {
        toast.error("Import Failed", res.data.error || "Failed to import records.");
      }
    } catch (err: any) {
      console.error(err);
      toast.error(
        "Execution Error",
        err.response?.data?.error || "An error occurred while saving the imported data."
      );
    } finally {
      setImporting(false);
    }
  };

  const handleDownloadTemplate = (type: "parties" | "inventory" | "trial_balance") => {
    const token = getAccessToken();
    window.open(`${API_BASE_URL}/api/v1/accounting/import/templates/?type=${type}`, "_blank");
  };

  return (
    <DashboardLayout>
      <div className="max-w-6xl mx-auto space-y-8 pb-16">
        
        {/* Welcome Header for Newly Registered Users */}
        {isWelcome && (
          <div className="bg-gradient-to-r from-blue-600/15 via-primary/10 to-purple-600/15 border border-primary/20 rounded-2xl p-6 sm:p-8 relative overflow-hidden">
            <div className="max-w-2xl space-y-2 relative z-10">
              <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-primary/20 text-primary border border-primary/30">
                <Sparkles className="w-3.5 h-3.5" />
                <span>Quick Onboarding Setup</span>
              </div>
              <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-foreground">
                Welcome to ShriLekh, {activeCompany?.name || "Partner"}!
              </h1>
              <p className="text-sm text-muted-foreground leading-relaxed">
                Migrating from another software? You don&apos;t have to type your customers or stock again. 
                Upload your export file below from <strong>Tally</strong>, <strong>Vyapar</strong>, <strong>myBillBook</strong>, or <strong>Zoho Books</strong> and start invoicing immediately.
              </p>
            </div>
          </div>
        )}

        {/* Regular Header */}
        {!isWelcome && (
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/40 pb-5">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <Database className="w-5 h-5 text-primary" />
                <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-foreground">
                  Universal Import & Migration Hub
                </h1>
              </div>
              <p className="text-xs sm:text-sm text-muted-foreground">
                One-click ingestion for Tally XML, Vyapar, myBillBook, Zoho Books, Busy, and Custom Excel sheets.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => handleDownloadTemplate("parties")}
                className="px-3 py-1.5 rounded-lg text-xs font-medium border border-border/60 hover:bg-muted/60 transition-colors flex items-center gap-1.5 text-foreground cursor-pointer"
                title="Download Clean Customers & Suppliers Template"
              >
                <Download className="w-3.5 h-3.5 text-muted-foreground" />
                <span>Parties Template</span>
              </button>
              <button
                onClick={() => handleDownloadTemplate("inventory")}
                className="px-3 py-1.5 rounded-lg text-xs font-medium border border-border/60 hover:bg-muted/60 transition-colors flex items-center gap-1.5 text-foreground cursor-pointer"
                title="Download Clean Stock Items Template"
              >
                <Download className="w-3.5 h-3.5 text-muted-foreground" />
                <span>Stock Template</span>
              </button>
            </div>
          </div>
        )}

        {/* Supported Platforms Hero Bar */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {[
            { name: "TallyPrime / ERP 9", ext: ".xml / .xlsx", color: "text-amber-500 bg-amber-500/10 border-amber-500/20" },
            { name: "Vyapar", ext: ".xlsx / .csv", color: "text-blue-500 bg-blue-500/10 border-blue-500/20" },
            { name: "myBillBook", ext: ".xlsx", color: "text-emerald-500 bg-emerald-500/10 border-emerald-500/20" },
            { name: "Zoho Books", ext: ".csv / .xlsx", color: "text-rose-500 bg-rose-500/10 border-rose-500/20" },
            { name: "Busy / Marg", ext: ".xlsx", color: "text-purple-500 bg-purple-500/10 border-purple-500/20" },
            { name: "Custom Excel", ext: "All Spreadsheets", color: "text-cyan-500 bg-cyan-500/10 border-cyan-500/20" },
          ].map((item, idx) => (
            <div key={idx} className={`p-3 rounded-xl border flex flex-col justify-between ${item.color}`}>
              <div className="font-bold text-xs">{item.name}</div>
              <div className="text-[10px] opacity-75 font-mono mt-1">{item.ext}</div>
            </div>
          ))}
        </div>

        {/* Success Report Modal / Card */}
        {importSuccess && (
          <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-2xl p-6 sm:p-8 space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 flex items-center justify-center shrink-0">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-foreground">Import Completed Successfully!</h3>
                <p className="text-xs text-muted-foreground">{importSuccess.message}</p>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
              <div className="bg-card p-3 rounded-xl border border-border/40 text-center">
                <div className="text-2xl font-bold font-mono text-emerald-600 dark:text-emerald-400">
                  {importSuccess.created_count ?? 0}
                </div>
                <div className="text-[11px] text-muted-foreground mt-0.5">New Records Created</div>
              </div>
              <div className="bg-card p-3 rounded-xl border border-border/40 text-center">
                <div className="text-2xl font-bold font-mono text-blue-600 dark:text-blue-400">
                  {importSuccess.merged_count ?? 0}
                </div>
                <div className="text-[11px] text-muted-foreground mt-0.5">Existing Merged</div>
              </div>
              <div className="bg-card p-3 rounded-xl border border-border/40 text-center">
                <div className="text-2xl font-bold font-mono text-muted-foreground">
                  {importSuccess.skipped_count ?? 0}
                </div>
                <div className="text-[11px] text-muted-foreground mt-0.5">Skipped</div>
              </div>
              <div className="bg-card p-3 rounded-xl border border-border/40 text-center">
                <div className="text-2xl font-bold font-mono text-foreground">
                  {importSuccess.total_processed ?? (importSuccess.created_count + importSuccess.merged_count)}
                </div>
                <div className="text-[11px] text-muted-foreground mt-0.5">Total Processed</div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3 pt-4 border-t border-emerald-500/20">
              <Link
                href="/parties"
                className="px-4 py-2 bg-primary text-primary-foreground font-semibold rounded-lg text-xs hover:opacity-90 transition-opacity flex items-center gap-1.5"
              >
                <Users className="w-3.5 h-3.5" />
                <span>View Parties Directory</span>
              </Link>
              <Link
                href="/inventory"
                className="px-4 py-2 bg-secondary text-secondary-foreground font-semibold rounded-lg text-xs hover:bg-secondary/80 transition-colors flex items-center gap-1.5"
              >
                <Boxes className="w-3.5 h-3.5" />
                <span>View Stock & Inventory</span>
              </Link>
              <Link
                href="/dashboard"
                className="px-4 py-2 border border-border rounded-lg text-xs hover:bg-muted/50 transition-colors text-foreground"
              >
                Go to Dashboard
              </Link>
              <button
                onClick={resetUpload}
                className="ml-auto text-xs text-primary hover:underline cursor-pointer"
              >
                Import Another File
              </button>
            </div>
          </div>
        )}

        {/* Upload Zone */}
        {!importSuccess && !preview && (
          <div
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-2xl p-8 sm:p-14 text-center transition-all ${
              dragActive
                ? "border-primary bg-primary/5 scale-[1.01]"
                : "border-border/80 hover:border-primary/50 bg-card/60"
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xls,.csv,.xml"
              onChange={handleFileChange}
              className="hidden"
            />

            <div className="flex flex-col items-center justify-center space-y-4 max-w-md mx-auto">
              <div className="w-16 h-16 rounded-2xl bg-primary/10 text-primary flex items-center justify-center shadow-inner">
                {analyzing ? (
                  <RefreshCw className="w-8 h-8 animate-spin" />
                ) : (
                  <UploadCloud className="w-8 h-8" />
                )}
              </div>

              <div>
                <h3 className="text-lg font-bold text-foreground">
                  {analyzing ? "Analyzing File Structure..." : "Drop your export file here"}
                </h3>
                <p className="text-xs text-muted-foreground mt-1">
                  Supports Tally XML, Vyapar / myBillBook / Zoho Excel reports, or custom CSV
                </p>
              </div>

              <button
                type="button"
                disabled={analyzing}
                onClick={() => fileInputRef.current?.click()}
                className="px-6 py-2.5 rounded-xl bg-primary text-primary-foreground font-semibold text-xs shadow-md hover:opacity-90 transition-all cursor-pointer disabled:opacity-50"
              >
                {analyzing ? "Reading Headers..." : "Browse File from Computer"}
              </button>

              <div className="text-[11px] text-muted-foreground/80 flex items-center gap-2 pt-2">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
                <span>Zero Risk: Pre-flight audit lets you preview all data before saving</span>
              </div>
            </div>
          </div>
        )}

        {/* Pre-Flight Preview & Column Mapper */}
        {preview && !importSuccess && (
          <div className="space-y-6 animate-in fade-in duration-200">
            {/* Detection Summary Header */}
            <div className="bg-card border border-border/60 rounded-2xl p-5 sm:p-6 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-xl bg-primary/10 text-primary flex items-center justify-center font-bold text-sm shrink-0">
                  {parsedInfo?.file_type === "XML" ? <FileCode2 className="w-6 h-6" /> : <FileSpreadsheet className="w-6 h-6" />}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-base font-bold text-foreground">
                      {parsedInfo?.summary_text || `${preview.platform} File`}
                    </span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-primary/10 text-primary uppercase">
                      {preview.platform}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    File: <span className="font-mono text-foreground font-medium">{selectedFile?.name}</span> • {preview.total_detected} total rows identified
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={resetUpload}
                  className="px-3 py-1.5 rounded-lg text-xs border border-border hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                >
                  Change File
                </button>
              </div>
            </div>

            {/* Equilibrium Audit Card (if available) */}
            {preview.equilibrium && (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="p-4 rounded-xl border border-border/50 bg-card">
                  <div className="text-xs text-muted-foreground font-medium">Total Opening Debits (Receivable)</div>
                  <div className="text-xl font-bold font-mono text-emerald-600 dark:text-emerald-400 mt-1">
                    ₹{preview.equilibrium.total_debits.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </div>
                </div>
                <div className="p-4 rounded-xl border border-border/50 bg-card">
                  <div className="text-xs text-muted-foreground font-medium">Total Opening Credits (Payable)</div>
                  <div className="text-xl font-bold font-mono text-blue-600 dark:text-blue-400 mt-1">
                    ₹{preview.equilibrium.total_credits.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </div>
                </div>
                <div className="p-4 rounded-xl border border-border/50 bg-card">
                  <div className="text-xs text-muted-foreground font-medium">Equilibrium Status</div>
                  <div className="flex items-center gap-1.5 mt-1">
                    {preview.equilibrium.is_balanced ? (
                      <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                        <CheckCircle2 className="w-4 h-4" /> Balanced Dr == Cr
                      </span>
                    ) : (
                      <span className="text-xs font-bold text-amber-500 flex items-center gap-1">
                        <Scale className="w-4 h-4" /> Difference: ₹{Math.abs(preview.equilibrium.difference).toFixed(2)}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Duplicate Strategy Settings */}
            <div className="bg-card border border-border/60 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
              <div>
                <span className="font-semibold text-foreground">Duplicate Conflict Handling:</span>
                <p className="text-muted-foreground text-[11px] mt-0.5">
                  Detected {preview.duplicate_records} records that already exist in your ShriLekh company.
                </p>
              </div>
              <div className="inline-flex bg-muted/60 p-1 rounded-lg border border-border/40">
                <button
                  type="button"
                  onClick={() => setDuplicateStrategy("MERGE")}
                  className={`px-3 py-1 rounded-md font-medium transition-all cursor-pointer ${
                    duplicateStrategy === "MERGE"
                      ? "bg-primary text-primary-foreground shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  Merge / Update Missing
                </button>
                <button
                  type="button"
                  onClick={() => setDuplicateStrategy("SKIP")}
                  className={`px-3 py-1 rounded-md font-medium transition-all cursor-pointer ${
                    duplicateStrategy === "SKIP"
                      ? "bg-primary text-primary-foreground shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  Skip Existing
                </button>
              </div>
            </div>

            {/* Data Preview Table */}
            <div className="bg-card border border-border/60 rounded-2xl overflow-hidden shadow-sm">
              <div className="px-5 py-3 border-b border-border/40 flex items-center justify-between">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Pre-Flight Data Preview (First {preview.preview_samples?.length || 0} Records)
                </h4>
                <span className="text-xs text-muted-foreground">
                  {preview.valid_records} ready to import • {preview.duplicate_records} existing
                </span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-muted/40 text-muted-foreground border-b border-border/40 font-semibold">
                    <tr>
                      <th className="px-4 py-2.5">#</th>
                      <th className="px-4 py-2.5">Name</th>
                      {preview.entity_type === "PARTIES" ? (
                        <>
                          <th className="px-4 py-2.5">Phone</th>
                          <th className="px-4 py-2.5">GSTIN</th>
                          <th className="px-4 py-2.5 text-right">Opening Balance</th>
                          <th className="px-4 py-2.5">Type</th>
                        </>
                      ) : (
                        <>
                          <th className="px-4 py-2.5">SKU / Code</th>
                          <th className="px-4 py-2.5 text-right">Sale Price</th>
                          <th className="px-4 py-2.5 text-right">Purchase Price</th>
                          <th className="px-4 py-2.5 text-right">Opening Qty</th>
                          <th className="px-4 py-2.5">Unit</th>
                        </>
                      )}
                      <th className="px-4 py-2.5 text-center">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/30">
                    {preview.preview_samples?.map((row: any, idx: number) => (
                      <tr key={idx} className="hover:bg-muted/30 transition-colors">
                        <td className="px-4 py-2.5 font-mono text-muted-foreground">{row.row_num || idx + 1}</td>
                        <td className="px-4 py-2.5 font-medium text-foreground">{row.name}</td>
                        {preview.entity_type === "PARTIES" ? (
                          <>
                            <td className="px-4 py-2.5 font-mono text-muted-foreground">{row.phone || "—"}</td>
                            <td className="px-4 py-2.5 font-mono">{row.gstin || "—"}</td>
                            <td className="px-4 py-2.5 font-mono text-right font-medium">
                              ₹{(row.opening_balance || 0).toFixed(2)}
                            </td>
                            <td className="px-4 py-2.5">
                              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                row.balance_type === "DEBIT"
                                  ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                                  : "bg-blue-500/10 text-blue-600 dark:text-blue-400"
                              }`}>
                                {row.balance_type === "DEBIT" ? "Customer (Dr)" : "Supplier (Cr)"}
                              </span>
                            </td>
                          </>
                        ) : (
                          <>
                            <td className="px-4 py-2.5 font-mono text-muted-foreground">{row.sku || "—"}</td>
                            <td className="px-4 py-2.5 font-mono text-right font-medium">₹{(row.sale_price || 0).toFixed(2)}</td>
                            <td className="px-4 py-2.5 font-mono text-right text-muted-foreground">₹{(row.purchase_price || 0).toFixed(2)}</td>
                            <td className="px-4 py-2.5 font-mono text-right font-bold text-foreground">{row.opening_qty || 0}</td>
                            <td className="px-4 py-2.5 text-muted-foreground">{row.unit || "PCS"}</td>
                          </>
                        )}
                        <td className="px-4 py-2.5 text-center">
                          {row.is_duplicate ? (
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/10 text-amber-500 border border-amber-500/20">
                              Merge
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                              New
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Ingestion Action Footer */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-4 border-t border-border/40">
              <div className="text-xs text-muted-foreground">
                Clicking &quot;Confirm &amp; Import&quot; will write these records directly into your active company books.
              </div>

              <div className="flex items-center gap-3 w-full sm:w-auto">
                <button
                  type="button"
                  onClick={resetUpload}
                  disabled={importing}
                  className="px-4 py-2.5 rounded-xl border border-border text-xs font-semibold hover:bg-muted transition-colors cursor-pointer w-full sm:w-auto"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleExecuteImport}
                  disabled={importing}
                  className="px-6 py-2.5 rounded-xl bg-primary text-primary-foreground text-xs font-bold shadow-lg hover:opacity-90 transition-all flex items-center justify-center gap-2 cursor-pointer w-full sm:w-auto disabled:opacity-50"
                >
                  {importing ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Writing to Database...</span>
                    </>
                  ) : (
                    <>
                      <Check className="w-4 h-4" />
                      <span>Confirm &amp; Import All Records</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}

export default function UniversalImportPage() {
  return (
    <React.Suspense
      fallback={
        <DashboardLayout>
          <div className="flex flex-col items-center justify-center min-h-[400px] space-y-3">
            <div className="w-9 h-9 border-3 border-primary border-t-transparent rounded-full animate-spin"></div>
            <div className="text-sm text-muted-foreground font-medium">Loading Universal Import Hub...</div>
          </div>
        </DashboardLayout>
      }
    >
      <UniversalImportContent />
    </React.Suspense>
  );
}
