"""Chat fact ops prepare the same edit as the Facts panel on the Generic F10 import (plan 2.8 table)."""

import pytest

from packages.resume_core.assistant_compiler import CompileFailure, compile_ops, preview
from packages.resume_core.models.assistant import ProposeChangesV1
from packages.resume_core.template_panel_records import technology_targets
from resume_api.projects.service import response_for_workspace
from tests.templates.test_focus_panel import applied
from tests.templates.test_panel_records import before, imported, job_line, lines, record, request  # noqa: F401

pytestmark = pytest.mark.slow


def ops(*values):
    return ProposeChangesV1.model_validate({'summary': 'test', 'ops': list(values)}).ops


def chat(workspace, *values):
    return compile_ops(workspace, ops(*values), action_id='chat', occupied=set(), response_for=response_for_workspace)[0]


def refused(workspace, *values):
    with pytest.raises(CompileFailure) as failure:
        chat(workspace, *values)
    return failure.value


def blocks(workspace):
    return [''.join(getattr(part, 'text', '') for part in block.content) for block in workspace.project.document.blocks()
        if isinstance(block.content, list)]


def test_deleting_a_job_technology_takes_its_separator_as_the_panel_does(before):
    postgres = record(before, 'technology', 'PostgreSQL', job=True)
    after = chat(before, {'op': 'delete_fact', 'recordId': postgres.id})
    assert job_line(after) == 'Python Docker'
    assert blocks(after) == blocks(applied(before, request(before, 'remove', record_id=postgres.id))[0])


def test_deleting_every_technology_of_a_line_takes_the_line(before):
    names = [record(before, 'technology', name, job=True).id for name in ('Python', 'PostgreSQL', 'Docker')]
    after = chat(before, *({'op': 'delete_fact', 'recordId': value} for value in names))
    assert 'Python PostgreSQL Docker' in lines(before, 'projects')
    assert not any(not text.strip() for text in lines(after, 'projects'))
    panel = before
    for name in ('Python', 'PostgreSQL', 'Docker'):
        panel = applied(panel, request(panel, 'remove', record_id=record(panel, 'technology', name, job=True).id,
            identifier='remove-' + name))[0]
    assert blocks(after) == blocks(panel)


@pytest.mark.parametrize('kind', ['education', 'language'])
def test_deleting_education_or_language_takes_the_item_and_its_title(before, kind):
    target = record(before, kind)
    after = chat(before, {'op': 'delete_fact', 'recordId': target.id})
    assert blocks(after) == blocks(applied(before, request(before, 'remove', record_id=target.id))[0])


@pytest.mark.parametrize('kind, field, value', [('candidate', 'location', 'Yerevan'), ('education', 'qualification', 'Master'),
    ('education', 'specialty', 'Physics'), ('education', 'completion', '2019'), ('language', 'level', 'C1'),
    ('technology', 'experience', '5')])
def test_a_builtin_field_without_an_occurrence_saves_as_in_the_panel(before, kind, field, value):
    target = record(before, kind)
    after = chat(before, {'op': 'update_fact', 'recordId': target.id, 'field': field, 'value': value})
    panel = applied(before, request(before, 'edit', record_id=target.id, values={field: value}))[0]
    changed = next(item for item in after.project.facts.records if item.id == target.id)
    assert changed == next(item for item in panel.project.facts.records if item.id == target.id)
    assert blocks(after) == blocks(panel)


def test_a_job_technology_joins_the_jobs_line_and_the_preview_names_it(before):
    job = record(before, 'technology', 'PostgreSQL', job=True).job_id
    op = {'op': 'create_fact', 'kind': 'technology', 'values': {'display': 'Redis'}, 'jobId': job}
    after = chat(before, op)
    assert job_line(after) == 'Python PostgreSQL Docker Redis'
    assert any(entry['after'] == 'display: Redis' for entry in preview(before, after, ops(op)))


def test_a_general_technology_needs_its_group_and_the_refusal_lists_the_groups(before):
    groups = [value for value in technology_targets(before.project) if value.job_id is None]
    op = {'op': 'create_fact', 'kind': 'technology', 'values': {'display': 'Go'}}
    failure = refused(before, op)
    assert failure.code == 'ASSISTANT_OP_REFUSED' and failure.detail[0] == 'TECHNOLOGY_GROUP_REQUIRED'
    assert failure.detail[1:] == [f'{value.block_id}: {value.label}' for value in groups]
    assert refused(before, {**op, 'targetId': 'view:absent'}).detail[0] == 'TECHNOLOGY_GROUP_REQUIRED'
    after = chat(before, {**op, 'targetId': groups[0].block_id})
    assert lines(after, 'programming') == ['Python, Perl, Go']
    entry = preview(before, after, ops({**op, 'targetId': groups[0].block_id}))
    assert [(item['label'], item['after']) for item in entry] == [('create_fact', 'display: Go')]


def test_a_technology_takes_only_a_name(before):
    job = record(before, 'technology', 'PostgreSQL', job=True).job_id
    failure = refused(before, {'op': 'create_fact', 'kind': 'technology', 'jobId': job,
        'values': {'display': 'Redis', 'experience': '3'}})
    assert failure.code == 'ASSISTANT_FIELD_UNKNOWN'
