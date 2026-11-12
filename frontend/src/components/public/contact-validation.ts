import { SRILEKH_PUBLIC } from "./public-constants";

export interface ContactFormValues {
  fullName: string;
  businessEmail: string;
  phone: string;
  businessName: string;
  subject: string;
  message: string;
  honeypot: string;
}

export type ContactFormErrors = Partial<Record<keyof ContactFormValues, string>>;

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export const MAX_MAILTO_URI_LENGTH = 1900;

export const FIELD_MAX_LENGTHS = {
  fullName: 120,
  businessEmail: 254,
  phone: 30,
  businessName: 150,
  subject: 150,
  message: 1500,
} as const;

export function sanitizeSingleLine(value: string): string {
  return value.replace(/[\u0000-\u001F\u007F\r\n]+/g, " ").replace(/\s+/g, " ").trim();
}

export function sanitizeMultiline(value: string): string {
  return value
    .replace(/\r\n/g, "\n")
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "")
    .trim();
}

export function validateContactForm(form: ContactFormValues): ContactFormErrors {
  const errors: ContactFormErrors = {};
  const fullName = sanitizeSingleLine(form.fullName);
  const businessEmail = sanitizeSingleLine(form.businessEmail);
  const phone = sanitizeSingleLine(form.phone);
  const businessName = sanitizeSingleLine(form.businessName);
  const subject = sanitizeSingleLine(form.subject);
  const message = sanitizeMultiline(form.message);

  if (!fullName) {
    errors.fullName = "Please enter your full name.";
  } else if (fullName.length > FIELD_MAX_LENGTHS.fullName) {
    errors.fullName = `Full name must be ${FIELD_MAX_LENGTHS.fullName} characters or fewer.`;
  }

  if (!businessEmail) {
    errors.businessEmail = "Please enter your business email address.";
  } else if (
    businessEmail.length > FIELD_MAX_LENGTHS.businessEmail ||
    !EMAIL_REGEX.test(businessEmail)
  ) {
    errors.businessEmail = "Please enter a valid email address (e.g. name@company.com).";
  }

  if (phone) {
    if (phone.length > FIELD_MAX_LENGTHS.phone || phone.replace(/[^\d]/g, "").length < 7) {
      errors.phone = "If providing a phone number, please enter 7 to 30 valid characters.";
    }
  }

  if (businessName.length > FIELD_MAX_LENGTHS.businessName) {
    errors.businessName = `Business name must be ${FIELD_MAX_LENGTHS.businessName} characters or fewer.`;
  }

  if (!subject) {
    errors.subject = "Please enter a brief subject for your inquiry.";
  } else if (subject.length > FIELD_MAX_LENGTHS.subject) {
    errors.subject = `Subject must be ${FIELD_MAX_LENGTHS.subject} characters or fewer.`;
  }

  if (!message) {
    errors.message = "Please describe how we can help your business.";
  } else if (message.length < 10) {
    errors.message = "Please provide at least 10 characters in your message.";
  } else if (message.length > FIELD_MAX_LENGTHS.message) {
    errors.message = `Message must be ${FIELD_MAX_LENGTHS.message} characters or fewer.`;
  }

  return errors;
}

export function checkContactAntiSpam(
  honeypot: string,
  mountedAtMs: number,
  nowMs: number = Date.now()
): string | null {
  if (honeypot.trim() !== "") {
    return "Submission blocked by automated spam filter.";
  }
  if (nowMs - mountedAtMs < 1200) {
    return "Please take a moment to review your inquiry before submitting.";
  }
  return null;
}

export function buildPreparedInquiry(form: ContactFormValues): {
  subjectLine: string;
  bodyText: string;
  fullText: string;
  mailtoHref: string;
  isMailtoTruncated: boolean;
} {
  const fullName = sanitizeSingleLine(form.fullName);
  const businessEmail = sanitizeSingleLine(form.businessEmail);
  const phone = sanitizeSingleLine(form.phone);
  const businessName = sanitizeSingleLine(form.businessName);
  const subject = sanitizeSingleLine(form.subject);
  const message = sanitizeMultiline(form.message);

  const subjectLine = `[SriLekh Contact] ${subject}`;
  const bodyText = [
    `Name: ${fullName}`,
    `Email: ${businessEmail}`,
    phone ? `Phone: ${phone}` : null,
    businessName ? `Business Name: ${businessName}` : null,
    "",
    message,
  ]
    .filter((line): line is string => line !== null)
    .join("\n");

  const fullText = `Subject: ${subjectLine}\n\n${bodyText}`;
  const basePrefix = `mailto:${SRILEKH_PUBLIC.supportEmail}?subject=${encodeURIComponent(
    subjectLine
  )}&body=`;
  const fullMailto = `${basePrefix}${encodeURIComponent(bodyText)}`;

  if (fullMailto.length <= MAX_MAILTO_URI_LENGTH) {
    return {
      subjectLine,
      bodyText,
      fullText,
      mailtoHref: fullMailto,
      isMailtoTruncated: false,
    };
  }

  // Keep encoded mailto URI strictly within universal client limits
  const truncationNotice = "\n\n[Truncated for email URL limit — use Copy Inquiry Text for full message]";
  const budget = Math.max(0, MAX_MAILTO_URI_LENGTH - basePrefix.length - encodeURIComponent(truncationNotice).length);
  let candidate = bodyText;
  while (candidate.length > 0 && encodeURIComponent(candidate).length > budget) {
    candidate = candidate.slice(0, Math.max(0, candidate.length - 16));
  }
  const safeBody = `${candidate.trimEnd()}${truncationNotice}`;
  return {
    subjectLine,
    bodyText,
    fullText,
    mailtoHref: `${basePrefix}${encodeURIComponent(safeBody)}`,
    isMailtoTruncated: true,
  };
}
