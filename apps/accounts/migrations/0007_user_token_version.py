from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_emailverificationchallenge_unique_active_challenge_per_email_and_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='token_version',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
