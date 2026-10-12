import { createHash } from "node:crypto";
import { expect, test } from "@playwright/test";
import type { Route } from "@playwright/test";
import { zipSync } from "fflate";
import fixture from "../../../contracts/examples/render_request.json" with { type: "json" };
import type { PrepareRequest } from "../src/contracts/generated/prepare_request";
import type { RenderRequest } from "../src/contracts/generated/render_request";
import { acknowledgeVisibleWarnings } from "./export-review";

const prepared: RenderRequest = fixture as RenderRequest;
const docx = Uint8Array.from([0x50, 0x4b, 0x03, 0x04, 1]);
const pdf = new TextEncoder().encode("%PDF controlled preview");
const hash = (bytes: Uint8Array) => createHash("sha256").update(bytes).digest("hex");

function archive(request: RenderRequest): Buffer {
  const metadata = {
    snapshotId: request.snapshot.id, projectRevision: request.snapshot.projectRevision,
    snapshotSha256: request.snapshot.snapshotSha256, templateId: request.snapshot.templateId,
    templateVersion: request.snapshot.templateVersion, templatePackageSha256: request.snapshot.templatePackageSha256,
    rendererVersion: request.snapshot.rendererVersion, rendererSha256: request.snapshot.rendererSha256,
    pageCount: 1, docxSha256: hash(docx), pdfSha256: hash(pdf),
    capabilities: { editableDocx: true, pdfDerivedFromDocx: true, embeddedPdfFonts: true },
  };
  return Buffer.from(zipSync({ "resume.docx": docx, "resume.pdf": pdf,
    "render.json": new TextEncoder().encode(JSON.stringify(metadata)) }));
}

async function prepareRoute(route: Route): Promise<void> {
  const input = route.request().postDataJSON() as PrepareRequest;
  const request: RenderRequest = { ...prepared, baseRevision: input.project.revision,
    snapshot: { ...prepared.snapshot, projectRevision: input.project.revision },
    document: { ...prepared.document, candidate: { ...prepared.document.candidate,
      name: input.presentation.name, title: input.presentation.title } } };
  const ordered = (value: unknown): unknown => Array.isArray(value) ? value.map(ordered)
    : value && typeof value === "object" ? Object.fromEntries(Object.entries(value).sort(([left], [right]) =>
      left.localeCompare(right, "en")).map(([key, part]) => [key, ordered(part)])) : value;
  const { snapshotSha256: _oldHash, ...snapshot } = request.snapshot;
  void _oldHash;
  request.snapshot.snapshotSha256 = hash(new TextEncoder().encode(JSON.stringify(ordered({
    baseRevision: request.baseRevision, document: request.document, snapshot,
  }))));
  await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(request) });
}

test("old PDF remains visibly stale during a controlled replacement render", async ({ page }) => {
  await page.route("**/v1/prepare-render", prepareRoute);
  let calls = 0;
  let pending: Route | null = null;
  await page.route("**/v1/render", async (route) => {
    calls += 1;
    if (calls === 2) { pending = route; return; }
    const request = route.request().postDataJSON() as RenderRequest;
    await route.fulfill({ status: 200, contentType: "application/zip", body: archive(request) });
  });
  await page.goto("/legacy.html");
  await page.getByRole("button", { name: "Загрузить вымышленный пример" }).click();
  await page.getByRole("button", { name: "Обновить PDF" }).click();
  await expect(page.getByText("PDF готов", { exact: false })).toBeVisible();
  await page.getByLabel("Текст блока").fill("A cancelled draft.");
  await page.getByRole("button", { name: "Отменить ввод", exact: true }).click();
  await expect(page.getByText("PDF готов", { exact: false })).toBeVisible();
  await acknowledgeVisibleWarnings(page);
  await page.getByRole("button", { name: "3. Выгрузка" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать PDF" }).click();
  await download;
  expect(calls).toBe(1);
  await page.getByRole("button", { name: "2. Редактор" }).click();
  await page.getByRole("tab", { name: "Превью" }).click();
  await page.getByLabel("Текст блока").fill("A newer accepted profile.");
  await page.getByRole("button", { name: "Применить правку" }).click();
  await page.getByRole("button", { name: "Обновить PDF" }).click();
  await expect.poll(() => pending !== null).toBe(true);
  await expect(page.getByText(/PDF устарел.*сборка новой версии/)).toBeVisible();
  await expect(page.getByTitle("Превью PDF")).toBeVisible();
  const response = pending as Route | null;
  if (!response) throw new Error("missing pending render");
  const request = response.request().postDataJSON() as RenderRequest;
  await response.fulfill({ status: 200, contentType: "application/zip", body: archive(request) });
  await expect(page.getByText("PDF готов", { exact: false })).toBeVisible();
});

test("export shows progress and a render failure on its own screen", async ({ page }) => {
  await page.route("**/v1/prepare-render", prepareRoute);
  let pending: Route | null = null;
  await page.route("**/v1/render", (route) => { pending = route; });
  await page.goto("/legacy.html");
  await page.getByRole("button", { name: "Загрузить вымышленный пример" }).click();
  await acknowledgeVisibleWarnings(page);
  await page.getByRole("button", { name: "3. Выгрузка" }).click();
  await page.getByRole("button", { name: "Собрать и скачать PDF" }).click();
  await expect.poll(() => pending !== null).toBe(true);
  await expect(page.getByRole("status").getByText("Сборка документов…")).toBeVisible();
  const response = pending as Route | null;
  if (!response) throw new Error("missing pending render");
  await response.fulfill({ status: 500, body: "failed" });
  await expect(page.getByRole("alert")).toContainText("Не удалось подготовить или проверить документы");
});
