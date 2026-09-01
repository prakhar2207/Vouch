"use client";
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import StateSelect from '@/components/StateSelect';
import { getStateName } from '@/utils/gstStates';

export default function SettingsPage() {
  const router = useRouter();
  const [company, setCompany] = useState<any>(null);
  
  // Profile State
  const [name, setName] = useState('');
  const [gstin, setGstin] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [address, setAddress] = useState('');
  const [stateCode, setStateCode] = useState('');
  const [proprietorName, setProprietorName] = useState('');
  const [proprietorPhone, setProprietorPhone] = useState('');
  const [signature, setSignature] = useState<File | null>(null);
  
  const [tagline, setTagline] = useState('');
  const [bankName, setBankName] = useState('');
  const [bankAccountNumber, setBankAccountNumber] = useState('');
  const [bankIfsc, setBankIfsc] = useState('');
  const [bankBranch, setBankBranch] = useState('');
  
  // Settings State
  const [enableLedgerMapping, setEnableLedgerMapping] = useState(false);
  const [enableManualInvoice, setEnableManualInvoice] = useState(false);
  const [enableAdvancedItemCreation, setEnableAdvancedItemCreation] = useState(false);
  const [complexityLevel, setComplexityLevel] = useState(1);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login');
      return;
    }
    fetchCompany();
  }, [router]);

  const fetchCompany = async () => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const compRes = await axios.get('http://localhost:8000/api/v1/companies/', { headers });
      const comp = compRes.data.data[0];
      if (comp) {
        setCompany(comp);
        
        // Populate profile
        setName(comp.name || '');
        setGstin(comp.gstin || '');
        setEmail(comp.email || '');
        setPhone(comp.phone || '');
        setAddress(comp.address || '');
        setStateCode(comp.state_code || '');
        setProprietorName(comp.proprietor_name || '');
        setProprietorPhone(comp.proprietor_phone || '');
        
        setTagline(comp.tagline || '');
        setBankName(comp.bank_name || '');
        setBankAccountNumber(comp.bank_account_number || '');
        setBankIfsc(comp.bank_ifsc || '');
        setBankBranch(comp.bank_branch || '');

        // Populate settings
        setEnableLedgerMapping(comp.settings?.enable_ledger_mapping || false);
        setEnableManualInvoice(comp.settings?.enable_manual_invoice_number || false);
        setEnableAdvancedItemCreation(comp.settings?.enable_advanced_item_creation || false);
        setComplexityLevel(comp.settings?.complexity_level || 1);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const saveSettings = async () => {
    if (!company) return;
    setSaving(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      
      // Update Settings
      await axios.patch(`http://localhost:8000/api/v1/companies/${company.id}/update_settings/`, {
        enable_ledger_mapping: enableLedgerMapping,
        enable_manual_invoice_number: enableManualInvoice,
        enable_advanced_item_creation: enableAdvancedItemCreation,
        complexity_level: complexityLevel
      }, { headers });

      // Update Profile
      const formData = new FormData();
      formData.append('name', name);
      formData.append('gstin', gstin);
      formData.append('email', email);
      formData.append('phone', phone);
      formData.append('address', address);
      formData.append('state_code', stateCode);
      const sName = getStateName(stateCode);
      if (sName) {
        formData.append('state_name', sName);
      }
      formData.append('proprietor_name', proprietorName);
      formData.append('proprietor_phone', proprietorPhone);
      if (signature) {
        formData.append('proprietor_signature', signature);
      }
      formData.append('tagline', tagline);
      formData.append('bank_name', bankName);
      formData.append('bank_account_number', bankAccountNumber);
      formData.append('bank_ifsc', bankIfsc);
      formData.append('bank_branch', bankBranch);
      
      await axios.patch(`http://localhost:8000/api/v1/companies/${company.id}/`, formData, { 
        headers: {
          ...headers,
          'Content-Type': 'multipart/form-data'
        }
      });
      
      alert('Profile and Settings updated successfully!');
      fetchCompany();
    } catch (err) {
      console.error(err);
      alert('Failed to update profile/settings');
    } finally {
      setSaving(false);
    }
  };

  const handleSignatureChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setSignature(e.target.files[0]);
    }
  };

  return (
    <DashboardLayout>
      <div className="max-w-3xl mx-auto space-y-8">
        <div>
          <h1 className="text-3xl font-bold">Profile & Settings</h1>
          <p className="text-gray-400 mt-1">Manage your company preferences</p>
        </div>

        {company ? (
          <div className="bg-card border border-border rounded-xl shadow-sm p-6 space-y-8">
            {/* Company Profile Edit */}
            <div>
              <h2 className="text-lg font-semibold text-white mb-4 border-b border-zinc-800 pb-2">Firm Details</h2>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Firm Name</label>
                  <input type="text" value={name} onChange={e => setName(e.target.value)} className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded outline-none" />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">GSTIN</label>
                  <input type="text" value={gstin} onChange={e => setGstin(e.target.value.toUpperCase())} className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded outline-none uppercase" />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Email</label>
                  <input type="email" value={email} onChange={e => setEmail(e.target.value)} className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded outline-none" />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Phone</label>
                  <input type="tel" value={phone} onChange={e => setPhone(e.target.value)} className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded outline-none" />
                </div>
                <div>
                  <StateSelect
                    value={stateCode}
                    onChange={(code) => setStateCode(code)}
                    label="State / Union Territory"
                    placeholder="Search state by name or code (e.g. 09 / Uttar Pradesh)"
                  />
                </div>
                <div className="col-span-2">
                  <label className="block text-sm text-gray-400 mb-1">Billing Address</label>
                  <textarea value={address} onChange={e => setAddress(e.target.value)} rows={3} className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded outline-none resize-none" />
                </div>
                <div className="col-span-2">
                  <label className="block text-sm text-gray-400 mb-1">Tagline / Subheading (Printed below firm name)</label>
                  <input type="text" value={tagline} onChange={e => setTagline(e.target.value)} placeholder="e.g. HARDWARE, MILL STORES, PNEUMATICS" className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded outline-none" />
                </div>
              </div>
            </div>

            <div>
              <h2 className="text-lg font-semibold text-white mb-4 border-b border-zinc-800 pb-2">Bank Details</h2>
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label className="block text-sm text-gray-400 mb-1">Bank Name</label>
                  <input type="text" value={bankName} onChange={e => setBankName(e.target.value)} placeholder="e.g. State Bank of India" className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded outline-none" />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Account Number</label>
                  <input type="text" value={bankAccountNumber} onChange={e => setBankAccountNumber(e.target.value)} className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded outline-none" />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">IFSC Code</label>
                  <input type="text" value={bankIfsc} onChange={e => setBankIfsc(e.target.value.toUpperCase())} className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded outline-none uppercase" />
                </div>
                <div className="col-span-2">
                  <label className="block text-sm text-gray-400 mb-1">Branch</label>
                  <input type="text" value={bankBranch} onChange={e => setBankBranch(e.target.value)} className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded outline-none" />
                </div>
              </div>
            </div>

            <div>
              <h2 className="text-lg font-semibold text-white mb-4 border-b border-zinc-800 pb-2">Proprietor Details</h2>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Proprietor Name</label>
                  <input type="text" value={proprietorName} onChange={e => setProprietorName(e.target.value)} className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded outline-none" />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Proprietor Phone</label>
                  <input type="tel" value={proprietorPhone} onChange={e => setProprietorPhone(e.target.value)} className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded outline-none" />
                </div>
                <div className="col-span-2 mt-2">
                  <label className="block text-sm text-gray-400 mb-2">Digital Signature</label>
                  {company.proprietor_signature && (
                    <div className="mb-3 p-2 bg-white rounded w-fit">
                      <img src={`http://localhost:8000${company.proprietor_signature}`} alt="Signature" className="h-16 object-contain" />
                    </div>
                  )}
                  <input type="file" accept="image/*" onChange={handleSignatureChange} className="block w-full text-sm text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-500/10 file:text-blue-400 hover:file:bg-blue-500/20" />
                </div>
              </div>
            </div>

            <div>
              <h2 className="text-lg font-semibold text-white mb-4 border-b border-zinc-800 pb-2">Business Type & Complexity</h2>
              <div className="bg-zinc-900/50 p-4 rounded-lg border border-zinc-800 space-y-3">
                <label className="block text-white font-medium">Retailer Scale (Complexity Level)</label>
                <p className="text-gray-500 text-sm">
                  This controls how many advanced ERP features (like Godowns, Batches, Serials) are visible by default. 
                  The system auto-scales this as you create more categories, but you can manually override it here.
                </p>
                <select 
                  value={complexityLevel}
                  onChange={(e) => setComplexityLevel(Number(e.target.value))}
                  className="w-full max-w-md bg-zinc-800 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                >
                  <option value={1}>Level 1: Basic Retailer (1-5 Categories) - Simplest UI</option>
                  <option value={2}>Level 2: Growing Business (6-10 Categories) - Intermediate</option>
                  <option value={3}>Level 3: Advanced ERP (10+ Categories) - Full Features</option>
                </select>
              </div>
            </div>

            <div>
              <h2 className="text-lg font-semibold text-white mb-4 border-b border-zinc-800 pb-2">Accounting Preferences</h2>
              
              <div className="flex items-center justify-between bg-zinc-900/50 p-4 rounded-lg border border-zinc-800">
                <div>
                  <h3 className="text-white font-medium">Advanced Ledger Mapping</h3>
                  <p className="text-gray-500 text-sm mt-1">
                    Allow selecting specific Sales & Purchase ledgers for inter-state trading, exports, etc. 
                    If disabled, the system will default to a general "Sales Account" or "Purchase Account".
                  </p>
                </div>
                <button 
                  onClick={() => setEnableLedgerMapping(!enableLedgerMapping)}
                  className={`w-12 h-7 rounded-full transition-all relative shrink-0 ${enableLedgerMapping ? 'bg-blue-600' : 'bg-zinc-700'}`}
                >
                  <div className={`w-5 h-5 bg-white rounded-full absolute top-1 transition-all ${enableLedgerMapping ? 'left-6' : 'left-1'}`}></div>
                </button>
              </div>
              
              <div className="flex items-center justify-between bg-zinc-900/50 p-4 rounded-lg border border-zinc-800 mt-4">
                <div>
                  <h3 className="text-white font-medium">Manual Invoice Number & Date</h3>
                  <p className="text-gray-500 text-sm mt-1">
                    Allow manually entering custom invoice numbers and backdating invoices. 
                    If disabled, the system strictly auto-generates them upon saving.
                  </p>
                </div>
                <button 
                  onClick={() => setEnableManualInvoice(!enableManualInvoice)}
                  className={`w-12 h-7 rounded-full transition-all relative shrink-0 ${enableManualInvoice ? 'bg-blue-600' : 'bg-zinc-700'}`}
                >
                  <div className={`w-5 h-5 bg-white rounded-full absolute top-1 transition-all ${enableManualInvoice ? 'left-6' : 'left-1'}`}></div>
                </button>
              </div>
              <div className="flex items-center justify-between bg-zinc-900/50 p-4 rounded-lg border border-zinc-800 mt-4">
                <div>
                  <h3 className="text-white font-medium">Advanced Item Creation</h3>
                  <p className="text-gray-500 text-sm mt-1">
                    Show advanced options (Pricing Matrix, Multiple Packaging, Tax Override, Batch/Serial tracking) when creating a new item. 
                    If disabled, keeps item creation simple.
                  </p>
                </div>
                <button 
                  onClick={() => setEnableAdvancedItemCreation(!enableAdvancedItemCreation)}
                  className={`w-12 h-7 rounded-full transition-all relative shrink-0 ${enableAdvancedItemCreation ? 'bg-blue-600' : 'bg-zinc-700'}`}
                >
                  <div className={`w-5 h-5 bg-white rounded-full absolute top-1 transition-all ${enableAdvancedItemCreation ? 'left-6' : 'left-1'}`}></div>
                </button>
              </div>
            </div>

            <div className="flex justify-end pt-4 border-t border-zinc-800">
              <button 
                onClick={saveSettings} 
                disabled={saving}
                className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg font-medium shadow transition-colors disabled:opacity-50"
              >
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        ) : (
          <div className="text-gray-500">Loading settings...</div>
        )}
      </div>
    </DashboardLayout>
  );
}
