from datetime import date

from django.shortcuts import render

from dashboard.models import WorklogEntryPage
from dashboard.snippets import Holding, WatchlistItem

SCHEDULE = [
    ('06:30', '早间作战总报告', '外围市场、宏观、情绪预判、赛道消息汇总', '8~12'),
    ('09:27', '集合竞价预选报告', '持仓竞价强弱、监测池Top 3~5筛选', '8~12'),
    ('09:35', '开盘首轮确认', '确认真强/假强、首波承接', '6~8'),
    ('10:00', '早盘主线确认', '板块主线、持仓与预选同步度', '6~8'),
    ('10:30', '交易信号检查', '第一次明确买卖点/做T点识别', '8~10'),
    ('11:20', '午前定性', '上午走势总结、午后预案', '6~8'),
    ('13:10', '午后回流检查', '午后第一波资金方向确认', '6~8'),
    ('14:00', '尾盘前策略检查', '是否减仓、做T回补、锁利润', '8~10'),
    ('14:28', '尾盘资金确认扫描', '识别抢筹/抢跑、隔夜价值确认', '6~8'),
    ('14:40', '尾盘定性与隔夜判断', '强收/弱收、次日预期', '8~10'),
    ('17:30', '盘后复盘 + 龙虎榜', '复盘持仓、监测池、资金面与明日重点', '10~14'),
]


def worklog_view(request):
    latest_logs = WorklogEntryPage.objects.live().public().order_by('-log_date', '-log_time', '-first_published_at')[:8]
    today_logs = WorklogEntryPage.objects.live().public().filter(log_date=date.today()).order_by('-log_time', '-first_published_at')[:8]
    actionable_logs = WorklogEntryPage.objects.live().public().filter(is_actionable=True).order_by('-log_date', '-log_time', '-first_published_at')[:6]

    return render(request, 'dashboard/worklog.html', {
        'domain': 'kr2-openclaw.httpd.site',
        'fixed_points': 96,
        'reserve_points': 120,
        'watchlist': WatchlistItem.objects.filter(active=True).order_by('priority', 'code'),
        'holdings': Holding.objects.filter(active=True).order_by('code'),
        'schedule': SCHEDULE,
        'latest_logs': latest_logs,
        'today_logs': today_logs,
        'actionable_logs': actionable_logs,
    })
