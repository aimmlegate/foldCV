"""Where the re-parsed template definition differs from the stored one (Windows CI diagnostic)."""
import base64, json, sys
sys.path[:0] = [".", "services/api/src"]
from tests.templates.golden.corpus import corpus
from packages.resume_core.templates.compiler import canonical
from packages.resume_core.templates.loading import load_declared_definition, load_definition
from packages.resume_core.templates.models import TemplateDefinition


def walk(a, b, path=""):
    if type(a) is not type(b):
        yield path, repr(a)[:200], repr(b)[:200]
    elif isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                yield path + "/" + key, repr(a.get(key))[:200], repr(b.get(key))[:200]
            else:
                yield from walk(a[key], b[key], path + "/" + key)
    elif isinstance(a, list):
        if len(a) != len(b):
            yield path, f"len {len(a)}", f"len {len(b)}"
        for index, (x, y) in enumerate(zip(a, b)):
            yield from walk(x, y, f"{path}/{index}")
    elif a != b:
        yield path, repr(a)[:200], repr(b)[:200]


for name, fixture in corpus()["fixtures"].items():
    package = fixture["workspace"]["project"]["templatePackage"]
    original = base64.b64decode(package["originalBase64"])
    loaded = (load_declared_definition(original, package.get("originalFormat", "yaml"))
              if package["compilerVersion"] == 3 or package.get("originalFormat") else load_definition(original))
    parsed = json.loads(canonical(TemplateDefinition.model_validate(loaded)))
    stored = json.loads(canonical(TemplateDefinition.model_validate(package["definition"])))
    differences = list(walk(parsed, stored))
    print(name, "same" if not differences else f"{len(differences)} differences")
    for item in differences[:8]:
        print("   ", *item)
