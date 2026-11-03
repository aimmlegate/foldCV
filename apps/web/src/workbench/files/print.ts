/** PDF export prints the shown sheet (D133). A static copy is split into pages here, between blocks and by the template's
 * margins: WebKit applies no @page margins and cuts a grid column at the page edge. Each page is a copy of the sheet that
 * shows only its own blocks, so it lays out from its top and a small layout difference in print cuts no line. */
import { validLink } from "../editor/link";

export type PrintPage = { width: number; height: number; continuation_body_top: number; body_bottom: number };
export type PrintPlatform = "macos" | "windows" | "browser";
/** A vertical extent in CSS pixels from the top of the sheet; `keep` holds it on the page of the next one (a heading). */
export type Unit = { top: number; bottom: number; keep: boolean };

const rootClass = "print-root";
const pixels = 96 / 72;
// Measured edges differ by fractions of a pixel between the boxes of one line.
const slack = 0.5;

/** Paper of the template's size; each page copy carries the template's margins itself. */
export function pageRules(page: PrintPage): string {
  return `@page { size: ${String(page.width)}pt ${String(page.height)}pt; margin: 0; }`;
}

/** The page of each unit of one column, in order. The first page holds units down to `firstBottom`; a later page starts at the
 * unit that did not fit and holds `room` below its top. Overlapping units and a heading with the unit after it share a page;
 * a group taller than a page stays alone on its page. */
export function unitPages(units: readonly Unit[], firstBottom: number, room: number): number[] {
  const groups: { top: number; bottom: number; keep: boolean }[] = [], groupOf: number[] = [];
  for (const unit of units) {
    const last = groups.at(-1), overlaps = last !== undefined && unit.top < last.bottom - slack;
    if (last && (overlaps || last.keep)) {
      last.keep = overlaps ? last.keep || unit.keep : unit.keep;
      last.bottom = Math.max(last.bottom, unit.bottom);
    } else groups.push({ ...unit });
    groupOf.push(groups.length - 1);
  }
  const pages: number[] = [];
  let page = 0, limit = firstBottom;
  groups.forEach((group, index) => {
    if (index > 0 && group.bottom > limit + slack) { page += 1; limit = group.top + room; }
    pages.push(page);
  });
  return groupOf.map(index => pages[index] ?? 0);
}

/** Where the system print window saves a PDF. */
export function printHint(platform: PrintPlatform): string {
  if (platform === "macos") return "Откроется окно печати. Внизу слева нажмите «PDF» и выберите «Сохранить как PDF».";
  if (platform === "windows") return "Откроется окно печати. Выберите принтер «Microsoft Print to PDF» и нажмите «Печать».";
  return "Откроется окно печати. В поле «Принтер» выберите «Сохранить как PDF».";
}

export function printPlatform(): PrintPlatform {
  const desktop = document.documentElement.dataset["desktop"];
  return desktop === "macos" || desktop === "windows" ? desktop : "browser";
}

export function removePrintCopy(): void {
  for (const element of document.querySelectorAll(`body > .${rootClass}`)) element.remove();
}

/** The paged copy for the printer. Images decode before the measure, or they have no height, and again in the page copies. */
export async function printCopy(paper: HTMLElement, page: PrintPage): Promise<HTMLElement> {
  const { root, copy } = measured(paper, page);
  await loaded(root);
  paged(root, copy, page);
  await loaded(root);
  return root;
}

async function loaded(root: HTMLElement): Promise<void> {
  await Promise.all([document.fonts.ready, ...Array.from(root.querySelectorAll("img"), image => image.decode().catch(() => undefined))]);
}

/** The same at once, for a print the browser starts itself: the shown sheet's fonts and images are already loaded. */
export function printCopyNow(paper: HTMLElement, page: PrintPage): HTMLElement {
  const { root, copy } = measured(paper, page);
  return paged(root, copy, page);
}

/** A copy of the paper without editing, marks and buttons, laid out off screen. It loses the editor's class, so the editor's
 * queries skip it. */
function measured(paper: HTMLElement, page: PrintPage): { root: HTMLElement; copy: HTMLElement } {
  removePrintCopy();
  const root = document.createElement("div"), rules = document.createElement("style"), copy = paper.cloneNode(true);
  if (!(copy instanceof HTMLElement)) throw new Error("Не удалось подготовить резюме к печати.");
  root.className = `${rootClass} print-measure`; root.setAttribute("aria-hidden", "true"); root.inert = true;
  rules.textContent = pageRules(page);
  copy.classList.remove("cv-document");
  // The paper's own style rules stay in the document; a copy of them would repeat the assistant's change highlight.
  for (const element of copy.querySelectorAll("style, .uir-empty-region")) element.remove();
  for (const element of copy.querySelectorAll("[contenteditable]")) element.removeAttribute("contenteditable");
  for (const element of copy.querySelectorAll(".fcv-remark, .ProseMirror-selectednode, .selectedCell"))
    element.classList.remove("fcv-remark", "ProseMirror-selectednode", "selectedCell");
  linkCopy(copy);
  root.append(rules, copy);
  document.body.append(root);
  return { root, copy };
}

/** One copy of the sheet per page: the first as it is down to the body's bottom, a later one without the header, its columns
 * from the continuation top. A block whose units are all on other pages is left out of a page. */
function paged(root: HTMLElement, copy: HTMLElement, page: PrintPage): HTMLElement {
  try {
    const origin = copy.getBoundingClientRect().top, first = page.body_bottom * pixels, room = (page.body_bottom - page.continuation_body_top) * pixels;
    let count = 1;
    for (const column of copy.querySelectorAll<HTMLElement>(".fcv-region:not(.fcv-region-header)")) {
      const units = columnUnits(column, origin), pages = unitPages(units.map(entry => entry.unit), first, room);
      units.forEach(({ element }, index) => {
        const on = String(pages[index] ?? 0);
        element.dataset["printPage"] = on;
        for (let block = element.closest<HTMLElement>(".bn-block-outer"); block && block !== column; block = block.parentElement?.closest<HTMLElement>(".bn-block-outer") ?? null)
          block.dataset["printPages"] = `${block.dataset["printPages"] ?? ""} ${on}`;
      });
      count = Math.max(count, (pages.at(-1) ?? 0) + 1);
    }
    const pages = Array.from({ length: count }, (_, index) => pageCopy(copy, index, page));
    copy.remove();
    root.append(...pages);
    return root;
  } finally { root.classList.remove("print-measure"); }
}

function pageCopy(copy: HTMLElement, index: number, page: PrintPage): HTMLElement {
  const paper = copy.cloneNode(true), shown = String(index);
  if (!(paper instanceof HTMLElement)) throw new Error("Не удалось подготовить резюме к печати.");
  paper.classList.add("print-page");
  paper.style.width = `${String(page.width)}pt`; paper.style.height = `${String(page.body_bottom)}pt`;
  for (const element of paper.querySelectorAll<HTMLElement>("[data-print-page]")) if (element.dataset["printPage"] !== shown) element.classList.add("print-hidden");
  for (const element of paper.querySelectorAll<HTMLElement>("[data-print-pages]"))
    if (!(element.dataset["printPages"] ?? "").split(" ").includes(shown)) element.classList.add("print-hidden");
  if (index > 0) {
    for (const element of paper.querySelectorAll(".fcv-region-header, .fcv-logo")) element.classList.add("print-hidden");
    const sheet = paper.querySelector<HTMLElement>(".fcv-sheet");
    if (sheet) sheet.style.paddingTop = `${String(page.continuation_body_top)}pt`;
  }
  return paper;
}

/** What a page keeps whole, in order: a Focus row, or one block's own content (its children are units of their own). A
 * heading keeps with the unit after it. */
function columnUnits(column: HTMLElement, origin: number): { element: HTMLElement; unit: Unit }[] {
  const units: { element: HTMLElement; unit: Unit }[] = [];
  for (const block of column.querySelectorAll<HTMLElement>(".bn-block-outer")) {
    if (block.parentElement?.closest("[data-fcv-focus]")) continue;
    const element = block.matches("[data-fcv-focus]") ? block
      : block.querySelector<HTMLElement>(":scope > .bn-block > :is(.bn-block-content, .bn-react-node-view-renderer)");
    if (!element) continue;
    const rect = element.getBoundingClientRect();
    if (rect.height <= 0) continue;
    const content = element.matches(".bn-block-content") ? element : element.querySelector(".bn-block-content");
    const keep = element !== block && (content?.matches('[data-content-type="section"], [data-content-type="heading"]') ?? false);
    units.push({ element, unit: { top: rect.top - origin, bottom: rect.bottom - origin, keep } });
  }
  return units;
}

/** A link opens from the PDF as from the DOCX: only an absolute web or mail address; a bound link is a span in the editor. */
function linkCopy(copy: HTMLElement): void {
  for (const element of copy.querySelectorAll<HTMLElement>("a[href], .cv-bound-link[data-href]")) {
    const href = element instanceof HTMLAnchorElement ? element.getAttribute("href") ?? "" : element.dataset["href"] ?? "";
    if (element instanceof HTMLAnchorElement) {
      if (!validLink(href)) element.removeAttribute("href");
      continue;
    }
    if (!validLink(href)) continue;
    const anchor = document.createElement("a");
    for (const attribute of element.attributes) anchor.setAttribute(attribute.name, attribute.value);
    anchor.href = href;
    anchor.append(...element.childNodes);
    element.replaceWith(anchor);
  }
}
