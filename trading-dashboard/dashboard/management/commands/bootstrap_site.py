from datetime import date

from django.core.management.base import BaseCommand
from wagtail.models import Page, Site

from dashboard.models import WorklogEntryPage, WorklogIndexPage
from home.models import HomePage


class Command(BaseCommand):
    help = 'Bootstrap initial Wagtail pages for the trading dashboard.'

    def handle(self, *args, **options):
        root = Page.get_first_root_node()

        home = HomePage.objects.child_of(root).first()
        if not home:
            slug = 'dashboard-home'
            if Page.objects.child_of(root).filter(slug=slug).exists():
                slug = 'dashboard-home-1'
            home = HomePage(title='股神首页', slug=slug, intro='股神交易工作台首页')
            root.add_child(instance=home)
            home.save_revision().publish()
            self.stdout.write(self.style.SUCCESS('Created HomePage'))

        index = WorklogIndexPage.objects.filter(slug='worklogs').first()
        if not index:
            index = WorklogIndexPage(title='交易日志', slug='worklogs', intro='用于记录早报、盘前、盘中、盘后与提醒日志。')
            home.add_child(instance=index)
            index.save_revision().publish()
            self.stdout.write(self.style.SUCCESS('Created WorklogIndexPage'))

        if not WorklogEntryPage.objects.filter(slug='init-log').exists():
            entry = WorklogEntryPage(
                title='初始化日志',
                slug='init-log',
                log_date=date.today(),
                log_type='postclose',
                title_note='系统初始化',
                summary='交易日志系统已初始化，可继续录入每日工作日志。',
                body='<p>已创建初始站点结构、工作日志索引页和示例日志。</p>',
                points_used=0,
                is_actionable=False,
                related_symbols='002156,300394',
            )
            index.add_child(instance=entry)
            entry.save_revision().publish()
            self.stdout.write(self.style.SUCCESS('Created initial WorklogEntryPage'))

        site = Site.objects.filter(hostname='kr2-openclaw.httpd.site').first()
        if not site:
            Site.objects.create(hostname='kr2-openclaw.httpd.site', root_page=home, is_default_site=True, site_name='股神交易日志')
            self.stdout.write(self.style.SUCCESS('Created Wagtail Site'))
        else:
            site.root_page = home
            site.is_default_site = True
            site.site_name = '股神交易日志'
            site.save()
            self.stdout.write(self.style.SUCCESS('Updated Wagtail Site'))
