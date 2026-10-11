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
from packages.resume_core.rendering.privacy import guard_render_document


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
    def label(point):
        if point is None:
            return "н. в." if language == "ru" else "present"
        if point.precision == "year":
            return str(point.year)
        if point.precision == "month":
            return f"{point.year}-{point.month:02d}"
        return f"{point.year}-{point.month:02d}-{point.day:02d}"
    return ", ".join(f"{label(period.start)}–{label(period.end)}" for period in job.periods)


def prepare_document(payload: PrepareRequest) -> RenderRequest:
    project = payload.project
    presentation = payload.presentation
    blocks = {block.id: block for block in project.views}
    profile = next(block for block in project.views if block.kind == "profile")
    if any(block.status == "stale" and block.visible for block in project.views if block.kind in {"profile", "job_prose"}):
        raise ValueError("visible prose needs review")
    if any(block.kind in {"skills", "focus", "early_career", "contact"} and block.state.text.strip()
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
                years = item.experience.months_max // 12
                duration = f"≈ {years} {'лет' if presentation.source_language == 'ru' else 'years'}" if years else "< 1 года" if presentation.source_language == "ru" else "< 1 year"
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
        detailed.append(RenderProject(company=job.employer, period=_period(job, presentation.source_language),
                                      stack="", description=block.state.text, role=job.role,
                                      tasks=[], results=[]))
    sidebar = []
    early_block = next((block for block in project.views if block.kind == "early_career"), None)
    if project.as_of is not None and (early_block is None or early_block.visible):
        old_rows = early_career_rows((job for job in project.employment
                                      if blocks[presentation.job_prose_blocks[job.id]].visible), project.as_of)
        if old_rows:
            sidebar.append(SidebarSection(title="РАННИЙ ОПЫТ" if presentation.source_language == "ru" else "EARLY CAREER",
                                          items=[", ".join(format_early_career(row) for row in old_rows)]))
    for block in project.views:
        if block.kind == "education" and block.visible and block.state.text.strip():
            sidebar.append(SidebarSection(title="ОБРАЗОВАНИЕ", items=[block.state.text]))
    if presentation.languages:
        sidebar.append(SidebarSection(title="ЯЗЫКИ" if presentation.source_language == "ru" else "LANGUAGES",
                                      items=presentation.languages))
    skills_block = next((block for block in project.views if block.kind == "skills"), None)
    groups = [SkillGroup(title=category.upper(), items=", ".join(items))
              for category, items in group_technologies(project).items()] if skills_block is None or skills_block.visible else []
    document = RenderDocument(candidate=Candidate(name=presentation.name, title=presentation.title,
                                                   summary=profile.state.text if profile.visible else ""),
                              focus=focus, sidebar=sidebar, projects=detailed, achievements=[],
                              skillGroups=groups, footer="")
    guard_render_document(document)
    identity = RenderIdentity(id="render-" + hashlib.sha256((project.project_id + ":" + str(project.revision)).encode()).hexdigest()[:16],
                              projectRevision=project.revision, snapshotSha256="0" * 64,
                              templateId="generic", templateVersion="1.0.0",
                              templatePackageSha256=PACKAGE_SHA256,
                              rendererVersion=manifest["rendererVersion"], rendererSha256=renderer_sha256())
    draft = RenderRequest.model_construct(base_revision=project.revision, snapshot=identity, document=document)
    identity.snapshot_sha256 = snapshot_digest(draft)
    return RenderRequest(baseRevision=project.revision, snapshot=identity, document=document)
