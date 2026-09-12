from django.apps import AppConfig


class AccountingConfig(AppConfig):
    name = 'apps.accounting'

    def ready(self):
        import apps.accounting.signals
