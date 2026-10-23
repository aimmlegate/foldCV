"""Strict template import: an upload becomes a V7 pre-draft with the store's active package, then one captured job.

The runtime call cap has no default: without an explicit configured value the import is unavailable.
"""

from packages.resume_core.models.template_import import ImportCapture, RuntimePolicy, StartTemplateImportV1
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.template_import import digest
from packages.resume_core.templates.store import TemplateStore
from packages.resume_core.dates import partial_date
from packages.resume_core.rich_assembly import identity
from .gui_projects import ProjectFailure


class TemplateImports:
    template_import_call_cap = None
    template_import_model = None

    def configure_template_imports(self, *, call_cap, model):
        """`model` returns the ModelCapture for the selected import model or raises ProjectFailure."""
        if call_cap is not None and (not isinstance(call_cap, int) or call_cap < 1):
            raise ValueError('template import call cap must be an explicit positive integer')
        self.template_import_call_cap, self.template_import_model = call_cap, model

    def template_jobs_ready(self):
        jobs = getattr(self, 'background_jobs', None)
        return jobs is not None and jobs.enabled and jobs.templates is not None

    def template_import_package(self):
        return TemplateStore(self.storage.root).active()

    def template_import_status(self):
        available = self.template_import_call_cap is not None and self.template_import_model is not None and self.template_jobs_ready()
        package = self.template_import_package() if available else None
        return {'schemaVersion': 1, 'available': available, 'package': None if package is None else {
            'id': package.id, 'name': package.definition.template.name, 'revision': package.revision, 'packageHash': package.package_hash}}

    def allocate_template(self, title, package):
        self.ensure_loaded()
        stamp, identifier = self.clock(), identity('project')
        self.workspaces[identifier] = WorkspaceV7.model_validate({'schemaVersion': 7, 'projectId': identifier,
            'projectRevision': 1, 'documentRevision': 1, 'title': title, 'titleManuallySet': False,
            'createdAt': stamp.isoformat(), 'updatedAt': stamp.isoformat(), 'project': None,
            'preDraft': {'sources': [], 'facts': {'schemaVersion': 2, 'revision': 1, 'records': [], 'tombstones': [], 'extensions': [],
                'observations': [], 'relations': [], 'manualScopes': []}, 'selectedInput': 'text', 'selectedSourceId': None,
                'operations': [], 'warnings': [], 'templatePackage': package.model_dump(by_alias=True), 'templateOperations': []},
            'formattingAsOf': partial_date(stamp.date().isoformat()).model_dump(by_alias=True), 'sourceObservedAt': None,
            'rulesUsed': None, 'syncRecords': [], 'mutationReplay': [], 'warnings': []})
        self.persist(identifier)
        return identifier

    async def select_template(self, data, name, pasted):
        if not self.template_import_status()['available']:
            raise ProjectFailure('JOB_DISABLED', 409)
        identifier = self.allocate_template('Новое резюме' if pasted else name, self.template_import_package())
        return await self.select(data, name, pasted, id=identifier)

    def template_import_command(self, identifier, client_request_id, allow_text_rewrite):
        workspace = self.read(identifier)
        pre = workspace.pre_draft
        if workspace.schema_version != 7 or workspace.project is not None or pre is None or pre.template_package is None:
            raise ProjectFailure('IMPORT_PROTOCOL_MISMATCH', 409)
        if not pre.sources or not any(unit.text.strip() for source in pre.sources for unit in source.units):
            raise ProjectFailure('NO_USABLE_TEXT', 409)
        package, sources = pre.template_package, {source.id: source.byte_sha256 for source in pre.sources}
        primary = self.template_import_model()
        capture = ImportCapture(packageHash=package.package_hash, sourceHashes=sources, factRevisions={},
            authorityHash=digest({'project': identifier, 'model': primary.model_dump(mode='json', by_alias=True)}),
            dependencyHash=digest({'package': package.package_hash, 'sources': sources}), allowTextRewrite=allow_text_rewrite,
            primary=primary, fallback=None, formattingAsOf=workspace.formatting_as_of,
            policy=RuntimePolicy(callCap=self.template_import_call_cap, concurrency=1, processingSeconds=300, cleanupSeconds=5,
                finalizationSeconds=30, primaryRepairs=1, fallbackRepairs=1))
        return StartTemplateImportV1(kind='start_new_import', protocol='template_import_v1', clientRequestId=client_request_id,
            capture=capture)

    async def start_template_import(self, identifier, client_request_id, allow_text_rewrite):
        if not self.template_import_status()['available']:
            raise ProjectFailure('JOB_DISABLED', 409)
        command = self.template_import_command(identifier, client_request_id, allow_text_rewrite)
        jobs = self.background_jobs
        jobs.store.open(identifier)
        return await jobs.templates.submit(identifier, command)
