"use client";

import { API_BASE_URL } from '@/utils/api';
import { useState } from 'react';
import axios from 'axios';
import { setTokens } from '@/utils/auth';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import StateSelect from '@/components/StateSelect';

export default function Register() {
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const router = useRouter();

  // Step 1: Auth
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  
  // Step 2: Firm Details
  const [firmName, setFirmName] = useState('');
  const [gstin, setGstin] = useState('');
  const [phone, setPhone] = useState('');
  const [companyEmail, setCompanyEmail] = useState('');
  const [address, setAddress] = useState('');
  const [stateCode, setStateCode] = useState('');

  // Step 3: Proprietor Details (Optional)
  const [proprietorName, setProprietorName] = useState('');
  const [proprietorPhone, setProprietorPhone] = useState('');
  
  const handleNext = (e: React.FormEvent) => {
    e.preventDefault();
    if (step === 1 && (!email || !password)) return;
    if (step === 2 && (!firmName || !gstin || !phone || !address || !stateCode)) return;
    setStep(step + 1);
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    
    try {
      const payload = {
        email,
        password,
        name: firmName,
        gstin,
        phone,
        company_email: companyEmail || email,
        address,
        state_code: stateCode,
        proprietor_name: proprietorName,
        proprietor_phone: proprietorPhone
      };
      
      const res = await axios.post(`${API_BASE_URL}/api/v1/auth/register/`, payload);
      
      // Store tokens and redirect
      if (res.data.success) {
        setTokens(res.data.access, res.data.refresh);
        router.push('/dashboard');
      } else {
        setError(res.data.error || 'Registration failed');
      }
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to register. Email may already exist.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background text-foreground py-12">
      <div className="bg-card text-card-foreground p-8 rounded-xl shadow-lg border border-border w-full max-w-lg">
        
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold mb-2">Create your Vouch Account</h1>
          <p className="text-gray-400 text-sm">
            Step {step} of 3: {step === 1 ? 'Account Details' : step === 2 ? 'Firm Details' : 'Proprietor Details'}
          </p>
          <div className="flex gap-2 justify-center mt-4">
            <div className={`h-1.5 w-12 rounded-full ${step >= 1 ? 'bg-blue-500' : 'bg-zinc-800'}`}></div>
            <div className={`h-1.5 w-12 rounded-full ${step >= 2 ? 'bg-blue-500' : 'bg-zinc-800'}`}></div>
            <div className={`h-1.5 w-12 rounded-full ${step >= 3 ? 'bg-blue-500' : 'bg-zinc-800'}`}></div>
          </div>
        </div>

        {error && <p className="bg-red-500/10 border border-red-500/20 text-red-400 p-3 rounded-lg mb-6 text-sm">{error}</p>}
        
        <form onSubmit={step === 3 ? handleRegister : handleNext} className="space-y-5">
          
          {/* STEP 1: AUTH */}
          {step === 1 && (
            <div className="space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-300">
              <div>
                <label className="block text-sm font-semibold mb-1 text-gray-300">Login Email *</label>
                <input type="email" value={email} onChange={e => setEmail(e.target.value)} required className="w-full bg-zinc-900 border border-zinc-700 p-2.5 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none" placeholder="admin@example.com" />
              </div>
              <div>
                <label className="block text-sm font-semibold mb-1 text-gray-300">Password *</label>
                <input type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={6} className="w-full bg-zinc-900 border border-zinc-700 p-2.5 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none" placeholder="••••••••" />
              </div>
            </div>
          )}

          {/* STEP 2: FIRM DETAILS */}
          {step === 2 && (
            <div className="space-y-4 animate-in fade-in slide-in-from-right-4 duration-300">
              <div>
                <label className="block text-sm font-semibold mb-1 text-gray-300">Firm Name *</label>
                <input type="text" value={firmName} onChange={e => setFirmName(e.target.value)} required className="w-full bg-zinc-900 border border-zinc-700 p-2.5 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none" placeholder="Your Business Name" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-semibold mb-1 text-gray-300">GSTIN *</label>
                  <input type="text" value={gstin} onChange={e => setGstin(e.target.value.toUpperCase())} required className="w-full bg-zinc-900 border border-zinc-700 p-2.5 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none uppercase" placeholder="22AAAAA0000A1Z5" maxLength={15} />
                </div>
                <div>
                  <label className="block text-sm font-semibold mb-1 text-gray-300">Mobile No. *</label>
                  <input type="tel" value={phone} onChange={e => setPhone(e.target.value)} required className="w-full bg-zinc-900 border border-zinc-700 p-2.5 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none" placeholder="+91 9876543210" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-semibold mb-1 text-gray-300">Company Email (Optional)</label>
                  <input type="email" value={companyEmail} onChange={e => setCompanyEmail(e.target.value)} className="w-full bg-zinc-900 border border-zinc-700 p-2.5 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none" placeholder="contact@business.com" />
                </div>
                <div>
                  <StateSelect
                    value={stateCode}
                    onChange={(code) => setStateCode(code)}
                    label="State / Union Territory *"
                    placeholder="Search state or code..."
                    required
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-semibold mb-1 text-gray-300">Billing Address *</label>
                <textarea value={address} onChange={e => setAddress(e.target.value)} required rows={3} className="w-full bg-zinc-900 border border-zinc-700 p-2.5 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none resize-none" placeholder="Full business address..." />
              </div>
            </div>
          )}

          {/* STEP 3: PROPRIETOR DETAILS */}
          {step === 3 && (
            <div className="space-y-4 animate-in fade-in slide-in-from-right-4 duration-300">
              <div className="bg-blue-500/10 border border-blue-500/20 p-4 rounded-lg mb-4">
                <p className="text-sm text-blue-400">
                  <span className="font-bold">Note:</span> These details are optional right now, but they are <strong>compulsory before you can generate invoices</strong>.
                </p>
              </div>
              
              <div>
                <label className="block text-sm font-semibold mb-1 text-gray-300">Proprietor Name</label>
                <input type="text" value={proprietorName} onChange={e => setProprietorName(e.target.value)} className="w-full bg-zinc-900 border border-zinc-700 p-2.5 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none" placeholder="e.g. Rahul Sharma" />
              </div>
              <div>
                <label className="block text-sm font-semibold mb-1 text-gray-300">Proprietor Phone</label>
                <input type="tel" value={proprietorPhone} onChange={e => setProprietorPhone(e.target.value)} className="w-full bg-zinc-900 border border-zinc-700 p-2.5 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none" placeholder="+91 9876543210" />
              </div>
              
              <div>
                <label className="block text-sm font-semibold mb-1 text-gray-300">Digital Signature</label>
                <div className="border-2 border-dashed border-zinc-700 rounded-lg p-6 text-center bg-zinc-900/50">
                  <p className="text-gray-500 text-sm mb-2">You can upload your signature later from the Profile Settings.</p>
                </div>
              </div>
            </div>
          )}

          <div className="flex gap-4 pt-4 mt-8 border-t border-zinc-800">
            {step > 1 && (
              <button type="button" onClick={() => setStep(step - 1)} className="flex-1 bg-zinc-800 text-white p-3 rounded-lg font-bold hover:bg-zinc-700 transition-colors">
                Back
              </button>
            )}
            
            <button type="submit" disabled={loading} className="flex-1 bg-blue-600 text-white p-3 rounded-lg font-bold hover:bg-blue-700 transition-colors shadow-lg disabled:opacity-50">
              {loading ? 'Processing...' : step === 3 ? 'Complete Registration' : 'Next Step →'}
            </button>
          </div>
          
        </form>

        <div className="mt-8 text-center text-sm text-gray-500">
          Already have an account? <Link href="/login" className="text-blue-400 hover:underline">Log in</Link>
        </div>
      </div>
    </div>
  );
}
