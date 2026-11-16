from django.apps import AppConfig


class GstConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.gst'

    def ready(self):
        # Register system checks
        try:
            from apps.gst import encryption_checks  # noqa: F401
        except ImportError:
            pass
