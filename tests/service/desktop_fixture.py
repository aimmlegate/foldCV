"""Run `resume_api.desktop.serve` with a synthetic frontend (tests/service/test_desktop.py)."""

import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "services/api/src")]

from resume_api import desktop  # noqa: E402

root, frontend = map(Path, sys.argv[1:3])
desktop.frontend = lambda: frontend
asyncio.run(desktop.serve(root))
