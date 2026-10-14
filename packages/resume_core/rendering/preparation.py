"""Map an explicit in-memory editor presentation to the fixed render document."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field, model_validator

from packages.resume_core.dates import old_job
from packages.resume_core.models.contracts import Project as WorkingProject
from packages.resume_core.selection import early_career_rows, format_early_career, group_technologies, select_focus
from packages.resume_core.rendering.models import (Candidate, FocusItem, Project as RenderProject,
                                                  RenderDocument, RenderIdentity, RenderRequest, RenderWire, SidebarSection,
                                                  SkillGroup, snapshot_digest)
from packages.resume_core.rendering.template import PACKAGE_SHA256, renderer_sha256, require_template


class PreparationFailure(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class Presentation(RenderWire):
    name: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=240)
    source_language: Literal["ru", "en", "mixed"]
    job_prose_blocks: dict[str, str] = Field(max_length=60)
    languages: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_languages(self) -> Presentation:
        if len(self.languages) > 20 or any(not item.strip() or len(item) > 80 for item in self.languages):
            raise ValueError("invalid language")
        return self


class PrepareRequest(RenderWire):
    project: WorkingProject
    presentation: Presentation

    @model_validator(mode="after")
    def valid_bindings(self) -> PrepareRequest:
        if self.project.schema_version != 3:
            raise ValueError("unsupported project")
        template = self.project.template
        if template is None or template.id != "generic" or template.version != "1.0.0" or template.package_sha256 != PACKAGE_SHA256:
            raise ValueError("selected template does not match renderer")
        jobs = {job.id for job in self.project.employment}
        blocks = {block.id: block for block in self.project.views}
        if set(self.presentation.job_prose_blocks) != jobs:
            raise ValueError("every job needs an explicit prose binding")
        ids = list(self.presentation.job_prose_blocks.values())
        if len(ids) != len(set(ids)) or any(blocks.get(item) is None or blocks[item].kind != "job_prose" for item in ids):
            raise ValueError("invalid prose binding")
        if len([block for block in blocks.values() if block.kind == "profile"]) != 1:
            raise ValueError("exactly one profile required")
        if any(block.kind == "job_prose" and block.visible and block.id not in ids for block in blocks.values()):
            raise ValueError("visible prose is not bound to a job")
        return self


def _period(job, language: str) -> str:
    if not job.periods:
        return "Даты не указаны" if language == "ru" else "Dates not specified"
    def label(point):
        if point is None:
            return "н. в." if language == "ru" else "present"
        if point.precision == "year":
            return str(point.year)
        if point.precision == "month":
            return f"{point.year}-{point.month:02d}"
        return f"{point.year}-{point.month:02d}-{point.day:02d}"
    return ", ".join(f"{label(period.start)}–{label(period.end)}" for period in job.periods)


def _duration(months: int, language: str) -> str:
    years = months // 12
    if not years:
        return "< 1 года" if language == "ru" else "< 1 year"
    if language == "ru":
        unit = "лет" if 11 <= years % 100 <= 14 else "год" if years % 10 == 1 else "года" if years % 10 in {2, 3, 4} else "лет"
    else:
        unit = "year" if years == 1 else "years"
    return f"≈ {years} {unit}"


def prepare_document(payload: PrepareRequest) -> RenderRequest:
    project = payload.project
    presentation = payload.presentation
    blocks = {block.id: block for block in project.views}
    profile = next(block for block in project.views if block.kind == "profile")
    if any(block.status == "stale" and block.visible for block in project.views if block.kind in {"profile", "job_prose"}):
        raise ValueError("visible prose needs review")
    if any(block.kind in {"skills", "focus", "early_career"} and block.state.text.strip()
           for block in project.views):
        raise ValueError("unsupported structured edit")
    manifest = require_template()
    asset_prefix = "skills/format-resume/assets/"
    available = [path.removeprefix(asset_prefix) for path in manifest["assets"] if path.startswith(asset_prefix)]
    focus = []
    focus_block = next((block for block in project.views if block.kind == "focus"), None)
    if focus_block is None or focus_block.visible:
        for item in select_focus(project, available):
            duration = ""
            if item.experience is not None:
                duration = _duration(item.experience.months_min, presentation.source_language)
            focus.append(FocusItem(label=item.display, duration=duration, icon=item.canonical_id))
    detailed = []
    for job in project.employment:
        if project.as_of is None:
            is_old = False
        else:
            is_old = bool(job.periods) and all(old_job(period.end, project.as_of) for period in job.periods)
        if is_old:
            continue
        block = blocks[presentation.job_prose_blocks[job.id]]
        if not block.visible:
            continue
        if not block.state.text.strip():
            raise ValueError("visible job prose is empty")
        if len(block.state.text) > 4000:
            raise PreparationFailure("JOB_DESCRIPTION_TOO_LONG")
        if len(_period(job, presentation.source_language)) > 100:
            raise PreparationFailure("JOB_PERIOD_TOO_LONG")
        detailed.append(RenderProject(company=job.employer, period=_period(job, presentation.source_language),
                                      stack="", description=block.state.text, role=job.role,
                                      tasks=[], results=[]))
    sidebar = []
    early_block = next((block for block in project.views if block.kind == "early_career"), None)
    if project.as_of is not None and (early_block is None or early_block.visible):
        old_rows = early_career_rows(project.employment, project.as_of)
        if old_rows:
            sidebar.append(SidebarSection(title="РАННИЙ ОПЫТ" if presentation.source_language == "ru" else "EARLY CAREER",
                                          items=[", ".join(format_early_career(row) for row in old_rows)]))
    for block in project.views:
        if block.kind == "contact" and block.visible and block.state.text.strip():
            sidebar.append(SidebarSection(title="КОНТАКТЫ И ДАННЫЕ" if presentation.source_language == "ru" else "CONTACTS AND DETAILS",
                                          items=[block.state.text]))
        if block.kind == "education" and block.visible and block.state.text.strip():
            if len(block.state.text) > 4000:
                raise PreparationFailure("EDUCATION_TOO_LONG")
            sidebar.append(SidebarSection(title="ОБРАЗОВАНИЕ" if presentation.source_language == "ru" else "EDUCATION", items=[block.state.text]))
    if presentation.languages:
        sidebar.append(SidebarSection(title="ЯЗЫКИ" if presentation.source_language == "ru" else "LANGUAGES",
                                      items=presentation.languages))
    skills_block = next((block for block in project.views if block.kind == "skills"), None)
    groups = [SkillGroup(title=category.upper(), items=", ".join(items))
              for category, items in group_technologies(project).items()] if skills_block is None or skills_block.visible else []
    if profile.visible and len(profile.state.text) > 12000:
        raise PreparationFailure("PROFILE_TOO_LONG")
    document = RenderDocument(sourceLanguage=presentation.source_language,
                              candidate=Candidate(name=presentation.name, title=presentation.title,
                                                   summary=profile.state.text if profile.visible else ""),
                              focus=focus, sidebar=sidebar, projects=detailed, achievements=[],
                              skillGroups=groups, footer="")
    identity = RenderIdentity(id="render-" + hashlib.sha256((project.project_id + ":" + str(project.revision)).encode()).hexdigest()[:16],
                              projectRevision=project.revision, snapshotSha256="0" * 64,
                              templateId="generic", templateVersion="1.0.0",
                              templatePackageSha256=PACKAGE_SHA256,
                              rendererVersion=manifest["rendererVersion"], rendererSha256=renderer_sha256())
    draft = RenderRequest.model_construct(base_revision=project.revision, snapshot=identity, document=document)
    identity.snapshot_sha256 = snapshot_digest(draft)
    return RenderRequest(baseRevision=project.revision, snapshot=identity, document=document)
