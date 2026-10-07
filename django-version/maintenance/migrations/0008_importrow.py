import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("maintenance", "0007_importbatch")]

    operations = [
        migrations.CreateModel(
            name="ImportRow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sheet", models.CharField(max_length=120)),
                ("source_row", models.PositiveIntegerField()),
                ("cells", models.JSONField(default=dict)),
                ("formulas", models.JSONField(default=dict)),
                ("source_code", models.CharField(blank=True, max_length=300)),
                ("issues", models.JSONField(default=list)),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="source_rows", to="maintenance.importbatch")),
            ],
            options={"ordering": ["sheet", "source_row", "id"]},
        ),
        migrations.AddConstraint(
            model_name="importrow",
            constraint=models.UniqueConstraint(fields=("batch", "sheet", "source_row"), name="unique_import_source_row"),
        ),
        migrations.AddIndex(
            model_name="importrow",
            index=models.Index(fields=["batch", "sheet", "source_row"], name="maintenance_import_rows_idx"),
        ),
    ]
