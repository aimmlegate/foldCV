"""The one executable of the frozen macOS helper: the service and the workers it starts as modes of itself."""

from pathlib import Path
import sys

# The service compiles nothing into the signed bundle.
sys.dont_write_bytecode = True
if not getattr(sys, "frozen", False):
    source = Path(__file__).resolve().parents[2]
    sys.path[:0] = [str(source), str(source / "services/api/src")]


def main(arguments: list[str]) -> int:
    mode, *rest = arguments or [""]
    if mode == "serve":
        from resume_api.desktop import main as serve
        return serve(rest)
    if rest:
        return 64
    if mode == "extract":
        from packages.resume_core.extraction.worker import main as extract
        return extract()
    if mode == "render":
        from packages.resume_core.rendering.worker import main as render
        return render()
    if mode == "public-fetch":
        from resume_api.agent.web import worker_main
        return worker_main()
    if mode == "check":
        from resume_api.desktop import check
        return check()
    return 64


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
