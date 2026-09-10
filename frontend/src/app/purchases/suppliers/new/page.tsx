"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import StateSelect from '@/components/StateSelect';
import { useToast } from '@/context/ToastContext';
import { Plus, Trash2, AlertCircle, CheckCircle2, ArrowLeft } from 'lucide-react';

interface PendingBill {
  bill_number: string;
  voucher_date: string;
  due_date: string;
  amount: string;
}

export default function NewSupplierPage() {
  const router = useRouter();
  const { toast } = useToast();
  const [companyId, setCompanyId] = useState('');
  const [saving, setSaving] = useState(false);

  // FY start date default (Apr 1 of current FY)
  const defaultOpeningDate = useMemo(() => {
    const today = new Date();
    const year = today.getMonth() >= 3 ? today.getFullYear() : today.getFullYear() - 1;
    return `${year}-04-01`;
  }, []);
  
  const [formData, setFormData] = useState({
    name: '',
    gstin: '',
    state_code: '',
    phone: '',
    email: '',
    address: '',
    discount_percent: '',
    credit_limit: '',
    credit_period_days: '0',
  });

  // Opening balance state (Simple Mode)
  const [hasOpeningBalance, setHasOpeningBalance] = useState(false);
  const [openingBalance, setOpeningBalance] = useState('');
  const [openingDate, setOpeningDate] = useState(defaultOpeningDate);
  const [trackingMode, setTrackingMode] = useState<'TOTAL' | 'BILLS'>('TOTAL');
  const [pendingBills, setPendingBills] = useState<PendingBill[]>([
    { bill_number: '', voucher_date: defaultOpeningDate, due_date: defaultOpeningDate, amount: '' }
  ]);

  // Conflict state
  const [conflictData, setConflictData] = useState<any>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login');
      return;
    }
    const token = getAccessToken();
    const headers = { Authorization: `Bearer ${token}` };
    axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers }).then(res => {
      setCompanyId(res.data.data[0]?.id);
    });
  }, [router]);

  // Bills sum vs Opening balance reconciliation
  const billsSum = useMemo(() => {
    return pendingBills.reduce((acc, bill) => {
      const val = parseFloat(bill.amount) || 0;
      return acc + val;
    }, 0);
  }, [pendingBills]);

  const targetOpNum = parseFloat(openingBalance) || 0;
  const reconciliationDiff = Math.abs(targetOpNum - billsSum);
  const isReconciled = trackingMode === 'TOTAL' || (targetOpNum > 0 && Math.abs(targetOpNum - billsSum) < 0.01);

  const addPendingBillRow = () => {
    setPendingBills([
      ...pendingBills,
      { bill_number: '', voucher_date: openingDate, due_date: openingDate, amount: '' }
    ]);
  };

  const removePendingBillRow = (index: number) => {
    if (pendingBills.length <= 1) return;
    setPendingBills(pendingBills.filter((_, idx) => idx !== index));
  };

  const updatePendingBill = (index: number, field: keyof PendingBill, value: string) => {
    const updated = [...pendingBills];
    updated[index][field] = value;
    setPendingBills(updated);
  };

  const handleSave = async (roleAction?: string) => {
    if (!formData.name.trim()) {
      toast.error("Supplier name is required");
      return;
    }

    if (hasOpeningBalance && trackingMode === 'BILLS' && !isReconciled) {
      toast.error("Bill total does not match opening balance", `Entered: ₹${billsSum}, Required: ₹${targetOpNum}`);
      return;
    }

    setSaving(true);
    try {
      const token = getAccessToken();
      const payload: any = {
        ...formData,
        discount_percent: formData.discount_percent ? parseFloat(formData.discount_percent) : 0,
        credit_limit: formData.credit_limit ? parseFloat(formData.credit_limit) : null,
        credit_period_days: parseInt(formData.credit_period_days) || 0,
        group_name: 'Sundry Creditors',
        ledger_type: 'SUPPLIER',
        opening_balance_type: 'CREDIT',
      };

      if (roleAction) {
        payload.role_action = roleAction;
      }

      if (hasOpeningBalance && targetOpNum > 0) {
        payload.opening_balance = targetOpNum;
        payload.opening_date = openingDate;
        if (trackingMode === 'BILLS') {
          payload.pending_invoices = pendingBills.filter(i => (parseFloat(i.amount) || 0) > 0);
        }
      }

      const res = await axios.post(`${API_BASE_URL}/api/v1/ledgers/${companyId}/`, payload, {
        headers: { Authorization: `Bearer ${token}` }
      });

      toast.success("Supplier saved successfully!", `"${formData.name}" has been recorded.`);
      router.push('/parties');
    } catch (err: any) {
      if (err.response?.status === 409 && err.response?.data?.conflict_type === 'ROLE_DIFFERENCE') {
        setConflictData(err.response.data);
      } else {
        toast.error("Failed to create supplier", err.response?.data?.error || err.message);
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="max-w-3xl mx-auto space-y-6 pb-12">
        {/* Header */}
        <div className="flex items-center gap-3 sm:gap-4 border-b border-border/40 pb-4">
          <Link href="/parties" className="text-muted-foreground hover:text-foreground transition-colors p-1.5 rounded-lg hover:bg-muted">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight">New Supplier</h1>
            <p className="text-xs text-muted-foreground mt-0.5">Add a vendor or supplier to your books</p>
          </div>
        </div>

        {/* Form Container */}
        <form onSubmit={(e) => { e.preventDefault(); handleSave(); }} className="space-y-6">
          {/* 1. Basic Party Details Card */}
          <div className="bg-card border border-border/40 rounded-2xl shadow-sm p-5 sm:p-6 space-y-5">
            <h2 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Basic Information</h2>
            
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-5">
              <div className="sm:col-span-2">
                <label className="block text-sm font-medium text-foreground mb-1.5">
                  Supplier / Company Name <span className="text-red-400">*</span>
                </label>
                <input 
                  required 
                  type="text" 
                  placeholder="e.g. Bharat Logistics & Trading" 
                  value={formData.name} 
                  onChange={e => setFormData({...formData, name: e.target.value})} 
                  className="w-full bg-muted/40 border border-input text-foreground p-3 rounded-xl focus:ring-2 focus:ring-red-500 outline-none transition-all" 
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-1.5">GSTIN (Optional)</label>
                <input 
                  type="text" 
                  maxLength={15}
                  placeholder="15-digit GSTIN" 
                  value={formData.gstin} 
                  onChange={e => setFormData({...formData, gstin: e.target.value.toUpperCase()})} 
                  className="w-full bg-muted/40 border border-input text-foreground p-3 rounded-xl focus:ring-2 focus:ring-red-500 outline-none transition-all font-mono uppercase" 
                />
              </div>

              <div>
                <StateSelect
                  value={formData.state_code}
                  onChange={(code) => setFormData({...formData, state_code: code})}
                  label="State / Union Territory"
                  placeholder="Select state..."
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-1.5">Phone Number</label>
                <input 
                  type="tel" 
                  placeholder="10-digit mobile or landline" 
                  value={formData.phone} 
                  onChange={e => setFormData({...formData, phone: e.target.value})} 
                  className="w-full bg-muted/40 border border-input text-foreground p-3 rounded-xl focus:ring-2 focus:ring-red-500 outline-none transition-all font-mono" 
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-1.5">Email Address</label>
                <input 
                  type="email" 
                  placeholder="accounts@supplier.com" 
                  value={formData.email} 
                  onChange={e => setFormData({...formData, email: e.target.value})} 
                  className="w-full bg-muted/40 border border-input text-foreground p-3 rounded-xl focus:ring-2 focus:ring-red-500 outline-none transition-all" 
                />
              </div>

              <div className="sm:col-span-2">
                <label className="block text-sm font-medium text-foreground mb-1.5">Billing Address</label>
                <textarea 
                  rows={2} 
                  placeholder="Warehouse, building, city, pin code" 
                  value={formData.address} 
                  onChange={e => setFormData({...formData, address: e.target.value})} 
                  className="w-full bg-muted/40 border border-input text-foreground p-3 rounded-xl focus:ring-2 focus:ring-red-500 outline-none transition-all resize-none"
                />
              </div>
            </div>
          </div>

          {/* 2. Credit Terms Card */}
          <div className="bg-card border border-border/40 rounded-2xl shadow-sm p-5 sm:p-6 space-y-5">
            <h2 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Credit Terms</h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-5">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1.5">Payment Terms</label>
                <select
                  value={formData.credit_period_days}
                  onChange={e => setFormData({...formData, credit_period_days: e.target.value})}
                  className="w-full bg-muted/40 border border-input text-foreground p-3 rounded-xl focus:ring-2 focus:ring-red-500 outline-none transition-all"
                >
                  <option value="0">Immediate / Cash</option>
                  <option value="7">7 Days</option>
                  <option value="15">15 Days</option>
                  <option value="30">30 Days</option>
                  <option value="45">45 Days</option>
                  <option value="60">60 Days</option>
                  <option value="90">90 Days</option>
                </select>
                <p className="text-[11px] text-muted-foreground mt-1">Due date auto-calculates on purchase bills</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-1.5">Default Discount (%)</label>
                <input 
                  type="number" 
                  min="0"
                  max="100"
                  step="0.1"
                  placeholder="e.g. 5.0" 
                  value={formData.discount_percent} 
                  onChange={e => setFormData({...formData, discount_percent: e.target.value})} 
                  className="w-full bg-muted/40 border border-input text-foreground p-3 rounded-xl focus:ring-2 focus:ring-red-500 outline-none transition-all font-mono" 
                />
                <p className="text-[11px] text-muted-foreground mt-1">Default discount rate on purchases</p>
              </div>
            </div>
          </div>

          {/* 3. Opening Balance Card (MSME Simple Mode) */}
          <div className="bg-card border border-border/40 rounded-2xl shadow-sm p-5 sm:p-6 space-y-5">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Opening Balance</h2>
                <p className="text-base font-semibold text-foreground mt-1">
                  Do you already owe this supplier money?
                </p>
              </div>
              <div className="flex items-center gap-2 bg-muted/60 p-1 rounded-xl border border-border/40">
                <button
                  type="button"
                  onClick={() => setHasOpeningBalance(false)}
                  className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all ${!hasOpeningBalance ? 'bg-card text-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground'}`}
                >
                  No
                </button>
                <button
                  type="button"
                  onClick={() => setHasOpeningBalance(true)}
                  className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all ${hasOpeningBalance ? 'bg-red-500 text-white shadow-xs' : 'text-muted-foreground hover:text-foreground'}`}
                >
                  Yes
                </button>
              </div>
            </div>

            {hasOpeningBalance && (
              <div className="space-y-5 pt-4 border-t border-border/40 animate-in fade-in slide-in-from-top-2">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1.5">
                      Amount You Owe (₹) <span className="text-red-400">*</span>
                    </label>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      required={hasOpeningBalance}
                      placeholder="e.g. 30000"
                      value={openingBalance}
                      onChange={e => setOpeningBalance(e.target.value)}
                      className="w-full bg-muted/40 border border-input text-foreground p-3 rounded-xl focus:ring-2 focus:ring-red-500 outline-none transition-all font-mono text-lg font-bold"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1.5">
                      Opening Date (As of)
                    </label>
                    <input
                      type="date"
                      value={openingDate}
                      onChange={e => setOpeningDate(e.target.value)}
                      className="w-full bg-muted/40 border border-input text-foreground p-3 rounded-xl focus:ring-2 focus:ring-red-500 outline-none transition-all font-mono"
                    />
                  </div>
                </div>

                {/* Tracking Option */}
                <div className="bg-muted/30 border border-border/40 rounded-xl p-4 space-y-3">
                  <span className="block text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    How do you want to track this?
                  </span>
                  <div className="flex flex-col sm:flex-row gap-3">
                    <label className={`flex-1 p-3 rounded-xl border flex items-center gap-3 cursor-pointer transition-all ${trackingMode === 'TOTAL' ? 'border-red-500 bg-red-500/5 text-foreground font-semibold shadow-xs' : 'border-border/60 bg-card text-muted-foreground hover:text-foreground'}`}>
                      <input
                        type="radio"
                        name="trackingModeSupplier"
                        checked={trackingMode === 'TOTAL'}
                        onChange={() => setTrackingMode('TOTAL')}
                        className="text-red-500 focus:ring-red-500"
                      />
                      <span>Just the total balance</span>
                    </label>

                    <label className={`flex-1 p-3 rounded-xl border flex items-center gap-3 cursor-pointer transition-all ${trackingMode === 'BILLS' ? 'border-red-500 bg-red-500/5 text-foreground font-semibold shadow-xs' : 'border-border/60 bg-card text-muted-foreground hover:text-foreground'}`}>
                      <input
                        type="radio"
                        name="trackingModeSupplier"
                        checked={trackingMode === 'BILLS'}
                        onChange={() => setTrackingMode('BILLS')}
                        className="text-red-500 focus:ring-red-500"
                      />
                      <span>Enter the pending supplier bills</span>
                    </label>
                  </div>
                </div>

                {/* Pending Bills Sub-Form */}
                {trackingMode === 'BILLS' && (
                  <div className="space-y-4 pt-2">
                    <div className="flex justify-between items-center">
                      <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Pending Bills Breakdown</span>
                      <button
                        type="button"
                        onClick={addPendingBillRow}
                        className="text-xs font-semibold text-red-400 hover:text-red-300 flex items-center gap-1 bg-red-500/10 px-2.5 py-1 rounded-lg transition-colors cursor-pointer"
                      >
                        <Plus className="w-3.5 h-3.5" />
                        <span>Add Bill</span>
                      </button>
                    </div>

                    <div className="space-y-2.5">
                      {pendingBills.map((bill, idx) => (
                        <div key={idx} className="flex flex-col sm:flex-row items-center gap-2 bg-muted/40 p-2.5 rounded-xl border border-border/40">
                          <input
                            type="text"
                            placeholder="Bill # (e.g. BILL-992)"
                            value={bill.bill_number}
                            onChange={e => updatePendingBill(idx, 'bill_number', e.target.value)}
                            className="w-full sm:flex-1 bg-card border border-input text-foreground px-3 py-2 rounded-lg text-xs font-mono outline-none focus:ring-1 focus:ring-red-500"
                          />
                          <input
                            type="date"
                            title="Bill Date"
                            value={bill.voucher_date}
                            onChange={e => updatePendingBill(idx, 'voucher_date', e.target.value)}
                            className="w-full sm:w-36 bg-card border border-input text-foreground px-3 py-2 rounded-lg text-xs font-mono outline-none focus:ring-1 focus:ring-red-500"
                          />
                          <input
                            type="date"
                            title="Due Date"
                            value={bill.due_date}
                            onChange={e => updatePendingBill(idx, 'due_date', e.target.value)}
                            className="w-full sm:w-36 bg-card border border-input text-foreground px-3 py-2 rounded-lg text-xs font-mono outline-none focus:ring-1 focus:ring-red-500"
                          />
                          <div className="relative w-full sm:w-36">
                            <span className="absolute left-2.5 top-2 text-muted-foreground text-xs">₹</span>
                            <input
                              type="number"
                              min="0"
                              step="0.01"
                              placeholder="Amount"
                              value={bill.amount}
                              onChange={e => updatePendingBill(idx, 'amount', e.target.value)}
                              className="w-full bg-card border border-input text-foreground pl-6 pr-3 py-2 rounded-lg text-xs font-mono font-semibold outline-none focus:ring-1 focus:ring-red-500"
                            />
                          </div>
                          <button
                            type="button"
                            onClick={() => removePendingBillRow(idx)}
                            disabled={pendingBills.length <= 1}
                            className="p-2 text-muted-foreground hover:text-rose-500 rounded-lg hover:bg-card transition-colors disabled:opacity-30 cursor-pointer"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      ))}
                    </div>

                    {/* Reconciliation Status */}
                    <div className={`p-3 rounded-xl border flex items-center justify-between text-xs font-medium ${isReconciled ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-amber-500/10 border-amber-500/30 text-amber-300'}`}>
                      <div className="flex items-center gap-2">
                        {isReconciled ? <CheckCircle2 className="w-4 h-4 text-emerald-400" /> : <AlertCircle className="w-4 h-4 text-amber-400" />}
                        {isReconciled ? (
                          <span>Bills total matches opening balance (₹{targetOpNum.toLocaleString('en-IN', { minimumFractionDigits: 2 })})</span>
                        ) : (
                          <span>
                            You entered ₹{billsSum.toLocaleString('en-IN', { minimumFractionDigits: 2 })} in bills, but opening balance is ₹{targetOpNum.toLocaleString('en-IN', { minimumFractionDigits: 2 })}. Difference: ₹{reconciliationDiff.toLocaleString('en-IN', { minimumFractionDigits: 2 })}.
                          </span>
                        )}
                      </div>
                      <span className="font-mono font-bold">
                        {isReconciled ? "Balanced" : "Mismatch"}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-3 pt-2">
            <Link href="/parties" className="px-5 py-2.5 rounded-xl border border-border/60 hover:bg-muted text-muted-foreground hover:text-foreground text-sm font-semibold transition-colors">
              Cancel
            </Link>
            <button
              type="submit"
              disabled={saving || (hasOpeningBalance && trackingMode === 'BILLS' && !isReconciled)}
              className="bg-red-600 hover:bg-red-700 text-white px-8 py-3 rounded-xl shadow-md shadow-red-500/20 text-sm font-bold transition-all disabled:opacity-50 cursor-pointer flex items-center gap-2"
            >
              {saving ? 'Saving Supplier...' : 'Save Supplier'}
            </button>
          </div>
        </form>

        {/* Role Conflict Dialog */}
        {conflictData && (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4 z-50 animate-in fade-in">
            <div className="bg-card border border-border/60 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4">
              <div className="flex items-center gap-3 text-amber-400">
                <AlertCircle className="w-6 h-6" />
                <h3 className="text-lg font-bold text-foreground">Existing Business Role</h3>
              </div>
              <p className="text-sm text-muted-foreground leading-relaxed">
                {conflictData.message}
              </p>
              <div className="space-y-2 pt-2">
                <button
                  type="button"
                  onClick={() => { setConflictData(null); handleSave('CREATE_SEPARATE'); }}
                  className="w-full bg-red-600 hover:bg-red-700 text-white py-2.5 px-4 rounded-xl text-xs font-bold transition-colors cursor-pointer"
                >
                  Create Separate Supplier Account
                </button>
                <button
                  type="button"
                  onClick={() => { setConflictData(null); handleSave('UPGRADE_TO_BOTH'); }}
                  className="w-full bg-muted hover:bg-muted/80 text-foreground py-2.5 px-4 rounded-xl text-xs font-bold border border-border/40 transition-colors cursor-pointer"
                >
                  Mark Existing as Both Customer & Supplier
                </button>
                <button
                  type="button"
                  onClick={() => setConflictData(null)}
                  className="w-full py-2 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
