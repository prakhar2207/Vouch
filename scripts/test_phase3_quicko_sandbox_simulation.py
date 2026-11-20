import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import requests
import django

sys.path.insert(0, r'c:\Users\prakh\OneDrive\Desktop\projects\B2B')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.companies.models import Company
from apps.gst.models import CompanyGSTConfig
from apps.gst.services.providers.quicko_provider import QuickoSandboxProvider
from apps.gst.services.providers.base import GSTCapability
from apps.gst.services.sandbox_client import SandboxGSTClient
from apps.gst.exceptions import (
    GSTAuthenticationError,
    GSTIntegrationError,
    LiveFilingProhibitedError,
    ProductionSafetyViolationError,
)

SANDBOX_ID = '4e62863a-08f9-4e99-b0bd-64873acfdd33'

class QuickoSandboxResilienceTests(unittest.TestCase):
    def setUp(self):
        self.company = Company.objects.get(id=SANDBOX_ID)
        assert str(self.company.id) == SANDBOX_ID, "ABORT: Tests may ONLY run against Apex Belting Store sandbox!"
        
        self.config = CompanyGSTConfig(
            company=self.company,
            provider='SANDBOX_CO_IN',
            is_sandbox=True,
            sandbox_api_key='test_mock_key',
            sandbox_api_secret='test_mock_secret',
            sandbox_base_url='https://api.sandbox.co.in'
        )
        self.provider = QuickoSandboxProvider(self.config, self.company)
        self.client = self.provider.client
        self.client.config = self.config

    # 1. Capability Verification
    def test_capabilities_scoped(self):
        self.assertEqual(self.provider.capabilities, {GSTCapability.GSTIN_LOOKUP.value})
        self.assertTrue(self.provider.has_capability(GSTCapability.GSTIN_LOOKUP))
        self.assertFalse(self.provider.has_capability(GSTCapability.GSTR1_FILE))
        self.assertFalse(self.provider.has_capability(GSTCapability.GSTR3B_FILE))
        self.assertFalse(self.provider.has_capability(GSTCapability.EINVOICE_GENERATE))
        self.assertFalse(self.provider.has_capability(GSTCapability.EWAY_BILL_GENERATE))

    # 2. Return Filing & GSP Actions Strictly Prohibited
    def test_filing_prohibited(self):
        with self.assertRaises(LiveFilingProhibitedError):
            self.provider.file_gstr1({})
        with self.assertRaises(LiveFilingProhibitedError):
            self.provider.file_gstr3b({})
        with self.assertRaises(ProductionSafetyViolationError):
            self.provider.generate_einvoice({})
        with self.assertRaises(ProductionSafetyViolationError):
            self.provider.generate_eway_bill({})

    # 3. Successful GSTIN Lookup
    @patch.object(SandboxGSTClient, 'get_access_token', return_value="mock_jwt_token_123")
    @patch('apps.gst.services.sandbox_client.requests.request')
    def test_successful_lookup(self, mock_req, mock_token):
        mock_search = MagicMock(status_code=200)
        mock_search.json.return_value = {
            "code": 200,
            "data": {
                "gstin": "27AAACA1234A1Z5",
                "tradeNam": "Apex Belting Store",
                "lgnm": "Apex Belting & Industrial Supplies Pvt Ltd",
                "sts": "Active",
                "stcd": "Maharashtra",
                "rgdt": "01/07/2017"
            }
        }
        mock_req.return_value = mock_search

        res = self.client.search_taxpayer("27AAACA1234A1Z5")
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("trade_name"), "Apex Belting Store")
        self.assertEqual(res.get("legal_name"), "Apex Belting & Industrial Supplies Pvt Ltd")
        self.assertEqual(res.get("status"), "Active")

    # 4. Invalid GSTIN Format / Checksum
    @patch.object(SandboxGSTClient, 'get_access_token', return_value="mock_jwt_token_123")
    @patch('apps.gst.services.sandbox_client.requests.request')
    def test_invalid_gstin_format(self, mock_req, mock_token):
        mock_search = MagicMock(status_code=422)
        mock_search.json.return_value = {
            "code": 422,
            "message": "Invalid GSTIN format or checksum"
        }
        mock_req.return_value = mock_search

        res = self.client.search_taxpayer("INVALID_GSTIN_123")
        self.assertFalse(res.get("success"))
        self.assertEqual(res.get("status_code"), 422)
        self.assertIn("Invalid GSTIN", res.get("error", ""))

    # 5. Authentication Failure (401 Unauthorized from Quicko)
    @patch('apps.gst.services.sandbox_client.requests.request')
    def test_authentication_failure(self, mock_req):
        mock_auth = MagicMock(status_code=401)
        mock_auth.text = '{"message": "Invalid API Key or Secret"}'
        mock_auth.json.return_value = {"message": "Invalid API Key or Secret"}
        mock_req.return_value = mock_auth

        # Client must raise GSTAuthenticationError with sanitized message
        with self.assertRaises(GSTAuthenticationError) as cm:
            self.client.get_access_token(force_refresh=True)
        self.assertIn("Authentication failed", str(cm.exception))
        self.assertNotIn("test_mock_secret", str(cm.exception))

    # 6. Provider Timeout (Gateway Timeout)
    @patch.object(SandboxGSTClient, 'get_access_token', return_value="mock_jwt_token_123")
    @patch('apps.gst.services.sandbox_client.requests.request')
    def test_provider_timeout(self, mock_req, mock_token):
        mock_req.side_effect = requests.exceptions.Timeout("Connection timed out after 15s")

        res = self.client.search_taxpayer("27AAACA1234A1Z5")
        self.assertFalse(res.get("success"))
        self.assertEqual(res.get("status_code"), 504)
        self.assertIn("Timeout", res.get("error", ""))

    # 7. Malformed Response (Non-JSON or Corrupted Payload)
    @patch.object(SandboxGSTClient, 'get_access_token', return_value="mock_jwt_token_123")
    @patch('apps.gst.services.sandbox_client.requests.request')
    def test_malformed_response(self, mock_req, mock_token):
        mock_search = MagicMock(status_code=502)
        mock_search.text = "<html><body>502 Bad Gateway</body></html>"
        mock_search.json.side_effect = ValueError("No JSON object could be decoded")
        mock_req.return_value = mock_search

        res = self.client.search_taxpayer("27AAACA1234A1Z5")
        self.assertFalse(res.get("success"))
        self.assertEqual(res.get("status_code"), 502)
        self.assertIn("502", res.get("error", ""))

    # 8. Provider Unavailability (Connection Error / Server Down)
    @patch.object(SandboxGSTClient, 'get_access_token', return_value="mock_jwt_token_123")
    @patch('apps.gst.services.sandbox_client.requests.request')
    def test_provider_unavailability(self, mock_req, mock_token):
        mock_req.side_effect = requests.exceptions.ConnectionError("Failed to establish a new connection")

        res = self.client.search_taxpayer("27AAACA1234A1Z5")
        self.assertFalse(res.get("success"))
        self.assertEqual(res.get("status_code"), 504)
        self.assertIn("ConnectionError", res.get("error", ""))

    # 9. Credential and Sensitive Data Redaction
    def test_redaction(self):
        raw_headers = {
            "Authorization": "Bearer sensitive_sandbox_jwt_secret",
            "x-api-key": "sensitive_api_key_abc",
            "x-api-secret": "super_secret_xyz"
        }
        redacted = self.provider.redact_sensitive_data(raw_headers)
        self.assertEqual(redacted["Authorization"], "********")
        self.assertEqual(redacted["x-api-secret"], "********")
        self.assertNotIn("sensitive_sandbox_jwt_secret", str(redacted))
        self.assertNotIn("super_secret_xyz", str(redacted))

if __name__ == '__main__':
    unittest.main()
