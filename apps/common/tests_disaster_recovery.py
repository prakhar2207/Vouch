import os
import gzip
import shutil
import tempfile
from pathlib import Path
from django.test import TestCase
from django.conf import settings
from apps.common.services.backup_service import DatabaseBackupService
from apps.companies.models import Company
from apps.inventory.models import Product, ProductCategory

class DisasterRecoveryBackupRestoreTestCase(TestCase):
    """
    Validates end-to-end disaster recovery:
    1. Backup creation with AES-256 Fernet encryption & GZIP compression
    2. SHA-256 integrity verification
    3. Decryption and decompression validation
    4. Data restore verification and record matching
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.company = Company.objects.create(
            name="Disaster Recovery Test Corp",
            gstin="27AADCB2230M1Z2"
        )
        self.category = ProductCategory.objects.create(
            company=self.company,
            name="Industrial Bearings"
        )
        self.product = Product.objects.create(
            company=self.company,
            category=self.category,
            name="Deep Groove Ball Bearing 6204",
            sku="BRG-6204-SKF",
            selling_price=450.00,
            purchase_price=320.00,
            stock_quantity=100
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_backup_encryption_checksum_and_restore(self):
        # 1. Execute Backup
        backup_res = DatabaseBackupService.perform_backup(
            upload_s3=False,
            encrypt=True,
            output_dir=self.temp_dir
        )
        self.assertTrue(backup_res["success"], f"Backup failed: {backup_res.get('error')}")
        self.assertTrue(backup_res["is_encrypted"])
        self.assertTrue(os.path.exists(backup_res["file_path"]))

        backup_file = Path(backup_res["file_path"])

        # 2. Verify SHA-256 Checksum
        import hashlib
        sha = hashlib.sha256()
        with open(backup_file, "rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        self.assertEqual(sha.hexdigest(), backup_res["sha256_checksum"])

        # 3. Verify Decryption & Decompression
        unpacked_bytes = DatabaseBackupService.unpack_backup(backup_file)
        self.assertGreater(len(unpacked_bytes), 0)
        self.assertTrue(
            unpacked_bytes.strip().startswith(b"[") or unpacked_bytes.startswith(b"SQLite format 3\x00") or b"BEGIN" in unpacked_bytes or b"CREATE" in unpacked_bytes
        )

        # 4. Dry-run restore
        dry_run_res = DatabaseBackupService.restore_backup(backup_file, target_db_alias="default", dry_run=True)
        self.assertTrue(dry_run_res["success"])
        if dry_run_res["backup_type"] == "DJANGO_JSON_FIXTURE":
            self.assertGreater(dry_run_res["records_restored"], 0)

        # 5. Full restore validation
        restore_res = DatabaseBackupService.restore_backup(backup_file, target_db_alias="default", dry_run=False)
        self.assertTrue(restore_res["success"])

        # 6. Verify restored record integrity
        refreshed_prod = Product.objects.get(id=self.product.id)
        self.assertEqual(refreshed_prod.name, "Deep Groove Ball Bearing 6204")
        self.assertEqual(refreshed_prod.sku, "BRG-6204-SKF")
        self.assertEqual(refreshed_prod.selling_price, 450.00)
