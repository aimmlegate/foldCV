import { expect, test } from "@playwright/test";
import { execFileSync, spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { mkdtempSync, readFileSync, realpathSync, rmSync, cpSync, existsSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { createHash } from "node:crypto";
import type { GuiProjectResponse } from "../src/contracts/generated/gui_project_response";
import { validateContract } from "../src/contracts/validate";
import type { Page } from "@playwright/test";
import type { GuiRewriteRequest } from "../src/contracts/generated/gui_rewrite_request";
import type { RulesSettings } from "../src/contracts/generated/rules_settings";
import { unzipSync } from "fflate";

const root = resolve(import.meta.dirname, "../../..");
let temp: string, runRoot: string, origin: string;
let server: ChildProcessWithoutNullStreams | undefined;
test.beforeAll(() => {
  temp = mkdtempSync(resolve(realpathSync(tmpdir()), "foldcv-next-entry-"));
  execFileSync("npm", ["run", "build", "--", "--outDir", resolve(temp, "dist")], { cwd: resolve(root, "apps/web"), stdio: "pipe" });
});
test.beforeEach(async ({}, info) => {
  runRoot = mkdtempSync(resolve(temp, "run-"));
  cpSync(resolve(temp, "dist"), resolve(runRoot, "dist"), { recursive: true });
  const example = info.title.includes("focus warning") ? "E2-focus" : info.title.includes("E2") ? "E2" : "E1";
  if (info.title.includes("task A13")) writeFileSync(resolve(runRoot, "multiple-examples"), "Controlled E1/E2 projects.");
  if (info.title.includes("task A11")) writeFileSync(resolve(runRoot, "related-example"), "Controlled shared-claim fixture.");
  if (info.title.includes("without LibreOffice")) writeFileSync(resolve(runRoot, "no-converter"), "The owned worker must render with unavailable legacy dependencies.");
  if (!info.title.includes("A10") && !info.title.includes("task A11")) writeFileSync(resolve(runRoot, "pause-analysis"), "Isolate the accepted foreground feature from background analysis.");
  origin = await launch(example);
});
async function launch(example: string): Promise<string> {
  const child = spawn(resolve(root, ".venv/bin/python"), ["tests/service/browser_next_fixture.py", runRoot, resolve(runRoot, "dist"), example], { cwd: root, stdio: "pipe" });
  server = child;
  return new Promise<string>((ready, reject) => {
    let text = "";
    const timer = setTimeout(() => reject(new Error("Controlled entry server timed out")), 15000);
    child.stdout.on("data", (chunk: Buffer) => {
      text += chunk.toString("utf8"); const line = text.split("\n")[0];
      if (line?.startsWith("http://127.0.0.1:")) { clearTimeout(timer); ready(line); }
    });
    child.once("exit", () => { clearTimeout(timer); reject(new Error("Controlled entry server stopped")); });
  });
}
async function stopServer() {
  if (server && server.exitCode === null && server.signalCode === null) {
    const exit = new Promise<void>(ready => server?.once("exit", () => ready()));
    server.kill("SIGTERM"); await exit;
  }
}
test.afterEach(async () => {
  await stopServer();
  if (existsSync(resolve(runRoot, "pause-analysis")) && existsSync(resolve(runRoot, "model-requests.json"))) {
    const modelRequests: unknown = JSON.parse(readFileSync(resolve(runRoot, "model-requests.json"), "utf8"));
    expect(JSON.stringify(modelRequests)).not.toContain('reconcile_edits');
  }
  if (existsSync(resolve(runRoot, "operations"))) expect(readdirSync(resolve(runRoot, "operations"))).toEqual([]);
});
test.afterAll(() => { if (temp) rmSync(temp, { recursive: true, force: true }); });
function response(value: unknown): GuiProjectResponse {
  if (!isResponse(value)) throw new Error("Invalid project response");
  return value;
}
function isResponse(value: unknown): value is GuiProjectResponse { return validateContract("gui_project_response", value); }

test("built API entry creates E1 with two operations and no browser assembly or fact forms", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await expect(page.locator('[data-app="foldcv-next"]')).toHaveCount(1);
  expect(new URL(page.url()).hash).toBe("");
  await expect(page.getByRole("button", { name: "Создать резюме" })).toBeDisabled();
  await page.getByRole("button", { name: "Открыть пример" }).click();
  const raw = readFileSync(resolve(root, "tests/fixtures/recovery/E1.txt"), "utf8");
  await expect(page.getByLabel("Или вставьте текст")).toHaveValue(raw);
  const created = page.waitForResponse(result => new URL(result.url()).pathname === "/v1/projects" && result.request().method() === "POST");
  await page.getByRole("button", { name: "Создать резюме" }).click();
  const initial: unknown = await (await created).json();
  const id = response(initial).workspace.projectId;
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  await expect(page.locator('[data-field-content="candidate/name"]')).toHaveText("Ирина Примерова");
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Разрабатываю backend-сервисы на Python.");
  await expect(page.locator('[contenteditable="true"]')).toHaveCount(1);
  const value: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();
  const workspace = response(value).workspace;
  expect(workspace.project?.operations.map(operation => operation.usage?.logicalAttempts)).toEqual([1, 1]);
  expect(workspace.project?.renders).toHaveLength(1);
  expect([workspace.projectRevision, workspace.documentRevision]).toEqual([2, 2]);
  expect(response(value).durability).toBe("durable");
  expect(response(value).savedDocumentRevision).toBe(workspace.documentRevision);
  expect(existsSync(resolve(runRoot, "FoldCV/projects", id, "workspace.json"))).toBe(true);
  const artifact = workspace.project?.renders[0];
  const link = page.getByRole("link", { name: "Скачать исходный DOCX" });
  await expect(link).toHaveAttribute("href", `/v1/projects/${id}/renders/${artifact?.id}/docx`);
  const downloaded = page.waitForEvent("download");
  await link.click();
  const file = await downloaded;
  const path = await file.path();
  expect(path).not.toBeNull();
  const bytes = readFileSync(path ?? "");
  expect(createHash("sha256").update(bytes).digest("hex")).toBe(artifact?.docx?.sha256);
  expect(bytes.subarray(0, 2).toString()).toBe("PK");
  await expect(page.getByRole("button", { name: "Сохранить проект", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Экспорт DOCX", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Настройки", exact: true })).toBeVisible();
});

test("built E2 entry locates empty sections and one shared conflict outside editable text", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByLabel("Или вставьте текст").fill(readFileSync(resolve(root, "tests/fixtures/recovery/E2.txt"), "utf8"));
  await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  await expect(page.locator('[data-annotation-type="missing"]')).toHaveCount(3);
  await expect(page.locator('[data-section-id="education"]')).toHaveText("Образование не указано");
  await expect(page.locator('[data-section-id="languages"]')).toHaveText("Языки не указаны");
  const conflict = page.locator('[data-annotation-code="team_size_conflict"]');
  await expect(conflict).toHaveCount(1);
  await expect(conflict).toHaveAttribute("contenteditable", "false");
  const anchor = await conflict.getAttribute("data-anchor-field");
  expect(anchor).toMatch(/^job:.+\/context$/);
  await expect(page.locator(`[data-field-content="${anchor}"]`)).toHaveText("");
  await expect(page.locator('[data-annotation-code="missing_surname"]')).toHaveCount(0);
  await expect(page.locator('[data-field-content^="education:"]')).toHaveCount(0);
  await expect(page.locator('[data-field-content^="language:"]')).toHaveCount(0);
  expect(await page.locator('[data-field-content]').allTextContents()).not.toContain("Образование не указано");
  await expect(page.getByRole("link", { name: "Скачать исходный DOCX" })).toBeVisible();
});

test("built E2 focus warning stays at skills and outside authored text", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByLabel("Или вставьте текст").fill(readFileSync(resolve(root, "tests/fixtures/recovery/E2.txt"), "utf8"));
  await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  const warning = page.locator('[data-annotation-code="focus_entry_removed"]');
  await expect(warning).toHaveAttribute("data-annotation-type", "warning");
  await expect(warning).toHaveAttribute("data-section-id", "skills-focus");
  await expect(warning).toHaveAttribute("contenteditable", "false");
  await expect(page.locator('[data-annotation-type="missing"]')).toHaveCount(3);
  expect((await page.locator('[data-field-content]').allTextContents()).join(" ")).not.toContain("исключена из фокуса");
});

test("built E1 source panel reads captured job evidence with zero extra content operations", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Открыть пример" }).click();
  await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  const context = page.locator('[data-field-content$="/context"]').first();
  await context.evaluate(field => {
    const text = document.createTreeWalker(field, NodeFilter.SHOW_TEXT).nextNode();
    const root = document.querySelector<HTMLElement>('[contenteditable="true"]');
    if (!text || !root) throw new Error("Context field is missing");
    root.focus(); window.getSelection()?.setBaseAndExtent(text, 0, text, text.textContent?.length ?? 0);
    document.dispatchEvent(new Event("selectionchange"));
  });
  const read = page.waitForResponse(result => new URL(result.url()).pathname.endsWith("/source-context"));
  await page.getByRole("button", { name: "Показать исходник" }).click();
  const result: unknown = await (await read).json();
  expect(validateContract("source_context", result)).toBe(true);
  const panel = page.getByRole("complementary", { name: "Исходный контекст" });
  await expect(panel.locator("blockquote", { hasText: "Сервис обработки заказов." }).first()).toBeVisible();
  await expect(panel.locator('[data-source-relation="exact"]').first()).toBeVisible();
  await page.getByRole("button", { name: "Закрыть исходный контекст" }).click();
  await expect(panel).toHaveCount(0);
  const link = await page.getByRole("link", { name: "Скачать исходный DOCX" }).getAttribute("href");
  const id = link?.split("/")[3];
  const raw: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();
  expect(response(raw).workspace.project?.operations.filter(item => item.kind !== "reconcile_edits")).toHaveLength(2);
});

test("built E1 changed capture is rejected and source refresh preserves the typing buffer", async ({ page }) => {
  await page.route("**/source-context", async route => {
    const value: unknown = route.request().postDataJSON();
    if (typeof value !== "object" || value === null || !("documentRevision" in value) || typeof value.documentRevision !== "number") throw new Error("Invalid context request");
    await route.continue({ postData: JSON.stringify({ ...value, documentRevision: value.documentRevision - 1 }) });
  });
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Открыть пример" }).click();
  await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  const profile = page.locator('[data-field-content="profile/text"]');
  await profile.click();
  await page.keyboard.press("End");
  await page.keyboard.type(" Added 😀");
  await profile.evaluate(field => {
    const text = document.createTreeWalker(field, NodeFilter.SHOW_TEXT).nextNode();
    if (!text) throw new Error("Profile text is missing");
    window.getSelection()?.setBaseAndExtent(text, 0, text, text.textContent?.length ?? 0);
    document.dispatchEvent(new Event("selectionchange"));
  });
  await page.getByRole("button", { name: "Показать исходник" }).click();
  const panel = page.getByRole("complementary", { name: "Исходный контекст" });
  await expect(panel.getByRole("status")).toContainText("Выделение устарело");
  await expect(panel.locator("blockquote")).toHaveCount(0);
  await expect(profile).toContainText("Added 😀");
});

test("built E1 continuous typing retains a session and real two-step block restore", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Открыть пример" }).click();
  await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  const link = await page.getByRole("link", { name: "Скачать исходный DOCX" }).getAttribute("href"), id = link?.split("/")[3];
  const read = async () => { const value: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json(); return response(value).workspace; };
  const profile = page.locator('[data-field-content="profile/text"]'), original = await profile.innerText();
  await page.locator('[contenteditable="true"]').evaluate(root => root.setAttribute("data-instance", "original"));
  await profile.click();await page.keyboard.press("End");
  await page.keyboard.type(" Long continuous user addition", { delay: 80 });
  await expect.poll(async () => (await read()).project?.document.profile.text.text).toContain("Long continuous user addition");
  expect((await read()).undoSlots["profile"]).toBeNull();
  expect((await read()).editSessions["profile"]?.baseline.record.kind).toBe("profile");
  expect((await read()).project?.operations.filter(item => item.kind !== "reconcile_edits")).toHaveLength(2);
  await page.getByRole("button", { name: "Показать исходник" }).click();
  await expect(page.getByRole("complementary", { name: "Исходный контекст" }).getByRole("status")).toContainText("добавлен пользователем");
  await page.getByRole("button", { name: "Закрыть исходный контекст" }).click();
  await expect.poll(async () => (await read()).undoSlots["profile"]?.record.kind).toBe("profile");
  const first = await profile.innerText();
  await profile.click();await page.keyboard.press("End");await page.keyboard.type(" unfinished");
  await page.keyboard.press("Control+z");
  await expect(profile).toHaveText(first);
  expect((await read()).undoSlots["profile"]).not.toBeNull();
  await page.keyboard.press("Meta+z");
  await expect(profile).toHaveText(original);
  await expect.poll(async () => (await read()).undoSlots["profile"]).toBeNull();
  const revision = (await read()).documentRevision;
  await page.keyboard.press("Control+z");
  await expect(profile).toHaveText(original);
  await expect.poll(async () => (await read()).documentRevision).toBe(revision);
  await expect(page.locator('[contenteditable="true"]')).toHaveAttribute("data-instance", "original");
});

test("built E1 lost acknowledgment retry applies once and keeps newer buffered text", async ({ page }) => {
  let interrupted = false;
  await page.route("**/mutations", async route => {
    if (!interrupted) { interrupted = true;await route.fetch();await route.abort("failed"); }
    else await route.continue();
  });
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Открыть пример" }).click();await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  const profile = page.locator('[data-field-content="profile/text"]');await profile.click();await page.keyboard.press("End");await page.keyboard.type(" First");
  await expect(page.getByRole("alert")).toContainText("Не удалось сохранить правки");
  await expect(profile).toContainText("First");
  await page.keyboard.type(" newer");
  await page.getByRole("button", { name: "Повторить сохранение" }).click();
  await expect(page.getByRole("alert")).toHaveCount(0);
  const link = await page.getByRole("link", { name: "Скачать исходный DOCX" }).getAttribute("href"), id = link?.split("/")[3];
  await expect.poll(async () => { const raw: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();return response(raw).workspace.project?.document.profile.text.text; }).toContain("First newer");
  await expect(profile).toContainText("First newer");
  const raw: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();const workspace = response(raw).workspace;
  expect(workspace.project?.operations.filter(item => item.kind !== "reconcile_edits")).toHaveLength(2);expect(workspace.documentRevision).toBe(4);
  expect(workspace.editSessions["profile"]).toBeUndefined();
});

test("built E1 explicit rows periods and visibility survive editor projection changes", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Открыть пример" }).click();await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  await page.getByText("Разделы и строки", { exact: true }).click();
  await page.getByRole("button", { name: "Добавить работу", exact: true }).click();
  await expect(page.locator('[data-field-content$="/employer"]')).toHaveCount(3);
  await page.getByRole("button", { name: "Скрыть Работа 3", exact: true }).click();
  await expect(page.getByText("Работа 3 · скрыт из DOCX", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Показать Работа 3", exact: true }).click();
  await page.getByRole("button", { name: "Выше Работа 3", exact: true }).click();
  await expect(page.getByRole("button", { name: "Удалить Работа 2", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Удалить Работа 2", exact: true }).click();
  await expect(page.locator('[data-field-content$="/employer"]')).toHaveCount(2);
  await page.getByRole("button", { name: "Добавить образование", exact: true }).click();
  await expect(page.locator('[data-field-content$="/institution"]')).toHaveCount(2);
  await page.getByRole("button", { name: "Добавить язык", exact: true }).click();
  await expect(page.locator('[data-field-content^="language:"][data-field-content$="/name"]')).toHaveCount(3);
  await page.getByText("Периоды: Север", { exact: true }).click();
  const periods = page.locator('[data-period-job]').filter({ hasText: "Периоды: Север" });
  await periods.getByRole("button", { name: "Добавить период", exact: true }).click();
  await expect(periods.getByRole("checkbox")).toHaveCount(2);
  await periods.getByRole("button", { name: "Период выше" }).last().click();
  await periods.getByRole("button", { name: "Удалить период" }).first().click();
  await expect(periods.getByRole("checkbox")).toHaveCount(1);
  await page.getByRole("button", { name: "Отменить правку блока", exact: true }).click();
  await expect(periods.getByRole("checkbox")).toHaveCount(1);
  await expect(periods.getByRole("checkbox")).toBeChecked();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.locator('[contenteditable="true"]')).toHaveCount(1);
});

test("built E1 delayed edit acknowledgment preserves newer typing and editor identity", async ({ page }) => {
  let release = () => {};const held = new Promise<void>(ready => { release = ready; });
  let admitted = () => {};const written = new Promise<void>(ready => { admitted = ready; });
  let first = true;
  await page.route("**/mutations", async route => {
    if (first) { first = false;const result = await route.fetch();admitted();await held;await route.fulfill({ response: result }); }
    else await route.continue();
  });
  try {
    await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
    await page.getByRole("button", { name: "Открыть пример" }).click();await page.getByRole("button", { name: "Создать резюме" }).click();
    await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
    const profile = page.locator('[data-field-content="profile/text"]');
    await page.locator('[contenteditable="true"]').evaluate(root => root.setAttribute("data-instance", "original"));
    await profile.click();await page.keyboard.press("End");await page.keyboard.type(" First");
    await written;
    await page.keyboard.type(" newer");release();
    const link = await page.getByRole("link", { name: "Скачать исходный DOCX" }).getAttribute("href"), id = link?.split("/")[3];
    await expect.poll(async () => { const raw: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();return response(raw).workspace.project?.document.profile.text.text; }).toContain("First newer");
    await expect(profile).toContainText("First newer");
    await expect(page.locator('[contenteditable="true"]')).toHaveAttribute("data-instance", "original");
    await expect(page.getByRole("alert")).toHaveCount(0);
  } finally { release(); }
});

test("built E1 active composition sends no partial mutation and retains completed IME text", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Открыть пример" }).click();await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  const link = await page.getByRole("link", { name: "Скачать исходный DOCX" }).getAttribute("href"), id = link?.split("/")[3];
  const profile = page.locator('[data-field-content="profile/text"]');await profile.click();
  await profile.evaluate(field => {
    const root = document.querySelector('[contenteditable="true"]');const text = document.createTreeWalker(field, NodeFilter.SHOW_TEXT).nextNode();
    if (!root || !text) throw new Error("Profile text is missing");
    root.dispatchEvent(new CompositionEvent("compositionstart", { bubbles: true, data: "" }));
    text.textContent = `${text.textContent ?? ""}入力`;
    root.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertCompositionText", data: "入力", isComposing: true }));
  });
  await page.keyboard.press("Control+z");
  await page.waitForTimeout(1200);
  const before: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();
  expect(response(before).workspace.documentRevision).toBe(2);
  await profile.evaluate(field => {
    const root = field.closest('[contenteditable="true"]');
    root?.dispatchEvent(new CompositionEvent("compositionend", { bubbles: true, data: "入力" }));
    root?.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: "入力" }));
  });
  await expect.poll(async () => { const raw: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();return response(raw).workspace.project?.document.profile.text.text; }).toContain("入力");
  await expect(profile).toContainText("入力");
});

test("post-review delayed B acknowledgment retains return to A through durable reopen", async ({ page }) => {
  let release = () => {}, admitted = () => {};
  const held = new Promise<void>(ready => { release = ready; });
  const written = new Promise<void>(ready => { admitted = ready; });
  let first = true;
  await page.route("**/mutations", async route => {
    if (first) { first = false; const result = await route.fetch(); admitted(); await held; await route.fulfill({ response: result }); }
    else await route.continue();
  });
  try {
    await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
    await page.getByRole("button", { name: "Открыть пример" }).click();
    await page.getByRole("button", { name: "Создать резюме" }).click();
    await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
    const profile = page.locator('[data-field-content="profile/text"]');
    const original = await profile.innerText();
    await replaceFieldText(page, "profile/text", "Temporary B");
    await written;
    await replaceFieldText(page, "profile/text", original);
    await expect(page.locator(".next-save")).not.toHaveText("Сохранено");
    release();
    await expect(profile).toHaveText(original);
    await expect.poll(async () => (await currentWorkspace(page)).project?.document.profile.text.text).toBe(original);
    await expect(page.getByText("Сохранено", { exact: true })).toBeVisible();
    await page.reload();
    await expect(profile).toHaveText(original);
    const saved = await currentWorkspace(page);
    await openProject(page, saved.projectId);
    await expect(profile).toHaveText(original);
    const downloaded = page.waitForEvent("download");
    await page.getByRole("button", { name: "Сохранить проект", exact: true }).click();
    const path = await (await downloaded).path();
    if (!path) throw new Error("Missing portable download");
    await projectMenu(page);
    await page.getByLabel("Файл проекта", { exact: true }).setInputFiles({
      name: "returned-to-A.foldcv", mimeType: "application/zip", buffer: readFileSync(path),
    });
    await expect.poll(() => new URL(page.url()).searchParams.get("project")).not.toBe(saved.projectId);
    await expect(profile).toHaveText(original);
    await exportCurrent(page);
    await expect(page.getByRole("button", { name: "Скачать DOCX", exact: true })).toBeEnabled();
    const docx = await downloadDocx(page, "returned-to-A.docx");
    expect(docx.xml).toContain(original);
    expect(docx.xml).not.toContain("Temporary B");
  } finally { release(); }
});

test("post-review delayed successful source response is discarded after target editing", async ({ page }) => {
  let release = () => {}, admitted = () => {};
  const held = new Promise<void>(ready => { release = ready; });
  const fetched = new Promise<void>(ready => { admitted = ready; });
  await page.route("**/source-context", async route => {
    const result = await route.fetch();
    const raw: unknown = await result.json();
    expect(typeof raw === "object" && raw !== null && "status" in raw && raw.status === "evidence").toBe(true);
    admitted(); await held; await route.fulfill({ response: result });
  });
  try {
    await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
    await page.getByRole("button", { name: "Открыть пример" }).click();
    await page.getByRole("button", { name: "Создать резюме" }).click();
    await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
    const field = page.locator('[data-field-content$="/context"]').first();
    const id = await field.getAttribute("data-field-content");
    if (!id) throw new Error("Missing context field");
    await selectFields(page, id, 0, id, (await field.innerText()).length);
    await page.getByRole("button", { name: "Показать исходник" }).click();
    await fetched;
    await replaceFieldText(page, id, "New local context");
    const received = page.waitForResponse(result => result.url().endsWith("/source-context"));
    release(); await received;
    const panel = page.getByRole("complementary", { name: "Исходный контекст" });
    await expect(panel.getByRole("status")).toContainText("Выделение устарело");
    await expect(panel.locator("blockquote")).toHaveCount(0);
    await expect(field).toHaveText("New local context");
  } finally { release(); }
});

test("post-review progress combines assembly and render into four visible stages", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Открыть пример" }).click();
  await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  await page.getByText("Этапы создания", { exact: true }).click();
  const stages = page.getByRole("list", { name: "Этапы создания" });
  await expect(stages.getByRole("listitem")).toHaveCount(4);
  await expect(stages.getByText("Проверяем и оформляем", { exact: true })).toBeVisible();
  await expect(stages.locator('[data-stage="assemble"]')).toHaveAttribute("data-status", "completed");
});

test("built E1 disk acknowledgment refresh retains open session and resumes its baseline", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Открыть пример" }).click();await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  const profile = page.locator('[data-field-content="profile/text"]'), original = await profile.innerText();
  await profile.click();await page.keyboard.press("End");await page.keyboard.type(" Durable addition");
  await expect(page.locator(".next-save")).toHaveText("Сохранено");
  const id = new URL(page.url()).searchParams.get("project");expect(id).not.toBeNull();
  const disk: unknown = JSON.parse(readFileSync(resolve(runRoot, "FoldCV/projects", id ?? "", "workspace.json"), "utf8"));
  expect(validateContract("workspace_v5", disk)).toBe(true);
  const before: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();
  const sessionId = response(before).workspace.editSessions["profile"]?.sessionId;
  expect(sessionId).toBeDefined();expect(response(before).workspace.undoSlots["profile"]).toBeNull();
  await page.reload();
  await expect(profile).toContainText("Durable addition");
  await profile.click();await page.keyboard.press("End");await page.keyboard.type(" continued");
  await expect(page.locator(".next-save")).toHaveText("Сохранено");
  const after: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();
  expect(response(after).workspace.editSessions["profile"]?.sessionId).toBe(sessionId);
  expect(response(after).workspace.project?.operations.filter(item => item.kind !== "reconcile_edits")).toHaveLength(2);
  await page.keyboard.press("Control+z");
  await expect(profile).toHaveText(original);
  await expect(page.getByRole("alert")).toHaveCount(0);
  const persisted: unknown = JSON.parse(readFileSync(resolve(runRoot, "FoldCV/projects", id ?? "", "workspace.json"), "utf8"));
  expect(validateContract("workspace_v5", persisted)).toBe(true);
  const stored = response(after).workspace;
  expect(response(after).savedDocumentRevision).toBe(stored.documentRevision);
});

test("built E1 save failure shows unsaved text and explicit retry obtains a disk acknowledgment", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Открыть пример" }).click();await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  const flag = resolve(runRoot, "fail-user-saves");writeFileSync(flag, "1");
  const profile = page.locator('[data-field-content="profile/text"]');await profile.click();await page.keyboard.press("End");await page.keyboard.type(" Pending disk");
  await expect(page.getByRole("alert")).toContainText("Не удалось сохранить правки");
  await expect(page.locator(".next-save")).not.toHaveText("Сохранено");
  const id = new URL(page.url()).searchParams.get("project");
  expect(readFileSync(resolve(runRoot, "FoldCV/projects", id ?? "", "workspace.json"), "utf8")).not.toContain("Pending disk");
  const failed: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();
  expect(response(failed).durability).toBe("failed");expect(response(failed).savedDocumentRevision).toBe(2);
  await expect(profile).toContainText("Pending disk");rmSync(flag);
  await page.getByRole("button", { name: "Повторить сохранение" }).click();
  await expect(page.getByRole("alert")).toHaveCount(0);await expect(page.locator(".next-save")).toHaveText("Сохранено");
  expect(readFileSync(resolve(runRoot, "FoldCV/projects", id ?? "", "workspace.json"), "utf8")).toContain("Pending disk");
  await page.reload();await expect(profile).toContainText("Pending disk");
  const saved: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();
  expect(response(saved).workspace.project?.operations.filter(item => item.kind !== "reconcile_edits")).toHaveLength(2);
});

test("built failed-file preDraft refresh retains warnings original bytes and the same project", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByLabel("Файл резюме").setInputFiles({ name: "broken.pdf", mimeType: "application/pdf", buffer: Buffer.from("broken PDF bytes") });
  await expect(page.getByText("Доступного текста нет. Выберите другой файл или вставьте текст.", { exact: true })).toBeVisible();
  await expect(page.locator(".next-save")).toHaveText("Сохранено");
  const id = new URL(page.url()).searchParams.get("project");
  const before: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();
  const sourceId = response(before).workspace.preDraft?.selectedSourceId;
  const blobs = readdirSync(resolve(runRoot, "FoldCV/projects", id ?? "", "sources"));
  expect(blobs).toHaveLength(1);expect(readFileSync(resolve(runRoot, "FoldCV/projects", id ?? "", "sources", blobs[0] ?? ""), "utf8")).toBe("broken PDF bytes");
  await page.reload();await expect(page.getByText("Выбрано: broken.pdf", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Создать резюме" })).toBeDisabled();
  const after: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();
  expect(response(after).workspace.preDraft?.selectedSourceId).toBe(sourceId);
  expect(response(after).workspace.preDraft?.operations).toHaveLength(0);
  expect(new URL(page.url()).searchParams.get("project")).toBe(id);
});

test("built E1 backend restart opens its disk snapshot without generation or pointer movement", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Открыть пример" }).click();await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  const profile = page.locator('[data-field-content="profile/text"]');await profile.click();await page.keyboard.press("End");await page.keyboard.type(" Survives restart");
  await expect(page.locator(".next-save")).toHaveText("Сохранено");
  const id = new URL(page.url()).searchParams.get("project");
  const before: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();
  const saved = response(before).workspace;
  await stopServer();origin = await launch("E1");
  await page.goto(`${origin}/next.html?project=${id}#secret=synthetic-next-secret-0123456789`);
  await expect(profile).toContainText("Survives restart");await expect(page.locator(".next-save")).toHaveText("Сохранено");
  expect(new URL(page.url()).hash).toBe("");expect(new URL(page.url()).searchParams.get("project")).toBe(id);
  const raw: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();const workspace = response(raw).workspace;
  expect([workspace.projectRevision, workspace.documentRevision]).toEqual([saved.projectRevision, saved.documentRevision]);
  expect(workspace.editSessions).toEqual(saved.editSessions);expect(workspace.undoSlots).toEqual(saved.undoSlots);
  expect(workspace.project?.operations.filter(item => item.kind !== "reconcile_edits")).toHaveLength(2);
  await expect(page.getByRole("link", { name: "Скачать исходный DOCX" })).toBeVisible();
});

test("built E1 first unsent edit starts the save deadline and canceled composition resumes it", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Открыть пример" }).click();await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  const profile = page.locator('[data-field-content="profile/text"]');await profile.click();await page.keyboard.press("End");
  const writes: number[] = [];
  page.on("request", request => { if (new URL(request.url()).pathname.endsWith("/mutations")) writes.push(performance.now()); });
  const started = performance.now();await page.keyboard.type(" Timer");
  await page.waitForTimeout(350);expect(writes).toHaveLength(0);
  await expect.poll(() => writes.length).toBeGreaterThan(0);expect((writes[0] ?? 0) - started).toBeGreaterThan(850);
  await expect(page.locator(".next-save")).toHaveText("Сохранено");
  await page.keyboard.type(" Before canceled IME");
  await profile.evaluate(field => field.closest('[contenteditable="true"]')?.dispatchEvent(new CompositionEvent("compositionstart", { bubbles: true })));
  const count = writes.length;await page.waitForTimeout(1200);expect(writes).toHaveLength(count);
  await profile.evaluate(field => field.closest('[contenteditable="true"]')?.dispatchEvent(new CompositionEvent("compositionend", { bubbles: true })));
  await expect(page.locator(".next-save")).toHaveText("Сохранено");expect(writes.length).toBeGreaterThan(count);
});

test("built E2 filled sections and complete dates clear gaps without calls or fabricated values", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByLabel("Или вставьте текст").fill(readFileSync(resolve(root, "tests/fixtures/recovery/E2.txt"), "utf8"));
  await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  await page.getByText("Разделы и строки", { exact: true }).click();
  await page.getByRole("button", { name: "Добавить образование", exact: true }).click();
  const institution = page.locator('[data-field-content$="/institution"]');await expect.poll(() => institution.evaluate(node => node.closest("[contenteditable]")?.getAttribute("contenteditable"))).toBe("true");await institution.click();await page.keyboard.type("User university");
  await expect(page.locator('[data-annotation-code="missing_education"]')).toHaveCount(0);
  await page.getByRole("button", { name: "Добавить язык", exact: true }).click();
  const language = page.locator('[data-field-content^="language:"][data-field-content$="/name"]');await expect.poll(() => language.evaluate(node => node.closest("[contenteditable]")?.getAttribute("contenteditable"))).toBe("true");await language.click();await page.keyboard.type("User language");
  await expect(page.locator('[data-annotation-code="missing_languages"]')).toHaveCount(0);
  await page.getByText("Периоды: Гамма", { exact: true }).click();
  const group = page.locator('[data-period-job]').filter({ hasText: "Периоды: Гамма" });
  await group.getByRole("button", { name: "Добавить период", exact: true }).click();
  const start = page.locator('[data-field-content$="/startText"]').first();await expect.poll(() => start.evaluate(node => node.closest("[contenteditable]")?.getAttribute("contenteditable"))).toBe("true");await start.click();await page.keyboard.type("2020");
  const end = page.locator('[data-field-content$="/endText"]').first();await end.click();await page.keyboard.type("2022");
  await expect(page.locator('[data-annotation-code="missing_job_dates"]')).toHaveCount(0);
  await expect(page.locator('[data-duration]')).toHaveCount(1);
  await expect(page.locator('[data-annotation-code="team_size_conflict"]')).toHaveCount(1);
  await expect(page.locator('[data-annotation-code="missing_surname"]')).toHaveCount(0);
  const id = new URL(page.url()).searchParams.get("project");
  const raw: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();const workspace = response(raw).workspace;
  expect(workspace.project?.operations.filter(item => item.kind !== "reconcile_edits")).toHaveLength(2);expect(workspace.sourceObservedAt).toBeNull();
  expect(workspace.project?.document.languages[0]?.proficiency.text).toBe("");
  await page.getByRole("button", { name: "Удалить User university", exact: true }).click();
  await expect(page.locator('[data-annotation-code="missing_education"]')).toHaveCount(1);
  await expect(page.locator('[data-annotation-code="missing_education"]')).toHaveAttribute("data-section-id", "education");
});

test("built E1 invalid typed dates remove duration and restore refreshes its marks", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Открыть пример" }).click();await page.getByRole("button", { name: "Создать резюме" }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  await page.getByText("Разделы и строки", { exact: true }).click();await page.getByText("Периоды: Север", { exact: true }).click();
  const group = page.locator('[data-period-job]').filter({ hasText: "Периоды: Север" });await group.getByRole("checkbox").click();
  await expect(group.getByRole("checkbox")).not.toBeChecked();
  const end = page.locator('[data-field-content$="/endText"]').first();await end.click();await page.keyboard.type("2024");
  await expect(page.locator('[data-duration]')).toHaveCount(1);
  await end.click();await page.keyboard.press("End");await page.keyboard.type("invalid");
  await expect(page.locator('[data-duration]')).toHaveCount(0);
  await expect(page.locator('[data-annotation-code="missing_job_dates"]')).toHaveCount(1);
  await expect(end).toContainText("invalid");
  await page.keyboard.press("Control+z");
  await expect(page.locator('[data-annotation-code="missing_job_dates"]')).toHaveCount(0);
  await expect(page.locator('[data-duration]')).toHaveCount(0);
  await expect(end).toHaveText("");
  const id = new URL(page.url()).searchParams.get("project");
  const raw: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();
  expect(response(raw).workspace.project?.operations.filter(item => item.kind !== "reconcile_edits")).toHaveLength(2);
});

test("built entry persists manual theme, follows system and fits a narrow keyboard layout", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByLabel("Тема", { exact: true }).selectOption("light");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByLabel("Тема", { exact: true }).selectOption("system");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("button", { name: "Открыть пример" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Или вставьте текст")).not.toHaveValue("");
  await expect(page.getByRole("tab")).toHaveCount(0);
  expect(await page.evaluate(() => Object.keys(localStorage).filter(key => key !== "foldcv-theme"))).toEqual([]);
});

test("missing built next entry returns legacy HTTP 200 but fails the unique root smoke", async ({ page }) => {
  cpSync(resolve(runRoot, "dist/legacy.html"), resolve(runRoot, "dist/index.html"));
  rmSync(resolve(runRoot, "dist/next.html"));
  const result = await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  expect(result?.status()).toBe(200);
  await expect(page.locator('[data-app="foldcv-next"]')).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Из исходника — в готовое резюме" })).toBeVisible();
});

test("chosen failed file disables inactive paste and explicit text recovery keeps project ID", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Открыть пример" }).click();
  const selected = page.waitForResponse(result => new URL(result.url()).pathname === "/v1/projects/input");
  await page.getByLabel("Файл резюме").setInputFiles({ name: "failed.pdf", mimeType: "application/pdf", buffer: Buffer.from("broken") });
  const selectedValue: unknown = await (await selected).json();
  const selectedWorkspace = response(selectedValue).workspace;
  await expect(page.getByText("Выбрано: failed.pdf", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Создать резюме" })).toBeDisabled();
  await expect(page.getByLabel("Или вставьте текст")).toHaveValue("");
  expect(selectedWorkspace.preDraft?.operations).toEqual([]);
  const raw = readFileSync(resolve(root, "tests/fixtures/recovery/E1.txt"), "utf8");
  await page.getByLabel("Или вставьте текст").fill(raw);
  const created = page.waitForResponse(result => new URL(result.url()).pathname === `/v1/projects/${selectedWorkspace.projectId}/generations`);
  await page.getByRole("button", { name: "Создать резюме" }).click();
  const createdValue: unknown = await (await created).json();
  expect(response(createdValue).workspace.projectId).toBe(selectedWorkspace.projectId);
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
});

async function createRewriteExample(page: Page, entry = "/") {
  const secret = new URL(page.url()).origin === origin ? "" : "#secret=synthetic-next-secret-0123456789";
  await page.goto(`${origin}${entry}${secret}`);
  await page.getByRole("button", { name: "Открыть пример", exact: true }).click();
  await page.getByRole("button", { name: "Создать резюме", exact: true }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
}
async function currentWorkspace(page: Page) {
  const id = new URL(page.url()).searchParams.get("project");
  const raw: unknown = await (await page.request.get(`${origin}/v1/projects/${id}`)).json();
  return response(raw).workspace;
}
async function selectFields(page: Page, first: string, start: number, last: string, end: number) {
  await page.locator(`[data-field-content="${first}"]`).click();
  await page.evaluate(({ first, start, last, end }) => {
    function point(id: string, offset: number) {
      const element = document.querySelector(`[data-field-content="${id}"]`);
      if (!element) throw new Error("Missing field");
      const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
      let node = walker.nextNode();
      while (node) {
        const size = node.textContent?.length ?? 0;
        if (offset <= size) return { node, offset };
        offset -= size;node = walker.nextNode();
      }
      throw new Error("Missing text endpoint");
    }
    const a = point(first, start), b = point(last, end);
    window.getSelection()?.setBaseAndExtent(a.node, a.offset, b.node, b.offset);
    document.dispatchEvent(new Event("selectionchange"));
  }, { first, start, last, end });
  await expect.poll(() => page.evaluate(() => window.getSelection()?.toString() ?? "")).not.toBe("");
}
async function replaceFieldText(page: Page, id: string, text: string) {
  const field = page.locator(`[data-field-content="${id}"]`);
  const before = await field.textContent() ?? "";
  await selectFields(page, id, 0, id, before.length);
  const lines = text.split("\n");
  for (const [index, line] of lines.entries()) { if (index > 0) await page.keyboard.press("Enter");await page.keyboard.insertText(line); }
  await expect(field).toHaveText(text);
}
async function openSelectionAssistant(page: Page) {
  await expect(page.getByRole("button", { name: "Улучшить выделение", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Улучшить выделение", exact: true }).click();
  await expect(page.getByRole("complementary", { name: "Помощник текста" })).toBeVisible();
}
async function submitRewrite(page: Page, instruction = "Make clearer") {
  await page.getByLabel("Что изменить", { exact: true }).fill(instruction);
  await page.getByRole("button", { name: "Обновить выделение", exact: true }).click();
}
function isRewrite(value: unknown): value is GuiRewriteRequest { return validateContract("gui_rewrite_request", value); }
function isRules(value: unknown): value is RulesSettings { return validateContract("rules_settings", value); }

test("built E1 partial Unicode rewrite captures after durable flush and presets only fill the instruction", async ({ page }) => {
  await createRewriteExample(page);
  const posted: GuiRewriteRequest[] = [];
  let acknowledged = 2;
  page.on("response", result => {
    if (result.url().endsWith("/mutations")) void result.json().then((raw: unknown) => {
      if (typeof raw === "object" && raw !== null && "documentRevision" in raw && typeof raw.documentRevision === "number") acknowledged = raw.documentRevision;
    });
  });
  page.on("request", event => {
    if (event.url().endsWith("/rewrite")) { const raw: unknown = event.postDataJSON();if (!isRewrite(raw)) throw new Error("Invalid rewrite request");posted.push(raw);expect(raw.selection.documentRevision).toBe(acknowledged); }
  });
  await replaceFieldText(page, "profile/text", "Alpha 😀é\nBeta");
  await selectFields(page, "profile/text", 6, "profile/text", 11);
  await openSelectionAssistant(page);
  await page.getByRole("button", { name: "Яснее", exact: true }).click();
  await expect(page.getByLabel("Что изменить")).not.toHaveValue("");expect(posted).toHaveLength(0);
  await page.getByRole("button", { name: "Обновить выделение", exact: true }).click();
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Alpha Яснее: 😀é\nBeta");
  expect(posted).toHaveLength(1);expect(posted[0]?.selection.spans).toEqual([{ fieldId: "profile/text", range: { start: 6, end: 11 }, capturedText: "😀é\n" }]);
  const workspace = await currentWorkspace(page);expect(workspace.project?.operations.filter(item => item.kind !== "reconcile_edits")).toHaveLength(3);
  await page.getByRole("button", { name: "Отменить правку блока", exact: true }).click();
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Alpha 😀é\nBeta");
  await page.getByRole("button", { name: "Отменить правку блока", exact: true }).click();
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Alpha 😀é\nBeta");
});

test("built E1 heading structured and whole job rewrites keep field and record boundaries", async ({ page }) => {
  await createRewriteExample(page);
  const before = await currentWorkspace(page), job = before.project?.document.jobs[0];if (!job) throw new Error("Missing job");
  for (const id of ["candidate/title", job.role.fieldId]) {
    const original = await page.locator(`[data-field-content="${id}"]`).textContent() ?? "";
    await selectFields(page, id, 0, id, original.length);await openSelectionAssistant(page);await submitRewrite(page);
    await expect(page.locator(`[data-field-content="${id}"]`)).toHaveText("Яснее: " + original);
  }
  await page.locator(`[data-field-content="${job.role.fieldId}"]`).click();
  await page.getByRole("button", { name: "Улучшить текст блока", exact: true }).click();
  await expect(page.getByRole("complementary", { name: "Помощник текста" })).toBeVisible();
  await submitRewrite(page);
  await expect(page.locator(`[data-field-content="${job.role.fieldId}"]`)).toHaveText("Яснее: Яснее: " + job.role.text);
  const after = await currentWorkspace(page);expect(after.project?.document.jobs.map(row => row.id)).toEqual(before.project?.document.jobs.map(row => row.id));
  expect(after.project?.document.education).toEqual(before.project?.document.education);
  expect(after.project?.document.jobs[0]?.periods.map(period => period.id)).toEqual(job.periods.map(period => period.id));
  await page.getByRole("button", { name: "Отменить правку блока", exact: true }).click();
  await expect(page.locator(`[data-field-content="${job.role.fieldId}"]`)).toHaveText("Яснее: " + job.role.text);
});

test("built E1 cross section rewrite preserves an added sentence and removed detail with per block restore", async ({ page }) => {
  await createRewriteExample(page);
  const before = await currentWorkspace(page), job = before.project?.document.jobs[0];if (!job) throw new Error("Missing job");
  const addition = "Подготовила инструкцию для дежурной смены.";
  await replaceFieldText(page, job.tasks.fieldId, addition);
  await selectFields(page, "profile/text", 0, job.tasks.fieldId, addition.length);
  await openSelectionAssistant(page);await submitRewrite(page);
  await expect(page.locator(`[data-field-content="${job.tasks.fieldId}"]`)).toHaveText("Яснее: " + addition);
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Яснее: " + before.project?.document.profile.text.text);
  const after = await currentWorkspace(page);expect(after.undoSlots["profile"]).not.toBeNull();expect(after.undoSlots[`job:${job.id}`]).not.toBeNull();
  expect(after.project?.sources).toEqual(before.project?.sources);
  await page.locator('[data-field-content="profile/text"]').click();await page.getByRole("button", { name: "Отменить правку блока", exact: true }).click();
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText(before.project?.document.profile.text.text ?? "");
  await page.locator(`[data-field-content="${job.tasks.fieldId}"]`).click();await page.getByRole("button", { name: "Отменить правку блока", exact: true }).click();
  await expect(page.locator(`[data-field-content="${job.tasks.fieldId}"]`)).toHaveText(addition);
});

test("built E1 typing cancels a delayed rewrite and an error keeps authored text without retry", async ({ page }) => {
  await createRewriteExample(page);
  const before = await page.locator('[data-field-content="profile/text"]').textContent() ?? "";
  await selectFields(page, "profile/text", 0, "profile/text", before.length);await openSelectionAssistant(page);
  writeFileSync(resolve(runRoot, "hold-rewrite"), "controlled wait");await submitRewrite(page);
  await expect.poll(() => existsSync(resolve(runRoot, "rewrite-started"))).toBe(true);
  await replaceFieldText(page, "profile/text", "Newer typed text");
  rmSync(resolve(runRoot, "hold-rewrite"));
  await expect(page.getByText("Улучшение отменено. Ваши правки остаются в редакторе.", { exact: true })).toBeVisible();
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Newer typed text");
  await expect(page.locator(".next-save")).toHaveText("Сохранено");
  const current = await currentWorkspace(page);expect(current.project?.operations.filter(item => item.kind !== "reconcile_edits").at(-1)?.status).toBe("cancelled");
  await selectFields(page, "profile/text", 0, "profile/text", 16);await openSelectionAssistant(page);await submitRewrite(page, "TEST_ERROR");
  await expect(page.getByText("Не удалось обновить выделение.", { exact: false })).toBeVisible();
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Newer typed text");
  expect((await currentWorkspace(page)).project?.operations.filter(item => item.kind !== "reconcile_edits")).toHaveLength(4);
});

test("built E1 a metadata change during rewrite rejects its late reply and preserves current text", async ({ page }) => {
  await createRewriteExample(page);
  const before = await currentWorkspace(page), text = before.project?.document.profile.text.text ?? "";
  await selectFields(page, "profile/text", 0, "profile/text", text.length);await openSelectionAssistant(page);
  writeFileSync(resolve(runRoot, "hold-rewrite"), "controlled wait");await submitRewrite(page);
  await expect.poll(() => existsSync(resolve(runRoot, "rewrite-started"))).toBe(true);
  const result = await page.request.patch(`${origin}/v1/projects/${before.projectId}/metadata`, { headers: { Origin: origin }, data: { title: "Renamed during rewrite", baseRevision: before.projectRevision } });
  expect(result.ok()).toBe(true);rmSync(resolve(runRoot, "hold-rewrite"));
  await expect(page.getByText("Не удалось обновить выделение.", { exact: false })).toBeVisible();
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText(text);
  const after = await currentWorkspace(page);expect(after.title).toBe("Renamed during rewrite");expect(after.documentRevision).toBe(before.documentRevision);
  expect(after.project?.operations.filter(item => item.kind !== "reconcile_edits").at(-1)?.errorCode).toBe("SELECTION_STALE");
});

async function exportCurrent(page: Page) {
  await page.getByRole("button", { name: "Экспорт DOCX", exact: true }).click();
  await expect(page.getByRole("region", { name: "Экспорт DOCX", exact: true })).toBeVisible();
}
async function downloadDocx(page: Page, name: string) {
  const receipt = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать DOCX", exact: true }).click();
  const download = await receipt;
  expect(download.suggestedFilename()).toBe("resume.docx");
  const path = resolve(runRoot, name);await download.saveAs(path);
  const bytes = readFileSync(path), entries = unzipSync(bytes);
  const xml = entries["word/document.xml"];if (!xml) throw new Error("Missing DOCX document");
  return { bytes, xml: new TextDecoder().decode(xml), entries, path };
}
function renderCount() {
  const raw: unknown = JSON.parse(readFileSync(resolve(runRoot, "render-count.json"), "utf8"));
  if (typeof raw !== "object" || raw === null || !("count" in raw) || typeof raw.count !== "number") throw new Error("Invalid render count");
  return raw.count;
}

test("built E1 minimum slice exports current additions and a partial rewrite with no extra model call", async ({ page }) => {
  await createRewriteExample(page);
  const before = await currentWorkspace(page), job = before.project?.document.jobs[0];if (!job) throw new Error("Missing job");
  const addition = "Подготовила инструкцию для дежурной смены.";
  await replaceFieldText(page, job.tasks.fieldId, addition);
  await selectFields(page, job.tasks.fieldId, 0, job.tasks.fieldId, 11);await openSelectionAssistant(page);await submitRewrite(page);
  await expect(page.locator(`[data-field-content="${job.tasks.fieldId}"]`)).toHaveText("Яснее: " + addition);
  await exportCurrent(page);await expect(page.getByRole("button", { name: "Скачать DOCX", exact: true })).toBeEnabled();
  const file = await downloadDocx(page, "current-resume.docx");
  expect(file.xml).toContain("Яснее: " + addition);expect(file.xml).not.toContain("Интеграционные тесты.");
  expect(file.xml).not.toContain("editorial_plan_stale");expect(file.xml).not.toContain("mail@example.com");expect(file.entries["word/styles.xml"]).toBeDefined();
  const exported = await currentWorkspace(page), operation = exported.project?.operations.filter(item => item.kind !== "reconcile_edits").at(-1);
  expect(exported.project?.operations.filter(item => ["normalize_semantics", "draft_prose", "rewrite_prose"].includes(item.kind))).toHaveLength(3);
  expect(operation?.kind).toBe("render");expect(operation?.usage).toBeNull();
  const snapshot = exported.project?.renders.find(item => item.id === operation?.renderSnapshotId);if (!snapshot) throw new Error("Missing snapshot");
  expect(snapshot.projectRevision).toBe(exported.projectRevision);expect(snapshot.documentRevision).toBe(exported.documentRevision);
  expect(snapshot.docx?.sha256).toBe(createHash("sha256").update(file.bytes).digest("hex"));expect(snapshot.pdf).toBeNull();
  expect(renderCount()).toBe(2);
  await page.getByRole("button", { name: "К тексту", exact: true }).click();
  await page.locator(`[data-field-content="${job.tasks.fieldId}"]`).click();await page.getByRole("button", { name: "Отменить правку блока", exact: true }).click();
  await expect(page.locator(`[data-field-content="${job.tasks.fieldId}"]`)).toHaveText(addition);
  expect(renderCount()).toBe(2);
});

test("built E2 current export reuses verified cache and keeps semantic gaps outside DOCX", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByLabel("Или вставьте текст").fill(readFileSync(resolve(root, "tests/fixtures/recovery/E2.txt"), "utf8"));
  await page.getByRole("button", { name: "Создать резюме" }).click();await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  await exportCurrent(page);await expect(page.getByRole("button", { name: "Скачать DOCX", exact: true })).toBeEnabled();
  const file = await downloadDocx(page, "e2-current.docx");
  expect(file.xml).toContain("Dates not specified");expect(file.xml).not.toContain("Уточните даты");expect(file.xml).not.toContain("Образование не указано");
  expect(file.xml).not.toContain("team_size_conflict");expect(renderCount()).toBe(1);
  await page.getByRole("button", { name: "К тексту", exact: true }).click();await exportCurrent(page);
  await expect(page.getByRole("button", { name: "Скачать DOCX", exact: true })).toBeEnabled();expect(renderCount()).toBe(1);
  expect((await currentWorkspace(page)).project?.operations.filter(item => item.kind !== "render" && item.kind !== "reconcile_edits")).toHaveLength(2);
});

test("built E1 oversized field stays intact with a located DOCX error and current retry", async ({ page }) => {
  await createRewriteExample(page);
  const job = (await currentWorkspace(page)).project?.document.jobs[0];if (!job) throw new Error("Missing job");
  const long = "x".repeat(4001);await replaceFieldText(page, job.context.fieldId, long);
  await exportCurrent(page);await expect(page.getByText("Текст поля слишком длинный", { exact: false })).toBeVisible();
  await expect(page.getByText("Поле: Контекст.", { exact: false })).toBeVisible();await expect(page.getByRole("button", { name: "Скачать DOCX", exact: true })).toHaveCount(0);
  expect(renderCount()).toBe(1);
  await page.getByRole("button", { name: "К тексту", exact: true }).click();await expect(page.locator(`[data-field-content="${job.context.fieldId}"]`)).toHaveText(long);
  await replaceFieldText(page, job.context.fieldId, "Short current context.");await exportCurrent(page);
  await expect(page.getByRole("button", { name: "Скачать DOCX", exact: true })).toBeEnabled();
  expect((await downloadDocx(page, "retry-current.docx")).xml).toContain("Short current context.");expect(renderCount()).toBe(2);
});

test("built E1 editing during DOCX formation rejects late output and retry captures the new text", async ({ page }) => {
  await createRewriteExample(page);await replaceFieldText(page, "profile/text", "First current profile.");
  writeFileSync(resolve(runRoot, "hold-export"), "controlled wait");await exportCurrent(page);
  await expect.poll(() => existsSync(resolve(runRoot, "export-started"))).toBe(true);
  await page.getByRole("button", { name: "К тексту", exact: true }).click();await replaceFieldText(page, "profile/text", "Newer current profile.");
  await expect(page.locator(".next-save")).toHaveText("Сохранено");rmSync(resolve(runRoot, "hold-export"));
  await expect.poll(async () => (await currentWorkspace(page)).project?.operations.filter(item => item.kind !== "reconcile_edits").at(-1)?.status).toBe("failed");
  const old = (await currentWorkspace(page)).project?.operations.filter(item => item.kind !== "reconcile_edits").at(-1);expect(old?.errorCode).toBe("EXPORT_STALE");
  const stale = await page.request.get(`${origin}/v1/projects/${new URL(page.url()).searchParams.get("project")}/exports/${old?.id}/docx`);expect(stale.status()).toBe(409);
  await exportCurrent(page);await expect(page.getByRole("button", { name: "Скачать DOCX", exact: true })).toBeEnabled();
  const file = await downloadDocx(page, "newer-profile.docx");expect(file.xml).toContain("Newer current profile.");expect(file.xml).not.toContain("First current profile.");
});

test("built E1 active composition and failed save keep the editor mounted and start no export", async ({ page }) => {
  await createRewriteExample(page);
  await replaceFieldText(page, "profile/text", "Saved input");await expect(page.locator(".next-save")).toHaveText("Сохранено");
  await page.evaluate(() => {
    const editor = document.querySelector('[contenteditable="true"]'), field = document.querySelector('[data-field-content="profile/text"]');
    if (!editor || !field) throw new Error("Missing editor");const text = document.createTreeWalker(field, NodeFilter.SHOW_TEXT).nextNode();if (!text) throw new Error("Missing text");
    editor.dispatchEvent(new CompositionEvent("compositionstart", { bubbles: true }));text.textContent = "Saved input入力";
    editor.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertCompositionText", data: "入力", isComposing: true }));
    const button = Array.from(document.querySelectorAll('button')).find(button => button.textContent === "Экспорт DOCX");button?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  await expect(page.getByText("Завершите ввод и сохраните правки.", { exact: false })).toBeVisible();await expect(page.locator('[contenteditable="true"]')).toHaveCount(1);
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Saved input入力");expect(renderCount()).toBe(1);
  await page.evaluate(() => { const editor = document.querySelector('[contenteditable="true"]');editor?.dispatchEvent(new CompositionEvent("compositionend", { bubbles: true, data: "入力" })); });
  await expect(page.locator(".next-save")).toHaveText("Сохранено");
  writeFileSync(resolve(runRoot, "fail-user-saves"), "controlled failure");await replaceFieldText(page, "profile/text", "Unsaved kept input.");
  await page.getByRole("button", { name: "Экспорт DOCX", exact: true }).click();
  await expect(page.getByText("Завершите ввод и сохраните правки.", { exact: false })).toBeVisible();await expect(page.locator('[contenteditable="true"]')).toHaveCount(1);
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Unsaved kept input.");expect(renderCount()).toBe(1);
  rmSync(resolve(runRoot, "fail-user-saves"));
});

test("built E1 corrupt transport bytes cannot download and retry uses the same verified artifact", async ({ page }) => {
  await createRewriteExample(page);await exportCurrent(page);await expect(page.getByRole("button", { name: "Скачать DOCX", exact: true })).toBeEnabled();
  await page.route("**/exports/*/docx", async route => { const result = await route.fetch();const bytes = await result.body();bytes[0] = 0;await route.fulfill({ response: result, body: bytes }); });
  await page.getByRole("button", { name: "Скачать DOCX", exact: true }).click();await expect(page.getByText("Не удалось скачать DOCX.", { exact: false })).toBeVisible();
  expect(renderCount()).toBe(1);await page.unroute("**/exports/*/docx");
  const file = await downloadDocx(page, "verified-retry.docx");expect(file.xml).toContain("Ирина Примерова");expect(renderCount()).toBe(1);
});

test("built E1 Settings opens with no probe and keeps one persistent analysis control outside the editor", async ({ page }) => {
  await createRewriteExample(page);const before = await currentWorkspace(page);
  await page.getByRole("button", { name: "Настройки", exact: true }).click();
  await expect(page.getByRole("region", { name: "Настройки", exact: true })).toBeVisible();
  await expect(page.getByText("Подключение ещё не проверено.", { exact: true })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Автоматически проверять изменения", exact: true })).toHaveCount(1);
  await expect(page.getByRole("checkbox", { name: "Автоматически проверять изменения", exact: true })).toBeEnabled();
  expect(existsSync(resolve(runRoot, "connection-actions.json"))).toBe(false);expect(existsSync(resolve(runRoot, "native-login-called"))).toBe(false);
  const after = await currentWorkspace(page);expect(after.projectRevision).toBe(before.projectRevision);expect(after.documentRevision).toBe(before.documentRevision);
  expect(after.project?.document).toEqual(before.project?.document);
  await page.getByRole("button", { name: "Вернуться", exact: true }).click();await expect(page.locator('[data-field-content="profile/text"]')).toHaveText(before.project?.document.profile.text.text ?? "");
});

test("built E1 Settings reported model is saved and reaches normalization and drafting", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Настройки", exact: true }).click();await page.getByRole("button", { name: "Проверить подключение", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Модель", exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "Модель", exact: true }).selectOption("fixture-model-b");
  await expect(page.getByText("Сохранённый выбор: fixture-model-b.", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Вернуться", exact: true }).click();await page.getByRole("button", { name: "Открыть пример", exact: true }).click();
  await page.getByRole("button", { name: "Создать резюме", exact: true }).click();await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  const raw: unknown = JSON.parse(readFileSync(resolve(runRoot, "model-requests.json"), "utf8"));
  expect(raw).toEqual([{ model: "fixture-model-b", kind: "normalize_semantics" }, { model: "fixture-model-b", kind: "draft_prose" }]);
  await page.getByRole("button", { name: "Настройки", exact: true }).click();await expect(page.getByRole("combobox", { name: "Модель", exact: true })).toHaveValue("fixture-model-b");
  await page.getByRole("button", { name: "Отключить модель", exact: true }).click();await expect(page.getByText("Модель отключена от FoldCV.", { exact: false })).toBeVisible();
  expect(existsSync(resolve(runRoot, "native-login-called"))).toBe(false);
});

test("built E1 Settings distinguishes quota and login without native global sign in", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);await page.getByRole("button", { name: "Настройки", exact: true }).click();
  writeFileSync(resolve(runRoot, "connection-case"), "quota_exhausted");await page.getByRole("button", { name: "Проверить подключение", exact: true }).click();
  await expect(page.getByText("Лимит подписки исчерпан.", { exact: false })).toBeVisible();
  writeFileSync(resolve(runRoot, "connection-case"), "login_required");await page.getByRole("button", { name: "Проверить подключение", exact: true }).click();
  await expect(page.getByText("Нужен вход с подпиской ChatGPT", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Войти в выделенный CLI", exact: true })).toHaveCount(0);
  expect(existsSync(resolve(runRoot, "native-login-called"))).toBe(false);
  writeFileSync(resolve(runRoot, "connection-case"), "unknown_limits");await page.getByRole("button", { name: "Проверить подключение", exact: true }).click();
  await expect(page.getByText("сведения о лимите не получены", { exact: false })).toBeVisible();
});

test("built E1 Settings detach cancels a controlled pending check and retains current text", async ({ page }) => {
  await createRewriteExample(page);await replaceFieldText(page, "profile/text", "Current retained text.");
  await page.getByRole("button", { name: "Настройки", exact: true }).click();writeFileSync(resolve(runRoot, "hold-connection"), "controlled wait");
  await page.getByRole("button", { name: "Проверить подключение", exact: true }).click();
  await expect.poll(() => existsSync(resolve(runRoot, "connection-actions.json"))).toBe(true);
  await page.getByRole("button", { name: "Отключить модель", exact: true }).click();
  await expect(page.getByText("Модель отключена от FoldCV.", { exact: false })).toBeVisible();rmSync(resolve(runRoot, "hold-connection"));
  await page.getByRole("button", { name: "Вернуться", exact: true }).click();await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Current retained text.");
  expect((await currentWorkspace(page)).project?.operations.filter(item => item.kind !== "render" && item.kind !== "reconcile_edits")).toHaveLength(2);
});

function analysisCalls() {
  if (!existsSync(resolve(runRoot, "model-requests.json"))) return 0;
  const metadata: unknown = JSON.parse(readFileSync(resolve(runRoot, "model-requests.json"), "utf8"));
  return JSON.stringify(metadata).match(/reconcile_edits/g)?.length ?? 0;
}

async function analysisSetting(page: Page, enabled: boolean) {
  await page.getByRole("button", { name: "Настройки", exact: true }).click();
  const checkbox = page.getByRole("checkbox", { name: "Автоматически проверять изменения", exact: true });
  await expect(checkbox).toBeEnabled();if (await checkbox.isChecked() !== enabled) await checkbox.click();
  if (enabled) await expect(checkbox).toBeChecked();else await expect(checkbox).not.toBeChecked();
  await expect(checkbox).toBeEnabled();
  await page.getByRole("button", { name: "Вернуться", exact: true }).click();
}

test("built E1 A10 typing and save ticks wait for completion while stale analysis never consumes undo", async ({ page }) => {
  await createRewriteExample(page);writeFileSync(resolve(runRoot, "hold-analysis"), "controlled wait");
  await replaceFieldText(page, "profile/text", "Completed claim");await expect(page.locator(".next-save")).toHaveText("Сохранено");
  expect(analysisCalls()).toBe(0);
  await page.keyboard.press("End");await page.keyboard.press("Enter");
  await expect.poll(analysisCalls).toBe(1);await expect(page.getByText("Проверяем изменения", { exact: true })).toBeVisible();
  const before = await currentWorkspace(page);expect(before.editSessions.profile).toBeDefined();expect(before.undoSlots.profile).toBeNull();
  await page.keyboard.insertText("New incomplete text");await expect(page.locator(".next-save")).toHaveText("Сохранено");
  const current = await currentWorkspace(page);expect(current.documentRevision).toBeGreaterThan(before.documentRevision);
  await expect.poll(() => existsSync(resolve(runRoot, "analysis-released"))).toBe(true);expect(analysisCalls()).toBe(1);
  rmSync(resolve(runRoot, "hold-analysis"));await page.locator('[data-field-content="candidate/title"]').click();
  await expect.poll(analysisCalls).toBe(2);
  await expect.poll(async () => (await currentWorkspace(page)).project?.operations.filter(item => item.kind === "reconcile_edits" && item.status === "completed").length).toBe(1);
  const settled = await currentWorkspace(page);expect(settled.project?.document.profile.text.text).toBe("Completed claim\nNew incomplete text");
  expect(settled.undoSlots.profile?.record).toEqual(before.editSessions.profile?.baseline.record);
});

test("built E1 A10 the single Settings switch persists pause and resumes one accumulated batch", async ({ page }) => {
  await createRewriteExample(page);await analysisSetting(page, false);
  await replaceFieldText(page, "profile/text", "Paused correction");await page.locator('[data-field-content="candidate/title"]').click();
  await expect(page.getByText("Проверка изменений приостановлена", { exact: true })).toBeVisible();expect(analysisCalls()).toBe(0);
  await page.reload();await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Paused correction");expect(analysisCalls()).toBe(0);
  await analysisSetting(page, true);await expect.poll(analysisCalls).toBe(1);
  await expect.poll(async () => (await currentWorkspace(page)).project?.operations.filter(item => item.kind === "reconcile_edits" && item.status === "completed").length).toBe(1);
  await page.getByRole("button", { name: "Настройки", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: "Автоматически проверять изменения", exact: true })).toHaveCount(1);
  await expect(page.getByRole("checkbox", { name: "Автоматически проверять изменения", exact: true })).toBeChecked();expect(analysisCalls()).toBe(1);
});

test("built E1 A10 quota failure preserves typing and retry runs only on an explicit action", async ({ page }) => {
  await createRewriteExample(page);writeFileSync(resolve(runRoot, "fail-analysis"), "controlled quota");
  await replaceFieldText(page, "profile/text", "User correction");await page.locator('[data-field-content="candidate/title"]').click();
  await expect(page.getByRole("button", { name: "Повторить проверку", exact: true })).toBeVisible();expect(analysisCalls()).toBe(1);
  rmSync(resolve(runRoot, "fail-analysis"));await page.reload();await expect(page.getByRole("button", { name: "Повторить проверку", exact: true })).toBeVisible();
  expect(analysisCalls()).toBe(1);await page.getByRole("button", { name: "Повторить проверку", exact: true }).click();
  await expect.poll(analysisCalls).toBe(2);await expect(page.getByRole("button", { name: "Повторить проверку", exact: true })).toHaveCount(0);
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("User correction");
});

test("built E1 A10 rewrite stops its running reconciliation and sends one current batch after replacement", async ({ page }) => {
  await createRewriteExample(page);writeFileSync(resolve(runRoot, "hold-analysis"), "controlled wait");
  await replaceFieldText(page, "profile/text", "Completed rewrite target");await page.keyboard.press("End");await page.keyboard.press("Enter");
  await expect.poll(analysisCalls).toBe(1);
  await selectFields(page, "profile/text", 0, "profile/text", "Completed rewrite target".length);
  await openSelectionAssistant(page);await submitRewrite(page);
  await expect.poll(() => existsSync(resolve(runRoot, "analysis-released"))).toBe(true);
  await expect.poll(() => existsSync(resolve(runRoot, "rewrite-started"))).toBe(true);rmSync(resolve(runRoot, "hold-analysis"));
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Яснее: Completed rewrite target\n");
  await expect.poll(analysisCalls).toBe(2);
  await expect.poll(async () => (await currentWorkspace(page)).project?.operations.filter(item => item.kind === "reconcile_edits" && item.status === "completed").length).toBe(1);
  const metadata: unknown = JSON.parse(readFileSync(resolve(runRoot, "model-requests.json"), "utf8"));
  expect(metadata).toEqual(["normalize_semantics", "draft_prose", "reconcile_edits", "rewrite_prose", "reconcile_edits"].map(kind => ({ model: "fixture", kind })));
});

async function relatedExample(page: Page) {
  await createRewriteExample(page);
  const workspace = await currentWorkspace(page), job = workspace.project?.document.jobs[0];
  if (!job) throw new Error("Missing controlled job");
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Обучила двух новых разработчиков.");
  await replaceFieldText(page, job.tasks.fieldId, "Обучила трёх новых разработчиков.");
  await page.locator('[data-field-content="profile/text"]').click();
  await expect.poll(analysisCalls).toBe(1);
  const mark = page.locator('[data-annotation-id="related-profile-conflict"]');await expect(mark).toBeVisible();
  return { job, mark: page.locator('[data-annotation-id="related-profile-conflict"]') };
}

test("built example E1 task A11 keeps the older profile until an explicit related update and preserves the newer shared fact on restore", async ({ page }) => {
  const { job, mark } = await relatedExample(page);
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Обучила двух новых разработчиков.");
  await mark.getByText("Связанные изменения", { exact: true }).click();
  await expect(mark.getByText("Обучила трёх новых разработчиков.", { exact: true })).toBeVisible();
  const before = await currentWorkspace(page);
  await mark.getByRole("button", { name: "Обновить связанный текст", exact: true }).click();
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Обучила трёх новых разработчиков.");
  await expect(mark).toHaveCount(0);const current = await currentWorkspace(page);
  expect([current.projectRevision, current.documentRevision]).toEqual([before.projectRevision + 1, before.documentRevision + 1]);
  expect(current.undoSlots.profile?.record.kind).toBe("profile");expect(analysisCalls()).toBe(1);
  await page.locator(`[data-field-content="${job.tasks.fieldId}"]`).click();await page.getByRole("button", { name: "Отменить правку блока", exact: true }).click();
  await expect(page.locator(`[data-field-content="${job.tasks.fieldId}"]`)).toHaveText("Обучила двух новых разработчиков.");
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Обучила трёх новых разработчиков.");
  await expect(page.locator('[data-annotation-code="restore_shared_fact_conflict"]')).toHaveCount(1);expect(analysisCalls()).toBe(1);
});

test("built example E1 task A11 restores the job first and clears its profile conflict with no extra assessment", async ({ page }) => {
  const { job, mark } = await relatedExample(page);
  await page.locator(`[data-field-content="${job.tasks.fieldId}"]`).click();await page.getByRole("button", { name: "Отменить правку блока", exact: true }).click();
  await expect(page.locator(`[data-field-content="${job.tasks.fieldId}"]`)).toHaveText("Обучила двух новых разработчиков.");
  await expect(mark).toHaveCount(0);await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Обучила двух новых разработчиков.");
  expect((await currentWorkspace(page)).relatedUpdateSuggestions).toEqual([]);expect(analysisCalls()).toBe(1);
});

test("built example E1 task A11 rejects a delayed related action after a newer saved edit", async ({ page }) => {
  const { mark } = await relatedExample(page);
  let release: (() => void) | undefined, intercepted = false;
  const wait = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/mutations", async route => {
    const body: unknown = route.request().postDataJSON();
    if (typeof body === "object" && body !== null && "kind" in body && body.kind === "apply-related-update") {
      intercepted = true;await wait;
    }
    await route.continue();
  });
  await mark.getByText("Связанные изменения", { exact: true }).click();
  await mark.getByRole("button", { name: "Обновить связанный текст", exact: true }).click();await expect.poll(() => intercepted).toBe(true);
  await replaceFieldText(page, "profile/text", "Новая правка профиля.");await expect(page.locator(".next-save")).toHaveText("Сохранено");
  const saved = await currentWorkspace(page);release?.();
  await expect(page.getByText("Предложение устарело.", { exact: false })).toBeVisible();
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Новая правка профиля.");
  const after = await currentWorkspace(page);expect([after.projectRevision, after.documentRevision]).toEqual([saved.projectRevision, saved.documentRevision]);
  expect(analysisCalls()).toBe(1);
});

async function projectMenu(page: Page) {
  await page.getByRole("button", { name: "Меню проекта", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Локальные проекты", exact: true })).toBeVisible();
}
async function newProject(page: Page) {
  await projectMenu(page);await page.getByRole("button", { name: "Новое резюме", exact: true }).click();
  await expect(page.getByLabel("Или вставьте текст")).toBeVisible();
}
async function openProject(page: Page, id: string) {
  await projectMenu(page);await page.locator(`[data-project-id="${id}"]`).getByRole("button", { name: "Открыть", exact: true }).click();
  await expect.poll(() => new URL(page.url()).searchParams.get("project")).toBe(id);
  await expect(page.locator('[contenteditable="true"]')).toHaveCount(1);
}

test("built example E8 task A13 persists manual names and switches isolated E1 E2 projects without content calls", async ({ page }) => {
  await createRewriteExample(page);const first = await currentWorkspace(page);
  await replaceFieldText(page, "profile/text", "Saved first project addition.");
  await projectMenu(page);const row = page.locator(`[data-project-id="${first.projectId}"]`);
  await row.getByRole("button", { name: "Переименовать", exact: true }).click();
  await page.getByLabel("Имя проекта", { exact: true }).fill("Manual first project");await page.getByRole("button", { name: "Сохранить имя", exact: true }).click();
  await expect(row.getByText("Manual first project", { exact: true })).toBeVisible();
  await page.getByRole("dialog", { name: "Локальные проекты" }).getByRole("button", { name: "Закрыть", exact: true }).click();
  await newProject(page);await page.getByLabel("Или вставьте текст").fill(readFileSync(resolve(root, "tests/fixtures/recovery/E2.txt"), "utf8"));
  await page.getByRole("button", { name: "Создать резюме", exact: true }).click();await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  const second = await currentWorkspace(page);expect(second.projectId).not.toBe(first.projectId);
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Разрабатываю пайплайны данных.");
  await openProject(page, first.projectId);await expect(page.getByRole("button", { name: "Меню проекта", exact: true })).toHaveText("Manual first project");
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Saved first project addition.");
  await page.reload();await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Saved first project addition.");
  await openProject(page, second.projectId);expect(analysisCalls()).toBe(0);
  const metadata: unknown = JSON.parse(readFileSync(resolve(runRoot, "model-requests.json"), "utf8"));
  expect(metadata).toEqual(["normalize_semantics", "draft_prose", "normalize_semantics", "draft_prose"].map(kind => ({ model: "fixture", kind })));
});

test("built example E8 task A13 failed save blocks switching and keeps the current typing buffer", async ({ page }) => {
  await createRewriteExample(page);const first = await currentWorkspace(page);
  writeFileSync(resolve(runRoot, "fail-user-saves"), "controlled failure");await replaceFieldText(page, "profile/text", "Unacknowledged project edit.");
  await projectMenu(page);await page.getByRole("button", { name: "Новое резюме", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Локальные проекты" }).getByRole("alert")).toBeVisible();
  expect(new URL(page.url()).searchParams.get("project")).toBe(first.projectId);
  await page.getByRole("dialog", { name: "Локальные проекты" }).getByRole("button", { name: "Закрыть", exact: true }).click();
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Unacknowledged project edit.");rmSync(resolve(runRoot, "fail-user-saves"));
  await page.getByRole("button", { name: "Повторить сохранение", exact: true }).click();await expect(page.locator(".next-save")).toHaveText("Сохранено");
  await newProject(page);await expect(page.getByLabel("Или вставьте текст")).toHaveValue("");expect(analysisCalls()).toBe(0);
});

test("built example E8 task A13 confirms deletion during pending rewrite and preserves the other project and exported file", async ({ page }) => {
  await createRewriteExample(page);const first = await currentWorkspace(page);await exportCurrent(page);
  const exported = await downloadDocx(page, "retained-user-export.docx"), expected = readFileSync(exported.path);
  await page.getByRole("button", { name: "К тексту", exact: true }).click();await newProject(page);
  await page.getByLabel("Или вставьте текст").fill(readFileSync(resolve(root, "tests/fixtures/recovery/E2.txt"), "utf8"));
  await page.getByRole("button", { name: "Создать резюме", exact: true }).click();await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  const second = await currentWorkspace(page);await openProject(page, first.projectId);
  writeFileSync(resolve(runRoot, "hold-rewrite"), "controlled wait");const profile = (await currentWorkspace(page)).project?.document.profile.text.text ?? "";
  await selectFields(page, "profile/text", 0, "profile/text", profile.length);await openSelectionAssistant(page);await submitRewrite(page);
  await expect.poll(() => existsSync(resolve(runRoot, "rewrite-started"))).toBe(true);await openProject(page, second.projectId);
  await projectMenu(page);const row = page.locator(`[data-project-id="${first.projectId}"]`);await row.getByRole("button", { name: "Удалить", exact: true }).click();
  expect(existsSync(resolve(runRoot, "FoldCV/projects", first.projectId))).toBe(true);
  const deleted = page.waitForResponse(result => result.request().method() === "DELETE" && new URL(result.url()).pathname.endsWith(first.projectId));
  await page.getByRole("button", { name: "Удалить проект", exact: true }).click();
  expect((await deleted).status()).toBe(200);await expect.poll(() => existsSync(resolve(runRoot, "FoldCV/projects", first.projectId))).toBe(false);await expect(row).toHaveCount(0);
  expect(existsSync(resolve(runRoot, "FoldCV/projects", first.projectId))).toBe(false);expect(readFileSync(exported.path)).toEqual(expected);
  await page.getByRole("dialog", { name: "Локальные проекты" }).getByRole("button", { name: "Закрыть", exact: true }).click();
  expect((await currentWorkspace(page)).projectId).toBe(second.projectId);await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Разрабатываю пайплайны данных.");
  expect((await page.request.get(`${origin}/v1/projects/${first.projectId}`)).status()).toBe(410);expect(analysisCalls()).toBe(0);
});

test("built example E8 task A13 cleanup failure stays visible and retries without losing another project", async ({ page }) => {
  await createRewriteExample(page);const first = await currentWorkspace(page);await newProject(page);await createRewriteExample(page);const second = await currentWorkspace(page);
  writeFileSync(resolve(runRoot, "fail-project-cleanup"), "controlled failure");await projectMenu(page);
  await page.locator(`[data-project-id="${first.projectId}"]`).getByRole("button", { name: "Удалить", exact: true }).click();
  await page.getByRole("button", { name: "Удалить проект", exact: true }).click();await expect(page.getByText("Не удалось подтвердить удаление всех файлов.", { exact: false })).toBeVisible();
  expect(existsSync(resolve(runRoot, "FoldCV/projects", first.projectId))).toBe(true);rmSync(resolve(runRoot, "fail-project-cleanup"));
  await page.getByRole("button", { name: "Вернуться к списку", exact: true }).click();const row = page.locator(`[data-project-id="${first.projectId}"]`);
  await row.getByRole("button", { name: "Повторить очистку", exact: true }).click();await page.getByRole("region", { name: "Подтверждение удаления", exact: true }).getByRole("button", { name: "Повторить очистку", exact: true }).click();
  await expect(row).toHaveCount(0);await page.getByRole("dialog", { name: "Локальные проекты" }).getByRole("button", { name: "Закрыть", exact: true }).click();
  expect((await currentWorkspace(page)).projectId).toBe(second.projectId);expect(analysisCalls()).toBe(0);
});

test("built example E3d task A14 portable reopen preserves edits prior version and sources with zero calls", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });await createRewriteExample(page);
  await replaceFieldText(page, "profile/text", "Portable prior.");await page.locator('[data-field-content="candidate/name"]').click();
  await expect.poll(async () => (await currentWorkspace(page)).undoSlots["profile"]?.record.kind).toBe("profile");
  await replaceFieldText(page, "profile/text", "Portable current.");
  const downloaded = page.waitForEvent("download");await page.getByRole("button", { name: "Сохранить проект", exact: true }).click();
  const file = await downloaded, path = await file.path();expect(path).not.toBeNull();
  const before = await currentWorkspace(page), calls = readFileSync(resolve(runRoot, "model-requests.json"), "utf8");
  const archive = unzipSync(readFileSync(path ?? ""));expect(Object.keys(archive)).toContain("workspace.json");
  expect(Object.keys(archive).some(name => name.startsWith("template/"))).toBe(false);
  await projectMenu(page);await page.getByLabel("Файл проекта", { exact: true }).setInputFiles({ name: "synthetic.foldcv", mimeType: "application/zip", buffer: readFileSync(path ?? "") });
  await expect.poll(() => new URL(page.url()).searchParams.get("project")).not.toBe(before.projectId);
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Portable current.");
  const after = await currentWorkspace(page);expect(after.project?.document).toEqual(before.project?.document);expect(after.undoSlots).toEqual(before.undoSlots);
  expect(after.project?.sources).toEqual(before.project?.sources);expect(after.formattingAsOf).toEqual(before.formattingAsOf);expect(after.mutationReplay).toEqual([]);
  expect(readFileSync(resolve(runRoot, "model-requests.json"), "utf8")).toBe(calls);
  if (process.env.FOLDCV_EVIDENCE_ROOT) {
    writeFileSync(resolve(process.env.FOLDCV_EVIDENCE_ROOT, "E3d-portable-project.foldcv"), readFileSync(path ?? ""));
    await page.screenshot({ path: resolve(process.env.FOLDCV_EVIDENCE_ROOT, "E3d-portable-reopen.png") });
  }
  await page.locator('[data-field-content="profile/text"]').click();await page.keyboard.press("Control+z");await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Portable prior.");
  await page.reload();await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Portable prior.");
  const old: unknown = await (await page.request.get(`${origin}/v1/projects/${before.projectId}`)).json();expect(response(old).workspace.project?.document.profile.text.text).toBe("Portable current.");
  expect(readFileSync(resolve(runRoot, "model-requests.json"), "utf8")).toBe(calls);
});

test("built example E8 task A14 corrupt portable file keeps current text project and settings", async ({ page }) => {
  await createRewriteExample(page);await replaceFieldText(page, "profile/text", "Retained while opening corrupt file.");
  await projectMenu(page);await expect.poll(async () => (await currentWorkspace(page)).project?.document.profile.text.text).toBe("Retained while opening corrupt file.");
  const before = await currentWorkspace(page), url = page.url(), calls = readFileSync(resolve(runRoot, "model-requests.json"), "utf8");
  await page.getByLabel("Файл проекта", { exact: true }).setInputFiles({ name: "broken.foldcv", mimeType: "application/zip", buffer: Buffer.from("corrupt bytes") });
  await expect(page.getByRole("dialog", { name: "Локальные проекты" }).getByRole("alert")).toContainText("Не удалось открыть файл проекта");
  expect(page.url()).toBe(url);expect((await currentWorkspace(page)).project?.document).toEqual(before.project?.document);
  await page.getByRole("dialog", { name: "Локальные проекты" }).getByRole("button", { name: "Закрыть", exact: true }).click();
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Retained while opening corrupt file.");
  expect(readFileSync(resolve(runRoot, "model-requests.json"), "utf8")).toBe(calls);
});

test("built task A14 legacy v4 migration notice opens read only history and imported text remains editable", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);await projectMenu(page);
  await page.getByLabel("Файл проекта", { exact: true }).setInputFiles(resolve(root, "contracts/examples/recovery/legacy_workspace_v4.foldcv"));
  await expect(page.locator('[data-field-content="candidate/name"]')).toHaveText("Мария Примерова");
  await page.getByText("Особенности переноса", { exact: true }).click();await expect(page.getByText("Свободный текст старого фокуса перенесён в навыки без подбора логотипов.", { exact: true })).toBeVisible();
  await page.getByText("Особенности переноса", { exact: true }).click();
  await page.getByRole("button", { name: "Показать текст переноса", exact: true }).click();const panel = page.getByRole("complementary", { name: "Исходный контекст" });
  await expect(panel.locator('[data-legacy-kind="unapplied_draft"]').first()).toBeVisible();expect(await panel.locator('[contenteditable="true"]').count()).toBe(0);
  if (process.env.FOLDCV_EVIDENCE_ROOT) await page.screenshot({ path: resolve(process.env.FOLDCV_EVIDENCE_ROOT, "legacy-migration-history.png") });
  await page.getByRole("button", { name: "Закрыть исходный контекст", exact: true }).click();await replaceFieldText(page, "profile/text", "Editable imported profile.");
  await page.locator('[data-field-content="candidate/name"]').click();await expect(page.locator(".next-save")).toHaveText("Сохранено");
  await page.reload();await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Editable imported profile.");
  expect(existsSync(resolve(runRoot, "model-requests.json"))).toBe(false);
});

test("built task A14 portable save error keeps current text and offers a fresh download", async ({ page }) => {
  await createRewriteExample(page);await replaceFieldText(page, "profile/text", "Retained after save error.");
  await page.route("**/archive", route => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "PROJECT_SAVE_FAILED" } }) }));
  await page.getByRole("button", { name: "Сохранить проект", exact: true }).click();await expect(page.getByText("Не удалось сохранить файл проекта.", { exact: false })).toBeVisible();
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Retained after save error.");await page.unroute("**/archive");
  const downloaded = page.waitForEvent("download");await page.getByRole("button", { name: "Сохранить проект", exact: true }).click();expect((await downloaded).suggestedFilename()).toBe("project.foldcv");
});

test("built task A14 failed imported project save retries same identity and preserves current project", async ({ page }) => {
  await createRewriteExample(page);const before = await currentWorkspace(page);
  const downloaded = page.waitForEvent("download");await page.getByRole("button", { name: "Сохранить проект", exact: true }).click();
  const path = await (await downloaded).path();expect(path).not.toBeNull();let importedId: string | null = null;
  await page.route("**/v1/projects/archive", async route => {
    const result = await route.fetch(), body: unknown = await result.json();const value = response(body);importedId = value.workspace.projectId;
    await route.fulfill({ response: result, json: { ...value, durability: "failed", savedProjectRevision: null, savedDocumentRevision: null } });
  });
  await projectMenu(page);await page.getByLabel("Файл проекта", { exact: true }).setInputFiles({ name: "synthetic.foldcv", mimeType: "application/zip", buffer: readFileSync(path ?? "") });
  const retry = page.getByRole("button", { name: "Повторить сохранение открытого проекта", exact: true });await expect(retry).toBeVisible();
  expect(new URL(page.url()).searchParams.get("project")).toBe(before.projectId);expect((await currentWorkspace(page)).project?.document).toEqual(before.project?.document);
  await retry.click();await expect.poll(() => new URL(page.url()).searchParams.get("project")).toBe(importedId);
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText(before.project?.document.profile.text.text ?? "");
  expect((await currentWorkspace(page)).projectId).not.toBe(before.projectId);
});

test("built example E4 task A18 saves Rules preserves document and reloads its revision and rewrite presets", async ({ page }) => {
  await createRewriteExample(page);const before = await currentWorkspace(page), calls = readFileSync(resolve(runRoot, "model-requests.json"), "utf8");
  await page.getByRole("button", { name: "Настройки", exact: true }).click();const text = page.getByLabel("Markdown правил", { exact: true });await expect(text).toBeEnabled();
  const original = await text.inputValue();const updated = original.replace("15 years", "20 years").replace("Сократи", "CUSTOM SHORTEN Сократи");expect(updated).not.toBe(original);
  await text.fill(updated);await page.getByRole("button", { name: "Сохранить правила", exact: true }).click();await expect(page.getByText("Правила сохранены.", { exact: false })).toBeVisible();
  await expect(page.getByText("Версия правил: 2", { exact: true })).toBeVisible();expect((await currentWorkspace(page)).project?.document).toEqual(before.project?.document);
  expect((await currentWorkspace(page)).undoSlots).toEqual(before.undoSlots);expect(readFileSync(resolve(runRoot, "model-requests.json"), "utf8")).toBe(calls);
  await page.reload();await page.getByRole("button", { name: "Настройки", exact: true }).click();await expect(page.getByLabel("Markdown правил", { exact: true })).toHaveValue(updated);
  await page.getByRole("button", { name: "Вернуться", exact: true }).click();const profile = before.project?.document.profile.text.text ?? "";
  await selectFields(page, "profile/text", 0, "profile/text", profile.length);await openSelectionAssistant(page);
  await page.getByRole("button", { name: "Сократить", exact: true }).click();await expect(page.getByLabel("Что изменить", { exact: true })).toHaveValue(/CUSTOM SHORTEN/);
  const sent = page.waitForRequest(request => new URL(request.url()).pathname.endsWith("/rewrite"));await page.getByRole("button", { name: "Обновить выделение", exact: true }).click();
  const raw: unknown = (await sent).postDataJSON();if (!isRewrite(raw)) throw new Error("Invalid rewrite capture");expect(raw.rulesSha256).not.toBe(before.rulesUsed?.sha256);
  await expect(page.locator('[data-field-content="profile/text"]')).toContainText("Яснее:");const after = await currentWorkspace(page);
  const rewritten = after.project?.operations.filter(operation => operation.kind === "rewrite_prose").at(-1);
  expect(rewritten?.rulesUsed?.revision).toBe(2);expect(rewritten?.rulesUsed?.markdown).toBe(updated);
});

test("built task A18 rejects missing preset headings without revision and preserves rule draft on storage error", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);await page.getByRole("button", { name: "Настройки", exact: true }).click();
  const text = page.getByLabel("Markdown правил", { exact: true });await expect(text).toBeEnabled();const original = await text.inputValue();
  await text.fill("Editorial text without presets");await page.getByRole("button", { name: "Сохранить правила", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("## Preset: shorten");await expect(page.getByRole("alert")).toContainText("## Preset: clarify");await expect(page.getByText("Версия правил: 1", { exact: true })).toBeVisible();
  await expect(text).toHaveValue("Editorial text without presets");const saved: unknown = await (await page.request.get(`${origin}/v1/settings/rules`)).json();expect(validateContract("rules_settings", saved)).toBe(true);
  expect(typeof saved === "object" && saved !== null && "markdown" in saved && saved.markdown).toBe(original);
  await text.fill(`${original}\nNew policy`);await page.route("**/settings/rules", route => route.request().method() === "PUT"
    ? route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: { code: "RULES_SAVE_FAILED" } }) }) : route.continue());
  await page.getByRole("button", { name: "Сохранить правила", exact: true }).click();await expect(page.getByRole("alert")).toContainText("Не удалось сохранить правила");await expect(text).toHaveValue(`${original}\nNew policy`);
  await page.unroute("**/settings/rules");await page.getByRole("button", { name: "Сохранить правила", exact: true }).click();await expect(page.getByText("Версия правил: 2", { exact: true })).toBeVisible();
  expect(existsSync(resolve(runRoot, "model-requests.json"))).toBe(false);
});

test("built task A18 delayed Rules acknowledgment keeps newer typing and stale comparison keeps the draft", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);await page.getByRole("button", { name: "Настройки", exact: true }).click();
  const text = page.getByLabel("Markdown правил", { exact: true });await expect(text).toBeEnabled();const original = await text.inputValue();let release: (() => void) | undefined, reached = false;
  const held = new Promise<void>(ready => { release = ready; });await page.route("**/settings/rules", async route => {
    if (route.request().method() !== "PUT") { await route.continue();return; }
    const response = await route.fetch();reached = true;await held;await route.fulfill({ response });
  });
  await text.fill(`${original}\nSubmitted policy`);await page.getByRole("button", { name: "Сохранить правила", exact: true }).click();await expect.poll(() => reached).toBe(true);
  await text.fill(`${original}\nNewer unsent policy`);release?.();await expect(page.getByText("Предыдущий текст правил сохранён.", { exact: false })).toBeVisible();await expect(text).toHaveValue(`${original}\nNewer unsent policy`);
  await page.unroute("**/settings/rules");const concurrent = await page.request.put(`${origin}/v1/settings/rules`, { headers: { Origin: origin }, data: { markdown: `${original}\nOther window policy`, baseRevision: 2 } });expect(concurrent.status()).toBe(200);
  await page.getByRole("button", { name: "Сохранить правила", exact: true }).click();await expect(page.getByRole("alert")).toContainText("изменены в другом окне");await expect(text).toHaveValue(`${original}\nNewer unsent policy`);
  await page.getByRole("button", { name: "Загрузить актуальную версию правил", exact: true }).click();await expect(page.getByLabel("Сохранённая версия правил", { exact: true })).toHaveValue(`${original}\nOther window policy`);
  await expect(text).toHaveValue(`${original}\nNewer unsent policy`);await expect(page.getByText("Версия правил: 3", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Сохранить правила", exact: true }).click();await expect(page.getByText("Версия правил: 4", { exact: true })).toBeVisible();expect(existsSync(resolve(runRoot, "model-requests.json"))).toBe(false);
});

test("built task A15 start shows local model disclosure and saved projects reopen without calls", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  const disclosure = page.getByRole("region", { name: "Хранение и модель", exact: true });await expect(disclosure).toContainText("запись на диск");await expect(disclosure).toContainText("до нажатия");await expect(disclosure).toContainText("модели через CLI");
  await expect(disclosure).toContainText("автоматической проверке правок");await expect(disclosure).toContainText("Автопроверку можно приостановить в настройках");
  expect(await disclosure.evaluate(element => { const button = document.querySelector(".next-create");return button !== null && (element.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0; })).toBe(true);
  await expect(page.getByRole("region", { name: "Сохранённые проекты", exact: true })).toContainText("Пока нет сохранённых проектов");
  expect(existsSync(resolve(runRoot, "connection-actions.json"))).toBe(false);expect(existsSync(resolve(runRoot, "model-requests.json"))).toBe(false);
  if (process.env.FOLDCV_EVIDENCE_ROOT) await page.screenshot({ path: resolve(process.env.FOLDCV_EVIDENCE_ROOT, "A15-start.png") });
  await createRewriteExample(page);const saved = await currentWorkspace(page), calls = readFileSync(resolve(runRoot, "model-requests.json"), "utf8");
  await newProject(page);const row = page.locator(`[data-start-project="${saved.projectId}"]`);await expect(row).toBeVisible();await row.getByRole("button").click();
  await expect(page.locator('[data-field-content="candidate/name"]')).toHaveText("Ирина Примерова");expect((await currentWorkspace(page)).projectId).toBe(saved.projectId);
  expect(readFileSync(resolve(runRoot, "model-requests.json"), "utf8")).toBe(calls);
});

test("built example E6 task A15 rejected file replacement cannot reactivate inactive paste or previous source", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);const raw = readFileSync(resolve(root, "tests/fixtures/recovery/E1.txt"));
  await page.getByLabel("Файл резюме", { exact: true }).setInputFiles({ name: "first.txt", mimeType: "text/plain", buffer: raw });
  await expect(page.getByRole("button", { name: "Создать резюме", exact: true })).toBeEnabled();const before = await currentWorkspace(page);
  await page.getByLabel("Или вставьте текст", { exact: true }).fill("Inactive paste must not be sent.");
  await page.getByLabel("Файл резюме", { exact: true }).setInputFiles({ name: "oversized.txt", mimeType: "text/plain", buffer: Buffer.alloc(6 * 1024 * 1024 + 1, 65) });
  await expect(page.getByRole("alert").first()).toBeVisible();await expect(page.getByText("Выбрано: oversized.txt", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Или вставьте текст", { exact: true })).toHaveValue("");await expect(page.getByRole("button", { name: "Создать резюме", exact: true })).toBeDisabled();
  expect((await currentWorkspace(page)).preDraft).toEqual(before.preDraft);expect(existsSync(resolve(runRoot, "model-requests.json"))).toBe(false);
  await page.getByLabel("Файл резюме", { exact: true }).setInputFiles({ name: "replacement.txt", mimeType: "text/plain", buffer: raw });await expect(page.getByRole("button", { name: "Создать резюме", exact: true })).toBeEnabled();
  expect((await currentWorkspace(page)).projectId).toBe(before.projectId);await page.getByRole("button", { name: "Создать резюме", exact: true }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });expect((await currentWorkspace(page)).projectId).toBe(before.projectId);
  await expect(page.locator('[data-field-content="candidate/name"]')).toHaveText("Ирина Примерова");
});

test("built task A15 real Generation stages support cancel and explicit retry while keeping input", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });writeFileSync(resolve(runRoot, "hold-normalization"), "Controlled pending normalization.");
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);await page.getByRole("button", { name: "Открыть пример", exact: true }).click();
  await page.getByRole("button", { name: "Создать резюме", exact: true }).click();const progress = page.getByRole("region", { name: "Создание резюме", exact: true });
  await expect(progress.locator('[data-stage="normalize_semantics"]')).toHaveAttribute("data-status", "running");await expect(progress.locator('[data-stage="draft_prose"]')).toHaveAttribute("data-status", "queued");
  const before = await currentWorkspace(page);if (process.env.FOLDCV_EVIDENCE_ROOT) await page.screenshot({ path: resolve(process.env.FOLDCV_EVIDENCE_ROOT, "A15-progress.png") });
  await page.getByRole("button", { name: "Отменить создание", exact: true }).click();await expect(page.getByText("Создание отменено", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Или вставьте текст", { exact: true })).toHaveValue(readFileSync(resolve(root, "tests/fixtures/recovery/E1.txt"), "utf8"));
  expect((await currentWorkspace(page)).projectId).toBe(before.projectId);rmSync(resolve(runRoot, "hold-normalization"));
  await page.getByRole("button", { name: "Повторить создание", exact: true }).click();await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  const after = await currentWorkspace(page);expect(after.projectId).toBe(before.projectId);expect(after.generations.at(-1)?.stages.every(stage => stage.status === "completed")).toBe(true);
  expect(after.project?.operations.filter(operation => operation.kind === "normalize_semantics" || operation.kind === "draft_prose").map(operation => operation.usage?.logicalAttempts)).toEqual([1, 1, 1]);
});

test("built example E6 task A15 drop and failed file recovery retain project identity before explicit creation", async ({ page }) => {
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);const raw = readFileSync(resolve(root, "tests/fixtures/recovery/E1.txt"), "utf8");
  const transfer = await page.evaluateHandle(text => { const value = new DataTransfer();value.items.add(new File([text], "dropped.txt", { type: "text/plain" }));return value; }, raw);
  await page.locator(".next-upload").dispatchEvent("drop", { dataTransfer: transfer });await expect(page.getByRole("button", { name: "Создать резюме", exact: true })).toBeEnabled();
  const before = await currentWorkspace(page);expect(existsSync(resolve(runRoot, "model-requests.json"))).toBe(false);
  await page.getByLabel("Файл резюме", { exact: true }).setInputFiles({ name: "broken.pdf", mimeType: "application/pdf", buffer: Buffer.from("Synthetic invalid PDF") });
  await expect(page.getByText("Доступного текста нет. Выберите другой файл или вставьте текст.", { exact: true })).toBeVisible();await expect(page.getByRole("button", { name: "Создать резюме", exact: true })).toBeDisabled();
  expect((await currentWorkspace(page)).projectId).toBe(before.projectId);expect(existsSync(resolve(runRoot, "model-requests.json"))).toBe(false);
  await page.getByLabel("Или вставьте текст", { exact: true }).fill(raw);await page.getByRole("button", { name: "Создать резюме", exact: true }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });const after = await currentWorkspace(page);
  expect(after.projectId).toBe(before.projectId);expect(after.project?.sources).toHaveLength(3);expect(after.project?.operations.filter(operation => operation.kind === "normalize_semantics" || operation.kind === "draft_prose")).toHaveLength(2);
});

test("built task A19 provider preflight failure retains submitted input saved identity and explicit creation", async ({ page }) => {
  writeFileSync(resolve(runRoot, "deny-creation"), "Controlled unavailable provider.");await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Открыть пример", exact: true }).click();await page.getByRole("button", { name: "Создать резюме", exact: true }).click();
  await expect(page.getByRole("alert").first()).toContainText("Подключите модель");await expect(page.locator(".next-save")).toHaveText("Сохранено");
  const before = await currentWorkspace(page);expect(before.preDraft?.sources).toHaveLength(1);expect(before.generations).toEqual([]);expect(existsSync(resolve(runRoot, "model-requests.json"))).toBe(false);
  await page.reload();await expect(page.getByLabel("Или вставьте текст", { exact: true })).toHaveValue(readFileSync(resolve(root, "tests/fixtures/recovery/E1.txt"), "utf8"));
  rmSync(resolve(runRoot, "deny-creation"));await page.getByRole("button", { name: "Создать резюме", exact: true }).click();await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  const after = await currentWorkspace(page);expect(after.projectId).toBe(before.projectId);expect(after.project?.sources).toHaveLength(1);expect(after.project?.operations).toHaveLength(2);
});

test("built example E5 task A19 source replacement restart retries the current source and invalidates old stages", async ({ page }) => {
  writeFileSync(resolve(runRoot, "multiple-examples"), "Controlled source switch.");writeFileSync(resolve(runRoot, "deny-draft"), "Controlled failed draft.");
  await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);await page.getByRole("button", { name: "Открыть пример", exact: true }).click();await page.getByRole("button", { name: "Создать резюме", exact: true }).click();
  await expect(page.getByText("Создание не завершено", { exact: true })).toBeVisible({ timeout: 30000 });const before = await currentWorkspace(page);
  rmSync(resolve(runRoot, "deny-draft"));await page.getByLabel("Файл резюме", { exact: true }).setInputFiles({ name: "replacement.txt", mimeType: "text/plain", buffer: readFileSync(resolve(root, "tests/fixtures/recovery/E2.txt")) });
  await expect(page.getByRole("button", { name: "Создать резюме", exact: true })).toBeEnabled();const selected = await currentWorkspace(page);await page.reload();
  await expect(page.getByText("Выбрано: replacement.txt", { exact: true })).toBeVisible();await page.getByRole("button", { name: "Повторить создание", exact: true }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });const after = await currentWorkspace(page);
  expect(after.projectId).toBe(before.projectId);expect(after.generations.at(-1)?.sourceIds).toEqual([selected.preDraft?.selectedSourceId]);await expect(page.locator('[data-field-content="candidate/name"]')).toHaveText("Алексей");
  expect(after.project?.operations.filter(operation => operation.kind === "normalize_semantics" || operation.kind === "draft_prose")).toHaveLength(4);
});

test("built example E5 task A19 backend restart repeats only DOCX with provider unavailable and preserves edited work", async ({ page }) => {
  writeFileSync(resolve(runRoot, "fail-export"), "Controlled DOCX failure.");await page.goto(`${origin}/next.html#secret=synthetic-next-secret-0123456789`);
  await page.getByRole("button", { name: "Открыть пример", exact: true }).click();await page.getByRole("button", { name: "Создать резюме", exact: true }).click();
  await expect(page.getByText("Документ готов. DOCX пока не удалось оформить; текст доступен для правок.", { exact: true })).toBeVisible({ timeout: 30000 });const before = await currentWorkspace(page);
  expect(before.generations.at(-1)?.status).toBe("failed");const calls = readFileSync(resolve(runRoot, "model-requests.json"), "utf8");
  await stopServer();rmSync(resolve(runRoot, "fail-export"));writeFileSync(resolve(runRoot, "deny-creation"), "Render has no provider dependency.");origin = await launch("E1");
  await page.goto(`${origin}/next.html?project=${before.projectId}#secret=synthetic-next-secret-0123456789`);await expect(page.locator('[data-field-content="profile/text"]')).toHaveText(before.project?.document.profile.text.text ?? "");
  expect(readFileSync(resolve(runRoot, "model-requests.json"), "utf8")).toBe(calls);await page.getByRole("button", { name: "Повторить создание", exact: true }).click();
  await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });const after = await currentWorkspace(page);
  expect(after.project?.document).toEqual(before.project?.document);expect(after.project?.facts).toEqual(before.project?.facts);expect(readFileSync(resolve(runRoot, "model-requests.json"), "utf8")).toBe(calls);
  await replaceFieldText(page, "profile/text", "Current edit after recovered export.");await expect(page.locator(".next-save")).toHaveText("Сохранено");
  const stale = await page.request.post(`${origin}/v1/projects/${before.projectId}/generations/${before.generations.at(-1)?.id}/retry`, { headers: { Origin: origin }, data: {} });expect(stale.status()).toBe(409);
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Current edit after recovered export.");expect(readFileSync(resolve(runRoot, "model-requests.json"), "utf8")).toBe(calls);
});

test("built example E7 task A16 document outline collapse and focus mode preserve editor buffers and shell actions", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });await createRewriteExample(page);const before = await currentWorkspace(page);
  await page.locator('[contenteditable="true"]').evaluate(root => root.setAttribute("data-instance", "stable-document"));
  await page.locator('[data-outline-section="profile"]').click();await expect(page.locator('[data-field-content="profile/text"]')).toBeInViewport();
  await page.keyboard.insertText("Layout addition. ");await expect(page.locator('[data-field-content="profile/text"]')).toContainText("Layout addition.");
  await page.getByRole("button", { name: "Режим фокуса", exact: true }).click();await expect(page.getByRole("navigation", { name: "Разделы документа", exact: true })).toBeHidden();
  await expect(page.locator('[contenteditable="true"]')).toHaveAttribute("data-instance", "stable-document");await page.keyboard.insertText("Focused addition. ");
  await page.getByRole("button", { name: "Выйти из режима фокуса", exact: true }).click();await expect(page.getByRole("navigation", { name: "Разделы документа", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Свернуть оглавление", exact: true }).click();await expect(page.locator('[data-outline-section="profile"]')).toBeHidden();
  await page.getByRole("button", { name: "Развернуть оглавление", exact: true }).click();await expect(page.locator('[data-field-content="profile/text"]')).toContainText("Focused addition.");
  await expect(page.locator('[contenteditable="true"]')).toHaveCount(1);await expect(page.locator('[contenteditable="true"]')).toHaveAttribute("data-instance", "stable-document");
  await page.locator('[data-outline-section="candidate"]').click();await expect(page.locator(".next-save")).toHaveText("Сохранено");const after = await currentWorkspace(page);
  expect(after.documentRevision).toBeGreaterThan(before.documentRevision);expect(after.project?.operations.filter(operation => operation.kind !== "reconcile_edits")).toHaveLength(2);
  for (const name of ["Сохранить проект", "Экспорт DOCX", "Настройки"]) await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
  if (process.env.FOLDCV_EVIDENCE_ROOT) await page.screenshot({ path: resolve(process.env.FOLDCV_EVIDENCE_ROOT, "A16-document-light.png") });
  await page.getByLabel("Тема", { exact: true }).selectOption("dark");if (process.env.FOLDCV_EVIDENCE_ROOT) await page.screenshot({ path: resolve(process.env.FOLDCV_EVIDENCE_ROOT, "A16-document-dark.png") });
  await page.setViewportSize({ width: 390, height: 844 });expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.locator('[data-outline-section="profile"]').click();await expect(page.locator('[data-field-content="profile/text"]')).toBeInViewport();
  if (process.env.FOLDCV_EVIDENCE_ROOT) await page.screenshot({ path: resolve(process.env.FOLDCV_EVIDENCE_ROOT, "A16-document-narrow.png") });
});

test("built example E7 task A16 document date structure and hidden controls stay connected to canonical fields", async ({ page }) => {
  await createRewriteExample(page);const before = await currentWorkspace(page), job = before.project?.document.jobs[0], period = job?.periods[0];if (!job || !period) throw new Error("Missing fixture job period");
  await page.locator('[data-outline-section="jobs"]').click();await page.getByRole("button", { name: "Дата: Начало работы", exact: true }).first().click();
  await expect(page.getByText("Год, месяц или день. Текст даты остаётся в документе.", { exact: true })).toBeVisible();await page.getByRole("button", { name: "Вернуться к тексту", exact: true }).click();
  await replaceFieldText(page, period.startText.fieldId, "2015-07");await page.locator('[data-outline-section="profile"]').click();await expect(page.locator(".next-save")).toHaveText("Сохранено");
  expect((await currentWorkspace(page)).project?.document.jobs[0]?.periods[0]?.startText.text).toBe("2015-07");
  await page.getByText("Разделы и строки", { exact: true }).click();await page.getByRole("button", { name: "Скрыть О специалисте", exact: true }).click();
  await expect(page.locator('.next-field[data-field-id="profile/text"]')).toHaveAttribute("data-hidden-record", "true");await expect(page.locator('.next-field[data-field-id="profile/text"]').getByText("Скрыто из DOCX", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Показать О специалисте", exact: true }).click();await expect(page.locator('.next-field[data-field-id="profile/text"]')).toHaveAttribute("data-hidden-record", "false");
  await page.getByRole("button", { name: "Добавить образование", exact: true }).click();await expect(page.locator('[data-field-content^="education:"]')).toHaveCount(8);
  expect((await currentWorkspace(page)).project?.document.education).toHaveLength(2);await expect(page.locator('[contenteditable="true"]')).toHaveCount(1);
});

test("built example E3a task A16 assistant captures selection beside the same document and presets only fill saved instructions", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });await createRewriteExample(page);const before = await currentWorkspace(page);
  await page.locator('[contenteditable="true"]').evaluate(root => root.setAttribute("data-instance", "stable-assistant"));
  const text = before.project?.document.profile.text.text ?? "";await selectFields(page, "profile/text", 0, "profile/text", text.length);await openSelectionAssistant(page);
  const panel = page.getByRole("complementary", { name: "Помощник текста" });await expect(panel.locator('[data-captured-field="profile/text"]')).toHaveText(text);
  const paper = await page.locator(".next-document").boundingBox(), bounds = await panel.boundingBox();if (!paper || !bounds) throw new Error("Missing document or assistant bounds");
  expect(paper.x + paper.width).toBeLessThanOrEqual(bounds.x);expect(bounds.x + bounds.width).toBeLessThanOrEqual(1280);
  const rules: unknown = await (await page.request.get(`${origin}/v1/settings/rules`)).json();if (!isRules(rules)) throw new Error("Invalid saved Rules");
  for (const [name, instruction] of [["Сократить", rules.presets.shorten], ["Яснее", rules.presets.clarify]] as const) {
    await page.getByRole("button", { name, exact: true }).click();await expect(page.getByLabel("Что изменить", { exact: true })).toHaveValue(instruction ?? "");
  }
  expect((await currentWorkspace(page)).project?.operations).toEqual(before.project?.operations);
  await expect(page.locator('[contenteditable="true"]')).toHaveCount(1);await expect(page.locator('[contenteditable="true"]')).toHaveAttribute("data-instance", "stable-assistant");
  if (process.env.FOLDCV_EVIDENCE_ROOT) await page.screenshot({ path: resolve(process.env.FOLDCV_EVIDENCE_ROOT, "A16-assistant-light.png") });
  await page.getByLabel("Тема", { exact: true }).selectOption("dark");if (process.env.FOLDCV_EVIDENCE_ROOT) await page.screenshot({ path: resolve(process.env.FOLDCV_EVIDENCE_ROOT, "A16-assistant-dark.png") });
  await page.setViewportSize({ width: 390, height: 844 });await expect(panel).toBeVisible();expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  if (process.env.FOLDCV_EVIDENCE_ROOT) await page.screenshot({ path: resolve(process.env.FOLDCV_EVIDENCE_ROOT, "A16-assistant-narrow.png") });
  await page.getByLabel("Что изменить", { exact: true }).focus();await page.keyboard.press("Escape");await expect(panel).toHaveCount(0);
  await expect(page.locator('[contenteditable="true"]')).toHaveAttribute("data-instance", "stable-assistant");expect(await page.evaluate(() => window.getSelection()?.toString())).toBe(text);
});

test("built task A16 assistant pending open cannot reappear after Settings closes its capture", async ({ page }) => {
  await createRewriteExample(page);let release: (() => void) | undefined;const held = new Promise<void>(ready => { release = ready; });let entered = false;
  await page.route("**/v1/settings/rules", async route => { if (!entered) { entered = true;await held; }await route.continue(); });
  const text = await page.locator('[data-field-content="profile/text"]').textContent() ?? "";await selectFields(page, "profile/text", 0, "profile/text", text.length);
  await page.getByRole("button", { name: "Улучшить выделение", exact: true }).click();await expect.poll(() => entered).toBe(true);
  await page.getByRole("button", { name: "Настройки", exact: true }).click();await expect(page.getByRole("heading", { name: "Настройки", exact: true })).toBeVisible();
  const delivered = page.waitForResponse(result => result.url().endsWith("/v1/settings/rules"));release?.();await delivered;
  await page.getByRole("button", { name: "Вернуться", exact: true }).click();await expect(page.getByRole("complementary", { name: "Помощник текста" })).toHaveCount(0);
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText(text);expect((await currentWorkspace(page)).project?.operations).toHaveLength(2);
});

test("built task A16 assistant source evidence stays beside the editor and closes by keyboard without content calls", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });await createRewriteExample(page);const before = await currentWorkspace(page), field = before.project?.document.jobs[0]?.context;if (!field) throw new Error("Missing context field");
  await selectFields(page, field.fieldId, 0, field.fieldId, field.text.length);await page.getByRole("button", { name: "Показать исходник", exact: true }).click();
  const panel = page.getByRole("complementary", { name: "Исходный контекст" });await expect(panel.locator("blockquote").first()).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Помощник текста" })).toHaveCount(0);expect((await currentWorkspace(page)).project?.operations).toEqual(before.project?.operations);
  if (process.env.FOLDCV_EVIDENCE_ROOT) await page.screenshot({ path: resolve(process.env.FOLDCV_EVIDENCE_ROOT, "A16-source-light.png") });
  await page.getByRole("button", { name: "Закрыть исходный контекст", exact: true }).focus();await page.keyboard.press("Escape");await expect(panel).toHaveCount(0);
  expect(await page.evaluate(() => window.getSelection()?.toString())).toBe(field.text);await expect(page.locator('[contenteditable="true"]')).toHaveCount(1);
});

test("built examples E1 E3 task A21 flow connects edit restore local portable reopen and DOCX without LibreOffice", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });await createRewriteExample(page, "/");const initial = await currentWorkspace(page), job = initial.project?.document.jobs[0];if (!job) throw new Error("Missing job");
  expect(initial.project?.operations).toHaveLength(2);expect(initial.project?.document.earlyCareer.text.text).toContain("2008–2009");
  const addition = "Подготовила инструкцию для дежурной смены.";await replaceFieldText(page, job.tasks.fieldId, addition);
  await selectFields(page, job.tasks.fieldId, 0, job.tasks.fieldId, 11);await openSelectionAssistant(page);await submitRewrite(page);
  await expect(page.locator(`[data-field-content="${job.tasks.fieldId}"]`)).toHaveText("Яснее: " + addition);
  await page.locator(`[data-field-content="${job.tasks.fieldId}"]`).click();await page.getByRole("button", { name: "Отменить правку блока", exact: true }).click();
  await expect(page.locator(`[data-field-content="${job.tasks.fieldId}"]`)).toHaveText(addition);
  await page.getByRole("button", { name: "Отменить правку блока", exact: true }).click();await expect(page.locator(`[data-field-content="${job.tasks.fieldId}"]`)).toHaveText(addition);
  await replaceFieldText(page, "profile/text", "Connected prior.");await page.locator('[data-outline-section="candidate"]').click();await expect(page.locator(".next-save")).toHaveText("Сохранено");
  await replaceFieldText(page, "profile/text", "Connected current.");await page.locator('[data-outline-section="jobs"]').click();await expect(page.locator(".next-save")).toHaveText("Сохранено");
  const saved = await currentWorkspace(page), calls = readFileSync(resolve(runRoot, "model-requests.json"), "utf8");await page.reload();
  await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Connected current.");const local = await currentWorkspace(page);
  expect(local.project?.document).toEqual(saved.project?.document);expect(local.undoSlots).toEqual(saved.undoSlots);expect(local.project?.sources).toEqual(initial.project?.sources);
  expect(readFileSync(resolve(runRoot, "model-requests.json"), "utf8")).toBe(calls);
  const portable = page.waitForEvent("download");await page.getByRole("button", { name: "Сохранить проект", exact: true }).click();const archiveFile = await portable, archivePath = await archiveFile.path();if (!archivePath) throw new Error("Missing archive download");
  const bytes = readFileSync(archivePath), entries = unzipSync(bytes), workspaceBytes = entries["workspace.json"];if (!workspaceBytes) throw new Error("Missing archived workspace");
  const raw: unknown = JSON.parse(new TextDecoder().decode(workspaceBytes));expect(validateContract("workspace_v5", raw)).toBe(true);
  const original = readFileSync(resolve(root, "tests/fixtures/recovery/E1.txt"));expect(Object.entries(entries).some(([path, bytes]) => path.startsWith("sources/") && Buffer.from(bytes).equals(original))).toBe(true);
  await projectMenu(page);await page.getByLabel("Файл проекта", { exact: true }).setInputFiles({ name: "connected.foldcv", mimeType: "application/zip", buffer: bytes });
  await expect.poll(() => new URL(page.url()).searchParams.get("project")).not.toBe(saved.projectId);await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Connected current.");
  const imported = await currentWorkspace(page);expect(imported.project?.document).toEqual(saved.project?.document);expect(imported.project?.facts).toEqual(saved.project?.facts);
  expect(imported.undoSlots).toEqual(saved.undoSlots);expect(imported.formattingAsOf).toEqual(saved.formattingAsOf);expect(imported.mutationReplay).toEqual([]);
  expect(readFileSync(resolve(runRoot, "model-requests.json"), "utf8")).toBe(calls);
  await exportCurrent(page);await expect(page.getByRole("button", { name: "Скачать DOCX", exact: true })).toBeEnabled();const docx = await downloadDocx(page, "connected.docx");
  expect(docx.xml).toContain(addition);expect(docx.xml).toContain("Connected current.");expect(docx.xml).not.toContain("Интеграционные тесты.");expect(docx.xml).not.toContain("mail@example.com");expect(Object.keys(docx.entries).some(path => path.endsWith(".pdf"))).toBe(false);
  expect(existsSync(resolve(runRoot, "converter-disabled"))).toBe(true);expect(readFileSync(resolve(runRoot, "model-requests.json"), "utf8")).toBe(calls);
  if (process.env.FOLDCV_EVIDENCE_ROOT) {
    writeFileSync(resolve(process.env.FOLDCV_EVIDENCE_ROOT, "A21-connected.foldcv"), bytes);writeFileSync(resolve(process.env.FOLDCV_EVIDENCE_ROOT, "A21-connected.docx"), docx.bytes);
    await page.screenshot({ path: resolve(process.env.FOLDCV_EVIDENCE_ROOT, "A21-export.png") });
  }
  await page.getByRole("button", { name: "К тексту", exact: true }).click();await page.locator('[data-outline-section="profile"]').click();
  await page.getByRole("button", { name: "Отменить правку блока", exact: true }).click();await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Connected prior.");
  await page.locator('[data-outline-section="jobs"]').click();await expect(page.locator(".next-save")).toHaveText("Сохранено");await page.reload();await expect(page.locator('[data-field-content="profile/text"]')).toHaveText("Connected prior.");
  if (process.env.FOLDCV_EVIDENCE_ROOT) await page.screenshot({ path: resolve(process.env.FOLDCV_EVIDENCE_ROOT, "A21-editor-reopen.png") });
  expect(readFileSync(resolve(runRoot, "model-requests.json"), "utf8")).toBe(calls);
});

test("built task A21 cutover default entry creates and reopens the same project while next and legacy stay explicit", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });await page.goto(`${origin}/#secret=synthetic-next-secret-0123456789`);
  await expect(page.locator('[data-app="foldcv-next"]')).toHaveCount(1);await expect(page.getByRole("heading", { name: "Из исходника — в готовое резюме", exact: true })).toHaveCount(0);
  await expect(page.getByText("Автопроверку можно приостановить в настройках.", { exact: false })).toBeVisible();
  if (process.env.FOLDCV_EVIDENCE_ROOT) await page.screenshot({ path: resolve(process.env.FOLDCV_EVIDENCE_ROOT, "A21-default-start.png") });
  await page.getByRole("button", { name: "Открыть пример", exact: true }).click();await page.getByRole("button", { name: "Создать резюме", exact: true }).click();await expect(page.getByText("Резюме готово", { exact: true })).toBeVisible({ timeout: 30000 });
  expect(new URL(page.url()).pathname).toBe("/");const initial = await currentWorkspace(page), calls = readFileSync(resolve(runRoot, "model-requests.json"), "utf8");
  await page.getByRole("button", { name: "Настройки", exact: true }).click();await expect(page.getByRole("heading", { name: "Настройки", exact: true })).toBeVisible();await page.getByRole("button", { name: "Вернуться", exact: true }).click();
  await projectMenu(page);await page.getByRole("button", { name: "Новое резюме", exact: true }).click();await expect(page.getByLabel("Или вставьте текст", { exact: true })).toHaveValue("");
  expect(new URL(page.url()).pathname).toBe("/");await page.locator(`[data-start-project="${initial.projectId}"]`).getByRole("button").click();await expect(page.locator('[data-field-content="candidate/name"]')).toHaveText("Ирина Примерова");
  expect(new URL(page.url()).pathname).toBe("/");expect((await currentWorkspace(page)).projectId).toBe(initial.projectId);expect(readFileSync(resolve(runRoot, "model-requests.json"), "utf8")).toBe(calls);
  for (const path of ["/", "/index.html", "/next.html", "/legacy.html"]) { const result = await page.request.get(`${origin}${path}`);expect(result.status()).toBe(200);expect(result.headers()["cache-control"]).toBe("no-store"); }
  await page.goto(`${origin}/next.html?project=${initial.projectId}`);await expect(page.locator('[data-app="foldcv-next"]')).toHaveCount(1);await expect(page.locator('[data-field-content="candidate/name"]')).toHaveText("Ирина Примерова");
  expect(readFileSync(resolve(runRoot, "model-requests.json"), "utf8")).toBe(calls);await page.goto(`${origin}/legacy.html`);await expect(page.getByRole("heading", { name: "Из исходника — в готовое резюме", exact: true })).toBeVisible();await expect(page.locator('[data-app="foldcv-next"]')).toHaveCount(0);
});

test("built task A21 cutover missing default bundle fails visibly while the explicit legacy entry remains usable", async ({ page }) => {
  rmSync(resolve(runRoot, "dist/index.html"));const result = await page.goto(`${origin}/`);expect(result?.status()).toBe(503);
  await expect(page.locator('[data-app="foldcv-next"]')).toHaveCount(0);const raw: unknown = await (await page.request.get(`${origin}/`)).json();
  expect(raw).toEqual({ error: { code: "FRONTEND_UNAVAILABLE", retryable: false, stage: "request" } });
  await page.goto(`${origin}/legacy.html`);await expect(page.getByRole("heading", { name: "Из исходника — в готовое резюме", exact: true })).toBeVisible();expect(existsSync(resolve(runRoot, "model-requests.json"))).toBe(false);
});
