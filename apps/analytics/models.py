import uuid
import datetime
from decimal import Decimal
from django.db import models
from apps.companies.models import Company

class CashCycleSnapshot(models.Model):
    """
    Stores historical records of the company's Working Capital & Cash Conversion Cycle (CCC).
    Tracks Net CCC, DIO, DSO, and DPO over time to measure capital velocity improvement or decrement.
    """
    HEALTH_CHOICES = (
        ('HEALTHY', 'Healthy (<90 Days)'),
        ('MODERATE', 'Moderate (90-140 Days)'),
        ('ELEVATED_CYCLE', 'Elevated Cycle (>140 Days)'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='cash_cycle_snapshots')
    recorded_date = models.DateField(default=datetime.date.today)
    period_label = models.CharField(max_length=64, help_text="e.g. 'Oct 2026', 'Sep 2026', or 'Q2 Baseline'")

    # Core Cash Conversion Cycle Pillars (Days)
    net_ccc_days = models.IntegerField(default=0, help_text="Net Cash Conversion Cycle in days (DIO + DSO - DPO)")
    dio_days = models.IntegerField(default=0, help_text="Days Inventory Outstanding")
    dso_days = models.IntegerField(default=0, help_text="Days Sales Outstanding")
    dpo_days = models.IntegerField(default=0, help_text="Days Payable Outstanding")

    # Financial Balances at time of snapshot (INR)
    accounts_receivable = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    accounts_payable = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    inventory_valuation = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    total_sales = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    total_purchases = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    working_capital_health = models.CharField(max_length=32, choices=HEALTH_CHOICES, default="MODERATE")
    notes = models.CharField(max_length=255, blank=True, null=True, help_text="Optional annotation or milestone tag")
    is_system_generated = models.BooleanField(default=True, help_text="True if recorded automatically by analytics engine")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['recorded_date', 'created_at']
        unique_together = ('company', 'period_label')

    def __str__(self):
        return f"{self.company.name} - {self.period_label}: CCC {self.net_ccc_days}d"
