from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('dashboard', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Holding',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=20, unique=True, verbose_name='股票代码')),
                ('name', models.CharField(max_length=100, verbose_name='股票名称')),
                ('shares', models.PositiveIntegerField(default=0, verbose_name='持股数量')),
                ('cost', models.DecimalField(decimal_places=2, max_digits=12, verbose_name='持仓成本')),
                ('note', models.CharField(blank=True, max_length=255, verbose_name='备注')),
                ('active', models.BooleanField(default=True, verbose_name='是否启用')),
            ],
            options={'ordering': ['code']},
        ),
        migrations.CreateModel(
            name='WatchlistItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=20, unique=True, verbose_name='股票代码')),
                ('note', models.CharField(blank=True, max_length=255, verbose_name='备注')),
                ('priority', models.PositiveIntegerField(default=50, verbose_name='优先级')),
                ('active', models.BooleanField(default=True, verbose_name='是否启用')),
            ],
            options={'ordering': ['priority', 'code']},
        ),
    ]
