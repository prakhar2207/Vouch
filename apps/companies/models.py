import uuid
from django.db import models
from apps.accounts.models import User

class Company(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    legal_name = models.CharField(max_length=255)
    gstin = models.CharField(max_length=15)
    pan = models.CharField(max_length=10)
    state_code = models.CharField(max_length=2)
    state_name = models.CharField(max_length=100)
    address = models.TextField()
    city = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    financial_year_start = models.DateField()
    
    # Proprietor Details
    proprietor_name = models.CharField(max_length=255, null=True, blank=True)
    proprietor_phone = models.CharField(max_length=20, null=True, blank=True)
    proprietor_signature = models.ImageField(upload_to='signatures/', null=True, blank=True)
    
    # Optional Details
    tagline = models.CharField(max_length=255, null=True, blank=True)
    bank_name = models.CharField(max_length=255, null=True, blank=True)
    bank_account_number = models.CharField(max_length=100, null=True, blank=True)
    bank_ifsc = models.CharField(max_length=50, null=True, blank=True)
    bank_branch = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class UserCompany(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='companies')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='users')
    role = models.CharField(max_length=20, choices=User.ROLE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'company')

    def __str__(self):
        return f"{self.user.email} - {self.company.name} ({self.role})"

class CompanySettings(models.Model):
    company = models.OneToOneField(Company, on_delete=models.CASCADE, primary_key=True, related_name='settings')
    sales_invoice_prefix = models.CharField(max_length=10, default='SAL')
    purchase_invoice_prefix = models.CharField(max_length=10, default='PUR')
    allow_negative_stock = models.BooleanField(default=False)
    complexity_level = models.IntegerField(default=1, help_text="1: Small (1-5), 2: Medium (6-10), 3: Large (10+)")
    enable_ledger_mapping = models.BooleanField(default=False)
    enable_manual_invoice_number = models.BooleanField(default=False)
    enable_advanced_item_creation = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Settings for {self.company.name}"
