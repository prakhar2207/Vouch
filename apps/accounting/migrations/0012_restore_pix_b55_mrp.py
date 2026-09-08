from decimal import Decimal
from django.db import migrations

def restore_pix_mrp(apps, schema_editor):
    Product = apps.get_model('inventory', 'Product')

    # 1. Restore PIX B 55 MRP to 504.00 if it was overwritten to a sales rate like 205.54
    b55_pix = Product.objects.filter(brand__iexact='PIX', name__iexact='B 55')
    for p in b55_pix:
        if p.selling_price < Decimal('500.00'):
            p.selling_price = Decimal('504.00')
            p.save(update_fields=['selling_price'])

def reverse_pix_mrp(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0011_reassign_sales_tax_to_output_ledgers'),
    ]

    operations = [
        migrations.RunPython(restore_pix_mrp, reverse_pix_mrp),
    ]
