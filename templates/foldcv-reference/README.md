# FoldCV reference template 1.0.0

`spec.json` is the shared editor/Python geometry and typography authority.
`reference-measurements.json` contains all 182 text-run boxes, five vector
drawings and nine image placements from the verified three-page reference.
Personal text and reference bytes are excluded. The private anonymous frames
were inspected on every page; their characters are substituted, not examples
to copy into resumes.

The fixed body columns start at 26.5/160.76 pt and are 118/420 pt wide, with a
16.26 pt gap. First-page body starts at 95 pt; continuation content starts at
24 pt. The source's 770 pt body bottom leaves a repeated brand-contact footer
at baseline 800 pt. The name/title and brand are header elements. Actual user
content can move between all regions without changing geometry.

Body is Source Sans Pro Light 10 pt with 12.57 pt leading. Supporting dates/
stacks use Regular 10 pt; job headings use Semibold 12 pt with 15.08 pt leading;
section headings use Bold 14 pt. The header uses Black 18 pt/Semibold 16 pt.
Word family/style mapping follows the real TTF names in the specification.
Semibold, Light and Black are separate Word families. Regular/Bold share the
Source Sans Pro family. All five files have `fsType = 0`; keep their OFL notice.

The page-one line is decorative: x=10..535 pt, y=79.5 pt, width 0.6 pt, #888888.
Its four filled section bands are #EFEFEF, 28 pt high and 445 pt wide, starting
10 pt before the main text. Page two has no vector drawings. These are template
decorations, separate from user images. The brand and eight technology PNGs
match the reference's decoded colors/alpha. Focus also has two text-only entries
at the same minimum 38 pt spacing. Candidate technology order/wording is authored;
the reference's technology choices are not generation defaults.

Helvetica maps to native macOS Helvetica for bullet runs at 14 pt; it is not
redistributed. Editor CSS bundles all five Source Sans Pro faces with explicit
weights. No OS font installation. The new rich writer must embed full used faces
and keep content flowing with editable paragraphs/splittable tables. Existing
legacy font checks and renderer identity stay separate.

Installed Word metadata: 16.113.4, build 16.113.26100421, inspected 2026-10-14.
Microsoft documents font embedding for Word for Microsoft 365 for Mac and
recommends full-character embedding for subsequent edits.
[Microsoft font guidance](https://support.microsoft.com/en-us/office/fonts/benefits-of-embedding-custom-fonts).
Actual embedded-font use, editing and save/reopen remain the manual Word gate.
The version alone is not that acceptance.

Reference page breaks are not prescribed. Continuous editor flow and native Word
pagination may differ. Long text, extra focus entries and large sections remain
editable and complete; page estimates never reject content. Source Sans Pro font
substitution by an internal QA converter is a recorded fidelity limitation,
not proof of the native Helvetica/Word mapping.
