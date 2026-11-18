"""The unified rules of the résumé builder: the owner's own list of requirements (2026-11-18), short, by block, in
the user's language. They say how a block is worded. The import writes a block the CV has no text for by them, and
the editor offers a block's rules as the text of a rewording request, where the user reads and edits them before
anything is sent.

Each template carries its own copy (`model.rules` for every block, a block's `rules`), so a template may word its
blocks its own way; the bundled templates hold this text as it stands here. A template with no rules at all (one
made before them) gets this text. The legacy import's prompts (`extract`, `rewrite`) are not read here."""

# What holds for every block.
STYLE = [
    'Имена и официальные названия компаний, продуктов и технологий — в принятом написании: FastAPI, Node.js, '
    'GitLab CI/CD, Kubernetes.',
    'Цифры, сроки, уровни и масштаб ответственности — только из исходных данных. Уровень Senior или Lead — только '
    'если он есть в исходных данных.',
    'Сроки: «1 год», «2 года», «5 лет».',
]

BLOCKS = {
    'summary': [
        'О себе: 2–3 предложения о специализации, релевантном опыте и ключевой экспертизе.',
        'Подробности и метрики остаются в карточках опыта.',
    ],
    'projects': [
        'Описание проекта — 1–2 предложения: что это за продукт и для кого он.',
        'Задачи: один пункт описывает одну зону ответственности. Пример: «Подготовка ежемесячных отчётов по продажам и '
        'сверка данных с CRM».',
        'Результаты: личный вклад и подтверждённый эффект. Пример: «Автоматизировал сверку данных и сократил подготовку '
        'отчёта с двух дней до четырёх часов». Если эффект неизвестен, описать выполненную работу.',
        'Обязанности — в задачах, назначение продукта или проекта — в описании.',
        'В русском тексте — «проверка кода», «развёртывание», «в реальном времени».',
    ],
    'career_highlights': [
        'Достижения: личный вклад и подтверждённый эффект, один пункт — одно достижение. Если эффект неизвестен, описать '
        'выполненную работу.',
    ],
}


def block_rules(block, definition=None):
    """The rules of one block as the lines of a request: the block's own, then the rules for every block. They are
    the template's when it has any, else the unified ones."""
    declared = next((value for value in definition.blocks if value.id == block), None) if definition is not None else None
    if definition is not None and (definition.model.rules or any(value.rules for value in definition.blocks)):
        return [*(declared.rules if declared is not None else []), *definition.model.rules]
    return [*BLOCKS.get(block, []), *STYLE]


def block_text(block, definition=None):
    return '\n'.join(block_rules(block, definition))
