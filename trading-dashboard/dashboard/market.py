from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from dashboard.data import HOLDINGS_DATA, WATCHLIST_DATA

CACHE_DIR = Path('/home/ubuntu/.openclaw/workspace/memory/market-cache')
CACHE_FILE = CACHE_DIR / 'tushare-market-snapshots.json'
CACHE_TTL_SECONDS = 300
REQUEST_RETRIES = 2
REQUEST_RETRY_DELAY_SECONDS = 1.2
STALE_CACHE_ACCEPT_SECONDS = 172800


class MarketDataError(Exception):
    pass


@lru_cache(maxsize=1)
def _get_tushare_pro():
    try:
        import tushare as ts  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise MarketDataError(f'Tushare unavailable: {exc}') from exc

    token = os.environ.get('TUSHARE_TOKEN')
    if not token:
        raise MarketDataError('TUSHARE_TOKEN is not configured.')

    try:
        return ts.pro_api(token)
    except Exception as exc:  # noqa: BLE001
        raise MarketDataError(f'Unable to initialize Tushare client: {exc}') from exc


def _to_ts_code(code: str) -> str:
    code = code.strip()
    if code.startswith(('0', '3')):
        return f'{code}.SZ'
    return f'{code}.SH'


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:  # noqa: BLE001
        return None


def get_portfolio_codes() -> list[str]:
    codes = [item['code'] for item in HOLDINGS_DATA]
    for item in WATCHLIST_DATA:
        code = item['code']
        if code not in codes:
            codes.append(code)
    return codes


def _read_cache() -> dict[str, Any] | None:
    if not CACHE_FILE.exists():
        return None
    try:
        return json.loads(CACHE_FILE.read_text(encoding='utf-8'))
    except Exception:  # noqa: BLE001
        return None


def _write_cache(payload: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def _is_cache_fresh(payload: dict[str, Any], ttl_seconds: int = CACHE_TTL_SECONDS) -> bool:
    fetched_at = payload.get('fetched_at')
    if not fetched_at:
        return False
    try:
        fetched_dt = datetime.fromisoformat(fetched_at)
    except Exception:  # noqa: BLE001
        return False
    return (datetime.now() - fetched_dt).total_seconds() <= ttl_seconds


def _load_rows_from_cache(payload: dict[str, Any] | None, codes: list[str]) -> list[dict[str, Any]]:
    if not payload:
        return []
    rows = payload.get('rows', [])
    rows_by_code = {row.get('code'): row for row in rows if row.get('code')}
    result = []
    for code in codes:
        row = rows_by_code.get(code)
        if row:
            result.append(row)
    return result


def _attempt_fetch_snapshot(pro: Any, code: str, start_date: datetime, end_date: datetime) -> dict[str, Any]:
    ts_code = _to_ts_code(code)
    hist = pro.daily(
        ts_code=ts_code,
        start_date=start_date.strftime('%Y%m%d'),
        end_date=end_date.strftime('%Y%m%d'),
    )
    if hist is None or hist.empty:
        raise MarketDataError(f'{code}: no daily data')

    hist = hist.sort_values('trade_date').reset_index(drop=True)
    latest = hist.iloc[-1]
    prev = hist.iloc[-2] if len(hist) >= 2 else None
    close = _to_float(latest.get('close'))
    pct = _to_float(latest.get('pct_chg'))
    amount = _to_float(latest.get('amount'))
    volume = _to_float(latest.get('vol'))
    ma5 = _to_float(hist['close'].tail(5).mean()) if 'close' in hist.columns else None
    ma10 = _to_float(hist['close'].tail(10).mean()) if 'close' in hist.columns else None
    prev_close = _to_float(prev.get('close')) if prev is not None else None
    close_vs_prev = None
    if close is not None and prev_close:
        close_vs_prev = close - prev_close

    minute = None
    minute_error = None
    for minute_attempt in range(REQUEST_RETRIES + 1):
        try:
            minute_df = pro.stk_mins(
                ts_code=ts_code,
                freq='5min',
                start_date=start_date.strftime('%Y-%m-%d %H:%M:%S'),
                end_date=end_date.strftime('%Y-%m-%d %H:%M:%S'),
            )
            if minute_df is not None and not minute_df.empty:
                minute_df = minute_df.sort_values('trade_time').reset_index(drop=True)
                minute_row = minute_df.iloc[-1]
                minute = {
                    'time': str(minute_row.get('trade_time', '')),
                    'close': _to_float(minute_row.get('close')),
                    'volume': _to_float(minute_row.get('vol')),
                }
            minute_error = None
            break
        except Exception as exc:  # noqa: BLE001
            minute_error = str(exc)
            if minute_attempt < REQUEST_RETRIES:
                time.sleep(REQUEST_RETRY_DELAY_SECONDS)

    row = {
        'code': code,
        'name': '',
        'trade_date': str(latest.get('trade_date', '')),
        'close': close,
        'pct_change': pct,
        'amount': amount,
        'volume': volume,
        'ma5': ma5,
        'ma10': ma10,
        'close_vs_prev': close_vs_prev,
        'minute': minute,
    }
    if minute_error:
        row['minute_error'] = minute_error
    return row


def get_market_snapshots(codes: list[str], window_days: int = 10) -> tuple[list[dict[str, Any]], str | None, dict[str, Any]]:
    cache_payload = _read_cache()
    if cache_payload and _is_cache_fresh(cache_payload):
        cached_rows = _load_rows_from_cache(cache_payload, codes)
        if cached_rows:
            return cached_rows, cache_payload.get('warning'), {
                'source': 'cache',
                'fetched_at': cache_payload.get('fetched_at'),
                'stale': False,
                'cache_file': str(CACHE_FILE),
            }

    pro = _get_tushare_pro()
    end_date = datetime.now()
    start_date = end_date - timedelta(days=window_days)
    rows: list[dict[str, Any]] = []
    errors: list[str] = []

    for code in codes:
        row = None
        last_error = None
        for attempt in range(REQUEST_RETRIES + 1):
            try:
                row = _attempt_fetch_snapshot(pro, code, start_date, end_date)
                break
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                if attempt < REQUEST_RETRIES:
                    time.sleep(REQUEST_RETRY_DELAY_SECONDS)
        if row:
            rows.append(row)
        else:
            errors.append(f'{code}: {last_error or "fetch failed"}')

    warning = None
    if errors:
        warning = '；'.join(errors[:5])
        if len(errors) > 5:
            warning += f'；另有 {len(errors) - 5} 条错误'

    if rows:
        payload = {
            'fetched_at': datetime.now().isoformat(timespec='seconds'),
            'warning': warning,
            'rows': rows,
        }
        _write_cache(payload)
        return rows, warning, {
            'source': 'live',
            'fetched_at': payload['fetched_at'],
            'stale': False,
            'cache_file': str(CACHE_FILE),
        }

    cached_rows = _load_rows_from_cache(cache_payload, codes)
    cache_acceptable = False
    if cache_payload and cache_payload.get('fetched_at'):
        try:
            fetched_dt = datetime.fromisoformat(cache_payload['fetched_at'])
            cache_acceptable = (datetime.now() - fetched_dt).total_seconds() <= STALE_CACHE_ACCEPT_SECONDS
        except Exception:  # noqa: BLE001
            cache_acceptable = False
    if cached_rows and cache_acceptable:
        return cached_rows, f'Tushare 拉取失败，已回退到最近缓存。{warning or ""}'.strip(), {
            'source': 'cache',
            'fetched_at': cache_payload.get('fetched_at') if cache_payload else None,
            'stale': True,
            'cache_file': str(CACHE_FILE),
        }

    raise MarketDataError(warning or 'Tushare returned no usable data and no cache fallback is available.')
