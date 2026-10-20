from django.conf import settings
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("maintenance", "0016_asset_criticality")]
    operations = [
        migrations.AddField(model_name="preventiveplan", name="simple_schedule", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="preventiveplan", name="schedule_repeat", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="preventiveplan", name="schedule_time", field=models.TimeField(blank=True, null=True)),
        migrations.AddField(model_name="preventiveplan", name="schedule_end", field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name="preventiveplan", name="schedule_user", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="preventiveplan", name="schedule_key", field=models.CharField(blank=True, max_length=120, null=True)),
        migrations.AddField(model_name="preventiveplan", name="schedule_hash", field=models.CharField(blank=True, max_length=64)),
        migrations.AddConstraint(model_name="preventiveplan", constraint=models.UniqueConstraint(fields=("schedule_user", "schedule_key"), name="unique_preventive_schedule_request")),
    ]
