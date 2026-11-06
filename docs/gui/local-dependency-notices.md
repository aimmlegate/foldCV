# Local dependency notices

This developer run uses the pinned versions in
[local-version-manifest.json](local-version-manifest.json) and the repository
requirement and package lock files. Python, Node and web packages are installed
locally by the developer; LibreOffice is downloaded into ignored `.tools/` after
the script checks its published image hash. The checked-in template assets and
fonts remain separate files in this checkout.

LibreOffice's bundled notice identifies Mozilla Public License 2.0 and
third-party terms in its `Resources/LICENSE` file. Source Sans Pro fonts carry
the SIL Open Font License 1.1 in `skills/format-resume/assets/fonts/LICENSE.txt`.
The included Devicon assets have their notice in
`skills/format-resume/assets/devicon/LICENSE`. Keep these notices with any later
distribution decision.

FoldCV is licensed under the GNU AGPL-3.0-or-later since D150 (2026-11-06), with the
`LICENSE` file at the repository root. PyMuPDF 1.28.2 declares AGPL-3.0 or an Artifex
commercial licence; FoldCV uses it under the AGPL, and the apps carry the notice. The
components inside the apps and their licence texts are generated into
`THIRD-PARTY-NOTICES.md` by `tools/third_party_notices.py` and ship inside the helper,
the macOS app, the DMG and the Windows zip; regenerate the file after a dependency
change. A migration away from PyMuPDF stays planned in `pdf-extraction-plan.md` for
the case the product licence changes. Reference template asset rights still need a
distribution decision.

The T3 Code source inspection was a protocol reference at revision
`98beed1a226c42b85c52ff5ee9d5dbb67d776a77`.
This T17 package adds no copied T3 implementation or bundled CLI. The optional
user-installed Codex CLI uses its own subscription login. There is no paid API
fallback and no claim of unlimited or zero-cost subscription use.
