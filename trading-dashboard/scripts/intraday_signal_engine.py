#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = Path(os.environ.get('TRADING_RUNTIME_DIR', APP_ROOT / 'runtime'))
STATE_FILE = RUNTIME_DIR / 'intraday-signal-state.json'
REPORT_DIR = APP_ROOT / 'reports' / 'trading-signals'
PUSH_LOG = RUNTIME_DIR / 'trading-plan-push.log'
CACHE_DIR = RUNTIME_DIR / 'intraday-cache'
ENV_FILES = [
    APP_ROOT / '.env',
    APP_ROOT / '.env.tushare',
]

if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
if str(APP_ROOT / 'scripts') not in sys.path:
    sys.path.insert(0, str(APP_ROOT / 'scripts'))

REQUEST_RETRIES = 2
REQUEST_RETRY_DELAY_SECONDS = 1.0
SNAPSHOT_WATCH_LIMIT = 12
DEEP_WATCH_LIMIT = 2

DATA_TTLS = {
    'daily': 300,
    'weekly': 900,
    'factor': 86400,
    'daily_basic': 86400,
    'chip': 900,
    'minute': 45,
}


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


def get_pro():
    load_env_files()
    token = os.environ.get('TUSHARE_TOKEN')
    if not token:
        raise RuntimeError('缺少 TUSHARE_TOKEN')

    import tushare as ts  # type: ignore

    return ts.pro_api(token)


def to_ts_code(code: str) -> str:
    return f'{code}.SZ' if code.startswith(('0', '3')) else f'{code}.SH'


def to_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def load_portfolio():
    django_warning = None
    try:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
        import django

        django.setup()
        from dashboard.snippets import Holding, WatchlistItem  # type: ignore

        holdings = list(Holding.objects.filter(active=True).order_by('code').values('code', 'name', 'shares', 'cost', 'note'))
        watchlist = list(WatchlistItem.objects.filter(active=True).order_by('priority', 'code').values('code', 'name', 'priority', 'note'))
        return holdings, watchlist, None
    except Exception as exc:  # noqa: BLE001
        django_warning = str(exc)

    fallback_path = APP_ROOT / 'scripts' / 'trading-plan-data.json'
    payload = json.loads(fallback_path.read_text(encoding='utf-8'))
    return payload.get('holdings', []), payload.get('watchlist', []), django_warning


def fetch_with_retry(fetcher):
    last_error = None
    for attempt in range(REQUEST_RETRIES + 1):
        try:
            return fetcher()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < REQUEST_RETRIES:
                time.sleep(REQUEST_RETRY_DELAY_SECONDS)
    raise last_error  # type: ignore[misc]


def cache_path(kind: str, code: str) -> Path:
    return CACHE_DIR / kind / f'{code}.json'


def read_cache(kind: str, code: str, ttl_seconds: int):
    path = cache_path(kind, code)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None
    fetched_at = payload.get('fetched_at')
    if not fetched_at:
        return None
    try:
        age = (datetime.now() - datetime.fromisoformat(fetched_at)).total_seconds()
    except Exception:
        return None
    if age > ttl_seconds:
        return None
    return payload.get('data')


def write_cache(kind: str, code: str, data) -> None:
    path = cache_path(kind, code)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({'fetched_at': datetime.now().isoformat(timespec='seconds'), 'data': data}, ensure_ascii=False),
        encoding='utf-8',
    )


def today_cache_key() -> str:
    return datetime.now().strftime('%Y-%m-%d')


def dataframe_to_records(df):
    if df is None or df.empty:
        return []
    return df.to_dict(orient='records')


def records_to_sorted(records, field: str):
    if not records:
        return []
    return sorted(records, key=lambda item: str(item.get(field, '')))


def fetch_dataset(pro, code: str, kind: str, fetcher, sort_field: str):
    cached = read_cache(kind, code, DATA_TTLS[kind])
    if cached is not None:
        if kind in {'factor', 'daily_basic'}:
            if cached and cached[-1].get('_cache_day') == today_cache_key():
                return records_to_sorted(cached, sort_field)
        else:
            return records_to_sorted(cached, sort_field)

    df = fetch_with_retry(fetcher)
    records = dataframe_to_records(df)
    records = records_to_sorted(records, sort_field)
    if kind in {'factor', 'daily_basic'}:
        cache_day = today_cache_key()
        for item in records:
            item['_cache_day'] = cache_day
    write_cache(kind, code, records)
    return records


def load_snapshot_rows(holdings: list, watchlist: list):
    try:
        from dashboard.market import get_market_snapshots  # type: ignore
        from dashboard.focus import rank_focus_candidates  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return [], [], [f'快照模块加载失败：{exc}']

    codes = []
    for item in holdings:
        if item['code'] not in codes:
            codes.append(item['code'])
    for item in watchlist[:SNAPSHOT_WATCH_LIMIT]:
        if item['code'] not in codes:
            codes.append(item['code'])

    try:
        rows, warning, _meta = get_market_snapshots(codes)
    except Exception as exc:  # noqa: BLE001
        return [], [], [f'快照读取失败：{exc}']

    ranked = rank_focus_candidates(holdings, watchlist, rows)
    watch_candidates = ranked[:DEEP_WATCH_LIMIT]
    warnings = [warning] if warning else []
    return rows, watch_candidates, warnings


def fetch_symbol_context(pro, code: str, include_minute: bool = True) -> dict:
    ts_code = to_ts_code(code)
    daily = fetch_dataset(pro, code, 'daily', lambda: pro.daily(ts_code=ts_code, start_date='20250101'), 'trade_date')
    if not daily:
        raise RuntimeError(f'{code} 缺少 daily 数据')

    weekly = fetch_dataset(pro, code, 'weekly', lambda: pro.weekly(ts_code=ts_code, start_date='20240101'), 'trade_date')
    factors = fetch_dataset(pro, code, 'factor', lambda: pro.stk_factor(ts_code=ts_code, start_date='20250101'), 'trade_date')
    daily_basic = fetch_dataset(pro, code, 'daily_basic', lambda: pro.daily_basic(ts_code=ts_code, start_date='20250101'), 'trade_date')
    minute = fetch_dataset(pro, code, 'minute', lambda: pro.stk_mins(ts_code=ts_code, freq='1min'), 'trade_time') if include_minute else []

    chip = []
    try:
        chip = fetch_dataset(pro, code, 'chip', lambda: pro.cyq_perf(ts_code=ts_code, start_date='20250101'), 'trade_date')
    except Exception:
        chip = []

    latest_daily = daily[-1]
    prev_daily = daily[-2] if len(daily) >= 2 else None
    latest_weekly = weekly[-1] if weekly else None
    latest_factor = factors[-1] if factors else None
    latest_basic = daily_basic[-1] if daily_basic else None
    latest_minute = minute[-1] if minute else None
    latest_chip = chip[-1] if chip else None

    close = to_float(latest_daily.get('close'))
    daily_closes = [to_float(item.get('close')) for item in daily if to_float(item.get('close')) is not None]
    weekly_closes = [to_float(item.get('close')) for item in weekly if to_float(item.get('close')) is not None]
    ma5 = to_float(sum(daily_closes[-5:]) / len(daily_closes[-5:])) if len(daily_closes) >= 5 else None
    ma10 = to_float(sum(daily_closes[-10:]) / len(daily_closes[-10:])) if len(daily_closes) >= 10 else None
    weekly_ma5 = to_float(sum(weekly_closes[-5:]) / len(weekly_closes[-5:])) if len(weekly_closes) >= 5 else None
    weekly_close = to_float(latest_weekly.get('close')) if latest_weekly is not None else None

    minute_close = to_float(latest_minute.get('close')) if latest_minute is not None else close
    minute_open = to_float(latest_minute.get('open')) if latest_minute is not None else None
    intraday_pct = None
    if minute_open and minute_close:
        intraday_pct = (minute_close - minute_open) / minute_open * 100

    return {
        'code': code,
        'close': close,
        'pct_change': to_float(latest_daily.get('pct_chg')),
        'ma5': ma5,
        'ma10': ma10,
        'weekly_close': weekly_close,
        'weekly_ma5': weekly_ma5,
        'minute_close': minute_close,
        'minute_time': str(latest_minute.get('trade_time')) if latest_minute is not None else '',
        'intraday_pct': intraday_pct,
        'turnover_rate': to_float(latest_basic.get('turnover_rate')) if latest_basic is not None else None,
        'volume_ratio': to_float(latest_basic.get('volume_ratio')) if latest_basic is not None else None,
        'macd': to_float(latest_factor.get('macd')) if latest_factor is not None else None,
        'kdj_j': to_float(latest_factor.get('kdj_j')) if latest_factor is not None else None,
        'rsi_6': to_float(latest_factor.get('rsi_6')) if latest_factor is not None else None,
        'chip_focus': to_float(latest_chip.get('cost_50pct')) if latest_chip is not None else None,
        'prev_close': to_float(prev_daily.get('close')) if prev_daily is not None else None,
    }


def prefill_intraday_cache(pro, holding_codes: list[str], watch_codes: list[str]) -> dict:
    warmed = []
    errors = []

    for code in holding_codes:
        try:
            fetch_symbol_context(pro, code, include_minute=True)
            warmed.append(code)
        except Exception as exc:  # noqa: BLE001
            errors.append(f'{code}: {exc}')

    for code in watch_codes[:DEEP_WATCH_LIMIT]:
        try:
            fetch_symbol_context(pro, code, include_minute=True)
            warmed.append(code)
        except Exception as exc:  # noqa: BLE001
            errors.append(f'{code}: {exc}')

    return {'warmed': warmed, 'errors': errors}


def build_holding_signal(item: dict, ctx: dict) -> dict | None:
    cost = to_float(item.get('cost'))
    close = ctx.get('minute_close') or ctx.get('close')
    if cost is None or close is None:
        return None

    profit_pct = (close - cost) / cost * 100
    ma5 = ctx.get('ma5')
    ma10 = ctx.get('ma10')
    weekly_ma5 = ctx.get('weekly_ma5')
    weekly_close = ctx.get('weekly_close')
    macd = ctx.get('macd')
    kdj_j = ctx.get('kdj_j')
    rsi_6 = ctx.get('rsi_6')
    intraday_pct = ctx.get('intraday_pct')

    action = None
    reasons = []

    if profit_pct <= -5 or (
        isinstance(macd, (int, float)) and macd < 0 and
        isinstance(rsi_6, (int, float)) and rsi_6 < 35 and
        isinstance(close, (int, float)) and isinstance(ma10, (int, float)) and close < ma10
    ):
        action = '止损/减仓'
        reasons.append(f'现价较成本 {profit_pct:.2f}%')
        reasons.append('日线转弱')
    elif profit_pct >= 6 and (
        isinstance(kdj_j, (int, float)) and kdj_j > 85 or
        isinstance(rsi_6, (int, float)) and rsi_6 > 75
    ):
        action = '止盈/减仓'
        reasons.append(f'浮盈 {profit_pct:.2f}%')
        reasons.append('短线过热')
    elif profit_pct >= 2 and (
        isinstance(intraday_pct, (int, float)) and intraday_pct > 1.2 and
        isinstance(close, (int, float)) and isinstance(ma5, (int, float)) and close > ma5
    ):
        action = '做T减仓观察'
        reasons.append(f'浮盈 {profit_pct:.2f}%')
        reasons.append('分时偏强')
    elif profit_pct > -2 and (
        isinstance(close, (int, float)) and isinstance(ma5, (int, float)) and isinstance(ma10, (int, float)) and close > ma5 >= ma10 and
        isinstance(macd, (int, float)) and macd > 0 and
        isinstance(weekly_close, (int, float)) and isinstance(weekly_ma5, (int, float)) and weekly_close >= weekly_ma5
    ):
        action = '持有/回踩加仓观察'
        reasons.append('日周线结构未坏')
        reasons.append('MACD维持正值')

    if not action:
        return None

    return {
        'kind': 'holding',
        'code': item['code'],
        'name': item.get('name', ''),
        'action': action,
        'reason': '，'.join(reasons),
        'score': round(abs(profit_pct), 2),
    }


def build_watch_signal(item: dict, ctx: dict) -> dict | None:
    close = ctx.get('minute_close') or ctx.get('close')
    ma5 = ctx.get('ma5')
    ma10 = ctx.get('ma10')
    weekly_close = ctx.get('weekly_close')
    weekly_ma5 = ctx.get('weekly_ma5')
    pct = ctx.get('pct_change')
    intraday_pct = ctx.get('intraday_pct')
    turnover_rate = ctx.get('turnover_rate')
    volume_ratio = ctx.get('volume_ratio')
    macd = ctx.get('macd')
    kdj_j = ctx.get('kdj_j')
    rsi_6 = ctx.get('rsi_6')
    chip_focus = ctx.get('chip_focus')

    if not (
        isinstance(close, (int, float)) and isinstance(ma5, (int, float)) and isinstance(ma10, (int, float)) and
        isinstance(weekly_close, (int, float)) and isinstance(weekly_ma5, (int, float))
    ):
        return None

    if not (close > ma5 >= ma10 and weekly_close >= weekly_ma5):
        return None
    if not (isinstance(macd, (int, float)) and macd > 0):
        return None
    if not (isinstance(rsi_6, (int, float)) and 50 <= rsi_6 <= 80):
        return None
    if not (isinstance(pct, (int, float)) and pct >= 2):
        return None

    reasons = [f'涨跌幅 {pct:.2f}%']
    if isinstance(intraday_pct, (int, float)):
        reasons.append(f'分时 {intraday_pct:.2f}%')
    reasons.append('日线站上 MA5/MA10')
    reasons.append('周线未破 MA5')
    if isinstance(turnover_rate, (int, float)):
        reasons.append(f'换手 {turnover_rate:.2f}%')
    if isinstance(volume_ratio, (int, float)):
        reasons.append(f'量比 {volume_ratio:.2f}')
    if isinstance(kdj_j, (int, float)):
        reasons.append(f'KDJ-J {kdj_j:.1f}')
    if isinstance(chip_focus, (int, float)) and close >= chip_focus:
        reasons.append('筹码峰不压制')

    action = '进入今日重点股票'
    if isinstance(turnover_rate, (int, float)) and turnover_rate >= 3 and isinstance(volume_ratio, (int, float)) and volume_ratio >= 1:
        action = '买入候选'

    score = (pct or 0) + (volume_ratio or 0) + max(0, 60 - int(item.get('priority', 50) or 50)) / 20
    return {
        'kind': 'watch',
        'code': item['code'],
        'name': item.get('name', ''),
        'action': action,
        'reason': '，'.join(reasons),
        'score': round(score, 2),
    }


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {}


def save_state(payload: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def signal_signature(signal: dict) -> str:
    return f"{signal['kind']}|{signal['code']}|{signal['action']}|{signal['reason']}"


def build_message(signals: list[dict], warnings: list[str]) -> tuple[str, str]:
    now = datetime.now().strftime('%F %R')
    holdings = [item for item in signals if item['kind'] == 'holding']
    watches = [item for item in signals if item['kind'] == 'watch']

    lines = [f'【盘中机会提醒】{now}']
    summary_parts = []

    lines.append('持仓动作：')
    if holdings:
        for item in holdings:
            lines.append(f"- {item['code']} {item['name']}：{item['action']}；{item['reason']}")
        summary_parts.append('持仓 ' + '、'.join(f"{item['code']} {item['action']}" for item in holdings[:2]))
    else:
        lines.append('- 暂无新增持仓动作。')

    lines.append('买卖候选：')
    if watches:
        for item in watches:
            lines.append(f"- {item['code']} {item['name']}：{item['action']}；{item['reason']}")
        summary_parts.append('候选 ' + '、'.join(f"{item['code']} {item['action']}" for item in watches[:2]))
    else:
        lines.append('- 暂无新增买入候选。')

    if warnings:
        lines.append('注意：' + '；'.join(warnings[:3]))

    summary = '｜'.join(summary_parts) or '盘中暂无新增可操作信号'
    return '\n'.join(lines), summary[:250]


def save_report(message: str) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{datetime.now().strftime('%F-%H%M')}.md"
    path.write_text(message + '\n', encoding='utf-8')
    return path


def append_push_log(payload: dict) -> None:
    PUSH_LOG.parent.mkdir(parents=True, exist_ok=True)
    with PUSH_LOG.open('a', encoding='utf-8') as f:
        f.write(json.dumps(payload, ensure_ascii=False) + '\n')


def sync_to_wagtail(message: str, summary: str, signals: list[dict]) -> dict:
    try:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
        import django

        django.setup()
        from django.utils import timezone  # type: ignore
        from dashboard.models import WorklogEntryPage, WorklogIndexPage  # type: ignore

        parent = WorklogIndexPage.objects.first()
        if not parent:
            raise RuntimeError('WorklogIndexPage 不存在')

        now = timezone.localtime()
        slug = f"intraday-alert-{now.strftime('%Y%m%d-%H%M')}"
        body_html = ''.join(f'<p>{line}</p>' for line in message.splitlines() if line.strip())
        related_symbols = ','.join(dict.fromkeys(item['code'] for item in signals))
        title = f"{now.strftime('%H:%M')} 盘中机会提醒"

        existing = WorklogEntryPage.objects.filter(slug=slug).first()
        if existing:
            existing.title = title
            existing.log_date = now.date()
            existing.log_time = now.time().replace(second=0, microsecond=0)
            existing.log_type = 'alert'
            existing.title_note = '盘中信号自动生成'
            existing.summary = summary
            existing.body = body_html
            existing.points_used = 0
            existing.is_actionable = True
            existing.related_symbols = related_symbols
            existing.save_revision().publish()
            return {'status': 'updated', 'slug': slug, 'page_id': existing.id}

        page = WorklogEntryPage(
            title=title,
            slug=slug,
            log_date=now.date(),
            log_time=now.time().replace(second=0, microsecond=0),
            log_type='alert',
            title_note='盘中信号自动生成',
            summary=summary,
            body=body_html,
            points_used=0,
            is_actionable=True,
            related_symbols=related_symbols,
        )
        parent.add_child(instance=page)
        page.save_revision().publish()
        return {'status': 'created', 'slug': slug, 'page_id': page.id}
    except Exception as exc:  # noqa: BLE001
        return {'status': 'error', 'error': str(exc)}


def main() -> int:
    holdings, watchlist, portfolio_warning = load_portfolio()
    warnings = [portfolio_warning] if portfolio_warning else []
    pro = get_pro()
    _snapshot_rows, deep_watch_candidates, snapshot_warnings = load_snapshot_rows(holdings, watchlist)
    warnings.extend([item for item in snapshot_warnings if item])

    signals = []
    for item in holdings:
        try:
            ctx = fetch_symbol_context(pro, item['code'], include_minute=True)
            signal = build_holding_signal(item, ctx)
            if signal:
                signals.append(signal)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{item['code']} 持仓信号失败：{exc}")

    watch_targets = deep_watch_candidates
    if not watch_targets:
        holding_codes = {item['code'] for item in holdings}
        watch_targets = [item for item in watchlist if item['code'] not in holding_codes][:DEEP_WATCH_LIMIT]

    for item in watch_targets:
        try:
            ctx = fetch_symbol_context(pro, item['code'], include_minute=True)
            signal = build_watch_signal(item, ctx)
            if signal:
                signals.append(signal)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{item['code']} 监测失败：{exc}")

    signals.sort(key=lambda item: item.get('score', 0), reverse=True)
    state = load_state()
    current_signatures = [signal_signature(item) for item in signals]
    previous_signatures = state.get('signatures', [])
    new_signals = [item for item in signals if signal_signature(item) not in previous_signatures]

    save_state({
        'ts': datetime.now().isoformat(timespec='seconds'),
        'signatures': current_signatures,
    })

    if not new_signals:
        print('STATUS=no_signal')
        return 0

    message, summary = build_message(new_signals, warnings)
    report_path = save_report(message)
    wagtail_sync = sync_to_wagtail(message, summary, new_signals)
    append_push_log({
        'ts': datetime.now().isoformat(timespec='seconds'),
        'kind': 'intraday_signal',
        'signals': new_signals,
        'report': str(report_path),
        'wagtail_sync': wagtail_sync,
    })

    print('STATUS=signal')
    print(message)
    print(f'REPORT_PATH={report_path}')
    print('WAGTAIL_SYNC=' + json.dumps(wagtail_sync, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
