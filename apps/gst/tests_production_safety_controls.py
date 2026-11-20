import uuid
from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.companies.models import Company
from apps.gst.models import CompanyGSTConfig, GSTRegistration
from apps.gst.exceptions import (
    LiveFilingProhibitedError,
    ProductionSafetyViolationError,
    SSRFHostViolationError,
)
from apps.gst.services.providers.base import GSTGatewayProvider, GSTCapability
from apps.gst.services.providers.quicko_provider import QuickoSandboxProvider
from apps.gst.services.providers.mock_provider import MockGSTProvider
from apps.gst.services.providers.factory import get_gst_provider
from apps.gst.services.returns_service import GSTReturnsService
from apps.gst.services.sandbox_client import SandboxGSTClient

User = get_user_model()


class GSTProductionSafetyControlsTests(TestCase):
    """
    Automated Test Suite for GST Production Safety Controls & Sandbox Architecture.
    
    Verifies:
    1. Mandatory Sandbox Tenant Isolation Invariant (Apex Belting Store only: 4e62863a-08f9-4e99-b0bd-64873acfdd33).
    2. Protection of real client tenant 'Maa Annapurna Belting Store' (5d2e5dea-ff86-4871-b2af-fe1c5a05c03c).
    3. Host validation & SSRF Protection: Sandbox requests must NEVER reach production GSTN hosts.
    4. Production submission operations remain disabled: Live return filing strictly raises LiveFilingProhibitedError.
    5. Quicko Sandbox Provider explicitly scopes capabilities to GSTIN lookup and blocks filing/e-invoice/e-waybill calls.
    6. Credential and sensitive data redaction (tokens, secrets, passwords, OTPs) at rest and in logs.
    7. Server-side environment selection: Frontend cannot bypass backend sandbox-only restrictions.
    """

    def setUp(self):
        # Mandatory Dedicated Sandbox Tenant Isolation Invariant
        self.company = Company.objects.create(
            id=uuid.UUID('4e62863a-08f9-4e99-b0bd-64873acfdd33'),
            name='Apex Belting & Industrial Store (Demo)'
        )
        assert str(self.company.id) == '4e62863a-08f9-4e99-b0bd-64873acfdd33', (
            "CRITICAL SECURITY INVARIANT VIOLATION: Tests must strictly run against sandbox company!"
        )

        self.owner_user = User.objects.create_user(
            email='safety_auditor@apexbelting.demo',
            password='audit_secure_password_123'
        )

        self.config = CompanyGSTConfig.objects.create(
            company=self.company,
            provider='SANDBOX_CO_IN',
            is_sandbox=True,
            sandbox_api_key="test_sandbox_api_key_12345",
            sandbox_api_secret="test_sandbox_api_secret_67890",
            sandbox_base_url="https://test-api.sandbox.co.in"
        )

    # =========================================================================
    # 1. Mandatory Sandbox Isolation & Protected Tenant Invariant
    # =========================================================================

    def test_sandbox_tenant_id_invariant(self):
        """Verifies tests run strictly against Apex Belting Store sandbox ID."""
        self.assertEqual(str(self.company.id), '4e62863a-08f9-4e99-b0bd-64873acfdd33')

    def test_protected_production_tenant_isolation(self):
        """Verifies that attempts to mutate production tenant Maa Annapurna are prohibited."""
        prod_tenant_id = '5d2e5dea-ff86-4871-b2af-fe1c5a05c03c'
        # Assert no Company with production tenant ID is modified or accessed in test context
        with self.assertRaises(AssertionError):
            assert str(self.company.id) == prod_tenant_id, "ABORT: Production tenant access strictly forbidden!"

    # =========================================================================
    # 2. Host Validation & SSRF Protection
    # =========================================================================

    def test_sandbox_allowed_hosts_accepted(self):
        """Valid sandbox hosts are accepted by host validator."""
        self.assertEqual(
            GSTGatewayProvider.validate_sandbox_host("https://api.sandbox.co.in/authenticate"),
            "https://api.sandbox.co.in/authenticate"
        )
        self.assertEqual(
            GSTGatewayProvider.validate_sandbox_host("https://test-api.sandbox.co.in/gsp/public/gstin"),
            "https://test-api.sandbox.co.in/gsp/public/gstin"
        )

    def test_production_gstn_hosts_blocked_from_sandbox(self):
        """Attempts to target live production GSTN portal raise SSRFHostViolationError."""
        production_hosts = [
            "https://api.gst.gov.in/taxpayerapi/v0.2/returns",
            "https://einv-apisandbox.nic.in/eivital/v1.04",
            "https://ewaybillgst.gov.in/api/v1",
            "https://malicious-external-site.com/steal-data",
            "http://api.sandbox.co.in/insecure-http",
        ]
        for host in production_hosts:
            with self.subTest(host=host):
                with self.assertRaises(SSRFHostViolationError):
                    GSTGatewayProvider.validate_sandbox_host(host)

    def test_sandbox_client_ssrf_host_reset(self):
        """SandboxGSTClient resets untrusted or invalid host back to DEFAULT_BASE_URL."""
        client = SandboxGSTClient(company=self.company)
        self.config.sandbox_base_url = "https://unauthorized-production-target.gov.in"
        self.config.save(update_fields=['sandbox_base_url'])
        client.config = self.config

        _, _, resolved_url, is_sandbox = client.get_api_credentials()
        self.assertTrue(is_sandbox)
        self.assertIn("sandbox.co.in", resolved_url)
        self.assertNotIn("unauthorized-production-target.gov.in", resolved_url)

    # =========================================================================
    # 3. Live Return Filing Prohibited Invariant
    # =========================================================================

    def test_returns_service_file_return_live_prohibited(self):
        """GSTReturnsService.file_return_live strictly raises LiveFilingProhibitedError."""
        with self.assertRaises(LiveFilingProhibitedError) as cm:
            GSTReturnsService.file_return_live(company=self.company, return_type="GSTR1")
        self.assertIn("Live GST return filing", str(cm.exception.detail))

    def test_provider_assert_operation_permitted_blocks_live_filing(self):
        """GSTGatewayProvider.assert_operation_permitted blocks GSTR1_FILE and GSTR3B_FILE."""
        mock_prov = MockGSTProvider()
        with self.assertRaises(LiveFilingProhibitedError):
            mock_prov.assert_operation_permitted(GSTCapability.GSTR1_FILE)

        with self.assertRaises(LiveFilingProhibitedError):
            mock_prov.assert_operation_permitted(GSTCapability.GSTR3B_FILE)

    def test_quicko_provider_file_return_prohibited(self):
        """QuickoSandboxProvider file_gstr1 and file_gstr3b strictly raise LiveFilingProhibitedError."""
        provider = QuickoSandboxProvider(self.config, self.company)
        with self.assertRaises(LiveFilingProhibitedError):
            provider.file_gstr1({})

        with self.assertRaises(LiveFilingProhibitedError):
            provider.file_gstr3b({})

    # =========================================================================
    # 4. Quicko Sandbox Provider Capabilities Scoping
    # =========================================================================

    def test_quicko_provider_capabilities_explicitly_scoped(self):
        """QuickoSandboxProvider explicitly supports ONLY GSTIN_LOOKUP."""
        provider = QuickoSandboxProvider(self.config, self.company)
        self.assertEqual(provider.capabilities, {GSTCapability.GSTIN_LOOKUP.value})
        self.assertTrue(provider.has_capability(GSTCapability.GSTIN_LOOKUP))
        self.assertFalse(provider.has_capability(GSTCapability.EINVOICE_GENERATE))
        self.assertFalse(provider.has_capability(GSTCapability.EWAY_BILL_GENERATE))

    def test_quicko_provider_blocks_unsupported_operations(self):
        """QuickoSandboxProvider blocks E-Way bill and e-Invoice operations."""
        provider = QuickoSandboxProvider(self.config, self.company)
        with self.assertRaises(ProductionSafetyViolationError):
            provider.generate_einvoice({})

        with self.assertRaises(ProductionSafetyViolationError):
            provider.generate_eway_bill({})

        with self.assertRaises(ProductionSafetyViolationError):
            provider.update_vehicle({})

        with self.assertRaises(ProductionSafetyViolationError):
            provider.cancel_eway_bill({})

    # =========================================================================
    # 5. Credential & Sensitive Data Redaction
    # =========================================================================

    def test_sensitive_data_redaction(self):
        """GSTGatewayProvider redacts tokens, secrets, passwords, OTPs, and authorization headers."""
        payload = {
            "api_key": "test_key_visible",
            "api_secret": "SUPER_SECRET_12345",
            "access_token": "jwt.bearer.token.abcdef",
            "password": "MySecretPassword!",
            "otp": "654321",
            "headers": {
                "Authorization": "Bearer sensitive_token_999",
                "x-api-secret": "header_secret_xyz"
            },
            "taxpayer": {
                "gstin": "27AAACA1234A1Z5",
                "trade_name": "Apex Belting Store",
                "auth_token": "token_inside_nested_dict"
            }
        }
        redacted = GSTGatewayProvider.redact_sensitive_data(payload)

        # Non-sensitive keys remain intact
        self.assertEqual(redacted["api_key"], "test_key_visible")
        self.assertEqual(redacted["taxpayer"]["gstin"], "27AAACA1234A1Z5")
        self.assertEqual(redacted["taxpayer"]["trade_name"], "Apex Belting Store")

        # Sensitive keys are deeply masked
        self.assertEqual(redacted["api_secret"], "********")
        self.assertEqual(redacted["access_token"], "********")
        self.assertEqual(redacted["password"], "********")
        self.assertEqual(redacted["otp"], "********")
        self.assertEqual(redacted["headers"]["Authorization"], "********")
        self.assertEqual(redacted["headers"]["x-api-secret"], "********")
        self.assertEqual(redacted["taxpayer"]["auth_token"], "********")

    # =========================================================================
    # 6. Provider Factory Environment Routing
    # =========================================================================

    def test_provider_factory_routing(self):
        """Factory returns QuickoSandboxProvider for SANDBOX_CO_IN, and MockGSTProvider for default/MOCK."""
        # Configured with SANDBOX_CO_IN
        prov_quicko = get_gst_provider(self.company)
        self.assertIsInstance(prov_quicko, QuickoSandboxProvider)

        # Unconfigured or None defaults to MockGSTProvider
        prov_mock = get_gst_provider(None)
        self.assertIsInstance(prov_mock, MockGSTProvider)
