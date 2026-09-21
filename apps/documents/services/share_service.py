import hashlib
import logging
import secrets
from datetime import timedelta
from typing import Optional, Tuple

from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.accounts.models import User
from apps.documents.capabilities import get_document_capabilities
from apps.documents.models import DocumentShare, DocumentShareEvent, DocumentSnapshot

logger = logging.getLogger(__name__)

SHARE_TYPE_PREFIXES = {
    'INVOICE': 'i',
    'STATEMENT': 's',
    'DOCUMENT': 'd',
}


class DocumentShareService:
    """
    Manages secure, token-hashed sharing URLs and event auditing.
    Tokens are stored in PostgreSQL exclusively as SHA-256 digests.
    """

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.strip().encode('utf-8')).hexdigest()

    @classmethod
    def create_share(
        cls,
        snapshot: DocumentSnapshot,
        user: Optional[User] = None,
        expires_in_days: Optional[int] = 30,
    ) -> Tuple[str, DocumentShare]:
        """
        Generates a 32-character cryptographically secure token,
        hashes it with SHA-256 for database storage, and returns (raw_token, DocumentShare).
        """
        caps = get_document_capabilities(snapshot.document_type)
        if not caps.share:
            raise PermissionDenied(f"Sharing is not permitted for document type: {snapshot.document_type}")

        raw_token = secrets.token_urlsafe(32)
        token_hash = cls.hash_token(raw_token)

        if snapshot.document_type in ['SALES_INVOICE', 'PURCHASE_INVOICE', 'CREDIT_NOTE', 'DEBIT_NOTE']:
            share_type = 'INVOICE'
        elif snapshot.document_type in ['CUSTOMER_STATEMENT', 'SUPPLIER_STATEMENT', 'LEDGER']:
            share_type = 'STATEMENT'
        else:
            share_type = 'DOCUMENT'

        expires_at = None
        if expires_in_days and expires_in_days > 0:
            expires_at = timezone.now() + timedelta(days=expires_in_days)

        share = DocumentShare.objects.create(
            document_snapshot=snapshot,
            token_hash=token_hash,
            share_type=share_type,
            expires_at=expires_at,
            created_by=user,
        )

        DocumentShareEvent.objects.create(
            share=share,
            event_type='CREATED',
        )

        return raw_token, share

    @classmethod
    def resolve_share(
        cls,
        raw_token: str,
        request=None,
        record_event: Optional[str] = None,
    ) -> DocumentShare:
        """
        Looks up a DocumentShare by hashing the raw token.
        Validates active status and expiry. Optionally records an audit event.
        """
        token_hash = cls.hash_token(raw_token)
        share = DocumentShare.objects.select_related('document_snapshot', 'document_snapshot__company').filter(
            token_hash=token_hash
        ).first()

        if not share:
            raise PermissionDenied("Invalid or non-existent share link.")

        if not share.is_active:
            if share.revoked_at:
                raise PermissionDenied("This share link has been revoked by the sender.")
            else:
                raise PermissionDenied("This share link has expired.")

        if record_event:
            ip_hash = ''
            user_agent = ''
            if request:
                ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
                if ip:
                    ip_hash = hashlib.sha256(ip.split(',')[0].strip().encode('utf-8')).hexdigest()
                user_agent = request.META.get('HTTP_USER_AGENT', '')[:250]

            DocumentShareEvent.objects.create(
                share=share,
                event_type=record_event,
                ip_hash=ip_hash,
                user_agent=user_agent,
            )

        return share

    @classmethod
    def revoke_share(cls, share: DocumentShare, user: Optional[User] = None):
        """Revokes an active share link."""
        share.revoked_at = timezone.now()
        share.save(update_fields=['revoked_at'])
        DocumentShareEvent.objects.create(
            share=share,
            event_type='REVOKED',
        )

    @classmethod
    def build_share_url(cls, raw_token: str, share_type: str, base_url: str = "https://vouch-pi-one.vercel.app") -> str:
        prefix = SHARE_TYPE_PREFIXES.get(share_type, 'd')
        return f"{base_url}/share/{prefix}/{raw_token}"

    @classmethod
    def generate_whatsapp_message(
        cls,
        snapshot: DocumentSnapshot,
        raw_token: str,
        base_url: str = "https://vouch-pi-one.vercel.app",
    ) -> str:
        """
        Builds a professional, clean WhatsApp message with document details and secure share URL.
        """
        dto = snapshot.snapshot_json
        seller = dto.get('seller', {})
        buyer = dto.get('buyer', {})
        doc = dto.get('document', {})
        subtotals = dto.get('subtotals', {})

        share_type = 'INVOICE' if snapshot.document_type in ['SALES_INVOICE', 'PURCHASE_INVOICE', 'CREDIT_NOTE', 'DEBIT_NOTE'] else 'STATEMENT'
        share_url = cls.build_share_url(raw_token, share_type, base_url)

        if share_type == 'INVOICE':
            doc_title = "TAX INVOICE"
            if snapshot.document_type == 'CREDIT_NOTE':
                doc_title = "CREDIT NOTE"
            elif snapshot.document_type == 'DEBIT_NOTE':
                doc_title = "DEBIT NOTE"

            grand_total = subtotals.get('grand_total', 0.0)
            msg = (
                f"🧾 *{doc_title} #{doc.get('document_number', '')}*\n\n"
                f"Dear *{buyer.get('name', 'Valued Customer')}*,\n\n"
                f"Here is your document from *{seller.get('name', 'Vouch')}*:\n"
                f"• *Document No:* {doc.get('document_number', '')}\n"
                f"• *Date:* {doc.get('document_date', '')}\n"
                f"• *Amount:* ₹{grand_total:,.2f}\n\n"
                f"📄 *View Online, Download PDF & 1-Click Auto-Book:*\n"
                f"{share_url}\n\n"
                f"Thank you for doing business with us!\n"
                f"*{seller.get('name', 'Vouch')}*"
            )
        else:
            # Statement
            cl_bal = dto.get('closing_balance', {})
            cl_amt = cl_bal.get('amount', 0.0)
            cl_type = cl_bal.get('type', 'DR')
            msg = (
                f"📊 *STATEMENT OF ACCOUNT*\n\n"
                f"Dear *{buyer.get('name', dto.get('party', {}).get('name', 'Valued Partner'))}*,\n\n"
                f"Here is your account statement from *{seller.get('name', dto.get('company', {}).get('name', 'Vouch'))}*:\n"
                f"• *Period:* {doc.get('from_date', 'Inception')} to {doc.get('to_date', 'Present')}\n"
                f"• *Closing Balance:* ₹{cl_amt:,.2f} ({cl_type})\n\n"
                f"📄 *View & Download Statement PDF:*\n"
                f"{share_url}\n\n"
                f"Thank you!\n"
                f"*{seller.get('name', dto.get('company', {}).get('name', 'Vouch'))}*"
            )

        return msg
