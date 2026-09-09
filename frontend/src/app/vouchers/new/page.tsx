"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import { useToast } from '@/context/ToastContext';
import SearchableSelect, { SearchableOption } from '@/components/SearchableSelect';
import AddBankModal from '@/components/modals/AddBankModal';
import { 
  Banknote, 
  Landmark, 
  FileText, 
  QrCode, 
  CreditCard, 
  Plus, 
  Zap, 
  Send,
  Calendar,
  Hash,
  ArrowDownLeft,
  ArrowUpRight
} from 'lucide-react';

type PaymentMode = 'CASH' | 'CHEQUE' | 'NEFT' | 'RTGS' | 'IMPS' | 'UPI' | 'BANK_TRANSFER';

export default function NewVoucherPage() {
  const router = useRouter();
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);
  const [companyId, setCompanyId] = useState('');
  const [ledgers, setLedgers] = useState<any[]>([]);

  const [voucherType, setVoucherType] = useState<'RECEIPT' | 'PAYMENT'>('RECEIPT');
  const [partyLedgerId, setPartyLedgerId] = useState('');
  const [paymentLedgerId, setPaymentLedgerId] = useState('');
  const [amount, setAmount] = useState('');
  const [narration, setNarration] = useState('');
  const [voucherDate, setVoucherDate] = useState(new Date().toISOString().split('T')[0]);

  // Payment Instrument State
  const [paymentMode, setPaymentMode] = useState<PaymentMode>('CASH');
  const [chequeNo, setChequeNo] = useState('');
  const [chequeDate, setChequeDate] = useState(new Date().toISOString().split('T')[0]);
  const [bankName, setBankName] = useState('');
  const [transactionNo, setTransactionNo] = useState('');
  const [transferDate, setTransferDate] = useState(new Date().toISOString().split('T')[0]);
  const [upiId, setUpiId] = useState('');

  // Add Bank Modal state
  const [isAddBankModalOpen, setIsAddBankModalOpen] = useState(false);

  useEffect(() => {
    if (!isAuthenticated()) { router.push('/login'); return; }
    fetchLedgers();
  }, [router]);

  const fetchLedgers = async () => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const cid = compRes.data.data[0]?.id;
      if (!cid) return;
      setCompanyId(cid);

      const res = await axios.get(`${API_BASE_URL}/api/v1/ledgers/${cid}/`, { headers });
      const ledgerList = res.data.data || [];
      setLedgers(ledgerList);

      // Default Cash Account selection if in CASH mode
      const defaultCash = ledgerList.find((l: any) => 
        l.group === 'Cash-in-Hand' || l.ledger_type === 'CASH' || l.name.toLowerCase().includes('cash')
      );
      if (defaultCash && !paymentLedgerId) {
        setPaymentLedgerId(defaultCash.id);
      }
    } catch (err) {
      console.error(err);
    }
  };

  // Filter parties based on voucher type
  const partyLedgers = ledgers.filter((l: any) => {
    const grp = (l.group || '').toLowerCase();
    const ltype = (l.ledger_type || '').toUpperCase();
    if (voucherType === 'RECEIPT') {
      return grp.includes('debtor') || ltype === 'CUSTOMER' || grp.includes('customer');
    } else {
      return grp.includes('creditor') || ltype === 'SUPPLIER' || grp.includes('supplier');
    }
  });

  // Fallback to all debtors & creditors if strict filter has none
  const effectivePartyLedgers = partyLedgers.length > 0 
    ? partyLedgers 
    : ledgers.filter((l: any) => (l.group || '').includes('Debtor') || (l.group || '').includes('Creditor'));

  const partyOptions: SearchableOption[] = effectivePartyLedgers.map((l: any) => ({
    id: l.id,
    name: l.name,
    group: l.group,
    balance: l.current_balance,
    balanceType: l.opening_balance_type === 'DEBIT' ? 'Dr' : 'Cr',
    subtitle: l.gstin ? `GSTIN: ${l.gstin}` : (l.phone ? `Ph: ${l.phone}` : undefined),
  }));

  // Cash vs Bank Ledgers
  const cashLedgers = ledgers.filter((l: any) =>
    l.group === 'Cash-in-Hand' || l.ledger_type === 'CASH' || l.name.toLowerCase().includes('cash')
  );

  const bankLedgers = ledgers.filter((l: any) =>
    (l.group || '').toLowerCase().includes('bank') || l.ledger_type === 'BANK'
  );

  const currentAccounts = paymentMode === 'CASH' ? cashLedgers : bankLedgers;

  const accountOptions: SearchableOption[] = currentAccounts.map((l: any) => ({
    id: l.id,
    name: l.name,
    group: l.group,
    balance: l.current_balance,
    balanceType: l.opening_balance_type === 'DEBIT' ? 'Dr' : 'Cr',
  }));

  // Automatically switch account when paymentMode changes
  const handlePaymentModeChange = (mode: PaymentMode) => {
    setPaymentMode(mode);
    if (mode === 'CASH') {
      const defaultCash = cashLedgers[0];
      if (defaultCash) setPaymentLedgerId(defaultCash.id);
    } else {
      // If currently selected account is cash, switch to first bank account if available
      const isCurrentCash = cashLedgers.some((l: any) => l.id === paymentLedgerId);
      if (isCurrentCash || !paymentLedgerId) {
        if (bankLedgers.length > 0) {
          setPaymentLedgerId(bankLedgers[0].id);
        } else {
          setPaymentLedgerId('');
        }
      }
    }
  };

  const handleBankCreated = (newBank: any) => {
    setLedgers((prev) => [...prev, newBank]);
    setPaymentLedgerId(newBank.id);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!partyLedgerId) {
      toast.warning(`Please select a ${voucherType === 'RECEIPT' ? 'customer' : 'supplier'}.`);
      return;
    }
    if (!paymentLedgerId) {
      toast.warning(`Please select a ${paymentMode === 'CASH' ? 'Cash' : 'Bank'} account.`);
      return;
    }
    if (!amount || parseFloat(amount) <= 0) {
      toast.warning('Please enter a valid amount.');
      return;
    }

    // Validate mode-specific required fields
    if (paymentMode === 'CHEQUE' && !chequeNo.trim()) {
      toast.warning('Please enter the Cheque / DD number.');
      return;
    }
    if ((paymentMode === 'NEFT' || paymentMode === 'RTGS' || paymentMode === 'IMPS' || paymentMode === 'UPI') && !transactionNo.trim()) {
      toast.warning(`Please enter the ${paymentMode} transaction / reference number.`);
      return;
    }

    setSaving(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      // Compile reference number and structured narration
      let referenceNumber = '';
      let instrumentDetails = '';

      if (paymentMode === 'CHEQUE') {
        referenceNumber = `Chq# ${chequeNo.trim()}`;
        instrumentDetails = `via Cheque #${chequeNo.trim()} dtd ${chequeDate}${bankName.trim() ? ` (Bank: ${bankName.trim()})` : ''}`;
      } else if (paymentMode === 'NEFT') {
        referenceNumber = `NEFT:${transactionNo.trim()}`;
        instrumentDetails = `via NEFT UTR: ${transactionNo.trim()}${bankName.trim() ? ` (Bank: ${bankName.trim()})` : ''}`;
      } else if (paymentMode === 'RTGS') {
        referenceNumber = `RTGS:${transactionNo.trim()}`;
        instrumentDetails = `via RTGS UTR: ${transactionNo.trim()}`;
      } else if (paymentMode === 'IMPS') {
        referenceNumber = `IMPS:${transactionNo.trim()}`;
        instrumentDetails = `via IMPS RRN: ${transactionNo.trim()}`;
      } else if (paymentMode === 'UPI') {
        referenceNumber = `UPI:${transactionNo.trim()}`;
        instrumentDetails = `via UPI Ref: ${transactionNo.trim()}${upiId.trim() ? ` (${upiId.trim()})` : ''}`;
      } else if (paymentMode === 'BANK_TRANSFER') {
        referenceNumber = `TXN:${transactionNo.trim()}`;
        instrumentDetails = `via Bank Transfer Ref: ${transactionNo.trim()}`;
      } else {
        referenceNumber = '';
        instrumentDetails = 'via Cash';
      }

      // Merge narration
      let finalNarration = narration.trim();
      if (instrumentDetails) {
        finalNarration = finalNarration 
          ? `${finalNarration} [${instrumentDetails}]`
          : instrumentDetails;
      }

      const payload = {
        company_id: companyId,
        voucher_type: voucherType,
        party_ledger_id: partyLedgerId,
        payment_ledger_id: paymentLedgerId,
        amount: parseFloat(amount),
        reference_number: referenceNumber,
        narration: finalNarration,
        voucher_date: voucherDate,
      };

      const res = await axios.post(`${API_BASE_URL}/api/v1/accounting/payment-receipt/`, payload, { headers });
      
      if (res.data.success) {
        toast.success(
          `${voucherType === 'RECEIPT' ? 'Receipt' : 'Payment'} ${res.data.voucher_number} posted!`,
          `Amount: ₹${res.data.amount}`
        );
        router.push('/vouchers');
        router.refresh();
      } else {
        toast.error('Failed to post voucher', res.data.error);
      }
    } catch (err: any) {
      toast.error('Error posting voucher', err.response?.data?.error || err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6 max-w-3xl mx-auto pb-12">

        {/* Header */}
        <div className="flex items-center gap-3 sm:gap-4 border-b border-border pb-4">
          <Link href="/vouchers" className="text-muted-foreground hover:text-foreground transition-colors p-1">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
          </Link>
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold">New Payment / Receipt</h1>
            <p className="text-muted-foreground mt-1 text-xs sm:text-sm">Record a cash or bank inflow/outflow against parties</p>
          </div>
        </div>

        {/* Type Selector */}
        <div className="grid grid-cols-2 gap-3 sm:gap-4">
          <button
            type="button"
            onClick={() => {
              setVoucherType('RECEIPT');
              setPartyLedgerId('');
            }}
            className={`p-3.5 sm:p-5 rounded-xl border-2 text-center transition-all cursor-pointer ${
              voucherType === 'RECEIPT'
                ? 'border-green-500 bg-green-500/10 shadow-sm'
                : 'border-input bg-card hover:border-zinc-500'
            }`}
          >
            <div className={`w-10 h-10 mx-auto rounded-full flex items-center justify-center mb-2 ${
              voucherType === 'RECEIPT' ? 'bg-green-500/20 text-green-400' : 'bg-muted text-muted-foreground'
            }`}>
              <ArrowDownLeft className="w-5 h-5" />
            </div>
            <p className={`text-base sm:text-lg font-bold ${voucherType === 'RECEIPT' ? 'text-green-400' : 'text-foreground'}`}>Receipt</p>
            <p className="text-muted-foreground text-xs mt-0.5 hidden sm:block">Money received from customer</p>
          </button>
          
          <button
            type="button"
            onClick={() => {
              setVoucherType('PAYMENT');
              setPartyLedgerId('');
            }}
            className={`p-3.5 sm:p-5 rounded-xl border-2 text-center transition-all cursor-pointer ${
              voucherType === 'PAYMENT'
                ? 'border-red-500 bg-red-500/10 shadow-sm'
                : 'border-input bg-card hover:border-zinc-500'
            }`}
          >
            <div className={`w-10 h-10 mx-auto rounded-full flex items-center justify-center mb-2 ${
              voucherType === 'PAYMENT' ? 'bg-red-500/20 text-red-400' : 'bg-muted text-muted-foreground'
            }`}>
              <ArrowUpRight className="w-5 h-5" />
            </div>
            <p className={`text-base sm:text-lg font-bold ${voucherType === 'PAYMENT' ? 'text-red-400' : 'text-foreground'}`}>Payment</p>
            <p className="text-muted-foreground text-xs mt-0.5 hidden sm:block">Money paid to supplier</p>
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="bg-card border border-border rounded-xl shadow-sm p-4 sm:p-6 space-y-6">
          
          {/* Party Searchable Selection */}
          <div>
            <div className="flex justify-between items-center mb-1.5">
              <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {voucherType === 'RECEIPT' ? 'Customer (Receiving From) *' : 'Supplier (Paying To) *'}
              </label>
              <Link 
                href={voucherType === 'RECEIPT' ? '/sales/customers/new' : '/purchases/suppliers/new'} 
                className="text-blue-500 hover:text-blue-400 text-xs font-medium flex items-center gap-1"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Add New {voucherType === 'RECEIPT' ? 'Customer' : 'Supplier'}</span>
              </Link>
            </div>
            <SearchableSelect
              value={partyLedgerId}
              onChange={(val) => setPartyLedgerId(val)}
              options={partyOptions}
              placeholder={voucherType === 'RECEIPT' ? '-- Select Customer --' : '-- Select Supplier --'}
              searchPlaceholder={`Type to search ${voucherType === 'RECEIPT' ? 'customer' : 'supplier'}...`}
              required
            />
          </div>

          {/* Payment Mode Selector */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
              Payment / Receipt Mode *
            </label>
            <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-2">
              {[
                { mode: 'CASH' as PaymentMode, label: 'Cash', icon: Banknote },
                { mode: 'CHEQUE' as PaymentMode, label: 'Cheque / DD', icon: FileText },
                { mode: 'NEFT' as PaymentMode, label: 'NEFT', icon: Landmark },
                { mode: 'RTGS' as PaymentMode, label: 'RTGS', icon: Zap },
                { mode: 'IMPS' as PaymentMode, label: 'IMPS', icon: Send },
                { mode: 'UPI' as PaymentMode, label: 'UPI / QR', icon: QrCode },
                { mode: 'BANK_TRANSFER' as PaymentMode, label: 'NetBanking', icon: CreditCard },
              ].map(({ mode, label, icon: Icon }) => {
                const isSelected = paymentMode === mode;
                return (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => handlePaymentModeChange(mode)}
                    className={`px-3 py-2.5 rounded-xl border text-xs font-semibold flex flex-col items-center justify-center gap-1.5 transition-all cursor-pointer ${
                      isSelected
                        ? 'bg-blue-600 text-foreground border-blue-500 shadow-md ring-2 ring-blue-500/30'
                        : 'bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground border-input'
                    }`}
                  >
                    <Icon className="w-4 h-4 shrink-0" />
                    <span className="truncate">{label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Cash / Bank Account Selector */}
          <div>
            <div className="flex justify-between items-center mb-1.5">
              <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {paymentMode === 'CASH'
                  ? (voucherType === 'RECEIPT' ? 'Received Into (Cash Account) *' : 'Paid From (Cash Account) *')
                  : (voucherType === 'RECEIPT' ? 'Received Into (Bank Account) *' : 'Paid From (Bank Account) *')}
              </label>
              {paymentMode !== 'CASH' && (
                <button
                  type="button"
                  onClick={() => setIsAddBankModalOpen(true)}
                  className="text-blue-500 hover:text-blue-400 text-xs font-semibold flex items-center gap-1 cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Add Bank Account</span>
                </button>
              )}
            </div>

            {paymentMode !== 'CASH' && bankLedgers.length === 0 ? (
              <div className="p-4 rounded-xl border border-dashed border-border bg-muted/20 text-center space-y-2">
                <p className="text-sm font-medium text-foreground">No Bank Account ledger found</p>
                <p className="text-xs text-muted-foreground">
                  You need a Bank Account ledger (e.g. HDFC Bank, SBI) to record {paymentMode} transactions.
                </p>
                <button
                  type="button"
                  onClick={() => setIsAddBankModalOpen(true)}
                  className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-lg bg-blue-600 text-foreground hover:bg-blue-700 transition-colors cursor-pointer"
                >
                  <Plus className="w-4 h-4" />
                  <span>Create Bank Account Now</span>
                </button>
              </div>
            ) : (
              <SearchableSelect
                value={paymentLedgerId}
                onChange={(val) => setPaymentLedgerId(val)}
                options={accountOptions}
                placeholder={paymentMode === 'CASH' ? '-- Select Cash Account --' : '-- Select Bank Account --'}
                searchPlaceholder="Search cash or bank account..."
                required
                onAddNew={paymentMode !== 'CASH' ? () => setIsAddBankModalOpen(true) : undefined}
                addNewText="+ Add Bank Account"
              />
            )}
          </div>

          {/* Dynamic Instrument Details Card */}
          {paymentMode !== 'CASH' && (
            <div className="p-4 sm:p-5 rounded-xl border border-border bg-muted/20 space-y-4">
              <div className="flex items-center gap-2 border-b border-border/60 pb-2">
                <span className="text-xs font-bold uppercase tracking-wider text-foreground flex items-center gap-1.5">
                  <Hash className="w-3.5 h-3.5 text-blue-400" />
                  <span>{paymentMode} Transaction Details</span>
                </span>
              </div>

              {/* CHEQUE Fields */}
              {paymentMode === 'CHEQUE' && (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-muted-foreground mb-1">
                      Cheque / DD Number *
                    </label>
                    <input
                      type="text"
                      required
                      value={chequeNo}
                      onChange={(e) => setChequeNo(e.target.value)}
                      placeholder="e.g. 004521"
                      className="w-full bg-card border border-input text-foreground px-3 py-2 rounded-lg text-sm font-mono focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-muted-foreground mb-1">
                      Cheque Date *
                    </label>
                    <input
                      type="date"
                      required
                      value={chequeDate}
                      onChange={(e) => setChequeDate(e.target.value)}
                      className="w-full bg-card border border-input text-foreground px-3 py-2 rounded-lg text-sm font-mono focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-muted-foreground mb-1">
                      Issuing / Drawn on Bank
                    </label>
                    <input
                      type="text"
                      value={bankName}
                      onChange={(e) => setBankName(e.target.value)}
                      placeholder="e.g. SBI, HDFC, ICICI"
                      className="w-full bg-card border border-input text-foreground px-3 py-2 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </div>
                </div>
              )}

              {/* NEFT / RTGS / IMPS Fields */}
              {(paymentMode === 'NEFT' || paymentMode === 'RTGS' || paymentMode === 'IMPS') && (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="sm:col-span-2">
                    <label className="block text-xs font-semibold text-muted-foreground mb-1">
                      {paymentMode} UTR / Transaction No. *
                    </label>
                    <input
                      type="text"
                      required
                      value={transactionNo}
                      onChange={(e) => setTransactionNo(e.target.value)}
                      placeholder="e.g. UTRB260909123456 or 425189201928"
                      className="w-full bg-card border border-input text-foreground px-3 py-2 rounded-lg text-sm font-mono uppercase focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-muted-foreground mb-1">
                      Transfer Date
                    </label>
                    <input
                      type="date"
                      value={transferDate}
                      onChange={(e) => setTransferDate(e.target.value)}
                      className="w-full bg-card border border-input text-foreground px-3 py-2 rounded-lg text-sm font-mono focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </div>
                </div>
              )}

              {/* UPI Fields */}
              {paymentMode === 'UPI' && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-muted-foreground mb-1">
                      UPI Ref / UTR No. (12 Digits) *
                    </label>
                    <input
                      type="text"
                      required
                      value={transactionNo}
                      onChange={(e) => setTransactionNo(e.target.value)}
                      placeholder="e.g. 425189201928"
                      className="w-full bg-card border border-input text-foreground px-3 py-2 rounded-lg text-sm font-mono focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-muted-foreground mb-1">
                      Payer UPI ID / Mobile / App
                    </label>
                    <input
                      type="text"
                      value={upiId}
                      onChange={(e) => setUpiId(e.target.value)}
                      placeholder="e.g. customer@okhdfcbank, GPay"
                      className="w-full bg-card border border-input text-foreground px-3 py-2 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </div>
                </div>
              )}

              {/* NetBanking / Other Transfer */}
              {paymentMode === 'BANK_TRANSFER' && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-muted-foreground mb-1">
                      Transaction / Reference No. *
                    </label>
                    <input
                      type="text"
                      required
                      value={transactionNo}
                      onChange={(e) => setTransactionNo(e.target.value)}
                      placeholder="e.g. TXN987654321"
                      className="w-full bg-card border border-input text-foreground px-3 py-2 rounded-lg text-sm font-mono focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-muted-foreground mb-1">
                      Transfer Date
                    </label>
                    <input
                      type="date"
                      value={transferDate}
                      onChange={(e) => setTransferDate(e.target.value)}
                      className="w-full bg-card border border-input text-foreground px-3 py-2 rounded-lg text-sm font-mono focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Amount & Voucher Date */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                Amount (₹) *
              </label>
              <input
                required
                type="number"
                step="0.01"
                min="0.01"
                placeholder="0.00"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="w-full bg-muted/50 border border-input text-foreground px-3.5 py-2.5 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all text-xl sm:text-2xl font-bold font-mono tabular-nums"
              />
            </div>
            
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                Voucher Date *
              </label>
              <input
                required
                type="date"
                value={voucherDate}
                onChange={(e) => setVoucherDate(e.target.value)}
                className="w-full bg-muted/50 border border-input text-foreground px-3.5 py-2.5 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all font-mono min-h-[44px]"
              />
            </div>
          </div>

          {/* Narration */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
              Narration / Notes
            </label>
            <textarea
              rows={2}
              placeholder="e.g. Payment against invoice INV-0021"
              value={narration}
              onChange={(e) => setNarration(e.target.value)}
              className="w-full bg-muted/50 border border-input text-foreground p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all resize-none text-sm"
            />
          </div>

          {/* Double Entry Summary Card */}
          {amount && parseFloat(amount) > 0 && (
            <div className={`rounded-xl p-4 sm:p-5 border-2 ${
              voucherType === 'RECEIPT' ? 'border-green-500/30 bg-green-500/5' : 'border-red-500/30 bg-red-500/5'
            }`}>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <p className="text-muted-foreground text-xs font-semibold uppercase tracking-wider">
                    {voucherType === 'RECEIPT' ? 'Money to Receive' : 'Money to Pay'}
                  </p>
                  <p className="text-foreground text-xs font-mono mt-1">
                    {voucherType === 'RECEIPT'
                      ? `Debit: ${paymentMode === 'CASH' ? 'Cash' : 'Bank Account'} → Credit: Customer Ledger`
                      : `Debit: Supplier Ledger → Credit: ${paymentMode === 'CASH' ? 'Cash' : 'Bank Account'}`}
                  </p>
                </div>
                <p className={`text-2xl sm:text-3xl font-bold font-mono tabular-nums ${voucherType === 'RECEIPT' ? 'text-green-500' : 'text-red-500'}`}>
                  ₹{parseFloat(amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </p>
              </div>
            </div>
          )}

          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={saving}
              className={`w-full sm:w-auto justify-center px-8 py-3 rounded-lg font-semibold text-foreground shadow-lg transition-all cursor-pointer min-h-[44px] ${
                voucherType === 'RECEIPT'
                  ? 'bg-green-600 hover:bg-green-700'
                  : 'bg-red-600 hover:bg-red-700'
              } disabled:opacity-50`}
            >
              {saving ? 'Posting...' : `Post ${voucherType === 'RECEIPT' ? 'Receipt' : 'Payment'}`}
            </button>
          </div>
        </form>

        {/* Add Bank Account Modal */}
        <AddBankModal
          isOpen={isAddBankModalOpen}
          onClose={() => setIsAddBankModalOpen(false)}
          companyId={companyId}
          onSuccess={handleBankCreated}
        />
      </div>
    </DashboardLayout>
  );
}
