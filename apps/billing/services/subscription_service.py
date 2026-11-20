import logging
import uuid
from datetime import timedelta
from typing import Dict, Any, Optional
from django.utils import timezone
from django.db import transaction
from rest_framework.exceptions import ValidationError, PermissionDenied

from apps.billing.models import (
    SubscriptionPlan,
    Subscription,
    PaymentTransaction,
    BillingInvoice,
    WebhookEvent
)
from apps.billing.services.razorpay_service import RazorpayService
from apps.billing.services.invoice_service import InvoiceService
from apps.billing.services.entitlement_service import EntitlementService

logger = logging.getLogger(__name__)


class SubscriptionService:
    """
    Core subscription orchestration service.
    Handles checkout order generation, cryptographic payment verification,
    subscription activation, renewals, cancellations, and webhook event dispatch.
    """

    @classmethod
    def create_checkout_order(
        cls,
        company,
        user,
        plan_id: str
    ) -> Dict[str, Any]:
        """
        Creates an order for subscription checkout.
        Enforces plan validity, company authorization, and records pending transaction.
        """
        try:
            plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            raise ValidationError(f"Plan '{plan_id}' does not exist or is not active.")

        total_amount_paise = plan.total_amount_paise
        transaction_number = f"TXN-{uuid.uuid4().hex[:12].upper()}"

        # 1. Create Razorpay order via Razorpay API / Test Mode
        notes = {
            "company_id": str(company.id),
            "company_name": company.name,
            "user_id": str(user.id) if user else "",
            "plan_id": plan.id,
            "transaction_number": transaction_number,
        }

        order_data = RazorpayService.create_order(
            amount_paise=total_amount_paise,
            currency=plan.currency,
            receipt=transaction_number,
            notes=notes
        )

        razorpay_order_id = order_data.get("id")

        # 2. Persist pending PaymentTransaction
        txn = PaymentTransaction.objects.create(
            transaction_number=transaction_number,
            company=company,
            user=user,
            razorpay_order_id=razorpay_order_id,
            amount_paise=total_amount_paise,
            currency=plan.currency,
            status='created',
            metadata={
                "plan_id": plan.id,
                "plan_name": plan.name,
                "billing_interval": plan.billing_interval,
                "order_details": order_data
            }
        )

        return {
            "order_id": razorpay_order_id,
            "amount": total_amount_paise,
            "currency": plan.currency,
            "key_id": RazorpayService.get_key_id(),
            "transaction_number": txn.transaction_number,
            "plan": {
                "id": plan.id,
                "name": plan.name,
                "total_amount_rupees": float(plan.total_amount_rupees),
                "billing_interval": plan.billing_interval,
            },
            "company": {
                "id": str(company.id),
                "name": company.name,
                "email": company.email or (user.email if user else ""),
            }
        }

    @classmethod
    def verify_and_activate_checkout(
        cls,
        company,
        user,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str
    ) -> Dict[str, Any]:
        """
        Authoritatively verifies Razorpay checkout signature and activates the subscription.
        Prevents duplicate execution, replay attacks, and cross-company tampering.
        """
        if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
            raise ValidationError("razorpay_order_id, razorpay_payment_id, and razorpay_signature are required.")

        # 1. Look up pending transaction for this company
        txn = PaymentTransaction.objects.filter(
            razorpay_order_id=razorpay_order_id,
            company=company
        ).first()

        if not txn:
            logger.error(f"Unauthorized or non-existent transaction for order={razorpay_order_id}, company={company.id}")
            raise ValidationError("Order not found or not associated with this company workspace.")

        # 2. Duplicate payment check (Idempotency)
        if txn.status == 'captured' and txn.signature_verified:
            logger.info(f"Transaction {txn.transaction_number} already verified and active.")
            sub = txn.subscription
            inv = getattr(txn, 'invoice', None)
            return {
                "success": True,
                "already_processed": True,
                "subscription_id": str(sub.id) if sub else None,
                "plan_id": sub.plan_id if sub else None,
                "invoice_number": inv.invoice_number if inv else None,
            }

        # 3. Verify cryptographic HMAC signature
        is_valid = RazorpayService.verify_payment_signature(
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_signature=razorpay_signature
        )

        if not is_valid:
            txn.status = 'failed'
            txn.failure_reason = "Cryptographic signature verification failed."
            txn.save(update_fields=['status', 'failure_reason', 'updated_at'])
            logger.warning(f"Signature verification failed for order={razorpay_order_id}, payment={razorpay_payment_id}")
            raise ValidationError("Payment signature verification failed.")

        with transaction.atomic():
            # 4. Resolve plan from transaction metadata
            plan_id = txn.metadata.get("plan_id")
            try:
                plan = SubscriptionPlan.objects.get(id=plan_id)
            except SubscriptionPlan.DoesNotExist:
                raise ValidationError(f"Plan '{plan_id}' does not exist.")

            now = timezone.now()
            # Annual subscription validity: 365 days
            if plan.billing_interval == 'annual':
                period_end = now + timedelta(days=365)
            else:
                period_end = now + timedelta(days=30)

            # 5. Create or update company subscription
            sub = Subscription.objects.create(
                company=company,
                user=user,
                plan=plan,
                billing_interval=plan.billing_interval,
                status='active',
                current_period_start=now,
                current_period_end=period_end,
                next_billing_at=period_end,
                metadata={
                    "activated_via": "razorpay_checkout",
                    "payment_id": razorpay_payment_id,
                    "order_id": razorpay_order_id,
                }
            )

            # 6. Update transaction to captured
            txn.status = 'captured'
            txn.razorpay_payment_id = razorpay_payment_id
            txn.razorpay_signature = razorpay_signature
            txn.signature_verified = True
            txn.subscription = sub
            txn.save(update_fields=[
                'status',
                'razorpay_payment_id',
                'razorpay_signature',
                'signature_verified',
                'subscription',
                'updated_at'
            ])

            # 7. Generate subscription billing tax invoice
            invoice = InvoiceService.create_invoice_for_transaction(txn, sub)

            logger.info(
                f"Successfully activated {plan.name} for company={company.name} "
                f"via txn={txn.transaction_number}, invoice={invoice.invoice_number}"
            )

            return {
                "success": True,
                "subscription_id": str(sub.id),
                "plan_id": plan.id,
                "plan_name": plan.name,
                "status": sub.status,
                "current_period_end": sub.current_period_end.isoformat(),
                "invoice_number": invoice.invoice_number,
                "transaction_number": txn.transaction_number,
            }

    @classmethod
    def cancel_subscription(
        cls,
        company,
        user,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        Cancels the active company subscription.
        Access continues until current_period_end per standard SaaS billing policy.
        """
        with transaction.atomic():
            sub = Subscription.objects.select_for_update().filter(
                company=company,
                status='active'
            ).order_by('-created_at').first()

            if not sub:
                raise ValidationError("No active subscription found to cancel.")

            sub.status = 'cancelled'
            sub.cancelled_at = timezone.now()
            meta = dict(sub.metadata)
            meta["cancellation_reason"] = reason or "Customer requested cancellation"
            meta["cancelled_by_user_id"] = str(user.id) if user else ""
            sub.metadata = meta
            sub.save(update_fields=['status', 'cancelled_at', 'metadata', 'updated_at'])

            logger.info(f"Cancelled subscription {sub.id} for company={company.name}")

            return {
                "success": True,
                "subscription_id": str(sub.id),
                "status": sub.status,
                "access_valid_until": sub.current_period_end.isoformat(),
                "message": "Subscription cancelled. Access remains active until the end of your billing cycle."
            }

    @classmethod
    def process_webhook_event(
        cls,
        event_payload: Dict[str, Any],
        signature: str,
        raw_body: bytes
    ) -> Dict[str, Any]:
        """
        Idempotent Razorpay Webhook processor.
        Verifies cryptographic authenticity of raw body and processes relevant events:
        - payment.captured
        - payment.failed
        - subscription.charged
        - subscription.cancelled
        """
        # 1. Verify webhook signature
        if not RazorpayService.verify_webhook_signature(raw_body, signature):
            logger.warning("Rejected webhook with invalid signature.")
            raise ValidationError("Invalid webhook signature.")

        event_id = event_payload.get("event_id") or event_payload.get("id") or str(uuid.uuid4())
        event_type = event_payload.get("event") or "unknown"

        with transaction.atomic():
            # 2. Check for duplicate webhook event (Idempotency)
            existing_event = WebhookEvent.objects.filter(event_id=event_id).first()
            if existing_event:
                if existing_event.processing_status == 'processed':
                    logger.info(f"Duplicate webhook event {event_id} ignored (already processed).")
                    return {"status": "ignored", "reason": "duplicate_event"}

            webhook_record, _ = WebhookEvent.objects.get_or_create(
                event_id=event_id,
                defaults={
                    "event_type": event_type,
                    "signature": signature,
                    "signature_verified": True,
                    "payload": event_payload,
                    "processing_status": "pending",
                }
            )

            try:
                if event_type == "payment.captured":
                    payment_entity = event_payload.get("payload", {}).get("payment", {}).get("entity", {})
                    order_id = payment_entity.get("order_id")
                    payment_id = payment_entity.get("id")

                    if order_id and payment_id:
                        txn = PaymentTransaction.objects.filter(razorpay_order_id=order_id).first()
                        if txn and txn.status != 'captured':
                            txn.status = 'captured'
                            txn.razorpay_payment_id = payment_id
                            txn.signature_verified = True
                            txn.save(update_fields=['status', 'razorpay_payment_id', 'signature_verified', 'updated_at'])

                elif event_type == "payment.failed":
                    payment_entity = event_payload.get("payload", {}).get("payment", {}).get("entity", {})
                    order_id = payment_entity.get("order_id")
                    if order_id:
                        txn = PaymentTransaction.objects.filter(razorpay_order_id=order_id).first()
                        if txn:
                            txn.status = 'failed'
                            txn.failure_reason = payment_entity.get("error_description", "Payment failed")
                            txn.save(update_fields=['status', 'failure_reason', 'updated_at'])

                elif event_type == "subscription.cancelled":
                    sub_entity = event_payload.get("payload", {}).get("subscription", {}).get("entity", {})
                    sub_id = sub_entity.get("id")
                    if sub_id:
                        sub = Subscription.objects.filter(razorpay_subscription_id=sub_id).first()
                        if sub:
                            sub.status = 'cancelled'
                            sub.cancelled_at = timezone.now()
                            sub.save(update_fields=['status', 'cancelled_at', 'updated_at'])

                webhook_record.processing_status = 'processed'
                webhook_record.processed_at = timezone.now()
                webhook_record.save(update_fields=['processing_status', 'processed_at'])

                return {"status": "success", "event_id": event_id, "event_type": event_type}

            except Exception as e:
                logger.error(f"Error processing webhook event {event_id}: {e}", exc_info=True)
                webhook_record.processing_status = 'failed'
                webhook_record.error_message = str(e)
                webhook_record.retry_count += 1
                webhook_record.save(update_fields=['processing_status', 'error_message', 'retry_count'])
                raise
