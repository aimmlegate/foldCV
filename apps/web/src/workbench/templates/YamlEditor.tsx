import { useEffect, useImperativeHandle, useRef, type Ref } from "react";
import { pointerRange, sectionTab, topLevelSections, type SectionTab, type TemplateProblem } from "./config";
import { MODEL_URI, monaco, monacoTheme } from "./monaco";

const SERVER_OWNER = "foldcv-template-check";

/** `reveal` puts the cursor on the problem again, for the status line after the reader moved away. */
export type YamlEditorHandle = { reveal: () => void };
export type YamlEditorProps = { value: string; change: (value: string) => void; problem: TemplateProblem | null; readOnly: boolean;
  tab: SectionTab; ref?: Ref<YamlEditorHandle> };

/** Monaco with live schema checks; `problem` is the server compiler's finding, placed at its JSON pointer. The top-level
 * keys of `tab` stay open, the others folded. */
export default function YamlEditor({ value, change, problem, readOnly, tab, ref }: YamlEditorProps) {
  const host = useRef<HTMLDivElement>(null), editor = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const changeRef = useRef(change), external = useRef(false), tabRef = useRef(tab);
  const problemAt = useRef<monaco.IPosition | null>(null), arranged = useRef(0);
  changeRef.current = change; tabRef.current = tab;
  /** Folds the keys outside the tab, opens the tab's keys, then shows `at` or the tab's first line. The fold commands
   * wait for the folding ranges, so this also works right after a new value; a later call wins. No smooth scroll
   * and no focus here: in WKWebView that pair leaves the scroller unpainted (D144). */
  const arrange = (at: monaco.IPosition | null) => {
    const instance = editor.current, model = instance?.getModel();
    if (!instance || !model) return;
    const run = ++arranged.current, sections = topLevelSections(model.getValue());
    const inside = sections.filter(section => sectionTab(section.key) === tabRef.current).map(section => section.line);
    const outside = sections.filter(section => sectionTab(section.key) !== tabRef.current).map(section => section.line);
    void (async () => {
      if (outside.length) await instance.getAction("editor.fold")?.run({ selectionLines: outside, levels: 1, direction: "down" });
      if (inside.length) await instance.getAction("editor.unfold")?.run({ selectionLines: inside, levels: 1, direction: "down" });
      if (run !== arranged.current || editor.current !== instance) return;
      if (at) { instance.setPosition(at); instance.revealLineInCenter(at.lineNumber); }
      else instance.revealLineNearTop(tabRef.current === "template" ? 1 : (inside[0] ?? 0) + 1);
    })();
  };
  const arrangeRef = useRef(arrange);
  arrangeRef.current = arrange;
  useImperativeHandle(ref, () => ({ reveal: () => {
    const instance = editor.current, at = problemAt.current;
    if (!instance || !at) return;
    instance.setPosition(at); instance.revealLineInCenter(at.lineNumber); instance.focus();
  } }), []);
  useEffect(() => {
    if (!host.current) return;
    const model = monaco.editor.getModel(MODEL_URI) ?? monaco.editor.createModel(value, "yaml", MODEL_URI);
    const instance = monaco.editor.create(host.current, { model, theme: monacoTheme(), automaticLayout: true, minimap: { enabled: false },
      fontSize: 13, tabSize: 2, insertSpaces: true, scrollBeyondLastLine: false, wordWrap: "off", renderWhitespace: "none",
      // The tabs fold whole sections; the default fold background would paint them as a selection.
      foldingHighlight: false });
    const listener = model.onDidChangeContent(() => { if (!external.current) changeRef.current(model.getValue()); });
    editor.current = instance;
    arrangeRef.current(null);
    return () => { listener.dispose(); instance.dispose(); model.dispose(); editor.current = null; };
  }, []); // One model per mount; later values arrive through the effect below.
  useEffect(() => {
    const model = editor.current?.getModel();
    // A value from the parent (load, save, reset) is not a user edit.
    if (!model || model.getValue() === value) return;
    external.current = true;
    try { model.setValue(value); } finally { external.current = false; }
    arrangeRef.current(null);
  }, [value]);
  useEffect(() => { arrangeRef.current(null); }, [tab]);
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
    // The parent opened the problem's tab; the cursor also unfolds a nested section that hides it.
    arrangeRef.current(start);
  }, [problem]);
  return <div className="template-yaml-editor" ref={host} />;
}
