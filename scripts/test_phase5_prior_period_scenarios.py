import os
import sys
import unittest
from decimal import Decimal
from datetime import date
import django

sys.path.insert(0, r'c:\Users\prakh\OneDrive\Desktop\projects\B2B')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.companies.models import Company
from apps.gst.models import GSTRegistration, GSTReturnWorkspace
from apps.gst.services.returns_service import GSTReturnsService
from apps.gst.services.workspace_service import GSTWorkspaceService
from apps.accounting.models import Voucher

SANDBOX_ID = '4e62863a-08f9-4e99-b0bd-64873acfdd33'

class PriorPeriodGSTScenarioTests(unittest.TestCase):
    def setUp(self):
        self.company = Company.objects.get(id=SANDBOX_ID)
        assert str(self.company.id) == SANDBOX_ID, "ABORT: Tests may ONLY run against Apex Belting Store sandbox!"
        self.registration = GSTRegistration.objects.filter(company=self.company).first()

    def test_gstr1_amendment_tables_presence(self):
        """Verify presence of amendment tables in GSTR-1 payload."""
        gstr1 = GSTReturnsService.prepare_gstr1(company=self.company, return_period='022026')
        raw = gstr1.get("official_gstr1_json", {})
        amendment_keys = ['b2ba', 'b2cla', 'b2csa', 'cdnra', 'cdnura', 'expa', 'ata', 'txpda']
        for k in amendment_keys:
            self.assertIn(k, raw)
            self.assertEqual(raw[k], [], f"Key {k} is expected to be empty list in main branch")

    def test_gstr3b_reversal_tables_stubbed(self):
        """Verify Table 4(B) and 4(D) in GSTR-3B payload."""
        gstr3b = GSTReturnsService.prepare_gstr3b(company=self.company, return_period='022026')
        t4 = gstr3b.get("table_4_itc", {})
        reversals = t4.get("itc_reversed", {})
        ineligible = t4.get("itc_ineligible", {})
        self.assertEqual(reversals.get("as_per_rules_42_43", {}).get("igst"), 0.0)
        self.assertEqual(reversals.get("others", {}).get("igst"), 0.0)
        self.assertEqual(ineligible.get("as_per_sec_17_5", {}).get("igst"), 0.0)

    def test_workspace_regeneration_on_exported(self):
        """Verify behavior when generating draft on an EXPORTED workspace."""
        ws = GSTWorkspaceService.get_or_create_workspace(
            company=self.company,
            registration=self.registration,
            return_type='GSTR1',
            return_period='022026'
        )
        ws.status = 'EXPORTED'
        ws.save(update_fields=['status'])
        
        # generate_draft can be called on EXPORTED workspace, updating draft_payload
        res = GSTWorkspaceService.generate_draft(ws)
        ws.refresh_from_db()
        self.assertEqual(ws.status, 'EXPORTED')
        self.assertIsNotNone(ws.draft_payload)
        self.assertFalse(ws.is_stale)

if __name__ == '__main__':
    unittest.main()
