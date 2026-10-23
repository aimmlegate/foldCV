"""Application-owned discovery handles and exact source-span sidecars."""

from __future__ import annotations

import uuid

from .models.contracts import _unique
from .models.template_facts import HandleAllocation, Lineage, SourceSpan
from .models.template_import import EvidenceOption, FieldSidecar, ProposalReply
from .template_import import digest
from .templates.compiler import canonical, sha256
from .templates.projection import SchemaFailure, pointer_tokens, schema_at, validate_payload


def source_slice(sources,span: SourceSpan) -> str:
    matches = [s for s in sources if s.id == span.source_id and s.revision == span.source_revision]
    if len(matches) != 1:
        raise ValueError('source span has no unique captured source')
    units = [u for u in matches[0].units if u.id == span.unit_id and u.revision == span.unit_revision]
    unit = units[0] if len(units) == 1 else None
    if unit is None or span.end>len(unit.text): raise ValueError("invalid captured source span")
    text=unit.text[span.start:span.end]
    if sha256(text.encode('utf-8'))!=span.slice_hash: raise ValueError("source slice hash mismatch")
    return text


def capture_span(source,unit,start=0,end=None):
    end=len(unit.text) if end is None else end
    span=SourceSpan(sourceId=source.id,sourceRevision=source.revision,unitId=unit.id,unitRevision=unit.revision,
        start=start,end=end,sliceHash=sha256(unit.text[start:end].encode('utf-8')))
    source_slice([source],span)
    return span


def line_spans(source, unit):
    """Each non-blank line of a multi-line unit, with its line break, as one exact span."""
    spans, start = [], 0
    for line in unit.text.splitlines(keepends=True):
        if line.strip():
            spans.append(capture_span(source, unit, start, start + len(line)))
        start += len(line)
    return spans if len(spans) > 1 else []


def evidence_options(spans, sources, *, base=()):
    """Offer each exact span once under a short request-local reference; base options keep theirs."""
    options = list(base)
    seen, refs = {digest(option.span) for option in options}, {option.ref for option in options}
    for span in spans:
        if digest(span) in seen:
            continue
        number = len(refs) + 1
        while 'S' + str(number) in refs:
            number += 1
        seen.add(digest(span)); refs.add('S' + str(number))
        options.append(EvidenceOption(ref='S' + str(number), span=span, text=source_slice(sources, span)))
    return options


def offered_evidence(request):
    """The reference table a captured request offered, or None when the request predates references."""
    if request is None or 'evidence' not in request:
        return None
    options = [EvidenceOption.model_validate(value) for value in request['evidence']]
    _unique([option.ref for option in options], 'offered evidence reference')
    return {option.ref: option for option in options}


def restore_evidence(refs, table, sources):
    """The captured spans a reply selected; an unknown reference or changed source text refuses the reply."""
    spans = []
    for ref in refs:
        option = table.get(ref)
        if option is None:
            raise ValueError('evidence reference was not offered')
        if source_slice(sources, option.span) != option.text:
            raise ValueError('offered evidence text changed')
        spans.append(option.span)
    return spans


def codepoint_offset(text,utf16_offset):
    if type(utf16_offset) is not int or utf16_offset<0: raise ValueError("invalid UTF-16 offset")
    encoded=text.encode('utf-16-le')
    if utf16_offset*2>len(encoded): raise ValueError("UTF-16 offset exceeds text")
    try: return len(encoded[:utf16_offset*2].decode('utf-16-le'))
    except UnicodeError: raise ValueError("UTF-16 offset splits a surrogate pair") from None


def payload_value(payload,pointer):
    value=payload
    for token in pointer_tokens(pointer):
        if isinstance(value,dict) and token in value: value=value[token]
        elif isinstance(value,list) and token.isascii() and token.isdecimal() and (token=='0' or not token.startswith('0')) and int(token)<len(value):
            value=value[int(token)]
        else: raise ValueError("payload pointer does not resolve")
    return value


def empty_value(value):
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, dict):
        return all(empty_value(child) for child in value.values())
    if isinstance(value, list):
        return all(empty_value(child) for child in value)
    return False


def _semantic_payload(payload, fields, *, bindings=(), semantic_type=None, semantic_schema=None, root_tokens=()):
    value = {}
    def assign(keys, raw, *, shared_empty=False):
        target = value
        for key in keys[:-1]:
            child = target.setdefault(key, {})
            if not isinstance(child, dict):
                raise ValueError('overlapping semantic field bindings')
            target = child
        if keys[-1] in target:
            if shared_empty and target[keys[-1]] == raw:
                return
            raise ValueError('duplicate semantic field binding')
        target[keys[-1]] = raw
    for field in fields:
        assign(field.field_key.split('.'), payload_value(payload, field.pointer))
    for binding in bindings:
        pattern = pointer_tokens(binding.pointer)
        if binding.semantic_type != semantic_type or len(pattern) < len(root_tokens) or any(
                expected != '*' and expected != actual for expected, actual in zip(pattern, root_tokens)):
            continue
        path, keys = pattern[len(root_tokens):], binding.field.split('.')
        raw = payload_value(payload, ''.join('/' + token.replace('~', '~0').replace('/', '~1') for token in root_tokens))
        for index, token in enumerate(path):
            if raw is None or raw == {} or raw == []:
                # A nullable payload wrapper may map to a flat field or a nullable
                # semantic parent. Keep its explicit absence at the nearest valid path.
                for prefix in range(len(keys), 0, -1):
                    target = schema_at(semantic_schema, '/' + '/'.join(keys[:prefix]))
                    try:
                        validate_payload({**target, '$defs': semantic_schema.get('$defs', {})}, raw)
                    except SchemaFailure:
                        continue
                    assign(keys[:prefix], raw, shared_empty=True)
                    break
                break
            if not isinstance(raw, dict) or token not in raw:
                break
            raw = raw[token]
    return value


def _binding_instances(payload, bindings):
    result = set()
    def visit(value, tokens, prefix):
        if not tokens:
            yield prefix
        elif isinstance(value, list) and tokens[0] == '*':
            for index, child in enumerate(value):
                yield from visit(child, tokens[1:], prefix + [str(index)])
        elif isinstance(value, dict) and tokens[0] in value:
            yield from visit(value[tokens[0]], tokens[1:], prefix + [tokens[0]])
    for binding in bindings:
        for tokens in visit(payload, pointer_tokens(binding.pointer), []):
            pointer = ''.join('/' + token.replace('~', '~0').replace('/', '~1') for token in tokens)
            result.add((pointer, binding.semantic_type, binding.field))
    return result


def _bound_root(pointer, semantic_type, field_key, bindings):
    actual = pointer_tokens(pointer)
    candidates = [binding for binding in bindings if binding.semantic_type == semantic_type and binding.field == field_key
        and len(pointer_tokens(binding.pointer)) == len(actual)
        and all(pattern == '*' or pattern == token for pattern, token in zip(pointer_tokens(binding.pointer), actual, strict=True))]
    if len(candidates) != 1:
        raise ValueError('field has no unique compiled item binding')
    pattern = pointer_tokens(candidates[0].pointer)
    if candidates[0].item_pointer is not None:
        return actual[:len(pointer_tokens(candidates[0].item_pointer))]
    wildcards = [index for index, token in enumerate(pattern) if token == '*']
    if wildcards:
        return actual[:wildcards[-1] + 1]
    paths = [pointer_tokens(binding.pointer)[:-1] for binding in bindings if binding.semantic_type == semantic_type]
    prefix = paths[0]
    for path in paths[1:]:
        prefix = prefix[:next((index for index, pair in enumerate(zip(prefix, path)) if pair[0] != pair[1]), min(len(prefix), len(path)))]
    return actual[:len(prefix)]


def allocate_discoveries(reply: ProposalReply,*,operation_id,task_id,attempt_id,existing,type_schemas,id_factory=None,bindings=None,cell_id_factory=None,type_declarations=None,reserved=()):
    id_factory=id_factory or (lambda prefix:prefix+'-'+uuid.uuid4().hex)
    keys=[d.key for d in reply.discoveries]
    if len(keys)!=len(set(keys)): raise ValueError("duplicate discovery key")
    indexed={(a.operation_id,a.task_id,a.discovery_attempt_id,a.key):a for a in existing}
    if len(indexed)!=len(existing): raise ValueError("duplicate durable allocation")
    result=[]
    for discovery in reply.discoveries:
        schema=type_schemas.get(discovery.semantic_type)
        if schema is None: raise ValueError("unknown discovery semantic type")
        item = payload_value(reply.payload,discovery.pointer)
        fields = [field for field in reply.fields if field.item.kind == 'discovery_key' and field.item.key == discovery.key]
        value = _semantic_payload(reply.payload, fields, bindings=bindings, semantic_type=discovery.semantic_type,
            semantic_schema=schema, root_tokens=pointer_tokens(discovery.pointer)) if bindings is not None else item
        validate_payload(schema,value)
        if not isinstance(value,dict): raise ValueError("semantic records require explicit object fields")
        identity=(operation_id,task_id,attempt_id,discovery.key)
        allocation=indexed.get(identity)
        declaration = (type_declarations or {}).get(discovery.semantic_type)
        supplied_keys = sorted(field.field_key for field in fields) if bindings is not None else sorted(value)
        cell_keys = sorted({binding.field for binding in bindings if binding.semantic_type == discovery.semantic_type}) if bindings is not None else sorted(schema_at(schema, '').get('properties', {}))
        discovery_hash=sha256(canonical({'semanticType':discovery.semantic_type,'schema':schema,'fields':supplied_keys}))
        if declaration is not None and declaration.builtin_fields:
            cell_keys = sorted(declaration.builtin_fields)
            discovery_hash = sha256(canonical({'semanticType': discovery.semantic_type, 'schema': schema,
                'fields': supplied_keys, 'canonicalMapping': {key: value.model_dump() for key, value in declaration.builtin_fields.items()}}))
        new = allocation is None
        if allocation is None:
            item_handle, record_id = id_factory('item'), id_factory('record')
            allocation=HandleAllocation(operationId=operation_id,taskId=task_id,discoveryAttemptId=attempt_id,
                key=discovery.key,semanticType=discovery.semantic_type,discoveryHash=discovery_hash,
                itemHandle=item_handle,recordId=record_id,
                cellIds={key:cell_id_factory(discovery.semantic_type, record_id, key)
                    if cell_id_factory is not None else id_factory('cell') for key in cell_keys})
        elif allocation.discovery_hash!=discovery_hash:
            raise ValueError("discovery key was reused with different type/schema/fields")
        if declaration is not None:
            from .templates.builtin_mapping import bind_builtin_allocation
            allocation = bind_builtin_allocation(allocation, declaration, id_factory, new=new)
        result.append(allocation)
    all_allocations = {**indexed, **{(a.operation_id,a.task_id,a.discovery_attempt_id,a.key): a for a in result}}
    identifiers = [identifier for allocation in [*reserved, *all_allocations.values()]
        for identifier in [allocation.item_handle, allocation.record_id, *allocation.period_ids.values(), *allocation.cell_ids.values()]]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('allocated identities collide')
    return result


def resolve_fields(reply: ProposalReply,allocations,*,allowed_handles,sources,effective_cells,type_schemas,handle_types,bindings=None):
    if not reply.discoveries and not reply.fields and empty_value(reply.payload):
        return []
    local={a.key:a for a in allocations}
    by_handle={a.item_handle:a for a in allocations}
    allowed=set(allowed_handles)|set(by_handle)
    effective=set(effective_cells)
    seen=set();resolved=[];seen_pointers=set();selected_roots={};selected_fields={}
    expected_bindings = _binding_instances(reply.payload, bindings) if bindings is not None else None
    discoveries={d.key:d for d in reply.discoveries}
    for field in reply.fields:
        if field.item.kind=='discovery_key':
            allocation=local.get(field.item.key)
            if allocation is None: raise ValueError("unknown discovery selector")
            discovery = discoveries.get(field.item.key)
            if discovery is None: raise ValueError('selector is not a discovery in this reply')
            handle=allocation.item_handle;semantic=discovery.semantic_type
            root_tokens = pointer_tokens(discovery.pointer)
            expected = root_tokens + field.field_key.split('.')
            actual = pointer_tokens(field.pointer)
            if (bindings is None and actual != expected) or (bindings is not None and actual[:len(root_tokens)] != root_tokens):
                raise ValueError('field pointer is outside its discovered item')
            if bindings is not None and root_tokens != _bound_root(field.pointer, semantic, field.field_key, bindings):
                raise ValueError('discovery does not select its compiled item scope')
        else:
            handle=field.item.item_handle;semantic=handle_types.get(handle)
            if handle not in set(allowed_handles): raise ValueError('handle was not captured for this task')
            tokens = pointer_tokens(field.pointer)
            path = field.field_key.split('.')
            if bindings is None and tokens[-len(path):] != path:
                raise ValueError('captured field pointer does not match its semantic path')
            root_tokens = _bound_root(field.pointer, semantic, field.field_key, bindings) if bindings is not None else tokens[:-len(path)]
        if expected_bindings is not None and (field.pointer, semantic, field.field_key) not in expected_bindings:
            raise ValueError('field does not match a compiled binding')
        if handle not in allowed or semantic not in type_schemas: raise ValueError("handle is outside task scope")
        identity=(handle,field.field_key)
        if identity in seen: raise ValueError("duplicate field update")
        if field.pointer in seen_pointers: raise ValueError('payload field is assigned more than once')
        seen.add(identity)
        seen_pointers.add(field.pointer)
        root_identity = tuple(root_tokens)
        if handle in selected_roots and selected_roots[handle] != root_identity:
            raise ValueError('one handle selects multiple payload items')
        if any(other != handle and pointer == root_identity for other, pointer in selected_roots.items()):
            raise ValueError('payload item selects multiple handles')
        selected_roots[handle] = root_identity
        selected_fields.setdefault(handle, []).append(field)
        raw=payload_value(reply.payload,field.pointer)
        root=type_schemas[semantic]
        target=schema_at(root,'/'+field.field_key.replace('.','/'))
        validate_payload({**target,'$defs':root.get('$defs',{})},raw)
        if not empty_value(raw) and not field.evidence and not field.effective_cell_ids:
            raise ValueError("interpreted field needs captured evidence")
        if not set(field.effective_cell_ids)<=effective: raise ValueError("unknown/unadmitted effective cell")
        for span in field.evidence: source_slice(sources,span)
        resolved.append(FieldSidecar(itemHandle=handle,fieldKey=field.field_key,pointer=field.pointer,
            evidence=field.evidence,effectiveCellIds=field.effective_cell_ids))
    for discovery in reply.discoveries:
        allocation=local[discovery.key]
        value = _semantic_payload(reply.payload, selected_fields.get(allocation.item_handle, []), bindings=bindings,
            semantic_type=discovery.semantic_type, semantic_schema=type_schemas[discovery.semantic_type],
            root_tokens=pointer_tokens(discovery.pointer)) if bindings is not None else payload_value(reply.payload, discovery.pointer)
        def supplied_fields(item, prefix=''):
            if empty_value(item):
                return []
            if isinstance(item, dict) and item:
                return [leaf for key, child in item.items()
                    for leaf in supplied_fields(child, prefix + '.' + key if prefix else key)]
            return [prefix]
        covered = {key for handle, key in seen if handle == allocation.item_handle}
        if any(not any(path == key or path.startswith(key + '.') for key in covered)
               for path in supplied_fields(value)):
            raise ValueError("supplied field/evidence binding is missing")
    for handle, fields in selected_fields.items():
        if handle not in set(allowed_handles):
            continue
        semantic_value = _semantic_payload(reply.payload, fields, bindings=bindings or (),
            semantic_type=handle_types[handle], semantic_schema=type_schemas[handle_types[handle]], root_tokens=selected_roots[handle])
        validate_payload(type_schemas[handle_types[handle]], semantic_value)
        if bindings is None:
            pointer = ''.join('/' + key.replace('~', '~0').replace('/', '~1') for key in selected_roots[handle])
            raw_item = payload_value(reply.payload, pointer)
            def covered(value, path=''):
                if isinstance(value, dict) and value:
                    return all(covered(child, path + '.' + key if path else key) for key, child in value.items())
                return any(path == field.field_key or path.startswith(field.field_key + '.') for field in fields)
            if not covered(raw_item):
                raise ValueError('supplied captured field/evidence binding is missing')
    if expected_bindings is not None and expected_bindings != {(field.pointer,
            handle_types.get(field.item_handle) or by_handle[field.item_handle].semantic_type, field.field_key) for field in resolved}:
        raise ValueError('compiled field/evidence binding coverage is incomplete')
    return resolved


def resolve_lineage(reply: ProposalReply,allocations,*,allowed_parents,attempt_id):
    local={a.key:a.item_handle for a in allocations};used=set();parents=set();result=[]
    for lineage in reply.lineage:
        if not set(lineage.parents)<=set(allowed_parents) or not set(lineage.children)<=set(local):
            raise ValueError("lineage is outside task scope")
        if used & set(lineage.children) or parents & set(lineage.parents): raise ValueError("duplicate repair lineage")
        used.update(lineage.children);parents.update(lineage.parents)
        result.append(Lineage(kind=lineage.kind,parents=lineage.parents,
            children=[local[key] for key in lineage.children],attemptId=attempt_id))
    if used!=set(local): raise ValueError("new discoveries require explicit add/split/merge lineage")
    return result
