"use client";

import { API_BASE_URL } from '@/utils/api';
import { useState, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import axios from 'axios';
import Link from 'next/link';
import { Eye, EyeOff, Lock, AlertCircle, CheckCircle2 } from 'lucide-react';
import { VouchLogo } from '@/components/VouchLogo';

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const uid = searchParams.get('uid') || '';
  const token = searchParams.get('token') || '';

  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uid || !token) {
      setError('Invalid or expired password reset link. Please request a new one.');
      return;
    }

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters long.');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const res = await axios.post(`${API_BASE_URL}/api/v1/auth/password/reset/confirm/`, {
        uid,
        token,
        new_password: newPassword,
      });

      if (res.data.success) {
        setSuccess(true);
      } else {
        setError(res.data.error || 'Failed to reset password.');
      }
    } catch (err: any) {
      setError(err.response?.data?.error || 'Invalid or expired reset link. Please request a new one.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative z-10 bg-card/80 backdrop-blur-xl text-card-foreground p-6 sm:p-8 rounded-2xl shadow-xl border border-border/50 w-full max-w-sm">
      <div className="text-center mb-8">
        <div className="inline-flex items-center gap-2 mb-4">
          <VouchLogo size={36} showWordmark={true} />
        </div>
        <h1 className="text-xl font-extrabold text-foreground">Set New Password</h1>
        <p className="text-xs text-muted-foreground mt-1">
          Choose a strong password with at least 8 characters.
        </p>
      </div>

      {error && (
        <div role="alert" className="bg-destructive/10 border border-destructive/20 text-destructive p-3 rounded-xl mb-5 text-xs flex items-start gap-2">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {success ? (
        <div className="space-y-5 text-center">
          <div className="w-12 h-12 bg-emerald-500/10 border border-emerald-500/20 text-emerald-500 rounded-full flex items-center justify-center mx-auto">
            <CheckCircle2 className="w-6 h-6" />
          </div>
          <div className="space-y-1">
            <h2 className="text-sm font-bold text-foreground">Password Reset Complete</h2>
            <p className="text-xs text-muted-foreground">
              Your password has been updated. All previous sessions have been securely revoked.
            </p>
          </div>
          <div className="pt-2">
            <Link
              href="/login"
              className="w-full inline-flex items-center justify-center gap-2 bg-primary text-primary-foreground p-3 rounded-xl text-xs font-semibold hover:bg-primary/90 transition-colors shadow-md"
            >
              Sign In with New Password &rarr;
            </Link>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold mb-1.5 text-foreground">
              New Password
            </label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                className="w-full bg-muted/50 border border-input p-3 pr-10 rounded-xl text-sm text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring transition-all"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="••••••••"
                required
                autoFocus
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground p-1"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold mb-1.5 text-foreground">
              Confirm New Password
            </label>
            <input
              type={showPassword ? 'text' : 'password'}
              className="w-full bg-muted/50 border border-input p-3 rounded-xl text-sm text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring transition-all"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="••••••••"
              required
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
                Updating password...
              </span>
            ) : (
              <>
                <Lock className="w-4 h-4" /> Reset Password
              </>
            )}
          </button>
        </form>
      )}
    </div>
  );
}

export default function ResetPassword() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background text-foreground p-4 relative overflow-hidden">
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[300px] bg-gradient-to-tr from-primary/20 via-blue-500/10 to-transparent blur-3xl pointer-events-none rounded-full" />
      <Suspense fallback={<div className="text-center text-sm">Loading security token...</div>}>
        <ResetPasswordForm />
      </Suspense>
    </div>
  );
}
