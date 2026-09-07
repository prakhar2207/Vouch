# Generated manually to reset Modicord MRP / selling_price to 0.00 and ensure invoice tag
from decimal import Decimal
from django.db import migrations

def set_modicord_mrp_zero(apps, schema_editor):
    Product = apps.get_model('inventory', 'Product')
    Voucher = apps.get_model('accounting', 'Voucher')

    # Find all Modicord products
    modicord_products = Product.objects.filter(brand__icontains='modic')
    for p in modicord_products:
        # Modicord products uploaded from purchase bills without a price list have selling_price = 0.00
        p.selling_price = Decimal('0.00')
        # Check if product is referenced in any purchase voucher or has purchase_price > 0
        if p.voucher_items.filter(voucher__voucher_type='PURCHASE').exists() or p.purchase_price > Decimal('0.00'):
            p.purchase_price_from_invoice = True
        p.save(update_fields=['selling_price', 'purchase_price_from_invoice'])

def reverse_modicord_mrp(apps, schema_editor):
    pass

class Migration(migrations.Migration):
    dependencies = [
        ('accounting', '0007_relink_invoice_355_to_modicord'),
        ('inventory', '0005_product_purchase_price_from_invoice'),
    ]

    operations = [
        migrations.RunPython(set_modicord_mrp_zero, reverse_modicord_mrp),
    ]
