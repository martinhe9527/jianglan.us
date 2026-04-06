from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0004_minutebar_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='minutebar',
            name='source',
            field=models.CharField(default='tushare', max_length=32, verbose_name='数据源'),
        ),
    ]
