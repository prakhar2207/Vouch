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
    opening_date = models.DateField(null=True, blank=True)
    current_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    credit_limit = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    credit_period_days = models.PositiveIntegerField(default=0, help_text="Credit terms in days (0 for Immediate)")
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="Default discount percentage for this party")
    phone = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    bank_account_number = models.CharField(max_length=100, null=True, blank=True)
    bank_ifsc = models.CharField(max_length=50, null=True, blank=True)
    upi_id = models.CharField(max_length=100, null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def canonical_role(self):
        lt = (self.ledger_type or '').upper()
        if lt in ['CUSTOMER', 'SUPPLIER', 'BOTH']:
            return lt
        grp_name = (self.group.name if self.group else '').lower()
        if 'debtor' in grp_name:
            return 'CUSTOMER'
        if 'creditor' in grp_name:
            return 'SUPPLIER'
        return 'OTHER'

    @property
    def balance_state(self):
        """
        Determines semantic balance state:
        - CUSTOMER: >0 TO_COLLECT, <0 ADVANCE_RECEIVED, ==0 SETTLED
        - SUPPLIER: >0 TO_PAY, <0 ADVANCE_PAID, ==0 SETTLED
        - BOTH: >0 TO_COLLECT, <0 TO_PAY, ==0 SETTLED
        - OTHER: based on opening_balance_type
        """
        from decimal import Decimal
        bal = Decimal(str(self.current_balance or 0))
        if bal == Decimal('0.00'):
            return 'SETTLED'

        role = self.canonical_role
        if role == 'CUSTOMER':
            return 'TO_COLLECT' if bal > 0 else 'ADVANCE_RECEIVED'
        elif role == 'SUPPLIER':
            return 'TO_PAY' if bal > 0 else 'ADVANCE_PAID'
        elif role == 'BOTH':
            return 'TO_COLLECT' if bal > 0 else 'TO_PAY'
        else:
            if self.opening_balance_type == 'DEBIT':
                return 'TO_COLLECT' if bal > 0 else 'ADVANCE_RECEIVED'
            else:
                return 'TO_PAY' if bal > 0 else 'ADVANCE_PAID'

    @property
    def display_amount(self):
        from decimal import Decimal
        return abs(Decimal(str(self.current_balance or 0)))

    @property
    def initial_opening_balance(self):
        return self.opening_balance

    @property
    def initial_opening_type(self):
        return 'DR' if self.opening_balance_type == 'DEBIT' else 'CR'

    def __str__(self):
        return f"{self.name} ({self.company.name})"
