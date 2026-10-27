"""No module imports the legacy generations, the job stack or spikes, and none of the deleted modules is back (plan 1.3,
1.4, S22).

Static AST check over every module of packages/resume_core and resume_api; the modules are never imported.
Function-level imports count.
"""

import ast
import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = {'packages.resume_core': ROOT / 'packages/resume_core', 'resume_api': ROOT / 'services/api/src/resume_api'}

# Module names SR06 deleted (plan 1.3, 1.4 and the dead V6 import modules); none may exist again.
DELETED = [
    'packages.resume_core.background_*', 'packages.resume_core.template_commit_proofs',
    'packages.resume_core.template_preparation_store', 'packages.resume_core.template_writer_*',
    'packages.resume_core.template_delta', 'packages.resume_core.template_address_map',
    'packages.resume_core.template_retention', 'packages.resume_core.template_clipboard_store',
    'packages.resume_core.template_finalization', 'packages.resume_core.rich_project_store',
    'packages.resume_core.rich_snapshot_merge', 'packages.resume_core.rich_asset_lifecycle', 'packages.resume_core.rich_archive',
    'packages.resume_core.rich_import', 'packages.resume_core.rich_timeline', 'packages.resume_core.rich_format',
    'packages.resume_core.agent_store', 'packages.resume_core.agent_artifacts', 'packages.resume_core.agent_edits',
    'packages.resume_core.assistant_actions', 'packages.resume_core.assistant_coverage',
    'packages.resume_core.assistant_proposals', 'packages.resume_core.assistant_publication',
    'packages.resume_core.gui_*', 'packages.resume_core.normalization', 'packages.resume_core.drafting',
    'packages.resume_core.rewriting', 'packages.resume_core.checks', 'packages.resume_core.import_*',
    'packages.resume_core.resume_assessment', 'packages.resume_core.extraction_outcome', 'packages.resume_core.source_dates',
    'packages.resume_core.models.background', 'packages.resume_core.models.template_writer',
    'packages.resume_core.models.template_delta', 'packages.resume_core.models.template_authority',
    'packages.resume_core.models.template_publication', 'packages.resume_core.models.template_address',
    'packages.resume_core.models.assistant_*', 'packages.resume_core.models.recovery',
    'resume_api.jobs', 'resume_api.jobs.*', 'resume_api.rich_*', 'resume_api.template_exports', 'resume_api.template_imports',
    'resume_api.importer.template_checkpoints', 'resume_api.importer.template_persistence', 'resume_api.importer.job',
    'resume_api.importer.direct', 'resume_api.importer.template_direct', 'resume_api.importer.template_export',
    'resume_api.importer.session', 'resume_api.importer.result', 'resume_api.projects.pipeline',
    'resume_api.agent.approval*', 'resume_api.agent.action_*', 'resume_api.agent.continuation',
    'resume_api.agent.capabilities', 'resume_api.agent.history_proposals', 'resume_api.agent.outcomes',
    'resume_api.agent.project_*', 'resume_api.agent.proposals', 'resume_api.agent.publication',
    'resume_api.agent.leases', 'resume_api.agent.events', 'resume_api.agent.edits', 'resume_api.agent.service',
    'resume_api.agent.routes', 'resume_api.agent.tools', 'resume_api.agent.context', 'resume_api.agent.skills',
    'resume_api.gui_*', 'resume_api.normalization_content', 'resume_api.drafting_content', 'resume_api.rewriting_content',
    'resume_api.resume_assessment_content', 'resume_api.original_sources', 'resume_api.contracts',
]


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


def forbidden(target):
    parts = target.split('.')
    return (any(part.startswith(('gui_', 'background_')) for part in parts)
        or target == 'packages.resume_core.models.recovery' or parts[-1] == 'rich_project_store'
        or target == 'resume_api.jobs' or target.startswith('resume_api.jobs.')
        or target == 'spikes' or target.startswith('spikes.'))


def deleted(name):
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in DELETED)


def test_no_module_imports_a_legacy_generation_job_stack_or_spike():
    known = modules()
    found = [(name, target) for name, path in known.items() for target in sorted(imported(name, path, known))
        if forbidden(target) or deleted(target)]
    assert found == []


def test_core_does_not_import_the_api():
    known = modules()
    found = [(name, target) for name, path in known.items() if name.startswith('packages.')
        for target in sorted(imported(name, path, known)) if target == 'resume_api' or target.startswith('resume_api.')]
    assert found == []


def test_no_module_is_named_like_a_deleted_one():
    assert [name for name in modules() if deleted(name)] == []
    assert not (ROOT / 'spikes').exists()
