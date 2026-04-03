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
