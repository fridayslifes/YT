#!/usr/bin/env bash
# The repo's own gate: lint, tests, import sanity, change-propagation index, and post-change guard.
set -uo pipefail

cd "$(dirname "$0")"

export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/pycache}"
export RUFF_CACHE_DIR="${RUFF_CACHE_DIR:-/tmp/.ruff_cache}"

PY=".venv/bin/python"
if [ ! -x "$PY" ] || ! "$PY" -c "import sys" &>/dev/null; then
  if [ -x "/opt/homebrew/bin/python3.14" ]; then
    PY="/opt/homebrew/bin/python3.14"
    export PYTHONPATH=".:/opt/homebrew/lib/python3.14/site-packages:.venv/lib/python3.11/site-packages:${PYTHONPATH:-}"
    export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
  elif [ -x "/opt/homebrew/bin/python3" ]; then
    PY="/opt/homebrew/bin/python3"
    export PYTHONPATH=".:.venv/lib/python3.11/site-packages:${PYTHONPATH:-}"
    export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
  else
    echo "check.sh: $PY is missing. Create the venv first: uv venv --python 3.11 .venv" >&2
    exit 2
  fi
fi

RUFF=".venv/bin/ruff"

rc=0
step() {
  local label="$1"
  shift
  printf '\n=== %s ===\n' "$label"
  if "$@"; then
    echo "--- $label ok"
  else
    echo "--- FAILED: $label"
    rc=1
  fi
}

run_ruff() {
  if [ -x "$RUFF" ]; then
    "$RUFF" check tools tests
  else
    "$PY" -m ruff check tools tests
  fi
}

case "${1:-all}" in
  lint)   step "ruff"    run_ruff ;;
  test)   step "pytest"  "$PY" -m pytest -q ;;
  impact) step "impact"  "$PY" tools/master.py impact --all ;;
  guard)  step "guard"   "$PY" tools/guard.py ;;
  all)
    step "ruff"     run_ruff
    step "compile"  "$PY" -m compileall -q tools tests
    step "pytest"   "$PY" -m pytest -q
    step "impact"   "$PY" tools/master.py impact --all
    step "guard"    "$PY" tools/guard.py
    ;;
  *) echo "usage: ./check.sh [all|lint|test|impact|guard]" >&2; exit 2 ;;
esac

printf '\n'
if [ "$rc" -eq 0 ]; then
  echo "check.sh: PASS"
else
  echo "check.sh: FAIL - fix every reference the change left behind before reporting done."
fi
exit "$rc"
