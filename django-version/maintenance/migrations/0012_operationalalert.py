import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("maintenance", "0011_workorderdocument"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OperationalAlert",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_key", models.CharField(max_length=160, unique=True)),
                ("kind", models.CharField(max_length=40)),
                ("source_id", models.PositiveBigIntegerField()),
                ("area", models.CharField(blank=True, max_length=120)),
                ("title", models.CharField(max_length=250)),
                ("detail", models.TextField(blank=True)),
                ("severity", models.CharField(default="Aviso", max_length=20)),
                ("status", models.CharField(choices=[("Abierta", "Abierta"), ("Atendida", "Atendida"), ("Cerrada", "Cerrada")], db_index=True, default="Abierta", max_length=12)),
                ("handling_note", models.TextField(blank=True)),
                ("handled_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("handled_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="handled_operational_alerts", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["status", "-updated_at", "id"]},
        ),
    ]
