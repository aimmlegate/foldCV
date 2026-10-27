"""Every explicit Python error code needs a readable public catalog entry."""

import ast
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
CODE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+")


def test_every_explicit_python_code_has_a_public_message_or_non_error_reason():
    catalog = json.loads((ROOT / "contracts/error-messages.ru.json").read_text())
    codes = catalog["codes"]
    ignored = catalog["nonErrorSymbols"]
    missing = []
    for directory in (ROOT / "packages/resume_core", ROOT / "services/api/src/resume_api"):
        for path in directory.rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and CODE.fullmatch(node.value):
                    if node.value not in codes and node.value not in ignored:
                        missing.append(f"{path.relative_to(ROOT)}:{node.lineno} {node.value}")
                if isinstance(node, ast.Call):
                    name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
                    if re.search(r"Error$|Failure$|^problem$|^failure$|^fail$", name):
                        for argument in node.args[:1]:
                            if (isinstance(argument, ast.Constant) and isinstance(argument.value, str)
                                    and re.fullmatch(r"[A-Z]+", argument.value)
                                    and argument.value not in codes and argument.value not in ignored):
                                missing.append(f"{path.relative_to(ROOT)}:{node.lineno} {argument.value}")
    assert not missing, "Missing public descriptions:\n" + "\n".join(missing)


def test_catalog_references_are_complete_and_never_contain_raw_codes():
    catalog = json.loads((ROOT / "contracts/error-messages.ru.json").read_text())
    assert catalog["version"] == 1
    for code, key in catalog["codes"].items():
        message = catalog["messages"][key]
        assert re.search(r"[А-Яа-яЁё]", message), code
        assert not CODE.search(message), code
        assert message != code
    assert all(catalog["nonErrorSymbols"].values())
