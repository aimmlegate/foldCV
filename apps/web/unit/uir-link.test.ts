import assert from "node:assert/strict";
import test from "node:test";
import { validLink } from "../src/workbench/editor/link";

test("link input accepts web/mail targets and refuses script, local and broken targets", () => {
  for (const value of ["https://example.com/cv?q=1#work", "http://localhost:1234/path", "mailto:alex@example.com"]) assert.equal(validLink(value), true, value);
  for (const value of ["", "javascript:alert(1)", "data:text/html,test", "file:///tmp/cv", "/relative", "https://", "mailto:", "https://example.com/\nattack"]) assert.equal(validLink(value), false, value);
});
