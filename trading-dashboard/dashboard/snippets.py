from django.db import models
from wagtail.admin.panels import FieldPanel
from wagtail.snippets.models import register_snippet


@register_snippet
class Holding(models.Model):
    code = models.CharField('股票代码', max_length=20, unique=True)
    name = models.CharField('股票名称', max_length=100)
    shares = models.PositiveIntegerField('持股数量', default=0)
    cost = models.DecimalField('持仓成本', max_digits=12, decimal_places=2)
    note = models.CharField('备注', max_length=255, blank=True)
    active = models.BooleanField('是否启用', default=True)

    panels = [
        FieldPanel('code'),
        FieldPanel('name'),
        FieldPanel('shares'),
        FieldPanel('cost'),
        FieldPanel('note'),
        FieldPanel('active'),
    ]

    def __str__(self):
        return f'{self.code} {self.name}'

    class Meta:
        ordering = ['code']


@register_snippet
class WatchlistItem(models.Model):
    code = models.CharField('股票代码', max_length=20, unique=True)
    name = models.CharField('股票名称', max_length=100, blank=True)
    note = models.CharField('备注', max_length=255, blank=True)
    priority = models.PositiveIntegerField('优先级', default=50)
    active = models.BooleanField('是否启用', default=True)

    panels = [
        FieldPanel('code'),
        FieldPanel('name'),
        FieldPanel('note'),
        FieldPanel('priority'),
        FieldPanel('active'),
    ]

    def __str__(self):
        return f'{self.code} {self.name}'.strip()

    class Meta:
        ordering = ['priority', 'code']
