/** The two commands inside the rules Markdown (D147), read by the rule of `presets()` in `packages/resume_core/rules.py`:
 * a body runs from its `## Preset:` heading to the next `## ` heading outside a code fence; fenced lines belong to
 * the body. Editing one body rewrites only its own lines, so text outside the presets keeps every byte. */
export type PresetKey = "shorten" | "clarify";
export const presetHeadings: Readonly<Record<PresetKey, string>> = { shorten: "## Preset: shorten", clarify: "## Preset: clarify" };

type Section = { key: PresetKey; start: number; end: number };

/** Character ranges of the preset bodies (from after the heading line to the next heading line) and whether a heading
 * repeats, which Python refuses. */
function sections(markdown: string): { found: Section[]; repeated: boolean } {
  const found: Section[] = [];
  let repeated = false, active: Section | null = null, fence: string | null = null, offset = 0;
  for (const match of markdown.matchAll(/([^\r\n]*)(\r\n|\n|\r|$)/gu)) {
    const [whole, line = "", end = ""] = match;
    if (whole === "" && offset >= markdown.length) break;
    const next = offset + whole.length;
    const marker = /^ {0,3}(`{3,}|~{3,})/u.exec(line)?.[1];
    if (marker) {
      if (fence === null) fence = marker;
      else if (marker[0] === fence[0] && marker.length >= fence.length) fence = null;
    } else if (fence === null && line.startsWith("## ")) {
      if (active) { active.end = offset; active = null; }
      const key = (Object.keys(presetHeadings) as PresetKey[]).find(name => presetHeadings[name] === line);
      if (key) {
        if (found.some(section => section.key === key)) repeated = true;
        else { active = { key, start: next, end: markdown.length }; found.push(active); }
      }
    }
    offset = next;
    if (end === "") break;
  }
  return { found, repeated };
}

/** The bodies as Python stores them, trimmed; null for a preset without its heading. */
export function presetBodies(markdown: string): Record<PresetKey, string | null> & { repeated: boolean } {
  const { found, repeated } = sections(markdown), body = (key: PresetKey) => {
    const section = found.find(item => item.key === key);
    return section ? markdown.slice(section.start, section.end).replace(/\r\n|\r/gu, "\n").trim() : null;
  };
  return { shorten: body("shorten"), clarify: body("clarify"), repeated };
}

/** The Markdown with one body replaced, laid out as the default file is: a blank line after the heading and before the
 * next heading. An unchanged body returns the text as it is; a missing heading goes to the end. */
export function withPresetBody(markdown: string, key: PresetKey, body: string): string {
  if (presetBodies(markdown)[key] === body.trim()) return markdown;
  const section = sections(markdown).found.find(item => item.key === key);
  if (!section) {
    const base = markdown === "" ? "" : markdown.endsWith("\n\n") ? markdown : markdown.endsWith("\n") ? `${markdown}\n` : `${markdown}\n\n`;
    return `${base}${presetHeadings[key]}\n\n${body.trim()}\n`;
  }
  const lineBreak = section.start === 0 || /[\r\n]$/u.test(markdown.slice(0, section.start)) ? "" : "\n";
  return `${markdown.slice(0, section.start)}${lineBreak}\n${body.trim()}\n${section.end < markdown.length ? "\n" : ""}${markdown.slice(section.end)}`;
}

/** Why the commands cannot be saved as typed, or null. Python takes the bodies between the headings, so a field line
 * that would end a body early (a `## ` line, an unclosed fence) is caught before the save. */
export function commandsProblem(markdown: string, values: Readonly<Record<PresetKey, string>>): string | null {
  const parsed = presetBodies(markdown);
  if (!values.shorten.trim() || !values.clarify.trim()) return "Заполните обе команды.";
  if (parsed.repeated) return "Заголовок команды встречается в тексте дважды. Оставьте один.";
  if (parsed.shorten !== values.shorten.trim() || parsed.clarify !== values.clarify.trim())
    return "Строка, которая начинается с «## », или незакрытый блок кода разрывает команду. Уберите её.";
  return null;
}

/** The commands after another window saved: the new saved text, with each command changed here put back in. A command
 * left as it was takes the new saved one; text outside the commands comes from the new saved text. */
export function mergeCommands(base: string, old: string, draft: string): string {
  const before = presetBodies(old), mine = presetBodies(draft);
  return (["shorten", "clarify"] as const).reduce((text, key) => {
    const body = mine[key];
    return body !== null && body !== before[key] ? withPresetBody(text, key, body) : text;
  }, base);
}
