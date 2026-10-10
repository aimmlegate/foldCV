import { expect, test } from "@playwright/test";
import { spawn, execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, existsSync, realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import type { ChildProcessWithoutNullStreams } from "node:child_process";
import { unzipSync } from "fflate";

const root = resolve(import.meta.dirname, "../../../");
const web = resolve(root, "apps/web");
let server: ChildProcessWithoutNullStreams;
let origin: string;
let temp: string;

test.beforeAll(async () => {
  execFileSync("npm", ["run", "build"], { cwd: web, stdio: "pipe" });
  temp = mkdtempSync(resolve(realpathSync(tmpdir()), "foldcv-browser-"));
  server = spawn(resolve(root, ".venv/bin/python"), ["tests/service/browser_workflow_fixture.py", temp],
    { cwd: root, stdio: "pipe" });
  origin = await new Promise<string>((resolveOrigin, reject) => {
    let output = "";
    let errors = "";
    const timeout = setTimeout(() => reject(new Error("fixture server timed out")), 10_000);
    server.stderr.on("data", (chunk: Buffer) => { errors += chunk.toString("utf8"); });
    server.stdout.on("data", (chunk: Buffer) => {
      output += chunk.toString("utf8");
      const line = output.split("\n")[0];
      if (line?.startsWith("http://127.0.0.1:")) { clearTimeout(timeout); resolveOrigin(line); }
    });
    server.on("exit", () => { clearTimeout(timeout); reject(new Error(`fixture server stopped: ${errors}`)); });
  });
});

test.afterAll(async () => {
  if (server && server.exitCode === null) {
    const stopped = new Promise<void>((resolveStopped) => server.once("exit", () => resolveStopped()));
    server.kill("SIGTERM");
    await stopped;
  }
  if (temp) rmSync(temp, { recursive: true, force: true });
});

test("real service keeps PDF preview identical to download and DOCX editable with zero generation", async ({ page }) => {
  test.setTimeout(90_000);
  let renders = 0;
  let textCalls = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/v1/render")) renders += 1;
    if (/\/v1\/(normalize|draft|rewrite)$/.test(request.url())) textCalls += 1;
  });
  await page.goto(`${origin}/#secret=synthetic-browser-secret-0123456789`);
  await page.getByRole("button", { name: "Загрузить вымышленный пример" }).click();
  await page.getByLabel("Текст блока").fill("Synthetic edited profile for exact export.");
  await page.getByRole("button", { name: "Применить правку" }).click();
  await page.getByRole("button", { name: "Обновить PDF" }).click();
  await expect(page.getByText("PDF готов", { exact: false })).toBeVisible({ timeout: 45_000 });
  const shown = await page.getByTitle("Превью PDF").evaluate(async (iframe) => {
    if (!(iframe instanceof HTMLIFrameElement) || !iframe.src) throw new Error("missing PDF viewer");
    return Array.from(new Uint8Array(await (await fetch(iframe.src)).arrayBuffer()));
  });
  await page.getByRole("button", { name: "3. Выгрузка" }).click();
  const pdfPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать PDF" }).click();
  const pdf = await pdfPromise;
  expect(pdf.suggestedFilename()).toBe("resume.pdf");
  const pdfPath = await pdf.path();
  expect(pdfPath).not.toBeNull();
  expect(readFileSync(pdfPath!)).toEqual(Buffer.from(shown));
  const docxPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать DOCX" }).click();
  const docx = await docxPromise;
  const docxPath = await docx.path();
  expect(docxPath).not.toBeNull();
  const document = unzipSync(new Uint8Array(readFileSync(docxPath!)));
  expect(new TextDecoder().decode(document["word/document.xml"])).toContain("Synthetic edited profile for exact export.");
  expect(renders).toBe(1);
  await page.getByRole("button", { name: "2. Редактор" }).click();
  await page.getByLabel("Текст блока").fill("A second explicit synthetic revision.");
  await page.getByRole("button", { name: "Применить правку" }).click();
  await page.getByRole("button", { name: "3. Выгрузка" }).click();
  const newerDocxPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Собрать и скачать DOCX" }).click();
  const newerDocx = await newerDocxPromise;
  const newerPath = await newerDocx.path();
  expect(newerPath).not.toBeNull();
  const newerDocument = unzipSync(new Uint8Array(readFileSync(newerPath!)));
  expect(new TextDecoder().decode(newerDocument["word/document.xml"])).toContain("A second explicit synthetic revision.");
  await page.getByRole("button", { name: "2. Редактор" }).click();
  await expect(page.getByText("PDF готов", { exact: false })).toBeVisible();
  const newerShown = await page.getByTitle("Превью PDF").evaluate(async (iframe) => {
    if (!(iframe instanceof HTMLIFrameElement) || !iframe.src) throw new Error("missing PDF viewer");
    return Array.from(new Uint8Array(await (await fetch(iframe.src)).arrayBuffer()));
  });
  await page.getByRole("button", { name: "3. Выгрузка" }).click();
  const newerPdfPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать PDF" }).click();
  const newerPdfPath = await (await newerPdfPromise).path();
  expect(newerPdfPath).not.toBeNull();
  expect(readFileSync(newerPdfPath!)).toEqual(Buffer.from(newerShown));
  expect(renders).toBe(2);
  expect(textCalls).toBe(0);
  expect(existsSync(resolve(temp, "generation-attempt"))).toBe(false);
});
