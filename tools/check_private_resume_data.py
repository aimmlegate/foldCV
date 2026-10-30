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
RESUME_SUFFIXES = {".pdf", ".doc", ".docx", ".odt", ".rtf", ".foldcv"}
ARCHIVE_SUFFIXES = {".tar", ".tgz", ".gz", ".bz2", ".xz", ".7z", ".rar"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
# Tests hold sample contacts on purpose; these files still get the indicator and workspace checks.
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".css", ".sh"}
LEGACY_ARCHIVES = {"docs/gui/handoffs/AGENT-ASSISTANT/evidence/ag08-native-2-source.patch.gz",
    "docs/gui/handoffs/BACKGROUND-WORK/nb00b-evidence/pinned-protocol-schema.tar.gz"}
# International numbers and the separated Russian trunk form; a bare digit run is too often an id or a timestamp.
# The leading character class lets `re` skip ahead: evidence files reach 68 MB and every commit scans them.
PHONE = re.compile(r"[+8](?<![\w.+-].)(?:(?<=\+)\d[\d ().-]{8,16}\d|(?<=8)[ (.-]{1,2}\d{3}[ ).-]{1,2}\d{3}[ .-]\d{2}[ .-]\d{2})(?![\d-])")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def is_synthetic(path):
    return path.startswith("tests/fixtures/synthetic/") or "/synthetic/" in path


def is_fixture(path):
    return path.startswith(("contracts/examples/", "tests/fixtures/")) or "/synthetic/" in path


def private_path(path):
    p = PurePosixPath(path)
    if path.startswith((".private/", "experiments/", "output/", "tmp/")):
        return True
    synthetic = is_synthetic(path)
    legacy_fixture = path in {"contracts/examples/recovery/legacy_selected_v2.foldcv",
        "contracts/examples/recovery/legacy_workspace_v4.foldcv"}
    if p.suffix.lower() in RESUME_SUFFIXES and not synthetic and not legacy_fixture:
        return True
    if p.suffix.lower() == ".zip" and not synthetic and not path.startswith("assets/branding/"):
        return True
    if ARCHIVE_SUFFIXES.intersection(suffix.lower() for suffix in p.suffixes) and not synthetic and path not in LEGACY_ARCHIVES:
        return True
    qa = path.startswith("docs/gui/handoffs/")
    asset_snapshot = "/before/assets/" in path or "/after/assets/" in path
    return qa and (p.suffix.lower() in IMAGE_SUFFIXES and not asset_snapshot or "/gui-fixture/" in path)


def resume_payload(value):
    if isinstance(value, dict):
        if value.get("sources") and isinstance(value["sources"], list) and (
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


def json_values(text):
    """The parsed document, or the parsed lines of a JSON Lines file or log."""
    try:
        return [json.loads(text)]
    except ValueError:
        pass
    values = []
    for line in text.splitlines():
        try:
            values.append(json.loads(line))
        except ValueError:
            pass
    return values


def load_indicators():
    if not INDICATORS.is_file():
        return {}
    return json.loads(INDICATORS.read_text())


def inspect(path, blob, indicators):
    reasons = []
    if private_path(path):
        reasons.append("private artifact path")
    if blob.startswith(b"%PDF") and not is_synthetic(path):
        reasons.append("source PDF")
    if blob.startswith(b"PK"):
        try:
            with ZipFile(BytesIO(blob)) as archive:
                for name in archive.namelist():
                    if name.endswith("/") or archive.getinfo(name).file_size > 64 * 1024 * 1024:
                        continue
                    value = archive.read(name)
                    if value.startswith(b"%PDF") and not is_synthetic(path):
                        reasons.append("embedded source PDF")
                    if PurePosixPath(name).suffix.lower() in RESUME_SUFFIXES and not is_fixture(path):
                        reasons.append("embedded source document")
                    if b"\0" not in value[:8192]:
                        reasons.extend(inspect_text(path, value, indicators))
        except BadZipFile:
            reasons.append("unreadable document archive")
    elif b"\0" not in blob[:8192]:
        reasons.extend(inspect_text(path, blob, indicators))
    return sorted(set(reasons))


def inspect_text(path, blob, indicators):
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        return []
    reasons = []
    if "\\u04" in text:
        text += "\n" + "\n".join(json.dumps(value, ensure_ascii=False) for value in json_values(text))
    folded = text.casefold()
    for name in indicators.get("names", []):
        if name.casefold() in folded and re.search(r"(?<![^\W\d_])" + re.escape(name) + r"(?![^\W\d_])", text, re.I):
            reasons.append("known candidate identity")
            break
    if any(value.casefold() in folded for value in indicators.get("emails", [])):
        reasons.append("known candidate contact")
    fixture = is_fixture(path)
    anchors = ["experience", "education", "skills", "опыт работы", "образование", "навыки"]
    if not fixture and PurePosixPath(path).suffix.lower() not in CODE_SUFFIXES and sum(word in folded for word in anchors) >= 2:
        contacts = []
        for marker in re.finditer("@", folded):
            start = max(0, marker.start()-64)
            left = re.search(r"[\w.+-]{1,64}$", folded[start:marker.start()])
            right = re.match(r"[\w.-]{1,253}\.[a-z]{2,20}", folded[marker.end():marker.end()+255])
            if left and right:
                local = left[0]
                if start + left.start() > 0 and folded[start+left.start()-1] == "\\" and local[0] in "nrt":
                    local = local[1:]
                # A diff line's "+" or "-" before a decorator leaves no address.
                if any(character.isalnum() for character in local):
                    contacts.append(local + "@" + right[0])
        def private_contact(email):
            domain = email.rsplit("@", 1)[1]
            return (domain not in {"example.com", "example.net", "example.org"}
                and not domain.endswith((".example.com", ".example.net", ".example.org", ".test", ".example", ".invalid")))
        def private_phone(number):
            digits = re.sub(r"\D", "", number)
            # Sample numbers in test ids, and the reserved +1 555 01xx range.
            return len(digits) >= 10 and "1234567" not in digits and not digits.startswith("155501")
        if any(private_contact(email) for email in contacts) or any(private_phone(item[0]) for item in PHONE.finditer(text)):
            reasons.append("resume text with contact details")
    if not fixture and ('"sources"' in text or '"workspaceWire"' in text):
        if any(resume_payload(value) for value in json_values(text)):
            reasons.append("resume workspace or source dump")
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
