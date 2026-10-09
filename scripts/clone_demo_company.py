import os
import sys
import uuid
import re
import datetime
from decimal import Decimal

# Setup Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.db import transaction
from django.contrib.auth import get_user_model
from apps.companies.models import Company, UserCompany, CompanySettings
from apps.gst.models import CompanyGSTConfig, GSTFilingRecord
from apps.inventory.models import Warehouse, ProductCategory, Product, InventoryEntry
from apps.ledgers.models import LedgerGroup, Ledger
from apps.accounting.models import (
    FinancialYear, VoucherSequence, Voucher, VoucherItem,
    LedgerEntry, PaymentAllocation, BankStatementImport,
    BankTransaction, PartyMapping, ProformaInvoice, ProformaItem,
    AccountingFinding
)

User = get_user_model()

SOURCE_COMPANY_ID = "5d2e5dea-ff86-4871-b2af-fe1c5a05c03c"
TARGET_COMPANY_NAME = "Apex Belting & Industrial Store (Demo)"

PARTY_MAPPING = {
    # Sundry Creditors (Suppliers)
    "NEUTRAL BEARING CENTRE": {
        "name": "NATIONAL BEARING CENTRE",
        "gstin": "09AAAPN1234B1Z2",
        "pan": "AAAPN1234B",
        "state_code": "09",
        "phone": "9839011111",
        "email": "sales@nationalbearing.example.com",
        "address": "Shop 14, Bearing Market, Kanpur - 208001"
    },
    "OM SALES CORPORATION": {
        "name": "OM SHREE TRADING CORPORATION",
        "gstin": "09AAAPO5678C1Z4",
        "pan": "AAAPO5678C",
        "state_code": "09",
        "phone": "9839022222",
        "email": "contact@omshreetrading.example.com",
        "address": "12/480, Macrobert Ganj, Kanpur - 208001"
    },
    "SHREE ADINATH TRADERS": {
        "name": "SHREE ARYAVART TRADERS",
        "gstin": "07AAAPS9012D1Z6",
        "pan": "AAAPS9012D",
        "state_code": "07",
        "phone": "9811033333",
        "email": "orders@shreearyavart.example.com",
        "address": "402, Naya Bazar, Delhi - 110006"
    },
    "Satyam & Co.": {
        "name": "Sovereign & Co.",
        "gstin": "09AAAPS3456E1Z8",
        "pan": "AAAPS3456E",
        "state_code": "09",
        "phone": "9839044444",
        "email": "info@sovereignco.example.com",
        "address": "22, Latouche Road, Kanpur - 208001"
    },
    "Vardhman Belting Udyog": {
        "name": "Vardaan Industrial Belting",
        "gstin": "09AAAPV7890F1Z0",
        "pan": "AAAPV7890F",
        "state_code": "09",
        "phone": "9839055555",
        "email": "sales@vardaanbelting.example.com",
        "address": "D-18, Site-1, Panki Industrial Area, Kanpur - 208022"
    },

    # Sundry Debtors (Customers)
    "Adriti Polyplast": {
        "name": "Apex Polychem Industries",
        "gstin": "09AAAPA1111A1Z1",
        "pan": "AAAPA1111A",
        "state_code": "09",
        "phone": "9820010001",
        "email": "billing@apexpolychem.example.com",
        "address": "Plot 12, Panki Site 4, Kanpur - 208022"
    },
    "Aggarwal Enterprises": {
        "name": "Aura Trade Links",
        "gstin": "09AAAPB2222B1Z2",
        "pan": "AAAPB2222B",
        "state_code": "09",
        "phone": "9820010002",
        "email": "accounts@auratrade.example.com",
        "address": "88/142, Chamanganj, Kanpur - 208001"
    },
    "Ajay Machinery": {
        "name": "Ampex Machine Tools",
        "gstin": "22AAAPC3333C1Z3",
        "pan": "AAAPC3333C",
        "state_code": "22",
        "phone": "9820010003",
        "email": "ampex@tools-chhattisgarh.example.com",
        "address": "Industrial Area, Phase 1, Raipur - 492001"
    },
    "Ashray Enterprises": {
        "name": "Avon Technical Solutions",
        "gstin": "09AAAPD4444D1Z4",
        "pan": "AAAPD4444D",
        "state_code": "09",
        "phone": "9820010004",
        "email": "avon@techsolutions.example.com",
        "address": "B-5, Fazalganj Industrial Estate, Kanpur - 208012"
    },
    "Ashwarya Electricals (P) Ltd": {
        "name": "Aster Electrotech (P) Ltd",
        "gstin": "09AAAPE5555E1Z5",
        "pan": "AAAPE5555E",
        "state_code": "09",
        "phone": "9820010005",
        "email": "aster@electrotech.example.com",
        "address": "15, Cooperganj, Kanpur - 208003"
    },
    "Balaji Spices": {
        "name": "Bansal Agro Processors",
        "gstin": "09AAAPF6666F1Z6",
        "pan": "AAAPF6666F",
        "state_code": "09",
        "phone": "9820010006",
        "email": "accounts@bansalagro.example.com",
        "address": "Grain Market, Kanpur - 208001"
    },
    "Bhagwanti Footwear Products": {
        "name": "Brighton Polymer Products",
        "gstin": "09AAAPG7777G1Z7",
        "pan": "AAAPG7777G",
        "state_code": "09",
        "phone": "9820010007",
        "email": "brighton@polymers.example.com",
        "address": "Jajmau Industrial Complex, Kanpur - 208010"
    },
    "C L Agencies": {
        "name": "C M Commercial Agencies",
        "gstin": "09AAAPH8888H1Z8",
        "pan": "AAAPH8888H",
        "state_code": "09",
        "phone": "9820010008",
        "email": "cm@agencies.example.com",
        "address": "Nayaganj, Kanpur - 208001"
    },
    "Classic Pipe Enterprises": {
        "name": "Crestline Piping Solutions",
        "gstin": "09AAAPI9999I1Z9",
        "pan": "AAAPI9999I",
        "state_code": "09",
        "phone": "9820010009",
        "email": "crestline@pipes.example.com",
        "address": "Transport Nagar, Kanpur - 208023"
    },
    "Galaxy Packaing": {
        "name": "Global Packaging Solutions",
        "gstin": "09AAAPJ1010J1Z0",
        "pan": "AAAPJ1010J",
        "state_code": "09",
        "phone": "9820010010",
        "email": "globalpack@solutions.example.com",
        "address": "Dada Nagar Industrial Area, Kanpur - 208022"
    },
    "Global Enterprises": {
        "name": "Greenfield Enterprises",
        "gstin": "09AAAPK1212K1Z1",
        "pan": "AAAPK1212K",
        "state_code": "09",
        "phone": "9820010011",
        "email": "greenfield@enterprises.example.com",
        "address": "Panki Site 1, Kanpur - 208022"
    },
    "Globus Plastic India Pvt. Ltd.": {
        "name": "Genesis Polymers India Pvt. Ltd.",
        "gstin": "09AAAPL1313L1Z2",
        "pan": "AAAPL1313L",
        "state_code": "09",
        "phone": "9820010012",
        "email": "genesis@polymersindia.example.com",
        "address": "Plot 88, Rania Industrial Estate, Kanpur Dehat - 209304"
    },
    "Goodrich Industries": {
        "name": "Goldcrest Industrial Works",
        "gstin": "09AAAPM1414M1Z3",
        "pan": "AAAPM1414M",
        "state_code": "09",
        "phone": "9820010013",
        "email": "goldcrest@works.example.com",
        "address": "Fazalganj, Kanpur - 208012"
    },
    "Govardhan Trading Company": {
        "name": "Ganesh Trading Company",
        "gstin": "09AAAPN1515N1Z4",
        "pan": "AAAPN1515N",
        "state_code": "09",
        "phone": "9820010014",
        "email": "ganesh@trading.example.com",
        "address": "Collectorganj, Kanpur - 208001"
    },
    "Himangi Foods Pvt. Ltd.": {
        "name": "Horizon Agro Foods Pvt. Ltd.",
        "gstin": "09AAAPO1616O1Z5",
        "pan": "AAAPO1616O",
        "state_code": "09",
        "phone": "9820010015",
        "email": "horizon@agrofoods.example.com",
        "address": "Food Park, Panki, Kanpur - 208022"
    },
    "IND First Choice": {
        "name": "India Prime Hardware",
        "gstin": "09AAAPP1717P1Z6",
        "pan": "AAAPP1717P",
        "state_code": "09",
        "phone": "9820010016",
        "email": "prime@indiahw.example.com",
        "address": "Birhana Road, Kanpur - 208001"
    },
    "KAVYA ENTERPRISES": {
        "name": "KALYAN ENTERPRISES",
        "gstin": "09AAAQQ1818Q1Z7",
        "pan": "AAAQQ1818Q",
        "state_code": "09",
        "phone": "9820010017",
        "email": "kalyan@enterprises.example.com",
        "address": "Govind Nagar, Kanpur - 208006"
    },
    "Karishma Trading Company": {
        "name": "Kusum Trading Company",
        "gstin": "09AAARR1919R1Z8",
        "pan": "AAARR1919R",
        "state_code": "09",
        "phone": "9820010018",
        "email": "kusum@trading.example.com",
        "address": "Gumti No. 5, Kanpur - 208012"
    },
    "Khawaja Eng. Works": {
        "name": "Kohinoor Engineering Works",
        "gstin": "09AAASS2020S1Z9",
        "pan": "AAASS2020S",
        "state_code": "09",
        "phone": "9820010019",
        "email": "kohinoor@engworks.example.com",
        "address": "Chamanganj, Kanpur - 208001"
    },
    "Krishna Engineering": {
        "name": "Kamal Machine & Tool Co.",
        "gstin": "09AAATT2121T1Z0",
        "pan": "AAATT2121T",
        "state_code": "09",
        "phone": "9820010020",
        "email": "kamal@machinetool.example.com",
        "address": "Fazalganj Factory Area, Kanpur - 208012"
    },
    "M W R PIPES": {
        "name": "MODERN WATER PIPING LTD",
        "gstin": "09AAAUU2222U1Z1",
        "pan": "AAAUU2222U",
        "state_code": "09",
        "phone": "9820010021",
        "email": "modern@waterpipes.example.com",
        "address": "50 G, Ispat Nagar, Panki, Kanpur - 208022"
    },
    "M. L. Tradeing company": {
        "name": "M. K. Trading Company",
        "gstin": "09AAAVV2323V1Z2",
        "pan": "AAAVV2323V",
        "state_code": "09",
        "phone": "9820010022",
        "email": "mk@tradingco.example.com",
        "address": "Nayaganj, Kanpur - 208001"
    },
    "Maa Vindhyvasini Traders": {
        "name": "Maa Gayatri Trading Corporation",
        "gstin": "09AAAWW2424W1Z3",
        "pan": "AAAWW2424W",
        "state_code": "09",
        "phone": "9820010023",
        "email": "gayatri@traders.example.com",
        "address": "Kidwai Nagar, Kanpur - 208011"
    },
    "Mahaveer Plastics": {
        "name": "Mayur Industrial Plastics",
        "gstin": "09AAAYY2525X1Z4",
        "pan": "AAAYY2525X",
        "state_code": "09",
        "phone": "9820010024",
        "email": "mayur@plastics.example.com",
        "address": "Dada Nagar, Kanpur - 208022"
    },
    "Om Enterprises": {
        "name": "Orbit Sales Corporation",
        "gstin": "09AAAZZ2626Y1Z5",
        "pan": "AAAZZ2626Y",
        "state_code": "09",
        "phone": "9820010025",
        "email": "orbit@salescorp.example.com",
        "address": "Sharda Nagar, Kanpur - 208025"
    },
    "P.S. Platstic": {
        "name": "Paramount Polymers",
        "gstin": "",
        "pan": "",
        "state_code": "09",
        "phone": "9820010026",
        "email": "paramount@polymers.example.com",
        "address": "Panki Site 3, Kanpur - 208022"
    },
    "Panem Industries Pvt. Ltd.": {
        "name": "Premier Industrial Works Pvt. Ltd.",
        "gstin": "09AAABA2727Z1Z6",
        "pan": "AAABA2727Z",
        "state_code": "09",
        "phone": "9820010027",
        "email": "premier@indworks.example.com",
        "address": "UPSIDC Industrial Area, Kanpur - 208022"
    },
    "Prasad udyog": {
        "name": "Prabhat Industrial Udyog",
        "gstin": "09AAABB2828A1Z7",
        "pan": "AAABB2828A",
        "state_code": "09",
        "phone": "9820010028",
        "email": "prabhat@udyog.example.com",
        "address": "Fazalganj, Kanpur - 208012"
    },
    "Riya Plastic": {
        "name": "Regal Plastotech Solutions",
        "gstin": "09AAABC2929B1Z8",
        "pan": "AAABC2929B",
        "state_code": "09",
        "phone": "9820010029",
        "email": "regal@plastotech.example.com",
        "address": "Rania, Kanpur Dehat - 209304"
    },
    "S. R. Industries": {
        "name": "Shiva Precision Industries",
        "gstin": "09AAABD3030C1Z9",
        "pan": "AAABD3030C",
        "state_code": "09",
        "phone": "9820010030",
        "email": "shiva@precision.example.com",
        "address": "Site 2, Panki, Kanpur - 208022"
    },
    "SKAK Industries LLP": {
        "name": "Sterling K-Tech Industries LLP",
        "gstin": "09AAABE3131D1Z0",
        "pan": "AAABE3131D",
        "state_code": "09",
        "phone": "9820010031",
        "email": "sterling@ktech.example.com",
        "address": "Industrial Corridor, Kanpur - 208020"
    },
    "Saksham Enterprises & Fabricaters": {
        "name": "Sankalp Fabrication & Engineering",
        "gstin": "09AAABF3232E1Z1",
        "pan": "AAABF3232E",
        "state_code": "09",
        "phone": "9820010032",
        "email": "sankalp@fabeng.example.com",
        "address": "Transport Nagar, Kanpur - 208023"
    },
    "Sambasiva Enterprises": {
        "name": "Surya Precision Tools",
        "gstin": "37AAABG3333F1Z2",
        "pan": "AAABG3333F",
        "state_code": "37",
        "phone": "9820010033",
        "email": "surya@precisiontools.example.com",
        "address": "Auto Nagar, Vijayawada - 520007"
    },
    "Saraf Fincom Pvt Ltd.": {
        "name": "Summit Commercials Pvt. Ltd.",
        "gstin": "09AAABH3434G1Z3",
        "pan": "AAABH3434G",
        "state_code": "09",
        "phone": "9820010034",
        "email": "summit@commercials.example.com",
        "address": "Civil Lines, Kanpur - 208001"
    },
    "Shree Balaji Products": {
        "name": "Shree Ram Industrial Products",
        "gstin": "09AAABI3535H1Z4",
        "pan": "AAABI3535H",
        "state_code": "09",
        "phone": "9820010035",
        "email": "shreeram@indproducts.example.com",
        "address": "Panki Site 3, Kanpur - 208022"
    },
    "Shree Tirupati Plastics": {
        "name": "Shree Venkatesh Polymers",
        "gstin": "09AAABJ3636I1Z5",
        "pan": "AAABJ3636I",
        "state_code": "09",
        "phone": "9820010036",
        "email": "venkatesh@polymers.example.com",
        "address": "Dada Nagar, Kanpur - 208022"
    },
    "Shri Bhagyavanti Enterprises": {
        "name": "Shri Bharat Dynamics",
        "gstin": "29AAABK3737J1Z6",
        "pan": "AAABK3737J",
        "state_code": "29",
        "phone": "9820010037",
        "email": "bharat@dynamics-ka.example.com",
        "address": "Peenya Industrial Area, Bengaluru - 560058"
    },
    "Shyam Products": {
        "name": "Shivam Engineering Products",
        "gstin": "09AAABL3838K1Z7",
        "pan": "AAABL3838K",
        "state_code": "09",
        "phone": "9820010038",
        "email": "shivam@engproducts.example.com",
        "address": "Fazalganj, Kanpur - 208012"
    },
    "Som Disposable LLP": {
        "name": "Star Green Pack LLP",
        "gstin": "09AAABM3939L1Z8",
        "pan": "AAABM3939L",
        "state_code": "09",
        "phone": "9820010039",
        "email": "star@greenpack.example.com",
        "address": "Industrial Area, Rania - 209304"
    },
    "Sri Siddhi Vinayak Papad Udyog": {
        "name": "Suraj Food Products",
        "gstin": "09AAABN4040M1Z9",
        "pan": "AAABN4040M",
        "state_code": "09",
        "phone": "9820010040",
        "email": "suraj@foodproducts.example.com",
        "address": "Panki Site 1, Kanpur - 208022"
    },
    "Talwar Industries": {
        "name": "Trident Fasteners & Industries",
        "gstin": "09AAABO4141N1Z0",
        "pan": "AAABO4141N",
        "state_code": "09",
        "phone": "9820010041",
        "email": "trident@industries.example.com",
        "address": "Site 4, Panki Industrial Area, Kanpur - 208022"
    },
    "Unique Traders": {
        "name": "Universal Bearing & Mill Store",
        "gstin": "09AAABP4242O1Z1",
        "pan": "AAABP4242O",
        "state_code": "09",
        "phone": "9820010042",
        "email": "universal@millstore.example.com",
        "address": "Latouche Road, Kanpur - 208001"
    },
}

# String sanitization helper
def sanitize_text(text):
    if not text:
        return text
    s = str(text)
    # Replace company details
    s = re.sub(r"Maa\s+Annapurna\s+Belting\s+Store", "Apex Belting & Industrial Store", s, flags=re.IGNORECASE)
    s = re.sub(r"Maa\s+Annapurna", "Apex Belting", s, flags=re.IGNORECASE)
    s = re.sub(r"Ranjana\s+Shukla", "Rajesh Sharma", s, flags=re.IGNORECASE)
    s = s.replace("6386623787", "9876543210")
    s = s.replace("09CIFPS1329P2ZL", "09AAACA1234A1Z5")
    s = s.replace("CIFPS1329P", "AAACA1234A")
    s = s.replace("125008094288", "50200012345678")
    s = s.replace("CNRB0003827", "HDFC0001234")
    s = s.replace("m.annapurnabeltingstore@gmail.com", "demo@apexbelting.in")

    # Replace each party name
    for old_name, dummy_info in PARTY_MAPPING.items():
        if old_name in s:
            s = s.replace(old_name, dummy_info["name"])
        old_upper = old_name.upper()
        if old_upper in s:
            s = s.replace(old_upper, dummy_info["name"].upper())

    return s


def run_clone():
    print("=" * 60)
    print("Starting cloning of Maa Annapurna Belting Store -> Demo Company")
    print("=" * 60)

    with transaction.atomic():
        src_company = Company.objects.get(id=SOURCE_COMPANY_ID)
        print(f"Source Company: {src_company.name} (ID: {src_company.id})")

        # 1. Clean up existing target company if present
        existing_target = Company.objects.filter(name=TARGET_COMPANY_NAME).first()
        if existing_target:
            print(f"Removing existing target demo company {existing_target.id} for fresh clean clone...")
            existing_target.delete()

        # 2. Create Target Company
        target_company = Company.objects.create(
            name=TARGET_COMPANY_NAME,
            legal_name="Apex Belting & Industrial Store Private Limited",
            gstin="09AAACA1234A1Z5",
            pan="AAACA1234A",
            state_code="09",
            state_name="Uttar Pradesh",
            address="Plot 42, Phase-2, Industrial Area, Kanpur Nagar - 208022",
            city="Kanpur Nagar",
            pincode="208022",
            email="demo@apexbelting.in",
            phone="9876543210",
            financial_year_start=src_company.financial_year_start or datetime.date(2026, 4, 1),
            proprietor_name="Rajesh Sharma",
            proprietor_phone="9876543210",
            signature_data=src_company.signature_data,
            logo_data=src_company.logo_data,
            stamp_data=src_company.stamp_data,
            bank_name="HDFC Bank",
            bank_account_number="50200012345678",
            bank_ifsc="HDFC0001234",
            bank_branch="Industrial Estate Branch",
            upi_id="apexbelting@okhdfcbank",
            website="https://apexbelting.demo",
            tagline="Quality Industrial Transmission & Conveyor Solutions",
            is_active=True,
        )
        print(f"Created Target Company: {target_company.name} (ID: {target_company.id})")

        # 3. Create UserCompany links
        users_to_link = [
            ("m.annapurnabeltingstore@gmail.com", "OWNER"),
            ("shuklaarun520@gmail.com", "CA")
        ]
        for email, role in users_to_link:
            try:
                user_obj = User.objects.get(email=email)
                UserCompany.objects.get_or_create(
                    user=user_obj,
                    company=target_company,
                    defaults={"role": role}
                )
                print(f"Linked user {email} as {role} to target company.")
            except User.DoesNotExist:
                print(f"User {email} not found, skipping.")

        # 4. Clone CompanySettings & CompanyGSTConfig
        src_settings = CompanySettings.objects.filter(company=src_company).first()
        if src_settings:
            CompanySettings.objects.update_or_create(
                company=target_company,
                defaults={
                    "sales_invoice_prefix": src_settings.sales_invoice_prefix,
                    "purchase_invoice_prefix": src_settings.purchase_invoice_prefix,
                    "allow_negative_stock": src_settings.allow_negative_stock,
                    "complexity_level": src_settings.complexity_level,
                    "enable_ledger_mapping": src_settings.enable_ledger_mapping,
                    "enable_manual_invoice_number": src_settings.enable_manual_invoice_number,
                    "enable_advanced_item_creation": src_settings.enable_advanced_item_creation,
                    "enforce_credit_limit": src_settings.enforce_credit_limit,
                    "books_lock_date": src_settings.books_lock_date,
                    "document_branding": src_settings.document_branding,
                }
            )
            print("Cloned CompanySettings.")

        src_gst = CompanyGSTConfig.objects.filter(company=src_company).first()
        if src_gst:
            CompanyGSTConfig.objects.update_or_create(
                company=target_company,
                defaults={
                    "provider": src_gst.provider,
                    "is_sandbox": src_gst.is_sandbox,
                    "api_key": src_gst.api_key,
                    "api_secret": src_gst.api_secret,
                }
            )
            print("Cloned CompanyGSTConfig.")

        # 5. Clone FinancialYears
        fy_map = {}
        for src_fy in FinancialYear.objects.filter(company=src_company).order_by("start_date"):
            new_fy = FinancialYear.objects.create(
                company=target_company,
                name=src_fy.name,
                code=src_fy.code,
                start_date=src_fy.start_date,
                end_date=src_fy.end_date,
                is_closed=src_fy.is_closed,
                is_split_archived=src_fy.is_split_archived,
            )
            fy_map[src_fy.id] = new_fy
        print(f"Cloned {len(fy_map)} FinancialYear records.")

        # 6. Clone Warehouses
        wh_map = {}
        for src_wh in Warehouse.objects.filter(company=src_company):
            new_wh = Warehouse.objects.create(
                company=target_company,
                name=src_wh.name,
                address="Plot 42, Phase-2, Industrial Area, Kanpur Nagar - 208022",
                is_active=src_wh.is_active,
            )
            wh_map[src_wh.id] = new_wh
        print(f"Cloned {len(wh_map)} Warehouse records.")

        # 7. Clone ProductCategory
        cat_map = {}
        for src_cat in ProductCategory.objects.filter(company=src_company):
            new_cat = ProductCategory.objects.create(
                company=target_company,
                name=src_cat.name,
                hsn_code=src_cat.hsn_code,
                gst_rate=src_cat.gst_rate,
            )
            cat_map[src_cat.id] = new_cat
        print(f"Cloned {len(cat_map)} ProductCategory records.")

        # 8. Clone Products (1008 products)
        prod_map = {}
        products_to_create = []
        for src_prod in Product.objects.filter(company=src_company):
            new_id = uuid.uuid4()
            new_prod = Product(
                id=new_id,
                company=target_company,
                category=cat_map.get(src_prod.category_id),
                name=src_prod.name,
                brand=src_prod.brand,
                alias=src_prod.alias,
                sku=src_prod.sku,
                barcode=src_prod.barcode,
                description=src_prod.description,
                unit=src_prod.unit,
                alternate_unit=src_prod.alternate_unit,
                conversion_factor=src_prod.conversion_factor,
                hsn_code=src_prod.hsn_code,
                gst_rate=src_prod.gst_rate,
                tax_override=src_prod.tax_override,
                override_hsn_code=src_prod.override_hsn_code,
                override_gst_rate=src_prod.override_gst_rate,
                selling_price=src_prod.selling_price,
                wholesaler_price=src_prod.wholesaler_price,
                min_selling_price=src_prod.min_selling_price,
                purchase_price=src_prod.purchase_price,
                purchase_price_from_invoice=src_prod.purchase_price_from_invoice,
                stock_quantity=src_prod.stock_quantity,
                reorder_level=src_prod.reorder_level,
                track_batches=src_prod.track_batches,
                track_serial_numbers=src_prod.track_serial_numbers,
                costing_method=src_prod.costing_method,
                is_active=src_prod.is_active,
            )
            products_to_create.append(new_prod)
            prod_map[src_prod.id] = new_prod

        Product.objects.bulk_create(products_to_create, batch_size=500)
        print(f"Cloned {len(products_to_create)} Product records.")

        # 9. Clone LedgerGroups
        grp_map = {}
        for src_grp in LedgerGroup.objects.filter(company=src_company):
            new_grp = LedgerGroup.objects.create(
                company=target_company,
                name=src_grp.name,
                nature=src_grp.nature,
            )
            grp_map[src_grp.id] = new_grp
        print(f"Cloned {len(grp_map)} LedgerGroup records.")

        # 10. Clone Ledgers (67 records)
        ledger_map = {}
        for src_l in Ledger.objects.filter(company=src_company):
            grp = grp_map.get(src_l.group_id)
            old_name = src_l.name.strip()

            if old_name in PARTY_MAPPING:
                dummy_info = PARTY_MAPPING[old_name]
                new_name = dummy_info["name"]
                new_gstin = dummy_info["gstin"]
                new_pan = dummy_info["pan"]
                new_phone = dummy_info["phone"]
                new_email = dummy_info["email"]
                new_address = dummy_info["address"]
                new_state = dummy_info["state_code"]
                new_bank_acc = None
                new_bank_ifsc = None
                new_upi = None
            elif "State Bank of India" in old_name:
                new_name = "State Bank of India ( 4321)"
                new_gstin = ""
                new_pan = ""
                new_phone = ""
                new_email = ""
                new_address = "Civil Lines Branch, Kanpur"
                new_state = "09"
                new_bank_acc = "389211004321"
                new_bank_ifsc = "SBIN0004321"
                new_upi = "apexbelting@sbi"
            elif "Canara Bank" in old_name:
                new_name = "HDFC Bank (A/c ...5678)"
                new_gstin = ""
                new_pan = ""
                new_phone = ""
                new_email = ""
                new_address = "Industrial Estate Branch, Kanpur"
                new_state = "09"
                new_bank_acc = "50200012345678"
                new_bank_ifsc = "HDFC0001234"
                new_upi = "apexbelting@okhdfcbank"
            else:
                # Nominal/system ledgers
                new_name = src_l.name
                new_gstin = src_l.gstin
                new_pan = src_l.pan
                new_phone = src_l.phone
                new_email = src_l.email
                new_address = src_l.address
                new_state = src_l.state_code
                new_bank_acc = src_l.bank_account_number
                new_bank_ifsc = src_l.bank_ifsc
                new_upi = src_l.upi_id

            new_l = Ledger.objects.create(
                company=target_company,
                group=grp,
                name=new_name,
                ledger_type=src_l.ledger_type,
                gstin=new_gstin,
                state_code=new_state,
                opening_balance=src_l.opening_balance,
                opening_balance_type=src_l.opening_balance_type,
                opening_date=src_l.opening_date,
                current_balance=src_l.current_balance,
                credit_limit=src_l.credit_limit,
                credit_period_days=src_l.credit_period_days,
                discount_percent=src_l.discount_percent,
                phone=new_phone,
                email=new_email,
                address=new_address,
                bank_account_number=new_bank_acc,
                bank_ifsc=new_bank_ifsc,
                upi_id=new_upi,
                is_active=src_l.is_active,
                is_archived=src_l.is_archived,
                is_rcm=src_l.is_rcm,
                pan=new_pan,
                tds_applicable=src_l.tds_applicable,
                tds_section=src_l.tds_section,
                tds_rate=src_l.tds_rate,
            )
            ledger_map[src_l.id] = new_l
        print(f"Cloned {len(ledger_map)} Ledger records.")

        # 11. Clone VoucherSequence (14 records)
        vs_count = 0
        for src_vs in VoucherSequence.objects.filter(company=src_company):
            VoucherSequence.objects.create(
                company=target_company,
                financial_year=fy_map.get(src_vs.financial_year_id),
                voucher_type=src_vs.voucher_type,
                method=src_vs.method,
                prefix=src_vs.prefix,
                suffix=src_vs.suffix,
                starting_number=src_vs.starting_number,
                last_number=src_vs.last_number,
                width=src_vs.width,
            )
            vs_count += 1
        print(f"Cloned {vs_count} VoucherSequence records.")

        # 12. Clone Vouchers (361 records)
        voucher_map = {}
        vouchers_to_create = []
        src_vouchers = list(Voucher.objects.filter(company=src_company).order_by("voucher_date", "created_at"))

        for src_v in src_vouchers:
            new_id = uuid.uuid4()

            # Sanitize buyer details if buyer is in party mapping
            buyer_name = src_v.buyer_name or ""
            buyer_gstin = src_v.buyer_gstin or ""
            buyer_state = src_v.buyer_state_code or ""
            buyer_phone = src_v.buyer_phone or ""
            buyer_email = src_v.buyer_email or ""
            buyer_address = src_v.buyer_address or ""

            if buyer_name.strip() in PARTY_MAPPING:
                dm = PARTY_MAPPING[buyer_name.strip()]
                buyer_name = dm["name"]
                buyer_gstin = dm["gstin"]
                buyer_state = dm["state_code"]
                buyer_phone = dm["phone"]
                buyer_email = dm["email"]
                buyer_address = dm["address"]
            else:
                buyer_name = sanitize_text(buyer_name)

            new_v = Voucher(
                id=new_id,
                company=target_company,
                financial_year=fy_map.get(src_v.financial_year_id),
                voucher_type=src_v.voucher_type,
                voucher_number=src_v.voucher_number,
                external_invoice_number=src_v.external_invoice_number,
                is_reverse_charge=src_v.is_reverse_charge,
                tds_section=src_v.tds_section,
                tds_rate=src_v.tds_rate,
                tds_amount=src_v.tds_amount,
                tds_ledger=ledger_map.get(src_v.tds_ledger_id),
                is_advance=src_v.is_advance,
                advance_tax_rate=src_v.advance_tax_rate,
                advance_tax_amount=src_v.advance_tax_amount,
                advance_cgst=src_v.advance_cgst,
                advance_sgst=src_v.advance_sgst,
                advance_igst=src_v.advance_igst,
                advance_adjusted_amount=src_v.advance_adjusted_amount,
                revision_number=src_v.revision_number,
                correction_reason=src_v.correction_reason,
                correction_type=src_v.correction_type,
                voucher_date=src_v.voucher_date,
                due_date=src_v.due_date,
                reference_number=src_v.reference_number,
                party_ledger=ledger_map.get(src_v.party_ledger_id),
                buyer_name=buyer_name,
                buyer_address=buyer_address,
                buyer_gstin=buyer_gstin,
                buyer_state_code=buyer_state,
                buyer_phone=buyer_phone,
                buyer_email=buyer_email,
                itc_match_status=src_v.itc_match_status,
                itc_held_amount=src_v.itc_held_amount,
                itc_notes=src_v.itc_notes,
                narration=sanitize_text(src_v.narration),
                status=src_v.status,
                total_amount=src_v.total_amount,
                attachment_data=src_v.attachment_data,
                attachment_mime=src_v.attachment_mime,
                created_by=src_v.created_by,
            )
            vouchers_to_create.append(new_v)
            voucher_map[src_v.id] = new_v

        Voucher.objects.bulk_create(vouchers_to_create, batch_size=200)
        print(f"Cloned {len(vouchers_to_create)} Voucher records (pass 1).")

        # Second pass: link self-referencing voucher fields
        vouchers_to_update = []
        for src_v in src_vouchers:
            needs_update = False
            new_v = voucher_map[src_v.id]

            if src_v.reversal_voucher_id and src_v.reversal_voucher_id in voucher_map:
                new_v.reversal_voucher = voucher_map[src_v.reversal_voucher_id]
                needs_update = True
            if src_v.corrects_voucher_id and src_v.corrects_voucher_id in voucher_map:
                new_v.corrects_voucher = voucher_map[src_v.corrects_voucher_id]
                needs_update = True
            if src_v.original_invoice_id and src_v.original_invoice_id in voucher_map:
                new_v.original_invoice = voucher_map[src_v.original_invoice_id]
                needs_update = True
            if src_v.revision_of_id and src_v.revision_of_id in voucher_map:
                new_v.revision_of = voucher_map[src_v.revision_of_id]
                needs_update = True
            if src_v.superseded_by_id and src_v.superseded_by_id in voucher_map:
                new_v.superseded_by = voucher_map[src_v.superseded_by_id]
                needs_update = True

            if needs_update:
                vouchers_to_update.append(new_v)

        if vouchers_to_update:
            Voucher.objects.bulk_update(
                vouchers_to_update,
                fields=["reversal_voucher", "corrects_voucher", "original_invoice", "revision_of", "superseded_by"],
                batch_size=100
            )
            print(f"Updated {len(vouchers_to_update)} self-referencing Vouchers.")

        # 13. Clone VoucherItem (472 records)
        items_to_create = []
        for src_item in VoucherItem.objects.filter(voucher__company=src_company):
            new_item = VoucherItem(
                voucher=voucher_map[src_item.voucher_id],
                product=prod_map.get(src_item.product_id),
                warehouse=wh_map.get(src_item.warehouse_id),
                quantity=src_item.quantity,
                rate=src_item.rate,
                discount_percent=src_item.discount_percent,
                discount_amount=src_item.discount_amount,
                taxable_amount=src_item.taxable_amount,
                gst_rate=src_item.gst_rate,
                cgst_rate=src_item.cgst_rate,
                sgst_rate=src_item.sgst_rate,
                igst_rate=src_item.igst_rate,
                cess_rate=src_item.cess_rate,
                cgst_amount=src_item.cgst_amount,
                sgst_amount=src_item.sgst_amount,
                igst_amount=src_item.igst_amount,
                cess_amount=src_item.cess_amount,
                hsn_code=src_item.hsn_code,
                total_amount=src_item.total_amount,
            )
            items_to_create.append(new_item)

        VoucherItem.objects.bulk_create(items_to_create, batch_size=500)
        print(f"Cloned {len(items_to_create)} VoucherItem records.")

        # 14. Clone LedgerEntry (1289 records)
        entries_to_create = []
        for src_le in LedgerEntry.objects.filter(company=src_company):
            new_le = LedgerEntry(
                company=target_company,
                voucher=voucher_map[src_le.voucher_id],
                ledger=ledger_map[src_le.ledger_id],
                debit_amount=src_le.debit_amount,
                credit_amount=src_le.credit_amount,
                narration=sanitize_text(src_le.narration),
            )
            entries_to_create.append(new_le)

        LedgerEntry.objects.bulk_create(entries_to_create, batch_size=500)
        print(f"Cloned {len(entries_to_create)} LedgerEntry records.")

        # 15. Clone InventoryEntry (810 records)
        inv_to_create = []
        for src_ie in InventoryEntry.objects.filter(company=src_company):
            new_v_id = voucher_map[src_ie.voucher_id].id if src_ie.voucher_id in voucher_map else src_ie.voucher_id
            new_ie = InventoryEntry(
                company=target_company,
                product=prod_map[src_ie.product_id],
                warehouse=wh_map.get(src_ie.warehouse_id),
                voucher_id=new_v_id,
                movement_type=src_ie.movement_type,
                quantity=src_ie.quantity,
                rate=src_ie.rate,
                total_value=src_ie.total_value,
                batch_number=src_ie.batch_number,
                expiry_date=src_ie.expiry_date,
                serial_number=src_ie.serial_number,
            )
            inv_to_create.append(new_ie)

        InventoryEntry.objects.bulk_create(inv_to_create, batch_size=500)
        print(f"Cloned {len(inv_to_create)} InventoryEntry records.")

        # 16. Clone PaymentAllocation (212 records)
        pa_to_create = []
        for src_pa in PaymentAllocation.objects.filter(company=src_company):
            new_pv = voucher_map.get(src_pa.payment_voucher_id)
            new_iv = voucher_map.get(src_pa.invoice_voucher_id)
            if new_pv and new_iv:
                new_pa = PaymentAllocation(
                    company=target_company,
                    payment_voucher=new_pv,
                    invoice_voucher=new_iv,
                    allocated_amount=src_pa.allocated_amount,
                    adjusted_advance_tax=src_pa.adjusted_advance_tax,
                )
                pa_to_create.append(new_pa)

        PaymentAllocation.objects.bulk_create(pa_to_create, batch_size=200)
        print(f"Cloned {len(pa_to_create)} PaymentAllocation records.")

        # 17. Clone BankStatementImport & BankTransaction (8 imports, 210 transactions)
        stmt_map = {}
        for src_stmt in BankStatementImport.objects.filter(company=src_company):
            new_stmt = BankStatementImport.objects.create(
                company=target_company,
                bank_ledger=ledger_map.get(src_stmt.bank_ledger_id),
                source_file_name=src_stmt.source_file_name,
                file_hash=src_stmt.file_hash,
                file_format=src_stmt.file_format,
                status=src_stmt.status,
                total_rows=src_stmt.total_rows,
                successful_rows=src_stmt.successful_rows,
                unresolved_rows=src_stmt.unresolved_rows,
                failed_rows=src_stmt.failed_rows,
                error_summary=src_stmt.error_summary,
                opening_balance=src_stmt.opening_balance,
                closing_balance=src_stmt.closing_balance,
                calculated_closing_balance=src_stmt.calculated_closing_balance,
                balance_chain_valid=src_stmt.balance_chain_valid,
                discrepancy_amount=src_stmt.discrepancy_amount,
                statement_start_date=src_stmt.statement_start_date,
                statement_end_date=src_stmt.statement_end_date,
                created_by=src_stmt.created_by,
            )
            stmt_map[src_stmt.id] = new_stmt
        print(f"Cloned {len(stmt_map)} BankStatementImport records.")

        bt_to_create = []
        for src_bt in BankTransaction.objects.filter(company=src_company):
            new_bt = BankTransaction(
                company=target_company,
                statement_import=stmt_map.get(src_bt.statement_import_id),
                bank_ledger=ledger_map.get(src_bt.bank_ledger_id),
                transaction_date=src_bt.transaction_date,
                value_date=src_bt.value_date,
                description=sanitize_text(src_bt.description),
                normalized_narration=sanitize_text(src_bt.normalized_narration),
                reference_number=src_bt.reference_number,
                fingerprint=src_bt.fingerprint,
                debit_amount=src_bt.debit_amount,
                credit_amount=src_bt.credit_amount,
                balance=src_bt.balance,
                source_file=src_bt.source_file,
                source_page=src_bt.source_page,
                extraction_confidence=src_bt.extraction_confidence,
                status=src_bt.status,
                is_excluded=src_bt.is_excluded,
                exclusion_reason=src_bt.exclusion_reason,
                matched_party=ledger_map.get(src_bt.matched_party_id),
                matched_voucher=voucher_map.get(src_bt.matched_voucher_id),
                matched_invoice=voucher_map.get(src_bt.matched_invoice_id),
                match_confidence=src_bt.match_confidence,
                match_notes=src_bt.match_notes,
            )
            bt_to_create.append(new_bt)

        BankTransaction.objects.bulk_create(bt_to_create, batch_size=200)
        print(f"Cloned {len(bt_to_create)} BankTransaction records.")

        # 18. Clone PartyMapping (9 records)
        pm_count = 0
        for src_pm in PartyMapping.objects.filter(company=src_company):
            PartyMapping.objects.create(
                company=target_company,
                pattern=src_pm.pattern,
                normalized_pattern=src_pm.normalized_pattern,
                party=ledger_map[src_pm.party_id],
                mapping_type=src_pm.mapping_type,
                confirmed_by_user=src_pm.confirmed_by_user,
                confidence=src_pm.confidence,
                usage_count=src_pm.usage_count,
            )
            pm_count += 1
        print(f"Cloned {pm_count} PartyMapping records.")

        # 19. Clone ProformaInvoice & ProformaItem (1 record)
        for src_pi in ProformaInvoice.objects.filter(company=src_company):
            buyer_name = src_pi.buyer_name or ""
            buyer_gstin = src_pi.buyer_gstin or ""
            buyer_address = src_pi.buyer_address or ""
            if buyer_name.strip() in PARTY_MAPPING:
                dm = PARTY_MAPPING[buyer_name.strip()]
                buyer_name = dm["name"]
                buyer_gstin = dm["gstin"]
                buyer_address = dm["address"]

            new_pi = ProformaInvoice.objects.create(
                company=target_company,
                financial_year=fy_map.get(src_pi.financial_year_id),
                proforma_type=src_pi.proforma_type,
                proforma_number=src_pi.proforma_number,
                date=src_pi.date,
                valid_until=src_pi.valid_until,
                party_ledger=ledger_map.get(src_pi.party_ledger_id),
                buyer_name=buyer_name,
                buyer_address=buyer_address,
                buyer_gstin=buyer_gstin,
                buyer_state_code=src_pi.buyer_state_code,
                buyer_phone=src_pi.buyer_phone,
                buyer_email=src_pi.buyer_email,
                subtotal=src_pi.subtotal,
                taxable_amount=src_pi.taxable_amount,
                cgst_amount=src_pi.cgst_amount,
                sgst_amount=src_pi.sgst_amount,
                igst_amount=src_pi.igst_amount,
                total_tax=src_pi.total_tax,
                cartage_amount=src_pi.cartage_amount,
                round_off=src_pi.round_off,
                total_amount=src_pi.total_amount,
                customer_notes=src_pi.customer_notes,
                terms_and_conditions=src_pi.terms_and_conditions,
                status=src_pi.status,
                converted_voucher=voucher_map.get(src_pi.converted_voucher_id),
                converted_at=src_pi.converted_at,
                created_by=src_pi.created_by,
            )
            for src_pitem in ProformaItem.objects.filter(proforma=src_pi):
                ProformaItem.objects.create(
                    proforma=new_pi,
                    product=prod_map.get(src_pitem.product_id),
                    item_name=src_pitem.item_name,
                    hsn_code=src_pitem.hsn_code,
                    quantity=src_pitem.quantity,
                    unit=src_pitem.unit,
                    rate=src_pitem.rate,
                    discount_percent=src_pitem.discount_percent,
                    taxable_amount=src_pitem.taxable_amount,
                    gst_rate=src_pitem.gst_rate,
                    cgst_rate=src_pitem.cgst_rate,
                    cgst_amount=src_pitem.cgst_amount,
                    sgst_rate=src_pitem.sgst_rate,
                    sgst_amount=src_pitem.sgst_amount,
                    igst_rate=src_pitem.igst_rate,
                    igst_amount=src_pitem.igst_amount,
                    total_amount=src_pitem.total_amount,
                )
        print("Cloned ProformaInvoice and ProformaItem records.")

        # 20. Clone GSTFilingRecord (4 records)
        gst_count = 0
        for src_g in GSTFilingRecord.objects.filter(company=src_company):
            GSTFilingRecord.objects.create(
                company=target_company,
                return_type=src_g.return_type,
                return_period=src_g.return_period,
                financial_year=src_g.financial_year,
                status=src_g.status,
                arn=src_g.arn,
                provider_reference=src_g.provider_reference,
                payload_hash=src_g.payload_hash,
                total_taxable_value=src_g.total_taxable_value,
                total_tax_amount=src_g.total_tax_amount,
                invoices_count=src_g.invoices_count,
                filing_mode=src_g.filing_mode,
                response_snapshot=src_g.response_snapshot,
                error_message=src_g.error_message,
                submitted_by=src_g.submitted_by,
                submitted_at=src_g.submitted_at,
            )
            gst_count += 1
        print(f"Cloned {gst_count} GSTFilingRecord records.")

        # 21. Clone AccountingFindings (135 records)
        import json
        findings_to_create = []
        for src_af in AccountingFinding.objects.filter(company=src_company):
            ev_data = src_af.evidence
            if isinstance(ev_data, (dict, list)):
                try:
                    ev_str = sanitize_text(json.dumps(ev_data))
                    ev_data = json.loads(ev_str)
                except Exception:
                    ev_data = src_af.evidence

            new_af = AccountingFinding(
                company=target_company,
                severity=src_af.severity,
                category=src_af.category,
                title=sanitize_text(src_af.title),
                description=sanitize_text(src_af.description),
                evidence=ev_data,
                expected_state=sanitize_text(src_af.expected_state),
                actual_state=sanitize_text(src_af.actual_state),
                probable_cause=sanitize_text(src_af.probable_cause),
                suggested_action=sanitize_text(src_af.suggested_action),
                confidence=src_af.confidence,
                fix_action=src_af.fix_action,
                fix_preview=src_af.fix_preview,
                is_resolved=src_af.is_resolved,
                resolved_at=src_af.resolved_at,
                resolved_by=src_af.resolved_by,
            )
            findings_to_create.append(new_af)
        AccountingFinding.objects.bulk_create(findings_to_create, batch_size=200)
        print(f"Cloned {len(findings_to_create)} AccountingFinding records.")

        print("=" * 60)
        print("CLONING TRANSACTION COMPLETED SUCCESSFULLY!")
        print("=" * 60)

        # 22. Verification Checks
        print("\n--- RUNNING INTEGRITY AND LEAK CHECKS ---")
        from django.db.models import Sum

        total_dr = LedgerEntry.objects.filter(company=target_company).aggregate(s=Sum('debit_amount'))['s'] or Decimal('0.00')
        total_cr = LedgerEntry.objects.filter(company=target_company).aggregate(s=Sum('credit_amount'))['s'] or Decimal('0.00')
        print(f"Total Debit : Rs {total_dr:,.2f}")
        print(f"Total Credit: Rs {total_cr:,.2f}")
        print(f"Double-entry balance check: {'BALANCED (Dr == Cr)' if total_dr == total_cr else 'MISMATCH'}")

        # Check for any lingering real names
        leak_found = False
        for old_name in PARTY_MAPPING.keys():
            if Ledger.objects.filter(company=target_company, name__icontains=old_name).exists():
                print(f"WARNING: Leak found in Ledger name: {old_name}")
                leak_found = True
            if Voucher.objects.filter(company=target_company, buyer_name__icontains=old_name).exists():
                print(f"WARNING: Leak found in Voucher buyer_name: {old_name}")
                leak_found = True

        if not leak_found:
            print("Privacy check passed: 0 real party names found in cloned records!")
        else:
            print("Privacy check FAILED!")

        print(f"\nTarget Company ID: {target_company.id}")
        print(f"Target Company Name: {target_company.name}")
        print(f"Products: {Product.objects.filter(company=target_company).count()}")
        print(f"Ledgers: {Ledger.objects.filter(company=target_company).count()}")
        print(f"Vouchers: {Voucher.objects.filter(company=target_company).count()}")
        print(f"Voucher Items: {VoucherItem.objects.filter(voucher__company=target_company).count()}")
        print(f"Ledger Entries: {LedgerEntry.objects.filter(company=target_company).count()}")
        print(f"Inventory Entries: {InventoryEntry.objects.filter(company=target_company).count()}")
        print(f"Payment Allocations: {PaymentAllocation.objects.filter(company=target_company).count()}")
        print("Done!")

if __name__ == "__main__":
    run_clone()
