import json
import logging
from django.test import TestCase, RequestFactory
from django.http import HttpResponse

from apps.common.logging import (
    mask_sensitive_data,
    PIIMaskingFilter,
    StructuredJSONFormatter,
    RequestCorrelationMiddleware,
    set_correlation_context,
    clear_correlation_context,
    get_correlation_context
)
from apps.common.observability import DistributedObservability

class ObservabilityAndPIIMaskingTests(TestCase):
    def tearDown(self):
        clear_correlation_context()

    def test_pii_masking_gstin_and_pan(self):
        raw = "Company with GSTIN 29ABCDE1234F1Z5 and PAN ABCDE1234F initiated transaction."
        masked = mask_sensitive_data(raw)
        self.assertNotIn("29ABCDE1234F1Z5", masked)
        self.assertNotIn("ABCDE1234F", masked)
        self.assertIn("[MASKED_GSTIN]", masked)
        self.assertIn("[MASKED_PAN]", masked)

    def test_pii_masking_bank_account(self):
        raw = "Transfer to account: 123456789012 at SBI branch"
        masked = mask_sensitive_data(raw)
        self.assertNotIn("123456789012", masked)
        self.assertIn("[MASKED_BANK_ACC]", masked)

    def test_pii_masking_tokens_and_private_keys(self):
        raw_token = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjoxfQ.secret123"
        masked_token = mask_sensitive_data(raw_token)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", masked_token)
        self.assertIn("[MASKED_JWT]", masked_token)

        raw_key = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0Y3...\n-----END RSA PRIVATE KEY-----"
        masked_key = mask_sensitive_data(raw_key)
        self.assertNotIn("MIIEowIBAAKCAQEA0Y3", masked_key)
        self.assertIn("[MASKED_PRIVATE_KEY]", masked_key)

    def test_structured_json_formatter(self):
        set_correlation_context(
            request_id="req-9999",
            company_id="comp-1234",
            replica_id="replica-node-1"
        )

        formatter = StructuredJSONFormatter()
        record = logging.LogRecord(
            name="vouch.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="Client GSTIN 27AAACE1234F1Z3 processed",
            args=(),
            exc_info=None
        )

        output = formatter.format(record)
        data = json.loads(output)

        self.assertEqual(data["level"], "INFO")
        self.assertEqual(data["logger"], "vouch.test")
        self.assertEqual(data["correlation"]["request_id"], "req-9999")
        self.assertEqual(data["correlation"]["company_id"], "comp-1234")
        self.assertEqual(data["correlation"]["replica_id"], "replica-node-1")
        # Masked message
        self.assertNotIn("27AAACE1234F1Z3", data["message"])
        self.assertIn("[MASKED_GSTIN]", data["message"])

    def test_request_correlation_middleware(self):
        rf = RequestFactory()
        request = rf.get(
            '/api/v1/accounting/health/',
            HTTP_X_REQUEST_ID='custom-req-id-777',
            HTTP_X_COMPANY_ID='cmp-888',
            HTTP_X_DEVICE_ID='dev-333'
        )

        middleware = RequestCorrelationMiddleware(get_response=lambda r: HttpResponse("OK"))
        middleware.process_request(request)

        # In-request context
        self.assertEqual(request.request_id, 'custom-req-id-777')
        ctx = get_correlation_context()
        self.assertEqual(ctx['request_id'], 'custom-req-id-777')
        self.assertEqual(ctx['company_id'], 'cmp-888')

        response = HttpResponse("OK")
        resp = middleware.process_response(request, response)

        self.assertEqual(resp['X-Request-ID'], 'custom-req-id-777')
        # Cleared context
        self.assertEqual(get_correlation_context(), {})

    def test_distributed_observability_helpers(self):
        # Verify helper functions run without exception
        DistributedObservability.log_sync_event(
            event_type="push",
            replica_id="rep-1",
            operation_id="op-1",
            status="SUCCESS"
        )

        DistributedObservability.log_crdt_conflict(
            replica_id="rep-1",
            operation_id="op-2",
            entity_type="Voucher",
            resolution_strategy="LWW_TIMESTAMP"
        )

        DistributedObservability.log_security_event(
            event_type="signature_mismatch",
            reason="Ed25519 signature verification failed",
            device_id="dev-invalid"
        )

        DistributedObservability.log_subsystem_failure(
            subsystem="bank_reconciliation",
            error=ValueError("Invalid CSV format in bank statement")
        )
