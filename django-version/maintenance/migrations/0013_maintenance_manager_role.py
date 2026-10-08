from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("maintenance", "0012_operationalalert")]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[(role, role) for role in ("Administrador", "Jefe de mantenimiento", "Jefatura", "Técnico", "Solicitante")],
                default="Solicitante",
                max_length=30,
            ),
        ),
    ]
