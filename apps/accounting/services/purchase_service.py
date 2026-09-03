from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.inventory.models import Product
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry
from apps.gst.services.gst_calculator import GSTCalculator

class PurchaseInvoiceService:
    @staticmethod
    @transaction.atomic
    def generate_purchase_invoice(company: Company, user, party_ledger: Ledger, items_data: list, purchase_ledger: Ledger, input_cgst_ledger: Ledger, input_sgst_ledger: Ledger, input_igst_ledger: Ledger, supplier_invoice_number: str = None, voucher_date=None):
        """
        End-to-End orchestration of a Purchase Invoice.
        """
        from apps.accounting.services.sequence_service import InvoiceSequenceService
        v_date = voucher_date if voucher_date else timezone.now().date()
        if supplier_invoice_number and supplier_invoice_number.strip():
            v_num = supplier_invoice_number.strip()
            fy = InvoiceSequenceService.get_or_create_active_fy(company, v_date)
        else:
            v_num, fy = InvoiceSequenceService.get_next_number(company, 'PURCHASE', v_date)
        
        voucher = Voucher.objects.create(
            company=company,
            financial_year=fy,
            voucher_type='PURCHASE',
            voucher_number=v_num,
            reference_number=supplier_invoice_number,
            voucher_date=v_date,
            party_ledger=party_ledger,
            status='DRAFT',
            created_by=user,
            narration=f"Purchase from {party_ledger.name}"
        )
        
        total_invoice_value = Decimal('0.00')
        total_taxable_value = Decimal('0.00')
        total_cgst = Decimal('0.00')
        total_sgst = Decimal('0.00')
        total_igst = Decimal('0.00')
        
        for item in items_data:
            product_id = item.get('product_id')
            if product_id:
                product = Product.objects.get(id=product_id)
            else:
                name = item.get('product_name', 'Unnamed Product')
                import uuid
                sku = item.get('sku', name.upper()[:3] + '-' + str(uuid.uuid4())[:6])
                
                defaults_dict = {
                    'sku': sku,
                    'hsn_code': item.get('hsn_code', ''),
                    'gst_rate': Decimal(str(item.get('gst_rate', '18.00'))),
                    'purchase_price': Decimal(str(item.get('rate', '0.00'))),
                    'unit': item.get('unit', 'PCS')
                }
                
                from apps.inventory.models import ProductCategory
                category = None
                category_id = item.get('category_id')
                category_name = item.get('category_name')

                if category_id:
                    try:
                        category = ProductCategory.objects.get(id=category_id, company=company)
                    except ProductCategory.DoesNotExist:
                        pass
                
                if not category and category_name and str(category_name).strip():
                    cat_name = str(category_name).strip()
                    category, _ = ProductCategory.objects.get_or_create(
                        company=company,
                        name=cat_name,
                        defaults={
                            'hsn_code': item.get('hsn_code', ''),
                            'gst_rate': Decimal(str(item.get('gst_rate', '18.00')))
                        }
                    )

                if not category:
                    category = ProductCategory.objects.filter(company=company).first()
                    if not category:
                        category = ProductCategory.objects.create(
                            company=company,
                            name="General Purchases",
                            hsn_code=item.get('hsn_code', ''),
                            gst_rate=Decimal(str(item.get('gst_rate', '18.00')))
                        )

                if category:
                    defaults_dict['category'] = category
                    if not defaults_dict.get('hsn_code'):
                        defaults_dict['hsn_code'] = category.hsn_code
                    if 'gst_rate' not in defaults_dict or defaults_dict['gst_rate'] == 0:
                        defaults_dict['gst_rate'] = category.gst_rate

                product, created = Product.objects.get_or_create(
                    company=company,
                    name=name,
                    defaults=defaults_dict
                )

                if not created and not product.category and category:
                    product.category = category
                    product.save(update_fields=['category'])

            qty = Decimal(str(item['quantity']))
            rate = Decimal(str(item['rate']))

            # Update product purchase price to latest purchase rate
            if not created and rate > Decimal('0.00'):
                product.purchase_price = rate
                product.save(update_fields=['purchase_price'])

            discount_pct = Decimal(str(item.get('discount_percent', '0.00')))
            
            gross = qty * rate
            discount_amt = (gross * discount_pct / Decimal('100')).quantize(Decimal('0.01'))
            taxable_amount = gross - discount_amt
            
            # 2. Calculate GST
            taxes = GSTCalculator.calculate_taxes(
                company_state_code=company.state_code,
                party_state_code=party_ledger.state_code,
                taxable_amount=taxable_amount,
                gst_rate=product.gst_rate
            )
            
            total_amount = taxable_amount + taxes['total_tax']
            
            VoucherItem.objects.create(
                voucher=voucher,
                product=product,
                quantity=qty,
                rate=rate,
                discount_percent=discount_pct,
                discount_amount=discount_amt,
                taxable_amount=taxable_amount,
                gst_rate=product.gst_rate,
                total_amount=total_amount
            )
            
            total_taxable_value += taxable_amount
            total_cgst += taxes['cgst']
            total_sgst += taxes['sgst']
            total_igst += taxes['igst']
            total_invoice_value += total_amount
            
        voucher.total_amount = total_invoice_value
        voucher.save(update_fields=['total_amount'])
        
        # 3. Generate strict Ledger Entries (The Double Entry)
        # Credit the Supplier (Party)
        LedgerEntry.objects.create(
            voucher=voucher,
            ledger=party_ledger,
            debit_amount=Decimal('0.00'),
            credit_amount=total_invoice_value
        )
        
        # Debit the Purchase Account
        LedgerEntry.objects.create(
            voucher=voucher,
            ledger=purchase_ledger,
            debit_amount=total_taxable_value,
            credit_amount=Decimal('0.00')
        )
        
        # Debit Tax Accounts (Input Tax Credit)
        if total_cgst > 0:
            LedgerEntry.objects.create(
                voucher=voucher,
                ledger=input_cgst_ledger,
                debit_amount=total_cgst,
                credit_amount=Decimal('0.00')
            )
        if total_sgst > 0:
            LedgerEntry.objects.create(
                voucher=voucher,
                ledger=input_sgst_ledger,
                debit_amount=total_sgst,
                credit_amount=Decimal('0.00')
            )
        if total_igst > 0:
            LedgerEntry.objects.create(
                voucher=voucher,
                ledger=input_igst_ledger,
                debit_amount=total_igst,
                credit_amount=Decimal('0.00')
            )
            
        return voucher
