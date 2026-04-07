#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = Path(os.environ.get('TRADING_RUNTIME_DIR', APP_ROOT / 'runtime'))
STATE_DIR = RUNTIME_DIR / 'trading-calendar'
ENV_FILES = [
    APP_ROOT / '.env',
    APP_ROOT / '.env.tushare',
]


def load_env_files() -> None:
    for path in ENV_FILES:
        if not path.exists():
            continue
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip())


def month_cache_path(date_text: str) -> Path:
    return STATE_DIR / f'{date_text[:7]}.json'


def read_month_cache(date_text: str) -> dict | None:
    path = month_cache_path(date_text)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def write_month_cache(date_text: str, payload: dict) -> None:
    path = month_cache_path(date_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def fetch_month_calendar(date_text: str) -> dict:
    load_env_files()
    token = os.environ.get('TUSHARE_TOKEN')
    if not token:
        raise RuntimeError('缺少 TUSHARE_TOKEN')

    import tushare as ts  # type: ignore

    dt = datetime.strptime(date_text, '%Y-%m-%d')
    month_start = dt.replace(day=1).strftime('%Y%m%d')
    if dt.month == 12:
        month_end = dt.replace(month=12, day=31).strftime('%Y%m%d')
    else:
        next_month = dt.replace(month=dt.month + 1, day=1)
        month_end = (next_month - timedelta(days=1)).strftime('%Y%m%d')

    pro = ts.pro_api(token)
    df = pro.trade_cal(exchange='SSE', start_date=month_start, end_date=month_end)
    if df is None or df.empty:
        raise RuntimeError(f'{date_text} 未返回交易日历数据')
    df = df.sort_values('cal_date')
    records = []
    for _, row in df.iterrows():
        records.append({
            'cal_date': str(row['cal_date']),
            'is_open': int(row['is_open']),
            'pretrade_date': str(row.get('pretrade_date') or ''),
        })
    payload = {
        'month': date_text[:7],
        'fetched_at': datetime.now().isoformat(timespec='seconds'),
        'records': records,
    }
    write_month_cache(date_text, payload)
    return payload


def get_calendar_status(date_text: str) -> dict:
    target = date_text.replace('-', '')
    payload = read_month_cache(date_text)
    if not payload:
        payload = fetch_month_calendar(date_text)

    records = payload.get('records', [])
    matched = next((item for item in records if item.get('cal_date') == target), None)
    if not matched:
        payload = fetch_month_calendar(date_text)
        records = payload.get('records', [])
        matched = next((item for item in records if item.get('cal_date') == target), None)
    if not matched:
        raise RuntimeError(f'交易日历中找不到日期 {date_text}')

    weekday = datetime.strptime(date_text, '%Y-%m-%d').weekday()
    weekend_plan = 'none'
    if weekday == 5:
        weekend_plan = 'sat'
    elif weekday == 6:
        weekend_plan = 'sun'

    return {
        'date': date_text,
        'is_open': bool(int(matched.get('is_open', 0))),
        'pretrade_date': matched.get('pretrade_date', ''),
        'weekend_plan': weekend_plan,
        'cache_month': payload.get('month'),
    }


def main() -> int:
    date_text = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')
    status = get_calendar_status(date_text)
    print(json.dumps(status, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
