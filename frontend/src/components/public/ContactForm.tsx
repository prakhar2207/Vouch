"use client";

import React, { useState } from "react";
import { AlertCircle, Check, Copy, ExternalLink, Info, Mail, Send } from "lucide-react";
import { SRILEKH_PUBLIC } from "./public-constants";
import {
  buildPreparedInquiry,
  checkContactAntiSpam,
  FIELD_MAX_LENGTHS,
  validateContactForm,
  type ContactFormErrors,
  type ContactFormValues,
} from "./contact-validation";

export function ContactForm() {
  const [values, setValues] = useState<ContactFormValues>({
    fullName: "",
    businessEmail: "",
    phone: "",
    businessName: "",
    subject: "",
    message: "",
    honeypot: "",
  });
  const [errors, setErrors] = useState<ContactFormErrors>({});
  const [mountedAt] = useState<number>(() => Date.now());
  const [loading, setLoading] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [preparedMailto, setPreparedMailto] = useState<string | null>(null);
  const [preparedBody, setPreparedBody] = useState<string>("");
  const [isMailtoTruncated, setIsMailtoTruncated] = useState(false);
  const [copied, setCopied] = useState(false);

  const updateField = (field: keyof ContactFormValues, val: string) => {
    setValues((prev) => ({ ...prev, [field]: val }));
    if (errors[field]) {
      setErrors((prev) => {
        const copy = { ...prev };
        delete copy[field];
        return copy;
      });
    }
    if (submitError) setSubmitError("");
    if (preparedMailto) setPreparedMailto(null);
    if (isMailtoTruncated) setIsMailtoTruncated(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError("");
    setPreparedMailto(null);
    setIsMailtoTruncated(false);

    const spamError = checkContactAntiSpam(values.honeypot, mountedAt);
    if (spamError) {
      setSubmitError(spamError);
      return;
    }

    const validationErrors = validateContactForm(values);
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      return;
    }

    setLoading(true);
    try {
      const prepared = buildPreparedInquiry(values);
      setPreparedBody(prepared.fullText);
      setPreparedMailto(prepared.mailtoHref);
      setIsMailtoTruncated(prepared.isMailtoTruncated);
    } catch {
      setSubmitError(
        `Unable to prepare inquiry automatically. Please email ${SRILEKH_PUBLIC.supportEmail} directly.`
      );
    } finally {
      setLoading(false);
    }
  };

  const handleCopyInquiry = async () => {
    if (!preparedBody) return;
    try {
      await navigator.clipboard.writeText(preparedBody);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      setSubmitError(
        `Clipboard access was blocked by your browser. Please copy the text manually and email ${SRILEKH_PUBLIC.supportEmail}.`
      );
    }
  };

  return (
    <div className="rounded-2xl border border-border bg-card p-6 sm:p-8 shadow-sm space-y-6">
      <div className="space-y-1.5">
        <h2 className="text-xl font-extrabold text-foreground">Send an Inquiry</h2>
        <p className="text-xs sm:text-sm text-muted-foreground">
          Complete the form below to validate and prepare your message for{" "}
          <span className="font-semibold text-foreground">{SRILEKH_PUBLIC.supportEmail}</span>.
        </p>
      </div>

      {/* Explicit notice about absence of automated server-side form submission */}
      <div
        role="note"
        className="rounded-xl border border-blue-500/25 bg-blue-500/5 px-4 py-3 text-xs text-muted-foreground flex items-start gap-2.5"
      >
        <Info className="w-4 h-4 shrink-0 mt-0.5 text-blue-600 dark:text-blue-400" />
        <div>
          <span className="font-semibold text-foreground">Direct Email Dispatch Mode: </span>
          <span>
            No automated server-side contact submission endpoint exists yet. Completing this form
            only prepares a formatted email draft — your own email app must send the message, and
            SriLekh cannot receive or guarantee delivery until you send it.
          </span>
        </div>
      </div>

      {submitError && (
        <div
          role="alert"
          className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-xs text-destructive flex items-start gap-2"
        >
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{submitError}</span>
        </div>
      )}

      {preparedMailto && (
        <div
          role="status"
          aria-live="polite"
          className="rounded-xl border border-amber-500/35 bg-amber-500/10 p-4 space-y-3 text-xs"
        >
          <div className="font-bold text-amber-900 dark:text-amber-200 flex items-center gap-2">
            <Mail className="w-4 h-4 shrink-0" />
            <span>
              Not yet sent — send this prepared draft using your email application
            </span>
          </div>
          <p className="text-amber-900/90 dark:text-amber-200/90 leading-relaxed">
            Your input passed local validation, but no automated server-side delivery exists. Click{" "}
            <strong className="font-semibold">Open in Email App</strong> or copy the text below and
            send it to <span className="font-semibold">{SRILEKH_PUBLIC.supportEmail}</span>. We
            cannot guarantee delivery until your email client completes sending.
          </p>
          {isMailtoTruncated && (
            <p className="text-amber-900 dark:text-amber-200 font-medium">
              Note: Your long message was shortened inside the quick-launch URL to fit browser mail
              limits. Click &ldquo;Copy Inquiry Text&rdquo; for the complete text.
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2.5 pt-1">
            <a
              href={preparedMailto}
              className="px-4 py-2 bg-[#162C5B] hover:bg-[#0F1E3D] dark:bg-[#E28123] dark:hover:bg-[#c86815] text-white rounded-lg font-bold inline-flex items-center gap-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span>Open in Email App</span>
            </a>
            <button
              type="button"
              onClick={handleCopyInquiry}
              className="px-4 py-2 bg-card hover:bg-muted border border-border text-foreground rounded-lg font-semibold inline-flex items-center gap-1.5 transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? "Copied Inquiry" : "Copy Inquiry Text"}</span>
            </button>
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {/* Honeypot anti-spam trap hidden from screen readers and keyboard focus */}
        <div className="hidden" aria-hidden="true">
          <label htmlFor="contact-company-website">Leave this field blank</label>
          <input
            id="contact-company-website"
            name="company_website"
            type="text"
            tabIndex={-1}
            autoComplete="off"
            value={values.honeypot}
            onChange={(e) => updateField("honeypot", e.target.value)}
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Full Name */}
          <div>
            <label htmlFor="contact-full-name" className="block text-xs font-semibold mb-1.5 text-foreground">
              Full Name <span className="text-destructive">*</span>
            </label>
            <input
              id="contact-full-name"
              type="text"
              required
              maxLength={FIELD_MAX_LENGTHS.fullName}
              autoComplete="name"
              value={values.fullName}
              onChange={(e) => updateField("fullName", e.target.value)}
              aria-invalid={Boolean(errors.fullName)}
              aria-describedby={errors.fullName ? "contact-full-name-error" : undefined}
              placeholder="e.g. Rajesh Sharma"
              className="w-full bg-muted/40 border border-input px-3.5 py-2.5 rounded-xl text-sm text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition-all"
            />
            {errors.fullName && (
              <p id="contact-full-name-error" role="alert" className="mt-1 text-xs text-destructive">
                {errors.fullName}
              </p>
            )}
          </div>

          {/* Business Email */}
          <div>
            <label htmlFor="contact-email" className="block text-xs font-semibold mb-1.5 text-foreground">
              Business Email <span className="text-destructive">*</span>
            </label>
            <input
              id="contact-email"
              type="email"
              required
              maxLength={FIELD_MAX_LENGTHS.businessEmail}
              autoComplete="email"
              value={values.businessEmail}
              onChange={(e) => updateField("businessEmail", e.target.value)}
              aria-invalid={Boolean(errors.businessEmail)}
              aria-describedby={errors.businessEmail ? "contact-email-error" : undefined}
              placeholder="you@yourcompany.com"
              className="w-full bg-muted/40 border border-input px-3.5 py-2.5 rounded-xl text-sm text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition-all"
            />
            {errors.businessEmail && (
              <p id="contact-email-error" role="alert" className="mt-1 text-xs text-destructive">
                {errors.businessEmail}
              </p>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Phone Number (Optional) */}
          <div>
            <label htmlFor="contact-phone" className="block text-xs font-semibold mb-1.5 text-foreground">
              Phone Number <span className="text-muted-foreground font-normal">(optional)</span>
            </label>
            <input
              id="contact-phone"
              type="tel"
              maxLength={FIELD_MAX_LENGTHS.phone}
              autoComplete="tel"
              value={values.phone}
              onChange={(e) => updateField("phone", e.target.value)}
              aria-invalid={Boolean(errors.phone)}
              aria-describedby={errors.phone ? "contact-phone-error" : undefined}
              placeholder="+91 98XXXXXXXX"
              className="w-full bg-muted/40 border border-input px-3.5 py-2.5 rounded-xl text-sm text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition-all"
            />
            {errors.phone && (
              <p id="contact-phone-error" role="alert" className="mt-1 text-xs text-destructive">
                {errors.phone}
              </p>
            )}
          </div>

          {/* Business Name (Optional) */}
          <div>
            <label htmlFor="contact-business" className="block text-xs font-semibold mb-1.5 text-foreground">
              Business Name <span className="text-muted-foreground font-normal">(optional)</span>
            </label>
            <input
              id="contact-business"
              type="text"
              maxLength={FIELD_MAX_LENGTHS.businessName}
              autoComplete="organization"
              value={values.businessName}
              onChange={(e) => updateField("businessName", e.target.value)}
              aria-invalid={Boolean(errors.businessName)}
              aria-describedby={errors.businessName ? "contact-business-error" : undefined}
              placeholder="Your firm or company name"
              className="w-full bg-muted/40 border border-input px-3.5 py-2.5 rounded-xl text-sm text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition-all"
            />
            {errors.businessName && (
              <p id="contact-business-error" role="alert" className="mt-1 text-xs text-destructive">
                {errors.businessName}
              </p>
            )}
          </div>
        </div>

        {/* Subject */}
        <div>
          <label htmlFor="contact-subject" className="block text-xs font-semibold mb-1.5 text-foreground">
            Subject <span className="text-destructive">*</span>
          </label>
          <input
            id="contact-subject"
            type="text"
            required
            maxLength={FIELD_MAX_LENGTHS.subject}
            value={values.subject}
            onChange={(e) => updateField("subject", e.target.value)}
            aria-invalid={Boolean(errors.subject)}
            aria-describedby={errors.subject ? "contact-subject-error" : undefined}
            placeholder="Pricing inquiry, Tally migration, or support request"
            className="w-full bg-muted/40 border border-input px-3.5 py-2.5 rounded-xl text-sm text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition-all"
          />
          {errors.subject && (
            <p id="contact-subject-error" role="alert" className="mt-1 text-xs text-destructive">
              {errors.subject}
            </p>
          )}
        </div>

        {/* Message */}
        <div>
          <label htmlFor="contact-message" className="block text-xs font-semibold mb-1.5 text-foreground">
            Message <span className="text-destructive">*</span>
          </label>
          <textarea
            id="contact-message"
            rows={5}
            required
            maxLength={FIELD_MAX_LENGTHS.message}
            value={values.message}
            onChange={(e) => updateField("message", e.target.value)}
            aria-invalid={Boolean(errors.message)}
            aria-describedby={errors.message ? "contact-message-error" : undefined}
            placeholder="Share details about your business accounting needs or question..."
            className="w-full bg-muted/40 border border-input px-3.5 py-2.5 rounded-xl text-sm text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition-all resize-y"
          />
          {errors.message && (
            <p id="contact-message-error" role="alert" className="mt-1 text-xs text-destructive">
              {errors.message}
            </p>
          )}
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full sm:w-auto px-6 py-3 bg-[#162C5B] hover:bg-[#0F1E3D] dark:bg-[#E28123] dark:hover:bg-[#c86815] text-white rounded-xl text-sm font-bold shadow-md transition-all disabled:opacity-60 cursor-pointer inline-flex items-center justify-center gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Send className="w-4 h-4" />
          <span>{loading ? "Preparing Inquiry..." : "Prepare Inquiry Email"}</span>
        </button>
      </form>
    </div>
  );
}
