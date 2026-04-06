# Trading Dashboard

Wagtail + TailwindCSS + PostgreSQL + Nginx (Docker) project scaffold.

## Stack
- Wagtail (Django CMS)
- TailwindCSS
- PostgreSQL
- Nginx
- Docker Compose

## Current status
Core Django/Wagtail app is running, with trading worklog pages, scheduled auto-log generation, and a first Tushare market snapshot panel.
Tushare access now includes local cache fallback to reduce transient upstream failures.

## Planned structure
- `config/` Django settings and URLs
- `home/` Wagtail home app
- `dashboard/` worklog/report pages
- `theme/` Tailwind frontend source
- `deploy/nginx/` Nginx config
- `scripts/` startup scripts

## Market cache warm-up
To prefill market cache manually:

```bash
cd /home/ubuntu/.openclaw/workspace/trading-dashboard
. .venv/bin/activate
python scripts/warm_market_cache.py
```

This fetches holdings + top watchlist snapshots and writes cache under `../memory/market-cache/`.
Set `TUSHARE_TOKEN` in `.env` before running the warm-up script.

## Next step
1. add market cache warm-up to scheduled jobs
2. drive `今日重点股票` from market snapshots instead of only static/action logs
3. improve retry, fallback, and ranking logic for A-share candidates
4. connect advisory outputs into the website task/worklog flow
5. verify Docker/Nginx deployment end-to-end

## Intended access
- local: `http://localhost`
- later: `http://your-domain`
