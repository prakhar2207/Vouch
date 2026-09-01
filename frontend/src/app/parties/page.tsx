"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';

export default function PartiesPage() {
  const router = useRouter();
  const [parties, setParties] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login');
      return;
    }
    fetchParties();
  }, [router]);

  const fetchParties = async () => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      
      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const companyId = compRes.data.data[0]?.id;
      if (!companyId) return;

      const ledgersRes = await axios.get(`${API_BASE_URL}/api/v1/ledgers/${companyId}/`, { headers });
      
      const rawLedgers = ledgersRes.data.data || [];
      const filteredParties = rawLedgers.filter((l: any) => 
        l.group.includes('Debtor') || 
        l.group.includes('Creditor') || 
        l.name.includes('Customer') || 
        l.name.includes('Supplier')
      ).map((l: any) => ({
        ...l,
        type: l.group.includes('Debtor') ? 'Customer' : 'Supplier'
      }));

      setParties(filteredParties);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const filteredParties = parties.filter(p => p.name.toLowerCase().includes(searchTerm.toLowerCase()));

  return (
    <DashboardLayout>
      <div className="space-y-6 max-w-7xl mx-auto pb-12">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-border pb-6">
          <div>
            <h1 className="text-3xl font-bold">Parties</h1>
            <p className="text-gray-400 mt-1 text-sm">Manage your Customers and Suppliers</p>
          </div>
          <div className="flex gap-3 w-full sm:w-auto">
             <input 
                type="text" 
                placeholder="Search parties..." 
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                className="bg-zinc-900 border border-zinc-700 text-white px-4 py-2 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none flex-1 sm:w-64"
             />
            <Link href="/purchases/suppliers/new" className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg shadow transition-colors text-sm font-medium whitespace-nowrap flex items-center">
              + Supplier
            </Link>
            <Link href="/sales/customers/new" className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg shadow transition-colors text-sm font-medium whitespace-nowrap flex items-center">
              + Customer
            </Link>
          </div>
        </div>
        
        {loading ? (
            <div className="flex items-center justify-center py-20 text-gray-500">Loading parties...</div>
        ) : filteredParties.length === 0 ? (
            <div className="flex flex-col items-center justify-center text-center p-16 bg-card rounded-xl border border-border mt-8">
              <svg className="w-20 h-20 text-gray-400 dark:text-gray-600 mb-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path>
              </svg>
              <h3 className="text-2xl font-bold mb-2">No Parties Found</h3>
              <p className="text-gray-500 max-w-md mx-auto mb-8">You haven't added any customers or suppliers yet, or your search returned no results.</p>
              <div className="flex gap-4">
                <Link href="/purchases/suppliers/new" className="bg-red-600 text-white px-6 py-2.5 rounded-lg shadow hover:bg-red-700 transition-colors font-medium">
                  + Add Supplier
                </Link>
                <Link href="/sales/customers/new" className="bg-blue-600 text-white px-6 py-2.5 rounded-lg shadow hover:bg-blue-700 transition-colors font-medium">
                  + Add Customer
                </Link>
              </div>
            </div>
        ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                {filteredParties.map((party: any) => (
                    <div key={party.id} className="bg-card border border-border hover:border-zinc-500 transition-all rounded-xl p-6 flex flex-col group relative overflow-hidden">
                        
                        {/* Decorative Top Bar based on Type */}
                        <div className={`absolute top-0 left-0 right-0 h-1 ${party.type === 'Customer' ? 'bg-blue-500' : 'bg-red-500'}`}></div>

                        <div className="flex justify-between items-start mb-4 mt-1">
                            <div>
                                <h3 className="text-xl font-bold text-white mb-1 truncate pr-4" title={party.name}>{party.name}</h3>
                                <span className={`text-xs px-2.5 py-1 rounded-full border font-medium ${
                                    party.type === 'Customer' 
                                    ? 'text-blue-400 bg-blue-400/10 border-blue-400/20' 
                                    : 'text-red-400 bg-red-400/10 border-red-400/20'
                                }`}>
                                    {party.type}
                                </span>
                            </div>
                        </div>

                        <div className="space-y-3 flex-1">
                            <div className="flex justify-between text-sm">
                                <span className="text-gray-500">Ledger Group</span>
                                <span className="text-gray-300 font-medium">{party.group}</span>
                            </div>
                            
                            <div className="flex justify-between text-sm">
                                <span className="text-gray-500">Current Balance</span>
                                <div className="text-right">
                                    <span className="text-white font-bold text-lg">₹{parseFloat(party.current_balance).toLocaleString('en-IN', {minimumFractionDigits: 2})}</span>
                                    <span className="text-gray-500 ml-1 text-xs">{party.opening_balance_type}</span>
                                </div>
                            </div>
                        </div>

                        <div className="mt-6 pt-4 border-t border-zinc-800 flex justify-between items-center opacity-60 group-hover:opacity-100 transition-opacity">
                            <Link href={`/parties/${party.id}/edit`} className="text-sm text-gray-400 hover:text-white flex items-center gap-1">
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"></path></svg>
                                Edit Profile
                            </Link>
                            <Link href={`/parties/${party.id}/statement`} className="text-sm text-blue-500 hover:text-blue-400 font-medium">
                                View Statement &rarr;
                            </Link>
                        </div>
                    </div>
                ))}
            </div>
        )}
      </div>
    </DashboardLayout>
  );
}
