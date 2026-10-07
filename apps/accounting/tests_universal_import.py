from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.companies.models import Company, UserCompany
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product, ProductCategory
from apps.accounting.services.universal_import_service import (
    UniversalImportService,
    clean_str,
    clean_decimal,
    parse_balance_type,
)

User = get_user_model()


class UniversalImportServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="importer@vouch.com", password="password123")
        self.company = Company.objects.create(name="Universal Test Corp", gstin="27AABCT1234F1Z9")
        UserCompany.objects.create(user=self.user, company=self.company, role="OWNER")

    def test_clean_sanitization_helpers(self):
        """Tests that text and decimal sanitizers never crash on weird formats."""
        self.assertEqual(clean_str("  Apex Traders \n"), "Apex Traders")
        self.assertEqual(clean_str("9876543210.0"), "9876543210")
        self.assertEqual(clean_str(None), "")
        self.assertEqual(clean_str("NaN"), "")
        self.assertEqual(clean_str("-"), "")

        self.assertEqual(clean_decimal("₹ 1,50,000.50"), Decimal("150000.50"))
        self.assertEqual(clean_decimal("Rs. 45,000 Dr"), Decimal("45000.00"))
        self.assertEqual(clean_decimal("(12,500.00)"), Decimal("-12500.00"))
        self.assertEqual(clean_decimal("-5000"), Decimal("-5000.00"))
        self.assertEqual(clean_decimal(""), Decimal("0.00"))
        self.assertEqual(clean_decimal("N/A"), Decimal("0.00"))
        self.assertEqual(clean_decimal(None), Decimal("0.00"))

    def test_parse_balance_types(self):
        """Verifies natural language balance types from Vyapar, myBillBook, and Zoho."""
        self.assertEqual(parse_balance_type("To Receive"), "DEBIT")
        self.assertEqual(parse_balance_type("To Pay"), "CREDIT")
        self.assertEqual(parse_balance_type("To Collect"), "DEBIT")
        self.assertEqual(parse_balance_type("Customer"), "DEBIT")
        self.assertEqual(parse_balance_type("Vendor"), "CREDIT")
        self.assertEqual(parse_balance_type("Supplier"), "CREDIT")
        self.assertEqual(parse_balance_type("", "1000 Dr"), "DEBIT")
        self.assertEqual(parse_balance_type("", "1000 Cr"), "CREDIT")

    def test_vyapar_parties_csv_import(self):
        """Tests parsing and ingesting a simulated Vyapar parties export."""
        vyapar_csv = (
            "Party Name,Phone Number,GSTIN,To Receive / To Pay,Opening Balance,Billing Address\n"
            "Maa Durga Logistics,9876543210,27AABCM1111A1Z1,To Receive,125000.00,Shop 12 Ring Road Pune\n"
            "Balaji Raw Materials,9822000000,27AABCB2222B1Z2,To Pay,45000.00,MIDC Industrial Area\n"
        ).encode("utf-8")

        parsed = UniversalImportService.detect_and_parse_file(vyapar_csv, "Parties.csv")
        self.assertEqual(parsed["platform"], "VYAPAR")
        self.assertEqual(parsed["entity_type"], "PARTIES")
        self.assertEqual(parsed["total_rows"], 2)

        preview = UniversalImportService.generate_preview(parsed, self.company)
        self.assertEqual(preview["valid_records"], 2)
        self.assertEqual(preview["duplicate_records"], 0)
        self.assertEqual(preview["equilibrium"]["total_debits"], 125000.00)
        self.assertEqual(preview["equilibrium"]["total_credits"], 45000.00)

        # Ingest into Vouch
        res = UniversalImportService.execute_import(parsed, self.company, self.user)
        self.assertTrue(res["success"])
        self.assertEqual(res["created_count"], 2)

        # Verify created ledgers
        cust = Ledger.objects.get(company=self.company, name="Maa Durga Logistics")
        self.assertEqual(cust.ledger_type, "CUSTOMER")
        self.assertEqual(cust.opening_balance, Decimal("125000.00"))
        self.assertEqual(cust.opening_balance_type, "DEBIT")
        self.assertEqual(cust.phone, "9876543210")
        self.assertEqual(cust.gstin, "27AABCM1111A1Z1")

        supp = Ledger.objects.get(company=self.company, name="Balaji Raw Materials")
        self.assertEqual(supp.ledger_type, "SUPPLIER")
        self.assertEqual(supp.opening_balance, Decimal("45000.00"))
        self.assertEqual(supp.opening_balance_type, "CREDIT")

    def test_mybillbook_inventory_import(self):
        """Tests parsing and ingesting a simulated myBillBook stock items export."""
        mbb_csv = (
            "Item Name,Item Code,Category,Sales Price,Purchase Price,Opening Stock,Unit,HSN Code,Tax Rate\n"
            "V-Belt B 55 Industrial,SKU-B55,Transmission Belts,350.00,240.00,80,PCS,40103999,18.0%\n"
            "Conveyor Belt Heavy,SKU-CB-H,Conveyors,1200.00,850.00,25,MTR,40101290,18.0%\n"
        ).encode("utf-8")

        parsed = UniversalImportService.detect_and_parse_file(mbb_csv, "Item_List.csv")
        self.assertEqual(parsed["entity_type"], "ITEMS")
        self.assertEqual(parsed["total_rows"], 2)

        res = UniversalImportService.execute_import(parsed, self.company, self.user)
        self.assertTrue(res["success"])
        self.assertEqual(res["created_count"], 2)

        item = Product.objects.get(company=self.company, name="V-Belt B 55 Industrial")
        self.assertEqual(item.sku, "SKU-B55")
        self.assertEqual(item.selling_price, Decimal("350.00"))
        self.assertEqual(item.purchase_price, Decimal("240.00"))
        self.assertEqual(item.stock_quantity, Decimal("80.00"))
        self.assertEqual(item.unit, "PCS")
        self.assertEqual(item.hsn_code, "40103999")

    def test_zoho_books_contacts_import(self):
        """Tests parsing and ingesting a simulated Zoho Books Contacts export."""
        zoho_csv = (
            "Contact Name,Customer / Vendor,GST Identification Number (GSTIN),Phone,Opening Balance\n"
            'Godrej Aerospace Ltd,Customer,27AAACG0000G1Z5,9988776655,"₹ 5,00,000.00"\n'
        ).encode("utf-8")

        parsed = UniversalImportService.detect_and_parse_file(zoho_csv, "Contacts.csv")
        self.assertEqual(parsed["platform"], "ZOHO_BOOKS")
        self.assertEqual(parsed["entity_type"], "PARTIES")

        res = UniversalImportService.execute_import(parsed, self.company, self.user)
        self.assertTrue(res["success"])
        self.assertEqual(res["created_count"], 1)

        godrej = Ledger.objects.get(company=self.company, name="Godrej Aerospace Ltd")
        self.assertEqual(godrej.ledger_type, "CUSTOMER")
        self.assertEqual(godrej.opening_balance, Decimal("500000.00"))
        self.assertEqual(godrej.opening_balance_type, "DEBIT")

    def test_duplicate_merge_protection(self):
        """Ensures importing duplicate contacts safely merges missing fields without crashing."""
        # Pre-create a ledger with only a name
        group = LedgerGroup.objects.create(company=self.company, name="Sundry Debtors", nature="ASSET")
        Ledger.objects.create(
            company=self.company,
            name="Existing Client Traders",
            group=group,
            ledger_type="CUSTOMER",
            opening_balance=Decimal("0.00")
        )

        update_csv = (
            "Party Name,Phone Number,GSTIN,Opening Balance\n"
            "Existing Client Traders,9123456789,27AAACE1234E1Z1,80000.00\n"
        ).encode("utf-8")

        parsed = UniversalImportService.detect_and_parse_file(update_csv, "Parties.csv")
        preview = UniversalImportService.generate_preview(parsed, self.company)
        self.assertEqual(preview["duplicate_records"], 1)

        res = UniversalImportService.execute_import(parsed, self.company, self.user, duplicate_strategy="MERGE")
        self.assertTrue(res["success"])
        self.assertEqual(res["merged_count"], 1)
        self.assertEqual(res["created_count"], 0)

        # Confirm fields were populated into existing record
        updated = Ledger.objects.get(company=self.company, name="Existing Client Traders")
        self.assertEqual(updated.phone, "9123456789")
        self.assertEqual(updated.gstin, "27AAACE1234E1Z1")
