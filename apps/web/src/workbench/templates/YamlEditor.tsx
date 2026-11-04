import { useEffect, useImperativeHandle, useRef, type Ref } from "react";
import { pointerRange, technicalLines, type TemplateProblem } from "./config";
import { MODEL_URI, monaco, monacoTheme } from "./monaco";

const SERVER_OWNER = "foldcv-template-check";

/** `reveal` puts the cursor on the problem again, for the status line after the reader moved away. */
export type YamlEditorHandle = { reveal: () => void };
export type YamlEditorProps = { value: string; change: (value: string) => void; problem: TemplateProblem | null; readOnly: boolean;
  technical: boolean; ref?: Ref<YamlEditorHandle> };

function foldTechnical(instance: monaco.editor.IStandaloneCodeEditor, show: boolean) {
  const model = instance.getModel(), selectionLines = model ? technicalLines(model.getValue()) : [];
  // The fold commands wait for the folding ranges, so this also works right after a new value.
  if (selectionLines.length) instance.trigger("foldcv", show ? "editor.unfold" : "editor.fold", { selectionLines, levels: 1, direction: "down" });
}

/** Monaco with live schema checks; `problem` is the server compiler's finding, placed at its JSON pointer. Technical
 * sections stay folded unless `technical` is set. */
export default function YamlEditor({ value, change, problem, readOnly, technical, ref }: YamlEditorProps) {
  const host = useRef<HTMLDivElement>(null), editor = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const problemAt = useRef<monaco.IPosition | null>(null);
  useImperativeHandle(ref, () => ({ reveal: () => {
    const instance = editor.current, at = problemAt.current;
    if (!instance || !at) return;
    instance.setPosition(at); instance.revealLineInCenter(at.lineNumber); instance.focus();
  } }), []);
  const changeRef = useRef(change), external = useRef(false), technicalRef = useRef(technical);
  changeRef.current = change; technicalRef.current = technical;
  useEffect(() => {
    if (!host.current) return;
    const model = monaco.editor.getModel(MODEL_URI) ?? monaco.editor.createModel(value, "yaml", MODEL_URI);
    const instance = monaco.editor.create(host.current, { model, theme: monacoTheme(), automaticLayout: true, minimap: { enabled: false },
      fontSize: 13, tabSize: 2, insertSpaces: true, scrollBeyondLastLine: false, wordWrap: "off", renderWhitespace: "none" });
    const listener = model.onDidChangeContent(() => { if (!external.current) changeRef.current(model.getValue()); });
    editor.current = instance;
    foldTechnical(instance, technicalRef.current);
    return () => { listener.dispose(); instance.dispose(); model.dispose(); editor.current = null; };
  }, []); // One model per mount; later values arrive through the effect below.
  useEffect(() => {
    const model = editor.current?.getModel();
    // A value from the parent (load, save, reset) is not a user edit.
    if (!model || model.getValue() === value) return;
    external.current = true;
    try { model.setValue(value); } finally { external.current = false; }
    if (editor.current) foldTechnical(editor.current, technicalRef.current);
  }, [value]);
  useEffect(() => { if (editor.current) foldTechnical(editor.current, technical); }, [technical]);
  useEffect(() => { editor.current?.updateOptions({ readOnly }); }, [readOnly]);
  useEffect(() => {
    const model = editor.current?.getModel();
    if (!model) return;
    if (!problem) { monaco.editor.setModelMarkers(model, SERVER_OWNER, []); problemAt.current = null; return; }
    const range = pointerRange(model.getValue(), problem.path);
    const start = model.getPositionAt(range.start), end = model.getPositionAt(range.end);
    problemAt.current = start;
    monaco.editor.setModelMarkers(model, SERVER_OWNER, [{ severity: monaco.MarkerSeverity.Error, message: `${problem.path}: ${problem.message}`,
      startLineNumber: start.lineNumber, startColumn: start.column, endLineNumber: end.lineNumber, endColumn: end.column }]);
    // The cursor unfolds a folded section that hides the problem.
    editor.current?.setPosition(start);
    editor.current?.revealLineInCenterIfOutsideViewport(start.lineNumber);
  }, [problem]);
  return <div className="template-yaml-editor" ref={host} />;
}
