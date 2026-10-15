// Read demonstration data without loading the prototype's browser controller.
import fs from "node:fs";
import vm from "node:vm";
const context = { innerWidth: 1440, document: { querySelector: () => ({ outerHTML: "" }) } };
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync("design/future-editor/visual/index.js", "utf8"), context);
const source = fs.readFileSync("design/future-editor/prototype.js", "utf8");
vm.runInContext(source.slice(0, source.indexOf("state.projects = [sampleProject")), context);
process.stdout.write(vm.runInContext('JSON.stringify(sampleProject("uir-structured"), null, 2)', context));
