"use client";

import { useState } from 'react';
import axios from 'axios';
import { setTokens } from '@/utils/auth';
import { useRouter } from 'next/navigation';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const router = useRouter();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await axios.post('http://localhost:8000/api/v1/auth/login/', { email: username, password });
      setTokens(res.data.access, res.data.refresh);
      router.push('/dashboard');
    } catch (err) {
      setError('Invalid credentials');
    }
  };

  return (
    <div className="flex h-screen items-center justify-center bg-background text-foreground">
      <div className="bg-card text-card-foreground p-8 rounded shadow-md border border-border w-96">
        <h1 className="text-2xl font-bold mb-6">Vouch Login</h1>
        {error && <p className="text-red-500 mb-4 text-sm">{error}</p>}
        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="block text-sm font-semibold mb-1">Username</label>
            <input 
              type="text" 
              className="w-full border p-2 rounded bg-background" 
              value={username} 
              onChange={e => setUsername(e.target.value)} 
              required 
            />
          </div>
          <div>
            <label className="block text-sm font-semibold mb-1">Password</label>
            <input 
              type="password" 
              className="w-full border p-2 rounded bg-background" 
              value={password} 
              onChange={e => setPassword(e.target.value)} 
              required 
            />
          </div>
          <button type="submit" className="w-full bg-blue-600 text-white p-2 rounded font-bold hover:bg-blue-700">
            Login
          </button>
        </form>

        <div className="mt-6 text-center text-sm text-gray-500">
          Don't have an account? <a href="/register" className="text-blue-400 hover:underline">Register here</a>
        </div>
      </div>
    </div>
  );
}
