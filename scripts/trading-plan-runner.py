#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path('/home/ubuntu/.openclaw/workspace')
STATE_DIR = ROOT / 'memory'
SLOTS_FILE = ROOT / 'scripts' / 'trading-plan-slots.json'
DATA_FILE = ROOT / 'scripts' / 'trading-plan-data.json'
PUSH_LOG = STATE_DIR / 'trading-plan-push.log'
REPORT_DIR = ROOT / 'reports' / 'trading-plan'


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
        sys.path.insert(0, str(ROOT / 'trading-dashboard'))
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
        f'【自动任务】{title}',
        f'时间：{now.strftime("%F %R")}',
        f'目标：{goal}',
    ]

    if holdings:
        lines.append('当前持仓：')
        for item in holdings:
            lines.append(f"- {item['code']} {item['name']}｜{item['shares']}股｜成本 {item['cost']}")
    else:
        lines.append('当前持仓：暂无可读数据')

    held_codes = {item['code'] for item in holdings}
    candidates = [item for item in watchlist if item['code'] not in held_codes][:5]
    if candidates:
        lines.append('候选观察：')
        for item in candidates:
            label = f"{item['code']} {item['name']}".strip()
            lines.append(f"- {label}｜优先级 {item['priority']}")
    else:
        lines.append('候选观察：暂无可读数据')

    lines.append('状态：当前为自动触发版，已能按时生成并记录消息；分析结论仍需继续接入数据源与策略逻辑。')
    if warning:
        lines.append(f'注意：本次读取站点数据时出现问题：{warning}')

    return '\n'.join(lines)


def save_report(slot: str, message: str):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    path = REPORT_DIR / f"{now.strftime('%F')}-{slot.replace(':', '')}.md"
    path.write_text(message + '\n', encoding='utf-8')
    return path


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

    # Placeholder for real provider push. For now, record the exact outbound payload.
    append_log(PUSH_LOG, json.dumps({
        'ts': datetime.now().isoformat(timespec='seconds'),
        'slot': slot,
        'title': slot_info.get('title', slot),
        'report': str(report_path),
        'message': message,
        'status': 'prepared'
    }, ensure_ascii=False))

    print(message)
    print(f'REPORT_PATH={report_path}')


if __name__ == '__main__':
    main()
