import { useId, useState, type DragEvent, type KeyboardEvent } from "react";
import type { PanelCommand } from "../../rich/v7-panel";
import { adjacentTechnology, lineMates } from "../../rich/technology-order";

/** `lines`: the lines a move stays inside; without them every listed id can reach every other. */
export function useTechnologyDrag(ids: readonly string[], operation: "move_technology" | "move_focus", disabled: boolean,
  submit: (command: PanelCommand) => Promise<void>, lines?: readonly (readonly string[])[]) {
  const scope = useId();
  const reachable = (id: string) => lines ? lineMates(lines, ids, id) : ids;
  const [dragging, setDragging] = useState<string | null>(null), [over, setOver] = useState<string | null>(null);
  function move(recordId: string, beforeRecordId: string | null) {
    if (!disabled && recordId !== beforeRecordId) void submit({ operation, recordId, beforeRecordId }).catch(() => {});
  }
  return {
    handle: (id: string) => ({
      draggable: !disabled,
      onDragStart: (event: DragEvent<HTMLButtonElement>) => {
        if (disabled) { event.preventDefault(); return; }
        event.dataTransfer.setData("application/x-foldcv-technology", scope);
        event.dataTransfer.effectAllowed = "move"; setDragging(id);
      },
      onDragEnd: () => { setDragging(null); setOver(null); },
      onKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => {
        if (!event.altKey || event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
        event.preventDefault(); event.stopPropagation();
        const target = adjacentTechnology(reachable(id), id, event.key === "ArrowUp" ? -1 : 1);
        if (target !== undefined) move(id, target);
      },
    }),
    target: (id: string | null) => ({
      "data-drop-target": dragging !== null && dragging !== id && over === (id ?? "end") || undefined,
      onDragOver: (event: DragEvent<HTMLElement>) => {
        if (disabled || !dragging || dragging === id || id !== null && !reachable(dragging).includes(id)
          || !event.dataTransfer.types.includes("application/x-foldcv-technology")) return;
        event.preventDefault(); event.dataTransfer.dropEffect = "move"; setOver(id ?? "end");
      },
      onDrop: (event: DragEvent<HTMLElement>) => {
        if (disabled || !dragging || id !== null && !reachable(dragging).includes(id)
          || event.dataTransfer.getData("application/x-foldcv-technology") !== scope) return;
        event.preventDefault(); move(dragging, id); setDragging(null); setOver(null);
      },
    }),
    dragging,
    /** Whether the id has a neighbour to move past. */
    movable: (id: string) => reachable(id).length > 1,
  };
}
