from __future__ import annotations

import json
import os
import signal
import time
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dashboard.data import HOLDINGS_DATA, WATCHLIST_DATA

APP_ROOT = Path(__file__).resolve().parents[1]
LOCAL_TZ = ZoneInfo('Asia/Shanghai')
RUNTIME_DIR = Path(os.getenv('TRADING_RUNTIME_DIR', APP_ROOT / 'runtime'))
CACHE_DIR = RUNTIME_DIR / 'market-cache'
CACHE_FILE = CACHE_DIR / 'tushare-market-snapshots.json'
CACHE_TTL_SECONDS = 300
REQUEST_RETRIES = 2
REQUEST_RETRY_DELAY_SECONDS = 1.2
STALE_CACHE_ACCEPT_SECONDS = 172800
FAILED_FETCH_RETRY_COOLDOWN_SECONDS = int(os.getenv('MARKET_FAILED_FETCH_RETRY_COOLDOWN_SECONDS', '180'))
LIVE_DECISION_MAX_AGE_SECONDS = int(os.getenv('MARKET_LIVE_DECISION_MAX_AGE_SECONDS', '900'))
FETCH_TIMEOUT_SECONDS = float(os.getenv('MARKET_FETCH_TIMEOUT_SECONDS', '4'))
MARKET_LIVE_FETCH_ENABLED = os.getenv('MARKET_LIVE_FETCH_ENABLED', '').lower() in {'1', 'true', 'yes', 'on'}


class MarketDataError(Exception):
    pass


class MarketFetchTimeoutError(TimeoutError):
    pass


class _deadline:
    def __init__(self, seconds: float):
        self.seconds = max(seconds, 0)
        self._previous = None

    def _handle_timeout(self, _signum, _frame):
        raise MarketFetchTimeoutError(f'Tushare request timed out after {self.seconds:.1f}s')

    def __enter__(self):
        self._previous = signal.signal(signal.SIGALRM, self._handle_timeout)
        signal.setitimer(signal.ITIMER_REAL, self.seconds)

    def __exit__(self, exc_type, exc, tb):
        signal.setitimer(signal.ITIMER_REAL, 0)
        if self._previous is not None:
            signal.signal(signal.SIGALRM, self._previous)


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
    if code.endswith(('.SZ', '.SH', '.BJ')):
        return code
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


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except Exception:  # noqa: BLE001
        return None


def _seconds_since(value: Any) -> float | None:
    parsed = _parse_iso_datetime(value)
    if parsed is None:
        return None
    return max((datetime.now() - parsed).total_seconds(), 0)


def _is_cache_fresh(payload: dict[str, Any], ttl_seconds: int = CACHE_TTL_SECONDS) -> bool:
    age_seconds = _seconds_since(payload.get('fetched_at'))
    return age_seconds is not None and age_seconds <= ttl_seconds


def _format_age_text(age_seconds: float | None) -> str:
    if age_seconds is None:
        return '时间未知'
    if age_seconds < 60:
        return '刚刚更新'
    if age_seconds < 3600:
        return f'{int(age_seconds // 60)} 分钟前'
    if age_seconds < 86400:
        return f'{int(age_seconds // 3600)} 小时前'
    return f'{int(age_seconds // 86400)} 天前'


def _format_display_time(value: Any, short: bool = False) -> str | None:
    parsed = _parse_iso_datetime(value)
    if parsed is None:
        return None
    local_dt = parsed.astimezone(LOCAL_TZ)
    return local_dt.strftime('%m-%d %H:%M' if short else '%Y-%m-%d %H:%M:%S')


def _build_meta(
    payload: dict[str, Any] | None,
    *,
    source: str,
    stale: bool,
    warning: str | None = None,
    fetch_skipped: bool = False,
) -> dict[str, Any]:
    fetched_at = payload.get('fetched_at') if payload else None
    age_seconds = _seconds_since(fetched_at)
    last_live_error = payload.get('last_live_error') if payload else None
    live_fetch_disabled = not MARKET_LIVE_FETCH_ENABLED

    if source == 'live':
        status = '实时'
        explanation = '已完成本轮拉取，可用于当前跟踪。'
    elif stale:
        status = '回退缓存'
        explanation = '实时拉取不可用，当前仅供参考，不宜直接据此做盘中决策。'
    else:
        status = '缓存'
        explanation = '最近缓存复用，适合看盘跟踪，不等同实时盘口。'

    source_label = {
        'live': '实时拉取',
        'cache': '最近缓存',
        'fallback_cache': '回退缓存',
    }.get(source, source)

    if fetch_skipped and last_live_error:
        explanation = f'近期实时拉取失败，先复用缓存。{explanation}'
    elif live_fetch_disabled and source != 'live':
        explanation = f'实时拉取已关闭。{explanation}'

    is_live_usable = age_seconds is not None and age_seconds <= LIVE_DECISION_MAX_AGE_SECONDS and source == 'live'
    if source == 'live':
        decision_hint = '可作盘中参考' if is_live_usable else '更适合跟踪观察'
    elif source == 'cache':
        decision_hint = '适合跟踪观察，不等同实时盘口'
    else:
        decision_hint = '仅作回退参考，别直接据此做盘中决策'

    return {
        'source': source,
        'source_label': source_label,
        'status': status,
        'status_label': status,
        'fetched_at': fetched_at,
        'fetched_at_short': _format_display_time(fetched_at, short=True),
        'age_seconds': age_seconds,
        'age_text': _format_age_text(age_seconds),
        'stale': stale,
        'warning': warning,
        'last_live_error': last_live_error,
        'last_attempt_at': payload.get('last_attempt_at') if payload else None,
        'last_attempt_at_short': _format_display_time(payload.get('last_attempt_at') if payload else None, short=True),
        'fetch_skipped': fetch_skipped,
        'fetch_retry_after_seconds': FAILED_FETCH_RETRY_COOLDOWN_SECONDS,
        'is_live_usable': is_live_usable,
        'decision_hint': decision_hint,
        'explanation': explanation,
        'cache_file': str(CACHE_FILE),
    }


def _should_cooldown_after_failed_fetch(payload: dict[str, Any] | None) -> bool:
    if not payload or not payload.get('last_live_error'):
        return False
    since_attempt = _seconds_since(payload.get('last_attempt_at'))
    return since_attempt is not None and since_attempt <= FAILED_FETCH_RETRY_COOLDOWN_SECONDS


def _record_fetch_attempt(
    payload: dict[str, Any] | None,
    *,
    warning: str | None,
    success: bool,
    fetched_at: str | None = None,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    updated = dict(payload or {})
    updated['last_attempt_at'] = datetime.now().isoformat(timespec='seconds')
    updated['last_live_error'] = None if success else warning
    if success:
        updated['fetched_at'] = fetched_at
        updated['warning'] = warning
        updated['rows'] = rows or []
    _write_cache(updated)
    return updated


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


def get_cached_market_snapshots(
    codes: list[str],
    allow_stale: bool = True,
) -> tuple[list[dict[str, Any]], str | None, dict[str, Any] | None]:
    payload = _read_cache()
    if not payload:
        return [], None, None

    rows = _load_rows_from_cache(payload, codes)
    if not rows:
        return [], None, None

    stale = not _is_cache_fresh(payload)
    if stale and not allow_stale:
        return [], None, None

    warning = payload.get('warning')
    if stale:
        warning = '当前展示为缓存行情。' if not warning else f'当前展示为缓存行情。{warning}'

    source = 'fallback_cache' if stale else 'cache'
    return rows, warning, _build_meta(payload, source=source, stale=stale, warning=warning)


def _attempt_fetch_snapshot(pro: Any, code: str, start_date: datetime, end_date: datetime) -> dict[str, Any]:
    ts_code = _to_ts_code(code)
    with _deadline(FETCH_TIMEOUT_SECONDS):
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
            with _deadline(FETCH_TIMEOUT_SECONDS):
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
    cached_rows, cached_warning, cached_meta = get_cached_market_snapshots(codes, allow_stale=True)
    if cached_meta and not cached_meta.get('stale'):
        return cached_rows, cached_warning, cached_meta

    if not MARKET_LIVE_FETCH_ENABLED:
        if cached_rows and cached_meta:
            disabled_meta = _build_meta(cache_payload, source=cached_meta.get('source', 'cache'), stale=bool(cached_meta.get('stale')), warning=cached_warning)
            return cached_rows, cached_warning, disabled_meta
        raise MarketDataError('Live market fetch is disabled and no cache is available.')

    if cached_rows and _should_cooldown_after_failed_fetch(cache_payload):
        cooldown_warning = cache_payload.get('last_live_error') or cached_warning
        cooldown_meta = _build_meta(
            cache_payload,
            source='fallback_cache' if cached_meta and cached_meta.get('stale') else 'cache',
            stale=True,
            warning=cooldown_warning,
            fetch_skipped=True,
        )
        return cached_rows, cooldown_warning, cooldown_meta

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
        fetched_at = datetime.now().isoformat(timespec='seconds')
        payload = _record_fetch_attempt(
            cache_payload,
            warning=warning,
            success=True,
            fetched_at=fetched_at,
            rows=rows,
        )
        return rows, warning, _build_meta(payload, source='live', stale=False, warning=warning)

    cached_rows = _load_rows_from_cache(cache_payload, codes)
    cache_acceptable = False
    if cache_payload and cache_payload.get('fetched_at'):
        try:
            fetched_dt = datetime.fromisoformat(cache_payload['fetched_at'])
            cache_acceptable = (datetime.now() - fetched_dt).total_seconds() <= STALE_CACHE_ACCEPT_SECONDS
        except Exception:  # noqa: BLE001
            cache_acceptable = False
    if cached_rows and cache_acceptable:
        fallback_warning = f'Tushare 拉取失败，已回退到最近缓存。{warning or ""}'.strip()
        updated_payload = _record_fetch_attempt(cache_payload, warning=warning, success=False)
        return cached_rows, fallback_warning, _build_meta(
            updated_payload,
            source='fallback_cache',
            stale=True,
            warning=fallback_warning,
        )

    raise MarketDataError(warning or 'Tushare returned no usable data and no cache fallback is available.')
