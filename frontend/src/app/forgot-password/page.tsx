"use client";

import { API_BASE_URL } from '@/utils/api';
import { useState } from 'react';
import axios from 'axios';
import Link from 'next/link';
import { ArrowLeft, Mail, AlertCircle, CheckCircle2 } from 'lucide-react';
import { VouchLogo } from '@/components/VouchLogo';

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      await axios.post(`${API_BASE_URL}/api/v1/auth/password/reset/request/`, {
        email: email.trim().toLowerCase(),
      });
      setSubmitted(true);
    } catch (err: any) {
      // Security: even on network error, keep message safe
      setError(err.response?.data?.error || 'Unable to request password reset. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background text-foreground p-4 relative overflow-hidden">
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[300px] bg-gradient-to-tr from-primary/20 via-blue-500/10 to-transparent blur-3xl pointer-events-none rounded-full" />

      <div className="relative z-10 bg-card/80 backdrop-blur-xl text-card-foreground p-6 sm:p-8 rounded-2xl shadow-xl border border-border/50 w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-4">
            <VouchLogo size={36} showWordmark={true} />
          </div>
          <h1 className="text-xl font-extrabold text-foreground">Reset Password</h1>
          <p className="text-xs text-muted-foreground mt-1">
            Enter your registered email to receive a password reset link.
          </p>
        </div>

        {error && (
          <div role="alert" className="bg-destructive/10 border border-destructive/20 text-destructive p-3 rounded-xl mb-5 text-xs flex items-start gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {submitted ? (
          <div className="space-y-5 text-center">
            <div className="w-12 h-12 bg-emerald-500/10 border border-emerald-500/20 text-emerald-500 rounded-full flex items-center justify-center mx-auto">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <div className="space-y-1">
              <h2 className="text-sm font-bold text-foreground">Check your inbox</h2>
              <p className="text-xs text-muted-foreground leading-relaxed">
                If an account exists for <strong className="text-foreground">{email}</strong>, we've sent instructions to reset your password.
              </p>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Didn't receive it? Check your spam folder or try requesting again in a few minutes.
            </p>
            <div className="pt-2">
              <Link
                href="/login"
                className="w-full inline-flex items-center justify-center gap-2 bg-muted text-foreground p-3 rounded-xl text-xs font-semibold hover:bg-muted/80 transition-colors"
              >
                <ArrowLeft className="w-3.5 h-3.5" /> Back to Login
              </Link>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="reset-email" className="block text-xs font-semibold mb-1.5 text-foreground">
                Email Address
              </label>
              <input
                id="reset-email"
                type="email"
                autoComplete="email"
                className="w-full bg-muted/50 border border-input p-3 rounded-xl text-sm text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring transition-all"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                required
                autoFocus
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full min-h-[44px] bg-primary text-primary-foreground p-3 rounded-xl font-bold text-sm hover:bg-primary/90 transition-all shadow-md shadow-primary/20 disabled:opacity-75 flex items-center justify-center gap-2 cursor-pointer"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                  Sending link...
                </span>
              ) : (
                <>
                  <Mail className="w-4 h-4" /> Send Reset Link
                </>
              )}
            </button>

            <div className="pt-4 text-center">
              <Link
                href="/login"
                className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 transition-colors"
              >
                <ArrowLeft className="w-3 h-3" /> Back to Sign In
              </Link>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
