import uuid
from decimal import Decimal
from datetime import timedelta
from django.db import migrations
from django.utils import timezone


def grant_enterprise_to_maa_annapurna(apps, schema_editor):
    Company = apps.get_model('companies', 'Company')
    SubscriptionPlan = apps.get_model('billing', 'SubscriptionPlan')
    Subscription = apps.get_model('billing', 'Subscription')
    DailyUsageTracker = apps.get_model('billing', 'DailyUsageTracker')

    # 1. Ensure Enterprise Plan exists in database
    enterprise_features = {
        "b2b_edi_network": True,
        "sales_invoicing": True,
        "double_entry_accounting": True,
        "gst_compliance": True,
        "inventory_management": True,
        "banking_reconciliation": True,
        "offline_pwa": True,
        "audit_trail": True,
        "bi_sales_timeline": True,
        "bi_monthly_trajectory": True,
        "bi_brand_mix": True,
        "bi_sales_forecast": True,
        "bi_rfm_segmentation": True,
        "bi_inventory_turnover": True,
        "bi_pareto_matrix": True,
        "bi_churn_radar": True,
        "bi_cash_cycle": True,
    }
    enterprise_limits = {
        "ocr_fast_daily": 100,
        "ocr_deep_daily": 20,
    }

    enterprise_plan, _ = SubscriptionPlan.objects.update_or_create(
        id="enterprise",
        defaults={
            "name": "Enterprise",
            "tagline": "Large Distributors",
            "description": "Full platform access with 80/20 Pareto Matrix, Churn Radar, Cash Conversion Cycle analytics, and high-volume OCR scanning.",
            "target_persona": "Large Distributors",
            "billing_interval": "annual",
            "base_amount_paise": 399900,
            "tax_rate": Decimal("18.00"),
            "tax_amount_paise": 71982,
            "total_amount_paise": 471882,
            "currency": "INR",
            "tier_order": 4,
            "features": enterprise_features,
            "limits": enterprise_limits,
            "is_active": True,
        }
    )

    # 2. Search for Maa Annapurna Belting Store tenant
    target_uuid = "5d2e5dea-ff86-4871-b2af-fe1c5a05c03c"
    matching_companies = Company.objects.filter(id=target_uuid)
    if not matching_companies.exists():
        matching_companies = Company.objects.filter(name__icontains="Maa Annapurna")

    if not matching_companies.exists():
        print(f"[MIGRATION 0002] Maa Annapurna Belting Store not present in current DB; skipping subscription grant.")
        return

    now = timezone.now()
    ten_years_later = now + timedelta(days=3650)

    # Elevated limits granted specifically for SriLekh platform services
    granted_metadata = {
        "granted_by": "system_admin",
        "notes": "Full platform access and elevated OCR quotas granted for Maa Annapurna Belting Store",
        "limits": {
            "ocr_fast_daily": 1000,
            "ocr_deep_daily": 200,
        }
    }

    for company in matching_companies:
        sub = Subscription.objects.filter(company=company).first()
        if sub:
            sub.plan = enterprise_plan
            sub.status = "active"
            sub.billing_interval = "annual"
            sub.current_period_start = now
            sub.current_period_end = ten_years_later
            sub.cancelled_at = None
            sub.ended_at = None
            sub.metadata = granted_metadata
            sub.save()
        else:
            sub = Subscription.objects.create(
                id=uuid.uuid4(),
                company=company,
                plan=enterprise_plan,
                billing_interval="annual",
                status="active",
                current_period_start=now,
                current_period_end=ten_years_later,
                metadata=granted_metadata
            )

        # Clear daily usage trackers immediately so any exhausted quota is refreshed
        deleted_count, _ = DailyUsageTracker.objects.filter(company=company).delete()

        print(
            f"[MIGRATION 0002] Granted Enterprise subscription to '{company.name}' ({company.id}): "
            f"Active until {ten_years_later.date()}, daily usage reset ({deleted_count} trackers cleared)."
        )


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(grant_enterprise_to_maa_annapurna, reverse_code=migrations.RunPython.noop),
    ]
