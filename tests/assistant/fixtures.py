"""Synthetic V7 projects for the assistant: mixed literal and field text, a table cell and an image caption."""

from io import BytesIO

from PIL import Image

from packages.resume_core.models.template_document import TemplateImageBlock, TemplateTableBlock
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.rich_images import normalize_image
from tests.templates.storage_fixtures import workspace as papers


def literal(text, ref):
    return {'type': 'text', 'text': text, 'styles': {}, 'presentation': ref}


def field(key, cell, binding, occurrence, text, ref):
    return {'type': 'fact_field', 'bindingId': binding, 'bindingRootId': occurrence, 'occurrenceId': occurrence,
        'recordId': 'paper-a', 'fieldKey': key, 'cellId': cell, 'text': text, 'styles': {}, 'syncedFactRevision': 1,
        'complete': True, 'presentation': ref}


def joined():
    """'By Shared title / Journal North.': literals around two field occurrences of paper-a."""
    before, sources = papers()
    data = before.model_dump(by_alias=True)
    block = data['project']['document']['regions'][2]['blocks'][0]
    ref = block['content'][0]['presentation']
    block['content'] = [literal('By ', ref), field('title', 'a-title', 'fragment-paper-a', 'occurrence-paper-a', 'Shared title', ref),
        literal(' / ', ref), field('journal', 'a-journal', 'binding-journal', 'occurrence-journal', 'Journal North', ref),
        literal('.', ref)]
    return WorkspaceV7.model_validate(data), sources


def tabled():
    """The first block as a one-cell table holding plain text, and an image with a caption after it."""
    before, sources = papers()
    old = before.project.document.regions[2].blocks[0]
    ref = old.presentation
    before.project.document.regions[2].blocks[0] = TemplateTableBlock(type='table', id=old.id, revision=old.revision,
        props={}, children=[], provenance=[], presentation=ref, content={'rows': [{'id': 'row', 'cells': [
            {'id': 'cell-a', 'revision': 1, 'content': [literal('Cell text', old.content[0].presentation)]}]}],
            'columnWidths': [None], 'headerRows': 0, 'headerCols': 0})
    buffer = BytesIO()
    Image.new('RGB', (16, 8), 'red').save(buffer, format='PNG')
    asset, _blob = normalize_image(buffer.getvalue(), 'synthetic-image')
    before.project.assets = [asset]
    before.project.document.regions[2].blocks.append(TemplateImageBlock(type='image', id='image-block', revision=1,
        children=[], provenance=[], content=None, presentation=ref, props={'assetId': asset.id, 'alt': 'Synthetic image',
            'caption': [literal('Old caption', old.content[0].presentation)], 'width': 160, 'height': 80, 'alignment': 'left'}))
    return WorkspaceV7.model_validate(before.model_dump(by_alias=True)), sources
