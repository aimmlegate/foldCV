# Template authoring reference

A FoldCV template is one YAML file in the short form (`schema_version: 4`). It
describes the page layout, the text styles, the blocks of the document, what an
import extracts into each block and the facts each block records. The app
expands the short form to the full form (`schema_version: 3`) and compiles it;
`check_draft` runs that compiler. The shipped templates `generic-two-column`
and `generic-one-column` are complete working examples: read one with
`read_template` before you change a draft.

## YAML rules

- Plain YAML only: no anchors or aliases (`&`, `*`), no tags (`!`), string
  keys, no duplicate keys.
- `true` and `false` are the only booleans. Quote any other value YAML would
  read as a boolean, a date or a special number: `'yes'`, `'2024-01-01'`.
- Quote colors (`'#EFEFEF'`): `#` starts a comment. Write `'null'` in quotes
  inside a type list (`type: [string, 'null']`).
- Comments are allowed; they are kept only in the saved text.

## Top-level keys

All of these are required: `schema_version`, `template`, `model`, `blocks`,
`style`, `layout`, `source`, `content_definitions`, `fact_types`, `operations`,
`assets`, `provenance`. Unknown keys are refused.

- `template`: `id`, `revision`, `name`, `default_locale` (`ru`). The id uses
  letters, digits, `.`, `_`, `-` and starts with a letter or digit. A saved
  template keeps its id; a changed text needs a new revision.
- `model`: `extract` and `rewrite` are lists of instructions for every block;
  `permission: allowTextRewrite` is the only value. Rewrite instructions apply
  only when the user allows rewriting at import.
- `source`: `retain_original: true` and `retain_unmapped_facts: true`, fixed.
- `provenance`: free notes (a mapping). Keep it; it does not change the result.

## Field types (`schema`, `fields`, `content_definitions`)

- `string`: a non-empty string. `boolean`, `integer`, `number`: plain types.
- A name from `content_definitions`: `text`, `date`, `period`, `terms`,
  `texts` and `role_family` are defined in both shipped templates. `text` is a
  non-empty string or null; `date` is `{raw, year, month}` or null; `period` is
  `{raw, start, end, ongoing?}`; `terms` is `{items: texts}`; `texts` is a
  list of strings.
- `[X]`: a list of X. `{list: X, maxItems: 8}`: a list with array limits.
- A mapping: an object with these fields, all required. `name?:` lets that
  field be null; it works for a mapping or a plain type
  (`place?: {city: text}`, `ongoing?: boolean`) and is refused for a named
  type (`name?: text`).
- A mapping with `type`, `$ref`, `anyOf`, `enum` or `const` is a JSON schema
  kept as written, for example
  `{type: string, minLength: 1, maxLength: 40, pattern: '^[^,;]+$'}`.
- A block schema written as a YAML list of one mapping (`- institution: text`)
  is a list of objects; the block then shows one entry per item.

## Blocks

A block is one section of the document. Keys: `id`, `region`, `order`,
`schema`, `facts`, `extract`, `rewrite`, `review`, `checks`, `mode`,
`operation`, `when`, `per_entry`, `selectors`, `depends_on`, `view`. `id`,
`region`, `order`, `schema` and `view` are always needed; unknown keys are
refused.

- `id`: unique among blocks and operations.
- `region`: `header`, `sidebar` or `main`; the region must exist in
  `layout.regions`. `order`: an integer; blocks of one region show in order.
  Two blocks in one region with the same order are refused, unless both have a
  `when` on the same operation with different values (only one of them shows).
- `extract`: instructions for this block. `rewrite`: `fields` (pointers such as
  `/text` or `/*/tasks`) and `instructions` for rewriting those fields.
- `mode`: `model` by default (a model reads the imported document). `derived`
  takes its content from an operation (`other_projects` in the shipped
  templates).
- `when: role-branch = technical`: the block shows only on that branch of a
  `select_role_branch` operation; the value must be its `matched` or
  `otherwise`.
- `per_entry: true`: the import first lists the entries, then extracts them in
  parallel groups. Only for a model block whose schema is a list without
  `maxItems`, `minItems` or other list limits (`projects` uses it).
- `selectors` default to `source:all`; `depends_on` defaults to none. Leave
  both out.

### Checks and review

Every block gets an evidence check and a support check. `review:` is a list of
extra support instructions, read before the standard one. `checks:` as a
mapping adds checks of a kind with an instruction:

```yaml
checks:
  claim_ownership: Preserve source employer and project ownership.
  task_result_separation: Distinguish performed tasks from achieved effects.
  attribution: Keep personal/team attribution and exact numeric bounds.
```

Kinds: `content_schema`, `evidence_identity`, `protected_values`,
`claim_ownership`, `complete_assignment`, `semantic_support`,
`task_result_separation`, `attribution`. `checks:` as a list replaces the full
list; do not use that form.

### Facts mapping

Facts are the records an import keeps beside the document text. A block names
the fact types it fills:

```yaml
facts:
  education: [institution, graduation_year, specialization, degree]
  education_place (extension_of): [place/city]
```

- `type: [fields]`: the item fields this fact type records.
- `type (relation): [nested/field]`: a part linked to the item, for a list
  block. The fact type must declare that relation (`relations:
  [extension_of education]`). Relations: `extension_of`, `owned_by`,
  `related_to`.
- `path=field`: the fact field has another name (`period/ongoing=present`,
  `items/*=display`).
- Without `facts:` the item's own fields record a fact type named like the
  block: `courses`, `location`, `opensource`, `portfolio` and `summary` work
  this way. A schema that is only a named type (`schema: terms`) needs
  `facts:`. Renaming such a block needs a `facts:` line that names the old
  fact type, or a fact type of the new name.
- A field shape must match the fact type's field shape. One item can be
  filled by one fact type only; nested parts go to extension types, as
  `project (extension_of)` in `projects`.

### Fact types

```yaml
- id: education
  fields:
    institution: text
    graduation_year: date
  builtin: education
  builtin_fields:
    institution: institution
    graduation_year: completion
- id: education_place
  fields:
    city: text
  relations:
  - extension_of education
```

`builtin` links a fact type to the app's own records; `builtin_fields` maps its
fields to theirs. A block that binds a field of such a type must bind only
fields listed in `builtin_fields`. Kinds and their fields, for example:
`candidate` (name,
title, location), `employment` (employer, role, and `start`, `end`, `present`
written `field @period`), `technology` (display, canonicalId, experience),
`education` (institution, qualification, specialty, completion as a date),
`language` (language, level), `certification` (name, issuer, date as a
date), `claim` (value), `detail` (value).

Keep the fact types of the base template. New ones are needed only for a new
kind of section.

## Operations

Operations are code steps the template switches on. The shipped templates use:

- `partition_employment` (`project-window`): when rewriting is allowed, jobs
  whose every period ended more than `years` ago move from the `detailed`
  block to the `compact` block. The compact block
  is `mode: derived` with `operation: project-window` and must show `/items`
  with a `join_items`, `bullets` or `tags` node.
- `select_role_branch` (`role-branch`): picks `matched` for the listed role
  families, else `otherwise`; `classification` names the fact field it reads,
  and its input block must bind that field (`identity` binds `role_family`).
- `assign_skills` (`technical-skills`, `role-skills`): spreads technologies
  over its `groups`. Every group is an input, all groups have the same `when`,
  and `uncertain_group` is one of them. Two assignments must be on different
  branches of one role operation.
- `format_period` (`source-periods`): the period separator and the label of a
  current job (`по настоящее время`).

Removing a block that an operation names breaks the check; change or remove the
operation with it. Moving a block to another region or order does not.

## Views

```yaml
view:
  heading: band
  title: {ru: ПРОЕКТЫ, en: PROJECTS}
  inset: 10.5
  item_gap: 12.57
  nodes:
  - type: join_fields
    fields: [/company, /project/name]
    separator: ' — '
    style: project
  fallback_style: body
```

- `heading`: `none`, `plain` (default) or `band` (the heading on a colored band
  of `style.section_band`). `title`: the heading per locale.
- `inset`: left indent of the block content in points; `item_gap`: space
  between entries in points; both default to 0.
- `fallback_style`: the style of a line no node covers. A view without nodes
  needs it.
- `mode` follows the schema (`items` for a list, `object` otherwise); leave it
  out.
- Field pointers in nodes start at one entry for a list block (`/company`) and
  at the block content otherwise (`/text`, `/items`). `/project/name` reaches
  into a nested object.
- Every `style`, `detail_style` and `fallback_style` must be a name in
  `style.text`; every `background` a name in `style.colors`.

Node types:

| type | keys | shows |
|---|---|---|
| `text` | `field`, `style`, `header_slot` | one scalar field or a date |
| `join_fields` | `fields`, `separator`, `style`, `header_slot` | several fields on one line |
| `join_items` | `field`, `separator`, `item_field`, `style` | a list on one line |
| `bullets` | `field`, `item_field`, `style` | a list as bullets |
| `tags` | `field`, `separator`, `item_field`, `background`, `style` | a list as chips on a colored background |
| `period` | `field`, `style` | a period with raw/start/end/ongoing |
| `link` | `name_field`, `url_field`, `style` | a name with its URL |
| `focus_entry` | `name_field`, `experience_field`, `style`, `detail_style` | a technology with an icon and its experience |

Every node also takes `prefix` and `label`, text per locale. The shipped
templates use `prefix` on a `join_fields` line (`{ru: 'Роль: ', en: 'Role: '}`)
and `label` on `bullets` (`{ru: 'Задачи:', en: 'Tasks:'}`). `item_field` picks a
field of each list item (`/display`, `/value`). Any other key not in the row of
its node type is refused.

`header_slot: name` and `header_slot: profession` mark the header lines that
`style.header.name_top` and `profession_top` place. Each slot is used once, on
a `text` or `join_fields` node of a block in the `header` region. Give every
header node a slot: the header holds the name line, the title line and the
logo, nothing else.

## Style

All sections are required, even when no block uses them.

- `page`: `width` and `height` in points (A4 is 596 × 842); `first_body_top`,
  `continuation_body_top` (where the body starts on page 1 and later pages) and
  `body_bottom`; the body must fit inside the page.
- `fonts`: token → font asset id (`bold: SourceSansPro-Bold`). Only `.ttf` or
  `.otf` assets are fonts.
- `colors`: name → `'#RRGGBB'`.
- `text`: style name → `font` (a token from `fonts`), `size`, `line_height`,
  `color` (a name from `colors`). Style names are free; the shipped templates
  use `name`, `profession`, `section`, `project`, `body`, `support`,
  `emphasis`, `tag`, `footer`.
- `header`: `name_top`, `profession_top`, `overflow:
  grow_header_and_move_body`, `logo` (`asset`, `x`, `top`, `width`, `height`,
  `fit: contain`) or null, `divider` (`x1`, `x2`, `y`, `width`, `color`,
  `follow_header: true`) or null.
- `section_band`: `height`, `background`, `text_inset`, `heading_style` (the
  text style of section headings).
- `bullets`: `marker`, `marker_offset`, `text_offset`, `marker_size`.
- `focus`: `icon_catalog` (an asset id or null), `icon_x`, `icon_width`,
  `icon_height`, `text_x`, `minimum_row_height`, `icon_fit: contain`,
  `missing_icon` (`initial` or `text_only`).
- `footer`: `text`, `center_x`, `baseline_y`, `style`, `repeat: every_page`.

Use the `regular` and `bold` faces of Source Sans Pro for text: Google Docs
knows only these two and replaces Light, Semibold and Black with Arial. Map a
light or semibold sample face to the nearest of the two.

## Layout

```yaml
layout:
  regions:
  - {id: header, x: 21.26, width: 450, flow: first_page_header}
  - {id: sidebar, x: 26.51, width: 118.5, flow: independent_column}
  - {id: main, x: 150.26, width: 430, flow: independent_column}
  reading_order: [header, sidebar, main]
  pagination:
    allow_project_split: true
    keep_heading_with_next: true
    allow_more_pages: true
    truncate_content: false
```

- Regions are `header, sidebar, main` or `header, main`, in that order;
  `reading_order` repeats the list. The header takes `first_page_header`, the
  others `independent_column`.
- `x + width` of a region stays within the page width; sidebar and main must
  not overlap. The sidebar stands left or right of main as its `x` says: a
  sidebar right of main has `x` at or past the end of main (`main.x +
  main.width`); the page, the DOCX and the PDF follow it.
- One column: drop the sidebar region and move its blocks to `main` with free
  orders.
- `pagination`: only `keep_heading_with_next` is a choice; the other three
  values are fixed as shown.

## Assets

```yaml
assets:
  SourceSansPro-Bold: assets/SourceSansPro-Bold.ttf
  logo:
    path: assets/foldcv.png
    role: logo
  technology-icons: assets/technology-icons.json
```

`id: path`; the role and type follow the extension (`.ttf`, `.otf` font;
`.png`, `.jpg` icon; `.json`, `.txt` catalog); a mapping with `path` and
`role` overrides the role. The shipped templates declare the logo that way,
with `role: logo`; keep that form. Keep the asset list of the base template: its files come with
it. A new path must name a file of the app's shipped template folder, inside
it and without `..`. On the public build the folder holds in `assets/`:
`SourceSansPro-Light.ttf`, `-Regular`, `-Semibold`, `-Bold`, `-Black`, the
italics `SourceSansPro-LightIt.ttf`, `-It` (Regular), `-SemiboldIt`,
`-BoldIt`, `-BlackIt`, `SourceSansPro-LICENSE.txt`,
`source-sans-provenance.json`, `foldcv.png` (the FoldCV logo),
`technology-icons.json` (the Focus icon catalog) and `devicon-LICENSE.txt`.

## What the template cannot express

- Photos: no node shows an image of the person. The header can show one logo
  from a shipped asset, or none.
- Free tables: content flows in the header and one or two columns; there is no
  table node and no third column.
- Contacts or other lines in the header: it holds the name, the title and the
  logo.
- Own fonts and images: assets resolve only against shipped files; the user
  cannot add a file.
- Text boxes, shapes, lines other than the header divider, and background
  images.
- A different color or font for one word: a whole node has one style.
- A header on every page: the header region is on the first page only; the
  footer repeats one fixed text on every page.

Name each of these in the proposal summary with the nearest approximation you
used.
