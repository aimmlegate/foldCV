# FoldCV

Local resume editor. It imports a PDF, DOCX, TXT or Markdown resume, extracts its
facts into a template, lets you edit and rewrite the text, and exports DOCX.

Projects stay on your computer in `~/Library/Application Support/FoldCV`. Model work
runs through your own Codex or Claude CLI sign-in. FoldCV has no server of its own
and uses no API keys.

## Run from source

Verified on macOS arm64 with Python 3.13 and Node 22.14.

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm --prefix apps/web ci
npm --prefix apps/web run build
bash tools/install-local-renderer.sh
.venv/bin/python tools/run-local.py --experimental-cli
```

The launcher starts one local service on `127.0.0.1` and opens the browser. Stop it
with Ctrl-C. Without `--experimental-cli` the app works with no model calls. See
[local setup](docs/gui/local-setup.md) for details.

## Repository

| Path | Contents |
| --- | --- |
| `apps/web` | React and TypeScript frontend |
| `services/api` | FastAPI local service, CLI providers, import and assistant |
| `packages/resume_core` | Project storage, templates and DOCX rendering |
| `contracts` | Generated JSON Schemas and contract examples |
| `templates` | Bundled resume templates |
| `design/future-editor/visual` | Visual layer used by the frontend |
| `skills/format-resume` | Command-line skill and its assets |
| `tools` | Launcher, checks and benchmarks |
| `tests` | Python test suites |

## Private templates

Put a template YAML and its `assets/` folder into the ignored `templates/local/`. A local
run or desktop build lists it first and uses it as the default. A clean clone ships only
the bundled generic templates.

## Documentation

- [Architecture](docs/gui/architecture.md): service, storage, API, CLI adapter and rendering.
- [Contracts](docs/gui/contracts.md): versioned JSON contracts and their generation.
- [Local setup](docs/gui/local-setup.md): setup, launcher modes and CLI sign-in.
- [Testing](docs/gui/testing.md): suites, budgets, GUI checks and the benchmark.
- [Resume data in Git](docs/gui/git-data-policy.md): what may be committed.
- [Dependency notices](docs/gui/local-dependency-notices.md): third-party licenses.

## Tests

```sh
PYTHONPATH=services/api/src .venv/bin/python -m pytest -q -p no:cacheprovider
```

## Command-line skill

Original file → complete archive → selected resume JSON → fixed PDF.

The supplied outputs define the layout, not the candidate's facts. The skill
handles extraction and rewriting; Python checks preservation and renders the
layout.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python skills/format-resume/scripts/archive.py INPUT.pdf experiments/case --as-of 2026-10-10
```

Apply [the skill](skills/format-resume/SKILL.md) to every source unit. Complete
`archive.json` and create `view.json` using the
[archive contract](skills/format-resume/references/archive-contract.md). Keep
original bytes and extracted text unchanged. Do not supply reference candidate
facts to this step. Then run:

```sh
.venv/bin/python skills/format-resume/scripts/finalize.py experiments/case/view.json experiments/case/archive.json
.venv/bin/python skills/format-resume/scripts/check_archive.py experiments/case/view.json experiments/case/archive.json
.venv/bin/python skills/format-resume/scripts/render.py experiments/case/view.json output/pdf/resume.pdf --source experiments/case/source.json --archive experiments/case/archive.json
```

Render the resulting PDF to images and inspect every page before delivery.
The render command runs the archive checks before writing a version 2 PDF.
For another presentation, create a new view from the full archive, never from
the shortened PDF. Keep each accepted archive version with its matching view.

### Preservation and checks

- Keep original bytes, full page text, stable source units, all employment, and
  sourced technology catalogs, including details excluded from the PDF.
- Give every source unit a disposition and every omission a reason. A partly
  represented unit is condensed, not fully shown.
- Recheck the source hash and freshly extracted text. Reject missing coverage,
  missing jobs, unsupported dates, altered duration estimates, and lost numeric
  markers in essential recent duties/results.
- Limit focus to eight known technologies with logos. Estimate experience by
  merging dated project periods; bound current jobs by the source observation
  date. Global skills and undated subprojects do not establish duration.
- Focus the profile on recent projects, group long technology lists, and shorten
  jobs wholly older than 15 years into a comma-separated early-career paragraph.

These checks establish preservation and accounting, not semantic completeness.
Source classification and importance still need review. A cited paragraph can
contain several facts; a rewrite may retain its numbers while losing ownership,
qualifiers, or context. Check these against the complete source before delivery.
Experience estimates describe project exposure, not continuous full-time use.

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q -p no:cacheprovider skills/format-resume/tests
```

### Scope

- PDF with extractable text, TXT, and Markdown inputs. Other formats and scans
  need a separate extraction or OCR step.
- One fixed PDF layout with the supplied logo, reference technology icons,
  additional Devicon icons, and Source Sans Pro fonts. Unknown technologies are
  excluded from focus but can remain in project and global skill lists.
- Source-linked candidate statements and a separate review list.
- Private data and generated files stay in ignored `experiments/`, `tmp/`, and
  `output/` folders. The reusable skill contains no candidate records.
