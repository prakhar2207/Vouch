import os
import sys
from django.core.checks import Error, Warning, register, Tags
from django.conf import settings
from apps.gst.encryption import get_gst_credential_fernet, CredentialSecurityError


@register(Tags.security)
def check_gst_encryption_configuration(app_configs, **kwargs):
    """
    Startup system check verifying that dedicated GST credential encryption keys
    are correctly configured and operational.
    """
    errors = []
    
    # Static file collection does not require cryptographic keys
    if 'collectstatic' in sys.argv:
        return errors

    env_name = str(
        getattr(settings, 'ENVIRONMENT', '') or os.environ.get('ENVIRONMENT', '')
    ).strip().lower()
    
    is_testing = ('test' in sys.argv) or getattr(settings, 'TESTING', False)
    
    primary_key = (
        getattr(settings, 'GST_ENCRYPTION_KEY', None)
        or os.environ.get('GST_ENCRYPTION_KEY')
        or getattr(settings, 'GST_CREDENTIAL_KEY', None)
        or os.environ.get('GST_CREDENTIAL_KEY')
    )

    if not primary_key and not is_testing:
        if env_name in ('staging', 'stage', 'production', 'prod'):
            errors.append(
                Error(
                    "Dedicated GST encryption key (GST_ENCRYPTION_KEY) is not configured in live environment.",
                    hint="Set GST_ENCRYPTION_KEY in your environment variables to a 44-character base64 Fernet key.",
                    obj="settings.GST_ENCRYPTION_KEY",
                    id="gst.E001",
                )
            )

    # Verify Fernet initializes cleanly without raising exceptions
    if primary_key or not (env_name in ('production', 'prod') and not is_testing):
        try:
            get_gst_credential_fernet()
        except CredentialSecurityError as e:
            errors.append(
                Error(
                    f"GST Credential Encryption provider failed to initialize: {e}",
                    hint="Verify that GST_ENCRYPTION_KEY and GST_ENCRYPTION_KEY_OLD are valid Fernet keys or passphrases.",
                    obj="apps.gst.encryption",
                    id="gst.E002",
                )
            )

    return errors
