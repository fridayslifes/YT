#!/usr/bin/env python3
"""Thin entry point for the master orchestrator: python tools/master.py <command>."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.orchestrator.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
