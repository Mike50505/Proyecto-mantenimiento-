from django.conf import settings
import django.contrib.auth.models
import django.db.models.deletion
from django.db import migrations, models
import maintenance.models


class Migration(migrations.Migration):
    dependencies = [('maintenance', '0014_user_custom_permissions')]
    operations = [
        migrations.AddField(model_name='user', name='deleted_at', field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name='user', name='deleted_by', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name='user', name='deletion_reason', field=models.TextField(blank=True)),
        migrations.AlterModelManagers(name='user', managers=[('objects', maintenance.models.LiveUserManager()), ('all_objects', django.contrib.auth.models.UserManager())]),
        migrations.AddField(model_name='asset', name='deleted_at', field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name='asset', name='deleted_by', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name='asset', name='deletion_reason', field=models.TextField(blank=True)),
        migrations.AlterModelManagers(name='asset', managers=[('objects', maintenance.models.LiveManager())]),
        migrations.AddField(model_name='workorder', name='deleted_at', field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name='workorder', name='deleted_by', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name='workorder', name='deletion_reason', field=models.TextField(blank=True)),
        migrations.AlterModelManagers(name='workorder', managers=[('objects', maintenance.models.LiveManager())]),
        migrations.AddField(model_name='inventoryitem', name='deleted_at', field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name='inventoryitem', name='deleted_by', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name='inventoryitem', name='deletion_reason', field=models.TextField(blank=True)),
        migrations.AlterModelManagers(name='inventoryitem', managers=[('objects', maintenance.models.LiveManager())]),
    ]
