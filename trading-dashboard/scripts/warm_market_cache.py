#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path('/home/ubuntu/.openclaw/workspace/trading-dashboard')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')

import django  # noqa: E402

django.setup()

from django.utils import timezone  # noqa: E402
from dashboard.market import get_market_snapshots  # noqa: E402
from dashboard.models import WorklogEntryPage, WorklogIndexPage  # noqa: E402
from dashboard.snippets import Holding, WatchlistItem  # noqa: E402

SKIP_WAGTAIL_SYNC = os.environ.get('WARM_MARKET_CACHE_SKIP_WAGTAIL', '').lower() in {'1', 'true', 'yes'}


def build_summary(rows: list[dict], warning: str | None) -> str:
    if not rows:
        summary = '市场快照预热未拿到可用行情数据。'
    else:
        parts = []
        for row in rows[:3]:
            pct = row.get('pct_change')
            pct_text = f'{pct:.2f}%' if isinstance(pct, (int, float)) else '-'
            parts.append(f"{row['code']} {row.get('name') or ''} {pct_text}".strip())
        summary = '快照预热完成：' + '；'.join(parts)
    if warning:
        summary += '｜存在告警'
    return summary[:250]


def build_body(codes: list[str], rows: list[dict], warning: str | None, meta: dict) -> str:
    lines = [
        f"缓存预热时间：{timezone.localtime().strftime('%F %R')}",
        f"股票范围：{', '.join(codes)}",
        f"数据来源：{meta.get('source', '-')}",
        f"缓存文件：{meta.get('cache_file', '-')}",
    ]
    if meta.get('fetched_at'):
        lines.append(f"抓取时间：{meta['fetched_at']}")
    if meta.get('stale'):
        lines.append('缓存状态：回退到旧缓存')
    if warning:
        lines.append(f'告警：{warning}')

    if rows:
        lines.append('行情快照：')
        for row in rows:
            pct = row.get('pct_change')
            close = row.get('close')
            ma5 = row.get('ma5')
            ma10 = row.get('ma10')
            minute = row.get('minute') or {}
            pct_text = f'{pct:.2f}%' if isinstance(pct, (int, float)) else '-'
            close_text = f'{close:.2f}' if isinstance(close, (int, float)) else '-'
            ma5_text = f'{ma5:.2f}' if isinstance(ma5, (int, float)) else '-'
            ma10_text = f'{ma10:.2f}' if isinstance(ma10, (int, float)) else '-'
            minute_text = ''
            if minute:
                minute_close = minute.get('close')
                minute_close_text = f"{minute_close:.2f}" if isinstance(minute_close, (int, float)) else '-'
                minute_text = f"；最近5分钟 {minute.get('time', '-')} close {minute_close_text}"
            lines.append(
                f"{row['code']} {row.get('name') or ''}：收盘 {close_text}，涨跌幅 {pct_text}，MA5 {ma5_text}，MA10 {ma10_text}{minute_text}"
            )

    return ''.join(f'<p>{line}</p>' for line in lines if line.strip())


def sync_to_wagtail(codes: list[str], rows: list[dict], warning: str | None, meta: dict) -> dict:
    parent = WorklogIndexPage.objects.first()
    if not parent:
        raise RuntimeError('WorklogIndexPage 不存在，无法写入缓存预热报告。')

    now = timezone.localtime()
    log_date = now.date()
    log_time = now.time().replace(second=0, microsecond=0)
    slug = f"market-cache-warm-{log_date.strftime('%Y%m%d')}-{log_time.strftime('%H%M')}"
    title = f"{log_time.strftime('%H:%M')} 市场快照缓存预热"
    summary = build_summary(rows, warning)
    body_html = build_body(codes, rows, warning, meta)
    related_symbols = ','.join(codes[:12])

    existing = WorklogEntryPage.objects.filter(slug=slug).first()
    if existing:
        existing.title = title
        existing.log_date = log_date
        existing.log_time = log_time
        existing.log_type = 'postclose'
        existing.title_note = '缓存预热自动生成'
        existing.summary = summary
        existing.body = body_html
        existing.points_used = 0
        existing.is_actionable = False
        existing.related_symbols = related_symbols
        existing.save_revision().publish()
        return {'status': 'updated', 'page_id': existing.id, 'slug': existing.slug}

    page = WorklogEntryPage(
        title=title,
        slug=slug,
        log_date=log_date,
        log_time=log_time,
        log_type='postclose',
        title_note='缓存预热自动生成',
        summary=summary,
        body=body_html,
        points_used=0,
        is_actionable=False,
        related_symbols=related_symbols,
    )
    parent.add_child(instance=page)
    page.save_revision().publish()
    return {'status': 'created', 'page_id': page.id, 'slug': page.slug}


def main() -> int:
    holdings = list(Holding.objects.filter(active=True).order_by('code'))
    watchlist = list(WatchlistItem.objects.filter(active=True).order_by('priority', 'code')[:5])

    codes: list[str] = []
    for item in holdings:
        if item.code not in codes:
            codes.append(item.code)
    for item in watchlist:
        if item.code not in codes:
            codes.append(item.code)

    rows, warning, meta = get_market_snapshots(codes)
    wagtail_sync = {'status': 'skipped'} if SKIP_WAGTAIL_SYNC else sync_to_wagtail(codes, rows, warning, meta)
    print(f'codes={codes}')
    print(f'meta={meta}')
    print(f'warning={warning}')
    print(f'rows={len(rows)}')
    print(f'wagtail_sync={wagtail_sync}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
