"""Retain ordinary authoring inverses only for the verified current opening."""

from copy import deepcopy
from contextlib import contextmanager
from dataclasses import dataclass, field
import threading

from .agent_edits import semantic
from .background_limits import LIMITS
from .background_store import BackgroundFailure, RetainedUsage
from .rich_dependencies import placements
from .rich_mutations import mutation_sha256
from .template_inverse import inverse_template_mutation
from .template_mutations import HistoryAuthorization
from .template_anchors import coverage_address
from .models.template_mutations import AuthoredBlockHistoryDelta
from .template_block_patches import block_delta, block_hash, restore_payload
from .templates.compiler import canonical, sha256


def values(workspace):
    project = workspace.project
    result = {('block', block.id): block.model_dump(mode='json', by_alias=True, exclude={'children'})
        for block in project.document.blocks()}
    result.update({('placement', key): list(value) for key, value in placements(project.document).items()})
    for name, items in [('builtin', project.facts.records), ('extension', project.facts.extensions),
            ('relation', project.facts.relations), ('issue', project.import_issues)]:
        result.update({(name, item.id): item.model_dump(mode='json', by_alias=True) for item in items})
    result.update({('builtin_scope', key): value for key, value in project.facts.builtin_manual_scopes.items()})
    result.update({('tombstone', item.record_id): item.model_dump(mode='json', by_alias=True) for item in project.facts.tombstones})
    result.update({('coverage_anchor', coverage_address(project, index)): item.model_dump(mode='json', by_alias=True)
        for index, item in enumerate(project.import_coverage)})
    previous = None
    for row in workspace.sync_records:
        result[('sync', row.id)] = row.model_dump(mode='json', by_alias=True)
        result[('sync_placement', row.id)] = {'afterSyncId': previous}
        previous = row.id
    return result


def changes(before, after):
    old, new = values(before), values(after)
    result = {}
    for key in sorted(old.keys() | new.keys()):
        left, right = old.get(key), new.get(key)
        if key[0] == 'block' and left is not None and right is not None:
            if block_hash(left) != block_hash(right):
                result[key] = block_delta(left, right)
        elif semantic(left) != semantic(right):
            result[key] = deepcopy(left), deepcopy(right)
    return result


def merge_changes(previous, latest, before, after):
    result = deepcopy(previous)
    current, resulting = values(before), values(after)
    for key, change in latest.items():
        old = previous.get(key)
        if old is None:
            result[key] = change
            continue
        if key[0] == 'block':
            expected = current.get(key)
            if isinstance(old, AuthoredBlockHistoryDelta):
                original = restore_payload(expected, old.after_semantic_hash, old.before_semantic_hash, old.inverse_patch)
                original['revision'] = expected['revision']
            else:
                if (expected is None) != (old[1] is None) or expected is not None and block_hash(expected) != block_hash(old[1]):
                    raise BackgroundFailure('DEPENDENCY_CHANGED')
                original = old[0]
            final = resulting.get(key)
            if original is not None and final is not None:
                if block_hash(original) == block_hash(final):
                    result.pop(key, None)
                else:
                    result[key] = block_delta(original, final)
            elif original is None and final is None:
                result.pop(key, None)
            else:
                result[key] = deepcopy(original), deepcopy(final)
        else:
            if semantic(change[0]) != semantic(old[1]):
                raise BackgroundFailure('DEPENDENCY_CHANGED')
            if semantic(old[0]) == semantic(change[1]):
                result.pop(key, None)
            else:
                result[key] = deepcopy(old[0]), deepcopy(change[1])
    return result


def restore(current, delta):
    existing = values(current)
    restored = deepcopy(existing)
    for key, change in delta.items():
        if isinstance(change, AuthoredBlockHistoryDelta):
            value = existing.get(key)
            if value is None:
                raise BackgroundFailure('DEPENDENCY_CHANGED')
            old = restore_payload(value, change.after_semantic_hash, change.before_semantic_hash, change.inverse_patch)
            restored[key] = {**old, 'revision': value['revision']}
            continue
        old, expected = change
        if (key[0] == 'block' and expected is not None and (existing.get(key) is None or block_hash(existing[key]) != block_hash(expected))
                or key[0] != 'block' and semantic(existing.get(key)) != semantic(expected)
                or key[0] == 'block' and expected is None and existing.get(key) is not None):
            raise BackgroundFailure('DEPENDENCY_CHANGED')
        if old is None:
            restored.pop(key, None)
        else:
            restored[key] = deepcopy(old)
    result = current.model_copy(deep=True)
    from .template_synchronization import restore_sync_rows
    result.sync_records = restore_sync_rows(current, restored, delta)
    facts = result.project.facts.model_dump(mode='json', by_alias=True)
    for name, key in [('builtin', 'records'), ('extension', 'extensions'), ('relation', 'relations')]:
        facts[key] = [value for (kind, _identifier), value in restored.items() if kind == name]
    facts['builtinManualScopes'] = {identifier: value for (kind, identifier), value in restored.items() if kind == 'builtin_scope'}
    live = {record['id'] for record in facts['records']}
    live.update(record['id'] for record in facts['extensions'] if record['active'])
    facts['tombstones'] = [value for (kind, identifier), value in restored.items() if kind == 'tombstone' and identifier not in live]
    result.project.facts = type(result.project.facts).model_validate(facts)
    issue_type = type(result.project.import_issues[0]) if result.project.import_issues else None
    result.project.import_issues = [issue_type.model_validate(value) for (kind, _identifier), value in restored.items() if kind == 'issue']
    for index, item in enumerate(result.project.import_coverage):
        retained = restored.get(('coverage_anchor', coverage_address(result.project, index)))
        if retained is None:
            raise BackgroundFailure('DEPENDENCY_CHANGED')
        item.block_ids = list(retained['blockIds'])
    blocks = {identifier: value for (kind, identifier), value in restored.items() if kind == 'block'}
    positions = {identifier: value for (kind, identifier), value in restored.items() if kind == 'placement'}
    mounted = set()
    def children(parent, ancestors=()):
        selected = {identifier: value for identifier, value in positions.items() if value[0] == parent}
        following = {}
        for identifier, (_owner, previous, _record) in selected.items():
            if previous in following or previous is not None and previous not in selected:
                raise BackgroundFailure('DEPENDENCY_CHANGED')
            following[previous] = identifier
        output, previous = [], None
        while previous in following:
            identifier = following[previous]
            if identifier in mounted or identifier in ancestors or identifier not in blocks:
                raise BackgroundFailure('DEPENDENCY_CHANGED')
            mounted.add(identifier)
            value = deepcopy(blocks[identifier])
            value['children'] = children(identifier, (*ancestors, identifier))
            output.append(value)
            previous = identifier
        if len(output) != len(selected):
            raise BackgroundFailure('DEPENDENCY_CHANGED')
        return output
    document = result.project.document.model_dump(mode='json', by_alias=True)
    for region in document['regions']:
        region['blocks'] = children(region['id'])
    if mounted != blocks.keys():
        raise BackgroundFailure('DEPENDENCY_CHANGED')
    result.project.document = type(result.project.document).model_validate(document)
    return result


def check_replay_budget(workspace, action, mutation, *, allow_conflict=False):
    if not action.delta:
        return
    try:
        target = restore(workspace, action.delta)
    except BackgroundFailure as error:
        if allow_conflict and error.code == 'DEPENDENCY_CHANGED':
            return
        raise
    identifier = 'history-budget-' + mutation.client_mutation_id
    while any(value.client_mutation_id == identifier for value in workspace.mutation_replay):
        identifier += '.'
    undo = inverse_template_mutation(target, workspace, origin_action_id=action.identifier,
        mutation_id=identifier, session_id=mutation.capture.session_id, action_token=action.token + 1)
    if undo is None:
        return
    from .rich_mutations import apply_rich_mutation
    authorization = TemplateLocalHistory.authorization(workspace, undo)
    restored, _duplicate = apply_rich_mutation(workspace, undo, history_authorization=authorization)
    inverse_template_mutation(workspace, restored, origin_action_id=action.identifier,
        mutation_id='inverse_' + identifier, session_id=mutation.capture.session_id,
        action_token=action.token + 2, kind='redo')


def rebase_sync_preconditions(opening, pending, candidate):
    if pending['direction'] not in {'undo', 'redo'}:
        return
    mutation = pending['mutation']
    if mutation.history.kind != pending['direction']:
        raise BackgroundFailure('OUTCOME_UNKNOWN')
    normalized = {step.record.id for step in mutation.steps if step.kind == 'put_template_sync'}
    actual = {row.id: row.model_dump(mode='json', by_alias=True) for row in candidate.workspace.sync_records
        if row.id in normalized}
    authority = {'lifecycleId', 'capture', 'dependencies'}
    rebased = {}
    for identifier, row in actual.items():
        if row['capture'] != mutation.capture.model_dump(mode='json', by_alias=True):
            raise BackgroundFailure('OUTCOME_UNKNOWN')
        payload = {key: value for key, value in row.items() if key not in authority}
        for action in opening.actions:
            if not action.valid or action.identifier == pending['action'].identifier:
                continue
            key = ('sync', identifier)
            change = action.delta.get(key)
            if change is None or change[1] is None:
                continue
            expected = {name: value for name, value in change[1].items() if name not in authority}
            if expected == payload:
                # Every retained delta guards its next replay with tuple[1], including undone actions.
                action.delta[key] = (change[0], deepcopy(row))
                rebased[action.identifier] = action
    for action in rebased.values():
        if len(canonical(TemplateLocalHistory.delta_wire(action.delta))) > LIMITS.inverse_bytes:
            raise BackgroundFailure('JOB_STORAGE_FULL')
        check_replay_budget(candidate.workspace, action, mutation, allow_conflict=True)


@dataclass
class Action:
    identifier: str
    generation: int
    token: int
    delta: dict
    scopes: set[str]
    valid: bool = True


@dataclass
class Opening:
    key: tuple
    actions: list[Action] = field(default_factory=list)
    cursor: int = 0
    generations: dict[str, int] = field(default_factory=dict)
    pending: dict = field(default_factory=dict)
    commands: dict = field(default_factory=dict)
    generation: int = 0
    known_ids: set[str] = field(default_factory=set)
    continuation: tuple[str, int] | None = None


class TemplateLocalHistory:
    def __init__(self, jobs=None):
        self.lock = threading.RLock()
        self.locks = {}
        self.openings = {}
        self.jobs = jobs
        self.usage_key = 'template_local_history:' + str(id(self))
        if jobs is not None:
            jobs.usage_providers[self.usage_key] = self.usage
            jobs.state_observers[self.usage_key] = self.lifecycle

    def lifecycle(self, state):
        current = self.openings.get(state.project_id)
        if current is not None and (state.tombstoned or state.writer is None
                or state.writer.status == 'clean_detached' or current.key != self.key(state)):
            self.discard(state.project_id)

    @staticmethod
    def delta_wire(delta):
        return [[list(key), item.model_dump(mode='json', by_alias=True)
            if isinstance(item, AuthoredBlockHistoryDelta) else list(item)] for key, item in delta.items()]

    @classmethod
    def retained(cls, opening):
        def action(value):
            return {'id': value.identifier, 'generation': value.generation, 'token': value.token,
                'delta': cls.delta_wire(value.delta), 'scopes': sorted(value.scopes), 'valid': value.valid}
        pending = {key: {**value, 'action': action(value['action']),
            'mutation': value['mutation'].model_dump(mode='json', by_alias=True)} for key, value in opening.pending.items()}
        commands = {key: [value[0], value[1].model_dump(mode='json', by_alias=True), *value[2:]]
            for key, value in opening.commands.items()}
        raw = {'key': list(opening.key), 'actions': [action(value) for value in opening.actions],
            'cursor': opening.cursor, 'generations': opening.generations, 'pending': pending, 'commands': commands,
            'generation': opening.generation, 'knownIds': sorted(opening.known_ids), 'continuation': opening.continuation}
        action_records = lambda value: 1 + len(value.delta) + len(value.scopes)
        records = (1 + sum(action_records(value) for value in opening.actions) + len(opening.generations)
            + len(opening.known_ids) + len(opening.commands) + int(opening.continuation is not None)
            + sum(1 + action_records(value['action']) for value in opening.pending.values()))
        return RetainedUsage(0, len(canonical(raw)) + sum(value.get('reserved_bytes', 0) for value in opening.pending.values()),
            records + sum(value.get('reserved_records', 0) for value in opening.pending.values()))

    def usage(self, *, replacing=None, states=None):
        openings = {**self.openings}
        if replacing is not None:
            openings[replacing.key[0]] = replacing
        result = {}
        for project, opening in openings.items():
            state = states.get(project) if states is not None else None
            if state is not None and (state.tombstoned or state.writer is None
                    or state.writer.status == 'clean_detached' or opening.key != self.key(state)):
                continue
            result[project] = self.retained(opening)
        return result

    def rollback_unpublished(self, owner, mutation):
        identifier = mutation.client_mutation_id
        try:
            with owner.coordinator._writer(mutation.project_id), owner.jobs.guard(mutation.project_id) as directory:
                state = owner.jobs._read(mutation.project_id, directory)
                workspace, _checksum = owner.coordinator.canonical._read_committed_unlocked(mutation.project_id)
                if (any(value.client_mutation_id == identifier for value in state.manual_intents)
                        or any(value.client_mutation_id == identifier for value in workspace.mutation_replay)):
                    return
                opening = self.openings.get(mutation.project_id)
                pending = opening.pending.get(identifier) if opening is not None else None
                if pending is None or pending['mutation_hash'] != mutation_sha256(mutation):
                    return
                opening.pending.pop(identifier)
                self.discard_empty(opening)
        except Exception:
            # Keep the reservation when durable publication evidence cannot be read.
            return

    def discard_empty(self, opening):
        if (not opening.actions and not opening.pending and not opening.commands and not opening.known_ids
                and not opening.generations and opening.generation == 0 and opening.continuation is None):
            if self.openings.get(opening.key[0]) is opening:
                self.discard(opening.key[0])
            return True
        return False

    @contextmanager
    def guard(self, project):
        with self.lock:
            lock = self.locks.setdefault(project, threading.RLock())
        with lock:
            yield

    @staticmethod
    def key(state):
        writer = state.writer
        return (state.project_id, state.lineage, writer.epoch, writer.incarnation, writer.session_id)

    def opening(self, state, *, create=False):
        key = self.key(state)
        old = self.openings.get(state.project_id)
        if old is not None and old.key != key:
            self.openings.pop(state.project_id)
            old = None
        if old is None and create:
            old = Opening(key)
        return old

    def discard(self, project):
        self.openings.pop(project, None)

    @staticmethod
    def observe(opening, state):
        current = {value.key: value.generation for value in state.generations}
        for action in opening.actions:
            if any(current.get(key) != opening.generations.get(key) for key in action.scopes):
                action.valid = False

    def reconcile(self, owner, state, workspace, directory):
        opening = self.opening(state)
        if opening is None:
            return None
        for identifier, pending in list(opening.pending.items()):
            proof = next((value for value in workspace.mutation_replay if value.client_mutation_id == identifier), None)
            intent = next((value for value in state.manual_intents if value.client_mutation_id == identifier), None)
            if proof is None:
                if intent is None or intent.phase == 'reconciled':
                    opening.pending.pop(identifier)
                    continue
                raise BackgroundFailure('OUTCOME_UNKNOWN')
            if proof.request_sha256 != pending['mutation_hash']:
                raise BackgroundFailure('OUTCOME_UNKNOWN')
            if intent is None or intent.phase != 'receipt_stored' or intent.candidate_pruned:
                opening.generation = max([opening.generation, *[value['action'].generation for value in opening.pending.values()]])
                opening.known_ids.update(value['action'].identifier for value in opening.pending.values())
                opening.actions.clear()
                opening.cursor = 0
                opening.pending.clear()
                opening.commands.clear()
                opening.continuation = None
                opening.generations = {value.key: value.generation for value in state.generations}
                return opening
            candidate = owner.coordinator._load_candidate(state, directory, intent)
            self._finish(opening, identifier, pending, candidate)
        if self.discard_empty(opening):
            return None
        self.observe(opening, state)
        return opening

    @staticmethod
    def _finish(opening, identifier, pending, candidate):
        scopes = {stamp.key for stamp in [*candidate.inverse_guards.reads, *candidate.inverse_guards.writes]}
        action, direction = pending['action'], pending['direction']
        if action.generation != opening.generation + 1:
            raise BackgroundFailure('OUTCOME_UNKNOWN')
        if direction == 'edit':
            old = next((value for value in opening.actions if value.identifier == action.identifier), None)
            latest = old is None or opening.actions.index(old) == opening.cursor - 1
            if not action.delta:
                if old is not None:
                    opening.actions.remove(old)
                    opening.cursor -= 1
                if latest:
                    opening.continuation = (action.identifier, action.token)
            elif old is None:
                opening.actions[opening.cursor:] = [action]
                opening.cursor += 1
                opening.continuation = None
            else:
                opening.actions[opening.actions.index(old)] = action
                opening.actions = opening.actions[:opening.cursor]
                if latest:
                    opening.continuation = None
        else:
            old = opening.actions[opening.cursor - 1 if direction == 'undo' else opening.cursor]
            if old.identifier != action.identifier or old.generation >= action.generation:
                raise BackgroundFailure('OUTCOME_UNKNOWN')
            opening.actions[opening.actions.index(old)] = action
            opening.cursor += -1 if direction == 'undo' else 1
            opening.commands[identifier] = (pending['command_hash'], pending['mutation'], action.identifier, action.generation)
            opening.continuation = None
            rebase_sync_preconditions(opening, pending, candidate)
        check_replay_budget(candidate.workspace, action, pending['mutation'])
        opening.generation = action.generation
        opening.known_ids.add(action.identifier)
        action.scopes.update(scopes)
        opening.generations = {stamp.key: stamp.generation for stamp in candidate.after_history.generations}
        opening.pending.pop(identifier)

    def prepare_edit(self, opening, mutation, before, after, candidate, state):
        if any(value.identifier == mutation.action_id for value in opening.actions[opening.cursor:]):
            raise BackgroundFailure('DEPENDENCY_CHANGED')
        delta = changes(before, after)
        old = next((value for value in opening.actions[:opening.cursor] if value.identifier == mutation.action_id), None)
        if old is None and mutation.action_id in opening.known_ids:
            anchor = opening.continuation
            if anchor is None or anchor[0] != mutation.action_id or mutation.capture.action_token < anchor[1]:
                raise BackgroundFailure('DEPENDENCY_CHANGED')
        scopes = set()
        if old is not None:
            index = opening.actions.index(old)
            later = opening.actions[index + 1:opening.cursor]
            if (not old.valid or mutation.capture.action_token < old.token
                    or later and mutation.kind != 'reconciliation'
                    or any(set(value.delta) & set(delta) for value in later)):
                raise BackgroundFailure('DEPENDENCY_CHANGED')
            delta = merge_changes(old.delta, delta, before, after)
            scopes.update(old.scopes)
        action = Action(mutation.action_id, opening.generation + 1, mutation.capture.action_token, delta, scopes)
        self._prepare(opening, mutation, action, 'edit', candidate, state)

    def _prepare(self, opening, mutation, action, direction, candidate, state, command_hash=None):
        action.scopes.update(stamp.key for stamp in [*candidate.inverse_guards.reads, *candidate.inverse_guards.writes])
        if len(canonical(self.delta_wire(action.delta))) > LIMITS.inverse_bytes:
            raise BackgroundFailure('JOB_STORAGE_FULL')
        prospective = deepcopy(opening)
        pending = {'mutation_hash': mutation_sha256(mutation), 'mutation': mutation.model_copy(deep=True),
            'action': deepcopy(action), 'direction': direction, 'command_hash': command_hash,
            'reserved_bytes': 0, 'reserved_records': 0}
        prospective.pending[mutation.client_mutation_id] = pending
        final = deepcopy(prospective)
        self._finish(final, mutation.client_mutation_id, final.pending[mutation.client_mutation_id], candidate)
        current_usage, final_usage = self.retained(prospective), self.retained(final)
        pending['reserved_bytes'] = max(0, final_usage.owned_bytes - current_usage.owned_bytes)
        pending['reserved_records'] = max(0, final_usage.records - current_usage.records)
        usage = self.retained(prospective)
        if usage.owned_bytes > LIMITS.sidecar_project_bytes or usage.records > LIMITS.metadata_project_records:
            raise BackgroundFailure('JOB_STORAGE_FULL')
        if self.jobs is not None:
            self.jobs._capacity(state, self.jobs._all(), retained_usage={self.usage_key: self.usage(replacing=prospective)})
        opening.pending[mutation.client_mutation_id] = pending
        self.openings[state.project_id] = opening

    @staticmethod
    def action(opening, request):
        if opening is None:
            raise BackgroundFailure('REQUEST_EXPIRED')
        index = opening.cursor - 1 if request.direction == 'undo' else opening.cursor
        if not 0 <= index < len(opening.actions):
            raise BackgroundFailure('REQUEST_EXPIRED')
        action = opening.actions[index]
        if action.identifier != request.origin_action_id or action.generation != request.action_generation or not action.valid:
            raise BackgroundFailure('DEPENDENCY_CHANGED')
        return action

    def derive(self, opening, current, request):
        action = self.action(opening, request)
        target = restore(current, action.delta)
        mutation = inverse_template_mutation(target, current, origin_action_id=action.identifier,
            mutation_id=request.client_mutation_id, session_id=request.proof.session_id,
            action_token=action.token + 1, kind=request.direction)
        if mutation is None:
            raise BackgroundFailure('REQUEST_EXPIRED')
        return mutation

    def prepare_replay(self, opening, request, mutation, before, after, candidate, state):
        old = self.action(opening, request)
        action = Action(old.identifier, opening.generation + 1, old.token + 1, changes(before, after), set(old.scopes))
        self._prepare(opening, mutation, action, request.direction, candidate, state, sha256(canonical(request)))

    @staticmethod
    def authorization(workspace, mutation):
        return HistoryAuthorization(workspace.project_id, workspace.document_revision, mutation.capture.session_id,
            mutation.capture.action_token, mutation.history.origin_action_id, mutation_sha256(mutation))

    @staticmethod
    def ack(opening, action_id):
        if opening is None:
            return None
        action = next((value for value in opening.actions if value.identifier == action_id), None)
        return {'actionId': action.identifier, 'generation': action.generation} if action else None
