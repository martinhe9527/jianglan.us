#!/usr/bin/env bash
set -euo pipefail

TZ="Asia/Shanghai"
export TZ

ROOT="/home/ubuntu/.openclaw/workspace"
STATE_DIR="$ROOT/memory"
STATE_FILE="$STATE_DIR/trading-plan-state.json"
RUNNER="$ROOT/scripts/trading-plan-runner.py"
mkdir -p "$STATE_DIR"

now_date=$(date +%F)
now_hm=$(date +%H:%M)
weekday=$(date +%u)

# Trading days: Mon-Fri only (exchange holidays not yet encoded)
if [[ "$weekday" -gt 5 ]]; then
  exit 0
fi

FIXED_SLOTS=("09:27" "09:40" "10:30" "11:20" "14:00" "14:50" "15:05")

if [[ ! -f "$STATE_FILE" ]]; then
  printf '{"date":"%s","done":[]}\n' "$now_date" > "$STATE_FILE"
fi

state_date=$(python3 - <<'PY' "$STATE_FILE"
import json,sys
p=sys.argv[1]
with open(p,'r',encoding='utf-8') as f:
    data=json.load(f)
print(data.get('date',''))
PY
)

if [[ "$state_date" != "$now_date" ]]; then
  printf '{"date":"%s","done":[]}\n' "$now_date" > "$STATE_FILE"
fi

mark_done() {
  local slot="$1"
  python3 - <<'PY' "$STATE_FILE" "$slot"
import json,sys
p,slot=sys.argv[1],sys.argv[2]
with open(p,'r',encoding='utf-8') as f:
    data=json.load(f)
done=data.setdefault('done',[])
if slot not in done:
    done.append(slot)
with open(p,'w',encoding='utf-8') as f:
    json.dump(data,f,ensure_ascii=False)
PY
}

is_intraday_window="no"
if [[ "$now_hm" > "09:14" && "$now_hm" < "11:31" ]]; then
  is_intraday_window="yes"
elif [[ "$now_hm" > "12:59" && "$now_hm" < "15:01" ]]; then
  is_intraday_window="yes"
fi

for slot in "${FIXED_SLOTS[@]}"; do
  if [[ "$now_hm" != "$slot" ]]; then
    continue
  fi

  already_done=$(python3 - <<'PY' "$STATE_FILE" "$slot"
import json,sys
p,slot=sys.argv[1],sys.argv[2]
with open(p,'r',encoding='utf-8') as f:
    data=json.load(f)
print('yes' if slot in data.get('done',[]) else 'no')
PY
)

  if [[ "$already_done" == "yes" ]]; then
    exit 0
  fi

  echo "[$(date '+%F %T')] trading-plan fixed slot triggered: $slot"

  if output=$(python3 "$RUNNER" "$slot" 2>&1); then
    mark_done "$slot"
    printf '%s\n' "$output"
    echo "[$(date '+%F %T')] trading-plan fixed slot finished: $slot"
    exit 0
  fi

  echo "[$(date '+%F %T')] trading-plan fixed slot failed: $slot"
  printf '%s\n' "$output" >&2
  exit 1
done

if [[ "$is_intraday_window" == "yes" ]]; then
  echo "[$(date '+%F %T')] trading-plan minute check window active"
fi

exit 0
