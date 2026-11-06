"""Prepare exact human text transactions without a second editor or inference."""

from ..models.template_authoring import ReplaceText, SetMarks
from .template_preparation_text import prepare_text_edit




























def prepare_edit(response, request, *, clipboard=None, occupied=None, remembered=None):
    """The prepared result of one authored operation on the exact durable response; `occupied` names the ids already
    taken (the repository session keeps them, otherwise they are collected from the workspace). `remembered`: the
    Focus icons the user chose before, which a row added from the facts panel takes (D122)."""
    if isinstance(request.operations[0], (ReplaceText, SetMarks)):
        return prepare_text_edit(response, request, occupied=occupied)
    from ..models.template_authoring import PasteInline
    if isinstance(request.operations[0], PasteInline):
        from .template_preparation_paste import prepare_inline_paste
        return prepare_inline_paste(response, request, clipboard=clipboard, occupied=occupied)
    from ..models.template_authoring import BuiltinPanel, DeleteEntity
    if isinstance(request.operations[0], (BuiltinPanel, DeleteEntity)):
        from .template_preparation_panel import prepare_panel_edit
        return prepare_panel_edit(response, request, occupied=occupied, remembered=remembered)
    from ..models.template_authoring import ResolveTemplateSync
    if isinstance(request.operations[0], ResolveTemplateSync):
        from .template_preparation_sync import prepare_sync_resolution
        return prepare_sync_resolution(response, request, occupied=occupied)
    from ..models.template_authoring import SetLinkTarget
    if isinstance(request.operations[0], SetLinkTarget):
        from .template_preparation_link import prepare_link_target
        return prepare_link_target(response, request, occupied=occupied)
    from .template_preparation_structure import prepare_structure_edit
    return prepare_structure_edit(response, request, clipboard=clipboard, occupied=occupied)
