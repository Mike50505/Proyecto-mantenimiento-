from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("maintenance", "0003_catalogentry"),
    ]

    operations = [
        migrations.AddField(
            model_name="asset",
            name="line",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="asset",
            name="location_detail",
            field=models.CharField(blank=True, max_length=250),
        ),
    ]
