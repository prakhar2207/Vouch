"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  CheckCircle2,
  FileSearch,
  Lock,
  Mail,
  ShieldAlert,
  Trash2,
} from "lucide-react";
import { PublicHeader } from "@/components/public/PublicHeader";
import { PublicFooter } from "@/components/public/PublicFooter";
import { SRILEKH_PUBLIC } from "@/components/public/public-constants";
import { api, API_BASE_URL } from "@/utils/api";
import { isAuthenticated, removeTokens } from "@/utils/auth";

interface CompanyImpact {
  id: string;
  name: string;
  role: string;
  other_active_members?: number;
}

interface DeletionImpactPreview {
  email: string;
  can_delete_immediately: boolean;
  sole_owned_requires_transfer: CompanyImpact[];
  sole_owned_single_user: CompanyImpact[];
  detachable_memberships: CompanyImpact[];
  retention_summary: string;
  confirmation_phrase: string;
}

interface DeletionReceipt {
  reference_id: string;
  status: string;
  company_resolution?: string;
  created_at?: string;
  completed_at?: string;
  retention_summary?: string;
  archived_company_ids?: string[];
}

export default function DeleteAccountPage() {
  const [loggedIn, setLoggedIn] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [preview, setPreview] = useState<DeletionImpactPreview | null>(null);
  const [previewError, setPreviewError] = useState("");

  const [currentPassword, setCurrentPassword] = useState("");
  const [confirmationText, setConfirmationText] = useState("");
  const [archiveSoloCompanies, setArchiveSoloCompanies] = useState(false);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [completedReceipt, setCompletedReceipt] = useState<DeletionReceipt | null>(null);

  const [lookupRef, setLookupRef] = useState("");
  const [lookupResult, setLookupResult] = useState<DeletionReceipt | null>(null);
  const [lookupError, setLookupError] = useState("");
  const [lookupLoading, setLookupLoading] = useState(false);

  useEffect(() => {
    const authed = isAuthenticated();
    setLoggedIn(authed);
    if (!authed) return;

    setLoadingPreview(true);
    api
      .get("/api/v1/auth/account/delete-request/")
      .then((res) => {
        if (res.data?.success && res.data?.data) {
          setPreview(res.data.data);
        }
      })
      .catch((err) => {
        const msg = err?.response?.data?.error || "Unable to verify current account ownership status.";
        setPreviewError(msg);
      })
      .finally(() => setLoadingPreview(false));
  }, []);

  const handleSubmitDeletion = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError("");
    if (!currentPassword) {
      setSubmitError("Please enter your current password to verify your identity.");
      return;
    }
    if (confirmationText.trim() !== "DELETE MY ACCOUNT") {
      setSubmitError("Type DELETE MY ACCOUNT exactly to confirm irreversible account deletion.");
      return;
    }
    if ((preview?.sole_owned_single_user?.length || 0) > 0 && !archiveSoloCompanies) {
      setSubmitError("Confirm archival of your single-user company workspace(s) before proceeding.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await api.post("/api/v1/auth/account/delete-request/", {
        current_password: currentPassword,
        confirmation_text: confirmationText.trim(),
        sole_company_action: archiveSoloCompanies ? "ARCHIVE_SOLO_COMPANIES" : "NONE",
        reason: reason.trim(),
      });
      if (res.data?.success) {
        setCompletedReceipt({
          reference_id: res.data.reference_id,
          status: res.data.status,
          completed_at: res.data.completed_at,
          retention_summary: res.data.retention_summary,
          archived_company_ids: res.data.archived_company_ids,
        });
        setLoggedIn(false);
        setPreview(null);
        removeTokens({ wipeLocalDeviceData: true, broadcastReason: "logout" });
      }
    } catch (err: any) {
      const msg =
        err?.response?.data?.error ||
        "Account deletion request failed. Please verify your password and company ownership.";
      setSubmitError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const handleStatusLookup = async (e: React.FormEvent) => {
    e.preventDefault();
    setLookupError("");
    setLookupResult(null);
    if (!lookupRef.trim()) {
      setLookupError("Enter a deletion reference UUID.");
      return;
    }
    setLookupLoading(true);
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/v1/auth/account/delete-status/?reference=${encodeURIComponent(lookupRef.trim())}`,
        { method: "GET" }
      );
      const data = await res.json();
      if (!res.ok || !data?.success) {
        setLookupError(data?.error || "Reference not found.");
      } else {
        setLookupResult(data.data);
      }
    } catch {
      setLookupError("Unable to reach status service. Try again shortly.");
    } finally {
      setLookupLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      <PublicHeader />

      <main className="flex-1 max-w-4xl w-full mx-auto px-4 sm:px-6 py-10 sm:py-14 space-y-8">
        <div className="space-y-3">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-600 dark:text-rose-400 text-xs font-bold">
            <Trash2 className="w-3.5 h-3.5" />
            <span>Account &amp; Personal Data Deletion</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight">
            Delete Your SriLekh Account
          </h1>
          <p className="text-sm text-muted-foreground leading-relaxed max-w-2xl">
            You can permanently delete your SriLekh user account either directly inside the app
            (<strong className="text-foreground">Settings → Account Profile → Permanent Account Deletion</strong>)
            or from this public web page—even after uninstalling the Android app.
          </p>
        </div>

        {/* Completed confirmation receipt */}
        {completedReceipt && (
          <section
            role="status"
            className="rounded-2xl border border-emerald-500/35 bg-emerald-500/5 p-6 space-y-3"
          >
            <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-400 font-bold text-base">
              <CheckCircle2 className="w-5 h-5" />
              <span>Account Permanently Deleted &amp; Anonymized</span>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Your personal identity, login credentials, push notification tokens, active JWT
              sessions, and local browser/device offline stores have been permanently erased or
              anonymized.
            </p>
            <div className="rounded-xl bg-background/80 border border-border p-3 text-xs space-y-1 font-mono">
              <div>
                <strong>Reference ID:</strong> {completedReceipt.reference_id}
              </div>
              <div>
                <strong>Status:</strong> {completedReceipt.status}
              </div>
              {completedReceipt.completed_at && (
                <div>
                  <strong>Completed At:</strong> {completedReceipt.completed_at}
                </div>
              )}
            </div>
            {completedReceipt.retention_summary && (
              <p className="text-xs text-muted-foreground leading-relaxed">
                {completedReceipt.retention_summary}
              </p>
            )}
          </section>
        )}

        {/* Authenticated Deletion Flow */}
        {!completedReceipt && (
          <section className="rounded-2xl border border-border bg-card p-6 space-y-5 shadow-2xs">
            <div className="flex items-center gap-2.5 border-b border-border/50 pb-4">
              <Lock className="w-4 h-4 text-primary shrink-0" />
              <div>
                <h2 className="text-base font-bold">
                  {loggedIn ? "Verified Account Deletion Request" : "Sign In to Delete Your Account"}
                </h2>
                <p className="text-xs text-muted-foreground">
                  {loggedIn
                    ? "Password re-authentication and explicit phrase confirmation are required."
                    : "For account security, sign in with the credentials of the account you want to permanently delete."}
                </p>
              </div>
            </div>

            {!loggedIn ? (
              <div className="space-y-4">
                <p className="text-xs text-muted-foreground leading-relaxed">
                  You are not currently signed in. Sign in to review your company ownership impact and
                  complete immediate permanent account deletion, or contact support for assisted
                  verification.
                </p>
                <div className="flex flex-wrap gap-3">
                  <Link
                    href="/login?next=/delete-account"
                    className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:bg-primary/90 transition-colors"
                  >
                    <span>Sign In &amp; Continue to Deletion</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </Link>
                  <a
                    href={`mailto:${SRILEKH_PUBLIC.supportEmail}?subject=${encodeURIComponent("SriLekh Account Deletion Request")}`}
                    className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl border border-border text-xs font-semibold hover:bg-muted transition-colors"
                  >
                    <Mail className="w-3.5 h-3.5" />
                    <span>Email {SRILEKH_PUBLIC.supportEmail}</span>
                  </a>
                </div>
              </div>
            ) : loadingPreview ? (
              <p className="text-xs text-muted-foreground">Checking workspace ownership impact...</p>
            ) : previewError ? (
              <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
                {previewError}
              </div>
            ) : (
              preview && (
                <form onSubmit={handleSubmitDeletion} className="space-y-5">
                  <div className="rounded-xl bg-muted/40 border border-border p-3.5 text-xs space-y-1">
                    <div>
                      <strong>Signed in as:</strong> {preview.email}
                    </div>
                    <div>
                      <strong>Detachable Shared Workspaces:</strong>{" "}
                      {preview.detachable_memberships.length}
                    </div>
                    <div>
                      <strong>Sole Single-User Workspaces:</strong>{" "}
                      {preview.sole_owned_single_user.length}
                    </div>
                  </div>

                  {preview.sole_owned_requires_transfer.length > 0 && (
                    <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 space-y-2 text-xs">
                      <div className="font-bold text-amber-800 dark:text-amber-200 flex items-center gap-2">
                        <ShieldAlert className="w-4 h-4 shrink-0" />
                        <span>Ownership Transfer Required Before Deletion</span>
                      </div>
                      <p className="text-amber-900 dark:text-amber-200/90 leading-relaxed">
                        You are the sole Owner/Admin for the multi-user workspace(s) below. Transfer
                        ownership to another active team member in{" "}
                        <Link href="/settings?tab=team" className="underline font-semibold">
                          Settings → Team Access
                        </Link>{" "}
                        so existing team members and accounting records are not locked out:
                      </p>
                      <ul className="list-disc pl-5 space-y-1 font-medium">
                        {preview.sole_owned_requires_transfer.map((c) => (
                          <li key={c.id}>
                            {c.name} ({c.other_active_members} other active team member(s))
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {preview.sole_owned_single_user.length > 0 && (
                    <div className="rounded-xl border border-border bg-muted/20 p-4 space-y-2 text-xs">
                      <div className="font-bold flex items-center gap-2 text-foreground">
                        <Building2 className="w-4 h-4 text-muted-foreground" />
                        <span>Single-User Workspace Archival Confirmation</span>
                      </div>
                      <p className="text-muted-foreground leading-relaxed">
                        You are the only member of the following active company workspace(s). Export any
                        Tally XML or financial reports before proceeding; deleting your account will
                        archive these workspace(s):
                      </p>
                      <ul className="list-disc pl-5 space-y-0.5 text-foreground">
                        {preview.sole_owned_single_user.map((c) => (
                          <li key={c.id}>{c.name}</li>
                        ))}
                      </ul>
                      <label className="flex items-start gap-2 pt-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={archiveSoloCompanies}
                          onChange={(e) => setArchiveSoloCompanies(e.target.checked)}
                          className="mt-0.5"
                        />
                        <span className="font-medium text-foreground">
                          I understand and authorize archiving my single-user workspace(s) listed above.
                        </span>
                      </label>
                    </div>
                  )}

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label htmlFor="del-password" className="block text-xs font-semibold mb-1.5">
                        Re-enter Current Password
                      </label>
                      <input
                        id="del-password"
                        type="password"
                        required
                        value={currentPassword}
                        onChange={(e) => setCurrentPassword(e.target.value)}
                        placeholder="Current password"
                        className="w-full rounded-xl border border-input bg-muted/30 px-3 py-2.5 text-sm"
                      />
                    </div>
                    <div>
                      <label htmlFor="del-confirm" className="block text-xs font-semibold mb-1.5">
                        Type <code>DELETE MY ACCOUNT</code> to confirm
                      </label>
                      <input
                        id="del-confirm"
                        type="text"
                        required
                        value={confirmationText}
                        onChange={(e) => setConfirmationText(e.target.value)}
                        placeholder="DELETE MY ACCOUNT"
                        className="w-full rounded-xl border border-input bg-muted/30 px-3 py-2.5 text-sm font-mono"
                      />
                    </div>
                  </div>

                  <div>
                    <label htmlFor="del-reason" className="block text-xs font-semibold mb-1.5">
                      Optional reason (feedback)
                    </label>
                    <textarea
                      id="del-reason"
                      rows={2}
                      maxLength={500}
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder="Optional feedback..."
                      className="w-full rounded-xl border border-input bg-muted/30 px-3 py-2 text-xs"
                    />
                  </div>

                  {submitError && (
                    <div
                      role="alert"
                      className="rounded-xl border border-destructive/35 bg-destructive/10 p-3 text-xs text-destructive flex items-start gap-2"
                    >
                      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                      <span>{submitError}</span>
                    </div>
                  )}

                  <button
                    type="submit"
                    disabled={submitting || !preview.can_delete_immediately}
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold transition-colors disabled:opacity-50 cursor-pointer"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>{submitting ? "Deleting Account..." : "Permanently Delete My Account"}</span>
                  </button>
                </form>
              )
            )}
          </section>
        )}

        {/* Legal Retention & What Is Deleted */}
        <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="rounded-2xl border border-border bg-card p-5 space-y-2">
            <h2 className="text-sm font-bold text-foreground">
              Data Immediately Deleted / Anonymized
            </h2>
            <ul className="list-disc pl-5 space-y-1.5 text-xs text-muted-foreground">
              <li>Personal email address, first/last name, and hashed login password.</li>
              <li>All active web cookies (`srilekh_access`, `srilekh_refresh`), mobile Bearer tokens, and `User.token_version` sessions.</li>
              <li>Unconsumed email OTP verification challenges, push notification endpoints, and team workspace links.</li>
              <li>On-device offline IndexedDB (`VouchOfflineDB`), `VouchSecurityVault`, and Service Worker caches when executed from this portal.</li>
            </ul>
          </div>

          <div className="rounded-2xl border border-border bg-card p-5 space-y-2">
            <h2 className="text-sm font-bold text-foreground">
              Data Retained for Statutory &amp; Audit Integrity
            </h2>
            <ul className="list-disc pl-5 space-y-1.5 text-xs text-muted-foreground">
              <li>Double-entry vouchers, invoices, tax ledgers, and hash-chained `AuditLog` entries inside multi-user or archived business workspaces remain preserved in anonymized form to comply with Indian accounting and tax recordkeeping requirements.</li>
              <li>Encrypted database backup archives rotate out automatically per `BACKUP_RETENTION_DAYS` (default `7` days locally).</li>
              <li>
                <strong>Formal Statutory Retention Period:</strong>{" "}
                <span className="text-foreground font-semibold">
                  [Pending Owner &amp; Legal Counsel Confirmation]
                </span>
                .
              </li>
            </ul>
          </div>
        </section>

        {/* Reference Status Check */}
        <section className="rounded-2xl border border-border bg-card p-6 space-y-4">
          <div className="flex items-center gap-2">
            <FileSearch className="w-4 h-4 text-primary" />
            <h2 className="text-sm font-bold">Verify Existing Deletion Request Status</h2>
          </div>
          <p className="text-xs text-muted-foreground">
            Enter your deletion reference UUID to verify non-PII completion status.
          </p>
          <form onSubmit={handleStatusLookup} className="flex flex-col sm:flex-row gap-2">
            <input
              type="text"
              value={lookupRef}
              onChange={(e) => setLookupRef(e.target.value)}
              placeholder="e.g. 550e8400-e29b-41d4-a716-446655440000"
              className="flex-1 rounded-xl border border-input bg-muted/30 px-3 py-2 text-xs font-mono"
            />
            <button
              type="submit"
              disabled={lookupLoading}
              className="px-4 py-2 rounded-xl border border-border bg-muted/40 hover:bg-muted text-xs font-bold cursor-pointer"
            >
              {lookupLoading ? "Checking..." : "Check Status"}
            </button>
          </form>
          {lookupError && <p className="text-xs text-destructive">{lookupError}</p>}
          {lookupResult && (
            <div className="rounded-xl border border-border bg-muted/30 p-3 text-xs space-y-1">
              <div>
                <strong>Status:</strong> {lookupResult.status}
              </div>
              <div>
                <strong>Resolution:</strong> {lookupResult.company_resolution}
              </div>
              {lookupResult.completed_at && (
                <div>
                  <strong>Completed:</strong> {lookupResult.completed_at}
                </div>
              )}
            </div>
          )}
        </section>
      </main>

      <PublicFooter />
    </div>
  );
}
