from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("maintenance", "0013_maintenance_manager_role")]
    operations = [
        migrations.AddField(
            model_name="user", name="custom_permissions",
            field=models.BooleanField(default=False),
        ),
    ]
