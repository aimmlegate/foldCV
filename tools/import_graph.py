"""Static import graph of the core and the service, read from the AST; no module is imported.

Commands: fanin, fanout, cycles, who <module[:symbol]>, uses <module:symbol>, orphans. Function-level imports count
as edges. Module names are dotted (`packages.resume_core.dates`); a name without one of the package prefixes is
tried under each of them.
"""

import argparse
import ast
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = (("packages.resume_core", "packages/resume_core"), ("resume_api", "services/api/src/resume_api"))
# Folders read only for their importers of the graph's modules (`who --with tests`).
EXTRA = {"tests": "tests", "tools": "tools", "packaging": "packaging", "skills": "skills", "unit": "apps/web/unit"}


@dataclass
class Import:
    source: str
    target: str
    symbol: str | None
    line: int
    local: bool


@dataclass
class Graph:
    paths: dict[str, Path] = field(default_factory=dict)
    imports: list[Import] = field(default_factory=list)
    extra: set[str] = field(default_factory=set)

    def edges(self):
        result = defaultdict(set)
        for item in self.imports:
            if item.source in self.extra or item.target == item.source:
                continue
            result[item.source].add(item.target)
        return result


def module_names(folder, prefix):
    found = {}
    for path in sorted(folder.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        parts = [part for part in path.relative_to(folder).with_suffix("").parts if part != "__init__"]
        found[".".join([prefix, *parts]) if prefix else ".".join(parts)] = path
    return found


def origin_of(node, name, path):
    if not node.level:
        return node.module
    package = name if path.name == "__init__.py" else name.rpartition(".")[0]
    parts = package.split(".")
    base = parts[:len(parts) - node.level + 1]
    return ".".join([*base, node.module] if node.module else base)


def attribute_chain(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return list(reversed(parts))
    return None


def read_file(graph, name, path):
    known = graph.paths
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    top = {id(node) for node in tree.body}
    nested = {id(child) for node in tree.body if isinstance(node, (ast.If, ast.Try))
              for child in ast.walk(node) if isinstance(child, (ast.Import, ast.ImportFrom))}
    aliases = {}
    for node in ast.walk(tree):
        local = id(node) not in top and id(node) not in nested
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = longest_known(alias.name, known)
                if target is None:
                    continue
                graph.imports.append(Import(name, target, None, node.lineno, local))
                # `import a.b` binds `a`; `import a.b as m` binds `m` to `a.b`.
                if alias.asname:
                    aliases[alias.asname] = target
                else:
                    aliases[alias.name.split(".")[0]] = alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            origin = origin_of(node, name, path)
            if origin is None:
                continue
            for alias in node.names:
                module = f"{origin}.{alias.name}"
                if module in known:
                    graph.imports.append(Import(name, module, None, node.lineno, local))
                    aliases[alias.asname or alias.name] = module
                elif origin in known:
                    graph.imports.append(Import(name, origin, None if alias.name == "*" else alias.name,
                                                node.lineno, local))
    # `module.symbol` through an imported module alias counts as a symbol import.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        chain = attribute_chain(node)
        if not chain or chain[0] not in aliases:
            continue
        dotted = ".".join([aliases[chain[0]], *chain[1:]])
        module = longest_known(dotted, known)
        if module is None or module == dotted:
            continue
        symbol = dotted[len(module) + 1:].split(".")[0]
        graph.imports.append(Import(name, module, symbol, node.lineno, True))


def longest_known(dotted, known):
    parts = dotted.split(".")
    for end in range(len(parts), 0, -1):
        candidate = ".".join(parts[:end])
        if candidate in known:
            return candidate
    return None


def build(root=ROOT, packages=PACKAGES, extra=()):
    graph = Graph()
    for prefix, folder in packages:
        graph.paths.update(module_names(Path(root) / folder, prefix))
    files = dict(graph.paths)
    for label in extra:
        folder = Path(root) / EXTRA.get(label, label)
        for name, path in module_names(folder, f"<{label}>").items():
            if path.suffix == ".py":
                files[name] = path
                graph.extra.add(name)
    for name, path in files.items():
        read_file(graph, name, path)
    # Dedupe: one row per (source, target, symbol, line).
    seen = set()
    unique = []
    for item in graph.imports:
        key = (item.source, item.target, item.symbol, item.line)
        if key not in seen:
            seen.add(key)
            unique.append(item)
    graph.imports = unique
    return graph


def resolve(graph, name):
    if name in graph.paths:
        return name
    for prefix, _ in PACKAGES:
        if f"{prefix}.{name}" in graph.paths:
            return f"{prefix}.{name}"
    matches = [module for module in graph.paths if module.endswith("." + name)]
    if len(matches) == 1:
        return matches[0]
    raise SystemExit(f"unknown module {name}" + (f": {', '.join(sorted(matches))}" if matches else ""))


def strongly_connected(edges, nodes):
    index, low, stack, on_stack, result = {}, {}, [], set(), []
    counter = [0]

    def visit(start):
        work = [(start, iter(sorted(edges.get(start, ()))))]
        index[start] = low[start] = counter[0]
        counter[0] += 1
        stack.append(start)
        on_stack.add(start)
        while work:
            node, children = work[-1]
            for child in children:
                if child not in index:
                    index[child] = low[child] = counter[0]
                    counter[0] += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(sorted(edges.get(child, ())))))
                    break
                if child in on_stack:
                    low[node] = min(low[node], index[child])
            else:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[node])
                if low[node] == index[node]:
                    component = []
                    while True:
                        item = stack.pop()
                        on_stack.discard(item)
                        component.append(item)
                        if item == node:
                            break
                    result.append(sorted(component))

    for node in sorted(nodes):
        if node not in index:
            visit(node)
    return sorted((c for c in result if len(c) > 1), key=lambda c: (-len(c), c))


def reexports(graph, module, symbol):
    """Modules that bind `symbol` from `module` at import level, so their importers use it too."""
    return sorted({item.source for item in graph.imports
                   if item.target == module and item.symbol == symbol and not item.local
                   and item.source not in graph.extra})


def who(graph, spec):
    module, _, symbol = spec.partition(":")
    module = resolve(graph, module)
    rows = []
    todo, done = [(module, symbol or None, None)], set()
    while todo:
        target, name, via = todo.pop()
        if (target, name) in done:
            continue
        done.add((target, name))
        for item in graph.imports:
            if item.target != target or (name and item.symbol != name):
                continue
            rows.append((item.source, item.line, item.symbol, item.local, via))
        if name:
            todo.extend((source, name, source) for source in reexports(graph, target, name) if source != target)
    return sorted(set(rows), key=lambda row: (row[0], row[1]))


def statement_names(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    if isinstance(node, ast.Assign):
        return [target.id for target in node.targets if isinstance(target, ast.Name)]
    if isinstance(node, (ast.AnnAssign, ast.AugAssign)) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


def references(node, symbol):
    """Lines where `symbol` is named inside `node`, string annotations included."""
    lines = []
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id == symbol:
            lines.append(child.lineno)
        elif isinstance(child, ast.Constant) and isinstance(child.value, str) and symbol in child.value:
            try:
                parsed = ast.parse(child.value, mode="eval")
            except SyntaxError:
                continue
            if any(isinstance(n, ast.Name) and n.id == symbol for n in ast.walk(parsed)):
                lines.append(child.lineno)
    return lines


def uses(graph, spec):
    module, _, symbol = spec.partition(":")
    if not symbol:
        raise SystemExit("uses needs <module:symbol>")
    path = graph.paths[resolve(graph, module)]
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    rows = []
    for node in tree.body:
        names = statement_names(node)
        if symbol in names and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        owner = ",".join(names) or f"<module:{node.lineno}>"
        if names == ["__all__"]:
            owner = "__all__"
        for line in references(node, symbol):
            rows.append((owner, line))
    return sorted(set(rows), key=lambda row: row[1])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--package", action="append", metavar="PREFIX=DIR",
                        help="graph package (default: the core and the service)")
    parser.add_argument("--with", dest="extra", default="",
                        help="comma list of folders read for importers only: tests,tools,packaging,skills,unit")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("fanin", "fanout", "cycles", "orphans"):
        sub.add_parser(name)
    sub.add_parser("who").add_argument("spec")
    sub.add_parser("uses").add_argument("spec")
    args = parser.parse_args(argv)
    packages = PACKAGES
    if args.package:
        packages = tuple(tuple(item.split("=", 1)) for item in args.package)
    extra = [item for item in args.extra.split(",") if item]
    graph = build(args.root, packages, extra)
    edges = graph.edges()
    if args.command == "fanin":
        counts = defaultdict(set)
        for source, targets in edges.items():
            for target in targets:
                counts[target].add(source)
        for module in sorted(graph.paths, key=lambda m: (-len(counts[m]), m)):
            print(f"{len(counts[module]):4d} {module}")
    elif args.command == "fanout":
        for module in sorted(graph.paths, key=lambda m: (-len(edges.get(m, ())), m)):
            print(f"{len(edges.get(module, ())):4d} {module}")
    elif args.command == "cycles":
        components = strongly_connected(edges, graph.paths)
        print(f"components {len(components)} largest {len(components[0]) if components else 0}")
        for component in components:
            print(f"{len(component)}: {' '.join(component)}")
    elif args.command == "orphans":
        imported = {target for targets in edges.values() for target in targets}
        imported |= {item.target for item in graph.imports}
        for module in sorted(set(graph.paths) - imported):
            print(module)
    elif args.command == "who":
        rows = who(graph, args.spec)
        for source, line, symbol, local, via in rows:
            detail = f" {symbol}" if symbol else ""
            print(f"{source}:{line}{detail}{' (local)' if local else ''}{f' via {via}' if via else ''}")
        print(f"importers {len({row[0] for row in rows})}", file=sys.stderr)
    elif args.command == "uses":
        rows = uses(graph, args.spec)
        for owner, line in rows:
            print(f"{owner}:{line}")
        print(f"references {len(rows)}", file=sys.stderr)


if __name__ == "__main__":
    main()
