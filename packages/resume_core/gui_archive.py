"""Portable v5 snapshots and explicit dispatch of legacy project archives."""

from pydantic import ValidationError
from .gui_archive_zip import (ArchiveFailure,read_zip,write_zip,parse_json,json_bytes,digest,safe_path,alias)
from .gui_exports import matching_snapshot
from .gui_rendering import render_input
from .gui_archive_validation import validate_workspace
from .models.contracts import ArchiveManifest,ZipManifest,Project
from .models.recovery import ArchiveManifestV5,WorkspaceV5,authored_fields
from .rendering.template import renderer_sha256,PACKAGE_SHA256,MANIFEST,RenderFailure
from .rendering.docx_errors import DocxFailure
from .gui_migration import migrate_v3


def checked_manifest(raw,files):
    version=raw.get('schemaVersion') if isinstance(raw,dict) else None
    cls={3:ZipManifest,4:ArchiveManifest,5:ArchiveManifestV5}.get(version)
    if cls is None:raise ArchiveFailure('ARCHIVE_VERSION_UNSUPPORTED')
    manifest=cls.model_validate(raw)
    entries={entry.path:entry for entry in manifest.entries}
    if len(entries)!=len(manifest.entries) or set(entries)!=set(files)-{'manifest.json'} or any(not safe_path(path) for path in entries):raise ArchiveFailure('ARCHIVE_MANIFEST_INVALID')
    if len({alias(path) for path in entries})!=len(entries):raise ArchiveFailure('ARCHIVE_MANIFEST_INVALID')
    for path,entry in entries.items():
        if len(files[path])!=entry.uncompressed_size or digest(files[path])!=entry.sha256:raise ArchiveFailure('ARCHIVE_HASH_MISMATCH')
    if version==4:
        if any(entry.role=='render' and entry.path not in {'renders/preview.pdf','renders/resume.docx','renders/request.json'} or
            entry.role=='source_original' and not entry.path.startswith('sources/') and entry.path!='legacy/v2/original' for entry in entries.values()):raise ArchiveFailure('ARCHIVE_MANIFEST_INVALID')
    return manifest,entries


def check_templates(project,entries,files):
    template=project.template if project else None
    pinned=parse_json(MANIFEST.read_bytes())
    if template and (template.id!='generic' or template.version!='1.0.0' or template.package_sha256!=PACKAGE_SHA256):raise ArchiveFailure('ARCHIVE_TEMPLATE_INVALID')
    if template and any(pinned['assets'].get(asset.path)!=asset.sha256 for asset in template.assets):raise ArchiveFailure('ARCHIVE_TEMPLATE_INVALID')
    supplied={path for path,entry in entries.items() if entry.role=='template_asset'}
    if supplied:
        if template is None:raise ArchiveFailure('ARCHIVE_TEMPLATE_INVALID')
        expected={'template/manifest.json':digest(MANIFEST.read_bytes()),**{'template/'+path:sha for path,sha in pinned['assets'].items()}}
        if supplied!=set(expected) or any(digest(files[path])!=expected[path] for path in supplied):raise ArchiveFailure('ARCHIVE_TEMPLATE_INVALID')


def original_bytes(owner,entries,files):
    result={}
    for source in owner.sources:
        entry=entries.get(source.byte_ref)
        content=files.get(source.byte_ref)
        if entry is None or entry.role!='source_original' or content is None or digest(content)!=source.byte_sha256:raise ArchiveFailure('ARCHIVE_SOURCE_MISMATCH')
        result[source.id]=content
    return result


def export_archive(workspace,originals,artifacts):
    workspace=validate_workspace(workspace.model_copy(deep=True));owner=workspace.project or workspace.pre_draft
    payload={};roles={}
    def add(path,role,data):
        if path in payload or not safe_path(path) or alias(path) in {alias(name) for name in payload}:raise ArchiveFailure('ARCHIVE_INVALID_PATH')
        payload[path]=data;roles[path]=role
    for source in owner.sources:
        content=originals.get(source.id)
        if content is None or digest(content)!=source.byte_sha256:raise ArchiveFailure('ARCHIVE_SOURCE_MISMATCH')
        add(source.byte_ref,'source_original',content)
    current=None
    if workspace.project:
        try:
            fingerprint=render_input(workspace)[2]
            current=next((snapshot for snapshot in reversed(owner.renders) if matching_snapshot(workspace,snapshot,artifacts.get(snapshot.id),fingerprint,renderer_sha256())),None)
        except (ValueError,DocxFailure,RenderFailure):
            current=None
    for snapshot in owner.renders:
        snapshot.artifact_available=current is not None and snapshot.id==current.id
    if current:add(current.docx.path,'render',artifacts[current.id])
    add('workspace.json','workspace',json_bytes(workspace.model_dump(mode='json',by_alias=True)))
    if len(payload)>47:raise ArchiveFailure('ARCHIVE_ENTRY_LIMIT')
    manifest=ArchiveManifestV5(schemaVersion=5,appVersion='0.1.0',projectId=workspace.project_id,
        entries=[{'path':path,'role':roles[path],'sha256':digest(data),'uncompressedSize':len(data)} for path,data in payload.items()])
    payload={'manifest.json':json_bytes(manifest.model_dump(mode='json',by_alias=True)),**payload}
    return write_zip(payload)


def open_archive(data,id,clock):
    try:
        files=read_zip(data)
        if 'manifest.json' not in files and 'archive.json' in files:
            from .gui_migration_v2 import migrate_v2_archive
            workspace,originals,artifacts=migrate_v2_archive(files,id,clock)
            return validate_workspace(workspace),originals,artifacts
        raw=parse_json(files.get('manifest.json'));manifest,entries=checked_manifest(raw,files)
        if manifest.schema_version==5:
            workspace=WorkspaceV5.model_validate(parse_json(files.get('workspace.json')))
            if workspace.project_id!=manifest.project_id:raise ArchiveFailure('ARCHIVE_ID_MISMATCH')
            validate_workspace(workspace)
            originals=original_bytes(workspace.project or workspace.pre_draft,entries,files)
            if {entry.path for entry in entries.values() if entry.role=='source_original'}!={source.byte_ref for source in (workspace.project or workspace.pre_draft).sources}:raise ArchiveFailure('ARCHIVE_SOURCE_MISMATCH')
            renders=[entry for entry in entries.values() if entry.role=='render']
            if renders and not any(snapshot.docx.path==renders[0].path and snapshot.docx.sha256==renders[0].sha256 and snapshot.docx.size==renders[0].uncompressed_size for snapshot in (workspace.project or workspace.pre_draft).renders):raise ArchiveFailure('ARCHIVE_RENDER_INVALID')
            workspace.project_id=id
            if workspace.project:workspace.project.project_id=id
            for operation in (workspace.project or workspace.pre_draft).operations:operation.project_id=id
            for generation in workspace.generations:generation.project_id=id
            workspace.mutation_replay=[]
            workspace.migration_notices=list(dict.fromkeys([*workspace.migration_notices,'portable_project_imported']))
            # Imported cache bytes cannot authenticate renderer/content claims; keep metadata unavailable.
            for snapshot in (workspace.project or workspace.pre_draft).renders:snapshot.artifact_available=False
            return workspace,originals,{}
        raw_project=parse_json(files.get('project.json')) if getattr(manifest,'project_id',None) is not None else None
        project=Project.model_validate(raw_project) if raw_project is not None else None
        if project and project.project_id!=manifest.project_id:raise ArchiveFailure('ARCHIVE_ID_MISMATCH')
        check_templates(project,entries,files)
        if manifest.schema_version==3:
            workspace=migrate_v3(project,id,clock);originals=original_bytes(project,entries,files)
        else:
            from .gui_migration_v4 import migrate_v4_workspace
            workspace,originals=migrate_v4_workspace(parse_json(files.get('workspace.json')),project,manifest,entries,files,id,clock)
        return validate_workspace(workspace),originals,{}
    except ArchiveFailure:raise
    except (ValidationError,ValueError,TypeError,KeyError,AttributeError,UnicodeError,RecursionError):raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID') from None
