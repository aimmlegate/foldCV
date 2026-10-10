"""Versioned literal technology catalog and conservative name resolution."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


CATALOG_VERSION = "generic-1"


@dataclass(frozen=True)
class CatalogEntry:
    canonical_id: str
    category: str
    logo: str | None
    aliases: tuple[str, ...]


CATALOG = (
    CatalogEntry("golang", "language", "images/golang.png", ("golang", "go (golang)")),
    CatalogEntry("python", "language", "devicon/python.png", ("python",)),
    CatalogEntry("csharp", "language", "devicon/csharp.png", ("c#", "csharp", "c sharp")),
    CatalogEntry("cplusplus", "language", "devicon/cplusplus.png", ("c++",)),
    CatalogEntry("dotnet", "framework", "devicon/dotnet.png", (".net", ".net core", ".net framework", ".net standard")),
    CatalogEntry("postgresql", "database", "images/postgresql.png", ("postgresql", "postgres", "postges", "postrgesql")),
    CatalogEntry("redis", "database", "images/redis.png", ("redis",)),
    CatalogEntry("kafka", "messaging", "images/kafka.png", ("kafka", "apache kafka")),
    CatalogEntry("rabbitmq", "messaging", "images/rabbitmq.png", ("rabbitmq",)),
    CatalogEntry("kubernetes", "platform", "images/kubernetes.png", ("kubernetes",)),
    CatalogEntry("docker", "platform", "devicon/docker.png", ("docker",)),
    CatalogEntry("php", "language", "images/php.png", ("php",)),
    CatalogEntry("nodejs", "runtime", "images/nodejs.png", ("node.js", "nodejs")),
    CatalogEntry("grpc", "framework", "devicon/grpc.png", ("grpc",)),
    CatalogEntry("linux", "platform", "devicon/linux.png", ("linux",)),
    CatalogEntry("fastapi", "framework", "devicon/fastapi.png", ("fastapi",)),
    CatalogEntry("djangorest", "framework", "devicon/djangorest.png", ("django rest framework", "django rest framework (drf)")),
    CatalogEntry("grafana", "observability", "devicon/grafana.png", ("grafana",)),
    CatalogEntry("kibana", "observability", "devicon/kibana.png", ("kibana",)),
)
BY_ID = {entry.canonical_id: entry for entry in CATALOG}
_ALIASES = {alias: entry.canonical_id for entry in CATALOG for alias in entry.aliases}
_VERSION = re.compile(r"\s+(?:v)?(\d+(?:\.\d+)*(?:[-+][a-z0-9.]+)?)$", re.I)


@dataclass(frozen=True)
class ResolvedTechnology:
    canonical_id: str | None
    display: str
    version: str | None
    status: str  # catalog, ambiguous, or unknown


def normalize_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def resolve_technology(display: str) -> ResolvedTechnology:
    name = normalize_name(display)
    if not name:
        return ResolvedTechnology(None, display, None, "unknown")
    if name.startswith("microsoft "):
        name = name[len("microsoft "):]
    match = _VERSION.search(name)
    version = match.group(1) if match else None
    base = name[:match.start()] if match else name
    if base == "go" and version:
        base = "golang"
    if base in {"go", "drf", "r", "node"}:
        return ResolvedTechnology(None, display, version, "ambiguous")
    canonical_id = _ALIASES.get(base)
    return ResolvedTechnology(canonical_id, display, version,
                              "catalog" if canonical_id else "unknown")


def canonical_id(display: str) -> str | None:
    return resolve_technology(display).canonical_id
