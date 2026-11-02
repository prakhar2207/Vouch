import uuid
import json
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.companies.models import Company, UserCompany
from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.audit.views import AuditLogListView

class AuditHashCompletenessTests(TestCase):
    """
    Exhaustive regression test suite verifying DEFECT 3 remediation:
    Audit hash payload completeness (actor attribution, IP address, UTC timestamp),
    cryptographic chaining, tamper-evidence detection, and API telemetry.
    """
    def setUp(self):
        self.company_id = uuid.UUID('4e62863a-08f9-4e99-b0bd-64873acfdd33')
        self.company, _ = Company.objects.get_or_create(
            id=self.company_id,
            defaults={'name': 'Apex Belting & Industrial Store (Demo)'}
        )
        assert str(self.company.id) == '4e62863a-08f9-4e99-b0bd-64873acfdd33', "ABORT: Sandbox isolation invariant!"

        self.user, _ = User.objects.get_or_create(
            email='auditor@apexbelting.demo',
            defaults={'first_name': 'Lead', 'last_name': 'Auditor'}
        )
        UserCompany.objects.get_or_create(user=self.user, company=self.company, defaults={'role': 'ADMIN'})

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_audit_creation_with_actor_ip_and_timestamp(self):
        """Audit log creation includes actor attribution, IP address, and deterministic v2 hash."""
        log = AuditLog.objects.create(
            company=self.company,
            user=self.user,
            action='POST',
            model_name='Voucher',
            record_id=str(uuid.uuid4()),
            changes={"voucher_number": "RCP/26-27/0001", "total_amount": "15000.00"},
            ip_address='192.168.1.100'
        )
        self.assertEqual(log.schema_version, 'v2')
        self.assertIsNotNone(log.created_at)
        self.assertEqual(log.ip_address, '192.168.1.100')
        self.assertEqual(log.user, self.user)
        self.assertIsNotNone(log.current_hash)
        self.assertEqual(len(log.current_hash), 64)

        # Verify hash matches compute_hash
        expected_hash = log.compute_hash(log.previous_hash)
        self.assertEqual(log.current_hash, expected_hash)

        # Chain telemetry should be clean VERIFIED
        telemetry = AuditLogListView.verify_company_chain_telemetry(self.company)
        self.assertEqual(telemetry['status'], 'VERIFIED')
        self.assertEqual(telemetry['total_records_checked'], 1)
        self.assertEqual(telemetry['invalid_records_count'], 0)

    def test_tamper_detection_data_modification(self):
        """Tampering with audit record payload breaks the cryptographic chain."""
        log1 = AuditLog.objects.create(
            company=self.company,
            user=self.user,
            action='CREATE',
            model_name='Voucher',
            record_id='VCH-001',
            changes={"amount": "1000.00"},
            ip_address='10.0.0.1'
        )
        log2 = AuditLog.objects.create(
            company=self.company,
            user=self.user,
            action='POST',
            model_name='Voucher',
            record_id='VCH-001',
            changes={"amount": "1000.00", "status": "POSTED"},
            ip_address='10.0.0.1'
        )

        # Chain initially verified
        t_before = AuditLogListView.verify_company_chain_telemetry(self.company)
        self.assertEqual(t_before['status'], 'VERIFIED')

        # Tamper directly at database level: change amount from 1000.00 to 9999.00
        AuditLog.objects.filter(id=log1.id).update(changes={"amount": "9999.00"})

        # Chain must immediately detect tampering and pinpoint log1
        t_after = AuditLogListView.verify_company_chain_telemetry(self.company)
        self.assertEqual(t_after['status'], 'BROKEN')
        self.assertEqual(t_after['first_tampered_id'], str(log1.id))
        self.assertGreaterEqual(t_after['invalid_records_count'], 1)

    def test_tamper_detection_record_deletion(self):
        """Deleting an audit log record breaks previous_hash linkage."""
        log1 = AuditLog.objects.create(company=self.company, user=self.user, action='CREATE', model_name='Ledger', record_id='L-1')
        log2 = AuditLog.objects.create(company=self.company, user=self.user, action='UPDATE', model_name='Ledger', record_id='L-1')
        log3 = AuditLog.objects.create(company=self.company, user=self.user, action='POST', model_name='Ledger', record_id='L-1')

        # Chain initially valid
        self.assertEqual(AuditLogListView.verify_company_chain_telemetry(self.company)['status'], 'VERIFIED')

        # Force-delete middle record
        log2.delete(force=True)

        # Chain must detect broken previous_hash reference on log3
        telemetry = AuditLogListView.verify_company_chain_telemetry(self.company)
        self.assertEqual(telemetry['status'], 'BROKEN')
        self.assertEqual(telemetry['first_tampered_id'], str(log3.id))

    def test_audit_verification_endpoint(self):
        """API endpoint /api/v1/audit/verify/ returns real cryptographic verification telemetry."""
        AuditLog.objects.create(company=self.company, user=self.user, action='CREATE', model_name='Product', record_id='P-100')
        
        res = self.client.get(f'/api/v1/audit/verify/{self.company.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['telemetry']['status'], 'VERIFIED')
        self.assertEqual(data['telemetry']['invalid_records_count'], 0)
        self.assertIn('last_verified_at', data['telemetry'])
