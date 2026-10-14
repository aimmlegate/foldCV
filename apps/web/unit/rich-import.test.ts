import assert from "node:assert/strict";
import test from "node:test";
import { hasInput, importBody } from "../src/rich/import-source";

test("paste import keeps every source byte and uses the paste multipart contract", async () => {
  const text = "  Original\r\n\nТелефон +1 555 0100\n";
  const body = importBody({ kind: "text", text });
  assert.deepEqual([...body.keys()], ["paste"]);
  const file = body.get("paste");
  assert.ok(file instanceof File);
  assert.equal(file.name, "pasted.txt");
  assert.deepEqual(new Uint8Array(await file.arrayBuffer()), new TextEncoder().encode(text));
  assert.equal(hasInput({ kind: "text", text: " \n\t" }), false);
  assert.equal(hasInput({ kind: "text", text }), true);
});

test("file import retains the chosen file instead of sending a stale pasted draft", async () => {
  const file = new File([new Uint8Array([0, 255, 2])], "resume.pdf", { type: "application/pdf" });
  const input = { kind: "file" as const, file };
  const body = importBody(input);
  assert.equal(hasInput(input), true);
  assert.equal(body.get("file"), file);
  assert.equal(body.has("paste"), false);
  assert.deepEqual(new Uint8Array(await file.arrayBuffer()), new Uint8Array([0, 255, 2]));
});
