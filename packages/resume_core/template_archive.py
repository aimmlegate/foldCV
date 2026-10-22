"""Portable v7 projects retain package bytes and distrust foreign render caches."""

import base64

from pydantic import ValidationError

from .gui_archive_zip import ArchiveFailure, alias, digest, json_bytes, parse_json, read_zip, write_zip
from .models.template_workspace import ArchiveManifestV7, WorkspaceV7
from .rich_archive import inert_sync_history, referenced_assets
from .rich_images import ImageFailure, verify_image_bytes
from .templates.compiler import canonical
from .templates.models import TemplatePackage
from .templates.store import verify_package


def _verify_image(asset, blob):
    try:
        verify_image_bytes(asset, blob)
    except ImageFailure:
        raise ArchiveFailure('ARCHIVE_IMAGE_MISMATCH') from None


def archive_payload_v7(workspace,originals,images,current_render=None):
    workspace=WorkspaceV7.model_validate(workspace.model_dump(by_alias=True))
    inert_sync_history(workspace)
    owner=workspace.project or workspace.pre_draft
    package=owner.template_package
    if package is not None: verify_package(package)
    payload={};roles={}
    def add(path,role,blob):
        if path in payload and payload[path]==blob and roles[path]==role: return
        if alias(path) in {alias(p) for p in payload}: raise ArchiveFailure('ARCHIVE_INVALID_PATH')
        payload[path]=blob;roles[path]=role
    for source in owner.sources:
        raw=originals.get(source.id)
        if raw is None or digest(raw)!=source.byte_sha256: raise ArchiveFailure('ARCHIVE_SOURCE_MISMATCH')
        add(source.byte_ref,'source_original',raw)
    if package is not None:
        add('template/package.json','template_package',canonical(package))
        for asset in package.assets:
            add('template/assets/'+asset.sha256,'template_asset',base64.b64decode(asset.bytes_base64,validate=True))
    if workspace.project:
        workspace.project.assets=referenced_assets(workspace.project)
        workspace.project.renders=[]
        for asset in workspace.project.assets:
            blob=images.get(asset.id)
            if blob is None: raise ArchiveFailure('ARCHIVE_IMAGE_MISMATCH')
            _verify_image(asset,blob);add(asset.path,'user_image',blob)
    add('workspace.json','workspace',json_bytes(workspace.model_dump(mode='json',by_alias=True)))
    try:
        manifest=ArchiveManifestV7(schemaVersion=7,appVersion='0.1.0',projectId=workspace.project_id,
            entries=[{'path':path,'role':roles[path],'sha256':digest(blob),'size':len(blob)} for path,blob in payload.items()])
    except ValidationError: raise ArchiveFailure('ARCHIVE_CAPACITY_LIMIT') from None
    return {'manifest.json':manifest.model_dump_json(by_alias=True).encode(),**payload}


def open_archive_v7(data,project_id):
    try:
        files=read_zip(data);manifest=ArchiveManifestV7.model_validate(parse_json(files.get('manifest.json')))
        entries={entry.path:entry for entry in manifest.entries}
        if set(entries)!=set(files)-{'manifest.json'}: raise ArchiveFailure('ARCHIVE_MANIFEST_INVALID')
        for path,entry in entries.items():
            if len(files[path])!=entry.size or digest(files[path])!=entry.sha256: raise ArchiveFailure('ARCHIVE_HASH_MISMATCH')
        workspace=WorkspaceV7.model_validate(parse_json(files.get('workspace.json')))
        if workspace.project_id!=manifest.project_id: raise ArchiveFailure('ARCHIVE_ID_MISMATCH')
        owner=workspace.project or workspace.pre_draft
        package=owner.template_package
        if package is not None:
            captured=verify_package(TemplatePackage.model_validate(parse_json(files.get('template/package.json'))))
            if canonical(package)!=canonical(captured): raise ArchiveFailure('ARCHIVE_TEMPLATE_INVALID')
            expected_assets={'template/assets/'+a.sha256 for a in package.assets}
            for asset in package.assets:
                if files.get('template/assets/'+asset.sha256)!=base64.b64decode(asset.bytes_base64,validate=True):
                    raise ArchiveFailure('ARCHIVE_TEMPLATE_INVALID')
        else:
            expected_assets=set()
            if any(e.role=='template_package' for e in entries.values()): raise ArchiveFailure('ARCHIVE_TEMPLATE_INVALID')
        if expected_assets!={e.path for e in entries.values() if e.role=='template_asset'}:
            raise ArchiveFailure('ARCHIVE_TEMPLATE_INVALID')
        originals={};images={}
        if {s.byte_ref for s in owner.sources}!={e.path for e in entries.values() if e.role=='source_original'}:
            raise ArchiveFailure('ARCHIVE_SOURCE_MISMATCH')
        for source in owner.sources:
            if digest(files[source.byte_ref])!=source.byte_sha256: raise ArchiveFailure('ARCHIVE_SOURCE_MISMATCH')
            originals[source.id]=files[source.byte_ref]
        expected_images=set()
        if workspace.project:
            referenced=referenced_assets(workspace.project)
            if len(referenced)!=len(workspace.project.assets): raise ArchiveFailure('ARCHIVE_IMAGE_MISMATCH')
            for asset in referenced:
                if asset.path not in entries or entries[asset.path].role!='user_image':
                    raise ArchiveFailure('ARCHIVE_IMAGE_MISMATCH')
                _verify_image(asset,files[asset.path]);images[asset.id]=files[asset.path];expected_images.add(asset.path)
            workspace.project.project_id=project_id
            workspace.project.renders=[]
        if expected_images!={e.path for e in entries.values() if e.role=='user_image'}:
            raise ArchiveFailure('ARCHIVE_IMAGE_MISMATCH')
        workspace.project_id=project_id;workspace.mutation_replay=[]
        for operation in owner.template_operations:
            operation.project_id=project_id
            if operation.state not in {'published','failed','cancelled'}: operation.state='fenced'
        for operation in owner.operations:
            if operation.status in {'queued','running'}:
                operation.status='interrupted';operation.error_code='OPERATION_INTERRUPTED'
        inert_sync_history(workspace)
        return WorkspaceV7.model_validate(workspace.model_dump(by_alias=True)),originals,{},images
    except ArchiveFailure: raise
    except (ValueError,TypeError,KeyError,AttributeError,UnicodeError,RecursionError):
        raise ArchiveFailure('ARCHIVE_WORKSPACE_INVALID') from None
