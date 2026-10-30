"""Immutable packages, the current version of each template and the default template for new imports.

`active.json` names the default id and the package each id uses when the user saved one; an id without a saved
package uses its bundled file. Schema 1 named one active package: it is the current version of its id and the default.
"""

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

BUNDLED_DIR = Path(__file__).resolve().parents[3] / "templates/bundled"
# Templates shipped with the app by id, sharing one asset folder; the first one is the default until the user picks
# another.
BUNDLED_TEMPLATES = {"generic-two-column": BUNDLED_DIR / "generic-two-column.yaml",
    "generic-one-column": BUNDLED_DIR / "generic-one-column.yaml"}
BUNDLED_TEMPLATE = BUNDLED_TEMPLATES["generic-two-column"]
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
        # Checkpoints reuse large packages. Cache only an exact hash of every captured byte; a workspace's package
        # leaves its asset bytes out of its JSON (D104), so they join the key here.
        fingerprint = sha256(canonical(package) + "".join(asset.bytes_base64 for asset in package.assets).encode("ascii"))
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


class UnknownTemplate(LookupError):
    """No bundled template and no saved package has this id."""


def bundled_package(template_id: str) -> TemplatePackage | None:
    path = BUNDLED_TEMPLATES.get(template_id)
    if path is None: return None
    package = compile_template(path)
    if package.id != template_id: raise SchemaFailure("/template/id", "bundled template id mismatch")
    return package


def bundled_folder(template_id: str) -> Path:
    """Where new asset paths of an edited template are read; an id the app does not ship uses the first bundled folder."""
    return Path(BUNDLED_TEMPLATES.get(template_id) or next(iter(BUNDLED_TEMPLATES.values()))).parent


def _digest(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


class TemplateStore:
    def __init__(self, root: Path):
        self.root = Path(root) / "template-packages"

    def _read(self, path: Path):
        owned_file(path, 2 * PACKAGE_BYTES)
        return strict_json(path.read_bytes())

    def _stored(self, digest, template_id=None) -> TemplatePackage:
        if not _digest(digest): raise SchemaFailure("/store/active", "invalid package hash")
        package = verify_package(TemplatePackage.model_validate(self._read(self.root / digest / "package.json")))
        if package.package_hash != digest: raise SchemaFailure("/store/active", "package hash mismatch")
        if template_id is not None and package.id != template_id: raise SchemaFailure("/store/active", "package id mismatch")
        return package

    def _pointer(self):
        """(chosen default id or None, {id: saved package hash})."""
        path = self.root / "active.json"
        if not path.exists() and not path.is_symlink(): return None, {}
        pointer = self._read(path)
        if isinstance(pointer,dict) and set(pointer) == {"schemaVersion","packageHash"} and pointer["schemaVersion"] == 1:
            package = self._stored(pointer["packageHash"])
            return package.id, {package.id: package.package_hash}
        if (not isinstance(pointer,dict) or set(pointer) != {"schemaVersion","defaultId","current"} or pointer["schemaVersion"] != 2
                or not (pointer["defaultId"] is None or isinstance(pointer["defaultId"],str)) or not isinstance(pointer["current"],dict)):
            raise SchemaFailure("/store/active", "invalid active template pointer")
        if not all(_digest(value) for value in pointer["current"].values()):
            raise SchemaFailure("/store/active", "invalid package hash")
        return pointer["defaultId"], dict(pointer["current"])

    def _write(self, default_id, current) -> None:
        atomic_write(self.root / "active.json", canonical({"schemaVersion":2,"defaultId":default_id,"current":current}))

    @staticmethod
    def _default(default_id, current) -> str:
        # A chosen id that no longer exists (a bundled template an update removed) falls back to the first bundled one.
        return default_id if default_id in BUNDLED_TEMPLATES or default_id in current else next(iter(BUNDLED_TEMPLATES))

    def _versions(self, template_id, current):
        bundled = bundled_package(template_id)
        if template_id in current: return self._stored(current[template_id], template_id), bundled
        if bundled is None: raise UnknownTemplate(template_id)
        return bundled, bundled

    def versions(self, template_id: str):
        """(current package, bundled package or None) of one template id."""
        return self._versions(template_id, self._pointer()[1])

    def _current(self, template_id, current) -> TemplatePackage:
        # A saved version needs no bundled compile; otherwise the bundled one is current.
        if template_id in current: return self._stored(current[template_id], template_id)
        return self._versions(template_id, current)[0]

    def current(self, template_id: str) -> TemplatePackage:
        """The package new imports with this id use: the one saved last, else the bundled one."""
        return self._current(template_id, self._pointer()[1])

    def default_id(self) -> str:
        return self._default(*self._pointer())

    def templates(self):
        """(default id, [(current package, bundled package or None)]): bundled ids in order, then ids only saved here."""
        default_id, current = self._pointer()
        ids = [*BUNDLED_TEMPLATES, *sorted(set(current) - set(BUNDLED_TEMPLATES))]
        return self._default(default_id, current), [self._versions(template_id, current) for template_id in ids]

    def revision_taken(self, package: TemplatePackage) -> bool:
        """True when the package's ID/revision already names different stored bytes, so saving would refuse it."""
        registry_path = self.root / "identities.json"
        if not registry_path.exists(): return False
        registry = self._read(registry_path)
        retained = registry.get(canonical([package.id,package.revision]).decode("utf-8")) if isinstance(registry,dict) else None
        return retained is not None and retained != package.package_hash

    def save(self, package: TemplatePackage, *, default: bool = False) -> None:
        """Store the package as the current version of its id; `default` also makes that id the one new imports use."""
        verify_package(package)
        with locked_root(self.root, ".templates.lock"):
            registry_path = self.root / "identities.json"
            registry = self._read(registry_path) if registry_path.exists() else {}
            if not isinstance(registry,dict): raise SchemaFailure("/store/identities", "identity registry must be an object")
            identity = canonical([package.id,package.revision]).decode("utf-8")
            retained = registry.get(identity)
            if retained is not None and retained != package.package_hash:
                raise SchemaFailure("/template/revision", "ID/revision already identifies different package bytes")
            default_id, current = self._pointer()
            path = self.root / package.package_hash / "package.json"
            if path.exists():
                existing = verify_package(TemplatePackage.model_validate(self._read(path)))
                if existing.package_hash != package.package_hash: raise SchemaFailure("/store", "package identity mismatch")
            else:
                atomic_write(path, canonical(package))
            # The hash leaves the original text out (D106), so a change of comments or form is this same package; the
            # text saved last stays beside it.
            atomic_write(path.parent / "original.json",
                canonical({"format":package.original_format,"base64":package.original_base64}))
            registry[identity] = package.package_hash
            atomic_write(registry_path, canonical(registry))
            current[package.id] = package.package_hash
            self._write(package.id if default else default_id, current)

    def saved_original(self, package: TemplatePackage):
        """(format, bytes) of the text saved last for the current version `package`; None when the store has none."""
        path = self.root / package.package_hash / "original.json"
        if self._pointer()[1].get(package.id) != package.package_hash or not path.exists(): return None
        stored = self._read(path)
        try:
            return stored["format"], base64.b64decode(stored["base64"], validate=True)
        except (KeyError, TypeError, ValueError):
            return None

    def activate(self, package: TemplatePackage) -> None:
        """Save the package and make its id the default for new imports."""
        self.save(package, default=True)

    def set_default(self, template_id: str) -> None:
        with locked_root(self.root, ".templates.lock"):
            _default_id, current = self._pointer()
            if template_id not in BUNDLED_TEMPLATES and template_id not in current: raise UnknownTemplate(template_id)
            self._write(template_id, current)

    def reset(self, template_id: str) -> None:
        """Drop the saved version of a bundled template; its bundled file is the current version again."""
        if template_id not in BUNDLED_TEMPLATES: raise UnknownTemplate(template_id)
        with locked_root(self.root, ".templates.lock"):
            default_id, current = self._pointer()
            if current.pop(template_id, None) is not None:
                self._write(default_id, current)

    def active(self) -> TemplatePackage:
        """The current version of the default template."""
        default_id, current = self._pointer()
        return self._current(self._default(default_id, current), current)
