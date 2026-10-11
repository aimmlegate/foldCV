# Payload contract

All displayed candidate text uses a statement object:

```json
{"text": "Rewritten statement", "sources": ["evidence-id"]}
```

`evidence` maps IDs to `{ "page": 1, "quote": "Literal input excerpt" }`.
Quotes are matched against the specified extracted page after whitespace
normalization. Cite every part of a combined claim. Quotes must support the
meaning, not just share keywords; the literal validator cannot establish this.

Required top-level fields:

- `template`: `generic-v1`.
- `candidate`: `name`, `title`, `summary` statements.
- `focus`: list of `{label: statement, icon: string|null, duration: statement|null}`.
  Icons: `golang`, `postgresql`, `redis`, `kafka`, `rabbitmq`, `kubernetes`, `php`, `nodejs`.
  These are explicit legacy IDs, not the full focus catalog. For Python, C#, .NET,
  Docker and other `policy.py` catalog labels, use null for automatic logo lookup.
- `sidebar`: list of `{title: string, items: statement[]}`. Titles are fixed labels:
  ОБРАЗОВАНИЕ, СЕРТИФИКАТЫ, КУРСЫ, ЛОКАЦИЯ, ЯЗЫКИ.
- `projects`: list of `{company, period, role, stack, description, tasks, results}`.
  The first three are required statements; `stack` and `description` may be null.
  `tasks` and `results` are lists of statements. Long stacks use newline-separated
  labeled groups, with comma-separated technology names within each group.
- `achievements`: list of statements for career-wide achievements.
- `skill_groups`: list of `{title: string, items: statement}`. Group titles:
  ЯП, ФРЕЙМВОРКИ, БИБЛИОТЕКИ; СУБД, ИНСТРУМЕНТЫ;
  ИНФРАСТРУКТУРА, ТАСК-МЕНЕДЖЕРЫ; ИНФРАСТРУКТУРА; ЯП, СУБД; ОС.
- `evidence`: source excerpt map.
- `review`: list of `{field, issue, decision}` strings, excluded from the PDF.
- `omitted`: list of `{field, reason}` strings, excluded from the PDF.

Use null or empty lists for unsupported optional data. Titles, punctuation,
section labels, logo, and corporate footer belong to the template and do not
require candidate evidence. Do not put private candidate data in the skill.
