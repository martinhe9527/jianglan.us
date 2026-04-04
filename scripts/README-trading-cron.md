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
- Triggers once per configured slot per day.
- Configured slots are stored in `scripts/trading-plan-slots.json`.
- On each slot, cron now calls `scripts/trading-plan-runner.py`.
- The runner will:
  - read current holdings/watchlist from the Wagtail project when available
  - generate a slot message
  - write a report file under `reports/trading-plan/`
  - create or update the corresponding Wagtail `WorklogEntryPage` for that slot/date
  - append the prepared outbound payload to `memory/trading-plan-push.log`
  - print the generated message into the cron log

## Current limitation
- This is now more than a pure scheduler, but it is still not yet a real market-data autopilot.
- The generated content is based on local holdings/watchlist data and fixed slot metadata.
- Real Feishu push delivery is not yet wired through OpenClaw runtime from cron.
- Strategy logic, market data, retry policy, and final provider delivery still need to be connected.
- Exchange holidays are not yet encoded; current scheduler still treats Monday-Friday as trading days.
