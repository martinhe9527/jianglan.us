#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = APP_ROOT / 'scripts'
RUNTIME_DIR = Path(os.environ.get('TRADING_RUNTIME_DIR', APP_ROOT / 'runtime'))
REPORT_DIR = APP_ROOT / 'reports' / 'trading-plan'
PUSH_LOG = RUNTIME_DIR / 'trading-plan-push.log'
SLOTS_FILE = SCRIPTS_DIR / 'trading-plan-slots.json'
DATA_FILE = SCRIPTS_DIR / 'trading-plan-data.json'
WARM_CACHE_SCRIPT = SCRIPTS_DIR / 'warm_market_cache.py'

if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')

from trading_risk_check import evaluate_holdings  # type: ignore
from dashboard.focus import select_focus_candidates  # type: ignore


def load_json(path: Path, default):
    if not path.exists():
        return default
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


def append_log(path: Path, line: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(line.rstrip() + '\n')


def warm_market_cache():
    if not WARM_CACHE_SCRIPT.exists():
        return {'status': 'skipped', 'reason': 'warm_market_cache.py not found'}

    env = os.environ.copy()
    env['WARM_MARKET_CACHE_SKIP_WAGTAIL'] = '1'
    env.setdefault('PYTHONPATH', str(APP_ROOT))

    try:
        result = subprocess.run(
            [sys.executable, str(WARM_CACHE_SCRIPT)],
            cwd=str(APP_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        return {'status': 'error', 'error': str(exc)}

    stdout = (result.stdout or '').strip()
    stderr = (result.stderr or '').strip()
    output = '\n'.join(part for part in [stdout, stderr] if part).strip()

    if result.returncode == 0:
        return {'status': 'ok', 'output': output}
    return {'status': 'error', 'code': result.returncode, 'output': output}


def setup_django():
    import django

    django.setup()


def load_holdings():
    django_warning = None
    try:
        setup_django()
        from dashboard.snippets import Holding, WatchlistItem  # type: ignore

        holdings = list(Holding.objects.filter(active=True).order_by('code').values('code', 'name', 'shares', 'cost', 'note'))
        watchlist = list(WatchlistItem.objects.filter(active=True).order_by('priority', 'code').values('code', 'name', 'priority', 'note'))
        return holdings, watchlist, None
    except Exception as exc:  # noqa: BLE001
        django_warning = str(exc)

    fallback = load_json(DATA_FILE, {'holdings': [], 'watchlist': []})
    holdings = fallback.get('holdings', [])
    watchlist = fallback.get('watchlist', [])
    if holdings or watchlist:
        return holdings, watchlist, f'Django数据读取失败，已回退到容器内JSON快照：{django_warning}'
    return [], [], django_warning


def load_market_snapshots(holdings: list, watchlist: list):
    try:
        setup_django()
        from dashboard.market import get_market_snapshots  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return [], f'市场快照模块加载失败：{exc}'

    codes = []
    for item in holdings:
        code = item['code']
        if code not in codes:
            codes.append(code)
    for item in watchlist[:5]:
        code = item['code']
        if code not in codes:
            codes.append(code)

    try:
        rows, market_warning, _meta = get_market_snapshots(codes)
    except Exception as exc:  # noqa: BLE001
        return [], f'市场快照读取失败：{exc}'
    return rows, market_warning


def build_message(slot: str, slot_info: dict, holdings: list, watchlist: list, market_rows: list, warning: str | None):
    now = datetime.now()
    title = slot_info.get('title', slot)
    goal = slot_info.get('goal', '')
    lines = [
        f'【{title}】{now.strftime("%F %R")}',
        f'目标：{goal}',
    ]

    risk_warning = None
    risk_map = {}
    if holdings:
        try:
            risk_results = evaluate_holdings(holdings)
            risk_map = {item['code']: item for item in risk_results}
        except Exception as exc:  # noqa: BLE001
            risk_warning = f'持仓风控判断暂未接入成功：{exc}'

    lines.append('持仓动作：')
    if holdings:
        for item in holdings[:3]:
            risk = risk_map.get(item['code'])
            if risk:
                lines.append(f"- {item['code']} {item['name']}：{risk['action']}；现有持仓 {item['shares']}股，{risk['reason']}")
            else:
                lines.append(f"- {item['code']} {item['name']}：继续观察；现有持仓 {item['shares']}股，先围绕成本 {item['cost']} 做风控。")
    else:
        lines.append('- 暂无持仓数据：先不下动作。')

    focus_candidates, reserve_candidates, focus_source = select_focus_candidates(holdings, watchlist, market_rows)

    lines.append('自选动作：')
    if focus_candidates:
        for item in focus_candidates:
            extra = ''
            if focus_source == 'snapshots' and item.get('reason'):
                extra = f"；{item['reason']}"
            lines.append(f"- {item['code']} {item['name']}：保留观察；先放入观察池，等待更强确认{extra}。")
        for item in reserve_candidates:
            lines.append(f"- {item['code']} {item['name']}：暂不列入今日重点；继续排队观察。")
    else:
        lines.append('- 暂无自选候选：先不新增重点。')

    lines.append('今日重点：')
    if focus_candidates:
        lines.append('、'.join(f"{item['code']} {item['name']}" for item in focus_candidates))
    else:
        lines.append('暂无')

    if warning:
        lines.append(f'注意：数据读取已回退，原因：{warning}')
    if risk_warning:
        lines.append(f'注意：{risk_warning}')

    return '\n'.join(lines)


def resolve_slot_time(slot: str, slot_info: dict):
    return slot_info.get('time') or (slot if ':' in slot else None)


def build_summary(slot_info: dict, holdings: list, watchlist: list, market_rows: list, warning: str | None):
    holding_text = '、'.join(f"{item['code']} {item['name']}" for item in holdings[:2]) or '暂无持仓'
    focus_candidates, _reserve_candidates, _focus_source = select_focus_candidates(holdings, watchlist, market_rows)
    focus_candidates = focus_candidates[:2]
    focus_text = '、'.join(f"{item['code']} {item['name']}" for item in focus_candidates) or '暂无重点'

    summary = f"持仓动作：{holding_text}｜今日重点：{focus_text}"
    if warning:
        summary += '｜数据回退'
    return summary[:250]


def build_related_symbols(holdings: list, watchlist: list, market_rows: list):
    held_codes = [item['code'] for item in holdings]
    focus_candidates, _reserve_candidates, _focus_source = select_focus_candidates(holdings, watchlist, market_rows)
    candidate_codes = [item['code'] for item in focus_candidates[:3]]
    codes = held_codes + candidate_codes
    seen = []
    for code in codes:
        if code not in seen:
            seen.append(code)
    return ','.join(seen[:8])


def slugify_slot(slot: str):
    return slot.replace(':', '')


def save_report(slot: str, message: str):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    path = REPORT_DIR / f"{now.strftime('%F')}-{slot.replace(':', '')}.md"
    path.write_text(message + '\n', encoding='utf-8')
    return path


def sync_to_wagtail(slot: str, slot_info: dict, message: str, holdings: list, watchlist: list, market_rows: list, warning: str | None):
    try:
        setup_django()

        from django.utils import timezone  # type: ignore
        from dashboard.models import WorklogEntryPage, WorklogIndexPage  # type: ignore

        parent = WorklogIndexPage.objects.first()
        if not parent:
            raise RuntimeError('WorklogIndexPage 不存在，无法写入自动日志。')

        now = timezone.localtime()
        log_date = now.date()
        slot_time = resolve_slot_time(slot, slot_info)
        log_time = datetime.strptime(slot_time, '%H:%M').time() if slot_time else None
        title = f"{slot} {slot_info.get('title', slot)}"
        slug = f"auto-{log_date.strftime('%Y%m%d')}-{slugify_slot(slot)}"
        summary = build_summary(slot_info, holdings, watchlist, market_rows, warning)
        related_symbols = build_related_symbols(holdings, watchlist, market_rows)
        log_type = slot_info.get('log_type', 'intraday')
        is_actionable = log_type in {'preopen', 'intraday', 'alert'}
        body_html = ''.join(f'<p>{line}</p>' for line in message.splitlines() if line.strip())

        existing = WorklogEntryPage.objects.filter(slug=slug).first()
        if existing:
            existing.title = title
            existing.log_date = log_date
            existing.log_time = log_time
            existing.log_type = log_type
            existing.summary = summary
            existing.body = body_html
            existing.points_used = 0
            existing.is_actionable = is_actionable
            existing.related_symbols = related_symbols
            existing.title_note = '自动任务生成'
            existing.save_revision().publish()
            return {'status': 'updated', 'page_id': existing.id, 'title': existing.title, 'slug': existing.slug}

        page = WorklogEntryPage(
            title=title,
            slug=slug,
            log_date=log_date,
            log_time=log_time,
            log_type=log_type,
            title_note='自动任务生成',
            summary=summary,
            body=body_html,
            points_used=0,
            is_actionable=is_actionable,
            related_symbols=related_symbols,
        )
        parent.add_child(instance=page)
        page.save_revision().publish()
        return {'status': 'created', 'page_id': page.id, 'title': page.title, 'slug': page.slug}
    except Exception as exc:  # noqa: BLE001
        return {'status': 'error', 'error': str(exc)}


def main():
    if len(sys.argv) < 2:
        raise SystemExit('Usage: trading-plan-runner.py <HH:MM>')

    slot = sys.argv[1]
    slot_map = load_json(SLOTS_FILE, {})
    slot_info = slot_map.get(slot)
    if not slot_info:
        raise SystemExit(f'Unknown slot: {slot}')

    warm_result = warm_market_cache()
    holdings, watchlist, warning = load_holdings()
    market_rows, market_warning = load_market_snapshots(holdings, watchlist)
    if market_warning:
        warning = f'{warning}；{market_warning}' if warning else market_warning
    if warm_result.get('status') == 'error':
        warm_output = warm_result.get('output') or warm_result.get('error') or 'unknown error'
        warning = f'{warning}；缓存预热失败：{warm_output}' if warning else f'缓存预热失败：{warm_output}'

    message = build_message(slot, slot_info, holdings, watchlist, market_rows, warning)
    report_path = save_report(slot, message)
    wagtail_sync = sync_to_wagtail(slot, slot_info, message, holdings, watchlist, market_rows, warning)

    append_log(PUSH_LOG, json.dumps({
        'ts': datetime.now().isoformat(timespec='seconds'),
        'slot': slot,
        'title': slot_info.get('title', slot),
        'warm_cache': warm_result,
        'report': str(report_path),
        'message': message,
        'wagtail_sync': wagtail_sync,
        'status': 'prepared' if wagtail_sync.get('status') != 'error' else 'sync_error',
    }, ensure_ascii=False))

    print('WARM_CACHE=' + json.dumps(warm_result, ensure_ascii=False))
    print(message)
    print(f'REPORT_PATH={report_path}')
    print('WAGTAIL_SYNC=' + json.dumps(wagtail_sync, ensure_ascii=False))


if __name__ == '__main__':
    main()
