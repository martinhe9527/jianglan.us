from collections import Counter
from datetime import date

from django.shortcuts import render

from dashboard.focus import build_log_focus_symbols, select_focus_candidates
from dashboard.market import MarketDataError, get_market_snapshots
from dashboard.models import WorklogEntryPage
from dashboard.snippets import Holding, WatchlistItem

SCHEDULE = [
    ('06:30', '早间作战总报告', '外围市场、宏观、情绪预判、赛道消息汇总', ''),
    ('09:27', '集合竞价预选报告', '持仓竞价强弱、监测池Top 3~5筛选', ''),
    ('09:35', '开盘首轮确认', '确认真强/假强、首波承接', ''),
    ('10:00', '早盘主线确认', '板块主线、持仓与预选同步度', ''),
    ('10:30', '交易信号检查', '第一次明确买卖点/做T点识别', ''),
    ('11:20', '午前定性', '上午走势总结、午后预案', ''),
    ('13:10', '午后回流检查', '午后第一波资金方向确认', ''),
    ('14:00', '尾盘前策略检查', '是否减仓、做T回补、锁利润', ''),
    ('14:28', '尾盘资金确认扫描', '识别抢筹/抢跑、隔夜价值确认', ''),
    ('14:40', '尾盘定性与隔夜判断', '强收/弱收、次日预期', ''),
    ('17:30', '盘后复盘 + 龙虎榜', '复盘持仓、监测池、资金面与明日重点', ''),
]

def worklog_view(request):
    latest_logs = WorklogEntryPage.objects.live().public().order_by('-log_date', '-log_time', '-first_published_at')[:8]
    today_logs_qs = WorklogEntryPage.objects.live().public().filter(log_date=date.today()).order_by('-log_time', '-first_published_at')
    today_logs = today_logs_qs[:8]
    actionable_logs = WorklogEntryPage.objects.live().public().filter(is_actionable=True).order_by('-log_date', '-log_time', '-first_published_at')[:6]
    holdings = Holding.objects.filter(active=True).order_by('code')
    watchlist = WatchlistItem.objects.filter(active=True).order_by('priority', 'code')
    holding_positions = [
        {
            'code': item.code,
            'name': item.name,
            'shares': item.shares,
        }
        for item in holdings
    ]
    today_points = sum(item.points_used for item in today_logs)

    market_warning = None
    market_cards = []
    market_meta = None
    focus_symbols = []
    focus_source = 'logs'
    market_rows = []
    try:
        market_codes = []
        for item in holdings:
            market_codes.append(item.code)
        for item in watchlist[:5]:
            if item.code not in market_codes:
                market_codes.append(item.code)
        market_rows, market_warning, market_meta = get_market_snapshots(market_codes)
        name_map = {item.code: item.name for item in holdings}
        name_map.update({item.code: item.name for item in watchlist})
        holding_codes = {item.code for item in holdings}
        for row in market_rows:
            row['name'] = name_map.get(row['code'], '')
            row['is_holding'] = row['code'] in holding_codes
            market_cards.append(row)
        focus_symbols, _reserve_symbols, focus_source = select_focus_candidates(
            holdings,
            watchlist,
            market_rows,
            focus_limit=12,
            reserve_limit=0,
        )
    except MarketDataError as exc:
        market_warning = str(exc)

    if not focus_symbols:
        focus_symbols, _reserve_symbols, focus_source = select_focus_candidates(
            holdings,
            watchlist,
            [],
            focus_limit=12,
            reserve_limit=0,
        )

    if not focus_symbols:
        focus_symbols = build_log_focus_symbols(actionable_logs, holdings, watchlist)
        if focus_symbols:
            focus_source = 'logs'

    market_rows_by_code = {row['code']: row for row in market_rows if row.get('code')}
    for item in focus_symbols:
        row = market_rows_by_code.get(item.get('code'))
        if not row:
            item['realtime_close'] = None
            item['realtime_time'] = None
            item['realtime_volume'] = None
            item['realtime_open'] = None
            item['realtime_high'] = None
            item['realtime_low'] = None
            continue

        minute = row.get('minute') or {}
        item['realtime_close'] = minute.get('close')
        item['realtime_time'] = minute.get('time')
        item['realtime_volume'] = minute.get('volume')
        item['realtime_open'] = minute.get('open')
        item['realtime_high'] = minute.get('high')
        item['realtime_low'] = minute.get('low')

    today_type_counter = Counter(today_logs_qs.values_list('log_type', flat=True))
    type_map = {
        'morning': '早报',
        'preopen': '盘前',
        'intraday': '盘中',
        'postclose': '盘后',
        'alert': '提醒',
    }
    today_type_summary = [
        {'key': key, 'label': type_map.get(key, key), 'count': count}
        for key, count in today_type_counter.items()
    ]

    recorded_slots = set()
    for log in today_logs_qs:
        if log.log_time:
            recorded_slots.add(log.log_time.strftime('%H:%M'))
    ops_status = [
        {
            'time': time,
            'task': task,
            'goal': goal,
            'done': time in recorded_slots,
        }
        for time, task, goal, _points in SCHEDULE
    ]

    return render(request, 'dashboard/worklog.html', {
        'domain': 'jianglan.us',
        'site_name': 'Jianglan',
        'site_tagline': '盘口、仓位、预选池、复盘笔记。',
        'fixed_points': 96,
        'reserve_points': 120,
        'watchlist': watchlist,
        'holdings': holdings,
        'holding_positions': holding_positions,
        'today_points': today_points,
        'focus_symbols': focus_symbols[:12],
        'focus_source': focus_source,
        'schedule': SCHEDULE,
        'ops_status': ops_status,
        'today_type_summary': today_type_summary,
        'latest_logs': latest_logs,
        'today_logs': today_logs,
        'actionable_logs': actionable_logs,
        'market_cards': market_cards,
        'market_warning': market_warning,
        'market_meta': market_meta,
        'auto_refresh_seconds': 60,
    })
