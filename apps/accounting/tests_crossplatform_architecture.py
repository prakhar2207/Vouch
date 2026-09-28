import json
import uuid
from decimal import Decimal
from django.test import TestCase, RequestFactory
from django.utils import timezone
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User
from apps.companies.models import Company, UserCompany
from apps.ledgers.models import Ledger, LedgerGroup
from apps.inventory.models import Product
from apps.accounting.models import Voucher, SyncEvent, FinancialYear
from apps.common.idempotency import IdempotencyMiddleware
from apps.common.client_context import ClientContextMiddleware


class CrossPlatformArchitectureTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='tester@vouch.internal',
            password='testpassword123'
        )
        self.company = Company.objects.create(
            name="Architecture Test Corp",
            gstin="07AAAAA0000A1Z5"
        )
        UserCompany.objects.create(
            user=self.user,
            company=self.company,
            role="OWNER"
        )
        self.group = LedgerGroup.objects.create(
            company=self.company,
            name="Sundry Debtors",
            nature="ASSET"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)


    def test_client_context_middleware(self):
        """Verifies device telemetry parsing and server version header injection."""
        factory = RequestFactory()
        request = factory.get(
            '/api/v1/sync/bootstrap/',
            HTTP_X_CLIENT_TYPE='mobile_ios',
            HTTP_X_APP_VERSION='2.1.0',
            HTTP_X_DEVICE_ID='iPhone15Pro-XYZ-9988'
        )
        
        middleware = ClientContextMiddleware(lambda req: req)
        # Calling process_request
        middleware.process_request(request)
        self.assertTrue(hasattr(request, 'client_context'))
        self.assertEqual(request.client_context.client_type, 'mobile_ios')
        self.assertEqual(request.client_context.app_version, '2.1.0')
        self.assertEqual(request.client_context.device_id, 'iPhone15Pro-XYZ-9988')
        self.assertTrue(request.client_context.is_mobile)
        self.assertFalse(request.client_context.is_desktop)

        # Calling process_response
        from django.http import HttpResponse
        res = HttpResponse("OK")
        final_res = middleware.process_response(request, res)
        self.assertEqual(final_res.get('X-Server-Version'), '1.0.2')

    def test_idempotency_engine_replay(self):
        """Verifies duplicate network requests with identical idempotency keys return cached responses."""
        from django.http import JsonResponse
        from django.core.cache import cache
        cache.clear()

        factory = RequestFactory()
        key = str(uuid.uuid4())
        request = factory.post(
            '/api/v1/sync/push/',
            data=json.dumps({"test": 123}),
            content_type='application/json',
            HTTP_X_IDEMPOTENCY_KEY=key,
            HTTP_X_COMPANY_ID=str(self.company.id)
        )
        request.user = self.user

        call_count = 0
        def dummy_view(req):
            nonlocal call_count
            call_count += 1
            return JsonResponse({"voucher_number": "INV-001", "call_count": call_count}, status=201)

        middleware = IdempotencyMiddleware(dummy_view)

        # 1st request
        res1 = middleware(request)
        self.assertEqual(res1.status_code, 201)
        data1 = json.loads(res1.content)
        self.assertEqual(data1["call_count"], 1)
        self.assertIsNone(res1.get('X-Idempotent-Replay'))

        # 2nd request with same idempotency key (simulating offline queue network retry)
        res2 = middleware(request)
        self.assertEqual(res2.status_code, 201)
        data2 = json.loads(res2.content)
        self.assertEqual(data2["call_count"], 1)  # Cached! Underlying view was NOT called again.
        self.assertEqual(res2.get('X-Idempotent-Replay'), 'true')
        self.assertEqual(call_count, 1)

    def test_sync_bootstrap_api(self):
        """Verifies single-roundtrip bootstrap bundles chart of accounts, products, and monotonic cursor."""
        # Create sample ledger and product
        Ledger.objects.create(
            company=self.company,
            group=self.group,
            name="Sample Customer",
            ledger_type="CUSTOMER",
            is_active=True
        )
        Product.objects.create(
            company=self.company,
            name="Industrial Valve 50mm",
            sku="VALVE-001",
            selling_price=Decimal("1200.00"),
            is_active=True
        )
        SyncEvent.objects.create(
            company=self.company,
            entity_type="PRODUCT",
            entity_id=uuid.uuid4(),
            operation="CREATE"
        )

        res = self.client.post(
            reverse('api_sync_bootstrap'),
            data={'company_id': str(self.company.id)},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = res.json()
        self.assertTrue(body['success'])
        data = body['data']
        self.assertIn('snapshot_cursor', data)
        self.assertGreaterEqual(data['snapshot_cursor'], 1)
        self.assertEqual(data['company']['name'], "Architecture Test Corp")
        self.assertGreaterEqual(len(data['ledgers']), 1)
        self.assertGreaterEqual(len(data['products']), 1)
        self.assertEqual(data['products'][0]['sku'], "VALVE-001")

    def test_sync_stream_sse_initial_handshake(self):
        """Verifies SSE real-time stream returns text/event-stream with initial connected event."""
        url = reverse('api_sync_stream') + f"?company_id={self.company.id}&cursor=0"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res['Content-Type'], 'text/event-stream')
        self.assertEqual(res['Cache-Control'], 'no-cache, no-transform')
        self.assertEqual(res['X-Accel-Buffering'], 'no')

        # Read first chunk from streaming generator
        stream_chunks = []
        for chunk in res.streaming_content:
            chunk_str = chunk.decode('utf-8') if isinstance(chunk, bytes) else str(chunk)
            stream_chunks.append(chunk_str)
            break # verify initial handshake then stop

        first_event = "".join(stream_chunks)
        self.assertIn("event: connected", first_event)
        self.assertIn('"status": "connected"', first_event)
        self.assertIn(str(self.company.id), first_event)

    def test_invoice_notification_dispatch_fallback(self):
        """Verifies invoice dispatch handles Celery task fallback gracefully without errors."""
        from apps.accounting.services.invoice_notification_service import InvoiceNotificationService
        from unittest.mock import patch

        party = Ledger.objects.create(
            company=self.company,
            group=self.group,
            name="Dispatch Party",
            ledger_type="CUSTOMER",
            phone="9876543210"
        )
        voucher = Voucher.objects.create(
            company=self.company,
            party_ledger=party,
            voucher_type="SALES",
            voucher_number="VCH-DISPATCH-001",
            voucher_date=timezone.now().date(),
            total_amount=Decimal("1500.00"),
            status="POSTED",
            created_by=self.user
        )

        # Dispatch in sync mode to ensure no unhandled exceptions
        with patch.object(InvoiceNotificationService, 'send_invoice_email', return_value=True):
            InvoiceNotificationService.dispatch_invoice_on_post(voucher, async_mode=False)
