#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export PORT="${PORT:-8001}"
exec .venv/bin/python server.py
