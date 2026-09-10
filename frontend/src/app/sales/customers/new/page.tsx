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

interface PendingInvoice {
  invoice_number: string;
  voucher_date: string;
  due_date: string;
  amount: string;
}

export default function NewCustomerPage() {
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
  const [trackingMode, setTrackingMode] = useState<'TOTAL' | 'INVOICES'>('TOTAL');
  const [pendingInvoices, setPendingInvoices] = useState<PendingInvoice[]>([
    { invoice_number: '', voucher_date: defaultOpeningDate, due_date: defaultOpeningDate, amount: '' }
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

  // Invoices sum vs Opening balance reconciliation
  const invoicesSum = useMemo(() => {
    return pendingInvoices.reduce((acc, inv) => {
      const val = parseFloat(inv.amount) || 0;
      return acc + val;
    }, 0);
  }, [pendingInvoices]);

  const targetOpNum = parseFloat(openingBalance) || 0;
  const reconciliationDiff = Math.abs(targetOpNum - invoicesSum);
  const isReconciled = trackingMode === 'TOTAL' || (targetOpNum > 0 && Math.abs(targetOpNum - invoicesSum) < 0.01);

  const addPendingInvoiceRow = () => {
    setPendingInvoices([
      ...pendingInvoices,
      { invoice_number: '', voucher_date: openingDate, due_date: openingDate, amount: '' }
    ]);
  };

  const removePendingInvoiceRow = (index: number) => {
    if (pendingInvoices.length <= 1) return;
    setPendingInvoices(pendingInvoices.filter((_, idx) => idx !== index));
  };

  const updatePendingInvoice = (index: number, field: keyof PendingInvoice, value: string) => {
    const updated = [...pendingInvoices];
    updated[index][field] = value;
    setPendingInvoices(updated);
  };

  const handleSave = async (roleAction?: string) => {
    if (!formData.name.trim()) {
      toast.error("Customer name is required");
      return;
    }

    if (hasOpeningBalance && trackingMode === 'INVOICES' && !isReconciled) {
      toast.error("Invoice total does not match opening balance", `Entered: ₹${invoicesSum}, Required: ₹${targetOpNum}`);
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
        group_name: 'Sundry Debtors',
        ledger_type: 'CUSTOMER',
        opening_balance_type: 'DEBIT',
      };

      if (roleAction) {
        payload.role_action = roleAction;
      }

      if (hasOpeningBalance && targetOpNum > 0) {
        payload.opening_balance = targetOpNum;
        payload.opening_date = openingDate;
        if (trackingMode === 'INVOICES') {
          payload.pending_invoices = pendingInvoices.filter(i => (parseFloat(i.amount) || 0) > 0);
        }
      }

      const res = await axios.post(`${API_BASE_URL}/api/v1/ledgers/${companyId}/`, payload, {
        headers: { Authorization: `Bearer ${token}` }
      });

      toast.success("Customer saved successfully!", `"${formData.name}" has been recorded.`);
      router.push('/parties');
    } catch (err: any) {
      if (err.response?.status === 409 && err.response?.data?.conflict_type === 'ROLE_DIFFERENCE') {
        setConflictData(err.response.data);
      } else {
        toast.error("Failed to create customer", err.response?.data?.error || err.message);
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
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight">New Customer</h1>
            <p className="text-xs text-muted-foreground mt-0.5">Add a business or client to your books</p>
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
                  Customer / Business Name <span className="text-primary">*</span>
                </label>
                <input 
                  required 
                  type="text" 
                  placeholder="e.g. Acme Enterprises" 
                  value={formData.name} 
                  onChange={e => setFormData({...formData, name: e.target.value})} 
                  className="w-full bg-muted/40 border border-input text-foreground p-3 rounded-xl focus:ring-2 focus:ring-primary outline-none transition-all" 
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
                  className="w-full bg-muted/40 border border-input text-foreground p-3 rounded-xl focus:ring-2 focus:ring-primary outline-none transition-all font-mono uppercase" 
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
                  className="w-full bg-muted/40 border border-input text-foreground p-3 rounded-xl focus:ring-2 focus:ring-primary outline-none transition-all font-mono" 
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-1.5">Email Address</label>
                <input 
                  type="email" 
                  placeholder="invoicing@customer.com" 
                  value={formData.email} 
                  onChange={e => setFormData({...formData, email: e.target.value})} 
                  className="w-full bg-muted/40 border border-input text-foreground p-3 rounded-xl focus:ring-2 focus:ring-primary outline-none transition-all" 
                />
              </div>

              <div className="sm:col-span-2">
                <label className="block text-sm font-medium text-foreground mb-1.5">Billing Address</label>
                <textarea 
                  rows={2} 
                  placeholder="Street address, building, city, pin code" 
                  value={formData.address} 
                  onChange={e => setFormData({...formData, address: e.target.value})} 
                  className="w-full bg-muted/40 border border-input text-foreground p-3 rounded-xl focus:ring-2 focus:ring-primary outline-none transition-all resize-none"
                />
              </div>
            </div>
          </div>

          {/* 2. Credit Terms & Limits Card */}
          <div className="bg-card border border-border/40 rounded-2xl shadow-sm p-5 sm:p-6 space-y-5">
            <h2 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Credit Terms & Limits</h2>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-5">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1.5">Payment Terms</label>
                <select
                  value={formData.credit_period_days}
                  onChange={e => setFormData({...formData, credit_period_days: e.target.value})}
                  className="w-full bg-muted/40 border border-input text-foreground p-3 rounded-xl focus:ring-2 focus:ring-primary outline-none transition-all"
                >
                  <option value="0">Immediate / Cash</option>
                  <option value="7">7 Days</option>
                  <option value="15">15 Days</option>
                  <option value="30">30 Days</option>
                  <option value="45">45 Days</option>
                  <option value="60">60 Days</option>
                  <option value="90">90 Days</option>
                </select>
                <p className="text-[11px] text-muted-foreground mt-1">Due date auto-calculates on bills</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-1.5">Credit Limit (₹)</label>
                <input 
                  type="number" 
                  min="0"
                  step="1000"
                  placeholder="e.g. 100000" 
                  value={formData.credit_limit} 
                  onChange={e => setFormData({...formData, credit_limit: e.target.value})} 
                  className="w-full bg-muted/40 border border-input text-foreground p-3 rounded-xl focus:ring-2 focus:ring-primary outline-none transition-all font-mono" 
                />
                <p className="text-[11px] text-muted-foreground mt-1">Warns when outstanding exceeds limit</p>
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
                  className="w-full bg-muted/40 border border-input text-foreground p-3 rounded-xl focus:ring-2 focus:ring-primary outline-none transition-all font-mono" 
                />
                <p className="text-[11px] text-muted-foreground mt-1">Pre-fills on sales invoice lines</p>
              </div>
            </div>
          </div>

          {/* 3. Opening Balance Card (MSME Simple Mode) */}
          <div className="bg-card border border-border/40 rounded-2xl shadow-sm p-5 sm:p-6 space-y-5">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Opening Balance</h2>
                <p className="text-base font-semibold text-foreground mt-1">
                  Does this customer already owe you money?
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
                  className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all ${hasOpeningBalance ? 'bg-primary text-primary-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground'}`}
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
                      Amount Owed (₹) <span className="text-primary">*</span>
                    </label>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      required={hasOpeningBalance}
                      placeholder="e.g. 50000"
                      value={openingBalance}
                      onChange={e => setOpeningBalance(e.target.value)}
                      className="w-full bg-muted/40 border border-input text-foreground p-3 rounded-xl focus:ring-2 focus:ring-primary outline-none transition-all font-mono text-lg font-bold"
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
                      className="w-full bg-muted/40 border border-input text-foreground p-3 rounded-xl focus:ring-2 focus:ring-primary outline-none transition-all font-mono"
                    />
                  </div>
                </div>

                {/* Tracking Option */}
                <div className="bg-muted/30 border border-border/40 rounded-xl p-4 space-y-3">
                  <span className="block text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    How do you want to track this?
                  </span>
                  <div className="flex flex-col sm:flex-row gap-3">
                    <label className={`flex-1 p-3 rounded-xl border flex items-center gap-3 cursor-pointer transition-all ${trackingMode === 'TOTAL' ? 'border-primary bg-primary/5 text-foreground font-semibold shadow-xs' : 'border-border/60 bg-card text-muted-foreground hover:text-foreground'}`}>
                      <input
                        type="radio"
                        name="trackingMode"
                        checked={trackingMode === 'TOTAL'}
                        onChange={() => setTrackingMode('TOTAL')}
                        className="text-primary focus:ring-primary"
                      />
                      <span>Just the total balance</span>
                    </label>

                    <label className={`flex-1 p-3 rounded-xl border flex items-center gap-3 cursor-pointer transition-all ${trackingMode === 'INVOICES' ? 'border-primary bg-primary/5 text-foreground font-semibold shadow-xs' : 'border-border/60 bg-card text-muted-foreground hover:text-foreground'}`}>
                      <input
                        type="radio"
                        name="trackingMode"
                        checked={trackingMode === 'INVOICES'}
                        onChange={() => setTrackingMode('INVOICES')}
                        className="text-primary focus:ring-primary"
                      />
                      <span>Enter the pending invoices</span>
                    </label>
                  </div>
                </div>

                {/* Pending Invoices Sub-Form */}
                {trackingMode === 'INVOICES' && (
                  <div className="space-y-4 pt-2">
                    <div className="flex justify-between items-center">
                      <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Pending Invoices Breakdown</span>
                      <button
                        type="button"
                        onClick={addPendingInvoiceRow}
                        className="text-xs font-semibold text-primary hover:text-primary/80 flex items-center gap-1 bg-primary/10 px-2.5 py-1 rounded-lg transition-colors cursor-pointer"
                      >
                        <Plus className="w-3.5 h-3.5" />
                        <span>Add Invoice</span>
                      </button>
                    </div>

                    <div className="space-y-2.5">
                      {pendingInvoices.map((inv, idx) => (
                        <div key={idx} className="flex flex-col sm:flex-row items-center gap-2 bg-muted/40 p-2.5 rounded-xl border border-border/40">
                          <input
                            type="text"
                            placeholder="Invoice # (e.g. INV-042)"
                            value={inv.invoice_number}
                            onChange={e => updatePendingInvoice(idx, 'invoice_number', e.target.value)}
                            className="w-full sm:flex-1 bg-card border border-input text-foreground px-3 py-2 rounded-lg text-xs font-mono outline-none focus:ring-1 focus:ring-primary"
                          />
                          <input
                            type="date"
                            title="Invoice Date"
                            value={inv.voucher_date}
                            onChange={e => updatePendingInvoice(idx, 'voucher_date', e.target.value)}
                            className="w-full sm:w-36 bg-card border border-input text-foreground px-3 py-2 rounded-lg text-xs font-mono outline-none focus:ring-1 focus:ring-primary"
                          />
                          <input
                            type="date"
                            title="Due Date"
                            value={inv.due_date}
                            onChange={e => updatePendingInvoice(idx, 'due_date', e.target.value)}
                            className="w-full sm:w-36 bg-card border border-input text-foreground px-3 py-2 rounded-lg text-xs font-mono outline-none focus:ring-1 focus:ring-primary"
                          />
                          <div className="relative w-full sm:w-36">
                            <span className="absolute left-2.5 top-2 text-muted-foreground text-xs">₹</span>
                            <input
                              type="number"
                              min="0"
                              step="0.01"
                              placeholder="Amount"
                              value={inv.amount}
                              onChange={e => updatePendingInvoice(idx, 'amount', e.target.value)}
                              className="w-full bg-card border border-input text-foreground pl-6 pr-3 py-2 rounded-lg text-xs font-mono font-semibold outline-none focus:ring-1 focus:ring-primary"
                            />
                          </div>
                          <button
                            type="button"
                            onClick={() => removePendingInvoiceRow(idx)}
                            disabled={pendingInvoices.length <= 1}
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
                          <span>Invoices total matches opening balance (₹{targetOpNum.toLocaleString('en-IN', { minimumFractionDigits: 2 })})</span>
                        ) : (
                          <span>
                            You entered ₹{invoicesSum.toLocaleString('en-IN', { minimumFractionDigits: 2 })} in invoices, but opening balance is ₹{targetOpNum.toLocaleString('en-IN', { minimumFractionDigits: 2 })}. Difference: ₹{reconciliationDiff.toLocaleString('en-IN', { minimumFractionDigits: 2 })}.
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
              disabled={saving || (hasOpeningBalance && trackingMode === 'INVOICES' && !isReconciled)}
              className="bg-primary hover:bg-primary/90 text-primary-foreground px-8 py-3 rounded-xl shadow-md shadow-primary/20 text-sm font-bold transition-all disabled:opacity-50 cursor-pointer flex items-center gap-2"
            >
              {saving ? 'Saving Customer...' : 'Save Customer'}
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
                  className="w-full bg-primary hover:bg-primary/90 text-primary-foreground py-2.5 px-4 rounded-xl text-xs font-bold transition-colors cursor-pointer"
                >
                  Create Separate Customer Account
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
