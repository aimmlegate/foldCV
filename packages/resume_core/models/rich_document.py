"""Versioned rich tree. Legacy document types keep their original meaning."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field, model_validator

from .contracts import Id, Revision, Wire, _unique
from .recovery import EvidenceSpan

Color = Annotated[str, Field(pattern=r"^(default|#[a-fA-F0-9]{6})$")]
Alignment = Literal["left", "center", "right", "justify"]


class InlineStyles(Wire):
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    code: bool = False
    text_color: Color = "default"
    background_color: Color = "default"


class StyledText(Wire):
    type: Literal["text"]
    text: str
    styles: InlineStyles


class Hyperlink(Wire):
    type: Literal["link"]
    href: str = Field(min_length=1)
    content: list[StyledText]


class FactFieldSpan(Wire):
    type: Literal["fact_field"]
    binding_id: Id
    record_id: Id
    field_key: Id
    text: str
    styles: InlineStyles
    synced_fact_revision: Revision


RichInline = Annotated[Union[StyledText, Hyperlink, FactFieldSpan], Field(discriminator="type")]


class NarrativeCitation(Wire):
    kind: Literal["citation"]
    id: Id
    record_id: Id
    field_keys: list[Id]
    evidence: list[EvidenceSpan]


class FieldBinding(Wire):
    kind: Literal["field_binding"]
    id: Id
    record_id: Id
    field_key: Id


class WorkingOwnership(Wire):
    kind: Literal["working_owner"]
    id: Id
    record_id: Id


class SourceWitness(Wire):
    kind: Literal["source"]
    id: Id
    evidence: list[EvidenceSpan] = Field(min_length=1)


Provenance = Annotated[Union[NarrativeCitation, FieldBinding, WorkingOwnership, SourceWitness], Field(discriminator="kind")]


class ParagraphProps(Wire):
    alignment: Alignment = "left"
    text_color: Color = "default"
    background_color: Color = "default"


class HeadingProps(ParagraphProps):
    level: Literal[1, 2, 3]


class NumberedProps(ParagraphProps):
    start: int | None = Field(default=None, ge=1)


class ChecklistProps(ParagraphProps):
    checked: bool


class CodeProps(Wire):
    language: str
    background_color: Color = "default"


class EmptyProps(Wire):
    pass


class SectionProps(ParagraphProps):
    record_id: Id | None
    presentation: Literal["standard", "focus"] = "standard"


class ImageProps(Wire):
    asset_id: Id
    alt: str
    caption: list[RichInline]
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    alignment: Literal["left", "center", "right"]


class TableCell(Wire):
    id: Id
    revision: Revision
    content: list[RichInline]
    background_color: Color = "default"
    alignment: Alignment = "left"
    colspan: int = Field(default=1, ge=1)
    rowspan: int = Field(default=1, ge=1)


class TableRow(Wire):
    id: Id
    cells: list[TableCell]


class TableContent(Wire):
    rows: list[TableRow] = Field(min_length=1)
    column_widths: list[float | None] = Field(min_length=1)
    header_rows: int = Field(ge=0)
    header_cols: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def valid_table(self) -> TableContent:
        if self.header_rows > len(self.rows):
            raise ValueError("table header exceeds rows")
        if self.header_cols > len(self.column_widths):
            raise ValueError("table header exceeds columns")
        if any(width is not None and width <= 0 for width in self.column_widths):
            raise ValueError("invalid table column width")
        active, expires, coverage, cached = {}, {}, 0, None
        for r, row in enumerate(self.rows):
            for column in expires.pop(r, []):
                end = active.pop(column)
                coverage -= end - column
                cached = None
            if cached is None:
                cached = []
                for start, end in sorted(active.items()):
                    if cached and cached[-1][1] == start:
                        cached[-1] = (cached[-1][0], end)
                    else:
                        cached.append((start, end))
            column, index, current, additions = 0, 0, coverage, []
            for cell in row.cells:
                while index < len(cached) and cached[index][0] <= column:
                    column = max(column, cached[index][1]); index += 1
                if r + cell.rowspan > len(self.rows) or column + cell.colspan > len(self.column_widths):
                    raise ValueError("table span exceeds grid")
                if index < len(cached) and column + cell.colspan > cached[index][0]:
                    raise ValueError("overlapping table spans")
                current += cell.colspan
                if cell.rowspan > 1:
                    additions.append((column, column + cell.colspan, r + cell.rowspan))
                column += cell.colspan
            if current != len(self.column_widths):
                raise ValueError("incomplete table grid")
            for start, end, expiry in additions:
                active[start] = end; coverage += end - start
                expires.setdefault(expiry, []).append(start)
                cached = None
        return self


class BlockIdentity(Wire):
    id: Id
    revision: Revision
    provenance: list[Provenance]
    children: list[RichBlock]


class ParagraphBlock(BlockIdentity):
    type: Literal["paragraph"]
    props: ParagraphProps
    content: list[RichInline]


class HeadingBlock(BlockIdentity):
    type: Literal["heading"]
    props: HeadingProps
    content: list[RichInline]


class BulletBlock(BlockIdentity):
    type: Literal["bullet_list"]
    props: ParagraphProps
    content: list[RichInline]


class NumberedBlock(BlockIdentity):
    type: Literal["numbered_list"]
    props: NumberedProps
    content: list[RichInline]


class ChecklistBlock(BlockIdentity):
    type: Literal["check_list"]
    props: ChecklistProps
    content: list[RichInline]


class ToggleBlock(BlockIdentity):
    type: Literal["toggle_list"]
    props: ParagraphProps
    content: list[RichInline]


class QuoteBlock(BlockIdentity):
    type: Literal["quote"]
    props: ParagraphProps
    content: list[RichInline]


class CodeBlock(BlockIdentity):
    type: Literal["code"]
    props: CodeProps
    content: str


class DividerBlock(BlockIdentity):
    type: Literal["divider"]
    props: EmptyProps
    content: None


class TableBlock(BlockIdentity):
    type: Literal["table"]
    props: ParagraphProps
    content: TableContent


class ImageBlock(BlockIdentity):
    type: Literal["image"]
    props: ImageProps
    content: None


class SectionBlock(BlockIdentity):
    type: Literal["section"]
    props: SectionProps
    content: list[RichInline]


RichBlock = Annotated[Union[ParagraphBlock, HeadingBlock, BulletBlock, NumberedBlock, ChecklistBlock,
                           ToggleBlock, QuoteBlock, CodeBlock, DividerBlock, TableBlock, ImageBlock,
                           SectionBlock], Field(discriminator="type")]
for _block_class in (BlockIdentity, ParagraphBlock, HeadingBlock, BulletBlock, NumberedBlock, ChecklistBlock,
                     ToggleBlock, QuoteBlock, CodeBlock, DividerBlock, TableBlock, ImageBlock, SectionBlock):
    _block_class.model_rebuild()


class RichRegion(Wire):
    id: Id
    role: Literal["header", "sidebar", "main"]
    revision: Revision
    blocks: list[RichBlock]


class RichDocumentV1(Wire):
    schema_version: Literal[1]
    revision: Revision
    regions: list[RichRegion] = Field(min_length=3, max_length=3)

    def blocks(self) -> list[RichBlock]:
        result: list[RichBlock] = []

        def visit(block: RichBlock) -> None:
            result.append(block)
            for child in block.children:
                visit(child)

        for region in self.regions:
            for block in region.blocks:
                visit(block)
        return result

    @model_validator(mode="after")
    def identity(self) -> RichDocumentV1:
        if [region.role for region in self.regions] != ["header", "sidebar", "main"]:
            raise ValueError("fixed region reading order required")
        ids = [region.id for region in self.regions]
        owned: list[str] = []
        binding_ids: list[str] = []
        for block in self.blocks():
            ids.append(block.id)
            _unique([link.id for link in block.provenance], "block provenance")
            if isinstance(block, SectionBlock) and block.props.record_id is not None:
                owned.append(block.props.record_id)
            if isinstance(block, TableBlock):
                for row in block.content.rows:
                    ids.append(row.id)
                    ids.extend(cell.id for cell in row.cells)
            inline_groups = ([block.content] if isinstance(block.content, list)
                             else [cell.content for row in block.content.rows for cell in row.cells]
                             if isinstance(block, TableBlock) else [])
            if isinstance(block, ImageBlock):
                inline_groups.append(block.props.caption)
            binding_ids.extend(span.binding_id for group in inline_groups for span in group
                               if isinstance(span, FactFieldSpan))
        _unique(ids, "rich node")
        _unique(owned, "primary record owner")
        _unique(binding_ids, "fact field binding")
        if sum(isinstance(block, ImageBlock) for block in self.blocks()) > 20:
            raise ValueError("live image limit exceeded")
        return self
