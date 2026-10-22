"""Authored v2 rich trees preserve presentation and independent link bindings."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .contracts import Id, Wire, _unique
from .rich_document import (BlockIdentity, ParagraphBlock, HeadingBlock, BulletBlock, NumberedBlock,
    ChecklistBlock, ToggleBlock, QuoteBlock, CodeBlock, DividerBlock, TableBlock, ImageBlock,
    SectionBlock, FactFieldSpan, StyledText, Hyperlink, ImageProps, TableCell, TableRow, TableContent,
    RichRegion, RichDocumentV1)
from ..templates.models import AuthoredPresentation
from .template_facts import SourceSpan


class PresentedText(StyledText):
    presentation: AuthoredPresentation | None = None
    citations: list[SourceSpan] = Field(default_factory=list, exclude_if=lambda value: not value)


class ManualScopeSpan(StyledText):
    type: Literal['manual_scope']
    scope_id: Id
    occurrence_id: Id
    fragment_id: Id
    presentation: AuthoredPresentation | None
    citations: list[SourceSpan] = Field(default_factory=list, exclude_if=lambda value: not value)


class PresentedHyperlink(Hyperlink):
    content: list[PresentedText]
    presentation: AuthoredPresentation | None = None


class FieldRef(Wire):
    record_id: Id
    field_key: Id
    cell_id: Id
    occurrence_id: Id


class FieldOccurrence(FactFieldSpan):
    cell_id: Id | None
    occurrence_id: Id
    complete: bool
    presentation: AuthoredPresentation | None
    citations: list[SourceSpan] = Field(default_factory=list, exclude_if=lambda value: not value)

    @model_validator(mode="after")
    def occurrence_root(self):
        if self.binding_root_id != self.occurrence_id:
            raise ValueError("field occurrence/root mismatch")
        return self


class BoundLink(Wire):
    type: Literal["bound_link"]
    href: str
    content: list[PresentedText | FieldOccurrence]
    label_binding: FieldRef | None
    url_binding: FieldRef | None
    presentation: AuthoredPresentation | None

    @model_validator(mode="after")
    def binding_identity(self):
        if self.label_binding is None and self.url_binding is None:
            raise ValueError("bound link needs a label or URL field")
        return self


TemplateInline = Annotated[PresentedText | PresentedHyperlink | FieldOccurrence | BoundLink | ManualScopeSpan,
    Field(discriminator="type")]


class AuthoredBlock(BlockIdentity):
    children: list[TemplateBlock]
    presentation: AuthoredPresentation | None


class TemplateParagraphBlock(AuthoredBlock, ParagraphBlock):
    content: list[TemplateInline]


class TemplateHeadingBlock(AuthoredBlock, HeadingBlock):
    content: list[TemplateInline]


class TemplateBulletBlock(AuthoredBlock, BulletBlock):
    content: list[TemplateInline]


class TemplateNumberedBlock(AuthoredBlock, NumberedBlock):
    content: list[TemplateInline]


class TemplateChecklistBlock(AuthoredBlock, ChecklistBlock):
    content: list[TemplateInline]


class TemplateToggleBlock(AuthoredBlock, ToggleBlock):
    content: list[TemplateInline]


class TemplateQuoteBlock(AuthoredBlock, QuoteBlock):
    content: list[TemplateInline]


class TemplateCodeBlock(AuthoredBlock, CodeBlock):
    pass


class TemplateDividerBlock(AuthoredBlock, DividerBlock):
    pass


class TemplateTableCell(TableCell):
    content: list[TemplateInline]


class TemplateTableRow(TableRow):
    cells: list[TemplateTableCell]


class TemplateTableContent(TableContent):
    rows: list[TemplateTableRow]


class TemplateTableBlock(AuthoredBlock, TableBlock):
    content: TemplateTableContent


class TemplateImageProps(ImageProps):
    caption: list[TemplateInline]


class TemplateImageBlock(AuthoredBlock, ImageBlock):
    props: TemplateImageProps


class TemplateSectionBlock(AuthoredBlock, SectionBlock):
    content: list[TemplateInline]


TemplateBlock = Annotated[TemplateParagraphBlock | TemplateHeadingBlock | TemplateBulletBlock |
    TemplateNumberedBlock | TemplateChecklistBlock | TemplateToggleBlock | TemplateQuoteBlock |
    TemplateCodeBlock | TemplateDividerBlock | TemplateTableBlock | TemplateImageBlock | TemplateSectionBlock,
    Field(discriminator="type")]

for _model in (AuthoredBlock,TemplateParagraphBlock,TemplateHeadingBlock,TemplateBulletBlock,TemplateNumberedBlock,
    TemplateChecklistBlock,TemplateToggleBlock,TemplateQuoteBlock,TemplateCodeBlock,TemplateDividerBlock,
    TemplateTableBlock,TemplateImageBlock,TemplateSectionBlock):
    _model.model_rebuild()


class TemplateRegion(RichRegion):
    blocks: list[TemplateBlock]


class RichDocumentV2(RichDocumentV1):
    schema_version: Literal[2]
    regions: list[TemplateRegion] = Field(min_length=3,max_length=3)

    @model_validator(mode="after")
    def bound_identity(self):
        identifiers=[]
        roots = {}
        def reference(record_id, field_key, cell_id, root):
            identity = (record_id, field_key, cell_id)
            if root in roots and roots[root] != identity:
                raise ValueError('occurrence root refers to different semantic cells')
            roots[root] = identity
        for block in self.blocks():
            groups=[block.content] if isinstance(block.content,list) else [cell.content for row in block.content.rows for cell in row.cells] if isinstance(block,TableBlock) else []
            if isinstance(block,ImageBlock): groups.append(block.props.caption)
            for content in groups:
                for span in content:
                    if isinstance(span,BoundLink):
                        for bound in (span.label_binding, span.url_binding):
                            if bound is not None:
                                reference(bound.record_id, bound.field_key, bound.cell_id, bound.occurrence_id)
                        for child in span.content:
                            if isinstance(child, FieldOccurrence):
                                identifiers.append(child.binding_id)
                                reference(child.record_id, child.field_key, child.cell_id, child.occurrence_id)
                                label = span.label_binding or span.url_binding
                                if label is None or (child.record_id, child.field_key, child.cell_id, child.occurrence_id) != (
                                        label.record_id, label.field_key, label.cell_id, label.occurrence_id):
                                    raise ValueError('link label span disagrees with its field binding')
                    elif isinstance(span,FieldOccurrence):
                        identifiers.append(span.binding_id)
                        reference(span.record_id, span.field_key, span.cell_id, span.occurrence_id)
                    elif isinstance(span, ManualScopeSpan):
                        identifiers.append(span.fragment_id)
                        identity = ('manual_scope', span.scope_id)
                        if span.occurrence_id in roots and roots[span.occurrence_id] != identity:
                            raise ValueError('manual occurrence root refers to another scope or field')
                        roots[span.occurrence_id] = identity
        _unique(identifiers,"authored field fragment")
        return self
