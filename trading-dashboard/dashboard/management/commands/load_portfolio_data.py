from decimal import Decimal

from django.core.management.base import BaseCommand

from dashboard.data import HOLDINGS_DATA, WATCHLIST_DATA
from dashboard.snippets import Holding, WatchlistItem


class Command(BaseCommand):
    help = 'Load holdings and watchlist snippets.'

    def handle(self, *args, **options):
        for item in WATCHLIST_DATA:
            WatchlistItem.objects.update_or_create(code=item['code'], defaults=item)
        self.stdout.write(self.style.SUCCESS(f'Loaded {len(WATCHLIST_DATA)} watchlist items'))

        for item in HOLDINGS_DATA:
            payload = item.copy()
            payload['cost'] = Decimal(payload['cost'])
            Holding.objects.update_or_create(code=payload['code'], defaults=payload)
        self.stdout.write(self.style.SUCCESS(f'Loaded {len(HOLDINGS_DATA)} holdings'))
