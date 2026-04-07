#!/usr/bin/env python3
from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path('/home/ubuntu/.openclaw/workspace')
COMPOSE_FILE = ROOT / 'trading-dashboard' / 'docker-compose.yml'


def main() -> int:
    compose_bin = subprocess.run(['bash', '-lc', 'command -v docker-compose'], capture_output=True, text=True, check=False)
    docker_compose = compose_bin.stdout.strip()
    if not docker_compose:
        raise SystemExit('docker-compose not found in PATH')

    date_arg = sys.argv[1] if len(sys.argv) > 1 else ''
    quoted_date = f' {shlex.quote(date_arg)}' if date_arg else ''
    result = subprocess.run(
        [
            docker_compose,
            '-f',
            str(COMPOSE_FILE),
            'exec',
            '-T',
            'web',
            'sh',
            '-lc',
            f'cd /app && PYTHONPATH=/app python scripts/trading_calendar.py{quoted_date}',
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
