#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec /Users/pengpjiang/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 app.py
