"use client";

import React, { useState, useEffect, useMemo, useRef } from 'react';
import { AgGridReact } from 'ag-grid-react';
import { AllCommunityModule, ModuleRegistry, ValidationModule } from 'ag-grid-community';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import { useHotkeys } from 'react-hotkeys-hook';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import { ThemeToggle } from '@/components/ThemeToggle';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-quartz.css';
import { useTheme } from 'next-themes';

ModuleRegistry.registerModules([AllCommunityModule, ValidationModule]);

export default function VoucherEntry() {
  const router = useRouter();
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [voucherType, setVoucherType] = useState('F8');
  const [ledgers, setLedgers] = useState<any[]>([]);
  const [products, setProducts] = useState<any[]>([]);
  const [rowData, setRowData] = useState([{ id: 1, type: 'Dr', ledger: '', amount: 0 }]);
  const gridRef = useRef<AgGridReact>(null);

  useEffect(() => {
    setMounted(true);
    if (!isAuthenticated()) {
      router.push('/login');
      return;
    }
    fetchData();
  }, [router]);

  useHotkeys('f4', (e) => { e.preventDefault(); setVoucherType('F4'); }); // Contra
  useHotkeys('f5', (e) => { e.preventDefault(); setVoucherType('F5'); }); // Payment
  useHotkeys('f6', (e) => { e.preventDefault(); setVoucherType('F6'); }); // Receipt
  useHotkeys('f7', (e) => { e.preventDefault(); setVoucherType('F7'); }); // Journal
  useHotkeys('f8', (e) => { e.preventDefault(); setVoucherType('F8'); }); // Sales
  useHotkeys('f9', (e) => { e.preventDefault(); setVoucherType('F9'); }); // Purchase

  const fetchData = async () => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const [ledgersRes, productsRes] = await Promise.all([
        axios.get('http://localhost:8000/api/ledgers/', { headers }),
        axios.get('http://localhost:8000/api/products/', { headers })
      ]);
      setLedgers(ledgersRes.data);
      setProducts(productsRes.data);
    } catch (e) {
      console.error(e);
    }
  };

  const colDefs = useMemo(() => [
    { field: 'type', headerName: 'Dr/Cr', editable: true, cellEditor: 'agSelectCellEditor', cellEditorParams: { values: ['Dr', 'Cr'] }, width: 120 },
    { field: 'ledger', headerName: 'Ledger Account', editable: true, cellEditor: 'agSelectCellEditor', cellEditorParams: { values: ledgers.map(l => l.name) }, flex: 1 },
    { field: 'amount', headerName: 'Amount', editable: true, type: 'numericColumn', width: 200, valueFormatter: (p: any) => p.value ? `Rs. ${Number(p.value).toFixed(2)}` : '' },
  ], [ledgers]);

  const onCellValueChanged = (params: any) => {
    const data = [...rowData];
    // if last row is edited and valid, add new empty row
    if (params.node.rowIndex === data.length - 1 && params.data.ledger && params.data.amount > 0) {
      const isBalancingCr = params.data.type === 'Dr' ? 'Cr' : 'Dr';
      data.push({ id: data.length + 1, type: isBalancingCr, ledger: '', amount: 0 });
      setRowData(data);
    }
  };

  const handleSave = async () => {
    const drTotal = rowData.filter(r => r.type === 'Dr').reduce((acc, r) => acc + Number(r.amount), 0);
    const crTotal = rowData.filter(r => r.type === 'Cr').reduce((acc, r) => acc + Number(r.amount), 0);
    
    if (drTotal !== crTotal) {
      return alert(`Voucher does not balance! Dr: ${drTotal}, Cr: ${crTotal}`);
    }

    const payload = {
      type: voucherType,
      date: new Date().toISOString().split('T')[0],
      voucher_number: `VCH-${Date.now()}`,
      ledger_entries: rowData.filter(r => r.ledger && r.amount > 0).map(r => {
        const ledgerId = ledgers.find(l => l.name === r.ledger)?.id;
        return {
          ledger: ledgerId,
          debit_amount: r.type === 'Dr' ? r.amount : 0,
          credit_amount: r.type === 'Cr' ? r.amount : 0
        };
      })
    };

    try {
      const token = getAccessToken();
      await axios.post('http://localhost:8000/api/vouchers/', payload, {
        headers: { Authorization: `Bearer ${token}` }
      });
      alert('Voucher Saved Successfully!');
      router.push('/');
    } catch (e) {
      console.error(e);
      alert('Failed to save voucher.');
    }
  };

  const voucherNames: Record<string, string> = { F4: 'Contra', F5: 'Payment', F6: 'Receipt', F7: 'Journal', F8: 'Sales', F9: 'Purchase' };

  if (!mounted) return null;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-[#0a0a0a] text-foreground transition-colors duration-200">
      <div className="max-w-7xl mx-auto p-8 h-screen flex flex-col">
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-4xl font-extrabold tracking-tight">Voucher Entry</h1>
            <p className="text-gray-500 dark:text-gray-400 text-sm mt-2">Use <kbd className="bg-gray-200 dark:bg-gray-800 px-1.5 py-0.5 rounded font-mono text-xs">F4-F9</kbd> to rapidly switch voucher types.</p>
          </div>
          <div className="flex items-center gap-5">
            <span className={`px-5 py-2.5 font-bold rounded-lg shadow-sm border ${voucherType === 'F8' || voucherType === 'F9' ? 'bg-blue-100 text-blue-800 border-blue-200 dark:bg-blue-900/40 dark:text-blue-300 dark:border-blue-800' : 'bg-white text-gray-800 border-gray-200 dark:bg-zinc-800 dark:text-gray-200 dark:border-zinc-700'}`}>
              <span className="opacity-70 mr-2">{voucherType}</span> {voucherNames[voucherType]}
            </span>
            <ThemeToggle />
            <button onClick={() => router.push('/')} className="text-gray-600 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 font-medium transition-colors">
              &larr; Dashboard
            </button>
          </div>
        </div>

        <div className={`flex-1 mb-8 shadow-xl rounded-xl overflow-hidden border border-gray-200 dark:border-zinc-800 ${resolvedTheme === 'dark' ? 'ag-theme-quartz-dark' : 'ag-theme-quartz'}`}>
          <AgGridReact
            ref={gridRef}
            theme="legacy"
            rowData={rowData}
            columnDefs={colDefs}
            onCellValueChanged={onCellValueChanged}
            singleClickEdit={true}
            stopEditingWhenCellsLoseFocus={true}
            defaultColDef={{ resizable: true }}
            rowHeight={50}
            headerHeight={55}
          />
        </div>

        <div className="flex justify-between items-center bg-white dark:bg-zinc-900 p-6 rounded-xl shadow-sm border border-gray-200 dark:border-zinc-800">
          <div className="text-gray-500 dark:text-gray-400 text-sm">
            Total Rows: <span className="font-bold text-gray-800 dark:text-gray-200">{rowData.length}</span>
          </div>
          <div className="flex gap-4">
            <button onClick={() => setRowData([{ id: 1, type: 'Dr', ledger: '', amount: 0 }])} className="text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-zinc-800 hover:bg-gray-200 dark:hover:bg-zinc-700 px-6 py-2.5 rounded-lg font-semibold transition-colors">
              Reset Grid
            </button>
            <button onClick={handleSave} className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-500/30 px-8 py-2.5 rounded-lg font-semibold transition-all hover:scale-[1.02]">
              Save Voucher
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
