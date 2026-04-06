from __future__ import annotations


def rank_focus_candidates(holdings, watchlist, market_rows):
    holding_codes = {item['code'] if isinstance(item, dict) else item.code for item in holdings}
    watch_map = {
        (item['code'] if isinstance(item, dict) else item.code): item
        for item in watchlist
    }
    ranked = []

    for row in market_rows:
        code = row.get('code')
        if not code or code in holding_codes or code not in watch_map:
            continue

        watch_item = watch_map[code]
        name = watch_item.get('name') if isinstance(watch_item, dict) else watch_item.name
        priority = watch_item.get('priority', 50) if isinstance(watch_item, dict) else watch_item.priority

        pct = row.get('pct_change')
        close = row.get('close')
        ma5 = row.get('ma5')
        ma10 = row.get('ma10')

        score = 0.0
        if isinstance(pct, (int, float)):
            score += pct * 1.6
        if isinstance(close, (int, float)) and isinstance(ma5, (int, float)) and close >= ma5:
            score += 1.5
        if isinstance(close, (int, float)) and isinstance(ma10, (int, float)) and close >= ma10:
            score += 1.0
        score += max(0, 60 - int(priority or 50)) / 20

        reasons = []
        if isinstance(pct, (int, float)):
            reasons.append(f'涨跌幅 {pct:.2f}%')
        if isinstance(close, (int, float)) and isinstance(ma5, (int, float)) and close >= ma5:
            reasons.append('站上 MA5')
        if isinstance(close, (int, float)) and isinstance(ma10, (int, float)) and close >= ma10:
            reasons.append('站上 MA10')
        reasons.append(f'优先级 {priority}')

        ranked.append({
            'code': code,
            'name': name or row.get('name') or '',
            'pct_change': pct,
            'close': close,
            'score': round(score, 2),
            'reason': ' / '.join(reasons),
        })

    ranked.sort(
        key=lambda item: (
            item['score'],
            item['pct_change'] if isinstance(item['pct_change'], (int, float)) else -999,
        ),
        reverse=True,
    )
    return ranked


def select_focus_candidates(holdings, watchlist, market_rows, focus_limit=3, reserve_limit=2):
    ranked = rank_focus_candidates(holdings, watchlist, market_rows)
    if ranked:
        return ranked[:focus_limit], ranked[focus_limit:focus_limit + reserve_limit], 'snapshots'

    holding_codes = {item['code'] if isinstance(item, dict) else item.code for item in holdings}
    watch_candidates = []
    for item in watchlist:
        code = item['code'] if isinstance(item, dict) else item.code
        if code in holding_codes:
            continue
        watch_candidates.append({
            'code': code,
            'name': item.get('name', '') if isinstance(item, dict) else item.name,
            'reason': '来自观察池顺序回退',
        })
        if len(watch_candidates) >= focus_limit + reserve_limit:
            break

    return watch_candidates[:focus_limit], watch_candidates[focus_limit:focus_limit + reserve_limit], 'watchlist'


def build_log_focus_symbols(actionable_logs, holdings, watchlist):
    holding_map = {
        (item['code'] if isinstance(item, dict) else item.code): (item['name'] if isinstance(item, dict) else item.name)
        for item in holdings
    }
    watchlist_map = {
        (item['code'] if isinstance(item, dict) else item.code): (item['name'] if isinstance(item, dict) else item.name)
        for item in watchlist
    }
    holding_codes = set(holding_map.keys())
    seen = set()
    focus_symbols = []

    for log in actionable_logs:
        raw_symbols = getattr(log, 'related_symbols', '') or ''
        for code in [part.strip() for part in raw_symbols.split(',') if part.strip()]:
            if code in seen or code in holding_codes:
                continue
            focus_symbols.append({
                'code': code,
                'name': holding_map.get(code) or watchlist_map.get(code) or '',
                'reason': '来自近期动作日志',
            })
            seen.add(code)
    return focus_symbols
