import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("maintenance", "0004_asset_line_location"),
    ]

    operations = [
        migrations.CreateModel(
            name="AssetCodeEquivalence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=80)),
                ("code_key", models.CharField(max_length=80)),
                ("status", models.CharField(choices=[(value, value) for value in ("Pendiente", "Aprobada", "Rechazada")], default="Pendiente", max_length=12)),
                ("source_file", models.CharField(blank=True, max_length=250)),
                ("source_sheet", models.CharField(blank=True, max_length=120)),
                ("source_row", models.PositiveIntegerField(blank=True, null=True)),
                ("notes", models.TextField()),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("review_reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("asset", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="code_equivalences", to="maintenance.asset")),
                ("proposed_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="proposed_asset_codes", to=settings.AUTH_USER_MODEL)),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="reviewed_asset_codes", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name="assetcodeequivalence",
            constraint=models.UniqueConstraint(fields=("asset", "code_key"), name="unique_asset_code_candidate"),
        ),
        migrations.AddConstraint(
            model_name="assetcodeequivalence",
            constraint=models.UniqueConstraint(condition=models.Q(("status", "Aprobada")), fields=("code_key",), name="unique_approved_asset_code"),
        ),
    ]
