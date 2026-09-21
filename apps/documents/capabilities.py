from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class DocumentCapabilities:
    pdf: bool = True
    preview: bool = True
    share: bool = False
    email: bool = False
    whatsapp: bool = False
    edi: bool = False


DOCUMENT_CAPABILITIES: Dict[str, DocumentCapabilities] = {
    'SALES_INVOICE': DocumentCapabilities(
        pdf=True, preview=True, share=True, email=True, whatsapp=True, edi=True
    ),
    'PURCHASE_INVOICE': DocumentCapabilities(
        pdf=True, preview=True, share=True, email=True, whatsapp=True, edi=False
    ),
    'CREDIT_NOTE': DocumentCapabilities(
        pdf=True, preview=True, share=True, email=True, whatsapp=True, edi=False
    ),
    'DEBIT_NOTE': DocumentCapabilities(
        pdf=True, preview=True, share=True, email=True, whatsapp=True, edi=False
    ),
    'PAYMENT': DocumentCapabilities(
        pdf=True, preview=True, share=True, email=True, whatsapp=True, edi=False
    ),
    'RECEIPT': DocumentCapabilities(
        pdf=True, preview=True, share=True, email=True, whatsapp=True, edi=False
    ),
    'CONTRA': DocumentCapabilities(
        pdf=True, preview=True, share=True, email=True, whatsapp=True, edi=False
    ),
    'JOURNAL': DocumentCapabilities(
        pdf=True, preview=True, share=True, email=True, whatsapp=True, edi=False
    ),
    'CUSTOMER_STATEMENT': DocumentCapabilities(
        pdf=True, preview=True, share=True, email=True, whatsapp=True, edi=False
    ),
    'SUPPLIER_STATEMENT': DocumentCapabilities(
        pdf=True, preview=True, share=True, email=True, whatsapp=True, edi=False
    ),
    'LEDGER': DocumentCapabilities(
        pdf=True, preview=True, share=True, email=True, whatsapp=True, edi=False
    ),
    'TRIAL_BALANCE': DocumentCapabilities(
        pdf=True, preview=True, share=False, email=False, whatsapp=False, edi=False
    ),
    'PROFIT_AND_LOSS': DocumentCapabilities(
        pdf=True, preview=True, share=False, email=False, whatsapp=False, edi=False
    ),
    'BALANCE_SHEET': DocumentCapabilities(
        pdf=True, preview=True, share=False, email=False, whatsapp=False, edi=False
    ),
}


def get_document_capabilities(document_type: str) -> DocumentCapabilities:
    """Returns capabilities for a given document type. Defaults to safe restricted values."""
    return DOCUMENT_CAPABILITIES.get(document_type, DocumentCapabilities(pdf=True, preview=True))


def can_edi(document_type: str) -> bool:
    """Convenience checker to verify if a document type is permitted for EDI import/export."""
    return get_document_capabilities(document_type).edi
