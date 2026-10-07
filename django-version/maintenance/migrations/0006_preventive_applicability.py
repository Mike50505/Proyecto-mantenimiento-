import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("maintenance", "0005_assetcodeequivalence")]

    operations = [
        migrations.AddField(model_name="preventivetask", name="applicability_status", field=models.CharField(choices=[("Pendiente", "Pendiente"), ("Interna", "Interna"), ("Externa", "Externa"), ("No aplica", "No aplica")], default="Pendiente", max_length=12)),
        migrations.AddField(model_name="preventivetask", name="applicability_reason", field=models.TextField(blank=True)),
        migrations.AddField(model_name="preventivetask", name="validated_by", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="validated_preventive_tasks", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="preventivetask", name="validated_at", field=models.DateTimeField(blank=True, null=True)),
    ]
