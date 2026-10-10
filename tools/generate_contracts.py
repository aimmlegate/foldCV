"""Export deterministic JSON Schemas from the Python contract authority."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from packages.resume_core.models.contracts import Project, Proposal, TemplateManifest, ZipManifest

OUT = ROOT / "contracts" / "json-schema"


def main() -> None:
    if sys.argv[1:] == ["--clean-types"]:
        for path in sorted((ROOT / "apps" / "web" / "src" / "contracts" / "generated").glob("*.ts")):
            text = path.read_text(encoding="utf-8")
            marker = "export "
            start = text.find(marker)
            if start < 0:
                raise ValueError(f"missing declarations in {path}")
            path.write_text(text[start:], encoding="utf-8")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    for name, model in {
        "project": Project,
        "proposal": Proposal,
        "template": TemplateManifest,
        "zip_manifest": ZipManifest,
    }.items():
        schema = model.model_json_schema(mode="validation")
        (OUT / f"{name}.schema.json").write_text(
            json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
