"""Authored scope accounting and comparison from the canonical candidate."""

from dataclasses import dataclass
import json

from .agent_edits import Scope
from .agent_store import digest
from .assistant_proposals import reviewed_value
from .models.assistant_proposals import AssistantChangeV1
from .rich_dependencies import placements
from .rich_fields import inline_groups
from .rich_mutations import inline_text


@dataclass(frozen=True)
class Unit:
    reader: str
    kind: str
    value: object
    description: str = ""


def block_label(block):
    kind = {"paragraph": "Абзац", "heading": "Заголовок", "section": "Раздел", "table": "Таблица",
        "image": "Изображение", "code": "Код", "quote": "Цитата", "bullet_list": "Пункт списка",
        "numbered_list": "Нумерованный пункт", "checklist": "Пункт с отметкой"}.get(block.type, "Блок")
    text = block.content if isinstance(block.content, str) else " ".join("".join(inline_text(span) for span in spans) for _, spans in inline_groups(block))
    return kind + (" «" + text[:80] + ("…" if len(text) > 80 else "") + "»" if text else "")


def properties(value):
    labels = {"alignment": "Выравнивание", "textColor": "Цвет текста", "backgroundColor": "Фон", "level": "Уровень",
        "start": "Начало нумерации", "checked": "Отметка", "language": "Язык кода", "presentation": "Представление",
        "manualOrder": "Ручной порядок", "assetId": "Изображение", "alt": "Описание", "width": "Ширина", "height": "Высота",
        "colspan": "Объединение столбцов", "rowspan": "Объединение строк"}
    values = {"left": "слева", "right": "справа", "center": "по центру", "justify": "по ширине", "default": "обычный",
        "standard": "обычное", "focus": "выделение", "red": "красный", "blue": "синий", "green": "зелёный"}
    return "; ".join(f"{labels.get(key, key)}: {values.get(part, part) if isinstance(part, str) else part}" for key, part in value.items()
        if key not in {"recordId", "caption", "id", "revision", "row", "column"})


def units(workspace, scope, *, allowed=None, new_ids=()):
    allowed = allowed or Scope(workspace, scope)
    blocks = workspace.project.document.blocks()
    places = placements(workspace.project.document)
    labels = {block.id: block_label(block) for block in blocks}
    labels.update({region.id: {"header": "Шапка", "main": "Основная колонка", "sidebar": "Боковая колонка"}.get(region.role, region.role)
        for region in workspace.project.document.regions})
    included = {block.id for block in blocks if allowed.whole or block.id in allowed.complete
        or block.id in new_ids or any(key[0] == block.id for key in allowed.ranges)}
    positions = {key: places[key] for key in sorted(included)}
    result = {"scope:" + scope.kind: Unit("context", "structure", reviewed_value(positions))}
    if allowed.whole:
        for region in workspace.project.document.regions:
            result["region:" + region.id] = Unit("context", "structure", {"role": region.role,
                "blocks": [block.id for block in region.blocks]}, labels[region.id] + "\n" + "\n".join(labels[block.id] for block in region.blocks))
    referenced = set()
    for block in blocks:
        if block.id not in included:
            continue
        referenced.update(getattr(link, "record_id", None) for link in block.provenance)
        referenced.add(places[block.id][2])
        value = block.model_dump(mode="json", by_alias=True, exclude={"children", "content"})
        value["props"].pop("caption", None)
        value.update(children=[child.id for child in block.children], position=places[block.id])
        if block.type == "table":
            value["table"] = {"widths": block.content.column_widths, "headerRows": block.content.header_rows,
                "headerCols": block.content.header_cols, "rows": [row.id for row in block.content.rows]}
            for row_index, row in enumerate(block.content.rows):
                result[f"row:{block.id}:{row.id}"] = Unit(block.id, "structure", [cell.id for cell in row.cells], f"Строка {row_index + 1}: {len(row.cells)} ячеек")
                for index, cell in enumerate(row.cells):
                    cell_value = cell.model_dump(mode="json", by_alias=True, exclude={"content"})
                    cell_value.update(row=row.id, column=index)
                    result[f"cell:{block.id}:{cell.id}"] = Unit(cell.id, "structure", reviewed_value(cell_value),
                        f"Строка {row_index + 1}, ячейка {index + 1}. " + properties(cell_value))
        parent, previous, _ = places[block.id]
        description = labels[block.id] + "\nВнутри: " + labels.get(parent, "документа")
        description += "\nПосле: " + labels.get(previous, "начало") + "\n" + properties(value["props"])
        if block.type == "table":
            description += f"\nШирины: {block.content.column_widths}; строки заголовка: {block.content.header_rows}; столбцы заголовка: {block.content.header_cols}"
        result["block:" + block.id] = Unit(block.id, "structure", reviewed_value(value), description)
        for container, spans in inline_groups(block):
            referenced.update(getattr(span, "record_id", None) for span in spans)
            result[f"field:{block.id}:{container}"] = Unit(container if block.type == "table" else block.id,
                "field", reviewed_value(spans))
        if isinstance(block.content, str):
            result[f"field:{block.id}:content"] = Unit(block.id, "field", block.content)
    for record in workspace.project.facts.records:
        if allowed.whole or record.id in referenced or getattr(record, "job_id", None) in referenced:
            result["fact:" + record.id] = Unit(record.id, "fact", reviewed_value(record))
    if allowed.whole:
        values = reviewed_value(workspace.project.facts)
        values.pop("records")
        report = workspace.project.facts.extraction
        description = f"Удалённых записей: {len(workspace.project.facts.tombstones)}."
        if report:
            description += f" Извлечение: {'полное' if report.status == 'complete' else 'частичное'}; неразрешённых фрагментов: {len(report.unresolved)}."
        result["facts:collection"] = Unit("facts_collection", "fact", values, description)
    return {unit_id(key): value for key, value in result.items()}


def unit_id(key):
    return key if len(key) <= 256 else key.split(":", 1)[0] + ":" + digest(key)


def plain(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(plain(part) for part in value)
    if isinstance(value, dict):
        if value.get("type") == "link":
            return plain(value["content"])
        return value.get("text", "")
    return ""


def metadata(value):
    if isinstance(value, str):
        return [{"type": "code"}]
    result = []
    for span in value:
        item = {key: part for key, part in span.items() if key not in {"text", "content", "syncedFactRevision"}}
        if span.get("type") == "link":
            styles = []
            for part in span["content"]:
                if not styles or styles[-1] != part["styles"]:
                    styles.append(part["styles"])
            item["styles"] = styles
        if not result or result[-1] != item:
            result.append(item)
    return result


def metadata_text(parts):
    result = []
    marks = {"bold": "полужирный", "italic": "курсив", "underline": "подчёркнутый", "strike": "зачёркнутый", "code": "код"}
    for part in parts:
        text = "Ссылка: " + part["href"] + ". " if part.get("type") == "link" else ""
        if part.get("type") == "fact_field":
            text += "Связь с полем фактов «" + part["fieldKey"] + "». "
        styles = part.get("styles", {})
        groups = styles if isinstance(styles, list) else [styles]
        for group in groups:
            active = [label for key, label in marks.items() if group.get(key)]
            for key, label in (("textColor", "цвет текста"), ("backgroundColor", "фон")):
                if group.get(key, "default") != "default":
                    active.append(label + ": " + group[key])
            text += ", ".join(active) if active else "обычный текст"
        result.append(text)
    return "\n".join(result)


def fact_text(value):
    if isinstance(value, dict):
        if "rawText" in value:
            status = {"known": "известно", "unknown": "неизвестно", "unresolved": "не определено",
                "pending": "ожидает", "conflict": "конфликт"}[value["status"]]
            exact = value.get("value")
            detail = ""
            if isinstance(exact, dict):
                detail = "; значение: " + json.dumps(exact, ensure_ascii=False, sort_keys=True)
            return str(value["rawText"] or "") + " [" + status + detail + ("; будет отмечено исправлением пользователя" if value.get("userCorrected") else "") + "]"
        return "\n".join(text for key, part in value.items() if key not in {"evidence", "userCorrected"}
            and (text := fact_text(part)))
    if isinstance(value, list):
        return "\n".join(text for part in value if (text := fact_text(part)))
    return ""


def summary(unit):
    if unit is None:
        return ""
    if unit.description:
        return unit.description
    if unit.kind == "field":
        return plain(unit.value)
    if unit.kind == "fact":
        return fact_text(unit.value)
    return json.dumps(unit.value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def comparison(before, after):
    changes = []
    for key in sorted(before.keys() | after.keys()):
        if key.startswith("scope:"):
            continue
        old, new = before.get(key), after.get(key)
        if old is not None and new is not None and digest(old.value) == digest(new.value):
            continue
        kind = (old or new).kind
        if kind == "field":
            old_value, new_value = old.value if old else [], new.value if new else []
            if plain(old_value) != plain(new_value):
                changes.append(AssistantChangeV1(unitId=key, before=plain(old_value), after=plain(new_value), effect="wording"))
            if metadata(old_value) != metadata(new_value):
                changes.append(AssistantChangeV1(unitId=unit_id(key + ":format"), before=metadata_text(metadata(old_value)),
                    after=metadata_text(metadata(new_value)), effect="format"))
        else:
            previous, following = summary(old), summary(new)
            # Equal display text must not conceal changed precision, provenance or membership.
            if previous == following:
                previous += "\nСвойства: " + json.dumps(old.value if old else None, ensure_ascii=False, sort_keys=True)
                following += "\nСвойства: " + json.dumps(new.value if new else None, ensure_ascii=False, sort_keys=True)
            changes.append(AssistantChangeV1(unitId=key, before=previous, after=following, effect=kind))
    return changes
