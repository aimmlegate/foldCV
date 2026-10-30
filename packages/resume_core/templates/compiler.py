"""Compile local templates into immutable, self-contained recipe packages."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from .loading import load_declared_definition
from .models import (CapturedAsset, CompilationManifest, CompiledBlock, CompiledRecipe,
                     TemplateDefinition, TemplatePackage)
from .projection import (FORMATS, PROFILE_ID, PROFILE_VERSION, SchemaFailure,
                         binding_shape, project_payload, reachable_schema, schema_at, validate_schema)
from .builtin_mapping import check_item_roots, types_at, validate_builtin_mapping, validate_item_pointer
from .focus import icon_catalog
from .operations import runnable

COMPILER_VERSION = "template-compiler-1"
COMPILER_VERSION_2 = "template-compiler-2"
COMPILER_VERSION_3 = "template-compiler-3"
OPERATION_VERSION = "template-operations-1"
PROJECTION_VERSION = "closed-json-1"
ASSET_BYTES = 20 * 1024 * 1024
PACKAGE_BYTES = 40 * 1024 * 1024
CAPABILITIES = ["text", "join_fields", "join_items", "bullets", "tags", "period", "link", "focus_entry"]
ADDED_CAPABILITIES = ['object_items', 'builtin_mapping', 'explicit_item_roots', 'fallback_style', 'header_slots', 'date_text']
# Settings and the import form name the template in one URL path segment, and the router decodes %2F before matching.
TEMPLATE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")


def is_date(shape):
    """A partial date object; text and join nodes show its stated raw text."""
    kind = shape.get("type")
    kinds = set(kind if isinstance(kind, list) else [kind])
    return 'object' in kinds and kinds <= {'object', 'null'} and {'raw', 'year', 'month'} <= set(shape.get('properties', {}))


def date_text(definition):
    for block in definition.blocks:
        full = reachable_schema(block.content_schema, definition.content_definitions)
        try:
            base = schema_at(full, "/*") if block.view.mode == "items" else full
            view = {**base, "$defs": full.get("$defs", {})}
            if any(is_date(schema_at(view, pointer)) for node in block.view.nodes if node.type in {'text', 'join_fields'}
                    for pointer in [*node.fields, *([node.field] if node.field else [])]):
                return True
        except SchemaFailure:
            # compile_definition reports the invalid pointer with its location.
            continue
    return False


def added_capabilities(definition):
    return [name for name, used in [
        ('object_items', any(node.item_field is not None for block in definition.blocks for node in block.view.nodes)),
        ('builtin_mapping', any(fact.builtin_fields for fact in definition.fact_types)),
        ('explicit_item_roots', any(binding.item_pointer is not None for block in definition.blocks for binding in block.bindings)),
        ('fallback_style', any(block.view.fallback_style is not None for block in definition.blocks)),
        ('header_slots', any(node.header_slot is not None for block in definition.blocks for node in block.view.nodes)),
        ('date_text', date_text(definition)),
    ] if used]


def compiler_version(definition):
    return COMPILER_VERSION_3


def canonical(value) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", by_alias=True)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def unique(values, path):
    if len(values) != len(set(values)):
        raise SchemaFailure(path, "duplicate identity")
    return set(values)


def asset_path(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or any(part in {".", ".."} for part in path.parts) or "\\" in relative:
        raise SchemaFailure("/assets/" + relative, "asset path must remain inside the package root")
    root = root.resolve(strict=True)
    candidate = root
    for part in path.parts:
        candidate = candidate / part
        if candidate.is_symlink(): raise SchemaFailure("/assets/" + relative, "symlink assets are unsupported")
    if not candidate.is_file() or not candidate.resolve().is_relative_to(root):
        raise SchemaFailure("/assets/" + relative, "asset is missing or outside the package root")
    if candidate.stat().st_size > ASSET_BYTES:
        raise SchemaFailure("/assets/" + relative, "asset exceeds technical byte limit")
    return candidate


# Limits of a whole list: entries extracted on their own each see a part of it, so none could keep them.
ITEM_LIMITS = ("minItems", "maxItems", "uniqueItems", "contains", "minContains", "maxContains")


def splits_entries(block) -> bool:
    """Whether a block extracts its entries on their own (D117): per_entry on a model block whose content is a list
    without item limits."""
    schema = block.content_schema
    return (bool(block.per_entry) and block.mode == "model" and schema.get("type") == "array"
        and not any(key in schema for key in ITEM_LIMITS))


def dependency_order(definition: TemplateDefinition) -> dict[str, int]:
    blocks = {item.id: item for item in definition.blocks}
    operations = {item.id: item for item in definition.operations}
    if blocks.keys() & operations.keys(): raise SchemaFailure("/operations", "block and operation IDs must be distinct")
    graph = {}
    for item in [*definition.operations, *definition.blocks]:
        dependencies = list(item.depends_on)
        inputs = item.inputs if item.id in operations else item.selectors
        dependencies += [ref.id for ref in inputs if ref.kind in {"block", "operation"}]
        if item.id in blocks:
            if item.operation: dependencies.append(item.operation)
            if item.when: dependencies.append(item.when.operation)
        graph[item.id] = set(dependencies)
    visited, active, ordered = set(), set(), []
    def visit(key):
        if key not in graph: raise SchemaFailure("/dependencies/" + key, "unknown dependency")
        if key in active: raise SchemaFailure("/dependencies/" + key, "dependency cycle")
        if key in visited: return
        active.add(key)
        for dep in sorted(graph[key]): visit(dep)
        active.remove(key); visited.add(key); ordered.append(key)
    for key in graph: visit(key)
    return {key: index for index, key in enumerate(ordered)}


def check_runs(definition):
    """Refuse what every import would refuse or lose. New packages only: stored ones re-verify without it and keep
    opening, and their runtime refuses or shows source lines."""
    operations = {item.id: item for item in definition.operations}
    blocks = {item.id: item for item in definition.blocks}
    for operation in definition.operations:
        if not runnable(operation, definition):
            raise SchemaFailure("/operations/" + operation.id, "operation is not registered or its inputs do not let it run")
        if operation.kind == "partition_employment":
            # The materializer lists old jobs through this field; any other view hides them from both blocks.
            compact = blocks[operation.parameters.compact]
            if not any(node.type in {"join_items", "bullets", "tags"} and node.field == "/items" and node.item_field is None
                    for node in compact.view.nodes):
                raise SchemaFailure("/blocks/" + compact.id + "/view", "compact block must show the list /items")
    for block in definition.blocks:
        if block.mode == "derived":
            source = operations[block.operation]
            if source.kind != "partition_employment" or source.parameters.compact != block.id:
                raise SchemaFailure("/blocks/" + block.id + "/operation",
                    "derived block needs the partition_employment operation that names it compact")
        if not block.view.nodes and block.view.fallback_style is None:
            raise SchemaFailure("/blocks/" + block.id + "/view", "a view without nodes needs fallback_style")


def compile_template(path: Path) -> TemplatePackage:
    path = Path(path)
    raw = path.read_bytes()
    return compile_bytes(raw, path.parent, original_format="json" if path.suffix.lower() == ".json" else "yaml")


def compile_bytes(raw: bytes, root: Path, *, original_format="yaml", assets=None) -> TemplatePackage:
    """`assets` maps an asset path to bytes captured earlier (an edited active package); other paths read from `root`."""
    try:
        definition = TemplateDefinition.model_validate(load_declared_definition(raw,original_format))
    except ValidationError as error:
        first = error.errors(include_input=False)[0]
        raise SchemaFailure("/" + "/".join(map(str, first["loc"])), first["msg"]) from None
    version = compiler_version(definition)
    compiled, recipe, manifest = compile_definition(definition, version)
    # New packages only: stored packages re-verify without it and keep opening; their runtime refuses such replies.
    check_item_roots(definition)
    check_runs(definition)
    if not TEMPLATE_ID.fullmatch(definition.template.id):
        raise SchemaFailure("/template/id", "template id must use letters, digits, '.', '_' or '-' and start with a letter or digit")
    captured = []
    total = 0
    for asset in definition.assets:
        blob = assets.get(asset.path) if assets is not None else None
        if blob is None:
            blob = asset_path(root, asset.path).read_bytes()
        elif len(blob) > ASSET_BYTES:
            raise SchemaFailure("/assets/" + asset.path, "asset exceeds technical byte limit")
        # A stored asset with no bytes reads as not loaded, and a render input refuses it.
        if not blob:
            raise SchemaFailure("/assets/" + asset.path, "asset is empty")
        total += len(blob)
        if total > PACKAGE_BYTES: raise SchemaFailure("/assets", "package exceeds technical byte limit")
        captured.append(CapturedAsset(id=asset.id,path=asset.path,role=asset.role,mimeType=asset.mime_type,
                                     sha256=sha256(blob),size=len(blob),bytesBase64=base64.b64encode(blob).decode("ascii")))
    config_hash = sha256(canonical(definition))
    identity = {"configHash":config_hash,"compilerVersion":version,"operationVersion":OPERATION_VERSION,
        "projectionVersion":PROJECTION_VERSION,"recipe":recipe.model_dump(by_alias=True),
        "assets":{a.id:a.sha256 for a in captured},"blocks":[b.model_dump(by_alias=True) for b in compiled],
        "manifest":manifest.model_dump(by_alias=True)}
    package = TemplatePackage(schemaVersion=1,id=definition.template.id,revision=definition.template.revision,
        packageHash=sha256(canonical(identity)),configHash=config_hash,originalHash=sha256(raw),
        originalFormat=original_format,originalBase64=base64.b64encode(raw).decode("ascii"),definition=definition,
        compilerVersion=version,operationVersion=OPERATION_VERSION,projectionVersion=PROJECTION_VERSION,
        recipe=recipe,assets=captured,blocks=compiled,manifest=manifest)
    try:
        icon_catalog(package)
    except ValueError as error:
        raise SchemaFailure("/style/focus/icon_catalog", str(error)) from None
    return package


def compile_definition_v1(definition: TemplateDefinition):
    """Verify derivation under this exact compiler version without asset I/O."""
    return compile_definition(definition, COMPILER_VERSION)


def compile_definition(definition: TemplateDefinition, version):
    additions = added_capabilities(definition)
    if version not in {COMPILER_VERSION, COMPILER_VERSION_2, COMPILER_VERSION_3} or version == COMPILER_VERSION and additions:
        raise SchemaFailure('/compiler', 'unsupported configuration for captured compiler version')
    capabilities = [*CAPABILITIES, *additions]
    assets = unique([a.id for a in definition.assets], "/assets")
    unique([a.path for a in definition.assets], "/assets/path")
    blocks = unique([b.id for b in definition.blocks], "/blocks")
    operations = unique([o.id for o in definition.operations], "/operations")
    types = unique([f.id for f in definition.fact_types], "/fact_types")
    style = definition.style
    def require(value, choices, location):
        if value not in choices: raise SchemaFailure(location, "unknown reference: " + str(value))
    for name, asset in style.fonts.items():
        require(asset, assets, "/style/fonts/" + name)
        if next(a for a in definition.assets if a.id == asset).role != "font":
            raise SchemaFailure("/style/fonts/" + name, "font token requires a font asset")
    for name, text in style.text.items():
        require(text.font, style.fonts, "/style/text/" + name + "/font")
        require(text.color, style.colors, "/style/text/" + name + "/color")
    require(style.section_band.heading_style, style.text, "/style/section_band/heading_style")
    require(style.section_band.background, style.colors, "/style/section_band/background")
    require(style.footer.style, style.text, "/style/footer/style")
    if style.header.logo: require(style.header.logo.asset, assets, "/style/header/logo")
    if style.header.divider: require(style.header.divider.color, style.colors, "/style/header/divider")
    if style.focus.icon_catalog: require(style.focus.icon_catalog, assets, "/style/focus/icon_catalog")
    regions = definition.layout.regions
    region_ids = [r.id for r in regions]
    # A one-column layout declares no sidebar; documents keep all three regions and its sidebar stays empty.
    if region_ids not in (["header", "sidebar", "main"], ["header", "main"]) or definition.layout.reading_order != region_ids:
        raise SchemaFailure("/layout", "header, optional sidebar and main reading order required")
    for region in regions:
        if region.x + region.width > style.page.width:
            raise SchemaFailure("/layout/regions/" + region.id, "region exceeds page width")
        expected = "first_page_header" if region.id == "header" else "independent_column"
        if region.flow != expected: raise SchemaFailure("/layout/regions/" + region.id, "unsupported region flow")
    if len(regions) == 3:
        sidebar, main = regions[1:]
        if max(sidebar.x, main.x) < min(sidebar.x + sidebar.width, main.x + main.width):
            raise SchemaFailure("/layout/regions", "body columns overlap")
    fact_schemas = {}
    for fact in definition.fact_types:
        fact_schemas[fact.id] = reachable_schema(fact.data_schema, definition.content_definitions)
        validate_builtin_mapping(fact, fact_schemas[fact.id])
        for relation in fact.relations:
            for target in relation.target_types: require(target, types, "/fact_types/" + fact.id + "/relations")
    validate_schema({"type":"object", "properties":{}, "additionalProperties":False, "$defs":definition.content_definitions})
    order = dependency_order(definition)
    compiled = []
    placements = {}
    header_slots = set()
    for item in [*definition.operations, *definition.blocks]:
        refs = item.inputs if item.id in operations else item.selectors
        for ref in refs:
            if ref.kind == "source": require(ref.id, {"all"}, "/selectors")
            elif ref.kind == "fact_type": require(ref.id, types, "/selectors")
            elif ref.kind == "block": require(ref.id, blocks, "/selectors")
            else: require(ref.id, operations, "/selectors")
    for operation in definition.operations:
        if operation.kind == "partition_employment":
            for target in (operation.parameters.detailed, operation.parameters.compact): require(target, blocks, "/operations/" + operation.id)
        if operation.kind == "assign_skills":
            for target in operation.parameters.groups: require(target, blocks, "/operations/" + operation.id)
            require(operation.parameters.uncertain_group, operation.parameters.groups, "/operations/" + operation.id)
        if operation.kind == "select_role_branch" and operation.parameters.classification is not None:
            source = operation.parameters.classification
            location = "/operations/" + operation.id + "/parameters/classification"
            require(source.semantic_type, types, location)
            pointer = "/" + source.field.replace(".", "/")
            if not set(operation.parameters.role_families) <= set(binding_shape(fact_schemas[source.semantic_type], pointer).get("enum", [])):
                raise SchemaFailure(location, "classification must enumerate every role family")
            # The branch reads an admitted value, so a block that binds it must run first.
            producers = {ref.id for ref in operation.inputs if ref.kind == "block"}
            if not any(binding.semantic_type == source.semantic_type and binding.field == source.field
                    for block in definition.blocks if block.id in producers for binding in block.bindings):
                raise SchemaFailure(location, "classification needs an input block that binds it")
    for block in definition.blocks:
        full = reachable_schema(block.content_schema, definition.content_definitions)
        projected, server_only = project_payload(full)
        unique([c.id for c in block.checks], "/blocks/" + block.id + "/checks")
        for check in block.checks:
            for pointer in check.parameters.fields: schema_at(full, pointer)
        for pointer in block.rewrite.fields: schema_at(full, pointer)
        binding_keys = []
        for binding in block.bindings:
            schema_at(full, binding.pointer)
            validate_item_pointer(full, binding)
            require(binding.semantic_type, types, "/blocks/" + block.id + "/bindings")
            declaration = next(fact for fact in definition.fact_types if fact.id == binding.semantic_type)
            if declaration.builtin_fields and binding.field not in declaration.builtin_fields:
                raise SchemaFailure(binding.pointer, 'builtin extra field requires an explicit extension type')
            target_pointer = "/" + binding.field.replace(".", "/")
            if binding_shape(full,binding.pointer) != binding_shape(fact_schemas[binding.semantic_type],target_pointer):
                raise SchemaFailure("/blocks/" + block.id + "/bindings" + binding.pointer, "incompatible semantic binding type")
            binding_keys.append(binding.pointer)
            if binding.relation:
                schema_at(full, binding.relation.subject_pointer)
                if binding.item_pointer is not None:
                    from .projection import pointer_tokens
                    source_root = pointer_tokens(binding.item_pointer)
                    target_root = pointer_tokens(binding.relation.subject_pointer)
                    if (types_at(full, binding.relation.subject_pointer) - {'object', 'null'}
                            or 'object' not in types_at(full, binding.relation.subject_pointer)):
                        raise SchemaFailure(binding.pointer, 'relation subject_pointer must select an object')
                    if binding.relation.kind in {'owned_by', 'extension_of'} and (
                            len(target_root) >= len(source_root) or source_root[:len(target_root)] != target_root):
                        raise SchemaFailure(binding.pointer, 'ownership target root must be an unambiguous item ancestor')
                fact = next(f for f in definition.fact_types if f.id == binding.semantic_type)
                if binding.relation.kind not in {r.kind for r in fact.relations}:
                    raise SchemaFailure("/blocks/" + block.id + "/bindings", "undeclared relationship kind")
        unique(binding_keys, "/blocks/" + block.id + "/bindings")
        base = schema_at(full, "/*") if block.view.mode == "items" else full
        if block.view.fallback_style is not None:
            require(block.view.fallback_style, style.text, '/blocks/' + block.id + '/view/fallback_style')
        if block.operation is not None: require(block.operation, operations, "/blocks/" + block.id + "/operation")
        if block.mode == "derived" and block.operation is None:
            raise SchemaFailure("/blocks/" + block.id + "/operation", "derived block needs a registered operation")
        if block.when:
            require(block.when.operation, operations, "/blocks/" + block.id + "/when")
            condition = next(o for o in definition.operations if o.id == block.when.operation)
            if condition.kind != "select_role_branch" or block.when.equals not in {condition.parameters.matched,condition.parameters.otherwise}:
                raise SchemaFailure("/blocks/" + block.id + "/when", "incompatible operation condition output")
        if block.view.mode == "object" and block.content_schema.get("type") == "array":
            raise SchemaFailure("/blocks/" + block.id + "/view", "array content requires items mode")
        if block.per_entry and not splits_entries(block):
            raise SchemaFailure("/blocks/" + block.id + "/per_entry",
                "per_entry needs a model block whose content is a list without item limits")
        for node in block.view.nodes:
            if node.header_slot is not None:
                if block.placement.region != 'header' or node.header_slot in header_slots:
                    raise SchemaFailure('/blocks/' + block.id + '/view/header_slot', 'header slot needs one unique header node')
                header_slots.add(node.header_slot)
            require(node.style, style.text, "/blocks/" + block.id + "/view/style")
            if node.detail_style: require(node.detail_style, style.text, "/view/detail_style")
            if node.background: require(node.background, style.colors, "/view/background")
            pointers = [*node.fields, *[p for p in (node.field, node.name_field, node.url_field, node.experience_field) if p is not None]]
            view_schema = {**base, "$defs": full.get("$defs", {})}
            for pointer in pointers:
                shape = schema_at(view_schema, pointer)
                kind = shape.get("type")
                kinds = set(kind if isinstance(kind,list) else [kind])
                expected = {"array"} if node.type in {"join_items","bullets","tags"} else {"object","null"} if node.type == "period" else {"string","number","integer","boolean","null"}
                if node.type in {"text", "join_fields"} and is_date(shape):
                    continue
                if not kinds or not kinds <= expected:
                    raise SchemaFailure("/view/" + block.id + pointer, "incompatible view field type")
                if node.type in {"join_items","bullets","tags"}:
                    child = schema_at({**shape, "$defs":full.get("$defs",{})}, "/*")
                    if node.item_field is not None:
                        child = schema_at({**child, '$defs': full.get('$defs', {})}, node.item_field)
                    child_kind = child.get("type")
                    child_types = set(child_kind if isinstance(child_kind,list) else [child_kind])
                    if not child_types <= {"string","number","integer","boolean","null"}:
                        raise SchemaFailure("/view/" + block.id + pointer, "collection items must be scalar")
                if node.type == "period" and not {"raw","start","end","ongoing"} <= set(shape.get("properties",{})):
                    raise SchemaFailure("/view/" + block.id + pointer, "period fields must declare raw/start/end/ongoing")
        if block.placement.region not in region_ids:
            raise SchemaFailure("/blocks/" + block.id + "/placement", "block region is not in the layout")
        key = (block.placement.region, block.placement.order)
        siblings = placements.setdefault(key, [])
        for sibling in siblings:
            if not (block.when and sibling.when and block.when.operation == sibling.when.operation and block.when.equals != sibling.when.equals):
                raise SchemaFailure("/blocks/" + block.id + "/placement", "ambiguous active block order")
        siblings.append(block)
        compiled.append(CompiledBlock(id=block.id, fullSchema=full, providerSchema=projected,
                                      serverOnly=server_only, dependencyOrder=order[block.id]))
    recipe = CompiledRecipe(schemaVersion=1,renderInputVersion=1,capabilities=capabilities,
        style=style,layout=definition.layout,views={b.id:b.view for b in definition.blocks},
        placements={b.id:b.placement for b in definition.blocks})
    manifest = CompilationManifest(profileId=PROFILE_ID,profileVersion=PROFILE_VERSION,
        serverOnly={b.id:b.server_only for b in compiled},supportedFormats=list(FORMATS),capabilities=capabilities)
    return compiled, recipe, manifest
