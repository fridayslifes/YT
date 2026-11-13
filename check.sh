#!/usr/bin/env bash
# The repo's own gate: lint, tests, import sanity, change-propagation index, and post-change guard.
set -uo pipefail

cd "$(dirname "$0")"

export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/pycache}"
export RUFF_CACHE_DIR="${RUFF_CACHE_DIR:-/tmp/.ruff_cache}"

PY=".venv/bin/python"
if [ ! -x "$PY" ] || ! "$PY" -c "import sys" &>/dev/null; then
  if command -v python3 >/dev/null 2>&1; then
    PY="$(command -v python3)"
    export PYTHONPATH=".:${PYTHONPATH:-}"
    for site in .venv/lib/python*/site-packages; do
      if [ -d "$site" ]; then
        export PYTHONPATH="$site:${PYTHONPATH}"
      fi
    done
    export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
  else
    echo "check.sh: $PY is missing. Create the venv first: python3 -m venv .venv" >&2
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
