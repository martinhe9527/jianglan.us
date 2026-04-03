#!/usr/bin/env bash
set -euo pipefail
exec docker-compose logs --tail=200
