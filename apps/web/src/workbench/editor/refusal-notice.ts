/** A refused input is said at the place of work (F4 of the tester feedback of 2026-11-23): pure rules, time and boxes as
 * parameters. */
export type Shown = { text: string; at: number };
export type Box = { left: number; top: number; right: number; bottom: number };

/** How long the message stays, and how long the same text stays quiet after it was shown. */
export const REFUSAL_SHOWN = 4000, REFUSAL_QUIET = 3000;
const EDGE = 8, GAP = 6;

/** Whether a refusal shows now: the same text does not show again within the quiet time. */
export function refusalDue(last: Shown | null, text: string, now: number, quiet = REFUSAL_QUIET): boolean {
  return !last || last.text !== text || now - last.at >= quiet;
}

/** The message above the first line of the selection (the caret line for a caret), kept in the window. It never stands on
 * the «Изменить текст» button: when the two meet, it goes above the button. */
export function refusalPlace(line: Box, size: { width: number; height: number }, window: { width: number; height: number },
  button: Box | null = null): { left: number; top: number } {
  const left = Math.max(EDGE, Math.min(line.left, window.width - size.width - EDGE));
  let top = line.top - GAP - size.height;
  const meets = (at: number) => !!button && left < button.right && button.left < left + size.width && at < button.bottom && button.top < at + size.height;
  if (meets(top) && button) top = button.top - GAP - size.height;
  // No room above: below the line, past the button when it stands there.
  if (top < EDGE) {
    top = line.bottom + GAP;
    if (meets(top) && button) top = button.bottom + GAP;
  }
  return { left, top: Math.max(EDGE, Math.min(top, window.height - size.height - EDGE)) };
}
