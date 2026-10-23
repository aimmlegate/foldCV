"""Selected-text rewrite for V7: generation reads verified text; only an explicit Apply edits the document."""

from .rich_mutations import locate, utf16_slice
from .template_preparation import _range_content
from .templates.presentation import snapshot_identity


def rewrite_source(workspace, request):
    """The exact selected text of one block or cell at the request's snapshot."""
    if workspace.schema_version != 7 or workspace.project is None or snapshot_identity(workspace) != request.snapshot:
        raise ValueError('rewrite snapshot is not current')
    found = locate(workspace.project.document, request.range.block_id)
    if found is None:
        raise ValueError('rewrite block missing')
    _content, text = _range_content(found[0][found[1]], request.range)
    return utf16_slice(text, request.range.start, request.range.end)
