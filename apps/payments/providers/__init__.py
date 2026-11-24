# apps/payments/providers/__init__.py
from apps.payments.constants import PaymentProviderType
from apps.payments.interfaces.provider_interface import PaymentProviderInterface
from apps.payments.providers.setu_provider import SetuPaymentProvider
from apps.payments.providers.bank_transfer_provider import BankTransferProvider


def get_payment_provider(provider_type: str) -> PaymentProviderInterface:
    """
    Factory method to retrieve the requested payment provider adapter.
    """
    if provider_type == PaymentProviderType.SETU:
        return SetuPaymentProvider()
    elif provider_type == PaymentProviderType.BANK_TRANSFER:
        return BankTransferProvider()
    else:
        # Default fallback to Setu for UPI
        return SetuPaymentProvider()


__all__ = ['SetuPaymentProvider', 'BankTransferProvider', 'get_payment_provider']
