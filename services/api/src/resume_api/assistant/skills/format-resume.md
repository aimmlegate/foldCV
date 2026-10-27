# Format the current resume

Read `references/editorial-rules.md`. Formatting keeps the exact wording, facts
and links. Read the whole document with `read_resume` (every page), then propose
`format_block` ops (heading level, list kind, alignment, colors) in one
`propose_changes` call. Keep formatting separate from rewriting.

The proposal is a preview that the user applies in the panel. A DOCX or .foldcv
file comes from `export_document`; it exports the saved document, not an
unapplied proposal.
