import type { Metadata } from "next";
import Link from "next/link";
import { LegalDocumentShell, type LegalSectionLink } from "@/components/public/LegalDocumentShell";
import { SRILEKH_PUBLIC } from "@/components/public/public-constants";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description:
    "Learn how SriLekh collects, stores, synchronizes, and protects business, GST, accounting, and offline device data with reference to India's Digital Personal Data Protection Act, 2023.",
  alternates: {
    canonical: "/privacy-policy",
  },
};

const sections: LegalSectionLink[] = [
  { id: "introduction", title: "1. Introduction" },
  { id: "information-collected", title: "2. Information We Collect" },
  { id: "account-business-info", title: "3. Account and Business Information" },
  { id: "financial-accounting-data", title: "4. Financial and Accounting Data" },
  { id: "device-technical-info", title: "5. Device and Technical Information" },
  { id: "how-we-use", title: "6. How We Use Information" },
  { id: "storage-security", title: "7. Data Storage and Security" },
  { id: "data-sharing", title: "8. Data Sharing and Third-Party Services" },
  { id: "cookies", title: "9. Cookies and Similar Technologies" },
  { id: "offline-storage", title: "10. Offline Storage and Synchronization" },
  { id: "data-retention", title: "11. Data Retention" },
  { id: "user-rights", title: "12. User Rights and Data Requests" },
  { id: "account-closure", title: "13. Account Closure and Data Deletion" },
  { id: "childrens-privacy", title: "14. Children's Privacy" },
  { id: "policy-updates", title: "15. Policy Updates" },
  { id: "contact-information", title: "16. Contact Information" },
];

function SectionHeading({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h2 id={id} className="scroll-mt-24 text-lg sm:text-xl font-extrabold text-foreground pt-2">
      {children}
    </h2>
  );
}

export default function PrivacyPolicyPage() {
  return (
    <LegalDocumentShell
      activePath="/privacy-policy"
      badge="Legal & Data Governance"
      title="Privacy Policy"
      subtitle="How SriLekh handles account, multi-tenant business, GST, accounting, uploaded document, and offline synchronized data for Indian businesses."
      reviewNotice="This Privacy Policy is drafted with reference to India's Digital Personal Data Protection Act, 2023 (DPDP Act) and accurately reflects SriLekh's current codebase. Legal entity registration details, Grievance Officer particulars, contractual processor DPAs, cloud residency disclosures, and statutory retention schedules remain subject to final confirmation by the SriLekh business owner and qualified Indian legal counsel."
      sections={sections}
    >
      <section className="space-y-3">
        <SectionHeading id="introduction">1. Introduction</SectionHeading>
        <p>
          This Privacy Policy explains how {SRILEKH_PUBLIC.businessLabel} (&ldquo;SriLekh&rdquo;,
          &ldquo;we&rdquo;, &ldquo;our&rdquo;, or &ldquo;us&rdquo;) collects, uses, stores, and
          protects information when business users visit{" "}
          <Link href="/" className="text-primary font-medium hover:underline">
            {SRILEKH_PUBLIC.productionUrl}
          </Link>{" "}
          or use the SriLekh web application, Progressive Web App (PWA), and companion client apps.
        </p>
        <p>
          This document is structured with reference to applicable Indian data-protection
          principles, including the Digital Personal Data Protection Act, 2023 (DPDP Act) and rules
          or notifications issued thereunder. Publication of this page does not by itself
          constitute legal certification or regulatory audit attestation.
        </p>
        <p className="text-xs rounded-lg border border-amber-500/25 bg-amber-500/5 px-3.5 py-2 text-amber-900 dark:text-amber-200">
          <strong>Legal Entity Confirmation Pending:</strong> Full registered legal entity name and
          physical office address of the Data Fiduciary must be confirmed by the SriLekh owner prior
          to final commercial publication.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="information-collected">2. Information We Collect</SectionHeading>
        <p>
          SriLekh collects only the information entered by you or generated during your authorized
          use of the accounting platform across three primary categories: account and business
          profile details, financial and accounting records, and essential technical telemetry
          needed to authenticate sessions, issue security audit trails, and synchronize offline
          activity.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="account-business-info">3. Account and Business Information</SectionHeading>
        <p>When registering an account or configuring a multi-tenant company workspace, we store:</p>
        <ul className="list-disc pl-5 space-y-1.5 text-muted-foreground">
          <li>
            User identity and role details: email address, optional first and last name, salted
            password verification hash, email verification status, and assigned company role (such
            as Owner, Administrator, Chartered Accountant, Employee, or Viewer).
          </li>
          <li>
            Company master profile details: firm name, legal name, GSTIN, PAN, state code and name,
            business address, city, pincode, contact email and phone, financial year configuration,
            proprietor name and phone, bank name, bank account number, IFSC, branch, optional UPI
            VPA, and uploaded branding assets (company logo, official stamp, or proprietor
            signature stored as image files or encoded data).
          </li>
          <li>
            Team access records linking authorized team members to specific company workspaces.
          </li>
        </ul>
      </section>

      <section className="space-y-3">
        <SectionHeading id="financial-accounting-data">4. Financial and Accounting Data</SectionHeading>
        <p>Within each isolated tenant company workspace, SriLekh processes records you create:</p>
        <ul className="list-disc pl-5 space-y-1.5 text-muted-foreground">
          <li>
            Double-entry vouchers, journal entries, proforma quotations, credit/debit notes, and
            ledger balances, together with any attachments uploaded to vouchers.
          </li>
          <li>
            Customer and supplier party details (names, GSTINs, state codes, billing addresses,
            email addresses, phone numbers, and receivable/payable allocations).
          </li>
          <li>
            Inventory categories, items, HSN codes, warehouse/godown locations, price list import
            jobs, and stock movements.
          </li>
          <li>
            GST calculation data, GSTR report summaries, uploaded GSTR-2B reconciliation records,
            and sandbox/saved E-Way Bill or E-Invoice database records.
          </li>
          <li>
            Uploaded business documents such as purchase bill images/PDFs submitted for OCR
            extraction, bank statement files (CSV, Excel, PDF, OFX, QIF) uploaded for
            reconciliation, and extracted transaction descriptions.
          </li>
          <li>
            B2B inward voucher requests, inter-company mirror ledger exchanges, protocol device
            authorizations, and application audit trail logs.
          </li>
        </ul>
      </section>

      <section className="space-y-3">
        <SectionHeading id="device-technical-info">5. Device and Technical Information</SectionHeading>
        <p>To operate authentication, security controls, and cross-device sync, SriLekh records:</p>
        <ul className="list-disc pl-5 space-y-1.5 text-muted-foreground">
          <li>
            IP address recorded on email OTP verification/reset challenges (`EmailVerificationChallenge`)
            and optionally in audit log records where passed.
          </li>
          <li>
            Pseudonymous device and replica identifiers (`vouch_device_id`, `vouch_protocol_replica_id`),
            Ed25519 public keys registered per authorized device (`AuthorizedDevice`), and push
            notification subscription endpoints where explicitly enabled by the user.
          </li>
          <li>
            Standard server access and observability logs (with regex-based masking applied to
            sensitive patterns such as GSTINs, PANs, bank account numbers, bearer tokens, and
            secrets).
          </li>
        </ul>
        <p className="text-muted-foreground">
          SriLekh does not currently bundle third-party advertising trackers or third-party session
          analytics SDKs such as Google Analytics, Mixpanel, PostHog, or Sentry.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="how-we-use">6. How We Use Information</SectionHeading>
        <p>We use collected data strictly to operate the SriLekh software for your business:</p>
        <ul className="list-disc pl-5 space-y-1.5 text-muted-foreground">
          <li>Authenticate users, verify email ownership via OTP challenges, and enforce team role permissions.</li>
          <li>Record double-entry accounting transactions, calculate GST taxes, and generate financial reports, Tally XML exports, and PDF documents.</li>
          <li>Extract structured fields from purchase bills, manufacturer price lists, or bank statements you explicitly upload.</li>
          <li>Synchronize supported transactions created offline once your browser or device reconnects.</li>
          <li>Send transactional notifications (such as verification OTPs, security notices, and invoice emails) from verified platform addresses.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <SectionHeading id="storage-security">7. Data Storage and Security</SectionHeading>
        <p>
          SriLekh implements practical application-level security controls visible in the codebase:
        </p>
        <ul className="list-disc pl-5 space-y-1.5 text-muted-foreground">
          <li>
            User passwords and OTP verification codes are stored as salted cryptographic hashes
            rather than plaintext.
          </li>
          <li>
            API sessions use signed JSON Web Tokens (JWT) with access/refresh rotation and
            company-scoped authorization checks so users can only access companies to which they
            are explicitly mapped.
          </li>
          <li>
            Accounting and administrative actions generate append-only audit trail entries using
            SHA-256 hash chaining to help detect tampering.
          </li>
          <li>
            Sensitive GST portal credential fields (`CompanyGSTConfig`) and generated disaster
            recovery database backup archives support AES-based Fernet encryption when configured.
          </li>
        </ul>
        <p className="text-muted-foreground">
          Web browser sessions use server-set <strong className="text-foreground">HttpOnly, Secure</strong> cookies
          (`srilekh_access` and `srilekh_refresh`) with origin-aware `SameSite` policy, paired with
          CSRF validation (`X-CSRFToken`) and immediate server-side `token_version` + refresh-token
          revocation on logout or password reset—without persisting raw JWT strings in browser
          `localStorage` or JavaScript-readable cookies. Native mobile sessions (Capacitor) store
          Bearer tokens in OS app-sandboxed storage (`@capacitor/preferences` with Android OS backup
          disabled); hardware Keystore/Keychain encryption is a planned native enhancement rather than
          an active control. Sensitive offline financial payloads in IndexedDB (`VouchOfflineDB`) are
          sealed at rest using 256-bit WebCrypto AES-GCM encryption with non-extractable keys stored
          in `VouchSecurityVault` (minimal index metadata such as `companyId`, `userId`, `status`,
          and dates remain unencrypted for local querying). SriLekh does not claim ISO 27001 or SOC 2 certification or
          India-only cloud residency guarantees unless separately confirmed and published by the
          business owner.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="data-sharing">8. Data Sharing and Third-Party Services</SectionHeading>
        <p>
          SriLekh does not sell your business or customer records. Based on our codebase and
          deployment architecture, data may be processed by the following infrastructure and
          functional service providers (contractual processor details and regional disclosures remain{" "}
          <strong className="text-foreground">[Pending Owner Confirmation]</strong>):
        </p>
        <ul className="list-disc pl-5 space-y-1.5 text-muted-foreground">
          <li>
            <strong className="text-foreground">Frontend &amp; Backend Hosting:</strong> Vercel
            (frontend delivery/CDN) and Render (Django API and background Celery worker execution).
          </li>
          <li>
            <strong className="text-foreground">Database &amp; Queue Infrastructure:</strong>{" "}
            Managed PostgreSQL (Neon cloud PostgreSQL; current configuration connects to an AWS
            Singapore `ap-southeast-1` endpoint) and Redis for background task queuing and OTP/rate
            caching.
          </li>
          <li>
            <strong className="text-foreground">Google Gemini API (`google.genai`):</strong> When
            server AI/OCR keys are configured and you trigger purchase bill OCR, scanned/image bank
            statement extraction, or price-list AI parsing, the uploaded document bytes/images are
            transmitted to Google Gemini for structured field extraction.
          </li>
          <li>
            <strong className="text-foreground">Transactional Email Delivery:</strong> Configured
            SMTP server (defaulting to Gmail SMTP if not overridden) for OTP verification, password
            reset, security alerts, and user-initiated invoice emails.
          </li>
          <li>
            <strong className="text-foreground">Optional Cloud Backup Storage:</strong> Amazon S3
            (via `boto3`, defaulting to `ap-south-1` region if `BACKUP_S3_BUCKET` is configured)
            for encrypted database backup archives.
          </li>
          <li>
            <strong className="text-foreground">External GST / Future Financial APIs:</strong> GST
            portal calls currently default to internal sandbox/mock mode; external GSP verification
            (such as Cashfree) or future Razorpay subscription checkout / Setu Account Aggregator
            integrations will only process data if enabled and initiated with your consent.
          </li>
        </ul>
        <p className="text-muted-foreground">
          Because cloud hosting, CDN, and AI extraction providers may operate infrastructure outside
          India, personal and business data may be transferred or processed internationally. Formal
          processor disclosures and transfer mechanisms remain{" "}
          <strong className="text-foreground">[Pending Owner &amp; Legal Counsel Confirmation]</strong>.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="cookies">9. Cookies and Similar Technologies</SectionHeading>
        <p>
          SriLekh uses strictly functional browser cookies, `localStorage`, and native mobile app
          storage (Capacitor `Preferences` when installed as a mobile app) — we do not use
          third-party advertising cookies:
        </p>
        <ul className="list-disc pl-5 space-y-1.5 text-muted-foreground">
          <li>
            Browser authentication cookies (`srilekh_access`, `srilekh_refresh` — `HttpOnly`, marked
            `Secure` on HTTPS, origin-aware `SameSite=Lax` or `SameSite=None`) plus CSRF protection
            cookie (`csrftoken`) and lightweight non-secret session metadata (`vouch_session_meta`
            timestamps/mode without JWT tokens). Installed Capacitor mobile apps store native Bearer
            tokens in app-sandboxed Capacitor `Preferences` instead of browser cookies.
          </li>
          <li>
            Session &amp; tenant context in `localStorage`: cached user profile (`vouch_user`),
            active company metadata (`vouch_active_company_id`, `vouch_cached_companies_list`),
            display theme preference, and pseudonymous device/replica IDs (`vouch_device_id`,
            `vouch_protocol_replica_id`).
          </li>
          <li>
            IndexedDB browser databases: `VouchOfflineDB` (Dexie offline accounting caches, OCR
            cache, and outbox queue with AES-GCM-256 encrypted financial payloads) and `VouchSecurityVault`
            (non-extractable Ed25519 signing and AES-GCM-256 offline encryption keys).
          </li>
        </ul>
      </section>

      <section className="space-y-3">
        <SectionHeading id="offline-storage">10. Offline Storage and Synchronization</SectionHeading>
        <p>
          SriLekh supports offline-resilient workflows as a Progressive Web App. Understanding how
          local device storage differs from cloud server storage—and what happens when you sign out
          or switch companies—is important:
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
          <div className="rounded-xl border border-border bg-card p-4 space-y-1.5">
            <h3 className="text-sm font-bold text-foreground">Locally Stored Device Data</h3>
            <p className="text-xs text-muted-foreground">
              Stored in browser IndexedDB (`VouchOfflineDB` and `VouchSecurityVault`),
              `localStorage`, and Service Worker static/page caches so cached masters and queued
              offline sales/purchase drafts persist across connectivity drops.
            </p>
          </div>
          <div className="rounded-xl border border-border bg-card p-4 space-y-1.5">
            <h3 className="text-sm font-bold text-foreground">Server-Stored Cloud Records</h3>
            <p className="text-xs text-muted-foreground">
              Stored in our backend PostgreSQL database once synced. Authoritative voucher numbers,
              audit logs, and multi-user company records reside on the cloud server. API calls are
              never stored in public Service Worker caches.
            </p>
          </div>
        </div>
        <p className="text-muted-foreground">
          <strong className="text-foreground">Standard vs. Shared-Device Logout &amp; Tenant Switch:</strong>{" "}
          Switching companies aborts in-flight syncs and clears cached tenant read tables while
          preserving unacknowledged outbox entries scoped by `userId` and `companyId`. On{" "}
          <strong className="text-foreground">Standard Logout</strong>, authentication sessions are
          revoked, read caches are cleared, and Service Worker session caches are purged while any
          unsynchronized `QUEUED`/`IN_FLIGHT`/`FAILED` outbox records stay preserved in
          encrypted IndexedDB (`userId`/`companyId`) so pending entries are not silently lost. On shared or
          untrusted devices, select{" "}
          <strong className="text-foreground">Secure Shared-Device Logout</strong>, which explicitly
          deletes `VouchOfflineDB`, `VouchSecurityVault`, `vouch_*` storage keys, and Service
          Worker caches.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="data-retention">11. Data Retention</SectionHeading>
        <p>
          Active company accounting records remain stored while your workspace is active. Encrypted
          database backup archives maintain a configurable local retention cycle (defaulting to{" "}
          <strong className="text-foreground">7 days</strong> via `BACKUP_RETENTION_DAYS` in
          application settings). Final statutory retention periods across PostgreSQL databases,
          S3 backups, server logs, and third-party processors remain{" "}
          <strong className="text-foreground">
            [Pending Owner &amp; Legal Counsel Confirmation]
          </strong>
          .
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="user-rights">12. User Rights and Data Requests</SectionHeading>
        <p>
          Subject to applicable Indian law including the DPDP Act, 2023 (to the extent commenced
          and applicable), you may request access to personal information associated with your
          account, correction of inaccurate profile details, or erasure/grievance assistance by
          writing to{" "}
          <a
            href={`mailto:${SRILEKH_PUBLIC.supportEmail}`}
            className="text-primary font-medium hover:underline"
          >
            {SRILEKH_PUBLIC.supportEmail}
          </a>
          . Company owners can also update business profile details directly inside SriLekh
          settings and export financial data (including Tally XML).
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="account-closure">13. Account Closure and Data Deletion</SectionHeading>
        <p>
          You can permanently delete your SriLekh user account either in-app (
          <strong className="text-foreground">Settings → Account Profile → Delete Account</strong>)
          or via our public web portal at{" "}
          <Link href="/delete-account" className="text-primary font-medium hover:underline">
            /delete-account
          </Link>{" "}
          even after uninstalling any mobile app. After password re-authentication and explicit
          confirmation, SriLekh immediately revokes active sessions (`token_version`), deletes OTP
          challenges and push subscriptions, detaches or archives eligible single-user workspaces,
          and permanently anonymizes personal user identity (`first_name`, `last_name`, `email`,
          credentials). Multi-user workspaces where you are the sole Owner/Admin require ownership
          transfer to another team member first. Double-entry vouchers, tax ledgers, and hash-chained
          audit records are retained in anonymized form as required for statutory accounting/tax
          integrity, and encrypted backups rotate per `BACKUP_RETENTION_DAYS` (`7` days local
          default); formal statutory retention durations remain{" "}
          <strong className="text-foreground">
            [Pending Owner &amp; Legal Counsel Confirmation]
          </strong>
          .
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="childrens-privacy">14. Children&apos;s Privacy</SectionHeading>
        <p>
          SriLekh is a B2B commercial accounting platform intended solely for businesses and
          individuals 18 years of age or older. We do not knowingly collect personal data from
          children.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="policy-updates">15. Policy Updates</SectionHeading>
        <p>
          We may update this Privacy Policy as platform features (such as Razorpay subscription
          billing or Setu Account Aggregator integrations) or Indian legal requirements evolve.
          Material updates will be published on this page with an updated effective date once
          finalized.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="contact-information">16. Contact Information</SectionHeading>
        <p>
          For privacy questions, data requests, or grievances, contact us via our{" "}
          <Link href="/contact" className="text-primary font-medium hover:underline">
            Contact page
          </Link>{" "}
          or email{" "}
          <a
            href={`mailto:${SRILEKH_PUBLIC.supportEmail}`}
            className="text-primary font-medium hover:underline"
          >
            {SRILEKH_PUBLIC.supportEmail}
          </a>
          .
        </p>
        <p className="text-xs rounded-lg border border-amber-500/25 bg-amber-500/5 px-3.5 py-2 text-amber-900 dark:text-amber-200">
          <strong>Grievance Officer &amp; Registered Address:</strong> [Pending Owner &amp; Legal
          Counsel Confirmation before live public release].
        </p>
      </section>
    </LegalDocumentShell>
  );
}
