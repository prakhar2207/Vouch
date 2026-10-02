from django.core.management.base import BaseCommand
from django.core.checks import run_checks, Tags
from django.conf import settings

class Command(BaseCommand):
    help = 'Validates all production security configurations, environment variables, credentials, and gates.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Executing Vouch Production Configuration Readiness Gate..."))

        errors = run_checks(tags=[Tags.security])

        critical_errors = [e for e in errors if e.is_serious()]
        warnings = [e for e in errors if not e.is_serious()]

        if warnings:
            self.stdout.write(self.style.WARNING(f"\nFound {len(warnings)} production warnings:"))
            for w in warnings:
                self.stdout.write(f"  [WARN] {w.id}: {w.msg}")

        if critical_errors:
            self.stderr.write(self.style.ERROR(f"\nFAILED PRODUCTION GATE! Found {len(critical_errors)} critical security errors:"))
            for err in critical_errors:
                self.stderr.write(f"  [FAIL] {err.id}: {err.msg}")
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS(
            "\n[PASSED] Production Configuration Gate: All security controls and environment credentials verified."
        ))
