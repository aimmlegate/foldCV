"""The local app log `<data root>/logs/foldcv.log`: what ran and how it ended, for diagnostics the user can send.

Entries name programs, commands, outcomes, codes and times; never resume text, prompts, model output or secrets.
Loggers under `foldcv` write at INFO, every other logger only from WARNING."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import platform
import re
import traceback

EVENTS = logging.getLogger("foldcv")
NAME = "foldcv.log"
BYTES = 524_288
KEPT = 2
# One-time values of sign-in addresses stay out of the logs.
ONE_TIME = re.compile(r"\b(state|code_challenge|code)=[^&\s]+")


def configure(root: Path) -> None:
    """Adds the file handler once; a log that cannot be opened leaves the service running without it."""
    handlers = logging.getLogger().handlers
    if any(getattr(handler, "foldcv_log", False) for handler in handlers):
        return
    folder = root / "logs"
    try:
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        handler = RotatingFileHandler(folder / NAME, maxBytes=BYTES, backupCount=KEPT, encoding="utf-8")
    except OSError:
        return
    handler.foldcv_log = True  # type: ignore[attr-defined]
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    EVENTS.setLevel(logging.INFO)
    EVENTS.info("service started: Python %s, %s, data root %s", platform.python_version(), platform.platform(), root)


def masked(text: str) -> str:
    return ONE_TIME.sub(r"\1=…", text)


def failure(error: BaseException) -> str:
    """A failure as the log names it, with the one it replaced: its code, else its type; a system error adds its
    numbers and text, which name files and causes but no content."""
    text = _named(error)
    context = error.__context__
    if context is not None and _named(context) != text:
        text += f" (from {_named(context)})"
    return text


def _named(error: BaseException) -> str:
    code = getattr(error, "code", None)
    if isinstance(code, str) and code:
        return code
    if isinstance(error, OSError):
        winerror = getattr(error, "winerror", None)
        return (f"{type(error).__name__} errno={error.errno}" + (f" winerror={winerror}" if winerror else "")
                + f": {error.strerror}")
    return type(error).__name__


def where(error: BaseException) -> str:
    """The frames of a traceback without the exception's message, which may quote data."""
    return "".join(traceback.format_tb(error.__traceback__)).rstrip()
