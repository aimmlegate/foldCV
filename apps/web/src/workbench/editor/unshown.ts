/** Lines of the original that the resume does not show, marked red in the original beside it (a trial of the look):
 * what a comparison of two versions shows as removed. The reason of each stands in its tip.
 * A line is found by its text with white space left out, so a line the viewer breaks or spaces otherwise is still
 * found. Nothing here touches the resume. */

export type UnshownReason = "no_field" | "dropped" | "hidden" | "changed";
/** `words`: the words to mark when the resume shows the rest of the line; null marks the whole line. */
export type Unshown = { reason: UnshownReason; text: string; words: readonly string[] | null };
export type ChangedLine = { text: string; words: readonly string[] | null };
export const unshownLabels: Readonly<Record<UnshownReason, string>> = { no_field: "не вошло в поля шаблона", dropped: "значение отброшено",
  hidden: "скрыто при импорте", changed: "изменено в резюме" };
export const unshownCodes: Readonly<Record<string, UnshownReason>> = { IMPORT_LINES_NO_FIELD: "no_field", IMPORT_LINES_DROPPED: "dropped",
  IMPORT_LINES_HIDDEN: "hidden" };

type IssueInput = { state: string; message: string; code?: string };

/** The lines the import's notices carry: one per text line, with the words to mark after a tab. A notice an edit of its
 * block retired still counts: the original has the line and the resume does not, whatever was edited since. */
export function unshownLines(issues: readonly IssueInput[]): Unshown[] {
  const found: Unshown[] = [];
  for (const issue of issues) {
    const reason = issue.code === undefined ? undefined : unshownCodes[issue.code];
    if (reason === undefined) continue;
    for (const row of issue.message.split("\n")) {
      const [text = "", words = ""] = row.split("\t");
      if (text.trim()) found.push({ reason, text: text.trim(), words: words.trim() ? words.trim().split(/\s+/u) : null });
    }
  }
  return found;
}

/** The import's lines with the lines Python finds in the present document (the words of a value's source line the
 * resume no longer shows). One row per line text: a line is found in the original by its text, so two rows of one text
 * would mark a second, equal line. Whole beats words; words add up. */
export function withChanged(lines: readonly Unshown[], changed: readonly { text: string; words: readonly string[] | null }[]): Unshown[] {
  const rows = lines.map(line => ({ ...line })), found = new Map<string, Unshown>(rows.map(line => [line.text, line]));
  const extra: Unshown[] = [];
  for (const row of changed) {
    const text = row.text.trim(), held = found.get(text);
    if (!text) continue;
    if (!held) { const line: Unshown = { reason: "changed", text, words: row.words }; found.set(text, line); extra.push(line); }
    else if (held.words !== null) held.words = row.words === null ? null : [...new Set([...held.words, ...row.words])];
  }
  return [...rows, ...extra];
}

const fold = (text: string): string => text.toLowerCase().replaceAll("ё", "е");
// A word as the service counts it: three letters or more, or a number.
const word = /\p{L}{3,}|\d+/gu;

/** Pieces of text (text nodes, the runs of a PDF page) read as one text with white space left out. */
/** `gap`: white space or the end of a piece stood right before this character. */
export type TextIndex = { flat: string; piece: number[]; offset: number[]; taken: boolean[]; gap: boolean[] };
export function textIndex(pieces: readonly string[]): TextIndex {
  const piece: number[] = [], offset: number[] = [], gap: boolean[] = [];
  let flat = "";
  pieces.forEach((value, index) => {
    let apart = true;
    for (let at = 0; at < value.length; at++) {
      const char = value.charAt(at);
      if (/\s/u.test(char) || char === "​") { apart = true; continue; }
      // One folded character per source character keeps the two maps in step.
      flat += fold(char).charAt(0) || char;
      piece.push(index); offset.push(at); gap.push(apart);
      apart = false;
    }
  });
  return { flat, piece, offset, taken: new Array<boolean>(flat.length).fill(false), gap };
}

const wordChar = /[\p{L}\p{N}]/u;
/** Whether a word runs on across this place: a letter or digit on both sides with nothing set between them. The end of
 * a piece parts words, as a viewer gives each line its own piece. */
function insideWord(index: TextIndex, at: number): boolean {
  return at > 0 && at < index.flat.length && !index.gap[at] && wordChar.test(index.flat.charAt(at - 1)) && wordChar.test(index.flat.charAt(at));
}

export type Segment = { piece: number; start: number; end: number };

/** Where the line stands: its first place no earlier line took, as one range per piece. Null when the text is not there. */
export function findLine(index: TextIndex, text: string): Segment[] | null {
  const needle = textIndex([text]).flat;
  if (!needle) return null;
  for (let at = index.flat.indexOf(needle); at >= 0; at = index.flat.indexOf(needle, at + 1)) {
    // The line is whole words of the text: «Java» is not found inside «JavaScript».
    if (insideWord(index, at) || insideWord(index, at + needle.length)) continue;
    let free = true;
    for (let position = at; position < at + needle.length; position++) if (index.taken[position]) { free = false; break; }
    if (!free) continue;
    const segments: Segment[] = [];
    for (let position = at; position < at + needle.length; position++) {
      index.taken[position] = true;
      const piece = index.piece[position] ?? 0, offset = index.offset[position] ?? 0, last = segments.at(-1);
      if (last && last.piece === piece) last.end = offset + 1; else segments.push({ piece, start: offset, end: offset + 1 });
    }
    return segments;
  }
  return null;
}

/** The parts of the segments that are the given words; all of them when `words` is null. */
export function narrowed(pieces: readonly string[], segments: readonly Segment[], words: readonly string[] | null): Segment[] {
  if (words === null) return [...segments];
  const wanted = new Set(words.map(fold)), found: Segment[] = [];
  for (const segment of segments) {
    const text = (pieces[segment.piece] ?? "").slice(segment.start, segment.end);
    for (const match of text.matchAll(word)) {
      if (wanted.has(fold(match[0]))) found.push({ piece: segment.piece, start: segment.start + match.index, end: segment.start + match.index + match[0].length });
    }
  }
  return found;
}

/** Every range to mark in the pieces, with its reason. */
export function unshownRanges(pieces: readonly string[], lines: readonly Unshown[]): (Segment & { reason: UnshownReason })[] {
  const index = textIndex(pieces), found: (Segment & { reason: UnshownReason })[] = [];
  for (const line of lines) {
    const segments = findLine(index, line.text);
    if (segments) for (const segment of narrowed(pieces, segments, line.words)) found.push({ ...segment, reason: line.reason });
  }
  return found;
}

export const unshownClass = "unshown";
/** The style of a mark inside a rendered original (its own document, so the rules travel with it). */
export const unshownStyle = `mark.${unshownClass}{color:inherit;border-radius:2px;padding:0 1px;-webkit-box-decoration-break:clone;box-decoration-break:clone}`
  + `mark.${unshownClass}{background:#ffc9c5}`;

/** Wraps the lines in the text under `root` in marks; gives the number of marks made. */
export function markDom(root: HTMLElement, lines: readonly Unshown[]): number {
  if (!lines.length) return 0;
  const owner = root.ownerDocument, walker = owner.createTreeWalker(root, 4 /* NodeFilter.SHOW_TEXT */), nodes: Text[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) nodes.push(node as Text);
  const ranges = unshownRanges(nodes.map(node => node.data), lines);
  // From the end of each text node backwards, so the offsets of the ranges before stay true.
  ranges.sort((left, right) => right.piece - left.piece || right.start - left.start);
  for (const range of ranges) {
    const node = nodes[range.piece];
    if (!node || range.end > node.data.length) continue;
    const middle = node.splitText(range.start);
    middle.splitText(range.end - range.start);
    const mark = owner.createElement("mark");
    mark.className = `${unshownClass} ${unshownClass}-${range.reason}`;
    mark.title = `Нет в резюме: ${unshownLabels[range.reason]}`;
    middle.replaceWith(mark);
    mark.append(middle);
  }
  return ranges.length;
}

/** A run of text of a PDF page as pdf.js gives it: `transform[4]`, `[5]` is the start of its baseline, in page units. */
export type PdfRun = { str: string; transform: readonly number[]; width: number; height: number };
/** A box over a page, in page units with the origin at the bottom left. */
export type PdfBox = { reason: UnshownReason; left: number; bottom: number; right: number; top: number };

/** The runs in reading order: by baseline from the top, then from the left. A PDF may store the words of one line in
 * another order («2017 —» before «Сентябрь»). */
export function readingOrder(runs: readonly PdfRun[]): PdfRun[] {
  const baseline = (run: PdfRun) => run.transform[5] ?? 0, left = (run: PdfRun) => run.transform[4] ?? 0;
  const sorted = runs.filter(run => run.str.length > 0).sort((first, second) => baseline(second) - baseline(first)), found: PdfRun[] = [];
  for (let start = 0; start < sorted.length;) {
    const head = sorted[start];
    if (!head) break;
    const reach = (head.height || Math.hypot(head.transform[2] ?? 0, head.transform[3] ?? 0)) * 0.5;
    let end = start + 1;
    while (end < sorted.length && baseline(head) - baseline(sorted[end] ?? head) <= reach) end++;
    found.push(...sorted.slice(start, end).sort((first, second) => left(first) - left(second)));
    start = end;
  }
  return found;
}

/** The boxes over the lines on one page. A part of a run is placed by its share of the run's characters. */
export function pdfBoxes(page: readonly PdfRun[], lines: readonly Unshown[]): PdfBox[] {
  const runs = readingOrder(page);
  return unshownRanges(runs.map(run => run.str), lines).flatMap(range => {
    const run = runs[range.piece];
    if (!run || !run.str.length) return [];
    const x = run.transform[4] ?? 0, y = run.transform[5] ?? 0;
    const height = run.height || Math.hypot(run.transform[2] ?? 0, run.transform[3] ?? 0);
    const left = x + run.width * range.start / run.str.length, right = x + run.width * range.end / run.str.length;
    return [{ reason: range.reason, left, right, bottom: y - height * 0.25, top: y + height * 0.95 }];
  });
}
