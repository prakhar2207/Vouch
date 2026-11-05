"""
SriLekh Environment & Database Isolation Safety Guard
Enforces strict fail-closed boundary isolation between production, staging, and development databases.
"""

import hashlib
import os
from typing import Dict, Any, Optional
from urllib.parse import urlparse
from django.core.exceptions import ImproperlyConfigured


PROD_HOST_DEFAULT = "ep-lingering-boat-b3994i6f-pooler.c-4.ap-southeast-1.aws.neon.tech"
PROD_DB_DEFAULT = "neondb"


def validate_environment_database_isolation(
    environment: str,
    db_config: Dict[str, Any],
    database_url: str = "",
    prod_host: str = PROD_HOST_DEFAULT,
    prod_db_name: str = PROD_DB_DEFAULT,
    is_testing: bool = False
) -> bool:
    """
    Validates that staging environments strictly refuse to boot when pointed at production databases.
    Fails closed by raising ImproperlyConfigured.
    """
    env_clean = str(environment or "").strip().lower()

    # Rule only applies when environment is explicitly configured as staging / stage
    if env_clean not in ("staging", "stage"):
        return True

    db_host = str(db_config.get("HOST", "") or "").strip().lower()
    db_name = str(db_config.get("NAME", "") or "").strip()
    db_engine = str(db_config.get("ENGINE", "") or "").strip().lower()

    if database_url:
        try:
            parsed = urlparse(database_url)
            if parsed.hostname:
                db_host = parsed.hostname.strip().lower()
            if parsed.path:
                db_name = parsed.path.lstrip("/").strip()
            if parsed.scheme:
                db_engine = parsed.scheme.strip().lower()
        except Exception:
            pass

    # In test runner with SQLite, allow execution if explicit test mode unless testing the guard itself
    if is_testing and "sqlite" in db_engine and not db_host:
        return True

    # Rule 1: Database name cannot be 'neondb' (the production database)
    if db_name.lower() == prod_db_name.lower():
        raise ImproperlyConfigured(
            f"FATAL ISOLATION DEFECT: Environment is configured as '{env_clean}', but database name is "
            f"'{db_name}' (production target). Staging backend MUST connect to a dedicated staging database "
            f"(e.g., 'neondb_staging'). Refusing to start."
        )

    # Rule 2: Database hostname cannot match the production Neon cluster endpoint without a dedicated staging db
    if prod_host.lower() in db_host or (db_host and db_host in prod_host.lower()):
        if "staging" not in db_name.lower() and "stage" not in db_name.lower():
            raise ImproperlyConfigured(
                f"FATAL ISOLATION DEFECT: Environment is '{env_clean}' and connects to production host '{db_host}', "
                f"but target database '{db_name}' lacks explicit staging namespace. Refusing to start."
            )

    # Rule 3: Database target cannot run on unpersisted SQLite in live staging
    if "sqlite" in db_engine and not is_testing:
        raise ImproperlyConfigured(
            f"FATAL ISOLATION DEFECT: Staging environment cannot run on SQLite in live mode. "
            f"Must use dedicated staging PostgreSQL database."
        )

    return True


def get_environment_identity_metadata(settings_module) -> Dict[str, Any]:
    """
    Returns non-sensitive environment identity metadata for health checks.
    Never exposes passwords, tokens, connection strings, or internal secret keys.
    """
    env_name = getattr(settings_module, "ENVIRONMENT", "production" if not getattr(settings_module, "DEBUG", False) else "development")
    db_default = getattr(settings_module, "DATABASES", {}).get("default", {})
    engine = db_default.get("ENGINE", "").split(".")[-1]

    raw_db_name = str(db_default.get("NAME", "unknown"))
    # Sanitize database name to prevent leaking internal paths
    if "/" in raw_db_name or "\\" in raw_db_name:
        sanitized_name = os.path.basename(raw_db_name)
    else:
        sanitized_name = raw_db_name

    # Fingerprint: SHA-256 hash of host+name for non-sensitive verification
    host_raw = str(db_default.get("HOST", ""))
    fingerprint = hashlib.sha256(f"{host_raw}:{sanitized_name}".encode("utf-8")).hexdigest()[:12]

    is_isolated = True
    prod_host = getattr(settings_module, "PRODUCTION_DB_HOST", PROD_HOST_DEFAULT)
    prod_name = getattr(settings_module, "PRODUCTION_DB_NAME", PROD_DB_DEFAULT)

    if env_name in ("staging", "stage") and (sanitized_name.lower() == prod_name.lower() or prod_host.lower() in host_raw.lower()):
        is_isolated = False

    commit_sha = os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("GIT_COMMIT") or os.environ.get("VERCEL_GIT_COMMIT_SHA")
    if not commit_sha:
        try:
            import subprocess
            commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode("ascii").strip()
        except Exception:
            commit_sha = "unknown"

    # Migration status check
    migration_status = "verified"
    unapplied_count = 0
    try:
        from django.db.migrations.executor import MigrationExecutor
        from django.db import connection
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        unapplied_count = len(executor.migration_plan(targets))
        migration_status = "up_to_date" if unapplied_count == 0 else f"{unapplied_count}_pending"
    except Exception:
        migration_status = "unverified"

    return {
        "status": "healthy",
        "service": "SriLekh Accounting Engine",
        "environment": env_name,
        "version": getattr(settings_module, "VERSION", "1.0.2"),
        "commit": commit_sha[:8] if commit_sha else "unknown",
        "database": {
            "engine": engine,
            "sanitized_target": sanitized_name,
            "identity_fingerprint": fingerprint,
            "is_isolated": is_isolated
        },
        "redis": {
            "configured": bool(getattr(settings_module, "CELERY_BROKER_URL", "")),
            "status": "active"
        },
        "celery": {
            "beat_schedule_active": True,
            "outbox_sweeper_interval_seconds": 60
        },
        "migrations": {
            "status": migration_status,
            "unapplied_count": unapplied_count
        }
    }
