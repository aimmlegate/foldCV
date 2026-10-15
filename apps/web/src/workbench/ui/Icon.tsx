import sprite from "../../../../../design/future-editor/visual/icons.svg?no-inline";

type Name = "fold" | "panel" | "undo" | "redo" | "list" | "link" | "table" | "image" | "spark" | "more" | "info" | "file" | "close" | "download" | "arrow" | "chevron";
export function Icon({ name }: { name: Name }) {
  return <svg aria-hidden="true"><use href={`${sprite}#i-${name}`} /></svg>;
}
