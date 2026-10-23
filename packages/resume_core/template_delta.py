"""Project validated previews into compact structural patches and metadata."""

from .background_limits import LIMITS
from .background_store import BackgroundFailure
from .canonical_patch import apply_patch, build_patch
from .models.canonical_patch import CanonicalPatchV1
from .models.template_delta import TemplatePreparedEditDeltaV1
from .rich_identity import resume_identity
from .template_preparation import prepare_edit
from .templates.compiler import canonical, sha256
from .templates.presentation import presentation_matches, snapshot_identity


def plan_patch(old, new, limit=1000):
    """The editor plan patch; past the step bound the changed top-level parts go whole."""
    steps = build_patch(old, new)
    if len(steps) > limit:
        steps = CanonicalPatchV1(schemaVersion=1, steps=[{'kind': 'set', 'pointer': '/' + key,
            'valueWire': canonical(new[key]).decode()} for key in sorted(new) if canonical(new[key]) != canonical(old.get(key))]).steps
    return {'beforeHash': sha256(canonical(old)), 'afterHash': sha256(canonical(new)), 'steps': steps}


def prepared_delta(base, prepared):
    before, after = base.workspace, prepared.preview.workspace
    if (base.snapshot != prepared.base_snapshot or snapshot_identity(before) != prepared.base_snapshot
            or snapshot_identity(after) != prepared.preview.snapshot or base.presentation is None
            or prepared.preview.presentation is None or before.project is None or after.project is None
            or canonical(before.project.template_package) != canonical(after.project.template_package)
            or not presentation_matches(base.presentation.model_dump(mode='json', by_alias=True), before)
            or not presentation_matches(prepared.preview.presentation.model_dump(mode='json', by_alias=True), after)):
        raise ValueError('compact preparation needs its exact captured base and result')
    if prepared.mutation is None:
        if (canonical(before) != canonical(after) or base.identity != prepared.preview.identity
                or base.generation != prepared.preview.generation):
            raise ValueError('no-op preparation changes its response metadata')
    elif prepared.preview.identity != resume_identity(after):
        raise ValueError('prepared identity does not come from the result workspace')
    old, new = before.model_dump(mode='json', by_alias=True), after.model_dump(mode='json', by_alias=True)
    old_refs, new_refs = base.presentation.blocks, prepared.preview.presentation.blocks
    old_wire = canonical({key: value.model_dump(mode='json', by_alias=True) for key, value in old_refs.items()})
    new_wire = canonical({key: value.model_dump(mode='json', by_alias=True) for key, value in new_refs.items()})
    patch = build_patch(old, new)
    if canonical(apply_patch(old, patch)) != canonical(new):
        raise ValueError('compact preparation patch differs from preview')
    editor = None
    if base.presentation.editor is not None and prepared.preview.presentation.editor is not None:
        editor = plan_patch(base.presentation.editor.model_dump(mode='json', by_alias=True),
            prepared.preview.presentation.editor.model_dump(mode='json', by_alias=True))
    result = TemplatePreparedEditDeltaV1(schemaVersion=1, clientMutationId=prepared.client_mutation_id,
        baseSnapshot=prepared.base_snapshot, baseWorkspaceSha256=sha256(canonical(old)),
        resultSnapshot=prepared.preview.snapshot, resultWorkspaceSha256=sha256(canonical(new)),
        capture=prepared.capture, requestHash=prepared.request_hash, createdIds=prepared.created_ids,
        mutationWire=prepared.mutation.model_dump_json(by_alias=True) if prepared.mutation is not None else None,
        workspacePatch=patch, presentationPatch={'beforeHash': sha256(old_wire), 'afterHash': sha256(new_wire),
            'set': {key: value for key, value in new_refs.items() if key not in old_refs or value != old_refs[key]},
            'remove': sorted(old_refs.keys() - new_refs.keys()), **({'editor': editor} if editor is not None else {})},
        resultIdentity=prepared.preview.identity, resultGeneration=prepared.preview.generation)
    if len(canonical(result)) > LIMITS.proposal_bytes:
        raise BackgroundFailure('JOB_STORAGE_FULL')
    return result


def prepare_text_delta(response, request, proof, *, clipboard=None):
    return prepared_delta(response, prepare_edit(response, request, proof, clipboard=clipboard))
