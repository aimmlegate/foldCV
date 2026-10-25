"""One-shot assistant probe (D101, plan step A2): ask the live model for a rewrite batch outside the app.

One request through the same Codex CLI provider the assistant uses, with a JSON output schema in the A1 shape
(replace_text without start and end replaces a whole paragraph) and no tools, service or project. The two wordy
paragraphs of the CAP live fixture are the document. The reply is checked offline: every operation must compile against
the paragraph it names, and the result must not keep the old sentence tail. Each call is charged to the `probes` cap of
cap-live-ledger.json before dispatch, whatever its outcome.
"""

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import sys
import threading
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "services/api/src")]

from packages.resume_core.models.agent import AgentReplaceText  # noqa: E402

MODEL = "gpt-6-luna"
PROFILE = Path.home() / "Library/Application Support/FoldCV/cli-experiment"
LEDGER = ROOT / "docs/gui/handoffs/ASSISTANT-CAPABILITIES/cap-live-ledger.json"
SNAPSHOT = "read_full_document_1"
PARAGRAPHS = {
    "bullet": ("В течение всего периода работы в компании я занимался тем, что разрабатывал и поддерживал внутренние "
        "сервисы, которые потом использовались другими командами для решения их ежедневных рабочих задач."),
    "nested": ("Кроме того, я на регулярной основе принимал активное участие в процессе проведения ревью кода, в ходе "
        "которого внимательно проверял изменения коллег и давал им подробную обратную связь."),
}
REQUEST = ("Перепиши всё резюме: сделай формулировки короче и яснее. Сохрани язык, факты, даты, ссылки, контакты, "
    "порядок разделов и оформление. Подготовь один полный вариант для просмотра.")
TOOL_TEXT = {
    "a1": ("Text edits use replace_text with target:{snapshotId,blockId,cellId:null,field:\"content\"}, content:[{text:\"...\"}] "
        "to replace a whole paragraph; add start and end (exact UTF-16 offsets from find_resume_content) only for a substring."),
    "a1-explicit": ("Text edits use replace_text with target:{snapshotId,blockId,cellId:null,field:\"content\"}, content:[{text:\"...\"}]. "
        "Omit start and end to replace the whole paragraph; ranges are only for substrings, never for a rewritten sentence."),
}


class OneShotBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operations: list[AgentReplaceText] = Field(max_length=10)


def prompt(variant):
    blocks = "\n".join('- blockId "%s" (snapshotId "%s", %d UTF-16 units): %s' % (key, SNAPSHOT, len(text.encode("utf-16-le")) // 2, text)
        for key, text in PARAGRAPHS.items())
    return ("You are the FoldCV resume assistant. The user asks: " + REQUEST + "\n"
        "The document was read fully; these are its paragraphs:\n" + blocks + "\n"
        "Tool reference: " + TOOL_TEXT[variant] + "\n"
        "Return the replace_text operations that shorten and clarify these paragraphs in Russian, keeping every fact. "
        "Do not call tools; answer with the JSON batch only.")


def apply(operation):
    text = PARAGRAPHS.get(operation.target.block_id)
    if text is None:
        return None, "unknown block"
    units = len(text.encode("utf-16-le")) // 2
    new = "".join(part.text for part in operation.content)
    if operation.target.whole_field:
        return new, "whole"
    if operation.target.end > units:
        return None, "range beyond the field"
    utf16 = text.encode("utf-16-le")
    result = (utf16[: operation.target.start * 2] + new.encode("utf-16-le") + utf16[operation.target.end * 2:]).decode("utf-16-le")
    return result, "range %d-%d of %d" % (operation.target.start, operation.target.end, units)


def check(batch):
    """A pass: both paragraphs replaced whole (or by a range covering all of them) and no old opening words remain."""
    results, rewritten = {}, {}
    for operation in batch.operations:
        result, how = apply(operation)
        results[operation.target.block_id] = how
        if result is not None:
            rewritten[operation.target.block_id] = result
    tails = {key: (key in rewritten and (text[:12] in rewritten[key] or len(rewritten[key]) >= len(text)))
        for key, text in PARAGRAPHS.items()}
    passed = set(rewritten) == set(PARAGRAPHS) and not any(tails.values()) and all(how == "whole" or how.startswith("range 0-") for how in results.values())
    return {"operations": results, "oldTailKept": tails, "rewritten": rewritten, "passed": passed}


def charge(count, variant):
    with open("/private/tmp/foldcv-cap-oneshot-budget.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ledger = json.loads(LEDGER.read_text())
        probes = ledger["probes"]
        if probes["spent"] + count > probes["cap"]:
            raise SystemExit("one-shot cap reached: %d spent of %d, %d planned" % (probes["spent"], probes["cap"], count))
        numbers = list(range(probes["spent"] + 1, probes["spent"] + count + 1))
        probes["spent"] += count
        for number in numbers:
            probes["calls"].append({"number": number, "variant": variant, "model": MODEL, "status": "charged",
                "startedAt": datetime.now(timezone.utc).isoformat()})
        LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=1) + "\n")
        return numbers


def settle(number, record):
    with open("/private/tmp/foldcv-cap-oneshot-budget.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ledger = json.loads(LEDGER.read_text())
        call = next(call for call in ledger["probes"]["calls"] if call["number"] == number)
        call.update(record)
        LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=1) + "\n")


def run_once(variant, out, number):
    from resume_api.cli.experimental_profile import installed_profile
    from resume_api.lifecycle import OperationFiles
    from resume_api.providers.codex_cli import CodexCliProvider
    from resume_api.providers.content import ContentFailure, ContentInput, GenerationPolicy
    profile = installed_profile(PROFILE)
    provider = CodexCliProvider(profile.executable, experimental_profile=profile)
    temp = out / ("operations-%d" % number)
    temp.mkdir(mode=0o700)
    request = ContentInput(prompt(variant), OneShotBatch,
        GenerationPolicy(MODEL, timeout_seconds=180, allow_repair=False, reasoning_effort="medium"))
    began, record = time.monotonic(), {"status": "failed"}
    try:
        files = OperationFiles(temp)
        with files.open():
            result = provider.generate(request, files, threading.Event())
        batch = result.value
        raw = getattr(result, "raw_return", None) or batch.model_dump_json(by_alias=True)
        (out / ("reply-%d.json" % number)).write_text(raw)
        verdict = check(batch)
        record = {"status": "passed" if verdict["passed"] else "quality_failed", "seconds": round(time.monotonic() - began, 2),
            "inputTokens": getattr(result.usage, "input_tokens", None), "outputTokens": getattr(result.usage, "output_tokens", None),
            "operations": verdict["operations"], "oldTailKept": verdict["oldTailKept"]}
        (out / ("rewritten-%d.json" % number)).write_text(json.dumps(verdict["rewritten"], ensure_ascii=False, indent=1))
    except ContentFailure as error:
        record = {"status": "failed", "code": error.code, "seconds": round(time.monotonic() - began, 2)}
    settle(number, record)
    print(json.dumps({"number": number, **record}, ensure_ascii=False), flush=True)
    return record


def main(args):
    out = args.out.resolve()
    if out.parent != Path("/private/tmp") or not out.name.startswith("foldcv-cap-oneshot-") or out.exists():
        raise SystemExit("A new /private/tmp/foldcv-cap-oneshot-* folder is required")
    numbers = charge(args.calls, args.variant)
    out.mkdir(mode=0o700)
    (out / "prompt.txt").write_text(prompt(args.variant))
    for number in numbers:
        run_once(args.variant, out, number)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=sorted(TOOL_TEXT), default="a1")
    parser.add_argument("--calls", type=int, default=1)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args())
