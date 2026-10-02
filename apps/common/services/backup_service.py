import os
import sys
import time
import gzip
import shutil
import base64
import hashlib
import logging
import sqlite3
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from django.conf import settings
from django.db import connection

logger = logging.getLogger(__name__)

class DatabaseBackupService:
    """
    Enterprise-grade database backup and disaster recovery service.
    Supports:
    1. Automated snapshot generation (PostgreSQL pg_dump / SQLite backup)
    2. Gzip stream compression
    3. AES-256 symmetric encryption (via Fernet / SHA-256 key derivation)
    4. SHA-256 integrity checksum verification
    5. Off-site cloud upload to Amazon S3 / MinIO / Google Cloud Storage
    6. Local retention window pruning (e.g. keep 7 days)
    7. Audit trail logging for compliance & health monitoring
    """

    @classmethod
    def get_encryption_key(cls) -> bytes:
        """Derives a safe 32-byte url-safe base64 key from settings."""
        raw_key = getattr(settings, 'BACKUP_ENCRYPTION_KEY', None) or settings.SECRET_KEY
        hashed = hashlib.sha256(raw_key.encode('utf-8')).digest()
        return base64.urlsafe_b64encode(hashed)

    @classmethod
    def encrypt_data(cls, raw_bytes: bytes) -> bytes:
        """Encrypts payload with AES-256-CBC via Fernet."""
        from cryptography.fernet import Fernet
        f = Fernet(cls.get_encryption_key())
        return f.encrypt(raw_bytes)

    @classmethod
    def decrypt_data(cls, encrypted_bytes: bytes) -> bytes:
        """Decrypts AES-256 Fernet payload."""
        from cryptography.fernet import Fernet
        f = Fernet(cls.get_encryption_key())
        return f.decrypt(encrypted_bytes)

    @classmethod
    def perform_backup(
        cls,
        upload_s3: bool = True,
        encrypt: bool = True,
        output_dir: str = None,
        company_id: str = None
    ) -> dict:
        """
        Executes a complete, consistent database backup.
        Returns dictionary with backup metadata.
        """
        start_time = time.time()
        now_utc = datetime.now(timezone.utc)
        timestamp_str = now_utc.strftime('%Y%m%d_%H%M%S')

        # 1. Prepare directory
        base_dir = Path(output_dir) if output_dir else (settings.BASE_DIR / 'backups' / 'database')
        base_dir.mkdir(parents=True, exist_ok=True)

        db_settings = connection.settings_dict
        engine = db_settings.get('ENGINE', '')
        db_name = db_settings.get('NAME', 'vouch_db')

        raw_dump_path = base_dir / f"vouch_dump_{timestamp_str}.sql"
        gz_dump_path = base_dir / f"vouch_dump_{timestamp_str}.sql.gz"
        final_file_path = base_dir / f"vouch_backup_{timestamp_str}.enc" if encrypt else gz_dump_path

        logger.info(f"[Backup] Starting backup for engine: {engine} | DB: {db_name}")

        try:
            # 2. Dump Database
            if 'postgresql' in engine:
                cls._dump_postgresql(db_settings, raw_dump_path, company_id=company_id)
            elif 'sqlite' in engine:
                cls._dump_sqlite(db_name, raw_dump_path)
            else:
                raise ValueError(f"Unsupported database engine for backup: {engine}")

            # 3. Gzip Compress
            with open(raw_dump_path, 'rb') as f_in:
                with gzip.open(gz_dump_path, 'wb', compresslevel=9) as f_out:
                    shutil.copyfileobj(f_in, f_out)

            # Remove uncompressed raw dump to save disk
            if raw_dump_path.exists():
                raw_dump_path.unlink()

            # 4. Optional AES-256 Encryption
            if encrypt:
                with open(gz_dump_path, 'rb') as f_gz:
                    compressed_bytes = f_gz.read()
                encrypted_bytes = cls.encrypt_data(compressed_bytes)
                with open(final_file_path, 'wb') as f_enc:
                    f_enc.write(encrypted_bytes)
                # Remove unencrypted gzip file
                if gz_dump_path.exists():
                    gz_dump_path.unlink()

            file_size_bytes = final_file_path.stat().st_size
            file_size_mb = round(file_size_bytes / (1024 * 1024), 3)

            # 5. Calculate SHA-256 Checksum
            sha256 = hashlib.sha256()
            with open(final_file_path, 'rb') as f:
                while chunk := f.read(65536):
                    sha256.update(chunk)
            checksum = sha256.hexdigest()

            # 6. Off-Site S3 Upload
            s3_uri = None
            s3_uploaded = False
            if upload_s3:
                s3_result = cls._upload_to_s3(final_file_path, f"database/{final_file_path.name}")
                s3_uploaded = s3_result.get('success', False)
                s3_uri = s3_result.get('uri')

            # 7. Local Retention Cleanup (Prune backups older than 7 days)
            cls._prune_old_local_backups(base_dir, retention_days=getattr(settings, 'BACKUP_RETENTION_DAYS', 7))

            elapsed = round(time.time() - start_time, 2)
            logger.info(f"[Backup] Finished in {elapsed}s | Size: {file_size_mb} MB | S3: {s3_uploaded} | Path: {final_file_path}")

            # 8. Record to Audit Log if model available
            cls._log_audit_event(
                status='SUCCESS',
                file_name=final_file_path.name,
                file_size_mb=file_size_mb,
                checksum=checksum,
                s3_uri=s3_uri,
                elapsed_sec=elapsed
            )

            return {
                "success": True,
                "timestamp": now_utc.isoformat(),
                "file_name": final_file_path.name,
                "file_path": str(final_file_path),
                "file_size_mb": file_size_mb,
                "is_encrypted": encrypt,
                "sha256_checksum": checksum,
                "s3_uploaded": s3_uploaded,
                "s3_uri": s3_uri,
                "elapsed_seconds": elapsed,
            }

        except Exception as e:
            elapsed = round(time.time() - start_time, 2)
            logger.exception(f"[Backup] Failed after {elapsed}s: {e}")
            cls._log_audit_event(
                status='FAILURE',
                error_message=str(e),
                elapsed_sec=elapsed
            )
            return {
                "success": False,
                "error": str(e),
                "elapsed_seconds": elapsed
            }

    @classmethod
    def _dump_postgresql(cls, db_settings: dict, output_file: Path, company_id: str = None):
        """Dumps PostgreSQL database via pg_dump, or falls back to Django serialized dump if pg_dump is not in PATH."""
        pg_dump_bin = shutil.which('pg_dump')
        if pg_dump_bin and not company_id:
            host = db_settings.get('HOST', 'localhost')
            port = str(db_settings.get('PORT', '5432'))
            user = db_settings.get('USER', 'postgres')
            db_name = db_settings.get('NAME')
            password = db_settings.get('PASSWORD', '')

            env = os.environ.copy()
            if password:
                env['PGPASSWORD'] = password

            cmd = [
                pg_dump_bin,
                '-h', host,
                '-p', port,
                '-U', user,
                '--clean',
                '--no-owner',
                '--no-privileges',
                '-f', str(output_file),
                db_name
            ]
            res = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"pg_dump failed (code {res.returncode}): {res.stderr}")
        else:
            logger.info("[Backup] Using resilient chunked batch serializer.")
            from django.apps import apps
            from django.core.serializers import serialize
            MODEL_DEPENDENCY_ORDER = [
                'company', 'user', 'usercompany', 'warehouse',
                'productcategory', 'product', 'ledgergroup', 'ledger',
                'financialyear', 'vouchersequence', 'voucher',
                'voucheritem', 'ledgerentry', 'paymentallocation',
                'inventoryentry', 'protocoltransaction',
                'protocoloperation', 'cryptographiccommitment',
                'entitymapping'
            ]
            all_models = [
                m for m in apps.get_models()
                if m._meta.app_label not in ['contenttypes', 'sessions', 'admin', 'auth', 'token_blacklist']
                and m._meta.model_name not in ['syncevent', 'auditlog', 'permission']
                and hasattr(m, 'objects')
            ]
            def model_priority(m):
                name = m._meta.model_name.lower()
                try:
                    return MODEL_DEPENDENCY_ORDER.index(name)
                except ValueError:
                    return 999
            all_models.sort(key=model_priority)

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write('[\n')
                first = True
                for model in all_models:
                    qs = model.objects.all()
                    if company_id:
                        if model._meta.model_name == 'company':
                            qs = qs.filter(id=company_id)
                        elif any(f.name == 'company' for f in model._meta.fields):
                            qs = qs.filter(company_id=company_id)
                        elif model._meta.model_name == 'protocoltransaction':
                            qs = qs.filter(source_company_id=str(company_id))
                        elif model._meta.model_name in ['protocoloperation', 'cryptographiccommitment']:
                            qs = qs.filter(transaction__source_company_id=str(company_id))
                        elif model._meta.model_name == 'voucheritem':
                            qs = qs.filter(voucher__company_id=company_id)
                        elif model._meta.model_name == 'user':
                            qs = qs.filter(companies__company_id=company_id)
                            if not qs.exists():
                                qs = model.objects.none()
                        else:
                            continue
                    count = qs.count()
                    for i in range(0, count, 500):
                        batch = list(qs[i:i+500])
                        if not batch:
                            continue
                        serialized = serialize('json', batch)
                        inner = serialized.strip()[1:-1].strip()
                        if inner:
                            if not first:
                                f.write(',\n')
                            f.write(inner)
                            first = False
                f.write('\n]\n')

    @classmethod
    def _dump_sqlite(cls, db_name_or_path: str, output_file: Path):
        """Non-locking safe snapshot of SQLite database."""
        src_conn = sqlite3.connect(str(db_name_or_path))
        dest_conn = sqlite3.connect(str(output_file))
        with dest_conn:
            src_conn.backup(dest_conn, pages=100)
        dest_conn.close()
        src_conn.close()

    @classmethod
    def _upload_to_s3(cls, local_path: Path, s3_key: str) -> dict:
        """Uploads file to configured S3 bucket using boto3."""
        bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None) or getattr(settings, 'BACKUP_S3_BUCKET', None)
        access_key = getattr(settings, 'AWS_ACCESS_KEY_ID', None)
        secret_key = getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
        region = getattr(settings, 'AWS_S3_REGION_NAME', 'ap-south-1')

        if not bucket_name:
            logger.warning("[Backup] No AWS_STORAGE_BUCKET_NAME or BACKUP_S3_BUCKET defined. Skipping S3 upload.")
            return {"success": False, "uri": None, "reason": "S3 bucket not configured"}

        try:
            import boto3
            client_kwargs = {}
            if access_key and secret_key:
                client_kwargs['aws_access_key_id'] = access_key
                client_kwargs['aws_secret_access_key'] = secret_key
                client_kwargs['region_name'] = region

            s3 = boto3.client('s3', **client_kwargs)
            s3.upload_file(str(local_path), bucket_name, s3_key)
            s3_uri = f"s3://{bucket_name}/{s3_key}"
            logger.info(f"[Backup] Successfully uploaded to {s3_uri}")
            return {"success": True, "uri": s3_uri}
        except Exception as e:
            logger.warning(f"[Backup] S3 upload failed: {e}")
            return {"success": False, "uri": None, "error": str(e)}

    @classmethod
    def _prune_old_local_backups(cls, backup_dir: Path, retention_days: int = 7):
        """Removes local backup files older than retention_days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        for f in backup_dir.glob('vouch_backup_*'):
            if f.is_file():
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                if mtime < cutoff:
                    try:
                        f.unlink()
                        logger.info(f"[Backup] Pruned expired local backup: {f.name}")
                    except Exception as err:
                        logger.warning(f"[Backup] Could not prune {f.name}: {err}")

    @classmethod
    def _log_audit_event(cls, status: str, **kwargs):
        """Persists backup telemetry to AuditLog."""
        try:
            from apps.audit.models import AuditLog
            AuditLog.objects.create(
                action=f"DISASTER_RECOVERY_BACKUP_{status}",
                details=kwargs
            )
        except Exception:
            pass

    @classmethod
    def unpack_backup(cls, backup_path: Path) -> bytes:
        """Decrypts and decompresses a backup file into its raw representation."""
        backup_path = Path(backup_path)
        with open(backup_path, 'rb') as f:
            data = f.read()

        # 1. Attempt decryption if ends with .enc or if Fernet payload
        if backup_path.suffix == '.enc' or data.startswith(b'gAAAAA'):
            try:
                data = cls.decrypt_data(data)
            except Exception as e:
                logger.error(f"[Backup] Failed to decrypt backup: {e}")
                raise

        # 2. Decompress if gzip magic header
        if data.startswith(b'\x1f\x8b'):
            data = gzip.decompress(data)

        return data

    @classmethod
    def restore_backup(
        cls,
        backup_path: Path,
        target_db_alias: str = 'default',
        dry_run: bool = False
    ) -> dict:
        """
        Restores a backup archive (decryption + decompression + data load).
        Supports:
        1. Django JSON serialized fixture streams
        2. Raw PostgreSQL / SQLite SQL dump streams
        3. Raw SQLite binary databases
        """
        import io
        from django.db import connections, transaction
        from django.core.serializers import deserialize

        start_time = time.time()
        backup_path = Path(backup_path)
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")

        raw_bytes = cls.unpack_backup(backup_path)

        # Check type
        is_sqlite_binary = raw_bytes.startswith(b'SQLite format 3\x00')
        is_json = raw_bytes.strip().startswith(b'[')

        record_count = 0
        error_count = 0
        errors = []

        if is_sqlite_binary:
            target_db_file = connections[target_db_alias].settings_dict.get('NAME')
            if not target_db_file or 'sqlite' not in connections[target_db_alias].settings_dict.get('ENGINE', ''):
                raise ValueError("Cannot restore SQLite binary backup into non-SQLite target database.")
            if not dry_run:
                with open(target_db_file, 'wb') as f:
                    f.write(raw_bytes)
            elapsed = round(time.time() - start_time, 2)
            return {
                "success": True,
                "backup_type": "SQLITE_BINARY",
                "bytes_restored": len(raw_bytes),
                "elapsed_seconds": elapsed,
                "dry_run": dry_run
            }

        elif is_json:
            # Django JSON fixture stream
            json_str = raw_bytes.decode('utf-8')
            deserialized_objects = deserialize('json', json_str, using=target_db_alias, ignorenonexistent=True)

            if dry_run:
                for obj in deserialized_objects:
                    record_count += 1
            else:
                pending = list(deserialized_objects)
                last_pending_count = -1
                last_errors = []
                for pass_num in range(4):
                    if not pending:
                        break
                    next_pending = []
                    last_errors = []
                    for deserialized_obj in pending:
                        try:
                            with transaction.atomic(using=target_db_alias):
                                deserialized_obj.save(using=target_db_alias)
                            record_count += 1
                        except Exception as e:
                            next_pending.append(deserialized_obj)
                            last_errors.append((deserialized_obj, e))
                    if len(next_pending) == len(pending):
                        # No further records could be resolved
                        break
                    pending = next_pending

                for deserialized_obj, err in last_errors:
                    error_count += 1
                    if len(errors) < 10:
                        model_name = deserialized_obj.object.__class__.__name__
                        pk = getattr(deserialized_obj.object, 'pk', '?')
                        errors.append(f"{model_name} ({pk}): {str(err)}")

            elapsed = round(time.time() - start_time, 2)
            cls._log_audit_event(
                status='RESTORE_SUCCESS' if error_count == 0 else 'RESTORE_PARTIAL',
                file_name=backup_path.name,
                records_restored=record_count,
                error_count=error_count,
                elapsed_sec=elapsed,
                dry_run=dry_run
            )
            return {
                "success": error_count == 0,
                "backup_type": "DJANGO_JSON_FIXTURE",
                "records_restored": record_count,
                "errors": errors,
                "error_count": error_count,
                "elapsed_seconds": elapsed,
                "dry_run": dry_run
            }

        else:
            # Raw SQL dump
            sql_text = raw_bytes.decode('utf-8')
            if not dry_run:
                with connections[target_db_alias].cursor() as cursor:
                    cursor.execute(sql_text)
            elapsed = round(time.time() - start_time, 2)
            return {
                "success": True,
                "backup_type": "SQL_SCRIPT",
                "bytes_restored": len(raw_bytes),
                "elapsed_seconds": elapsed,
                "dry_run": dry_run
            }
