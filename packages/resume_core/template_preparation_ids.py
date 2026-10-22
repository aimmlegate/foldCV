"""Opening-bound allocation uses named source slots, never traversal counters."""

from .templates.compiler import canonical, sha256


def allocate_id(factory, prefix, slot):
    allocator = getattr(factory, 'allocate', None)
    return allocator(prefix, slot) if allocator is not None else factory(prefix)


def existing_ids(workspace):
    identifiers = set()
    def visit(value, identity=False):
        if isinstance(value, dict):
            for key, child in value.items():
                identifiers.add(key)
                visit(child, identity or key == 'id' or key.endswith(('Id', 'Ids', 'Handle', 'Handles')))
        elif isinstance(value, list):
            for child in value:
                visit(child, identity)
        elif identity and isinstance(value, str):
            identifiers.add(value)
    visit(workspace.model_dump(mode='json', by_alias=True) if hasattr(workspace, 'model_dump') else workspace)
    return identifiers


class EditIdAllocator:
    def __init__(self, proof, client_mutation_id, op_id, occupied):
        self.namespace = [proof.lineage, proof.epoch, proof.incarnation, proof.session_id,
            client_mutation_id, op_id]
        self.op_id = op_id
        self.occupied = set(occupied)
        self.slots = {}
        self.prefixes = {}
        self.derived_slots = set()

    def allocate(self, prefix, slot):
        key = canonical(slot).decode()
        if key in self.slots:
            if key in self.derived_slots or self.prefixes[key] != prefix:
                raise ValueError('allocation slot changes purpose')
            return self.slots[key]
        digest = sha256(b'FoldCV authoring v1\0' + canonical([*self.namespace, slot]))
        identifier = prefix + '-' + digest
        if identifier in self.occupied:
            raise ValueError('allocated authoring identity collides')
        self.occupied.add(identifier)
        self.slots[key], self.prefixes[key] = identifier, prefix
        return identifier

    def derived(self, purpose, slot, identifier):
        key = canonical(slot).decode()
        category = 'derived:' + purpose
        if key in self.slots:
            if key not in self.derived_slots or self.prefixes[key] != category or self.slots[key] != identifier:
                raise ValueError('derived output slot changes purpose or value')
            return identifier
        if identifier in self.occupied:
            raise ValueError('derived authoring identity collides')
        self.occupied.add(identifier)
        self.derived_slots.add(key)
        self.slots[key], self.prefixes[key] = identifier, category
        return identifier

    @property
    def created_ids(self):
        return {self.op_id: dict(self.slots)}
