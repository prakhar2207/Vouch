import uuid
from django.db import models
from apps.companies.models import Company

class LedgerGroup(models.Model):
    NATURE_CHOICES = (
        ('ASSET', 'Asset'),
        ('LIABILITY', 'Liability'),
        ('INCOME', 'Income'),
        ('EXPENSE', 'Expense'),
        ('EQUITY', 'Equity'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='ledger_groups')
    name = models.CharField(max_length=255)
    parent_group = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='sub_groups')
    nature = models.CharField(max_length=50, choices=NATURE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.company.name})"

class Ledger(models.Model):
    BALANCE_TYPE_CHOICES = (
        ('DEBIT', 'Debit'),
        ('CREDIT', 'Credit'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='ledgers')
    group = models.ForeignKey(LedgerGroup, on_delete=models.PROTECT, related_name='ledgers')
    name = models.CharField(max_length=255)
    ledger_type = models.CharField(max_length=100) # e.g., CUSTOMER, SUPPLIER, BANK, CASH, TAX, GENERAL
    gstin = models.CharField(max_length=15, null=True, blank=True)
    state_code = models.CharField(max_length=2, null=True, blank=True)
    
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    opening_balance_type = models.CharField(max_length=10, choices=BALANCE_TYPE_CHOICES, default='DEBIT')
    current_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    credit_limit = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.company.name})"
