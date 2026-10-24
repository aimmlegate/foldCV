"""S4 compile rules: built-in record mappings, item roots, related items and dates shown as stated."""

import json

import pytest

from packages.resume_core.templates.compiler import compile_bytes, compile_definition, compiler_version
from packages.resume_core.templates.models import TemplateDefinition
from packages.resume_core.templates.projection import SchemaFailure, reachable_schema
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from tests.templates.generic_fixtures import generic_package


def config():
    return generic_package().definition.model_dump(mode='json', by_alias=True)


def compiled(value):
    return compile_bytes(json.dumps(value).encode(), BUNDLED_TEMPLATE.parent, original_format='json')


def block(value, identifier):
    return next(item for item in value['blocks'] if item['id'] == identifier)


def binding(value, identifier, pointer):
    return next(item for item in block(value, identifier)['bindings'] if item['pointer'] == pointer)


def test_the_bundled_template_maps_its_types_to_the_existing_record_kinds():
    package = generic_package()
    assert package.revision == '2.0.0' and 'date_text' in package.recipe.capabilities
    kinds = {fact.id: (fact.builtin_kind, {key: value.field for key, value in fact.builtin_fields.items()})
        for fact in package.definition.fact_types}
    assert kinds['foldcv:identity'] == ('candidate', {'name': 'name', 'profession': 'title'})
    assert kinds['foldcv:education'] == ('education', {'institution': 'institution', 'graduation_year': 'completion',
        'specialization': 'specialty', 'degree': 'qualification'})
    assert kinds['foldcv:courses'] == ('certification', {'school': 'issuer', 'title': 'name', 'year': 'date'})
    assert kinds['foldcv:languages'] == ('language', {'name': 'language', 'level': 'level'})
    assert kinds['foldcv:projects'][0] == 'employment' and kinds['foldcv:project_claim'] == ('claim', {'value': 'value'})
    assert {name for name, (kind, _fields) in kinds.items() if kind == 'technology'} == {'foldcv:focus', 'foldcv:project_technology',
        'foldcv:programming', 'foldcv:data_and_tools', 'foldcv:infrastructure', 'foldcv:role_tools'}
    # Fields the record kinds do not have stay template-owned, attached to their record.
    # Exact source text that falls back into a view reads as body text, never as a name or project title.
    assert {block.view.fallback_style or block.view.nodes[0].style for block in package.definition.blocks} == {'body', 'support'}
    assert {name: kind for name, (kind, _fields) in kinds.items() if kind is None} == {name: None for name in [
        'foldcv:role_family', 'foldcv:education_place', 'foldcv:location', 'foldcv:language_note', 'foldcv:opensource',
        'foldcv:portfolio', 'foldcv:summary', 'foldcv:project', 'foldcv:project_role', 'foldcv:other_projects',
        'foldcv:career_highlights', 'foldcv:key_skills']}


def test_two_semantic_types_at_one_item_root_are_refused_for_new_packages_only():
    value = config()
    timezone = binding(value, 'location', '/timezone')
    timezone.update(semantic_type='foldcv:summary', field='text')
    with pytest.raises(SchemaFailure, match='two semantic types share one item root'):
        compiled(value)
    # Stored packages re-verify through the shared derivation, which keeps accepting them.
    definition = TemplateDefinition.model_validate(value)
    compile_definition(definition, compiler_version(definition))


def test_a_related_item_without_an_explicit_root_is_refused_for_new_packages():
    value = config()
    del binding(value, 'projects', '/*/tasks/*/value')['item_pointer']
    with pytest.raises(SchemaFailure, match='explicit item_pointer'):
        compiled(value)


def test_text_and_join_nodes_show_a_date_object_but_no_other_object():
    value = config()
    block(value, 'education')['view']['nodes'][1]['fields'] = ['/graduation_year', '/place']
    with pytest.raises(SchemaFailure, match='incompatible view field type'):
        compiled(value)


def test_reachable_schemas_are_cached_by_content_and_returned_as_copies():
    definitions = {'text': {'type': ['string', 'null']}}
    payload = {'type': 'object', 'additionalProperties': False, 'required': ['name'],
        'properties': {'name': {'$ref': '#/$defs/text'}}}
    first = reachable_schema(payload, definitions)
    first['properties']['name'] = {'type': 'integer'}
    assert reachable_schema(payload, definitions)['properties']['name'] == {'$ref': '#/$defs/text'}
    definitions['text'] = {'type': 'string'}
    assert reachable_schema(payload, definitions)['$defs']['text'] == {'type': 'string'}
