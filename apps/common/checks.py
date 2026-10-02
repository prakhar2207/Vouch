import os
from django.core.checks import Error, Warning, register, Tags
from django.conf import settings

@register(Tags.security, deploy=True)
def check_production_security_gate(app_configs, **kwargs):
    """
    Authoritative Production Configuration Gate for Vouch Financial ERP & Protocol.
    Fails startup / deploy checks if security controls are missing or running in degraded mode.
    """
    errors = []

    # 1. SECRET_KEY Integrity
    secret_key = getattr(settings, 'SECRET_KEY', '')
    if not secret_key:
        errors.append(Error("SECRET_KEY is empty or not configured.", id="vouch.security.E001"))
    elif secret_key.startswith('django-insecure-') or len(secret_key) < 32:
        errors.append(Error("SECRET_KEY is using an insecure or default development key (length < 32 or starts with 'django-insecure-').", id="vouch.security.E002"))

    # 2. DEBUG Mode
    if getattr(settings, 'DEBUG', False):
        errors.append(Error("DEBUG is set to True. Must be False in production.", id="vouch.security.E003"))

    # 3. ALLOWED_HOSTS
    allowed_hosts = getattr(settings, 'ALLOWED_HOSTS', [])
    if '*' in allowed_hosts or not allowed_hosts:
        errors.append(Error("ALLOWED_HOSTS cannot contain wildcard '*' or be empty in production.", id="vouch.security.E004"))

    # 4. CORS Protection
    if getattr(settings, 'CORS_ALLOW_ALL_ORIGINS', False):
        errors.append(Error("CORS_ALLOW_ALL_ORIGINS is True. Production must enforce explicit origin allowlists.", id="vouch.security.E005"))

    cors_origins = getattr(settings, 'CORS_ALLOWED_ORIGINS', [])
    for origin in cors_origins:
        if origin.startswith('http://') and not ('localhost' in origin or '127.0.0.1' in origin):
            errors.append(Error(f"Insecure HTTP origin detected in CORS_ALLOWED_ORIGINS: {origin}", id="vouch.security.E006"))

    # 5. Database Engine
    db_engine = settings.DATABASES.get('default', {}).get('ENGINE', '')
    if 'postgresql' not in db_engine:
        errors.append(Warning(f"Production database engine should be PostgreSQL, got {db_engine}.", id="vouch.security.W007"))

    # 6. VAPID Keys for Web Push Notifications
    vapid_pub = os.environ.get('VAPID_PUBLIC_KEY', '') or getattr(settings, 'VAPID_PUBLIC_KEY', '')
    vapid_priv = os.environ.get('VAPID_PRIVATE_KEY', '') or getattr(settings, 'VAPID_PRIVATE_KEY', '')
    if not vapid_pub or not vapid_priv:
        errors.append(Error("VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY must be configured for Web Push Notifications.", id="vouch.security.E008"))

    # 7. Cloud KMS Configuration
    kms_provider = os.environ.get('VOUCH_KMS_PROVIDER', 'LOCAL').strip().upper()
    if kms_provider == 'LOCAL':
        errors.append(Error("VOUCH_KMS_PROVIDER cannot be 'LOCAL' in production deployment (--deploy). A hardware KMS (AWS, GCP, AZURE, PKCS11) is required for non-repudiation.", id="vouch.security.E013"))
    elif kms_provider == 'AWS':
        aws_arn = os.environ.get('AWS_KMS_KEY_ARN', '')
        if not aws_arn:
            errors.append(Error("VOUCH_KMS_PROVIDER is set to AWS, but AWS_KMS_KEY_ARN is not configured.", id="vouch.security.E009"))
    elif kms_provider in ['GCP', 'GOOGLE']:
        gcp_key = os.environ.get('GCP_KMS_KEY_NAME', '')
        if not gcp_key:
            errors.append(Error("VOUCH_KMS_PROVIDER is set to GCP, but GCP_KMS_KEY_NAME is not configured.", id="vouch.security.E010"))

    # 8. Server-Managed AI Credentials
    gemini_key = os.environ.get('GEMINI_API_KEY', '') or getattr(settings, 'GEMINI_API_KEY', '')
    if not gemini_key:
        errors.append(Warning("GEMINI_API_KEY is not configured on the server. AI OCR bill scanning will fall back to digital text stream parser.", id="vouch.security.W011"))

    # 9. Celery Broker Connectivity
    if not getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', True):
        broker_url = getattr(settings, 'CELERY_BROKER_URL', '')
        if not broker_url or 'redis' not in broker_url and 'amqp' not in broker_url:
            errors.append(Error("CELERY_BROKER_URL must be configured with Redis or AMQP when background worker tasks are enabled.", id="vouch.security.E012"))

    # 10. Backup Encryption Key Isolation
    backup_key = os.environ.get('BACKUP_ENCRYPTION_KEY', '') or getattr(settings, 'BACKUP_ENCRYPTION_KEY', '')
    if not backup_key or backup_key == secret_key:
        errors.append(Warning("BACKUP_ENCRYPTION_KEY is sharing the same key as SECRET_KEY. Configure a dedicated BACKUP_ENCRYPTION_KEY in production for defense-in-depth backup isolation.", id="vouch.security.W014"))

    return errors
