# FoldCV visual source

This is the visual layer extracted from the approved prototype. The prototype
loads it directly. Use its code for the first-release interface, including the
document editor's appearance. Do not recreate the design from screenshots.

## Contents

| File | Purpose |
| --- | --- |
| `index.css` | One stylesheet entry point, in the original cascade order |
| `tokens.css` | Exact colors and system/serif font stacks |
| `interface.css` | Layout, document appearance, controls, states and responsive rules |
| `chat.css` | Drawer, transcript, composer, activity, sources and edit receipts |
| `icons.svg` | All 26 original SVG symbols |
| `shell.html` | Application shell, history, header and shared dialog containers |
| `templates.json` | 118 HTML fragments with exact static parts and dynamic slot descriptions |
| `copy.ru.json` | 277 text entries; demo content is identified separately where possible |
| `build.mjs` | Builds the small browser renderer from the declarative sources |
| `index.js` | Browser renderer used by the prototype |
| `manifest.json` | Retained file hashes for this extraction |

Template keys use `editor.<source function>.<number>` and
`chat.<source function>.<number>`. `parts[n]` is followed by dynamic slot `n`;
`slots` describes the original expression. Source positions describe the
extraction input, not the current refactored controller. Template and copy
catalogs are data; the slot descriptions are not evaluated.

Major groups: `renderNew`, `renderProgress`, `renderCheck`, `renderEditor`,
`blockHtml`, `factsHtml`, `technologySummary`, `technologyOptions`,
`renderBlockPanel`, `renderRewrite`, `renderSettings`, `exportDialog`,
`chat.render` and `chat.messageHtml`.

## Editing

Edit the CSS, SVG, shell or JSON sources, then rebuild:

```sh
node design/future-editor/visual/build.mjs
```

Use Node 22. The build needs no dependencies. Refresh the prototype and check
the affected states. Refresh the manifest when accepting a changed visual source.
The old `styles.css` and `agent-chat.css` paths are compatibility imports.

## React adoption

Import the exact CSS and sprite; convert the shell and fragments mechanically
to JSX with typed props, preserving DOM structure, classes, spacing and states.
Radix supplies behavior and accessibility, not a replacement visual theme.

The browser renderer is a prototype adapter, not a production React component
library. It joins pre-escaped strings. Production components must use React text
nodes, validated data and the existing editor API, without injecting candidate
HTML through these templates. Keep data/state/event handling outside the visual
components. Do not import `prototype.js` or `agent-chat.js` into the application.

The catalogs include demonstration labels, sample records, prototype navigation
and simulated results. Those are references for appearance, not production
defaults or claims. Remove the prototype screen switcher and demo disclosures;
replace sample values with real state. Keep product labels in natural Russian.
The prototype uses system fonts and Georgia; it has no remote font dependency.

The separate measured DOCX template and its assets remain governed by the export
contract.
