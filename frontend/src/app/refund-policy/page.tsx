import type { Metadata } from "next";
import Link from "next/link";
import { LegalDocumentShell, type LegalSectionLink } from "@/components/public/LegalDocumentShell";
import { NativeCommercialGuard } from "@/components/public/NativeCommercialGuard";
import { SRILEKH_PUBLIC } from "@/components/public/public-constants";

export const metadata: Metadata = {
  title: "Refund & Cancellation Policy",
  description:
    "Official Razorpay-compliant refund, cancellation, duplicate charge, and failed transaction policy for SriLekh accounting software subscriptions.",
  alternates: {
    canonical: "/refund-policy",
  },
};

const sections: LegalSectionLink[] = [
  { id: "introduction", title: "1. Introduction & Scope" },
  { id: "subscription-billing", title: "2. Subscription Plans & Billing Cycle" },
  { id: "money-back-guarantee", title: "3. 7-Day Money-Back Guarantee" },
  { id: "refund-eligibility", title: "4. Refund Eligibility & Exclusions" },
  { id: "duplicate-payments", title: "5. Duplicate Charges & Overpayments" },
  { id: "failed-transactions", title: "6. Failed or Timed-Out Transactions" },
  { id: "cancellation", title: "7. Cancellation of Subscription" },
  { id: "refund-method", title: "8. Mode of Refund (Original Source)" },
  { id: "processing-timeline", title: "9. Refund Processing Timeline (5–7 Business Days)" },
  { id: "gst-treatment", title: "10. GST Treatment & Credit Notes" },
  { id: "grievance-contact", title: "11. Support & Grievance Redressal" },
];

function SectionHeading({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h2 id={id} className="scroll-mt-24 text-lg sm:text-xl font-extrabold text-foreground pt-3">
      {children}
    </h2>
  );
}

export default function RefundPolicyPage() {
  return (
    <NativeCommercialGuard>
      <LegalDocumentShell
        activePath="/refund-policy"
        badge="Razorpay Merchant Compliance"
        title="Refund &amp; Cancellation Policy"
        subtitle="Transparent refund, cancellation, duplicate charge reversal, and payment processing terms for SriLekh business software subscriptions."
        reviewNotice="This document constitutes SriLekh's official commercial refund and cancellation framework in strict compliance with the Consumer Protection (E-Commerce) Rules, 2020, and Razorpay Payment Gateway Merchant Standards. All refunds are credited directly back to the original payment source."
        sections={sections}
      >
        {/* 1. Introduction */}
        <section className="space-y-3">
          <SectionHeading id="introduction">1. Introduction &amp; Scope</SectionHeading>
          <p>
            This Refund and Cancellation Policy governs commercial software subscriptions purchased
            through {SRILEKH_PUBLIC.brandName} (&ldquo;SriLekh&rdquo;, &ldquo;we&rdquo;, &ldquo;our&rdquo;, or &ldquo;us&rdquo;) via
            our website ({SRILEKH_PUBLIC.productionUrl}) and authorized payment gateways including
            Razorpay.
          </p>
          <p>
            By subscribing to any paid plan on SriLekh, you acknowledge that you have read,
            understood, and agreed to the cancellation windows, refund conditions, and banking
            settlement timelines outlined below.
          </p>
        </section>

        {/* 2. Subscription Plans & Billing Cycle */}
        <section className="space-y-3">
          <SectionHeading id="subscription-billing">2. Subscription Plans &amp; Billing Cycle</SectionHeading>
          <p>
            SriLekh offers annual SaaS subscription plans designed for Indian businesses:
          </p>
          <ul className="list-disc pl-5 space-y-1.5 text-muted-foreground">
            <li>
              <strong className="text-foreground">Starter Plan:</strong> ₹599 / year (+ 18% GST = ₹707 total)
            </li>
            <li>
              <strong className="text-foreground">Growth Plan:</strong> ₹1,499 / year (+ 18% GST = ₹1,769 total)
            </li>
            <li>
              <strong className="text-foreground">Pro AI Plan:</strong> ₹2,599 / year (+ 18% GST = ₹3,067 total)
            </li>
            <li>
              <strong className="text-foreground">Enterprise Plan:</strong> ₹3,999 / year (+ 18% GST = ₹4,719 total)
            </li>
          </ul>
          <p className="text-muted-foreground">
            All subscriptions are billed upfront annually. Applicable Goods &amp; Services Tax (18% GST) is
            charged transparently at checkout, and an official B2B GST tax invoice is issued to the
            subscriber for claiming Input Tax Credit (ITC).
          </p>
        </section>

        {/* 3. 7-Day Money-Back Guarantee */}
        <section className="space-y-3">
          <SectionHeading id="money-back-guarantee">3. 7-Day Money-Back Guarantee</SectionHeading>
          <p>
            We stand behind the quality and reliability of SriLekh. Every new annual subscription is
            backed by our <strong className="text-foreground">7-Day No-Risk Money-Back Guarantee</strong>:
          </p>
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-emerald-950 dark:text-emerald-200 text-xs sm:text-sm space-y-1.5">
            <p className="font-bold">
              100% Full Refund within 7 Calendar Days
            </p>
            <p>
              If you determine that SriLekh does not meet your business or accounting requirements, you may
              request a full 100% refund within <strong>7 calendar days</strong> of your initial purchase
              timestamp. No complex questions asked.
            </p>
          </div>
          <p className="text-muted-foreground">
            To trigger your guarantee refund, simply send an email from your registered account email
            address to{" "}
            <a href={`mailto:${SRILEKH_PUBLIC.supportEmail}`} className="text-primary font-medium hover:underline">
              {SRILEKH_PUBLIC.supportEmail}
            </a>{" "}
            with your Razorpay Payment ID within the 7-day window.
          </p>
        </section>

        {/* 4. Refund Eligibility & Exclusions */}
        <section className="space-y-3">
          <SectionHeading id="refund-eligibility">4. Refund Eligibility &amp; Exclusions</SectionHeading>
          <p className="text-muted-foreground">
            Refunds are evaluated under the following conditions:
          </p>
          <ul className="list-disc pl-5 space-y-1.5 text-muted-foreground">
            <li>
              <strong className="text-foreground">Eligible for Full Refund:</strong> Requests submitted within 7 days
              of original subscription purchase, verified duplicate payments, and unfulfilled service
              failures verified by our technical team.
            </li>
            <li>
              <strong className="text-foreground">Ineligible for Refund:</strong> Refund requests submitted after 7
              calendar days from the purchase date are not eligible for cash refunds. Your subscription
              will remain fully active with all plan features until the end of the paid annual term.
            </li>
            <li>
              <strong className="text-foreground">Plan Upgrades:</strong> If you upgrade to a higher tier midway
              through the year, any prorated credit applied toward your upgrade is non-refundable.
            </li>
          </ul>
        </section>

        {/* 5. Duplicate Charges */}
        <section className="space-y-3">
          <SectionHeading id="duplicate-payments">5. Duplicate Charges &amp; Overpayments</SectionHeading>
          <p>
            In the event that your bank account, credit/debit card, or UPI handle is mistakenly debited
            more than once for the same order due to network latency, duplicate button taps, or payment
            gateway timeout:
          </p>
          <ol className="list-decimal pl-5 space-y-1.5 text-muted-foreground">
            <li>
              Email{" "}
              <a href={`mailto:${SRILEKH_PUBLIC.supportEmail}`} className="text-primary font-medium hover:underline">
                {SRILEKH_PUBLIC.supportEmail}
              </a>{" "}
              with the duplicate Razorpay Payment IDs (e.g. <code className="text-xs bg-muted px-1.5 py-0.5 rounded">pay_xxxxxxxxxxxxxx</code>).
            </li>
            <li>
              Our finance team will verify the duplicate charge against Razorpay&rsquo;s settlement records within
              <strong> 24 business hours</strong>.
            </li>
            <li>
              A 100% refund of the duplicate amount will be initiated immediately back to your original
              funding source.
            </li>
          </ol>
        </section>

        {/* 6. Failed Transactions */}
        <section className="space-y-3">
          <SectionHeading id="failed-transactions">6. Failed or Timed-Out Transactions</SectionHeading>
          <p>
            If money is debited from your bank account or UPI wallet during checkout but the transaction
            fails or times out on the website before your SriLekh account is upgraded:
          </p>
          <p className="text-muted-foreground">
            This typically happens due to an intermittent bank network delay. In accordance with Reserve
            Bank of India (RBI) guidelines, Razorpay and your issuing bank automatically reconcile and
            reverse such failed transactions back to your account within <strong>2 to 5 banking working days</strong>.
            If your funds are not automatically returned within 5 working days, contact our support team with
            the Bank Reference / UTR Number for manual tracing.
          </p>
        </section>

        {/* 7. Cancellation */}
        <section className="space-y-3">
          <SectionHeading id="cancellation">7. Cancellation of Subscription</SectionHeading>
          <p>
            You have complete control over your subscription:
          </p>
          <ul className="list-disc pl-5 space-y-1.5 text-muted-foreground">
            <li>
              <strong className="text-foreground">Cancel Anytime:</strong> You may cancel your subscription or disable
              recurring mandate renewal at any time from your account settings or by contacting support.
            </li>
            <li>
              <strong className="text-foreground">Access Preservation:</strong> Upon cancellation outside the 7-day
              guarantee window, you will continue to enjoy uninterrupted access to your paid tier features until the
              end of your current prepaid annual billing cycle.
            </li>
            <li>
              <strong className="text-foreground">Data Preservation:</strong> Even after your subscription ends, your
              accounting data, ledgers, and voucher audit trails remain securely preserved under our statutory
              data retention standards. You can export your books via Tally XML or PDF at any time.
            </li>
          </ul>
        </section>

        {/* 8. Mode of Refund */}
        <section className="space-y-3">
          <SectionHeading id="refund-method">8. Mode of Refund (Original Source)</SectionHeading>
          <p>
            In strict compliance with RBI payment aggregator directives and Razorpay compliance mandates:
          </p>
          <div className="rounded-xl border border-border bg-card p-4 space-y-2 text-xs sm:text-sm text-muted-foreground">
            <p className="font-semibold text-foreground">
              Strict Original Payment Instrument Reversal:
            </p>
            <p>
              All refunds are processed <strong>exclusively back to the original payment source</strong> (e.g., the
              same UPI ID, Debit Card, Credit Card, or Net Banking bank account) from which the initial transaction
              originated.
            </p>
            <p>
              Under no circumstances can refunds be issued in cash, demand draft, cheque, or credited to an
              unrelated third-party bank account.
            </p>
          </div>
        </section>

        {/* 9. Processing Timeline */}
        <section className="space-y-3">
          <SectionHeading id="processing-timeline">9. Refund Processing Timeline (5–7 Business Days)</SectionHeading>
          <p>
            Once a refund request is approved by SriLekh, the refund is initiated via the Razorpay payment gateway
            within <strong>24 business hours</strong>.
          </p>
          <p className="text-muted-foreground">
            The turnaround time (TAT) for the funds to reflect in your bank account depends on your payment
            instrument and bank clearing network:
          </p>
          <div className="overflow-x-auto rounded-xl border border-border">
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="bg-muted/50 border-b border-border font-bold text-foreground">
                  <th className="p-3">Payment Method</th>
                  <th className="p-3">Standard Clearing Turnaround Time (TAT)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60 text-muted-foreground">
                <tr>
                  <td className="p-3 font-medium text-foreground">UPI (GPay, PhonePe, Paytm, BHIM)</td>
                  <td className="p-3 text-emerald-700 dark:text-emerald-400 font-semibold">2 to 4 Business Days</td>
                </tr>
                <tr>
                  <td className="p-3 font-medium text-foreground">Net Banking (50+ Indian Banks)</td>
                  <td className="p-3">3 to 5 Business Days</td>
                </tr>
                <tr>
                  <td className="p-3 font-medium text-foreground">Debit Card / Credit Card (Visa, Mastercard, RuPay)</td>
                  <td className="p-3">5 to 7 Business Days</td>
                </tr>
                <tr>
                  <td className="p-3 font-medium text-foreground">Corporate / Commercial Cards</td>
                  <td className="p-3">Up to 7–9 Business Days (Bank SLA)</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        {/* 10. GST Treatment */}
        <section className="space-y-3">
          <SectionHeading id="gst-treatment">10. GST Treatment &amp; Credit Notes</SectionHeading>
          <p className="text-muted-foreground">
            For all refunded transactions, SriLekh issues an official <strong className="text-foreground">GST Credit Note</strong>{" "}
            in compliance with Section 34 of the Central Goods and Services Tax (CGST) Act, 2017.
          </p>
          <p className="text-muted-foreground">
            The Credit Note details the original Tax Invoice number, the refunded taxable value, and the
            reversed 18% GST (CGST + SGST or IGST). This ensures seamless reconciliation in your monthly GSTR-2B /
            GSTR-3B filings without tax discrepancies.
          </p>
        </section>

        {/* 11. Support & Grievance Contact */}
        <section className="space-y-3">
          <SectionHeading id="grievance-contact">11. Support &amp; Grievance Redressal</SectionHeading>
          <p>
            If you have questions about your billing, wish to initiate a refund request, or require assistance
            with payment verification, contact our support desk:
          </p>
          <div className="rounded-2xl border border-border bg-card p-5 space-y-2 text-xs sm:text-sm text-muted-foreground">
            <p>
              <strong className="text-foreground">Platform Name:</strong> {SRILEKH_PUBLIC.brandName} ({SRILEKH_PUBLIC.businessLabel})
            </p>
            <p>
              <strong className="text-foreground">Billing Support Email:</strong>{" "}
              <a href={`mailto:${SRILEKH_PUBLIC.supportEmail}`} className="text-primary font-semibold hover:underline">
                {SRILEKH_PUBLIC.supportEmail}
              </a>
            </p>
            <p>
              <strong className="text-foreground">Support Helpline:</strong> +91 6386623787 (Mon–Sat, 10:00 AM – 6:00 PM IST)
            </p>
            <p>
              <strong className="text-foreground">Grievance &amp; Registered Address:</strong> S-60, Panki Industrial Area, Site-3, Kanpur, Uttar Pradesh, 208022, India.
            </p>
          </div>
          <p className="text-xs text-muted-foreground pt-1">
            Also review our{" "}
            <Link href="/pricing" className="text-primary font-medium hover:underline">
              Pricing Plans
            </Link>
            ,{" "}
            <Link href="/terms" className="text-primary font-medium hover:underline">
              Terms &amp; Conditions
            </Link>
            , and{" "}
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
