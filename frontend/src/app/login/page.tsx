"use client";

import { API_BASE_URL } from '@/utils/api';
import { useState, useEffect } from 'react';
import axios from 'axios';
import { isCapacitorNative, setAuthenticatedSession, setUser } from '@/utils/auth';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Eye, EyeOff, LogIn, AlertCircle } from 'lucide-react';
import { VouchLogo } from '@/components/VouchLogo';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [sessionExpiredNotice, setSessionExpiredNotice] = useState(false);
  const [loading, setLoading] = useState(false);
  const [warmingUp, setWarmingUp] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const router = useRouter();

  // Pre-warm backend container and detect if navigated due to session expiry
  useEffect(() => {
    if (typeof window !== 'undefined' && window.location.search.includes('expired=1')) {
      setSessionExpiredNotice(true);
    }
    try {
      fetch(`${API_BASE_URL}/api/health/`, { method: 'GET', keepalive: true }).catch(() => {});
    } catch {
      // Passive warm-up attempt, ignore network drops
    }
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setWarmingUp(false);

    // If request takes longer than 2.5s (due to container sleep / cold start), inform the user
    const slowTimer = setTimeout(() => {
      setWarmingUp(true);
    }, 2500);

    try {
      const native = isCapacitorNative();
      const res = await axios.post(
        `${API_BASE_URL}/api/v1/auth/login/`,
        { email: username, password },
        {
          withCredentials: !native,
          headers: { 'X-Client-Type': native ? 'capacitor' : 'web' },
        }
      );
      clearTimeout(slowTimer);
      setAuthenticatedSession({
        user: res.data.user,
        csrfToken: res.data.csrf_token,
        expiresAt: res.data.expires_at,
        refreshExpiresAt: res.data.refresh_expires_at,
        access: res.data.access,
        refresh: res.data.refresh,
      });
      if (res.data.user) {
        setUser(res.data.user);
      }
      const user = res.data.user;
      if (user?.is_superuser) {
        if (typeof window !== 'undefined') {
          localStorage.removeItem('vouch_active_company_id');
        }
        router.push('/admin');
      } else {
        router.push('/dashboard');
      }
    } catch (err: any) {
      clearTimeout(slowTimer);
      setWarmingUp(false);
      const serverErr = err.response?.data?.email || err.response?.data?.detail || err.response?.data?.error;
      if (Array.isArray(serverErr)) {
        setError(serverErr[0]);
      } else if (serverErr) {
        setError(serverErr);
      } else {
        setError('Invalid credentials. Please check your email and password.');
      }
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background text-foreground p-4 relative overflow-hidden">
      {/* Ambient gradient glow */}
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[300px] bg-gradient-to-tr from-primary/20 via-amber-500/10 to-transparent blur-3xl pointer-events-none rounded-full" />
      <div className="absolute bottom-0 right-0 w-[400px] h-[200px] bg-gradient-to-tl from-primary/10 via-amber-500/5 to-transparent blur-3xl pointer-events-none rounded-full" />

      <div className="relative z-10 bg-card/80 backdrop-blur-xl text-card-foreground p-6 sm:p-8 rounded-2xl shadow-xl shadow-black/5 border border-border/50 w-full max-w-sm">
        {/* Branding */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-4">
            <VouchLogo size={36} showWordmark={true} />
            <span className="px-2 py-0.5 text-xs font-mono font-semibold text-muted-foreground bg-muted border border-border rounded-md">
              CORE
            </span>
          </div>
          <h1 className="text-xl font-extrabold text-foreground">Welcome back</h1>
          <p className="text-xs text-muted-foreground mt-1">Sign in to your accounting workspace</p>
        </div>

        {/* Session Expired Notice */}
        {sessionExpiredNotice && !error && (
          <div role="status" className="bg-amber-500/10 border border-amber-500/20 text-amber-500 p-3 rounded-xl mb-5 text-xs flex items-start gap-2 animate-in fade-in">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>Your session has expired. Please sign in again to continue.</span>
          </div>
        )}

        {/* Error */}
        {error && (
          <div role="alert" aria-live="assertive" className="bg-destructive/10 border border-destructive/20 text-destructive p-3 rounded-xl mb-5 text-xs flex items-start gap-2 animate-in fade-in">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleLogin} className="space-y-4">
          {/* Email Field */}
          <div>
            <label htmlFor="login-email" className="block text-xs font-semibold mb-1.5 text-foreground">Email</label>
            <input 
              id="login-email"
              type="email" 
              autoComplete="email"
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
              <label htmlFor="login-password" className="text-xs font-semibold text-foreground">Password</label>
              <Link 
                href="/forgot-password"
                className="text-xs text-muted-foreground hover:text-primary transition-colors"
              >
                Forgot password?
              </Link>
            </div>
            <div className="relative">
              <input 
                id="login-password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                className="w-full bg-muted/50 border border-input p-3 pr-10 rounded-xl text-sm text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition-all" 
                value={password} 
                onChange={e => setPassword(e.target.value)} 
                placeholder="••••••••"
                required 
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors cursor-pointer p-1 rounded-md"
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Submit */}
          <button 
            type="submit" 
            disabled={loading}
            className="w-full min-h-[44px] bg-primary text-primary-foreground p-3 rounded-xl font-bold text-sm hover:bg-primary/90 transition-all shadow-md shadow-primary/20 disabled:opacity-75 cursor-pointer flex items-center justify-center gap-2"
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <span className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                Signing in...
              </span>
            ) : (
              <>
                <LogIn className="w-4 h-4" />
                Sign In
              </>
            )}
          </button>

          {/* Cold-start alert for free-tier backends */}
          {warmingUp && (
            <p className="text-[11px] text-center text-amber-500/90 animate-pulse transition-opacity">
              Connecting to secure database...
            </p>
          )}
        </form>

        <div className="mt-8 pt-6 border-t border-border/50 text-center">
          <p className="text-xs text-muted-foreground">
            Don't have an account?{' '}
            <Link href="/register" className="text-primary hover:underline font-semibold transition-colors">
              Create an account
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
