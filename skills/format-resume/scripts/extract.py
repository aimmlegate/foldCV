"""Extract source text without assuming a resume export format."""

import argparse
import hashlib
import json
from pathlib import Path

import pymupdf


def extract(path):
    if path.suffix.lower() == ".pdf":
        with pymupdf.open(path) as doc:
            pages = [{"page": i + 1, "text": page.get_text(sort=True)}
                     for i, page in enumerate(doc)]
        warnings = [f"Page {p['page']}: little text; inspect for scans or missing content."
                    for p in pages if len(p["text"].strip()) < 50]
    elif path.suffix.lower() in {".txt", ".md"}:
        pages = [{"page": 1, "text": path.read_text(encoding="utf-8-sig")}]
        warnings = []
    else:
        raise ValueError("This prototype reads PDF, TXT, and Markdown. Convert other inputs first.")
    return {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "pages": pages, "warnings": warnings}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = extract(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Extracted {len(result['pages'])} pages; {len(result['warnings'])} warnings.")
