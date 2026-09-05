from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.inventory.models import Product
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry
from apps.gst.services.gst_calculator import GSTCalculator

class SalesInvoiceService:
    @staticmethod
    @transaction.atomic
    def generate_sales_invoice(company: Company, user, party_ledger: Ledger, items_data: list, sales_ledger: Ledger, cgst_ledger: Ledger, sgst_ledger: Ledger, igst_ledger: Ledger, manual_voucher_number=None, manual_voucher_date=None):
        """
        End-to-End orchestration of a Sales Invoice.
        1. Calculates precise GST and discounts.
        2. Generates Voucher and VoucherItems.
        3. Generates the exact 5-way double-entry accounting strings.
        Returns the DRAFT voucher.
        """
        # 1. Create Voucher Header
        from apps.accounting.services.sequence_service import InvoiceSequenceService
        v_date = manual_voucher_date if manual_voucher_date else timezone.now().date()
        if manual_voucher_number:
            v_num = manual_voucher_number
            fy = InvoiceSequenceService.get_or_create_active_fy(company, v_date)
        else:
            v_num, fy = InvoiceSequenceService.get_next_number(company, 'SALES', v_date)
        
        voucher = Voucher.objects.create(
            company=company,
            financial_year=fy,
            voucher_type='SALES',
            voucher_number=v_num,
            voucher_date=v_date,
            party_ledger=party_ledger,
            status='DRAFT',
            created_by=user,
            narration=f"Sales to {party_ledger.name}"
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
                # Auto-create product on the fly if it doesn't exist
                name = item.get('product_name', 'Unnamed Product')
                import uuid
                sku = item.get('sku', name.upper()[:3] + '-' + str(uuid.uuid4())[:6])
                
                defaults_dict = {
                    'sku': sku,
                    'hsn_code': item.get('hsn_code', ''),
                    'gst_rate': Decimal(str(item.get('gst_rate', '18.00'))),
                    'selling_price': Decimal(str(item.get('rate', '0.00'))),
                    'unit': item.get('unit', 'PCS')
                }
                
                # Link category and inherit if available
                category_id = item.get('category_id')
                if category_id:
                    from apps.inventory.models import ProductCategory
                    try:
                        category = ProductCategory.objects.get(id=category_id)
                        defaults_dict['category'] = category
                        defaults_dict['hsn_code'] = category.hsn_code
                        defaults_dict['gst_rate'] = category.gst_rate
                    except ProductCategory.DoesNotExist:
                        pass
                
                product, created = Product.objects.get_or_create(
                    company=company,
                    name=name,
                    defaults=defaults_dict
                )

            qty = Decimal(str(item['quantity']))
            rate = Decimal(str(item.get('rate', '0.00')))
            discount_pct = Decimal(str(item.get('discount_percent', '0.00')))
            
            # Automatically fetch rate from product's list price / MRP if rate is 0
            if rate <= Decimal('0.00') and product.selling_price > Decimal('0.00'):
                rate = product.selling_price
                
            # Automatically apply party's default discount if discount_percent is 0
            if discount_pct <= Decimal('0.00') and party_ledger.discount_percent > Decimal('0.00'):
                discount_pct = party_ledger.discount_percent

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
            
            # Create Voucher Item
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
            
        # Round Off calculation:
        # If decimal value < 0.5 then floor, if >= 0.5 then ceiling
        unrounded_total = total_invoice_value
        integer_part = Decimal(int(unrounded_total))
        decimal_part = unrounded_total - integer_part
        if decimal_part < Decimal('0.50'):
            rounded_total = integer_part.quantize(Decimal('0.01'))
        else:
            rounded_total = (integer_part + Decimal('1.00')).quantize(Decimal('0.01'))
            
        round_off = (rounded_total - unrounded_total).quantize(Decimal('0.01'))

        voucher.total_amount = rounded_total
        voucher.save(update_fields=['total_amount'])
        
        # 3. Generate strict Ledger Entries (The Double Entry)
        # Debit the Party (Customer) with rounded total payable amount
        LedgerEntry.objects.create(
            voucher=voucher,
            ledger=party_ledger,
            debit_amount=rounded_total,
            credit_amount=Decimal('0.00')
        )
        
        # Credit the Sales Account
        LedgerEntry.objects.create(
            voucher=voucher,
            ledger=sales_ledger,
            debit_amount=Decimal('0.00'),
            credit_amount=total_taxable_value
        )
        
        # Credit Tax Accounts
        if total_cgst > 0:
            LedgerEntry.objects.create(
                voucher=voucher,
                ledger=cgst_ledger,
                debit_amount=Decimal('0.00'),
                credit_amount=total_cgst
            )
        if total_sgst > 0:
            LedgerEntry.objects.create(
                voucher=voucher,
                ledger=sgst_ledger,
                debit_amount=Decimal('0.00'),
                credit_amount=total_sgst
            )
        if total_igst > 0:
            LedgerEntry.objects.create(
                voucher=voucher,
                ledger=igst_ledger,
                debit_amount=Decimal('0.00'),
                credit_amount=total_igst
            )

        # Round Off balancing entry:
        # If round_off < 0: Debits (party = rounded) < Credits (sales + taxes = unrounded).
        # Need DEBIT of abs(round_off) to Round Off ledger (Expense).
        # If round_off > 0: Debits (party = rounded) > Credits (sales + taxes = unrounded).
        # Need CREDIT of round_off to Round Off ledger (Income).
        if round_off != Decimal('0.00'):
            round_off_ledger = SalesInvoiceService._get_or_create_round_off_ledger(company)
            if round_off < Decimal('0.00'):
                LedgerEntry.objects.create(
                    voucher=voucher,
                    ledger=round_off_ledger,
                    debit_amount=abs(round_off),
                    credit_amount=Decimal('0.00')
                )
            else:
                LedgerEntry.objects.create(
                    voucher=voucher,
                    ledger=round_off_ledger,
                    debit_amount=Decimal('0.00'),
                    credit_amount=round_off
                )

        # Trigger B2B Network EDI Handshake if buyer is a registered Company
        try:
            from apps.accounting.services.edi_service import EDIService
            EDIService.create_inward_request_for_sales_voucher(voucher)
        except Exception as e:
            # Non-blocking log to ensure sales invoice creation doesn't fail
            print(f"[EDI Error] Failed to create inward voucher request: {e}")
            
        return voucher

    @staticmethod
    def _get_or_create_round_off_ledger(company: Company) -> Ledger:
        from apps.ledgers.models import LedgerGroup
        round_off = Ledger.objects.filter(company=company, name__iexact="Round Off").first()
        if not round_off:
            expense_grp = LedgerGroup.objects.filter(company=company, nature="EXPENSE").first()
            if not expense_grp:
                expense_grp = LedgerGroup.objects.filter(company=company, name__icontains="Expense").first()
            if not expense_grp:
                expense_grp = LedgerGroup.objects.create(
                    company=company,
                    name="Indirect Expenses",
                    nature="EXPENSE"
                )
            round_off = Ledger.objects.create(
                company=company,
                group=expense_grp,
                name="Round Off",
                ledger_type="ROUND_OFF"
            )
        return round_off
