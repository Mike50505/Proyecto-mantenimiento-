from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('maintenance', '0018_work_order_images')]
    operations = [migrations.AddField(
        model_name='workorderimage', name='content_type',
        field=models.CharField(default='image/jpeg', editable=False, max_length=30),
    )]
