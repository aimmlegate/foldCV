import sprite from "../../../../../design/future-editor/visual/icons.svg?no-inline";

type Name = "fold" | "panel" | "undo" | "redo" | "list" | "link" | "table" | "image" | "spark" | "more" | "info" | "file" | "close" | "download" | "arrow" | "chevron" | "plus" | "trash" | "upload" | "settings" | "check" | "chat" | "globe" | "expand" | "stop" | "copy" | "archive" | "warning" | "locate";
export function Icon({ name }: { name: Name }) {
  if (name === "settings") return <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M19.11 9.05L19.53 10.40L21.88 10.44L21.88 13.56L19.53 13.60L19.11 14.95L18.46 16.19L20.09 17.88L17.88 20.09L16.19 18.46L14.95 19.11L13.60 19.53L13.56 21.88L10.44 21.88L10.40 19.53L9.05 19.11L7.81 18.46L6.12 20.09L3.91 17.88L5.54 16.19L4.89 14.95L4.47 13.60L2.12 13.56L2.12 10.44L4.47 10.40L4.89 9.05L5.54 7.81L3.91 6.12L6.12 3.91L7.81 5.54L9.05 4.89L10.40 4.47L10.44 2.12L13.56 2.12L13.60 4.47L14.95 4.89L16.19 5.54L17.88 3.91L20.09 6.12L18.46 7.81Z" /><circle cx="12" cy="12" r="3" /></svg>;
  // The prototype sprite has no archive, warning or locate glyph and stays unchanged.
  if (name === "archive") return <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M3 4h18v4H3zM5 8v12h14V8M10 12h4" /></svg>;
  if (name === "warning") return <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 3 2 20h20L12 3zM12 10v4.5M12 17.5h.01" /></svg>;
  if (name === "locate") return <svg aria-hidden="true" viewBox="0 0 24 24"><circle cx="12" cy="12" r="6.5" /><path d="M12 2.5v4M12 17.5v4M2.5 12h4M17.5 12h4" /></svg>;
  return <svg aria-hidden="true"><use href={`${sprite}#i-${name}`} /></svg>;
}
