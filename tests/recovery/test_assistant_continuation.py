"""Explicit continuation carries proved reads and useful text without publishing."""

import json
import time

import pytest

from packages.resume_core.agent_store import AgentFailure, run_in
from packages.resume_core.models.agent import AgentOwner, AgentRunRequest
from packages.resume_core.models.assistant_continuation import AssistantContinueRunV1, AssistantDraftReadV1
from packages.resume_core.models.assistant_proposals import AssistantAssemblyRequestV1
from tests.recovery.test_assistant_proposals import environment, read_document, append, complete
from resume_api.agent.continuation import identity_request, submit_run
from resume_api.agent.service import RunControl
from resume_api.agent.tools import ToolSession
from tests.recovery.test_agent_tools import Fetcher


async def incomplete(tmp_path):
    service, runtime, projects, workspace, session = environment(tmp_path)
    snapshot = await read_document(session)
    # The turn ends before finalize, as in a live run; the end of the run seals the useful draft.
    result, _ = await append(session, 'part', snapshot=snapshot)
    assert result['disposition'] == 'building'
    service.proposals.finish(workspace.project_id, session.run.id)
    value = service.proposals.get(workspace.project_id, result['proposalId'], 1)
    assert value.proposal.state == 'incomplete'
    await session.close()
    service.store.finish(workspace.project_id, session.run.id, 'interrupted', error='AGENT_INTERRUPTED', text='Черновик сохранён, документ не изменён.')
    old = run_in(service.store.load(workspace.project_id), session.run.id)[2].request
    lease = service.leases.leases[workspace.project_id]
    request = AgentRunRequest.model_validate({**old.model_dump(by_alias=True), 'clientRequestId': 'continue_1',
        'owner': {'epoch': lease.epoch, 'token': lease.token}})
    return service, runtime, projects, workspace, value, AssistantContinueRunV1(protocolVersion=1,
        proposal=identity_request(value), request=request)


@pytest.mark.asyncio
async def test_continue_is_idempotent_new_version_with_complete_proof_and_no_canonical_change(tmp_path):
    service, runtime, projects, workspace, old, payload = await incomplete(tmp_path)
    before = projects.storage.read_committed(workspace.project_id)[0].model_dump_json()
    run, created = submit_run(service, workspace.project_id, payload)
    again, duplicate = submit_run(service, workspace.project_id, payload)
    assert created and not duplicate and again.id == run.id and run.id != old.proposal.origin_run_id
    version = service.proposals.get(workspace.project_id, old.proposal.id, 2)
    assert version.proposal.state == 'building' and version.proposal.operation_count == 1
    assert version.approval is None and version.revoked_acceptances == [] and version.calls == {}
    assert version.read_groups and all(group.current_alias for group in version.read_groups)
    control = RunControl(workspace.project_id, run.id, run.owner_epoch, run.connection_epoch, time.monotonic())
    session = ToolSession(service, control, run, Fetcher())
    try:
        journal = run_in(service.store.load(workspace.project_id), run.id)[2]
        prompt = session.book.initial(run, journal)
        assert 'continuedDraft' in prompt and session.planned_task == old.proposal.task_id
        assert all(unit.read for unit in version.proposal.coverage)
        await read_document(session)
        # Fresh reads must not invalidate carried operation references.
        first = await session.call('prepare_edit_batch', AssistantAssemblyRequestV1(protocolVersion=1,
            proposalId=old.proposal.id, version=2, taskId=old.proposal.task_id, key='next', phase='append'))
        assert 'error' not in first, first
        assert first['version'] == 2
        current = first
        index = 0
        while current['unresolvedUnits']:
            current = await session.call('prepare_edit_batch', AssistantAssemblyRequestV1(protocolVersion=1,
                proposalId=old.proposal.id, version=2, taskId=old.proposal.task_id, key='coverage_'+str(index), phase='append',
                unchanged=[{'unitId': item['unitId'], 'reason': 'Keep this authored part.'}
                    for item in current['coverage'] if item['state'] == 'unresolved']))
            assert 'error' not in current, current
            index += 1
        done = await session.call('prepare_edit_batch', AssistantAssemblyRequestV1(protocolVersion=1,
            proposalId=old.proposal.id, version=2, taskId=old.proposal.task_id, key='final', phase='finalize'))
        assert done['disposition'] == 'draft_ready' and done['version'] == 2
        final = service.proposals.get(workspace.project_id, old.proposal.id, 2)
        assert final.proposal.content_sha256 == old.proposal.content_sha256
        assert service.proposals.get(workspace.project_id, old.proposal.id, 1) == old
        assert projects.storage.read_committed(workspace.project_id)[0].model_dump_json() == before
        assert not runtime.calls
    finally:
        await session.close()
    service.store.finish(workspace.project_id, run.id, 'interrupted', error='AGENT_INTERRUPTED')
    from packages.resume_core.models.assistant_approval import AssistantAcceptanceV1
    from packages.resume_core.assistant_proposals import content_digest
    from tests.recovery.test_assistant_approval import commit_request
    from tests.recovery.test_agent_publication import manual, block
    before_workspace = projects.storage.read_committed(workspace.project_id)[0]
    accepted = AssistantAcceptanceV1(protocolVersion=1, proposalId=old.proposal.id, version=2,
        contentSha256=final.proposal.content_sha256, acceptanceId='continued_click', owner=payload.request.owner)
    claimed = service.approval.claim(workspace.project_id, accepted)
    saved = service.approval.commit(workspace.project_id, commit_request(accepted, claimed))
    assert saved.receipt.durable and content_digest(saved.project.workspace) == final.proposal.content_sha256
    for direction, target in (('undo', before_workspace), ('redo', saved.project.workspace)):
        command = manual(projects.read(workspace.project_id), action=claimed.claim.batch.mutation.action_id, kind=direction)
        command.steps[0].block = block(target).model_copy(update={'children': []})
        command.capture.session_id = claimed.claim.batch.mutation.capture.session_id
        result = projects.mutate(workspace.project_id, command)
        assert result.durability == 'durable' and content_digest(result.workspace) == content_digest(target)
    assert len(projects.read(workspace.project_id).mutation_replay) == 3 and not runtime.calls


@pytest.mark.asyncio
async def test_continued_draft_pages_are_exact_bounded_and_grant_no_read_credit(tmp_path):
    service, runtime, _, workspace, old, payload = await incomplete(tmp_path)
    run, _ = submit_run(service, workspace.project_id, payload)
    session = ToolSession(service, RunControl(workspace.project_id, run.id, run.owner_epoch,
        run.connection_epoch, time.monotonic()), run, Fetcher())
    try:
        session.book.initial(run, run_in(service.store.load(workspace.project_id), run.id)[2])
        snapshots = set(session.book.by_snapshot)
        request = AssistantDraftReadV1(protocolVersion=1, proposalId=old.proposal.id, version=2)
        parts = []
        while True:
            page = await session.call('get_project_resources', request)
            assert 'error' not in page, page
            assert len(json.dumps(page, ensure_ascii=False, separators=(',', ':')).encode()) <= 16384
            assert page['readCredit'] is False
            parts.append(page['content'])
            if page['nextCursor'] is None:
                break
            request = request.model_copy(update={'cursor': page['nextCursor']})
        data = json.loads(''.join(parts))
        assert data['operations'] and data['coverage'] and data['changes']
        assert set(session.book.by_snapshot) == snapshots
        assert not runtime.calls
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_continue_rejects_changed_scope_or_account_without_a_new_run(tmp_path):
    from resume_api.agent.service import AgentConnection
    service, runtime, _, workspace, old, payload = await incomplete(tmp_path)
    before = len(service.store.load(workspace.project_id).journals)
    changed = payload.model_copy(deep=True); changed.request.message = 'A different task'
    with pytest.raises(AgentFailure, match='AGENT_SCOPE_INVALID'):
        submit_run(service, workspace.project_id, changed)
    service.connection = lambda: AgentConnection(True, ('assistant-model',), 'another_account')
    with pytest.raises(AgentFailure, match='AGENT_CONNECTION_CHANGED'):
        submit_run(service, workspace.project_id, payload)
    assert len(service.store.load(workspace.project_id).journals) == before
    assert service.proposals.get(workspace.project_id, old.proposal.id, 1) == old
    assert not runtime.calls


@pytest.mark.asyncio
async def test_noop_result_survives_payload_reclamation_and_does_not_fill_version_slots(tmp_path):
    from resume_api.agent.outcomes import outcome
    service, runtime, projects, workspace, session = environment(tmp_path)
    before = projects.storage.read_committed(workspace.project_id)[1]
    for index in range(22):
        lease = service.leases.leases[workspace.project_id]
        service.leases.renew(workspace.project_id, AgentOwner(epoch=lease.epoch, token=lease.token))
        if index:
            old = run_in(service.store.load(workspace.project_id), session.run.id)[2].request
            lease = service.leases.leases[workspace.project_id]
            request = AgentRunRequest.model_validate({**old.model_dump(by_alias=True), 'clientRequestId': f'noop_{index}',
                'owner': {'epoch': lease.epoch, 'token': lease.token}})
            run, _ = service.submit(workspace.project_id, request)
            session = ToolSession(service, RunControl(workspace.project_id, run.id, run.owner_epoch,
                run.connection_epoch, time.monotonic()), run, Fetcher())
        snapshot = await read_document(session)
        first, _ = await append(session, 'same', snapshot=snapshot, text='Styled')
        done = await complete(session, first)
        assert done['disposition'] == 'no_change'
        assert service.proposals.list(workspace.project_id)
        await session.close()
        service.store.finish(workspace.project_id, session.run.id, 'interrupted', error='AGENT_INTERRUPTED')
        result = outcome(service, workspace.project_id, session.run.id)
        assert result.outcome == 'no_change' and not result.durable
        assert not service.proposals.list(workspace.project_id)
        assert not run_in(service.store.load(workspace.project_id), session.run.id)[1].saved_batch_id
    assert projects.storage.read_committed(workspace.project_id)[1] == before
    assert not runtime.calls


@pytest.mark.asyncio
async def test_exact_encoded_control_capacity_allows_max_nonce_metadata_and_one_saved_compaction(tmp_path, monkeypatch):
    from tests.recovery.test_assistant_approval import ready, commit_request
    from packages.resume_core import assistant_proposals as capacity
    approval, service, runtime, projects, workspace, payload = await ready(tmp_path)
    value = service.proposals.get(workspace.project_id, payload.proposal_id, 1)
    path = service.proposals.directory(workspace.project_id) / service.proposals.filename(value)
    size = path.stat().st_size
    assert size == value.control_capacity and len(value.control_padding) > 16000
    monkeypatch.setattr(capacity, 'VERSION_BYTES', size)
    monkeypatch.setattr(capacity, 'PROJECT_BYTES', size)
    monkeypatch.setattr(capacity, 'APPLICATION_BYTES', size)
    def metadata(values):
        current = values[0]
        current.revoked_acceptances = [f'r{index}_' + 'x' * (128-len(f'r{index}_')) for index in range(99)]
        current.proposal.reason = '\x00' * 2000
        return current
    service.proposals.update(workspace.project_id, metadata)
    assert path.stat().st_size == size
    claim = approval.claim(workspace.project_id, payload)
    assert path.stat().st_size == size
    result = approval.commit(workspace.project_id, commit_request(payload, claim))
    assert result.receipt.durable
    applied = service.proposals.get(workspace.project_id, payload.proposal_id, 1)
    assert applied.compacted and applied.control_capacity == 0 and not applied.control_padding
    assert not applied.read_groups and applied.baseline is None and path.stat().st_size < size
    assert not runtime.calls


@pytest.mark.asyncio
async def test_large_authored_field_has_exact_comparison_chunks_and_a_small_edit_request(tmp_path):
    from tests.recovery.test_agent_edits import replace
    from packages.resume_core.rich_mutations import inline_text
    service, runtime, projects, workspace, session = environment(tmp_path)
    current = projects.read(workspace.project_id).model_copy(deep=True)
    block = next(block for block in current.project.document.blocks() if block.id == 'narrative')
    block.content[0].text = 'x' * 270000
    before = "".join(inline_text(span) for span in block.content)
    projects.workspaces[workspace.project_id] = current
    assert projects.persist(workspace.project_id) == 'durable'
    try:
        snapshot = await read_document(session)
        request = AssistantAssemblyRequestV1(protocolVersion=1, taskId='rewrite_resume', key='one_character',
            phase='append', snapshotIds=[snapshot.id], operations=[replace(snapshot, 'narrative', 0, 1, 'y')])
        assert len(request.model_dump_json(by_alias=True).encode()) < 2048
        first = await session.call('prepare_edit_batch', request)
        assert 'error' not in first, first
        done = await complete(session, first)
        assert done['disposition'] == 'draft_ready'
        value = service.proposals.get(workspace.project_id, done['proposalId'], 1)
        changes = [item for item in value.proposal.changes if item.effect == 'wording']
        assert len(changes) == 2
        assert ''.join(item.before for item in changes) == before
        assert ''.join(item.after for item in changes) == 'y' + before[1:]
        assert len({item.unit_id for item in changes}) == 2
        assert ''.join(inline_text(span) for span in next(block for block in projects.read(workspace.project_id).project.document.blocks()
            if block.id == 'narrative').content) == before
        assert not runtime.calls
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_queued_continue_uses_one_new_job_same_artifact_journal_and_never_publishes(tmp_path):
    import asyncio
    from tests.recovery.test_background_agent import environment as queued_environment
    from packages.resume_core.background_supervisor import ExecutionOutcome
    from packages.resume_core.models.assistant_continuation import AssistantContinueJobV1
    from resume_api.agent.continuation import submit_job
    jobs, factory, workspace, payload, _, service = await queued_environment(tmp_path)
    service.assistant_protocol_enabled = True
    payload.request.allow_edits = False
    before = jobs.projects.storage.read_committed(workspace.project_id)[1]
    prepared = []
    async def first(control, _actor):
        session = jobs.tools.session(control)
        try:
            snapshot = await read_document(session)
            result, _ = await append(session, 'part', snapshot=snapshot)
            assert result['disposition'] == 'building'
            prepared.append(result)
            return ExecutionOutcome(finished_at=jobs.supervisor.clock.now())
        finally:
            await session.close()
    async def second(control, _actor):
        session = jobs.tools.session(control)
        try:
            assert 'continuedDraft' in session.prompt
            data = await session.call('prepare_edit_batch', AssistantAssemblyRequestV1(protocolVersion=1,
                proposalId=prepared[0]['proposalId'], version=2, taskId='rewrite_resume', phase='append', key='carry'))
            index = 0
            while data['unresolvedUnits']:
                data = await session.call('prepare_edit_batch', AssistantAssemblyRequestV1(protocolVersion=1,
                    proposalId=prepared[0]['proposalId'], version=2, taskId='rewrite_resume', phase='append', key=f'coverage_{index}',
                    unchanged=[{'unitId': item['unitId'], 'reason': 'Keep authored content.'}
                        for item in data['coverage'] if item['state'] == 'unresolved']))
                assert 'error' not in data, data
                index += 1
            data = await session.call('prepare_edit_batch', AssistantAssemblyRequestV1(protocolVersion=1,
                proposalId=prepared[0]['proposalId'], version=2, taskId='rewrite_resume', phase='finalize', key='final'))
            assert data['disposition'] == 'draft_ready'
            return ExecutionOutcome(finished_at=jobs.supervisor.clock.now())
        finally:
            await session.close()
    factory.callbacks[payload.request.client_request_id] = first
    try:
        old, _ = await jobs.submit(workspace.project_id, payload)
        await factory.actor(old)
        await asyncio.wait_for(jobs.supervisor.controls[old.id].task, 10)
        # The scripted factory bypasses the queued runtime, which seals a building draft at the end of the job.
        service.proposals.finish(workspace.project_id, old.id)
        value = service.proposals.get(workspace.project_id, prepared[0]['proposalId'], 1)
        assert value.proposal.state == 'incomplete'
        next_payload = payload.model_copy(deep=True); next_payload.request.client_request_id = 'continue_queue'
        factory.callbacks['continue_queue'] = second
        request = AssistantContinueJobV1(protocolVersion=1, proposal=identity_request(value), request=next_payload)
        new, created = await submit_job(service, jobs, workspace.project_id, request)
        again, duplicate = await submit_job(service, jobs, workspace.project_id, request)
        assert created and not duplicate and new.id == again.id and new.id != old.id
        await factory.actor(new)
        await asyncio.wait_for(jobs.supervisor.controls[new.id].task, 10)
        final = service.proposals.get(workspace.project_id, value.proposal.id, 2)
        assert final.proposal.state == 'ready' and final.proposal.operation_count == 1
        assert jobs.store.read(workspace.project_id, new.id).receipt is None
        assert jobs.projects.storage.read_committed(workspace.project_id)[1] == before
    finally:
        await jobs.shutdown()


@pytest.mark.asyncio
async def test_utf8_message_and_call_limits_keep_useful_draft_and_an_exact_remedy(tmp_path):
    from packages.resume_core.models.assistant_capabilities import AssistantTaskRequestV1
    from tests.recovery.test_agent_edits import replace
    service, runtime, projects, workspace, session = environment(tmp_path)
    before = projects.storage.read_committed(workspace.project_id)[1]
    try:
        snapshot = await read_document(session)
        first, _ = await append(session, 'useful', snapshot=snapshot)
        original = service.proposals.get(workspace.project_id, first['proposalId'], 1)
        operation = replace(snapshot, 'narrative', 0, 6, '😀' * 10000)
        operation['content'].append({'text': '😀' * 10000})
        oversized = AssistantAssemblyRequestV1(protocolVersion=1, proposalId=original.proposal.id, taskId='rewrite_resume',
            key='oversize', phase='append', snapshotIds=[snapshot.id], operations=[operation])
        assert len(oversized.model_dump_json(by_alias=True).encode()) > 65536
        failed = await session.call('prepare_edit_batch', oversized)
        assert failed['error']['code'] == 'AGENT_TOOL_LIMIT' and 'reason' in failed
        assert service.proposals.get(workspace.project_id, original.proposal.id, 1).candidate == original.candidate
        task = AssistantTaskRequestV1(protocolVersion=1, taskId='rewrite_resume', stage='review')
        while session.calls < 64:
            assert 'error' not in await session.call('get_project_resources', task)
        denied = await session.call('get_project_resources', task)
        assert denied['error']['code'] == 'AGENT_TOOL_LIMIT' and session.calls == 64
        service.proposals.finish(workspace.project_id, session.run.id)
        final = service.proposals.get(workspace.project_id, original.proposal.id, 1)
        assert final.proposal.state == 'incomplete' and final.proposal.reason.startswith('Лимит:')
        assert final.candidate == original.candidate and final.proposal.operation_count == 1
        assert projects.storage.read_committed(workspace.project_id)[1] == before and not runtime.calls
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_aggregate_101st_operation_never_replaces_or_publishes_the_saved_100_operation_draft(tmp_path):
    from tests.recovery.test_agent_edits import replace
    service, runtime, projects, workspace, session = environment(tmp_path)
    current = projects.read(workspace.project_id).model_copy(deep=True)
    block = next(block for block in current.project.document.blocks() if block.id == 'narrative')
    block.content[0].text = 'word ' * 101
    projects.workspaces[workspace.project_id] = current
    assert projects.persist(workspace.project_id) == 'durable'
    before = projects.storage.read_committed(workspace.project_id)[1]
    try:
        snapshot = await read_document(session)
        result = await session.call('prepare_edit_batch', AssistantAssemblyRequestV1(protocolVersion=1, taskId='rewrite_resume',
            key='hundred', phase='append', snapshotIds=[snapshot.id],
            operations=[replace(snapshot, 'narrative', index*5, index*5+1, 'x') for index in range(100)]))
        assert 'error' not in result, result
        value = service.proposals.get(workspace.project_id, result['proposalId'], 1)
        denied = await session.call('prepare_edit_batch', AssistantAssemblyRequestV1(protocolVersion=1, taskId='rewrite_resume',
            proposalId=value.proposal.id, key='too_many', phase='finalize', snapshotIds=[snapshot.id],
            operations=[replace(snapshot, 'narrative', 500, 501, 'x')]))
        assert denied['error']['code'] == 'AGENT_EDIT_LIMIT'
        service.proposals.finish(workspace.project_id, session.run.id)
        retained = service.proposals.get(workspace.project_id, value.proposal.id, 1)
        assert retained.proposal.state == 'incomplete' and retained.proposal.operation_count == 100
        assert retained.candidate == value.candidate
        assert projects.storage.read_committed(workspace.project_id)[1] == before and not runtime.calls
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_http_continue_requires_protocol_dispatches_one_scripted_turn_and_retains_useful_quota_draft(tmp_path):
    import asyncio
    from tests.recovery.test_agent_routes import application, enabled
    from tests.support.agent import run_request
    from resume_api.agent.runtime import RuntimeResult
    from resume_api.agent.tools import AgentTools
    prompts = []
    async def script(value, _cancel, _emit):
        prompts.append(value.prompt)
        return RuntimeResult(state='failed', error='AGENT_QUOTA', text='Достигнут лимит; черновик сохранён.')
    async with application(tmp_path, script) as (client, _, service, workspace, conversation, prefix, runtime, _):
        service.assistant_protocol_enabled = True
        settings = await enabled(client)
        lease = service.leases.open(workspace.project_id, 'history_1')
        request = run_request(conversation.id, owner=lease.owner.model_dump(by_alias=True), settingsRevision=settings['revision'])
        request.allow_edits = False
        run, _ = service.submit(workspace.project_id, request)
        session = ToolSession(service, RunControl(workspace.project_id, run.id, run.owner_epoch,
            run.connection_epoch, time.monotonic()), run, Fetcher())
        try:
            snapshot = await read_document(session)
            first, _ = await append(session, 'useful', snapshot=snapshot)
        finally:
            await session.close()
        service.proposals.finish(workspace.project_id, run.id)
        service.store.finish(workspace.project_id, run.id, 'interrupted', error='AGENT_INTERRUPTED')
        value = service.proposals.get(workspace.project_id, first['proposalId'], 1)
        next_request = request.model_copy(update={'client_request_id': 'http_continue'})
        payload = AssistantContinueRunV1(protocolVersion=1, proposal=identity_request(value), request=next_request).model_dump(by_alias=True)
        before = service.projects.storage.read_committed(workspace.project_id)[1]
        assert (await client.post(prefix+'/continuations/run', json=payload)).status_code == 409
        bad = dict(payload); bad['protocolVersion'] = True
        assert (await client.post(prefix+'/continuations/run', json=bad, headers={'X-FoldCV-Assistant-Protocol': '1'})).status_code == 422
        assert not runtime.calls
        service.tools = AgentTools(service, fetcher=Fetcher())
        first_reply = await client.post(prefix+'/continuations/run', json=payload, headers={'X-FoldCV-Assistant-Protocol': '1'})
        assert first_reply.status_code == 202, first_reply.text
        again = await client.post(prefix+'/continuations/run', json=payload, headers={'X-FoldCV-Assistant-Protocol': '1'})
        assert again.status_code == 200 and again.json()['id'] == first_reply.json()['id']
        await asyncio.wait_for(service.controls[first_reply.json()['id']].task, 10)
        result = await client.get(prefix+'/outcomes/'+first_reply.json()['id'], headers={'X-FoldCV-Assistant-Protocol': '1'})
        assert result.json()['outcome'] == 'incomplete' and not result.json()['durable']
        retained = service.proposals.get(workspace.project_id, value.proposal.id, 2)
        assert retained.proposal.state == 'incomplete' and retained.proposal.changes == value.proposal.changes
        assert service.projects.storage.read_committed(workspace.project_id)[1] == before
        assert len(prompts) == 1 and 'continuedDraft' in prompts[0]
        assert runtime.native is False and runtime.calls == ['assistant-model']
        from resume_api.agent.service import AgentService
        restarted = AgentService(service.projects, runtime, service.connection, tools=None)
        restarted.assistant_protocol_enabled = True
        service.projects.agent = restarted
        restarted.recover()
        restored = restarted.proposals.get(workspace.project_id, value.proposal.id, 2)
        assert restored == retained and restored.proposal.state == 'incomplete'
        assert runtime.calls == ['assistant-model']



@pytest.mark.asyncio
async def test_terminal_origin_reserves_exact_receipt_headroom_before_apply(tmp_path, monkeypatch):
    from tests.recovery.test_assistant_approval import ready, commit_request
    from packages.resume_core.agent_store import budget_parts, reviewed_headroom
    from packages.resume_core import agent_limits
    approval, service, runtime, projects, workspace, payload = await ready(tmp_path)
    before = projects.storage.read_committed(workspace.project_id)[1]
    original = service.store.load(workspace.project_id)
    with monkeypatch.context() as bound:
        bound.setattr(agent_limits, 'JOURNAL_BYTES', budget_parts(original, original.journals[0])[0] + 1000)
        with pytest.raises(AgentFailure, match='AGENT_EDIT_LIMIT'):
            approval.claim(workspace.project_id, payload)
    assert projects.storage.read_committed(workspace.project_id)[1] == before
    claimed = approval.claim(workspace.project_id, payload)
    state = service.store.load(workspace.project_id)
    journal = run_in(state, claimed.claim.batch.run_id)[2]
    exact = budget_parts(state, journal)[0] + reviewed_headroom(journal)
    assert reviewed_headroom(journal) > 32000
    monkeypatch.setattr(agent_limits, 'JOURNAL_BYTES', exact)
    saved = approval.commit(workspace.project_id, commit_request(payload, claimed))
    assert saved.receipt.durable
    state = service.store.load(workspace.project_id)
    journal = run_in(state, claimed.claim.batch.run_id)[2]
    assert budget_parts(state, journal)[0] < exact and reviewed_headroom(journal) == 0
    assert not runtime.calls


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['canonical', 'expired', 'missing_proof'])
async def test_continue_rejects_stale_or_expired_proof_without_dispatch(tmp_path, change):
    from datetime import datetime, timedelta
    service, runtime, projects, workspace, old, payload = await incomplete(tmp_path)
    before = len(service.store.load(workspace.project_id).journals)
    if change == 'canonical':
        current = projects.read(workspace.project_id).model_copy(deep=True)
        next(block for block in current.project.document.blocks() if block.id == 'narrative').content[0].text = 'Human edit'
        projects.workspaces[workspace.project_id] = current
        assert projects.persist(workspace.project_id) == 'durable'
    elif change == 'expired':
        service.store.clock = lambda: (datetime.fromisoformat(old.proposal.expires_at) + timedelta(seconds=1)).isoformat()
    else:
        # A lost private proof must never become a fabricated completed read.
        from packages.resume_core.assistant_proposals import encoded
        old.read_groups = []
        path = service.proposals.directory(workspace.project_id) / service.proposals.filename(old)
        path.write_bytes(encoded(old))
        service.store.update(workspace.project_id, lambda state: setattr(run_in(state, old.proposal.origin_run_id)[2], 'snapshots', []))
    with pytest.raises(AgentFailure):
        submit_run(service, workspace.project_id, payload)
    assert len(service.store.load(workspace.project_id).journals) == before and not runtime.calls


@pytest.mark.asyncio
async def test_twenty_retained_versions_keep_the_same_work_and_refuse_another_dispatch(tmp_path):
    from resume_api.agent.continuation import options
    service, runtime, projects, workspace, value, payload = await incomplete(tmp_path)
    before = projects.storage.read_committed(workspace.project_id)[1]
    expected = value.proposal.content_sha256
    for version in range(2, 21):
        service.leases.renew(workspace.project_id, payload.request.owner)
        payload = payload.model_copy(deep=True)
        payload.proposal = identity_request(value)
        payload.request.client_request_id = f'explicit_step_{version}'
        run, created = submit_run(service, workspace.project_id, payload)
        assert created
        if version == 20:
            from resume_api.agent.capabilities import catalog
            fresh = {task.id: task for task in catalog(service, workspace.project_id).tasks}
            active = {task.id: task for task in catalog(service, workspace.project_id, draft_run_id=run.id).tasks}
            assert fresh['rewrite_resume'].generation.reason_code == 'AGENT_PROJECT_FULL'
            assert 'до 7 дней' in fresh['rewrite_resume'].generation.remedy
            assert fresh['check_resume'].generation.state == fresh['draft_text'].generation.state == 'available'
            assert active['rewrite_resume'].generation.state == 'available'
        service.proposals.finish(workspace.project_id, run.id)
        service.store.finish(workspace.project_id, run.id, 'interrupted', error='AGENT_INTERRUPTED')
        value = service.proposals.get(workspace.project_id, value.proposal.id, version)
        assert value.proposal.state == 'incomplete' and value.proposal.operation_count == 1
        assert value.proposal.content_sha256 == expected
    option = next(item for item in options(service, workspace.project_id).options if item.proposal.version == 20)
    assert option.versions_remaining == 0 and option.availability.state == 'temporarily_unavailable'
    payload.proposal = identity_request(value)
    payload.request.client_request_id = 'step_21'
    with pytest.raises(AgentFailure, match='AGENT_PROJECT_FULL'):
        submit_run(service, workspace.project_id, payload)
    assert len(service.store.load(workspace.project_id).journals) == 20
    assert projects.storage.read_committed(workspace.project_id)[1] == before and not runtime.calls


def test_known_oversize_resources_disable_generation_with_an_alternative_that_fits(tmp_path):
    from tests.recovery.test_agent_lifecycle import setup
    from resume_api.agent.capabilities import catalog
    from packages.resume_core.assistant_proposals import VERSION_BYTES
    service, runtime, projects, workspace, _, _, _ = setup(tmp_path, None)
    service.assistant_protocol_enabled = True
    before = projects.storage.read_committed(workspace.project_id)[1]
    large = projects.read(workspace.project_id).model_copy(deep=True)
    from packages.resume_core.models.contracts import Source
    large.project.sources = [Source.model_validate({'id': 'oversize_source', 'revision': 1,
        'originalName': 'synthetic.txt', 'mimeType': 'text/plain', 'byteSha256': 'a' * 64,
        'byteRef': 'sources/oversize_source/original', 'parser': 'text', 'parserVersion': 'fixture',
        'units': [{'id': 'oversize_unit', 'revision': 1, 'order': 0, 'text': 'x' * VERSION_BYTES,
            'location': {'kind': 'pasted', 'index': 0, 'row': None, 'column': None},
            'disposition': 'shown', 'representedFactIds': []}], 'overlays': [], 'warnings': []})]
    projects.workspaces[workspace.project_id] = large
    tasks = {task.id: task for task in catalog(service, workspace.project_id).tasks}
    reason = tasks['rewrite_resume'].generation
    assert reason.state == 'temporarily_unavailable' and reason.reason_code == 'AGENT_EDIT_LIMIT'
    assert 'Меньшая область не убирает' in reason.remedy
    assert tasks['rewrite_resume'].review.state == 'available'
    assert tasks['draft_text'].generation.state == tasks['check_resume'].generation.state == 'available'
    assert projects.storage.read_committed(workspace.project_id)[1] == before and not runtime.calls
