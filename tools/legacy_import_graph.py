"""Import edges from the modules that stay to the legacy and protocol modules that go (simplification plan 1.3, 1.4).

    .venv/bin/python tools/legacy_import_graph.py [--json report.json]

Prints the legacy set, which legacy modules the kept modules reach, and every kept -> legacy edge with the imported
names. Static AST analysis; function-level imports count and are marked lazy.
"""

import argparse
import ast
from collections import defaultdict
import fnmatch
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = {'packages.resume_core': ROOT / 'packages/resume_core', 'resume_api': ROOT / 'services/api/src/resume_api',
    'spikes': ROOT / 'spikes'}

# Module name patterns that go, from the deletion lists of plan sections 1.3 and 1.4.
LEGACY = [
    'packages.resume_core.background_*', 'packages.resume_core.template_commit_proofs',
    'packages.resume_core.template_preparation_store', 'packages.resume_core.template_writer_*',
    'packages.resume_core.template_delta', 'packages.resume_core.template_address_map',
    'packages.resume_core.template_retention', 'packages.resume_core.template_clipboard_store',
    'packages.resume_core.template_finalization', 'packages.resume_core.rich_project_store',
    'packages.resume_core.rich_snapshot_merge', 'packages.resume_core.rich_asset_lifecycle',
    'packages.resume_core.rich_archive', 'packages.resume_core.rich_import', 'packages.resume_core.agent_store',
    'packages.resume_core.agent_artifacts', 'packages.resume_core.agent_edits', 'packages.resume_core.assistant_*',
    'packages.resume_core.gui_*', 'packages.resume_core.normalization', 'packages.resume_core.drafting',
    'packages.resume_core.rewriting', 'packages.resume_core.checks',
    'packages.resume_core.models.background', 'packages.resume_core.models.template_writer',
    'packages.resume_core.models.template_delta', 'packages.resume_core.models.template_authority',
    'packages.resume_core.models.template_publication', 'packages.resume_core.models.template_address',
    'packages.resume_core.models.assistant_*', 'packages.resume_core.models.recovery',
    'resume_api.jobs', 'resume_api.jobs.*', 'resume_api.rich_synchronization', 'resume_api.rich_assets',
    'resume_api.rich_projects', 'resume_api.rich_routes', 'resume_api.template_exports',
    'resume_api.importer.template_checkpoints', 'resume_api.importer.template_persistence', 'resume_api.importer.job',
    'resume_api.importer.direct', 'resume_api.importer.template_direct', 'resume_api.importer.session',
    'resume_api.agent.approval*', 'resume_api.agent.action_*', 'resume_api.agent.continuation',
    'resume_api.agent.capabilities', 'resume_api.agent.history_proposals', 'resume_api.agent.outcomes',
    'resume_api.agent.project_*', 'resume_api.agent.proposals', 'resume_api.agent.publication',
    'resume_api.agent.leases', 'resume_api.agent.events', 'resume_api.agent.edits', 'resume_api.agent.service',
    'resume_api.agent.routes', 'resume_api.agent.tools', 'resume_api.agent.context',
    'resume_api.gui_*', 'resume_api.normalization_content', 'resume_api.drafting_content',
    'resume_api.rewriting_content', 'resume_api.contracts', 'spikes', 'spikes.*',
]
# Rewritten in place under a new design; they stay as modules but their current imports are protocol edges too.
REWRITTEN = {'packages.resume_core.agent_progress'}
# The SR05 assistant: kept although an `assistant_*` pattern above names its module.
CURRENT = ['packages.resume_core.assistant_store', 'packages.resume_core.assistant_compiler',
    'packages.resume_core.models.assistant', 'resume_api.assistant', 'resume_api.assistant.*']


def modules():
    result = {}
    for prefix, folder in PACKAGES.items():
        for path in sorted(folder.rglob('*.py')):
            if '__pycache__' in path.parts:
                continue
            relative = path.relative_to(folder).with_suffix('')
            parts = [part for part in relative.parts if part != '__init__']
            name = '.'.join([prefix, *parts]) if parts else prefix
            result[name] = path
    return result


def legacy(name):
    return (any(fnmatch.fnmatchcase(name, pattern) for pattern in LEGACY)
        and not any(fnmatch.fnmatchcase(name, pattern) for pattern in CURRENT))


def resolve(name, known):
    """The longest known module named by an import target (`a.b.c` may name module `a.b` and symbol `c`)."""
    while name and name not in known:
        name = name.rpartition('.')[0]
    return name or None


def imports(name, path, known):
    tree = ast.parse(path.read_text(), str(path))
    package = name if path.name == '__init__.py' else name.rpartition('.')[0]
    top = {id(node) for node in tree.body}
    found = defaultdict(lambda: {'names': set(), 'lazy': True})
    def add(target, symbol, node):
        module = resolve(target, known)
        if module is None or module == name:
            return
        entry = found[module]
        if symbol:
            entry['names'].add(symbol)
        entry['lazy'] = entry['lazy'] and id(node) not in top
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add(alias.name, None, node)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split('.')
                base = base[:len(base) - node.level + 1]
                origin = '.'.join([*base, node.module] if node.module else base)
            else:
                origin = node.module or ''
            for alias in node.names:
                # `from pkg import module` names a module; `from module import symbol` a symbol.
                if origin + '.' + alias.name in known:
                    add(origin + '.' + alias.name, None, node)
                else:
                    add(origin, alias.name, node)
    return found


def report():
    known = modules()
    graph = {name: imports(name, path, known) for name, path in known.items()}
    old = sorted(name for name in known if legacy(name))
    kept = sorted(name for name in known if not legacy(name))
    edges = []
    for source in kept:
        for target, entry in sorted(graph[source].items()):
            if legacy(target):
                edges.append({'from': source, 'to': target, 'names': sorted(entry['names']), 'lazy': entry['lazy']})
    reached, queue = set(), [edge['to'] for edge in edges]
    while queue:
        current = queue.pop()
        if current in reached:
            continue
        reached.add(current)
        queue.extend(target for target in graph[current] if legacy(target))
    lines = sum(len(known[name].read_text().splitlines()) for name in old)
    return {'legacyModules': len(old), 'legacyLines': lines, 'keptModules': len(kept), 'edges': edges,
        'reachedLegacy': sorted(reached), 'unreachedLegacy': sorted(set(old) - reached),
        'keptImportingLegacy': sorted({edge['from'] for edge in edges}), 'legacy': old}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--json')
    args = parser.parse_args()
    value = report()
    if args.json:
        Path(args.json).write_text(json.dumps(value, indent=1) + '\n')
    print(f"legacy modules {value['legacyModules']} ({value['legacyLines']} lines), kept modules {value['keptModules']}")
    print(f"kept -> legacy edges {len(value['edges'])} from {len(value['keptImportingLegacy'])} kept modules")
    print(f"legacy reached from kept modules {len(value['reachedLegacy'])}, unreached {len(value['unreachedLegacy'])}: "
        + ', '.join(value['unreachedLegacy']))
    for edge in value['edges']:
        lazy = ' (lazy)' if edge['lazy'] else ''
        print(f"{edge['from']} -> {edge['to']}{lazy}: {', '.join(edge['names']) or 'module'}")


if __name__ == '__main__':
    main()
