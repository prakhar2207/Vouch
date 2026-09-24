from django.contrib import admin
from .models import ProductCategory, Product, Warehouse

@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'hsn_code', 'gst_rate')
    search_fields = ('name', 'hsn_code', 'company__name')

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'brand', 'company', 'category', 'sku', 'selling_price', 'stock_quantity', 'unit', 'gst_rate', 'is_active')
    list_filter = ('is_active', 'unit')
    search_fields = ('name', 'brand', 'sku', 'barcode', 'company__name', 'hsn_code')
    raw_id_fields = ('company', 'category')

@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'address', 'is_active', 'created_at')
    search_fields = ('name', 'company__name')
