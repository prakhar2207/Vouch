import datetime
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from apps.companies.models import Company
from apps.ledgers.models import Ledger, LedgerGroup
from apps.inventory.models import Product
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry, PaymentAllocation
from apps.accounting.services.sequence_service import InvoiceSequenceService
from apps.accounting.services.sales_service import SalesInvoiceService
from apps.accounting.services.purchase_service import PurchaseInvoiceService

class CreditDebitNoteService:
    @staticmethod
    def _resolve_sales_return_ledger(company: Company) -> Ledger:
        ledger = Ledger.objects.filter(company=company, name__icontains='Sales Return').first()
        if not ledger:
            ledger = Ledger.objects.filter(company=company, ledger_type='SALES').first() or \
                     Ledger.objects.filter(company=company, name__icontains='Sales').first()
        if not ledger:
            income_grp, _ = LedgerGroup.objects.get_or_create(company=company, name='Sales Accounts', defaults={'nature': 'INCOME'})
            ledger, _ = Ledger.objects.get_or_create(company=company, name='Sales Return Account', defaults={'group': income_grp, 'ledger_type': 'SALES'})
        return ledger

    @staticmethod
    def _resolve_purchase_return_ledger(company: Company) -> Ledger:
        ledger = Ledger.objects.filter(company=company, name__icontains='Purchase Return').first()
        if not ledger:
            ledger = Ledger.objects.filter(company=company, ledger_type='PURCHASE').first() or \
                     Ledger.objects.filter(company=company, name__icontains='Purchase').first()
        if not ledger:
            exp_grp, _ = LedgerGroup.objects.get_or_create(company=company, name='Purchase Accounts', defaults={'nature': 'EXPENSE'})
            ledger, _ = Ledger.objects.get_or_create(company=company, name='Purchase Return Account', defaults={'group': exp_grp, 'ledger_type': 'PURCHASE'})
        return ledger

    @classmethod
    @transaction.atomic
    def generate_credit_note(
        cls,
        company: Company,
        user,
        party_ledger: Ledger,
        items_data: list,
        reason: str = "Sales Return",
        original_invoice_number: str = None,
        voucher_date = None,
        narration: str = ""
    ) -> Voucher:
        """
        Creates and generates double-entry entries for a Credit Note (Customer Return / Discount).
        Accounting:
          Dr Sales Return Account (Taxable)
          Dr Output CGST / SGST / IGST (Reversing Output Tax)
          Cr Party Ledger (Total Gross)
        """
        v_date = voucher_date or timezone.now().date()
        if isinstance(v_date, str):
            v_date = datetime.date.fromisoformat(v_date.split('T')[0])

        seq_num, fy = InvoiceSequenceService.get_next_number(company, 'CREDIT_NOTE', v_date)

        voucher = Voucher.objects.create(
            company=company,
            financial_year=fy,
            voucher_type='CREDIT_NOTE',
            voucher_number=seq_num,
            reference_number=original_invoice_number or "",
            voucher_date=v_date,
            party_ledger=party_ledger,
            status='DRAFT',
            total_amount=Decimal('0.00'),
            narration=narration or f"Credit Note: {reason}" + (f" against {original_invoice_number}" if original_invoice_number else ""),
            created_by=user
        )

        company_state = (company.state_code or '09').zfill(2)
        party_state = (party_ledger.state_code if party_ledger else company_state) or company_state
        is_intra = (party_state == company_state)

        total_taxable = Decimal('0.00')
        total_cgst = Decimal('0.00')
        total_sgst = Decimal('0.00')
        total_igst = Decimal('0.00')
        total_gross = Decimal('0.00')

        for item_dict in items_data:
            product_id = item_dict.get('product_id') or item_dict.get('id')
            product = Product.objects.get(id=product_id, company=company)
            qty = Decimal(str(item_dict.get('quantity', 1)))
            rate = Decimal(str(item_dict.get('rate', product.selling_price or 0)))
            disc_pct = Decimal(str(item_dict.get('discount_percent', 0)))

            gross_line = qty * rate
            disc_amt = (gross_line * disc_pct / Decimal('100')).quantize(Decimal('0.01'))
            taxable = gross_line - disc_amt
            gst_rate = Decimal(str(item_dict.get('gst_rate', product.gst_rate or 18)))

            if is_intra:
                cgst_rate = (gst_rate / Decimal('2')).quantize(Decimal('0.01'))
                sgst_rate = cgst_rate
                igst_rate = Decimal('0.00')
                cgst_amt = (taxable * cgst_rate / Decimal('100')).quantize(Decimal('0.01'))
                sgst_amt = (taxable * sgst_rate / Decimal('100')).quantize(Decimal('0.01'))
                igst_amt = Decimal('0.00')
            else:
                cgst_rate = Decimal('0.00')
                sgst_rate = Decimal('0.00')
                igst_rate = gst_rate
                cgst_amt = Decimal('0.00')
                sgst_amt = Decimal('0.00')
                igst_amt = (taxable * igst_rate / Decimal('100')).quantize(Decimal('0.01'))

            line_tot = taxable + cgst_amt + sgst_amt + igst_amt

            VoucherItem.objects.create(
                voucher=voucher,
                product=product,
                quantity=qty,
                rate=rate,
                discount_percent=disc_pct,
                discount_amount=disc_amt,
                taxable_amount=taxable,
                gst_rate=gst_rate,
                cgst_rate=cgst_rate,
                sgst_rate=sgst_rate,
                igst_rate=igst_rate,
                cgst_amount=cgst_amt,
                sgst_amount=sgst_amt,
                igst_amount=igst_amt,
                hsn_code=product.hsn_code or "8483",
                total_amount=line_tot
            )

            total_taxable += taxable
            total_cgst += cgst_amt
            total_sgst += sgst_amt
            total_igst += igst_amt
            total_gross += line_tot

        voucher.total_amount = total_gross
        voucher.save(update_fields=['total_amount'])

        # Double-entry Accounting
        sales_ret_ledger = cls._resolve_sales_return_ledger(company)
        cgst_ledger = SalesInvoiceService._get_or_create_output_tax_ledger(company, 'CGST')
        sgst_ledger = SalesInvoiceService._get_or_create_output_tax_ledger(company, 'SGST')
        igst_ledger = SalesInvoiceService._get_or_create_output_tax_ledger(company, 'IGST')

        # 1. Debit Sales Return
        LedgerEntry.objects.create(
            voucher=voucher,
            company=company,
            ledger=sales_ret_ledger,
            debit_amount=total_taxable,
            credit_amount=Decimal('0.00'),
            narration=f"Sales return reversal for CN {voucher.voucher_number}"
        )

        # 2. Debit Output Taxes (Reversal of liability)
        if total_cgst > 0:
            LedgerEntry.objects.create(
                voucher=voucher,
                company=company,
                ledger=cgst_ledger,
                debit_amount=total_cgst,
                credit_amount=Decimal('0.00'),
                narration=f"Output CGST reversal for CN {voucher.voucher_number}"
            )
        if total_sgst > 0:
            LedgerEntry.objects.create(
                voucher=voucher,
                company=company,
                ledger=sgst_ledger,
                debit_amount=total_sgst,
                credit_amount=Decimal('0.00'),
                narration=f"Output SGST reversal for CN {voucher.voucher_number}"
            )
        if total_igst > 0:
            LedgerEntry.objects.create(
                voucher=voucher,
                company=company,
                ledger=igst_ledger,
                debit_amount=total_igst,
                credit_amount=Decimal('0.00'),
                narration=f"Output IGST reversal for CN {voucher.voucher_number}"
            )

        # 3. Credit Party Ledger (Reduces customer receivable)
        if party_ledger:
            LedgerEntry.objects.create(
                voucher=voucher,
                company=company,
                ledger=party_ledger,
                debit_amount=Decimal('0.00'),
                credit_amount=total_gross,
                narration=f"Credit Note credit to {party_ledger.name}"
            )

        return voucher

    @classmethod
    @transaction.atomic
    def generate_debit_note(
        cls,
        company: Company,
        user,
        party_ledger: Ledger,
        items_data: list,
        reason: str = "Purchase Return",
        original_invoice_number: str = None,
        voucher_date = None,
        narration: str = ""
    ) -> Voucher:
        """
        Creates and generates double-entry entries for a Debit Note (Supplier Return / Deduction).
        Accounting:
          Dr Party Ledger (Total Gross - reduces supplier payable)
          Cr Purchase Return Account (Taxable)
          Cr Input CGST / SGST / IGST (Reversing Input Tax)
        """
        v_date = voucher_date or timezone.now().date()
        if isinstance(v_date, str):
            v_date = datetime.date.fromisoformat(v_date.split('T')[0])

        seq_num, fy = InvoiceSequenceService.get_next_number(company, 'DEBIT_NOTE', v_date)

        voucher = Voucher.objects.create(
            company=company,
            financial_year=fy,
            voucher_type='DEBIT_NOTE',
            voucher_number=seq_num,
            reference_number=original_invoice_number or "",
            voucher_date=v_date,
            party_ledger=party_ledger,
            status='DRAFT',
            total_amount=Decimal('0.00'),
            narration=narration or f"Debit Note: {reason}" + (f" against {original_invoice_number}" if original_invoice_number else ""),
            created_by=user
        )

        company_state = (company.state_code or '09').zfill(2)
        party_state = (party_ledger.state_code if party_ledger else company_state) or company_state
        is_intra = (party_state == company_state)

        total_taxable = Decimal('0.00')
        total_cgst = Decimal('0.00')
        total_sgst = Decimal('0.00')
        total_igst = Decimal('0.00')
        total_gross = Decimal('0.00')

        for item_dict in items_data:
            product_id = item_dict.get('product_id') or item_dict.get('id')
            product = Product.objects.get(id=product_id, company=company)
            qty = Decimal(str(item_dict.get('quantity', 1)))
            rate = Decimal(str(item_dict.get('rate', product.selling_price or 0)))
            disc_pct = Decimal(str(item_dict.get('discount_percent', 0)))

            gross_line = qty * rate
            disc_amt = (gross_line * disc_pct / Decimal('100')).quantize(Decimal('0.01'))
            taxable = gross_line - disc_amt
            gst_rate = Decimal(str(item_dict.get('gst_rate', product.gst_rate or 18)))

            if is_intra:
                cgst_rate = (gst_rate / Decimal('2')).quantize(Decimal('0.01'))
                sgst_rate = cgst_rate
                igst_rate = Decimal('0.00')
                cgst_amt = (taxable * cgst_rate / Decimal('100')).quantize(Decimal('0.01'))
                sgst_amt = (taxable * sgst_rate / Decimal('100')).quantize(Decimal('0.01'))
                igst_amt = Decimal('0.00')
            else:
                cgst_rate = Decimal('0.00')
                sgst_rate = Decimal('0.00')
                igst_rate = gst_rate
                cgst_amt = Decimal('0.00')
                sgst_amt = Decimal('0.00')
                igst_amt = (taxable * igst_rate / Decimal('100')).quantize(Decimal('0.01'))

            line_tot = taxable + cgst_amt + sgst_amt + igst_amt

            VoucherItem.objects.create(
                voucher=voucher,
                product=product,
                quantity=qty,
                rate=rate,
                discount_percent=disc_pct,
                discount_amount=disc_amt,
                taxable_amount=taxable,
                gst_rate=gst_rate,
                cgst_rate=cgst_rate,
                sgst_rate=sgst_rate,
                igst_rate=igst_rate,
                cgst_amount=cgst_amt,
                sgst_amount=sgst_amt,
                igst_amount=igst_amt,
                hsn_code=product.hsn_code or "8483",
                total_amount=line_tot
            )

            total_taxable += taxable
            total_cgst += cgst_amt
            total_sgst += sgst_amt
            total_igst += igst_amt
            total_gross += line_tot

        voucher.total_amount = total_gross
        voucher.save(update_fields=['total_amount'])

        # Double-entry Accounting
        pur_ret_ledger = cls._resolve_purchase_return_ledger(company)
        input_cgst = PurchaseInvoiceService._get_or_create_input_tax_ledger(company, 'CGST')
        input_sgst = PurchaseInvoiceService._get_or_create_input_tax_ledger(company, 'SGST')
        input_igst = PurchaseInvoiceService._get_or_create_input_tax_ledger(company, 'IGST')

        # 1. Debit Party Ledger (Reduces supplier payable)
        if party_ledger:
            LedgerEntry.objects.create(
                voucher=voucher,
                company=company,
                ledger=party_ledger,
                debit_amount=total_gross,
                credit_amount=Decimal('0.00'),
                narration=f"Debit Note charge to {party_ledger.name}"
            )

        # 2. Credit Purchase Return
        LedgerEntry.objects.create(
            voucher=voucher,
            company=company,
            ledger=pur_ret_ledger,
            debit_amount=Decimal('0.00'),
            credit_amount=total_taxable,
            narration=f"Purchase return reversal for DN {voucher.voucher_number}"
        )

        # 3. Credit Input Taxes (Reversal of Input Tax Credit)
        if total_cgst > 0:
            LedgerEntry.objects.create(
                voucher=voucher,
                company=company,
                ledger=input_cgst,
                debit_amount=Decimal('0.00'),
                credit_amount=total_cgst,
                narration=f"Input CGST reversal for DN {voucher.voucher_number}"
            )
        if total_sgst > 0:
            LedgerEntry.objects.create(
                voucher=voucher,
                company=company,
                ledger=input_sgst,
                debit_amount=Decimal('0.00'),
                credit_amount=total_sgst,
                narration=f"Input SGST reversal for DN {voucher.voucher_number}"
            )
        if total_igst > 0:
            LedgerEntry.objects.create(
                voucher=voucher,
                company=company,
                ledger=input_igst,
                debit_amount=Decimal('0.00'),
                credit_amount=total_igst,
                narration=f"Input IGST reversal for DN {voucher.voucher_number}"
            )

        return voucher
