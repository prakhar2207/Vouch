import uuid
from django.db import models
from apps.companies.models import Company

class Warehouse(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='warehouses')
    name = models.CharField(max_length=255)
    address = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.company.name})"


class ProductCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='product_categories')
    name = models.CharField(max_length=255)
    hsn_code = models.CharField(max_length=50, null=True, blank=True)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=18.00)
    
    # Feature 2: Ledger Mapping per Category
    sales_ledger = models.ForeignKey('ledgers.Ledger', on_delete=models.SET_NULL, null=True, blank=True, related_name='category_sales')
    purchase_ledger = models.ForeignKey('ledgers.Ledger', on_delete=models.SET_NULL, null=True, blank=True, related_name='category_purchases')
    
    class Meta:
        unique_together = ('company', 'name')

    def __str__(self):
        return self.name

class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='products')
    category = models.ForeignKey(ProductCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    name = models.CharField(max_length=255)
    brand = models.CharField(max_length=255, null=True, blank=True)
    
    # Feature 1: Alias / Short Names
    alias = models.CharField(max_length=255, null=True, blank=True)
    
    sku = models.CharField(max_length=100)
    barcode = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    
    # Feature 6: Alternate / Compound Units
    unit = models.CharField(max_length=50) # e.g., PCS, KG, LTR
    alternate_unit = models.CharField(max_length=50, null=True, blank=True)
    conversion_factor = models.DecimalField(max_digits=15, decimal_places=4, default=1.0000) # 1 base unit = x alternate unit, or vice versa
    
    # Feature 3: Tax Overrides
    hsn_code = models.CharField(max_length=50, null=True, blank=True) # Will store active HSN
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00) # Will store active GST
    tax_override = models.BooleanField(default=False)
    override_hsn_code = models.CharField(max_length=50, null=True, blank=True)
    override_gst_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    # Feature 5: Multiple Price Levels
    selling_price = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    wholesaler_price = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    min_selling_price = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    purchase_price = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    stock_quantity = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    reorder_level = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    # Feature 4: Batch & Serial Tracking Flags
    track_batches = models.BooleanField(default=False)
    track_serial_numbers = models.BooleanField(default=False)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('company', 'sku')

    def __str__(self):
        return f"{self.name} - {self.sku}"


class InventoryEntry(models.Model):
    MOVEMENT_CHOICES = (
        ('IN', 'In'),
        ('OUT', 'Out'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='inventory_entries')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='entries')
    
    # Feature 7: Godown (Warehouse) Allocation
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='entries')
    
    voucher_id = models.UUIDField(null=True, blank=True)
    movement_type = models.CharField(max_length=10, choices=MOVEMENT_CHOICES)
    quantity = models.DecimalField(max_digits=15, decimal_places=2)
    rate = models.DecimalField(max_digits=15, decimal_places=2)
    total_value = models.DecimalField(max_digits=15, decimal_places=2)
    
    # Feature 4: Batch & Serial Tracking Data
    batch_number = models.CharField(max_length=100, null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    serial_number = models.CharField(max_length=100, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product.name} | {self.movement_type} {self.quantity}"

