import * as monaco from "monaco-editor";
import { configureMonacoYaml } from "monaco-yaml";
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import { useEffect, useRef } from "react";
import schema from "../../../../../../contracts/json-schema/template_definition.schema.json";
import { pointerRange, type TemplateProblem } from "./config";
import YamlWorker from "./yaml.worker?worker";

// The repository layout: the template's "# yaml-language-server: $schema=../../contracts/..." line resolves to SCHEMA_URI.
const MODEL_URI = monaco.Uri.parse("file:///templates/active/template.yaml");
const SCHEMA_URI = "file:///contracts/json-schema/template_definition.schema.json";
const SERVER_OWNER = "foldcv-template-check";

self.MonacoEnvironment = { getWorker: (_moduleId: string, label: string) => label === "yaml" ? new YamlWorker() : new EditorWorker() };
// The schema is bundled from the generated contract, so validation works offline and matches the Python model.
configureMonacoYaml(monaco, { enableSchemaRequest: false, validate: true, hover: true, completion: true,
  schemas: [{ fileMatch: [MODEL_URI.toString()], uri: SCHEMA_URI, schema }] });

export type YamlEditorProps = { value: string; change: (value: string) => void; problem: TemplateProblem | null; readOnly: boolean };

/** Monaco with live schema checks; `problem` is the server compiler's finding, placed at its JSON pointer. */
export default function YamlEditor({ value, change, problem, readOnly }: YamlEditorProps) {
  const host = useRef<HTMLDivElement>(null), editor = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const changeRef = useRef(change), external = useRef(false);
  changeRef.current = change;
  useEffect(() => {
    if (!host.current) return;
    const model = monaco.editor.getModel(MODEL_URI) ?? monaco.editor.createModel(value, "yaml", MODEL_URI);
    const instance = monaco.editor.create(host.current, { model, theme: "vs", automaticLayout: true, minimap: { enabled: false },
      fontSize: 13, tabSize: 2, insertSpaces: true, scrollBeyondLastLine: false, wordWrap: "off", renderWhitespace: "boundary" });
    const listener = model.onDidChangeContent(() => { if (!external.current) changeRef.current(model.getValue()); });
    editor.current = instance;
    return () => { listener.dispose(); instance.dispose(); model.dispose(); editor.current = null; };
  }, []); // One model per mount; later values arrive through the effect below.
  useEffect(() => {
    const model = editor.current?.getModel();
    // A value from the parent (load, save, reset) is not a user edit.
    if (model && model.getValue() !== value) { external.current = true; try { model.setValue(value); } finally { external.current = false; } }
  }, [value]);
  useEffect(() => { editor.current?.updateOptions({ readOnly }); }, [readOnly]);
  useEffect(() => {
    const model = editor.current?.getModel();
    if (!model) return;
    if (!problem) { monaco.editor.setModelMarkers(model, SERVER_OWNER, []); return; }
    const range = pointerRange(model.getValue(), problem.path);
    const start = model.getPositionAt(range.start), end = model.getPositionAt(range.end);
    monaco.editor.setModelMarkers(model, SERVER_OWNER, [{ severity: monaco.MarkerSeverity.Error, message: `${problem.path}: ${problem.message}`,
      startLineNumber: start.lineNumber, startColumn: start.column, endLineNumber: end.lineNumber, endColumn: end.column }]);
    editor.current?.revealLineInCenterIfOutsideViewport(start.lineNumber);
  }, [problem]);
  return <div className="template-yaml-editor" ref={host} />;
}
