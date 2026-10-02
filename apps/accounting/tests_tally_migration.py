import uuid
from decimal import Decimal
from django.test import TestCase
from apps.companies.models import Company
from apps.accounts.models import User
from apps.accounting.models import Voucher, LedgerEntry
from apps.ledgers.models import Ledger
from apps.inventory.models import Product
from apps.accounting.services.tally_migration_service import TallyMigrationService

SAMPLE_TALLY_XML = """<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Export Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <IMPORTDATA>
      <REQUESTDATA>
        <TALLYMESSAGE>
          <GROUP NAME="Sundry Debtors">
            <PARENT>Current Assets</PARENT>
          </GROUP>
        </TALLYMESSAGE>
        <TALLYMESSAGE>
          <LEDGER NAME="Bharat Steel Mills">
            <PARENT>Sundry Debtors</PARENT>
            <OPENINGBALANCE>-15000.00</OPENINGBALANCE>
            <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
            <PARTYGSTIN>27AABCB1234F1Z1</PARTYGSTIN>
            <INCOMETAXNUMBER>AABCB1234F</INCOMETAXNUMBER>
            <EMAIL>accounts@bharatsteel.in</EMAIL>
          </LEDGER>
        </TALLYMESSAGE>
        <TALLYMESSAGE>
          <LEDGER NAME="National Machinery Corp">
            <PARENT>Sundry Creditors</PARENT>
            <OPENINGBALANCE>15000.00</OPENINGBALANCE>
            <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
            <PARTYGSTIN>27AACCN9876G1Z2</PARTYGSTIN>
          </LEDGER>
        </TALLYMESSAGE>
        <TALLYMESSAGE>
          <STOCKITEM NAME="Cast Iron Piston 150mm">
            <BASEUNITS>PCS</BASEUNITS>
            <OPENINGBALANCE>50.00</OPENINGBALANCE>
            <OPENINGVALUE>25000.00</OPENINGVALUE>
          </STOCKITEM>
        </TALLYMESSAGE>
        <TALLYMESSAGE>
          <VOUCHER VCHTYPE="Sales">
            <VOUCHERNUMBER>TALLY-INV-101</VOUCHERNUMBER>
            <DATE>20260401</DATE>
            <PARTYLEDGERNAME>Bharat Steel Mills</PARTYLEDGERNAME>
            <ALLLEDGERENTRIES.LIST>
              <LEDGERNAME>Bharat Steel Mills</LEDGERNAME>
              <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
              <AMOUNT>-5900.00</AMOUNT>
            </ALLLEDGERENTRIES.LIST>
            <ALLLEDGERENTRIES.LIST>
              <LEDGERNAME>Domestic Sales</LEDGERNAME>
              <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
              <AMOUNT>5000.00</AMOUNT>
            </ALLLEDGERENTRIES.LIST>
            <ALLLEDGERENTRIES.LIST>
              <LEDGERNAME>Output CGST</LEDGERNAME>
              <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
              <AMOUNT>450.00</AMOUNT>
            </ALLLEDGERENTRIES.LIST>
            <ALLLEDGERENTRIES.LIST>
              <LEDGERNAME>Output SGST</LEDGERNAME>
              <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
              <AMOUNT>450.00</AMOUNT>
            </ALLLEDGERENTRIES.LIST>
          </VOUCHER>
        </TALLYMESSAGE>
      </REQUESTDATA>
    </IMPORTDATA>
  </BODY>
</ENVELOPE>"""

class TallyMigrationServiceTests(TestCase):
    def setUp(self):
        self.uid = uuid.uuid4().hex[:8].upper()
        self.company = Company.objects.create(name=f"Migrate Corp {self.uid}")
        self.user = User.objects.create(
            email=f"migrator_{self.uid.lower()}@vouch.test",
            role="ADMIN"
        )

    def test_parse_and_preview_tally_xml(self):
        parsed = TallyMigrationService.parse_tally_xml(SAMPLE_TALLY_XML)
        self.assertEqual(len(parsed["ledgers"]), 2)
        self.assertEqual(len(parsed["stock_items"]), 1)
        self.assertEqual(len(parsed["vouchers"]), 1)

        preview = TallyMigrationService.validate_and_preview(parsed, self.company)
        self.assertTrue(preview["opening_balances"]["is_balanced"])
        self.assertEqual(preview["opening_balances"]["total_debits"], 15000.0)
        self.assertEqual(preview["opening_balances"]["total_credits"], 15000.0)
        self.assertEqual(preview["summary"]["valid_vouchers"], 1)

    def test_execute_migration_and_audit_report(self):
        parsed = TallyMigrationService.parse_tally_xml(SAMPLE_TALLY_XML)
        res = TallyMigrationService.execute_migration(parsed, self.company, self.user)
        self.assertTrue(res["success"])
        report = res["report"]
        self.assertEqual(report["records_created"]["ledgers"], 5)  # 2 parsed + 3 dynamically created for voucher
        self.assertEqual(report["records_created"]["products"], 1)
        self.assertEqual(report["records_created"]["vouchers"], 1)
        self.assertEqual(report["records_created"]["ledger_entries"], 4)
        self.assertEqual(report["reconciliation_status"], "VERIFIED_EQUILIBRIUM")

        # Verify created DB records
        vch = Voucher.objects.get(company=self.company, voucher_number="TALLY-INV-101")
        self.assertEqual(vch.total_amount, Decimal('5900.00'))
        entries = LedgerEntry.objects.filter(voucher=vch)
        dr_sum = sum(e.debit_amount for e in entries)
        cr_sum = sum(e.credit_amount for e in entries)
        self.assertEqual(dr_sum, cr_sum)
        self.assertEqual(dr_sum, Decimal('5900.00'))
