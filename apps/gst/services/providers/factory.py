from .base import GSTGatewayProvider
from .mock_provider import MockGSTProvider
from .gsp_provider import GSPProvider
from .quicko_provider import QuickoSandboxProvider
from apps.gst.models import CompanyGSTConfig

def get_gst_provider(company=None) -> GSTGatewayProvider:
    """
    Factory to retrieve the active GST Gateway Provider for a given company.
    Defaults to MockGSTProvider if no company is supplied or if no config exists.
    """
    if not company:
        return MockGSTProvider()

    config = CompanyGSTConfig.objects.filter(company=company).first()
    if not config or config.provider == 'MOCK':
        return MockGSTProvider(config)

    if config.provider == 'SANDBOX_CO_IN':
        return QuickoSandboxProvider(config, company)

    return GSPProvider(config)
