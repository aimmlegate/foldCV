"""Capture exact classified fragments without retaining their source workspace."""

from types import SimpleNamespace

from .models.template_clipboard import ClassifiedClipboardBlocks,ClassifiedClipboardInline,RetainedTemplateClipboardV1
from .models.template_document import BoundLink,ManualScopeSpan
from .models.rich_document import FactFieldSpan,Hyperlink
from .rich_fields import inline_groups
from .rich_mutations import locate
from .template_authoring import citation_spans,classify_blocks,classify_fragment
from .template_clipboard_witnesses import field_witness,fingerprint,scope_witness,source_witness,verify_witnesses
from .template_identity import capture_span
from .templates.presentation import snapshot_identity,validate_presentation
from .templates.store import verify_package


SUPPORTED_CAPTURE_BLOCKS=frozenset({'paragraph','heading','bullet_list','numbered_list'})


def normalize_inline_presentation(content,block):
    def visit(part,inherited):
        explicit=getattr(part,'presentation',None)
        effective=explicit or inherited
        if explicit is None and effective is not None:
            part.presentation=effective.model_copy(deep=True)
            part.presentation.overrides.alignment=None
        styles=getattr(part,'styles',None)
        if styles is not None:
            for key in ['text_color','background_color']:
                value=getattr(block.props,key,'default')
                if getattr(styles,key)=='default' and value!='default':setattr(styles,key,value)
        if isinstance(part,(Hyperlink,BoundLink)):
            for child in part.content:visit(child,effective)
    result=[part.model_copy(deep=True) for part in content]
    for part in result:visit(part,block.presentation)
    return result


def evidence_span(project,evidence):
    sources=[value for value in project.sources if value.id==evidence.source_id and value.revision==evidence.source_revision]
    units=[unit for source in sources for unit in source.units
        if unit.id==evidence.unit_id and unit.revision==evidence.unit_revision]
    if len(sources)!=1 or len(units)!=1 or evidence.text not in units[0].text:
        raise ValueError('clipboard provenance has no exact retained source')
    unit=units[0];start=unit.text.find(evidence.text)
    if unit.text.find(evidence.text,start+1)>=0:return capture_span(sources[0],unit)
    return capture_span(sources[0],unit,start,start+len(evidence.text))


def block_citations(project,block):
    result={}
    for provenance in block.provenance:
        if provenance.kind=='field_binding':
            spans=citation_spans(project,provenance)
        else:spans=[evidence_span(project,value) for value in getattr(provenance,'evidence',[])]
        for span in spans:result[fingerprint(span)]=span
    return list(result.values())


def selected_witnesses(project,payload):
    fields,scopes,sources={},{},{}
    def cite(span):
        witness=source_witness(project,span);sources[witness.span_hash]=witness
    def field(reference):
        witness=field_witness(project,reference.record_id,reference.field_key,getattr(reference,'cell_id',None))
        previous=fields.setdefault(witness.cell_id,witness)
        if previous!=witness:raise ValueError('clipboard cell has inconsistent witnesses')
        for span in citation_spans(project,reference):cite(span)
    def inline(part):
        if isinstance(part,ManualScopeSpan):
            scopes[part.scope_id]=scope_witness(project,part.scope_id)
            for span in citation_spans(project,part):cite(span)
        elif isinstance(part,FactFieldSpan):field(part)
        if isinstance(part,BoundLink):
            for reference in [part.label_binding,part.url_binding]:
                if reference is not None:field(reference)
        for span in getattr(part,'citations',[]):cite(span)
        if isinstance(part,(Hyperlink,BoundLink)):
            for child in part.content:inline(child)
    if payload.kind=='inline':
        for part in payload.content:inline(part)
    else:
        for block in payload.blocks:
            for provenance in block.provenance:
                if provenance.kind=='field_binding':field(provenance)
            for span in block_citations(project,block):cite(span)
            for _container,group in inline_groups(block):
                for part in group:inline(part)
    return ([fields[key] for key in sorted(fields)]+[scopes[key] for key in sorted(scopes)]
        +[sources[key] for key in sorted(sources)])


def capture_clipboard(workspace,capture,request_hash):
    if workspace.schema_version!=7 or workspace.project is None or capture.source_snapshot!=snapshot_identity(workspace):
        raise ValueError('clipboard capture requires its exact current snapshot')
    project=workspace.project;verify_package(project.template_package)
    def target(identifier,revision):
        found=locate(project.document,identifier)
        if found is None or found[0][found[1]].revision!=revision:raise ValueError('clipboard source block is stale')
        block=found[0][found[1]]
        if block.type not in SUPPORTED_CAPTURE_BLOCKS or block.children:
            raise ValueError('clipboard capture structure is unsupported')
        return block
    selection=capture.selection
    if selection.kind=='range':
        selected=selection.range
        if selected.cell_id is not None or selected.field!='content':raise ValueError('clipboard range is unsupported')
        block=target(selected.block_id,selected.before_revision)
        copied=classify_fragment(project,block,selected.start,selected.end)
        content=normalize_inline_presentation(copied.content,copied)
        citations=block_citations(project,copied)
        def attach(part):
            if isinstance(part,(Hyperlink,BoundLink)):
                return bool(part.content) and attach(part.content[0])
            for span in citations:
                if span not in part.citations:part.citations.append(span.model_copy(deep=True))
            return True
        if citations and content:attach(content[0])
        payload=ClassifiedClipboardInline(kind='inline',content=content)
        copied.content=content;validation_blocks=[copied]
    else:
        order={block.id:index for index,block in enumerate(project.document.blocks())}
        blocks=[target(item.block_id,item.before_revision) for item in selection.blocks]
        blocks.sort(key=lambda block:order[block.id])
        validation_blocks=classify_blocks(project,blocks)
        payload=ClassifiedClipboardBlocks(kind='blocks',blocks=validation_blocks)
    validate_presentation(SimpleNamespace(blocks=lambda:iter(validation_blocks)),project.template_package)
    witnesses=selected_witnesses(project,payload)
    package=fingerprint(project.template_package)
    verify_witnesses(project,witnesses,package)
    return RetainedTemplateClipboardV1(capture=capture.model_copy(deep=True),requestHash=request_hash,
        packageFingerprint=package,payload=payload,witnesses=witnesses)
