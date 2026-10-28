"""Undo journal of one project (D109): `history.jsonl` beside `workspace.json`, local and never archived.

Each line keeps full before and after payloads of the undoable keys an edit changed: the `values()` keys of
`template_local_history` plus the order of the fact, issue and tombstone lists, which those keys do not encode. Undo
applies an action's `before`, redo its `after`; both go through the repository commit like any edit.

Every commit leaves a line with its resulting revision (a `mark` when no undoable key changed), so a journal that ends
below the workspace revision lost a line and restarts the history instead of undoing around the missing edit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path

from .storage import StorageFailure, atomic_write, private_directory
from .template_local_history import values

ACTIONS = 200
BYTES = 16 * 1024 * 1024
LOG = logging.getLogger(__name__)
# List kinds whose order the payload keys do not carry; their id order is journaled as ('order', kind).
ORDERED = (('builtin', 'records'), ('extension', 'extensions'), ('relation', 'relations'), ('tombstone', 'tombstones'))


# Revision counters move with every touch; an action that changed nothing else is no undo step (net-empty typing).
COUNTERS = frozenset({'revision', 'syncedFactRevision'})


def semantic(value):
    if isinstance(value, dict):
        return {key: semantic(child) for key, child in value.items() if key not in COUNTERS}
    if isinstance(value, list):
        return [semantic(child) for child in value]
    return value


def same(left, right):
    return left == right or semantic(left) == semantic(right)


class JournalStale(Exception):
    """The action's keys no longer hold the values the action left; applying it would overwrite later work."""


def snapshot(workspace):
    """The undoable state: every `values()` key with its full payload, plus the id order of the keyed lists."""
    if workspace.project is None:
        return {}
    result = values(workspace)
    project = workspace.project
    facts = project.facts
    for kind, name in ORDERED:
        items = getattr(facts, name)
        result[('order', kind)] = [item.record_id if kind == 'tombstone' else item.id for item in items]
    result[('order', 'issue')] = [item.id for item in project.import_issues]
    return result


def changes(before, after):
    """(before, after) payloads of the keys whose values differ; a missing key is None on its side."""
    old, new = {}, {}
    for key in before.keys() | after.keys():
        left, right = before.get(key), after.get(key)
        if left != right:
            old[key], new[key] = left, right
    return old, new


def apply(workspace, payloads):
    """The workspace with the given keys set to these payloads (None removes a key); validated."""
    target = snapshot(workspace)
    for key, payload in payloads.items():
        if payload is None:
            target.pop(key, None)
        else:
            target[key] = payload
    return rebuild(workspace, target)


def _ordered(target, kind, current):
    items = {identifier: value for (name, identifier), value in target.items() if name == kind}
    order = target.get(('order', kind), current)
    known = set(order)
    return [items[identifier] for identifier in order if identifier in items] + [
        value for identifier, value in items.items() if identifier not in known]


def rebuild(workspace, target):
    from .rich_dependencies import placements
    from .template_anchors import coverage_addresses
    project = workspace.project
    data = workspace.model_dump(mode='json', by_alias=True)
    if project.template_operations:
        # Loaded import records are not part of a dump (D104); keep them.
        data['project']['templateOperations'] = [value.model_dump(mode='json', by_alias=True) for value in project.template_operations]
    facts = data['project']['facts']
    for kind, name in ORDERED:
        current = [item.record_id if kind == 'tombstone' else item.id for item in getattr(project.facts, name)]
        facts[name] = _ordered(target, kind, current)
    facts['builtinManualScopes'] = {identifier: value for (kind, identifier), value in target.items() if kind == 'builtin_scope'}
    live = {record['id'] for record in facts['records']}
    live.update(record['id'] for record in facts['extensions'] if record['active'])
    facts['tombstones'] = [value for value in facts['tombstones'] if value['recordId'] not in live]
    data['project']['importIssues'] = _ordered(target, 'issue', [item.id for item in project.import_issues])
    coverage = data['project']['importCoverage']
    for address, row in zip(coverage_addresses(project), coverage, strict=True):
        anchor = target.get(('coverage_anchor', address))
        if anchor is None:
            raise JournalStale('coverage anchor missing')
        row['blockIds'] = list(anchor['blockIds'])
    blocks = {identifier: value for (kind, identifier), value in target.items() if kind == 'block'}
    positions = {identifier: value for (kind, identifier), value in target.items() if kind == 'placement'}
    mounted = set()

    def children(parent, ancestors=()):
        selected = {identifier: value for identifier, value in positions.items() if value[0] == parent}
        following = {}
        for identifier, (_owner, previous, _record) in selected.items():
            if previous in following or previous is not None and previous not in selected:
                raise JournalStale('block placement chain broken')
            following[previous] = identifier
        output, previous = [], None
        while previous in following:
            identifier = following[previous]
            if identifier in mounted or identifier in ancestors or identifier not in blocks:
                raise JournalStale('block placement cycle or missing block')
            mounted.add(identifier)
            value = dict(blocks[identifier])
            value['children'] = children(identifier, (*ancestors, identifier))
            output.append(value)
            previous = identifier
        if len(output) != len(selected):
            raise JournalStale('block placement unreachable')
        return output

    for region in data['project']['document']['regions']:
        region['blocks'] = children(region['id'])
    if mounted != blocks.keys():
        raise JournalStale('block without placement')
    rows = {identifier: value for (kind, identifier), value in target.items() if kind == 'sync'}
    after = {identifier: value['afterSyncId'] for (kind, identifier), value in target.items() if kind == 'sync_placement'}
    ordered, previous = [], None
    following = {}
    for identifier, predecessor in after.items():
        if predecessor in following:
            raise JournalStale('sync order broken')
        following[predecessor] = identifier
    while previous in following:
        previous = following[previous]
        if previous not in rows:
            raise JournalStale('sync row missing')
        ordered.append(rows[previous])
    if len(ordered) != len(rows):
        raise JournalStale('sync order unreachable')
    data['syncRecords'] = ordered
    rebuilt = type(workspace).model_validate(data)
    # The rebuilt tree derives each placement again; a difference means the target payloads were incoherent.
    if {key: list(value) for key, value in placements(rebuilt.project.document).items()} != {
            identifier: list(value) for identifier, value in positions.items()}:
        raise JournalStale('placements differ after rebuild')
    return rebuilt


def _encode(payloads):
    return [[kind, identifier, value] for (kind, identifier), value in sorted(payloads.items(), key=lambda item: item[0])]


def _decode(entries):
    return {(kind, identifier): value for kind, identifier, value in entries}


def _size(action):
    return len(json.dumps([_encode(action.before), _encode(action.after)], ensure_ascii=False, separators=(',', ':')))


@dataclass
class Action:
    action_id: str
    seq: int
    before: dict
    after: dict
    bytes: int = 0

    @property
    def empty(self):
        return not self.before and not self.after


@dataclass
class ProjectJournal:
    path: Path
    undo: list = field(default_factory=list)
    redo: list = field(default_factory=list)
    seq: int = 0
    # The top undo action may still take lines of the same action id while nothing else was written after it.
    open_seq: int | None = None
    lines: int = 0
    gap: bool = False
    # The revision after the last line; None when no line names it (an empty or older journal).
    revision: int | None = None

    @classmethod
    def load(cls, path, *, revision=None, compact=True):
        """The journal of a project whose workspace file is at `revision`; a journal behind or ahead of it restarts."""
        journal = cls(Path(path))
        try:
            journal._load()
        except (OSError, StorageFailure) as error:
            LOG.warning('journal unreadable, history starts empty: %s', type(error).__name__)
            journal.undo, journal.redo, journal.open_seq = [], [], None
        if revision is not None and journal.revision is not None and journal.revision != revision:
            LOG.warning('journal ends at revision %s, the project file at %s; history restarts', journal.revision, revision)
            journal.barrier(revision_after=revision, reason='journal_behind')
        if compact and journal.oversized():
            journal.compact(revision=revision)
        return journal

    def oversized(self, factor=2):
        return self.lines > factor * ACTIONS or self._file_bytes() > 2 * BYTES

    def _file_bytes(self):
        try:
            return os.stat(self.path, follow_symlinks=False).st_size
        except FileNotFoundError:
            return 0

    def _load(self):
        if not self.path.exists() and not self.path.is_symlink():
            return
        if self.path.is_symlink():
            raise StorageFailure('UNSAFE_STORAGE')
        raw = self.path.read_bytes()
        offset = 0
        for line in raw.splitlines(keepends=True):
            try:
                if not line.endswith(b'\n'):
                    raise ValueError('torn line')
                self._replay(json.loads(line))
            except (ValueError, KeyError, TypeError, JournalStale):
                LOG.warning('journal tail truncated at byte %d', offset)
                os.truncate(self.path, offset)
                break
            offset += len(line)
            self.lines += 1

    def _replay(self, line):
        kind = line['kind']
        if kind == 'edit':
            self._edit(line['actionId'], line['seq'], _decode(line['before']), _decode(line['after']))
        elif kind in {'undo', 'redo'}:
            source, target = (self.undo, self.redo) if kind == 'undo' else (self.redo, self.undo)
            if not source or source[-1].action_id != line['originActionId'] or source[-1].seq != line['seq']:
                raise JournalStale('history line does not name the stack top')
            target.append(source.pop())
            self.open_seq = None
        elif kind == 'barrier':
            self.undo, self.redo, self.open_seq = [], [], None
        elif kind != 'mark':
            raise ValueError('unknown journal line')
        self.seq = max(self.seq, line.get('seq', 0))
        if line.get('revisionAfter') is not None:
            self.revision = line['revisionAfter']

    def _edit(self, action_id, seq, before, after):
        top = self.undo[-1] if self.undo else None
        if top is not None and top.seq == seq and self.open_seq == seq and top.action_id == action_id:
            for key, value in before.items():
                top.before.setdefault(key, value)
            top.after.update(after)
            if all(same(top.before[key], top.after.get(key)) for key in top.before):
                top.before, top.after = {}, {}
            if top.empty:
                self.undo.pop()
                self.open_seq = None
                return
            top.bytes = _size(top)
        else:
            action = Action(action_id, seq, dict(before), dict(after))
            action.bytes = _size(action)
            self.undo.append(action)
            self.open_seq = seq
        self.redo = []
        self._bound()

    def _bound(self):
        while len(self.undo) > ACTIONS or self.undo and sum(action.bytes for action in [*self.undo, *self.redo]) > BYTES:
            self.undo.pop(0)

    def state(self):
        def describe(stack):
            return {'actionId': stack[-1].action_id, 'kind': 'edit'} if stack else None
        return {'undo': describe(self.undo), 'redo': describe(self.redo)}

    def top(self, direction):
        stack = self.undo if direction == 'undo' else self.redo
        return stack[-1] if stack else None

    def target(self, direction, current):
        """Payloads that undo or redo the top action, after checking that its keys still hold what it left."""
        action = self.top(direction)
        if action is None:
            raise JournalStale('nothing to ' + direction)
        expected, payloads = (action.after, action.before) if direction == 'undo' else (action.before, action.after)
        if any(not same(current.get(key), value) for key, value in expected.items()):
            raise JournalStale('history keys changed since the action')
        return action, payloads

    def _append(self, line):
        """Write one line and fsync; a failure is a logged gap and the history restarts at the next line."""
        lines = [line]
        if self.gap and line['kind'] != 'barrier':
            # The cleared history is written down first; otherwise a reload would bring the older actions back.
            lines.insert(0, {'kind': 'barrier', 'seq': self.seq, 'revisionAfter': line.get('revisionBefore'),
                'at': self._now(), 'reason': 'gap'})
        try:
            private_directory(self.path.parent)
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            try:
                os.write(descriptor, b''.join(json.dumps(item, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
                    + b'\n' for item in lines))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except (OSError, StorageFailure) as error:
            LOG.warning('journal gap: %s', type(error).__name__)
            self.lost()
            return False
        self.lines += len(lines)
        self.gap = False
        if line.get('revisionAfter') is not None:
            self.revision = line['revisionAfter']
        return True

    def lost(self):
        """A line could not be written: the history restarts, and the next line is preceded by a barrier."""
        self.gap = True
        self.undo, self.redo, self.open_seq = [], [], None

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def record_edit(self, *, action_id, client_mutation_id, revision_before, revision_after, before, after):
        """Journal an edit from full snapshots; an edit that changed no undoable key leaves only a mark."""
        old, new = changes(before, after)
        if all(same(old[key], new[key]) for key in old):
            self.mark(revision_before=revision_before, revision_after=revision_after)
            return False
        top = self.undo[-1] if self.undo else None
        seq = top.seq if top is not None and self.open_seq == top.seq and top.action_id == action_id else self.seq + 1
        line = {'kind': 'edit', 'seq': seq, 'actionId': action_id, 'clientMutationId': client_mutation_id,
            'revisionBefore': revision_before, 'revisionAfter': revision_after, 'at': self._now(),
            'before': _encode(old), 'after': _encode(new)}
        if not self._append(line):
            return False
        self.seq = max(self.seq, seq)
        self._edit(action_id, seq, old, new)
        return True

    def record_history(self, *, direction, action, client_mutation_id, revision_before, revision_after):
        before, after = (action.after, action.before) if direction == 'undo' else (action.before, action.after)
        line = {'kind': direction, 'seq': action.seq, 'originActionId': action.action_id,
            'clientMutationId': client_mutation_id, 'revisionBefore': revision_before, 'revisionAfter': revision_after,
            'at': self._now(), 'before': _encode(before), 'after': _encode(after)}
        if not self._append(line):
            return False
        self._replay({'kind': direction, 'originActionId': action.action_id, 'seq': action.seq})
        return True

    def barrier(self, *, revision_after, reason):
        self._append({'kind': 'barrier', 'seq': self.seq, 'revisionAfter': revision_after, 'at': self._now(), 'reason': reason})
        self.undo, self.redo, self.open_seq = [], [], None

    def mark(self, *, revision_before=None, revision_after):
        """A commit without undoable changes (an export record, a rename): only its revision is written, and only
        while there is history a missing line could misplace."""
        if not self.undo and not self.redo and not self.gap:
            return True
        return self._append({'kind': 'mark', 'seq': self.seq, 'revisionBefore': revision_before,
            'revisionAfter': revision_after, 'at': self._now()})

    def compact(self, revision=None):
        """Rewrite the file as the retained actions: undo stack as edits, then the redo list as edits and undos.
        The last line names `revision`, the workspace revision the retained actions end at."""
        lines = []
        def edit(action):
            return {'kind': 'edit', 'seq': action.seq, 'actionId': action.action_id, 'clientMutationId': None,
                'revisionBefore': None, 'revisionAfter': None, 'at': self._now(),
                'before': _encode(action.before), 'after': _encode(action.after)}
        for action in self.undo:
            lines.append(edit(action))
        for action in reversed(self.redo):
            lines.append(edit(action))
        for action in self.redo:
            lines.append({'kind': 'undo', 'seq': action.seq, 'originActionId': action.action_id, 'clientMutationId': None,
                'revisionBefore': None, 'revisionAfter': None, 'at': self._now(), 'before': [], 'after': []})
        if not lines and not self.path.exists():
            return
        if revision is not None:
            if lines:
                lines[-1]['revisionAfter'] = revision
            else:
                lines.append({'kind': 'mark', 'seq': self.seq, 'revisionBefore': None, 'revisionAfter': revision,
                    'at': self._now()})
        try:
            atomic_write(self.path, b''.join(json.dumps(line, ensure_ascii=False, separators=(',', ':')).encode('utf-8') + b'\n'
                for line in lines))
            self.lines = len(lines)
            self.gap = False
            if revision is not None:
                self.revision = revision
            # A redo action's edit line must not merge into the undo stack top on the next load.
            self.open_seq = None
        except (OSError, StorageFailure) as error:
            LOG.warning('journal compaction failed: %s', type(error).__name__)

    def referenced(self, kind):
        """Ids of one payload kind that retained actions can bring back (images kept for undo of a delete)."""
        found = set()
        for action in [*self.undo, *self.redo]:
            for side in (action.before, action.after):
                for (name, identifier), value in side.items():
                    if name == kind and value is not None:
                        found.add(identifier)
        return found
