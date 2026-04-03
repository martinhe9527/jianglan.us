from decimal import Decimal

from django.core.management.base import BaseCommand

from dashboard.snippets import Holding, WatchlistItem

WATCHLIST = [
    '002565','002361','603601','301005','002131','300136','002413','000559','600105','002195','603667','002050','603778','600171','600460','600584','002156','002149','300308','300502','300604','002709','600089','002371','300394','688008','002202','300223','002837','603986','301200','300014'
]

HOLDINGS = [
    {'code': '002156', 'name': '通富微电', 'shares': 2500, 'cost': Decimal('47.50'), 'note': '持仓优先跟踪'},
    {'code': '300394', 'name': '天孚通信', 'shares': 200, 'cost': Decimal('339.50'), 'note': '2026-04-03 上午买入'},
]


class Command(BaseCommand):
    help = 'Load holdings and watchlist snippets.'

    def handle(self, *args, **options):
        for item in WATCHLIST:
            WatchlistItem.objects.get_or_create(code=item)
        self.stdout.write(self.style.SUCCESS(f'Loaded {len(WATCHLIST)} watchlist items'))

        for item in HOLDINGS:
            Holding.objects.update_or_create(code=item['code'], defaults=item)
        self.stdout.write(self.style.SUCCESS(f'Loaded {len(HOLDINGS)} holdings'))
