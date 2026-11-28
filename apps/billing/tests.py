import json
import uuid
from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User
from apps.companies.models import Company, UserCompany
from apps.accounting.models import Voucher, LedgerEntry
from apps.billing.models import (
    SubscriptionPlan,
    Subscription,
    PaymentTransaction,
    BillingInvoice,
    WebhookEvent,
    DailyUsageTracker,
)
from apps.billing.services.entitlement_service import EntitlementService
from apps.billing.services.subscription_service import SubscriptionService
from apps.billing.services.razorpay_service import RazorpayService


class BillingAndSubscriptionTests(TestCase):
    """
    Comprehensive test suite for Razorpay payments, subscriptions,
    entitlement engine, tenant isolation, and accounting non-interference.
    """

    def setUp(self):
        # 1. Sync approved plans
        EntitlementService.sync_default_plans()

        # 2. Setup Primary Test User & Company
        self.user = User.objects.create_user(
            email="owner@teststore.in",
            password="StrongPassword123!",
            first_name="Store",
            last_name="Owner",
            role="OWNER",
            email_verified=True
        )

        self.company = Company.objects.create(
            name="Test Store Private Limited",
            gstin="09AAACT2727Q1ZP",
            state_code="09",
            state_name="Uttar Pradesh",
            email="owner@teststore.in"
        )

        self.membership = UserCompany.objects.create(
            user=self.user,
            company=self.company,
            role="OWNER"
        )

        # 3. Setup Secondary User & Company for Tenant Isolation tests
        self.other_user = User.objects.create_user(
            email="competitor@otherstore.in",
            password="OtherPassword123!",
            first_name="Other",
            last_name="Owner",
            role="OWNER",
            email_verified=True
        )

        self.other_company = Company.objects.create(
            name="Competitor Retailers",
            gstin="27AABCT1234D1ZR",
            state_code="27",
            state_name="Maharashtra",
            email="competitor@otherstore.in"
        )

        self.other_membership = UserCompany.objects.create(
            user=self.other_user,
            company=self.other_company,
            role="OWNER"
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    # ==========================================
    # 1. Plan Retrieval & Catalog Tests
    # ==========================================

    def test_public_plans_list(self):
        """Public visitors can list active subscription plans without authentication."""
        unauthed_client = APIClient()
        response = unauthed_client.get(reverse('billing-plans-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data.get("success"))
        plans = data.get("plans")
        self.assertEqual(len(plans), 4)
        plan_ids = [p["id"] for p in plans]
        self.assertListEqual(plan_ids, ["starter", "growth", "pro_ai", "enterprise"])

        # Check starter amounts: 599 + 18% GST = 706.82
        starter = next(p for p in plans if p["id"] == "starter")
        self.assertEqual(starter["base_amount_paise"], 59900)
        self.assertEqual(starter["total_amount_paise"], 70682)

    def test_public_plan_detail(self):
        """Plan detail endpoint returns exact features and limits."""
        unauthed_client = APIClient()
        response = unauthed_client.get(reverse('billing-plan-detail', kwargs={"plan_id": "growth"}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data.get("success"))
        plan = data.get("plan")
        self.assertEqual(plan["name"], "Growth")
        self.assertEqual(plan["limits"]["ocr_fast_daily"], 15)
        self.assertEqual(plan["limits"]["ocr_deep_daily"], 3)
        self.assertTrue(plan["features"]["bi_sales_timeline"])
        self.assertFalse(plan["features"]["bi_rfm_segmentation"])

    # ==========================================
    # 2. Checkout Order Creation Tests
    # ==========================================

    def test_create_checkout_order_success(self):
        """Company owner can initiate a checkout order for an active plan."""
        url = reverse('billing-checkout-create-order')
        payload = {
            "plan_id": "growth",
            "company_id": str(self.company.id)
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertTrue(data.get("success"))
        checkout = data.get("checkout")
        self.assertEqual(checkout["amount"], 176882)
        self.assertEqual(checkout["currency"], "INR")
        self.assertTrue(checkout["order_id"].startswith("order_"))

        # Verify PaymentTransaction was persisted
        txn = PaymentTransaction.objects.filter(razorpay_order_id=checkout["order_id"]).first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.company, self.company)
        self.assertEqual(txn.amount_paise, 176882)
        self.assertEqual(txn.status, "created")

    def test_create_checkout_order_invalid_plan(self):
        """Reject checkout requests with non-existent plan ID."""
        url = reverse('billing-checkout-create-order')
        payload = {
            "plan_id": "non_existent_tier",
            "company_id": str(self.company.id)
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_checkout_order_cross_tenant_denied(self):
        """User cannot create checkout order for a company they do not belong to."""
        url = reverse('billing-checkout-create-order')
        payload = {
            "plan_id": "growth",
            "company_id": str(self.other_company.id)  # Competitor company
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ==========================================
    # 3. Payment Verification & Activation Tests
    # ==========================================

    def test_verify_payment_success_and_activation(self):
        """Valid payment signature activates subscription, marks transaction captured, and issues invoice."""
        # 1. Create order
        checkout = SubscriptionService.create_checkout_order(
            company=self.company,
            user=self.user,
            plan_id="pro_ai"
        )
        order_id = checkout["order_id"]
        payment_id = f"pay_{uuid.uuid4().hex[:14]}"
        valid_signature = RazorpayService.compute_signature(order_id, payment_id)

        # 2. Verify payment
        url = reverse('billing-checkout-verify')
        payload = {
            "company_id": str(self.company.id),
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": valid_signature,
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("plan_id"), "pro_ai")

        # 3. Verify Database State
        sub = Subscription.objects.get(id=data["subscription_id"])
        self.assertEqual(sub.company, self.company)
        self.assertEqual(sub.status, "active")
        self.assertTrue(sub.is_currently_active)

        txn = PaymentTransaction.objects.get(razorpay_order_id=order_id)
        self.assertEqual(txn.status, "captured")
        self.assertTrue(txn.signature_verified)
        self.assertEqual(txn.subscription, sub)

        inv = BillingInvoice.objects.get(invoice_number=data["invoice_number"])
        self.assertEqual(inv.company, self.company)
        self.assertEqual(inv.transaction, txn)
        self.assertEqual(inv.total_amount_paise, 306682)

    def test_verify_payment_tampered_signature_rejected(self):
        """Tampered signature is rejected and marks transaction as failed."""
        checkout = SubscriptionService.create_checkout_order(
            company=self.company,
            user=self.user,
            plan_id="growth"
        )
        order_id = checkout["order_id"]
        payment_id = f"pay_{uuid.uuid4().hex[:14]}"
        fake_signature = "invalid_tampered_signature_hash_000000"

        url = reverse('billing-checkout-verify')
        payload = {
            "company_id": str(self.company.id),
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": fake_signature,
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Ensure subscription was NOT created
        self.assertFalse(Subscription.objects.filter(company=self.company).exists())
        txn = PaymentTransaction.objects.get(razorpay_order_id=order_id)
        self.assertEqual(txn.status, "failed")

    def test_verify_payment_idempotent_duplicate_callback(self):
        """Repeated verification call with identical credentials does not create duplicate subscriptions."""
        checkout = SubscriptionService.create_checkout_order(
            company=self.company,
            user=self.user,
            plan_id="starter"
        )
        order_id = checkout["order_id"]
        payment_id = f"pay_{uuid.uuid4().hex[:14]}"
        valid_signature = RazorpayService.compute_signature(order_id, payment_id)

        payload = {
            "company_id": str(self.company.id),
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": valid_signature,
        }

        # First call: succeeds
        res1 = self.client.post(reverse('billing-checkout-verify'), payload, format='json')
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        # Second call: returns already processed idempotently
        res2 = self.client.post(reverse('billing-checkout-verify'), payload, format='json')
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertTrue(res2.json().get("already_processed"))

        # Verify only 1 subscription and 1 invoice exist
        self.assertEqual(Subscription.objects.filter(company=self.company).count(), 1)
        self.assertEqual(BillingInvoice.objects.filter(company=self.company).count(), 1)

    # ==========================================
    # 4. Webhook Processing Tests
    # ==========================================

    def test_webhook_payment_captured(self):
        """Razorpay webhook event payment.captured verifies and updates transaction."""
        checkout = SubscriptionService.create_checkout_order(
            company=self.company,
            user=self.user,
            plan_id="starter"
        )
        order_id = checkout["order_id"]
        payment_id = f"pay_{uuid.uuid4().hex[:14]}"

        event_body = {
            "entity": "event",
            "event": "payment.captured",
            "event_id": f"evt_{uuid.uuid4().hex[:12]}",
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "order_id": order_id,
                        "amount": 70682,
                        "currency": "INR",
                        "status": "captured"
                    }
                }
            }
        }
        raw_bytes = json.dumps(event_body).encode('utf-8')
        sig = RazorpayService.compute_webhook_signature(raw_bytes)

        unauthed_client = APIClient()
        response = unauthed_client.post(
            reverse('billing-razorpay-webhook'),
            data=raw_bytes,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=sig
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        txn = PaymentTransaction.objects.get(razorpay_order_id=order_id)
        self.assertEqual(txn.status, "captured")
        self.assertEqual(txn.razorpay_payment_id, payment_id)

    def test_webhook_invalid_signature_rejected(self):
        """Webhook with invalid signature is rejected with 400 Bad Request."""
        raw_bytes = b'{"event": "payment.captured"}'
        unauthed_client = APIClient()
        response = unauthed_client.post(
            reverse('billing-razorpay-webhook'),
            data=raw_bytes,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE="tampered_webhook_signature"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ==========================================
    # 5. Subscription Lifecycle & Cancellation Tests
    # ==========================================

    def test_cancel_subscription_success(self):
        """Company owner can cancel subscription, preserving access until period end."""
        # 1. Activate subscription
        plan = SubscriptionPlan.objects.get(id="growth")
        period_end = timezone.now() + timedelta(days=365)
        sub = Subscription.objects.create(
            company=self.company,
            user=self.user,
            plan=plan,
            status="active",
            current_period_start=timezone.now(),
            current_period_end=period_end
        )

        url = reverse('billing-subscription-cancel')
        response = self.client.post(url, {
            "company_id": str(self.company.id),
            "reason": "Moving to another branch"
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        sub.refresh_from_db()
        self.assertEqual(sub.status, "cancelled")
        self.assertIsNotNone(sub.cancelled_at)
        self.assertEqual(sub.metadata.get("cancellation_reason"), "Moving to another branch")

    # ==========================================
    # 6. Feature Entitlement & Limit Enforcement Tests
    # ==========================================

    def test_unsubscribed_company_receives_free_baseline(self):
        """Company with no active subscription receives default baseline entitlements."""
        entitlements = EntitlementService.get_company_entitlements(self.company.id)
        self.assertFalse(entitlements["has_active_subscription"])
        self.assertEqual(entitlements["limits"]["ocr_fast_daily"], 2)
        self.assertEqual(entitlements["limits"]["ocr_deep_daily"], 0)
        self.assertFalse(entitlements["features"]["bi_sales_timeline"])

    def test_daily_ocr_quota_enforcement(self):
        """Daily OCR quota increments atomically and denies further requests when limit reached."""
        # Baseline limit: 2 fast scans / day
        metric = "ocr_fast_scans"
        limit_key = "ocr_fast_daily"

        # Scan 1: Allowed
        ok, count, max_lim = EntitlementService.check_and_increment_usage(self.company.id, metric, limit_key)
        self.assertTrue(ok)
        self.assertEqual(count, 1)

        # Scan 2: Allowed
        ok, count, max_lim = EntitlementService.check_and_increment_usage(self.company.id, metric, limit_key)
        self.assertTrue(ok)
        self.assertEqual(count, 2)

        # Scan 3: Blocked (Limit reached)
        ok, count, max_lim = EntitlementService.check_and_increment_usage(self.company.id, metric, limit_key)
        self.assertFalse(ok)
        self.assertEqual(count, 2)

    def test_analytics_feature_gating_across_tiers(self):
        """Analytics APIs strictly enforce tier requirements via HTTP 403 Forbidden."""
        rfm_url = reverse('rfm_analysis', kwargs={"company_id": str(self.company.id)})

        # 1. Unsubscribed / Starter tier: Blocked from RFM
        res = self.client.get(rfm_url)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(res.json().get("upgrade_required"))

        # 2. Upgrade to Pro AI tier: RFM is unlocked!
        pro_plan = SubscriptionPlan.objects.get(id="pro_ai")
        Subscription.objects.create(
            company=self.company,
            user=self.user,
            plan=pro_plan,
            status="active",
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timedelta(days=365)
        )

        res = self.client.get(rfm_url)
        # RFM is authorized (returns 200 or engine calculation)
        self.assertNotEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # ==========================================
    # 7. Double-Entry Accounting Non-Interference
    # ==========================================

    def test_subscription_payments_do_not_create_accounting_vouchers(self):
        """
        Critical Accounting Invariant:
        SaaS subscription purchases must never generate sales/receipt vouchers
        inside the tenant's books.
        """
        initial_vouchers = Voucher.objects.filter(company=self.company).count()
        initial_entries = LedgerEntry.objects.filter(company=self.company).count()

        # Complete checkout and activation
        checkout = SubscriptionService.create_checkout_order(
            company=self.company,
            user=self.user,
            plan_id="enterprise"
        )
        payment_id = f"pay_{uuid.uuid4().hex[:14]}"
        sig = RazorpayService.compute_signature(checkout["order_id"], payment_id)

        SubscriptionService.verify_and_activate_checkout(
            company=self.company,
            user=self.user,
            razorpay_order_id=checkout["order_id"],
            razorpay_payment_id=payment_id,
            razorpay_signature=sig
        )

        final_vouchers = Voucher.objects.filter(company=self.company).count()
        final_entries = LedgerEntry.objects.filter(company=self.company).count()

        # Must remain exactly zero changes in accounting ledgers
        self.assertEqual(final_vouchers, initial_vouchers, "Subscription payment must NOT create accounting vouchers!")
        self.assertEqual(final_entries, initial_entries, "Subscription payment must NOT create ledger entries!")

    # ==========================================
    # 8. Tenant Isolation & IDOR Protection
    # ==========================================

    def test_cross_tenant_invoice_download_prevented(self):
        """User cannot access or download billing invoices belonging to another company."""
        # Create invoice for other_company
        txn = PaymentTransaction.objects.create(
            transaction_number="TXN-OTHER-001",
            company=self.other_company,
            user=self.other_user,
            amount_paise=70682,
            status="captured"
        )
        other_invoice = BillingInvoice.objects.create(
            invoice_number="SL-INV-202611-0099",
            company=self.other_company,
            user=self.other_user,
            transaction=txn,
            customer_name=self.other_company.name,
            customer_email="competitor@otherstore.in",
            plan_name="Starter",
            billing_period_start=timezone.localdate(),
            billing_period_end=timezone.localdate() + timedelta(days=365),
            taxable_amount_paise=59900,
            total_amount_paise=70682,
            status="paid"
        )

        # User attempts to download other company's invoice
        url = reverse('billing-invoice-download', kwargs={"invoice_id": str(other_invoice.id)})
        # Passing company_id of own company should return 404 (not found in company)
        response = self.client.get(f"{url}?company_id={self.company.id}")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Attempting with competitor's company_id should return 403 (unauthorized company)
        response = self.client.get(f"{url}?company_id={self.other_company.id}")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ==========================================
    # 9. Enterprise Grant & Custom Operational Limit Overrides
    # ==========================================

    def test_grant_enterprise_subscription_and_custom_quotas(self):
        """Administrative grant of Enterprise subscription unlocks all features and custom quotas."""
        # 1. Simulate quota exhaustion on baseline free tier
        DailyUsageTracker.objects.create(
            company=self.company,
            metric="ocr_fast_scans",
            date=timezone.localdate(),
            count=2
        )
        # Verify blocked on baseline (max_limit=2)
        allowed, current, max_lim = EntitlementService.check_and_increment_usage(
            self.company.id, "ocr_fast_scans", "ocr_fast_daily"
        )
        self.assertFalse(allowed)
        self.assertEqual(current, 2)
        self.assertEqual(max_lim, 2)

        # 2. Grant Enterprise subscription with elevated quotas
        sub = EntitlementService.grant_enterprise_subscription(
            company_id=self.company.id,
            user_id=self.user.id,
            days=3650,
            custom_limits={"ocr_fast_daily": 1000, "ocr_deep_daily": 200},
            notes="Administrative test grant"
        )
        self.assertEqual(sub.status, "active")
        self.assertEqual(sub.plan_id, "enterprise")

        # 3. Verify company entitlements reflect all features and custom limits
        entitlements = EntitlementService.get_company_entitlements(self.company.id)
        self.assertTrue(entitlements["has_active_subscription"])
        self.assertEqual(entitlements["plan_id"], "enterprise")
        self.assertEqual(entitlements["limits"]["ocr_fast_daily"], 1000)
        self.assertEqual(entitlements["limits"]["ocr_deep_daily"], 200)

        # All BI & Enterprise features must be True
        for feat_key in [
            "b2b_edi_network", "sales_invoicing", "double_entry_accounting",
            "gst_compliance", "inventory_management", "banking_reconciliation",
            "offline_pwa", "audit_trail", "bi_sales_timeline", "bi_monthly_trajectory",
            "bi_brand_mix", "bi_sales_forecast", "bi_rfm_segmentation",
            "bi_inventory_turnover", "bi_pareto_matrix", "bi_churn_radar", "bi_cash_cycle"
        ]:
            self.assertTrue(
                EntitlementService.check_feature_access(self.company.id, feat_key),
                f"Feature {feat_key} must be enabled on Enterprise tier!"
            )

        # 4. Verify usage tracker was reset and subsequent OCR request succeeds
        allowed, new_count, max_lim = EntitlementService.check_and_increment_usage(
            self.company.id, "ocr_fast_scans", "ocr_fast_daily"
        )
        self.assertTrue(allowed)
        self.assertEqual(new_count, 1)
        self.assertEqual(max_lim, 1000)

