"""Opening-scoped clipboard payloads share the existing retention budgets."""

from dataclasses import dataclass,field,replace

from .background_store import BackgroundFailure,RetainedUsage
from .models.template_authoring import TemplateClipboardCaptureV1
from .models.template_clipboard import RetainedTemplateClipboardV1
from .template_clipboard import capture_clipboard,selected_witnesses
from .template_clipboard_witnesses import fingerprint,verify_witnesses
from .template_local_history import TemplateLocalHistory
from .templates.compiler import canonical,sha256


def retained_records(value):
    if isinstance(value,dict):
        return 1+sum(retained_records(child)+int(isinstance(child,str)
            and (key=='id' or key.endswith(('Id','Handle')))) for key,child in value.items())
    if isinstance(value,list):return 1+sum(max(1,retained_records(child)) for child in value)
    return 0


@dataclass(frozen=True)
class ClipboardEntry:
    request_hash: str
    capture_id: str
    payload: bytes | None
    payload_records: int


@dataclass
class ClipboardOpening:
    key: tuple
    entries: dict[str,ClipboardEntry]=field(default_factory=dict)


class TemplateClipboards:
    def __init__(self,jobs):
        self.jobs,self.openings=jobs,{}
        self.usage_key='template_clipboards:'+str(id(self))
        jobs.usage_providers[self.usage_key]=self.usage
        jobs.state_observers[self.usage_key]=self.observe

    @staticmethod
    def closed(state,key):
        return (state.tombstoned or state.writer is None or state.writer.status=='clean_detached'
            or TemplateLocalHistory.key(state)!=key)

    def observe(self,state):
        opening=self.openings.get(state.project_id)
        if opening is not None and self.closed(state,opening.key):self.openings.pop(state.project_id)

    def opening(self,state):
        self.observe(state)
        return self.openings.get(state.project_id)

    def usage(self,*,replacing=None,states=None):
        openings=dict(self.openings)
        if replacing is not None:openings[replacing.key[0]]=replacing
        result={}
        for project,opening in openings.items():
            state=states.get(project) if states is not None else None
            if state is not None and self.closed(state,opening.key):continue
            entries={identifier:{'requestHash':entry.request_hash,'captureId':entry.capture_id,
                'payload':entry.payload.decode() if entry.payload is not None else None,
                'payloadRecords':entry.payload_records} for identifier,entry in opening.entries.items()}
            result[project]=RetainedUsage(sum(len(entry.payload) for entry in opening.entries.values() if entry.payload is not None),
                len(canonical({'key':list(opening.key),'entries':entries})),
                1+sum(3+entry.payload_records for entry in opening.entries.values()))
        return result

    def find(self,state,request):
        opening=self.opening(state)
        entry=opening.entries.get(request.client_capture_id) if opening is not None else None
        if entry is not None and entry.request_hash!=fingerprint(request):
            raise BackgroundFailure('JOB_IDEMPOTENCY_CONFLICT')
        return entry

    @staticmethod
    def workspace_guard(state,workspace):
        if workspace.schema_version!=7 or workspace.project is None or workspace.project_id!=state.project_id:
            raise BackgroundFailure('JOB_SCOPE_INVALID')

    def read(self,state,entry):
        opening=self.opening(state)
        if (opening is None or not any(value is entry for value in opening.entries.values())
                or entry.payload is None):raise BackgroundFailure('REQUEST_EXPIRED')
        try:
            retained=RetainedTemplateClipboardV1.model_validate_json(entry.payload)
            if (retained.request_hash!=entry.request_hash or retained.capture.clipboard_capture_id!=entry.capture_id
                    or retained.capture.project_id!=state.project_id):raise ValueError('clipboard binding changed')
            return retained
        except (ValueError,TypeError,KeyError,RecursionError):raise BackgroundFailure('REQUEST_EXPIRED') from None

    def admit(self,state,workspace,request):
        self.workspace_guard(state,workspace)
        entry=self.find(state,request)
        if entry is not None:return self.read(state,entry).capture.model_copy(deep=True)
        key=TemplateLocalHistory.key(state)
        identifier='clipboard-'+sha256(canonical(['FoldCV clipboard v1',list(key),request.client_capture_id]))
        capture=TemplateClipboardCaptureV1(schemaVersion=1,clipboardCaptureId=identifier,projectId=state.project_id,
            sourceSnapshot=request.snapshot.model_copy(deep=True),selection=request.selection.model_copy(deep=True))
        retained=capture_clipboard(workspace,capture,fingerprint(request))
        value=retained.model_dump(mode='json',by_alias=True);payload=canonical(value)
        entry=ClipboardEntry(retained.request_hash,identifier,payload,retained_records(value))
        current=self.opening(state)
        candidate=ClipboardOpening(key,{**(current.entries if current is not None else {}),request.client_capture_id:entry})
        self.jobs._capacity(state,self.jobs._all(),retained_usage={self.usage_key:self.usage(replacing=candidate)})
        self.openings[state.project_id]=candidate
        return capture.model_copy(deep=True)

    def read_for_paste(self,state,workspace,identifier):
        self.workspace_guard(state,workspace)
        opening=self.opening(state)
        entry=next((value for value in opening.entries.values() if value.capture_id==identifier),None) if opening else None
        if entry is None:raise BackgroundFailure('REQUEST_EXPIRED')
        retained=self.read(state,entry)
        try:
            verify_witnesses(workspace.project,retained.witnesses,retained.package_fingerprint)
            if selected_witnesses(workspace.project,retained.payload)!=retained.witnesses:
                raise ValueError('clipboard witness coverage changed')
        except ValueError:raise BackgroundFailure('DEPENDENCY_CHANGED') from None
        return retained

    def release(self,state,identifier):
        opening=self.opening(state)
        if opening is None:raise BackgroundFailure('REQUEST_EXPIRED')
        client=next((key for key,value in opening.entries.items() if value.capture_id==identifier),None)
        if client is None:raise BackgroundFailure('REQUEST_EXPIRED')
        entry=opening.entries[client]
        opening.entries[client]=replace(entry,payload=None,payload_records=0)
