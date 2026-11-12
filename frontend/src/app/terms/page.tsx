import type { Metadata } from "next";
import Link from "next/link";
import { LegalDocumentShell, type LegalSectionLink } from "@/components/public/LegalDocumentShell";
import { SRILEKH_PUBLIC } from "@/components/public/public-constants";

export const metadata: Metadata = {
  title: "Terms and Conditions",
  description:
    "Terms and Conditions governing access to SriLekh accounting, GST billing, inventory, and financial record management software.",
  alternates: {
    canonical: "/terms",
  },
};

const sections: LegalSectionLink[] = [
  { id: "acceptance", title: "1. Acceptance of Terms" },
  { id: "description", title: "2. Description of SriLekh Services" },
  { id: "registration", title: "3. Account Registration" },
  { id: "user-responsibilities", title: "4. User Responsibilities" },
  { id: "business-data", title: "5. Business and Financial Data" },
  { id: "accounting-accuracy", title: "6. Accounting Accuracy and User Verification" },
  { id: "gst-compliance", title: "7. GST and Regulatory Responsibilities" },
  { id: "subscription-payment", title: "8. Subscription and Payment Terms" },
  { id: "acceptable-use", title: "9. Acceptable Use" },
  { id: "intellectual-property", title: "10. Intellectual Property" },
  { id: "third-party-services", title: "11. Third-Party Services" },
  { id: "service-availability", title: "12. Service Availability and Maintenance" },
  { id: "data-backup", title: "13. Data Backup and User Responsibilities" },
  { id: "suspension-termination", title: "14. Suspension and Termination" },
  { id: "limitation-liability", title: "15. Limitation of Liability" },
  { id: "indemnification", title: "16. Indemnification" },
  { id: "governing-law", title: "17. Governing Law and Jurisdiction" },
  { id: "changes-to-terms", title: "18. Changes to Terms" },
  { id: "contact-information", title: "19. Contact Information" },
];

function SectionHeading({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h2 id={id} className="scroll-mt-24 text-lg sm:text-xl font-extrabold text-foreground pt-2">
      {children}
    </h2>
  );
}

export default function TermsPage() {
  return (
    <LegalDocumentShell
      activePath="/terms"
      badge="Terms of Service"
      title="Terms & Conditions"
      subtitle="The operational rules, accounting verification duties, and commercial framework governing use of the SriLekh software platform."
      reviewNotice="Commercial payment clauses, liability caps, indemnification wording, legal entity name, and court jurisdiction below are marked for confirmation by the SriLekh owner and Indian legal counsel before live commercial rollout."
      sections={sections}
    >
      <section className="space-y-3">
        <SectionHeading id="acceptance">1. Acceptance of Terms</SectionHeading>
        <p>
          By creating an account, accessing{" "}
          <Link href="/" className="text-primary font-medium hover:underline">
            {SRILEKH_PUBLIC.productionUrl}
          </Link>
          , or using the {SRILEKH_PUBLIC.brandName} application, you agree to be bound by these
          Terms &amp; Conditions on behalf of yourself and the business entity you represent. Please
          also review our{" "}
          <Link href="/privacy-policy" className="text-primary font-medium hover:underline">
            Privacy Policy
          </Link>{" "}
          and{" "}
          <Link href="/refund-policy" className="text-primary font-medium hover:underline">
            Refund Policy
          </Link>
          .
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="description">2. Description of SriLekh Services</SectionHeading>
        <p>
          SriLekh provides cloud-based and offline-capable accounting, GST invoicing, inventory
          tracking, bank statement reconciliation, and financial reporting software tools designed
          for Indian businesses. Specific capabilities are described on our{" "}
          <Link href="/pricing" className="text-primary font-medium hover:underline">
            Pricing &amp; Capabilities page
          </Link>
          .
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="registration">3. Account Registration</SectionHeading>
        <p>
          You must provide accurate business and contact information during registration and
          complete required email verification steps. Company owners may invite team members or
          Chartered Accountants under specific access roles (Owner, Admin, CA, Employee, Viewer).
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="user-responsibilities">4. User Responsibilities</SectionHeading>
        <p>
          You are solely responsible for safeguarding your login credentials, JWT sessions, and
          devices, as well as managing user permissions within your company workspace. Promptly
          notify{" "}
          <a
            href={`mailto:${SRILEKH_PUBLIC.supportEmail}`}
            className="text-primary font-medium hover:underline"
          >
            {SRILEKH_PUBLIC.supportEmail}
          </a>{" "}
          if you suspect unauthorized access.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="business-data">5. Business and Financial Data</SectionHeading>
        <p>
          You retain full ownership of all accounting vouchers, ledgers, invoices, inventory lists,
          and uploaded documents entered into your company workspace. You confirm that you hold the
          necessary rights and permissions to upload customer, supplier, and bank statement records
          into SriLekh.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="accounting-accuracy">
          6. Accounting Accuracy and User Verification
        </SectionHeading>
        <div className="rounded-xl border border-border bg-card p-4 space-y-2 text-muted-foreground">
          <p className="text-foreground font-semibold">
            SriLekh provides accounting software and productivity tools — not professional
            accounting, audit, taxation, or legal advice.
          </p>
          <ul className="list-disc pl-5 space-y-1.5">
            <li>
              You remain fully responsible for reviewing all transactions, ledger classifications,
              party balances, and generated PDF or XML exports before relying on or filing them.
            </li>
            <li>
              Automated computations (such as tax splits, rounding, OCR purchase bill extraction,
              or bank reconciliation suggestions) assist data entry and do not replace human review
              by an owner or qualified Chartered Accountant.
            </li>
          </ul>
        </div>
      </section>

      <section className="space-y-3">
        <SectionHeading id="gst-compliance">
          7. GST and Regulatory Responsibilities
        </SectionHeading>
        <p>
          All statutory obligations under the Central/State Goods and Services Tax (CGST/SGST/IGST)
          laws, Income Tax Act, E-Way Bill rules, and E-Invoicing mandates—including accurate HSN
          classification, tax rate selection, timely GST return filings, and verification of
          generated tax reports—remain solely the responsibility of your business unless a distinct
          authorized service is expressly contracted in writing.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="subscription-payment">
          8. Subscription and Payment Terms
        </SectionHeading>
        <p className="text-muted-foreground">
          Online subscription pricing, billing intervals, applicable taxes (such as GST), renewal
          mechanics, and gateway settlement rules are{" "}
          <strong className="text-foreground">
            [Pending Owner &amp; Legal Confirmation — Paid Subscriptions Not Yet Active]
          </strong>
          . Once finalized, published pricing on{" "}
          <Link href="/pricing" className="text-primary font-medium hover:underline">
            /pricing
          </Link>{" "}
          and payment terms in the{" "}
          <Link href="/refund-policy" className="text-primary font-medium hover:underline">
            Refund Policy
          </Link>{" "}
          will apply.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="acceptable-use">9. Acceptable Use</SectionHeading>
        <p>You agree not to misuse SriLekh, including refraining from:</p>
        <ul className="list-disc pl-5 space-y-1.5 text-muted-foreground">
          <li>Attempting to bypass tenant isolation, authentication tokens, or role permissions.</li>
          <li>Uploading malicious files, automated scraping, or conducting unauthorized load/penetration tests on production systems.</li>
          <li>Using SriLekh to generate fraudulent invoices or engage in unlawful financial activity.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <SectionHeading id="intellectual-property">10. Intellectual Property</SectionHeading>
        <p>
          All software source code, UI design, logos, trademarks, and documentation belonging to
          SriLekh remain the property of SriLekh and its owners. These Terms grant a limited,
          non-exclusive, revocable license to use the software for your authorized business
          operations.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="third-party-services">11. Third-Party Services</SectionHeading>
        <p>
          Certain workflows interact with third-party cloud hosting, email delivery, AI document
          parsing, or external government/payment interfaces when enabled. Availability and terms of
          external third-party services remain governed by their respective providers.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="service-availability">
          12. Service Availability and Maintenance
        </SectionHeading>
        <p>
          We strive to maintain reliable access to SriLekh, but temporary interruptions may occur
          for maintenance, hosting updates, or network outages. While offline mode supports queueing
          compatible entries locally until reconnection, uninterrupted real-time uptime guarantees
          (SLAs) are not offered unless specified in a separate written agreement.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="data-backup">
          13. Data Backup and User Responsibilities
        </SectionHeading>
        <p>
          While cloud database infrastructure includes standard operational backups, you are strongly
          advised to periodically export critical financial statements, GST summaries, and Tally XML
          backups for your statutory business archives.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="suspension-termination">14. Suspension and Termination</SectionHeading>
        <p>
          We may suspend or terminate access in cases of material breach of these Terms, suspected
          security abuse, or statutory order. You may discontinue use or request workspace closure at
          any time by contacting support.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="limitation-liability">15. Limitation of Liability</SectionHeading>
        <p className="text-muted-foreground">
          To the extent permitted by applicable Indian law, SriLekh is provided on an
          &ldquo;as-available&rdquo; basis and will not be liable for indirect, incidental, or
          consequential business losses arising from user data entry errors, tax filing omissions,
          or third-party outages. Any aggregate monetary liability cap is{" "}
          <strong className="text-foreground">
            [Pending Owner &amp; Legal Counsel Review]
          </strong>
          .
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="indemnification">16. Indemnification</SectionHeading>
        <p className="text-muted-foreground">
          You agree to indemnify SriLekh against third-party or regulatory claims arising directly
          from inaccurate accounting data uploaded by your account, unauthorized team access within
          your workspace, or unlawful use of the service.{" "}
          <strong className="text-foreground">[Subject to Final Legal Counsel Review]</strong>
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="governing-law">17. Governing Law and Jurisdiction</SectionHeading>
        <p className="text-muted-foreground">
          These Terms are governed by the laws of India. Exclusive court jurisdiction city/state
          remains{" "}
          <strong className="text-foreground">
            [Pending Owner Confirmation — Registered Office Jurisdiction, India]
          </strong>
          .
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="changes-to-terms">18. Changes to Terms</SectionHeading>
        <p>
          We may revise these Terms periodically. Updated versions will be published on this page,
          and continued use after notice constitutes acceptance of the revised Terms.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="contact-information">19. Contact Information</SectionHeading>
        <p>
          Questions regarding these Terms can be sent via our{" "}
          <Link href="/contact" className="text-primary font-medium hover:underline">
            Contact page
          </Link>{" "}
          or emailed to{" "}
          <a
            href={`mailto:${SRILEKH_PUBLIC.supportEmail}`}
            className="text-primary font-medium hover:underline"
          >
            {SRILEKH_PUBLIC.supportEmail}
          </a>
          .
        </p>
      </section>
    </LegalDocumentShell>
  );
}
