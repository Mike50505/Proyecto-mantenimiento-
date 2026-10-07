from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("maintenance", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorder",
            name="idempotency_hash",
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
