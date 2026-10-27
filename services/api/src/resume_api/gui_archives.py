"""Durable portable snapshots and separate imported project identities."""

import asyncio
import uuid
from packages.resume_core.gui_archive import export_archive,open_archive
from packages.resume_core.archive_zip import ArchiveFailure
from .gui_errors import ProjectFailure


class GuiArchiveMixin:
    async def portable_archive(self,id,request):
        self.read(id)
        with self.state_lock:
            workspace=self.workspaces[id]
            if (request.project_revision,request.document_revision)!=(workspace.project_revision,workspace.document_revision):raise ProjectFailure('ARCHIVE_STALE')
            if self.persist(id)=='failed':raise ProjectFailure('PROJECT_SAVE_FAILED',503)
            captured=self.read_memory(id)
            originals={source.id:self.originals[(id,source.id)] for source in self.owner(captured).sources}
            artifacts={snapshot.id:self.artifacts.get((id,snapshot.id)) for snapshot in self.owner(captured).renders}
        try:return await asyncio.to_thread(export_archive,captured,originals,artifacts)
        except ArchiveFailure as error:raise ProjectFailure(error.code,422) from None

    async def import_archive(self,data):
        id='project-'+uuid.uuid4().hex
        try:workspace,originals,artifacts=await asyncio.to_thread(open_archive,data,id,self.clock())
        except ArchiveFailure as error:raise ProjectFailure(error.code,422) from None
        self.ensure_loaded()
        with self.state_lock:
            owner=self.owner(workspace)
            for op in owner.operations:
                op.project_id=id
                if op.status in {'queued','running'}:
                    op.status,op.error_code='interrupted','INTERRUPTED'
            for generation in workspace.generations:
                generation.project_id=id
                if generation.status in {'queued','running'}:generation.status='interrupted'
                for stage in generation.stages:
                    if stage.status in {'queued','running'}:stage.status,stage.error_code='interrupted','INTERRUPTED'
            workspace.updated_at=self.clock().isoformat()
            self.workspaces[id]=workspace
            self.originals.update({(id,sid):value for sid,value in originals.items()})
            self.artifacts.update({(id,rid):value for rid,value in artifacts.items()})
            self.restore_analysis_pending(id)
            self.persist(id)
        return id
