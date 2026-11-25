# Generated for SriLekh GST Round 2.4.4 - Database Audit Immutability & Rollback Safeguards

import django.db.models.deletion
import os
from django.conf import settings
from django.db import migrations, models


def install_frequency_audit_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            CREATE OR REPLACE FUNCTION prevent_frequency_audit_tampering_fn()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'Statutory Audit Integrity Invariant: gst_gstregistrationfrequencyauditlog records are immutable and cannot be updated or deleted.';
            END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS trg_prevent_frequency_audit_tampering ON gst_gstregistrationfrequencyauditlog;
            CREATE TRIGGER trg_prevent_frequency_audit_tampering
            BEFORE UPDATE OR DELETE ON gst_gstregistrationfrequencyauditlog
            FOR EACH ROW
            EXECUTE FUNCTION prevent_frequency_audit_tampering_fn();
        """)


def guard_frequency_trigger_rollback(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    if os.environ.get('ALLOW_AUDIT_TRIGGER_ROLLBACK', '').lower() not in ['1', 'true', 'yes']:
        raise RuntimeError(
            "Statutory Compliance Invariant: Immutability triggers on gst_gstregistrationfrequencyauditlog cannot be dropped "
            "via standard application rollback. Controlled administrative rollback requires ALLOW_AUDIT_TRIGGER_ROLLBACK=true."
        )


class Migration(migrations.Migration):

    dependencies = [
        ('gst', '0027_attribution_operation_and_frequency_audit'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='gstregistrationfrequencyauditlog',
            name='gst_registration',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='frequency_audit_logs',
                to='gst.gstregistration'
            ),
        ),
        migrations.AlterField(
            model_name='gstregistrationfrequencyauditlog',
            name='verified_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.RunPython(install_frequency_audit_trigger, guard_frequency_trigger_rollback),
    ]
