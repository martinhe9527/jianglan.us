from django.db import models
from wagtail.admin.panels import FieldPanel
from wagtail.fields import RichTextField
from wagtail.models import Page


class WorklogIndexPage(Page):
    intro = RichTextField(blank=True)
    subpage_types = ['dashboard.WorklogEntryPage']

    content_panels = Page.content_panels + [
        FieldPanel('intro'),
    ]


class WorklogEntryPage(Page):
    LOG_TYPES = [
        ('morning', '早报'),
        ('preopen', '盘前'),
        ('intraday', '盘中'),
        ('postclose', '盘后'),
        ('alert', '提醒'),
    ]

    log_date = models.DateField('日志日期')
    log_time = models.TimeField('日志时间', blank=True, null=True)
    log_type = models.CharField('日志类型', max_length=20, choices=LOG_TYPES, default='intraday')
    title_note = models.CharField('补充标题', max_length=255, blank=True)
    summary = models.TextField('摘要', blank=True)
    body = RichTextField('正文', blank=True)
    points_used = models.PositiveIntegerField('消耗积分', default=0)
    is_actionable = models.BooleanField('是否有动作价值', default=False)
    related_symbols = models.CharField('相关股票', max_length=255, blank=True, help_text='例如 300394,002156')

    parent_page_types = ['dashboard.WorklogIndexPage']
    subpage_types = []

    content_panels = Page.content_panels + [
        FieldPanel('log_date'),
        FieldPanel('log_time'),
        FieldPanel('log_type'),
        FieldPanel('title_note'),
        FieldPanel('summary'),
        FieldPanel('body'),
        FieldPanel('points_used'),
        FieldPanel('is_actionable'),
        FieldPanel('related_symbols'),
    ]

    class Meta:
        ordering = ['-log_date', '-log_time', '-first_published_at']


class MinuteBar(models.Model):
    symbol = models.CharField('股票代码', max_length=16, db_index=True)
    name = models.CharField('股票名称', max_length=64, blank=True)
    trade_date = models.DateField('交易日期', db_index=True)
    bar_time = models.TimeField('分钟时间', db_index=True)
    open_price = models.DecimalField('开盘价', max_digits=12, decimal_places=3)
    high_price = models.DecimalField('最高价', max_digits=12, decimal_places=3)
    low_price = models.DecimalField('最低价', max_digits=12, decimal_places=3)
    close_price = models.DecimalField('收盘价', max_digits=12, decimal_places=3)
    volume = models.BigIntegerField('成交量', default=0)
    amount = models.DecimalField('成交额', max_digits=20, decimal_places=3, default=0)
    source = models.CharField('数据源', max_length=32, default='tushare')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['-trade_date', '-bar_time', 'symbol']
        constraints = [
            models.UniqueConstraint(
                fields=['symbol', 'trade_date', 'bar_time'],
                name='unique_symbol_trade_date_bar_time',
            )
        ]

    def __str__(self):
        return f'{self.symbol} {self.trade_date} {self.bar_time}'
