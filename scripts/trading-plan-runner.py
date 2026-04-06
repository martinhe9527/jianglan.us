#!/usr/bin/env python3
import json
import os
import site
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path('/home/ubuntu/.openclaw/workspace')
DASHBOARD_ROOT = ROOT / 'trading-dashboard'
VENV_SITE_PACKAGES = next((DASHBOARD_ROOT / '.venv' / 'lib').glob('python*/site-packages'), None)
STATE_DIR = ROOT / 'memory'
SLOTS_FILE = ROOT / 'scripts' / 'trading-plan-slots.json'
DATA_FILE = ROOT / 'scripts' / 'trading-plan-data.json'
PUSH_LOG = STATE_DIR / 'trading-plan-push.log'
REPORT_DIR = ROOT / 'reports' / 'trading-plan'

if VENV_SITE_PACKAGES and VENV_SITE_PACKAGES.exists():
    site.addsitedir(str(VENV_SITE_PACKAGES))

RISK_VENV_SITE = next((ROOT / '.venv-market' / 'lib').glob('python*/site-packages'), None)
if RISK_VENV_SITE and RISK_VENV_SITE.exists():
    site.addsitedir(str(RISK_VENV_SITE))

sys.path.insert(0, str(ROOT / 'scripts'))
from trading_risk_check import evaluate_holdings  # type: ignore


def load_json(path: Path, default):
    if not path.exists():
        return default
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


def append_log(path: Path, line: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(line.rstrip() + '\n')


def load_holdings():
    django_warning = None
    try:
        sys.path.insert(0, str(DASHBOARD_ROOT))
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
        import django
        django.setup()
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
        return holdings, watchlist, f'Django数据读取失败，已回退到本地JSON快照：{django_warning}'
    return [], [], django_warning


def build_message(slot: str, slot_info: dict, holdings: list, watchlist: list, warning: str | None):
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
                lines.append(
                    f"- {item['code']} {item['name']}：{risk['action']}；现有持仓 {item['shares']}股，{risk['reason']}"
                )
            else:
                lines.append(
                    f"- {item['code']} {item['name']}：继续观察；现有持仓 {item['shares']}股，先围绕成本 {item['cost']} 做风控。"
                )
    else:
        lines.append('- 暂无持仓数据：先不下动作。')

    held_codes = {item['code'] for item in holdings}
    watch_candidates = [item for item in watchlist if item['code'] not in held_codes][:5]
    focus_candidates = watch_candidates[:3]
    reserve_candidates = watch_candidates[3:5]

    lines.append('自选动作：')
    if focus_candidates:
        for item in focus_candidates:
            lines.append(
                f"- {item['code']} {item['name']}：保留观察；先放入观察池，等待更强确认。"
            )
        for item in reserve_candidates:
            lines.append(
                f"- {item['code']} {item['name']}：暂不列入今日重点；继续排队观察。"
            )
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


def build_summary(slot_info: dict, holdings: list, watchlist: list, warning: str | None):
    holding_text = '、'.join(
        f"{item['code']} {item['name']}" for item in holdings[:2]
    ) or '暂无持仓'
    held_codes = {item['code'] for item in holdings}
    focus_candidates = [item for item in watchlist if item['code'] not in held_codes][:2]
    focus_text = '、'.join(
        f"{item['code']} {item['name']}" for item in focus_candidates
    ) or '暂无重点'

    summary = f"持仓动作：{holding_text}｜今日重点：{focus_text}"
    if warning:
        summary += '｜数据回退'
    return summary[:250]


def build_related_symbols(holdings: list, watchlist: list):
    held_codes = [item['code'] for item in holdings]
    held_set = set(held_codes)
    candidate_codes = [item['code'] for item in watchlist if item['code'] not in held_set][:3]
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


def sync_to_wagtail(slot: str, slot_info: dict, message: str, holdings: list, watchlist: list, warning: str | None):
    try:
        if str(DASHBOARD_ROOT) not in sys.path:
            sys.path.insert(0, str(DASHBOARD_ROOT))
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
        import django
        django.setup()

        from django.utils import timezone  # type: ignore
        from dashboard.models import WorklogEntryPage, WorklogIndexPage  # type: ignore

        parent = WorklogIndexPage.objects.first()
        if not parent:
            raise RuntimeError('WorklogIndexPage 不存在，无法写入自动日志。')

        now = timezone.localtime()
        log_date = now.date()
        log_time = datetime.strptime(slot, '%H:%M').time()
        title = f"{slot} {slot_info.get('title', slot)}"
        slug = f"auto-{log_date.strftime('%Y%m%d')}-{slugify_slot(slot)}"
        summary = build_summary(slot_info, holdings, watchlist, warning)
        related_symbols = build_related_symbols(holdings, watchlist)
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

    holdings, watchlist, warning = load_holdings()
    message = build_message(slot, slot_info, holdings, watchlist, warning)
    report_path = save_report(slot, message)
    wagtail_sync = sync_to_wagtail(slot, slot_info, message, holdings, watchlist, warning)

    append_log(PUSH_LOG, json.dumps({
        'ts': datetime.now().isoformat(timespec='seconds'),
        'slot': slot,
        'title': slot_info.get('title', slot),
        'report': str(report_path),
        'message': message,
        'wagtail_sync': wagtail_sync,
        'status': 'prepared' if wagtail_sync.get('status') != 'error' else 'sync_error'
    }, ensure_ascii=False))

    print(message)
    print(f'REPORT_PATH={report_path}')
    print('WAGTAIL_SYNC=' + json.dumps(wagtail_sync, ensure_ascii=False))


if __name__ == '__main__':
    main()
