import { useEffect, useRef } from "react";
import { monaco } from "./monaco";

/** A read-only inline diff of the editor text against a proposed text; loaded only when a card opens it. */
export default function ProposalDiff({ original, modified }: { original: string; modified: string }) {
  const host = useRef<HTMLDivElement>(null);
  const models = useRef<{ original: monaco.editor.ITextModel; modified: monaco.editor.ITextModel } | null>(null);
  useEffect(() => {
    if (!host.current) return;
    const pair = { original: monaco.editor.createModel(original, "yaml"), modified: monaco.editor.createModel(modified, "yaml") };
    const diff = monaco.editor.createDiffEditor(host.current, { readOnly: true, originalEditable: false, renderSideBySide: false,
      automaticLayout: true, minimap: { enabled: false }, fontSize: 12, scrollBeyondLastLine: false, hideUnchangedRegions: { enabled: true } });
    diff.setModel(pair);
    models.current = pair;
    return () => { diff.dispose(); pair.original.dispose(); pair.modified.dispose(); models.current = null; };
  }, []); // One pair of models per mount; new texts arrive through the effect below.
  useEffect(() => {
    const pair = models.current;
    if (!pair) return;
    if (pair.original.getValue() !== original) pair.original.setValue(original);
    if (pair.modified.getValue() !== modified) pair.modified.setValue(modified);
  }, [original, modified]);
  return <div className="template-proposal-diff" ref={host} />;
}
