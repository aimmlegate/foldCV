import { useState } from "react";
import type { RichProjectResponse } from "../../contracts/generated/rich_project_response";
import { Dialog } from "../ui/Dialog";
import { sourceText } from "./source";

export function SourceDialog({ sources, close }: { sources: NonNullable<RichProjectResponse["workspace"]["project"]>["sources"]; close: () => void }) {
  const [id, setId] = useState(sources[0]?.id ?? "");
  const source = sources.find(item => item.id === id);
  return <Dialog open close={close} title="Исходник">
    {sources.length > 1 && <label>Источник<select aria-label="Источник" value={id} onChange={event => setId(event.currentTarget.value)}>{sources.map(item => <option key={item.id} value={item.id}>{item.originalName}</option>)}</select></label>}
    <p className="dialog-subtitle">{source?.originalName ?? "Источник отсутствует"}</p>
    <div className="source-original">{source && sourceText(source)}</div>
  </Dialog>;
}
