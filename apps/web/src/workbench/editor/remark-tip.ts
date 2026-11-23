/** Where the tip of a mark stands (F1 of the tester feedback of 2026-11-23). A pure rule: the component measures, this
 * decides. All values are window pixels. */
export type Box = { left: number; top: number; right: number; bottom: number };
export type TipPlaceName = "below" | "above" | "right" | "left" | "above-block" | "below-block" | "window-top";
export type TipInput = {
  /** The window's inner size. */
  window: { width: number; height: number };
  /** The tip's height when it is this wide. */
  heightAt: (width: number) => number;
  /** A word mark: the hovered line and the pointer's x; the tip goes under the line, or above it. */
  word?: { line: Box; x: number };
  /** A block mark: its first and last line, the paper of the page, and the «Переписать» button of the block when shown. */
  block?: { first: Box; last: Box; paper: Box; button: Box | null };
};
export type TipPlace = { place: TipPlaceName; left: number; top: number; width: number };

export const TIP_EDGE = 8, TIP_GAP = 6, TIP_PAPER_GAP = 12, TIP_WIDTH = 320, TIP_NARROW = 200;

const overlaps = (a: Box, b: Box) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(value, high));

export function tipPlace(input: TipInput): TipPlace {
  const { width: W, height: H } = input.window, full = Math.min(TIP_WIDTH, W - 2 * TIP_EDGE);
  const left = (x: number, width: number) => clamp(x, TIP_EDGE, W - width - TIP_EDGE);
  if (input.word) {
    const { line, x } = input.word, height = input.heightAt(full), below = line.bottom + TIP_GAP;
    const top = below + height <= H - TIP_EDGE ? below : Math.max(TIP_EDGE, line.top - TIP_GAP - height);
    return { place: top === below ? "below" : "above", left: left(Math.max(line.left, x - 24), full), top, width: full };
  }
  const block = input.block;
  if (!block) return { place: "window-top", left: TIP_EDGE, top: TIP_EDGE, width: full };
  const { first, last, paper, button } = block;
  const lines: Box = { left: Math.min(first.left, last.left), top: first.top, right: Math.max(first.right, last.right), bottom: last.bottom };
  const box = (place: Omit<TipPlace, "place">): Box => ({ left: place.left, top: place.top, right: place.left + place.width,
    bottom: place.top + input.heightAt(place.width) });
  // The tip goes below the block's «Переписать» button when the two would stand at one place.
  const clear = (place: Omit<TipPlace, "place">): Omit<TipPlace, "place"> =>
    button && overlaps(box(place), button) ? { ...place, top: button.bottom + TIP_GAP } : place;
  const fits = (place: Omit<TipPlace, "place">) => { const value = box(place); return value.top >= TIP_EDGE && value.bottom <= H - TIP_EDGE; };
  // Beside the paper: as wide as the room allows, from 200 to 320 px; the top at the top of the block, kept in the window.
  const beside = (side: "right" | "left"): TipPlace | null => {
    const room = side === "right" ? W - TIP_EDGE - (paper.right + TIP_PAPER_GAP) : paper.left - TIP_PAPER_GAP - TIP_EDGE;
    if (room < TIP_NARROW) return null;
    const width = Math.min(TIP_WIDTH, room), height = input.heightAt(width);
    const x = side === "right" ? paper.right + TIP_PAPER_GAP : paper.left - TIP_PAPER_GAP - width;
    const place = clear({ left: x, top: clamp(first.top, TIP_EDGE, H - TIP_EDGE - height), width });
    return fits(place) ? { place: side, ...place } : null;
  };
  const near = (name: "above-block" | "below-block"): TipPlace | null => {
    const top = name === "above-block" ? first.top - TIP_GAP - input.heightAt(full) : last.bottom + TIP_GAP;
    const place = clear({ left: left(lines.left, full), top, width: full });
    return fits(place) && !overlaps(box(place), lines) ? { place: name, ...place } : null;
  };
  return beside("right") ?? beside("left") ?? near("above-block") ?? near("below-block")
    ?? { place: "window-top", ...clear({ left: left(lines.left, full), top: TIP_EDGE, width: full }) };
}
