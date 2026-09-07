from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0009_clean_orphan_invoice_tags_and_recalc_pix_b72'),
    ]

    operations = [
        migrations.AddField(
            model_name='voucher',
            name='buyer_name',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='voucher',
            name='buyer_address',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='voucher',
            name='buyer_gstin',
            field=models.CharField(blank=True, max_length=15, null=True),
        ),
        migrations.AddField(
            model_name='voucher',
            name='buyer_state_code',
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
        migrations.AddField(
            model_name='voucher',
            name='buyer_phone',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
