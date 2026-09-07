#!/usr/bin/env bash
# Joblooper first run for macOS and Linux.
#
# This exists because the guided setup is written in Python, so it cannot be
# what tells you that Python is missing. Everything here runs on a machine with
# nothing installed.
set -u
cd "$(dirname "$0")"

printf '\n  Joblooper\n  Checking what this computer already has...\n\n'

python_cmd=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 \
     && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)' >/dev/null 2>&1; then
    python_cmd="$candidate"
    break
  fi
done

if [ -n "$python_cmd" ]; then
  printf '  Python found. Starting Joblooper...\n\n'
  exec "$python_cmd" jl.py setup "$@"
fi

printf '  Python 3.10 or newer is required, and this computer does not have it.\n'
printf '  Nothing else is needed: Joblooper uses no other libraries.\n\n'

# Only offer a manager that is actually present, and show the exact command
# before running anything.
if command -v brew >/dev/null 2>&1; then
  install_cmd="brew install python@3.12"
elif command -v apt-get >/dev/null 2>&1; then
  install_cmd="sudo apt-get install -y python3"
elif command -v dnf >/dev/null 2>&1; then
  install_cmd="sudo dnf install -y python3"
elif command -v pacman >/dev/null 2>&1; then
  install_cmd="sudo pacman -S --noconfirm python"
else
  install_cmd=""
fi

if [ -z "$install_cmd" ]; then
  printf '  To install it yourself:\n\n'
  printf '      macOS   https://www.python.org/downloads/  (or install Homebrew first)\n'
  printf '      Linux   use your distribution'"'"'s package manager\n\n'
  printf '  Then run ./start.sh again.\n\n'
  exit 1
fi

printf '  It can be installed for you with:\n\n      %s\n\n' "$install_cmd"
printf '  Install Python now? [y/N] '
read -r reply
case "$reply" in
  y|Y|yes|YES) ;;
  *)
    printf '\n  Nothing was installed. Run %s yourself, then ./start.sh again.\n\n' "$install_cmd"
    exit 1
    ;;
esac

printf '\n  Installing Python...\n'
# shellcheck disable=SC2086
if $install_cmd; then
  printf '\n  Python is installed. Starting Joblooper...\n\n'
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      exec "$candidate" jl.py setup "$@"
    fi
  done
fi
printf '\n  That did not complete. Install Python 3.10+ yourself, then run ./start.sh again.\n\n'
exit 1
