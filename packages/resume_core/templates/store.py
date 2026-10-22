"""Immutable packages and an atomic, explicitly selected active pointer."""

from __future__ import annotations

import base64
from collections import OrderedDict
from pathlib import Path
import threading

from ..storage import atomic_write, locked_root
from ..project_store import owned_file, strict_json
from .compiler import (ADDED_CAPABILITIES, CAPABILITIES, COMPILER_VERSION, COMPILER_VERSION_2, COMPILER_VERSION_3, OPERATION_VERSION, PACKAGE_BYTES,
                       PROJECTION_VERSION, canonical, compile_definition, compile_template, sha256)
from .loading import load_declared_definition,load_definition
from .models import TemplateDefinition, TemplatePackage
from .projection import SchemaFailure, validate_schema

BUNDLED_TEMPLATE = Path(__file__).resolve().parents[3] / "templates/generic-two-column/template.yaml"
_VERIFIED_PACKAGES = OrderedDict()
_VERIFIED_LOCK = threading.Lock()


def package_identity(package: TemplatePackage):
    return {"configHash":package.config_hash,"compilerVersion":package.compiler_version,
        "operationVersion":package.operation_version,"projectionVersion":package.projection_version,
        "recipe":package.recipe.model_dump(by_alias=True),"assets":{a.id:a.sha256 for a in package.assets},
        "blocks":[b.model_dump(by_alias=True) for b in package.blocks],"manifest":package.manifest.model_dump(by_alias=True)}


def verify_package(package: TemplatePackage) -> TemplatePackage:
    if (package.compiler_version not in {COMPILER_VERSION, COMPILER_VERSION_2, COMPILER_VERSION_3} or package.operation_version != OPERATION_VERSION
            or package.projection_version != PROJECTION_VERSION or package.recipe.schema_version != 1
            or package.recipe.render_input_version != 1 or set(package.recipe.capabilities) - set([*CAPABILITIES, *ADDED_CAPABILITIES])):
        raise SchemaFailure("/package", "unsupported package/recipe compatibility")
    try:
        # Checkpoints reuse large packages. Cache only an exact hash of every captured byte.
        fingerprint = sha256(canonical(package))
        with _VERIFIED_LOCK:
            if fingerprint in _VERIFIED_PACKAGES:
                _VERIFIED_PACKAGES.move_to_end(fingerprint)
                return package
        original = base64.b64decode(package.original_base64, validate=True)
        if sha256(original) != package.original_hash: raise ValueError("original bytes hash mismatch")
        loaded=(load_declared_definition(original,package.original_format)
            if package.compiler_version==COMPILER_VERSION_3 else load_definition(original))
        definition = TemplateDefinition.model_validate(loaded)
        if canonical(definition) != canonical(package.definition): raise ValueError("original configuration mismatch")
        if sha256(canonical(definition)) != package.config_hash: raise ValueError("configuration hash mismatch")
        if (package.id,package.revision) != (definition.template.id,definition.template.revision):
            raise ValueError("package identity mismatch")
        if len({a.id for a in package.assets}) != len(package.assets): raise ValueError("duplicate asset")
        declared = {a.id:a for a in definition.assets}
        if set(declared) != {a.id for a in package.assets}: raise ValueError("asset manifest mismatch")
        total = 0
        for asset in package.assets:
            blob = base64.b64decode(asset.bytes_base64, validate=True)
            total += len(blob)
            source = declared[asset.id]
            if (len(blob) != asset.size or sha256(blob) != asset.sha256
                    or (asset.path,asset.role,asset.mime_type) != (source.path,source.role,source.mime_type)):
                raise ValueError("asset bytes/manifest mismatch")
        if total > PACKAGE_BYTES: raise ValueError("package exceeds technical byte limit")
        if (package.recipe.style != definition.style or package.recipe.layout != definition.layout
                or package.recipe.views != {b.id:b.view for b in definition.blocks}
                or package.recipe.placements != {b.id:b.placement for b in definition.blocks}):
            raise ValueError("captured recipe mismatch")
        if len(package.blocks) != len(definition.blocks) or {b.id for b in package.blocks} != {b.id for b in definition.blocks}:
            raise ValueError("compiled block manifest mismatch")
        compiled, recipe, manifest = compile_definition(definition, package.compiler_version)
        if package.blocks != compiled or package.recipe != recipe or package.manifest != manifest:
            raise ValueError("compiled schema/projection/recipe derivation mismatch")
        for block in package.blocks:
            validate_schema(block.full_schema)
            validate_schema(block.provider_schema)
        if sha256(canonical(package_identity(package))) != package.package_hash:
            raise ValueError("package hash mismatch")
    except (ValueError, TypeError, KeyError) as error:
        raise SchemaFailure("/package", str(error)) from None
    with _VERIFIED_LOCK:
        _VERIFIED_PACKAGES[fingerprint] = None
        _VERIFIED_PACKAGES.move_to_end(fingerprint)
        while len(_VERIFIED_PACKAGES) > 8:
            _VERIFIED_PACKAGES.popitem(last=False)
    return package


class TemplateStore:
    def __init__(self, root: Path):
        self.root = Path(root) / "template-packages"

    def _read(self, path: Path):
        owned_file(path, 2 * PACKAGE_BYTES)
        return strict_json(path.read_bytes())

    def activate(self, package: TemplatePackage) -> None:
        verify_package(package)
        with locked_root(self.root, ".templates.lock"):
            registry_path = self.root / "identities.json"
            registry = self._read(registry_path) if registry_path.exists() else {}
            if not isinstance(registry,dict): raise SchemaFailure("/store/identities", "identity registry must be an object")
            identity = canonical([package.id,package.revision]).decode("utf-8")
            retained = registry.get(identity)
            if retained is not None and retained != package.package_hash:
                raise SchemaFailure("/template/revision", "ID/revision already identifies different package bytes")
            path = self.root / package.package_hash / "package.json"
            if path.exists():
                existing = verify_package(TemplatePackage.model_validate(self._read(path)))
                if existing.package_hash != package.package_hash: raise SchemaFailure("/store", "package identity mismatch")
            else:
                atomic_write(path, canonical(package))
            registry[identity] = package.package_hash
            atomic_write(registry_path, canonical(registry))
            atomic_write(self.root / "active.json", canonical({"schemaVersion":1,"packageHash":package.package_hash}))

    def active(self) -> TemplatePackage:
        path = self.root / "active.json"
        if not path.exists() and not path.is_symlink(): return compile_template(BUNDLED_TEMPLATE)
        pointer = self._read(path)
        if not isinstance(pointer,dict) or set(pointer) != {"schemaVersion","packageHash"} or pointer["schemaVersion"] != 1:
            raise SchemaFailure("/store/active", "invalid active template pointer")
        digest = pointer["packageHash"]
        if not isinstance(digest,str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise SchemaFailure("/store/active", "invalid package hash")
        package = verify_package(TemplatePackage.model_validate(self._read(self.root / digest / "package.json")))
        if package.package_hash != digest: raise SchemaFailure("/store/active", "package hash mismatch")
        return package
