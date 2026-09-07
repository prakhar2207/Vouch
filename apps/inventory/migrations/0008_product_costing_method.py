from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0007_merge_category_prefixed_duplicates'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='costing_method',
            field=models.CharField(
                choices=[
                    ('AVG_COST', 'Average Cost'),
                    ('FIFO', 'FIFO'),
                    ('LIFO', 'LIFO'),
                    ('STD_COST', 'Standard Cost'),
                ],
                default='AVG_COST',
                max_length=20,
            ),
        ),
    ]
