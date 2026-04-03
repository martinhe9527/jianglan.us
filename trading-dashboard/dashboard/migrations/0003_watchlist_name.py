from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('dashboard', '0002_snippets'),
    ]

    operations = [
        migrations.AddField(
            model_name='watchlistitem',
            name='name',
            field=models.CharField(blank=True, max_length=100, verbose_name='股票名称'),
        ),
    ]
