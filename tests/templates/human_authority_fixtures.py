"""Human raw and pending text share the same retained authority checks."""

from packages.resume_core.models.template_facts import ManualEditScope, WorkingFactsV2
from tests.templates.storage_fixtures import papers


HUMAN_TEXT = 'Exact human wording, kept through model replacement.'


def human_papers(state):
    facts = papers()
    cell = facts.extensions[0].cells[0]
    cell.state, cell.origin, cell.user_corrected, cell.typed_value = state, 'human', True, None
    if state == 'pending_manual':
        cell.raw_input, cell.manual_scope_id = '', 'human-scope'
        facts.manual_scopes.append(ManualEditScope(id='human-scope', actionId='human-edit', rawInput=HUMAN_TEXT,
            cellIds=[cell.id], blockIds=[]))
    else:
        cell.raw_input = HUMAN_TEXT
    return WorkingFactsV2.model_validate(facts.model_dump(by_alias=True))
