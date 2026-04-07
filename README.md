# jianglan.us
![Uploading image.png…]()

A trading-focused web workspace centered on execution rhythm, market observation, and daily decision support.

## Overview

This repository contains the working code and supporting assets behind `jianglan.us`.
The main application is a Django/Wagtail dashboard that combines:

- landing page branding and theming
- watchlist and holdings views
- timed trading reports
- market snapshot and intraday signal workflows
- operational scripts for scheduled execution

## Main app

The primary web application lives in [`trading-dashboard/`](./trading-dashboard).

Stack:

- Django + Wagtail
- Tailwind CSS
- PostgreSQL
- Nginx
- Docker Compose

## Repository structure

- [`trading-dashboard/`](./trading-dashboard) Django/Wagtail website and trading dashboard
- [`scripts/`](./scripts) workspace-level automation and helper scripts
- [`reports/`](./reports) generated trading reports and worklog outputs
- [`memory/`](./memory) runtime notes, state, and historical working context
- [`skills/`](./skills) reusable skills and supporting tooling

## Current focus

- improve landing page presentation and branding
- stabilize market data ingestion and fallback behavior
- strengthen watchlist, holdings, and intraday decision support
- keep the trading worklog and scheduled execution flow consistent

## Local development

Run the main app from the `trading-dashboard` directory.

```bash
cd /home/ubuntu/.openclaw/workspace/trading-dashboard
docker-compose up -d
```

Django checks:

```bash
cd /home/ubuntu/.openclaw/workspace/trading-dashboard
./.venv/bin/python manage.py check
```

## Notes

- Runtime data, reports, and environment files should be treated carefully.
- If this repository is prepared for public release, secrets, logs, caches, and private trading data should be cleaned first.

## License

Licensed under AGPL-3.0.
