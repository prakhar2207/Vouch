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
    def generate_sales_invoice(
        company: Company, 
        user, 
        party_ledger: Ledger, 
        items_data: list, 
        sales_ledger: Ledger = None, 
        cgst_ledger: Ledger = None, 
        sgst_ledger: Ledger = None, 
        igst_ledger: Ledger = None, 
        manual_voucher_number=None, 
        manual_voucher_date=None,
        buyer_name=None,
        buyer_address=None,
        buyer_gstin=None,
        buyer_state_code=None,
        buyer_phone=None,
        cartage_amount: Decimal = Decimal('0.00'),
        cartage_ledger: Ledger = None
    ):
        """
        End-to-End orchestration of a Sales Invoice.
        1. Calculates precise GST and discounts.
        2. Generates Voucher and VoucherItems (with optional ad-hoc buyer details).
        3. Generates the exact 5-way double-entry accounting strings.
        Returns the DRAFT voucher.
        """
        # 0. Safeguard: Ensure tax ledgers are strictly OUTPUT tax ledgers (never Input)
        if party_ledger and party_ledger.company_id != company.id:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(f"Party ledger '{party_ledger.name}' does not belong to company '{company.name}'.")
        if sales_ledger and sales_ledger.company_id != company.id:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(f"Sales ledger '{sales_ledger.name}' does not belong to company '{company.name}'.")

        if not sales_ledger:
            from apps.ledgers.models import LedgerGroup
            sales_ledger = Ledger.objects.filter(company=company, ledger_type='SALES').first() or \
                           Ledger.objects.filter(company=company, name__icontains='Sales').first()
            if not sales_ledger:
                income_grp, _ = LedgerGroup.objects.get_or_create(company=company, name='Sales Accounts', defaults={'nature': 'INCOME'})
                sales_ledger, _ = Ledger.objects.get_or_create(company=company, name='Sales Account', defaults={'group': income_grp, 'ledger_type': 'SALES'})

        if not cgst_ledger or 'input' in cgst_ledger.name.lower():
            cgst_ledger = SalesInvoiceService._get_or_create_output_tax_ledger(company, 'CGST')
        if not sgst_ledger or 'input' in sgst_ledger.name.lower():
            sgst_ledger = SalesInvoiceService._get_or_create_output_tax_ledger(company, 'SGST')
        if not igst_ledger or 'input' in igst_ledger.name.lower():
            igst_ledger = SalesInvoiceService._get_or_create_output_tax_ledger(company, 'IGST')

        # 1. Create Voucher Header
        from apps.accounting.services.sequence_service import InvoiceSequenceService
        v_date = manual_voucher_date if manual_voucher_date else timezone.now().date()
        if manual_voucher_number:
            v_num = manual_voucher_number
            fy = InvoiceSequenceService.get_or_create_active_fy(company, v_date)
        else:
            v_num, fy = InvoiceSequenceService.get_next_number(company, 'SALES', v_date)
        
        narration_text = f"Sales to {buyer_name} (Settlement: {party_ledger.name})" if buyer_name else f"Sales to {party_ledger.name}"
        
        voucher = Voucher.objects.create(
            company=company,
            financial_year=fy,
            voucher_type='SALES',
            voucher_number=v_num,
            voucher_date=v_date,
            party_ledger=party_ledger,
            buyer_name=buyer_name,
            buyer_address=buyer_address,
            buyer_gstin=buyer_gstin,
            buyer_state_code=buyer_state_code,
            buyer_phone=buyer_phone,
            status='DRAFT',
            created_by=user,
            narration=narration_text
        )
        
        total_invoice_value = Decimal('0.00')
        total_taxable_value = Decimal('0.00')
        total_cgst = Decimal('0.00')
        total_sgst = Decimal('0.00')
        total_igst = Decimal('0.00')
        
        for item in items_data:
            product = None
            product_id = item.get('product_id')
            if product_id and str(product_id).strip():
                from apps.common.tenant import get_company_product
                product = get_company_product(company, product_id)

            if not product:
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
                if category_id and str(category_id).strip():
                    from apps.inventory.models import ProductCategory
                    try:
                        category = ProductCategory.objects.filter(id=category_id, company=company).first()
                        if category:
                            defaults_dict['category'] = category
                            defaults_dict['hsn_code'] = category.hsn_code
                            defaults_dict['gst_rate'] = category.gst_rate
                    except Exception:
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
                
            # Only apply party's default discount if discount_percent is not provided in item
            if item.get('discount_percent') is None and party_ledger.discount_percent > Decimal('0.00'):
                discount_pct = party_ledger.discount_percent

            gross = qty * rate
            discount_amt = (gross * discount_pct / Decimal('100')).quantize(Decimal('0.01'))
            taxable_amount = gross - discount_amt
            
            # 2. Calculate GST
            target_party_state = party_ledger.state_code or buyer_state_code or company.state_code
            taxes = GSTCalculator.calculate_taxes(
                company_state_code=company.state_code,
                party_state_code=target_party_state,
                taxable_amount=taxable_amount,
                gst_rate=product.gst_rate
            )
            
            total_amount = taxable_amount + taxes['total_tax']
            
            # Create Voucher Item with complete historical tax snapshots
            from apps.inventory.models import Warehouse
            line_wh = None
            if item.get('warehouse_id'):
                line_wh = Warehouse.objects.filter(id=item['warehouse_id'], company=company).first()

            VoucherItem.objects.create(
                voucher=voucher,
                product=product,
                warehouse=line_wh,
                quantity=qty,
                rate=rate,
                discount_percent=discount_pct,
                discount_amount=discount_amt,
                taxable_amount=taxable_amount,
                gst_rate=product.gst_rate,
                cgst_rate=taxes.get('cgst_rate', Decimal('0.00')),
                sgst_rate=taxes.get('sgst_rate', Decimal('0.00')),
                igst_rate=taxes.get('igst_rate', Decimal('0.00')),
                cess_rate=taxes.get('cess_rate', Decimal('0.00')),
                cgst_amount=taxes.get('cgst', Decimal('0.00')),
                sgst_amount=taxes.get('sgst', Decimal('0.00')),
                igst_amount=taxes.get('igst', Decimal('0.00')),
                cess_amount=taxes.get('cess', Decimal('0.00')),
                hsn_code=product.hsn_code or item.get('hsn_code', ''),
                total_amount=total_amount
            )
            
            total_taxable_value += taxable_amount
            total_cgst += taxes['cgst']
            total_sgst += taxes['sgst']
            total_igst += taxes['igst']
            total_invoice_value += total_amount
            
        # Add Cartage (Freight Outward) if specified
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
        # If round_off < 0: Debits (party = rounded) < Credits (sales + taxes + cartage = unrounded).
        # Need DEBIT of abs(round_off) to Round Off ledger (Expense).
        # If round_off > 0: Debits (party = rounded) > Credits (sales + taxes + cartage = unrounded).
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

        # Cartage / Freight Outward entry (Credit Cartage Outward on Sales Invoice)
        if cartage_amt > Decimal('0.00'):
            if not cartage_ledger:
                cartage_ledger = SalesInvoiceService._get_or_create_cartage_ledger(company, 'OUTWARD')
            LedgerEntry.objects.create(
                voucher=voucher,
                ledger=cartage_ledger,
                debit_amount=Decimal('0.00'),
                credit_amount=cartage_amt
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
    def _get_or_create_cartage_ledger(company: Company, direction: str = 'OUTWARD') -> Ledger:
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
            cartage = Ledger.objects.filter(company=company, name__icontains="cartage").first() or \
                      Ledger.objects.filter(company=company, name__icontains="freight").first()
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
    def _get_or_create_output_tax_ledger(company: Company, tax_type: str) -> Ledger:
        """
        Safely gets or creates the Output tax ledger for SALES.
        tax_type: 'CGST', 'SGST', or 'IGST'
        Guarantees:
        - NEVER matches an 'Input' ledger.
        - Checks for exact 'Output <tax_type>' or '<tax_type> Output'.
        - If neither exists, creates 'Output <tax_type>' under 'Duties & Taxes' (LIABILITY).
        """
        from apps.ledgers.models import LedgerGroup
        tax_grp, _ = LedgerGroup.objects.get_or_create(
            company=company,
            name='Duties & Taxes',
            defaults={'nature': 'LIABILITY'}
        )
        target_name = f"Output {tax_type.upper()}"
        ledger = Ledger.objects.filter(company=company, name__iexact=target_name).first()
        if not ledger:
            ledger = Ledger.objects.filter(company=company, name__iexact=f"{tax_type.upper()} Output").first()
        if not ledger:
            ledger, _ = Ledger.objects.get_or_create(
                company=company,
                name=target_name,
                defaults={'group': tax_grp, 'ledger_type': 'TAX'}
            )
        return ledger

    @classmethod
    def reassign_misallocated_tax_entries(cls, company: Company = None):
        """
        Auto-heals and enforces strict GST tax separation:
        1. Any SALES voucher credit entry hitting an INPUT tax ledger or generic tax ledger
           is reassigned to the corresponding OUTPUT tax ledger.
        2. Any PURCHASE voucher debit entry hitting an OUTPUT tax ledger
           is reassigned to the corresponding INPUT tax ledger.
        3. Recalculates current_balance and LedgerBalance for all affected ledgers from scratch.
        """
        from apps.companies.models import Company as CompanyModel
        from apps.accounting.models import LedgerEntry, LedgerBalance
        from apps.accounting.services.purchase_service import PurchaseInvoiceService
        from decimal import Decimal

        companies = [company] if company else list(CompanyModel.objects.all())

        for comp in companies:
            # Fast-path check: do we have any misallocated entries in this company?
            misallocated_sales = LedgerEntry.objects.filter(
                voucher__company=comp,
                voucher__voucher_type='SALES',
                credit_amount__gt=0
            ).select_related('ledger')

            has_misallocated_sales = any(
                'INPUT' in (e.ledger.name or '').upper() or (e.ledger.name or '').strip().upper() in ['CGST', 'SGST', 'IGST']
                for e in misallocated_sales
            )

            misallocated_purchases = LedgerEntry.objects.filter(
                voucher__company=comp,
                voucher__voucher_type='PURCHASE',
                debit_amount__gt=0
            ).select_related('ledger')

            has_misallocated_purchases = any(
                'OUTPUT' in (e.ledger.name or '').upper()
                for e in misallocated_purchases
            )

            if not has_misallocated_sales and not has_misallocated_purchases:
                continue

            output_cgst = cls._get_or_create_output_tax_ledger(comp, 'CGST')
            output_sgst = cls._get_or_create_output_tax_ledger(comp, 'SGST')
            output_igst = cls._get_or_create_output_tax_ledger(comp, 'IGST')

            input_cgst = PurchaseInvoiceService._get_or_create_input_tax_ledger(comp, 'CGST')
            input_sgst = PurchaseInvoiceService._get_or_create_input_tax_ledger(comp, 'SGST')
            input_igst = PurchaseInvoiceService._get_or_create_input_tax_ledger(comp, 'IGST')

            affected_ledgers = set()

            # Fix Sales tax entries
            if has_misallocated_sales:
                for entry in misallocated_sales:
                    lname = (entry.ledger.name or '').strip().upper()
                    if 'INPUT' in lname or lname in ['CGST', 'SGST', 'IGST']:
                        affected_ledgers.add(entry.ledger)
                        if 'CGST' in lname:
                            entry.ledger = output_cgst
                            affected_ledgers.add(output_cgst)
                        elif 'SGST' in lname or 'UTGST' in lname:
                            entry.ledger = output_sgst
                            affected_ledgers.add(output_sgst)
                        elif 'IGST' in lname:
                            entry.ledger = output_igst
                            affected_ledgers.add(output_igst)
                        entry.save(update_fields=['ledger'])

            # Fix Purchase tax entries
            if has_misallocated_purchases:
                for entry in misallocated_purchases:
                    lname = (entry.ledger.name or '').strip().upper()
                    if 'OUTPUT' in lname:
                        affected_ledgers.add(entry.ledger)
                        if 'CGST' in lname:
                            entry.ledger = input_cgst
                            affected_ledgers.add(input_cgst)
                        elif 'SGST' in lname or 'UTGST' in lname:
                            entry.ledger = input_sgst
                            affected_ledgers.add(input_sgst)
                        elif 'IGST' in lname:
                            entry.ledger = input_igst
                            affected_ledgers.add(input_igst)
                        entry.save(update_fields=['ledger'])

            # Recalculate closing balances for all affected ledgers
            for ldr in affected_ledgers:
                op_balance = Decimal(str(ldr.opening_balance or '0.00'))
                entries = LedgerEntry.objects.filter(ledger=ldr, voucher__status='POSTED')
                total_dr = Decimal('0.00')
                total_cr = Decimal('0.00')
                for e in entries:
                    total_dr += Decimal(str(e.debit_amount or '0.00'))
                    total_cr += Decimal(str(e.credit_amount or '0.00'))

                if ldr.opening_balance_type == 'DEBIT':
                    ldr.current_balance = op_balance + total_dr - total_cr
                else:
                    ldr.current_balance = op_balance + total_cr - total_dr

                ldr.save(update_fields=['current_balance'])

                # Update LedgerBalance (FY level balances) if exists
                for lb in LedgerBalance.objects.filter(ledger=ldr).select_related('financial_year'):
                    fy = lb.financial_year
                    fy_entries = LedgerEntry.objects.filter(
                        ledger=ldr,
                        voucher__status='POSTED',
                        voucher__voucher_date__gte=fy.start_date,
                        voucher__voucher_date__lte=fy.end_date
                    )
                    fy_dr = Decimal('0.00')
                    fy_cr = Decimal('0.00')
                    for e in fy_entries:
                        fy_dr += Decimal(str(e.debit_amount or '0.00'))
                        fy_cr += Decimal(str(e.credit_amount or '0.00'))
                    
                    lb_op = Decimal(str(lb.opening_balance or '0.00'))
                    if lb.opening_type == 'DR':
                        net = lb_op + fy_dr - fy_cr
                        lb.closing_type = 'DR' if net >= 0 else 'CR'
                        lb.closing_balance = abs(net)
                    else:
                        net = lb_op + fy_cr - fy_dr
                        lb.closing_type = 'CR' if net >= 0 else 'DR'
                        lb.closing_balance = abs(net)
                    lb.save(update_fields=['closing_balance', 'closing_type'])

