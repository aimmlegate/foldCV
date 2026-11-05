"""The core keeps its layer order and never imports the api. Static AST check over every module of packages/resume_core
and resume_api; the modules are never imported. Function-level imports count.

Layers of packages/resume_core, lowest first: models (with extraction and the root modules), templates, editing,
importing, rendering, repository, responses. A module imports its own layer or a lower one. The pairs that do not are
listed in layer_exceptions.txt (MT08, 2026-11-05): a new pair fails, and so does a listed pair that no longer goes up,
so the list only shrinks.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = {'packages.resume_core': ROOT / 'packages/resume_core', 'resume_api': ROOT / 'services/api/src/resume_api'}
LAYERS = ['models', 'templates', 'editing', 'importing', 'rendering', 'repository', 'responses']
EXCEPTIONS = Path(__file__).with_name('layer_exceptions.txt')


def modules():
    found = {}
    for prefix, folder in PACKAGES.items():
        for path in sorted(folder.rglob('*.py')):
            if '__pycache__' in path.parts:
                continue
            parts = [part for part in path.relative_to(folder).with_suffix('').parts if part != '__init__']
            found['.'.join([prefix, *parts])] = path
    return found


def imported(name, path, known):
    """Absolute module names one file imports, at any depth."""
    package = name if path.name == '__init__.py' else name.rpartition('.')[0]
    result = set()
    for node in ast.walk(ast.parse(path.read_text(), str(path))):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split('.')[:len(package.split('.')) - node.level + 1]
                origin = '.'.join([*base, node.module] if node.module else base)
            else:
                origin = node.module
            result.add(origin)
            # `from package import module` names a module, `from module import name` a symbol.
            result.update(origin + '.' + alias.name for alias in node.names if origin + '.' + alias.name in known)
    return result


def layer(name):
    """The layer of a core module: its package under packages/resume_core; root modules are models level."""
    parts = name.split('.')[2:]
    top = parts[0] if len(parts) > 1 else 'models'
    return {'extraction': 'models'}.get(top, top if top in LAYERS else 'models')


def upward_pairs():
    known = modules()
    core = {name: path for name, path in known.items() if name.startswith('packages.resume_core.')}
    return {(name, target) for name, path in core.items() for target in imported(name, path, known)
            if target in core and LAYERS.index(layer(target)) > LAYERS.index(layer(name))}


def listed():
    return {tuple(line.split(' -> ')) for line in EXCEPTIONS.read_text(encoding='utf-8').splitlines()
            if line.strip() and not line.startswith('#')}


def test_core_imports_its_own_layer_or_a_lower_one():
    found, allowed = upward_pairs(), listed()
    assert sorted(found - allowed) == [], 'a new import goes up a layer'
    assert sorted(allowed - found) == [], 'a listed pair no longer goes up: take it out of layer_exceptions.txt'


def test_core_does_not_import_the_api():
    known = modules()
    found = [(name, target) for name, path in known.items() if name.startswith('packages.')
        for target in sorted(imported(name, path, known)) if target == 'resume_api' or target.startswith('resume_api.')]
    assert found == []
