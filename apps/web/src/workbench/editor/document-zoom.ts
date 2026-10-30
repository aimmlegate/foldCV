import { useEffect, useState, type RefObject } from "react";

export const zoomLevels = [0.75, 1, 1.25, 1.5] as const;
export type ZoomChoice = "fit" | (typeof zoomLevels)[number];
const key = "foldcv.workspace.zoom";
// The readability rule's scale is the largest the page takes when it follows the free width.
const largest = 1.25, smallest = 0.5;

export function parseZoom(value: string | null): ZoomChoice {
  return zoomLevels.find(level => String(level) === value) ?? "fit";
}

export function readZoom(): ZoomChoice {
  try { return parseZoom(localStorage.getItem(key)); } catch { return "fit"; }
}

export function saveZoom(value: ZoomChoice): void {
  try { localStorage.setItem(key, String(value)); } catch { /* Keep the choice for this opening when storage is unavailable. */ }
}

/** The scale that shows the whole page in the free width. */
export function fittedZoom(available: number, pageWidth: number): number {
  return Math.min(largest, Math.max(smallest, available / pageWidth));
}

/** The free width of a scroller changes with the window, the panes and the padding the Facts panel reserves. */
export function useFittedZoom(scroller: RefObject<HTMLElement | null>, pageWidth: number): number {
  const [zoom, setZoom] = useState(largest);
  useEffect(() => {
    const element = scroller.current;
    if (!element) return;
    const measure = () => {
      // A hidden pane has no width to follow.
      if (!element.clientWidth) return;
      const style = getComputedStyle(element);
      // The page's border counts too, or a scrollbar appears for two pixels.
      setZoom(fittedZoom(element.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight) - 4, pageWidth));
    };
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [scroller, pageWidth]);
  return zoom;
}
