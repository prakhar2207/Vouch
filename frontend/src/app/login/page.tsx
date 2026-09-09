"use client";

import { API_BASE_URL } from '@/utils/api';
import { useState } from 'react';
import axios from 'axios';
import { setTokens } from '@/utils/auth';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Eye, EyeOff, LogIn, AlertCircle } from 'lucide-react';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const router = useRouter();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await axios.post(`${API_BASE_URL}/api/v1/auth/login/`, { email: username, password });
      setTokens(res.data.access, res.data.refresh);
      router.push('/dashboard');
    } catch (err) {
      setError('Invalid credentials. Please check your email and password.');
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background text-foreground p-4 relative overflow-hidden">
      {/* Ambient gradient glow */}
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[300px] bg-gradient-to-tr from-primary/20 via-purple-500/10 to-transparent blur-3xl pointer-events-none rounded-full" />
      <div className="absolute bottom-0 right-0 w-[400px] h-[200px] bg-gradient-to-tl from-primary/10 via-transparent to-transparent blur-3xl pointer-events-none rounded-full" />

      <div className="relative z-10 bg-card/80 backdrop-blur-xl text-card-foreground p-6 sm:p-8 rounded-2xl shadow-xl shadow-black/5 border border-border/50 w-full max-w-sm">
        {/* Branding */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-4">
            <span className="text-3xl font-black tracking-tight bg-gradient-to-r from-blue-600 via-indigo-600 to-violet-600 bg-clip-text text-transparent">
              Vouch
            </span>
            <span className="px-2 py-0.5 text-xs font-mono font-semibold text-muted-foreground bg-muted border border-border rounded-md">
              CORE
            </span>
          </div>
          <h1 className="text-xl font-extrabold text-foreground">Welcome back</h1>
          <p className="text-xs text-muted-foreground mt-1">Sign in to your accounting workspace</p>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-destructive/10 border border-destructive/20 text-destructive p-3 rounded-xl mb-5 text-xs flex items-start gap-2 animate-in fade-in">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleLogin} className="space-y-4">
          {/* Email Field */}
          <div>
            <label className="block text-xs font-semibold mb-1.5 text-foreground">Email</label>
            <input 
              type="text" 
              className="w-full bg-muted/50 border border-input p-3 rounded-xl text-sm text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition-all" 
              value={username} 
              onChange={e => setUsername(e.target.value)} 
              placeholder="you@company.com"
              required 
              autoFocus
            />
          </div>

          {/* Password Field */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-semibold text-foreground">Password</label>
              <span className="text-xs text-muted-foreground hover:text-foreground cursor-pointer">Forgot password?</span>
            </div>
            <div className="relative">
              <input 
                type={showPassword ? 'text' : 'password'}
                className="w-full bg-muted/50 border border-input p-3 pr-10 rounded-xl text-sm text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition-all" 
                value={password} 
                onChange={e => setPassword(e.target.value)} 
                placeholder="••••••••"
                required 
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                tabIndex={-1}
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Submit */}
          <button 
            type="submit" 
            disabled={loading}
            className="w-full min-h-[44px] bg-primary text-primary-foreground p-3 rounded-xl font-bold text-sm hover:bg-primary/90 transition-all shadow-md shadow-primary/20 disabled:opacity-60 cursor-pointer flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <span className="w-4 h-4 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin" />
                <span>Signing in...</span>
              </>
            ) : (
              <>
                <LogIn className="w-4 h-4" />
                <span>Sign In</span>
              </>
            )}
          </button>
        </form>

        {/* Footer */}
        <div className="mt-6 text-center text-xs text-muted-foreground">
          Don't have an account?{' '}
          <Link href="/register" className="text-primary hover:underline font-semibold">
            Register here
          </Link>
        </div>

        {/* Keyboard hint */}
        <div className="mt-4 text-center">
          <span className="text-xs text-muted-foreground font-mono">
            Press Enter to sign in
          </span>
        </div>
      </div>
    </div>
  );
}
