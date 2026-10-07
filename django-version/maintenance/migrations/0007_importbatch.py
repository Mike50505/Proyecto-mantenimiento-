import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("maintenance", "0006_preventive_applicability"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ImportBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("content_hash", models.CharField(max_length=64, unique=True)),
                ("filename", models.CharField(max_length=250)),
                ("status", models.CharField(choices=[("Revision", "En revisión"), ("Descartado", "Descartado")], default="Revision", max_length=12)),
                ("preview", models.JSONField(default=dict)),
                ("discarded_at", models.DateTimeField(blank=True, null=True)),
                ("discard_reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("discarded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="discarded_import_batches", to=settings.AUTH_USER_MODEL)),
                ("uploaded_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="import_batches", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddIndex(
            model_name="importbatch",
            index=models.Index(fields=["status", "created_at"], name="maintenance_status_8ac840_idx"),
        ),
    ]
