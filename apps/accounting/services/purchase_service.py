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
    def generate_purchase_invoice(
        company: Company, 
        user, 
        party_ledger: Ledger, 
        items_data: list, 
        purchase_ledger: Ledger, 
        input_cgst_ledger: Ledger, 
        input_sgst_ledger: Ledger, 
        input_igst_ledger: Ledger, 
        supplier_invoice_number: str = None, 
        voucher_date=None,
        cartage_amount: Decimal = Decimal('0.00'),
        cartage_ledger: Ledger = None
    ):
        """
        End-to-End orchestration of a Purchase Invoice.
        """
        # 0. Safeguard: Ensure tax ledgers are strictly INPUT tax ledgers (never Output)
        if not input_cgst_ledger or 'output' in input_cgst_ledger.name.lower():
            input_cgst_ledger = PurchaseInvoiceService._get_or_create_input_tax_ledger(company, 'CGST')
        if not input_sgst_ledger or 'output' in input_sgst_ledger.name.lower():
            input_sgst_ledger = PurchaseInvoiceService._get_or_create_input_tax_ledger(company, 'SGST')
        if not input_igst_ledger or 'output' in input_igst_ledger.name.lower():
            input_igst_ledger = PurchaseInvoiceService._get_or_create_input_tax_ledger(company, 'IGST')

        # 1. Create Voucher Header
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
                raw_name = str(item.get('product_name') or item.get('name') or 'Unnamed Product').strip()
                from apps.inventory.models import ProductCategory
                from apps.inventory.services.normalization_service import normalize_product_name, get_canonical_key, strip_category_prefix
                import uuid

                category = None
                category_id = item.get('category_id')
                category_name = item.get('category_name')

                if category_id and str(category_id).strip():
                    try:
                        category = ProductCategory.objects.filter(id=category_id, company=company).first()
                    except Exception:
                        pass
                elif category_name and str(category_name).strip():
                    category = ProductCategory.objects.filter(name__iexact=str(category_name).strip(), company=company).first()
                    if not category:
                        category = ProductCategory.objects.create(
                            company=company,
                            name=str(category_name).strip(),
                            hsn_code=item.get('hsn_code', ''),
                            gst_rate=Decimal(str(item.get('gst_rate', '18.00')))
                        )

                cat_name = category.name if category else None
                name = normalize_product_name(raw_name, cat_name)
                canon_key = get_canonical_key(raw_name, cat_name)
                sku = item.get('sku', name.upper()[:3] + '-' + str(uuid.uuid4())[:6])
                
                defaults_dict = {
                    'sku': sku,
                    'hsn_code': item.get('hsn_code', ''),
                    'gst_rate': Decimal(str(item.get('gst_rate', '18.00'))),
                    'purchase_price': Decimal(str(item.get('rate', '0.00'))),
                    'unit': item.get('unit', 'PCS')
                }
                
                if category:
                    defaults_dict['category'] = category
                    if not defaults_dict.get('hsn_code'):
                        defaults_dict['hsn_code'] = category.hsn_code
                    if 'gst_rate' not in defaults_dict or defaults_dict['gst_rate'] == 0:
                        defaults_dict['gst_rate'] = category.gst_rate

                item_brand = (item.get('brand') or '').strip()

                if item_brand:
                    product = Product.objects.filter(
                        company=company,
                        name__iexact=name,
                        brand__iexact=item_brand
                    ).first()
                    if not product:
                        # Check canonical key match (e.g. matching existing 'A 31' when bill has 'A-31')
                        all_brand_prods = Product.objects.filter(company=company, brand__iexact=item_brand)
                        for p in all_brand_prods:
                            if get_canonical_key(p.name, p.category.name if p.category else cat_name) == canon_key:
                                product = p
                                if p.name != name:
                                    p.name = name
                                    p.save(update_fields=['name'])
                                break

                    if not product:
                        defaults_dict['brand'] = item_brand
                        defaults_dict['purchase_price_from_invoice'] = True
                        product = Product.objects.create(
                            company=company,
                            name=name,
                            **defaults_dict
                        )
                        created = True
                    else:
                        created = False
                else:
                    # No brand mentioned in purchase bill -> Do NOT touch branded products!
                    # Target or create an unbranded product variant
                    product = Product.objects.filter(
                        company=company,
                        name__iexact=name,
                        brand__in=["", None, "Unbranded", "Generic"]
                    ).first()
                    if not product:
                        unbranded_prods = Product.objects.filter(company=company, brand__in=["", None, "Unbranded", "Generic"])
                        for p in unbranded_prods:
                            if get_canonical_key(p.name, p.category.name if p.category else cat_name) == canon_key:
                                product = p
                                if p.name != name:
                                    p.name = name
                                    p.save(update_fields=['name'])
                                break

                    if not product:
                        # If an existing branded item exists with this name, inherit its category
                        existing_sibling = Product.objects.filter(company=company, name__iexact=name).first()
                        if existing_sibling and existing_sibling.category:
                            defaults_dict['category'] = existing_sibling.category
                        defaults_dict['brand'] = ""
                        defaults_dict['purchase_price_from_invoice'] = True
                        product = Product.objects.create(
                            company=company,
                            name=name,
                            **defaults_dict
                        )
                        created = True
                    else:
                        created = False

                if not created and not product.category and category:
                    product.category = category
                    product.save(update_fields=['category'])

            qty = Decimal(str(item['quantity']))
            unit_str = str(item.get('unit') or getattr(product, 'unit', 'PCS') or 'PCS').strip().upper()
            fractional_units = ['KG', 'KGS', 'KILOGRAM', 'KILOGRAMS', 'LTR', 'LTRS', 'LITRE', 'LITRES', 'LITER', 'LITERS', 'MTR', 'MTRS', 'METER', 'METERS', 'METRE', 'METRES']
            if unit_str not in fractional_units:
                qty = Decimal(str(int(round(float(qty)))))
            rate = Decimal(str(item['rate']))

            discount_pct = Decimal(str(item.get('discount_percent', '0.00')))
            
            # Update product purchase price to latest purchase rate from invoice (net of discount)
            net_rate = (rate * (Decimal('100') - discount_pct) / Decimal('100')).quantize(Decimal('0.01'))
            if net_rate > Decimal('0.00'):
                product.purchase_price = net_rate
                product.purchase_price_from_invoice = True
                product.save(update_fields=['purchase_price', 'purchase_price_from_invoice'])
            
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
            
        # Add Cartage (Freight Inward) if specified
        try:
            cartage_amt = Decimal(str(cartage_amount or '0.00')).quantize(Decimal('0.01'))
        except Exception:
            cartage_amt = Decimal('0.00')

        # Round Off calculation:
        # If decimal value < 0.5 then floor, if >= 0.5 then ceiling
        unrounded_total = total_invoice_value + cartage_amt
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
        # Credit the Supplier (Party) with rounded total payable amount
        LedgerEntry.objects.create(
            voucher=voucher,
            ledger=party_ledger,
            debit_amount=Decimal('0.00'),
            credit_amount=rounded_total
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

        # Debit Cartage / Freight Inward entry (Direct Expenses)
        if cartage_amt > Decimal('0.00'):
            if not cartage_ledger:
                cartage_ledger = PurchaseInvoiceService._get_or_create_cartage_ledger(company, 'INWARD')
            LedgerEntry.objects.create(
                voucher=voucher,
                ledger=cartage_ledger,
                debit_amount=cartage_amt,
                credit_amount=Decimal('0.00')
            )

        # Round Off balancing entry for Purchase:
        # If round_off < 0: Debits (purchase + taxes + cartage = unrounded) > Credits (party = rounded).
        # Need CREDIT of abs(round_off) to Round Off ledger (Income/Discount received).
        # If round_off > 0: Debits (purchase + taxes + cartage = unrounded) < Credits (party = rounded).
        # Need DEBIT of round_off to Round Off ledger (Expense).
        if round_off != Decimal('0.00'):
            round_off_ledger = PurchaseInvoiceService._get_or_create_round_off_ledger(company)
            if round_off > Decimal('0.00'):
                LedgerEntry.objects.create(
                    voucher=voucher,
                    ledger=round_off_ledger,
                    debit_amount=round_off,
                    credit_amount=Decimal('0.00')
                )
            else:
                LedgerEntry.objects.create(
                    voucher=voucher,
                    ledger=round_off_ledger,
                    debit_amount=Decimal('0.00'),
                    credit_amount=abs(round_off)
                )
            
        return voucher

    @staticmethod
    def _get_or_create_cartage_ledger(company: Company, direction: str = 'INWARD') -> Ledger:
        from apps.ledgers.models import LedgerGroup
        if direction.upper() == 'INWARD':
            group_name = "Direct Expenses"
            ledger_name = "Cartage Inward"
        else:
            group_name = "Indirect Expenses"
            ledger_name = "Cartage Outward"

        grp = LedgerGroup.objects.filter(company=company, name__iexact=group_name).first()
        if not grp:
            grp, _ = LedgerGroup.objects.get_or_create(
                company=company,
                name=group_name,
                defaults={"nature": "EXPENSE"}
            )

        cartage = Ledger.objects.filter(company=company, name__iexact=ledger_name).first()
        if not cartage:
            cartage = Ledger.objects.filter(company=company, name__icontains="cartage inward").first() or \
                      Ledger.objects.filter(company=company, name__icontains="freight inward").first()
        if not cartage:
            cartage = Ledger.objects.create(
                company=company,
                group=grp,
                name=ledger_name,
                ledger_type="EXPENSE"
            )
        return cartage

    @staticmethod
    def _get_or_create_round_off_ledger(company: Company) -> Ledger:
        from apps.ledgers.models import LedgerGroup
        indirect_grp = LedgerGroup.objects.filter(company=company, name__iexact="Indirect Expenses").first() or \
                       LedgerGroup.objects.filter(company=company, name__icontains="Indirect Expense").first()
        if not indirect_grp:
            indirect_grp, _ = LedgerGroup.objects.get_or_create(
                company=company,
                name="Indirect Expenses",
                defaults={"nature": "EXPENSE"}
            )

        round_off = Ledger.objects.filter(company=company, name__iexact="Round Off").first()
        if not round_off:
            round_off = Ledger.objects.create(
                company=company,
                group=indirect_grp,
                name="Round Off",
                ledger_type="ROUND_OFF"
            )
        elif round_off.group_id != indirect_grp.id:
            # Self-healing: if Round Off was previously assigned to Purchase Accounts, reassign to Indirect Expenses
            round_off.group = indirect_grp
            round_off.save(update_fields=['group'])

        return round_off

    @staticmethod
    def _get_or_create_input_tax_ledger(company: Company, tax_type: str) -> Ledger:
        """
        Safely gets or creates the Input tax ledger for PURCHASES.
        tax_type: 'CGST', 'SGST', or 'IGST'
        Guarantees:
        - NEVER matches an 'Output' ledger.
        - Checks for exact 'Input <tax_type>' or '<tax_type> Input'.
        - If neither exists, creates 'Input <tax_type>' under 'Duties & Taxes' (LIABILITY).
        """
        from apps.ledgers.models import LedgerGroup
        tax_grp, _ = LedgerGroup.objects.get_or_create(
            company=company,
            name='Duties & Taxes',
            defaults={'nature': 'LIABILITY'}
        )
        target_name = f"Input {tax_type.upper()}"
        ledger = Ledger.objects.filter(company=company, name__iexact=target_name).first()
        if not ledger:
            ledger = Ledger.objects.filter(company=company, name__iexact=f"{tax_type.upper()} Input").first()
        if not ledger:
            ledger = Ledger.objects.get_or_create(
                company=company,
                name=target_name,
                defaults={'group': tax_grp, 'ledger_type': 'TAX'}
            )[0]
        return ledger
