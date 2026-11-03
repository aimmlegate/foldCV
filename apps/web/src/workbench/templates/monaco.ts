import * as monaco from "monaco-editor";
import { configureMonacoYaml } from "monaco-yaml";
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import schema from "../../../../../contracts/template-source.schema.json";
import YamlWorker from "./yaml.worker?worker";

// The editor and the proposal diff share one setup, whichever loads first.
// The repository layout: the template's "# yaml-language-server: $schema=../../contracts/..." line resolves to SCHEMA_URI.
export const MODEL_URI = monaco.Uri.parse("file:///templates/active/template.yaml");
const SCHEMA_URI = "file:///contracts/template-source.schema.json";

self.MonacoEnvironment = { getWorker: (_moduleId: string, label: string) => label === "yaml" ? new YamlWorker() : new EditorWorker() };
// The schema is generated from the Python model plus the short form, so hints work offline; the server stays the authority.
configureMonacoYaml(monaco, { enableSchemaRequest: false, validate: true, hover: true, completion: true,
  schemas: [{ fileMatch: [MODEL_URI.toString()], uri: SCHEMA_URI, schema }] });

export { monaco };
