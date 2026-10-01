import hashlib
import uuid
from decimal import Decimal
import logging
from typing import Dict, List, Any, Optional
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.companies.models import Company
from apps.ledgers.models import Ledger, LedgerGroup
from apps.inventory.models import Product, Warehouse
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry
from apps.accounting.services.voucher_service import VoucherService
from apps.accounting.services.sales_service import SalesInvoiceService
from apps.accounting.services.purchase_service import PurchaseInvoiceService
from apps.accounting.services.credit_debit_note_service import CreditDebitNoteService
from apps.accounting.services.sequence_service import InvoiceSequenceService
from apps.accounting.services.allocation_service import PaymentAllocationService
from apps.gst.services.gst_calculator import GSTCalculator

from .schema import CanonicalTransaction
from .operation import AccountingOperation, OperationType
from .models import ProtocolBridgeExecution

logger = logging.getLogger(__name__)

class LedgerBridgeError(Exception):
    """Raised when bridging protocol state to Vouch accounting engine fails."""
    pass

class LedgerBridge:
    """
    Vouch Accounting Ledger Bridge.
    Connects the converged distributed protocol state directly into Vouch's 
    production accounting engine, creating and posting actual Vouchers, LedgerEntries,
    Inventory movements, and GST liabilities.
    Enforces the golden rule: THE PROTOCOL PRODUCES CANONICAL OPERATIONS; 
    VOUCH'S AUTHORITATIVE ACCOUNTING ENGINE EXECUTES THEM.
    """

    @staticmethod
    def _get_or_create_party_ledger(company: Company, party_name: str, party_gstin: str, party_state: str, is_customer: bool) -> Ledger:
        group_name = "Sundry Debtors" if is_customer else "Sundry Creditors"
        nature = "ASSET" if is_customer else "LIABILITY"
        ledger_type = "CUSTOMER" if is_customer else "SUPPLIER"

        group, _ = LedgerGroup.objects.get_or_create(
            company=company,
            name=group_name,
            defaults={"nature": nature}
        )

        ledger = None
        if party_gstin:
            ledger = Ledger.objects.filter(company=company, gstin__iexact=party_gstin.strip()).first()
        if not ledger:
            ledger = Ledger.objects.filter(company=company, name__iexact=party_name.strip()).first()

        if not ledger:
            ledger = Ledger.objects.create(
                company=company,
                group=group,
                name=party_name.strip(),
                gstin=party_gstin.strip().upper() if party_gstin else "",
                state_code=party_state.strip() if party_state else "",
                ledger_type=ledger_type
            )
        return ledger

    @staticmethod
    def _get_or_create_bank_ledger(company: Company) -> Ledger:
        bank_grp, _ = LedgerGroup.objects.get_or_create(
            company=company, 
            name="Bank Accounts", 
            defaults={"nature": "ASSET"}
        )
        bank_ledger = Ledger.objects.filter(company=company, ledger_type='BANK').first() or \
                      Ledger.objects.filter(company=company, name__icontains='Bank').first() or \
                      Ledger.objects.filter(company=company, name__icontains='Cash').first()
        if not bank_ledger:
            bank_ledger = Ledger.objects.create(
                company=company,
                group=bank_grp,
                name="Bank Settlement Account",
                ledger_type="BANK"
            )
        return bank_ledger

    @staticmethod
    @transaction.atomic
    def execute_converged_accounting(
        company: Company,
        canonical_tx: CanonicalTransaction,
        converged_operations: List[AccountingOperation],
        user: Any = None
    ) -> Dict[str, Any]:
        """
        Executes the complete set of converged operations against Vouch's accounting engine:
        1. Identifies if the local enterprise is Seller (SALES) or Buyer (PURCHASE).
        2. Provisions or matches counterparty ledgers, products, and tax accounts.
        3. Creates and posts the primary Invoice Voucher via SalesInvoiceService / PurchaseInvoiceService.
        4. Sequentially executes subsequent compensating operations (Credit/Debit Notes, Payments).
        5. Returns audit trail of physical database records created.
        """
        is_seller = (canonical_tx.source_entity.identity_value == company.gstin or 
                     canonical_tx.source_entity.name.strip().lower() == company.name.strip().lower())

        voucher_type = 'SALES' if is_seller else 'PURCHASE'
        counterparty_entity = canonical_tx.destination_entity if is_seller else canonical_tx.source_entity

        # Idempotency Protection: H(company_id || tx_id || sorted_op_ids)
        sorted_op_ids = sorted([op.operation_id for op in converged_operations])
        idempotency_raw = f"{company.id}|{canonical_tx.transaction_id}|{sorted_op_ids}"
        idempotency_key = hashlib.sha256(idempotency_raw.encode('utf-8')).hexdigest()

        existing_exec = ProtocolBridgeExecution.objects.filter(
            idempotency_key=idempotency_key,
            status="SUCCESS"
        ).first()

        if existing_exec:
            logger.info(f"LedgerBridge: returning cached idempotent execution for {canonical_tx.transaction_id}")
            return {
                "status": "BRIDGE_SUCCESS",
                "idempotent_cached": True,
                "company_id": str(company.id),
                "company_name": company.name,
                "role": existing_exec.role,
                "base_voucher_number": existing_exec.base_voucher_number,
                "posted_vouchers": existing_exec.posted_vouchers,
                "vouchers_count": len(existing_exec.posted_vouchers)
            }

        # 0. Resolve created_by user
        if not user:
            from apps.accounts.models import User
            company_user = company.users.select_related('user').first()
            user = company_user.user if company_user else User.objects.first()

        # 1. Match / Provision Counterparty Ledger
        party_ledger = LedgerBridge._get_or_create_party_ledger(
            company=company,
            party_name=counterparty_entity.name,
            party_gstin=counterparty_entity.identity_value,
            party_state=counterparty_entity.state_code or "",
            is_customer=is_seller
        )

        # 2. Match / Provision Products
        product_map: Dict[str, Product] = {}
        items_data: List[Dict[str, Any]] = []

        for line in canonical_tx.items:
            prod = Product.objects.filter(company=company, sku__iexact=line.sku).first()
            if not prod:
                prod = Product.objects.filter(company=company, name__iexact=line.name).first()
            if not prod:
                prod = Product.objects.create(
                    company=company,
                    name=line.name,
                    sku=line.sku,
                    hsn_code=line.hsn_code,
                    gst_rate=line.tax_rate_percent,
                    unit=line.unit,
                    selling_price=line.unit_price,
                    purchase_price=line.unit_price
                )
            product_map[line.line_id] = prod
            items_data.append({
                'product_id': prod.id,
                'product_name': prod.name,
                'quantity': line.quantity,
                'rate': line.unit_price,
                'discount_percent': Decimal('0.00'),
                'hsn_code': line.hsn_code,
                'gst_rate': line.tax_rate_percent,
                'unit': line.unit
            })

        posted_vouchers: List[Voucher] = []

        # 3. Create and Post Base Invoice Voucher using authoritative Vouch Invoice Services
        base_voucher = Voucher.objects.filter(
            company=company,
            voucher_type=voucher_type,
            external_invoice_number=canonical_tx.transaction_id
        ).first()

        v_date = canonical_tx.issued_at.date() if canonical_tx.issued_at else timezone.now().date()

        if not base_voucher:
            if is_seller:
                base_voucher = SalesInvoiceService.generate_sales_invoice(
                    company=company,
                    user=user,
                    party_ledger=party_ledger,
                    items_data=items_data,
                    manual_voucher_date=v_date,
                    cartage_amount=canonical_tx.totals.shipping_charges
                )
            else:
                base_voucher = PurchaseInvoiceService.generate_purchase_invoice(
                    company=company,
                    user=user,
                    party_ledger=party_ledger,
                    items_data=items_data,
                    supplier_invoice_number=f"BILL-{canonical_tx.transaction_id[:12]}",
                    voucher_date=v_date,
                    cartage_amount=canonical_tx.totals.shipping_charges
                )

            base_voucher.external_invoice_number = canonical_tx.transaction_id
            base_voucher.save(update_fields=['external_invoice_number'])
            VoucherService.post_voucher(base_voucher, process_stock=True, force_duplicate=True)
            posted_vouchers.append(base_voucher)
        elif base_voucher.status != 'POSTED':
            VoucherService.post_voucher(base_voucher, process_stock=True, force_duplicate=True)
            posted_vouchers.append(base_voucher)

        # 4. Process Subsequent Compensating & Financial Operations in Causal Order
        for op in converged_operations:
            if op.operation_type in (OperationType.ITEM_REJECTED, OperationType.CREDIT_NOTE_ISSUED, OperationType.DEBIT_NOTE_ISSUED):
                payload = op.payload
                qty = Decimal(str(payload.get('quantity', 0)))
                taxable = Decimal(str(payload.get('taxable_amount', 0)))
                line_id = payload.get('line_id')
                prod = product_map.get(line_id) or Product.objects.filter(company=company).first()
                if not prod or qty <= 0:
                    continue

                rate = (taxable / qty).quantize(Decimal('0.01')) if qty > 0 else taxable
                corr_item_data = [{
                    'product_id': prod.id,
                    'quantity': qty,
                    'rate': rate,
                    'discount_percent': Decimal('0.00'),
                    'gst_rate': prod.gst_rate or Decimal('18.00'),
                    'hsn_code': prod.hsn_code
                }]

                corr_type = 'CREDIT_NOTE' if is_seller else 'DEBIT_NOTE'
                existing_corr = Voucher.objects.filter(
                    company=company,
                    voucher_type=corr_type,
                    reference_number__icontains=op.operation_id[:8]
                ).first()

                if not existing_corr:
                    if is_seller:
                        corr_voucher = CreditDebitNoteService.generate_credit_note(
                            company=company,
                            user=user,
                            party_ledger=party_ledger,
                            items_data=corr_item_data,
                            reason=f"Converged Compensation {op.operation_id}",
                            original_invoice_number=base_voucher.voucher_number,
                            voucher_date=timezone.now().date()
                        )
                    else:
                        corr_voucher = CreditDebitNoteService.generate_debit_note(
                            company=company,
                            user=user,
                            party_ledger=party_ledger,
                            items_data=corr_item_data,
                            reason=f"Converged Compensation {op.operation_id}",
                            original_invoice_number=base_voucher.voucher_number,
                            voucher_date=timezone.now().date()
                        )
                    corr_voucher.external_invoice_number = canonical_tx.transaction_id
                    corr_voucher.corrects_voucher = base_voucher
                    corr_voucher.save(update_fields=['external_invoice_number', 'corrects_voucher'])
                    VoucherService.post_voucher(corr_voucher, process_stock=True, force_duplicate=True)
                    posted_vouchers.append(corr_voucher)

            elif op.operation_type == OperationType.PAYMENT_ALLOCATED:
                pay_amt = Decimal(str(op.payload.get('amount', 0)))
                if pay_amt <= Decimal('0.00'):
                    continue

                pay_type = 'RECEIPT' if is_seller else 'PAYMENT'
                ref_num = f"PAY-{op.operation_id[:8]}"
                existing_pay = Voucher.objects.filter(
                    company=company,
                    voucher_type=pay_type,
                    reference_number=ref_num
                ).first()

                if not existing_pay:
                    bank_ledger = LedgerBridge._get_or_create_bank_ledger(company)
                    today = timezone.now().date()
                    seq_num, fy = InvoiceSequenceService.get_next_number(company, pay_type, today)
                    pay_voucher = Voucher.objects.create(
                        company=company,
                        financial_year=fy,
                        voucher_type=pay_type,
                        voucher_number=seq_num,
                        reference_number=ref_num,
                        external_invoice_number=canonical_tx.transaction_id,
                        voucher_date=today,
                        party_ledger=party_ledger,
                        total_amount=pay_amt,
                        status='DRAFT',
                        created_by=user,
                        narration=f"Converged settlement for {canonical_tx.transaction_id}"
                    )

                    if pay_type == 'RECEIPT':
                        # Debit Bank, Credit Party
                        LedgerEntry.objects.create(voucher=pay_voucher, company=company, ledger=bank_ledger, debit_amount=pay_amt, credit_amount=Decimal('0.00'), narration=f"Settlement from {party_ledger.name}")
                        LedgerEntry.objects.create(voucher=pay_voucher, company=company, ledger=party_ledger, debit_amount=Decimal('0.00'), credit_amount=pay_amt, narration=f"Settlement via {bank_ledger.name}")
                    else:
                        # Debit Party, Credit Bank
                        LedgerEntry.objects.create(voucher=pay_voucher, company=company, ledger=party_ledger, debit_amount=pay_amt, credit_amount=Decimal('0.00'), narration=f"Settlement to {party_ledger.name}")
                        LedgerEntry.objects.create(voucher=pay_voucher, company=company, ledger=bank_ledger, debit_amount=Decimal('0.00'), credit_amount=pay_amt, narration=f"Settlement via {bank_ledger.name}")

                    VoucherService.post_voucher(pay_voucher, process_stock=False, force_duplicate=True)
                    if base_voucher:
                        try:
                            PaymentAllocationService.auto_allocate_voucher(pay_voucher, preferred_invoice_id=str(base_voucher.id))
                        except Exception as e:
                            logger.warning(f"Payment allocation warning: {e}")
                    posted_vouchers.append(pay_voucher)

        posted_numbers = [v.voucher_number for v in posted_vouchers]
        try:
            ProtocolBridgeExecution.objects.create(
                execution_id=f"EXEC-{uuid.uuid4().hex[:12].upper()}",
                idempotency_key=idempotency_key,
                company_id=str(company.id),
                transaction_id=canonical_tx.transaction_id,
                role="SELLER" if is_seller else "BUYER",
                base_voucher_number=base_voucher.voucher_number if base_voucher else None,
                posted_vouchers=posted_numbers,
                status="SUCCESS"
            )
        except Exception as e:
            logger.warning(f"Could not persist ProtocolBridgeExecution audit: {e}")

        return {
            "status": "BRIDGE_SUCCESS",
            "company_id": str(company.id),
            "company_name": company.name,
            "role": "SELLER" if is_seller else "BUYER",
            "base_voucher_number": base_voucher.voucher_number if base_voucher else None,
            "posted_vouchers": posted_numbers,
            "vouchers_count": len(posted_vouchers)
        }
