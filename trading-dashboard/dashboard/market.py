from __future__ import annotations

from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

from dashboard.data import HOLDINGS_DATA, WATCHLIST_DATA


class MarketDataError(Exception):
    pass


@lru_cache(maxsize=1)
def _import_akshare():
    try:
        import akshare as ak  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise MarketDataError(f'AKShare unavailable: {exc}') from exc
    return ak


def _normalize_symbol(code: str) -> str:
    if code.startswith(('6', '9')):
        return f'sh{code}'
    return f'sz{code}'


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


def get_market_snapshots(codes: list[str], window_days: int = 10) -> tuple[list[dict[str, Any]], str | None]:
    ak = _import_akshare()
    end_date = datetime.now()
    start_date = end_date - timedelta(days=window_days)
    rows: list[dict[str, Any]] = []
    errors: list[str] = []

    for code in codes:
        try:
            hist = ak.stock_zh_a_hist(
                symbol=code,
                period='daily',
                start_date=start_date.strftime('%Y%m%d'),
                end_date=end_date.strftime('%Y%m%d'),
                adjust='',
            )
            if hist is None or hist.empty:
                errors.append(f'{code}: no daily data')
                continue

            latest = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) >= 2 else None
            close = _to_float(latest.get('收盘'))
            pct = _to_float(latest.get('涨跌幅'))
            amount = _to_float(latest.get('成交额'))
            volume = _to_float(latest.get('成交量'))
            ma5 = _to_float(hist['收盘'].tail(5).mean()) if '收盘' in hist.columns else None
            ma10 = _to_float(hist['收盘'].tail(10).mean()) if '收盘' in hist.columns else None
            prev_close = _to_float(prev.get('收盘')) if prev is not None else None
            close_vs_prev = None
            if close is not None and prev_close:
                close_vs_prev = close - prev_close

            minute = None
            try:
                minute_df = ak.stock_zh_a_minute(symbol=_normalize_symbol(code), period='5', adjust='')
                if minute_df is not None and not minute_df.empty:
                    minute_row = minute_df.iloc[-1]
                    minute = {
                        'time': str(minute_row.get('day', '')),
                        'close': _to_float(minute_row.get('close')),
                        'volume': _to_float(minute_row.get('volume')),
                    }
            except Exception:
                minute = None

            rows.append({
                'code': code,
                'name': '',
                'trade_date': str(latest.get('日期', '')),
                'close': close,
                'pct_change': pct,
                'amount': amount,
                'volume': volume,
                'ma5': ma5,
                'ma10': ma10,
                'close_vs_prev': close_vs_prev,
                'minute': minute,
            })
        except Exception as exc:  # noqa: BLE001
            errors.append(f'{code}: {exc}')

    warning = None
    if errors:
        warning = '；'.join(errors[:5])
        if len(errors) > 5:
            warning += f'；另有 {len(errors) - 5} 条错误'
    return rows, warning
