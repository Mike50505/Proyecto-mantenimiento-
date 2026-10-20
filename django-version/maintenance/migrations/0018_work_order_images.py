from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('maintenance', '0017_simple_preventive_orders')]
    operations = [migrations.CreateModel(
        name='WorkOrderImage',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('kind', models.CharField(choices=[('report', 'Falla reportada'), ('completion', 'Trabajo terminado')], max_length=12)),
            ('image_content', models.BinaryField()),
            ('sha256', models.CharField(max_length=64)),
            ('width', models.PositiveIntegerField()),
            ('height', models.PositiveIntegerField()),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='work_order_images', to=settings.AUTH_USER_MODEL)),
            ('work_order', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='images', to='maintenance.workorder')),
        ],
        options={'ordering': ['created_at', 'pk'], 'constraints': [models.UniqueConstraint(fields=('work_order', 'kind', 'sha256'), name='unique_order_image_content')]},
    )]
