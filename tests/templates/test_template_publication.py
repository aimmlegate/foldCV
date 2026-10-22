"""Template snapshots use the real canonical claim/receipt transaction offline."""

import threading
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services' / 'api' / 'src'))

from packages.resume_core.background_history import ScopeHistory, digest_bytes
from packages.resume_core.background_publication import CanonicalCoordinator
from packages.resume_core.background_store import BackgroundFailure, JobStore
from packages.resume_core.models.template_authority import TemplateFinalizationBinding
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.rich_project_store import RichProjectStore
from packages.resume_core.template_finalization import capture_finalization
from packages.resume_core.template_identity import capture_span
from tests.templates.pipeline_fixtures import ready_operation, setup_operation
from tests.templates.storage_fixtures import presentation, workspace


WALL = '2026-10-21T00:05:01+00:00'


class TemplatePublicationFixture:
    def __init__(self, root, *, create=True):
        from resume_api.agent.context import query_fingerprint
        self.root, self.now = root, WALL
        self.canonical = RichProjectStore(root)
        self.jobs = JobStore(root, clock=lambda: self.now)
        self.history = ScopeHistory(self.jobs, query_fingerprint)
        self.publisher = CanonicalCoordinator(self.jobs, self.history, self.canonical, lambda *_: None)
        self.external_authority = True
        def gate(_binding, _before, _after):
            if not self.external_authority:
                raise BackgroundFailure('DEPENDENCY_CHANGED')
        self.publisher.template_authority = gate
        self.project = 'pipeline-project'
        self.originals = {(self.project, key): raw for key, raw in workspace()[1].items()}
        if not create:
            return
        full = workspace()[0].model_dump(by_alias=True)
        operation = ready_operation()
        _, _, package, source, facts = setup_operation()
        operation.state, operation.inference_closed = 'cleanup_pending', True
        operation.tasks[0].state = 'source_fallback'
        full['projectId'] = full['project']['projectId'] = self.project
        full['projectRevision'] = full['documentRevision'] = full['project']['revision'] = 2
        full['project']['facts'] = facts.model_dump(by_alias=True)
        full['project']['document']['revision'] = 2
        for region in full['project']['document']['regions']:
            region['blocks'] = []
        full['project']['document']['regions'][2]['blocks'] = [{'id': 'source-fallback', 'revision': 1,
            'type': 'paragraph', 'props': {}, 'content': [{'type': 'text', 'text': source.units[0].text, 'styles': {}}],
            'children': [], 'provenance': [], 'presentation': presentation(package)}]
        full['project']['importCoverage'] = [{'span': capture_span(source, source.units[0]).model_dump(by_alias=True),
            'itemHandle': None, 'blockIds': ['source-fallback'], 'disposition': 'fallback', 'reason': 'controlled-check-failure'}]
        self.after = WorkspaceV7.model_validate(full)
        operation.finalization = capture_finalization(operation, self.after.project, WALL)
        operation.state = 'finalizing'
        self.after.project.template_operations = [operation]
        before = self.after.model_dump(by_alias=True)
        before['projectRevision'] = before['documentRevision'] = 1
        before['preDraft'] = {'selectedInput': 'text', 'selectedSourceId': source.id,
            'sources': [source.model_dump(by_alias=True)], 'facts': facts.model_dump(by_alias=True),
            'operations': [], 'warnings': [], 'templatePackage': package.model_dump(by_alias=True),
            'templateOperations': [operation.model_dump(by_alias=True)]}
        before['project'] = None
        self.before = WorkspaceV7.model_validate(before)
        self.canonical.save(self.before, self.originals, {})
        self.jobs.open(self.project)
        self.publisher.authorize_template(self.project, operation)
        self.binding = TemplateFinalizationBinding(operationId=operation.id,
            authorizationId=operation.authorizations[-1].id, finalizationId=operation.finalization.id)
        self.command = 'template_publication_' + operation.finalization.id

    def publish(self):
        return self.publisher.snapshot(self.project, digest_bytes(self.before), self.after, self.command,
            originals=self.originals, template_finalization=self.binding)

    def current(self):
        return self.canonical.read_committed(self.project)[0]

    def fresh(self):
        fresh = TemplatePublicationFixture(self.root, create=False)
        fresh.before, fresh.after, fresh.binding, fresh.command = self.before, self.after, self.binding, self.command
        return fresh


def test_expired_processing_uses_application_finalization_and_replays_without_application(tmp_path):
    fixture = TemplatePublicationFixture(tmp_path)
    saved, duplicate = fixture.publish()
    assert not duplicate and saved.project is not None
    assert saved.project.template_operations[0].inference_closed
    assert fixture.current() == fixture.after
    again, duplicate = fixture.publish()
    assert duplicate and again == saved
    assert len(fixture.jobs.load(fixture.project).manual_intents) == 1


@pytest.mark.parametrize('reason', ['cancel', 'authority', 'expiry', 'missing_gate'])
def test_denial_before_claim_keeps_exact_prior_workspace(tmp_path, reason):
    fixture = TemplatePublicationFixture(tmp_path)
    original = digest_bytes(fixture.current())
    def act(name, _project):
        if name != 'before_commit_claim':
            return
        if reason == 'cancel':
            assert fixture.publisher.cancel_template(fixture.project, fixture.binding.operation_id)
        elif reason == 'authority':
            fixture.external_authority = False
        elif reason == 'expiry':
            fixture.now = '2026-10-21T00:05:31+00:00'
        else:
            del fixture.publisher.template_authority
    fixture.publisher.observer = act
    expected = {'cancel': 'CANCELLED', 'authority': 'DEPENDENCY_CHANGED', 'expiry': 'REQUEST_EXPIRED', 'missing_gate': 'WRITER_UNKNOWN'}[reason]
    with pytest.raises(BackgroundFailure, match=expected):
        fixture.publish()
    assert digest_bytes(fixture.current()) == original
    assert fixture.jobs.load(fixture.project).manual_intents[0].phase == 'reconciled'


def test_cancellation_after_durable_claim_reports_saved_and_never_promises_rollback(tmp_path):
    fixture = TemplatePublicationFixture(tmp_path)
    attempts, attempted, result = [], threading.Event(), []
    def cancel():
        attempted.set()
        result.append(fixture.publisher.cancel_template(fixture.project, fixture.binding.operation_id))
    def act(name, _project):
        if name == 'commit_claimed':
            thread = threading.Thread(target=cancel)
            attempts.append(thread)
            thread.start()
            assert attempted.wait(2)
    fixture.publisher.observer = act
    fixture.publish()
    for thread in attempts:
        thread.join(5)
        assert not thread.is_alive()
    assert result == [False] and fixture.current() == fixture.after
    assert fixture.jobs.load(fixture.project).manual_intents[0].phase == 'receipt_stored'


@pytest.mark.parametrize('phase,saved', [('intent_stored', False), ('workspace_replaced', True),
    ('workspace_durable', True), ('receipt_stored', True)])
def test_fresh_object_recovers_exact_prior_or_new_template_snapshot(tmp_path, phase, saved):
    fixture = TemplatePublicationFixture(tmp_path)
    reached = []
    def fail(name, _project):
        if name == phase:
            reached.append(name)
            raise OSError('controlled publication interruption')
    fixture.publisher.observer = fail
    if phase == 'receipt_stored':
        assert fixture.publish()[0] == fixture.after
    else:
        with pytest.raises((OSError, BackgroundFailure)):
            fixture.publish()
    assert reached == [phase]
    fresh = fixture.fresh()
    state = fresh.publisher.recover(fresh.project)
    assert fresh.current() == (fresh.after if saved else fresh.before)
    assert state.manual_intents[0].phase == ('receipt_stored' if saved else 'reconciled')
    assert fresh.publisher.recover(fresh.project) == state
