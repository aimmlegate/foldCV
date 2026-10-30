# Project instructions

## Style

- Use English for code comments, commits, PRs, and technical documentation.
- Be clear and short. Use plain words and standard technical terms.
- Use an imperative, one-line commit subject. Add at most two body lines if needed.
- Keep PR descriptions to a few bullets about the change and its purpose.
- Comment only on a non-obvious reason, in one or two lines.
- Do not add authorship trailers, generation labels, or AI mentions to artifacts.

## Frontend and TypeScript

For all project-owned `.ts` and `.tsx` files, including tests and generated
contracts, follow [.cursor/rules/frontend-standards.mdc](.cursor/rules/frontend-standards.mdc).
The confirmed stack is React, TypeScript, Radix Primitives, and Tailwind.

## Local-only files

Plans, handoffs, prompts, reviews and research stay local and never go to Git; see
[the policy](docs/gui/git-data-policy.md). They exist only in the main checkout, under
`docs/gui/`. Keep new ones there and do not force-add them. Read
`docs/gui/implementation-plan.md` there before implementing a GUI slice.

## Shared memory

Use `~/.claude/projects/<slug>/memory/` for project memories shared with Claude.
Derive `<slug>` from the repository root by replacing each non-alphanumeric
character with `-`. Keep `MEMORY.md` as the index. Save one fact per file with
`name`, `description`, and `metadata.type` frontmatter and a one-line index pointer.
Update existing facts instead of duplicating them. Do not use another memory store.
