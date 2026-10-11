"""Project-local entry point for the FoldCV service."""

from pathlib import Path
import argparse
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/api/src"))

from tools.local_readiness import ReadinessError, preflight

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--help", action="help", help="show local launcher options and exit")
parser.add_argument("--codex-executable", type=Path)
parser.add_argument("--check", action="store_true")
parser.add_argument("--experimental-cli", action="store_true")
parser.add_argument("--no-open", action="store_true")
parser.add_argument("--port", type=int, default=0)
preflight_options, remaining = parser.parse_known_args()
if remaining:
    parser.error("unknown option")
if preflight_options.check and (preflight_options.no_open or preflight_options.port):
    parser.error("--check cannot start the service")
if preflight_options.experimental_cli and (preflight_options.codex_executable is not None
                                           or os.environ.get("FOLDCV_CODEX_EXECUTABLE")):
    parser.error("--experimental-cli uses the pinned native CLI; remove the executable override")
try:
    selected = os.environ.get("FOLDCV_CODEX_EXECUTABLE")
    print(preflight(preflight_options.codex_executable or (Path(selected) if selected else None),
                    experimental_cli=preflight_options.experimental_cli), file=sys.stderr)
except ReadinessError as error:
    raise SystemExit(str(error)) from None

if preflight_options.check:
    raise SystemExit(0)

from resume_api.launcher import main

main()
