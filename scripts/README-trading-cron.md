# Trading Cron Setup

## Files
- `scripts/trading-day-check.sh` — checks every minute whether a trading-plan time slot should run.
- `scripts/install-trading-cron.sh` — installs the user crontab entry.

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
- Treats Monday-Friday as trading days.
- Minute-check window is limited to `09:15-11:30` and `13:00-15:00`.
- Fixed report slots are `09:27`, `09:40`, `10:30`, `11:20`, `14:00`, `14:50`, `15:05`.
- Triggers once per configured fixed slot per day.
- Configured slots are stored in `scripts/trading-plan-slots.json`.
- On each fixed slot, cron calls `scripts/trading-plan-runner.py`.
- The runner will:
  - read current holdings/watchlist from the Wagtail project when available
  - generate a concise slot message in `持仓动作 / 自选动作 / 今日重点` format
  - write a report file under `reports/trading-plan/`
  - create or update the corresponding Wagtail `WorklogEntryPage` for that slot/date
  - append the prepared outbound payload to `memory/trading-plan-push.log`
  - print the generated message into the cron log

## Current limitation
- V1 has landed on scheduling and concise fixed-slot reporting, but it is still not yet a real market-data autopilot.
- Minute-check window is only logged as active; trigger-based intraday alert logic still needs to be added.
- The generated content is based on local holdings/watchlist data and fixed slot metadata.
- Real Feishu push delivery is not yet wired through OpenClaw runtime from cron.
- Strategy logic, market data, retry policy, and final provider delivery still need to be connected.
- Exchange holidays are not yet encoded; current scheduler still treats Monday-Friday as trading days.
