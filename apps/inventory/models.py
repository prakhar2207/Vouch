import uuid
from decimal import Decimal
from django.db import models
from apps.companies.models import Company
from apps.accounts.models import User

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
    purchase_price_from_invoice = models.BooleanField(default=False)
    
    stock_quantity = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    reorder_level = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    # Feature 4: Batch & Serial Tracking Flags
    track_batches = models.BooleanField(default=False)
    track_serial_numbers = models.BooleanField(default=False)
    
    # Custom attributes & features (e.g. color, imei_numbers list, specs, warranty)
    attributes = models.JSONField(default=dict, blank=True)
    
    # Feature 8: Inventory Valuation & Costing Method
    COSTING_METHOD_CHOICES = (
        ('AVG_COST', 'Average Cost'),
        ('FIFO', 'FIFO'),
        ('LIFO', 'LIFO'),
        ('STD_COST', 'Standard Cost'),
    )
    costing_method = models.CharField(max_length=20, choices=COSTING_METHOD_CHOICES, default='AVG_COST')
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('company', 'sku')
        indexes = [
            models.Index(fields=['company', 'is_active', 'name']),
            models.Index(fields=['company', 'updated_at']),
        ]

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

    class Meta:
        indexes = [
            models.Index(fields=['company', 'product', 'created_at']),
            models.Index(fields=['company', 'voucher_id']),
        ]

    def __str__(self):
        return f"{self.product.name} | {self.movement_type} {self.quantity}"


class PriceListImportJob(models.Model):
    STATUS_CHOICES = (
        ('UPLOADED', 'Uploaded'),
        ('QUEUED', 'Queued'),
        ('PROCESSING', 'Processing'),
        ('EXTRACTION_COMPLETED', 'Extraction Completed'),
        ('REVIEW_REQUIRED', 'Review Required'),
        ('READY_TO_COMMIT', 'Ready to Commit'),
        ('COMMITTING', 'Committing'),
        ('COMPLETED', 'Completed'),
        ('PARTIALLY_COMPLETED', 'Partially Completed'),
        ('FAILED', 'Failed'),
        ('CANCELLED', 'Cancelled'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='price_list_imports')
    category = models.ForeignKey(ProductCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='price_list_imports')
    brand = models.CharField(max_length=255, blank=True, null=True)
    source_filename = models.CharField(max_length=255)
    file_format = models.CharField(max_length=20, default='PDF') # PDF, XLSX, XLS, CSV, IMAGE
    file_hash = models.CharField(max_length=64, db_index=True)
    effective_date = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='UPLOADED')
    total_detected = models.PositiveIntegerField(default=0)
    matched_count = models.PositiveIntegerField(default=0)
    new_count = models.PositiveIntegerField(default=0)
    needs_review_count = models.PositiveIntegerField(default=0)
    applied_count = models.PositiveIntegerField(default=0)
    error_summary = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_price_list_imports')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['company', 'file_hash']),
            models.Index(fields=['company', 'created_at']),
        ]

    def __str__(self):
        return f"Import {self.source_filename} ({self.status}) - {self.company.name}"


class PriceListExtractedItem(models.Model):
    CONFIDENCE_CHOICES = (
        ('HIGH_CONFIDENCE', 'High Confidence'),
        ('NEEDS_REVIEW', 'Needs Review'),
        ('LOW_CONFIDENCE', 'Low Confidence'),
        ('INVALID', 'Invalid'),
        ('DUPLICATE', 'Duplicate'),
        ('UNMATCHED', 'Unmatched'),
    )

    ACTION_CHOICES = (
        ('CREATE_PRODUCT', 'Create New Product'),
        ('UPDATE_PRICE', 'Update Existing Product Price'),
        ('UPDATE_SELECTED_FIELDS', 'Update Selected Fields'),
        ('SKIP', 'Skip Product'),
        ('MANUAL_REVIEW', 'Mark for Manual Review'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(PriceListImportJob, on_delete=models.CASCADE, related_name='extracted_items')
    raw_text = models.TextField(blank=True, null=True)
    source_page = models.PositiveIntegerField(default=1)

    item_name = models.CharField(max_length=255)
    normalized_name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100, blank=True, null=True)
    barcode = models.CharField(max_length=100, blank=True, null=True)
    hsn_code = models.CharField(max_length=50, blank=True, null=True)
    unit = models.CharField(max_length=50, default='PCS')
    pack_size = models.CharField(max_length=50, blank=True, null=True)
    case_qty = models.PositiveIntegerField(default=1)
    section = models.CharField(max_length=255, blank=True, null=True)

    mrp = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    list_price = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    selling_price = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    purchase_price = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    wholesale_price = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    retail_price = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    is_tax_inclusive = models.BooleanField(null=True, blank=True)

    matched_product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='price_list_matches')
    match_method = models.CharField(max_length=50, blank=True, null=True)
    match_confidence = models.FloatField(default=0.0)
    match_reason = models.CharField(max_length=255, blank=True, null=True)

    existing_selling_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    existing_purchase_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    existing_mrp = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    price_delta = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    price_delta_percent = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    confidence_tier = models.CharField(max_length=30, choices=CONFIDENCE_CHOICES, default='NEEDS_REVIEW')
    validation_warnings = models.JSONField(default=list, blank=True)
    proposed_action = models.CharField(max_length=30, choices=ACTION_CHOICES, default='UPDATE_PRICE')
    is_approved = models.BooleanField(default=False)
    is_applied = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['job', 'confidence_tier']),
            models.Index(fields=['job', 'proposed_action']),
        ]

    def __str__(self):
        return f"{self.item_name} (MRP: {self.mrp}) -> {self.proposed_action}"


class PriceHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='price_histories')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='price_history')
    import_job = models.ForeignKey(PriceListImportJob, on_delete=models.SET_NULL, null=True, blank=True, related_name='price_changes')
    old_selling_price = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    new_selling_price = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    old_purchase_price = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    new_purchase_price = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    old_mrp = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    new_mrp = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    effective_date = models.CharField(max_length=100, blank=True, null=True)
    source = models.CharField(max_length=100, default='PRICE_LIST_IMPORT')
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='price_changes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'product', 'created_at']),
        ]

    def __str__(self):
        return f"{self.product.name}: ₹{self.old_selling_price} -> ₹{self.new_selling_price}"

