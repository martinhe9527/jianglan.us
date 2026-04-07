#!/usr/bin/env bash
set -euo pipefail

TZ="Asia/Shanghai"
export TZ

ROOT="/home/ubuntu/.openclaw/workspace"
STATE_DIR="$ROOT/memory"
STATE_FILE="$STATE_DIR/trading-plan-state.json"
COMPOSE_FILE="$ROOT/trading-dashboard/docker-compose.yml"
WEB_SERVICE="web"
DOCKER_COMPOSE_BIN="$(command -v docker-compose || true)"
mkdir -p "$STATE_DIR"

if [[ -z "$DOCKER_COMPOSE_BIN" ]]; then
  echo "docker-compose not found in PATH" >&2
  exit 1
fi

run_in_web() {
  "$DOCKER_COMPOSE_BIN" -f "$COMPOSE_FILE" exec -T "$WEB_SERVICE" "$@"
}

run_in_web_app() {
  local script_name="$1"
  shift

  local quoted_args=""
  if [[ "$#" -gt 0 ]]; then
    quoted_args=$(printf " %q" "$@")
  fi

  run_in_web sh -lc "cd /app && PYTHONPATH=/app python scripts/${script_name}${quoted_args}"
}

now_date=$(date +%F)
now_hm=$(date +%H:%M)
calendar_json=$(run_in_web_app trading_calendar.py "$now_date")
is_open=$(python3 - <<'PY' "$calendar_json"
import json,sys
data=json.loads(sys.argv[1])
print('yes' if data.get('is_open') else 'no')
PY
)
weekend_plan=$(python3 - <<'PY' "$calendar_json"
import json,sys
data=json.loads(sys.argv[1])
print(data.get('weekend_plan','none'))
PY
)

TRADING_SLOTS=("06:30" "09:27" "09:35" "10:00" "10:30" "11:20" "13:10" "14:00" "14:28" "14:40" "17:30")
WEEKEND_SLOT=""
if [[ "$weekend_plan" == "sat" ]]; then
  WEEKEND_SLOT="SAT-08:30"
elif [[ "$weekend_plan" == "sun" ]]; then
  WEEKEND_SLOT="SUN-15:00"
fi

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
if [[ "$is_open" == "yes" && "$now_hm" > "09:14" && "$now_hm" < "11:31" ]]; then
  is_intraday_window="yes"
elif [[ "$is_open" == "yes" && "$now_hm" > "12:59" && "$now_hm" < "15:01" ]]; then
  is_intraday_window="yes"
fi

run_slot() {
  local slot="$1"

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

  if output=$(run_in_web_app trading-plan-runner.py "$slot" 2>&1); then
    mark_done "$slot"
    printf '%s\n' "$output"
    echo "[$(date '+%F %T')] trading-plan fixed slot finished: $slot"
    exit 0
  fi

  echo "[$(date '+%F %T')] trading-plan fixed slot failed: $slot"
  printf '%s\n' "$output" >&2
  exit 1
}

if [[ "$is_open" == "yes" ]]; then
  for slot in "${TRADING_SLOTS[@]}"; do
    if [[ "$now_hm" == "$slot" ]]; then
      run_slot "$slot"
    fi
  done
elif [[ -n "$WEEKEND_SLOT" ]]; then
  weekend_time="${WEEKEND_SLOT#*-}"
  if [[ "$now_hm" == "$weekend_time" ]]; then
    run_slot "$WEEKEND_SLOT"
  fi
fi

if [[ "$is_intraday_window" == "yes" ]]; then
  if intraday_output=$(run_in_web_app intraday_signal_engine.py 2>&1); then
    if [[ "$intraday_output" != "STATUS=no_signal" ]]; then
      echo "[$(date '+%F %T')] intraday signal engine emitted"
      printf '%s\n' "$intraday_output"
    fi
  else
    echo "[$(date '+%F %T')] intraday signal engine failed"
    printf '%s\n' "$intraday_output" >&2
    exit 1
  fi
fi

exit 0
