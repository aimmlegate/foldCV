"""A repository with one synthetic project and literal text edits built with the domain mutation code."""

import hashlib

from packages.resume_core.project_repository import ProjectRepository
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.templates.compiler import canonical
from tests.templates.storage_fixtures import workspace as papers
from tests.templates.test_transactions import request

PROJECT = 'template-project'


def repository(root, *, clock=None):
    value, sources = papers()
    repo = ProjectRepository(root / 'data', **({'clock': clock} if clock else {}))
    repo.create(value, blobs=[('sources', key, raw, hashlib.sha256(raw).hexdigest()) for key, raw in sources.items()])
    return repo


def text_of(workspace, index=0):
    return ''.join(span.text for span in workspace.project.document.regions[2].blocks[index].content)


def typing(text, *, identifier, action=None, index=0):
    """A build that replaces the whole text of one main-region block with literal text."""
    def build(workspace):
        block = workspace.project.document.regions[2].blocks[index]
        length = sum(len(span.text.encode('utf-16-le')) // 2 for span in block.content)
        mutation = request(workspace, [{'kind': 'replace_inline_range', 'blockId': block.id, 'beforeRevision': block.revision,
            'cellId': None, 'field': 'content', 'start': 0, 'end': length,
            'content': [{'type': 'text', 'text': text, 'styles': {}}]}], identifier)
        mutation.action_id = mutation.capture.action_id = action or identifier
        return apply_rich_mutation(workspace, mutation)[0]
    return build


def edit(repo, text, *, identifier, action=None, index=0, base=None):
    return repo.mutate(PROJECT, base_revision=repo.read(PROJECT).project_revision if base is None else base,
        client_mutation_id=identifier, request_sha256=hashlib.sha256(canonical([identifier, text, index])).hexdigest(),
        action_id=action or identifier, kind='edit', build=typing(text, identifier=identifier, action=action, index=index))


def history(repo, direction, *, identifier, expected=None):
    return repo.history(PROJECT, direction=direction, base_revision=repo.read(PROJECT).project_revision,
        client_mutation_id=identifier, request_sha256=hashlib.sha256(identifier.encode()).hexdigest(),
        expected_action_id=expected)
