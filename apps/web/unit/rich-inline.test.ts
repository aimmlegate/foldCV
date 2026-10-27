import assert from "node:assert/strict";
import test from "node:test";
import { wireColor, wireMarks } from "../src/rich/inline";

test("editor marks become explicit wire styles with palette names as RGB values", () => {
  assert.deepEqual(wireMarks({}), { bold: false, italic: false, underline: false, strike: false, code: false,
    textColor: "default", backgroundColor: "default" });
  const styled = wireMarks({ underline: true, strike: true, code: true, backgroundColor: "blue", textColor: "rgb(12, 34, 56)" });
  assert.equal(styled.backgroundColor, "#ddebf1");
  assert.equal(styled.textColor, "#0c2238");
  assert.equal(styled.underline && styled.strike && styled.code, true);
});

test("unsupported colors cannot silently become default", () => {
  assert.equal(wireColor("#aBc", "text"), "#aabbcc");
  assert.equal(wireColor("#A0B1C2", "background"), "#a0b1c2");
  assert.throws(() => wireColor("rgb(256, 0, 0)", "text"), /RICH_COLOR_UNSUPPORTED/);
  assert.throws(() => wireColor("invented-color", "text"), /RICH_COLOR_UNSUPPORTED/);
});
