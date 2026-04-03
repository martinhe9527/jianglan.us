from dashboard.models import WorklogEntryPage
from dashboard.snippets import Holding, WatchlistItem


def dashboard_summary():
    latest_logs = WorklogEntryPage.objects.live().public().order_by('-log_date', '-log_time', '-first_published_at')[:8]
    actionable_logs = WorklogEntryPage.objects.live().public().filter(is_actionable=True).order_by('-log_date', '-log_time', '-first_published_at')[:6]
    holdings = Holding.objects.filter(active=True).order_by('code')
    watchlist = WatchlistItem.objects.filter(active=True).order_by('priority', 'code')

    return {
        'latest_logs': latest_logs,
        'actionable_logs': actionable_logs,
        'holdings': holdings,
        'watchlist': watchlist,
    }
