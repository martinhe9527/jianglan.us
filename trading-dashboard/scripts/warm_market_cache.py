#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path('/home/ubuntu/.openclaw/workspace/trading-dashboard')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')

import django  # noqa: E402

django.setup()

from dashboard.market import get_market_snapshots  # noqa: E402
from dashboard.snippets import Holding, WatchlistItem  # noqa: E402


def main() -> int:
    holdings = list(Holding.objects.filter(active=True).order_by('code'))
    watchlist = list(WatchlistItem.objects.filter(active=True).order_by('priority', 'code')[:5])

    codes: list[str] = []
    for item in holdings:
        if item.code not in codes:
            codes.append(item.code)
    for item in watchlist:
        if item.code not in codes:
            codes.append(item.code)

    rows, warning, meta = get_market_snapshots(codes)
    print(f'codes={codes}')
    print(f'meta={meta}')
    print(f'warning={warning}')
    print(f'rows={len(rows)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
