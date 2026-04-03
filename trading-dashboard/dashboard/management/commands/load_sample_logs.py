from datetime import date, time

from django.core.management.base import BaseCommand
from wagtail.models import Page

from dashboard.models import WorklogEntryPage, WorklogIndexPage


SAMPLES = [
    {
        'title': '早间作战总报告',
        'slug': 'sample-morning-report',
        'log_date': date.today(),
        'log_time': time(6, 30),
        'log_type': 'morning',
        'title_note': '外围市场与情绪预判',
        'summary': '隔夜外围偏中性，今日A股更看板块轮动与核心股承接。',
        'body': '<p>重点观察持仓股与半导体、光模块方向。盘前不宜激进追高，优先看强势股回踩承接。</p>',
        'points_used': 10,
        'is_actionable': True,
        'related_symbols': '002156,300394',
    },
    {
        'title': '09:27 集合竞价观察',
        'slug': 'sample-preopen-report',
        'log_date': date.today(),
        'log_time': time(9, 27),
        'log_type': 'preopen',
        'title_note': '盘前Top观察名单',
        'summary': '持仓股与监测池筛出盘前重点观察标的。',
        'body': '<p>重点看 300394、002156 以及监测池中的强势票是否在开盘后延续竞价强度。</p>',
        'points_used': 9,
        'is_actionable': True,
        'related_symbols': '002156,300394,603986',
    },
    {
        'title': '盘后复盘示例',
        'slug': 'sample-postclose-review',
        'log_date': date.today(),
        'log_time': time(17, 30),
        'log_type': 'postclose',
        'title_note': '龙虎榜与持仓复盘',
        'summary': '盘后重点复盘持仓、监测池强弱与次日预案。',
        'body': '<p>复盘持仓表现、市场情绪、板块资金流向以及明日重点观察名单。</p>',
        'points_used': 12,
        'is_actionable': False,
        'related_symbols': '002156,300394',
    },
]


class Command(BaseCommand):
    help = 'Load sample worklog entries for development/demo.'

    def handle(self, *args, **options):
        index = WorklogIndexPage.objects.first()
        if not index:
            self.stdout.write(self.style.ERROR('WorklogIndexPage not found. Run bootstrap_site first.'))
            return

        for item in SAMPLES:
            if WorklogEntryPage.objects.filter(slug=item['slug']).exists():
                continue
            entry = WorklogEntryPage(**item)
            index.add_child(instance=entry)
            entry.save_revision().publish()
            self.stdout.write(self.style.SUCCESS(f"Created sample log: {item['title']}"))
