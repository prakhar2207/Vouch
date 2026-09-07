# Generated manually to repair Invoice #355 line items and transfer stock from PIX to Modicord
from decimal import Decimal
import uuid
from django.db import migrations

def relink_invoice_355_to_modicord(apps, schema_editor):
    Voucher = apps.get_model('accounting', 'Voucher')
    VoucherItem = apps.get_model('accounting', 'VoucherItem')
    Product = apps.get_model('inventory', 'Product')
    InventoryEntry = apps.get_model('inventory', 'InventoryEntry')

    # Find vouchers matching #355 or supplier SHREE ADINATH TRADERS
    vouchers = list(Voucher.objects.filter(voucher_number__in=['355', '0355', '#355']))
    adinath_vouchers = list(Voucher.objects.filter(party_ledger__name__icontains='ADINATH', voucher_type='PURCHASE'))
    
    all_target_vouchers = {v.id: v for v in (vouchers + adinath_vouchers)}.values()

    for v in all_target_vouchers:
        # Check if party is Adinath or invoice number is 355
        is_adinath = v.party_ledger and 'ADINATH' in v.party_ledger.name.upper()
        is_355 = str(v.voucher_number).strip() in ['355', '0355', '#355']
        if not (is_adinath or is_355):
            continue

        company = v.company

        # Determine target Modicord brand naming in this company
        existing_modicor = Product.objects.filter(company=company, brand__icontains='modic').first()
        target_brand = existing_modicor.brand if existing_modicor else 'Modicord'

        for item in v.items.all():
            old_prod = item.product
            if not old_prod:
                continue

            current_brand = (old_prod.brand or '').strip()
            # If item is linked to PIX or any non-Modicord brand, relink it to Modicord
            if 'MODIC' not in current_brand.upper():
                qty = item.quantity
                rate = item.rate

                # 1. Deduct stock from the mistakenly credited product (e.g. PIX)
                old_prod.stock_quantity = max(Decimal('0.00'), old_prod.stock_quantity - qty)
                old_prod.save(update_fields=['stock_quantity'])

                # 2. Find or create the Modicord product
                new_prod = Product.objects.filter(
                    company=company,
                    name__iexact=old_prod.name,
                    brand__icontains='modic'
                ).first()

                if not new_prod:
                    sku = f"{old_prod.name[:4].upper()}-{uuid.uuid4().hex[:6].upper()}"
                    new_prod = Product.objects.create(
                        company=company,
                        category=old_prod.category,
                        name=old_prod.name,
                        brand=target_brand,
                        sku=sku,
                        hsn_code=old_prod.hsn_code or '4010',
                        gst_rate=old_prod.gst_rate or Decimal('18.00'),
                        unit=old_prod.unit or 'PCS',
                        stock_quantity=Decimal('0.00'),
                        purchase_price=rate,
                        purchase_price_from_invoice=True,
                        selling_price=Decimal('0.00')
                    )

                # 3. Add stock to the Modicord product and update purchase price
                new_prod.stock_quantity += qty
                if rate > Decimal('0.00'):
                    new_prod.purchase_price = rate
                    new_prod.purchase_price_from_invoice = True
                new_prod.save(update_fields=['stock_quantity', 'purchase_price', 'purchase_price_from_invoice'])

                # 4. Relink voucher item to Modicord product
                item.product = new_prod
                item.save(update_fields=['product'])

                # 5. Relink inventory ledger entries
                InventoryEntry.objects.filter(
                    voucher_id=v.id,
                    product=old_prod
                ).update(product=new_prod)

def reverse_relink(apps, schema_editor):
    pass

class Migration(migrations.Migration):
    dependencies = [
        ('accounting', '0006_resync_sequences_and_recalculate_ledger_balances'),
        ('inventory', '0005_product_purchase_price_from_invoice'),
    ]

    operations = [
        migrations.RunPython(relink_invoice_355_to_modicord, reverse_relink),
    ]
