from django.db import migrations, models


def seed_catalogs(apps, schema_editor):
    CatalogEntry = apps.get_model("maintenance", "CatalogEntry")
    defaults = {
        "priority": ["Paro de máquina", "Alta", "Media", "Baja", "Seguimiento"],
        "classification": ["Mantenimiento Preventivo", "Mantenimiento Correctivo", "Mantenimiento Autónomo", "Apoyo para ajuste de máquina", "Daño de Herramental", "Daño de Fixture", "Proyecto Kaizen"],
        "specialty": ["Eléctrico 440V/110V/220V", "Mecánica", "Soldadura", "Hidráulica/Neumática", "Modificación de pieza", "Reparación de activo"],
    }
    for kind, values in defaults.items():
        for index, value in enumerate(values):
            CatalogEntry.objects.create(kind=kind, value=value, sort_order=index)


class Migration(migrations.Migration):
    dependencies = [
        ("maintenance", "0002_workorder_idempotency_hash"),
    ]

    operations = [
        migrations.CreateModel(
            name="CatalogEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[(value, value) for value in ("priority", "classification", "specialty", "area", "line", "shift")], max_length=30)),
                ("value", models.CharField(max_length=120)),
                ("active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["kind", "sort_order", "value"]},
        ),
        migrations.AddConstraint(
            model_name="catalogentry",
            constraint=models.UniqueConstraint(fields=("kind", "value"), name="unique_catalog_value"),
        ),
        migrations.RunPython(seed_catalogs, migrations.RunPython.noop),
    ]
