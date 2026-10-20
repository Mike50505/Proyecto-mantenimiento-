from django.db import migrations, models


def migrate_criticality(apps, schema_editor):
    Asset = apps.get_model("maintenance", "Asset")
    assets = Asset._base_manager.using(schema_editor.connection.alias)
    assets.filter(critical=True).update(criticality="A")
    assets.filter(critical=False).update(criticality="C")


class Migration(migrations.Migration):
    dependencies = [("maintenance", "0015_audited_soft_deletion")]
    operations = [
        migrations.AddField(
            model_name="asset", name="criticality",
            field=models.CharField(choices=[("A", "Muy crítico"), ("B", "Medianamente crítico"), ("C", "La producción puede seguir sin él")], default="C", max_length=1),
        ),
        migrations.RunPython(migrate_criticality, migrations.RunPython.noop),
    ]
