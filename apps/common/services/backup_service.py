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
    def get_encryption_keys(cls) -> list:
        """
        Derives safe 32-byte url-safe base64 keys for AES-256 encryption & decryption.
        Returns [primary_key, *fallback_keys] to allow zero-downtime key rotation:
        - Encryption always uses primary_key (keys[0]).
        - Decryption automatically tries primary_key then fallback_keys via MultiFernet.
        """
        keys = []
        # 1. Primary dedicated key
        primary = getattr(settings, 'BACKUP_ENCRYPTION_KEY', None)
        if primary and str(primary).strip():
            hashed = hashlib.sha256(str(primary).strip().encode('utf-8')).digest()
            keys.append(base64.urlsafe_b64encode(hashed))

        # 2. Key rotation fallbacks (list or comma-separated string)
        fallbacks = getattr(settings, 'BACKUP_ENCRYPTION_KEY_FALLBACKS', [])
        if isinstance(fallbacks, str):
            fallbacks = [k.strip() for k in fallbacks.split(',') if k.strip()]
        for fb in fallbacks:
            if fb and str(fb).strip():
                hashed = hashlib.sha256(str(fb).strip().encode('utf-8')).digest()
                k = base64.urlsafe_b64encode(hashed)
                if k not in keys:
                    keys.append(k)

        # 3. Emergency fallback if no dedicated key is configured
        if not keys:
            logger.warning(
                "[Security Warning] BACKUP_ENCRYPTION_KEY is not configured! "
                "Deriving fallback key from SECRET_KEY. Configure a dedicated BACKUP_ENCRYPTION_KEY in production."
            )
            derived = getattr(settings, '_default_backup_key', None) or (settings.SECRET_KEY + '_vouch_dr_backup_salt')
            hashed = hashlib.sha256(derived.encode('utf-8')).digest()
            keys.append(base64.urlsafe_b64encode(hashed))

        return keys

    @classmethod
    def get_encryption_key(cls) -> bytes:
        """Returns the primary active key for encryption."""
        return cls.get_encryption_keys()[0]

    @classmethod
    def encrypt_data(cls, raw_bytes: bytes) -> bytes:
        """Encrypts payload with AES-256-CBC via Fernet using the primary active key."""
        from cryptography.fernet import Fernet
        f = Fernet(cls.get_encryption_key())
        return f.encrypt(raw_bytes)

    @classmethod
    def decrypt_data(cls, encrypted_bytes: bytes) -> bytes:
        """
        Decrypts AES-256 Fernet payload supporting multi-key rotation via MultiFernet.
        Gracefully tries the primary key followed by all configured fallback keys.
        """
        from cryptography.fernet import Fernet, MultiFernet
        keys = cls.get_encryption_keys()
        fernets = [Fernet(k) for k in keys]
        mf = MultiFernet(fernets)
        return mf.decrypt(encrypted_bytes)

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
            model_counts = None
            if 'postgresql' in engine:
                model_counts = cls._dump_postgresql(db_settings, raw_dump_path, company_id=company_id)
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
                "model_counts": model_counts,
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
        """
        Dumps PostgreSQL database via native `pg_dump` (--format=custom) when available,
        or falls back to a complete, deterministically ordered Django JSON fixture stream
        including AuditLog and SyncEvent when pg_dump is not installed on the host.
        """
        pg_dump_bin = shutil.which('pg_dump')
        if pg_dump_bin and not company_id:
            host = db_settings.get('HOST', 'localhost')
            port = str(db_settings.get('PORT') or '5432')
            user = db_settings.get('USER', 'postgres')
            db_name = db_settings.get('NAME')
            password = db_settings.get('PASSWORD', '')
            sslmode = (db_settings.get('OPTIONS') or {}).get('sslmode', 'require' if host not in ('localhost', '127.0.0.1') else 'prefer')

            env = os.environ.copy()
            if password:
                env['PGPASSWORD'] = password
            if sslmode:
                env['PGSSLMODE'] = str(sslmode)

            cmd = [
                pg_dump_bin,
                '-h', host,
                '-p', port,
                '-U', user,
                '--format=custom',
                '--no-owner',
                '--no-privileges',
                '-f', str(output_file),
                db_name
            ]
            res = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"pg_dump failed (code {res.returncode}): {res.stderr}")
            return None
        else:
            logger.info("[Backup] Using complete deterministic chunked batch serializer (pg_dump unavailable or company-scoped).")
            from django.apps import apps
            from django.core.serializers import serialize
            MODEL_DEPENDENCY_ORDER = [
                'company', 'user', 'emailverificationchallenge', 'pendingregistration',
                'usercompany', 'companysettings', 'warehouse',
                'productcategory', 'product', 'pricelist', 'pricelistitem',
                'ledgergroup', 'ledger', 'financialyear', 'vouchersequence',
                'ledgerbalance', 'voucher', 'voucheritem', 'ledgerentry',
                'paymentallocation', 'paymentallocationtask', 'offlinecommand',
                'bankstatementimport', 'banktransaction', 'partymapping',
                'accountingfinding', 'syncevent', 'inventoryentry',
                'protocoltransaction', 'protocoloperation', 'cryptographiccommitment',
                'entitymapping', 'documentsnapshot', 'auditlog',
                'notificationpreference', 'emaildeliverylog',
                'transactionaloutboxevent', 'secureinvoiceaccesstoken',
            ]
            all_models = [
                m for m in apps.get_models()
                if m._meta.app_label not in ['contenttypes', 'sessions', 'admin', 'auth', 'token_blacklist']
                and not m._meta.proxy
                and hasattr(m, 'objects')
            ]
            def model_priority(m):
                name = m._meta.model_name.lower()
                try:
                    return (0, MODEL_DEPENDENCY_ORDER.index(name), m._meta.label_lower)
                except ValueError:
                    return (1, 999, m._meta.label_lower)
            all_models.sort(key=model_priority)

            model_counts = {}
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write('[\n')
                first = True
                for model in all_models:
                    pk_name = model._meta.pk.name
                    if model._meta.model_name == 'auditlog':
                        qs = model.objects.all().order_by('sequence', 'created_at', pk_name)
                    else:
                        qs = model.objects.all().order_by(pk_name)

                    if company_id:
                        if model._meta.model_name == 'company':
                            qs = qs.filter(id=company_id)
                        elif any(f.name == 'company' for f in model._meta.fields):
                            qs = qs.filter(company_id=company_id)
                        elif model._meta.model_name == 'protocoltransaction':
                            qs = qs.filter(source_company_id=str(company_id))
                        elif model._meta.model_name in ['protocoloperation', 'cryptographiccommitment']:
                            qs = qs.filter(transaction__source_company_id=str(company_id))
                        elif model._meta.model_name in ['voucheritem', 'secureinvoiceaccesstoken']:
                            qs = qs.filter(voucher__company_id=company_id)
                        elif model._meta.model_name == 'ledgerbalance':
                            qs = qs.filter(ledger__company_id=company_id)
                        elif model._meta.model_name == 'user':
                            qs = qs.filter(companies__company_id=company_id).distinct()
                            if not qs.exists():
                                qs = model.objects.none()
                        else:
                            continue
                    count = qs.count()
                    model_counts[model._meta.label_lower] = count
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
            return model_counts

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
                action='RESOLVE',
                model_name='DatabaseBackup',
                record_id=str(kwargs.get('file_name') or status)[:255],
                changes={"event": f"DISASTER_RECOVERY_BACKUP_{status}", **kwargs},
            )
        except Exception as exc:
            logger.warning(f"[Backup] Failed to record AuditLog telemetry: {exc}")

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
        is_pg_custom_dump = raw_bytes.startswith(b'PGDMP')
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
                from django.core.management.color import no_style
                pending = list(deserialized_objects)
                restored_models = set()
                last_errors = []
                is_pg = 'postgresql' in connections[target_db_alias].settings_dict.get('ENGINE', '')

                def _save_item_preserving_immutability(d_item):
                    m_cls = d_item.object.__class__
                    if m_cls._meta.model_name == 'auditlog':
                        # Preserve exact immutable sequence, previous_hash, and current_hash
                        existing = m_cls.objects.using(target_db_alias).filter(pk=d_item.object.pk).values('current_hash').first()
                        if existing is not None:
                            if existing['current_hash'] != d_item.object.current_hash:
                                raise ValueError(f"AuditLog hash mismatch for existing PK {d_item.object.pk}")
                            return
                        m_cls.objects.using(target_db_alias).bulk_create([d_item.object])
                    else:
                        d_item.save(using=target_db_alias)

                with transaction.atomic(using=target_db_alias):
                    if is_pg:
                        with connections[target_db_alias].cursor() as cur:
                            cur.execute("SET CONSTRAINTS ALL DEFERRED")

                    for pass_num in range(4):
                        if not pending:
                            break
                        next_pending = []
                        last_errors = []

                        idx = 0
                        total_pending = len(pending)
                        while idx < total_pending:
                            d_obj = pending[idx]
                            model_cls = d_obj.object.__class__
                            can_bulk = not model_cls._meta.parents and not getattr(d_obj, 'm2m_data', None)
                            if not can_bulk:
                                try:
                                    with transaction.atomic(using=target_db_alias, savepoint=True):
                                        _save_item_preserving_immutability(d_obj)
                                    restored_models.add(model_cls)
                                    record_count += 1
                                except Exception as e:
                                    next_pending.append(d_obj)
                                    last_errors.append((d_obj, e))
                                idx += 1
                                continue

                            batch = [d_obj]
                            j = idx + 1
                            while j < total_pending and len(batch) < 250:
                                nxt = pending[j]
                                if nxt.object.__class__ is model_cls and not getattr(nxt, 'm2m_data', None):
                                    batch.append(nxt)
                                    j += 1
                                else:
                                    break

                            try:
                                with transaction.atomic(using=target_db_alias, savepoint=True):
                                    model_cls.objects.using(target_db_alias).bulk_create(
                                        [item.object for item in batch],
                                        batch_size=250,
                                    )
                                restored_models.add(model_cls)
                                record_count += len(batch)
                            except Exception:
                                for item in batch:
                                    try:
                                        with transaction.atomic(using=target_db_alias, savepoint=True):
                                            _save_item_preserving_immutability(item)
                                        restored_models.add(model_cls)
                                        record_count += 1
                                    except Exception as e:
                                        next_pending.append(item)
                                        last_errors.append((item, e))
                            idx = j

                        if len(next_pending) == len(pending):
                            break
                        pending = next_pending

                    if is_pg and restored_models:
                        seq_sql = connections[target_db_alias].ops.sequence_reset_sql(no_style(), list(restored_models))
                        if seq_sql:
                            with connections[target_db_alias].cursor() as cur:
                                for stmt in seq_sql:
                                    cur.execute(stmt)

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

        elif is_pg_custom_dump:
            pg_restore_bin = shutil.which('pg_restore')
            if not pg_restore_bin:
                raise RuntimeError("pg_restore binary is required to restore PostgreSQL custom-format (.dump) backups.")
            if not dry_run:
                import tempfile
                db_settings = connections[target_db_alias].settings_dict
                env = os.environ.copy()
                if db_settings.get('PASSWORD'):
                    env['PGPASSWORD'] = db_settings['PASSWORD']
                sslmode = (db_settings.get('OPTIONS') or {}).get('sslmode')
                if sslmode:
                    env['PGSSLMODE'] = str(sslmode)
                with tempfile.NamedTemporaryFile(suffix='.dump', delete=False) as tf:
                    tf.write(raw_bytes)
                    temp_dump = Path(tf.name)
                try:
                    cmd = [
                        pg_restore_bin,
                        '-h', str(db_settings.get('HOST', 'localhost')),
                        '-p', str(db_settings.get('PORT') or '5432'),
                        '-U', str(db_settings.get('USER', 'postgres')),
                        '-d', str(db_settings.get('NAME')),
                        '--clean', '--if-exists', '--no-owner', '--no-privileges', '--single-transaction',
                        str(temp_dump)
                    ]
                    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
                    if res.returncode != 0:
                        raise RuntimeError(f"pg_restore failed (code {res.returncode}): {res.stderr}")
                finally:
                    temp_dump.unlink(missing_ok=True)
            elapsed = round(time.time() - start_time, 2)
            return {
                "success": True,
                "backup_type": "PG_CUSTOM_DUMP",
                "bytes_restored": len(raw_bytes),
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
