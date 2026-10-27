# Review and revise the current resume

This command works on the current authored resume. It does not start an import
or restore hidden text from an original file; the New resume screen imports.

Read `references/editorial-rules.md`. A bare `/import-resume` explains these
rules and checks the project with `check_resume` without proposing a change.

Read the whole document with `read_resume` (every page) and the relevant facts
with `read_facts` before you propose anything. Read originals with
`read_original` only for source-dependent questions or corrections. Report
extraction gaps in the answer.

Propose changes with one `propose_changes` call: `set_block_text` rewrites a
whole paragraph and keeps its field occurrences verbatim and in order;
`replace_text` changes one exact phrase inside one span; `update_fact` changes a
fact field. The proposal is a preview: the user applies it in the panel. Nothing
you propose is saved by the tool, and you cannot apply it.
