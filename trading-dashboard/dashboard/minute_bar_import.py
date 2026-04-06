from __future__ import annotations

import pandas as pd
from django.utils import timezone

from dashboard.models import MinuteBar


def normalize_symbol(code: str) -> str:
    return code.strip()


def to_ts_code(code: str) -> str:
    code = normalize_symbol(code)
    if code.startswith(('0', '3')):
        return f'{code}.SZ'
    return f'{code}.SH'


def import_minute_bars(symbol: str, name: str = '') -> dict:
    import os
    import tushare as ts  # type: ignore

    symbol = normalize_symbol(symbol)
    token = os.environ.get('TUSHARE_TOKEN')
    if not token:
        raise RuntimeError('TUSHARE_TOKEN is not configured.')

    pro = ts.pro_api(token)
    df = pro.stk_mins(
        ts_code=to_ts_code(symbol),
        freq='1min',
    )
    if df.empty:
        return {'symbol': symbol, 'inserted': 0, 'updated': 0, 'rows': 0}

    df = df.copy().sort_values('trade_time').reset_index(drop=True)
    inserted = 0
    updated = 0

    for _, row in df.iterrows():
        dt = pd.to_datetime(row['trade_time'])
        defaults = {
            'name': name,
            'open_price': row['open'],
            'high_price': row['high'],
            'low_price': row['low'],
            'close_price': row['close'],
            'volume': int(row.get('vol', 0) or 0),
            'amount': row.get('amount', 0) or 0,
            'source': 'tushare',
            'updated_at': timezone.now(),
        }
        obj, created = MinuteBar.objects.update_or_create(
            symbol=symbol,
            trade_date=dt.date(),
            bar_time=dt.time(),
            defaults=defaults,
        )
        if created:
            inserted += 1
        else:
            updated += 1

    return {
        'symbol': symbol,
        'inserted': inserted,
        'updated': updated,
        'rows': len(df),
    }
