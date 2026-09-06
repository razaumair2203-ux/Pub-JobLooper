#!/usr/bin/env bash
# Thin wrapper. The check list and isolation live in tools/run_checks.py so the
# POSIX and PowerShell entry points can never drift apart again.
set -uo pipefail
cd "$(dirname "$0")"
exec python -B tools/run_checks.py "${1:-full}"
