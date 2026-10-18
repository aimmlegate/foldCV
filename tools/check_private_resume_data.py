"""Reject private resume artifacts in staged files and outgoing Git history."""

from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from zipfile import BadZipFile, ZipFile


ROOT = Path(__file__).resolve().parents[1]
INDICATORS = ROOT / ".private/resume-qa/indicators.json"
RESUME_SUFFIXES = {".pdf", ".doc", ".docx", ".rtf", ".foldcv"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def private_path(path):
    p = PurePosixPath(path)
    if path.startswith((".private/", "experiments/", "output/", "tmp/")):
        return True
    synthetic = path.startswith("tests/fixtures/synthetic/") or "/synthetic/" in path
    legacy_fixture = path in {"contracts/examples/recovery/legacy_selected_v2.foldcv",
        "contracts/examples/recovery/legacy_workspace_v4.foldcv"}
    if p.suffix.lower() in RESUME_SUFFIXES and not synthetic and not legacy_fixture:
        return True
    if p.suffix.lower() == ".zip" and not synthetic and not path.startswith("assets/branding/"):
        return True
    qa = path.startswith("docs/gui/handoffs/")
    asset_snapshot = "/before/assets/" in path or "/after/assets/" in path
    return qa and (p.suffix.lower() in IMAGE_SUFFIXES and not asset_snapshot or "/gui-fixture/" in path)


def resume_payload(value):
    if isinstance(value, dict):
        if isinstance(value.get("sources"), list) and (
                isinstance(value.get("facts"), dict) or isinstance(value.get("document"), dict)):
            return True
        for key, item in value.items():
            if key == "workspaceWire" and isinstance(item, str):
                try:
                    if resume_payload(json.loads(item)):
                        return True
                except ValueError:
                    pass
            if isinstance(item, (dict, list)) and resume_payload(item):
                return True
    elif isinstance(value, list):
        return any(resume_payload(item) for item in value)
    return False


def load_indicators():
    if not INDICATORS.is_file():
        return {}
    return json.loads(INDICATORS.read_text())


def inspect(path, blob, indicators):
    reasons = []
    if private_path(path):
        reasons.append("private artifact path")
    if blob.startswith(b"PK"):
        try:
            with ZipFile(BytesIO(blob)) as archive:
                for name in archive.namelist():
                    if name.endswith("/") or archive.getinfo(name).file_size > 64 * 1024 * 1024:
                        continue
                    value = archive.read(name)
                    if value.startswith(b"%PDF") and not ("/synthetic/" in path or path.startswith("tests/fixtures/synthetic/")):
                        reasons.append("embedded source PDF")
                    if name.endswith((".xml", ".json", ".txt")):
                        reasons.extend(inspect_text(name, value, indicators, payload=False))
        except BadZipFile:
            reasons.append("unreadable document archive")
    elif b"\0" not in blob[:8192]:
        reasons.extend(inspect_text(path, blob, indicators))
    return sorted(set(reasons))


def inspect_text(path, blob, indicators, *, payload=True):
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        return []
    reasons = []
    if "\\u04" in text:
        try:
            text = json.dumps(json.loads(text), ensure_ascii=False)
        except ValueError:
            pass
    folded = text.casefold()
    for name in indicators.get("names", []):
        if name.casefold() in folded and re.search(r"(?<![^\W\d_])" + re.escape(name) + r"(?![^\W\d_])", text, re.I):
            reasons.append("known candidate identity")
            break
    if any(value.casefold() in folded for value in indicators.get("emails", [])):
        reasons.append("known candidate contact")
    fixture = path.startswith(("contracts/examples/", "tests/fixtures/")) or "/synthetic/" in path
    if payload and not fixture and path.endswith((".txt", ".md", ".json")):
        anchors = ["experience", "education", "skills", "опыт работы", "образование", "навыки"]
        contacts = []
        for marker in re.finditer("@", folded):
            start = max(0, marker.start()-64)
            left = re.search(r"[\w.+-]{1,64}$", folded[start:marker.start()])
            right = re.match(r"[\w.-]{1,253}\.[a-z]{2,20}", folded[marker.end():marker.end()+255])
            if left and right:
                local = left[0]
                if start + left.start() > 0 and folded[start+left.start()-1] == "\\" and local[0] in "nrt":
                    local = local[1:]
                if local:
                    contacts.append(local + "@" + right[0])
        def private_contact(email):
            domain = email.rsplit("@", 1)[1]
            return (email != "mail@example.com" and domain not in {"example.com", "example.net", "example.org"}
                and not domain.endswith((".example.com", ".example.net", ".example.org", ".test", ".example", ".invalid")))
        if sum(word in folded for word in anchors) >= 2 and any(private_contact(email) for email in contacts):
            reasons.append("resume text with contact details")
    if payload and not fixture and path.endswith(".json") and ('"sources"' in text or '"workspaceWire"' in text):
        try:
            if resume_payload(json.loads(text)):
                reasons.append("resume workspace or source dump")
        except ValueError:
            pass
    return reasons


def check_objects(objects):
    indicators = load_indicators()
    failures = []
    process = subprocess.Popen(["git", "cat-file", "--batch"], cwd=ROOT,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for oid, path in objects:
            process.stdin.write(oid.encode() + b"\n")
            process.stdin.flush()
            header = process.stdout.readline().split()
            if len(header) != 3:
                continue
            size = int(header[2])
            blob = process.stdout.read(size)
            process.stdout.read(1)
            if header[1] != b"blob":
                continue
            reasons = inspect(path, blob, indicators)
            if reasons:
                failures.append((path, reasons))
    finally:
        process.stdin.close()
        process.stdout.close()
        process.wait()
    for path, reasons in failures:
        print(f"BLOCKED {path}: {', '.join(reasons)}", file=sys.stderr)
    return 1 if failures else 0


def main():
    if "--pre-push" in sys.argv:
        tips = [line.split()[1] for line in sys.stdin if len(line.split()) == 4 and set(line.split()[1]) != {"0"}]
        if not tips:
            return 0
        rows = git("rev-list", "--objects", *tips).decode().splitlines()
        objects = [tuple(row.split(" ", 1)) for row in rows if " " in row]
    elif "--history" in sys.argv:
        rows = git("rev-list", "--objects", "HEAD").decode().splitlines()
        objects = [tuple(row.split(" ", 1)) for row in rows if " " in row]
    else:
        rows = git("ls-files", "--stage", "-z").split(b"\0")
        objects = [(row.split(b"\t", 1)[0].split()[1].decode(), row.split(b"\t", 1)[1].decode()) for row in rows if row]
    return check_objects(objects)


if __name__ == "__main__":
    raise SystemExit(main())
