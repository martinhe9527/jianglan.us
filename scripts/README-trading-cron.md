# Trading Cron Setup

## Files
- `scripts/trading-day-check.sh` — host-side thin cron trigger; decides slot timing and executes canonical scripts inside Docker `web`.
- `scripts/install-trading-cron.sh` — installs the user crontab entry.
- `trading-dashboard/scripts/trading-plan-runner.py` — canonical fixed-slot report runner, executed inside `/app`.
- `trading-dashboard/scripts/intraday_signal_engine.py` — canonical intraday signal runner, executed inside `/app`.
- `trading-dashboard/scripts/trading_calendar.py` — canonical trading calendar lookup, executed inside `/app`.

## Install
```bash
cd /home/ubuntu/.openclaw/workspace
chmod +x scripts/trading-day-check.sh scripts/install-trading-cron.sh
bash scripts/install-trading-cron.sh
```

## Verify
```bash
crontab -l
tail -f /home/ubuntu/.openclaw/workspace/memory/trading-plan-cron.log
cat /home/ubuntu/.openclaw/workspace/memory/trading-plan-state.json
```

## Current behavior
- Runs every minute.
- Uses Asia/Shanghai timezone.
- Minute-check window is limited to `09:15-11:30` and `13:00-15:00`.
- Fixed report slots are `06:30`, `09:27`, `09:35`, `10:00`, `10:30`, `11:20`, `13:10`, `14:00`, `14:28`, `14:40`, `17:30`.
- Triggers once per configured fixed slot per day.
- Configured slots are stored canonically in `trading-dashboard/scripts/trading-plan-slots.json`.
- Cron runs `scripts/trading-day-check.sh` on the host, but calendar lookup, fixed-slot report generation, and intraday signal checks are all executed inside the Docker `web` container via `docker-compose exec -T web sh -lc 'cd /app && ...'`.
- The runner will:
  - read current holdings/watchlist from the Wagtail project running in Docker
  - generate a concise slot message in `持仓动作 / 自选动作 / 今日重点` format
  - write a report file under `trading-dashboard/reports/trading-plan/`
  - create or update the corresponding Wagtail `WorklogEntryPage` for that slot/date in the Docker PostgreSQL database
  - append the prepared outbound payload to `trading-dashboard/runtime/trading-plan-push.log`
  - print the generated message into the cron log

To backfill today's online records directly into the Docker database:
```bash
docker-compose -f /home/ubuntu/.openclaw/workspace/trading-dashboard/docker-compose.yml exec -T web sh -lc "cd /app && PYTHONPATH=/app python scripts/trading-plan-runner.py 06:30"
docker-compose -f /home/ubuntu/.openclaw/workspace/trading-dashboard/docker-compose.yml exec -T web sh -lc "cd /app && PYTHONPATH=/app python scripts/trading-plan-runner.py 09:27"
docker-compose -f /home/ubuntu/.openclaw/workspace/trading-dashboard/docker-compose.yml exec -T web sh -lc "cd /app && PYTHONPATH=/app python scripts/trading-plan-runner.py 09:35"
```

To reinstall or refresh cron:
```bash
cd /home/ubuntu/.openclaw/workspace
bash scripts/install-trading-cron.sh
```

These commands assume the canonical runner/calendar/intraday scripts live under `trading-dashboard/scripts/`, which are mounted into the web container at `/app/scripts/`.

## Current limitation
- V1 has landed on scheduling and concise fixed-slot reporting, but it is still not yet a real market-data autopilot.
- Minute-check window is only logged as active; trigger-based intraday alert logic still needs to be added.
- The generated content is based on live Django holdings/watchlist data first, then container-side fallback JSON if Django read fails.
- Real Feishu push delivery is not yet wired through OpenClaw runtime from cron.
- Strategy logic, market data, retry policy, and final provider delivery still need to be connected.
- Exchange holidays are resolved from the container-side Tushare trading calendar cache, not by naive weekday checks.
