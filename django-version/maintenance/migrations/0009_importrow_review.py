import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("maintenance", "0008_importrow"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="importrow", name="review_status",
            field=models.CharField(choices=[("Pendiente", "Pendiente"), ("Excluida", "Excluida"), ("Propuesta", "Propuesta")], default="Pendiente", max_length=12),
        ),
        migrations.AddField(
            model_name="importrow", name="proposed_asset",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="import_row_proposals", to="maintenance.asset"),
        ),
        migrations.AddField(
            model_name="importrow", name="review_note",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="importrow", name="reviewed_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="reviewed_import_rows", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="importrow", name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="importrow", name="version",
            field=models.PositiveIntegerField(default=1),
        ),
    ]
