from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("maintenance", "0009_importrow_review")]

    operations = [
        migrations.AddField(
            model_name="importrow", name="cell_details",
            field=models.JSONField(default=dict),
        ),
    ]
