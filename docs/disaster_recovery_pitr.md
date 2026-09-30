# Vouch ERP — Disaster Recovery & Point-In-Time Recovery (PITR) Standard Operating Procedure

## 1. Architectural Overview

Vouch incorporates a multi-tiered disaster recovery and data integrity architecture to guarantee zero data loss and business continuity across cloud hardware failures, regional outages, or accidental data deletions:

1. **Daily Automated Encrypted Snapshots (Cold Backups)**:
   - Compressed via **Gzip (Level 9)**.
   - Encrypted with **AES-256-CBC (Fernet)** using a SHA-256 key derived from `BACKUP_ENCRYPTION_KEY`.
   - Verified via **SHA-256 Checksums** and logged directly to `AuditLog`.
   - Uploaded off-site to Amazon S3 / MinIO / Google Cloud Storage.
   - Automatic local pruning: Backups older than 7 days (`BACKUP_RETENTION_DAYS`) are pruned automatically.
   - Scheduled via Celery Beat every night at **02:00 AM IST (20:30 UTC)**.

2. **Continuous WAL Archiving & Point-In-Time Recovery (Hot Backups)**:
   - PostgreSQL Write-Ahead Log (WAL) archiving streams every transaction off-site in real time.
   - Allows restoring the database to any specific second (e.g. 5 minutes before an accidental drop or corruption).

---

## 2. PostgreSQL Production WAL Archiving Configuration

In your production PostgreSQL configuration file (`postgresql.conf`):

```ini
# Enable WAL Archiving
wal_level = replica
archive_mode = on
archive_timeout = 300  # Force WAL switch every 5 minutes

# Archive command: pushes completed WAL segments to S3
archive_command = 'aws s3 cp %p s3://your-vouch-backups/wal_archive/%f --storage-class STANDARD_IA'
```

Restart PostgreSQL to apply changes:
```bash
sudo systemctl restart postgresql
```

---

## 3. Manual Backup & Verification Commands

### Trigger Manual Backup Immediately:
```bash
python manage.py backup_database --verify
```

### Options:
* `--verify`: Automatically performs an AES-256 in-memory decryption test to verify that the snapshot is readable and uncorrupted.
* `--no-s3`: Stores the encrypted snapshot locally in `backups/database/` without attempting S3 upload.
* `--no-encrypt`: Exports an unencrypted `.sql.gz` (recommended only for dev environment migrations).
* `--output-dir <path>`: Specifies custom backup directory.

---

## 4. Step-by-Step Disaster Recovery Playbook

If a critical database failure, ransomware event, or accidental deletion occurs:

### Step 1: Download the Target Backup from S3
```bash
aws s3 cp s3://your-vouch-backups/database/vouch_backup_YYYYMMDD_HHMMSS.enc ./recovery_backup.enc
```

### Step 2: Decrypt the Backup
Run this one-liner via Python:
```python
from apps.common.services.backup_service import DatabaseBackupService

with open("recovery_backup.enc", "rb") as f_in:
    enc_data = f_in.read()

dec_data = DatabaseBackupService.decrypt_data(enc_data)

with open("restored_snapshot.json.gz", "wb") as f_out:
    f_out.write(dec_data)
```

### Step 3: Decompress & Restore
```bash
# For Gzip uncompression
gzip -d restored_snapshot.json.gz

# Load data into fresh database
python manage.py loaddata restored_snapshot.json
```

### Step 4: Replay WAL Logs (For Point-In-Time Recovery to Exact Minute)
Create `recovery.signal` in the PostgreSQL data directory:
```ini
restore_command = 'aws s3 cp s3://your-vouch-backups/wal_archive/%f %p'
recovery_target_time = '2026-09-30 14:00:00+05:30'  # Exact recovery target
recovery_target_action = 'promote'
```
Start PostgreSQL; it will roll forward to the exact second requested and promote to primary.

---

## 5. Security & Compliance Checklist
- [x] Encryption keys are never hardcoded; derived dynamically from environment variables (`BACKUP_ENCRYPTION_KEY`).
- [x] S3 buckets have Object Lock (WORM - Write Once Read Many) enabled to prevent ransomware alteration.
- [x] All backup runs emit tamper-proof records to `AuditLog`.
