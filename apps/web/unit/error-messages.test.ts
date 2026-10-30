import assert from "node:assert/strict";
import test from "node:test";
import { register } from "node:module";
import { readdirSync, readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join, relative } from "node:path";
import ts from "typescript";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import catalog from "../../../contracts/error-messages.ru.json" with { type: "json" };
import { defaultErrorMessage, errorMessage, knownErrorMessage, messageText } from "../src/errors/messages";
import { ProjectApiFailure } from "../src/rich/v7-connection";
import { factError } from "../src/workbench/facts/error";
import { noticeText } from "../src/workbench/ui/notice-text";
import { errorText } from "../src/assistant/presentation";
register(`data:text/javascript,${encodeURIComponent('export async function load(url, context, next) { if (url.includes("/icons.svg")) return { format: "module", source: \'export default "icons.svg"\', shortCircuit: true }; return next(url, context); }')}`, import.meta.url);
const { Header } = await import("../src/workbench/layout/Header");
const { Installation } = await import("../src/workbench/settings/Installation");

const root = fileURLToPath(new URL("../../../", import.meta.url));
const ignored: Readonly<Record<string, string>> = catalog.nonErrorSymbols;
const rawCode = /\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b/u;

function sources(directory: string): string[] {
  if (!existsSync(directory)) return [];
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return ["generated", "standalone", "node_modules"].includes(entry.name) ? [] : sources(path);
    return entry.isFile() && /\.tsx?$/u.test(path) ? [path] : [];
  });
}

test("every explicit frontend and desktop code has a public description or a documented non-error meaning", () => {
  const missing: string[] = [];
  for (const path of [...sources(join(root, "apps/web/src")), ...sources(join(root, "apps/desktop/src"))]) {
    const source = ts.createSourceFile(path, readFileSync(path, "utf8"), ts.ScriptTarget.Latest, true);
    const visit = (node: ts.Node): void => {
      const errorLiteral = ts.isStringLiteralLike(node) && ts.isNewExpression(node.parent)
        && /(?:Error|Failure)$/u.test(node.parent.expression.getText(source))
        && node.parent.arguments?.[0] === node && /^[A-Z][A-Z0-9_]*$/u.test(node.text);
      if (ts.isStringLiteralLike(node) && (errorLiteral || /^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$/u.test(node.text))
        && !Object.hasOwn(ignored, node.text) && !knownErrorMessage(node.text)) {
        missing.push(`${relative(root, path)}:${source.getLineAndCharacterOfPosition(node.getStart()).line + 1} ${node.text}`);
      }
      ts.forEachChild(node, visit);
    };
    visit(source);
  }
  assert.deepEqual(missing, []);
});

test("all catalog entries resolve to Russian text without raw codes", () => {
  assert.ok(Object.keys(catalog.codes).length > 600);
  for (const code of Object.keys(catalog.codes)) {
    const message = knownErrorMessage(code);
    assert.ok(message && /[А-Яа-яЁё]/u.test(message), code);
    assert.ok(!rawCode.test(message), code);
    assert.notEqual(message, code);
  }
  for (const reason of Object.values(ignored)) assert.ok(reason.trim());
});

for (const raw of ["FUTURE_SAVE_FAILURE", "toString", "__proto__", "Cannot read properties of undefined",
  "Error: private diagnostic\n at save (/Users/example/private.ts:12)", "Ошибка PROJECT_SAVE_FAILED в /private/tmp/secret", "Ошибка https://example.com/private", "Ошибка ENOSPC при записи", "Ошибка download_failed при загрузке"]) {
  test(`unrecognized diagnostic is hidden: ${raw.split("\n")[0]}`, () => {
    assert.equal(errorMessage(new Error(raw)), defaultErrorMessage);
    assert.equal(noticeText(raw), defaultErrorMessage);
  });
}

test("no message sends the user to the hidden «Лимиты» section (D110)", () => {
  for (const [key, message] of Object.entries(catalog.messages)) assert.ok(!message.includes("Лимиты"), key);
  for (const code of ["IMPORT_PROCESSING_EXHAUSTED", "PROJECT_TOO_LARGE", "JOB_STORAGE_FULL"]) assert.ok(!knownErrorMessage(code)?.includes("настройках"), code);
  assert.match(knownErrorMessage("IMPORT_PROCESSING_EXHAUSTED") ?? "", /исходник короче/u);
  assert.match(knownErrorMessage("PROJECT_TOO_LARGE") ?? "", /Уменьшите объём/u);
});

test("presentation preserves machine errors and existing human validation text", () => {
  const error = new ProjectApiFailure("PROJECT_SAVE_FAILED", 503);
  const message = errorMessage(error);
  assert.match(message, /сохранить/u); assert.ok(!message.includes(error.code));
  assert.equal(error.code, "PROJECT_SAVE_FAILED"); assert.equal(error.message, "PROJECT_SAVE_FAILED"); assert.equal(error.status, 503);
  for (const text of ["Сохранено", "Изменения сохраняются…", "Введите название технологии до 80 символов."])
    assert.equal(messageText(text), text);
  assert.equal(messageText(""), "");
  assert.equal(errorMessage(null), defaultErrorMessage);
  assert.equal(errorMessage({ code: "toString" }), defaultErrorMessage);
  assert.equal(errorMessage(new TypeError("Failed to fetch")), catalog.messages.connection);
  assert.equal(errorMessage(new DOMException("private abort text", "AbortError")), catalog.messages.cancelled);
});

test("all existing error presentation adapters use safe readable messages", () => {
  for (const code of ["PROJECT_SAVE_FAILED", "RICH_MUTATION_LIMIT", "AGENT_OUTCOME_UNKNOWN", "FUTURE_SAVE_FAILURE"]) {
    for (const message of [factError(new ProjectApiFailure(code)), errorText(code), noticeText(code)]) {
      assert.ok(message && /[А-Яа-яЁё]/u.test(message)); assert.ok(!message.includes(code)); assert.ok(!rawCode.test(message));
    }
  }
});

test("save status and installation render descriptions without error codes in visible text or titles", () => {
  const header = renderToStaticMarkup(createElement(Header, { title: "Synthetic resume", subtitle: "Engineer", collapsed: false,
    expand: () => {}, status: "PROJECT_SAVE_FAILED", ready: true, busy: false, save: () => {}, exportFile: () => {}, retrySave: () => {} }));
  assert.ok(!header.includes("PROJECT_SAVE_FAILED")); assert.match(header, /Не сохранено/u); assert.match(header, /сохранить/u);
  const installation = renderToStaticMarkup(createElement(Installation, { value: { available: true, state: "failed",
    version: "0.0.0", downloadedBytes: 0, totalBytes: 0, error: "download_failed" }, display: "Codex" }));
  assert.ok(!installation.includes("download_failed")); assert.match(installation, /скачать/u);
});

test("save failures, pending work and import warnings keep distinct meanings", () => {
  assert.match(errorMessage("DRAFT_STORAGE_FAILED"), /сохранить черновик/u);
  assert.match(errorMessage("DRAFT_STORAGE_FULL"), /объём хранения/u);
  assert.match(errorMessage("OUTCOME_UNKNOWN"), /не подтверждено/u);
  assert.match(errorMessage("BUSY"), /другое действие/u);
  assert.match(errorMessage("busy"), /Codex/u);
  assert.match(errorMessage("IMAGE_INVALID"), /добавить или прочитать/u);
  assert.match(errorMessage("IMAGE"), /не распознано как текст/u);
  assert.match(errorMessage("IMPORT_CONTENT_RECOVERED"), /восстановлена/u);
});
