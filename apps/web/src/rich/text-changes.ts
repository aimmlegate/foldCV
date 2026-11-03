/** One piece of a text in a before/after comparison; `changed` marks what the other side does not have. */
export type TextPart = { text: string; changed: boolean };
/** Words both sides keep: `length` words from word `a` of the first text and word `b` of the second. */
type Run = { a: number; b: number; length: number };

// Words keep inner hyphens and apostrophes ("e-commerce", "Go-сервисы"); any other sign is a token of its own.
const tokenPattern = /\s+|[\p{L}\p{N}\p{M}]+(?:[-‐'’][\p{L}\p{N}\p{M}]+)*|\S/gu;
// Past this many word pairs the changed middle is marked whole instead of matched word by word.
const matchLimit = 1_000_000;

/** Word-level changes between two texts, both sides as parts. Spaces alone never count as a change. */
export function textChanges(before: string, after: string): { before: TextPart[]; after: TextPart[] } {
  const a = before.match(tokenPattern) ?? [], b = after.match(tokenPattern) ?? [];
  const wordsA = a.filter(word), wordsB = b.filter(word);
  const keptA = new Set<number>(), keptB = new Set<number>();
  for (const run of merged(matches(wordsA, wordsB), wordsA, wordsB)) {
    for (let k = 0; k < run.length; k++) { keptA.add(run.a + k); keptB.add(run.b + k); }
  }
  return { before: parts(a, keptA), after: parts(b, keptB) };
}

function word(token: string): boolean { return !/^\s/u.test(token); }

/** A longest common subsequence of the words, as runs; the common start and end are taken first. */
function matches(a: string[], b: string[]): Run[] {
  let start = 0, endA = a.length, endB = b.length;
  while (start < endA && start < endB && a[start] === b[start]) start++;
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) { endA--; endB--; }
  const pairs: [number, number][] = [];
  for (let k = 0; k < start; k++) pairs.push([k, k]);
  const n = endA - start, m = endB - start;
  if (n > 0 && m > 0 && n * m <= matchLimit) {
    // longest[i * width + j]: the longest common subsequence of a from start + i and b from start + j, middles only.
    const width = m + 1, longest = new Uint32Array((n + 1) * width), at = (i: number, j: number) => longest[i * width + j] ?? 0;
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) {
      longest[i * width + j] = a[start + i] === b[start + j] ? at(i + 1, j + 1) + 1 : Math.max(at(i + 1, j), at(i, j + 1));
    }
    for (let i = 0, j = 0; i < n && j < m;) {
      if (a[start + i] === b[start + j]) { pairs.push([start + i, start + j]); i++; j++; }
      else if (at(i + 1, j) >= at(i, j + 1)) i++;
      else j++;
    }
  }
  for (let k = 0; endA + k < a.length; k++) pairs.push([endA + k, endB + k]);
  const runs: Run[] = [];
  for (const [i, j] of pairs) {
    const last = runs.at(-1);
    if (last && last.a + last.length === i && last.b + last.length === j) last.length++;
    else runs.push({ a: i, b: j, length: 1 });
  }
  return runs;
}

/** Drops a kept run no longer than the changes on both of its sides, so a common «и» or comma does not cut one rewritten
 * phrase into pieces. */
function merged(runs: Run[], a: string[], b: string[]): Run[] {
  const size = (words: string[], from: number, to: number) => words.slice(from, to).reduce((total, value) => total + value.length, 0);
  for (let dropped = true; dropped;) {
    dropped = false;
    for (const [k, run] of runs.entries()) {
      const previous = runs[k - 1], next = runs[k + 1], endA = run.a + run.length, endB = run.b + run.length;
      const left = Math.max(size(a, previous ? previous.a + previous.length : 0, run.a), size(b, previous ? previous.b + previous.length : 0, run.b));
      const right = Math.max(size(a, endA, next ? next.a : a.length), size(b, endB, next ? next.b : b.length));
      const own = size(a, run.a, endA);
      if (left > 0 && right > 0 && own <= left && own <= right) { runs.splice(k, 1); dropped = true; break; }
    }
  }
  return runs;
}

/** The tokens as parts; a space is changed only between two changed words, so a mark never starts or ends on one. */
function parts(tokens: string[], kept: Set<number>): TextPart[] {
  const result: TextPart[] = [], words = tokens.filter(word).length;
  let index = 0;
  for (const token of tokens) {
    const changed = word(token) ? !kept.has(index++) : index > 0 && index < words && !kept.has(index - 1) && !kept.has(index);
    const last = result.at(-1);
    if (last && last.changed === changed) last.text += token;
    else result.push({ text: token, changed });
  }
  return result;
}
