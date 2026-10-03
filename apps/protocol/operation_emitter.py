import hashlib
import uuid
import logging
from decimal import Decimal
from typing import Optional, Dict, Any

from apps.accounting.models import Voucher
from .operation import AccountingOperation, OperationType, OperationClass
from .models import ProtocolTransaction, ProtocolOperation

logger = logging.getLogger(__name__)

class ProtocolOperationEmitter:
    """
    Connects authoritative Vouch accounting actions directly into the
    distributed protocol's operational log.
    Every posted or cancelled voucher emits an immutable AccountingOperation.
    """

    VOUCHER_TYPE_MAP = {
        'SALES': OperationType.TRANSACTION_ISSUED,
        'PURCHASE': OperationType.PURCHASE_INVOICE_CREATED,
        'RECEIPT': OperationType.PAYMENT_ALLOCATED,
        'PAYMENT': OperationType.PAYMENT_ALLOCATED,
        'CREDIT_NOTE': OperationType.CREDIT_NOTE_ISSUED,
        'DEBIT_NOTE': OperationType.DEBIT_NOTE_ISSUED,
        'CONTRA': OperationType.CONTRA_CREATED,
        'JOURNAL': OperationType.JOURNAL_CREATED,
    }

    @classmethod
    def emit_from_voucher(cls, voucher: Voucher, action: str = "POST") -> Optional[ProtocolOperation]:
        """
        Emits an AccountingOperation for a Vouch voucher and persists to ProtocolOperation.
        """
        try:
            tx_id = voucher.external_invoice_number or f"TX-VOUCH-{voucher.voucher_number}"
            company_id = str(voucher.company_id)
            party_id = str(voucher.party_ledger_id) if voucher.party_ledger_id else "CASH"

            if action == "CANCEL":
                op_type = OperationType.VOUCHER_CANCELLED
                op_cls = OperationClass.FINALIZING
            else:
                op_type = cls.VOUCHER_TYPE_MAP.get(voucher.voucher_type, OperationType.TRANSACTION_ISSUED)
                op_cls = None

            # Calculate line items and taxes
            line_items = []
            taxable_sum = Decimal('0.00')
            cgst_sum = Decimal('0.00')
            sgst_sum = Decimal('0.00')
            igst_sum = Decimal('0.00')

            for item in voucher.items.select_related('product').all():
                p_name = item.product.name if (item.product and hasattr(item.product, 'name')) else "Line Item"
                taxable_val = getattr(item, 'taxable_amount', Decimal('0.00')) or Decimal('0.00')
                cgst_val = getattr(item, 'cgst_amount', Decimal('0.00')) or Decimal('0.00')
                sgst_val = getattr(item, 'sgst_amount', Decimal('0.00')) or Decimal('0.00')
                igst_val = getattr(item, 'igst_amount', Decimal('0.00')) or Decimal('0.00')
                tax_val = cgst_val + sgst_val + igst_val

                taxable_sum += taxable_val
                cgst_sum += cgst_val
                sgst_sum += sgst_val
                igst_sum += igst_val

                line_items.append({
                    "product_id": str(item.product_id) if item.product_id else None,
                    "product_name": p_name,
                    "quantity": float(getattr(item, 'quantity', 0)),
                    "rate": float(getattr(item, 'rate', 0)),
                    "taxable_amount": float(taxable_val),
                    "tax_amount": float(tax_val),
                    "hsn_code": getattr(item, 'hsn_code', ""),
                    "gst_rate": float(getattr(item, 'gst_rate', 0))
                })

            total_tax_sum = cgst_sum + sgst_sum + igst_sum
            round_off_val = getattr(voucher, 'round_off', Decimal('0.00')) or Decimal('0.00')

            payload: Dict[str, Any] = {
                "voucher_id": str(voucher.id),
                "voucher_number": voucher.voucher_number,
                "voucher_type": voucher.voucher_type,
                "voucher_date": str(voucher.voucher_date),
                "grand_total": float(voucher.total_amount),
                "taxable_amount": float(taxable_sum),
                "total_tax": float(total_tax_sum),
                "cgst_amount": float(cgst_sum),
                "sgst_amount": float(sgst_sum),
                "igst_amount": float(igst_sum),
                "round_off": float(round_off_val),
                "items": line_items,
                "action": action
            }

            # Find parent operation ID for causal chaining
            ptx, _ = ProtocolTransaction.objects.get_or_create(
                transaction_id=tx_id,
                defaults={
                    "transaction_type": voucher.voucher_type,
                    "protocol_version": "1.0",
                    "source_company_id": company_id,
                    "destination_company_id": party_id,
                    "canonical_payload": {"transaction_id": tx_id, "voucher_number": voucher.voucher_number}
                }
            )

            last_op = ptx.operations.order_by('-logical_timestamp').first()
            parents = [last_op.operation_id] if last_op else []
            logical_ts = (last_op.logical_timestamp + 1) if last_op else 1

            op_id = f"OP-{voucher.voucher_type[:3]}-{uuid.uuid4().hex[:8].upper()}"

            acct_op = AccountingOperation(
                operation_id=op_id,
                transaction_id=tx_id,
                replica_id=f"COMPANY-{company_id[:8]}",
                operation_type=op_type,
                operation_class=op_cls,
                payload=payload,
                logical_timestamp=logical_ts,
                parents=parents,
                tenant_id=company_id
            )

            # Cryptographically sign the server-authored operation via KMS
            sig = None
            try:
                from .kms import get_kms
                kms = get_kms()
                sig = kms.sign(key_id=acct_op.replica_id, message=acct_op.payload_hash.encode('utf-8'))
            except Exception as e:
                logger.warning(f"KMS signing warning for op {op_id}: {e}")
                sig = None

            db_op = ProtocolOperation.objects.create(
                operation_id=acct_op.operation_id,
                transaction=ptx,
                replica_id=acct_op.replica_id,
                operation_type=acct_op.operation_type.value if hasattr(acct_op.operation_type, 'value') else str(acct_op.operation_type),
                payload=dict(acct_op.payload),
                logical_timestamp=acct_op.logical_timestamp,
                parents=list(acct_op.parents),
                payload_hash=acct_op.payload_hash,
                signature=sig
            )

            logger.info(f"Emitted ProtocolOperation {op_id} for Voucher {voucher.voucher_number} ({action})")
            return db_op

        except Exception as e:
            logger.error(f"ProtocolOperationEmitter failure for Voucher {voucher.id}: {e}", exc_info=True)
            # Auxiliary protocol emission must NEVER abort the core financial ERP voucher posting
            logger.warning(f"Protocol operation emission skipped for Voucher {voucher.voucher_number}: {e}")
            return None
