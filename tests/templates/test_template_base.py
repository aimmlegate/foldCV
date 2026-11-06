"""Three table templates take their shared sections from templates/bundled/_base.yaml; the resolved text is the full
file they had before (MT10), so their package, config and original hashes stay."""

from pathlib import Path

import pytest

from packages.resume_core.templates import store
from packages.resume_core.templates.compiler import compile_bytes, compile_template
from packages.resume_core.templates.loading import load_definition
from packages.resume_core.models.template_package import TemplateDefinition
from packages.resume_core.hashing import canonical
from packages.resume_core.templates.projection import SchemaFailure

ROOT = Path(__file__).resolve().parents[2]
PRE_BASE = ROOT / 'tests/fixtures/synthetic/templates/pre-base'
TABLES = ['generic-skills-table', 'generic-questionnaire', 'generic-project-cards']


@pytest.mark.parametrize('template', list(store.shipped_templates()))
def test_every_shipped_text_is_the_full_file_it_was(template):
    resolved = store.bundled_source(template)
    full = (PRE_BASE / f'{template}.yaml').read_bytes()
    assert resolved == full
    definition = TemplateDefinition.model_validate(load_definition(resolved))
    assert canonical(definition) == canonical(TemplateDefinition.model_validate(load_definition(full)))
    folder = store.BUNDLED_TEMPLATES[template].parent
    assert store.bundled_package(template).original_hash == compile_bytes(full, folder).original_hash


@pytest.mark.parametrize('template', TABLES)
def test_a_table_file_names_the_base_and_compiles_only_through_it(template):
    path = store.BUNDLED_TEMPLATES[template]
    assert b'\nbase: _base\n' in path.read_bytes() and b'\nmodel:' not in path.read_bytes()
    with pytest.raises(SchemaFailure):
        compile_template(path)


def test_a_missing_base_is_an_explicit_error(tmp_path, monkeypatch):
    folder = tmp_path / 'bundled'
    folder.mkdir()
    source = store.BUNDLED_TEMPLATES['generic-skills-table']
    (folder / source.name).write_bytes(source.read_bytes())
    monkeypatch.setitem(store.BUNDLED_TEMPLATES, 'generic-skills-table', folder / source.name)
    with pytest.raises(SchemaFailure) as refused:
        store.bundled_source('generic-skills-table')
    assert refused.value.path == '/base'
