"""Registry reads and explicit deletion of one verified owned project."""

from packages.resume_core.gui_projects import GuiProjectListResponse, GuiDeleteProjectResult
from packages.resume_core.project_store import ProjectStoreFailure
from .gui_errors import ProjectFailure


class GuiManagementMixin:
    def list_projects(self):
        self.ensure_loaded()
        if self.storage is None:
            from packages.resume_core.models.recovery import RegistryEntry
            entries = [RegistryEntry(projectId=id, title=workspace.title, updatedAt=workspace.updated_at,
                tombstoned=False, cleanupStatus='none') for id, workspace in self.workspaces.items() if id not in self.deleted_ids]
        else:
            try: entries = self.storage.registry().entries
            except ProjectStoreFailure as error: raise ProjectFailure(error.code, 503) from None
            self.deleted_ids.update(entry.project_id for entry in entries if entry.tombstoned)
        return GuiProjectListResponse(entries=sorted([entry for entry in entries if not entry.tombstoned or entry.cleanup_status != 'complete'],
            key=lambda entry: (entry.updated_at, entry.project_id), reverse=True),
            errors=[{'projectId':id,'errorCode':code} for id,code in self.load_errors.items() if id not in self.deleted_ids])

    async def delete_project(self, id):
        self.ensure_loaded()
        if self.storage is None: raise ProjectFailure('PROJECT_STORAGE_REQUIRED', 503)
        try: self.storage.tombstone(id)
        except ProjectStoreFailure as error:
            self.list_projects()
            raise ProjectFailure(error.code, 409) from None
        with self.state_lock:
            self.deleted_ids.add(id)
            self.stop_analysis_timer(id)
            for key, cancel in [*self.cancels.items(), *self.input_cancels.items()]:
                if key[0] == id: cancel.set()
        try:
            for pid, oid in list(self.tasks):
                if pid == id: await self.cancel(id, oid, allow_deleted=True)
            for pid, sid in list(self.input_tasks):
                if pid == id: await self.cancel_input(id, sid)
        except ProjectFailure as error:
            return GuiDeleteProjectResult(projectId=id, status='cleanup_incomplete', errorCode=error.code)
        try: result = self.storage.cleanup_deleted(id)
        except ProjectStoreFailure as error:
            return GuiDeleteProjectResult(projectId=id, status='cleanup_incomplete', errorCode=error.code)
        if result.cleanup_status != 'complete':
            return GuiDeleteProjectResult(projectId=id, status='cleanup_incomplete', errorCode='PROJECT_CLEANUP_FAILED')
        with self.state_lock:
            self.workspaces.pop(id, None);self.save_errors.pop(id, None);self.saved_hashes.pop(id, None);self.saved_revisions.pop(id, None)
            self.load_errors.pop(id, None);self.selection_epochs.pop(id, None)
            for mapping in (self.originals,self.artifacts,self.cache,self.tasks,self.cancels):
                for key in list(mapping):
                    if key[0] == id: mapping.pop(key,None)
        return GuiDeleteProjectResult(projectId=id,status='deleted',errorCode=None)
