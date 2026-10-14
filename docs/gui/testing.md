# Test strategy

## Full-editor follow-up

D073–D077 and the NE contracts (including NE03A/NE03B) in the
[current prompt](prompts/03-native-editor-template.md) override conflicting
historical assertions below. Replace candidate-data exclusions, disabled history,
previous-block restore, fixed field membership and required legacy migration with
the newly agreed behavior. The Python renderer may change to support the measured
template and all supported rich content. Word macOS is the current visual/editing
target through a manual user gate; Windows is deferred. Durable reopen requires
a service restart, not just a browser reload. Verify mixed-version listing without
migration, one session history across document/facts, canonical education/language
ownership, image limits and explicit DOCX mappings. The left facts panel replaces the outline and its
explicit edits update linked document content. Employment overlaps remain valid
with subdued warnings; date cascades require preview/explicit apply and affect
only the necessary chain. Test per-job technology scope, synchronization/undo and
stale cascade responses. Keep applicable evidence, lifecycle, storage,
selection, IME and resource tests. Map replacements and remove deleted/renamed
test selectors with their implementation, including legacy exclusion regressions;
leave `tests/requirements.json` unchanged during planning. No new behavior or
replacement check is claimed as passed by this note.

D076 requires useful tests of observable behavior and concrete failure risks,
including relevant edge cases, rather than implementation mirrors or test counts.
Add a regression check for every review-discovered behavior defect, preferably
with a deterministic nonbrowser test that reproduces the failure before the fix.
For GUI-only defects, use reproducible T3 steps and record the checked revision,
expected/actual results and why an automated regression was not appropriate.
Documentation-only changes do not need artificial tests.

Do not develop, extend or execute automated browser scenarios for the NE runs;
the historical browser-test requirements below do not apply to this work. Use
the internal T3 browser for required GUI acceptance and retain useful Python,
Node state/contract, type/lint/build and affected rendering checks. The fast gate's
`npm run test:browser -- --list` only validates mapped names and is allowed; it
does not execute scenarios. Preserve historical specs/results, maintain obsolete
selectors and new nonbrowser mappings, and record T3 evidence separately. Do not
label an unrun browser suite passed or remove coverage merely to bypass the map.

D077 freezes the [rich cases](handoffs/CLI-GUI-CYCLES/rich-contract.md),
[date examples](handoffs/CLI-GUI-CYCLES/timeline-contract.md) and
[execution details](handoffs/CLI-GUI-CYCLES/execution-contract.md).
NE01 updates contradictory U01/A01/D01/P02 descriptions/selectors while retaining
the 22 existing IDs. NE03A adds these IDs to this strategy, the requirement map
and `tools/checks.py` together; mark future work unimplemented/partial honestly.

NE03A now maps rich schema, Python inverse, shared history/dependency and admission
checks below. The mounted synthetic T3 proof is retained in its task handoff.
Production rich persistence, assets, sync, facts and dates remain partial;
measured rendering/Word remain unimplemented until their owning tasks pass.

| New ID | Behavior and owning checks |
| --- | --- |
| NE-RICH | Typed rich schema, one editor, free region/block movement, durable round trips; NE03A/NE04/NE05/NE06 |
| NE-HISTORY | Composite document/fact session undo, no persisted history, late-result guards; NE03A/NE05/NE07 |
| NE-ASSETS | Local-only image ingestion, archive roles, byte/entry limits and undo retention; NE04/NE06 |
| NE-SYNC | Exact linked edits, bounded narrative update, dependency-based staleness and durable status; NE07/NE08 |
| NE-FACTS | Five-group CRUD, per-job technology scope, typed authority and preserved other records; NE08 |
| NE-DATES | Exact uncertainty predicates, monthly/daily cascade examples and nonblocking behavior; NE09 |
| NE-TEMPLATE | Rich editable DOCX, font/geometry/overflow and manual Word result; NE04–NE06/NE10/NE11 |

Use focused nonbrowser checks per patch and the full fast gate at each run's end.
The old 60-second, strict candidate exclusions and block-restore assertions below
are historical. Current GUI stages keep the 180-second single-attempt ceiling.
Mounted history/layout requires T3 evidence; a headless false `undo()` result is
not a reason to waive it. Native IME/drag/clipboard checks that T3 cannot perform
remain manual, distinct from synthetic events and Word checks.

## NE01 current policy and checks

NE01 removes candidate/contact content exclusions from GUI/legacy context, draft,
rewrite, reconciliation, related changes, shared render and default/saved rules.
Contact/personal/meta categories remain descriptive. Evidence, source ownership,
resource bounds, authentication and user omissions still apply.

U01 retains scoped direct edits and rewrites of contacts; the new rich history
contract replaces historical block-restore expectations in later tasks. A01 keeps
legacy format/byte/coverage checks without contact-fact filtering; NE04 will add
new unsupported-version handling without migration. D01 allows long names,
email/URLs/tokens with exact characters and wraps them in editable DOCX. P02 keeps
supported facts including candidate details while retaining job/date/focus scope.
Mapped nonbrowser replacements are in `ne01-test-replacements.json`; the native
recovery suite covers malformed neighbors, complete accounting, cancellation/
deadlines and durable warnings through cached retry/service reopen. T3 is separate
from automated checks; no new browser scenarios are run.

## Recovery iteration migration

The [recovery plan](flow-recovery-plan.md) defines the next iteration. The table
below overrides conflicting assertions in the legacy T00–T17 strategy that follows.
It is a migration contract, not a claim that replacement tests already exist.

`tests/requirements.json` currently accounts for 22 requirement IDs, including
links to 10 browser spec files. `tools/checks.py` checks that mapped tests actually
exist. A00 inventories those mappings; each implementation task adds its tests
and updates affected mappings together. Leave the map unchanged during planning.
Do not remove a test to evade a requirement or mark an unrun replacement passed.
At A21, switch the default entry and remove replaced legacy UI/specs only with
their replacement mappings. Keep applicable Python, CLI and skill regressions.
Use the existing web test directory/tooling for new-entry browser tests.
Task A06B also checks the built next.html served by the API; a Vite dev-server
pass alone cannot catch fallback to the old index.html. The Playwright config
starts only the Vite dev server on port 4173, so that check needs its own
API-served harness. Add new Python test directories to PYTHON_SUITES in
tools/checks.py and new schemas to the contracts:generate list, or validate_map
and contract generation reject them. New DOCX tests live in a converter-free
fast-group directory named by task A00; integration-render keeps the converter
for legacy PDF only. Under D040 Sol runs these gates and records acceptance per
task; skipped reviews are recorded as debt, never as passed reviews.

| Requirement IDs | Recovery assertions / replacement owners |
| --- | --- |
| C01 | Add Rules, EditorialPlan, Mutation/Result, SourceContext, Generation/Operation and versioned snapshots; freeze Workspace v5/Project v4 document fields, legacyText rows, LegacyData, DocxError and slot IDs before consumers; generated Python/TS contracts agree. Preserve Operation legacy kinds/statuses and v3 decoding. RenderSnapshotV4 is separate from the existing v3 RenderSnapshot. A00/A02–A08B, A12/A14. |
| X01 | Keep parser/format coverage and exact originals. Task A06 tests the input state machine and preDraft promotion in memory with stable IDs; task A12 alone owns durable originals, registry, private permissions and pre-creation warning recovery. Replacement file/paste keeps projectId. Paste then file selects only the file; failed extraction cannot silently reuse or send the inactive paste. Sample is E1 raw text and stays volatile until creation. A06/A12, E6. |
| X02 | Empty, scan-only or failed extraction shows warnings and paste/replacement input. Creation still makes zero inference calls until usable text exists; partial text/warnings are inspectable before creation. Test both UI and API guards. A06/A15, E6. |
| F01 | Keep immutable evidence and provenance; authoritative user edits update effective facts while source history stays intact. E2's controlled evidence oracle pairs exact “пять”/“шесть” spans with five/six. Wrong values fail that oracle; wrong spans fail evidence validation. Keep _observed_number unchanged; no general numeral parser or production fixture-text map. A03/A04/A07B/A10. |
| P01 | Keep exact interval/precision/overlap tests. Keep legacy old_job/skill cutoff tests unchanged. In the GUI, fifteen years is the seeded Markdown default; EditorialPlan alone controls disposition through rendering/coverage. Test formattingAsOf separately from sourceObservedAt; sourceObservedAt comes only from the controlled normalization observation assessment with a validated span, and E1/E2 stay null; migrate legacy as_of only to formattingAsOf. Preserve PartialDate precision on import. Fixed Draft/EditorialPlan fixtures test all-job prompt input and GUI builder application without old_job or Markdown parsing; actual example E4 model adherence stays a manual post-MVP check. A05/A08B. |
| P02 | Keep alias/logo/capacity and user-override checks. Replace fixed semantic ranking/group policy with Rules-based EditorialPlan validation; retain unknown/global-only tools in facts/text. Initial focus keeps the first eight distinct eligible catalog entries with logos in model order; later explicit user order wins. Removed entries produce warning annotations with code focus_entry_removed at skills-focus, with reasons; persist and replace/clear them on validation, never duplicate them on export. Verify zero extra calls, lower-bound duration labels using sourceLanguage (ru Russian, en/mixed English) and blank badges for incomplete exposure. A04/A05/A07/A08B. |
| G01 | Four explicit operations: normalization, drafting, scoped rewrite, edit reconciliation. Test completion-event triggers/coalescing/counts and pure zero-call paths separately. Rewrite cancels the same project's running reconciliation, waits for cleanup/lock release, rejects its old result and allows one new batch after success; paused mode retains it. A02/A05/A06/A09/A10/A11. |
| G02, G03 | Keep CLI protocol/lifecycle and metadata-only probes. Parent Generation, linked one-kind Operations, zero-call extract/assemble/render and guarded retries. GUI sets GenerationPolicy.allow_repair=false; legacy default stays true. GUI operations queue for the provider's non-blocking lock; BUSY never surfaces or counts. Count admitted GUI content attempts including early probe/model denial once, separately from actual inference and unknown usage. Preserve timeout_seconds <= 60 under D038. D034 personal mode does not pass the strict production gate. A01/A06/A19. |
| S01 | Keep loopback/Host/Origin/session/input checks on both route families. Legacy HTTP shapes and the legacy 20-operation cap survive through cutover and MVP, with removal as post-MVP cleanup; project routes support more than 20 sequential batches with shared concurrency/process guards. Replace no-project-retention with authorized private Python local storage and APIs. A12/A13, D035. |
| U01 | Direct editing, structural rows, visibility, arbitrary contiguous selection and one previous version per block. Test application-owned cross-field Selection separately from widget text selection. Use completion events and 500 ms event debounce, never typing-idle inference; distinguish undo-session departure. Verify 1000 ms buffer/session saves during continuous typing without pointer movement or inference. Cmd/Ctrl+Z only restores the active block, in two steps (changed buffer to session baseline, then stored version), and cannot undo row deletion. Period rows change through edit-field on the job and revert with the job restore. Remove lock/proposal/global-history assumptions. A08/A09/A12/A16. |
| U02 | Test counters from a preDraft at (1, 1) and generation at (2, 2): document change increments both once; facts/annotations/derivatives/rename alone increment only projectRevision; status/usage/disk ack/replay/no-op increment neither. Public Mutation.baseRevision is documentRevision; Operation.baseRevision remains projectRevision with separate capturedDocumentRevision. Background results compare both counters/dependencies. Persist slim mutation replay records (ID, payload hash, status, both revisions) and reject deleted-project writes. Test E3b's shared-fact restore and UTF-16/captured-text guards. A08–A13/A19/A20. |
| D01 | Reuse real Generic DOCX writer; verify OOXML, styles, structure, metadata and explicit user omissions. Test the full adapter mapping: required-field labels, location/certification/education/language/early-career sidebars including legacyText rows, authored skillsText, validated focus, separate context/tasks/results and ru versus en/mixed headings. Assert the final visible role is “Роль: не указана” / “Role: not specified”; cover year/month/day, multiple and present period strings. Inspect actual w:br nodes for short multiline education/certification, skills and early-career text, including consecutive breaks; NE01 extends long-token wrapping in layout.py. Keep achievements empty and footer explicitly "", omit empty/hidden optional sections, and never reconstruct them through legacy preparation/grouping. Use the plan's DocxError codes/paths for writer reasons and all schema-limit families, with safe field/section identity and no candidate text or truncation. New flow succeeds without LibreOffice or its bundled fonts; legacy PDF preflight stays intact. DOCX tests run in the converter-free fast group; python-docx==1.2.0 is pinned in requirements.txt. Tasks A06/A08/A20. |
| D02 | PDF output/layout deferred under D039. Preserve legacy converter tests as optional compatibility coverage; mark PDF assertions deferred, not passed, in the task A21 requirement-map migration. PDF source extraction remains required. |
| A01 | Independently bump manifest/workspace 4 → 5 and canonical project 3 → 4; read existing v2/v3/v4 shapes using the plan's current-content mapping. Preserve unsplit job prose as context, education/languages as legacyText, typed employment, private contacts and readable unmapped history without inference. Migrate profile.previous.text from BlockState; retain job_prose.previous as history, never whole-job undo. Old RenderSnapshots cannot masquerade as current RenderSnapshotV4. Imported locks are ignored with notice; local and portable saves share Workspace v5; historical Rules never replace global Rules; subsequent operations use global Rules and stored formattingAsOf. A14. |
| A02 | Keep the 47-entry limit; package workspace, sources and at most current DOCX, without template assets/history binaries. Keep all archive rejection/security cases without losing current work. Preserve old decoder version rejections in contracts/examples/cases.json; add valid Project v4/archive v5 and unknown-next-version cases for new dispatch. Do not delete the former future-version cases to make tests pass. A00/A03/A14. |
| E01 | Missing/uncertain facts create nonblocking annotations. Test section anchors with no education/language rows, Facts-owned missingSurname true/false/null, and E2's two leadership facts plus one conflict mark with neither claim exported. Keep one job-date gap until every period is complete/valid; start-only with present=false stays marked, while valid year/month precision and valid present periods clear it. Missing sourceObservedAt alone leaves the duration blank, not a date gap. Cover multiple periods and restore. Adapter display labels do not become facts or authored text. Keep corrupt-reference/structure failures; user additions/removals remain authoritative. A03/A04/A07/A08B/A11/A20. |
| E02 | D039: downloaded DOCX captures both revisions and render inputs; reuse requires current document/input/template identity. Test buffered edits, changed render dependencies, render failure/retry and no per-key rendering. PDF preview-byte equality is deferred. Tasks A06/A20. |
| R01 | Task A12 owns durable local originals/edits/previous versions and registry; A06 checkpoints are in-memory. Paste/sample is volatile until submission. Saved means a disk acknowledgment; refresh recovers that state and may lose only newer unacknowledged characters. No content in logs/errors/diagnostics/browser persistence. Test private permissions, tombstone-before-delete and project-local file-removal failure without the process cleanup_blocked latch. Do not promise no CLI-owned retention under D034. A12/A13/A14/A19. |
| B01 | New raw input → complete draft → final editor → export flow; no fact wizard/tabs. Settings separate, accessible focus/keyboard and all four design states. A06B discloses creation/model transfer without promising disk saving; A15 owns the final local-save disclosure after A12. Test the selected file/text indicator and migration notice's read-only source text. A06B/A14–A18/A20/A21. |
| N01 | Keep automated responsiveness/size/resource and coalescing checks. Actual CLI latency/usage is measured manually after MVP under D038; it does not block A21. A06/A10/A19/A21. |
| L01 | Keep packaging/start/stop/assets/paths/process cleanup on the existing target platform; prove new-app startup and DOCX export with LibreOffice absent; no platform expansion. A21. |

For recovery property tests, replace “changing prose does not alter facts” with
“original evidence is immutable; effective facts follow authoritative edits”.
Replace lock/proposal properties with per-block previous-version restore and
captured-selection guards. Unknown typed values remain visible/unresolved with
no stale numeric derivative; they are not silent edits to the source evidence.

Handoffs must prefix task IDs with `task`, requirement IDs with `requirement`,
and examples with `example`. In this table the first column is requirements;
all A-number references in the owner column are tasks. Follow the recovery plan
source order; every handoff repeats that D038 supersedes D037's pilot schedule,
D039 removes the PDF gate, D040 defers reviews as debt and D041 sets two-step
restore and the evidence-only observation date. Legacy bodies do not restore superseded behavior.
Copy the recovery plan's applicable mandatory handoff notes verbatim, including
legacy cutoff/duration bypasses, GUI versus legacy attempt counts, explicit empty
footer, version-dispatch fixtures, DOCX errors/preflight/newlines, the E2 evidence
oracle and the next.html marker. Accept task A00's concrete schemas before any
consumer starts, including task A03. Accept task A02's two preset texts before
task A09; a started dependency is not an accepted output.

Use E1–E8 and E3a–E3e phases as defined in the plan. D038 defers the CLI pilot and
live quality/usage evaluation to manual use after MVP. Automated integration uses
controlled provider responses and real parsing/rendering/persistence; the delivered
application still uses the real CLI adapter. Record live assertions as pending
manual evaluation rather than passed or blocking MVP delivery. Do not remove or
weaken automated checks to implement this scheduling decision. Operators later
use the same examples and existing safe duration/usage output; no benchmark system
or mandatory three-launch/60-second test series is required. The existing
GenerationPolicy.timeout_seconds <= 60 runtime bound remains required.
Inject a clock frozen at local date 2026-10-11 for formattingAsOf examples;
their results must not depend on date.today(). Explicit import-precision cases
retain their fixture's partial date.
Capture and inspect 1280×900 synthetic screenshots at product checkpoints; A16/A20
own final reference comparisons and theme/narrow-window/keyboard checks. Record
inspection, not assumed user approval. No real candidate data in test traces/artifacts.

BlockNote adapter acceptance belongs to task A06B before full editor work: one
instance, two-job field/date selection mapped to exact UTF-16 spans, IME/newlines,
disabled native history with `disableExtensions: ["history"]`, slot-aware popover
focus and echo-free backend patches. The built API-served next.html smoke test
asserts `[data-app="foldcv-next"]`; HTTP 200 alone cannot detect the legacy fallback.
Use controlled callbacks before task A08's backend exists. Tasks A08/A09 add real
mutation/restore/rewrite, structural guards and paste/stale-response cases.
Transient BlockNote state is allowed; a second canonical/persisted document is not.
See the recovery plan's BlockNote adapter boundary and linked integration report.

D039 limits MVP resume output to DOCX using the existing Python writer. Task A00
inventories PDF-only checks; tasks A06/A20 separate DOCX preflight/worker output
from conversion. Task A21 updates requirement mappings with explicit deferral
rather than deleting requirements or claiming PDF success. Keep DOCX and PDF-input
checks required; optional legacy PDF tests do not require a converter on an MVP
installation. The legacy mandatory-conversion paragraphs below are superseded.
The existing python-docx add_run already emits w:br for normalized LF. Preserve
that behavior and test OOXML breaks explicitly; paragraph text equality alone
is insufficient. Keep Word visual inspection separate from the automated result.

## Legacy T00–T17 strategy

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

NE07 adds scoped rich rewrite/completion, split-field roots, ownership corrections,
explicit exact-mention updates, restart interruption and stale-retry regressions.
Python and Node checks are mapped under NE-SYNC/NE-HISTORY/NE-FACTS. Mounted T3
results are retained separately; they do not stand in for native OS IME or Word.

NE08 adds Python checks for five-group facts, exact cited FOCUS tokens, per-job
technology isolation, precise/unresolved dates, reversible removal and one bounded
linked-narrative batch. Node uses real Python mutations for composite history,
late preview guards and unrelated typing. T3 covers mounted CRUD, date endpoints,
project rename/delete, owned reopen and portable/DOCX transfer. Timeline warnings
and cascades remain NE09; Word is a final manual gate.
