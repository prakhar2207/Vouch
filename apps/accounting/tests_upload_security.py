import io
import zipfile
from decimal import Decimal
import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.models import Company, UserCompany
from apps.accounting.services.tally_migration_service import TallyMigrationService
from apps.accounting.services.universal_import_service import UniversalImportService
from apps.accounting.services.upload_security import (
    MAX_IMPORT_FILE_SIZE,
    UploadValidationError,
    validate_xlsx_zip_bytes,
)
from apps.gst.services.itc_reconciliation_service import ITCReconciliationService


def _build_valid_xlsx_bytes(sheet_title="Sheet1", rows=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title
    for r in (rows or [["Item Name", "MRP", "Rate"], ["Belt A42", "500", "350"]]):
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    wb.close()
    return buf.getvalue()


def _build_zip_bomb_xlsx_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/worksheets/sheet1.xml", b"0" * (52 * 1024 * 1024))
    return buf.getvalue()


def _build_zip_slip_xlsx_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("../../evil.xml", b"<root/>")
    return buf.getvalue()


class Stage124UploadParserSecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="upload_sec@example.com",
            password="StrongPassword!123",
            first_name="Upload",
            last_name="Tester",
            role="OWNER",
            email_verified=True,
        )
        self.company = Company.objects.create(
            name="Apex Belting & Industrial Store (Demo)",
            gstin="09AABCA1234F1Z5",
        )
        UserCompany.objects.create(user=self.user, company=self.company, role="OWNER")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_universal_import_rejects_path_traversal_null_bytes_and_bad_mime(self):
        # Service-level validator blocks any unsanitized traversal paths, null bytes & >255 names directly
        for raw_bad in ["../../evil.csv", "dir/sub.xlsx", r"C:\evil.csv", "..\\bad.xlsx", "bad\x00name.csv", ("a" * 260) + ".csv"]:
            parsed = UniversalImportService.detect_and_parse_file(b"Item,Rate\nA,10", raw_bad)
            self.assertIn("error", parsed)

        # HTTP multipart requests reject '..' filenames and disallowed extensions
        for http_bad in ["..evil.csv", "payload.exe"]:
            f = SimpleUploadedFile(http_bad, b"Item,Rate\nA,10", content_type="text/csv")
            resp = self.client.post(
                "/api/v1/accounting/import/preview/",
                {"file": f, "company_id": str(self.company.id)},
                format="multipart",
            )
            self.assertEqual(resp.status_code, 400, f"Expected 400 for {http_bad!r}, got {resp.status_code}")

        html_upload = SimpleUploadedFile("report.csv", b"<html><script>alert(1)</script></html>", content_type="text/html")
        resp = self.client.post(
            "/api/v1/accounting/import/preview/",
            {"file": html_upload, "company_id": str(self.company.id)},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("MIME", resp.data.get("error", ""))

    def test_universal_import_rejects_empty_oversized_and_spoofed_binary_files(self):
        empty = SimpleUploadedFile("empty.csv", b"", content_type="text/csv")
        resp = self.client.post(
            "/api/v1/accounting/import/preview/",
            {"file": empty, "company_id": str(self.company.id)},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 400)

        exe_as_csv = SimpleUploadedFile("payload.csv", b"MZ\x90\x00executable", content_type="text/csv")
        resp = self.client.post(
            "/api/v1/accounting/import/preview/",
            {"file": exe_as_csv, "company_id": str(self.company.id)},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 400)

        oversized = SimpleUploadedFile(
            "huge.csv",
            b"a" * (MAX_IMPORT_FILE_SIZE + 10),
            content_type="text/csv",
        )
        resp = self.client.post(
            "/api/v1/accounting/import/preview/",
            {"file": oversized, "company_id": str(self.company.id)},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 400)

    def test_xlsx_zip_bomb_zip_slip_and_corrupt_archives_blocked_before_openpyxl(self):
        bomb = _build_zip_bomb_xlsx_bytes()
        with self.assertRaises(UploadValidationError):
            validate_xlsx_zip_bytes(bomb)

        parsed_bomb = UniversalImportService.detect_and_parse_file(bomb, "bomb.xlsx")
        self.assertIn("error", parsed_bomb)
        self.assertTrue("50MB" in parsed_bomb["error"] or "ZIP bomb" in parsed_bomb["error"])

        slip = _build_zip_slip_xlsx_bytes()
        parsed_slip = UniversalImportService.detect_and_parse_file(slip, "slip.xlsx")
        self.assertIn("error", parsed_slip)
        self.assertIn("Unsafe path", parsed_slip["error"])

        corrupt = b"PK\x03\x04corrupted_not_a_real_zip_body"
        parsed_corrupt = UniversalImportService.detect_and_parse_file(corrupt, "corrupt.xlsx")
        self.assertIn("error", parsed_corrupt)

    def test_tally_xml_blocks_xxe_doctype_and_entity_expansion(self):
        xxe = (
            '<?xml version="1.0"?>'
            '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            '<ENVELOPE><BODY>&xxe;</BODY></ENVELOPE>'
        )
        parsed = UniversalImportService.detect_and_parse_file(xxe.encode("utf-8"), "tally.xml")
        self.assertIn("error", parsed)
        self.assertIn("DOCTYPE/ENTITY", parsed["error"])

        with self.assertRaises(UploadValidationError):
            TallyMigrationService.parse_tally_xml(xxe)

    def test_gstr2b_excel_and_universal_xlsx_happy_paths_and_malformed_error_sanitization(self):
        # Malformed JSON via GSTR-2B upload should not leak stack/exception internals
        bad_json = SimpleUploadedFile("gstr2b.json", b"{not_valid_json", content_type="application/json")
        resp_bad = self.client.post(
            "/api/v1/gst/itc/upload-2b/",
            {"file": bad_json, "return_period": "042026"},
            HTTP_X_COMPANY_ID=str(self.company.id),
            format="multipart",
        )
        self.assertEqual(resp_bad.status_code, 400)
        self.assertNotIn("Traceback", str(resp_bad.data))

        # GSTR-2B ZIP bomb blocked cleanly
        bomb = _build_zip_bomb_xlsx_bytes()
        with self.assertRaises(UploadValidationError):
            ITCReconciliationService.ingest_gstr2b_excel(
                company=self.company,
                file_obj=io.BytesIO(bomb),
                user=self.user,
                file_name="bomb_2b.xlsx",
                return_period="042026",
            )

        # Valid GSTR-2B Excel still parses cleanly in streaming read_only=True mode
        valid_2b = _build_valid_xlsx_bytes(
            sheet_title="B2B",
            rows=[
                ["GSTIN of supplier", "Legal Name", "Invoice number", "Invoice date", "Invoice Value", "Taxable Value", "Integrated Tax"],
                ["27AAACP1234A1Z5", "Continental Belts", "INV-2B-001", "10-04-2026", "11800", "10000", "1800"],
            ],
        )
        batch = ITCReconciliationService.ingest_gstr2b_excel(
            company=self.company,
            file_obj=io.BytesIO(valid_2b),
            user=self.user,
            file_name="valid_2b.xlsx",
            return_period="042026",
        )
        self.assertEqual(batch.total_invoices_count, 1)
        self.assertEqual(batch.total_taxable_amount, Decimal("10000"))
        self.assertEqual(batch.total_itc_available, Decimal("1800"))

        # Valid universal XLSX preview
        valid_items = _build_valid_xlsx_bytes(
            sheet_title="Items",
            rows=[["Item Name", "Selling Price", "Purchase Price"], ["Fenner Belt B52", "650", "455"]],
        )
        xlsx_file = SimpleUploadedFile(
            "items.xlsx",
            valid_items,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp_ok = self.client.post(
            "/api/v1/accounting/import/preview/",
            {"file": xlsx_file, "company_id": str(self.company.id)},
            format="multipart",
        )
        self.assertEqual(resp_ok.status_code, 200)
        self.assertTrue(resp_ok.data.get("success"))
