# Trading Dashboard

Wagtail + TailwindCSS + PostgreSQL + Nginx (Docker) project scaffold.

## Stack
- Wagtail (Django CMS)
- TailwindCSS
- PostgreSQL
- Nginx
- Docker Compose

## Current status
This is an initial deployment scaffold. The container layout and env structure are ready.
The Django/Wagtail app itself still needs to be generated and wired.

## Planned structure
- `config/` Django settings and URLs
- `home/` Wagtail home app
- `dashboard/` worklog/report pages
- `theme/` Tailwind frontend source
- `deploy/nginx/` Nginx config
- `scripts/` startup scripts

## Next step
After you provide the domain, I can continue with:
1. generate the Wagtail project
2. wire Tailwind build
3. add worklog/report page models
4. configure Nginx server_name and reverse proxy
5. prepare production `.env`

## Intended access
- local: `http://localhost`
- later: `http://your-domain`
