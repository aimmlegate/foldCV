import * as monaco from "monaco-editor";
import { configureMonacoYaml } from "monaco-yaml";
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import { useEffect, useRef } from "react";
import schema from "../../../../../../contracts/template-source.schema.json";
import { pointerRange, technicalLines, type TemplateProblem } from "./config";
import YamlWorker from "./yaml.worker?worker";

// The repository layout: the template's "# yaml-language-server: $schema=../../contracts/..." line resolves to SCHEMA_URI.
const MODEL_URI = monaco.Uri.parse("file:///templates/active/template.yaml");
const SCHEMA_URI = "file:///contracts/template-source.schema.json";
const SERVER_OWNER = "foldcv-template-check";

self.MonacoEnvironment = { getWorker: (_moduleId: string, label: string) => label === "yaml" ? new YamlWorker() : new EditorWorker() };
// The schema is generated from the Python model plus the short form, so hints work offline; the server stays the authority.
configureMonacoYaml(monaco, { enableSchemaRequest: false, validate: true, hover: true, completion: true,
  schemas: [{ fileMatch: [MODEL_URI.toString()], uri: SCHEMA_URI, schema }] });

export type YamlEditorProps = { value: string; change: (value: string) => void; problem: TemplateProblem | null; readOnly: boolean;
  technical: boolean };

function foldTechnical(instance: monaco.editor.IStandaloneCodeEditor, show: boolean) {
  const model = instance.getModel(), selectionLines = model ? technicalLines(model.getValue()) : [];
  // The fold commands wait for the folding ranges, so this also works right after a new value.
  if (selectionLines.length) instance.trigger("foldcv", show ? "editor.unfold" : "editor.fold", { selectionLines, levels: 1, direction: "down" });
}

/** Monaco with live schema checks; `problem` is the server compiler's finding, placed at its JSON pointer. Technical
 * sections stay folded unless `technical` is set. */
export default function YamlEditor({ value, change, problem, readOnly, technical }: YamlEditorProps) {
  const host = useRef<HTMLDivElement>(null), editor = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const changeRef = useRef(change), external = useRef(false), technicalRef = useRef(technical);
  changeRef.current = change; technicalRef.current = technical;
  useEffect(() => {
    if (!host.current) return;
    const model = monaco.editor.getModel(MODEL_URI) ?? monaco.editor.createModel(value, "yaml", MODEL_URI);
    const instance = monaco.editor.create(host.current, { model, theme: "vs", automaticLayout: true, minimap: { enabled: false },
      fontSize: 13, tabSize: 2, insertSpaces: true, scrollBeyondLastLine: false, wordWrap: "off", renderWhitespace: "boundary" });
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
    if (!problem) { monaco.editor.setModelMarkers(model, SERVER_OWNER, []); return; }
    const range = pointerRange(model.getValue(), problem.path);
    const start = model.getPositionAt(range.start), end = model.getPositionAt(range.end);
    monaco.editor.setModelMarkers(model, SERVER_OWNER, [{ severity: monaco.MarkerSeverity.Error, message: `${problem.path}: ${problem.message}`,
      startLineNumber: start.lineNumber, startColumn: start.column, endLineNumber: end.lineNumber, endColumn: end.column }]);
    // The cursor unfolds a folded section that hides the problem.
    editor.current?.setPosition(start);
    editor.current?.revealLineInCenterIfOutsideViewport(start.lineNumber);
  }, [problem]);
  return <div className="template-yaml-editor" ref={host} />;
}
