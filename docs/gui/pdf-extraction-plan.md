# PDF extraction without PyMuPDF: plan (under D149, draft 3, 2026-11-06)

Status: decided on 2026-11-06 (D150): option A, FoldCV is licensed under the AGPL-3.0-or-later and PyMuPDF stays. This
plan is kept as the migration path for the case a non-AGPL licence is ever needed; no code change approved. Draft 3 folds in the three
independent reviews of draft 2 (notes kept outside the repository): an own line builder
and the effective font size in X2, visual-space boxes, the worker's environment allowlist, the macOS floor, the real
scope of option A, acceptance fields that match the tests, the three memory guards, settled packaging facts and the
shipping of licence notices. "Under D149" means the plan is the D149 deliverable; the choice itself gets its own
decision number when made.

Branch: this plan describes `maint/cleanup-2026-11` (D148/D149). On `main`, PyMuPDF is also in
`packages/resume_core/rendering/worker.py` (`_verify_pdf`, `_strip_pdf_metadata`), `skills/format-resume/scripts/extract.py`,
`tools/check_rich_layout.py`, `tools/measure_reference_template.py`, `tests/render/test_production.py` and
`tests/render/test_preparation.py`; the branch removed all of them. Merging the branch comes before X4.

## 1. Today

### 1.1 Licence standing

- `requirements.txt` pins `PyMuPDF==1.28.2`, licence "GNU AGPL 3.0 or Artifex commercial" in the installed metadata.
- The repository on GitHub is public and has no licence file, so it is "all rights reserved". By the build recipes,
  every public beta so far (macOS DMG, Windows zip) contains PyMuPDF: `requirements.txt` → `requirements-service.txt`
  (the Windows helper installs this) → `requirements-desktop.txt` (`tools/build-macos-dmg.sh` installs this). The
  release artifacts themselves were not opened.
- The AGPL asks that a distributed program containing the library is offered under the AGPL, with the Corresponding
  Source of that exact revision (including build scripts and the library's own source offer) and the library's
  notices. The betas offer none of this, so they are non-compliant. Copies already shipped cannot be made compliant
  after the fact; the owner can only remedy going forward and offer source for those revisions. The branch's
  `docs/gui/architecture.md` says so under `## PDF extraction licence` ("resolve licensing or use a suitable
  alternative before distribution"; `main` has the paragraph without the heading).
  `docs/gui/local-dependency-notices.md` still says the run is a personal local developer setup under D007, which is
  out of date since the public betas. This plan is not a legal opinion.

### 1.2 Where PyMuPDF is used

Shipped code (inside the helper):

- `packages/resume_core/extraction/parser.py::_pdf`: `pymupdf.open(stream=…, filetype="pdf")`, `needs_pass` →
  `EXTRACT_ENCRYPTED`, `is_repaired` → `EXTRACT_MALFORMED`, `page_count` against `MAX_PAGES` (40) → `EXTRACT_PAGE_LIMIT`,
  `load_page`, `page.get_image_info()` truthy → one `IMAGE` gap per page; `RuntimeError`/`ValueError`/`TypeError`/
  `IndexError` → `EXTRACT_MALFORMED`; the identity `parser="pymupdf"`, `parser_version=pymupdf.VersionBind + "/layout2"`.
  A `%%EOF` trailer check on the last 1024 bytes runs before the library. PDF units carry
  `ExtractLocation(kind="page", page, paragraph=<block number>)`.
- `packages/resume_core/extraction/pdf_layout.py::page_blocks`: `page.get_text("dict", flags=TEXTFLAGS_DICT &
  ~TEXT_PRESERVE_IMAGES, sort=False)`; per line: span `text`, `size` (length-weighted mean over visible spans),
  `flags & 16` (bold; `None` when spans disagree), line `bbox` in MuPDF order (left, top, right, bottom; origin top
  left, y downward, page rotation already applied), line `dir` (anything but `(1, 0)` marks the line uncertain), block
  `number`; each line text ends with one `\n`. Fragments join only lines with the same column path, the same uncertain
  flag, the same block, consecutive line numbers, equal bold and size within 0.5 pt. Everything after that (bands,
  columns by gaps, side labels, fragments, groups) is our own code and must not change.
- `packages/resume_core/rendering/captured_docx.py::renderer_identity`: reads the installed version of PyMuPDF through
  `importlib.metadata` into the captured DOCX renderer identity; raises if the package is absent.
- `tools/desktop/build_helper.py`: `METADATA` copies PyMuPDF's dist-info for that identity. The macOS helper is
  PyInstaller-frozen; the Windows helper is embeddable Python plus pip wheels (`tools/desktop/build_windows_helper.py`).
- `tools/desktop/build_windows_helper.py`: the `msvcp140.dll` copy from the VC redistributable was added for PyMuPDF
  (per its comment); the final check requires `site-packages/pymupdf`.
- `services/api/src/resume_api/extracting.py` imports the parser module for `MAX_SOURCE`, so the service process
  loads the library too, although it never parses.
- `tools/desktop/check_helper.py::check_workers` runs the helper's `extract` mode on `mixed-columns.pdf` and
  `rich.docx` and asserts a non-empty result; `tools/build-macos-dmg.sh` runs it on every DMG build and
  `.github/workflows/windows.yml` on pushes to `main` or a manual dispatch.

Development only (not distributed):

- `docs/gui/local-version-manifest.json` pins PyMuPDF 1.28.2 as its first package; `tools/local_readiness.py` checks
  the pins; `tests/service/test_readiness.py` expects "Python dependency PyMuPDF must be 1.28.2", and its `-S` run
  reports whichever package comes first in the manifest.
- Tests build their PDF fixtures with PyMuPDF's drawing API at run time: `tests/extract/test_parser.py` (an AES-256
  encrypted file; the page-limit case lowers `MAX_PAGES` to 2 on `mixed-columns.pdf`; the malformed case is a file
  without `%%EOF`, refused before the library), `tests/extract/test_structure.py` (`insert_text` rows in `helv`/`hebo`,
  two columns on one baseline, overlapping text plus a rotated string in one fixture), `tests/extract/test_sample_summary.py`
  (a two-column sample asserting bold and the exact sizes 20, 9 and 11, inserted images);
  `tests/render/test_captured_conversion.py` (slow) reads the LibreOffice-converted PDF with it. The only stored PDF
  fixture is `tests/fixtures/synthetic/import/mixed-columns.pdf`, also used by `tests/service/test_extract_worker.py`
  through the real worker.
- `tools/check_import_structure.py` (private corpus audit) compares every extracted line with PyMuPDF's own
  `get_text("blocks")` lines: an independent engine-to-engine check.

### 1.3 Facts that bound the change

- The browser preview of the original uses pdf.js (Apache-2.0), not PyMuPDF.
- Extraction runs in its own worker process per source (`extracting.py` → `packages/resume_core/extraction/worker.py`).
  Three guards apply: the worker's `RLIMIT_AS` of its start size plus 256 MB (POSIX only; whether macOS enforces it is
  unverified), the service's RSS monitor of 512 MB → `EXTRACT_MEMORY_LIMIT` and 120 s → `EXTRACT_TIMEOUT`, and the
  Windows job commit limit of 768 MB. `MemoryError`/`OSError` in the worker and a worker that dies without a status
  file both end as `EXTRACT_FAILED`. PDFium's one-thread rule costs nothing as long as extraction stays in the worker
  and the service process never calls the library.
- The worker gets an allowlisted environment (`safe_environment` / `windows_environment`): `PATH`, locale, `HOME`,
  temp and XDG entries, nothing else. Environment variables of the service do not reach it.
- `ExtractResult.parser` and `parser_version` are free strings (max 60); the stored `Source.parser` has no limit. A
  new parser name needs no contract change.
- `canonical_source` maps PDF units to `index = page - 1`: block numbers are not persisted, they only drive fragment
  joins and appear in `ExtractResult` locations.
- PDF units never get `heading_level`; nothing in extraction guesses headings.
- No test covers the `is_repaired` refusal.

## 2. Options

| Option | Licence | What changes | Risk |
|---|---|---|---|
| A. Keep PyMuPDF, license FoldCV under AGPL-3.0 | AGPL for the whole distributed app | a release-compliance slice (decision 1): `LICENSE`, notices in app and release, tagged source per release with the offer beside the download, PyMuPDF's own source offer, a statement for shipped betas | none in code; the owner's licence choice for the product; past betas stay as they were |
| B. Keep PyMuPDF, buy the Artifex commercial licence | commercial | nothing in code | cost |
| C. pypdfium2, pinned (bindings Apache-2.0 or BSD-3-Clause; PDFium BSD-3-Clause; bundled third-party notices) | permissive | an own line builder on PDFium's per-character raw API (X2); new source identity; fixture and audit setup (decision 6); notices shipped from the wheel | own line, box and size building must reproduce MuPDF's on the fixtures (section 5); the pin sets the macOS floor and the bold semantics (decision 7) |
| D. pdfplumber over pdfminer.six (MIT) | permissive | chars with `fontname`, `size`, boxes; `extract_words`/lines; `page.images` | pure Python, expected several times slower on long PDFs (unmeasured); different reading order on columns |

Considered and rejected: pypdf (BSD) has no reliable per-span geometry; pdf.js text extraction in the WebView (already
shipped for the preview) would move extraction out of Python, away from the worker guards, the tests and the audit.

Facts about C, verified on 2026-11-06:

- Wheels: pypdfium2 5.14.0 is 3.5 MB (macOS arm64) and 3.9 MB (Windows), about 7 MB installed; PyMuPDF 1.28.2 is
  23.9 MB and 19.8 MB, 58 MB installed.
- macOS floor per pin: 5.14.0 (PDFium 156.0.8076) is tagged `macosx_13_0`, dylib `minos 13.0`; 5.11.0 (PDFium
  151.0.7920) is tagged `macosx_12_0`, `minos 12.0`; 5.9.0 (PDFium 150.0.7869) is tagged `macosx_11_0` but its dylib
  has `minos 12.0`. The app promises macOS 12 (`README.md`, `MINIMUM_MACOS=12.0` in `tools/build-macos-dmg.sh`).
- Bold weight per build: PDFium builds after 7967 (July 2026) return the descriptor's `/FontWeight` when it is set,
  else an estimate from StemV; older builds use the StemV estimate only. A font without a descriptor (the standard
  `hebo` of the fixtures) gives 0 either way.
- Packaging: `pyinstaller-hooks-contrib==2026.8` (pinned in `requirements-desktop.txt`) ships `hook-pypdfium2_raw.py`
  and `hook-pypdfium2.py`, so the frozen macOS helper collects the library and version files without spec changes.
  The 5.14.0 `pdfium.dll` imports only `KERNEL32`, `ADVAPI32`, `GDI32` and `USER32`: it does not need `msvcp140`.
- The wheel's `dist-info/licenses` tree: `Apache-2.0.txt`, `BSD-3-Clause.txt`, `CC-BY-4.0.txt` and `BUILD_LICENSES`
  for abseil, agg23, fast_float, freetype, icu, lcms, libjpeg_turbo, libopenjpeg, libpng, llvm-libc, pdfium,
  pdfium-binaries, simdutf and zlib.
- APIs used by X2 exist in the raw bindings: `FPDFText_CountChars`, `FPDFText_GetUnicode`, `FPDFText_IsGenerated`,
  `FPDFText_GetTextObject`, `FPDFText_GetCharOrigin`, `FPDFText_GetMatrix`, `FPDFText_GetCharBox`,
  `FPDFText_GetFontSize`, `FPDFText_GetFontInfo`, `FPDFText_GetFontWeight`, `FPDFText_GetCharAngle`,
  `FPDFTextObj_GetFont`, `FPDFFont_GetAscent`, `FPDFFont_GetDescent`; `PdfiumError.err_code` with
  `FPDF_ERR_PASSWORD = 4`; `page.get_objects` with form recursion and `FPDF_PAGEOBJ_IMAGE`. The Python helpers wrap
  only the char box; the rest is ctypes.

## 3. Decisions for the owner

1. A or B (keep the parser). A is a release-compliance slice, not a file: `LICENSE` (AGPL-3.0), PyMuPDF/MuPDF
   notices in the app and the release page, a tag per released build with the source offer beside the download
   (Corresponding Source including the build scripts and PyMuPDF's own source or a link to it), and a statement for
   the betas already shipped (source offered for their revisions). B needs nothing in code.
2. C (recommended if a permissive licence is wanted), with decision 7 for the pin and X2 as a feasibility gate.
3. D only if C fails the X2 gate.
4. A now does not block C later, under two conditions: the owner controls, or obtains the rights to, all code kept
   after the switch (every outside contribution during the AGPL window under a contributor agreement or a separate
   licence), and the owner accepts that copies already distributed under the AGPL stay under it. With that discipline
   A as a stopgap and C as the target are compatible; current non-compliance does not make them so by itself.
5. Under C, repaired files: recommended to accept them (PDFium repairs silently; the refusal is untested). X3 then
   lists this as an explicit exception to "same failure codes", and X0 gets a repaired-with-valid-trailer fixture. A
   library-level malformed file (valid trailer, broken objects) must still be refused.
6. Under C, PyMuPDF stays a development dependency (`requirements-dev.txt`) in three roles: fixture builder, X0
   oracle, and the independent engine-to-engine reference of the private corpus audit. The alternative (rewrite the
   builders with pypdf or reportlab) reintroduces a dependency the branch just removed and costs about a day more.
7. Under C, the macOS floor (new): either (a) raise the promise to macOS 13 and pin `pypdfium2==5.14.0` (README,
   release notes, build script), or (b) keep macOS 12 and pin `pypdfium2==5.11.0` (PDFium 151.0.7920, StemV-only
   weight, older fixes). Recommendation: (b) now, (a) at the next floor review; any pin change repeats the bold, import
   table and notices checks of X3.

## 4. Slices if C is chosen

Rules: the extraction output is the contract. A new parser gets a new source identity (`parser="pdfium"`,
`parser_version="<PYPDFIUM_INFO.version>/<PDFIUM_INFO.build>/layout1"`, for example `5.11.0/7920/layout1`, within the
60-character limit); projects imported earlier keep theirs and are never re-extracted. Layout code (`_order`, `_gaps`,
`_side_labels`, fragments, groups) stays untouched; differences are tuned in the adapter only. X2 is a feasibility
gate: the estimate is revisited after it. The branch is merged into `main` before X4.

- X0 Oracle. Record today's `extract()` result for every fixture: unit texts and boundaries, locations (page compared,
  paragraph recorded only), every `SourceStructure` field, gaps, page count, failure codes and the `sample_summary`
  JSON. Fixtures: `mixed-columns.pdf`; the ones `test_parser.py`, `test_structure.py` and `test_sample_summary.py`
  build; and new ones built with PyMuPDF (dev) or hand-written content streams, the first two first: two columns on
  one baseline; overlapping text; rotated text alone (today's fixture mixes it with overlap, which already sets the
  uncertain flag); text drawn with `Tf 1` and the size in the text matrix; page `/Rotate 90`; a non-zero origin or
  crop box; a repaired file with a valid trailer; a library-level malformed file; 0 pages; 40 and 41 pages; an
  owner-password-only file; an image inside a form XObject, an image mask and an inline image; a line with regular
  and bold runs; justified text with a line-end hyphen; ligatures and a character outside the BMP; a dense multipage
  PDF for memory. Plus the private corpus audit summary (counts and hashes only).
- X1 Adapter seam. `_pdf` and `page_blocks` take a small `PdfDocument`/`PdfPage` protocol: document → needs password,
  was repaired (`None` when the engine cannot tell), page count, pages; page → lines in visual page space (MuPDF box
  order, y downward, page rotation applied) with text ending in one `\n`, length-weighted size, bold or `None`,
  rotated flag, block id and enumeration order; image presence. The PyMuPDF adapter keeps every output byte-identical
  (the oracle proves it).
- X2 pdfium adapter (the gate).
  - Switch: a `parser` key in `extract-input.json` written by `run_extract`, and a `parser=` parameter on `extract()`
    for the tests; no environment variable (the worker's allowlist drops them) and no Settings entry. The service
    default stays `pymupdf` until X4.
  - Open: `PdfDocument(bytes)` without a password; `PdfiumError` with `err_code == FPDF_ERR_PASSWORD` →
    `EXTRACT_ENCRYPTED`; `err_code == 0` on a zero-page file → `EXTRACT_PAGE_LIMIT` (today's code); any other
    `PdfiumError` → `EXTRACT_MALFORMED`; page count 1..40 as today.
  - Lines, built by us from per-character data, never from `get_text_range`: iterate char indexes, take the Unicode
    per index (surrogate-safe), skip generated characters and apply our own space rule; per char: text object,
    origin, text matrix, tight box, font via the text object (ascent, descent), font name and flags, weight, angle.
    Effective size = `Tf` size × the vertical scale of the text matrix. A line is a run of characters on one baseline
    whose origin continues the previous advance within a gap threshold, so two columns on one baseline become two
    lines; a block is a run of lines close vertically and overlapping horizontally in content order. The line box is
    the union of boxes rebuilt from origin, effective size, ascent and descent (MuPDF-like, not PDFium's font-bbox
    boxes), then mapped to visual space (`top = page_height - y_top`, rotation applied). Rotated = angle outside a
    tolerance around 0. Thresholds are tuned on the oracle, in the adapter only. PDFium replaces a line-end hyphen in
    its character array with U+0002; recover it from the text object's own text or record the loss per fixture.
  - Bold per char: weight ≥ 600 (for the pinned build's semantics, see section 2), or a font name containing
    Bold/Black/Heavy/Semibold, or the ForceBold descriptor flag (bit 19, mask `1 << 18`); the line is bold when all
    visible chars agree, `None` otherwise, as today.
  - Images: `page.get_objects` filtered to image objects with form recursion; one `IMAGE` gap per page with any image.
  - Library scope: the service imports the parser module for `MAX_SOURCE`; move the constant or import the library
    lazily there, keep the module-level import in the worker (the memory baseline is measured after it).
  - A written diff report per fixture against the oracle.
- X3 Acceptance.
  - Exact: unit texts and boundaries (no whitespace exception), order, `column`, `group`, `bold`, `layout_uncertain`,
    gaps, page count, the `sample_summary` JSON including the sizes 20, 9 and 11 the tests assert, failure codes with
    the exceptions of decision 5 and the zero-page mapping. Locations: page exact, paragraph not compared.
  - Tolerant: `bounds` and `gap_before` within 1 pt after the ascent/descent rebuild; other `font_size` values within
    0.5 pt. If the boxes cannot be rebuilt, the plan says so and the tolerance and `group` thresholds are re-decided,
    not silently widened.
  - The slow import suite green. Private corpus: the existing PyMuPDF-to-units comparison stays as the independent
    check, plus adapter-line conservation (every raw line reaches a unit once); reports carry counts and hashes only.
  - Time not worse than 2× on the largest fixture. Memory: the dense fixture passes under all three guards with exit 0
    on both platforms (a breach shows as `EXTRACT_FAILED`, not `EXTRACT_MEMORY_LIMIT`); peak RSS measured; pages and
    text pages closed as the loop advances.
  - Packaging: no spec change (the pinned hooks collect `pypdfium2_raw`; confirm in the build log); `check_helper.py`
    extended to assert `parser == "pdfium"` and non-trivial unit text, run by the DMG build and by a manual dispatch
    of `windows.yml` for the branch; the Windows required path becomes `site-packages/pypdfium2_raw`; the `msvcp140`
    step is dropped only after an import-table scan of every `.dll`/`.pyd` in the helper (pywin32, lxml, Pillow,
    pydantic-core, the PDFium DLL); helper and zip sizes noted.
- X4 Switch and clean-up, after the branch merge: `requirements.txt` (pypdfium2 pin in, PyMuPDF out),
  `requirements-dev.txt` (PyMuPDF pin in), `captured_docx.py` tuple (PyMuPDF out; the identity hash changes, which is
  expected), `build_helper.py` `METADATA` (PyMuPDF out, `pypdfium2` in, so its dist-info with the licences tree ships
  on macOS; Windows ships dist-info through pip), `build_windows_helper.py` (required path; `msvcp140` per X3),
  `local-version-manifest.json` (pypdfium2 added; PyMuPDF kept as the first, development, pin, or the `-S` readiness
  test string changed), `test_readiness.py`, `check_helper.py`, `tools/check_import_structure.py` (reference kept,
  conservation check added), `README.md` (macOS floor if decision 7a), `docs/gui/architecture.md` («PDF extraction
  licence» section), `docs/gui/local-dependency-notices.md` (pypdfium2 Apache-2.0 or BSD-3-Clause, PDFium
  BSD-3-Clause, the wheel's full licences tree, PyMuPDF development only, the "personal local setup" sentence
  replaced). Notices shipped: the wheel's `dist-info/licenses` tree copied into both helpers and named in the app,
  re-copied whenever the pin changes. Then clean builds from the switched branch with PyMuPDF absent from the build
  environment: DMG and Windows zip; payload inspected for `pymupdf`, `fitz`, MuPDF binaries and stale dist-info; the
  app starts, imports a PDF and exports a DOCX.
- X5 Live check: two real resumes of the owner (local only), imported in the switched desktop build with the Codex
  provider and the same template, compared with the same files imported on the PyMuPDF build: unit texts, columns and
  the import result.

Effort: X0–X2 about 3–4 days (the own line builder), X3–X5 about 2–3 days plus the owner's checks; 6–8 days in
total, revisited after the X2 gate.

### 4.1 Shortened variant: no parity bar

The slices above aim at output identical to PyMuPDF's on every fixture, so the existing tests pass unchanged. That bar
is self-imposed: projects imported earlier keep their identity and are never re-extracted, so only new imports see the
new parser. If "extracts well enough" is acceptable for new imports, C shrinks to about 2–3 days:

- S1 Adapter: the X2 adapter as specified (own line builder, visual-space boxes, effective size, the bold rule, the
  password, zero-page and malformed mappings, images), behind the same `parser` key. Thresholds are set once on the
  synthetic fixtures; no oracle diff per field.
- S2 Fixtures and tests: the X0 fixtures that matter for resumes (two columns on one baseline, overlap, rotated text,
  matrix-scaled size, a line-end hyphen, encrypted, zero pages, the page limit, images); the extraction tests get a
  pdfium variant with its own expected values where PyMuPDF's differ (sizes, boxes) instead of exact parity. PyMuPDF
  stays in `requirements-dev.txt` as the fixture builder.
- S3 Packaging and notices: the packaging items of X3 and the edits of X4 (requirements, metadata, manifest, readiness
  test, the `check_helper.py` assertion, the Windows required path and `msvcp140` per the DLL scan, the wheel's licences
  tree in both helpers, docs); clean builds with PyMuPDF absent.
- S4 Live check: the owner's two real resumes plus a few public sample PDFs, judged by eye on columns, bold and order;
  no engine comparison.

Decisions 5–7 still apply (repaired files accepted, PyMuPDF development-only, the pin and the macOS floor). Given up:
the byte-level comparison with the old engine, the engine-to-engine corpus audit (adapter-line conservation stays) and
the promise that files imported after the switch extract as before. Kept: old projects untouched, failure codes, the
worker guards, the notices. Time: S1 1–1.5 days, S2 0.5–1 day, S3 0.5 day, S4 with the owner. The lanes of section 6
reduce to two: S1, and S2 with S3.

## 5. Risks

- Line building: PDFium's text page is not MuPDF's. It merges everything on one baseline into one line with a
  generated space, replaces a line-end hyphen with U+0002 and collapses repeated spaces. Hence the own builder in
  X2; the two-column, overlap and hyphen fixtures decide whether it reproduces MuPDF's lines.
- Font size: `FPDFText_GetFontSize` is the `Tf` em size. Files written with `Tf 1` and the size in the text matrix
  give 1 for every character and collapse every threshold in `_order`. Hence the effective size and the matrix
  fixture.
- Boxes: PDFium's loose boxes come from the font bounding box and are taller than MuPDF's ascent/descent boxes; the
  overlap test, the band gaps and the `group` threshold all read them. Hence the rebuild; if it fails, `group` may
  need retuning.
- Bold: weight semantics depend on the pinned build; standard fonts without a descriptor give 0; synthetic bold is
  invisible to the weight. Name and ForceBold fallbacks; mixed lines give `None`. The oracle shows what changes.
- Columns and overlap: our thresholds were tuned on MuPDF boxes; different boxes can move a split. The oracle shows
  where.
- Ligatures, CID fonts without a ToUnicode map, characters outside the BMP and generated characters: both engines
  differ in what they emit; the fixtures decide.
- Repaired files: accepted under decision 5; a library-level malformed file must still be refused; owner-only
  passwords open without a password in both engines.
- Images: masks and inline images may be counted differently from `get_image_info`; the fixture decides.
- Memory: three guards; PDFium's out-of-memory path aborts the worker without a status file, which the service maps to
  `EXTRACT_FAILED`; the dense fixture must pass under every guard. Whether macOS enforces `RLIMIT_AS` is unverified.
- Threads: PDFium is not thread-safe; extraction stays in the worker and the service never calls the library.
- Pin and floor: the pin fixes the macOS floor, the PDFium build, the bold semantics and the DLL imports; every pin
  change repeats those checks (decision 7).
- Packaging: settled facts above are for 5.14.0; the frozen build log must show the hooks collecting the library, and
  the Windows runtime scan covers every native module, not only PDFium.
- Licence: option A is a compliance slice; shipped betas stay as they were; relicensing needs the rights to all kept
  code. Not a legal opinion.

## 6. Parallel execution if C is chosen

The critical path stays sequential: the line builder (X2a), its tuning against the oracle (the gate), then X3 → X4
→ X5. Everything else leaves that path. Wall-clock about 5–6 days instead of 6–8; the gain is bounded by the one
heavy step.

Start conditions: decisions 2 and 6; decision 7 may stay provisional with `pypdfium2==5.11.0` until X4, since the
builder code does not depend on the pin (only the weight semantics, the DLL facts and the floor do, and X3 repeats
those checks). Starting is a new decision beyond D149, which records "plan only".

| Lane | Content | Time | Depends on |
|---|---|---|---|
| 1. Adapter seam | X1: the `PdfDocument`/`PdfPage` protocol, the PyMuPDF adapter, the byte-identical proof | ~1 day | nothing |
| 2. Line builder | X2a as a separate module on PDFium's raw API: chars → lines → blocks, boxes from ascent/descent, effective size, bold, rotation; own unit tests on hand-written PDFs | 2–3 days | only the `Line` shape of X1, already written in section 4 |
| 3. Oracle and fixtures | X0a the recorder of `extract()` results, X0b the sixteen new fixtures, X2c the oracle-versus-adapter diff tool | 1–1.5 days | nothing |
| 4. Packaging and X4 preparation | import-table scan of every helper DLL (pefile over the downloaded wheels), the hooks in a frozen build log, the `check_helper.py` extension, the licences tree copied by both builders, the X4 patch (requirements, manifest, metadata, docs) prepared but not merged | ~1 day | nothing |
| 5. Licence slice A, if the owner picks "A now" | `LICENSE`, notices, release tags, the source offer | independent | decision 1 |

Sequential tail after lanes 1–3 merge: X2b (open, passwords, zero pages, images, the `parser` key, the lazy service
import), half a day; tuning the builder against the oracle through the diff tool, 1–2 days, which is the gate; then
X3 one day, X4 half a day, X5 with the owner.

No file conflicts: lane 1 edits `parser.py` and `pdf_layout.py`, lane 2 adds a new module, lane 3 adds tests and
fixtures, lane 4 edits `tools/desktop`, requirements and docs. Merge order: 1 → 3 → 2 → 4.

If the X2 gate fails, lanes 3 and 5 stay useful under any option; lane 4 is lost, but it is small.

Lane rules (from the D147 lanes): worktrees from `delegate_task` lack the gitignored `docs/gui`, so lanes get
absolute paths to the plan and the oracle; no branch `name/a` beside a branch `name`; Node 22 on the PATH, no
`npm install`; the parent reads every lane report in full.

## 7. Review log

- Draft 1 (2026-11-06), reviewed the same day: inventory limited to two modules; fixture builders and audit reference
  missing; PyInstaller collection and Windows runtime missing; bold rule too optimistic; acceptance without exact and
  tolerant fields; `dir` missing from the protocol; wrong citations. Folded into draft 2.
- Draft 2 (2026-11-06), three independent reviews the same day (notes kept outside the repository): own line builder
  and effective font size, y-flip and page rotation, char-index mapping and surrogates, the worker's environment
  allowlist, the macOS floor, option A scope and relicensing conditions, audit contradiction, acceptance fields against
  the tests, three memory guards and `EXTRACT_FAILED`, hooks and Windows runtime settled by a DLL scan, notices shipping
  and the full licences tree, the architecture heading on the branch, `ExtractResult.parser`, `check_helper.py`, the
  service-side import, the `-S` readiness test, reportlab gone from the branch, verified sizes. Folded into draft 3.
