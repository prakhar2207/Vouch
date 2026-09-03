"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useState, useEffect, useRef, useMemo, useCallback, Suspense } from "react";
import axios from "axios";
import { useRouter, useSearchParams } from "next/navigation";
import { AgGridReact } from "ag-grid-react";
import { ColDef, GridApi, GridReadyEvent, AllCommunityModule, ModuleRegistry } from "ag-grid-community";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import DashboardLayout from "@/components/DashboardLayout";
import { useShortcuts } from "@/context/ShortcutContext";
import {
  Layers,
  Plus,
  Trash2,
  CheckCircle2,
  AlertCircle,
  Calendar,
  Scale,
  Zap,
  Tag,
  Hash,
  FileText,
  ArrowUpRight,
  ArrowDownLeft,
} from "lucide-react";

ModuleRegistry.registerModules([AllCommunityModule]);

interface RowData {
  id: string;
  type: "Dr" | "Cr";
  ledger_id: string;
  ledger_name: string;
  debit_amount: number;
  credit_amount: number;
  narration: string;
}

const VOUCHER_TYPE_STYLES: Record<string, { label: string; badge: string; desc: string }> = {
  JOURNAL: {
    label: "Journal (F7)",
    badge: "bg-purple-500/15 text-purple-400 border-purple-500/30",
    desc: "General adjustments, asset purchases, non-cash entries",
  },
  PAYMENT: {
    label: "Payment (F5)",
    badge: "bg-amber-500/15 text-amber-400 border-amber-500/30",
    desc: "Payments to vendors, expenses, or cash withdrawals",
  },
  RECEIPT: {
    label: "Receipt (F6)",
    badge: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
    desc: "Inward customer receipts, income, or capital injections",
  },
  CONTRA: {
    label: "Contra (F4)",
    badge: "bg-blue-500/15 text-blue-400 border-blue-500/30",
    desc: "Bank to cash, cash to bank, or bank-to-bank transfers",
  },
  SALES: {
    label: "Sales (F8)",
    badge: "bg-sky-500/15 text-sky-400 border-sky-500/30",
    desc: "Accounting entries for customer invoices & GST output",
  },
  PURCHASE: {
    label: "Purchase (F9)",
    badge: "bg-rose-500/15 text-rose-400 border-rose-500/30",
    desc: "Vendor inward purchase ledger postings & input credit",
  },
};

function AgGridVoucherEntryContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { workingDate, registerSaveHandler, registerAltCCallback } = useShortcuts();

  const [companyId, setCompanyId] = useState<string>("");
  const [ledgers, setLedgers] = useState<any[]>([]);
  const [voucherType, setVoucherType] = useState<string>(searchParams?.get("type") || "JOURNAL");
  const [voucherDate, setVoucherDate] = useState<string>(workingDate || new Date().toISOString().split("T")[0]);
  const [voucherNumber, setVoucherNumber] = useState<string>("");
  const [mainNarration, setMainNarration] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const gridApiRef = useRef<GridApi | null>(null);

  const [rowData, setRowData] = useState<RowData[]>([
    { id: "1", type: "Dr", ledger_id: "", ledger_name: "", debit_amount: 0, credit_amount: 0, narration: "" },
    { id: "2", type: "Cr", ledger_id: "", ledger_name: "", debit_amount: 0, credit_amount: 0, narration: "" },
  ]);

  useEffect(() => {
    const typeParam = searchParams?.get("type");
    if (typeParam) {
      setVoucherType(typeParam.toUpperCase());
    }
  }, [searchParams]);

  useEffect(() => {
    if (workingDate) {
      setVoucherDate(workingDate);
    }
  }, [workingDate]);

  useEffect(() => {
    registerAltCCallback((newEntity: any) => {
      if (newEntity) {
        setLedgers((prev) => [...prev, newEntity]);
      }
    });
  }, [registerAltCCallback]);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }
    fetchLedgers();
  }, [router]);

  const fetchLedgers = async () => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const cid = compRes.data.data?.[0]?.id;
      if (!cid) return;
      setCompanyId(cid);

      const ledgersRes = await axios.get(`${API_BASE_URL}/api/v1/ledgers/${cid}/`, { headers });
      setLedgers(ledgersRes.data.data || []);
    } catch (err) {
      console.error(err);
    }
  };

  const ledgerNames = useMemo(() => ledgers.map((l) => l.name), [ledgers]);

  const totalDebit = useMemo(() => {
    return rowData.reduce((sum, row) => sum + (Number(row.debit_amount) || 0), 0);
  }, [rowData]);

  const totalCredit = useMemo(() => {
    return rowData.reduce((sum, row) => sum + (Number(row.credit_amount) || 0), 0);
  }, [rowData]);

  const difference = useMemo(() => {
    return Math.abs(totalDebit - totalCredit);
  }, [totalDebit, totalCredit]);

  const isBalanced = totalDebit > 0 && totalCredit > 0 && difference === 0;

  const onGridReady = useCallback((params: GridReadyEvent) => {
    gridApiRef.current = params.api;
  }, []);

  const addRow = useCallback(() => {
    const newId = String(Date.now());
    const lastRow = rowData[rowData.length - 1];
    const newType = lastRow?.type === "Dr" ? "Cr" : "Dr";
    const diff = Math.abs(totalDebit - totalCredit);

    const newRow: RowData = {
      id: newId,
      type: newType,
      ledger_id: "",
      ledger_name: "",
      debit_amount: newType === "Dr" && totalCredit > totalDebit ? diff : 0,
      credit_amount: newType === "Cr" && totalDebit > totalCredit ? diff : 0,
      narration: "",
    };

    setRowData((prev) => [...prev, newRow]);
  }, [rowData, totalDebit, totalCredit]);

  const autoBalance = useCallback(() => {
    if (isBalanced) return;
    const diff = Math.abs(totalDebit - totalCredit);
    if (diff === 0) return;

    if (totalDebit > totalCredit) {
      const lastCrIndex = [...rowData].reverse().findIndex((r) => r.type === "Cr");
      if (lastCrIndex !== -1) {
        const actualIndex = rowData.length - 1 - lastCrIndex;
        const updated = [...rowData];
        updated[actualIndex].credit_amount = Number((updated[actualIndex].credit_amount + diff).toFixed(2));
        setRowData(updated);
      } else {
        setRowData((prev) => [
          ...prev,
          { id: String(Date.now()), type: "Cr", ledger_id: "", ledger_name: "", debit_amount: 0, credit_amount: diff, narration: "Balancing figure" }
        ]);
      }
    } else {
      const lastDrIndex = [...rowData].reverse().findIndex((r) => r.type === "Dr");
      if (lastDrIndex !== -1) {
        const actualIndex = rowData.length - 1 - lastDrIndex;
        const updated = [...rowData];
        updated[actualIndex].debit_amount = Number((updated[actualIndex].debit_amount + diff).toFixed(2));
        setRowData(updated);
      } else {
        setRowData((prev) => [
          ...prev,
          { id: String(Date.now()), type: "Dr", ledger_id: "", ledger_name: "", debit_amount: diff, credit_amount: 0, narration: "Balancing figure" }
        ]);
      }
    }
  }, [isBalanced, totalDebit, totalCredit, rowData]);

  const removeRow = useCallback((index: number) => {
    if (rowData.length <= 2) return;
    setRowData((prev) => prev.filter((_, i) => i !== index));
  }, [rowData.length]);

  const applyTemplate = (type: string) => {
    const cashLedger = ledgers.find((l) => l.name.toLowerCase().includes("cash"))?.name || ledgers[0]?.name || "";
    const bankLedger = ledgers.find((l) => l.name.toLowerCase().includes("bank") || l.name.toLowerCase().includes("hdfc"))?.name || ledgers[1]?.name || "";

    if (type === "CONTRA_DEPOSIT") {
      setVoucherType("CONTRA");
      setMainNarration("Cash deposited into bank account");
      setRowData([
        { id: "1", type: "Dr", ledger_id: "", ledger_name: bankLedger, debit_amount: 0, credit_amount: 0, narration: "To Bank A/c" },
        { id: "2", type: "Cr", ledger_id: "", ledger_name: cashLedger, debit_amount: 0, credit_amount: 0, narration: "By Cash in hand" },
      ]);
    } else if (type === "VENDOR_PAYMENT") {
      setVoucherType("PAYMENT");
      setMainNarration("Payment made to vendor / supplier");
      setRowData([
        { id: "1", type: "Dr", ledger_id: "", ledger_name: "", debit_amount: 0, credit_amount: 0, narration: "Supplier Ledger" },
        { id: "2", type: "Cr", ledger_id: "", ledger_name: bankLedger || cashLedger, debit_amount: 0, credit_amount: 0, narration: "Bank Transfer" },
      ]);
    } else if (type === "CUSTOMER_RECEIPT") {
      setVoucherType("RECEIPT");
      setMainNarration("Received payment from customer");
      setRowData([
        { id: "1", type: "Dr", ledger_id: "", ledger_name: bankLedger || cashLedger, debit_amount: 0, credit_amount: 0, narration: "Bank Inflow" },
        { id: "2", type: "Cr", ledger_id: "", ledger_name: "", debit_amount: 0, credit_amount: 0, narration: "Customer Ledger" },
      ]);
    } else if (type === "EXPENSE_JOURNAL") {
      setVoucherType("JOURNAL");
      setMainNarration("Operating expense provision / adjustment");
      setRowData([
        { id: "1", type: "Dr", ledger_id: "", ledger_name: "", debit_amount: 0, credit_amount: 0, narration: "Expense Account" },
        { id: "2", type: "Cr", ledger_id: "", ledger_name: "", debit_amount: 0, credit_amount: 0, narration: "Payable / Bank" },
      ]);
    }
  };

  const columnDefs = useMemo<ColDef[]>(
    () => [
      {
        headerName: "#",
        valueGetter: "node.rowIndex + 1",
        width: 55,
        pinned: "left",
        cellClass: "text-center font-mono font-bold text-zinc-400 text-xs flex items-center justify-center",
        headerClass: "text-center",
      },
      {
        field: "type",
        headerName: "Polarity",
        width: 105,
        editable: true,
        cellEditor: "agSelectCellEditor",
        cellEditorParams: {
          values: ["Dr", "Cr"],
        },
        cellRenderer: (params: any) => {
          const isDr = params.value === "Dr";
          return (
            <div className="flex items-center h-full">
              <span
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-black tracking-wider shadow-sm ${
                  isDr
                    ? "bg-blue-500/20 text-blue-400 border border-blue-500/40"
                    : "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
                }`}
              >
                {isDr ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownLeft className="w-3 h-3" />}
                {params.value}
              </span>
            </div>
          );
        },
        onCellValueChanged: (params) => {
          const idx = params.node?.rowIndex;
          if (idx === undefined || idx === null) return;
          const updated = [...rowData];
          const row = updated[idx];
          if (!row) return;
          row.type = params.newValue;
          if (row.type === "Dr") {
            row.debit_amount = row.credit_amount || row.debit_amount;
            row.credit_amount = 0;
          } else {
            row.credit_amount = row.debit_amount || row.credit_amount;
            row.debit_amount = 0;
          }
          setRowData(updated);
        },
      },
      {
        field: "ledger_name",
        headerName: "Particulars (Ledger Account)",
        flex: 2.5,
        editable: true,
        cellEditor: "agSelectCellEditor",
        cellEditorParams: {
          values: ledgerNames,
        },
        cellRenderer: (params: any) => {
          if (!params.value) {
            return <span className="text-zinc-500 italic text-xs">Press Enter to select ledger account...</span>;
          }
          return (
            <div className="flex items-center gap-2 h-full font-semibold text-zinc-100">
              <span className="w-2 h-2 rounded-full bg-blue-400 shrink-0"></span>
              <span className="truncate">{params.value}</span>
            </div>
          );
        },
        onCellValueChanged: (params) => {
          const idx = params.node?.rowIndex;
          if (idx === undefined || idx === null) return;
          const selected = ledgers.find((l) => l.name === params.newValue);
          const updated = [...rowData];
          const row = updated[idx];
          if (!row) return;
          row.ledger_name = params.newValue;
          row.ledger_id = selected ? selected.id : "";
          setRowData(updated);
        },
      },
      {
        field: "debit_amount",
        headerName: "Debit (₹)",
        flex: 1.2,
        editable: (params) => params.data.type === "Dr",
        valueFormatter: (params) => (params.value ? Number(params.value).toLocaleString("en-IN", { minimumFractionDigits: 2 }) : ""),
        cellClass: "text-right font-mono font-bold text-blue-400 flex items-center justify-end pr-4",
        headerClass: "text-right pr-4",
        onCellValueChanged: (params) => {
          const idx = params.node?.rowIndex;
          if (idx === undefined || idx === null) return;
          const updated = [...rowData];
          if (!updated[idx]) return;
          const val = parseFloat(params.newValue) || 0;
          updated[idx].debit_amount = val;
          setRowData(updated);
        },
      },
      {
        field: "credit_amount",
        headerName: "Credit (₹)",
        flex: 1.2,
        editable: (params) => params.data.type === "Cr",
        valueFormatter: (params) => (params.value ? Number(params.value).toLocaleString("en-IN", { minimumFractionDigits: 2 }) : ""),
        cellClass: "text-right font-mono font-bold text-emerald-400 flex items-center justify-end pr-4",
        headerClass: "text-right pr-4",
        onCellValueChanged: (params) => {
          const idx = params.node?.rowIndex;
          if (idx === undefined || idx === null) return;
          const updated = [...rowData];
          if (!updated[idx]) return;
          const val = parseFloat(params.newValue) || 0;
          updated[idx].credit_amount = val;
          setRowData(updated);
        },
      },
      {
        field: "narration",
        headerName: "Row Narration",
        flex: 1.8,
        editable: true,
        cellRenderer: (params: any) => {
          if (!params.value) {
            return <span className="text-zinc-600 text-xs italic">Optional remark...</span>;
          }
          return <span className="text-xs text-zinc-300 truncate">{params.value}</span>;
        },
        onCellValueChanged: (params) => {
          const idx = params.node?.rowIndex;
          if (idx === undefined || idx === null) return;
          const updated = [...rowData];
          if (!updated[idx]) return;
          updated[idx].narration = params.newValue;
          setRowData(updated);
        },
      },
      {
        headerName: "",
        width: 50,
        pinned: "right",
        cellRenderer: (params: any) => {
          const idx = params.node?.rowIndex;
          return (
            <div className="flex items-center justify-center h-full">
              <button
                type="button"
                onClick={() => removeRow(idx)}
                disabled={rowData.length <= 2}
                title="Remove Row"
                className="p-1 text-zinc-500 hover:text-red-400 hover:bg-red-500/10 rounded transition-colors disabled:opacity-20 disabled:pointer-events-none cursor-pointer"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        },
      },
    ],
    [rowData, ledgers, ledgerNames, removeRow]
  );

  const handleSubmit = async () => {
    if (!isBalanced) {
      setStatusMessage({
        type: "error",
        text: `Voucher is unbalanced! Debit (₹${totalDebit.toFixed(2)}) must equal Credit (₹${totalCredit.toFixed(2)}). Difference: ₹${difference.toFixed(2)}.`,
      });
      return;
    }

    const invalidRow = rowData.find((r) => !r.ledger_id || (r.debit_amount === 0 && r.credit_amount === 0));
    if (invalidRow) {
      setStatusMessage({
        type: "error",
        text: "Please select a valid Ledger Account and enter an Amount for all active rows.",
      });
      return;
    }

    setSaving(true);
    setStatusMessage(null);

    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      const payload = {
        company_id: companyId,
        voucher_type: voucherType,
        voucher_date: voucherDate,
        voucher_number: voucherNumber || undefined,
        narration: mainNarration,
        entries: rowData.map((r) => ({
          ledger_id: r.ledger_id,
          debit_amount: r.debit_amount,
          credit_amount: r.credit_amount,
          narration: r.narration,
        })),
      };

      const res = await axios.post(`${API_BASE_URL}/api/vouchers/`, payload, { headers });

      setStatusMessage({
        type: "success",
        text: `Voucher #${res.data.voucher_number} posted successfully! Total: ₹${res.data.total_amount}`,
      });

      setRowData([
        { id: "1", type: "Dr", ledger_id: "", ledger_name: "", debit_amount: 0, credit_amount: 0, narration: "" },
        { id: "2", type: "Cr", ledger_id: "", ledger_name: "", debit_amount: 0, credit_amount: 0, narration: "" },
      ]);
      setVoucherNumber("");
      setMainNarration("");
    } catch (err: any) {
      setStatusMessage({
        type: "error",
        text: err.response?.data?.error || err.message || "Failed to post voucher.",
      });
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    return registerSaveHandler(handleSubmit);
  }, [registerSaveHandler, handleSubmit]);

  const typeConfig = VOUCHER_TYPE_STYLES[voucherType] || VOUCHER_TYPE_STYLES.JOURNAL;

  return (
    <DashboardLayout>
      <div className="h-[calc(100vh-5rem)] flex flex-col max-w-[1600px] mx-auto px-2 sm:px-4 py-2 gap-2.5 overflow-hidden">
        
        {/* Compact Header Bar */}
        <div className="bg-card border border-border/80 px-4 py-2.5 rounded-xl shadow-sm flex flex-wrap items-center justify-between gap-3 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-600 to-indigo-600 text-white flex items-center justify-center shadow-sm shrink-0">
              <Layers className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-black tracking-tight text-foreground">Quick Journal Entry</h1>
                <span className={`text-[10px] font-bold px-2 py-0.2 rounded-full border ${typeConfig.badge}`}>
                  {typeConfig.label}
                </span>
              </div>
              <p className="text-[11px] text-muted-foreground hidden sm:block">
                Double-entry spreadsheet engine. Navigate with <kbd className="px-1 py-0.2 bg-zinc-800 text-zinc-300 rounded border border-zinc-700 font-mono text-[9px]">Tab</kbd> / <kbd className="px-1 py-0.2 bg-zinc-800 text-zinc-300 rounded border border-zinc-700 font-mono text-[9px]">Enter</kbd>.
              </p>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="flex items-center gap-2">
            <button
              onClick={addRow}
              type="button"
              className="px-3 py-1.5 bg-secondary hover:bg-secondary/80 text-foreground rounded-lg text-xs font-bold border border-border transition-all flex items-center gap-1 shadow-sm cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5 text-blue-400" />
              <span>Add Line</span>
              <span className="text-[10px] text-muted-foreground font-mono ml-0.5">Alt+A</span>
            </button>

            {!isBalanced && difference > 0 && (
              <button
                onClick={autoBalance}
                type="button"
                className="px-3 py-1.5 bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 rounded-lg text-xs font-bold border border-amber-500/30 transition-all flex items-center gap-1 shadow-sm cursor-pointer"
                title="Auto-fill the difference into a balancing line"
              >
                <Scale className="w-3.5 h-3.5" />
                <span>Auto-Balance (₹{difference.toFixed(2)})</span>
              </button>
            )}

            <button
              onClick={handleSubmit}
              disabled={saving || !isBalanced}
              className={`px-4 py-1.5 rounded-lg text-xs font-bold shadow-sm transition-all flex items-center gap-1.5 cursor-pointer ${
                isBalanced
                  ? "bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white shadow-blue-600/25"
                  : "bg-zinc-800 text-zinc-500 border border-zinc-700 cursor-not-allowed opacity-60"
              }`}
            >
              {saving ? (
                <>
                  <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                  <span>Posting...</span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>Post Voucher</span>
                  <span className="text-[10px] font-mono px-1 py-0.2 bg-black/20 rounded">Ctrl+S</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Status Notification */}
        {statusMessage && (
          <div
            className={`px-3 py-2 rounded-lg border text-xs font-semibold flex items-center justify-between shrink-0 shadow-sm animate-in fade-in ${
              statusMessage.type === "success"
                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                : "bg-red-500/10 border-red-500/30 text-red-400"
            }`}
          >
            <div className="flex items-center gap-1.5">
              {statusMessage.type === "success" ? (
                <CheckCircle2 className="w-3.5 h-3.5 shrink-0 text-emerald-400" />
              ) : (
                <AlertCircle className="w-3.5 h-3.5 shrink-0 text-red-400" />
              )}
              <span>{statusMessage.text}</span>
            </div>
            <button onClick={() => setStatusMessage(null)} className="text-xs font-bold px-1.5 py-0.5">✕</button>
          </div>
        )}

        {/* Compact Metadata & Template Toolbar */}
        <div className="bg-card border border-border/80 px-3.5 py-2 rounded-xl shadow-sm grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2.5 items-center shrink-0">
          <div>
            <label className="block text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-1">Type</label>
            <select
              value={voucherType}
              onChange={(e) => setVoucherType(e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-700 text-white px-2 py-1.5 rounded-lg text-xs outline-none focus:ring-1 focus:ring-blue-500 font-semibold"
            >
              <option value="JOURNAL">Journal (F7)</option>
              <option value="PAYMENT">Payment (F5)</option>
              <option value="RECEIPT">Receipt (F6)</option>
              <option value="CONTRA">Contra (F4)</option>
              <option value="SALES">Sales (F8)</option>
              <option value="PURCHASE">Purchase (F9)</option>
            </select>
          </div>

          <div>
            <label className="block text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-1">Date</label>
            <input
              type="date"
              value={voucherDate}
              onChange={(e) => setVoucherDate(e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-700 text-white px-2 py-1.5 rounded-lg text-xs outline-none focus:ring-1 focus:ring-blue-500 font-mono"
            />
          </div>

          <div>
            <label className="block text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-1">Voucher No.</label>
            <input
              type="text"
              value={voucherNumber}
              onChange={(e) => setVoucherNumber(e.target.value)}
              placeholder="Auto if blank"
              className="w-full bg-zinc-900 border border-zinc-700 text-white px-2 py-1.5 rounded-lg text-xs outline-none focus:ring-1 focus:ring-blue-500 font-mono placeholder:text-zinc-500"
            />
          </div>

          <div className="col-span-2 lg:col-span-2">
            <label className="block text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-1">Narration</label>
            <input
              type="text"
              value={mainNarration}
              onChange={(e) => setMainNarration(e.target.value)}
              placeholder="Overall voucher description..."
              className="w-full bg-zinc-900 border border-zinc-700 text-white px-2 py-1.5 rounded-lg text-xs outline-none focus:ring-1 focus:ring-blue-500 placeholder:text-zinc-500"
            />
          </div>

          <div className="col-span-2 lg:col-span-1">
            <label className="block text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-1">Template</label>
            <select
              onChange={(e) => {
                if (e.target.value) {
                  applyTemplate(e.target.value);
                  e.target.value = "";
                }
              }}
              defaultValue=""
              className="w-full bg-blue-500/10 border border-blue-500/30 text-blue-400 px-2 py-1.5 rounded-lg text-xs outline-none font-semibold cursor-pointer"
            >
              <option value="" disabled>⚡ 1-Click Preset...</option>
              <option value="CONTRA_DEPOSIT">🏦 Bank Deposit (Contra)</option>
              <option value="VENDOR_PAYMENT">💸 Vendor Payment</option>
              <option value="CUSTOMER_RECEIPT">📥 Customer Receipt</option>
              <option value="EXPENSE_JOURNAL">📊 Expense Journal</option>
            </select>
          </div>
        </div>

        {/* AG Grid Data Entry Table - Fills remaining viewport cleanly */}
        <div className="bg-card border border-border/80 rounded-xl shadow-lg overflow-hidden flex flex-col flex-1 min-h-0">
          <div className="px-3 py-1.5 bg-zinc-900/90 border-b border-border flex items-center justify-between text-xs text-muted-foreground shrink-0">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              <span className="font-semibold text-foreground">Double-Entry Spreadsheet</span>
              <span className="text-[11px] text-zinc-500">({rowData.length} rows staged)</span>
            </div>
            <div className="flex items-center gap-2 text-[11px] text-zinc-400">
              <span>Press <kbd className="px-1 py-0.2 bg-zinc-800 text-zinc-300 rounded border border-zinc-700 font-mono text-[9px]">Alt+C</kbd> to quick-create ledger</span>
            </div>
          </div>

          {/* Grid Viewport */}
          <div className="ag-theme-quartz ag-theme-quartz-dark w-full flex-1 min-h-0">
            <AgGridReact
              rowData={rowData}
              columnDefs={columnDefs}
              onGridReady={onGridReady}
              rowSelection="single"
              animateRows={true}
              stopEditingWhenCellsLoseFocus={true}
              enterNavigatesVerticallyAfterEdit={true}
              singleClickEdit={true}
              suppressCellFocus={false}
              rowHeight={42}
              headerHeight={38}
            />
          </div>

          {/* Docked Totals & Real-Time Balance Status Bar - Always Visible */}
          <div className="bg-zinc-950 px-4 py-2.5 border-t border-border flex flex-wrap items-center justify-between gap-3 font-mono text-xs shrink-0">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-1.5 bg-zinc-900 px-3 py-1.5 rounded-lg border border-zinc-800">
                <span className="text-[11px] text-zinc-400 font-sans font-semibold">Total Debit:</span>
                <span className="text-blue-400 font-black text-sm">
                  ₹{totalDebit.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </span>
              </div>
              <div className="flex items-center gap-1.5 bg-zinc-900 px-3 py-1.5 rounded-lg border border-zinc-800">
                <span className="text-[11px] text-zinc-400 font-sans font-semibold">Total Credit:</span>
                <span className="text-emerald-400 font-black text-sm">
                  ₹{totalCredit.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-3">
              {isBalanced ? (
                <div className="px-3 py-1.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 rounded-lg font-bold text-xs flex items-center gap-1.5 shadow-sm">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                  <span>BALANCED · ₹0.00 Diff</span>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <div className="px-3 py-1.5 bg-red-500/10 text-red-400 border border-red-500/30 rounded-lg font-bold text-xs flex items-center gap-1.5 shadow-sm">
                    <span className="w-2 h-2 rounded-full bg-red-400 animate-pulse"></span>
                    <AlertCircle className="w-3.5 h-3.5 text-red-400" />
                    <span>
                      UNBALANCED · Diff: ₹{difference.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={autoBalance}
                    className="px-2.5 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 rounded-lg font-sans font-bold text-xs transition-colors cursor-pointer"
                  >
                    Auto-Fix
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

      </div>
    </DashboardLayout>
  );
}

export default function AgGridVoucherEntryPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-gray-400">Loading High-Density Grid...</div>}>
      <AgGridVoucherEntryContent />
    </Suspense>
  );
}
