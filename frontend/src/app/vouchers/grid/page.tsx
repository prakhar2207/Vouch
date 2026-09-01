"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useState, useEffect, useRef, useMemo, useCallback, Suspense } from "react";
import axios from "axios";
import { useRouter, useSearchParams } from "next/navigation";
import { AgGridReact } from "ag-grid-react";
import { ColDef, GridApi, GridReadyEvent } from "ag-grid-community";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-alpine.css";
import { getAccessToken, isAuthenticated } from "@/utils/auth";
import DashboardLayout from "@/components/DashboardLayout";
import { useShortcuts } from "@/context/ShortcutContext";

interface RowData {
  id: string;
  type: "Dr" | "Cr";
  ledger_id: string;
  ledger_name: string;
  debit_amount: number;
  credit_amount: number;
  narration: string;
}

function AgGridVoucherEntryContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { workingDate, registerSaveHandler, registerAltCCallback } = useShortcuts();

  const [companyId, setCompanyId] = useState<string>("");
  const [ledgers, setLedgers] = useState<any[]>([]);
  const [voucherType, setVoucherType] = useState<string>(searchParams?.get("type") || "JOURNAL");
  const [voucherDate, setVoucherDate] = useState<string>(workingDate);
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

  const addRow = () => {
    const newId = String(rowData.length + 1);
    const newType = rowData[rowData.length - 1]?.type === "Dr" ? "Cr" : "Dr";
    setRowData((prev) => [
      ...prev,
      { id: newId, type: newType, ledger_id: "", ledger_name: "", debit_amount: 0, credit_amount: 0, narration: "" },
    ]);
  };

  const removeRow = (index: number) => {
    if (rowData.length <= 2) return;
    setRowData((prev) => prev.filter((_, i) => i !== index));
  };

  const columnDefs = useMemo<ColDef[]>(
    () => [
      {
        headerName: "#",
        valueGetter: "node.rowIndex + 1",
        width: 60,
        pinned: "left",
        cellClass: "text-center font-mono font-bold text-zinc-400",
      },
      {
        field: "type",
        headerName: "Dr / Cr",
        width: 90,
        editable: true,
        cellEditor: "agSelectCellEditor",
        cellEditorParams: {
          values: ["Dr", "Cr"],
        },
        cellClass: (params) => (params.value === "Dr" ? "font-bold text-blue-500" : "font-bold text-amber-500"),
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
        flex: 2,
        editable: true,
        cellEditor: "agSelectCellEditor",
        cellEditorParams: {
          values: ledgerNames,
        },
        cellClass: "font-medium",
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
        flex: 1,
        editable: (params) => params.data.type === "Dr",
        valueFormatter: (params) => (params.value ? Number(params.value).toFixed(2) : ""),
        cellClass: "text-right font-mono font-semibold text-blue-600 dark:text-blue-400",
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
        flex: 1,
        editable: (params) => params.data.type === "Cr",
        valueFormatter: (params) => (params.value ? Number(params.value).toFixed(2) : ""),
        cellClass: "text-right font-mono font-semibold text-amber-600 dark:text-amber-400",
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
        flex: 1.5,
        editable: true,
        placeholder: "Optional row remark...",
        onCellValueChanged: (params) => {
          const idx = params.node?.rowIndex;
          if (idx === undefined || idx === null) return;
          const updated = [...rowData];
          if (!updated[idx]) return;
          updated[idx].narration = params.newValue;
          setRowData(updated);
        },
      },
    ],
    [rowData, ledgers, ledgerNames]
  );

  const handleSubmit = async () => {
    if (!isBalanced) {
      setStatusMessage({
        type: "error",
        text: `Voucher is unbalanced! Debit (₹${totalDebit.toFixed(2)}) must equal Credit (₹${totalCredit.toFixed(2)}).`,
      });
      return;
    }

    const invalidRow = rowData.find((r) => !r.ledger_id || (r.debit_amount === 0 && r.credit_amount === 0));
    if (invalidRow) {
      setStatusMessage({
        type: "error",
        text: "Please specify a valid Ledger Account and Amount for all rows.",
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
        text: `Voucher #${res.data.voucher_number} posted successfully! Amount: ₹${res.data.total_amount}`,
      });

      // Reset form
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

  return (
    <DashboardLayout>
      <div className="space-y-6 max-w-7xl mx-auto pb-16">
        {/* Header Bar */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-border pb-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">AG Grid Voucher Entry</h1>
            <p className="text-sm text-gray-400 mt-1">
              High-density keyboard-first double-entry engine. Navigate cells with <kbd className="px-1.5 py-0.5 bg-zinc-800 border border-zinc-700 rounded text-xs">Tab</kbd>, <kbd className="px-1.5 py-0.5 bg-zinc-800 border border-zinc-700 rounded text-xs">Enter</kbd>, and Arrow Keys.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={addRow}
              type="button"
              className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-white rounded-lg text-sm font-medium border border-zinc-700 transition-colors"
            >
              + Add Line
            </button>
            <button
              onClick={handleSubmit}
              disabled={saving || !isBalanced}
              className={`px-6 py-2 rounded-lg text-sm font-bold shadow-lg transition-colors ${
                isBalanced
                  ? "bg-blue-600 hover:bg-blue-700 text-white"
                  : "bg-gray-700 text-gray-400 cursor-not-allowed opacity-60"
              }`}
            >
              {saving ? "Posting..." : "Post Voucher (Ctrl+S)"}
            </button>
          </div>
        </div>

        {/* Status Notification */}
        {statusMessage && (
          <div
            className={`p-4 rounded-xl border text-sm font-medium flex items-center justify-between ${
              statusMessage.type === "success"
                ? "bg-green-500/10 border-green-500/30 text-green-400"
                : "bg-red-500/10 border-red-500/30 text-red-400"
            }`}
          >
            <span>{statusMessage.text}</span>
            <button onClick={() => setStatusMessage(null)} className="text-xs font-bold px-2">✕</button>
          </div>
        )}

        {/* Voucher Meta Form */}
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm grid grid-cols-1 sm:grid-cols-4 gap-4">
          <div>
            <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Voucher Type</label>
            <select
              value={voucherType}
              onChange={(e) => setVoucherType(e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500 font-semibold"
            >
              <option value="JOURNAL">Journal Voucher</option>
              <option value="PAYMENT">Payment Voucher</option>
              <option value="RECEIPT">Receipt Voucher</option>
              <option value="CONTRA">Contra Voucher</option>
              <option value="SALES">Sales Entry</option>
              <option value="PURCHASE">Purchase Entry</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Voucher Date</label>
            <input
              type="date"
              value={voucherDate}
              onChange={(e) => setVoucherDate(e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Voucher No. (Auto/Custom)</label>
            <input
              type="text"
              value={voucherNumber}
              onChange={(e) => setVoucherNumber(e.target.value)}
              placeholder="Auto-generated if blank"
              className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500 font-mono"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Narration / Remark</label>
            <input
              type="text"
              value={mainNarration}
              onChange={(e) => setMainNarration(e.target.value)}
              placeholder="Overall voucher description..."
              className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>

        {/* AG Grid Data Entry Table */}
        <div className="bg-card border border-border rounded-xl shadow-lg overflow-hidden flex flex-col">
          <div className="ag-theme-alpine-dark w-full" style={{ height: 360 }}>
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
            />
          </div>

          {/* Bottom Totals & Balance Bar */}
          <div className="bg-zinc-950 p-4 border-t border-border flex flex-col sm:flex-row items-center justify-between gap-4 font-mono text-sm">
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <span className="text-gray-400">Total Debit:</span>
                <span className="text-blue-400 font-bold text-base">₹{totalDebit.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-gray-400">Total Credit:</span>
                <span className="text-amber-400 font-bold text-base">₹{totalCredit.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
              </div>
            </div>

            <div className="flex items-center gap-4">
              {isBalanced ? (
                <span className="px-3 py-1 bg-green-500/20 text-green-400 border border-green-500/40 rounded-full font-bold text-xs flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse"></span>
                  BALANCED (₹0.00 Diff)
                </span>
              ) : (
                <span className="px-3 py-1 bg-red-500/20 text-red-400 border border-red-500/40 rounded-full font-bold text-xs flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-red-400"></span>
                  UNBALANCED (Diff: ₹{difference.toLocaleString("en-IN", { minimumFractionDigits: 2 })})
                </span>
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
    <Suspense fallback={<div className="p-8 text-center text-gray-400">Loading Grid...</div>}>
      <AgGridVoucherEntryContent />
    </Suspense>
  );
}
