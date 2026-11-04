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
                gstin=party_gstin.strip().upper()[:15] if party_gstin else "",
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
    def preflight_semantic_mappings(
        company: Company,
        canonical_tx: CanonicalTransaction
    ) -> Dict[str, Any]:
        """
        Executes semantic mapping preflight in an isolated atomic transaction.
        When company is BUYER (receiving foreign items):
            Checks and enforces EntityMapping approval states (PENDING, APPROVED, REJECTED).
            Persists ambiguous mappings durably as PENDING before attempting voucher creation.
        When company is SELLER:
            Resolves seller's own catalog items without foreign semantic mapping.
        Returns:
            {"status": "READY", "resolved_items": {...}} if all items are approved/resolved
            {"status": "AWAITING_APPROVAL", "pending_mappings": [...]} if any item needs human review
            {"status": "MAPPING_REJECTED", "error": "..."} if any item mapping was rejected
            {"status": "REVALIDATION_FAILED", "error": "..."} if an approved mapping targets a missing product
        """
        from .models import EntityMapping
        from .mapping import SemanticMappingEngine, MappingConfidence, ApprovalState

        is_seller = (
            canonical_tx.source_entity.identity_value == company.gstin or 
            canonical_tx.source_entity.name.strip().lower() == company.name.strip().lower()
        )

        source_id = str(canonical_tx.source_entity.identity_value or canonical_tx.source_entity.name or '').strip()
        dest_candidates = [str(company.id)]
        if company.gstin:
            dest_candidates.append(company.gstin.strip())

        with transaction.atomic():
            local_catalog = list(Product.objects.filter(company=company).values('id', 'name', 'sku', 'hsn_code', 'unit', 'gst_rate'))
            pending_mappings = []
            resolved_items = {}

            for idx, line in enumerate(canonical_tx.items):
                line_key = line.line_id or f"ITEM_{idx}_{line.sku}"

                # SELLER logic: Seller is selling its own goods; no foreign mapping needed
                if is_seller:
                    prod = Product.objects.filter(company=company, sku__iexact=line.sku).first()
                    if not prod:
                        prod = Product.objects.filter(company=company, name__iexact=line.name).first()
                    if prod:
                        resolved_items[line_key] = {
                            "product_id": prod.id,
                            "conversion_multiplier": Decimal('1.0'),
                            "mapping": None,
                            "needs_provisioning": False
                        }
                    else:
                        resolved_items[line_key] = {
                            "product_id": None,
                            "conversion_multiplier": Decimal('1.0'),
                            "mapping": None,
                            "needs_provisioning": True
                        }
                    continue

                # BUYER logic: Receiving foreign seller SKUs -> Enforce semantic mapping pipeline
                # Tier 1: Check existing EntityMapping in DB for this Buyer
                existing_mapping = EntityMapping.objects.filter(
                    source_company_id=source_id,
                    destination_company_id__in=dest_candidates,
                    foreign_sku=line.sku
                ).order_by('-mapping_version').first()

                if existing_mapping:
                    if existing_mapping.approval_state == ApprovalState.REJECTED.value:
                        reason = existing_mapping.rejection_reason or "Mapping rejected by administrator."
                        return {
                            "status": "MAPPING_REJECTED",
                            "error": f"Product line '{line.sku}' mapping was rejected: {reason}",
                            "mapping_id": existing_mapping.mapping_id,
                            "rejection_reason": reason
                        }
                    elif existing_mapping.approval_state == ApprovalState.PENDING.value:
                        pending_mappings.append(existing_mapping)
                        continue
                    elif existing_mapping.approval_state == ApprovalState.APPROVED.value:
                        # Revalidate that local product entity still exists in the company's catalog
                        prod = Product.objects.filter(company=company, sku__iexact=existing_mapping.local_sku).first()
                        if not prod:
                            return {
                                "status": "REVALIDATION_FAILED",
                                "error": f"Approved mapping for '{line.sku}' targets local SKU '{existing_mapping.local_sku}' which does not exist in local inventory. Revalidation failed.",
                                "mapping_id": existing_mapping.mapping_id
                            }
                        mult = Decimal(str(existing_mapping.conversion_multiplier or 1.0))
                        resolved_items[line_key] = {
                            "product_id": prod.id,
                            "conversion_multiplier": mult,
                            "mapping": existing_mapping,
                            "needs_provisioning": False
                        }
                        continue

                # Tier 2: Exact match by local SKU or Name
                prod = Product.objects.filter(company=company, sku__iexact=line.sku).first()
                if not prod:
                    prod = Product.objects.filter(company=company, name__iexact=line.name).first()
                if prod:
                    resolved_items[line_key] = {
                        "product_id": prod.id,
                        "conversion_multiplier": Decimal('1.0'),
                        "mapping": None,
                        "needs_provisioning": False
                    }
                    continue

                # Tier 3: Semantic match (Levenshtein / Jaccard / HSN Token)
                if local_catalog:
                    semantic_res = SemanticMappingEngine.match_product(
                        foreign_sku=line.sku,
                        foreign_name=line.name,
                        foreign_hsn=line.hsn_code,
                        catalog_items=local_catalog
                    )
                    if semantic_res:
                        matched_item, score, confidence = semantic_res
                        if score >= 0.90:
                            prod = Product.objects.filter(company=company, id=matched_item['id']).first()
                            if prod:
                                dest_id = company.gstin or str(company.id)
                                map_obj, _ = EntityMapping.objects.get_or_create(
                                    source_company_id=source_id,
                                    destination_company_id=dest_id,
                                    foreign_sku=line.sku,
                                    mapping_version=1,
                                    defaults={
                                        "mapping_id": f"MAP-{uuid.uuid4().hex[:12].upper()}",
                                        "local_sku": prod.sku,
                                        "confidence_level": confidence.value,
                                        "approval_state": ApprovalState.APPROVED.value,
                                        "conversion_multiplier": 1.0,
                                        "hsn_override": line.hsn_code
                                    }
                                )
                                resolved_items[line_key] = {
                                    "product_id": prod.id,
                                    "conversion_multiplier": Decimal('1.0'),
                                    "mapping": map_obj,
                                    "needs_provisioning": False
                                }
                                continue
                        else:
                            # 0.70 <= score < 0.90: Ambiguous confidence!
                            dest_id = company.gstin or str(company.id)
                            map_obj, _ = EntityMapping.objects.get_or_create(
                                source_company_id=source_id,
                                destination_company_id=dest_id,
                                foreign_sku=line.sku,
                                mapping_version=1,
                                defaults={
                                    "mapping_id": f"MAP-{uuid.uuid4().hex[:12].upper()}",
                                    "local_sku": matched_item.get('sku', ''),
                                    "confidence_level": confidence.value,
                                    "approval_state": ApprovalState.PENDING.value,
                                    "conversion_multiplier": 1.0,
                                    "hsn_override": line.hsn_code
                                }
                            )
                            pending_mappings.append(map_obj)
                            continue

                # Tier 4: No match exists (< 0.70)
                # Auto-provisioning is permitted when no ambiguous candidate exists
                resolved_items[line_key] = {
                    "product_id": None,
                    "conversion_multiplier": Decimal('1.0'),
                    "mapping": None,
                    "needs_provisioning": True
                }

            if pending_mappings:
                return {
                    "status": "AWAITING_APPROVAL",
                    "pending_mappings": [
                        {
                            "mapping_id": m.mapping_id,
                            "source_company_id": m.source_company_id,
                            "destination_company_id": m.destination_company_id,
                            "foreign_sku": m.foreign_sku,
                            "suggested_local_sku": m.local_sku,
                            "mapping_version": m.mapping_version,
                            "confidence_level": m.confidence_level,
                            "approval_state": m.approval_state,
                            "conversion_multiplier": m.conversion_multiplier,
                            "hsn_override": m.hsn_override,
                            "created_at": m.created_at.isoformat() if m.created_at else None
                        }
                        for m in pending_mappings
                    ]
                }

            return {
                "status": "READY",
                "resolved_items": resolved_items
            }

    @staticmethod
    def execute_converged_accounting(
        company: Company,
        canonical_tx: CanonicalTransaction,
        converged_operations: List[AccountingOperation],
        user: Any = None
    ) -> Dict[str, Any]:
        """
        Executes the complete set of converged operations against Vouch's accounting engine:
        1. Identifies if the local enterprise is Seller (SALES) or Buyer (PURCHASE).
        2. Preflights semantic mappings: persists PENDING mappings durably before posting.
        3. Provisions or matches counterparty ledgers, products, and tax accounts.
        4. Creates and posts the primary Invoice Voucher via SalesInvoiceService / PurchaseInvoiceService.
        5. Sequentially executes subsequent compensating operations (Credit/Debit Notes, Payments).
        6. Returns audit trail of physical database records created.
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

        # Step 1: Preflight Semantic Mappings (commits PENDING records before any voucher writes)
        from .models import EntityMapping
        from .mapping import MappingConfidence, ApprovalState

        preflight = LedgerBridge.preflight_semantic_mappings(company=company, canonical_tx=canonical_tx)

        if preflight["status"] == "AWAITING_APPROVAL":
            logger.warning(
                f"LedgerBridge: Transaction {canonical_tx.transaction_id} is blocked awaiting approval for "
                f"{len(preflight['pending_mappings'])} pending semantic mappings."
            )
            return {
                "status": "AWAITING_APPROVAL",
                "company_id": str(company.id),
                "company_name": company.name,
                "transaction_id": canonical_tx.transaction_id,
                "pending_mappings": preflight["pending_mappings"],
                "message": "Transaction awaiting semantic mapping approval before vouchers can be posted."
            }

        if preflight["status"] == "MAPPING_REJECTED":
            raise LedgerBridgeError(preflight["error"])

        if preflight["status"] == "REVALIDATION_FAILED":
            raise LedgerBridgeError(preflight["error"])

        # Step 2: Atomic Voucher Posting and Financial Execution
        with transaction.atomic():
            # Concurrency barrier: Lock company row to serialize simultaneous bridge workers
            Company.objects.select_for_update().filter(id=company.id).first()

            # Re-check under row lock
            existing_exec = ProtocolBridgeExecution.objects.filter(
                idempotency_key=idempotency_key,
                status="SUCCESS"
            ).first()

            if existing_exec:
                logger.info(f"LedgerBridge: returning cached idempotent execution (post-lock) for {canonical_tx.transaction_id}")
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

            # 2. Match / Provision Products using Preflight Results
            source_id = str(canonical_tx.source_entity.identity_value or canonical_tx.source_entity.name or '').strip()
            dest_id = str(canonical_tx.destination_entity.identity_value or canonical_tx.destination_entity.name or '').strip()

            product_map: Dict[str, Product] = {}
            conversion_multipliers: Dict[str, Decimal] = {}
            items_data: List[Dict[str, Any]] = []

            resolved_items = preflight.get("resolved_items", {})

            for idx, line in enumerate(canonical_tx.items):
                line_key = line.line_id or f"ITEM_{idx}_{line.sku}"
                res_info = resolved_items.get(line_key, {})
                prod = None
                conversion_multiplier = res_info.get("conversion_multiplier", Decimal('1.0'))

                if res_info.get("product_id"):
                    prod = Product.objects.filter(company=company, id=res_info["product_id"]).first()

                if not prod and res_info.get("needs_provisioning"):
                    prod = Product.objects.filter(company=company, sku=line.sku).first()
                    if not prod:
                        prod, _ = Product.objects.get_or_create(
                            company=company,
                            sku=line.sku,
                            defaults={
                                "name": line.name,
                                "hsn_code": line.hsn_code,
                                "gst_rate": line.tax_rate_percent,
                                "unit": line.unit,
                                "selling_price": line.unit_price,
                                "purchase_price": line.unit_price
                            }
                        )
                    if not is_seller:
                        EntityMapping.objects.get_or_create(
                            source_company_id=source_id,
                            destination_company_id=dest_id,
                            foreign_sku=line.sku,
                            mapping_version=1,
                            defaults={
                                "mapping_id": f"MAP-{uuid.uuid4().hex[:12].upper()}",
                                "local_sku": prod.sku,
                                "confidence_level": MappingConfidence.MANUAL.value,
                                "approval_state": ApprovalState.APPROVED.value,
                                "conversion_multiplier": 1.0,
                                "hsn_override": line.hsn_code
                            }
                        )

                if not prod:
                    raise LedgerBridgeError(f"Failed to resolve product for line '{line.sku}'")

                product_map[line.line_id] = prod
                conversion_multipliers[line.line_id] = conversion_multiplier

                effective_qty = line.quantity * conversion_multiplier
                effective_rate = (line.unit_price / conversion_multiplier).quantize(Decimal('0.01')) if conversion_multiplier != Decimal('1.0') else line.unit_price

                items_data.append({
                    'product_id': prod.id,
                    'product_name': prod.name,
                    'quantity': effective_qty,
                    'rate': effective_rate,
                    'discount_percent': Decimal('0.00'),
                    'hsn_code': line.hsn_code,
                    'gst_rate': line.tax_rate_percent,
                    'unit': prod.unit or line.unit
                })

            posted_vouchers: List[Voucher] = []

            # 3. Create and Post Base Invoice Voucher using authoritative Vouch Invoice Services
            base_voucher = Voucher.objects.filter(
                company=company,
                voucher_type=voucher_type,
                external_invoice_number=canonical_tx.transaction_id
            ).first()

            if isinstance(canonical_tx.issued_at, (int, float)):
                from datetime import datetime
                v_date = datetime.fromtimestamp(canonical_tx.issued_at, tz=timezone.get_current_timezone()).date()
            elif hasattr(canonical_tx.issued_at, 'date'):
                v_date = canonical_tx.issued_at.date()
            elif isinstance(canonical_tx.issued_at, str):
                from django.utils.dateparse import parse_date, parse_datetime
                parsed_dt = parse_datetime(canonical_tx.issued_at)
                v_date = parsed_dt.date() if parsed_dt else (parse_date(canonical_tx.issued_at) or timezone.now().date())
            else:
                v_date = timezone.now().date()

            if not base_voucher:
                manual_num = None
                for op in converged_operations:
                    if op.payload and op.payload.get('voucher_number'):
                        manual_num = str(op.payload.get('voucher_number')).strip()
                        break

                if is_seller:
                    base_voucher = SalesInvoiceService.generate_sales_invoice(
                        company=company,
                        user=user,
                        party_ledger=party_ledger,
                        items_data=items_data,
                        manual_voucher_number=manual_num,
                        manual_voucher_date=v_date,
                        buyer_name=counterparty_entity.name if is_seller else None,
                        buyer_gstin=counterparty_entity.identity_value if is_seller else None,
                        buyer_state_code=counterparty_entity.state_code if is_seller else None,
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

            # Collect referenced rejection op IDs to prevent duplicate voucher creation
            relevant_reciprocal_type = OperationType.CREDIT_NOTE_ISSUED if is_seller else OperationType.DEBIT_NOTE_ISSUED
            referenced_rejections = {
                op.payload.get('reference_rejection_op')
                for op in converged_operations
                if op.operation_type == relevant_reciprocal_type
                and op.payload.get('reference_rejection_op')
            }

            # 4. Process Subsequent Compensating & Financial Operations in Causal Order
            for op in converged_operations:
                # If a reciprocal Credit/Debit Note exists for this rejection, let the reciprocal note create the voucher
                if op.operation_type == OperationType.ITEM_REJECTED and op.operation_id in referenced_rejections:
                    continue

                if op.operation_type in (OperationType.ITEM_REJECTED, OperationType.CREDIT_NOTE_ISSUED, OperationType.DEBIT_NOTE_ISSUED):
                    # Party role check: Seller posts CREDIT_NOTE; Buyer posts DEBIT_NOTE
                    if is_seller and op.operation_type == OperationType.DEBIT_NOTE_ISSUED:
                        continue
                    if not is_seller and op.operation_type == OperationType.CREDIT_NOTE_ISSUED:
                        continue

                    payload = op.payload
                    qty = Decimal(str(payload.get('quantity', 0)))
                    taxable = Decimal(str(payload.get('taxable_amount', 0)))
                    line_id = payload.get('line_id')
                    prod = product_map.get(line_id) or Product.objects.filter(company=company).first()
                    if not prod or qty <= 0:
                        continue

                    mult = conversion_multipliers.get(line_id, Decimal('1.0'))
                    effective_corr_qty = qty * mult
                    rate = (taxable / effective_corr_qty).quantize(Decimal('0.01')) if effective_corr_qty > 0 else taxable
                    corr_item_data = [{
                        'product_id': prod.id,
                        'quantity': effective_corr_qty,
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
                                logger.error(f"Payment allocation failure for voucher {pay_voucher.voucher_number}: {e}", exc_info=True)
                                PaymentAllocationService.record_allocation_task(
                                    company=company,
                                    payment_voucher=pay_voucher,
                                    preferred_invoice=base_voucher,
                                    status='FAILED',
                                    error=str(e)
                                )
                                pay_voucher.notes = f"ALLOCATION_PENDING: Auto-allocation failed ({str(e)[:150]}). Manual reconciliation required."
                                pay_voucher.save(update_fields=['notes'])
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
                logger.error(f"FATAL: ProtocolBridgeExecution persistence failed for {canonical_tx.transaction_id}: {e}", exc_info=True)
                raise LedgerBridgeError(
                    f"Protocol bridge atomicity violation: Failed to persist durable ProtocolBridgeExecution record ({e}). "
                    f"Rolling back complete converged transaction to prevent inconsistent distributed state."
                ) from e

            return {
                "status": "BRIDGE_SUCCESS",
                "company_id": str(company.id),
                "company_name": company.name,
                "role": "SELLER" if is_seller else "BUYER",
                "base_voucher_id": str(base_voucher.id) if base_voucher else None,
                "base_voucher_number": base_voucher.voucher_number if base_voucher else None,
                "posted_vouchers": posted_numbers,
                "vouchers_count": len(posted_vouchers)
            }
