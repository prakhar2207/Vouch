# Generated manually to clean orphan invoice tags and recalculate PIX B 72 purchase price
from decimal import Decimal
from django.db import migrations

def clean_orphan_invoice_tags_and_recalc(apps, schema_editor):
    Product = apps.get_model('inventory', 'Product')
    VoucherItem = apps.get_model('accounting', 'VoucherItem')

    # 1. Specifically fix PIX B 72
    pix_b72_items = Product.objects.filter(brand__iexact='PIX', name__iexact='B 72')
    for p in pix_b72_items:
        # Check if it actually has any posted purchase vouchers
        has_purchases = VoucherItem.objects.filter(
            product=p,
            voucher__voucher_type='PURCHASE',
            voucher__status='POSTED'
        ).exists()

        if not has_purchases:
            p.purchase_price_from_invoice = False
            # Find discount ratio from other PIX products in the same category (e.g. BB 72 with 62% discount -> 0.38 factor)
            other_pix = Product.objects.filter(
                company=p.company,
                category=p.category,
                brand__iexact='PIX',
                selling_price__gt=0,
                purchase_price__gt=0
            ).exclude(id=p.id).first()

            if other_pix and other_pix.selling_price > Decimal('0.00'):
                factor = other_pix.purchase_price / other_pix.selling_price
            else:
                factor = Decimal('0.38') # 62% discount standard for PIX

            if p.selling_price > Decimal('0.00'):
                p.purchase_price = (p.selling_price * factor).quantize(Decimal('0.01'))
            elif p.purchase_price == Decimal('66.24'):
                p.selling_price = Decimal('678.00')
                p.purchase_price = Decimal('257.64')

            p.save(update_fields=['purchase_price', 'purchase_price_from_invoice', 'selling_price'])

    # 2. Globally clean any products that have purchase_price_from_invoice = True but have NO posted purchase vouchers
    for p in Product.objects.filter(purchase_price_from_invoice=True):
        has_purchases = VoucherItem.objects.filter(
            product=p,
            voucher__voucher_type='PURCHASE',
            voucher__status='POSTED'
        ).exists()
        if not has_purchases:
            p.purchase_price_from_invoice = False
            # If brand is PIX and purchase_price was set from invoice 355 (e.g. 66.24 or 64.40)
            if (p.brand or '').strip().upper() == 'PIX' and p.selling_price > Decimal('0.00'):
                p.purchase_price = (p.selling_price * Decimal('0.38')).quantize(Decimal('0.01'))
                p.save(update_fields=['purchase_price', 'purchase_price_from_invoice'])
            else:
                p.save(update_fields=['purchase_price_from_invoice'])

def reverse_clean(apps, schema_editor):
    pass

class Migration(migrations.Migration):
    dependencies = [
        ('accounting', '0008_set_modicord_mrp_zero'),
        ('inventory', '0005_product_purchase_price_from_invoice'),
    ]

    operations = [
        migrations.RunPython(clean_orphan_invoice_tags_and_recalc, reverse_clean),
    ]
