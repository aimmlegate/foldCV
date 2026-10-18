"""Small import drafts; interpretations remain editable text."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .contracts import Id, Sha256, Wire

IMPORT_TOOLS = ("read_import", "save_import", "finish_import")
ImportNote = Annotated[str, Field(min_length=1, max_length=4000)]
ImportText = Annotated[str, Field(max_length=4000)]


class ImportPeriod(Wire):
    start: ImportText = ""
    end: ImportText = ""
    present: bool = False


class ImportSkill(Wire):
    display: ImportNote
    technical: bool | None = Field(default=None, exclude_if=lambda value: value is None)
    experience: ImportText = Field(default="", exclude_if=lambda value: not value)


class ImportEmployment(Wire):
    kind: Literal["employment"]
    employer: ImportText = ""
    role: ImportText = ""
    periods: list[ImportPeriod] = Field(default_factory=list, max_length=40)
    technologies: list[ImportNote | ImportSkill] = Field(default_factory=list, max_length=100)


class ImportEducation(Wire):
    kind: Literal["education"]
    institution: ImportText = ""
    qualification: ImportText = ""
    specialty: ImportText = ""
    completion: ImportText = ""


class ImportTechnology(ImportSkill):
    kind: Literal["technology"]


class ImportLanguage(Wire):
    kind: Literal["language"]
    language: ImportText = ""
    level: ImportText = ""


ImportRecord = Annotated[ImportEmployment | ImportEducation | ImportTechnology | ImportLanguage,
    Field(discriminator="kind")]


class ImportFact(Wire):
    id: Id
    text: ImportText = ""
    source_keys: list[Id] = Field(default_factory=list, max_length=1000)
    record: ImportRecord | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def content(self):
        if self.record is None and not self.text:
            raise ValueError("Provide a fact record or a retained note")
        return self


class ImportBlock(Wire):
    id: Id
    source_keys: list[Id] = Field(default_factory=list, max_length=1000)
    region: Literal["header", "sidebar", "main"] = "main"
    kind: Literal["paragraph", "heading", "section", "bullet_list", "duplicate"] = "paragraph"
    title: str | None = Field(default=None, max_length=200)
    list_item: bool = Field(default=False, exclude_if=lambda value: not value)
    model_block: bool = Field(default=False, exclude_if=lambda value: not value)
    duplicate_of: list[Id] = Field(default_factory=list, max_length=1000, exclude_if=lambda value: not value)
    category: Literal["identity", "contacts", "summary", "experience", "education", "skills", "languages", "other"] | None = Field(
        default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def content(self):
        if not self.source_keys and not (self.kind in {"heading", "section"} and self.title and self.title.strip()):
            raise ValueError("A block needs source keys or a section heading")
        if (self.kind == "duplicate") != bool(self.duplicate_of):
            raise ValueError("Only a duplicate block needs duplicate targets")
        return self


class ImportProfile(Wire):
    name: str = Field(default="", max_length=4000)
    title: str = Field(default="", max_length=4000)
    location: str = Field(default="", max_length=4000)
    source_keys: list[Id] = Field(default_factory=list, max_length=1000)


class ImportBatch(Wire):
    batch_id: Id
    sequence: int = Field(ge=0, le=128)
    facts: list[ImportFact] = Field(default_factory=list, max_length=100)
    blocks: list[ImportBlock] = Field(default_factory=list, max_length=5000)
    profile: ImportProfile | None = None
    remove_fact_ids: list[Id] = Field(default_factory=list, max_length=100)
    remove_block_ids: list[Id] = Field(default_factory=list, max_length=5000)


class ImportFinish(Wire):
    sequence: int = Field(ge=0, le=128)
    issues: list[ImportNote] = Field(default_factory=list, max_length=100)


class ImportRead(Wire):
    section: Literal["source", "draft"] = "source"
    offset: int = Field(default=0, ge=0)


ParagraphRef = Annotated[str, Field(min_length=1, max_length=40)]


class ContentRefs(Wire):
    refs: list[ParagraphRef] = Field(default_factory=list, max_length=2000,
        description="Supporting paragraphs, for example p3 or the inclusive range p3-p8.")


class ContentFact(ContentRefs):
    kind: Literal["note", "text"] = "note"
    text: ImportNote


class ContentEmployment(ImportEmployment, ContentRefs):
    pass


class ContentEducation(ImportEducation, ContentRefs):
    pass


class ContentTechnology(ImportTechnology, ContentRefs):
    pass


class ContentLanguage(ImportLanguage, ContentRefs):
    pass


class ContentBlock(Wire):
    type: Literal["paragraph", "heading", "section", "list_item", "duplicate"]
    refs: list[ParagraphRef] = Field(min_length=1, max_length=2000,
        description="Source paragraphs in this complete block, in reading order. Keep source wording.")
    duplicate_of: list[ParagraphRef] = Field(default_factory=list, max_length=2000,
        exclude_if=lambda value: not value,
        description="For a duplicate only: refs to its visible occurrence in this outline. Retain the original source.")

    @model_validator(mode="after")
    def duplicate_targets(self):
        if (self.type == "duplicate") != bool(self.duplicate_of):
            raise ValueError("Only a duplicate block needs duplicateOf refs")
        return self


class ContentSection(Wire):
    category: Literal["identity", "contacts", "summary", "experience", "education", "skills", "languages", "other"] = "other"
    heading: str = Field(default="", max_length=200)
    refs: list[ParagraphRef] = Field(default_factory=list, max_length=2000,
        description="Source paragraphs in reading order. Ranges such as p3-p8 are inclusive.")
    list_items: list[Annotated[list[ParagraphRef], Field(min_length=1, max_length=2000)]] = Field(
        default_factory=list, max_length=500, exclude_if=lambda value: not value,
        description="Each inner array identifies one complete list item. Join broken continuations by meaning, "
        "including across layout groups or pages. Use existing paragraph refs; keep source wording.")
    blocks: list[ContentBlock] = Field(default_factory=list, max_length=1000,
        exclude_if=lambda value: not value,
        description="Ordered complete paragraphs, headings, sections, list items or marked duplicates. "
        "Use blocks instead of refs/listItems for this section; Python applies the layout.")

    @model_validator(mode="after")
    def block_format(self):
        if self.blocks and (self.refs or self.list_items):
            raise ValueError("Use either blocks or refs/listItems in each section")
        return self


class ContentProfile(Wire):
    name: str = Field(default="", max_length=4000)
    title: str = Field(default="", max_length=4000)
    location: str = Field(default="", max_length=4000)
    refs: list[ParagraphRef] = Field(default_factory=list, max_length=2000)


class ImportContent(Wire):
    facts: list[ContentEmployment | ContentEducation | ContentTechnology | ContentLanguage | ContentFact] | None = Field(
        default=None, max_length=100,
        description="Replace the whole fact list with employment, education, technology and language records. "
        "Use text notes only for facts that do not fit those groups. Omit to keep saved facts.")
    sections: list[ContentSection] | None = Field(default=None, max_length=40,
        description="Replace the whole outline. Omit to keep the saved sections. Python applies the layout.")
    profile: ContentProfile | None = None

    @model_validator(mode="after")
    def content(self):
        if self.facts is None and self.sections is None and self.profile is None:
            raise ValueError("Provide facts, sections or profile; omitted fields keep their saved values")
        return self


class ImportContentFinish(Wire):
    issues: list[ImportNote] = Field(default_factory=list, max_length=100)


class ImportReceipt(Wire):
    batch_id: Id
    request_sha256: Sha256
    sequence: int = Field(ge=1, le=128)


class ImportDraft(Wire):
    version: Literal[1] = 1
    source_sha256: Sha256
    skill_sha256: Sha256
    run_id: Id
    sequence: int = Field(default=0, ge=0, le=128)
    facts: list[ImportFact] = Field(default_factory=list, max_length=1000)
    blocks: list[ImportBlock] = Field(default_factory=list, max_length=5000)
    profile: ImportProfile = Field(default_factory=ImportProfile)
    receipts: list[ImportReceipt] = Field(default_factory=list, max_length=128)
    finished: bool = False
    issues: list[ImportNote] = Field(default_factory=list, max_length=100)
