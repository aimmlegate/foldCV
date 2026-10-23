"""Translated buffered input is accepted by Python and lands in the named owner."""

from packages.resume_core.models.template_authoring import TemplateEditPreparationV1
from packages.resume_core.models.template_document import FieldOccurrence, ManualScopeSpan
from packages.resume_core.template_address_map import build_address_map, content_leaves
from packages.resume_core.template_preparation import prepare_edit
from packages.resume_core.templates.presentation import snapshot_identity
from tests.templates.address_chain_fixtures import CHAINS, chains, encoded, plans
from tests.templates.address_map_fixtures import block_of
from tests.templates.test_template_preparation import proof, response


def test_checked_in_chain_fixture_is_reproducible():
    assert CHAINS.read_text(encoding='utf-8') == encoded(chains())


def owner_of(span):
    if isinstance(span, FieldOccurrence):
        return 'field', span.occurrence_id
    if isinstance(span, ManualScopeSpan):
        return 'scope', span.scope_id
    return 'literal', None


def test_every_expected_translation_prepares_and_lands_in_its_named_owner():
    checked = 0
    for (name, build, head, _operation, _options, _expect), case in zip(plans(), chains()['cases']):
        assert case['name'] == name
        if case['expected']['kind'] == 'conflict':
            continue
        value = build()
        prepared = prepare_edit(response(value), head(value), proof())
        after = prepared.preview.workspace
        operation = case['expected']['operation']
        request = TemplateEditPreparationV1(schemaVersion=1, clientMutationId='chain-' + name,
            snapshot=snapshot_identity(after), capture={'sessionId': 'session', 'actionId': 'chain-' + name,
                'actionToken': 1, 'dependencies': []}, operations=[{**operation, 'opId': 'op'}])
        result = prepare_edit(response(after), request, proof())
        assert result.mutation is not None, name
        build_address_map(response(after), request, result)
        target = operation.get('range', {}).get('insertionTarget')
        if target is None or target['kind'] == 'literal' and operation['text'] == '':
            checked += 1
            continue
        block = block_of(result.preview.workspace, operation['range']['blockId'])
        start = operation['range']['start']
        typed = [leaf for leaf in content_leaves(block.content) if leaf.start <= start and start + 1 <= leaf.end
            and leaf.span.text[start - leaf.start:start - leaf.start + 1] == operation['text'][:1]]
        assert typed, name
        before = block_of(after, operation['range']['blockId'])
        named = [leaf for leaf in content_leaves(before.content)
            if target['kind'] == 'field' and getattr(leaf.span, 'binding_id', None) == target['bindingId']
            or target['kind'] == 'manual_scope' and getattr(leaf.span, 'fragment_id', None) == target['fragmentId']]
        if target['kind'] == 'literal':
            assert owner_of(typed[0].span)[0] in {'literal', 'scope'}, name
        else:
            assert len(named) == 1, name
            expected_owner = owner_of(named[0].span)
            actual = owner_of(typed[0].span)
            # A repeat scope edit allocates a new immutable scope; ownership stays a shared-input scope.
            assert actual == expected_owner or expected_owner[0] == actual[0] == 'scope', name
        checked += 1
    assert checked >= 13
