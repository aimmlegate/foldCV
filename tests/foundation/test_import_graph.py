"""The import graph reads imports from the AST: fan-in, cycles and symbol-level importers and references."""

from tools import import_graph


def package(tmp_path):
    folder = tmp_path / "pkg"
    folder.mkdir()
    (folder / "__init__.py").write_text("")
    (folder / "alpha.py").write_text(
        "from .beta import Kept, helper\n"
        "\n"
        "def run():\n"
        "    from . import gamma\n"
        "    return gamma.value\n")
    (folder / "beta.py").write_text(
        "from pydantic import BaseModel\n"
        "\n"
        "class Ref(BaseModel):\n"
        "    path: str\n"
        "\n"
        "class Kept(BaseModel):\n"
        "    refs: list['Ref']\n"
        "\n"
        "class Dead(BaseModel):\n"
        "    name: str\n"
        "\n"
        "def helper():\n"
        "    return Kept(refs=[])\n")
    (folder / "gamma.py").write_text("import pkg.alpha\n\nvalue = 1\n")
    return import_graph.build(tmp_path, (("pkg", "pkg"),))


def test_fanin_and_cycle(tmp_path):
    graph = package(tmp_path)
    edges = graph.edges()
    assert edges["pkg.alpha"] == {"pkg.beta", "pkg.gamma"}
    assert edges["pkg.gamma"] == {"pkg.alpha"}
    assert import_graph.strongly_connected(edges, graph.paths) == [["pkg.alpha", "pkg.gamma"]]


def test_who_at_symbol_level(tmp_path):
    graph = package(tmp_path)
    assert [(row[0], row[2]) for row in import_graph.who(graph, "pkg.beta:Kept")] == [("pkg.alpha", "Kept")]
    assert import_graph.who(graph, "pkg.beta:Dead") == []
    # A function-level import and a module attribute both count.
    rows = import_graph.who(graph, "pkg.gamma:value")
    assert [(row[0], row[3]) for row in rows] == [("pkg.alpha", True)]


def test_uses_finds_string_annotations(tmp_path):
    graph = package(tmp_path)
    assert import_graph.uses(graph, "pkg.beta:Ref") == [("Kept", 7)]
    assert import_graph.uses(graph, "pkg.beta:Kept") == [("helper", 13)]
    assert import_graph.uses(graph, "pkg.beta:Dead") == []
