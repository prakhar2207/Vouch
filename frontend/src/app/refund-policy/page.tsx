import type { Metadata } from "next";
import Link from "next/link";
import { LegalDocumentShell, type LegalSectionLink } from "@/components/public/LegalDocumentShell";
import { NativeCommercialGuard } from "@/components/public/NativeCommercialGuard";
import { SRILEKH_PUBLIC } from "@/components/public/public-constants";

export const metadata: Metadata = {
  title: "Refund Policy",
  description:
    "Refund, cancellation, duplicate payment, and failed transaction framework for SriLekh accounting software subscriptions.",
  alternates: {
    canonical: "/refund-policy",
  },
};

const sections: LegalSectionLink[] = [
  { id: "introduction", title: "1. Introduction" },
  { id: "subscription-billing", title: "2. Subscription and Billing" },
  { id: "free-trials", title: "3. Free Trials (If Applicable)" },
  { id: "refund-eligibility", title: "4. Refund Eligibility" },
  { id: "non-refundable", title: "5. Non-Refundable Charges" },
  { id: "duplicate-payments", title: "6. Duplicate Payments" },
  { id: "failed-transactions", title: "7. Failed Transactions" },
  { id: "cancellation", title: "8. Cancellation of Subscription" },
  { id: "refund-procedure", title: "9. Refund Request Procedure" },
  { id: "processing-timeline", title: "10. Refund Processing Timeline" },
  { id: "contact-information", title: "11. Contact Information" },
];

function SectionHeading({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h2 id={id} className="scroll-mt-24 text-lg sm:text-xl font-extrabold text-foreground pt-2">
      {children}
    </h2>
  );
}

export default function RefundPolicyPage() {
  return (
    <NativeCommercialGuard>
    <LegalDocumentShell
      activePath="/refund-policy"
      badge="Billing & Cancellations"
      title="Refund Policy"
      subtitle="Clear information for Indian business owners regarding subscription billing, cancellations, duplicate charges, and refund procedures on SriLekh."
      reviewNotice="Online payment checkout (such as Razorpay) and paid subscription billing are NOT currently active in SriLekh. Refund eligibility windows, cancellation deadlines, trial rules, service delivery timelines, and bank credit timelines below are marked as pending confirmation by the SriLekh owner before live payment activation."
      sections={sections}
    >
      <section className="space-y-3">
        <SectionHeading id="introduction">1. Introduction</SectionHeading>
        <p>
          This Refund Policy explains how {SRILEKH_PUBLIC.businessLabel} (&ldquo;SriLekh&rdquo;)
          will handle billing, cancellations, duplicate charges, failed transactions, and refund
          requests for commercial subscriptions once online payments are enabled. Because online
          payment checkout is not yet active on the website, this page serves as a pre-launch
          policy framework rather than an active paid-subscription entitlement.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="subscription-billing">2. Subscription and Billing</SectionHeading>
        <p className="text-muted-foreground">
          Automated subscription billing and third-party payment gateway checkout are{" "}
          <strong className="text-foreground">not currently active</strong> in the SriLekh platform,
          and no payments can currently be made through the application. Exact plan fees, billing
          cycles, taxes, service activation rules, and payment methods remain{" "}
          <strong className="text-foreground">[Pending Owner Confirmation]</strong> and will be
          published on{" "}
          <Link href="/pricing" className="text-primary font-medium hover:underline">
            /pricing
          </Link>{" "}
          before any charges are collected.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="free-trials">3. Free Trials (If Applicable)</SectionHeading>
        <p className="text-muted-foreground">
          No automated free-trial period or promotional entitlement is currently configured or
          promised in the application. Whether a trial window is offered on future paid tiers
          remains <strong className="text-foreground">[Pending Owner Confirmation]</strong>.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="refund-eligibility">4. Refund Eligibility</SectionHeading>
        <p className="text-muted-foreground">
          Specific refund eligibility criteria (including whether prorated or fixed-day refund
          windows apply once paid plans launch) remain{" "}
          <strong className="text-foreground">[Pending Owner Confirmation]</strong>. No automatic,
          retroactive, or unconditional refund entitlement applies while online billing is inactive
          or until commercial billing rules are finalized by the business owner.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="non-refundable">5. Non-Refundable Charges</SectionHeading>
        <p className="text-muted-foreground">
          Any non-refundable service fees, setup charges, or custom migration costs (if offered in
          future) will be explicitly stated prior to payment confirmation.{" "}
          <strong className="text-foreground">[Pending Owner Confirmation]</strong>
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="duplicate-payments">6. Duplicate Payments</SectionHeading>
        <p>
          Once online payments are launched, if your bank account, UPI ID, or card is mistakenly
          charged more than once for the same subscription invoice or order reference, you will be
          able to submit both payment transaction IDs so our team can verify the payment gateway
          settlement log and initiate a reversal for any confirmed duplicate charge.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="failed-transactions">7. Failed Transactions</SectionHeading>
        <p>
          Once payment checkout is active, if a payment attempt fails or times out while money is
          debited from your bank or UPI account, the amount is typically reversed automatically by
          your issuing bank or payment network under applicable banking and payment gateway
          settlement rules. If a debited amount is not credited back automatically by your bank,
          support will assist upon receiving the payment reference number.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="cancellation">8. Cancellation of Subscription</SectionHeading>
        <p className="text-muted-foreground">
          Self-serve cancellation controls, notice deadlines, end-of-cycle access behavior, and
          recurring mandate cancellation steps are{" "}
          <strong className="text-foreground">[Pending Owner Confirmation]</strong> and will be
          published prior to activating recurring subscription plans.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="refund-procedure">9. Refund Request Procedure</SectionHeading>
        <p className="text-muted-foreground">
          <strong className="text-foreground">Future Procedure (Applicable Once Billing Launches):</strong>{" "}
          Because paid checkout is not currently enabled on SriLekh, no online subscription charges
          exist to refund at this stage. Once commercial billing is activated, customers needing
          billing reconciliation or refund review will be able to:
        </p>
        <ol className="list-decimal pl-5 space-y-1.5 text-muted-foreground">
          <li>
            Email{" "}
            <a
              href={`mailto:${SRILEKH_PUBLIC.supportEmail}`}
              className="text-primary font-medium hover:underline"
            >
              {SRILEKH_PUBLIC.supportEmail}
            </a>{" "}
            or reach us via the{" "}
            <Link href="/contact" className="text-primary font-medium hover:underline">
              Contact page
            </Link>
            .
          </li>
          <li>
            Include their registered account email, company name, payment/transaction reference ID,
            payment date, and a short description of the billing issue.
          </li>
        </ol>
      </section>

      <section className="space-y-3">
        <SectionHeading id="processing-timeline">10. Refund Processing Timeline</SectionHeading>
        <p className="text-muted-foreground">
          Official approval and bank credit timelines (which depend on payment gateway integration
          and issuing bank clearing cycles) remain{" "}
          <strong className="text-foreground">
            [Pending Owner &amp; Payment Partner Confirmation]
          </strong>{" "}
          and will be updated here once Razorpay merchant onboarding is completed.
        </p>
      </section>

      <section className="space-y-3">
        <SectionHeading id="contact-information">11. Contact Information</SectionHeading>
        <p>
          For general billing questions, reach out via our{" "}
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
          . Also see our{" "}
          <Link href="/terms" className="text-primary font-medium hover:underline">
            Terms &amp; Conditions
          </Link>{" "}
          and{" "}
          <Link href="/privacy-policy" className="text-primary font-medium hover:underline">
            Privacy Policy
          </Link>
          .
        </p>
      </section>
    </LegalDocumentShell>
    </NativeCommercialGuard>
  );
}
