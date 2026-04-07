#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path('/home/ubuntu/.openclaw/workspace')
COMPOSE_FILE = ROOT / 'trading-dashboard' / 'docker-compose.yml'


def main() -> int:
    compose_bin = subprocess.run(['bash', '-lc', 'command -v docker-compose'], capture_output=True, text=True, check=False)
    docker_compose = compose_bin.stdout.strip()
    if not docker_compose:
        raise SystemExit('docker-compose not found in PATH')

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
            'cd /app && PYTHONPATH=/app python scripts/intraday_signal_engine.py',
        ],
        check=False,
    )
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
