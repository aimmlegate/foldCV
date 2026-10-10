# Test strategy

Test every automatable behavior, data invariant and error path in the first
release. Tests ship with each implementation task. T16 audits the complete system;
it is not a deferred testing phase. The current wireframe is the interface base,
but tests target user behavior and data contracts, not its particular DOM tree.

This document specifies future work. It does not claim the application or these
suites already exist. Existing prototype policy tests remain a regression baseline.

## Required layers

- Unit tests for pure rules, validation, state transitions and context selection.
- Property tests for date unions, stable ordering, serialization and revisions.
- Contract tests for Python models, exported schemas, browser validators and CLI
  event decoding. Accepted and rejected examples must agree across languages.
- Integration tests with real parsers, filesystem operations, a fake CLI process
  and real DOCX/PDF conversion. Mocking the renderer does not test document output.
- Browser component and end-to-end tests for the core workflow and its failures.
- Document visual regressions using fixed fonts and converter versions.
- Explicit live-CLI evaluations for model behavior and runtime properties that
  fakes cannot establish. They are separate from ordinary CI.

No test may need real candidate data, provider credentials or a subscription in
ordinary CI. Block outbound provider traffic there. Real converters and local
fake subprocesses are allowed. The only live-provider test job is explicit and
has a fixed sample set, model, operation allowance and timeout.

## Required case matrix

These IDs form a release checklist. Each implemented requirement links to actual
test names in `tests/requirements.json`; each unimplemented requirement remains
visible. A matrix entry alone is not evidence that its tests exist or pass.

| ID | Area / implementation task | Required assertions |
| --- | --- | --- |
| C01 | Contracts / T01 | Valid and invalid fixtures agree in Python/browser; missing and extra fields, unsupported versions, broken IDs and impossible dates fail; generated contracts have no drift. |
| X01 | Extraction / T07 | PDF, DOCX, TXT, Markdown and pasted text; Cyrillic, Unicode normalization, columns, tables, line wraps, repeated headers, DOCX headers/footers and image-only pages; exact originals survive. |
| X02 | Extraction errors / T07 | Empty, encrypted, truncated, malformed, unsupported and oversized input; mixed scan pages and unsupported shapes create visible gaps; no silent truncation or inference fallback. |
| F01 | Facts and provenance / T10 | Source IDs resolve; overlays preserve originals; user assertions have user origin; literal fields cannot be overwritten by proposed facts; duplicates and ambiguous job associations remain accounted for. |
| P01 | Dates and experience / T02 | Concurrent/duplicate/nested intervals, leap dates, year/month precision, missing as-of, ongoing work, invalid periods, subproject bounds and the exact 15-year cutoff. |
| P02 | Technologies and presentation / T02, T11 | Alias/version handling, ambiguous short names, global-only skills, unknown tools, missing logos, max eight, stable priority/ties, grouping, early-career formatting and explicit user overrides. |
| G01 | Generation boundary / T03, T10–T12 | Normal path has two logical content operations, rewrite one, deterministic paths zero; failed normalization cannot start drafting; only prose uses generation; payload excludes unrelated data. |
| G02 | CLI protocol / T08 | Partial UTF-8/JSONL chunks, malformed events/results, unknown optional fields, duplicate completion, missing usage, excessive output, nonzero exit, auth/quota/model errors and bounded retry behavior. |
| G03 | CLI lifecycle / T00B, T08, T09 | Missing/wrong-version executable, native versus API-key login, safe argv/stdin, cancellation, process-tree cleanup, missing credentials, detach without global logout and no inference from status/idle work. |
| S01 | Local service / T03 | Input contracts, loopback/Host/Origin/session checks, typed sanitized errors, disconnected clients, operation limits and no completed-project retention. |
| U01 | Editor / T04, T12 | Manual edits, lock/unlock, one-step undo, visibility, typed fact changes, dependency invalidation, source display, apply/discard and safe display of untrusted text. |
| U02 | Races / T06, T12, T15 | A late proposal cannot overwrite edits; changes to supporting facts invalidate it; an old render cannot replace/export the current revision; cancelled results never apply. |
| D01 | DOCX content / T00, T05 | Editable paragraphs/runs/tables, Unicode, dates, metrics, logos, fonts, optional sections, long sidebar and multi-page content; no image-only Word wrapper. |
| D02 | PDF/layout / T00, T05 | Complete text, known page geometry and no unexpected clipping/blank pages; approved page-image baselines; unavailable fonts/converter and conversion timeout fail visibly. |
| A01 | Project archive / T14 | Save/open equality for sources, facts, edits, locks, review state, undo, template and optional renders; partial projects and explicit v2 migration; zero generation on reopen. |
| A02 | Archive rejection / T14 | Wrong hash, missing file, traversal, absolute paths, symlinks, duplicate entries, excessive expansion/size, unknown version and executable template content fail before use. |
| E01 | Export gate / T13, T15 | Missing essential facts/jobs and broken references block documents; justified exclusions remain valid; revision-bound acknowledgments expire; project saving still works after errors. |
| E02 | Export consistency / T06, T15 | PDF download equals the current preview bytes; DOCX and PDF refer to one immutable snapshot; stale preview is visibly stale; export rebuilds only when needed. |
| R01 | Data lifecycle / T16 | No source content in logs/errors/browser storage/CLI history; cleanup on success, failure, cancellation and next startup after a crash; unrelated files/history remain untouched. |
| B01 | Browser workflow / T06, T17 | Import → text/facts → edit → scoped rewrite → review → PDF/DOCX/project download → reopen; keyboard labels/focus, busy/error states and narrow-window usability. |
| N01 | Performance and limits / T17 | Local edit responsiveness, extraction/render time, cold/warm conversion, input/output memory bounds, call counts and reported tokens; measured on a declared fixture set and environment. |
| L01 | Packaging / T17 | Fresh install/start/stop, absent CLI or converter, fixed fonts/assets, temporary paths, executable paths with spaces and process cleanup on every claimed target OS. |

## Independent fixtures and expected results

Use synthetic resumes with a separately reviewed manifest of expected jobs,
dates, metrics, qualifiers, technologies and omissions. Do not derive expected
results by running the same production function under test. Store original bytes,
their hashes and small expected data files where useful.

Include short and long resumes, nested projects, overlapping jobs, sparse fields,
duplicate technology names, uncommon tools and important nonnumeric achievements.
Preserve examples such as "built a team from zero to five" versus "worked in a
team of five" and "up to 2000 per day" versus "2000 in total."

The supplied human outputs can contain newer facts than the inputs. They are
layout references, not unconditional factual truth. Annotate expected content
from each exact source revision. Keep private examples outside source control,
CI logs, browser traces and uploaded failure artifacts.

Freeze the clock/as-of date and random seeds. Use isolated temporary roots and
fixture credentials that cannot authenticate. Never edit the real user's CLI
config, credential store or existing session history in an automated test.

## Property and mutation cases

- An interval union is order-independent, idempotent, nonnegative and no larger
  than the sum of its intervals. Compare small generated cases with a simple
  independent set-of-months oracle.
- Adding the same project twice does not increase experience. Changing prose
  does not alter canonical dates, source bytes or facts.
- Ranking is stable for ties and repeated inputs, respects explicit overrides
  and never includes more than eight eligible focus technologies.
- Archive round trips preserve semantic state and exact source bytes. Optional
  render absence changes only render readiness. Migrations preserve old data,
  are versioned, and do not call a model implicitly.
- A scoped proposal changes only its addressed block. Unrelated blocks and locks
  remain equal. Undo restores text, provenance, locks and relevant review state.
- Deliberately remove a job/fact/reference, corrupt a hash, alter a duration or
  invalidate a proposal revision: the corresponding check must fail for the
  correct reason. Exercise all documented blocking and warning dispositions.

These tests check defined structural and policy invariants. A fact ID attached
to misleading prose is not proof of semantic support. Detect known semantic
loss cases in live evaluations and retain human source review for general prose.

## CLI and failure testing

Provide an executable fake CLI with scripted events, output fragments, exit
codes, delays and child processes. It accepts the same process contract as the
real adapter. Assert input travels on stdin and is absent from argv and logs.
Test paths and source text containing spaces, quotes, Unicode and shell syntax
as inert data. Do not invoke a shell to make those tests pass.

Inject clocks and completion signals for timing/race tests; avoid long sleeps.
Test cancellation before spawn, during input/output, after completion and during
render/export. Force the exact event order needed for stale-result tests. Exercise
both a graceful exit and a child that requires forced termination.

Keep transport errors, invalid structured output and user retries separate. At
most one automatic application repair/retry is allowed per operation. Do not
equate that limit with retries hidden inside the provider's CLI. Test the app's
counting with fakes and measure the real CLI separately.

## Document testing

Use the actual DOCX writer and pinned LibreOffice converter in a required test
job. Validate DOCX XML structure and extracted content, edit a paragraph through
a document library, reconvert and assert the edit appears. This checks practical
editability in addition to the presence of text in the ZIP.

Compare each synthetic PDF page with an approved raster baseline in a fixed
font/converter environment. Set a small documented tolerance for raster noise;
do not raise it to hide clipping or missing text. Pair visual checks with text,
page-count and geometry checks. A baseline update includes the old/new diff and
a reason; never accept changed screenshots automatically.

Repeated DOCX/PDF builds can differ in timestamps or packaging metadata. Compare
normalized structure, text and page renders for regeneration. Exact byte equality
is required specifically between the displayed PDF and its download from the
same render, and for preservation of source files. Do not demand raw ZIP equality
for separately regenerated documents.

Word and LibreOffice can render the same DOCX differently. Keep a release check
in each supported reader for pagination and ordinary editing. Automated tests
do not replace this reader-specific check or final visual review of new layouts.

## Zero-generation tests

Run extraction, deterministic fact editing, policy calculation, source review,
rendering, export and reopening with `ForbiddenContentProvider`, which raises on
any call. The tests must exercise the real operation services, not only isolated
helpers. CLI access itself must not be required for these paths.

An import-boundary test prevents deterministic modules from importing or receiving
the generation provider. A counting fake asserts two logical initial content
operations and one scoped rewrite. Changing fields, refreshing PDF, downloading,
opening settings and waiting idle add zero. Reopening accepted facts or retaining
source prose skips the corresponding content operation.

## CI and release gates

T01A establishes these jobs before feature implementation:

1. Fast checks on every change: static/type checks, schema drift, unit/property/
   contract tests, editor state/component tests and import boundaries.
2. Integration checks on every change to application behavior: real extractors,
   fake CLI, archive/privacy tests and real DOCX/PDF render regressions. These
   required jobs install dependencies; missing LibreOffice is a failure, not a
   passing skip. Use synthetic data for all failure artifacts.
3. Browser workflow tests with the real local service and fake CLI. Cover successful
   use, quota/invalid output, cancellation, stale results and archive round trips.
   Test the declared browser and supported OS matrix before release; record any
   untested platform instead of advertising it.
4. Live CLI/model evaluation after relevant prompt/model/CLI changes and before
   enabling a new version. Trigger explicitly with bounded allowance. Keep it
   separate from deterministic pass/fail CI so provider outages are identifiable.

Publish branch coverage and the requirement-to-test map. Every reachable branch
of deterministic business rules and every documented failure/recovery path needs
an assertion. Review uncovered application branches explicitly; do not exclude
difficult code to improve a percentage. Generated contracts and third-party code
are checked at boundaries, not counted as our authored test coverage.

Do not test trivial getters, styling details or implementation call order merely
to inflate coverage. Test their observable behavior through the relevant feature.
A high coverage percentage does not establish semantic fidelity or good layout.
New bug fixes include a regression that fails without the fix. Flaky tests are
fixed or recorded with a specific unresolved release condition, not hidden by
unlimited retries or routine skip markers.

Each task is done only when its mapped positive, boundary and negative cases pass.
Document manual judgments, live checks not yet run, and remaining platform gaps.
Local test entry points and CI jobs must run the same suites and fail on zero
collected tests. Preserve the existing prototype regression suite during migration.

## Model evaluations

Test models against source-derived fact annotations, not exact rewritten sentences.
Record schema validity, required-fact recall, invented material claims, preservation
of units/qualifiers/ownership, operator edits, latency and reported token use.
Treat a fabricated material claim or missing essential fact as a failed evaluated
case. Run selected cases more than once to expose variance, and distinguish observed
failure rates from guarantees about all future inputs.

Use synthetic cases for public artifacts and a separate private held-out set for
editorial quality. The three examples used to develop the rules are regressions,
not held-out evidence. Human review remains necessary for ambiguous prose and
document appearance. Do not add a second paid model as an automatic test judge
in the production path.
