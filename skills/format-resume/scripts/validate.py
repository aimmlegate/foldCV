"""Validate payload structure and literal evidence, not semantic entailment."""

import argparse
import json
import re
import unicodedata
from pathlib import Path

ICONS = {"golang", "postgresql", "redis", "kafka", "rabbitmq", "kubernetes", "php", "nodejs"}
SIDEBAR = {"ОБРАЗОВАНИЕ", "СЕРТИФИКАТЫ", "КУРСЫ", "ЛОКАЦИЯ", "ЯЗЫКИ"}
GROUPS = {"ЯП, ФРЕЙМВОРКИ, БИБЛИОТЕКИ", "СУБД, ИНСТРУМЕНТЫ",
          "ИНФРАСТРУКТУРА, ТАСК-МЕНЕДЖЕРЫ", "ИНФРАСТРУКТУРА", "ЯП, СУБД", "ОС"}


def normalize(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def validate(data, source):
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    require(data["template"] == "generic-v1", "Unknown template")
    pages = {p["page"]: normalize(p["text"]) for p in source["pages"]}
    evidence = data["evidence"]
    require(isinstance(evidence, dict) and evidence, "Missing evidence")
    for key, item in evidence.items():
        quote = normalize(item["quote"])
        require(bool(quote) and quote in pages.get(item["page"], ""),
                f"Evidence {key}: quote not found on page {item['page']}")

    count = 0

    def statement(item, label, optional=False):
        nonlocal count
        if optional and item is None:
            return
        require(isinstance(item, dict), f"{label}: expected a statement")
        require(isinstance(item.get("text"), str) and bool(item["text"].strip()), f"{label}: empty text")
        refs = item.get("sources")
        require(isinstance(refs, list) and bool(refs), f"{label}: missing sources")
        require(all(isinstance(r, str) and r in evidence for r in refs), f"{label}: unknown evidence")
        count += 1

    def statements(items, label):
        require(isinstance(items, list), f"{label}: expected a list")
        for i, item in enumerate(items):
            statement(item, f"{label}[{i}]")

    for key in ("name", "title", "summary"):
        statement(data["candidate"][key], f"candidate.{key}")
    require(isinstance(data["focus"], list) and len(data["focus"]) <= 8, "At most eight focus items")
    for item in data["focus"]:
        statement(item["label"], "focus.label")
        statement(item["duration"], "focus.duration", optional=True)
        require(item["icon"] is None or item["icon"] in ICONS, "Unknown focus icon")
    for item in data["sidebar"]:
        require(item["title"] in SIDEBAR, "Unknown sidebar heading")
        statements(item["items"], "sidebar.items")
    for project in data["projects"]:
        for key in ("company", "period", "role", "stack", "description"):
            statement(project[key], f"project.{key}", optional=key in {"stack", "description"})
        statements(project["tasks"], "project.tasks")
        statements(project["results"], "project.results")
    for item in data.get("earlier_experience", []):
        statement(item["summary"], "earlier_experience.summary")
    statements(data["achievements"], "achievements")
    for group in data["skill_groups"]:
        require(group["title"] in GROUPS, "Unknown skill group heading")
        statement(group["items"], "skill_group.items")
    for key, fields in (("review", ("field", "issue", "decision")), ("omitted", ("field", "reason"))):
        require(isinstance(data[key], list), f"{key}: expected a list")
        for item in data[key]:
            require(all(isinstance(item.get(f), str) and item[f] for f in fields), f"Invalid {key} item")
    return {"statements": count, "evidence_excerpts": len(evidence),
            "review_items": len(data["review"]), "semantic_review_required": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", type=Path)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    result = validate(json.loads(args.payload.read_text()), json.loads(args.source.read_text()))
    print(json.dumps(result, indent=2))
