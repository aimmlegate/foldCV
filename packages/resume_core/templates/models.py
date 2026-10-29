"""Stable template language and immutable compiled-package envelopes."""

from __future__ import annotations

import base64
import hashlib
import threading
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from ..models.contracts import Id, Sha256, Wire

JsonObject = dict[str, JsonValue]
RegionId = Literal["header", "sidebar", "main"]
Positive = Annotated[float, Field(gt=0)]
Points = Annotated[float, Field(ge=0)]


class Definition(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class TemplateIdentity(Definition):
    id: Id
    revision: Id
    name: str
    default_locale: str


class AssetDeclaration(Definition):
    id: Id
    path: str
    role: Literal["font", "logo", "icon", "catalog"]
    mime_type: str
    embedding: Literal["allowed", "not_applicable"]


class Page(Definition):
    width: Positive
    height: Positive
    first_body_top: Points
    continuation_body_top: Points
    body_bottom: Positive

    @model_validator(mode="after")
    def geometry(self) -> Page:
        if max(self.first_body_top, self.continuation_body_top) >= self.body_bottom or self.body_bottom >= self.height:
            raise ValueError("body bounds must be inside the page")
        return self


class TextStyle(Definition):
    font: Id
    size: Positive
    line_height: Positive
    color: Id


class Logo(Definition):
    asset: Id
    x: Points
    top: Points
    width: Positive
    height: Positive
    fit: Literal["contain"]


class Divider(Definition):
    x1: Points
    x2: Positive
    y: Points
    width: Positive
    color: Id
    follow_header: Literal[True]


class Header(Definition):
    name_top: Points
    profession_top: Points
    overflow: Literal["grow_header_and_move_body"]
    logo: Logo | None
    divider: Divider | None


class Band(Definition):
    height: Positive
    text_inset: Points
    background: Id
    heading_style: Id


class Bullets(Definition):
    marker: str
    marker_offset: Points
    text_offset: Points
    marker_size: Positive


class Focus(Definition):
    icon_catalog: Id | None
    icon_x: Points
    icon_width: Positive
    icon_height: Positive
    text_x: Points
    minimum_row_height: Positive
    icon_fit: Literal["contain"]
    # initial: a grey square with the first letter of the name (D113); text_only keeps earlier packages as they were.
    missing_icon: Literal["text_only", "initial"]


class Footer(Definition):
    text: str
    center_x: Points
    baseline_y: Points
    style: Id
    repeat: Literal["every_page"]


class Style(Definition):
    page: Page
    fonts: dict[str, Id]
    colors: dict[str, Annotated[str, Field(pattern=r"^#[a-fA-F0-9]{6}$")]]
    text: dict[str, TextStyle]
    header: Header
    section_band: Band
    bullets: Bullets
    focus: Focus
    footer: Footer


class Region(Definition):
    id: RegionId
    x: Points
    width: Positive
    flow: Literal["first_page_header", "independent_column"]


class Pagination(Definition):
    keep_heading_with_next: bool
    allow_project_split: Literal[True]
    allow_more_pages: Literal[True]
    truncate_content: Literal[False]


class Layout(Definition):
    regions: list[Region]
    reading_order: list[RegionId]
    pagination: Pagination


class SourcePolicy(Definition):
    retain_original: Literal[True]
    retain_unmapped_facts: Literal[True]


class ModelInstructions(Definition):
    extract: list[str]
    rewrite: list[str]
    permission: Literal["allowTextRewrite"]


class RelationDeclaration(Definition):
    kind: Literal["owned_by", "extension_of", "related_to"]
    target_types: list[Id]


class BuiltinFieldBinding(Definition):
    field: Id
    period: Id | None


class FactType(Definition):
    id: Id
    schema_version: Id
    data_schema: JsonObject = Field(alias="schema")
    builtin_kind: Literal["candidate", "detail", "employment", "subproject", "technology", "education",
                          "language", "certification", "claim", "metric", "leadership", "unresolved"] | None
    relations: list[RelationDeclaration]
    builtin_fields: dict[str, BuiltinFieldBinding] = Field(default_factory=dict, exclude_if=lambda value: not value)


class InputRef(Definition):
    kind: Literal["source", "fact_type", "block", "operation"]
    id: Id


class PartitionParameters(Definition):
    years: int = Field(gt=0)
    detailed: Id
    compact: Id


class FactField(Definition):
    semantic_type: Id
    field: Id


class RoleParameters(Definition):
    role_families: list[str]
    matched: str
    otherwise: str
    # The admitted fact that names the role family; retained packages without it keep their exact bytes.
    classification: FactField | None = Field(default=None, exclude_if=lambda value: value is None)


class SkillsParameters(Definition):
    groups: list[Id]
    uncertain_group: Id


class PeriodParameters(Definition):
    separator: str
    ongoing_label: dict[str, str]


class EmptyParameters(Definition):
    pass


class OperationBase(Definition):
    id: Id
    version: Literal[1]
    inputs: list[InputRef]
    depends_on: list[Id]


class PartitionOperation(OperationBase):
    kind: Literal["partition_employment"]
    parameters: PartitionParameters


class RoleOperation(OperationBase):
    kind: Literal["select_role_branch"]
    parameters: RoleParameters


class SkillsOperation(OperationBase):
    kind: Literal["assign_skills"]
    parameters: SkillsParameters


class PeriodOperation(OperationBase):
    kind: Literal["format_period"]
    parameters: PeriodParameters


class PreserveOperation(OperationBase):
    kind: Literal["preserve_stated_text"]
    parameters: EmptyParameters


Operation = Annotated[PartitionOperation | RoleOperation | SkillsOperation | PeriodOperation | PreserveOperation,
                      Field(discriminator="kind")]


class BindingRelation(Definition):
    kind: Literal["owned_by", "extension_of", "related_to"]
    subject_pointer: str


class Binding(Definition):
    pointer: str
    semantic_type: Id
    field: Id
    relation: BindingRelation | None
    item_pointer: str | None = Field(default=None, exclude_if=lambda value: value is None)


class CheckParameters(Definition):
    fields: list[str]
    instructions: list[str]


class Check(Definition):
    id: Id
    kind: Literal["content_schema", "evidence_identity", "protected_values", "claim_ownership",
                  "complete_assignment", "semantic_support", "task_result_separation", "attribution"]
    version: Literal[1]
    parameters: CheckParameters


class ViewNode(Definition):
    type: Literal["text", "join_fields", "join_items", "bullets", "tags", "period", "link", "focus_entry"]
    style: Id
    field: str | None = None
    fields: list[str] = Field(default_factory=list)
    separator: str = ""
    prefix: dict[str, str] = Field(default_factory=dict)
    label: dict[str, str] = Field(default_factory=dict)
    name_field: str | None = None
    url_field: str | None = None
    experience_field: str | None = None
    detail_style: Id | None = None
    background: Id | None = None
    item_field: str | None = Field(default=None, exclude_if=lambda value: value is None)
    header_slot: Literal['name', 'profession'] | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def node_shape(self) -> ViewNode:
        required = {"join_fields": ("fields",), "link": ("name_field", "url_field"),
                    "focus_entry": ("name_field", "experience_field")}.get(self.type, ("field",))
        if any(not getattr(self, key) for key in required):
            raise ValueError(f"{self.type} requires {', '.join(required)}")
        allowed = set(required) | {"style", "type", "prefix", "label"}
        if self.type in {'text', 'join_fields'}: allowed.add('header_slot')
        if self.type in {"join_fields", "join_items", "tags"}: allowed.add("separator")
        if self.type in {"join_items", "bullets", "tags"}: allowed.add("item_field")
        if self.type == "focus_entry": allowed.add("detail_style")
        if self.type == "tags": allowed.add("background")
        for key in type(self).model_fields:
            if key not in allowed and getattr(self, key):
                raise ValueError(f"{key} is incompatible with {self.type}")
        return self


class View(Definition):
    mode: Literal["object", "items"]
    heading: Literal["none", "plain", "band"]
    title: dict[str, str]
    inset: Points
    item_gap: Points
    nodes: list[ViewNode]
    fallback_style: Id | None = Field(default=None, exclude_if=lambda value: value is None)


class Rewrite(Definition):
    fields: list[str]
    instructions: list[str]


class Placement(Definition):
    region: RegionId
    order: int


class Condition(Definition):
    operation: Id
    equals: str


class Block(Definition):
    id: Id
    mode: Literal["model", "derived", "source_copy"]
    # Reasoning effort for this block's extraction calls; None keeps the captured model's effort (D101 probe H: the
    # whole projects block came back complete at high where medium stopped after one to five jobs).
    effort: Literal["low", "medium", "high"] | None = Field(default=None, exclude_if=lambda value: value is None)
    selectors: list[InputRef]
    content_schema: JsonObject
    bindings: list[Binding]
    extract: list[str]
    rewrite: Rewrite
    checks: list[Check]
    depends_on: list[Id]
    operation: Id | None
    when: Condition | None
    placement: Placement
    view: View


class TemplateDefinition(Definition):
    schema_version: Literal[3]
    template: TemplateIdentity
    assets: list[AssetDeclaration]
    style: Style
    layout: Layout
    source: SourcePolicy
    content_definitions: dict[str, JsonObject]
    fact_types: list[FactType]
    model: ModelInstructions
    operations: list[Operation]
    blocks: list[Block]
    provenance: JsonObject


class CompiledRecipe(Wire):
    schema_version: Literal[1]
    render_input_version: Literal[1]
    capabilities: list[Id]
    style: Style
    layout: Layout
    views: dict[str, View]
    placements: dict[str, Placement]


class CapturedAsset(Wire):
    id: Id
    path: str
    role: Literal["font", "logo", "icon", "catalog"]
    mime_type: str
    sha256: Sha256
    size: int = Field(ge=0)
    bytes_base64: str


class CompiledBlock(Wire):
    id: Id
    full_schema: JsonObject
    provider_schema: JsonObject
    server_only: list[str]
    dependency_order: int = Field(ge=0)


class CompilationManifest(Wire):
    profile_id: Id
    profile_version: Id
    server_only: dict[str, list[str]]
    supported_formats: list[str]
    capabilities: list[str]


class TemplatePackage(Wire):
    schema_version: Literal[1]
    id: Id
    revision: Id
    package_hash: Sha256
    config_hash: Sha256
    original_hash: Sha256
    original_format: Literal["yaml", "json"]
    original_base64: str
    definition: TemplateDefinition
    compiler_version: Id
    operation_version: Id
    projection_version: Id
    recipe: CompiledRecipe
    assets: list[CapturedAsset]
    blocks: list[CompiledBlock]
    manifest: CompilationManifest


# Captured asset bytes by SHA-256. They are immutable, so every copy of a workspace shares one text (D104).
_ASSET_TEXTS: dict[str, str] = {}
_ASSET_TYPES: dict[str, str] = {}
_ASSET_LOCK = threading.Lock()


def remember_asset(sha256: str, text: str, mime_type: str | None = None) -> None:
    with _ASSET_LOCK:
        known = sha256 in _ASSET_TEXTS
        if known and mime_type:
            _ASSET_TYPES.setdefault(sha256, mime_type)
    if known:
        return
    if hashlib.sha256(base64.b64decode(text, validate=True)).hexdigest() != sha256:
        raise ValueError("captured asset bytes do not match their hash")
    with _ASSET_LOCK:
        _ASSET_TEXTS[sha256] = text
        if mime_type:
            _ASSET_TYPES.setdefault(sha256, mime_type)


def asset_text(sha256: str) -> str | None:
    with _ASSET_LOCK:
        return _ASSET_TEXTS.get(sha256)


def asset_type(sha256: str) -> str | None:
    with _ASSET_LOCK:
        return _ASSET_TYPES.get(sha256)


class StoredAsset(CapturedAsset):
    """An asset of a workspace's captured package. Its bytes stay in memory and in the project's asset files, never in
    the workspace JSON, its hash or the browser's copy (D104: fonts were a quarter of every 10 MB reply)."""
    bytes_base64: str = Field(default="", exclude=True)

    @model_validator(mode="before")
    @classmethod
    def shared_bytes(cls, data):
        if isinstance(data, CapturedAsset) and not isinstance(data, cls):
            data = {**data.model_dump(by_alias=True), "bytesBase64": data.bytes_base64}
        if not isinstance(data, dict):
            return data
        text, digest, mime = data.get("bytesBase64"), data.get("sha256"), data.get("mimeType")
        if not isinstance(digest, str):
            return data
        if text:
            remember_asset(digest, text, mime if isinstance(mime, str) else None)
            return data
        text = asset_text(digest)
        if text is None:
            raise ValueError("captured asset bytes are not loaded")
        if isinstance(mime, str):
            remember_asset(digest, text, mime)
        return {**data, "bytesBase64": text}


class StoredTemplatePackage(TemplatePackage):
    assets: list[StoredAsset]

    @model_validator(mode="before")
    @classmethod
    def from_package(cls, data):
        if isinstance(data, TemplatePackage) and not isinstance(data, cls):
            return {**data.model_dump(by_alias=True), "assets": list(data.assets)}
        return data

    def full(self) -> TemplatePackage:
        """The same package with its asset bytes, for archives and the template store."""
        return TemplatePackage.model_validate({**self.model_dump(by_alias=True),
            "assets": [{**asset.model_dump(by_alias=True), "bytesBase64": asset.bytes_base64} for asset in self.assets]})

    def __eq__(self, other):
        # The same captured package whichever form holds it; Python asks the subclass first in both directions.
        if isinstance(other, TemplatePackage) and not isinstance(other, StoredTemplatePackage):
            return self.full() == other
        return super().__eq__(other)


class StyleOverrides(Wire):
    font: Id | None
    size: Positive | None
    color: Annotated[str, Field(pattern=r"^#[a-fA-F0-9]{6}$")] | None
    alignment: Literal["left", "center", "right", "justify"] | None
    bold: bool | None
    italic: bool | None


class AuthoredPresentation(Wire):
    package_hash: Sha256
    view_key: Id
    style_token: Id
    template_instance_id: Id | None
    item_handle: Id | None
    overrides: StyleOverrides
    node_index: int | None = Field(default=None, ge=0, exclude_if=lambda value: value is None)
