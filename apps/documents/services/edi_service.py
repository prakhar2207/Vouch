import json
import hashlib
import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Dict, Optional

from django.db import transaction
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounting.models import Voucher, VoucherItem
from apps.accounting.services.sequence_service import InvoiceSequenceService
from apps.companies.models import Company
from apps.inventory.models import Product, ProductCategory
from apps.ledgers.models import Ledger, LedgerGroup
from apps.documents.capabilities import can_edi
from apps.documents.models import DocumentSnapshot, EDIDocument, EDIExchange, DocumentAuditEvent

logger = logging.getLogger(__name__)


class InvoiceEDIService:
    """
    Manages the B2B Invoice-Only EDI Handshake and "Add to my Vouch" flow.
    Enforces that statements, financial reports, and non-invoice documents
    are strictly rejected from EDI processing.
    """

    @classmethod
    def get_or_create_edi_document(cls, snapshot: DocumentSnapshot) -> EDIDocument:
        """
        Creates or retrieves the canonical EDIDocument from an invoice snapshot.
        Rejects non-invoice document types.
        """
        if not can_edi(snapshot.document_type):
            raise PermissionDenied(f"EDI import/export is strictly forbidden for document type '{snapshot.document_type}'.")

        existing = getattr(snapshot, 'edi_document', None)
        if existing:
            return existing

        dto = snapshot.snapshot_json
        seller = dto.get('seller', {})
        buyer = dto.get('buyer', {})
        doc = dto.get('document', {})

        receiver_gstin = (buyer.get('gstin') or '').strip().upper()
        if receiver_gstin == 'UNREGISTERED':
            receiver_gstin = ''

        payload = {
            'schema_version': '1.0',
            'sender_company_id': str(snapshot.company.id),
            'sender_name': seller.get('name', snapshot.company.name),
            'sender_legal_name': seller.get('legal_name', snapshot.company.legal_name),
            'sender_gstin': seller.get('gstin', snapshot.company.gstin),
            'sender_address': seller.get('address', snapshot.company.address),
            'sender_city': seller.get('city', snapshot.company.city),
            'sender_state_code': seller.get('state_code', snapshot.company.state_code),
            'sender_phone': seller.get('phone', snapshot.company.phone),
            'sender_email': seller.get('email', snapshot.company.email),
            'invoice_number': doc.get('document_number', snapshot.document_number),
            'invoice_date': doc.get('document_date', str(snapshot.document_date)),
            'receiver_gstin': receiver_gstin,
            'receiver_name': buyer.get('name', ''),
            'total_amount': float(snapshot.total_amount or 0.0),
            'items': dto.get('items', []),
            'subtotals': dto.get('subtotals', {}),
            'tax_breakdown': dto.get('tax_breakdown', []),
            'terms': dto.get('terms', []),
        }

        canonical_json = json.dumps(payload, sort_keys=True)
        payload_hash = hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()
        idempotency_key = f"{snapshot.company_id}:{snapshot.source_id or snapshot.id}"

        edi_doc, _ = EDIDocument.objects.get_or_create(
            document_snapshot=snapshot,
            defaults={
                'schema_version': '1.0',
                'sender_company': snapshot.company,
                'receiver_gstin': receiver_gstin,
                'payload': payload,
                'payload_hash': payload_hash,
                'idempotency_key': idempotency_key,
            }
        )
        return edi_doc

    @classmethod
    @transaction.atomic
    def import_invoice_to_buyer(
        cls,
        edi_doc: EDIDocument,
        buyer_company: Company,
        user,
    ) -> Dict[str, Any]:
        """
        Executes the "Add to my Vouch" handshake:
        1. Verifies document capability (strictly invoices only).
        2. Verifies receiver GSTIN against buyer company GSTIN.
        3. Prevents duplicate imports.
        4. Matches or auto-creates supplier ledger (Sundry Creditors).
        5. Matches or auto-creates product catalog items.
        6. Generates next Purchase voucher number and saves DRAFT purchase invoice.
        7. NEVER auto-posts: buyer must confirm before ledger posting.
        """
        snapshot = edi_doc.document_snapshot
        if not can_edi(snapshot.document_type):
            raise PermissionDenied(f"EDI import is not permitted for document type: {snapshot.document_type}")

        if edi_doc.sender_company_id == buyer_company.id:
            raise ValidationError("Cannot import your own issued sales invoice into your own company.")

        payload = edi_doc.payload
        receiver_gstin = (edi_doc.receiver_gstin or '').strip().upper()
        buyer_gstin = (buyer_company.gstin or '').strip().upper()

        # Recipient GSTIN Verification
        gstin_warning = None
        if receiver_gstin and buyer_gstin and receiver_gstin != buyer_gstin:
            gstin_warning = (
                f"GSTIN Warning: This invoice was issued to {receiver_gstin}, "
                f"but your active company is {buyer_company.name} ({buyer_gstin})."
            )

        # Duplicate Prevention Check
        existing_exchange = EDIExchange.objects.select_related('draft_purchase_voucher').filter(
            edi_document=edi_doc,
            target_company=buyer_company,
            status__in=['DRAFT_CREATED', 'ACCEPTED']
        ).first()

        if existing_exchange and existing_exchange.draft_purchase_voucher:
            vch = existing_exchange.draft_purchase_voucher
            return {
                'success': True,
                'already_imported': True,
                'voucher_id': str(vch.id),
                'voucher_number': vch.voucher_number,
                'status': vch.status,
                'warning': gstin_warning,
                'message': f"This invoice was already imported as Purchase Bill #{vch.voucher_number}.",
            }

        # Match or Auto-Create Supplier Ledger
        sender_gstin = (payload.get('sender_gstin') or '').strip().upper()
        sender_name = payload.get('sender_name') or 'Supplier'

        supplier_ledger = None
        if sender_gstin:
            supplier_ledger = Ledger.objects.filter(
                company=buyer_company,
                gstin__iexact=sender_gstin
            ).first()

        if not supplier_ledger:
            supplier_ledger = Ledger.objects.filter(
                company=buyer_company,
                name__iexact=sender_name
            ).first()

        if not supplier_ledger:
            creditors_group = LedgerGroup.objects.filter(
                company=buyer_company,
                name__icontains="Creditor"
            ).first()
            if not creditors_group:
                creditors_group = LedgerGroup.objects.create(
                    company=buyer_company,
                    name="Sundry Creditors",
                    nature="LIABILITY"
                )

            supplier_ledger = Ledger.objects.create(
                company=buyer_company,
                group=creditors_group,
                name=sender_name,
                gstin=sender_gstin,
                state_code=payload.get('sender_state_code', ''),
                address=payload.get('sender_address', ''),
                phone=payload.get('sender_phone', ''),
                email=payload.get('sender_email', ''),
                ledger_type="SUPPLIER"
            )

        # Match or Auto-Create Products
        default_category = ProductCategory.objects.filter(company=buyer_company).first()
        if not default_category:
            default_category = ProductCategory.objects.create(
                company=buyer_company,
                name="General"
            )

        raw_items = payload.get('items', [])
        mapped_items = []

        for itm in raw_items:
            p_name = itm.get('name', 'Imported Product')
            hsn = itm.get('hsn_code', '')
            gst_rate = Decimal(str(itm.get('gst_rate', 18.0)))
            rate = Decimal(str(itm.get('rate', 0.0)))
            unit = itm.get('unit', 'PCS')

            prod = Product.objects.filter(
                company=buyer_company,
                name__iexact=p_name
            ).first()

            if not prod and hsn:
                prod = Product.objects.filter(
                    company=buyer_company,
                    hsn_code=hsn
                ).first()

            if not prod:
                prod = Product.objects.create(
                    company=buyer_company,
                    category=default_category,
                    name=p_name,
                    hsn_code=hsn,
                    unit=unit,
                    gst_rate=gst_rate,
                    purchase_price=rate,
                )

            mapped_items.append((prod, itm))

        # Generate Next Purchase Voucher Number
        raw_inv_date = payload.get('invoice_date')
        if raw_inv_date:
            try:
                v_date = date.fromisoformat(str(raw_inv_date).split('T')[0])
            except Exception:
                v_date = date.today()
        else:
            v_date = date.today()

        v_num, fy = InvoiceSequenceService.get_next_number(buyer_company, 'PURCHASE', v_date)
        inv_no = payload.get('invoice_number', '')

        # Create DRAFT Purchase Voucher (strictly DRAFT, never auto-posted)
        purchase_voucher = Voucher.objects.create(
            company=buyer_company,
            financial_year=fy,
            voucher_type='PURCHASE',
            voucher_number=v_num,
            voucher_date=v_date,
            reference_number=inv_no,
            external_invoice_number=inv_no,
            party_ledger=supplier_ledger,
            buyer_name=sender_name,
            buyer_gstin=sender_gstin,
            status='DRAFT',
            total_amount=Decimal(str(payload.get('total_amount', 0.0))),
            narration=f"Auto-imported from {sender_name} (Invoice #{inv_no}) via Vouch EDI Network",
            created_by=user,
        )

        for prod, itm in mapped_items:
            qty = Decimal(str(itm.get('quantity', 1.0)))
            rate = Decimal(str(itm.get('rate', 0.0)))
            disc_pct = Decimal(str(itm.get('discount_percent', 0.0)))
            taxable = Decimal(str(itm.get('taxable_amount', 0.0)))
            gst_rate = Decimal(str(itm.get('gst_rate', 18.0)))
            tot_amt = Decimal(str(itm.get('total_amount', 0.0)))

            VoucherItem.objects.create(
                voucher=purchase_voucher,
                product=prod,
                quantity=qty,
                rate=rate,
                discount_percent=disc_pct,
                taxable_amount=taxable,
                gst_rate=gst_rate,
                total_amount=tot_amt,
            )

        # Record EDIExchange
        exchange = EDIExchange.objects.create(
            edi_document=edi_doc,
            target_company=buyer_company,
            status='DRAFT_CREATED',
            draft_purchase_voucher=purchase_voucher,
        )

        # Audit Event
        DocumentAuditEvent.objects.create(
            company=buyer_company,
            document_snapshot=snapshot,
            action='EDI_IMPORT_DRAFT_CREATED',
            details={
                'purchase_voucher_id': str(purchase_voucher.id),
                'purchase_voucher_number': purchase_voucher.voucher_number,
                'source_invoice_number': inv_no,
            },
            user=user,
        )

        return {
            'success': True,
            'already_imported': False,
            'voucher_id': str(purchase_voucher.id),
            'voucher_number': purchase_voucher.voucher_number,
            'status': 'DRAFT',
            'warning': gstin_warning,
            'message': f"Successfully created Draft Purchase Bill #{purchase_voucher.voucher_number}. Please review and post.",
        }
