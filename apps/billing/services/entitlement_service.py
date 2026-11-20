import logging
from typing import Dict, Any, Tuple, Optional
from django.utils import timezone
from django.db import transaction
from django.db.models import F
from apps.billing.models import SubscriptionPlan, Subscription, DailyUsageTracker
from apps.billing.constants import APPROVED_PLANS, DEFAULT_BASELINE_ENTITLEMENTS

logger = logging.getLogger(__name__)


class EntitlementService:
    """
    Centralized Feature Entitlement Engine.
    SriLekh's plans control backend functionality, API access, and operational limits.
    """

    @classmethod
    def sync_default_plans(cls) -> int:
        """
        Idempotently synchronizes the approved pricing & feature matrix into the database.
        """
        created_or_updated = 0
        for plan_data in APPROVED_PLANS:
            plan, created = SubscriptionPlan.objects.update_or_create(
                id=plan_data["id"],
                defaults={
                    "name": plan_data["name"],
                    "tagline": plan_data["tagline"],
                    "description": plan_data["description"],
                    "target_persona": plan_data["target_persona"],
                    "billing_interval": plan_data["billing_interval"],
                    "base_amount_paise": plan_data["base_amount_paise"],
                    "tax_rate": plan_data["tax_rate"],
                    "tax_amount_paise": plan_data["tax_amount_paise"],
                    "total_amount_paise": plan_data["total_amount_paise"],
                    "currency": plan_data["currency"],
                    "tier_order": plan_data["tier_order"],
                    "features": plan_data["features"],
                    "limits": plan_data["limits"],
                    "is_active": True,
                }
            )
            created_or_updated += 1
        return created_or_updated

    @classmethod
    def get_company_subscription(cls, company_id) -> Optional[Subscription]:
        """
        Retrieves the primary active subscription for the given company.
        """
        if not company_id:
            return None
        now = timezone.now()
        # Look for active subscription where period end has not elapsed
        return Subscription.objects.filter(
            company_id=company_id,
            status='active',
            current_period_end__gte=now
        ).select_related('plan').first()

    @classmethod
    def get_company_entitlements(cls, company_id) -> Dict[str, Any]:
        """
        Authoritative calculation of company entitlements, features, and limits.
        Falls back to baseline free tier if no active subscription exists.
        """
        sub = cls.get_company_subscription(company_id)
        if sub and sub.plan:
            plan = sub.plan
            return {
                "has_active_subscription": True,
                "subscription_id": str(sub.id),
                "plan_id": plan.id,
                "plan_name": plan.name,
                "billing_interval": sub.billing_interval,
                "status": sub.status,
                "current_period_start": sub.current_period_start.isoformat(),
                "current_period_end": sub.current_period_end.isoformat(),
                "next_billing_at": sub.next_billing_at.isoformat() if sub.next_billing_at else None,
                "features": dict(plan.features),
                "limits": dict(plan.limits),
            }

        # Baseline fallback
        baseline = dict(DEFAULT_BASELINE_ENTITLEMENTS)
        baseline["has_active_subscription"] = False
        baseline["subscription_id"] = None
        baseline["current_period_start"] = None
        baseline["current_period_end"] = None
        baseline["next_billing_at"] = None
        return baseline

    @classmethod
    def check_feature_access(cls, company_id, feature_key: str) -> bool:
        """
        Checks whether the specified feature is unlocked for the company.
        """
        entitlements = cls.get_company_entitlements(company_id)
        features = entitlements.get("features", {})
        return bool(features.get(feature_key, False))

    @classmethod
    def check_and_increment_usage(
        cls,
        company_id,
        metric: str,
        limit_key: str
    ) -> Tuple[bool, int, int]:
        """
        Checks daily usage against the active plan limit.
        If within limit, increments atomically in the database and returns (True, new_count, max_limit).
        If limit is reached, returns (False, current_count, max_limit) without incrementing.
        """
        entitlements = cls.get_company_entitlements(company_id)
        limits = entitlements.get("limits", {})
        max_limit = limits.get(limit_key, 0)

        # 0 means disabled or no quota
        if max_limit <= 0:
            return False, 0, 0

        today = timezone.localdate()

        with transaction.atomic():
            tracker, created = DailyUsageTracker.objects.select_for_update().get_or_create(
                company_id=company_id,
                metric=metric,
                date=today,
                defaults={"count": 0}
            )

            if tracker.count >= max_limit:
                logger.warning(
                    f"Plan limit exceeded for company={company_id}, metric={metric}: "
                    f"{tracker.count}/{max_limit} on {today}"
                )
                return False, tracker.count, max_limit

            tracker.count += 1
            tracker.save(update_fields=["count"])
            return True, tracker.count, max_limit

    @classmethod
    def get_daily_usage(cls, company_id, metric: str) -> int:
        """
        Gets current usage count for today.
        """
        today = timezone.localdate()
        tracker = DailyUsageTracker.objects.filter(
            company_id=company_id,
            metric=metric,
            date=today
        ).first()
        return tracker.count if tracker else 0
